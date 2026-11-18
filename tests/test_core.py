import numpy as np
import pytest

from backend.domain.courses import parse_notes_limit
from backend.domain.timeslots import mask_from_time, slots_of
from backend.ingest.load import load_term, parse_home_class
from backend.recommend.solver import solve
from backend.sim.calibrate import load_alpha
from backend.sim.engine import SimConfig, run_once
from backend.sim.mechanisms.base import Seat
from backend.sim.mechanisms.fcfs import FCFSConfig, run_fcfs
from backend.sim.population import Student


def test_mask_roundtrip_and_conflict():
    a = mask_from_time({"mon": ["3", "4"], "tue": ["N"]})
    b = mask_from_time({"mon": ["4"]})
    c = mask_from_time({"mon": ["5"]})
    assert slots_of(a) == [("mon", "3"), ("mon", "4"), ("tue", "N")]
    assert a & b and not (a & c)


def test_notes_limit():
    assert parse_notes_limit("限40人") == 40
    assert parse_notes_limit("本課程上限 30 人") == 30
    assert parse_notes_limit("限本系生70人修") == 70
    assert parse_notes_limit("限五專學生修習") is None


def test_home_class():
    assert parse_home_class("電子三甲") == ("電子", 3, "甲")
    assert parse_home_class("工設一") == ("工設", 1, "")
    assert parse_home_class("電機所") is None


def _student(sid, reaction):
    return Student(sid, "x一", "x", 1, [], 6, 0, 0, 0, reaction)


def test_fcfs_invariants_and_order():
    seats = {"A": Seat("A", 1, 3, mask_from_time({"mon": ["1"]})),
             "B": Seat("B", 5, 3, mask_from_time({"mon": ["1"]}))}   # A、B 衝堂
    studs = [_student(i, r) for i, r in enumerate([0.01, 5, 10])]
    wl = {s.sid: [("A", 2.0), ("B", 1.0)] for s in studs}
    out = run_fcfs(studs, wl, seats, {s.sid: 0 for s in studs}, {s.sid: 6 for s in studs},
                   np.random.default_rng(0), FCFSConfig(arrival_sigma=0.01))
    assert len(seats["A"].enrolled) <= 1
    assert out.enrolled[0] == ["A"]                         # 最快者拿到 A
    for sid, got in out.enrolled.items():
        assert not ("A" in got and "B" in got)              # 不衝堂


@pytest.fixture(scope="module")
def courses():
    return list(load_term(115, 1))


def test_sim_reproducible_and_capacity(courses):
    cfg = SimConfig(scale=0.2, alpha=load_alpha(115, 1), mechanism="fcfs")
    s1, _, ct = run_once(courses, cfg, 7, return_tables=True)
    s2 = run_once(courses, cfg, 7)
    assert s1["welfare_mean"] == s2["welfare_mean"]
    assert (ct.enrolled <= ct.capacity).all()


def test_solver_no_conflict(courses):
    pool = [c for c in courses if c.mask and c.credit > 0][:200]
    scores = {c.id: 1.0 for c in pool}
    sols = solve(pool, scores, 10, 20, k=2)
    assert sols
    for s in sols:
        cs = [c for c in pool if c.id in s["courses"]]
        m = 0
        for c in cs:
            assert not (m & c.mask)
            m |= c.mask
        assert 10 <= s["credits"] <= 20
    if len(sols) == 2:
        assert set(sols[0]["courses"]) != set(sols[1]["courses"])


# ---------- 第二輪：名額分層與北科制度 ----------
from backend.ingest.load import detect_ceiling, estimate_capacity
from backend.domain.courses import from_raw
from backend.sim.mechanisms.ntut import NTUTConfig, run_ntut


def test_detect_ceiling():
    assert detect_ceiling([40, 50, 51, 30]) == 50 or detect_ceiling([40, 50, 51, 30]) == 51
    assert detect_ceiling([10, 50]) is None          # 最大值只出現一次
    assert detect_ceiling([60]) is None


