"""每日學習負擔（學生端與系所端共用的定義）。

依據（詳見 README「排課負擔的文獻依據」）：
- Williams & Shapiro (2018)：連續上多堂課、中間沒有休息會造成認知疲勞，對能力較弱的學生影響最大。
- Sievertsen, Gino & Piovesan (2016, PNAS)：休息能恢復表現，對低成就學生效果較大。

定義（扣分，不是禁止）：
- 連續上課：依節次順序 1 2 3 4 N 5 6 7 8 9 A B C D；空著的 N（中午）視為休息。
  任何「連續 max_consec+1 節都有課」的窗格扣一次分 → 連續 L 節的扣分恰為 max(0, L − max_consec)。
- 每日總節數：一天超過 max_daily 節，每多一節扣一次分。
"""
from __future__ import annotations

from dataclasses import dataclass

from .timeslots import DAYS, PERIODS


@dataclass
class Balance:
    max_consec: int = 3
    max_daily: int = 6
    weight: float = 0.5          # 每超出一節的扣分（學生端；系所端另設權重）


def windows(max_consec: int) -> list[list[str]]:
    """所有長度 max_consec+1 的連續節次窗格（每天）。"""
    L = max_consec + 1
    return [[f"{d}-{p}" for p in PERIODS[i:i + L]] for d in DAYS for i in range(len(PERIODS) - L + 1)]


def load_excess(slots: set[str], b: Balance) -> dict:
    """直接由已佔用節次計算：連續超出節數、每日超出節數，以及每天的明細。"""
    consec = sum(1 for w in windows(b.max_consec) if all(s in slots for s in w))
    per_day = {d: sum(1 for p in PERIODS if f"{d}-{p}" in slots) for d in DAYS}
    daily = sum(max(0, n - b.max_daily) for n in per_day.values())
    longest = {}
    for d in DAYS:
        run = best = 0
        for p in PERIODS:
            run = run + 1 if f"{d}-{p}" in slots else 0
            best = max(best, run)
        longest[d] = best
    return {"consec_excess": consec, "daily_excess": daily, "per_day": per_day, "longest_run": longest}
