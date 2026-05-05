from __future__ import annotations

import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .caldav import sync_to_caldav
from .cleanup import cleanup
from .config import AppConfig, load_app_config
from .merger import apply_delta, prepare_whatif
from .models import (
    AddTasksRequest,
    BlockTimeRequest,
    DeleteTasksRequest,
    DeltaRequest,
    ModifyTask,
    ModifyTaskRequest,
    PlanState,
    SetConstraintsRequest,
)
from .runner import run_engine
from .state import (
    _git,
    checkout_main,
    checkout_whatif,
    diff_main_whatif,
    init_git_repo,
    load,
    merge_whatif,
    save,
)

_config: AppConfig | None = None


def get_config() -> AppConfig:
    assert _config is not None, "config not initialized"
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config
    _config = load_app_config()

    state_dir = str(Path(_config.state_dir))
    init_git_repo(state_dir)

    result = _git(state_dir, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        state = load(_config)
        save(_config, state)
        result = _git(state_dir, "rev-parse", "--abbrev-ref", "HEAD")
        current = result.stdout.strip()
        if current != "main":
            _git(state_dir, "branch", "-m", current, "main")
    else:
        result = _git(state_dir, "rev-parse", "--abbrev-ref", "HEAD")
        current = result.stdout.strip()
        if current == "master":
            _git(state_dir, "branch", "-m", "master", "main")

    checkout_main(_config)
    yield


app = FastAPI(title="projarvis", version="2.0.0", lifespan=lifespan)


def _unassigned_tasks(state: PlanState) -> list[str]:
    return [tid for tid in state.tasks if tid not in state.task_solutions]


@app.get("/api/v1/plan")
def get_plan():
    config = get_config()
    checkout_main(config)
    state = load(config)
    return state.model_dump()


@app.post("/api/v1/tasks/add")
def add_tasks(body: AddTasksRequest):
    if not body.tasks:
        raise HTTPException(status_code=400, detail="No tasks provided")

    config = get_config()
    checkout_whatif(config)
    state = load(config)
    new_state = apply_delta(state, DeltaRequest(add=body.tasks))
    save(config, new_state)
    return {"status": "ok", "added": len(body.tasks)}


@app.post("/api/v1/tasks/{task_id}/modify")
def modify_task(task_id: str, body: ModifyTaskRequest):
    config = get_config()
    checkout_whatif(config)
    state = load(config)

    if task_id not in state.tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    mod = ModifyTask(id=task_id, **body.model_dump(exclude_none=True))
    new_state = apply_delta(state, DeltaRequest(modify=[mod]))
    save(config, new_state)
    return {"status": "ok"}


@app.delete("/api/v1/tasks")
def delete_tasks(body: DeleteTasksRequest):
    config = get_config()
    checkout_whatif(config)
    state = load(config)

    for tid in body.task_ids:
        if tid not in state.tasks:
            raise HTTPException(status_code=404, detail=f"Task {tid} not found")

    new_state = apply_delta(state, DeltaRequest(delete=list(body.task_ids)))
    save(config, new_state)
    return {"status": "ok", "deleted": len(body.task_ids)}


@app.post("/api/v1/block-time")
def block_time(body: BlockTimeRequest):
    config = get_config()
    checkout_whatif(config)
    state = load(config)

    for b in body.blocks:
        state.overrides.append({
            "date": f"{b.date}T00:00:00",
            "action": "remove",
            "blocks": [[b.start, b.end]],
        })
    save(config, state)
    return {"status": "ok", "blocked": len(body.blocks)}


@app.post("/api/v1/constraints")
def set_constraints(body: SetConstraintsRequest):
    config = get_config()
    checkout_whatif(config)
    state = load(config)

    if body.mode == "append":
        new_types = {c.type for c in body.constraints}
        state.constraints = [c for c in state.constraints if c.type not in new_types]
        state.constraints.extend(body.constraints)
    else:
        state.constraints = list(body.constraints)

    save(config, state)
    return {"status": "ok", "constraints_count": len(state.constraints)}


@app.post("/api/v1/what-if")
def run_what_if():
    config = get_config()
    checkout_whatif(config)
    state = load(config)

    prepared_state, auto_overrides = prepare_whatif(state)
    result_state, _error_info = run_engine(prepared_state, config, auto_overrides)

    if result_state.last_status == "INFEASIBLE":
        return {
            "diff": "",
            "status": "INFEASIBLE",
            "unassigned_tasks": _unassigned_tasks(result_state),
        }

    diff = diff_main_whatif(config)
    return {
        "diff": diff,
        "status": result_state.last_status,
        "unassigned_tasks": _unassigned_tasks(result_state),
    }


@app.post("/api/v1/commit")
def commit():
    config = get_config()
    state_dir = str(Path(config.state_dir))

    result = _git(state_dir, "rev-parse", "--verify", "whatif")
    if result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail="No whatif branch exists. Make changes on whatif first.",
        )

    merge_whatif(config)
    state = load(config)
    clean_state = cleanup(state)
    save(config, clean_state)

    try:
        sync_to_caldav(clean_state, config)
    except Exception as exc:
        warnings.warn(f"CalDAV sync during commit failed: {exc}")

    return {"status": "ok", "revision": clean_state.revision}