def _raw(cid, people, notes=""):
    return {"id": cid, "code": "C" + cid, "name": {"zh": cid}, "credit": "3", "courseType": "★",
            "class": [{"name": "資工三"}], "teacher": [{"name": "T"}], "classroom": [{"name": "R1"}],
            "time": {"mon": ["1"]}, "people": str(people), "notes": notes}


def test_capacity_priority(monkeypatch):
    import backend.ingest.load as L
    cs = [from_raw(_raw("1", 30, "限40人")), from_raw(_raw("2", 30)), from_raw(_raw("3", 30))]
    monkeypatch.setattr(L, "load_overrides", lambda: {"C1|T": 99, "C3|T": 25})
    estimate_capacity(cs, [], {"C2|T": [45, 45, 20]})
    assert (cs[0].capacity, cs[0].capacity_source) == (99, "teacher")      # 教師回報優先於備註
    assert cs[1].capacity_source == "ceiling" and cs[1].capacity == 45
    assert (cs[2].capacity, cs[2].capacity_source) == (25, "teacher")      # 可小於實際人數（加簽）


def _st(sid, dept, reaction=1.0):
    return Student(sid, dept + "三", dept, 3, [], 3, 0, 0, 0, reaction)


def _seat(cid, cap, dept, general=False, day="mon"):
    return Seat(cid, cap, 3, mask_from_time({day: ["2"]}), dept=dept, general=general)


def test_ntut_priority_week_blocks_outsiders():
    seats = {"D": _seat("D", 1, "資工")}
    studs = [_st(0, "電機", 0.001), _st(1, "資工", 50)]   # 外系生最快，本系生較慢
    wl = {0: [("D", 2.0)], 1: [("D", 2.0)]}
    cfg = NTUTConfig(horizon_days=3, priority_days=7, p_request=0, exo_drop=0, arrival_sigma=0.01)
    out = run_ntut(studs, wl, seats, {0: 0, 1: 0}, {0: 3, 1: 3}, np.random.default_rng(0), cfg)
    assert out.enrolled[1] == ["D"] and out.enrolled[0] == []


def test_ntut_general_open_day0_and_capacity():
    seats = {"G": _seat("G", 2, None, general=True)}
    studs = [_st(i, d) for i, d in enumerate(["資工", "電機", "化工", "機械"])]
    wl = {s.sid: [("G", 1.0)] for s in studs}
    cfg = NTUTConfig(horizon_days=2, p_request=0, exo_drop=0)
    out = run_ntut(studs, wl, seats, {s.sid: 0 for s in studs}, {s.sid: 3 for s in studs}, np.random.default_rng(1), cfg)
    assert len(seats["G"].enrolled) == 2


def test_ntut_swap_releases_seat_and_addsign_limit():
    # A、B 衝堂；學生 0 先拿 B，A 開放（第 7 天）後換到 A → B 釋出給學生 1
    seats = {"A": _seat("A", 1, "電機"), "B": _seat("B", 1, "資工")}
    studs = [_st(0, "資工", 0.001), _st(1, "資工", 50)]
    wl = {0: [("A", 5.0), ("B", 1.0)], 1: [("B", 1.0)]}
    cfg = NTUTConfig(horizon_days=14, priority_days=7, p_request=0, exo_drop=0, visits_per_day=4, arrival_sigma=0.01)
    out = run_ntut(studs, wl, seats, {0: 0, 1: 0}, {0: 3, 1: 3}, np.random.default_rng(2), cfg)
    assert out.enrolled[0] == ["A"] and out.enrolled[1] == ["B"]
    assert seats["B"].released == 1
    # 加簽上限：名額 1、extra 0.5 → 最多 2 人
    seats = {"C": _seat("C", 1, "資工")}
    studs = [_st(i, "資工", 0.01 * (i + 1)) for i in range(6)]
    wl = {s.sid: [("C", 1.0)] for s in studs}
    cfg = NTUTConfig(horizon_days=14, p_request=1.0, p_approve=1.0, addsign_extra=0.5, exo_drop=0)
    run_ntut(studs, wl, seats, {s.sid: 0 for s in studs}, {s.sid: 3 for s in studs}, np.random.default_rng(3), cfg)
    assert len(seats["C"].enrolled) == 2 and seats["C"].addsigned == 1


