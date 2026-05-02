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
SLOTS_PER_DAY = 12


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


# ── deadline ────────────────────────────────────────────────

class TestDeadlinePlugin:
    def test_forced_early_week(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"deadline": "2026-05-04T12:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="deadline", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        # "a" has deadline in week 0 → must be week 0
        assert any(t.id == "a" for t in assignments[0])

    def test_deadline_iso_out_of_range_skipped(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"deadline": "2020-01-01T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="deadline", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        # deadline out of epoch range → silently skipped, all tasks assigned
        assert cap.status == "OK"

    def test_no_deadline_metadata_noop(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="deadline", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"


# ── fixed_time ──────────────────────────────────────────────

class TestFixedTimePlugin:
    def test_locks_week(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"fixed_time": "2026-05-11T09:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="fixed_time", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        # "a" has fixed_time in week 1 → must be week 1
        assert any(t.id == "a" for t in assignments[1])

    def test_fixed_time_out_of_range_skipped(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"fixed_time": "2020-01-01T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="fixed_time", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_no_fixed_time_metadata_noop(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
        ]
        constraints = [ConstraintSpec(type="fixed_time", params={})]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=1)
        assert cap.status == "OK"


# ── dependency ──────────────────────────────────────────────

class TestDependencyPlugin:
    def test_cross_week_ordering(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="dependency", params={"pairs": [["a", "b"]]})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
        # a before b → a's week <= b's week. With earliest-bias both will be week 0
        w0_ids = {t.id for t in assignments[0]}
        w1_ids = {t.id for t in assignments.get(1, [])}
        # If b is in week 0, a must also be week 0
        if "b" in w0_ids:
            assert "a" in w0_ids

    def test_dependency_nonexistent_task_skipped(self):
        tasks = [L1TaskSpec(id="a", total_duration=8)]
        constraints = [
            ConstraintSpec(type="dependency", params={"pairs": [["a", "nonexistent"]]})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_empty_pairs_noop(self):
        tasks = [L1TaskSpec(id="a", total_duration=8)]
        constraints = [
            ConstraintSpec(type="dependency", params={"pairs": []})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"


# ── energy_budget ───────────────────────────────────────────

class TestEnergyBudgetPlugin:
    def test_focus_hard_cap_infeasible(self):
        # 2 tasks × 8 slots × 1.0 focus = 16 focus each
        # daily budget 1 focus → weekly budget = 1 × 5 = 5 per week
        # 2 tasks both need 16 focus → can't fit in any week → INFEASIBLE
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
            L1TaskSpec(id="b", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
        ]
        constraints = [
            ConstraintSpec(type="energy_budget", params={"focus_budget_per_day": 1})
        ]
        _, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OVERSATURATED"

    def test_focus_within_cap_ok(self):
        # 2 tasks × 8 slots × 1.0 focus = 16 each
        # daily budget 10 → weekly = 50 → both fit in one week
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
            L1TaskSpec(id="b", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
        ]
        constraints = [
            ConstraintSpec(type="energy_budget", params={"focus_budget_per_day": 10})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_energy_spreads_across_weeks(self):
        # 3 tasks × 8 slots × 1.0 focus = 8 focus each
        # daily budget 1 → weekly = 5. 2 weeks = 10 total.
        # 3 tasks need 24 total → OVERSATURATED
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
            L1TaskSpec(id="b", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
            L1TaskSpec(id="c", total_duration=8, l2_metadata={"focus_multiplier": 1.0}),
        ]
        constraints = [
            ConstraintSpec(type="energy_budget", params={"focus_budget_per_day": 1})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OVERSATURATED"

    def test_no_multipliers_noop(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="energy_budget", params={"focus_budget_per_day": 1})
        ]
        _, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_empty_tasks_noop(self):
        constraints = [
            ConstraintSpec(type="energy_budget", params={"focus_budget_per_day": 10})
        ]
        _, cap = run_allocate([], constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_exercise_budget_hard_cap(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"exercise_multiplier": 1.0}),
            L1TaskSpec(id="b", total_duration=8, l2_metadata={"exercise_multiplier": 1.0}),
        ]
        constraints = [
            ConstraintSpec(type="energy_budget", params={"exercise_budget_per_day": 1})
        ]
        _, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OVERSATURATED"


# ── task_distribution ───────────────────────────────────────

class TestTaskDistribution:
    def test_front_load_all_tasks(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, priority=1),
            L1TaskSpec(id="b", total_duration=8, priority=1),
        ]
        constraints = [
            ConstraintSpec(type="task_distribution", params={"mode": "front_load"})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_ramp_up_deadline_tasks(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"deadline": "2026-05-15T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="task_distribution", params={"mode": "ramp_up"})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_deadline_driven_deadline_tasks(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8, l2_metadata={"deadline": "2026-05-15T00:00:00"}),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="task_distribution", params={"mode": "deadline_driven"})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_even_with_task_ids(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="task_distribution", params={
                "mode": "even",
                "task_ids": ["a", "b"],
                "weight": 10,
            })
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_unknown_mode_noop(self):
        tasks = [L1TaskSpec(id="a", total_duration=8)]
        constraints = [
            ConstraintSpec(type="task_distribution", params={"mode": "nonexistent"})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"

    def test_earliest_bias_does_nothing_extra(self):
        tasks = [
            L1TaskSpec(id="a", total_duration=8),
            L1TaskSpec(id="b", total_duration=8),
        ]
        constraints = [
            ConstraintSpec(type="task_distribution", params={"mode": "earliest_bias"})
        ]
        assignments, cap = run_allocate(tasks, constraints, horizon_weeks=2)
        assert cap.status == "OK"
