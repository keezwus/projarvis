# L2 SchedulingEngine API

## 调用合同

```python
from projarvis.planner.time_epoch import TimeEpoch
from projarvis.planner.l2.time_mapper import TimeMapper
from projarvis.planner.l2.engine import SchedulingEngine
from projarvis.planner.l2.models import TimeSpec, TaskSpec, ConstraintSpec
from projarvis.planner.models import SolverParams

epoch = TimeEpoch(horizon_start)
time_spec = TimeSpec(horizon_start, horizon_days, weekly_base, overrides)
tm = TimeMapper(time_spec, epoch)

engine = SchedulingEngine(tm)
engine.hydrate(tasks)                          # 1. 创建 CP-SAT 变量
engine.apply_constraints(constraints)          # 2. 应用约束插件（可选）
engine.set_objective()                         # 3. 设定优化目标
solution = engine.solve(params)                # 4. 求解
```

每一步只能调用一次。重复调用抛 `RuntimeError`。

## 公共方法

### `SchedulingEngine.__init__(time_mapper: TimeMapper)`

接收压缩域映射器。不创建模型变量。

### `hydrate(tasks: list[TaskSpec]) -> None`

- 为每个 task 创建 `start`, `end` IntVar 和 `interval` IntervalVar
- 添加块边界约束（防止任务跨越不可用时段）
- 添加全局 `NoOverlap` 约束
- 检测重复 ID：`ValidationError`

约束条件：
- `tasks` 非空
- 每个 task 的 `duration >= 1`
- `time_mapper.total_slots > 0`

### `apply_constraints(constraints: list[ConstraintSpec]) -> None`

- 自动发现并加载 `l2.plugins` 下的所有插件
- 遍历 `constraints`，按 `type` 查找插件函数
- 对每个约束的 `params` 做盲扫：ISO 8601 字符串 → 压缩槽位
- 调用插件 `fn(model, variables, converted_params, time_mapper)`

未知约束类型 → `ConstraintError`。

### `set_objective() -> None`

目标函数：`Minimize(sum(task_starts) + sum(plugin_objective_terms))`

插件可通过 `engine.add_objective_term(expr)` 追加优化项。

### `solve(params: SolverParams | None) -> Solution`

- 构建 CpSolver，求解
- 提取结果：压缩槽位 → real slot
- INFEASIBLE → `Solution(status="INFEASIBLE", tasks={}, conflicts=[...])`

不抛异常。INFEASIBLE 是合法返回值。

## Models

### TaskSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 唯一标识 |
| `duration` | int | 固定槽位数，>= 1（15min/槽位） |
| `metadata` | dict | 透传，引擎不消费 |

### TimeSpec

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `horizon_start` | str | — | ISO 8601 datetime |
| `horizon_days` | int | 7 | 窗口天数 |
| `weekly_base` | dict | {} | 每日可用块，key=星期全名 |
| `overrides` | list[dict] | [] | 日期级覆盖 |

### ConstraintSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | str | 插件注册名 |
| `params` | dict | 插件参数，时间字段用 ISO 8601 |

### SolverParams

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_time_seconds` | float | 30.0 | 单次求解时限 |
| `num_workers` | int | 0 | 并行线程数，0=全核 |
| `random_seed` | int\|None | None | 随机种子 |
| `verbose` | bool | False | 求解日志 |

### Solution

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | str | OPTIMAL \| FEASIBLE \| INFEASIBLE |
| `solve_time_ms` | float | 求解耗时 |
| `objective_value` | float\|None | 目标值，INFEASIBLE 时为 None |
| `tasks` | dict[str, TaskResult] | task_id → TaskResult |
| `conflicts` | list[str] | INFEASIBLE 假设集 |

### TaskResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | task id |
| `start_slot` | int | real slot（距 horizon_start 的 15min 槽位偏移） |
| `end_slot` | int | real slot（排他） |
| `duration_slots` | int | 实际占用槽位数 |

## JSON 输入格式

```json
{
  "time_spec": {
    "horizon_start": "2026-05-04T00:00:00",
    "horizon_days": 7,
    "weekly_base": {
      "monday":    [["09:00", "12:00"], ["14:00", "18:00"]],
      "tuesday":   [["09:00", "12:00"], ["14:00", "18:00"]],
      "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
      "thursday":  [["09:00", "12:00"], ["14:00", "18:00"]],
      "friday":    [["09:00", "12:00"], ["14:00", "17:00"]],
      "saturday":  [],
      "sunday":    []
    },
    "overrides": [
      {"date": "2026-05-05T00:00:00", "action": "remove", "blocks": [["14:00", "18:00"]]}
    ]
  },
  "tasks": [
    {"id": "deep_work", "duration": 8, "metadata": {}}
  ],
  "constraints": [
    {"type": "no_meetings_tuesday", "params": {}}
  ],
  "solver": {
    "max_time_seconds": 30.0,
    "random_seed": 42
  }
}
```

## JSON 输出格式

```json
{
  "status": "OPTIMAL",
  "solve_time_ms": 12.3,
  "objective_value": 45.0,
  "tasks": {
    "deep_work": {
      "start_slot": 0,
      "end_slot": 8,
      "duration_slots": 8
    }
  },
  "conflicts": []
}
```

## 错误处理

| 异常 | 触发条件 |
|------|---------|
| `RuntimeError` | 方法调用顺序错误或重复调用 |
| `ValidationError` | tasks 为空、重复 ID、duration < 1、无可用槽位 |
| `ConstraintError` | 未知约束类型 |
| `TimeMappingError` | ISO 8601 不在可用时间范围内或未对齐 |

求解 INFEASIBLE **不抛异常**——返回 `Solution(status="INFEASIBLE")`。
