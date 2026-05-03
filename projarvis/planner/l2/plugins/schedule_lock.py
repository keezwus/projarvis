from ..registry import register_constraint
from projarvis.planner.exceptions import TimeMappingError


@register_constraint("schedule_lock")
def schedule_lock(model, variables, params, time_mapper=None):
    for tid, tv in variables["tasks"].items():
        ls = tv["spec"].metadata.get("locked_start")
        if ls is None:
            continue
        try:
            ls_slot = time_mapper.resolve_time_ref(ls)
        except TimeMappingError:
            continue
        model.Add(tv["start"] == ls_slot)
