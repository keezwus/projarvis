from ..registry import register_constraint


@register_constraint("dependency")
def dependency(model, variables, params, time_mapper=None):
    pairs = params.get("pairs")
    if not pairs:
        return

    buffer_slots = params.get("buffer_slots", 0)
    tasks = variables["tasks"]

    for before_id, after_id in pairs:
        before = tasks.get(before_id)
        after = tasks.get(after_id)
        if before is None or after is None:
            continue
        model.Add(after["start"] >= before["end"] + buffer_slots)
