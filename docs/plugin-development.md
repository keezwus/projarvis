# Plugin Development Guide

## 一、代码结构与功能

### TimeEpoch
全局时间基础设施（`projarvis/planner/time_epoch.py`），以 `horizon_start` 为纪元锚点，在 real slot 这条线性轴上做所有转换。

- 常量：`MINUTES_PER_SLOT=15`, `SLOTS_PER_DAY=96`, `SLOTS_PER_WEEK=672`, `DAY_NAMES`
- 纯函数：`hhmm_to_minutes()`, `minutes_to_hhmm()`, `hhmm_to_slot()`, `slot_to_hhmm()`
- 工具：`is_iso_datetime()` — 稳健的 ISO 8601 字符串识别
- `TimeEpoch(horizon_start)` — real slot ↔ datetime 核心转换、槽位算术、周边界

### TimeMapper
时间压缩映射层，接收共享 `TimeEpoch`，将真实可用时间块压缩为连续整数域供 CP-SAT 使用。

- `TimeSpec` + `TimeEpoch` → `TimeMapper(time_spec, epoch)` → `[0, N-1]` 压缩域
- 提供双向映射、`resolve_time_ref`（ISO 8601 → 压缩槽位）、时间查询方法（`day_of_week`, `day_name`, `time_of_day`, `hour`, `minute`, `is_morning`, `is_afternoon`, `is_evening`）

### SchedulingEngine
核心引擎，负责变量创建、约束分发、求解、结果提取。

- `engine.hydrate(tasks)` — 创建 CP-SAT 变量 + 块边界约束 + 全局 NoOverlap
- `engine.apply_constraints(constraints)` — 盲扫 ISO 8601 → 插件分发
- `engine.solve()` — 求解 → 压缩解 → `TimeMapper.compressed_to_real()` → `Solution`（纯整数 slot 输出）

### Registry
`@register_constraint("type_name")` 装饰器注册插件，`discover_plugins()` 自动扫描 `projarvis.planner.l2.plugins` 目录。

### Models
所有数据契约：`TaskSpec`, `TimeSpec`, `ConstraintSpec`, `SolverParams`, `Solution`, `TaskResult`。

`TaskResult` 只保留 slot 字段（`start_slot`, `end_slot`, `duration_slots`），ISO 时间由序列化层或调用方按需生成。

### Solver
`SolverParams` dataclass → `CpSolver` 封装，不暴露 OR-Tools 类型。

### 数据流

```
TimeSpec + TimeEpoch → TimeMapper(ts, epoch) → [0, N-1] 压缩域
TaskSpec[] → Engine.hydrate() → CP-SAT 变量 + 块边界约束 + NoOverlap
ConstraintSpec[] → Engine.apply_constraints() → 盲扫 ISO 8601 → 插件分发
Engine.solve() → 压缩解 → TimeMapper.compressed_to_real() → Solution (real slot 整数)
```

## 二、插件契约与参数

### 插件签名

```python
def plugin_fn(
    model: cp_model.CpModel,
    variables: dict,
    args: dict,                        # 时间字段已转为压缩槽位，非时间字段保留原始类型
    time_mapper: TimeMapper | None = None,
) -> None:
```

插件通过 `time_mapper` 查询压缩槽位的时间属性，例如：
- `time_mapper.day_of_week(comp_slot)` → 0=Monday
- `time_mapper.hour(comp_slot)` → 小时数
- `time_mapper.is_morning(comp_slot)` → 是否上午
- `time_mapper.compressed_to_real(comp_slot)` → 真实槽位

### 四条铁则

1. **OnlyEnforceIf** — 可选约束必须用 `BoolVar + OnlyEnforceIf` 封装
2. **命名空间隔离** — 插件写入 `variables["plugins"][type_name]`，不可写其他 key
3. **黑盒注册** — 只通过 `@register_constraint` 暴露，不可直接 import 插件模块
4. **不碰求解器** — 插件不直接操作 CpSolver 对象。追加优化项通过 Engine 的 `add_objective_term(expr)` 方法

### 任务筛选

插件自己遍历 `variables["tasks"]`，可用：
- `task["spec"].id` — 显式指定任务
- `task["spec"].tags` — 标签匹配
- 两者都不传 — 全量匹配

### 时间字段

约束参数中所有时间用 ISO 8601 datetime 字符串（`"2026-05-04T09:00:00"`），Engine 在调用插件前自动转换为压缩槽位。插件无需处理时间解析。

### 插件变量命名空间

```python
variables = {
    "tasks": {
        "task_id": {
            "start": IntVar,       # 压缩开始槽位
            "end": IntVar,         # 压缩结束槽位
            "duration": int,       # 固定时长
            "interval": IntervalVar,
            "spec": TaskSpec,      # 含 id, duration, tags, metadata
        }
    },
    "plugins": {
        "my_plugin": { ... }      # 只写这里
    }
}
```

### 追加优化项

```python
def my_plugin(model, variables, args, time_mapper):
    # ...
    engine.add_objective_term(weight * sum_of_preferences)
```

注意：`engine.add_objective_term()` 只能在 `hydrate()` 之后、`set_objective()` 之前调用。Engine 在 `set_objective()` 中汇总 `Minimize(sum(starts) + sum(_objective_terms))`。

## 三、JSON 字段说明

### TimeSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `horizon_start` | str | ISO 8601 datetime，时间锚点 |
| `horizon_days` | int | 时间窗口天数，默认 7 |
| `weekly_base` | dict | 每周基准可用块，key=星期全名（monday~sunday），value=`[["HH:MM","HH:MM"],...]` |
| `overrides` | list | 临时变更，每项 `{"date": "ISO 8601 datetime", "action": "add"\|"remove", "blocks": [["HH:MM","HH:MM"],...]}` |

注：`slot_minutes` 在 `time_epoch.py`（`MINUTES_PER_SLOT = 15`）中统一管理，不在 JSON 接口中出现。`weekly_base` 块不允许重叠或乱序（开始 >= 结束），TimeMapper 构建时报 `ValidationError`。

### TaskSpec

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `id` | str | 是 | 唯一标识，重复报错 |
| `duration` | int | 是 | 固定槽位数，>= 1 |
| `tags` | list[str] | 否 | 标签，供插件筛选 |
| `metadata` | dict | 否 | 透传，引擎不读 |

### ConstraintSpec

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | str | 插件名，对应 `@register_constraint` 注册名 |
| `params` | dict | 插件自定义参数，时间用 ISO 8601 |

### SolverParams

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_time_seconds` | float | 30.0 | 求解时间上限 |
| `num_workers` | int | 0 | 并行线程数，0=全核 |
| `random_seed` | int\|None | None | 随机种子 |
| `verbose` | bool | False | 求解日志 |
