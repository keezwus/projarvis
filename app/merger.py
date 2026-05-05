from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil
from uuid import uuid4

from .models import PlanState, DeltaRequest, TaskInfo
from .state import this_monday
from projarvis.planner.models import META_LOCKED_START, META_PREVIOUS_START


def apply_delta(state: PlanState, delta: DeltaRequest) -> PlanState:
    new_state = state.model_copy(deep=True)

    for task_id in delta.delete:
        new_state.tasks.pop(task_id, None)
        new_state.task_solutions.pop(task_id, None)

    for mod in delta.modify:
        if mod.id not in new_state.tasks:
            continue
        task = new_state.tasks[mod.id]
        if mod.title is not None:
            task.l2_metadata["title"] = mod.title
        if mod.duration_minutes is not None:
            task.total_duration = max(1, ceil(mod.duration_minutes / 15))
        if mod.priority is not None:
            task.priority = mod.priority
        if mod.metadata is not None:
            task.l2_metadata.update(mod.metadata)
        task.l2_metadata.pop(META_LOCKED_START, None)
        task.l2_metadata.pop(META_PREVIOUS_START, None)
        new_state.task_solutions.pop(mod.id, None)

    for add in delta.add:
        task_id = str(uuid4())
        total_duration = max(1, ceil(add.duration_minutes / 15))
        l2_metadata: dict = {"title": add.title}
        l2_metadata.update(add.metadata)
        new_state.tasks[task_id] = TaskInfo(
            id=task_id,
            total_duration=total_duration,
            priority=add.priority,
            l2_metadata=l2_metadata,
        )

    return new_state


def prepare_whatif(state: PlanState) -> tuple[PlanState, list[dict]]:
    new_state = state.model_copy(deep=True)
    monday = this_monday()

    horizon_start_dt = datetime.fromisoformat(new_state.horizon_start)
    if horizon_start_dt < monday:
        new_state.horizon_start = monday.isoformat()
        horizon_start_dt = monday

    completed_ids = []
    for tid, sol in new_state.task_solutions.items():
        if datetime.fromisoformat(sol.end) < now:
            completed_ids.append(tid)
    for tid in completed_ids:
        new_state.tasks.pop(tid, None)
        new_state.task_solutions.pop(tid, None)

    auto_overrides: list[dict] = []
    for day_offset in range(now.weekday() + 1):
        day_date = this_monday + timedelta(days=day_offset)
        date_str = day_date.strftime("%Y-%m-%dT00:00:00")
        if day_offset < now.weekday():
            blocks = [["00:00", "23:59"]]
        else:
            blocks = [["00:00", now.strftime("%H:%M")]]
        auto_overrides.append({
            "date": date_str,
            "action": "remove",
            "blocks": blocks,
        })

    for tid, sol in new_state.task_solutions.items():
        if tid not in new_state.tasks:
            continue
        start_dt = datetime.fromisoformat(sol.start)
        week_num = (start_dt - horizon_start_dt).days // 7
        if week_num == 0:
            new_state.tasks[tid].l2_metadata[META_LOCKED_START] = sol.start
        else:
            new_state.tasks[tid].l2_metadata[META_PREVIOUS_START] = sol.start

    return new_state, auto_overrides
