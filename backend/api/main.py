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
from backend.ingest.load import ROOT, available_terms, course_dept, load_standards, load_term, parse_home_class
from backend.recommend.solver import solve
from backend.sim.calibrate import load_alpha
from backend.sim.engine import SimConfig, run
from backend.sim.mechanisms.fcfs import FCFSConfig
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
    return {"terms": available_terms(), "days": DAYS, "periods": PERIODS, "periodTimes": PERIOD_TIMES,
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
        if c.id in r.exclude or not c.mask or c.credit <= 0 or c.people == 0:
            continue
        s = r.favorites.get(c.id)
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
        scores[c.id] = s * c.credit
    sols = solve(list(t.values()), scores, r.min_credit, r.max_credit, must, r.k)
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
    return json.loads(p.read_text())


@app.get("/api/sim/report")
def sim_report():
    r = dict(_report("sim_115_1.json"))
    r.pop("course_table", None)
    out = {"main": r}
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


@app.post("/api/sim/run")
def sim_run(r: SimReq):
    cfg = SimConfig(year=115, sem=1, scale=r.scale, seeds=list(range(r.seeds)), capacity_factor=r.capacity_factor,
                    fcfs=FCFSConfig(servers=r.servers, service_time=r.service_time,
                                    median_arrival=r.median_arrival, timeout=r.timeout),
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
        rows.append({**r, "teachers": c.teachers, "observed": c.people, "capacitySource": c.capacity_source,
                     "time": c.time, "advice": _advice(r, c.capacity_source)})
    return sorted(rows, key=lambda x: -x["oversub"])[:300]


def _advice(r, src="notes"):
    if r["oversub"] < 0.4 and src != "notes":
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


@app.get("/api/standards")
def standards(year: int = 115):
    return load_standards(year)


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="static")
