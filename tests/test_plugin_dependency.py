from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine


def test_dependency_basic_ordering():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("review", "read")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"pairs": [["read", "review"]]})],
    )
    assert sol.status != "INFEASIBLE"
    read = sol.tasks["read"]
    review = sol.tasks["review"]
    assert review.start_slot >= read.end_slot


def test_dependency_with_buffer():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A", "B")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"buffer_slots": 4, "pairs": [["A", "B"]]})],
    )
    assert sol.status != "INFEASIBLE"
    assert sol.tasks["B"].start_slot >= sol.tasks["A"].end_slot + 4


def test_dependency_multiple_predecessors():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A", "B", "C")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"pairs": [["A", "C"], ["B", "C"]]})],
    )
    assert sol.status != "INFEASIBLE"
    c_start = sol.tasks["C"].start_slot
    assert c_start >= sol.tasks["A"].end_slot
    assert c_start >= sol.tasks["B"].end_slot


def test_dependency_chain():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A", "B", "C")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"pairs": [["A", "B"], ["B", "C"]]})],
    )
    assert sol.status != "INFEASIBLE"
    assert sol.tasks["B"].start_slot >= sol.tasks["A"].end_slot
    assert sol.tasks["C"].start_slot >= sol.tasks["B"].end_slot


def test_dependency_missing_pair_skipped():
    """Non-existent task_id in a pair is silently skipped."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"pairs": [["X", "A"]]})],
    )
    assert sol.status != "INFEASIBLE"


def test_dependency_empty_pairs():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A", "B")
    sol = run_engine(tm, tasks, [ConstraintSpec(type="dependency", params={})])
    assert sol.status != "INFEASIBLE"


def test_dependency_no_buffer_defaults_to_zero():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks("A", "B")
    sol = run_engine(
        tm,
        tasks,
        [ConstraintSpec(type="dependency", params={"pairs": [["A", "B"]]})],
    )
    assert sol.status != "INFEASIBLE"
    assert sol.tasks["B"].start_slot >= sol.tasks["A"].end_slot
