from ..registry import register_distributor


@register_distributor("dependency")
def dependency_distributor(model, variables, params, windows, time_mappers, epoch):
    pairs = params.get("pairs", [])
    n_weeks = len(windows)
    td = variables["tasks"]
    for before_id, after_id in pairs:
        if before_id not in td or after_id not in td:
            continue
        before_week = sum(w * td[before_id]["vars"][w] for w in range(n_weeks))
        after_week = sum(w * td[after_id]["vars"][w] for w in range(n_weeks))
        model.Add(before_week <= after_week)
