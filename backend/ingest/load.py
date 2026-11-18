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
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend.domain.courses import Course, from_raw

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

HOME_CLASS_RE = re.compile(r"^(?P<dept>[^\d（(]+?)(?P<grade>[一二三四五])(?P<sec>[甲乙丙丁戊])?$")
GRADE_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


SNAPSHOT = ROOT / "data" / "snapshot"


def available_terms() -> dict[str, list[int]]:
    p = RAW / "main.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, list[int]] = {}
    for f in sorted(SNAPSHOT.glob("*_*.json.gz")):
        y, s = f.name.split(".")[0].split("_")
        out.setdefault(y, []).append(int(s))
    return out


def write_snapshot(year: int, sem: int) -> Path:
    """把已推估名額的課程存成壓縮快照（約 1MB），讓沒有 data/raw 的電腦也能執行網站。"""
    import dataclasses
    import gzip
    courses = load_term(year, sem)
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    p = SNAPSHOT / f"{year}_{sem}.json.gz"
    payload = {"meta": CAPACITY_META.get((year, sem), {}),
               "courses": [dataclasses.asdict(c) for c in courses]}
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return p


def _load_snapshot(year: int, sem: int) -> list[Course] | None:
    import gzip
    p = SNAPSHOT / f"{year}_{sem}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    courses = [Course(**d) for d in payload["courses"]]
    overrides = load_overrides()                    # 教師回報仍優先
    for c in courses:
        if course_key(c) in overrides:
            c.capacity, c.capacity_source = overrides[course_key(c)], "teacher"
    CAPACITY_META[(year, sem)] = {**payload.get("meta", {}), "source": "snapshot"}
    return courses


def _raw_courses(year: int, sem: int) -> list[dict]:
    p = RAW / str(year) / str(sem) / "main.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} 不存在；請先執行 scripts/fetch_data.sh {year} {sem}")
    return json.loads(p.read_text(encoding="utf-8"))


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


OVERRIDES = ROOT / "data" / "overrides" / "capacity.json"


def course_key(c: Course) -> str:
    """課號 code + 教師：跨學期辨識「同一門課」（課號 id 每學期不同）。"""
    return f"{c.code}|{'、'.join(c.teachers)}"


def load_overrides() -> dict[str, int]:
    try:
        return {k: int(v["capacity"]) for k, v in json.loads(OVERRIDES.read_text(encoding="utf-8")).items()}
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        return {}


def save_override(key: str, capacity: int, note: str = "") -> None:
    OVERRIDES.parent.mkdir(parents=True, exist_ok=True)
    try:
        d = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        d = {}
    import datetime
    d[key] = {"capacity": int(capacity), "note": note, "updated": datetime.date.today().isoformat()}
    OVERRIDES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    load_term.cache_clear()


def detect_ceiling(history: list[int], tol: int = 2, k: int = 2) -> int | None:
    """重複天花板：歷史人數中「接近最大值（±tol）」出現 ≥k 次 → 取其眾數。
    原理：滿額的課會反覆停在同一個數字附近。加簽會把人數推高，因此需再做偏誤校正（見下）。"""
    v = [p for p in history if p > 0]
    if len(v) < k:
        return None
    m = max(v)
    near = [p for p in v if p >= m - tol]
    if len(near) < k:
        return None
    return Counter(near).most_common(1)[0][0]


def estimate_capacity(courses: list[Course], history: list[list[Course]],
                      long_history: dict[str, list[int]] | None = None) -> dict:
    """人數上限不在資料中（已查證），且無法向教務處取得，故分層估計（可信度由高到低）：
    1. teacher：教師在系統回報的實際上限（data/overrides/capacity.json）
    2. notes：備註「限N人」
    3. ceiling：近 5 年同課號+教師的重複天花板 ÷ 偏誤係數
       偏誤係數 = 在「有備註上限」的課上，median(天花板/備註上限)；這是用有標籤資料做的交叉校正。
    4. classroom_hist / course_hist / default：低可信度
    注意：人數可因加簽超過上限，因此 capacity 不再強制 >= people。
    """
    overrides = load_overrides()
    room_max: dict[str, int] = defaultdict(int)
    code_max: dict[str, int] = defaultdict(int)
    for term in history + [courses]:
        for c in term:
            for r in c.classrooms:
                room_max[r] = max(room_max[r], c.people)
            code_max[c.code] = max(code_max[c.code], c.people)
    lh = long_history or {}
    ratios = [ce / c.notes_limit for c in courses
              if c.notes_limit and (ce := detect_ceiling(lh.get(course_key(c), [])))]
    bias = float(np.median(ratios)) if len(ratios) >= 10 else 1.0
    for c in courses:
        key = course_key(c)
        ce = detect_ceiling(lh.get(key, []))
        if key in overrides:
            cap, src = overrides[key], "teacher"
        elif c.notes_limit:
            cap, src = c.notes_limit, "notes"
        elif ce:
            cap, src = round(ce / bias), "ceiling"
        elif c.classrooms and max(room_max[r] for r in c.classrooms) > 0:
            cap, src = max(room_max[r] for r in c.classrooms), "classroom_hist"
        elif code_max.get(c.code, 0) > 0:
            cap, src = code_max[c.code], "course_hist"
        else:
            cap, src = math.ceil(c.people * 1.15) + 5, "default"
        if src in ("classroom_hist", "course_hist", "default"):
            cap = max(cap, c.people)          # 低可信度估計至少不小於實際人數
        c.capacity = max(int(cap), 1)
        c.capacity_source = src
    return {"ceiling_bias": round(bias, 3), "ceiling_bias_n": len(ratios)}


def long_history(year: int, sem: int, years: int = 5) -> dict[str, list[int]]:
    """近 years 年（不含當期）同課號+教師的人數序列。"""
    out: dict[str, list[int]] = defaultdict(list)
    for y, s in _prev_terms(year, sem, years * 2):
        try:
            for x in _raw_courses(y, s):
                c = from_raw(x)
                out[course_key(c)].append(c.people)
        except FileNotFoundError:
            pass
    return out


@lru_cache(maxsize=8)
def load_term(year: int, sem: int, history_terms: int = 2) -> tuple[Course, ...]:
    if not (RAW / str(year) / str(sem) / "main.json").exists():
        snap = _load_snapshot(year, sem)
        if snap is not None:
            return tuple(snap)
    courses = [from_raw(x) for x in _raw_courses(year, sem)]
    hist = []
    for y, s in _prev_terms(year, sem, history_terms):
        try:
            hist.append([from_raw(x) for x in _raw_courses(y, s)])
        except FileNotFoundError:
            pass
    CAPACITY_META[(year, sem)] = estimate_capacity(courses, hist, long_history(year, sem))
    return tuple(courses)


CAPACITY_META: dict[tuple[int, int], dict] = {}


@lru_cache(maxsize=4)
def load_standards(year: int) -> dict:
    p = RAW / str(year) / "standard.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
