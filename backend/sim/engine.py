"""把母體、代理人、機制、指標串起來。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from backend.domain.courses import Course
from backend.ingest.load import load_term
from .agents import UtilityAgent
from .mechanisms.base import Seat
from .mechanisms.fcfs import FCFSConfig, run_fcfs
from .mechanisms.ntut import NTUTConfig, run_ntut
from .metrics import aggregate, course_table, student_table, summarize
from .population import generate
from .utility import Betas, elective_pool


@dataclass
class SimConfig:
    year: int = 115
    sem: int = 1
    scale: float = 1.0                 # 母體縮放（1.0 = 估計的實際班級人數）
    seeds: list[int] = field(default_factory=lambda: [0])
    capacity_factor: float = 1.0       # 敏感度分析：所有選修名額 ×k
    max_list: int = 15
    betas: Betas = field(default_factory=Betas)
    fcfs: FCFSConfig = field(default_factory=FCFSConfig)
    mechanism: str = "ntut"            # "ntut"（北科兩週制度）| "fcfs"（純搶課）
    ntut: NTUTConfig = field(default_factory=NTUTConfig)
    alpha: dict[str, float] | None = None   # 校準後的課程吸引力


def run_once(courses: list[Course], cfg: SimConfig, seed: int, return_tables=False):
    rng = np.random.default_rng(seed)
    by_id = {c.id: c for c in courses}
    pool = elective_pool(courses, cfg.alpha)
    students = generate(courses, rng, cfg.scale)
    seats = {f.id: Seat(f.id, max(1, round(by_id[f.id].capacity * cfg.capacity_factor)), f.credit, f.mask,
                        dept=f.dept, general=f.general)
             for f in pool.feats}
    base_masks, budgets, wishlists = {}, {}, {}
    for s in students:
        m = 0
        for cid in s.required:
            m |= by_id[cid].mask
        base_masks[s.sid] = m
        budgets[s.sid] = max(0.0, s.credit_target - sum(by_id[c].credit for c in s.required))
        wishlists[s.sid] = UtilityAgent(s, pool, cfg.betas, rng, cfg.max_list).wishlist()
    if cfg.mechanism == "ntut":
        out = run_ntut(students, wishlists, seats, base_masks, budgets, rng, cfg.ntut)
    else:
        out = run_fcfs(students, wishlists, seats, base_masks, budgets, rng, cfg.fcfs)
    st = student_table(out, students)
    ct = course_table(out, {c.id: c.name for c in courses})
    summ = summarize(st, ct, out.log)
    if return_tables:
        return summ, st, ct
    return summ


def clean(o):
    """把 NaN/inf/numpy 型別轉成 JSON 可序列化的值。"""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if not np.isfinite(f) else f
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def run(cfg: SimConfig) -> dict:
    courses = list(load_term(cfg.year, cfg.sem))
    runs, last = [], None
    for sd in cfg.seeds:
        summ, st, ct = run_once(courses, cfg, sd, return_tables=True)
        runs.append(summ)
        last = (summ, st, ct)
    summ, st, ct = last
    by_id = {c.id: c for c in courses}
    top = ct.head(30).copy()
    top["teachers"] = top.id.map(lambda i: "、".join(by_id[i].teachers))
    top["observed_people"] = top.id.map(lambda i: by_id[i].people)
    top["capacity_source"] = top.id.map(lambda i: by_id[i].capacity_source)
    return clean({
        "config": {**{k: v for k, v in asdict(cfg).items() if k != "alpha"}, "calibrated": cfg.alpha is not None},
        "aggregate": aggregate(runs),
        "last_run": summ,
        "top_oversubscribed": top.to_dict("records"),
        "course_table": ct.to_dict("records"),
    })
