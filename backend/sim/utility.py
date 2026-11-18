"""隨機效用模型（Random Utility Model / multinomial logit）。

U_sc = α_c + β·x_sc + ε_sc,  ε ~ Gumbel(0,1)
- α_c：課程固有吸引力（以歷史選課人數校準，見 calibrate.py）
- x_sc：學生×課程特徵（系所興趣、年級相符、時段厭惡、英語授課）
Gumbel 噪音使「在選項集合中選最大效用」的機率等於 logit 公式，是離散選擇理論的標準假設。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.domain.courses import Course
from backend.domain.timeslots import slots_of
from backend.ingest.load import course_dept, parse_home_class
from .population import Student


@dataclass
class Betas:
    interest: float = 1.0
    grade_match: float = 0.6
    early: float = 1.0
    evening: float = 1.0
    english: float = 1.0
    general_ed: float = 0.3        # 通識/博雅基準吸引力
    outside: float = 0.0           # 不選此課的保留效用
    noise: float = 1.0


@dataclass
class CourseFeatures:
    id: str
    dept: str | None
    grades: set[int]
    n_early: int
    n_evening: int
    english: bool
    general: bool
    credit: float
    mask: int


def features(c: Course) -> CourseFeatures:
    grades = {h[1] for n in c.classes if (h := parse_home_class(n))}
    sl = slots_of(c.mask)
    return CourseFeatures(
        id=c.id, dept=course_dept(c), grades=grades,
        n_early=sum(p == "1" for _, p in sl),
        n_evening=sum(p in "ABCD" for _, p in sl),
        english=c.language in ("英語",),
        general=c.type == "☆" or any(k in n for n in c.classes for k in ("博雅", "通識")),
        credit=c.credit, mask=c.mask,
    )


def systematic_utility(s: Student, f: CourseFeatures, alpha: float, b: Betas) -> float:
    v = alpha
    if f.dept:
        v += b.interest * s.dept_interest.get(f.dept, 0.0)
    if f.general:
        v += b.general_ed
    if f.grades:
        v += b.grade_match * (1.0 if s.grade in f.grades else -0.5 * min(abs(x - s.grade) for x in f.grades))
    v -= b.early * s.early_aversion * f.n_early / 2
    v -= b.evening * s.evening_aversion * f.n_evening / 2
    if f.english:
        v += b.english * s.english_pref
    return v


@dataclass
class ElectivePool:
    feats: list[CourseFeatures]
    alpha: np.ndarray
    index: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        self.index = {f.id: i for i, f in enumerate(self.feats)}
        fs = self.feats
        self.depts = sorted({f.dept for f in fs if f.dept})
        di = {d: i for i, d in enumerate(self.depts)}
        self.dept_idx = np.array([di.get(f.dept, -1) for f in fs])
        self.general = np.array([f.general for f in fs], float)
        self.n_early = np.array([f.n_early for f in fs], float)
        self.n_evening = np.array([f.n_evening for f in fs], float)
        self.english = np.array([f.english for f in fs], float)
        self.credit = np.array([f.credit for f in fs], float)
        # grade_match[g-1, c]：+1 年級相符；不符則 -0.5×年級差；無年級資訊為 0
        gm = np.zeros((5, len(fs)))
        for j, f in enumerate(fs):
            if f.grades:
                for g in range(1, 6):
                    gm[g - 1, j] = 1.0 if g in f.grades else -0.5 * min(abs(x - g) for x in f.grades)
        self.grade_match = gm

    def systematic(self, s: Student, b: Betas) -> np.ndarray:
        """向量化版本的 systematic_utility（對所有課程）。"""
        interest = np.array([s.dept_interest.get(d, 0.0) for d in self.depts] + [0.0])
        v = self.alpha.copy()
        v += b.interest * interest[self.dept_idx]          # dept_idx=-1 取到最後的 0
        v += b.general_ed * self.general
        v += b.grade_match * self.grade_match[min(s.grade, 5) - 1]
        v -= b.early * s.early_aversion * self.n_early / 2
        v -= b.evening * s.evening_aversion * self.n_evening / 2
        v += b.english * s.english_pref * self.english
        return v


def elective_pool(courses: list[Course], alpha: dict[str, float] | None = None) -> ElectivePool:
    """可搶的課：選修（★☆）、有上課時間、學分>0、大學部開課或通識。
    people==0 的課排除：資料於選課結束後爬取，0 人多為停開或限特定對象（假設，待查證）。"""
    feats = []
    for c in courses:
        if c.required or not c.mask or c.credit <= 0 or c.people == 0:
            continue
        f = features(c)
        if f.dept is None and not f.general:
            continue
        feats.append(f)
    a = np.array([(alpha or {}).get(f.id, 0.0) for f in feats])
    return ElectivePool(feats, a)
