"""節次 ↔ 位元遮罩。

北科節次（已由 115-1 實際資料確認出現的值）：1 2 3 4 N 5 6 7 8 9 A B C D。
N 為中午時段，位於第 4 與第 5 節之間。
每天 14 個節次 × 7 天 = 98 bits，以 Python int 表示，衝堂檢查即 a & b != 0。
"""
from __future__ import annotations

DAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
PERIODS = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"]
NP = len(PERIODS)
_PIDX = {p: i for i, p in enumerate(PERIODS)}

# 大致上課時間（供前端顯示；以北科公告為準）
PERIOD_TIMES = {
    "1": "08:10", "2": "09:10", "3": "10:10", "4": "11:10", "N": "12:10",
    "5": "13:10", "6": "14:10", "7": "15:10", "8": "16:10", "9": "17:10",
    "A": "18:30", "B": "19:20", "C": "20:20", "D": "21:10",
}


def bit(day: str, period: str) -> int:
    return 1 << (DAYS.index(day) * NP + _PIDX[period])


def mask_from_time(time: dict[str, list[str]]) -> int:
    m = 0
    for day, periods in time.items():
        if day not in DAYS:
            continue
        for p in periods:
            p = str(p).strip().upper()
            if p in _PIDX:
                m |= bit(day, p)
    return m


def slots_of(mask: int) -> list[tuple[str, str]]:
    out = []
    for d, day in enumerate(DAYS):
        for i, p in enumerate(PERIODS):
            if mask >> (d * NP + i) & 1:
                out.append((day, p))
    return out


def period_index(period: str) -> int:
    return _PIDX[period]


def is_early(period: str) -> bool:
    return period in ("1",)


def is_evening(period: str) -> bool:
    return period in ("A", "B", "C", "D")
