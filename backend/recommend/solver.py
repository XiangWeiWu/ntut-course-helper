"""自動排課：CP-SAT 最大化偏好分數。

硬限制：不衝堂（每個節次最多一門）、學分介於 [min,max]、必選課一定排入、排除課不排。
同名課（多個開課班）至多選一；必選課豁免（同課可能拆成多個課號），且排除與必選課同名的其他班。產生 k 組解：每找到一組，就加入「不得與既有解完全相同」的 no-good cut。
"""
from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from backend.domain.courses import Course
from backend.domain.timeslots import slots_of


def solve(courses: list[Course], scores: dict[str, float], min_credit: float = 0, max_credit: float = 25,
          must: list[str] = (), k: int = 3, time_limit: float = 5.0) -> list[dict]:
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
    cr = sum(int(round(c.credit * 10)) * x[c.id] for c in cand)
    m.Add(cr >= int(min_credit * 10))
    m.Add(cr <= int(max_credit * 10))
    m.Maximize(sum(int(round(scores.get(c.id, 0) * 100)) * x[c.id] for c in cand))
    sols = []
    for _ in range(k):
        sv = cp_model.CpSolver()
        sv.parameters.max_time_in_seconds = time_limit
        st = sv.Solve(m)
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        chosen = [c for c in cand if sv.Value(x[c.id])]
        sols.append({"courses": [c.id for c in chosen], "credits": sum(c.credit for c in chosen),
                     "score": sum(scores.get(c.id, 0) for c in chosen),
                     "optimal": st == cp_model.OPTIMAL})
        m.AddBoolOr([x[c.id].Not() for c in chosen] + [x[c.id] for c in cand if c not in chosen])
    return sols
