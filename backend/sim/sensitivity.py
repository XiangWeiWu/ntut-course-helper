"""敏感度分析（北科制度）：本系優先天數 × 加簽同意率 × 名額係數；另附純 FCFS 對照。"""
from __future__ import annotations

import json
from dataclasses import replace

from backend.ingest.load import ROOT, load_term
from .calibrate import load_alpha
from .engine import SimConfig, clean, run_once
from .mechanisms.ntut import NTUTConfig


def _avg(acc, k):
    return round(sum(r[k] for r in acc) / len(acc), 4)


def grid(year=115, sem=1, seeds=3):
    courses = list(load_term(year, sem))
    alpha = load_alpha(year, sem)
    rows = []
    for mech, prio, pa in [("fcfs", None, None)] + [("ntut", p, a) for p in (0, 7) for a in (0.0, 0.5, 0.9)]:
        for capf in (0.8, 1.0, 1.2):
            acc = []
            for sd in range(seeds):
                cfg = SimConfig(year=year, sem=sem, alpha=alpha, capacity_factor=capf, mechanism=mech)
                if mech == "ntut":
                    cfg.ntut = replace(NTUTConfig(), priority_days=prio, p_approve=pa)
                acc.append(run_once(courses, cfg, sd))
            srv = lambda k: round(sum(r["server"].get(k, 0) or 0 for r in acc) / len(acc), 2)
            rows.append({"mechanism": mech, "priority_days": prio, "p_approve": pa, "capacity_factor": capf,
                         "welfare": _avg(acc, "welfare_mean"), "welfare_other_dept": _avg(acc, "welfare_other_dept"),
                         "gini": _avg(acc, "welfare_gini"), "arrival_spearman": _avg(acc, "arrival_spearman"),
                         "top1": _avg(acc, "top1_rate"), "visits_p90": round(sum(r["visits_p50_p90"][1] for r in acc) / len(acc), 1),
                         "addsigned": srv("seats_addsigned"), "released": srv("seats_released")})
            print(rows[-1])
    # 跨系成本是無資料可估的先驗：不同值需各自重新校準 α
    from .calibrate import calibrate
    from .utility import Betas
    for x in (0.0, 1.5, 3.0):
        b = Betas(cross_dept=x)
        a = calibrate(year, sem, betas=b, verbose=False)
        acc = [run_once(courses, SimConfig(year=year, sem=sem, alpha=a, betas=b), sd) for sd in range(seeds)]
        rows.append({"mechanism": "ntut", "priority_days": 7, "p_approve": 0.8, "capacity_factor": 1.0, "cross_dept": x,
                     "welfare": _avg(acc, "welfare_mean"), "welfare_other_dept": _avg(acc, "welfare_other_dept"),
                     "gini": _avg(acc, "welfare_gini"), "arrival_spearman": _avg(acc, "arrival_spearman"),
                     "top1": _avg(acc, "top1_rate"), "visits_p90": round(sum(r["visits_p50_p90"][1] for r in acc) / len(acc), 1),
                     "addsigned": round(sum(r["server"]["seats_addsigned"] for r in acc) / len(acc), 1),
                     "released": round(sum(r["server"]["seats_released"] for r in acc) / len(acc), 1)})
        print(rows[-1])
    (ROOT / "reports" / "sensitivity.json").write_text(json.dumps(clean(rows), ensure_ascii=False, indent=1))
    return rows


if __name__ == "__main__":
    grid()
