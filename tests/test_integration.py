import json
import pytest
from projarvis.planner.time_mapper import TimeMapper
from projarvis.planner.l2.engine import SchedulingEngine
from projarvis.planner.serialization import parse_schedule, dumps
from projarvis.planner.models import SolverParams
from tests.conftest import load_fixture


class TestMinimalSchedule:
    def test_from_fixture(self):
        data = load_fixture("minimal_schedule.json")
        time_spec, tasks, constraints, solver_params = parse_schedule(data)

        tm = TimeMapper(time_spec)
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.apply_constraints(constraints)
        engine.set_objective()
        solution = engine.solve(solver_params)

        assert solution.status == "OPTIMAL"
        assert len(solution.tasks) == 4

        # Check IDs present
        for tid in ["standup", "deep_work", "lunch", "code_review"]:
            assert tid in solution.tasks

        # Check no overlaps
        sorted_tasks = sorted(solution.tasks.values(), key=lambda x: x.start_slot)
        for i in range(len(sorted_tasks) - 1):
            assert sorted_tasks[i].end_slot <= sorted_tasks[i + 1].start_slot, (
                f"{sorted_tasks[i].id} overlaps {sorted_tasks[i+1].id}"
            )

        # Check all tasks are within Monday available blocks
        # Mon blocks: 09:00-12:00 (slots 36-48), 14:00-18:00 (slots 56-72)
        for t in solution.tasks.values():
            in_morning = 36 <= t.start_slot < 48 and t.end_slot <= 48
            in_afternoon = 56 <= t.start_slot < 72 and t.end_slot <= 72
            assert in_morning or in_afternoon, (
                f"{t.id} starts at {t.start_slot}, ends at {t.end_slot} "
                f"— outside available blocks [36-48, 56-72]"
            )

    def test_serialization_roundtrip(self):
        data = load_fixture("minimal_schedule.json")
        time_spec, tasks, constraints, solver_params = parse_schedule(data)

        tm = TimeMapper(time_spec)
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.apply_constraints(constraints)
        engine.set_objective()
        solution = engine.solve(solver_params)

        json_str = dumps(solution)
        parsed = json.loads(json_str)

        assert parsed["status"] == "OPTIMAL"
        assert isinstance(parsed["solve_time_ms"], float)
        assert isinstance(parsed["objective_value"], (int, float))
        assert len(parsed["tasks"]) == 4


class TestFullWeekSchedule:
    def test_from_fixture(self):
        data = load_fixture("full_week.json")
        time_spec, tasks, constraints, solver_params = parse_schedule(data)

        tm = TimeMapper(time_spec)
        # Tue afternoon removed → Tue only has morning (12 slots)
        # Thu evening added 17:00-20:00 merges with 14:00-18:00 → 14:00-20:00 (24 slots)
        # Mon: 28, Tue: 12, Wed: 28, Thu: 36 (12+24), Fri: 24
        # Total: 28+12+28+36+24 = 128
        assert tm.total_slots == 128

        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.apply_constraints(constraints)
        engine.set_objective()
        solution = engine.solve(solver_params)

        assert solution.status == "OPTIMAL"
        assert len(solution.tasks) == 6

        # Check no overlaps
        sorted_tasks = sorted(solution.tasks.values(), key=lambda x: x.start_slot)
        for i in range(len(sorted_tasks) - 1):
            assert sorted_tasks[i].end_slot <= sorted_tasks[i + 1].start_slot


class TestInfeasibleSchedule:
    def test_too_many_tasks(self):
        """Schedule more tasks than available slots."""
        from projarvis.planner.models import TaskSpec, TimeSpec

        ts = TimeSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_days=1,
            weekly_base={"monday": [["09:00", "10:00"]]},  # only 1 hour = 4 slots
            overrides=[],
        )
        tasks = [TaskSpec(id=f"t{i}", duration=4) for i in range(3)]  # 3 tasks × 4 slots = 12 needed

        tm = TimeMapper(ts)
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.set_objective()
        solution = engine.solve()

        assert solution.status == "INFEASIBLE"
        assert solution.objective_value is None


class TestOverrideSchedule:
    def test_override_add_creates_new_block(self):
        from projarvis.planner.models import TaskSpec, TimeSpec

        ts = TimeSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_days=1,
            weekly_base={"monday": [["09:00", "12:00"]]},  # morning only
            overrides=[
                {"date": "2026-05-04T00:00:00", "action": "add", "blocks": [["18:00", "20:00"]]}
            ],
        )
        tm = TimeMapper(ts)
        # 09:00-12:00 = 12 slots + 18:00-20:00 = 8 slots = 20 total
        assert tm.total_slots == 20

        tasks = [TaskSpec(id="evening_task", duration=8)]
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.set_objective()
        solution = engine.solve()

        assert solution.status == "OPTIMAL"
        # Should be placed in the first available block (morning) due to earliest bias
        t = solution.tasks["evening_task"]
        assert t.start_slot == 36  # Monday 09:00