def test_no_conflicts_in_full_ntut_sim(courses):
    cfg = SimConfig(scale=0.15, alpha=load_alpha(115, 1))
    _, st, ct = run_once(courses, cfg, 3, return_tables=True)
    assert (ct.enrolled <= (ct.capacity * 1.23).apply(np.ceil)).all()


def test_solver_same_name_required_courses():
    """同一門必修拆成兩個課號（同名）時不可判為無解；但不得再加選同名的其他班。"""
    a = from_raw(_raw("A", 30)); a.name = "物理"; a.mask = mask_from_time({"mon": ["1"]})
    b = from_raw(_raw("B", 30)); b.name = "物理"; b.mask = mask_from_time({"tue": ["1"]})
    c = from_raw(_raw("C", 30)); c.name = "物理"; c.mask = mask_from_time({"wed": ["1"]})
    d = from_raw(_raw("D", 30)); d.name = "化學"; d.mask = mask_from_time({"thu": ["1"]})
    sols = solve([a, b, c, d], {"C": 5.0, "D": 1.0}, 0, 20, must=["A", "B"], k=1)
    assert sols and set(sols[0]["courses"]) == {"A", "B", "D"}


# ---------- 系所排課最佳化 ----------
from backend.timetable.check import evaluate, report
from backend.timetable.data import dept_units, split_blocks
from backend.timetable.optimize import solve_dept


def _c(cid, name, cls, ctype, time, teacher, room, people=30):
    return from_raw({"id": cid, "code": "K" + cid, "name": {"zh": name}, "credit": "3", "courseType": ctype,
                     "class": [{"name": n} for n in cls], "teacher": [{"name": teacher}],
                     "classroom": [{"name": room}], "time": time, "people": str(people)})


def test_split_blocks_lunch_and_evening():
    b = split_blocks({"mon": ["3", "4", "5"], "tue": ["7"]})
    assert [(x.day, x.periods) for x in b] == [("mon", ["3", "4"]), ("mon", ["5"]), ("tue", ["7"])]
    assert split_blocks({"mon": ["A", "B"]}) is None          # 夜間不搬
    assert split_blocks({"mon": ["N"]}) is None


def test_timetable_moves_upper_course_off_lower_required():
    cs = [
        _c("1", "微積分", ["測試一"], "●", {"mon": ["1", "2"]}, "甲", "R1"),
        _c("2", "高等選修", ["測試三"], "★", {"mon": ["1", "2"]}, "乙", "R2"),
        # 乙老師在其他系把整個星期都排滿，只剩 週三 5-6 → 唯一能避開衝堂的位置
        _c("3", "他系課", ["其他二"], "★", {d: ["1", "2", "3", "4", "5", "6", "7", "8", "9"] for d in
                                          ["mon", "tue", "thu", "fri"]} | {"wed": ["1", "2", "3", "4", "7", "8", "9"]}, "乙", "R9"),
    ]
    r = report("測試", cs, "A", 10)
    assert r["status"] == "OPTIMAL"
    assert r["before"]["retake_pairs"] == 1 and r["after"]["retake_pairs"] == 0
    assert r["after"]["teacher_violations"] == 0
    assert r["moves"] and r["moves"][0]["to"] == "三56"
    assert abs(r["model_objective"] - r["checker_objective"]) < 0.05


def test_timetable_scenarios_and_shared_courses():
    cs = [
        _c("1", "物理", ["測試一"], "●", {"tue": ["3", "4"]}, "甲", "R1"),
        _c("2", "專題", ["測試二"], "▲", {"tue": ["3", "4"]}, "乙", "R2"),
        _c("4", "共同課", ["測試三", "其他三"], "★", {"tue": ["3", "4"]}, "丁", "R4"),   # 跨系共用 → 不動
    ]
    units = {u.name: u for u in dept_units("測試", cs)}
    assert units["共同課"].shared and not units["共同課"].movable("B")
    assert not units["物理"].movable("A") and units["物理"].movable("B")    # 一年級必修只有 B 能搬
    assert units["專題"].movable("A")
    a = report("測試", cs, "A", 10)
    assert a["after"]["retake_pairs"] < a["before"]["retake_pairs"]
    assert a["checker_objective"] <= a["before"]["objective"] + 1e-6       # 不會比現況差


