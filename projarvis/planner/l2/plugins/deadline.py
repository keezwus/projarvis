from ..registry import register_constraint


@register_constraint("deadline")
def deadline(model, variables, params, time_mapper=None):
    for tid, tv in variables["tasks"].items():
        dl = tv["spec"].metadata.get("deadline")
        if dl is None:
            continue
        dl_slot = time_mapper.resolve_or_nearest(dl)
        model.Add(tv["end"] <= dl_slot)
