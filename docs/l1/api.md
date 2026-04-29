# L1 Multi-Week Orchestration Engine API

## 调用合同

```python
from projarvis.planner.l1.engine import L1Engine
from projarvis.planner.l1.models import LongHorizonSpec, L1TaskSpec
from projarvis.planner.l1.models import ConstraintSpec
from projarvis.planner.models import SolverParams

engine = L1Engine(spec)                                         # 1. 初始化
windows = engine.partition()                                    # 2. 切周
assignments, cap_report = engine.allocate(tasks, constraints)   # 3. 布尔分配
solution = engine.schedule(params, constraints)                  # 4. 逐周委托 L2
```

三阶段各自独立，不自动级联。schedule 必须在 allocate 之后调用。

## 设计核心

**L1 不拆分任务。** 每个任务是一个原子块，整个进入某一周。LLM 负责在 JSON 生成阶段将大任务拆解为可适配单周容量的子任务。

理由：L2 的 NoOverlap 要求每个 TaskSpec 是一个不可分割的 IntervalVar。L1 拆分出来的子块如果仍然跨越多天，L2 会 INFEASIBLE。拆分到底是 LLM 的语义责任——"复习第3章（8h）"比"deep_work_part_0（32 slots）"有意义。

## 公共方法

### `L1Engine.__init__(spec: LongHorizonSpec)`

- 创建 `TimeEpoch(spec.horizon_start)`
- 保存 spec

### `partition() -> list[HorizonWindow]`

- 按 `horizon_weeks` 切为 672-slot（7 天）窗口
- 每窗口过滤 overrides
- 构建临时 TimeMapper 获取 `available_slots`
- 幂等：重复调用返回缓存

### `allocate(tasks: list[L1TaskSpec], constraints: list[ConstraintSpec] | None = None) -> tuple[dict[int, list[L1TaskSpec]], CapacityReport]`

- 调用 partition()（如未调）
- 构建 L1 CP-SAT 布尔分配模型：
  - 变量 `y[t][w]` ∈ {0, 1}
  - 约束 `sum_w y[t][w] == 1`
  - 约束 `sum_t y[t][w] * total_duration[t] <= capacity[w]`
  - 目标 `minimize sum y[t][w] * w * priority[t]`
- INFEASIBLE → 空 dict + OVERSATURATED（不抛异常）
- 返回 `(assignments, report)`

### `schedule(params: SolverParams | None = None, constraints: list[ConstraintSpec] | None = None) -> MultiWeekSolution`

- 遍历窗口，有任务的周委托 L2
- L2 TaskSpec: `id = t.id`, `duration = t.total_duration`, `metadata = t.l2_metadata`（ID 原样传递）
- 空窗口 → WeekSolution(solution=None)
- L2 INFEASIBLE → ConflictReport
- overall_status:
  - `"OK"` — 所有非空周成功（OPTIMAL 或 FEASIBLE）
  - `"PARTIAL"` — 至少一周成功，至少一周 INFEASIBLE
  - `"INFEASIBLE"` — 所有非空周 INFEASIBLE，或 allocate 返回空分配

## Models

### LongHorizonSpec

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `horizon_start` | str | — | ISO 8601，约定为周一 00:00 |
| `horizon_weeks` | int | 4 | 窗口数 |
| `weekly_available` | dict | {} | 每日可用块，同 L2 `weekly_base` |
| `overrides` | list[dict] | [] | 日期级覆盖 |

### L1TaskSpec

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `id` | str | — | 唯一标识，L1→L2 原样传递 |
| `total_duration` | int | — | 任务槽位数（15min 单位） |
| `priority` | int | 999 | 越小越优先 |
| `l2_metadata` | dict | {} | 透传给 L2 TaskSpec.metadata |

### HorizonWindow

| 字段 | 类型 | 说明 |
|------|------|------|
| `week_index` | int | 0-based |
| `start_iso` | str | 窗口起始 ISO |
| `available_slots` | int | 该窗口可用槽位总数 |

