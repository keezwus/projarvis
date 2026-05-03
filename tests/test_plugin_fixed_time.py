from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine


# Monday 09:00-12:00 = compressed slots 0-11 (real 36-47)
# Monday 14:00-18:00 = compressed slots 12-27 (real 56-71)
# Tuesday 09:00-12:00 = compressed slots 28-39 (real 132-143)
# Tuesday 14:00-18:00 = compressed slots 40-55 (real 152-167)


def test_fixed_time_locks_start_and_end():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "meeting", "duration": 4, "metadata": {"fixed_time": "2026-05-04T10:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="fixed_time", params={})])
    assert sol.status != "INFEASIBLE"
    t = sol.tasks["meeting"]
    # 10:00 Mon = real slot 40
    assert t.start_slot == 40
    assert t.end_slot == 44
    assert t.duration_slots == 4


def test_fixed_time_mixed_tasks():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "meeting", "duration": 4, "metadata": {"fixed_time": "2026-05-04T10:00:00"}},
        {"id": "coding", "duration": 4},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="fixed_time", params={})])
    assert sol.status != "INFEASIBLE"
    # meeting locked at 10:00
    assert sol.tasks["meeting"].start_slot == 40
    # coding fills elsewhere, no overlap
    assert sol.tasks["coding"].start_slot != 40


def test_fixed_time_no_metadata_noop():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="fixed_time", params={})])
    assert sol.status != "INFEASIBLE"
    assert len(sol.tasks) == 2


def test_fixed_time_outside_availability():
    """fixed_time at 13:00 (lunch gap) — resolve_time_ref raises, plugin skips,
    task still exists but can't be placed → INFEASIBLE or scheduled elsewhere."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "meeting", "duration": 4, "metadata": {"fixed_time": "2026-05-04T13:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="fixed_time", params={})])
    # resolve_time_ref raises TimeMappingError, fixed_time plugin skips the task.
    # The task still has no fixed-time constraint, so it gets scheduled normally.
    assert sol.status != "INFEASIBLE"
    # Task was placed somewhere (just not at 13:00 since that's unavailable)
    t = sol.tasks["meeting"]
    assert t.start_slot >= 36  # somewhere on Monday


def test_fixed_time_multiple_tasks():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "morning", "duration": 2, "metadata": {"fixed_time": "2026-05-04T10:00:00"}},
        {"id": "afternoon", "duration": 4, "metadata": {"fixed_time": "2026-05-04T15:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="fixed_time", params={})])
    assert sol.status != "INFEASIBLE"
    # 10:00 Mon = real slot 40
    assert sol.tasks["morning"].start_slot == 40
    assert sol.tasks["morning"].duration_slots == 2
    # 15:00 Mon = real slot 60
    assert sol.tasks["afternoon"].start_slot == 60
    assert sol.tasks["afternoon"].duration_slots == 4
    # no overlap
    assert sol.tasks["morning"].end_slot <= sol.tasks["afternoon"].start_slot or \
        sol.tasks["afternoon"].end_slot <= sol.tasks["morning"].start_slot
