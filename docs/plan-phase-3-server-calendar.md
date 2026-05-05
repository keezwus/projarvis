# 轮 3：服务 + 日历 — caldav.py + server.py

## 背景

轮 1 定义了数据模型和状态管理。轮 2 实现了 merger 和 runner（delta 合并 + 引擎编排）。现在要把这些串成 HTTP 服务，并加上日历同步——用户调 API 后，手机日历自动更新。

## 本轮任务

- `app/caldav.py` — iCalendar 生成 + CalDAV 同步
- `app/server.py` — FastAPI 8 端点
- `app/cleanup.py` — state 垃圾清理
- `app/state.py` — 新增 4 个分支操作函数
- `app/models.py` — 新增端点请求模型（如需要）

### `app/models.py` — 新增请求模型

追加 4 个 Pydantic 模型（在 `DeltaRequest` 之后、`PlanState` 之前）：

```python
class AddTasksRequest(BaseModel):
    tasks: list[AddTask]

class ModifyTaskRequest(BaseModel):
    title: str | None = None
    duration_minutes: int | None = None
    priority: int | None = None
    metadata: dict | None = None
    # id 来自 URL 路径，不在 body 中

class BlockTimeRequest(BaseModel):
    date: str       # "2026-05-05"
    start: str      # "14:00"
    end: str        # "18:00"

class SetConstraintsRequest(BaseModel):
    constraints: list[ConstraintSpec]
    mode: str = "replace"  # "replace" or "append"
```

### `app/caldav.py`

**`solution_to_ical(state) -> str`**

将 PlanState 的 task_solutions 转为 iCalendar 格式（`icalendar` 库）：

- UID = `projarvis-{uuid}`
- SUMMARY = `task.l2_metadata.title`
- DTSTART / DTEND = solution.start / solution.end（ISO 8601）
- DESCRIPTION = 可选：duration、task id
- 每个 task 一个 VEVENT
- VCALENDAR PRODID = `-//projarvis//schedule//EN`

**`sync_to_caldav(state, config) -> None`**

推送日历到 Baikal。**只替换当天及未来的事件，保留当天之前的历史事件：**

1. 连接 CalDAV 服务器（`caldav.DAVClient`）
2. 拿到 calendar
3. 删除所有带 `X-PROJARVIS-TASK-ID` 且 `DTSTART >= today` 的旧事件
4. 创建新事件（`calendar.save_event`），只推送 `solution.start >= today` 的任务
5. `solution.start < today` 的历史事件已在日历上，不动

错误处理：连接失败则打印 warning 但不抛异常。后续重试。

### `app/cleanup.py`

**`cleanup(state, now: datetime | None = None) -> PlanState`**

定期清理 state 中过期的垃圾数据，返回 `state.model_copy(deep=True)`：

1. **过期的用户 overrides**: `datetime.fromisoformat(ov["date"]) < horizon_start` → 移除
2. **孤儿 task_solutions**: `task_id` 不在 `state.tasks` 中 → 移除
3. **无效 constraints**: dependency/deadline/fixed_time 等引用不存在的 task_id → 移除

调用时机：`run_engine` 在 `save` 之前调用（INFEASIBLE 分支不调）。`commit` 端点也会在 merge 后调一次（幂等）。

### `app/server.py` — FastAPI

8 个端点：

```
GET  /api/v1/plan
  实现: checkout_main → load → state.model_dump()
  返回 main 分支 state.json 完整内容（供 LLM 上下文用）

POST /api/v1/tasks/add
  body: AddTasksRequest — {"tasks": [{"title": "...", "duration_minutes": 180, "priority": 2}]}
  实现: checkout_whatif → load → apply_delta(DeltaRequest(add=body.tasks)) → save
  400 if tasks 为空

POST /api/v1/tasks/{task_id}/modify
  body: ModifyTaskRequest — {"title": "...", "duration_minutes": 120}
  实现: checkout_whatif → load → 404 if task_id 不存在 → apply_delta(DeltaRequest(modify=[...])) → save

DELETE /api/v1/tasks/{task_id}
  实现: checkout_whatif → load → 404 if task_id 不存在 → apply_delta(DeltaRequest(delete=[task_id])) → save

POST /api/v1/block-time
  body: BlockTimeRequest — {"date": "2026-05-03", "start": "14:00", "end": "18:00"}
  实现: checkout_whatif → load → 追加 override: {"date": f"{body.date}T00:00:00", "action": "remove", "blocks": [[body.start, body.end]]} → save

POST /api/v1/constraints
  body: SetConstraintsRequest — {"constraints": [...], "mode": "replace"}
  实现: checkout_whatif → load
        mode "replace" → state.constraints = list(body.constraints)
        mode "append" → 踢掉同 (type, params) 的旧项，state.constraints.extend(body.constraints)
        → save

POST /api/v1/what-if
  实现: checkout_whatif → load
        → prepare_whatif(state) → (prepared, auto_overrides)
        → run_engine(prepared, config, auto_overrides) → (result_state, _)
          (run_engine 内部已做 cleanup + save)
        → diff = diff_main_whatif(config)
        → INFEASIBLE → {diff: "", status: "INFEASIBLE", unassigned_tasks: [...]}
        → OK → {diff, status, unassigned_tasks}

POST /api/v1/commit
  实现: 400 if whatif 不存在
        → merge_whatif(config) → git checkout main && git merge whatif && git branch -D whatif
        → load → cleanup（幂等） → save
        → sync_to_caldav(clean_state, config)（best-effort, warn on failure）
        → {status: "ok", revision: N}
```

