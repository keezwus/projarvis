# L1 deadline — 跨周截止日期

任务必须在截止日期所在的周或之前完成。与 L2 `deadline` 插件协同：L1 管周级分配，L2 管天/槽位级约束。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `deadline` | ISO 8601 datetime，任务截止时间 |
| `ConstraintSpec` | — | 空开关 `{"type": "deadline", "params": {}}` |

L1 和 L2 的 deadline 读**同一个** `metadata.deadline` 字段。用户只需在 task 上声明一次 deadline，两个层级各自生效。

## JSON 示例

```json
{
  "tasks": [
    {"id": "report", "l1": {"total_duration": 16}, "l2": {"metadata": {"deadline": "2026-05-08T17:00:00"}}},
    {"id": "reading", "l1": {"total_duration": 8}}
  ],
  "constraints": [
    {"type": "deadline", "params": {}}
  ]
}
```

report 的 deadline 在 week 0 的周五 17:00 → L1 强制 report 必须在 week 0。

## 行为

- 遍历所有 task，检查 `l2_metadata.deadline`
- ISO 时间通过 `epoch.iso_to_real_slot()` 转为绝对槽位，再通过 `epoch.week_index()` 转为周索引
- 加硬约束：对 deadline 周之后的每一周 w，`y[task][w] == 0`
- 无 deadline 声明的 task 跳过

## 边界

- 无 task 声明 deadline → 静默返回（插件不添加任何约束）
- deadline ISO 超出 epoch 范围 → 抛出 `TimeMappingError`，被静默捕获，该 task 不加约束
- 仅控制周级分配。L2 `deadline` 插件在 schedule 阶段施加精确的 `end <= deadline_slot` 约束

## 与 L2 deadline 的关系

| 层级 | 做什么 | 约束 |
|------|--------|------|
| L1 | 确保 task 分到 deadline 周或之前 | `y[t][w] == 0` for w > dl_week |
| L2 | 确保 task 在该周内不晚于 deadline | `end <= deadline_slot` |

用户只需传一个 `{"type": "deadline", "params": {}}`，L1 和 L2 各自的插件都会被触发（不同注册表，不冲突）。
