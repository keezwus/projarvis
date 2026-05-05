from __future__ import annotations

import json
from datetime import timedelta

from .cleanup import cleanup
from .config import AppConfig
from .models import PlanState, TaskSolution
from .state import save

from projarvis.planner.l1.engine import L1Engine
from projarvis.planner.l1.serialization import parse_long_horizon
from projarvis.planner.time_epoch import TimeEpoch, MINUTES_PER_SLOT
from projarvis.planner.l1.models import MultiWeekSolution


def _build_tasks_json(tasks: dict) -> list[dict]:
    tasks_json: list[dict] = []
    for tid, task in tasks.items():
        tasks_json.append({
            "id": tid,
            "l1": {
                "total_duration": task.total_duration,
                "priority": task.priority,
            },
            "l2": {"metadata": task.l2_metadata},
        })
    return tasks_json


def _build_constraints_json(tasks: dict, constraints: list) -> list[dict]:
    has_locked = any("locked_start" in t.l2_metadata for t in tasks.values())
    has_previous = any("previous_start" in t.l2_metadata for t in tasks.values())
    constraints_json: list[dict] = []
    if has_locked:
        constraints_json.append({"type": "schedule_lock", "params": {}})
    if has_previous:
        constraints_json.append({"type": "schedule_stability", "params": {}})
    for cs in constraints:
        constraints_json.append({"type": cs.type, "params": cs.params})

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for c in constraints_json:
        key = (c["type"], json.dumps(c["params"], sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _run_single_pass(
    data: dict,
) -> MultiWeekSolution:
    spec, l1_tasks, l1_constraints, solver_params = parse_long_horizon(data)
    engine = L1Engine(spec)
    engine.partition()
    engine.allocate(l1_tasks, l1_constraints)
    return engine.schedule(solver_params, l1_constraints)


def run_engine(
    state: PlanState,
    config: AppConfig,
    auto_overrides: list[dict] | None = None,
) -> tuple[PlanState, dict | None]:
    new_state = state.model_copy(deep=True)
    merged_overrides = list(new_state.overrides) + (auto_overrides or [])

    data = {
        "horizon_spec": {
            "horizon_start": new_state.horizon_start,
            "horizon_weeks": new_state.horizon_weeks,
            "weekly_available": new_state.weekly_available,
            "overrides": merged_overrides,
        },
        "tasks": _build_tasks_json(new_state.tasks),
        "constraints": _build_constraints_json(
            new_state.tasks, new_state.constraints
        ),
        "solver": {
            "max_time_seconds": config.engine.max_time_seconds,
            "random_seed": new_state.random_seed,
        },
    }

    solution = _run_single_pass(data)

    first_pass_had_locks = any(
        "locked_start" in t.l2_metadata for t in new_state.tasks.values()
    )

    if solution.status == "INFEASIBLE" and first_pass_had_locks:
        for task in new_state.tasks.values():
            ls = task.l2_metadata.pop("locked_start", None)
            if ls is not None:
                task.l2_metadata["previous_start"] = ls

        data["tasks"] = _build_tasks_json(new_state.tasks)
        data["constraints"] = _build_constraints_json(
            new_state.tasks, new_state.constraints
        )
        solution = _run_single_pass(data)

        if solution.status == "INFEASIBLE":
            new_state.last_status = "INFEASIBLE"
            return new_state, None

    if solution.status == "INFEASIBLE":
        new_state.last_status = "INFEASIBLE"
        return new_state, None

    epoch = TimeEpoch(new_state.horizon_start)
    new_state.task_solutions = {}
    for ws in solution.weekly_solutions:
        if ws.solution is None:
            continue
        for tid, tr in ws.solution.tasks.items():
            start_dt = epoch.real_slot_to_datetime(tr.start_slot)
            end_dt = start_dt + timedelta(minutes=tr.duration_slots * MINUTES_PER_SLOT)
            new_state.task_solutions[tid] = TaskSolution(
                task_id=tid,
                start=start_dt.isoformat(),
                end=end_dt.isoformat(),
                duration_minutes=tr.duration_slots * MINUTES_PER_SLOT,
                week_index=ws.week_index,
            )

    for task in new_state.tasks.values():
        task.l2_metadata.pop("locked_start", None)
        task.l2_metadata.pop("previous_start", None)

    new_state.last_status = solution.status
    clean_state = cleanup(new_state)
    save(config, clean_state)
    return clean_state, None
