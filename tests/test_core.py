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
    cfg = SimConfig(scale=0.2, alpha=load_alpha(115, 1))
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
