# L2 约束插件开发

## 插件签名

```python
def plugin_fn(
    model: cp_model.CpModel,
    variables: dict,
    params: dict,                          # 时间字段已转为压缩槽位
    time_mapper: TimeMapper,               # 压缩域 → real slot 查询
) -> None:
```

`params` 的值已经被 Engine 预处理：所有 ISO 8601 字符串转换为压缩槽位整数，非时间字段保留原始类型。

## 注册

```python
from projarvis.planner.l2.registry import register_constraint

@register_constraint("no_meetings_tuesday")
def no_meetings_tuesday(model, variables, params, time_mapper):
    ...
```

Engine 启动时 `discover_plugins()` 自动扫描 `projarvis.planner.l2.plugins` 包，`importlib.import_module` 每个模块触发装饰器执行。插件文件放在 `l2/plugins/` 目录下即可自动注册，无需手动 import。

## `variables` 结构

```python
variables = {
    "tasks": {
        "task_id": {
            "start": IntVar,       # 压缩开始槽位
            "end": IntVar,         # 压缩结束槽位
            "duration": int,       # 固定时长
            "interval": IntervalVar,
            "spec": TaskSpec,      # id, duration, metadata
        }
    },
    "plugins": {
        "my_plugin": { ... }      # 插件私有命名空间，只写这里
    }
}
```

## 四条规则

1. **OnlyEnforceIf** — 可选约束必须用 `BoolVar + OnlyEnforceIf` 封装。结构类似：
   ```python
   bv = model.NewBoolVar("name")
   model.Add(constraint).OnlyEnforceIf(bv)
   model.Add(other_constraint).OnlyEnforceIf(bv.Not())
   ```

2. **命名空间隔离** — 插件写入 `variables["plugins"]["type_name"]`，不可写其他 key。跨插件只读 `variables["tasks"]`。

3. **不直接 import 插件模块** — 只通过 `@register_constraint` 注册。Engine 不 import 具体插件文件，通过 registry 查找。

4. **不碰 solver** — 插件不操作 CpSolver 对象。追加优化项通过 `engine.add_objective_term(expr)`。

## 时间查询

通过 `time_mapper` 查询压缩槽位的时间属性：

| 方法 | 返回 | 说明 |
|------|------|------|
| `day_of_week(slot)` | int | 0=Monday |
| `day_name(slot)` | str | "monday" |
| `time_of_day(slot)` | str | "09:00" |
| `hour(slot)` | int | 小时数 |
| `minute(slot)` | int | 分钟数 |
| `is_morning(slot)` | bool | < 12:00 |
| `is_afternoon(slot)` | bool | 12:00-18:00 |
| `is_evening(slot)` | bool | >= 18:00 |
| `compressed_to_real(slot)` | int | real slot |

## 任务筛选

插件自己遍历 `variables["tasks"]` 决定作用范围：

```python
for tid, tv in variables["tasks"].items():
    if params.get("task_id") and tid != params["task_id"]:
        continue
    if params.get("metadata_key") and params["metadata_key"] not in tv["spec"].metadata:
        continue
    # ... 对符合条件的 t 加约束
```

`task_id` 显式匹配和 `metadata` 过滤是推荐模式。不传 → 全量。

## 目标追加

```python
def my_plugin(model, variables, params, time_mapper):
    target = variables["tasks"].get(params["task_id"])
    if target is None:
        return
    # 插件自身持有的 engine 引用
    engine.add_objective_term(weight * target["end"])
```

`add_objective_term` 在 `hydrate()` 之后、`set_objective()` 之前有效。最终目标 = `Minimize(sum(starts) + sum(_objective_terms))`。
