"""讀取 data/raw（gh-pages 分支的 sparse clone）並正規化。

資料取得：本環境的 proxy 擋掉 gnehs.github.io，因此改以 git 取得同一份資料：
  git clone --depth 1 --branch gh-pages --filter=blob:none --no-checkout \
      https://github.com/gnehs/ntut-course-crawler-node data/raw
  git -C data/raw sparse-checkout set --no-cone '/main.json' '/115/1/*.json' ...
見 scripts/fetch_data.sh。
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from backend.domain.courses import Course, from_raw

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

HOME_CLASS_RE = re.compile(r"^(?P<dept>[^\d（(]+?)(?P<grade>[一二三四五])(?P<sec>[甲乙丙丁戊])?$")
GRADE_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def available_terms() -> dict[str, list[int]]:
    return json.loads((RAW / "main.json").read_text())


def _raw_courses(year: int, sem: int) -> list[dict]:
    p = RAW / str(year) / str(sem) / "main.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} 不存在；請先執行 scripts/fetch_data.sh {year} {sem}")
    return json.loads(p.read_text())


def parse_home_class(name: str):
    """'電子三甲' → ('電子', 3, '甲')；研究所、跨校、博雅等回傳 None。"""
    if "所" in name or "跨校" in name or "博雅" in name or "學程" in name or "專班" in name:
        return None
    m = HOME_CLASS_RE.match(name)
    if not m:
        return None
    return m["dept"], GRADE_NUM[m["grade"]], m["sec"] or ""


def course_dept(c: Course) -> str | None:
    for n in c.classes:
        h = parse_home_class(n)
        if h:
            return h[0]
    return None


def _prev_terms(year: int, sem: int, k: int) -> list[tuple[int, int]]:
    out, y, s = [], year, sem
    for _ in range(k):
        y, s = (y, 1) if s == 2 else (y - 1, 2)
        out.append((y, s))
    return out


def estimate_capacity(courses: list[Course], history: list[list[Course]]) -> None:
    """人數上限不在資料中（已以 115-1 全部欄位確認），故分層估計：
    1. 備註寫明「限N人」→ notes（可信）
    2. 該教室在歷史+本學期出現過的最大選課人數 → classroom_hist（教室容量的下界估計）
    3. 同課號歷史最大人數 → course_hist
    4. 否則 ceil(people*1.15)+5 → default
    最後一律確保 capacity >= people（實際已選人數不可能超過上限，除非加簽）。
    """
    room_max: dict[str, int] = defaultdict(int)
    code_max: dict[str, int] = defaultdict(int)
    for term in history + [courses]:
        for c in term:
            for r in c.classrooms:
                room_max[r] = max(room_max[r], c.people)
            code_max[c.code] = max(code_max[c.code], c.people)
    for c in courses:
        if c.notes_limit:
            cap, src = c.notes_limit, "notes"
        elif c.classrooms and max(room_max[r] for r in c.classrooms) > 0:
            cap, src = max(room_max[r] for r in c.classrooms), "classroom_hist"
        elif code_max.get(c.code, 0) > 0:
            cap, src = code_max[c.code], "course_hist"
        else:
            cap, src = math.ceil(c.people * 1.15) + 5, "default"
        c.capacity = max(cap, c.people, 1)
        c.capacity_source = src


@lru_cache(maxsize=8)
def load_term(year: int, sem: int, history_terms: int = 2) -> tuple[Course, ...]:
    courses = [from_raw(x) for x in _raw_courses(year, sem)]
    hist = []
    for y, s in _prev_terms(year, sem, history_terms):
        try:
            hist.append([from_raw(x) for x in _raw_courses(y, s)])
        except FileNotFoundError:
            pass
    estimate_capacity(courses, hist)
    return tuple(courses)


@lru_cache(maxsize=4)
def load_standards(year: int) -> dict:
    p = RAW / str(year) / "standard.json"
    return json.loads(p.read_text()) if p.exists() else {}
