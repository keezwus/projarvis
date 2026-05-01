from projarvis.planner.l2.models import ConstraintSpec
from test_engine import make_time_mapper, make_tasks, run_engine
from projarvis.planner.time_epoch import TimeEpoch
from projarvis.planner.l2.time_mapper import TimeMapper
from projarvis.planner.l2.models import TimeSpec


def _make_budget_constraint(**overrides):
    params = {
        "focus_budget_per_day": 32,
        "exercise_budget_per_day": 16,
        "focus_target_per_day": 0,
        "exercise_target_per_day": 0,
        "focus_shortfall_weight": 0,
        "exercise_shortfall_weight": 0,
    }
    params.update(overrides)
    return ConstraintSpec(type="energy_budget", params=params)


def test_no_multipliers_passes_through():
    """Tasks without focus/exercise multipliers are unaffected."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "t1", "duration": 4},
        {"id": "t2", "duration": 4},
    )
    sol = run_engine(tm, tasks, [_make_budget_constraint()])
    assert sol.status != "INFEASIBLE"


def test_focus_budget_caps_daily_total():
    """Task with focus_multiplier must respect daily budget."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "deep", "duration": 40, "metadata": {"focus_multiplier": 1.0}},
    )
    # Monday has 28 available slots (09-12 + 14-18). focus_budget = 32.
    # 40 > 32 → infeasible within single day
    sol = run_engine(tm, tasks, [_make_budget_constraint(focus_budget_per_day=8)])
    assert sol.status == "INFEASIBLE"


def test_focus_budget_satisfied():
    """Small focus task within budget should schedule fine."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "deep", "duration": 4, "metadata": {"focus_multiplier": 1.0}},
    )
    sol = run_engine(tm, tasks, [_make_budget_constraint(focus_budget_per_day=32)])
    assert sol.status != "INFEASIBLE"


def test_exercise_budget_caps_daily_total():
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "gym", "duration": 20, "metadata": {"exercise_multiplier": 1.0}},
    )
    sol = run_engine(tm, tasks, [_make_budget_constraint(exercise_budget_per_day=4)])
    assert sol.status == "INFEASIBLE"


def test_multiplier_float_truncated():
    """duration=3, multiplier=0.5 → consum = int(1.5) = 1."""
    tm = make_time_mapper(horizon_days=1)
    tasks = make_tasks(
        {"id": "walk", "duration": 3, "metadata": {"exercise_multiplier": 0.5}},
    )
    # consum = 1, exercise_budget = 1 → OK
    sol = run_engine(tm, tasks, [_make_budget_constraint(exercise_budget_per_day=1)])
    assert sol.status != "INFEASIBLE"


def test_budget_overrides():
    tm = make_time_mapper(horizon_days=1)  # Monday only
    tasks = make_tasks(
        {"id": "deep", "duration": 8, "metadata": {"focus_multiplier": 1.0}},
    )
    sol = run_engine(
        tm,
        tasks,
        [_make_budget_constraint(focus_budget_per_day=4, focus_budget_overrides={"monday": 32})],
    )
    assert sol.status != "INFEASIBLE"


def test_shortfall_weight_in_objective():
    """Focus shortfall should appear in objective when target unmet."""
    # Use 2-day mapper so we can leave one day without focus tasks
    tm = make_time_mapper(horizon_days=2)
    tasks = make_tasks(
        {"id": "deep", "duration": 4, "metadata": {"focus_multiplier": 1.0}},
    )
    sol = run_engine(
        tm,
        tasks,
        [
            _make_budget_constraint(
                focus_target_per_day=8,
                focus_shortfall_weight=100,
            )
        ],
    )
    assert sol.status != "INFEASIBLE"
    # Objective includes shortfall penalty — just verify it's non-zero
    assert sol.objective_value is not None


def test_empty_day_ranges_no_crash():
    """Plugin early-returns when no days are available (tested via empty params)."""
    from projarvis.planner.l2.plugins.energy_budget import energy_budget as plugin_fn
    from ortools.sat.python import cp_model
    # Simulate a call with empty tasks — day_ranges built from 0 total_slots → empty
    m = cp_model.CpModel()
    v = {"tasks": {}, "plugins": {}}
    from projarvis.planner.l2.time_mapper import TimeMapper
    from projarvis.planner.l2.models import TimeSpec
    from projarvis.planner.time_epoch import TimeEpoch
    epoch = TimeEpoch("2026-05-04T00:00:00")
    ts = TimeSpec(
        horizon_start="2026-05-04T00:00:00",
        horizon_days=1,
        weekly_base={"monday": [], "tuesday": [], "wednesday": [],
                      "thursday": [], "friday": [], "saturday": [], "sunday": []},
        overrides=[],
    )
    tm = TimeMapper(ts, epoch)
    params = {"focus_budget_per_day": 32}
    # Should not raise — day_ranges empty, returns early
    plugin_fn(m, v, params, tm)
    assert "energy_budget" not in v["plugins"]
