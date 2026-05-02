# L1 分发器插件 — 开发指南

L1 分发器插件在 `allocate()` 阶段被调用。插件控制**任务分配到哪一周**——通过往 CP-SAT 模型里加硬约束或目标项来影响周的分配决策。

## 插件签名

```python
def plugin_fn(
    model: cp_model.CpModel,
    variables: dict,
    params: dict,
    windows: list[HorizonWindow],
    time_mappers: list[TimeMapper],
    epoch: TimeEpoch,
) -> None:
```

| 参数 | 说明 |
|------|------|
| `model` | CP-SAT 模型，插件往里加 `model.Add(...)` 硬约束 |
| `variables` | `{"tasks": {...}, "plugins": {}}`，见下方结构 |
| `params` | 用户 JSON 中 `ConstraintSpec.params`，原样传入 |
| `windows` | `list[HorizonWindow]`，每周的 `week_index`、`start_iso`、`available_slots` |
| `time_mappers` | `list[TimeMapper]`，与 windows 同序。可调 `total_slots`、`day_name(comp)`、`resolve_or_nearest(iso)` |
| `epoch` | `TimeEpoch`，horizon 级别时间工具。`iso_to_real_slot()`、`week_index()`、`week_start_iso()` |

## 注册

```python
from projarvis.planner.l1.registry import register_distributor

@register_distributor("my_distributor")
def my_distributor(model, variables, params, windows, time_mappers, epoch):
    ...
```

插件放在 `l1/plugins/` 目录。Engine 在 `allocate()` 中调 `discover_distributors()` 扫描 `projarvis.planner.l1.plugins` 包，自动 import 所有模块。

## variables 结构

```python
variables = {
    "tasks": {
        "task_id": {
            "vars": [BoolVar, ...],   # y[tid][w]，每个 BoolVar = 该 task 是否分配到第 w 周
            "duration": int,           # total_duration
            "spec": L1TaskSpec,        # 含 id、priority、l2_metadata
        }
    },
    "plugins": {}                      # 插件写入目标项
}
```

`vars[w] == 1` 表示该 task 分配到第 w 周。one-hot 约束（`sum(vars) == 1`）由 engine 保证，插件无需处理。

## 插件能做两件事

### A. 硬约束（`model.Add(...)`）

直接写 CP-SAT 约束。所有插件共享同一个 `model`。示例：

```python
# 禁止 task_a 分配到 week 0 之后
for w in range(1, n_weeks):
    model.Add(variables["tasks"]["task_a"]["vars"][w] == 0)
```

### B. 目标项（写入 `variables["plugins"]`）

两种写入方式：

```python
# 方式 1：全局追加项（加到总目标末尾）
variables["plugins"]["my_plugin"] = [term1, term2]

# 方式 2：task_terms — 替换指定 task 的默认 base
# engine 对覆盖的 task 跳过默认 y[t][w] * w * priority，改用插件提供的项
variables["plugins"]["my_plugin"] = {
    "task_terms": {
        "task_a": [term_for_w0, term_for_w1, ...],
        "task_b": [term_for_w0, term_for_w1, ...],
    },
    "objective_terms": [global_term1, global_term2],  # 可选全局项
}
```

**规则**：
- 插件绝不调 `model.Minimize()`
- `task_terms` 和 `objective_terms` 可同时提供
- 如果一个 task 被多个插件的 `task_terms` 覆盖，后调用的覆盖先调用的
- 未被任何 `task_terms` 覆盖的 task，engine 用默认 `y[t][w] * w * priority`（earliest_bias）

## 目标函数构建

```
总目标 = 
  sum(被 task_terms 覆盖的 task 的插件项)
+ sum(未被覆盖的 task 的 y[t][w] * w * priority)  ← 默认 earliest_bias
+ sum(所有 objective_terms)
```

## 与 L2 插件的区别

| 维度 | L2 插件 | L1 插件 |
|------|---------|---------|
| 注册装饰器 | `@register_constraint` | `@register_distributor` |
| 签名 | `(model, variables, params, time_mapper)` | `(model, variables, params, windows, time_mappers, epoch)` |
| 时间粒度 | 单周（一个 TimeMapper） | 多周（list[TimeMapper] + epoch） |
| 变量 | `start/end/interval` 连续 IntVar | `y[t][w]` BoolVar 周分配 |
| 目标控制 | 只追加 `objective_terms` | 可追加 `objective_terms`，也可通过 `task_terms` **替换**默认 base |
| 发现路径 | `l2.plugins` | `l1.plugins` |
