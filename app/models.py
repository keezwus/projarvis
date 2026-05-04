from __future__ import annotations

from pydantic import BaseModel, Field


class TaskInfo(BaseModel):
    id: str
    total_duration: int
    priority: int = 100
    l2_metadata: dict = Field(default_factory=dict)


class TaskSolution(BaseModel):
    task_id: str
    start: str
    end: str
    duration_minutes: int
    week_index: int


class ConstraintSpec(BaseModel):
    type: str
    params: dict = Field(default_factory=dict)


class AddTask(BaseModel):
    title: str
    duration_minutes: int
    priority: int = 100
    metadata: dict = Field(default_factory=dict)


class ModifyTask(BaseModel):
    id: str
    title: str | None = None
    duration_minutes: int | None = None
    priority: int | None = None
    metadata: dict | None = None


class DeltaRequest(BaseModel):
    add: list[AddTask] = Field(default_factory=list)
    modify: list[ModifyTask] = Field(default_factory=list)
    delete: list[str] = Field(default_factory=list)


class PlanState(BaseModel):
    horizon_start: str
    horizon_weeks: int = 4
    weekly_available: dict[str, list[list[str]]] = Field(default_factory=dict)
    overrides: list[dict] = Field(default_factory=list)
    tasks: dict[str, TaskInfo] = Field(default_factory=dict)
    task_solutions: dict[str, TaskSolution] = Field(default_factory=dict)
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    last_status: str = "UNSCHEDULED"
    revision: int = 0
    random_seed: int = 42
