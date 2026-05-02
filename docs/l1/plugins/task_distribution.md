# L1 task_distribution — 多策略任务分发

控制任务在周与周之间的分布形态。单个插件支持 5 种 mode，通过 `params.mode` 切换。

## 数据位置

| 位置 | 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `ConstraintSpec.params` | `mode` | str | `"earliest_bias"` | 分发策略 |
| `ConstraintSpec.params` | `task_ids` | list[str] | — | 仅 `even` mode 需要，指定同组任务 ID |
| `ConstraintSpec.params` | `weight` | int | 1 | 仅 `even` mode，excess 惩罚权重 |

## mode 一览

| mode | 作用范围 | 行为 | 需要额外参数 |
|------|---------|------|:--:|
| `earliest_bias` | 所有 task | 默认，越早越好 | 否 |
| `even` | `task_ids` 指定的任务 | 同组任务在各周均匀铺开 | task_ids, weight |
| `front_load` | 所有 task | 比 earliest_bias 更激进地尽早 | 否 |
| `ramp_up` | 有 deadline 的 task | 前期松后期紧，越靠近截止日期越多 | 否 |
| `deadline_driven` | 有 deadline 的 task | 以每个任务的 deadline 为锚点，安排在附近 | 否 |

## JSON 示例

### even：均匀分布

```json
{
  "tasks": [
    {"id": "workout_1", "l1": {"total_duration": 8}},
    {"id": "workout_2", "l1": {"total_duration": 8}},
    {"id": "workout_3", "l1": {"total_duration": 8}},
    {"id": "other", "l1": {"total_duration": 16}}
  ],
  "constraints": [
    {
      "type": "task_distribution",
      "params": {"mode": "even", "task_ids": ["workout_1", "workout_2", "workout_3"], "weight": 10}
    }
  ]
}
```

3 个健身任务在各周均匀分布。other 不受影响，走默认 earliest_bias。

### front_load：前紧后松

```json
{
  "constraints": [
    {"type": "task_distribution", "params": {"mode": "front_load"}}
  ]
}
```

所有 task 尽早完成，比默认更激进。

### deadline_driven：ddl 锚定

```json
{
  "tasks": [
    {"id": "exam_prep", "l1": {"total_duration": 32}, "l2": {"metadata": {"deadline": "2026-05-22T00:00:00"}}},
    {"id": "reading", "l1": {"total_duration": 8}}
  ],
  "constraints": [
    {"type": "task_distribution", "params": {"mode": "deadline_driven"}}
  ]
}
```

exam_prep 有 deadline → 自动安排在 deadline 附近。reading 无 deadline → 走默认 earliest_bias。

## 实现原理

插件采用**覆盖 base** 策略：通过 `task_terms` 替换默认的 `y[t][w] * w * priority` 目标项。

- `earliest_bias`：不写入 task_terms，engine 用默认 base
- `front_load`：目标项 = `y[t][w] * w² * priority`（平方增长，后期代价更大）
- `ramp_up`：目标项 = `y[t][w] * (n_weeks - 1 - w) * priority`（反转方向，越早越贵）
- `deadline_driven`：目标项 = `y[t][w] * abs(w - dl_week) * priority`（偏离 ddl 越远越贵）
- `even`：目标项 = 每周期望 excess（`excess[w] >= 该周总duration - 平均值`），同时 task_terms = `y[t][w] * 0` 抵消 base bias

## 边界

- 未知 mode → 静默返回（不添加任何约束或目标项）
- `even` 的 task_ids 引用不存在的 task → 过滤掉，如果过滤后少于 2 个 task 则静默返回
- `ramp_up` 和 `deadline_driven`：无 deadline 的 task 自动跳过，走默认 earliest_bias
- `deadline` 硬约束插件和 `deadline_driven` 软分布可同时使用：硬约束禁止超过 ddl，软分布控制在 ddl 前如何分布
