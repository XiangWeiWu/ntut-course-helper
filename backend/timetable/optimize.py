"""系所排課最佳化（OR-Tools CP-SAT）。

硬限制（不新增衝突）：搬動後不得「新增」教師撞期、教室撞期（單一教室的課）、同班必修互相衝堂。
  現況中已存在的重疊一律保留、不視為錯誤——資料無法區分「真的排錯」與刻意安排
  （例：設計工作室 8–11 位老師同時段分組授課、英文系同名平行班或分流課程同時開）。
目標（最小化，與 check.evaluate 定義相同）：
   Σ 重修衝堂：高年級課 u 與低年級必修 l 衝堂 → w(u) × risk(l) / k(l)
       w(u)=2（u 為必修，重修生兩門都得修）或 1（選修）；k(l)＝全校同名課的不同時段數（可改選他班）
+  Σ 同年級選修 × 同班必修衝堂 × 0.5
+  0.15 × 原本的上課節次中「不再使用」的節數（搬動量） + 0.05 × 可搬課排在第 1 節的節數
+  0.3 × 各班每日負擔超出節數：把「開給該班的所有課」的時段聯集視為該班學生可能面對的最重負擔，
       連續超過 3 節、每天超過 6 節的部分扣分（定義見 backend/domain/load.py；依據見 README）
現況永遠是可行解（原位置一定在選項中），並作為初始解提示 → 結果不會比現況差。
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from ortools.sat.python import cp_model

from backend.domain.courses import Course
from backend.domain.load import Balance, windows
from backend.domain.timeslots import DAYS, PERIODS
from .data import Unit, block_options, block_slots, dept_units, same_block, slots
from .risk import risk_of

W_SAME, W_MOVE, W_P1 = 0.5, 0.15, 0.05
W_LOAD = 0.3
CLASS_BALANCE = Balance(max_consec=3, max_daily=6)
SCALE = 100


@dataclass
class Pair:
    u: str
    l: str
    weight: float
    kind: str          # retake | same_grade


def alternatives(courses: list[Course]) -> dict[str, int]:
    pats = defaultdict(set)
    for c in courses:
        if c.mask and c.people > 0:
            pats[c.name].add(tuple(sorted(slots(c.time))))
    return {k: len(v) for k, v in pats.items()}


def build_pairs(units: list[Unit], courses_by_id: dict[str, Course], alt: dict[str, int]) -> tuple[list[Pair], dict]:
    req = [l for l in units if l.required and l.grades]
    risk = {l.uid: risk_of(courses_by_id[l.ids[0]]) for l in req}
    pairs = []
    for u in units:
        if not u.grades:
            continue
        for l in req:
            if l.uid == u.uid:
                continue
            if l.grade < u.grade:
                w = (2 if u.required else 1) * risk[l.uid]["risk"] / max(alt.get(l.name, 1), 1)
                pairs.append(Pair(u.uid, l.uid, round(w, 4), "retake"))
            elif not u.required and l.grade == u.grade and set(u.classes) & set(l.classes):
                pairs.append(Pair(u.uid, l.uid, W_SAME, "same_grade"))
    return pairs, risk


def conflict_neighbors(u: Unit, other_teachers: list[str], other_rooms: list[str], other_classes: list[str],
                       other_required: bool) -> bool:
    """兩個場次是否「不可同時上課」：共用教師、共用（單一）教室，或同班必修。"""
    return bool(set(u.teachers) & set(other_teachers) or set(u.room_keys) & set(other_rooms)
                or (u.required and other_required and set(u.classes) & set(other_classes)))


def fixed_blockers(u: Unit, units: list[Unit], courses: list[Course], mov_ids: set[str], movable_uids: set[str]) -> set[str]:
    """可搬場次 u 不能去的時段：與 u 不可同時上課的固定課所佔時段，扣掉「原本就重疊」的那幾節（現況保留）。"""
    us = slots(u.time)
    out = set()
    unit_of = {i: x for x in units for i in x.ids}
    for c in courses:
        if not c.mask or c.id in mov_ids or c.id in u.ids:
            continue
        x = unit_of.get(c.id)
        req = x.required if x else False
        cls = x.classes if x else []
        rooms = c.classrooms if len(c.classrooms) == 1 else []
        if conflict_neighbors(u, c.teachers, rooms, cls, req):
            out |= slots(c.time) - us
    return out


def solve_dept(dept: str, courses: list[Course], scenario: str = "A", time_limit: float = 20.0) -> dict:
    t0 = time.time()
    by_id = {c.id: c for c in courses}
    units = dept_units(dept, courses)
    U = {u.uid: u for u in units}
    mov = [u for u in units if u.movable(scenario)]
    mov_uids = {u.uid for u in mov}
    mov_ids = {i for u in mov for i in u.ids}
    alt = alternatives(courses)
    pairs, risk = build_pairs(units, by_id, alt)

    m = cp_model.CpModel()
    x: dict[tuple[str, int], list] = {}
    occ = defaultdict(list)
    obj = []
    for u in mov:
        blocked = fixed_blockers(u, units, courses, mov_ids, mov_uids)
        for bi, b in enumerate(u.blocks):
            opts = []
            for o in block_options(b):
                orig = same_block(o, b)
                s = block_slots(o)
                if s & blocked and not orig:
                    continue
                v = m.NewBoolVar(f"{u.uid}_{bi}_{o.day}{o.periods[0]}")
                m.AddHint(v, 1 if orig else 0)
                opts.append((o, v))
                for sl in s:
                    occ[(u.uid, sl)].append(v)
                obj.append((W_P1 * o.periods.count("1"), v))
            m.AddExactlyOne(v for _, v in opts)
            x[(u.uid, bi)] = opts
        for sl in {k[1] for k in occ if k[0] == u.uid}:
            m.Add(sum(occ[(u.uid, sl)]) <= 1)                       # 自己的區塊不重疊
        for sl in slots(u.time):                                     # 搬動量
            obj.append((W_MOVE, 1 - sum(occ.get((u.uid, sl), []))))
        if len({b.day for b in u.blocks}) == len(u.blocks) > 1:     # 原本分在不同天 → 維持
            for d in {o.day for i in range(len(u.blocks)) for o, _ in x[(u.uid, i)]}:
                m.Add(sum(v for i in range(len(u.blocks)) for o, v in x[(u.uid, i)] if o.day == d) <= 1)

    def possible(uid):
        if uid in mov_uids:
            return {k[1] for k in occ if k[0] == uid}
        return slots(U[uid].time)

    def occ_expr(uid: str, sl: str):
        if uid in mov_uids:
            return occ.get((uid, sl), []), 0
        return [], 1 if sl in slots(U[uid].time) else 0

    # 可搬 × 可搬：不可同時上課且原本不重疊 → 不得重疊
    for i, u in enumerate(mov):
        for v in mov[i + 1:]:
            if not conflict_neighbors(u, v.teachers, v.room_keys, v.classes, v.required):
                continue
            kept = slots(u.time) & slots(v.time)                     # 現況已重疊的節次：保留
            for sl in (possible(u.uid) & possible(v.uid)) - kept:
                m.Add(sum(occ[(u.uid, sl)]) + sum(occ[(v.uid, sl)]) <= 1)

    const = 0.0
    for p in pairs:
        common = possible(p.u) & possible(p.l)
        if not common:
            continue
        if p.u not in mov_uids and p.l not in mov_uids:
            const += p.weight
            continue
        y = m.NewBoolVar(f"pair_{p.u}_{p.l}")
        for sl in common:
            a, ca = occ_expr(p.u, sl)
            b, cb = occ_expr(p.l, sl)
            m.Add(y >= sum(a) + ca + sum(b) + cb - 1)
        obj.append((p.weight, y))

    # 各班每日負擔：班級時段聯集 U_k[s] ≥ 每門可搬課的佔用；有固定課佔用的節次為常數 1
    class_units = defaultdict(list)
    for u in units:
        for k in u.classes:
            class_units[k].append(u.uid)
    B = CLASS_BALANCE
    for k, uids in class_units.items():
        uv: dict[str, object] = {}
        for sl in set().union(*(possible(uid) for uid in uids)):
            if any(uid not in mov_uids and sl in slots(U[uid].time) for uid in uids):
                uv[sl] = 1
                continue
            vs = [v for uid in uids if uid in mov_uids for v in occ.get((uid, sl), [])]
            if vs:
                b = m.NewBoolVar("")
                for v in vs:
                    m.Add(b >= v)
                uv[sl] = b
        for w in windows(B.max_consec):
            if not all(s in uv for s in w):
                continue
            terms = [uv[s] for s in w]
            if all(isinstance(t, int) for t in terms):
                const += W_LOAD
                continue
            z = m.NewBoolVar("")
            m.Add(z >= sum(terms) - B.max_consec)
            obj.append((W_LOAD, z))
        for d in DAYS:
            day = [uv[f"{d}-{p}"] for p in PERIODS if f"{d}-{p}" in uv]
            if len(day) <= B.max_daily:
                continue
            if all(isinstance(t, int) for t in day):
                const += W_LOAD * (len(day) - B.max_daily)
                continue
            e = m.NewIntVar(0, len(day), "")
            m.Add(e >= sum(day) - B.max_daily)
            obj.append((W_LOAD, e))

    m.Minimize(sum(int(round(w * SCALE)) * v for w, v in obj if w))   # v 可為變數或線性式
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = 8
    st = sv.Solve(m)
    status = sv.StatusName(st)
    if st == cp_model.FEASIBLE:
        # 未證明最佳時，輔助變數（衝堂標記、負擔超出量）可能沒有收緊，回報的目標值會偏高。
        # 固定課表後再解一次，只讓輔助變數收緊 → 回報值＝這份課表的真實分數（與獨立檢查器可比）。
        for opts in x.values():
            for _, v in opts:
                m.Add(v == sv.Value(v))
        sv2 = cp_model.CpSolver()
        sv2.parameters.max_time_in_seconds = 10.0
        sv2.parameters.num_workers = 8
        if sv2.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            sv = sv2

    new_time = {}
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for u in mov:
            t = {d: [] for d in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]}
            for bi in range(len(u.blocks)):
                for o, v in x[(u.uid, bi)]:
                    if sv.Value(v):
                        t[o.day] += o.periods
            new_time[u.uid] = t
    return {
        "dept": dept, "scenario": scenario, "status": status, "seconds": round(time.time() - t0, 2),
        "model_objective": round(sv.ObjectiveValue() / SCALE + const, 2) if new_time else None,
        "units": units, "pairs": pairs, "risk": risk, "new_time": new_time, "alt": alt,
    }
