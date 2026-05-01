# dependency — 任务依赖

前置-后继关系约束。B 必须在 A 完成后才能开始。

## 数据位置

| 位置 | 字段 | 说明 |
|---|---|---|
| `ConstraintSpec.params` | `pairs` | `[前置id, 后继id]` 的列表 |
| `ConstraintSpec.params` | `buffer_slots` | 可选，前置完成后等待的槽位数，默认 0 |

不涉及 `TaskSpec.metadata`。

## JSON 示例

```json
{
  "tasks": [
    {"id": "read_ch3",  "duration": 8},
    {"id": "notes_ch3", "duration": 4},
    {"id": "review_ch3", "duration": 8}
  ],
  "constraints": [
    {
      "type": "dependency",
      "params": {
        "buffer_slots": 4,
        "pairs": [
          ["read_ch3", "review_ch3"],
          ["notes_ch3", "review_ch3"]
        ]
      }
    }
  ]
}
```

review_ch3 必须在 read_ch3 和 notes_ch3 都完成 + 4 槽位（1 小时）之后才能开始。

## 行为

- 遍历 `pairs`，对每对 `[before_id, after_id]` 加 `start_after >= end_before + buffer_slots`
- 同一 task 有多个前置 → 多条不等式，solver 自动取最严格

## 边界

- `pairs` 缺失 → 静默返回
- pair 中的 task_id 不在当周 → 跳过（假设已在上周完成）
- 循环依赖 → 不检测，存在则 INFEASIBLE

## 与 task_break 的重叠

两个插件可能在同一对 task 上加约束。dependency 的 buffer 和 task_break 的 gap 同时存在时，solver 取 max。语义不同——buffer 是"前置完成后缓冲"，gap 是"所有任务通用间隔"——保留各自独立。
