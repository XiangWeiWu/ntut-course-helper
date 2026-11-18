"""由真實班級資料產生學生母體。

原則：
- 只模擬大學部「本班」（如 電子三甲），班級人數 = 該班必修課（●▲○△ 且只開給此班）
  已選人數的中位數 — 必修多為預排，人數最能代表班級規模。
- 必修課預先排入（可關閉），選修（★☆ 及他系課）才進入搶課。
- 個體異質性：時段偏好、英語授課接受度、手速（到達延遲）、學分目標、興趣（對各系的偏好）。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from backend.domain.courses import Course
from backend.ingest.load import course_dept, parse_home_class


@dataclass
class Student:
    sid: int
    home_class: str
    dept: str
    grade: int
    required: list[str]            # 預排必修課 id
    credit_target: float           # 本學期總學分目標
    early_aversion: float          # 第 1 節厭惡
    evening_aversion: float        # 夜間 A-D 厭惡
    english_pref: float            # 英語授課偏好（負值=排斥）
    reaction: float                # 到達延遲尺度參數（越小越快）
    dept_interest: dict[str, float] = field(default_factory=dict)


@dataclass
class ClassGroup:
    name: str
    dept: str
    grade: int
    size: int
    required: list[str]


def home_classes(courses: list[Course]) -> list[ClassGroup]:
    req = defaultdict(list)
    sizes = defaultdict(list)
    for c in courses:
        for n in c.classes:
            h = parse_home_class(n)
            if not h:
                continue
            if c.required and c.mask:
                req[n].append(c.id)
                if len(c.classes) == 1 and c.people > 0:
                    sizes[n].append(c.people)
    out = []
    for n, ids in req.items():
        if not sizes[n]:
            continue
        dept, grade, _ = parse_home_class(n)
        out.append(ClassGroup(n, dept, grade, int(np.median(sizes[n])), ids))
    return sorted(out, key=lambda g: g.name)


def generate(courses: list[Course], rng: np.random.Generator, scale: float = 1.0,
             include_classes: set[str] | None = None) -> list[Student]:
    by_id = {c.id: c for c in courses}
    depts = sorted({d for c in courses if (d := course_dept(c))})
    students: list[Student] = []
    for g in home_classes(courses):
        if include_classes and g.name not in include_classes:
            continue
        n = max(1, round(g.size * scale))
        # 去除彼此衝堂的必修（同課多班時只留一個）
        chosen, mask = [], 0
        for cid in g.required:
            c = by_id[cid]
            if not (c.mask & mask):
                chosen.append(cid)
                mask |= c.mask
        req_credit = sum(by_id[i].credit for i in chosen)
        for _ in range(n):
            interest = {d: float(rng.normal(0, 0.5)) for d in depts}
            interest[g.dept] = interest.get(g.dept, 0) + 1.5   # 本系偏好
            students.append(Student(
                sid=len(students), home_class=g.name, dept=g.dept, grade=g.grade,
                required=list(chosen),
                credit_target=float(np.clip(rng.normal(22 if g.grade < 4 else 15, 3), max(req_credit, 9), 30)),
                early_aversion=float(rng.gamma(2.0, 0.4)),
                evening_aversion=float(rng.gamma(2.0, 0.6)),
                english_pref=float(rng.normal(-0.3, 0.6)),
                reaction=float(rng.lognormal(0.0, 0.6)),
                dept_interest=interest,
            ))
    return students