def test_timetable_real_dept_no_new_violations(courses):
    r = report("資工", courses, "A", 15)
    assert r["after"]["teacher_violations"] == 0          # 沒有「新增」衝突
    assert r["after"]["room_violations"] == 0
    assert r["after"]["class_required_conflicts"] == 0
    assert r["checker_objective"] <= r["before"]["objective"] + 1e-6
    assert abs(r["model_objective"] - r["checker_objective"]) < 0.1
    assert {c["grade"] for c in r["cohorts"]} == {1, 2, 3, 4}


def test_combined_class_with_different_room_is_not_split():
    """同教師同時段、課名/教室不同的合班（例：本班與外生專班）→ 視為共用場次，不可拆開搬動。"""
    cs = [
        _c("1", "設計創作 (M)", ["測試三"], "★", {"wed": ["3", "4"]}, "甲", "R1"),
        _c("2", "設計創作", ["測試外生三"], "★", {"wed": ["3", "4"]}, "甲", "R2"),
        _c("3", "基礎設計", ["測試一"], "●", {"wed": ["3", "4"]}, "乙", "R3"),
    ]
    cs.append(_c("4", "團隊設計 (V)", ["測試二"], "★", {"fri": ["5", "6"]}, "丙", "R5"))
    cs[-1].teachers = ["丙", "丁", "戊"]                       # 協同教學：本班列多位老師
    cs.append(_c("5", "團隊設計", ["測試外生二"], "★", {"fri": ["5", "6"]}, "丁", "R6"))   # 外生班只列一位
    units = {x.name: x for x in dept_units("測試", cs)}
    assert units["團隊設計 (V)"].shared
    u = units["設計創作 (M)"]
    assert u.shared and not u.movable("B")
    r = report("測試", cs, "B", 10)
    assert r["after"]["teacher_violations"] == 0
    assert not any("設計創作" in m["name"] for m in r["moves"])


def test_existing_overlaps_are_kept_but_no_new_ones():
    """現況已重疊的同班必修（平行班/分流）保留；但搬動時不能製造新的同班必修衝堂。"""
    cs = [
        _c("1", "英語口語", ["測試二"], "▲", {"mon": ["1", "2"]}, "甲", "R1"),
        _c("2", "英語口語", ["測試二"], "▲", {"mon": ["1", "2"]}, "乙", "R2"),      # 平行班：原本就重疊
        _c("3", "寫作", ["測試二"], "▲", {"tue": ["3", "4"]}, "丙", "R3"),
        _c("4", "基礎課", ["測試一"], "●", {"tue": ["3", "4"]}, "丁", "R4"),        # 一年級必修，寫作與它衝堂
    ]
    r = report("測試", cs, "A", 10)
    assert r["after"]["class_required_conflicts"] == 0
    assert r["after"]["retake_pairs"] == 0
    moved = {m["name"]: m["to"] for m in r["moves"]}
    assert "寫作" in moved and "一12" not in moved["寫作"]          # 不能搬到兩個口語班的時段


def test_solver_groups_at_most_one():
    """重修組：同向度的不同博雅課只需選一門。"""
    a = from_raw(_raw("A", 30)); a.name = "博雅甲"; a.mask = mask_from_time({"mon": ["1"]})
    b = from_raw(_raw("B", 30)); b.name = "博雅乙"; b.mask = mask_from_time({"tue": ["1"]})
    c = from_raw(_raw("C", 30)); c.name = "博雅丙"; c.mask = mask_from_time({"wed": ["1"]})
    sols = solve([a, b, c], {"A": 10, "B": 9, "C": 8}, 0, 20, k=1, groups=[["A", "B", "C"]])
    assert sols[0]["courses"] == ["A"]
