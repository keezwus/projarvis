from ..registry import register_constraint
from projarvis.planner.exceptions import TimeMappingError
from projarvis.planner.models import META_PREVIOUS_START


@register_constraint("schedule_stability")
def schedule_stability(model, variables, params, time_mapper=None):
    w = params.get("default_weight", 5)
    if w <= 1:
        return

    domain_max = time_mapper.total_slots
    terms = []

    for tid, tv in variables["tasks"].items():
        ps = tv["spec"].metadata.get(META_PREVIOUS_START)
        if ps is None:
            continue
        try:
            ps_slot = time_mapper.resolve_time_ref(ps)
        except TimeMappingError:
            continue

        effective = tv["spec"].metadata.get("stability_weight", w)
        if effective <= 1:
            continue

        dp = model.NewIntVar(0, domain_max, f"ss_dp_{tid}")
        dm = model.NewIntVar(0, domain_max, f"ss_dm_{tid}")
        model.Add(tv["start"] - ps_slot == dp - dm)
        terms.append((dp + dm) * effective)

    if terms:
        variables.setdefault("plugins", {})["schedule_stability"] = terms
