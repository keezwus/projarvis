from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine


# Monday 09:00-12:00 = compressed slots 0-11 (real 36-47)
# Monday 14:00-18:00 = compressed slots 12-27 (real 56-71)
# Tuesday 09:00-12:00 = compressed slots 28-39 (real 132-143)
# Tuesday 14:00-18:00 = compressed slots 40-55 (real 152-167)


class TestScheduleStabilityL2:
    def test_high_weight_stays(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "coding", "duration": 4,
             "metadata": {"previous_start": "2026-05-04T15:00:00"}},
            {"id": "meeting", "duration": 4},
        )
        sol = run_engine(
            tm, tasks,
            [ConstraintSpec(type="schedule_stability",
                            params={"default_weight": 10})],
        )
        assert sol.status != "INFEASIBLE"
        # 15:00 Mon = real slot 60 → compressed slot 16
        # With weight=10, task should stay near original position
        t = sol.tasks["coding"]
        assert t.start_slot == 60
        assert t.duration_slots == 4

    def test_weight_1_no_stability(self):
        """weight=1 → derivative=0 for start < ps, task drifts to earliest."""
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "coding", "duration": 4,
             "metadata": {"previous_start": "2026-05-04T15:00:00"}},
            {"id": "meeting", "duration": 4},
        )
        sol = run_engine(
            tm, tasks,
            [ConstraintSpec(type="schedule_stability",
                            params={"default_weight": 1})],
        )
        assert sol.status != "INFEASIBLE"
        # weight=1: flat for start < ps, task likely drifts to earlier slot
        # Both tasks will be packed as early as possible
        starts = [t.start_slot for t in sol.tasks.values()]
        assert min(starts) == 36  # someone at Mon 09:00

    def test_default_weight_5_works(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "coding", "duration": 4,
             "metadata": {"previous_start": "2026-05-04T10:00:00"}},
        )
        sol = run_engine(
            tm, tasks,
            [ConstraintSpec(type="schedule_stability", params={})],
        )
        assert sol.status != "INFEASIBLE"
        # Default weight=5 > 1 → task stays at original position
        t = sol.tasks["coding"]
        assert t.start_slot == 40  # Mon 10:00

    def test_no_metadata_noop(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4},
            {"id": "t2", "duration": 4},
        )
        sol = run_engine(
            tm, tasks,
            [ConstraintSpec(type="schedule_stability",
                            params={"default_weight": 5})],
        )
        assert sol.status != "INFEASIBLE"
        assert len(sol.tasks) == 2

    def test_outside_availability_skipped(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4,
             "metadata": {"previous_start": "2026-05-04T13:00:00"}},
        )
        sol = run_engine(
            tm, tasks,
            [ConstraintSpec(type="schedule_stability",
                            params={"default_weight": 5})],
        )
        # previous_start in lunch gap → skipped, task scheduled normally
        assert sol.status != "INFEASIBLE"
