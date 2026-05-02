# L1 dependency — 跨周任务依赖

如果 A 依赖 B（B 必须先完成），则 B 必须在 A 之前或同一周。

## 数据位置

| 位置 | 字段 | 类型 | 说明 |
|------|------|------|------|
| `ConstraintSpec.params` | `pairs` | list[[str, str]] | 依赖对列表，每项 `[before_id, after_id]` |
| `ConstraintSpec.params` | `buffer_slots` | int（可选，默认 0） | L2 用，L1 忽略 |

## JSON 示例

```json
{
  "tasks": [
    {"id": "research", "l1": {"total_duration": 16}},
    {"id": "write", "l1": {"total_duration": 16}}
  ],
  "constraints": [
    {
      "type": "dependency",
      "params": {
        "pairs": [["research", "write"]],
        "buffer_slots": 2
      }
    }
  ]
}
```

research 必须先完成，write 才能开始 → L1 确保 research 的周 ≤ write 的周。

## 行为

- 遍历 `params.pairs`
- 对每对 `(before_id, after_id)`：计算 `before_week = sum(w * y[before][w])`，`after_week = sum(w * y[after][w])`
- 加硬约束：`before_week <= after_week`
- `params.buffer_slots` 在 L1 层面被忽略（周级不关心槽位级 buffer）

## 边界

- `pairs` 为空或不存在 → 静默返回
- pair 引用的 task_id 不存在 → 跳过该 pair
- 同一对 task 在同一周 → 约束允许（`<=`）。同周内的精确排序由 L2 `dependency` 插件处理
- 循环依赖（A → B → A）→ 不检测，solver 可能返回 INFEASIBLE

## 与 L2 dependency 的关系

| 层级 | 做什么 | 约束 |
|------|--------|------|
| L1 | 跨周排序 | `week_of(before) <= week_of(after)` |
| L2 | 同周内排序 | `start_after >= end_before + buffer_slots` |

用户传一个 `{"type": "dependency", "params": {"pairs": [...]}}`，L1 和 L2 各自的插件分别处理跨周和同周部分。
