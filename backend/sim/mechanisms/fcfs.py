"""先搶先贏（First-Come-First-Served）離散事件模擬。

時間軸：t=0 開放選課。
- 學生到達時間 T_s = reaction_s × LogNormal(ln(median_arrival), σ)：多數人在開放後數十秒內湧入。
- 每次「加選」是一個送到伺服器的請求；伺服器有 k 個 worker、每請求處理 service_time 秒，FIFO 排隊。
- 排隊等候超過 timeout 視為逾時（使用者看到錯誤），學生 backoff 後重送同一門課。
- 請求處理完成時才檢查名額 → 先完成者得；滿額則被拒，學生思考 think_time 後嘗試清單下一門。
- 學生在達成學分目標或清單用盡後離開。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np

from .base import Outcome, Seat, ideal_set


@dataclass
class FCFSConfig:
    median_arrival: float = 20.0   # 秒
    arrival_sigma: float = 1.0
    servers: int = 8
    service_time: float = 0.05     # 秒/請求 → 吞吐 = servers/service_time = 160 req/s
    timeout: float = 30.0
    backoff: float = 5.0
    think_time: float = 4.0        # 被拒/成功後到下一次請求的平均間隔
    credit_slack: float = 0.0      # 可超出學分預算的容忍（>0 時 credit_fill 可能 >1）


def run_fcfs(students, wishlists: dict[int, list[tuple[str, float]]], seats: dict[str, Seat],
             base_masks: dict[int, int], budgets: dict[int, float],
             rng: np.random.Generator, cfg: FCFSConfig = FCFSConfig()) -> Outcome:
    arrival = {s.sid: float(s.reaction * rng.lognormal(math.log(cfg.median_arrival), cfg.arrival_sigma))
               for s in students}
    ptr = {s.sid: 0 for s in students}
    mask = dict(base_masks)
    credits = {s.sid: 0.0 for s in students}
    enrolled = {s.sid: [] for s in students}
    servers = [0.0] * cfg.servers
    heapq.heapify(servers)

    # 事件：(time, seq, kind, sid, cid)；kind 0=學生行動（送出請求）, 1=伺服器處理完成
    ev, seq = [], 0
    for sid, t in arrival.items():
        heapq.heappush(ev, (t, seq, 0, sid, None)); seq += 1

    waits, timeouts, requests, rejections = [], 0, 0, 0
    queue_samples = []

    def next_course(sid):
        wl = wishlists[sid]
        while ptr[sid] < len(wl):
            cid = wl[ptr[sid]][0]
            s = seats[cid]
            if not (s.mask & mask[sid]) and credits[sid] + s.credit <= budgets[sid] + cfg.credit_slack \
                    and len(s.enrolled) < s.capacity:
                # 學生看得到「已滿」標示時不會送出（前端即時顯示剩餘名額的假設）
                return cid
            ptr[sid] += 1
        return None

    while ev:
        t, _, kind, sid, cid = heapq.heappop(ev)
        if kind == 0:
            if credits[sid] >= budgets[sid] - 0.5:
                continue
            cid = next_course(sid)
            if cid is None:
                continue
            requests += 1
            free = heapq.heappop(servers)
            start = max(t, free)
            wait = start - t
            queue_samples.append((t, wait))
            if wait > cfg.timeout:
                heapq.heappush(servers, free)  # 請求被丟棄，不占用 worker
                timeouts += 1
                heapq.heappush(ev, (t + cfg.timeout + rng.exponential(cfg.backoff), seq, 0, sid, None)); seq += 1
                continue
            heapq.heappush(servers, start + cfg.service_time)
            waits.append(wait)
            heapq.heappush(ev, (start + cfg.service_time, seq, 1, sid, cid)); seq += 1
        else:
            s = seats[cid]
            ok = len(s.enrolled) < s.capacity and not (s.mask & mask[sid])
            if ok:
                s.enrolled.append(sid)
                if len(s.enrolled) >= s.capacity and s.full_at is None:
                    s.full_at = t
                mask[sid] |= s.mask
                credits[sid] += s.credit
                enrolled[sid].append(cid)
            else:
                rejections += 1
            ptr[sid] += 1
            heapq.heappush(ev, (t + rng.exponential(cfg.think_time), seq, 0, sid, None)); seq += 1

    ideal = {s.sid: ideal_set(wishlists[s.sid], seats, base_masks[s.sid], budgets[s.sid]) for s in students}
    util = {s.sid: dict(wishlists[s.sid]) for s in students}
    w = np.array(waits) if waits else np.zeros(1)
    log = {
        "requests": requests, "timeouts": timeouts, "rejections": rejections,
        "wait_mean": float(w.mean()), "wait_p95": float(np.percentile(w, 95)), "wait_max": float(w.max()),
        "throughput_rps": cfg.servers / cfg.service_time,
        "queue_timeline": _bucket(queue_samples),
    }
    return Outcome(enrolled, ideal, util, arrival, seats, log)


def _bucket(samples, width=5.0, horizon=300.0):
    n = int(horizon / width)
    cnt, wsum = [0] * n, [0.0] * n
    for t, w in samples:
        i = int(t / width)
        if i < n:
            cnt[i] += 1
            wsum[i] += w
    return [{"t": i * width, "requests": cnt[i], "wait": (wsum[i] / cnt[i]) if cnt[i] else 0.0} for i in range(n)]
