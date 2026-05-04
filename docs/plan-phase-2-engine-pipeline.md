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

**`prepare_whatif(state) -> PlanState`**

what-if 前准备（六步）：

```
1. now = datetime.now()
2. horizon_start = max(state.horizon_start, 本周一 00:00)
3. 清理已完成：扫描 task_solutions，solution.end < now → 从 tasks 和 solutions 移除
4. 封锁过去时槽：对本周一到现在的已过时段，自动生成 override remove
   （例如现在周三 14:00 → Mon remove 全天, Tue remove 全天, Wed remove 00:00-14:00）
5. 锁定剩余：剩余 task_solutions 中的任务 → task.l2_metadata.locked_start = solution.start
6. 返回准备好的 state
```

### `app/runner.py`

**`run_engine(state, config) -> tuple[PlanState, dict | None]`**

返回 `(updated_state, diff)`。diff 是 `git diff main..whatif -- state.json` 的解析结果。

流程：
1. 构建 L1 JSON：tasks → L1TaskSpec（id=uuid, total_duration, priority, l2_metadata 原样透传）
2. 构建 constraints JSON：如果有 locked_start → 加 `{"type": "schedule_lock", "params": {}}`
3. 调 `parse_long_horizon(data)` → `L1Engine(spec)` → `partition()` → `allocate(tasks, constraints)` → `schedule(params, constraints)`
4. 如果 INFEASIBLE 且有硬锁 → 回退：`locked_start` → `previous_start`，`schedule_lock` → `schedule_stability(weight=50)`，重跑
5. 解析 `MultiWeekSolution` → `state.task_solutions`，计算 `duration_minutes = duration_slots * 15`
6. 清除临时 lock 字段（`locked_start = None`, `previous_start = None`）
7. `git add state.json && git commit -m "what-if: {摘要}"`

## 依赖

- 轮 1：`app.models`, `app.state`, `app.config`
- 引擎库：`projarvis.planner.l1`（`L1Engine`, `parse_long_horizon`, `L1TaskSpec`, `ConstraintSpec` 等）
- 本轮无新增外部依赖（所需库已在轮 1 加入 `pyproject.toml`）

## 重要细节

- duration_minutes → total_duration：向上取整到 15 分钟。`ceil(minutes / 15)`
- L1 engine 的 `ConstraintSpec`（`projarvis.planner.l1.models`）和 app 层的 `ConstraintSpec`（`app.models`）是同名不同类。runner 需要做转换
- schedule_lock/stability 参数格式参考 `projarvis/planner/l1/plugins/schedule_lock.py` 和 `schedule_stability.py`
- 引擎快照直接 git commit。不抛异常，INFEASIBLE 时 `task_solutions` 为空，`last_status = "INFEASIBLE"`

## 不做什么

- 不实现 caldav 同步
- 不实现 HTTP server
- 不实现 agent loop
- 不写测试文件（手动验证）

## 验证

```python
from app.config import AppConfig
from app.state import load, save
from app.models import DeltaRequest, AddTask, ModifyTask
from app.merger import apply_delta, prepare_whatif
from app.runner import run_engine

config = AppConfig()
state = load(config)

delta = DeltaRequest(add=[
    AddTask(title="复习第三章", duration_minutes=180, priority=2)
])
state = apply_delta(state, delta)
state = prepare_whatif(state)
state, diff = run_engine(state, config)

for tid, sol in state.task_solutions.items():
    t = state.tasks[tid]
    print(f"{t.l2_metadata['title']}: {sol.start} → {sol.end}")
print(f"status: {state.last_status}")
```
