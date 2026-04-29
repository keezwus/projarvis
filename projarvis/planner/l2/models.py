from dataclasses import dataclass, field


@dataclass
class TaskSpec:
    id: str
    duration: int  # 15-minute slots, >= 1
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ConstraintSpec:
    type: str
    params: dict


@dataclass
class TimeSpec:
    horizon_start: str              # ISO 8601 datetime, e.g. "2026-05-04T00:00:00"
    horizon_days: int = 7
    weekly_base: dict[str, list[list[str]]] = field(default_factory=dict)
    overrides: list[dict] = field(default_factory=list)



@dataclass
class TaskResult:
    id: str
    start_slot: int
    end_slot: int
    start_time: str
    end_time: str
    duration_slots: int


@dataclass
class Solution:
    status: str                     # OPTIMAL | FEASIBLE | INFEASIBLE
    solve_time_ms: float
    objective_value: float | None
    tasks: dict[str, TaskResult]
    conflicts: list[str] = field(default_factory=list)
