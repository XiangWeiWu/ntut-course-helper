"""校準課程吸引力 α_c，使模擬選課人數貼近歷史觀察值。

方法（BLP 式收縮映射 + 設限處理）：
  α_c ← α_c + η · [log(obs_c + 1) − log(sim_c + 1)]
- obs_c 是「被名額截斷」的觀察值：若 obs_c ≥ capacity_c（已滿），真實需求 ≥ obs_c，
  因此只在 sim 需求 < obs 時往上推，sim 需求較大時不往下拉（右設限 / censored）。
- 未滿的課：用模擬的「需求」對齊觀察人數（未滿代表需求 ≈ 選上人數）。
- 模擬母體只有大學部本班學生，觀察人數含研究所/他部學生 → 以「大學部可能占比」無法得知，
  這是已知偏誤；故 obs 以 min(obs, 模擬母體可達上限) 處理並於報告註明。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from backend.ingest.load import ROOT, load_term
from .agents import UtilityAgent
from .mechanisms.base import Seat, ideal_set
from .population import generate
from .utility import Betas, elective_pool

CAL_DIR = ROOT / "data" / "processed"


def _demand(courses, alpha, betas, seed, scale):
    rng = np.random.default_rng(seed)
    by_id = {c.id: c for c in courses}
    pool = elective_pool(courses, alpha)
    seats = {f.id: Seat(f.id, by_id[f.id].capacity, f.credit, f.mask) for f in pool.feats}
    d = Counter()
    for s in generate(courses, rng, scale):
        m = 0
        for cid in s.required:
            m |= by_id[cid].mask
        budget = max(0.0, s.credit_target - sum(by_id[c].credit for c in s.required))
        wl = UtilityAgent(s, pool, betas, rng).wishlist()
        d.update(ideal_set(wl, seats, m, budget))
    return pool, d


def calibrate(year: int, sem: int, iters: int = 12, lr: float = 0.7, scale: float = 0.5,
              betas: Betas = Betas(), verbose=True) -> dict[str, float]:
    """scale<1 以抽樣母體加速；需求再除以 scale 還原。"""
    courses = list(load_term(year, sem))
    by_id = {c.id: c for c in courses}
    pool = elective_pool(courses)
    alpha = {f.id: -1.0 for f in pool.feats}
    for it in range(iters):
        pool, d = _demand(courses, alpha, betas, seed=1000 + it, scale=scale)
        err = []
        for f in pool.feats:
            c = by_id[f.id]
            obs, sim = c.people, d.get(f.id, 0) / scale
            g = np.log(obs + 1) - np.log(sim + 1)
            if obs >= c.capacity and g < 0:
                g = 0.0                               # 已滿：需求只知下界
            alpha[f.id] = float(np.clip(alpha[f.id] + lr * g, -8, 6))
            err.append(abs(obs - min(sim, c.capacity)))
        if verbose:
            print(f"iter {it}: MAE(enrolled) = {np.mean(err):.2f}")
    return alpha


def alpha_by_code(year: int, sem: int, alpha: dict[str, float]) -> dict[str, float]:
    """以 課號code+教師 為鍵，讓 α 可移轉到下一學期（課號 id 每學期不同）。"""
    out = {}
    for c in load_term(year, sem):
        if c.id in alpha:
            out[f"{c.code}|{'、'.join(c.teachers)}"] = alpha[c.id]
            out.setdefault(c.code, alpha[c.id])
    return out


def transfer(code_alpha: dict[str, float], year: int, sem: int, default: float = -1.0) -> dict[str, float]:
    out = {}
    for c in load_term(year, sem):
        k = f"{c.code}|{'、'.join(c.teachers)}"
        out[c.id] = code_alpha.get(k, code_alpha.get(c.code, default))
    return out


def save_alpha(year, sem, alpha):
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    (CAL_DIR / f"alpha_{year}_{sem}.json").write_text(json.dumps(alpha), encoding="utf-8")


def load_alpha(year, sem):
    p = CAL_DIR / f"alpha_{year}_{sem}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=115)
    ap.add_argument("--sem", type=int, default=1)
    a = ap.parse_args()
    save_alpha(a.year, a.sem, calibrate(a.year, a.sem))
