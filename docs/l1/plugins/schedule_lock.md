# L1 schedule_lock — 硬锁定任务到原周

从上次调度结果中锁定任务的所属周，不允许在重计划中改变。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `locked_start` | ISO 8601 datetime，任务在上次调度中的开始时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "schedule_lock", "params": {}}` |

## JSON 示例

```json
{
  "tasks": [
    {"id": "coding", "l1": {"total_duration": 16}, "l2": {"metadata": {"locked_start": "2026-05-12T10:00:00"}}},
    {"id": "new_task", "l1": {"total_duration": 8}}
  ],
  "constraints": [
    {"type": "schedule_lock", "params": {}}
  ]
}
```

coding 上次在 5 月 12 日（week 1 的周二）→ L1 强制 coding 必须在 week 1。

## 行为

- 遍历所有 task，检查 `l2_metadata.locked_start`
- ISO 时间通过 `epoch.iso_to_real_slot()` 转为绝对槽位，再通过 `epoch.week_index()` 转为周索引
- 加硬约束：`y[task][locked_week] == 1`（该周必须分配）
- 无 `locked_start` 声明的 task 跳过

## 边界

- 无 task 声明 `locked_start` → 静默返回
- `locked_start` ISO 超出 epoch 范围 → `TimeMappingError` 被静默捕获，不加约束
- `locked_start` 的周索引超出 `windows` 范围 → 跳过
- 与 `deadline` 插件冲突（`locked_start` 在 deadline 之后）→ solver 返回 INFEASIBLE

## 与 fixed_time 的区别

| | `fixed_time` | `locked_start` |
|---|---|---|
| 语义 | 用户的绝对约定（会议、航班） | 上次调度结果，不是绝对约定 |
| 来源 | 用户指定 | 从上次 `MultiWeekSolution` 提取 |
| L2 协作 | L2 `fixed_time` 锁精确槽 | L2 `schedule_lock` 锁精确槽 |

不应给同一任务同时设置 `locked_start` 和 `previous_start`。
