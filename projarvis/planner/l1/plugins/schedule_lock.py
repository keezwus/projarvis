from ..registry import register_distributor
from projarvis.planner.exceptions import TimeMappingError


@register_distributor("schedule_lock")
def schedule_lock(model, variables, params, windows, time_mappers, epoch):
    for tid, td in variables["tasks"].items():
        ls = td["spec"].l2_metadata.get("locked_start")
        if ls is None:
            continue
        try:
            ls_slot = epoch.iso_to_real_slot(ls)
        except TimeMappingError:
            continue
        ls_week = epoch.week_index(ls_slot)
        n_weeks = len(windows)
        if 0 <= ls_week < n_weeks:
            model.Add(td["vars"][ls_week] == 1)
