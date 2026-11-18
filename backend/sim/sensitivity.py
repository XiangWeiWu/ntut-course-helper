"""敏感度分析：伺服器吞吐量與名額係數對公平性/效率的影響（每格多 seed 取平均）。"""
from __future__ import annotations

import json

from backend.ingest.load import ROOT, load_term
from .calibrate import load_alpha
from .engine import SimConfig, run_once
from .mechanisms.fcfs import FCFSConfig


def grid(year=115, sem=1, seeds=4):
    courses = list(load_term(year, sem))
    alpha = load_alpha(year, sem)
    rows = []
    for servers in (1, 2, 8, 32):
        for capf in (0.8, 1.0, 1.2):
            acc = []
            for sd in range(seeds):
                cfg = SimConfig(year=year, sem=sem, alpha=alpha, capacity_factor=capf,
                                fcfs=FCFSConfig(servers=servers))
                acc.append(run_once(courses, cfg, sd))
            m = lambda k: round(sum(r[k] for r in acc) / len(acc), 4)
            rows.append({"servers": servers, "throughput_rps": servers / 0.05, "capacity_factor": capf,
                         "welfare": m("welfare_mean"), "gini": m("welfare_gini"),
                         "arrival_spearman": m("arrival_spearman"), "top1": m("top1_rate"),
                         "wait_p95": round(sum(r["server"]["wait_p95"] for r in acc) / len(acc), 2),
                         "timeouts": round(sum(r["server"]["timeouts"] for r in acc) / len(acc), 1)})
            print(rows[-1])
    (ROOT / "reports" / "sensitivity.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return rows


if __name__ == "__main__":
    grid()
