from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine


class TestScheduleLockL2:
    def test_locks_start(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "coding", "duration": 4,
             "metadata": {"locked_start": "2026-05-04T10:00:00"}},
        )
        sol = run_engine(tm, tasks, [ConstraintSpec(type="schedule_lock", params={})])
        assert sol.status != "INFEASIBLE"
        t = sol.tasks["coding"]
        # 10:00 Mon = real slot 40
        assert t.start_slot == 40
        assert t.duration_slots == 4

    def test_mixed_tasks(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "locked_task", "duration": 4,
             "metadata": {"locked_start": "2026-05-04T10:00:00"}},
            {"id": "free_task", "duration": 4},
        )
        sol = run_engine(tm, tasks, [ConstraintSpec(type="schedule_lock", params={})])
        assert sol.status != "INFEASIBLE"
        assert sol.tasks["locked_task"].start_slot == 40
        assert sol.tasks["free_task"].start_slot != 40

    def test_no_locked_start_noop(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4},
            {"id": "t2", "duration": 4},
        )
        sol = run_engine(tm, tasks, [ConstraintSpec(type="schedule_lock", params={})])
        assert sol.status != "INFEASIBLE"
        assert len(sol.tasks) == 2

    def test_outside_availability(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4,
             "metadata": {"locked_start": "2026-05-04T13:00:00"}},
        )
        sol = run_engine(tm, tasks, [ConstraintSpec(type="schedule_lock", params={})])
        # locked_start in lunch gap → skipped, task scheduled elsewhere
        assert sol.status != "INFEASIBLE"
        t = sol.tasks["t1"]
        assert t.start_slot >= 36  # somewhere on Monday
