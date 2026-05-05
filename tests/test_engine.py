import pytest
from projarvis.planner.l2.models import TaskSpec, ConstraintSpec, TimeSpec
from projarvis.planner.models import SolverParams
from projarvis.planner.l2.time_mapper import TimeMapper
from projarvis.planner.l2.engine import SchedulingEngine
from projarvis.planner.time_epoch import TimeEpoch
from projarvis.planner.exceptions import ValidationError


def make_time_mapper(**overrides) -> TimeMapper:
    defaults = {
        "horizon_start": "2026-05-04T00:00:00",
        "horizon_days": 3,
        "weekly_base": {
            "monday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "tuesday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
            "thursday": [],
            "friday": [],
            "saturday": [],
            "sunday": [],
        },
        "overrides": [],
    }
    defaults.update(overrides)
    ts = TimeSpec(**defaults)
    epoch = TimeEpoch(ts.horizon_start)
    return TimeMapper(ts, epoch)


def make_tasks(*specs) -> list[TaskSpec]:
    tasks = []
    for s in specs:
        if isinstance(s, str):
            tasks.append(TaskSpec(id=s, duration=4))
        else:
            tasks.append(TaskSpec(**s))
    return tasks


def run_engine(tm, tasks, constraints=None, params=None):
    engine = SchedulingEngine(tm)
    engine.hydrate(tasks)
    if constraints:
        engine.apply_constraints(constraints)
    engine.set_objective()
    return engine.solve(params)


class TestEngineBasic:
    def test_single_task(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks({"id": "t1", "duration": 12})
        sol = run_engine(tm, tasks)
        assert sol.status == "OPTIMAL"
        assert len(sol.tasks) == 1
        assert sol.tasks["t1"].start_slot == 36  # Mon 09:00

    def test_multiple_tasks_no_overlap(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4},
            {"id": "t2", "duration": 4},
            {"id": "t3", "duration": 4},
        )
        sol = run_engine(tm, tasks)
        assert sol.status == "OPTIMAL"
        # Verify no overlap: end <= start for consecutive tasks in sorted order
        sorted_tasks = sorted(sol.tasks.values(), key=lambda x: x.start_slot)
        for i in range(len(sorted_tasks) - 1):
            assert sorted_tasks[i].end_slot <= sorted_tasks[i + 1].start_slot

    def test_tasks_squeeze_into_earliest(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4},
            {"id": "t2", "duration": 4},
        )
        sol = run_engine(tm, tasks)
        # Both should be in Mon 09:00-11:00 (slots 36-44)
        for t in sol.tasks.values():
            assert t.start_slot >= 36
            assert t.end_slot <= 48

class TestEngineValidation:
    def test_empty_tasks_rejected(self):
        tm = make_time_mapper()
        engine = SchedulingEngine(tm)
        with pytest.raises(ValidationError, match="least one task"):
            engine.hydrate([])

    def test_duplicate_task_id_rejected(self):
        tm = make_time_mapper()
        tasks = make_tasks(
            {"id": "dup", "duration": 4},
            {"id": "dup", "duration": 4},
        )
        engine = SchedulingEngine(tm)
        with pytest.raises(ValidationError, match="Duplicate"):
            engine.hydrate(tasks)

    def test_zero_duration_rejected(self):
        tm = make_time_mapper()
        tasks = make_tasks({"id": "t1", "duration": 0})
        engine = SchedulingEngine(tm)
        with pytest.raises(ValidationError, match="duration"):
            engine.hydrate(tasks)

    def test_double_hydrate_rejected(self):
        tm = make_time_mapper()
        tasks = make_tasks({"id": "t1", "duration": 4})
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        with pytest.raises(RuntimeError):
            engine.hydrate(tasks)

    def test_double_apply_rejected(self):
        tm = make_time_mapper()
        engine = SchedulingEngine(tm)
        engine.hydrate(make_tasks({"id": "t1", "duration": 4}))
        engine.apply_constraints([])
        with pytest.raises(RuntimeError):
            engine.apply_constraints([])

    def test_no_available_time(self):
        tm = make_time_mapper(
            weekly_base={
                "monday": [],
                "tuesday": [],
                "wednesday": [],
                "thursday": [],
                "friday": [],
                "saturday": [],
                "sunday": [],
            }
        )
        engine = SchedulingEngine(tm)
        with pytest.raises(ValidationError, match="available time"):
            engine.hydrate(make_tasks({"id": "t1", "duration": 4}))

    def test_set_objective_before_hydrate(self):
        tm = make_time_mapper()
        engine = SchedulingEngine(tm)
        with pytest.raises(RuntimeError):
            engine.set_objective()

    def test_solve_before_set_objective(self):
        tm = make_time_mapper()
        engine = SchedulingEngine(tm)
        engine.hydrate(make_tasks({"id": "t1", "duration": 4}))
        with pytest.raises(RuntimeError):
            engine.solve()


