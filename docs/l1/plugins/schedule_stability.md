# L1 schedule_stability — 周级稳定性软约束

重计划时尽量让任务留在原来分配的周，偏离时产生惩罚。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `previous_start` | ISO 8601 datetime，任务在上次调度中的开始时间 |
| `ConstraintSpec.params` | `default_weight` | int，默认 2。稳定性倍率，必须 > 1 |

## 权重设计

有效 weight = `priority × default_weight`。

| weight 条件 | 效果 |
|-------------|------|
| `default_weight > 1` | 稳定性胜出，任务留在原周 |
| `default_weight = 1` | neutral（与 L2 weight=1 相同问题：导数=0，无稳定性） |
| `default_weight < 1` | earliness 胜出，任务向 week 0 漂移 |

默认值 2 > 1，在默认策略 `earliest_bias` 下正常工作。

## JSON 示例

```json
{
  "tasks": [
    {"id": "coding", "l1": {"total_duration": 16, "priority": 10}, "l2": {"metadata": {"previous_start": "2026-05-12T10:00:00"}}},
    {"id": "reading", "l1": {"total_duration": 8, "priority": 1}}
  ],
  "constraints": [
    {"type": "schedule_stability", "params": {"default_weight": 2}}
  ]
}
```

coding 上次在 week 1，priority=10 → effective = 10 × 2 = 20。离开原周的惩罚很大。

## 行为

- 遍历所有 task，检查 `l2_metadata.previous_start`
- ISO 时间 → `epoch.iso_to_real_slot()` → `epoch.week_index()` → `previous_week`
- 惩罚项：`(1 - y[task][previous_week]) × priority × weight`
- 写入 `variables["plugins"]["schedule_stability"]`（`objective_terms`，叠加在默认目标之上）
- `TimeMappingError` 或超出范围 → 静默跳过
- `default_weight <= 1` → 直接返回（不激活）

## 边界

- 无 task 声明 `previous_start` → 静默返回
- `previous_start` ISO 超出 epoch 范围 → 跳过
- 不应给同一任务同时设置 `locked_start` 和 `previous_start`

## 与 task_distribution 策略交叉

`schedule_stability` 写入 `objective_terms`，与 `task_distribution` 的 `task_terms` 叠加。不同策略下的表现：

| 策略 | 目标形式 | 与 stability 的关系 |
|------|---------|-------------------|
| `earliest_bias` | `w × p` | 正常配合，weight > 1 即稳定 |
| `deadline_driven` | `|w - dl| × p` | 两者都向后拉，基本兼容 |
| `front_load` | `w² × p` | w² 梯度与稳定性天然冲突——需增大 weight 或二选一 |
| `ramp_up` | `(n-1-w) × p` | 方向与稳定性相反，建议只选其一 |

`front_load` + `schedule_stability` 同时启用时，如果任务被往后挤，w² 的梯度越来越大，最终压倒 stability。增大 `default_weight`（如 10-50）可缓解，或改为使用 `schedule_lock` 硬锁。
