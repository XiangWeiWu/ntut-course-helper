"""匯出 GitHub Pages 靜態版所需的資料到 frontend/public/data/。

python -m scripts.export_static            # 全部（含 21 個模擬情境，約 5 分鐘）
python -m scripts.export_static --no-sim   # 只匯出課程資料
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from backend.domain.timeslots import slots_of
from backend.ingest.load import CAPACITY_META, ROOT, course_dept, load_term, parse_home_class
from backend.sim.calibrate import load_alpha
from backend.sim.engine import SimConfig, clean, run
from backend.sim.mechanisms.ntut import NTUTConfig
from backend.sim.population import home_classes
from backend.sim.utility import is_general

OUT = ROOT / "frontend" / "public" / "data"


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(name, round((OUT / name).stat().st_size / 1024), "KB")


def export_courses(year, sem):
    cs = load_term(year, sem)
    rows = []
    for c in cs:
        d = c.to_dict(brief=True)
        d["dept"] = course_dept(c)
        d["grades"] = sorted({h[1] for n in c.classes if (h := parse_home_class(n))})
        d["required"] = c.required
        d["general"] = is_general(c)
        d["slots"] = [f"{day}-{p}" for day, p in slots_of(c.mask)]
        rows.append(d)
    dump("courses.json", rows)
    dump("classes.json", [{"name": g.name, "dept": g.dept, "grade": g.grade, "size": g.size, "required": g.required}
                          for g in home_classes(list(cs))])
    dump("meta.json", {"year": year, "sem": sem, "capacityMeta": CAPACITY_META.get((year, sem), {})})


def export_reports(year, sem):
    by_id = {c.id: c for c in load_term(year, sem)}
    main = json.loads((ROOT / "reports" / f"sim_{year}_{sem}.json").read_text(encoding="utf-8"))
    demand = []
    for r in main["course_table"]:
        c = by_id.get(r["id"])
        if c:
            demand.append({**r, "teachers": c.teachers, "observed": c.people, "capacity": c.capacity,
                           "capacitySource": c.capacity_source, "dept": course_dept(c), "code": c.code,
                           "oversub": r["demand"] / max(c.capacity, 1)})
    dump("teacher_demand.json", demand)
    rep = {}
    for k, f in (("main", f"sim_{year}_{sem}.json"), ("fcfs", f"sim_{year}_{sem}_fcfs.json"),
                 ("sensitivity", "sensitivity.json"), ("validation", "validation.json")):
        p = ROOT / "reports" / f
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.pop("course_table", None)
            rep[k] = d
    dump("sim_report.json", rep)


def scenario_key(mech, prio, pa, capf):
    return f"{mech}|{prio}|{pa}|{capf}"


def export_scenarios(year, sem, seeds=3):
    alpha = load_alpha(year, sem)
    grid = [("fcfs", "-", "-")] + [("ntut", p, a) for p in (0, 7) for a in (0.0, 0.5, 0.9)]
    out = {}
    for mech, prio, pa in grid:
        for capf in (0.8, 1.0, 1.2):
            cfg = SimConfig(year=year, sem=sem, alpha=alpha, capacity_factor=capf, seeds=list(range(seeds)), mechanism=mech)
            if mech == "ntut":
                cfg.ntut = replace(NTUTConfig(), priority_days=prio, p_approve=pa)
            r = run(cfg)
            r.pop("course_table", None)
            r["top_oversubscribed"] = r["top_oversubscribed"][:12]
            out[scenario_key(mech, prio, pa, capf)] = r
            print("scenario", mech, prio, pa, capf, r["aggregate"]["welfare_mean"]["mean"])
    dump("scenarios.json", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sim", action="store_true")
    a = ap.parse_args()
    export_courses(115, 1)
    export_reports(115, 1)
    if not a.no_sim:
        export_scenarios(115, 1)
