from ..registry import register_distributor
from projarvis.planner.exceptions import TimeMappingError


@register_distributor("task_distribution")
def task_distribution(model, variables, params, windows, time_mappers, epoch):
    mode = params.get("mode", "earliest_bias")
    td = variables["tasks"]

    dispatch = {
        "earliest_bias":     _terms_earliest,
        "even":              _terms_even,
        "front_load":        _terms_front_load,
        "ramp_up":           _terms_ramp_up,
        "deadline_driven":   _terms_deadline_driven,
    }
    fn = dispatch.get(mode)
    if fn is None:
        return

    result = fn(td, model, params, windows, time_mappers, epoch)
    if result is not None:
        variables.setdefault("plugins", {})["task_distribution"] = result


def _terms_earliest(td, model, params, windows, time_mappers, epoch):
    return None


def _terms_even(td, model, params, windows, time_mappers, epoch):
    task_ids = params.get("task_ids", [])
    valid_ids = [tid for tid in task_ids if tid in td]
    if not valid_ids:
        return None

    n_weeks = len(windows)
    total_dur = sum(td[tid]["duration"] for tid in valid_ids)
    avg = total_dur // n_weeks

    task_terms = {
        tid: [td[tid]["vars"][w] * 0 for w in range(n_weeks)]
        for tid in valid_ids
    }

    objective_terms = []
    weight = params.get("weight", 1)
    for w in range(n_weeks):
        actual = sum(td[tid]["vars"][w] * td[tid]["duration"] for tid in valid_ids)
        excess = model.NewIntVar(0, total_dur, f"even_excess_w{w}")
        model.Add(excess >= actual - avg)
        objective_terms.append(excess * weight)

    return {"task_terms": task_terms, "objective_terms": objective_terms}


def _terms_front_load(td, model, params, windows, time_mappers, epoch):
    n_weeks = len(windows)
    task_terms = {}
    for tid in td:
        task_terms[tid] = [
            td[tid]["vars"][w] * (w * w) * td[tid]["spec"].priority
            for w in range(n_weeks)
        ]
    return {"task_terms": task_terms}


def _terms_ramp_up(td, model, params, windows, time_mappers, epoch):
    n_weeks = len(windows)
    task_terms = {}
    for tid in td:
        dl = td[tid]["spec"].l2_metadata.get("deadline")
        if dl is None:
            continue
        task_terms[tid] = [
            td[tid]["vars"][w] * (n_weeks - 1 - w) * td[tid]["spec"].priority
            for w in range(n_weeks)
        ]
    return {"task_terms": task_terms} if task_terms else None


def _terms_deadline_driven(td, model, params, windows, time_mappers, epoch):
    n_weeks = len(windows)
    task_terms = {}
    for tid in td:
        dl = td[tid]["spec"].l2_metadata.get("deadline")
        if dl is None:
            continue
        try:
            dl_week = epoch.week_index(epoch.iso_to_real_slot(dl))
        except TimeMappingError:
            continue
        task_terms[tid] = [
            td[tid]["vars"][w] * abs(w - dl_week) * td[tid]["spec"].priority
            for w in range(n_weeks)
        ]
    return {"task_terms": task_terms} if task_terms else None
