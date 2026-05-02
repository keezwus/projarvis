# L1 分发器插件

L1 插件在 `allocate()` 阶段介入 CP-SAT 布尔分配模型，控制任务分配到哪一周。

## 插件签名

```python
def distributor_fn(
    model: cp_model.CpModel,
    variables: dict,
    params: dict,
    windows: list[HorizonWindow],
    time_mappers: list[TimeMapper],
    epoch: TimeEpoch,
) -> None:
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `model` | `CpModel` | L1 CP-SAT 布尔分配模型 |
| `variables` | `dict` | `{"tasks": {...}, "plugins": {}}`（见下方结构） |
| `params` | `dict` | 用户 JSON 中 `constraint.params`，原样传入 |
| `windows` | `list[HorizonWindow]` | 所有周窗口 |
| `time_mappers` | `list[TimeMapper]` | 每周的 TimeMapper，与 windows 同序。可遍历槽位按 `day_name` 分桶、调 `resolve_or_nearest()` |
| `epoch` | `TimeEpoch` | horizon 级时间工具，ISO ↔ 绝对槽位 ↔ 周索引 |

## 注册与发现

```python
from projarvis.planner.l1.registry import register_distributor

@register_distributor("my_plugin")
def my_plugin(model, variables, params, windows, time_mappers, epoch):
    ...
```

文件放在 `projarvis/planner/l1/plugins/`，`discover_distributors()` 自动扫描。

## `variables` 结构

```python
{
    "tasks": {
        "task_A": {
            "vars": [BoolVar_w0, BoolVar_w1, ...],  # y[tid][w]，BoolVar=1 表示分配到第 w 周
            "duration": 16,                           # total_duration（15 分钟槽位）
            "spec": L1TaskSpec(...),                  # 原始 task，含 l2_metadata
        },
        ...
    },
    "plugins": {},  # 插件写入目标项
}
```

引擎已确保 one-hot（`sum(y[t][w]) == 1`）和容量约束。插件在此基础上追加约束或目标项。

## 插件能做什么

对齐 L2 插件模式，插件能且只能做两件事：

### A. 硬约束：`model.Add(...)`

直接往 CP-SAT 模型加约束。用于：

- 禁止 task 进入某些周（deadline：`y[t][w] == 0 for w > dl_week`）
- 锁定 task 到特定周（fixed_time：`y[t][w] == 1`）
- 跨周排序（dependency：`week(A) <= week(B)`）
- 周级精力上限（energy_budget：`sum(y[t][w] * consum[t]) <= budget`）

### B. 软目标项：写入 `variables["plugins"]`

插件写入 `variables["plugins"][plugin_name]`，engine 在构建目标函数时收集。支持两种内容：

```python
# 全局追加项——加到总目标，不替换任何 task 的 base
variables["plugins"]["energy_budget"] = [penalty_term_1, penalty_term_2]

# task 替换项——替换指定 task 的默认 earliest_bias
variables["plugins"]["task_distribution"] = {
    "task_terms": {tid: [y[tid][0]*0, y[tid][1]*priority, ...]},
    "objective_terms": [excess_penalty_w0, excess_penalty_w1],  # 可选的全局项
}
```

- `"task_terms"`：`{task_id: [term_w0, term_w1, ...]}`。engine 用这些项**替换**该 task 的默认 `y[t][w] * w * priority`。未被覆盖的 task 走默认 earliest_bias。
- `"objective_terms"`：全局追加项，加到总目标（如 even 的 excess 惩罚、energy_budget 的 shortfall）。

**插件绝不调 `model.Minimize()`**——那是 engine 的职责。

---

## 内置插件

### deadline — 截止日期约束

**type**：`"deadline"`

**参数**：无（从 `l2_metadata.deadline` 读取）

**行为**：对每个 task，若 `l2_metadata.deadline` 存在，读取 ISO 时间 → 转为周索引 → 禁止分配到 deadline 之后的周。

**JSON**：
```json
{"type": "deadline", "params": {}}
```

**task metadata**：
```json
{"id": "essay", "l2_metadata": {"deadline": "2026-05-15T23:59:00"}}
```

---

### fixed_time — 固定时间锁定

**type**：`"fixed_time"`

**参数**：无（从 `l2_metadata.fixed_time` 读取）

**行为**：对每个 task，若 `l2_metadata.fixed_time` 存在，将 task 锁定到该时间所在的周。

**JSON**：
```json
{"type": "fixed_time", "params": {}}
```

**task metadata**：
```json
{"id": "meeting", "l2_metadata": {"fixed_time": "2026-05-11T14:00:00"}}
```

---

### dependency — 跨周依赖

**type**：`"dependency"`

**参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `pairs` | `list[list[str, str]]` | 依赖对 `[before_id, after_id]`，before 必须先完成 |

**行为**：对每个 pair，约束 `week(before) <= week(after)`（同周由 L2 dependency 插件处理排序）。

**JSON**：
```json
{
  "type": "dependency",
  "params": {
    "pairs": [["read_ch1", "write_summary"], ["plan", "execute"]]
  }
}
```

---

### task_distribution — 多策略分发器

**type**：`"task_distribution"`

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `mode` | `str` | `"earliest_bias"` | 分发模式 |
| `task_ids` | `list[str]` | `[]` | 仅 `even` 模式需要，指定均分组的 task |
| `weight` | `int` | `1` | 仅 `even` 模式，excess 惩罚权重 |

**模式一览**：

| mode | 作用范围 | 行为 |
|------|---------|------|
| `earliest_bias` | 所有 task | 默认，越早越好（不写 task_terms） |
| `front_load` | 所有 task | 用 `w²` 替代 `w`，比默认更强的早期偏好 |
| `ramp_up` | 有 deadline 的 task | 反转方向，越靠近 deadline 越多 |
| `deadline_driven` | 有 deadline 的 task | 以 deadline 为锚，惩罚偏离 `abs(w - dl_week)` |
| `even` | `task_ids` 指定的 task | 均匀分布。抵消 base bias + excess 惩罚驱动各周平衡 |

`front_load`、`ramp_up`、`deadline_driven` 自动确定作用范围，无需传 `task_ids`。只有 `even` 需要。

**JSON 示例**：
```json
// 均匀分布——把同系列 task 分散到不同周
{
  "type": "task_distribution",
  "params": {
    "mode": "even",
    "task_ids": ["review_ch3", "review_ch4", "review_ch5"],
    "weight": 5
  }
}

