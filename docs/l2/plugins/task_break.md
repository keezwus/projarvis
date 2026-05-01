# task_break — 任务间休息

任意两个任务之间强制最小间隔。

## 数据位置

| 位置 | 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|---|
| `ConstraintSpec.params` | `default_gap` | int | 1 | 最小间隔槽位数（15min/slot） |
| `ConstraintSpec.params` | `exempt_task_ids` | list[str] | [] | 豁免的 task id，不触发间隔 |

不涉及 `TaskSpec.metadata`。

## JSON 示例

```json
{
  "tasks": [
    {"id": "deep_work", "duration": 12},
    {"id": "study",     "duration": 8},
    {"id": "walk_block", "duration": 4},
    {"id": "lunch",     "duration": 4}
  ],
  "constraints": [
    {
      "type": "task_break",
      "params": {
        "default_gap": 1,
        "exempt_task_ids": ["walk_block", "lunch"]
      }
    }
  ]
}
```

deep_work 和 study 之间至少 1 slot（15 分钟）间隔。walk_block 和 lunch 是休息活动，和其他 task 之间不强制 gap。

## 行为

- 对每对 task (A, B) 引入 BoolVar 决定前后顺序
- A 的 start 在 B 的 end 之后 + gap，或反方向——恰好一种
- 目标函数 `Minimize(sum(starts))` 确保 gap 刚好压在 default_gap，不会无故扩大

## 与自然间隔（午餐/睡眠）

在可用块边界处的自然间隔（如上午块 12:00 结束，下午块 14:00 开始）天然远大于 default_gap，约束自动满足，不会插入额外休息。

## 功能范围

只做"每对任务之间的静态间隔"。不做连续工作时长追踪（`max_consecutive_work`）。

## 复杂度

O(n²/2) pair。30 task ≈ 435 BoolVar + 870 约束。

## 边界

- `default_gap` 缺失 → 默认 1
- < 2 个 task → 静默返回
- 所有 task 都在 exempt_task_ids 里 → 无约束添加
