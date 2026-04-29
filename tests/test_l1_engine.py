from projarvis.planner.l1.engine import L1Engine
from projarvis.planner.l1.models import (
    LongHorizonSpec,
    L1TaskSpec,
)

DEFAULT_AVAIL = {
    "monday":    [["09:00", "12:00"]],
    "tuesday":   [["09:00", "12:00"]],
    "wednesday": [["09:00", "12:00"]],
    "thursday":  [["09:00", "12:00"]],
    "friday":    [["09:00", "12:00"]],
    "saturday":  [],
    "sunday":    [],
}
SLOTS_PER_DAY = 12  # 09:00-12:00 = 3h = 12 slots


def make_spec(horizon_weeks=2):
    return LongHorizonSpec(
        horizon_start="2026-05-04T00:00:00",
        horizon_weeks=horizon_weeks,
        weekly_available=DEFAULT_AVAIL,
    )


class TestPartition:
    def test_single_week(self):
        engine = L1Engine(make_spec(horizon_weeks=1))
        windows = engine.partition()
        assert len(windows) == 1
        assert windows[0].week_index == 0
        assert windows[0].available_slots == SLOTS_PER_DAY * 5  # 5 weekdays

    def test_multi_week(self):
        engine = L1Engine(make_spec(horizon_weeks=3))
        windows = engine.partition()
        assert len(windows) == 3
        assert [w.week_index for w in windows] == [0, 1, 2]
        for w in windows:
            assert w.available_slots == SLOTS_PER_DAY * 5

    def test_idempotent(self):
        engine = L1Engine(make_spec(horizon_weeks=2))
        w1 = engine.partition()
        w2 = engine.partition()
        assert w1 is not w2  # returns copies
        assert len(w1) == len(w2)


class TestAllocate:
    def test_all_tasks_fit_one_week(self):
        engine = L1Engine(make_spec(horizon_weeks=2))
        engine.partition()
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=4),
        ]
        assignments, cap = engine.allocate(tasks)
        assert cap.status == "OK"
        # Both tasks should pack into week 0 (earliest-bias)
        assert len(assignments[0]) == 2
        assert len(assignments[1]) == 0

    def test_spread_across_weeks(self):
        engine = L1Engine(make_spec(horizon_weeks=2))
        engine.partition()
        capacity = SLOTS_PER_DAY * 5  # 60
        # Fill week 0 close to capacity, forcing spillover
        tasks = [L1TaskSpec(id=f"t{i}", total_duration=20) for i in range(5)]
        # 5 × 20 = 100, w0 capacity = 60, w1 capacity = 60
        # w0 can hold 3 (60), w1 gets 2 (40)
        assignments, cap = engine.allocate(tasks)
        assert cap.status == "OK"
        w0_ids = [t.id for t in assignments[0]]
        w1_ids = [t.id for t in assignments[1]]
        assert len(w0_ids) == 3
        assert len(w1_ids) == 2

    def test_oversaturated(self):
        engine = L1Engine(make_spec(horizon_weeks=1))
        engine.partition()
        tasks = [L1TaskSpec(id="big", total_duration=2000)]
        assignments, cap = engine.allocate(tasks)
        assert cap.status == "OVERSATURATED"
        assert assignments == {}

    def test_empty_tasks(self):
        engine = L1Engine(make_spec(horizon_weeks=2))
        engine.partition()
        assignments, cap = engine.allocate([])
        assert cap.status == "OK"
        assert assignments == {}


class TestSchedule:
    def test_ok_status(self):
        engine = L1Engine(make_spec(horizon_weeks=2))
        engine.partition()
        tasks = [
            L1TaskSpec(id="a", total_duration=4),
            L1TaskSpec(id="b", total_duration=8),
        ]
        engine.allocate(tasks)
        result = engine.schedule()
        assert result.status == "OK"
        assert result.weekly_solutions[0].solution.status in ("OPTIMAL", "FEASIBLE")

    def test_skipped_weeks(self):
        engine = L1Engine(make_spec(horizon_weeks=3))
        engine.partition()
        tasks = [L1TaskSpec(id="a", total_duration=4)]
        engine.allocate(tasks)
        result = engine.schedule()
        assert result.weekly_solutions[0].solution is not None  # has task
        assert result.weekly_solutions[1].solution is None      # skipped
        assert result.weekly_solutions[2].solution is None      # skipped

    def test_infeasible_on_empty_allocate(self):
        engine = L1Engine(make_spec(horizon_weeks=1))
        engine.partition()
        engine.allocate([L1TaskSpec(id="big", total_duration=9999)])
        result = engine.schedule()
        assert result.status == "INFEASIBLE"

    def test_requires_allocate_first(self):
        engine = L1Engine(make_spec(horizon_weeks=1))
        try:
            engine.schedule()
            assert False, "should have raised"
        except RuntimeError:
            pass
