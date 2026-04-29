from __future__ import annotations

import json
from datetime import timedelta

from projarvis.planner.time_epoch import TimeEpoch, MINUTES_PER_SLOT

from .models import (
    LongHorizonSpec,
    L1TaskSpec,
    ConstraintSpec,
    MultiWeekSolution,
    WeekSolution,
    CapacityReport,
    ConflictReport,
)
from projarvis.planner.models import SolverParams
from projarvis.planner.exceptions import ValidationError


def parse_long_horizon(
    json_dict: dict,
) -> tuple[LongHorizonSpec, list[L1TaskSpec], list[ConstraintSpec], SolverParams | None]:
    spec = _parse_horizon_spec(json_dict.get("horizon_spec", {}))
    tasks = _parse_tasks(json_dict.get("tasks", []))
    constraints = _parse_constraints(json_dict.get("constraints", []))
    solver = _parse_solver(json_dict.get("solver"))
    return spec, tasks, constraints, solver


def serialize_solution(solution: MultiWeekSolution, epoch: TimeEpoch) -> str:
    return json.dumps(_solution_to_dict(solution, epoch), ensure_ascii=False, indent=2)


# ── internal parse ──────────────────────────────────────────────


def _parse_horizon_spec(d: dict) -> LongHorizonSpec:
    return LongHorizonSpec(
        horizon_start=d.get("horizon_start", ""),
        horizon_weeks=d.get("horizon_weeks", 4),
        weekly_available=d.get("weekly_available", {}),
        overrides=d.get("overrides", []),
    )


def _parse_tasks(arr: list[dict]) -> list[L1TaskSpec]:
    seen: set[str] = set()
    tasks: list[L1TaskSpec] = []
    for item in arr:
        tid = item["id"]
        if tid in seen:
            raise ValidationError(f"Duplicate task id: {tid!r}")
        seen.add(tid)
        l1 = item.get("l1", {})
        l2 = item.get("l2", {})
        duration = l1["total_duration"]
        if not isinstance(duration, int) or duration < 1:
            raise ValidationError(
                f"Task {tid!r}: total_duration must be >= 1, got {duration}"
            )
        tasks.append(L1TaskSpec(
            id=tid,
            total_duration=duration,
            priority=l1.get("priority", 999),
            l2_metadata=l2.get("metadata", {}),
        ))
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


# ── internal serialize ──────────────────────────────────────────


def _solution_to_dict(sol: MultiWeekSolution, epoch: TimeEpoch) -> dict:
    return {
        "status": sol.status,
        "weekly_solutions": [
            _week_solution_to_dict(ws, epoch) for ws in sol.weekly_solutions
        ],
        "unassigned_tasks": [
            {"id": t.id, "total_duration": t.total_duration}
            for t in sol.unassigned_tasks
        ],
        "capacity_report": {"status": sol.capacity_report.status} if sol.capacity_report else None,
        "conflict_reports": [
            {
                "week_index": cr.week_index,
                "conflicts": cr.conflicts,
                "suggestion": cr.suggestion,
            }
            for cr in sol.conflict_reports
        ],
    }


def _week_solution_to_dict(ws: WeekSolution, epoch: TimeEpoch) -> dict:
    base: dict = {
        "week_index": ws.week_index,
        "start_iso": ws.start_iso,
    }
    if ws.solution is None:
        base["solution"] = None
    else:
        tasks: dict[str, dict] = {}
        for tid, tr in ws.solution.tasks.items():
            start_dt = epoch.real_slot_to_datetime(tr.start_slot)
            end_dt = start_dt + timedelta(minutes=tr.duration_slots * MINUTES_PER_SLOT)
            tasks[tid] = {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "duration_minutes": tr.duration_slots * MINUTES_PER_SLOT,
            }
        base["solution"] = {
            "status": ws.solution.status,
            "solve_time_ms": ws.solution.solve_time_ms,
            "objective_value": ws.solution.objective_value,
            "tasks": tasks,
            "conflicts": ws.solution.conflicts,
        }
    return base
