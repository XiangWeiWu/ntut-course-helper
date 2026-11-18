"""課程正規化模型與分類。

courseType 符號 → 學分類別：依 standard.json 中 credits 的欄位順序與實例交叉比對
（例：國文為 △ 校訂共同必修；師培中心 ▲ 課程對應「校訂專業必修學分 20」）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .timeslots import mask_from_time

COURSE_TYPES = {
    "○": "部訂共同必修",
    "△": "校訂共同必修",
    "☆": "共同選修",
    "●": "部訂專業必修",
    "▲": "校訂專業必修",
    "★": "專業選修",
}
REQUIRED_TYPES = {"○", "△", "●", "▲"}

_LIMIT_RE = re.compile(r"(?:上限|限)\s*(?:本系生)?\s*(\d{1,3})\s*人")


def parse_notes_limit(notes: str) -> int | None:
    """從備註抓「限40人」「上限30人」「限本系生70人」；抓不到回傳 None。"""
    m = _LIMIT_RE.search(notes or "")
    return int(m.group(1)) if m else None


def _num(s, default=0.0) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


@dataclass
class Course:
    id: str
    code: str
    name: str
    name_en: str
    credit: float
    hours: float
    type: str
    classes: list[str]
    class_codes: list[str]
    teachers: list[str]
    classrooms: list[str]
    time: dict[str, list[str]]
    mask: int
    people: int
    withdraw: int
    language: str
    notes: str
    description: str = ""
    notes_limit: int | None = None
    capacity: int = 0
    capacity_source: str = "unknown"  # notes | classroom_hist | course_hist | default
    extra: dict = field(default_factory=dict)

    @property
    def required(self) -> bool:
        return self.type in REQUIRED_TYPES

    @property
    def type_name(self) -> str:
        return COURSE_TYPES.get(self.type, "未知")

    def to_dict(self, brief: bool = False) -> dict:
        d = {
            "id": self.id, "code": self.code, "name": self.name, "nameEn": self.name_en,
            "credit": self.credit, "hours": self.hours, "type": self.type, "typeName": self.type_name,
            "classes": self.classes, "teachers": self.teachers, "classrooms": self.classrooms,
            "time": self.time, "people": self.people, "withdraw": self.withdraw,
            "language": self.language, "notes": self.notes,
            "capacity": self.capacity, "capacitySource": self.capacity_source,
        }
        if not brief:
            d["description"] = self.description
        return d


def from_raw(x: dict) -> Course:
    time = {k: [str(p) for p in v] for k, v in (x.get("time") or {}).items()}
    desc = x.get("description") or {}
    return Course(
        id=str(x["id"]),
        code=str(x.get("code", "")),
        name=(x.get("name") or {}).get("zh", ""),
        name_en=(x.get("name") or {}).get("en") or "",
        credit=_num(x.get("credit")),
        hours=_num(x.get("hours")),
        type=x.get("courseType", ""),
        classes=[c["name"] for c in x.get("class", [])],
        class_codes=[c.get("code", "") for c in x.get("class", [])],
        teachers=[t["name"] for t in x.get("teacher", [])],
        classrooms=[c["name"] for c in x.get("classroom", [])],
        time=time,
        mask=mask_from_time(time),
        people=int(_num(x.get("people"))),
        withdraw=int(_num(x.get("peopleWithdraw"))),
        language=x.get("language", ""),
        notes=x.get("notes", ""),
        description=desc.get("zh", "") if isinstance(desc, dict) else str(desc),
        notes_limit=parse_notes_limit(x.get("notes", "")),
    )
