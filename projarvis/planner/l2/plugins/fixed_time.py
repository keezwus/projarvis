from ..registry import register_constraint
from projarvis.planner.exceptions import TimeMappingError


@register_constraint("fixed_time")
def fixed_time(model, variables, params, time_mapper=None):
    for tid, tv in variables["tasks"].items():
        ft = tv["spec"].metadata.get("fixed_time")
        if ft is None:
            continue
        try:
            ft_start = time_mapper.resolve_time_ref(ft)
        except TimeMappingError:
            continue
        ft_end = ft_start + tv["duration"]
        model.Add(tv["start"] == ft_start)
        model.Add(tv["end"] == ft_end)
