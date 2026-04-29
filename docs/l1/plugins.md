# L1 分发器插件开发

> 本版脚手架已就位，插件体系尚未接入 engine 流程。本文档定义接口契约，供后续实现参考。

## 插件签名

```python
def distributor_fn(
    model: cp_model.CpModel,
    variables: dict,
    params: dict,
    windows: list[HorizonWindow],
    epoch: TimeEpoch,
) -> None:
```

与 L2 插件 `fn(model, variables, params, time_mapper)` 对齐前三个参数。

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | CpModel | L1 CP-SAT 布尔分配模型 |
| `variables` | dict | `{task_id: [y_w0, y_w1, ...]}`，BoolVar 数组 |
| `params` | dict | 约束参数，插件自己用 epoch 转换时间 |
| `windows` | list[HorizonWindow] | 所有周窗口 |
| `epoch` | TimeEpoch | ISO → week_index |

## 注册

```python
from projarvis.planner.l1.registry import register_distributor

@register_distributor("deadline")
def deadline_distributor(model, variables, params, windows, epoch):
    ...
```

`discover_distributors()` 扫描 `projarvis.planner.l1.plugins`。

## `variables` 结构

L1 使用布尔分配模型，每个 task 的变量是一个 `BoolVar` 数组：

```python
variables = {
    "review_ch3":    [BoolVar_w0, BoolVar_w1, BoolVar_w2],
    "practice_exam": [BoolVar_w0, BoolVar_w1, BoolVar_w2],
    "admin_stuff":   [BoolVar_w0, BoolVar_w1, BoolVar_w2],
}
```

L1 variables 是平坦的 `{task_id: list[BoolVar]}`。每个 BoolVar 表示"该 task 是否进入第 w 周"。

引擎自动添加 one-hot 约束（`sum_w y[t][w] == 1`）和容量约束。插件在此基础上追加约束或目标项。

## 常见模式

### 周边界封锁（deadline）

```python
def deadline_distributor(model, variables, params, windows, epoch):
    task_id = params["task_id"]
    y = variables.get(task_id)
    if y is None:
        return
    deadline_week = epoch.week_index(epoch.iso_to_real_slot(params["deadline"]))
    for w in range(deadline_week + 1, len(y)):
        model.Add(y[w] == 0)
```

### 周范围约束（earliest）

```python
def earliest_distributor(model, variables, params, windows, epoch):
    task_id = params["task_id"]
    y = variables.get(task_id)
    if y is None:
        return
    earliest_week = epoch.week_index(epoch.iso_to_real_slot(params["earliest"]))
    for w in range(earliest_week):
        model.Add(y[w] == 0)
```

### 权重目标（ramp_up）

```python
def ramp_up_distributor(model, variables, params, windows, epoch):
    task_id = params["task_id"]
    y = variables.get(task_id)
    if y is None:
        return
    lead_weeks = params.get("lead_weeks", len(windows))
    baseline = params.get("baseline", 0.1)
    peak = params.get("peak", 0.5)
    for w in range(lead_weeks):
        weight = baseline + (peak - baseline) * (w / max(lead_weeks - 1, 1))
        model.Maximize(int(weight * 1000) * y[w])
```

### 多周分布（spread）

```python
def spread_distributor(model, variables, params, windows, epoch):
    # 对多个同系列 task，让它们分散到不同周
    task_ids = params.get("task_ids", [])
    for w in range(len(windows)):
        model.Add(sum(variables[tid][w] for tid in task_ids) <= 1)
```

## 规则

1. **只写 model** — 加约束或目标项，不操作 solver
2. **不抛异常** — 参数缺失/无效时静默返回
3. **时间用 epoch** — 不接受预转换槽位
4. **变量全局视图** — 一次调用拿到所有 task，可处理跨 task 逻辑

## 与 L2 插件的差异

| | L2 约束插件 | L1 分发器插件 |
|---|---|---|
| 签名 | `fn(model, variables, params, time_mapper)` | `fn(model, variables, params, windows, epoch)` |
| 注册 | `@register_constraint` | `@register_distributor` |
| params 处理 | Engine 盲扫 ISO → 压缩槽位 | 插件自己用 epoch 转 |
| variables | `{tasks: {id: {start, end, ...}}, plugins: ...}` | `{task_id: [BoolVar_w0, ...]}` |
| 作用对象 | 任务在单周内的排布 | 任务分配到哪一周 |
| 任务拆分 | N/A | 不拆分——布尔变量，整块进一周 |
