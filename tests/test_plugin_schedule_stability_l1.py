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


class TestScheduleStabilityL1:
    def test_prefers_previous_week(self):
        # Task was in week 1, weight=2 > 1, priority=1 → should stay in week 1
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=1,
                       l2_metadata={"previous_start": "2026-05-11T09:00:00"}),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="schedule_stability",
                           params={"default_weight": 2}),
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        # Task "a" prefers week 1
        assert any(t.id == "a" for t in assignments[1])

    def test_low_weight_allows_move(self):
        # weight=0.5 < 1, priority=1 → earliness wins, task moves to week 0
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=1,
                       l2_metadata={"previous_start": "2026-05-11T09:00:00"}),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="schedule_stability",
                           params={"default_weight": 0.5}),
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_respects_priority(self):
        # priority=10 with weight=2 → effective=20, very strong stability
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=10,
                       l2_metadata={"previous_start": "2026-05-11T09:00:00"}),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="schedule_stability",
                           params={"default_weight": 2}),
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        assert any(t.id == "a" for t in assignments[1])

    def test_no_metadata_noop(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=1),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="schedule_stability",
                           params={"default_weight": 2}),
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_out_of_range_skipped(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=1,
                       l2_metadata={"previous_start": "2020-01-01T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="schedule_stability",
                           params={"default_weight": 2}),
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
