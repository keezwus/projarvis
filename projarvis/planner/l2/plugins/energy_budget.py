from ..registry import register_constraint


@register_constraint("energy_budget")
def energy_budget(model, variables, params, time_mapper=None):
    tasks = variables["tasks"]

    # ── 1. Build day_ranges: {day_name: [lo, hi)} ──────────────────
    day_ranges = {}
    for comp in range(time_mapper.total_slots):
        day = time_mapper.day_name(comp)
        if day not in day_ranges:
            day_ranges[day] = [comp, comp]
        day_ranges[day][1] = comp + 1

    if not day_ranges:
        return

    days = list(day_ranges.keys())

    # ── 2. Read params ─────────────────────────────────────────────
    fb_default = params.get("focus_budget_per_day", 0)
    fb_overrides = params.get("focus_budget_overrides", {})
    eb_default = params.get("exercise_budget_per_day", 0)
    eb_overrides = params.get("exercise_budget_overrides", {})

    ft_default = params.get("focus_target_per_day", 0)
    et_default = params.get("exercise_target_per_day", 0)

    fw = params.get("focus_shortfall_weight", 0)
    ew = params.get("exercise_shortfall_weight", 0)

    # ── 3. Pre-compute consum values per task ──────────────────────
    focus_consum = {}  # {tid: int}
    exercise_consum = {}
    for tid, tv in tasks.items():
        fm = tv["spec"].metadata.get("focus_multiplier", 0)
        if fm:
            focus_consum[tid] = int(tv["duration"] * fm)
        em = tv["spec"].metadata.get("exercise_multiplier", 0)
        if em:
            exercise_consum[tid] = int(tv["duration"] * em)

    # ── 4. Create is_on_day and contrib variables ──────────────────
    is_on = {}
    f_contrib = {}
    e_contrib = {}

    for tid in set(focus_consum) | set(exercise_consum):
        tv = tasks[tid]
        fc = focus_consum.get(tid, 0)
        ec = exercise_consum.get(tid, 0)

        is_on[tid] = {}
        if fc > 0:
            f_contrib[tid] = {}
        if ec > 0:
            e_contrib[tid] = {}

        ion_vars = []
        for day, (lo, hi) in day_ranges.items():
            ion = model.NewBoolVar(f"eb_on_{tid}_{day}")
            is_on[tid][day] = ion
            ion_vars.append(ion)

            model.Add(tv["start"] >= lo).OnlyEnforceIf(ion)
            model.Add(tv["start"] < hi).OnlyEnforceIf(ion)

            if fc > 0:
                v = model.NewIntVar(0, fc, f"eb_fc_{tid}_{day}")
                model.Add(v == fc).OnlyEnforceIf(ion)
                model.Add(v == 0).OnlyEnforceIf(ion.Not())
                f_contrib[tid][day] = v

            if ec > 0:
                v = model.NewIntVar(0, ec, f"eb_ec_{tid}_{day}")
                model.Add(v == ec).OnlyEnforceIf(ion)
                model.Add(v == 0).OnlyEnforceIf(ion.Not())
                e_contrib[tid][day] = v

        model.Add(sum(ion_vars) == 1)

    # ── 5. Hard constraints: daily budget caps ─────────────────────
    for day in days:
        fb = fb_overrides.get(day, fb_default)
        if fb > 0:
            terms = [f_contrib[tid][day] for tid in f_contrib if day in f_contrib[tid]]
            if terms:
                model.Add(sum(terms) <= fb)

        eb = eb_overrides.get(day, eb_default)
        if eb > 0:
            terms = [e_contrib[tid][day] for tid in e_contrib if day in e_contrib[tid]]
            if terms:
                model.Add(sum(terms) <= eb)

    # ── 6. Soft constraints: daily shortfall ───────────────────────
    shortfall_terms = []

    for day in days:
        fb = fb_overrides.get(day, fb_default)
        ft = ft_default
        if fw > 0 and ft > 0 and fb > 0:
            terms = [f_contrib[tid][day] for tid in f_contrib if day in f_contrib[tid]]
            actual = sum(terms) if terms else 0
            ssf = model.NewIntVar(0, ft, f"eb_fsf_{day}")
            model.Add(ssf >= ft - actual)
            shortfall_terms.append(ssf * fw)

        eb = eb_overrides.get(day, eb_default)
        et = et_default
        if ew > 0 and et > 0 and eb > 0:
            terms = [e_contrib[tid][day] for tid in e_contrib if day in e_contrib[tid]]
            actual = sum(terms) if terms else 0
            ssf = model.NewIntVar(0, et, f"eb_esf_{day}")
            model.Add(ssf >= et - actual)
            shortfall_terms.append(ssf * ew)

    # ── 7. Write objective terms ───────────────────────────────────
    if shortfall_terms:
        variables["plugins"]["energy_budget"] = shortfall_terms
