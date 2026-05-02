from ..registry import register_distributor
from projarvis.planner.exceptions import TimeMappingError


@register_distributor("fixed_time")
def fixed_time_distributor(model, variables, params, windows, time_mappers, epoch):
    for tid, td in variables["tasks"].items():
        ft = td["spec"].l2_metadata.get("fixed_time")
        if ft is None:
            continue
        try:
            ft_slot = epoch.iso_to_real_slot(ft)
        except TimeMappingError:
            continue
        ft_week = epoch.week_index(ft_slot)
        n_weeks = len(windows)
        if 0 <= ft_week < n_weeks:
            model.Add(td["vars"][ft_week] == 1)
