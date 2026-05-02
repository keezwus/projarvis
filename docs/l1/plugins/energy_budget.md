# L1 energy_budget — 周级精力预算

对高专注和高运动量任务做**周级**硬上限和软目标。与 L2 `energy_budget` 协同：L1 管周维度不超标，L2 管天维度不超标。

## 数据位置

| 位置 | 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `TaskSpec.metadata` | `focus_multiplier` | float | 0 | 单位时长专注消耗倍率 |
| `TaskSpec.metadata` | `exercise_multiplier` | float | 0 | 单位时长体力消耗倍率 |
| `ConstraintSpec.params` | `focus_budget_per_day` | int | 0 | 每日专注硬上限。L1 自动 × 工作日数 = 周预算 |
| `ConstraintSpec.params` | `exercise_budget_per_day` | int | 0 | 每日运动硬上限 |
| `ConstraintSpec.params` | `focus_target_per_day` | int | 0 | 每日专注软目标（L1 轻量级） |
| `ConstraintSpec.params` | `exercise_target_per_day` | int | 0 | 每日运动软目标 |
| `ConstraintSpec.params` | `focus_shortfall_weight` | int | 0 | 专注不足惩罚权重（L1 自动取 1/3） |
| `ConstraintSpec.params` | `exercise_shortfall_weight` | int | 0 | 运动不足惩罚权重（L1 自动取 1/3） |

**关键设计**：用户只需指定日预算。周预算由 L1 自动推导——通过 `TimeMapper` 遍历每周的压缩槽位、按 `day_name` 分桶数出工作日数，`周预算 = 日预算 × 工作日数`。

软目标权重自动降为 L2 的 1/3：L1 留余量给 L2 天级腾挪空间（如果 L1 把周预算填满，L2 天级可能排不开）。

## JSON 示例

```json
{
  "tasks": [
    {"id": "deep_work", "l1": {"total_duration": 16}, "l2": {"metadata": {"focus_multiplier": 1.0}}},
    {"id": "study",     "l1": {"total_duration": 16}, "l2": {"metadata": {"focus_multiplier": 1.0}}},
    {"id": "gym",       "l1": {"total_duration": 8},  "l2": {"metadata": {"exercise_multiplier": 1.0}}},
    {"id": "admin",     "l1": {"total_duration": 8}}
  ],
  "constraints": [
    {
      "type": "energy_budget",
      "params": {
        "focus_budget_per_day": 10,
        "exercise_budget_per_day": 6
      }
    }
  ]
}
```

- deep_work: 16 × 1.0 = 16 专注消耗
- study: 16 × 1.0 = 16 专注消耗
- gym: 8 × 1.0 = 8 运动消耗
- admin: 无 multiplier → 不参与
- 假设每周 5 个工作日：周专注预算 = 10 × 5 = 50，周运动预算 = 6 × 5 = 30
- deep_work + study = 32 ≤ 50 → 可以同周。如果用户再加一个 focus 任务，可能被迫分散

## 架构

| 约束 | 类型 | 含义 |
|------|------|------|
| 每周 Σ consum ≤ daily_budget × 工作日数 | 硬约束 | 不超周上限 |
| shortfall = max(0, target_per_day × 工作日数 − actual) | 软目标项 | 尽量用满（权重 = weight // 3） |

## 行为

- 通过 `time_mappers[w]` 遍历每周所有压缩槽位，按 `day_name(comp)` 分桶，数出工作日数
- 读 task 的 `focus_multiplier` / `exercise_multiplier`，计算 `consum = int(duration × multiplier)`
- 每周硬约束：`sum(y[t][w] × consum[t]) ≤ budget_per_day × working_days`
- 软目标：shortfall IntVar 惩罚项写入 `objective_terms`

## 边界

- multiplier 为 0 → 不参与对应维度
- `duration × multiplier` 取整后为 0 → 不参与约束
- 某周无该维度 task → shortfall 为 0（被 one-hot 自然处理）
- budget = 0 → 不加约束（0 = 不限制）
- 硬上限导致所有分配方案不可行 → solver 返回 `CapacityReport(status="OVERSATURATED")`

## 与 L2 energy_budget 的关系

| 维度 | L2 | L1 |
|------|----|----|
| 真值源 | `focus_budget_per_day` | 同一个 |
| 工作日发现 | `time_mapper.total_slots` → `day_name` 分桶 | `time_mappers[w]` 完全一致 |
| 聚合粒度 | 按天，创建 `is_on_day` BoolVar | 按周，复用已有 `y[t][w]` BoolVar |
| 消耗计算 | `int(duration × multiplier)` | 完全一致 |
| 硬约束 | `sum(contrib per day) ≤ daily_budget` | `sum(y × consum) ≤ daily × days` |
| 软目标 | shortfall × weight | shortfall × (weight // 3) |

用户只需传一个 `{"type": "energy_budget", "params": {...}}`，L1 和 L2 各自的插件分别处理周级和天级。
