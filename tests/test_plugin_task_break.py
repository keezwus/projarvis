from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine


def test_task_break_minimum_gap():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(
        tm, tasks, [ConstraintSpec(type="task_break", params={"default_gap": 1})]
    )
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    t2 = sol.tasks["t2"]
    if t1.start_slot < t2.start_slot:
        assert t2.start_slot >= t1.end_slot + 1
    else:
        assert t1.start_slot >= t2.end_slot + 1


def test_task_break_custom_gap():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(
        tm, tasks, [ConstraintSpec(type="task_break", params={"default_gap": 3})]
    )
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    t2 = sol.tasks["t2"]
    if t1.start_slot < t2.start_slot:
        assert t2.start_slot >= t1.end_slot + 3
    else:
        assert t1.start_slot >= t2.end_slot + 3


def test_task_break_default_gap_one():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(tm, tasks, [ConstraintSpec(type="task_break", params={})])
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    t2 = sol.tasks["t2"]
    if t1.start_slot < t2.start_slot:
        assert t2.start_slot >= t1.end_slot + 1
    else:
        assert t1.start_slot >= t2.end_slot + 1


def test_task_break_single_task_skips():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks({"id": "t1", "duration": 4})
    sol = run_engine(tm, tasks, [ConstraintSpec(type="task_break", params={})])
    assert sol.status != "INFEASIBLE"


def test_task_break_exempt_ids():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "walk", "duration": 1},
        {"id": "t1", "duration": 4},
    )
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="task_break", params={"default_gap": 4, "exempt_task_ids": ["walk"]})],
    )
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    walk = sol.tasks["walk"]
    # walk is exempt, so t1-walk pair may have gap < 4
    if t1.start_slot < walk.start_slot:
        gap = walk.start_slot - t1.end_slot
    else:
        gap = t1.start_slot - walk.end_slot
    assert gap < 4  # exempt pair — no forced 4-slot gap


def test_task_break_all_exempt_no_constraints():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "walk", "duration": 1},
        {"id": "meal", "duration": 1},
    )
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="task_break", params={"exempt_task_ids": ["walk", "meal"]})],
    )
    assert sol.status != "INFEASIBLE"


def test_task_break_three_tasks():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 2},
        {"id": "t2", "duration": 2},
        {"id": "t3", "duration": 2},
    )
    sol = run_engine(
        tm, tasks, [ConstraintSpec(type="task_break", params={"default_gap": 1})]
    )
    assert sol.status != "INFEASIBLE"
    # All pairs must have at least 1 gap
    ids = ["t1", "t2", "t3"]
    for i in range(3):
        for j in range(i + 1, 3):
            a = sol.tasks[ids[i]]
            b = sol.tasks[ids[j]]
            if a.start_slot < b.start_slot:
                assert b.start_slot >= a.end_slot + 1, f"{ids[i]}-{ids[j]} gap too small"
            else:
                assert a.start_slot >= b.end_slot + 1, f"{ids[i]}-{ids[j]} gap too small"


def test_task_break_does_not_expand_gap_artificially():
    """Gap should be exactly 1 when no other constraints force it larger."""
    tm = make_time_mapper(horizon_days=1)  # 28 available slots
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(
        tm, tasks, [ConstraintSpec(type="task_break", params={"default_gap": 1})]
    )
    assert sol.status != "INFEASIBLE"
    t1 = sol.tasks["t1"]
    t2 = sol.tasks["t2"]
    if t1.start_slot < t2.start_slot:
        gap = t2.start_slot - t1.end_slot
    else:
        gap = t1.start_slot - t2.end_slot
    assert gap == 1, f"Expected gap 1, got {gap}"
