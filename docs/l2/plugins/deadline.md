# deadline — 截止日期

任务必须在指定时间前完成。

## 数据位置

| 位置 | 字段 | 说明 |
|---|---|---|
| `TaskSpec.metadata` | `deadline` | ISO 8601 datetime，任务截止时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "deadline", "params": {}}` |

## JSON 示例

```json
{
  "tasks": [
    {"id": "ch3_review", "duration": 8, "metadata": {"deadline": "2026-05-05T17:00:00"}},
    {"id": "read_paper", "duration": 4}
  ],
  "constraints": [
    {"type": "deadline", "params": {}}
  ]
}
```

ch3_review 必须在周五 17:00 前结束。read_paper 无 deadline 声明，不受约束。

## 行为

- 遍历所有 task，检查 `metadata.deadline`
- ISO 时间通过 `resolve_or_nearest` 转为压缩槽位（落在可用窗口外时自动前移）
- 加硬约束：`end <= deadline_slot`
- 无 deadline 声明的 task 跳过

## 边界

- 无 task 声明 deadline → 静默返回
- deadline 早于 task 最小 duration → solver 返回 INFEASIBLE
- 多个 task 声明各自 deadline → 各自约束独立生效
