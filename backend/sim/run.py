"""CLI：python -m backend.sim.run --year 115 --sem 1 --seeds 5"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .calibrate import load_alpha
from .engine import SimConfig, run
from .mechanisms.fcfs import FCFSConfig
from .mechanisms.ntut import NTUTConfig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=115)
    ap.add_argument("--sem", type=int, default=1)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--capacity-factor", type=float, default=1.0)
    ap.add_argument("--servers", type=int, default=8)
    ap.add_argument("--service-time", type=float, default=0.05)
    ap.add_argument("--mechanism", choices=["ntut", "fcfs"], default="ntut")
    ap.add_argument("--priority-days", type=float, default=7.0)
    ap.add_argument("--no-calibration", action="store_true")
    ap.add_argument("--out", default="reports/sim.json")
    a = ap.parse_args()
    cfg = SimConfig(year=a.year, sem=a.sem, scale=a.scale, seeds=list(range(a.seeds)),
                    capacity_factor=a.capacity_factor,
                    fcfs=FCFSConfig(servers=a.servers, service_time=a.service_time),
                    alpha=None if a.no_calibration else load_alpha(a.year, a.sem),
                    mechanism=a.mechanism,
                    ntut=NTUTConfig(priority_days=a.priority_days, servers=a.servers, service_time=a.service_time))
    t = time.time()
    r = run(cfg)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps(r["aggregate"], ensure_ascii=False, indent=1))
    print(f"calibrated={cfg.alpha is not None}  {time.time() - t:.1f}s → {a.out}")


if __name__ == "__main__":
    main()
