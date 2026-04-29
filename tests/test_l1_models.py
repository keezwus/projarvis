from projarvis.planner.l1.models import (
    LongHorizonSpec,
    L1TaskSpec,
    ConstraintSpec,
    HorizonWindow,
    CapacityReport,
    ConflictReport,
    WeekSolution,
    MultiWeekSolution,
)


class TestLongHorizonSpec:
    def test_defaults(self):
        spec = LongHorizonSpec(horizon_start="2026-05-04T00:00:00")
        assert spec.horizon_weeks == 4
        assert spec.weekly_available == {}
        assert spec.overrides == []


class TestL1TaskSpec:
    def test_minimal(self):
        t = L1TaskSpec(id="task1", total_duration=16)
        assert t.priority == 999
        assert t.l2_metadata == {}

    def test_full(self):
        t = L1TaskSpec(
            id="task1",
            total_duration=32,
            priority=1,
            l2_metadata={"key": "value"},
        )
        assert t.total_duration == 32
        assert t.priority == 1
        assert t.l2_metadata == {"key": "value"}


class TestCapacityReport:
    def test_default_ok(self):
        r = CapacityReport()
        assert r.status == "OK"

    def test_oversaturated(self):
        r = CapacityReport(status="OVERSATURATED")
        assert r.status == "OVERSATURATED"


class TestConflictReport:
    def test_defaults(self):
        cr = ConflictReport(week_index=0)
        assert cr.conflicts == []
        assert cr.suggestion == ""


class TestWeekSolution:
    def test_no_solution(self):
        ws = WeekSolution(week_index=0, start_iso="2026-05-04T00:00:00")
        assert ws.solution is None
        assert ws.week_index == 0


class TestMultiWeekSolution:
    def test_defaults(self):
        sol = MultiWeekSolution()
        assert sol.status == "OK"
        assert sol.weekly_solutions == []
        assert sol.unassigned_tasks == []
