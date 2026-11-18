"""北科選課制度模擬（兩週，時間單位：小時）。

制度（依使用者描述）：
- Day 0 起：學生可選「本系開的課」與通識/博雅（全校開放）。他系的課要等到 Day 7（本系優先一週）。
- 先到先得；滿額時可申請「加簽」，由老師決定（延遲 1–3 天）。
- 有人退選才會釋出名額，其他人需「回來刷」才看得到。
- 選課期共 14 天。

學生行為：
- 每次登入（visit）依偏好由高到低逐一檢查清單中尚未取得的課：
  若「取得此課並退掉與之衝堂/超學分的低偏好課」能提高效用，就送出加選（atomic swap：拿到才退）。
  → 退選是內生的：學生換到更喜歡的課時，放掉的名額被釋出。
- 每個請求經過有限吞吐的伺服器（與 fcfs.py 相同的排隊/逾時模型）。
- 兩次開放（Day 0、Day 7）時幾乎所有人同時湧入；其間依個人頻率回訪（Poisson）。
- 被拒時以 p_request 申請加簽；老師在 已選 < 名額×(1+addsign_extra) 時以 p_approve 同意。
  預設 addsign_extra=0.23 取自資料：有備註上限的課中，超額者的中位超出比例為 22.7%（113-1～115-1，n=673）。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from .base import Outcome, Seat, ideal_set

H = 3600.0  # 秒/小時


@dataclass
class NTUTConfig:
    horizon_days: float = 14.0
    priority_days: float = 7.0        # 本系優先期長度；0 = 一開始全校開放
    general_open_day: float = 0.0     # 通識/博雅開放日
    median_arrival: float = 20.0      # 開放瞬間：到達中位數（秒）
    arrival_sigma: float = 1.0
    servers: int = 8
    service_time: float = 0.05        # 秒
    timeout: float = 30.0             # 秒
    think_time: float = 4.0           # 秒，兩次請求間隔
    visits_per_day: float = 1.5       # 回訪頻率中位數（個體異質，對數常態）
    visits_sigma: float = 0.7
    p_request: float = 0.3            # 被拒時申請加簽機率
    p_approve: float = 0.8            # 老師同意機率
    addsign_extra: float = 0.23       # 加簽上限 = 名額×(1+extra)
    addsign_delay_days: tuple = (1.0, 3.0)
    exo_drop: float = 0.02            # 每個已選課在期間內被外生退選的機率
    timeline_hours: float = 6.0


def run_ntut(students, wishlists, seats: dict[str, Seat], base_masks, budgets,
             rng: np.random.Generator, cfg: NTUTConfig = NTUTConfig()) -> Outcome:
    T_end = cfg.horizon_days * 24
    dept = {s.sid: s.dept for s in students}
    util = {s.sid: dict(wishlists[s.sid]) for s in students}
    held: dict[int, list[str]] = {s.sid: [] for s in students}
    mask = dict(base_masks)
    credits = {s.sid: 0.0 for s in students}
    rate = {s.sid: cfg.visits_per_day * float(rng.lognormal(0, cfg.visits_sigma)) / 24 for s in students}  # 次/小時
    asked_addsign: set[tuple[int, str]] = set()
    servers = [0.0] * cfg.servers
    heapq.heapify(servers)
    ev, seq = [], 0
    stats = {"requests": 0, "timeouts": 0, "rejections": 0, "swaps": 0, "addsign_requests": 0,
             "addsign_approved": 0, "exo_drops": 0, "visits": 0}
    waits = []
    got_time: dict[tuple[int, str], float] = {}
    nbin = int(T_end / cfg.timeline_hours) + 1
    tl_own, tl_out, tl_gen = [0] * nbin, [0] * nbin, [0] * nbin
    visits = {s.sid: 0 for s in students}

    def push(t, kind, sid, data=None):
        nonlocal seq
        heapq.heappush(ev, (t, seq, kind, sid, data)); seq += 1

    def open_at(sid, s: Seat) -> float:
        if s.general or s.dept is None:
            return cfg.general_open_day * 24
        return 0.0 if s.dept == dept[sid] else cfg.priority_days * 24

    def plan_swap(sid, cid):
        """回傳 (要退掉的課, 淨效用增益)；不可行回傳 None。"""
        s = seats[cid]
        if s.mask & base_masks[sid]:
            return None
        drop = [h for h in held[sid] if seats[h].mask & s.mask]
        cr = credits[sid] - sum(seats[h].credit for h in drop) + s.credit
        rest = sorted((h for h in held[sid] if h not in drop), key=lambda h: util[sid][h])
        while cr > budgets[sid] + 1e-9 and rest:
            h = rest.pop(0)
            drop.append(h)
            cr -= seats[h].credit
        if cr > budgets[sid] + 1e-9:
            return None
        gain = util[sid][cid] - sum(util[sid][h] for h in drop)
        return (drop, gain) if gain > 1e-9 else None

    def apply(sid, cid, drop, t, via_addsign=False):
        for h in drop:
            hs = seats[h]
            hs.enrolled.remove(sid)
            hs.released += 1
            held[sid].remove(h)
            mask[sid] &= ~hs.mask
            credits[sid] -= hs.credit
        s = seats[cid]
        s.enrolled.append(sid)
        if via_addsign:
            s.addsigned += 1
        if len(s.enrolled) >= s.capacity and s.full_at is None:
            s.full_at = t
        held[sid].append(cid)
        mask[sid] |= s.mask
        credits[sid] += s.credit
        got_time[(sid, cid)] = t
        stats["swaps"] += bool(drop)
        if rng.random() < cfg.exo_drop:
            push(t + rng.uniform(0, max(T_end - t, 0.0)), "exo_drop", sid, cid)

    def wanted(sid, t):
        """本次登入要依序嘗試的課（依偏好排序）：可選、未持有、有效用增益。"""
        return [cid for cid, _ in wishlists[sid]
                if cid not in held[sid] and open_at(sid, seats[cid]) <= t and plan_swap(sid, cid)]

    def schedule_visit(sid, t):
        nxt = t + rng.exponential(1 / rate[sid])
        # 下一個開放時點（Day 7）時大家會回來
        for o in (cfg.priority_days * 24, cfg.general_open_day * 24):
            if t < o < nxt:
                nxt = o + rng.lognormal(math.log(cfg.median_arrival), cfg.arrival_sigma) / H
        if nxt < T_end:
            push(nxt, "visit", sid)

    # 第一次開放：全部學生湧入
    first = {}
    for s in students:
        first[s.sid] = s.reaction * rng.lognormal(math.log(cfg.median_arrival), cfg.arrival_sigma)
        push(first[s.sid] / H, "visit", s.sid)

    while ev:
        t, _, kind, sid, data = heapq.heappop(ev)
        if t > T_end:
            break
        if kind == "visit":
            stats["visits"] += 1
            visits[sid] += 1
            todo = wanted(sid, t)
            if todo:
                push(t, "step", sid, todo)
            # 仍存在「能改善課表」但目前拿不到（已滿或尚未開放）的課 → 之後再回來刷
            if any(cid not in held[sid] and plan_swap(sid, cid) for cid, _ in wishlists[sid]):
                schedule_visit(sid, t)
        elif kind == "step":
            todo = data
            while todo and not plan_swap(sid, todo[0]):
                todo = todo[1:]
            if not todo:
                continue
            cid, rest = todo[0], todo[1:]
            s = seats[cid]
            if len(s.enrolled) >= s.capacity:
                # 畫面顯示已滿：不送出加選；可能申請加簽
                if (sid, cid) not in asked_addsign and rng.random() < cfg.p_request:
                    asked_addsign.add((sid, cid))
                    stats["addsign_requests"] += 1
                    push(t + rng.uniform(*cfg.addsign_delay_days) * 24, "addsign", sid, cid)
                if rest:
                    push(t + cfg.think_time / H, "step", sid, rest)
                continue
            stats["requests"] += 1
            free = heapq.heappop(servers)
            start = max(t, free)
            wait = (start - t) * H
            if wait > cfg.timeout:
                heapq.heappush(servers, free)
                stats["timeouts"] += 1
                push(t + (cfg.timeout + rng.exponential(5.0)) / H, "step", sid, todo)  # 重送同一門
                continue
            heapq.heappush(servers, start + cfg.service_time / H)
            waits.append(wait)
            push(start + cfg.service_time / H, "decide", sid, (cid, rest))
        elif kind == "decide":
            cid, rest = data
            s = seats[cid]
            pl = plan_swap(sid, cid)
            if pl and len(s.enrolled) < s.capacity:
                apply(sid, cid, pl[0], t)
            else:
                stats["rejections"] += 1
            if rest:
                push(t + rng.exponential(cfg.think_time) / H, "step", sid, rest)
        elif kind == "addsign":
            cid = data
            s = seats[cid]
            pl = plan_swap(sid, cid) if cid not in held[sid] else None
            limit = math.ceil(s.capacity * (1 + cfg.addsign_extra))
            if pl and len(s.enrolled) < limit and rng.random() < cfg.p_approve:
                apply(sid, cid, pl[0], t, via_addsign=True)
                stats["addsign_approved"] += 1
        elif kind == "exo_drop":
            cid = data
            if cid in held[sid]:
                s = seats[cid]
                s.enrolled.remove(sid)
                s.released += 1
                held[sid].remove(cid)
                mask[sid] &= ~s.mask
                credits[sid] -= s.credit
                stats["exo_drops"] += 1
                util[sid][cid] = -1e9          # 不再想要
                schedule_visit(sid, t)

    # 時間軸：每 timeline_hours 的累積持有座位（依最終持有者取得時間）
    for (sid, cid), tg in got_time.items():
        if cid not in held[sid]:
            continue
        s = seats[cid]
        arr = tl_gen if (s.general or s.dept is None) else (tl_own if s.dept == dept[sid] else tl_out)
        arr[min(int(tg / cfg.timeline_hours), nbin - 1)] += 1
    cum = lambda a: list(np.cumsum(a).astype(int))
    for s in students:  # 外生退選的課不計入 ideal/效用
        util[s.sid] = {k: v for k, v in util[s.sid].items() if v > -1e8}
    ideal = {s.sid: ideal_set([(c, u) for c, u in wishlists[s.sid] if c in util[s.sid]], seats,
                              base_masks[s.sid], budgets[s.sid]) for s in students}
    w = np.array(waits) if waits else np.zeros(1)
    held_days = [got_time[(sid, c)] / 24 for sid in held for c in held[sid]]
    log = {
        **stats,
        "wait_mean": float(w.mean()), "wait_p95": float(np.percentile(w, 95)), "wait_max": float(w.max()),
        "throughput_rps": cfg.servers / cfg.service_time,
        "visits_per_student": stats["visits"] / max(len(students), 1),
        "median_acquire_day": float(np.median(held_days)) if held_days else 0.0,
        "seats_addsigned": int(sum(s.addsigned for s in seats.values())),
        "seats_released": int(sum(s.released for s in seats.values())),
        "timeline": [{"day": i * cfg.timeline_hours / 24, "own_dept": a, "other_dept": b, "general": c}
                     for i, (a, b, c) in enumerate(zip(cum(tl_own), cum(tl_out), cum(tl_gen)))],
        "visits_by_student": visits,
    }
    return Outcome(held, ideal, util, first, seats, log)