分支操作（`state.py` 需新增）：
- `_ensure_main(config)` — 向后兼容：如果已有 `master` 分支，`git branch -m master main`
- `init_git_repo` 更新 — `git init` 后设 `init.defaultBranch = main`
- `checkout_whatif(config)` — 累积模式：whatif 存在就 `git checkout whatif`，不存在才 `git checkout -B whatif main`
- `checkout_main(config)` — `git checkout main`
- `merge_whatif(config)` — `git checkout main && git merge whatif && git branch -D whatif`。merge 失败 → `git merge --abort`
- `diff_main_whatif(config)` — `git diff main..whatif -- state.json`

工具 2-6 只改 whatif 分支上的 state.json。`what_if` 才实际调引擎。`commit` merge 回 main 并推日历。

端点参数模型定义在 `app/models.py`（轮 1 已有）。

## 依赖

- 轮 1：`app.models`, `app.state`, `app.config`
- 轮 2：`app.merger`, `app.runner`
- 需添加到 `pyproject.toml` 的 `[project.dependencies]`：`fastapi`, `uvicorn`, `icalendar`, `caldav`

## 重要细节

- 所有端点同步 (`def`) — FastAPI 自动跑在 thread pool。GIL + 文件锁保证互斥
- 分支操作在 `state.py` 中实现，用 `subprocess.run(["git", ...], cwd=config.state_dir)`
- server 启动时（lifespan）：`init_git_repo`（设 `init.defaultBranch = main`）→ `_ensure_main`（master→main 迁移）→ 无 commit 则 bootstrap 初始 state → `checkout_main`
- 工具 2-6（add/modify/delete/block_time/constraints）只改 whatif 分支上的 state.json，不动 main。`what_if` 才调引擎。`commit` merge 回 main 并推日历
- whatif 累积模式：`checkout_whatif` 存在则 plain checkout，不存在才 -B 创建。意味着多次操作累积在一个 whatif 分支上
- `merge_whatif` 成功后 `git branch -D whatif` 清理临时分支
- constraint 追加模式 `"append"` 踢掉同 `(type, params)` 的旧项再扩展，不是简单 append
- block_time 的 override date 拼 `T00:00:00`，action 固定 `"remove"`，对齐引擎格式
- CalDAV sync 用 `calendar.date_search(start=today)` 只查当天+未来事件，历史事件不动
- CalDAV 失败 → `warnings.warn`，不抛异常，不影响 HTTP 响应
- 无鉴权（开发和内网部署）。生产环境 nginx 前面挡 TLS + basic auth
- 端口 8000

## `app/runner.py` 改动

Phase 3 对 runner 做两处小改动（已实现）：

1. **cleanup before save**: `run_engine` 在调 `save` 之前先调 `cleanup(new_state)`，移除过期 overrides、孤儿 solutions、无效 constraints
2. **constraint dedup**: `_build_constraints_json` 合并自动生成（schedule_lock, schedule_stability）和用户 `state.constraints` 后，按 `(type, json.dumps(params, sort_keys=True))` 去重

## 不做什么

- 不实现 agent loop
- 不实现 Docker 部署
- 不实现 `POST /api/v1/schedule/reset` 端点（plan 中删除了）

## 验证

```bash
# 启动服务
uvicorn app.server:app --port 8000 &

# Golden path
curl -s http://localhost:8000/api/v1/plan | python -m json.tool
curl -s -X POST http://localhost:8000/api/v1/tasks/add \
  -H "Content-Type: application/json" \
  -d '{"tasks": [{"title": "复习第三章", "duration_minutes": 180, "priority": 2}]}'
curl -s -X POST http://localhost:8000/api/v1/block-time \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-05-05", "start": "14:00", "end": "18:00"}'
curl -s -X POST http://localhost:8000/api/v1/what-if
curl -s -X POST http://localhost:8000/api/v1/commit

# Error cases
curl -s -X POST http://localhost:8000/api/v1/tasks/add \
  -H "Content-Type: application/json" \
  -d '{"tasks": []}'                                          # → 400
curl -s -X POST http://localhost:8000/api/v1/tasks/nonexistent/modify \
  -H "Content-Type: application/json" \
  -d '{"title": "test"}'                                      # → 404
curl -s -X DELETE http://localhost:8000/api/v1/tasks/nonexistent  # → 404
curl -s -X POST http://localhost:8000/api/v1/commit           # → 400 (no whatif)
```
