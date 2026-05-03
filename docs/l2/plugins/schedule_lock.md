# schedule_lock — 硬锁定任务到原时间槽

从上次调度结果中锁定任务的精确时间槽，不允许在重计划中改变。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `locked_start` | ISO 8601 datetime，任务在上次调度中的开始时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "schedule_lock", "params": {}}` |

## JSON 示例

```json
{
  "tasks": [
    {"id": "coding", "duration": 8, "metadata": {"locked_start": "2026-05-04T10:00:00"}},
    {"id": "new_meeting", "duration": 4}
  ],
  "constraints": [
    {"type": "schedule_lock", "params": {}}
  ]
}
```

coding 锁定在周一 10:00 开始，持续 8 槽（2 小时）。new_meeting 自由调度。

## 行为

- 遍历所有 task，检查 `metadata.locked_start`
- ISO 时间通过 `time_mapper.resolve_time_ref()` 转为压缩槽位
- 加硬约束：`start == locked_slot`
- （`end - start == duration` 已由 `hydrate()` 保证，无需加 end 约束）
- 无 `locked_start` 声明的 task 跳过
- `TimeMappingError`（时间在可用域外）→ 静默跳过

## 边界

- 无 task 声明 `locked_start` → 静默返回
- `locked_start` 在午休或其他不可用时段 → `TimeMappingError` 被静默捕获，task 自由调度
- `locked_start` 对应的槽位跨度跨 lunch break 且 task 跨边界 → solver 返回 INFEASIBLE（被 block boundary 约束阻止）
- 不应给同一任务同时设置 `locked_start` 和 `previous_start`

## 与 fixed_time 的区别

| | `fixed_time` | `locked_start` |
|---|---|---|
| 语义 | 用户的绝对约定 | 上次调度结果 |
| 来源 | 用户指定 | 从上次 `Solution` 提取 |
| L1 协作 | L1 `fixed_time` 锁周 | L1 `schedule_lock` 锁周 |
