from dataclasses import dataclass, field

from projarvis.planner.l2.models import Solution as L2Solution


@dataclass
class ConstraintSpec:
    type: str
    params: dict


@dataclass
class LongHorizonSpec:
    horizon_start: str
    horizon_weeks: int = 4
    weekly_available: dict[str, list[list[str]]] = field(default_factory=dict)
    overrides: list[dict] = field(default_factory=list)


@dataclass
class L1TaskSpec:
    id: str
    total_duration: int
    priority: int = 999
    l2_metadata: dict = field(default_factory=dict)


@dataclass
class HorizonWindow:
    week_index: int
    start_iso: str
    available_slots: int


@dataclass
class CapacityReport:
    status: str = "OK"  # OK | OVERSATURATED


@dataclass
class ConflictReport:
    week_index: int
    conflicts: list[str] = field(default_factory=list)
    suggestion: str = ""


@dataclass
class WeekSolution:
    week_index: int
    start_iso: str
    solution: L2Solution | None = None


@dataclass
class MultiWeekSolution:
    status: str = "OK"  # OK | PARTIAL | INFEASIBLE
    weekly_solutions: list[WeekSolution] = field(default_factory=list)
    unassigned_tasks: list[L1TaskSpec] = field(default_factory=list)
    capacity_report: CapacityReport | None = None
    conflict_reports: list[ConflictReport] = field(default_factory=list)
