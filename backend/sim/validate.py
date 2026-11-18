"""Hold-out 驗證：在 (y0,s0) 校準 α → 依 課號+教師 移轉到 (y1,s1) → 模擬 → 與實際選課人數比較。

基準模型（baseline）：直接以「上一學期同課號+教師的人數」預測（無模型的天真預測），
若模擬不能贏過 baseline，代表代理人模型對「人數預測」沒有增益，只剩機制比較的價值。
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd

from backend.ingest.load import ROOT, load_term
from .calibrate import _demand, alpha_by_code, calibrate, save_alpha, transfer
from .engine import SimConfig, run_once
from .utility import Betas


def spearman(a, b):
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def validate(train=(114, 1), test=(115, 1), seeds=3):
    a_train = calibrate(*train, verbose=True)
    save_alpha(*train, a_train)
    code_alpha = alpha_by_code(*train, a_train)
    a_test = transfer(code_alpha, *test)
    courses = list(load_term(*test))
    by_id = {c.id: c for c in courses}
    prev = {}
    for c in load_term(*train):
        prev[f"{c.code}|{'、'.join(c.teachers)}"] = c.people
        prev.setdefault(c.code, c.people)

    sims = Counter()
    for sd in range(seeds):
        cfg = SimConfig(year=test[0], sem=test[1], alpha=a_test, seeds=[sd])
        _, _, ct = run_once(courses, cfg, sd, return_tables=True)
        for r in ct.itertuples():
            sims[r.id] += r.enrolled / seeds
    rows = []
    for cid, sim in sims.items():
        c = by_id[cid]
        k = f"{c.code}|{'、'.join(c.teachers)}"
        seen = k in prev or c.code in prev
        rows.append({"id": cid, "name": c.name, "obs": c.people, "sim": sim, "seen_before": seen,
                     "baseline": prev.get(k, prev.get(c.code, np.nan))})
    df = pd.DataFrame(rows)
    seen = df[df.seen_before]
    rep = {
        "train": train, "test": test, "n_courses": len(df), "n_seen_before": int(len(seen)),
        "sim_all": {"MAE": round(float((df.sim - df.obs).abs().mean()), 2), "spearman": round(spearman(df.sim, df.obs), 3)},
        "sim_seen": {"MAE": round(float((seen.sim - seen.obs).abs().mean()), 2), "spearman": round(spearman(seen.sim, seen.obs), 3)},
        "baseline_seen": {"MAE": round(float((seen.baseline - seen.obs).abs().mean()), 2),
                          "spearman": round(spearman(seen.baseline, seen.obs), 3)},
    }
    out = ROOT / "reports" / "validation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    df.to_csv(ROOT / "reports" / "validation_courses.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


if __name__ == "__main__":
    validate()
