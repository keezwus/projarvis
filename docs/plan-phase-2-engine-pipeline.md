# 轮 2：引擎管线 — merger.py + runner.py

## 背景

轮 1 完成了 config/models/state。现在要写 merger（合并 LLM delta + what-if 准备）和 runner（调 L1 引擎）。

## 本轮任务

### `app/merger.py`

**`apply_delta(state, delta: DeltaRequest) -> PlanState`**

合并 LLM 发来的增删改到 state：

1. DELETE: 遍历 `delta.delete`，从 `state.tasks` 和 `state.task_solutions` 移除
2. MODIFY: 遍历 `delta.modify`，更新对应字段（只更新非 None 字段）。清空该 task 的 `locked_start`/`previous_start`。从 `state.task_solutions` 移除（需要重新排程）
3. ADD: 遍历 `delta.add`，生成 UUID v4。`total_duration = ceil(duration_minutes / 15)`。title 写入 `l2_metadata.title`。其余 metadata 字段（deadline/fixed_time/focus_multiplier/exercise_multiplier）直接合并进 `l2_metadata`
4. 返回 **修改后的 state 副本**（不直接改原 state）

**`prepare_whatif(state) -> tuple[PlanState, list[dict]]`**

what-if 前准备，返回 `(prepared_state, auto_overrides)`。auto_overrides 是对过去时槽的临时封锁，**不写进 `state.overrides`**（不持久化），由 `run_engine` 在构建 JSON 时合并：

```
1. now = datetime.now()
2. horizon_start = max(state.horizon_start, 本周一 00:00) — 保证不从过去开始
3. 清理已完成：扫描 task_solutions，solution.end < now → 从 tasks 和 solutions 移除
4. 生成 auto_overrides（不持久化，独立返回）：
   - 格式: {"date": "YYYY-MM-DDT00:00:00", "action": "remove", "blocks": [["HH:MM", "HH:MM"]]}
   - 过去的整天 → blocks: [["00:00", "23:59"]]
   - 今天 → blocks: [["00:00", <当前时间>]]
5. 分层锁定剩余任务（用 solution.start 和新 horizon_start 重新算周号）：
   - 本周（week 0，含正在进行的）→ l2_metadata.locked_start = solution.start（硬锁）
   - 未来周 → l2_metadata.previous_start = solution.start（软锁）
6. 返回 (prepared_state, auto_overrides)
```

### `app/runner.py`

**`run_engine(state, config, auto_overrides=None) -> tuple[PlanState, dict | None]`**

返回 `(updated_state, None)`（diff 预留，Phase 3 做分支操作时实现）。

流程：
1. 构建 L1 JSON：tasks → L1TaskSpec（id=uuid, total_duration, priority, l2_metadata 原样透传）
2. 构建 constraints JSON：有 locked_start → 加 `schedule_lock`；有 previous_start → 加 `schedule_stability`；追加 `state.constraints`。合并后按 `(type, json.dumps(params, sort_keys=True))` 去重
3. 构建 horizon JSON：`state.overrides`（用户手工） + `auto_overrides`（prepare_whatif 返回的临时封锁）
4. 调 `parse_long_horizon(data)` → `L1Engine(spec)` → `partition()` → `allocate(tasks, constraints)` → `schedule(params, constraints)`
5. 如果 INFEASIBLE 且有硬锁 → 回退：`locked_start` → `previous_start`，`schedule_lock` → `schedule_stability`（使用插件默认权重），重跑。回退轮也 INFEASIBLE → 不保存，不清理 lock 字段，`last_status = "INFEASIBLE"`
6. 解析 `MultiWeekSolution` → `state.task_solutions`，计算 `duration_minutes = duration_slots * 15`
7. 清除临时 lock 字段（`locked_start = None`, `previous_start = None`）
8. 调 `cleanup(state)` 清理过期数据
9. `save(config, updated_state)` 持久化

## 依赖

- 轮 1：`app.models`, `app.state`, `app.config`
- 引擎库：`projarvis.planner.l1`（`L1Engine`, `parse_long_horizon`, `L1TaskSpec`, `ConstraintSpec` 等）
- 本轮无新增外部依赖（所需库已在轮 1 加入 `pyproject.toml`）

## 重要细节

- duration_minutes → total_duration：向上取整到 15 分钟。`ceil(minutes / 15)`
- `prepare_whatif` 返回的 `auto_overrides` 不与 `state.overrides` 合并存储，而是由 `run_engine` 在构建 JSON 时合并进 `horizon_spec.overrides`。保证过去时槽封锁不污染持久化状态
- 分层锁定：本周任务用硬锁（`locked_start`），未来周任务用软锁（`previous_start`）。本周用硬锁是因为这些任务已在日历上、用户可见，移动要用户确认
- constraint 去重：自动生成（schedule_lock, schedule_stability）和用户 constraints 合并后，按 `(type, params)` 完全相同去重
- `cleanup(state)` 在 save 之前调用，移除过期 overrides、孤儿 solutions、无效 constraints
- INFEASIBLE 回退只做一轮（硬锁→软锁），不回退到无锁。回退也失败时任务保持原样返回，用户手动调整
- L1 engine 的 `ConstraintSpec`（`projarvis.planner.l1.models`）和 app 层的 `ConstraintSpec`（`app.models`）是同名不同类。runner 需要做转换

## 边界情况

- **空任务列表**: runner 正常返回空 solutions
- **INFEASIBLE 无硬锁**: 不回退，`last_status = "INFEASIBLE"`，`task_solutions` 为空
- **horizon_start 在过去**: `prepare_whatif` 前移到本周一
- **duration_minutes 为 0**: `total_duration = max(1, ceil(0))` = 1
- **MODIFY 不存在的 task id**: 静默跳过
- **正在运行的任务**（`start < now < end`）: 过去时槽被 auto remove 覆盖后，`locked_start` 解析失败，锁默默跳过，任务变为自由浮动

## 不做什么

- 不实现 caldav 同步
- 不实现 HTTP server
- 不实现 agent loop
- 不写测试文件（手动验证）

## 验证

```python
from app.config import AppConfig
from app.state import load
from app.models import DeltaRequest, AddTask
from app.merger import apply_delta, prepare_whatif
from app.runner import run_engine

config = AppConfig()
state = load(config)

delta = DeltaRequest(add=[
    AddTask(title="复习第三章", duration_minutes=180, priority=2)
])
state = apply_delta(state, delta)
state, auto_overrides = prepare_whatif(state)
state, diff = run_engine(state, config, auto_overrides)

for tid, sol in state.task_solutions.items():
    t = state.tasks[tid]
    print(f"{t.l2_metadata['title']}: {sol.start} -> {sol.end}")
print(f"status: {state.last_status}")
```
