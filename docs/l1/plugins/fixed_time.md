# L1 fixed_time — 固定时间周锁定

有固定时间窗口的任务锁定到其所在周。与 L2 `fixed_time` 协同：L1 锁定周，L2 锁定精确槽位。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `fixed_time` | ISO 8601 datetime，任务固定开始时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "fixed_time", "params": {}}` |

## JSON 示例

```json
{
  "tasks": [
    {"id": "meeting", "l1": {"total_duration": 4}, "l2": {"metadata": {"fixed_time": "2026-05-12T14:00:00"}}},
    {"id": "coding", "l1": {"total_duration": 16}}
  ],
  "constraints": [
    {"type": "fixed_time", "params": {}}
  ]
}
```

meeting 固定在 5 月 12 日（week 1 的周二）→ L1 强制 meeting 必须在 week 1。

## 行为

- 遍历所有 task，检查 `l2_metadata.fixed_time`
- ISO 时间通过 `epoch.iso_to_real_slot()` 转为绝对槽位，再通过 `epoch.week_index()` 转为周索引
- 加硬约束：`y[task][fixed_week] == 1`（该周必须分配，one-hot 确保其他周为 0）
- 无 fixed_time 声明的 task 跳过

## 边界

- 无 task 声明 fixed_time → 静默返回
- fixed_time ISO 超出 epoch 范围 → `TimeMappingError` 被静默捕获，不加约束
- fixed_time 的周索引超出 `windows` 范围 → 跳过（task 仍受 one-hot 约束分配到某周）
- 与 `deadline` 插件冲突（fixed_time 在 deadline 之后）→ solver 返回 INFEASIBLE
- L2 `fixed_time` 插件会在该周内加 `start == fixed_start` 和 `end == fixed_end` 硬约束
