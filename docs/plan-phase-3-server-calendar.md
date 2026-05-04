# 轮 3：服务 + 日历 — caldav.py + server.py

## 背景

轮 1 定义了数据模型和状态管理。轮 2 实现了 merger 和 runner（delta 合并 + 引擎编排）。现在要把这些串成 HTTP 服务，并加上日历同步——用户调 API 后，手机日历自动更新。

## 本轮任务

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

推送日历到 Baikal：

1. 连接 CalDAV 服务器（`caldav.DAVClient`）
2. 拿到 calendar
3. 删除所有带 `X-PROJARVIS-TASK-ID` 的旧事件（delete-and-replace 策略）
4. 创建新事件（`calendar.save_event` 或批量 `save_object`）

错误处理：连接失则打印 warning 但不抛异常。后续重试。

### `app/server.py` — FastAPI

8 个端点：

```
GET  /api/v1/plan
  返回 main 分支 state.json 完整内容（供 LLM 上下文用）
  实现: load(config) → 直接返回 PlanState 的 dict

POST /api/v1/tasks/add
  body: {"tasks": [{"title": "...", "duration_minutes": 180, "priority": 2, "metadata": {}}]}
  实现: 切 whatif 分支 → apply_delta → save state.json

POST /api/v1/tasks/{id}/modify
  body: {"title": "...", "duration_minutes": 120, ...}
  实现: 切 whatif → apply_delta → save

DELETE /api/v1/tasks/{id}
  实现: 切 whatif → apply_delta → save

POST /api/v1/block-time
  body: {"date": "2026-05-03", "start": "14:00", "end": "18:00"}
  实现: 切 whatif → 写入 state.overrides → save

POST /api/v1/constraints
  body: {"constraints": [{"type": "task_break", "params": {"default_gap": 1}}]}
  实现: 切 whatif → 替换 state.constraints → save

POST /api/v1/what-if
  实现: prepare_whatif(state) → run_engine(state, config)
        → git commit → git diff main..whatif -- state.json
        → 返回 {diff: "...", status: "...", unassigned_tasks: [...]}

POST /api/v1/commit
  实现: git checkout main && git merge whatif
        → sync_to_caldav(state, config)
        → 返回 {status: "ok", revision: N}
```

分支操作（`state.py` 需要新增）：
- `checkout_whatif(config)` — `git checkout -B whatif main`（-B 强制覆盖）
- `checkout_main(config)` — `git checkout main`
- `merge_whatif(config)` — `git checkout main && git merge whatif`
- `diff_main_whatif(config)` — `git diff main..whatif -- state.json`

工具 2-6 只改 whatif 分支上的 state.json。`what_if` 才实际调引擎。`commit` merge 回 main 并推日历。

端点参数模型定义在 `app/models.py`（轮 1 已有）。

## 依赖

- 轮 1：`app.models`, `app.state`, `app.config`
- 轮 2：`app.merger`, `app.runner`
- 需添加到 `pyproject.toml` 的 `[project.dependencies]`：`fastapi`, `uvicorn`, `icalendar`, `caldav`

## 重要细节

- 分支操作在 `state.py` 中实现，用 `subprocess.run(["git", ...], cwd=config.state_dir)`
- server 启动时初始化 git repo（`state.init_git_repo(config.state_dir)`）
- 无鉴权（开发和内网部署）。生产环境 nginx 前面挡 TLS + basic auth
- 端口 8000
- `what_if` 和 `commit` 无请求体，无参数——所有变更已暂存在 whatif 分支上

## 不做什么

- 不实现 agent loop
- 不实现 Docker 部署
- 不写测试文件

## 验证

```bash
# 启动服务
uvicorn app.server:app --port 8000

# 加任务
curl -X POST http://localhost:8000/api/v1/tasks/add \
  -H "Content-Type: application/json" \
  -d '{"tasks": [{"title": "复习第三章", "duration_minutes": 180, "priority": 2}]}'

# 跑 what-if
curl -X POST http://localhost:8000/api/v1/what-if

# 看计划
curl http://localhost:8000/api/v1/plan

# 确认提交
curl -X POST http://localhost:8000/api/v1/commit
```
