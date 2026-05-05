from __future__ import annotations

from datetime import datetime

from .models import PlanState


def cleanup(state: PlanState, now: datetime | None = None) -> PlanState:
    new_state = state.model_copy(deep=True)
    horizon_start = datetime.fromisoformat(new_state.horizon_start)
    _now = now or datetime.now()

    new_state.overrides = [
        ov
        for ov in new_state.overrides
        if datetime.fromisoformat(ov["date"]) >= horizon_start
    ]

    new_state.task_solutions = {
        tid: sol
        for tid, sol in new_state.task_solutions.items()
        if tid in new_state.tasks
    }

    valid_ids = set(new_state.tasks.keys())
    new_state.constraints = [
        c for c in new_state.constraints if _constraint_is_valid(c, valid_ids)
    ]

    return new_state


def _constraint_is_valid(constraint, valid_ids: set[str]) -> bool:
    ref_fields = {
        "deadline": ["task_id"],
        "dependency": ["before", "after"],
        "fixed_time": ["task_id"],
    }
    fields = ref_fields.get(constraint.type)
    if fields is None:
        return True
    for field in fields:
        tid = constraint.params.get(field)
        if tid is not None and tid not in valid_ids:
            return False
    return True
