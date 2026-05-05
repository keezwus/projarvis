from ..registry import register_distributor
from projarvis.planner.exceptions import TimeMappingError
from projarvis.planner.models import META_PREVIOUS_START


@register_distributor("schedule_stability")
def schedule_stability(model, variables, params, windows, time_mappers, epoch):
    w = params.get("default_weight", 2)
    if w <= 1:
        return

    terms = []
    for tid, td in variables["tasks"].items():
        ps = td["spec"].l2_metadata.get(META_PREVIOUS_START)
        if ps is None:
            continue
        try:
            ps_slot = epoch.iso_to_real_slot(ps)
        except TimeMappingError:
            continue
        ps_week = epoch.week_index(ps_slot)
        n_weeks = len(windows)
        if not (0 <= ps_week < n_weeks):
            continue

        effective = td["spec"].priority * w
        terms.append((1 - td["vars"][ps_week]) * effective)

    if terms:
        variables.setdefault("plugins", {})["schedule_stability"] = terms
