"""系所排課最佳化的資料準備：把系所課程整理成「場次單位」與「時段區塊」。

- 單位（Unit）：同教師＋完全相同時段的多個課號（合班）視為同一場次，一起搬動。
- 區塊（Block）：一門課在某天的連續節次（例：一 5-6）。N（中午）會把 4 與 5 切開。
- 共用課（固定不動）：班級含他系或非本班（研究所、博雅、跨校…）、通識/體育/學院指定向度、
  或與他系課同教師同時段（合開）。只有平日 1–9 節的課可搬。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from backend.domain.courses import Course
from backend.domain.timeslots import PERIODS
from backend.ingest.load import parse_home_class
from backend.sim.utility import is_general

DAY5 = ["mon", "tue", "wed", "thu", "fri"]
DAYSEQ = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]          # 可排的日間節次（不含 N）
_PIDX = {p: i for i, p in enumerate(PERIODS)}
FIXED_NAMES = ("體育", "學院指定向度", "博雅", "全民國防", "服務學習", "勞作教育")


def slots(time: dict) -> set[str]:
    return {f"{d}-{p}" for d, ps in time.items() for p in ps}


@dataclass
class Block:
    day: str
    periods: list[str]

    @property
    def start(self) -> int:
        return DAYSEQ.index(self.periods[0])


@dataclass
class Unit:
    uid: str
    ids: list[str]
    name: str
    teachers: list[str]
    rooms: list[str]
    required: bool
    grades: list[int]                 # 本系年級
    classes: list[str]                # 本系本班
    time: dict
    credit: float
    shared: bool
    movable_time: bool                # 時段型態可搬（平日 1–9 節）
    blocks: list[Block] = field(default_factory=list)
    code: str = ""

    @property
    def room_keys(self) -> list[str]:
        """只有單一教室的課才做教室撞期檢查：多教室的課（講堂＋實驗室）資料沒有標示哪個時段用哪間。"""
        return self.rooms if len(self.rooms) == 1 else []

    @property
    def grade(self) -> int:
        return min(self.grades) if self.grades else 0

    def movable(self, scenario: str) -> bool:
        if self.shared or not self.movable_time:
            return False
        if scenario == "A":                       # 少改動：一年級必修不動
            return not (self.required and self.grade <= 1)
        return True


def split_blocks(time: dict) -> list[Block] | None:
    out = []
    for d, ps in time.items():
        if not ps:
            continue
        if d not in DAY5 or any(p not in DAYSEQ for p in ps):
            return None
        ps = sorted(ps, key=lambda p: _PIDX[p])
        run = [ps[0]]
        for p in ps[1:]:
            if _PIDX[p] == _PIDX[run[-1]] + 1:
                run.append(p)
            else:
                out.append(Block(d, run))
                run = [p]
        out.append(Block(d, run))
    return out


def sig(c: Course):
    """合班判定：同教師＋完全相同時段＝同一場次（教師不可能同時在兩處；教室或課名可能因資料登錄而不同）。
    無教師資料的課則再加上教室，避免把不相關的課合併。"""
    key = (tuple(sorted(c.teachers)), tuple(sorted(slots(c.time))))
    return key if c.teachers else key + (tuple(sorted(c.classrooms)),)


def dept_units(dept: str, courses: list[Course]) -> list[Unit]:
    def own(c):
        return [h for n in c.classes if (h := parse_home_class(n)) and h[0] == dept]

    mine = [c for c in courses if own(c) and c.mask]
    # 與他系課「共用任一位教師且時段完全相同」→ 合開（含協同教學：本班列 5 位老師、外生班只列 1 位）
    other_keys = {(t, tuple(sorted(slots(c.time)))) for c in courses if c.mask and not own(c) for t in c.teachers}
    other_sigs = {sig(c) for c in courses if c.mask and not own(c)}

    def linked(c):
        ts = tuple(sorted(slots(c.time)))
        return any((t, ts) in other_keys for t in c.teachers)
    groups = defaultdict(list)
    for c in mine:
        groups[sig(c)].append(c)
    units = []
    for i, (sg, cs) in enumerate(sorted(groups.items(), key=lambda kv: kv[1][0].id)):
        c0 = cs[0]
        homes = [h for c in cs for h in own(c)]
        all_classes = {n for c in cs for n in c.classes}
        shared = (any(not ((h := parse_home_class(n)) and h[0] == dept) for n in all_classes)
                  or any(is_general(c) for c in cs) or any(k in c0.name for k in FIXED_NAMES)
                  or sg in other_sigs or any(linked(c) for c in cs))
        blocks = split_blocks(c0.time)
        units.append(Unit(
            uid=f"u{i}", ids=[c.id for c in cs], name=c0.name, teachers=list(c0.teachers),
            rooms=sorted({r for c in cs for r in c.classrooms}), required=any(c.required for c in cs),
            grades=sorted({h[1] for h in homes}), classes=sorted({f"{h[0]}{'一二三四五'[h[1]-1]}{h[2]}" for h in homes}),
            time=c0.time, credit=c0.credit, shared=shared, movable_time=blocks is not None,
            blocks=blocks or [], code=c0.code))
    return units


def block_options(b: Block) -> list[Block]:
    """同長度、不跨午休（4|5 之間）、平日 1–9 節的所有放法。"""
    L = len(b.periods)
    out = []
    for d in DAY5:
        for s in range(0, len(DAYSEQ) - L + 1):
            if s <= 3 < s + L - 1:          # 跨越 4→5
                continue
            out.append(Block(d, DAYSEQ[s:s + L]))
    return out


def unmoved_blocks(u: "Unit", new_time: dict) -> int:
    """原區塊中，在新課表裡仍以完全相同（同天同節次）出現的數量；模型與檢查器共用此定義。"""
    new = split_blocks(new_time) or []
    pool = [(b.day, tuple(b.periods)) for b in new]
    n = 0
    for b in u.blocks:
        k = (b.day, tuple(b.periods))
        if k in pool:
            pool.remove(k)
            n += 1
    return n


def same_block(a: Block, b: Block) -> bool:
    return a.day == b.day and a.periods == b.periods


def block_slots(b: Block) -> set[str]:
    return {f"{b.day}-{p}" for p in b.periods}


def school_occupancy(courses: list[Course], exclude_ids: set[str]):
    """全校固定課的教師與教室佔用（集合；合開的重複課號只算一次）。"""
    teacher, room = defaultdict(set), defaultdict(set)
    for c in courses:
        if c.id in exclude_ids or not c.mask:
            continue
        s = slots(c.time)
        for t in c.teachers:
            teacher[t] |= s
        if len(c.classrooms) == 1:
            room[c.classrooms[0]] |= s
    return teacher, room