// 以 deadline 为锚点分配
{"type": "task_distribution", "params": {"mode": "deadline_driven"}}

// 激进的前紧后松
{"type": "task_distribution", "params": {"mode": "front_load"}}
```

---

### energy_budget — 周级精力预算

**type**：`"energy_budget"`

**参数**：

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `focus_budget_per_day` | int | 0 | 每日专注消耗硬上限（0=不限制） |
| `exercise_budget_per_day` | int | 0 | 每日运动消耗硬上限 |
| `focus_target_per_day` | int | 0 | 每日专注软目标 |
| `exercise_target_per_day` | int | 0 | 每日运动软目标 |
| `focus_shortfall_weight` | int | 0 | 专注不足惩罚权重（L1 自动取 1/3） |
| `exercise_shortfall_weight` | int | 0 | 运动不足惩罚权重（L1 自动取 1/3） |

**周预算推导**：`日预算 × 工作日数`。工作日数通过遍历 `time_mappers[w]` 的压缩槽位、按 `day_name` 分桶得出——与 L2 `energy_budget` 发现 `day_ranges` 的方式完全一致。

**硬约束**：`sum(y[t][w] × consum[t]) ≤ 周预算`。消耗值 `consum = int(duration × multiplier)`，multiplier 从 `l2_metadata` 读取，与 L2 完全一致。

**软目标**：shortfall 惩罚项，权重为 L2 的 1/3（至少为 1），留余量给 L2 天级排程。

**task metadata**：
```json
{"id": "deep_work", "l2_metadata": {"focus_multiplier": 0.8}}
```

**JSON 示例**：
```json
{
  "type": "energy_budget",
  "params": {
    "focus_budget_per_day": 20,
    "focus_target_per_day": 15,
    "focus_shortfall_weight": 3
  }
}
```

---

## 规则

1. **只写 model 和 variables["plugins"]** — 加硬约束或目标项，不调 Minimize 也不操作 solver
2. **不抛异常** — 参数缺失/无效/越界时静默跳过（`continue`/`return`）
3. **metadata 用 epoch** — ISO 时间通过 `epoch.iso_to_real_slot()` + `epoch.week_index()` 转周索引；或通过 `time_mappers[w].resolve_or_nearest()` 转压缩槽位
4. **硬约束独立、软目标叠加** — 多个插件加的硬约束取交集，目标项由 engine 汇总到 `sum(terms)` 中

## 与 L2 插件的差异

| | L2 约束插件 | L1 分发器插件 |
|---|---|---|
| 签名 | `fn(model, variables, params, time_mapper)` | `fn(model, variables, params, windows, time_mappers, epoch)` |
| 注册 | `@register_constraint` | `@register_distributor` |
| 扫描目录 | `l2/plugins/` | `l1/plugins/` |
| 作用阶段 | `schedule()` — 单周内排布 | `allocate()` — 任务分配到哪一周 |
| variables | `{"tasks": {id: {start, end, interval, spec}}, "plugins": {}}` | `{"tasks": {id: {vars, duration, spec}}, "plugins": {}}` |
| 变量粒度 | 连续 IntVar（start/end） | 布尔 BoolVar（y[t][w]） |
| 任务拆分 | solver 决定 start/end | 不拆分——布尔变量，整块进一周 |
| 目标项机制 | 只追加 `objective_terms` | 追加 `objective_terms` + 可选 `task_terms` 替换 base |
