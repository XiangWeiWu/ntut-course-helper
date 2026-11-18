"""獨立檢查器＋每屆畢業檢查＋報告輸出。

evaluate() 不使用最佳化模型的任何變數或線性化，只用「課表 → 時段集合」直接逐項計算，
用來交叉驗證 CP-SAT 回報的目標值，以及確認沒有「新增」教師/教室撞期或同班必修衝堂。
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from functools import lru_cache

from backend.domain.courses import REQUIRED_TYPES, Course
from backend.ingest.load import RAW, SNAPSHOT, parse_home_class
from .data import DAY5, DAYSEQ, Unit, slots
from .optimize import W_MOVE, W_P1, solve_dept

DAY_ZH = {"sun": "日", "mon": "一", "tue": "二", "wed": "三", "thu": "四", "fri": "五", "sat": "六"}


def time_text(t: dict) -> str:
    return " ".join(f"{DAY_ZH[d]}{''.join(ps)}" for d, ps in t.items() if ps) or "—"


def evaluate(units: list[Unit], times: dict[str, dict], movable: set[str], pairs, courses: list[Course]) -> dict:
    """新增衝突＝不可同時上課（共用教師／共用單一教室／同班必修）的兩門課，在「原本沒有重疊的節次」上重疊。
    逐一比對每個被搬的場次與全校其他所有課（含本系其他場次），不使用模型的任何結構。"""
    S = {u.uid: slots(times.get(u.uid, u.time)) for u in units}
    O = {u.uid: slots(u.time) for u in units}
    U = {u.uid: u for u in units}
    in_units = {i for u in units for i in u.ids}
    occupants = [(f"u{u.uid}", set(u.teachers), set(u.room_keys), set(u.classes), u.required, O[u.uid], S[u.uid])
                 for u in units]
    occupants += [(f"c{c.id}", set(c.teachers), set(c.classrooms) if len(c.classrooms) == 1 else set(), set(), False,
                   slots(c.time), slots(c.time)) for c in courses if c.mask and c.id not in in_units]
    new = {"teacher": 0, "room": 0, "class": 0}
    seen = set()
    for uid in movable:
        u = U[uid]
        for key, ts, rs, cl, req, orig, now in occupants:
            if key == f"u{uid}" or frozenset((key, f"u{uid}")) in seen:
                continue
            seen.add(frozenset((key, f"u{uid}")))
            if not ((S[uid] & now) - (O[uid] & orig)):          # 只有原本就重疊的節次 → 不算新增
                continue
            new["teacher"] += bool(set(u.teachers) & ts)
            new["room"] += bool(set(u.room_keys) & rs)
            new["class"] += bool(u.required and req and set(u.classes) & cl)
    tv, rv, cv = new["teacher"], new["room"], new["class"]
    conflicts, retake, same = [], 0.0, 0.0
    for p in pairs:
        if S[p.u] & S[p.l]:
            conflicts.append(p)
            if p.kind == "retake":
                retake += p.weight
            else:
                same += p.weight
    moved_periods = 0
    p1 = 0
    for uid in movable:
        u = U[uid]
        if uid in times:
            moved_periods += len(slots(u.time) - slots(times[uid]))   # 原本節次中不再使用的節數
        p1 += sum(1 for sl in S[uid] if sl.endswith("-1"))
    total = retake + same + W_MOVE * moved_periods + W_P1 * p1
    upper_hit = defaultdict(set)
    for p in conflicts:
        if p.kind == "retake":
            upper_hit[U[p.u].grade].add(p.u)
    upper_all = defaultdict(set)
    for u in units:
        if u.grades:
            upper_all[u.grade].add(u.uid)
    return {
        "objective": round(total, 2), "retake_score": round(retake, 2), "same_grade_score": round(same, 2),
        "retake_pairs": sum(p.kind == "retake" for p in conflicts),
        "same_grade_pairs": sum(p.kind == "same_grade" for p in conflicts),
        "teacher_violations": tv, "room_violations": rv, "class_required_conflicts": cv,
        "moved_periods": moved_periods,
        "upper_affected": {g: f"{len(upper_hit[g])}/{len(upper_all[g])}" for g in sorted(upper_all) if g >= 2},
        "_conflicts": conflicts,
    }


# ---------------- 課程標準（各屆） ----------------
@lru_cache(maxsize=1)
def _std_snapshot() -> dict:
    p = SNAPSHOT / "standards.json.gz"
    if p.exists():
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {}


def standard(cohort: int) -> dict:
    p = RAW / str(cohort) / "standard.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")).get("四技", {})
    return _std_snapshot().get("standards", {}).get(str(cohort), {})


@lru_cache(maxsize=1)
def dept_fullnames() -> dict[str, str]:
    """本班簡稱（資工）→ 系所全名（資工系），取自 department.json。"""
    p = RAW / "115" / "1" / "department.json"
    if p.exists():
        out = {}
        for d in json.loads(p.read_text(encoding="utf-8")):
            for c in d["class"]:
                h = parse_home_class(c["name"])
                if h:
                    out.setdefault(h[0], d["name"])
        return out
    return _std_snapshot().get("dept_map", {})


def write_snapshot(cohorts=(112, 113, 114, 115)):
    keep = lambda d: {"credits": d["credits"], "courses": [
        {k: c[k] for k in ("year", "sem", "type", "name", "credit")} for c in d["courses"]]}
    data = {"dept_map": dept_fullnames(),
            "standards": {str(y): {k: keep(v) for k, v in standard(y).items()} for y in cohorts}}
    with gzip.open(SNAPSHOT / "standards.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def cohort_check(dept: str, units: list[Unit], times: dict, courses: list[Course], year=115, sem=1) -> list[dict]:
    full = dept_fullnames().get(dept)
    out = []
    all_names = {c.name for c in courses}
    for g in (1, 2, 3, 4):
        cohort = year - g + 1
        std = standard(cohort)
        keys = [k for k in std if full and (k == full or k.startswith(full + "【"))] if full else []
        if not keys:
            out.append({"grade": g, "cohort": cohort, "standard": None, "note": "查無對應課程標準"})
            continue
        for key in keys:
            items = [c for c in std[key]["courses"] if c["year"] == str(g) and c["sem"] == str(sem) and c["type"] in REQUIRED_TYPES]
            mine = [u for u in units if g in u.grades]
            offered = {u.name for u in mine}
            missing = [c["name"] for c in items if c["name"] not in offered]
            matched = [u for u in mine if u.required and u.name in {c["name"] for c in items}]
            clash = []
            for i, a in enumerate(matched):
                for b in matched[i + 1:]:
                    if set(a.classes) & set(b.classes) and slots(times.get(a.uid, a.time)) & slots(times.get(b.uid, b.time)):
                        clash.append(f"{a.name} × {b.name}")
            out.append({"grade": g, "cohort": cohort, "standard": key,
                        "required": len(items), "credits": sum(float(c["credit"]) for c in items),
                        "missing": [{"name": n, "elsewhere": n in all_names} for n in missing],
                        "clashes": sorted(set(clash)),
                        "graduation_credits": std[key]["credits"].get("最低畢業學分數")})
    return out


# ---------------- 報告 ----------------
def report(dept: str, courses: list[Course], scenario: str = "A", time_limit: float = 20.0) -> dict:
    r = solve_dept(dept, courses, scenario, time_limit)
    units, pairs, risk = r["units"], r["pairs"], r["risk"]
    U = {u.uid: u for u in units}
    movable = {u.uid for u in units if u.movable(scenario)}
    before = evaluate(units, {}, movable, pairs, courses)
    after = evaluate(units, r["new_time"], movable, pairs, courses) if r["new_time"] else before

    def conflict_rows(ev, times):
        rows = []
        for p in sorted(ev["_conflicts"], key=lambda p: -p.weight):
            if p.kind != "retake":
                continue
            u, l = U[p.u], U[p.l]
            rows.append({"upper": u.name, "upper_grade": u.grade, "upper_required": u.required,
                         "upper_time": time_text(times.get(u.uid, u.time)),
                         "lower": l.name, "lower_grade": l.grade, "lower_time": time_text(times.get(l.uid, l.time)),
                         "risk": risk[l.uid]["risk"], "alternatives": r["alt"].get(l.name, 1), "weight": p.weight})
        return rows[:40]

    moves = []
    for uid, t in r["new_time"].items():
        u = U[uid]
        if slots(t) != slots(u.time):
            moves.append({"ids": u.ids, "name": u.name, "teachers": u.teachers, "rooms": u.rooms,
                          "grade": u.grade, "required": u.required,
                          "from": time_text(u.time), "to": time_text(t)})
    strip = lambda e: {k: v for k, v in e.items() if not k.startswith("_")}
    risk_rows = sorted(({"name": U[k].name, "grade": U[k].grade, "teachers": U[k].teachers,
                         "alternatives": r["alt"].get(U[k].name, 1), **v} for k, v in risk.items()),
                       key=lambda x: -x["risk"])
    # 結構性限制：低年級必修已佔用多少平日日間節次（佔滿時任何排法都無法讓高年級課完全避開）
    total = len(DAY5) * len(DAYSEQ)
    occupancy = {}
    for g in (2, 3, 4):
        occ = set()
        for u in units:
            if u.required and u.grades and u.grade < g:
                occ |= {x for x in slots(r["new_time"].get(u.uid, u.time)) if x.split("-")[0] in DAY5 and x.split("-")[1] in DAYSEQ}
        occupancy[g] = {"occupied": len(occ), "total": total}
    return {
        "dept": dept, "scenario": scenario, "status": r["status"], "seconds": r["seconds"],
        "lower_required_occupancy": occupancy,
        "units": len(units), "movable": len(movable), "shared_fixed": sum(u.shared for u in units),
        "model_objective": r["model_objective"], "checker_objective": after["objective"],
        "before": strip(before), "after": strip(after),
        "moves": sorted(moves, key=lambda m: (m["grade"], m["name"])),
        "conflicts_before": conflict_rows(before, {}), "conflicts_after": conflict_rows(after, r["new_time"]),
        "cohorts": cohort_check(dept, units, r["new_time"], courses),
        "cohorts_before": cohort_check(dept, units, {}, courses),
        "risk": risk_rows,
    }


def all_depts(courses: list[Course]) -> list[str]:
    cnt = defaultdict(int)
    for c in courses:
        for n in c.classes:
            if (h := parse_home_class(n)):
                cnt[h[0]] += 1
    return sorted(d for d, n in cnt.items() if n >= 8)
