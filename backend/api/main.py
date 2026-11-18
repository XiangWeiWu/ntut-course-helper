"""FastAPI：uvicorn backend.api.main:app --reload"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.domain.conflicts import find_conflicts, total_credits
from backend.domain.courses import COURSE_TYPES
from backend.domain.timeslots import DAYS, PERIOD_TIMES, PERIODS, slots_of
from backend.ingest.load import (CAPACITY_META, ROOT, available_terms, course_dept, course_key, load_standards,
                                 load_term, parse_home_class, save_override)
from backend.recommend.solver import solve
from backend.sim.calibrate import load_alpha
from backend.sim.engine import SimConfig, run
from backend.sim.mechanisms.fcfs import FCFSConfig
from backend.sim.mechanisms.ntut import NTUTConfig
from backend.sim.population import home_classes

app = FastAPI(title="NTUT 選課系統雛形")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def term(year, sem):
    try:
        return {c.id: c for c in load_term(year, sem)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/meta")
def meta():
    load_term(115, 1)
    return {"capacityMeta": {f"{k[0]}-{k[1]}": v for k, v in CAPACITY_META.items()},
            "terms": available_terms(), "days": DAYS, "periods": PERIODS, "periodTimes": PERIOD_TIMES,
            "courseTypes": COURSE_TYPES}


@app.get("/api/courses")
def courses(year: int = 115, sem: int = 1, q: str = "", dept: str = "", type: str = "",
            day: str = "", period: str = "", english: bool = False, limit: int = 200):
    out = []
    for c in term(year, sem).values():
        if q and q not in c.name and q not in c.name_en and not any(q in t for t in c.teachers) and q != c.id:
            continue
        if dept and dept != (course_dept(c) or "") and not any(dept in n for n in c.classes):
            continue
        if type and c.type not in type:
            continue
        if day and not c.time.get(day):
            continue
        if period and not any(period in v for v in c.time.values()):
            continue
        if english and c.language != "英語":
            continue
        out.append(c.to_dict(brief=True))
        if len(out) >= limit:
            break
    return out


@app.get("/api/courses/{cid}")
def course(cid: str, year: int = 115, sem: int = 1):
    c = term(year, sem).get(cid)
    if not c:
        raise HTTPException(404)
    return c.to_dict()


@app.get("/api/classes")
def classes(year: int = 115, sem: int = 1):
    return [{"name": g.name, "dept": g.dept, "grade": g.grade, "size": g.size, "required": g.required}
            for g in home_classes(list(term(year, sem).values()))]


class CheckReq(BaseModel):
    year: int = 115
    sem: int = 1
    ids: list[str]


@app.post("/api/schedule/check")
def check(r: CheckReq):
    t = term(r.year, r.sem)
    cs = [t[i] for i in r.ids if i in t]
    return {"conflicts": find_conflicts(cs), "credits": total_credits(cs)}


class SolveReq(BaseModel):
    year: int = 115
    sem: int = 1
    home_class: str | None = None
    favorites: dict[str, float] = Field(default_factory=dict)   # course id → 1..5 偏好
    must: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    min_credit: float = 16
    max_credit: float = 25
    avoid_early: bool = False
    avoid_evening: bool = True
    k: int = 3
    groups: list[list[str]] = Field(default_factory=list)   # 每組至多選一門


@app.post("/api/schedule/solve")
def schedule_solve(r: SolveReq):
    t = term(r.year, r.sem)
    must = list(r.must)
    dept = grade = None
    if r.home_class:
        g = next((g for g in home_classes(list(t.values())) if g.name == r.home_class), None)
        if g:
            dept, grade = g.dept, g.grade
            mask = 0
            for cid in g.required:                     # 預排必修（去衝堂）
                if not (t[cid].mask & mask):
                    must.append(cid)
                    mask |= t[cid].mask
    scores = {}
    for c in t.values():
        s = r.favorites.get(c.id)
        if c.id in r.exclude or not c.mask or c.people == 0 or (c.credit <= 0 and s is None):
            continue
        if s is None:
            if c.required:
                continue
            d = course_dept(c)
            hc = [h for n in c.classes if (h := parse_home_class(n))]
            if dept and d == dept and (not grade or any(h[1] == grade for h in hc)):
                s = 0.6
            elif c.type == "☆":
                s = 0.3
            else:
                continue
        sl = slots_of(c.mask)
        if r.avoid_early:
            s -= 0.4 * sum(p == "1" for _, p in sl)
        if r.avoid_evening:
            s -= 0.4 * sum(p in "ABCD" for _, p in sl)
        scores[c.id] = s * max(c.credit, 1)     # 0 學分的收藏課（如體育重修）仍有分數
    sols = solve(list(t.values()), scores, r.min_credit, r.max_credit, must, r.k, groups=r.groups)
    if not sols:
        raise HTTPException(422, "找不到可行課表（必修衝堂或學分範圍無法滿足）")
    for s in sols:
        s["courses"] = [t[i].to_dict(brief=True) for i in s["courses"]]
    return sols


@lru_cache(maxsize=1)
def _report(name):
    p = ROOT / "reports" / name
    if not p.exists():
        raise HTTPException(404, f"{name} 尚未產生，請先執行模擬（見 README）")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/sim/report")
def sim_report():
    r = dict(_report("sim_115_1.json"))
    r.pop("course_table", None)
    out = {"main": r}
    try:
        f = dict(_report("sim_115_1_fcfs.json"))
        f.pop("course_table", None)
        out["fcfs"] = f
    except HTTPException:
        out["fcfs"] = None
    for k, f in (("sensitivity", "sensitivity.json"), ("validation", "validation.json")):
        try:
            out[k] = _report(f)
        except HTTPException:
            out[k] = None
    return out


class SimReq(BaseModel):
    seeds: int = Field(3, ge=1, le=10)
    scale: float = Field(1.0, gt=0, le=2)
    capacity_factor: float = Field(1.0, gt=0, le=3)
    servers: int = Field(8, ge=1, le=256)
    service_time: float = Field(0.05, gt=0, le=2)
    median_arrival: float = Field(20.0, gt=0, le=600)
    timeout: float = Field(30.0, gt=0, le=600)
    mechanism: str = Field("ntut", pattern="^(ntut|fcfs)$")
    priority_days: float = Field(7.0, ge=0, le=14)
    p_request: float = Field(0.3, ge=0, le=1)
    p_approve: float = Field(0.8, ge=0, le=1)
    visits_per_day: float = Field(1.5, gt=0, le=24)


@app.post("/api/sim/run")
def sim_run(r: SimReq):
    cfg = SimConfig(year=115, sem=1, scale=r.scale, seeds=list(range(r.seeds)), capacity_factor=r.capacity_factor,
                    fcfs=FCFSConfig(servers=r.servers, service_time=r.service_time,
                                    median_arrival=r.median_arrival, timeout=r.timeout),
                    mechanism=r.mechanism,
                    ntut=NTUTConfig(servers=r.servers, service_time=r.service_time, median_arrival=r.median_arrival,
                                    timeout=r.timeout, priority_days=r.priority_days, p_request=r.p_request,
                                    p_approve=r.p_approve, visits_per_day=r.visits_per_day),
                    alpha=load_alpha(115, 1))
    res = run(cfg)
    res.pop("course_table", None)
    return res


@app.get("/api/teacher/demand")
def teacher_demand(teacher: str = "", dept: str = ""):
    """模擬需求 vs 名額。需求 = 無名額限制下想選此課的模擬學生數（多為下界估計，見報告）。"""
    t = term(115, 1)
    rows = []
    for r in _report("sim_115_1.json")["course_table"]:
        c = t.get(r["id"])
        if not c:
            continue
        if teacher and not any(teacher in x for x in c.teachers):
            continue
        if dept and (course_dept(c) or "") != dept:
            continue
        r = {**r, "capacity": c.capacity, "oversub": r["demand"] / max(c.capacity, 1)}   # 名額以最新（含教師回報）為準
        rows.append({**r, "teachers": c.teachers, "observed": c.people, "capacitySource": c.capacity_source,
                     "time": c.time, "advice": _advice(r, c.capacity_source)})
    return sorted(rows, key=lambda x: -x["oversub"])[:300]


class CapacityReq(BaseModel):
    course_id: str
    capacity: int = Field(ge=1, le=1000)
    note: str = Field("", max_length=200)


@app.post("/api/capacity")
def report_capacity(r: CapacityReq):
    """教師回報實際名額。以 課號code+教師 為鍵，下學期同一門課自動沿用。
    雛形未做身分驗證：正式上線需接學校 SSO，只允許授課教師本人修改。"""
    c = term(115, 1).get(r.course_id)
    if not c:
        raise HTTPException(404)
    save_override(course_key(c), r.capacity, r.note)
    c2 = term(115, 1)[r.course_id]
    return {"id": c2.id, "capacity": c2.capacity, "capacitySource": c2.capacity_source}


def _advice(r, src="notes"):
    if r["oversub"] < 0.4 and src not in ("notes", "teacher"):
        return "需求/名額偏低，但名額為推估（可能高估）：請先確認實際上限"
    if r["oversub"] >= 1.5:
        return "需求遠超名額：建議加開班或擴大教室"
    if r["oversub"] >= 1.0:
        return "接近滿額：可考慮小幅增加名額"
    if r["oversub"] < 0.4:
        return "需求偏低：檢視時段是否與必修衝堂"
    return "供需平衡"


@app.get("/api/dept/conflicts")
def dept_conflicts(dept: str, year: int = 115, sem: int = 1):
    """各年級必修占用的節次 vs 本系選修開在哪：找出「選修開在必修時段」造成學生無法修的情形。"""
    t = term(year, sem)
    grid = defaultdict(lambda: {"required": 0, "electives": []})
    for c in t.values():
        if (course_dept(c) or "") != dept or not c.mask:
            continue
        grades = sorted({h[1] for n in c.classes if (h := parse_home_class(n))})
        for day, p in slots_of(c.mask):
            for g in grades:
                cell = grid[f"{g}|{day}|{p}"]
                if c.required:
                    cell["required"] += 1
                else:
                    cell["electives"].append(c.name)
    return [{"grade": int(k.split("|")[0]), "day": k.split("|")[1], "period": k.split("|")[2], **v}
            for k, v in grid.items()]


_tt_cache: dict = {}


@app.get("/api/timetable/summary")
def timetable_summary():
    p = ROOT / "reports" / "timetable" / "summary.json"
    if not p.exists():
        raise HTTPException(404, "尚未產生，請執行 python -m backend.timetable.run_all")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/timetable/{dept}")
def timetable(dept: str, scenario: str = Query("A", pattern="^[AB]$"), recompute: bool = False):
    """系所排課最佳化報告：優先讀預先算好的結果；recompute=true 時即時重算（約 1–20 秒）。"""
    from backend.sim.engine import clean
    from backend.timetable.check import report
    p = ROOT / "reports" / "timetable" / f"{dept}_{scenario}.json"
    if p.exists() and not recompute:
        return json.loads(p.read_text(encoding="utf-8"))
    key = (dept, scenario)
    if recompute or key not in _tt_cache:
        _tt_cache[key] = clean(report(dept, list(term(115, 1).values()), scenario, 20.0))
    return _tt_cache[key]


@app.get("/api/grad/standards")
def grad_standards(cohort: int = Query(..., ge=100, le=130)):
    """某一屆（入學年）四技課程標準＋系所簡稱對照，供學生端畢業規劃使用。"""
    from backend.timetable.check import dept_fullnames, standard
    std = standard(cohort)
    if not std:
        raise HTTPException(404, f"查無 {cohort} 學年入學的課程標準")
    keep = lambda d: {"credits": d["credits"], "courses": [
        {k: c[k] for k in ("year", "sem", "type", "name", "credit")} for c in d["courses"]]}
    return {"cohort": cohort, "deptMap": dept_fullnames(), "standards": {k: keep(v) for k, v in std.items()}}


@app.get("/api/standards")
def standards(year: int = 115):
    return load_standards(year)


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
