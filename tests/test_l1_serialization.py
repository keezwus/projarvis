import json

from projarvis.planner.l1.serialization import (
    parse_long_horizon,
    serialize_solution,
)
from projarvis.planner.l1.models import (
    MultiWeekSolution,
    WeekSolution,
    CapacityReport,
)


class TestParseLongHorizon:
    def test_minimal(self):
        data = {
            "horizon_spec": {"horizon_start": "2026-05-04T00:00:00"},
            "tasks": [
                {"id": "t1", "l1": {"total_duration": 8}, "l2": {"metadata": {}}}
            ],
            "constraints": [],
        }
        spec, tasks, constraints, solver = parse_long_horizon(data)
        assert spec.horizon_start == "2026-05-04T00:00:00"
        assert spec.horizon_weeks == 4  # default
        assert len(tasks) == 1
        assert tasks[0].id == "t1"
        assert tasks[0].total_duration == 8
        assert tasks[0].priority == 999  # default
        assert tasks[0].l2_metadata == {}
        assert len(constraints) == 0
        assert solver is None

    def test_full_structure(self):
        data = {
            "horizon_spec": {
                "horizon_start": "2026-05-04T00:00:00",
                "horizon_weeks": 3,
                "weekly_available": {
                    "monday": [["09:00", "12:00"]],
                    "tuesday": [],
                },
                "overrides": [
                    {"date": "2026-05-05T00:00:00", "action": "remove", "blocks": [["09:00", "12:00"]]}
                ],
            },
            "tasks": [
                {
                    "id": "task_a",
                    "l1": {"total_duration": 16, "priority": 1},
                    "l2": {"metadata": {"key": "value"}},
                },
            ],
            "constraints": [
                {"type": "deadline", "params": {"task_id": "task_a", "deadline": "2026-05-11T00:00:00"}},
            ],
            "solver": {"max_time_seconds": 15.0},
        }
        spec, tasks, constraints, solver = parse_long_horizon(data)
        assert spec.horizon_weeks == 3
        assert len(spec.weekly_available) == 2
        assert len(spec.overrides) == 1
        assert tasks[0].priority == 1
        assert tasks[0].l2_metadata == {"key": "value"}
        assert len(constraints) == 1
        assert constraints[0].type == "deadline"
        assert constraints[0].params["deadline"] == "2026-05-11T00:00:00"
        assert solver.max_time_seconds == 15.0

    def test_duplicate_ids_rejected(self):
        data = {
            "horizon_spec": {"horizon_start": "2026-05-04T00:00:00"},
            "tasks": [
                {"id": "dup", "l1": {"total_duration": 8}},
                {"id": "dup", "l1": {"total_duration": 4}},
            ],
        }
        try:
            parse_long_horizon(data)
            assert False, "should have raised"
        except Exception as e:
            assert "dup" in str(e)

    def test_invalid_duration_rejected(self):
        data = {
            "horizon_spec": {"horizon_start": "2026-05-04T00:00:00"},
            "tasks": [
                {"id": "bad", "l1": {"total_duration": 0}},
            ],
        }
        try:
            parse_long_horizon(data)
            assert False, "should have raised"
        except Exception as e:
            assert "total_duration" in str(e)


class TestSerializeSolution:
    def test_basic(self):
        sol = MultiWeekSolution(
            status="OK",
            weekly_solutions=[
                WeekSolution(week_index=0, start_iso="2026-05-04T00:00:00"),
            ],
            capacity_report=CapacityReport(status="OK"),
        )
        result = json.loads(serialize_solution(sol))
        assert result["status"] == "OK"
        assert len(result["weekly_solutions"]) == 1
        assert result["capacity_report"]["status"] == "OK"

    def test_with_conflicts(self):
        from projarvis.planner.l1.models import ConflictReport
        sol = MultiWeekSolution(
            status="PARTIAL",
            weekly_solutions=[
                WeekSolution(week_index=0, start_iso="2026-05-04T00:00:00"),
            ],
            capacity_report=CapacityReport(status="OK"),
            conflict_reports=[
                ConflictReport(week_index=1, conflicts=["no feasible slot"], suggestion="try week 2"),
            ],
        )
        result = json.loads(serialize_solution(sol))
        assert result["status"] == "PARTIAL"
        assert len(result["conflict_reports"]) == 1
        assert result["conflict_reports"][0]["week_index"] == 1
