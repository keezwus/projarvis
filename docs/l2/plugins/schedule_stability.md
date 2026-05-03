# schedule_stability — 槽级稳定性软约束

重计划时尽量让任务留在原来的时间槽，偏离时产生惩罚。通过绝对值线性化将偏离量加入目标函数。

## 数据位置

| 位置 | 字段 | 说明 |
|------|------|------|
| `TaskSpec.metadata` | `previous_start` | ISO 8601 datetime，任务在上次调度中的开始时间 |
| `TaskSpec.metadata` | `stability_weight` | int，可选。单任务覆盖权重 |
| `ConstraintSpec.params` | `default_weight` | int，默认 5。全局稳定性权重 |

## 权重设计

目标函数贡献 = `start + |start - previous_start| × weight`。令 ps = previous_start。

| 区间 | 导数 | weight=1 | weight=5 |
|------|------|----------|----------|
| start < ps | `1 - w` | 0（平坦，无稳定性） | -4（推回 ps） |
| start > ps | `1 + w` | 2 | 6（推回 ps） |

weight=5 形成稳固盆地——偏离 1 槽净亏 4，但若打包收益 > 20 槽，任务仍可合理腾挪。

## JSON 示例

```json
{
  "tasks": [
    {"id": "coding", "duration": 8, "metadata": {"previous_start": "2026-05-04T10:00:00"}},
    {"id": "admin", "duration": 4, "metadata": {"previous_start": "2026-05-04T15:00:00", "stability_weight": 20}},
    {"id": "new_meeting", "duration": 4}
  ],
  "constraints": [
    {"type": "schedule_stability", "params": {"default_weight": 5}}
  ]
}
```

- coding 用全局 weight=5
- admin 覆盖 weight=20（特别不想动）
- new_meeting 无 `previous_start`，自由调度

## 行为

- 遍历所有 task，检查 `metadata.previous_start`
- ISO 时间通过 `time_mapper.resolve_time_ref()` 转为压缩槽位 `ps`
- 对每个 task 创建辅助变量：
  ```
  dp = NewIntVar(0, domain_max)  # 正向偏离量
  dm = NewIntVar(0, domain_max)  # 负向偏离量
  start - ps == dp - dm          # 绝对值线性化
  ```
- 惩罚项：`(dp + dm) × effective_weight` 写入 `variables["plugins"]["schedule_stability"]`
- 权重：`metadata.stability_weight` > `params.default_weight` > 默认 5
- `TimeMappingError`（时间不可用）→ 静默跳过
- `effective_weight <= 1` → 跳过该 task（不激活）

## 边界

- 无 task 声明 `previous_start` → 静默返回
- `previous_start` 在可用域外（如 override 导致的午休区）→ 跳过
- 不该给同一 task 同时设 `locked_start` 和 `previous_start`
- weight=1 不激活稳定性（导数=0），但不报错——仅跳过
- 绝对值线性化每个 task 增加 2 个 IntVar + 1 条线性约束

## 调参

- `default_weight=5`（默认）：温和盆地，适合多数场景
- `default_weight=10-20`：强锁定，任务几乎不动
- `default_weight=2-3`：轻度偏好，允许较多腾挪
- 单任务覆盖：`metadata.stability_weight` 设更高值
