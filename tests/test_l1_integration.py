import json

from projarvis.planner.l1.engine import L1Engine
from projarvis.planner.l1.serialization import parse_long_horizon, serialize_solution
from projarvis.planner.l1.models import MultiWeekSolution
from projarvis.planner.models import SolverParams
from tests.conftest import load_fixture


class TestL1EndToEnd:
    """Full L1 pipeline: JSON → parse → partition → allocate → schedule → JSON."""

    def test_multi_week_distribution(self):
        data = load_fixture("two_week_horizon.json")
        spec, tasks, constraints, solver_params = parse_long_horizon(data)

        engine = L1Engine(spec)
        windows = engine.partition()

        # 2 weeks, each has 5 weekdays × 12 slots = 60, but Tue w0 removed → 48
        assert len(windows) == 2
        assert windows[0].available_slots == 48  # Mon-Fri but Tue removed
        assert windows[1].available_slots == 60  # full 5 days

        assignments, cap_report = engine.allocate(tasks)
        assert cap_report.status == "OK"

        # 4 tasks total: 8+12+8+4 = 32 slots in w0 (48 available) → all fit w0
        # earliest-bias should pack all into week 0
        w0_total = sum(t.total_duration for t in assignments.get(0, []))
        w1_total = sum(t.total_duration for t in assignments.get(1, []))
        assert w0_total + w1_total == 32  # all assigned

        result = engine.schedule(solver_params)
        assert result.status == "OK"
        assert result.capacity_report.status == "OK"

        # Verify per-week no overlaps
        for ws in result.weekly_solutions:
            if ws.solution is None:
                continue
            assert ws.solution.status in ("OPTIMAL", "FEASIBLE")
            sorted_tasks = sorted(
                ws.solution.tasks.values(), key=lambda x: x.start_slot
            )
            for i in range(len(sorted_tasks) - 1):
                assert sorted_tasks[i].end_slot <= sorted_tasks[i + 1].start_slot, (
                    f"Week {ws.week_index}: {sorted_tasks[i].id} overlaps {sorted_tasks[i+1].id}"
                )

    def test_oversaturated(self):
        """Tasks exceeding all weekly capacity → OVERSATURATED."""
        from projarvis.planner.l1.models import LongHorizonSpec, L1TaskSpec

        spec = LongHorizonSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_weeks=1,
            weekly_available={"monday": [["09:00", "10:00"]]},  # 4 slots
        )
        engine = L1Engine(spec)
        engine.partition()

        tasks = [L1TaskSpec(id=f"big_{i}", total_duration=100) for i in range(3)]
        assignments, cap_report = engine.allocate(tasks)
        assert cap_report.status == "OVERSATURATED"
        assert assignments == {}

        result = engine.schedule()
        assert result.status == "INFEASIBLE"

    def test_empty_tasks(self):
        from projarvis.planner.l1.models import LongHorizonSpec

        spec = LongHorizonSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_weeks=2,
            weekly_available={"monday": [["09:00", "12:00"]]},
        )
        engine = L1Engine(spec)
        engine.partition()

        assignments, cap_report = engine.allocate([])
        assert cap_report.status == "OK"
        assert assignments == {}

        result = engine.schedule()
        assert result.status == "INFEASIBLE"  # no assignments → INFEASIBLE

    def test_serialization_roundtrip(self):
        data = load_fixture("two_week_horizon.json")
        spec, tasks, constraints, solver_params = parse_long_horizon(data)

        engine = L1Engine(spec)
        engine.partition()
        engine.allocate(tasks)
        result = engine.schedule(solver_params)

        from projarvis.planner.time_epoch import TimeEpoch
        epoch = TimeEpoch(spec.horizon_start)
        json_str = serialize_solution(result, epoch)
        parsed = json.loads(json_str)

        assert parsed["status"] in ("OK", "PARTIAL", "INFEASIBLE")
        assert len(parsed["weekly_solutions"]) == 2
        assert isinstance(parsed["capacity_report"]["status"], str)
        # Tasks IDs unchanged from input
        weekly_task_ids = set()
        for ws in parsed["weekly_solutions"]:
            if ws["solution"] is not None:
                for tid in ws["solution"]["tasks"]:
                    weekly_task_ids.add(tid)
        assert weekly_task_ids.issubset({t.id for t in tasks})


class TestL1ConstraintPassThrough:
    """Constraints flow from L1 schedule() into per-week L2 apply_constraints()."""

    def test_dependency_passthrough(self):
        from projarvis.planner.l1.models import (
            LongHorizonSpec,
            L1TaskSpec,
            ConstraintSpec,
        )

        spec = LongHorizonSpec(
            horizon_start="2026-05-04T00:00:00",
            horizon_weeks=1,
            weekly_available={"monday": [["09:00", "17:00"]]},
        )
        tasks = [
            L1TaskSpec(id="A", total_duration=4),
            L1TaskSpec(id="B", total_duration=4),
        ]
        constraints = [
            ConstraintSpec(type="dependency", params={"pairs": [["A", "B"]]})
        ]

        engine = L1Engine(spec)
        engine.partition()
        assignments, cap_report = engine.allocate(tasks)
        assert cap_report.status == "OK"

        result = engine.schedule(constraints=constraints)
        assert result.status == "OK"

        week0 = result.weekly_solutions[0].solution
        task_a = week0.tasks["A"]
        task_b = week0.tasks["B"]
        assert task_a.end_slot <= task_b.start_slot, (
            f"Dependency violated: A ends at {task_a.end_slot}, B starts at {task_b.start_slot}"
        )
