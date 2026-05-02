from ..registry import register_distributor
from projarvis.planner.exceptions import TimeMappingError


@register_distributor("deadline")
def deadline_distributor(model, variables, params, windows, time_mappers, epoch):
    for tid, td in variables["tasks"].items():
        dl = td["spec"].l2_metadata.get("deadline")
        if dl is None:
            continue
        try:
            dl_slot = epoch.iso_to_real_slot(dl)
        except TimeMappingError:
            continue
        dl_week = epoch.week_index(dl_slot)
        n_weeks = len(windows)
        for w in range(dl_week + 1, n_weeks):
            model.Add(td["vars"][w] == 0)
