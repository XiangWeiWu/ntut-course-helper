"""自動排課：CP-SAT 最大化偏好分數。

硬限制：不衝堂（每個節次最多一門）、學分介於 [min,max]、必選課一定排入、排除課不排。
同名課（多個開課班）至多選一；必選課豁免（同課可能拆成多個課號），且排除與必選課同名的其他班。產生 k 組解：每找到一組，就加入「不得與既有解完全相同」的 no-good cut。
"""
from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from backend.domain.courses import Course
from backend.domain.load import Balance, load_excess, windows
from backend.domain.timeslots import DAYS, PERIODS, slots_of


def solve(courses: list[Course], scores: dict[str, float], min_credit: float = 0, max_credit: float = 25,
          must: list[str] = (), k: int = 3, time_limit: float = 5.0, groups: list[list[str]] = (),
          balance: Balance | None = None) -> list[dict]:
    """groups：每組課號至多選一門（例：被當的「學院指定向度」可用任一門同向度博雅課重修，但只需一門）。
    balance：分散每日負擔（連續上課、每日總節數超出上限時扣分），定義見 backend/domain/load.py。
    目標 = Σ 偏好分數 − weight ×（連續超出節數 + 每日超出節數）。"""
    cand = [c for c in courses if c.mask and (c.id in scores or c.id in must)]
    m = cp_model.CpModel()
    x = {c.id: m.NewBoolVar(c.id) for c in cand}
    slot = defaultdict(list)
    by_name = defaultdict(list)
    must_names = {c.name for c in cand if c.id in must}
    for c in cand:
        for s in slots_of(c.mask):
            slot[s].append(x[c.id])
        if c.id not in must:
            by_name[c.name].append(x[c.id])
    for vs in slot.values():
        m.AddAtMostOne(vs)
    for name, vs in by_name.items():
        # 同名課至多一門；必選課不受限（同一門課可能拆成多個課號），但已必選的課名不再加選同名班
        m.Add(sum(vs) == 0) if name in must_names else m.AddAtMostOne(vs)
    for cid in must:
        if cid in x:
            m.Add(x[cid] == 1)
    for grp in groups:
        vs = [x[i] for i in grp if i in x]
        if len(vs) > 1:
            m.AddAtMostOne(vs)
    cr = sum(int(round(c.credit * 10)) * x[c.id] for c in cand)
    m.Add(cr >= int(min_credit * 10))
    m.Add(cr <= int(max_credit * 10))
    obj = [int(round(scores.get(c.id, 0) * 100)) * x[c.id] for c in cand]
    if balance:
        W = int(round(balance.weight * 100))
        occ = {s: sum(vs) for s, vs in ((f"{d}-{p}", slot.get((d, p), [])) for d in DAYS for p in PERIODS) if vs}
        for w in windows(balance.max_consec):
            if all(s in occ for s in w):
                z = m.NewBoolVar("")
                m.Add(z >= sum(occ[s] for s in w) - balance.max_consec)
                obj.append(-W * z)
        for d in DAYS:
            day = [occ[f"{d}-{p}"] for p in PERIODS if f"{d}-{p}" in occ]
            if len(day) > balance.max_daily:
                e = m.NewIntVar(0, len(day), "")
                m.Add(e >= sum(day) - balance.max_daily)
                obj.append(-W * e)
    m.Maximize(sum(obj))
    sols = []
    for _ in range(k):
        sv = cp_model.CpSolver()
        sv.parameters.max_time_in_seconds = time_limit
        st = sv.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        chosen = [c for c in cand if sv.Value(x[c.id])]
        pref = sum(scores.get(c.id, 0) for c in chosen)
        ex = load_excess({f"{d}-{p}" for c in chosen for d, p in slots_of(c.mask)}, balance or Balance())
        pen = (balance.weight * (ex["consec_excess"] + ex["daily_excess"])) if balance else 0.0
        sols.append({"courses": [c.id for c in chosen], "credits": sum(c.credit for c in chosen),
                     "score": round(pref - pen, 4), "preference": round(pref, 4), "penalty": round(pen, 4),
                     "load": ex, "optimal": st == cp_model.OPTIMAL})
        m.AddBoolOr([x[c.id].Not() for c in chosen] + [x[c.id] for c in cand if c not in chosen])
    return sols
