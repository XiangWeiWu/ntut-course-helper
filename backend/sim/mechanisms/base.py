from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Seat:
    id: str
    capacity: int
    credit: float
    mask: int
    enrolled: list[int] = field(default_factory=list)
    full_at: float | None = None


@dataclass
class Outcome:
    """機制輸出：可直接交給 metrics 比較不同機制。"""
    enrolled: dict[int, list[str]]          # sid → 選上的選修課
    ideal: dict[int, list[str]]             # sid → 無容量限制下會選的課（需求）
    utility: dict[int, dict[str, float]]    # sid → {cid: 效用}
    arrival: dict[int, float]
    seats: dict[str, Seat]
    log: dict = field(default_factory=dict)


def ideal_set(wishlist, seats: dict[str, Seat], base_mask: int, budget: float) -> list[str]:
    """不考慮名額時，依偏好貪婪地排入不衝堂、學分不超過預算的課。"""
    out, mask, cr = [], base_mask, 0.0
    for cid, _ in wishlist:
        s = seats[cid]
        if s.mask & mask or cr + s.credit > budget + 1e-9:
            continue
        out.append(cid)
        mask |= s.mask
        cr += s.credit
    return out
