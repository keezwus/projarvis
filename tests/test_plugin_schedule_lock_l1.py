from projarvis.planner.l1.engine import L1Engine
from projarvis.planner.l1.models import (
    LongHorizonSpec,
    L1TaskSpec,
    ConstraintSpec,
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


def make_spec(horizon_weeks=2):
    return LongHorizonSpec(
        horizon_start="2026-05-04T00:00:00",
        horizon_weeks=horizon_weeks,
        weekly_available=DEFAULT_AVAIL,
    )


def run_allocate(tasks, constraints=None, horizon_weeks=2):
    engine = L1Engine(make_spec(horizon_weeks=horizon_weeks))
    engine.partition()
    return engine.allocate(tasks, constraints)


class TestScheduleLockL1:
    def test_locks_week(self):
        # 2026-05-11 = Monday of week 1
        tasks = [
            L1TaskSpec(id="a", total_duration=8,
                       l2_metadata={"locked_start": "2026-05-11T09:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="schedule_lock", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        assert any(t.id == "a" for t in assignments[1])

    def test_mixed_tasks(self):
        tasks = [
            L1TaskSpec(id="locked", total_duration=8,
                       l2_metadata={"locked_start": "2026-05-04T09:00:00"}),
            L1TaskSpec(id="free", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="schedule_lock", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        assert any(t.id == "locked" for t in assignments[0])

    def test_no_locked_start_noop(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="schedule_lock", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_out_of_range_skipped(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8,
                       l2_metadata={"locked_start": "2020-01-01T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="schedule_lock", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
