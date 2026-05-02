from __future__ import annotations

from ortools.sat.python import cp_model

from projarvis.planner.time_epoch import TimeEpoch, SLOTS_PER_WEEK
from projarvis.planner.models import SolverParams
from projarvis.planner.exceptions import TimeMappingError
from projarvis.planner.l2.models import TimeSpec, TaskSpec as L2TaskSpec
from projarvis.planner.l2.time_mapper import TimeMapper
from projarvis.planner.l2.engine import SchedulingEngine

from .models import (
    LongHorizonSpec,
    L1TaskSpec,
    ConstraintSpec,
    HorizonWindow,
    CapacityReport,
    ConflictReport,
    WeekSolution,
    MultiWeekSolution,
)


class L1Engine:
    """Multi-week scheduling engine.

    Call contract:
        engine = L1Engine(spec)
        engine.partition()
        assignments, cap_report = engine.allocate(tasks, constraints)
        result = engine.schedule(params, constraints)
    """

    def __init__(self, spec: LongHorizonSpec) -> None:
        self._spec = spec
        self._epoch = TimeEpoch(spec.horizon_start)
        self._windows: list[HorizonWindow] = []
        self._assignments: dict[int, list[L1TaskSpec]] = {}
        self._capacity_report: CapacityReport | None = None
        self._allocated = False

    # ── public API ──────────────────────────────────────────────

    def partition(self) -> list[HorizonWindow]:
        if self._windows:
            return list(self._windows)

        windows: list[HorizonWindow] = []
        for w in range(self._spec.horizon_weeks):
            start_iso = self._epoch.week_start_iso(w)
            week_overrides = self._filter_overrides_for_week(w)
            ts = TimeSpec(
                horizon_start=start_iso,
                horizon_days=7,
                weekly_base=self._spec.weekly_available,
                overrides=week_overrides,
            )
            tm = TimeMapper(ts, self._epoch)
            windows.append(HorizonWindow(
                week_index=w,
                start_iso=start_iso,
                available_slots=tm.total_slots,
            ))

        self._windows = windows
        return list(windows)

    def allocate(
        self,
        tasks: list[L1TaskSpec],
        constraints: list[ConstraintSpec] | None = None,
    ) -> tuple[dict[int, list[L1TaskSpec]], CapacityReport]:
        if not self._windows:
            self.partition()

        if not tasks:
            self._assignments = {}
            self._capacity_report = CapacityReport(status="OK")
            self._allocated = True
            return {}, self._capacity_report

        model = cp_model.CpModel()

        # ── variables: y[t][w] ∈ {0, 1} ─────────────────────────
        n_weeks = len(self._windows)
        y: dict[str, list[cp_model.IntVar]] = {}
        for t in tasks:
            y[t.id] = []
            for w in range(n_weeks):
                y[t.id].append(model.NewBoolVar(f"y_{t.id}_w{w}"))

        # ── one-hot: each task exactly one week ──────────────────
        for t in tasks:
            model.Add(sum(y[t.id][w] for w in range(n_weeks)) == 1)

        # ── capacity ─────────────────────────────────────────────
        for w, window in enumerate(self._windows):
            model.Add(
                sum(y[t.id][w] * t.total_duration for t in tasks)
                <= window.available_slots
            )

        # ── build time_mappers & variables ───────────────────────
        time_mappers = []
        for w in range(n_weeks):
            week_overrides = self._filter_overrides_for_week(w)
            ts = TimeSpec(
                horizon_start=self._windows[w].start_iso,
                horizon_days=7,
                weekly_base=self._spec.weekly_available,
                overrides=week_overrides,
            )
            time_mappers.append(TimeMapper(ts, self._epoch))

        task_lookup = {t.id: t for t in tasks}
        variables: dict = {
            "tasks": {
                tid: {
                    "vars": y[tid],
                    "duration": t.total_duration,
                    "spec": t,
                }
                for tid, t in task_lookup.items()
            },
            "plugins": {},
        }

        # ── plugin dispatch ──────────────────────────────────────
        from .registry import discover_distributors, get_distributor
        discover_distributors()
        for cs in (constraints or []):
            plugin = get_distributor(cs.type)
            if plugin is not None:
                plugin(
                    model, variables, cs.params,
                    self._windows, time_mappers, self._epoch,
                )

        # ── objective ────────────────────────────────────────────
        terms: list[cp_model.LinearExpr] = []
        covered_ids: set[str] = set()
        for pdata in variables["plugins"].values():
            if isinstance(pdata, dict):
                tt = pdata.get("task_terms", {})
                for tid, tterms in tt.items():
                    terms.extend(tterms)
                    covered_ids.add(tid)
        for t in tasks:
            if t.id not in covered_ids:
                for w in range(n_weeks):
                    terms.append(y[t.id][w] * w * t.priority)
        for pdata in variables["plugins"].values():
            if isinstance(pdata, list):
                terms.extend(pdata)
            elif isinstance(pdata, dict):
                terms.extend(pdata.get("objective_terms", []))
        model.Minimize(sum(terms))

        # ── solve ────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)

        if status == cp_model.INFEASIBLE:
            self._assignments = {}
            self._capacity_report = CapacityReport(status="OVERSATURATED")
            self._allocated = True
            return {}, self._capacity_report

        assignments: dict[int, list[L1TaskSpec]] = {}
        for w in range(len(self._windows)):
            assignments[w] = []

        for t in tasks:
            for w in range(len(self._windows)):
                if solver.Value(y[t.id][w]) == 1:
                    assignments[w].append(t)

        self._assignments = assignments
        self._capacity_report = CapacityReport(status="OK")
        self._allocated = True
        return assignments, self._capacity_report

    def schedule(
        self,
        params: SolverParams | None = None,
        constraints: list[ConstraintSpec] | None = None,
    ) -> MultiWeekSolution:
        if not self._allocated:
            raise RuntimeError("Must call allocate() before schedule()")

        weekly_solutions: list[WeekSolution] = []
        conflict_reports: list[ConflictReport] = []
        all_ok = True
        any_infeasible = False

        for window in self._windows:
            week_tasks = self._assignments.get(window.week_index, [])
            if not week_tasks:
                weekly_solutions.append(WeekSolution(
                    week_index=window.week_index,
                    start_iso=window.start_iso,
                    solution=None,
                ))
                continue

            week_overrides = self._filter_overrides_for_week(window.week_index)
            ts = TimeSpec(
                horizon_start=window.start_iso,
                horizon_days=7,
                weekly_base=self._spec.weekly_available,
                overrides=week_overrides,
            )
            tm = TimeMapper(ts, self._epoch)
            l2_tasks = [
                L2TaskSpec(
                    id=t.id,
                    duration=t.total_duration,
                    metadata=t.l2_metadata,
                )
                for t in week_tasks
            ]

            engine = SchedulingEngine(tm)
            engine.hydrate(l2_tasks)
            if constraints:
                engine.apply_constraints(constraints)
            engine.set_objective()
            l2_solution = engine.solve(params)

            weekly_solutions.append(WeekSolution(
                week_index=window.week_index,
                start_iso=window.start_iso,
                solution=l2_solution,
            ))

            if l2_solution.status == "INFEASIBLE":
                any_infeasible = True
                conflict_reports.append(ConflictReport(
                    week_index=window.week_index,
                    conflicts=l2_solution.conflicts,
                    suggestion=(
                        f"Redistribute tasks out of week {window.week_index} "
                        f"or increase weekly availability."
                    ),
                ))
            elif l2_solution.status in ("OPTIMAL", "FEASIBLE"):
                pass  # OK
            else:
                any_infeasible = True

        # ── overall status ───────────────────────────────────────
        if not any_infeasible:
            overall = "OK"
        else:
            non_empty = [ws for ws in weekly_solutions if ws.solution is not None]
            if non_empty and all(ws.solution.status == "INFEASIBLE" for ws in non_empty):
                overall = "INFEASIBLE"
            else:
                overall = "PARTIAL"

        # If allocate returned empty assignments, all weeks are
        # skipped, no INFEASIBLE flag was raised → INFEASIBLE
        if not self._assignments:
            overall = "INFEASIBLE"

        return MultiWeekSolution(
            status=overall,
            weekly_solutions=weekly_solutions,
            capacity_report=self._capacity_report,
            conflict_reports=conflict_reports,
        )

    # ── internal ────────────────────────────────────────────────

    def _filter_overrides_for_week(self, week_index: int) -> list[dict]:
        week_start = self._epoch.week_start_slot(week_index)
        week_end = week_start + SLOTS_PER_WEEK

        filtered: list[dict] = []
        for ov in self._spec.overrides:
            try:
                ov_slot = self._epoch.iso_to_real_slot(ov["date"])
            except TimeMappingError:
                continue
            if week_start <= ov_slot < week_end:
                filtered.append(ov)
        return filtered
