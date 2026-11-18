"""必修的「重修風險」權重。

資料只有退選（停修）紀錄、沒有不及格率，因此以退選率作為代理指標（退選 ≠ 被當，報告中明示）。
- 課程層級：同課程代碼 code 在 110-1～115-1 的 Σ退選 / Σ選課人數
- 教師層級：近 5 年該教師的 Σ退選 / Σ人數（analytics/withdrawal-recent-5-years.json）
兩者都以經驗貝氏收縮到全校平均（先驗樣本數 n0=50），避免小班 1/3 這類極端值。
risk = 1 + 0.5·min(課程率/全校平均, 4) + 0.5·min(教師率/全校平均, 4)  ∈ [1, 5]；平均水準的課 ≈ 2。
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from functools import lru_cache

from backend.ingest.load import RAW, SNAPSHOT, _prev_terms, _raw_courses
from backend.domain.courses import from_raw

N0 = 50


def _shrink(w: float, n: float, mean: float) -> float:
    return (w + N0 * mean) / (n + N0)


def build_tables(year=115, sem=1, terms=11) -> dict:
    by_code = defaultdict(lambda: [0, 0])
    for y, s in [(year, sem)] + _prev_terms(year, sem, terms - 1):
        try:
            for x in _raw_courses(y, s):
                c = from_raw(x)
                by_code[c.code][0] += c.withdraw
                by_code[c.code][1] += c.people
        except FileNotFoundError:
            pass
    tw = sum(v[0] for v in by_code.values())
    tn = sum(v[1] for v in by_code.values())
    mean = tw / tn if tn else 0.0178
    teachers = {}
    p = RAW / "analytics" / "withdrawal-recent-5-years.json"
    if p.exists():
        for t in json.loads(p.read_text(encoding="utf-8"))["data"]:
            teachers[t["name"]] = [t["withdraw"], t["people"]]
    return {"mean": mean,
            "course": {k: round(_shrink(w, n, mean), 5) for k, (w, n) in by_code.items()},
            "teacher": {k: round(_shrink(w, n, mean), 5) for k, (w, n) in teachers.items()}}


@lru_cache(maxsize=1)
def tables() -> dict:
    snap = SNAPSHOT / "risk.json.gz"
    if (RAW / "analytics").exists():
        return build_tables()
    if snap.exists():
        with gzip.open(snap, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {"mean": 0.0178, "course": {}, "teacher": {}}


def write_snapshot():
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    with gzip.open(SNAPSHOT / "risk.json.gz", "wt", encoding="utf-8") as f:
        json.dump(build_tables(), f, ensure_ascii=False, separators=(",", ":"))


def risk_of(course) -> dict:
    t = tables()
    m = t["mean"] or 0.0178
    cr = t["course"].get(course.code, m)
    trs = [t["teacher"].get(x, m) for x in course.teachers] or [m]
    tr = max(trs)
    r = 1 + 0.5 * min(cr / m, 4) + 0.5 * min(tr / m, 4)
    return {"risk": round(r, 3), "course_rate": round(cr, 4), "teacher_rate": round(tr, 4)}
