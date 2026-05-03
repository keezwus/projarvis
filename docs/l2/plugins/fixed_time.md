# fixed_time — 固定时间槽锁定

有固定时间窗口的任务锁定到精确槽位。与 L1 `fixed_time` 协同：L1 锁定周，L2 锁定精确槽位。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `fixed_time` | ISO 8601 datetime，任务固定开始时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "fixed_time", "params": {}}` |

## JSON 示例

```json
{
  "tasks": [
    {"id": "meeting", "duration": 4, "metadata": {"fixed_time": "2026-05-04T14:00:00"}},
    {"id": "coding", "duration": 16}
  ],
  "constraints": [
    {"type": "fixed_time", "params": {}}
  ]
}
```

meeting 固定在周一下午 14:00 开始，持续 4 槽（1 小时）。coding 自由调度。

## 行为

- 遍历所有 task，检查 `metadata.fixed_time`
- ISO 时间通过 `time_mapper.resolve_time_ref()` 转为压缩槽位
- 加硬约束：`start == fixed_start`，`end == fixed_start + duration`
- 无 `fixed_time` 声明的 task 跳过
- `TimeMappingError`（时间在可用域外）→ 静默跳过

## 边界

- 无 task 声明 `fixed_time` → 静默返回
- `fixed_time` 在午休或其他不可用时段 → `TimeMappingError` 被静默捕获，task 自由调度
- `fixed_time` 对应的槽位跨度跨 lunch break 且 task 跨边界 → solver 返回 INFEASIBLE（被 block boundary 约束阻止）
- 多个 task 声明相同 `fixed_time` → solver 返回 INFEASIBLE（NoOverlap 冲突）

## 与 L1 fixed_time 的关系

| 层级 | 做什么 | 约束 |
|------|--------|------|
| L1 | 确保 task 分到 fixed_time 所在周 | `y[t][fixed_week] == 1` |
| L2 | 确保 task 在该周内固定在精确槽位 | `start == fixed_start`，`end == fixed_end` |

用户只需传一个 `{"type": "fixed_time", "params": {}}`，L1 和 L2 各自的插件都会被触发（不同注册表，不冲突）。
