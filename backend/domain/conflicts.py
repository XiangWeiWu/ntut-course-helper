from __future__ import annotations

from .courses import Course


def conflicts(a: Course, b: Course) -> bool:
    return bool(a.mask & b.mask)


def find_conflicts(courses: list[Course]) -> list[tuple[str, str]]:
    out = []
    for i, a in enumerate(courses):
        for b in courses[i + 1:]:
            if a.mask & b.mask:
                out.append((a.id, b.id))
    return out


def total_credits(courses: list[Course]) -> float:
    return sum(c.credit for c in courses)
