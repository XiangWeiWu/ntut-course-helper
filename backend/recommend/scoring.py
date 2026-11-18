"""推薦課表的計分（API 與群體模擬共用，與 frontend/src/static.ts 的 scheduleSolve 相同規則）。

- 班級必修預排（去衝堂）為 must。
- 收藏課：使用者給的分數；其他：本系同年級選修 0.6；共同選修（☆）、通識博雅課、本系其他年級選修 0.3
  （候選課太少時，為了湊滿學則最低學分只能選少數幾門共同選修，群體模擬會擠爆這些班）。
- 避開第 1 節／夜間：每節扣 0.4。
- 群體擁擠扣分（prices）：模擬多人同時採用推薦時，擠爆的開課班每學分扣 price（見 crowd.py）。
分數 × max(學分, 1)。
"""
from __future__ import annotations

from backend.domain.courses import Course
from backend.domain.timeslots import slots_of
from backend.ingest.load import course_dept, parse_home_class


def is_boya(c: Course) -> bool:
    return any(n.startswith("博雅課程") for n in c.classes)


def build(t: dict[str, Course], classes, home_class: str | None, favorites: dict[str, float] | None = None,
          exclude=(), must=(), avoid_early=False, avoid_evening=True, prices: dict[str, float] | None = None):
    favorites = favorites or {}
    prices = prices or {}
    must = list(must)
    dept = grade = None
    if home_class:
        g = next((g for g in classes if g.name == home_class), None)
        if g:
            dept, grade = g.dept, g.grade
            mask = 0
            for cid in g.required:
                if not (t[cid].mask & mask):
                    must.append(cid)
                    mask |= t[cid].mask
    scores = {}
    for c in t.values():
        s = favorites.get(c.id)
        if c.id in exclude or not c.mask or c.people == 0 or (c.credit <= 0 and s is None):
            continue
        if s is None:
            if c.required and not is_boya(c):        # 博雅課在資料中標為 △，但學生可自由選，不是預排必修
                continue
            d = course_dept(c)
            hc = [h for n in c.classes if (h := parse_home_class(n))]
            if dept and d == dept and (not grade or any(h[1] == grade for h in hc)):
                s = 0.6
            elif c.type == "☆" or is_boya(c) or (dept and d == dept):
                s = 0.3
            else:
                continue
        sl = slots_of(c.mask)
        if avoid_early:
            s -= 0.4 * sum(p == "1" for _, p in sl)
        if avoid_evening:
            s -= 0.4 * sum(p in "ABCD" for _, p in sl)
        s -= prices.get(c.id, 0.0)
        scores[c.id] = s * max(c.credit, 1)
    return scores, must
