from ..registry import register_constraint


@register_constraint("task_break")
def task_break(model, variables, params, time_mapper=None):
    gap = params.get("default_gap", 1)
    exempt_ids = set(params.get("exempt_task_ids", []))

    task_ids = list(variables["tasks"].keys())
    n = len(task_ids)
    if n < 2:
        return

    tasks = variables["tasks"]

    for i in range(n):
        for j in range(i + 1, n):
            tid_a = task_ids[i]
            tid_b = task_ids[j]

            if tid_a in exempt_ids or tid_b in exempt_ids:
                continue

            tv_a = tasks[tid_a]
            tv_b = tasks[tid_b]

            bv = model.NewBoolVar(f"tb_order_{tid_a}_{tid_b}")
            model.Add(tv_b["start"] >= tv_a["end"] + gap).OnlyEnforceIf(bv)
            model.Add(tv_a["start"] >= tv_b["end"] + gap).OnlyEnforceIf(bv.Not())
