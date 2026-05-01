from projarvis.planner.exceptions import TimeMappingError
from ..registry import register_constraint


def _resolve_or_nearest(tm, iso_string):
    """Convert ISO 8601 to compressed slot, scanning backward if outside availability."""
    real_slot = tm._epoch.iso_to_real_slot(iso_string)
    offset = real_slot - tm._start_slot
    for prev in range(offset, -1, -1):
        comp = tm._offset_to_comp.get(prev)
        if comp is not None:
            return comp
    raise TimeMappingError(
        f"Time {iso_string!r} is before all available slots"
    )


@register_constraint("deadline")
def deadline(model, variables, params, time_mapper=None):
    for tid, tv in variables["tasks"].items():
        dl = tv["spec"].metadata.get("deadline")
        if dl is None:
            continue
        dl_slot = _resolve_or_nearest(time_mapper, dl)
        model.Add(tv["end"] <= dl_slot)
