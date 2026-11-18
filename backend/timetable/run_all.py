"""對所有系所跑兩種方案，輸出 reports/timetable/*.json 與總表。
python -m backend.timetable.run_all [--time-limit 20]"""
from __future__ import annotations

import argparse
import json

from backend.ingest.load import ROOT, load_term
from backend.sim.engine import clean
from .check import all_depts, report

OUT = ROOT / "reports" / "timetable"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=20.0)
    ap.add_argument("--depts", nargs="*")
    a = ap.parse_args()
    cs = list(load_term(115, 1))
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for d in a.depts or all_depts(cs):
        row = {"dept": d}
        for sc in "AB":
            r = report(d, cs, sc, a.time_limit)
            (OUT / f"{d}_{sc}.json").write_text(json.dumps(clean(r), ensure_ascii=False), encoding="utf-8")
            row[sc] = {"status": r["status"], "retake_before": r["before"]["retake_score"],
                       "retake_after": r["after"]["retake_score"], "pairs_before": r["before"]["retake_pairs"],
                       "pairs_after": r["after"]["retake_pairs"], "moves": len(r["moves"]),
                       "model": r["model_objective"], "checker": r["checker_objective"],
                       "new_conflicts": r["after"]["teacher_violations"] + r["after"]["room_violations"] + r["after"]["class_required_conflicts"],
                       "missing": sum(len(c.get("missing", [])) for c in r["cohorts"]),
                       "load_before": r["before"]["class_load_excess"], "load_after": r["after"]["class_load_excess"]}
            print(d, sc, row[sc], flush=True)
        summary.append(row)
    if a.depts and (OUT / "summary.json").exists():          # 只重跑部分系所時，合併回原本的總表
        old = {r["dept"]: r for r in json.loads((OUT / "summary.json").read_text(encoding="utf-8"))}
        old.update({r["dept"]: r for r in summary})
        summary = [old[k] for k in sorted(old)]
    (OUT / "summary.json").write_text(json.dumps(clean(summary), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
