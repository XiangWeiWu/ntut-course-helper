"""模擬結果指標。

- welfare_ratio_s = Σ_{c∈選上} u_sc / Σ_{c∈理想} u_sc（效用以 wishlist 效用 − 最低值平移為正）
- credit_fill_s = 選上選修學分 / 理想選修學分
- Gini：公平性（0 = 完全平均）
- arrival_spearman：到達時間與 welfare 的 Spearman 相關（越負代表「手速」越決定結果）
- 課程層級：需求（理想集合中出現次數）、選上、容量、超額比、滿額時間
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from .mechanisms.base import Outcome


def gini(x: np.ndarray) -> float:
    x = np.sort(np.asarray(x, float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def student_table(out: Outcome, students) -> pd.DataFrame:
    rows = []
    for s in students:
        u = out.utility[s.sid]
        floor = min(u.values()) if u else 0.0
        pos = lambda c: u.get(c, floor) - floor + 1.0
        ideal, got = out.ideal[s.sid], out.enrolled[s.sid]
        ui = sum(pos(c) for c in ideal)
        ug = sum(pos(c) for c in got)
        ci = sum(out.seats[c].credit for c in ideal)
        cg = sum(out.seats[c].credit for c in got)
        rows.append({
            "sid": s.sid, "class": s.home_class, "dept": s.dept, "grade": s.grade,
            "arrival": out.arrival[s.sid], "ideal_n": len(ideal), "got_n": len(got),
            "ideal_credit": ci, "got_credit": cg,
            "credit_fill": min(cg / ci, 1.0) if ci else 1.0,
            "welfare": min(ug / ui, 1.0) if ui else 1.0,
            "top1": bool(ideal) and ideal[0] in got,
        })
    return pd.DataFrame(rows)


def course_table(out: Outcome, names: dict[str, str]) -> pd.DataFrame:
    demand = Counter(c for v in out.ideal.values() for c in v)
    rows = []
    for cid, s in out.seats.items():
        d = demand.get(cid, 0)
        rows.append({"id": cid, "name": names.get(cid, cid), "capacity": s.capacity,
                     "demand": d, "enrolled": len(s.enrolled), "oversub": d / s.capacity if s.capacity else 0,
                     "full_at": s.full_at})
    return pd.DataFrame(rows).sort_values("oversub", ascending=False)


def summarize(st: pd.DataFrame, ct: pd.DataFrame, log: dict) -> dict:
    by_grade = st.groupby("grade")[["welfare", "credit_fill", "top1"]].mean().round(3)
    q = pd.qcut(st["arrival"].rank(method="first"), 5, labels=["最快20%", "20-40%", "40-60%", "60-80%", "最慢20%"])
    by_arrival = st.groupby(q, observed=True)[["welfare", "credit_fill", "top1"]].mean().round(3)
    return {
        "students": int(len(st)),
        "welfare_mean": round(float(st.welfare.mean()), 4),
        "credit_fill_mean": round(float(st.credit_fill.mean()), 4),
        "top1_rate": round(float(st.top1.mean()), 4),
        "welfare_gini": round(gini(st.welfare.values), 4),
        "arrival_spearman": round(float(st[["arrival", "welfare"]].corr("spearman").iloc[0, 1]), 4),
        "oversubscribed_courses": int((ct.oversub > 1).sum()),
        "full_courses": int(ct.full_at.notna().sum()),
        "by_grade": {int(k): v for k, v in by_grade.to_dict("index").items()},
        "by_arrival": {str(k): v for k, v in by_arrival.to_dict("index").items()},
        "server": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in log.items() if k != "queue_timeline"},
        "queue_timeline": log.get("queue_timeline", []),
    }


def aggregate(runs: list[dict]) -> dict:
    """多個 seed 的平均與 95% 區間（百分位數法）。"""
    keys = ["welfare_mean", "credit_fill_mean", "top1_rate", "welfare_gini", "arrival_spearman",
            "oversubscribed_courses", "full_courses"]
    out = {}
    for k in keys:
        v = np.array([r[k] for r in runs], float)
        out[k] = {"mean": round(float(v.mean()), 4),
                  "ci95": [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]}
    return out
