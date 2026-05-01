# energy_budget — 体力/专注管理

对高专注和高运动量任务做每日上限（硬约束）和每日目标（软约束）。

## 数据位置

| 位置 | 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| `TaskSpec.metadata` | `focus_multiplier` | float | 0 | 单位时长专注消耗倍率 |
| `TaskSpec.metadata` | `exercise_multiplier` | float | 0 | 单位时长体力消耗倍率 |
| `ConstraintSpec.params` | `focus_budget_per_day` | int | 0 | 每日专注硬上限 |
| `ConstraintSpec.params` | `focus_budget_overrides` | dict | {} | 按天覆盖上限，key = monday~sunday |
| `ConstraintSpec.params` | `exercise_budget_per_day` | int | 0 | 每日运动硬上限 |
| `ConstraintSpec.params` | `exercise_budget_overrides` | dict | {} | 按天覆盖上限 |
| `ConstraintSpec.params` | `focus_target_per_day` | int | 0 | 每日专注软目标 |
| `ConstraintSpec.params` | `exercise_target_per_day` | int | 0 | 每日运动软目标 |
| `ConstraintSpec.params` | `focus_shortfall_weight` | int | 0 | 专注 shortfall 惩罚权重 |
| `ConstraintSpec.params` | `exercise_shortfall_weight` | int | 0 | 运动 shortfall 惩罚权重 |

multiplier 默认 0：普通任务不声明即不消耗配额。实际消耗 = `int(duration × multiplier)`，在插件调用时 Python 层面取整，不进入 CP-SAT 浮点运算。

## JSON 示例

```json
{
  "tasks": [
    {"id": "deep_work",  "duration": 12, "metadata": {"focus_multiplier": 1.0}},
    {"id": "study",      "duration": 8,  "metadata": {"focus_multiplier": 1.0}},
    {"id": "gym",        "duration": 6,  "metadata": {"exercise_multiplier": 1.0}},
    {"id": "walk",       "duration": 2,  "metadata": {"exercise_multiplier": 0.5}},
    {"id": "admin",      "duration": 4}
  ],
  "constraints": [
    {
      "type": "energy_budget",
      "params": {
        "focus_budget_per_day": 32,
        "focus_budget_overrides": {"friday": 20},
        "exercise_budget_per_day": 16,
        "focus_target_per_day": 24,
        "exercise_target_per_day": 8,
        "focus_shortfall_weight": 100,
        "exercise_shortfall_weight": 100
      }
    }
  ]
}
```

- deep_work（12 slots × 1.0 = 12 consum）和 study（8）消耗专注
- gym（6 × 1.0 = 6）消耗运动，walk（2 × 0.5 = int(1.0) = 1）消耗 1 运动
- admin 无 multiplier 声明 → 不参与任何 budget
- 周五专注上限降到 20，其他天 32

## 架构

| 约束 | 类型 | 含义 |
|---|---|---|
| 每天 Σ consum ≤ budget | 硬约束 | 不超每日上限 |
| shortfall = max(0, target − actual) | 软目标项 | 尽量用满配额 |

## 边界

- multiplier 为 0 → 不参与对应维度
- `duration × multiplier` 取整后可能为 0（如 duration=1, multiplier=0.5 → 0），此时不参与约束
- 某天无该维度 task → shortfall = target（罚满，除非 weight=0）
- budget < target → 硬约束优先，target 永远达不到但不 infeasible
