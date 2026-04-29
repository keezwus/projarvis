from __future__ import annotations

import json

from .models import (
    TaskSpec,
    ConstraintSpec,
    TimeSpec,
    TaskResult,
    Solution,
)
from projarvis.planner.models import SolverParams
from projarvis.planner.exceptions import ValidationError


def parse_schedule(
    json_dict: dict,
) -> tuple[TimeSpec, list[TaskSpec], list[ConstraintSpec], SolverParams | None]:
    ts = _parse_time_spec(json_dict.get("time_spec", {}))
    tasks = _parse_tasks(json_dict.get("tasks", []))
    constraints = _parse_constraints(json_dict.get("constraints", []))
    solver = _parse_solver(json_dict.get("solver"))
    return ts, tasks, constraints, solver


def dumps(solution: Solution) -> str:
    return json.dumps(_solution_to_dict(solution), ensure_ascii=False, indent=2)


# ── internal ────────────────────────────────────────────────────

def _parse_time_spec(d: dict) -> TimeSpec:
    return TimeSpec(
        horizon_start=d.get("horizon_start", ""),
        horizon_days=d.get("horizon_days", 7),
        weekly_base=d.get("weekly_base", {}),
        overrides=d.get("overrides", []),
    )


def _parse_tasks(arr: list[dict]) -> list[TaskSpec]:
    seen: set[str] = set()
    tasks: list[TaskSpec] = []
    for item in arr:
        tid = item["id"]
        if tid in seen:
            raise ValidationError(f"Duplicate task id: {tid!r}")
        seen.add(tid)
        tasks.append(
            TaskSpec(
                id=tid,
                duration=item["duration"],
                metadata=item.get("metadata", {}),
            )
        )
    return tasks


def _parse_constraints(arr: list[dict]) -> list[ConstraintSpec]:
    return [ConstraintSpec(type=item["type"], params=item.get("params", {})) for item in arr]


def _parse_solver(d: dict | None) -> SolverParams | None:
    if d is None:
        return None
    return SolverParams(
        max_time_seconds=d.get("max_time_seconds", 30.0),
        num_workers=d.get("num_workers", 0),
        random_seed=d.get("random_seed"),
        verbose=d.get("verbose", False),
    )


def _solution_to_dict(sol: Solution) -> dict:
    return {
        "status": sol.status,
        "solve_time_ms": sol.solve_time_ms,
        "objective_value": sol.objective_value,
        "tasks": {
            tid: {
                "start_slot": tr.start_slot,
                "end_slot": tr.end_slot,
                "duration_slots": tr.duration_slots,
            }
            for tid, tr in sol.tasks.items()
        },
        "conflicts": sol.conflicts,
    }