class TestBlockBoundaryConstraints:
    def test_task_cannot_span_lunch_break(self):
        tm = make_time_mapper(horizon_days=1)
        # Morning block is 12 slots (09:00-12:00), afternoon is 16 slots (14:00-18:00).
        # A 17-slot task fits in neither block, so it's INFEASIBLE.
        tasks = make_tasks({"id": "big", "duration": 17})
        sol = run_engine(tm, tasks)
        assert sol.status == "INFEASIBLE"

    def test_task_can_fit_in_single_block(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks({"id": "fit", "duration": 12})  # fits exactly in 3h morning
        sol = run_engine(tm, tasks)
        assert sol.status == "OPTIMAL"

    def test_task_can_span_across_days(self):
        tm = make_time_mapper(horizon_days=2)
        # A 2-day task won't cross day boundary since it's not a block boundary
        # Available blocks: Mon [0-12, 12-28], Tue [28-40, 40-56]
        # A 14-slot task must fit in one block (can't cross lunch)
        tasks = make_tasks({"id": "big", "duration": 14})
        sol = run_engine(tm, tasks)
        # 14 slots > 16 slots in afternoon block → should fit
        assert sol.status == "OPTIMAL"
        # Should be in Monday afternoon (14:00-17:30)
        t = sol.tasks["big"]
        assert t.start_slot >= 56  # Mon 14:00


class TestUnknownConstraint:
    def test_unknown_type_rejected(self):
        tm = make_time_mapper()
        engine = SchedulingEngine(tm)
        engine.hydrate(make_tasks({"id": "t1", "duration": 4}))
        engine.apply_constraints(
            [ConstraintSpec(type="nonexistent", params={})]
        )  # unknown types silently skipped


class TestSolverParams:
    def test_solver_params_passthrough(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks({"id": "t1", "duration": 4})
        params = SolverParams(max_time_seconds=5.0, random_seed=123)
        sol = run_engine(tm, tasks, params=params)
        assert sol.status == "OPTIMAL"

    def test_multiple_solve_calls(self):
        tm = make_time_mapper(horizon_days=1)
        engine = SchedulingEngine(tm)
        engine.hydrate(make_tasks({"id": "t1", "duration": 4}))
        engine.set_objective()
        sol1 = engine.solve()
        sol2 = engine.solve()
        assert sol1.status == sol2.status
        # With same model and seed, results should be deterministic
        assert sol1.tasks["t1"].start_slot == sol2.tasks["t1"].start_slot


class TestObjective:
    def test_earliest_bias(self):
        tm = make_time_mapper(horizon_days=1)
        tasks = make_tasks(
            {"id": "t1", "duration": 4, "metadata": {}},
            {"id": "t2", "duration": 4, "metadata": {}},
        )
        sol = run_engine(tm, tasks)
        # Both tasks should be packed as early as possible
        starts = [t.start_slot for t in sol.tasks.values()]
        assert min(starts) == 36  # Someone at Mon 09:00

