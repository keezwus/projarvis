import pytest
from projarvis.planner.l2.models import TaskSpec, ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine

# Monday 09:00 = real slot 36, 10:00 = 40, 11:00 = 44, 12:00 = 48, 13:00 = 52


def test_deadline_constrains_single_task():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4, "metadata": {"deadline": "2026-05-04T11:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="deadline", params={})])
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    assert t1.end_slot <= 44  # 11:00


def test_deadline_no_metadata_passes_through():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks({"id": "t1", "duration": 4})
    sol = run_engine(tm, tasks, [ConstraintSpec(type="deadline", params={})])
    assert sol.status != "INFEASIBLE"


def test_deadline_too_tight_causes_infeasible():
    tm = make_time_mapper(horizon_days=1)  # Monday 09:00-12:00
    tasks = make_tasks(
        {"id": "big", "duration": 8, "metadata": {"deadline": "2026-05-04T10:00:00"}},
    )
    # task 8 slots, earliest end = 36+8=44 > 40 (10:00)
    sol = run_engine(tm, tasks, [ConstraintSpec(type="deadline", params={})])
    assert sol.status == "INFEASIBLE"


def test_deadline_resolves_nearest_when_outside_availability():
    """Deadline at 13:00 (lunch gap) snaps to 11:45 (last morning slot)."""
    tm = make_time_mapper(horizon_days=1)  # Monday 09:00-12:00, 14:00-18:00
    tasks = make_tasks(
        {"id": "t1", "duration": 2, "metadata": {"deadline": "2026-05-04T13:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="deadline", params={})])
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    assert t1.end_slot <= 47  # snapped to last morning slot (11:45)


def test_deadline_all_tasks_constrained():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 3, "metadata": {"deadline": "2026-05-04T11:00:00"}},
        {"id": "t2", "duration": 3, "metadata": {"deadline": "2026-05-04T11:00:00"}},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="deadline", params={})])
    assert sol.status != "INFEASIBLE"
    for tid in ("t1", "t2"):
        assert sol.tasks[tid].end_slot <= 44