### CapacityReport

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | str | OK \| OVERSATURATED |

### ConflictReport

| 字段 | 类型 | 说明 |
|------|------|------|
| `week_index` | int | 冲突周 |
| `conflicts` | list[str] | L2 返回的冲突假设 |
| `suggestion` | str | 可读建议 |

### WeekSolution

| 字段 | 类型 | 说明 |
|------|------|------|
| `week_index` | int | 周序号 |
| `start_iso` | str | 窗口起始 |
| `solution` | L2 Solution \| None | L2 结果，空窗口为 None |

### MultiWeekSolution

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | str | OK \| PARTIAL \| INFEASIBLE |
| `weekly_solutions` | list[WeekSolution] | 逐周结果 |
| `unassigned_tasks` | list[L1TaskSpec] | 未能分配的任务 |
| `capacity_report` | CapacityReport \| None | 容量诊断 |
| `conflict_reports` | list[ConflictReport] | 冲突诊断 |

## JSON 输入格式

```json
{
  "horizon_spec": {
    "horizon_start": "2026-05-04T00:00:00",
    "horizon_weeks": 2,
    "weekly_available": {
      "monday":    [["09:00", "12:00"], ["14:00", "18:00"]],
      "tuesday":   [["09:00", "12:00"], ["14:00", "18:00"]],
      "wednesday": [["09:00", "12:00"], ["14:00", "18:00"]],
      "thursday":  [["09:00", "12:00"], ["14:00", "18:00"]],
      "friday":    [["09:00", "12:00"], ["14:00", "17:00"]],
      "saturday":  [],
      "sunday":    []
    },
    "overrides": []
  },
  "tasks": [
    {
      "id": "review_ch3",
      "l1": { "total_duration": 28, "priority": 1 },
      "l2": { "metadata": {} }
    },
    {
      "id": "practice_exam",
      "l1": { "total_duration": 16, "priority": 1 },
      "l2": { "metadata": {} }
    },
    {
      "id": "admin_stuff",
      "l1": { "total_duration": 4, "priority": 3 },
      "l2": { "metadata": {} }
    }
  ],
  "constraints": [],
  "solver": { "max_time_seconds": 30.0, "random_seed": 42 }
}
```

| 路径 | 字段 | 必须 | 说明 |
|------|------|------|------|
| — | `id` | 是 | 唯一标识，L1→L2 原样传递 |
| `l1.total_duration` | int | 是 | 任务槽位数，必须 <= 单周 capacity |
| `l1.priority` | int | 否 | 越小越优先，默认 999 |
| `l2.metadata` | dict | 否 | 透传给 L2 |

## JSON 输出格式

```json
{
  "status": "OK",
  "weekly_solutions": [
    {
      "week_index": 0,
      "start_iso": "2026-05-04T00:00:00",
      "solution": {
        "status": "OPTIMAL",
        "solve_time_ms": 12.3,
        "objective_value": 45.0,
        "tasks": {
          "review_ch3":    { "start_slot": 0,   "end_slot": 28,  "duration_slots": 28 },
          "practice_exam": { "start_slot": 28,  "end_slot": 44,  "duration_slots": 16 },
          "admin_stuff":   { "start_slot": 44,  "end_slot": 48,  "duration_slots": 4  }
        },
        "conflicts": []
      }
    }
  ],
  "unassigned_tasks": [],
  "capacity_report": { "status": "OK" },
  "conflict_reports": []
}
```

task id 与输入一致，不加前缀。

## 错误处理

| 异常 | 触发条件 |
|------|---------|
| `RuntimeError` | schedule() 在 allocate() 之前调用 |
| `TimeMappingError` | horizon_start 未对齐 15min 槽位 |

allocate INFEASIBLE 和 L2 INFEASIBLE 均不抛异常——通过 CapacityReport 和 ConflictReport 承载。
