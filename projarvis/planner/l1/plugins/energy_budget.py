from ..registry import register_distributor


@register_distributor("energy_budget")
def energy_budget_distributor(model, variables, params, windows, time_mappers, epoch):
    task_data = variables.get("tasks", {})
    n_weeks = len(windows)
    if not task_data or n_weeks == 0:
        return

    # ── 1. count working days per week via TimeMapper ────────────
    working_days_per_week = []
    for tm in time_mappers:
        days = set()
        for comp in range(tm.total_slots):
            days.add(tm.day_name(comp))
        working_days_per_week.append(len(days))

    # ── 2. pre-compute consum values per task ────────────────────
    focus_consum = {}
    exercise_consum = {}
    for tid, td in task_data.items():
        spec = td["spec"]
        fm = spec.l2_metadata.get("focus_multiplier", 0)
        if fm:
            focus_consum[tid] = int(td["duration"] * fm)
        em = spec.l2_metadata.get("exercise_multiplier", 0)
        if em:
            exercise_consum[tid] = int(td["duration"] * em)

    # ── 3. hard constraints: weekly budget caps ──────────────────
    fbp = params.get("focus_budget_per_day", 0)
    ebp = params.get("exercise_budget_per_day", 0)

    for w in range(n_weeks):
        wd = working_days_per_week[w]

        fb = fbp * wd
        if fb > 0 and focus_consum:
            terms = [
                td["vars"][w] * focus_consum[tid]
                for tid, td in task_data.items() if tid in focus_consum
            ]
            if terms:
                model.Add(sum(terms) <= fb)

        eb = ebp * wd
        if eb > 0 and exercise_consum:
            terms = [
                td["vars"][w] * exercise_consum[tid]
                for tid, td in task_data.items() if tid in exercise_consum
            ]
            if terms:
                model.Add(sum(terms) <= eb)

    # ── 4. soft targets: shortfall penalty (lighter than L2) ─────
    ft = params.get("focus_target_per_day", 0)
    et = params.get("exercise_target_per_day", 0)
    fw = params.get("focus_shortfall_weight", 0)
    ew = params.get("exercise_shortfall_weight", 0)

    fw_l1 = max(1, fw // 3) if fw > 0 else 0
    ew_l1 = max(1, ew // 3) if ew > 0 else 0

    shortfall_terms = []

    for w in range(n_weeks):
        wd = working_days_per_week[w]
        fb = fbp * wd
        eb = ebp * wd
        ftw = ft * wd
        etw = et * wd

        if fw_l1 > 0 and ft > 0 and fb > 0 and focus_consum:
            actual = sum(
                td["vars"][w] * focus_consum[tid]
                for tid, td in task_data.items() if tid in focus_consum
            )
            ssf = model.NewIntVar(0, ftw, f"eb_l1_fsf_w{w}")
            model.Add(ssf >= ftw - actual)
            shortfall_terms.append(ssf * fw_l1)

        if ew_l1 > 0 and et > 0 and eb > 0 and exercise_consum:
            actual = sum(
                td["vars"][w] * exercise_consum[tid]
                for tid, td in task_data.items() if tid in exercise_consum
            )
            ssf = model.NewIntVar(0, etw, f"eb_l1_esf_w{w}")
            model.Add(ssf >= etw - actual)
            shortfall_terms.append(ssf * ew_l1)

    if shortfall_terms:
        variables.setdefault("plugins", {})["energy_budget"] = shortfall_terms
