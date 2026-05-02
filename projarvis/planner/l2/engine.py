from __future__ import annotations

from ortools.sat.python import cp_model

from .time_mapper import TimeMapper
from .models import TaskSpec, ConstraintSpec, TaskResult, Solution
from projarvis.planner.models import SolverParams
from projarvis.planner.exceptions import ValidationError, TimeMappingError
from projarvis.planner.time_epoch import is_iso_datetime
from .registry import get_plugin, discover_plugins
from .solver import create_solver


class SchedulingEngine:
    """L2 single-week scheduling engine.

    Call contract (documented, not enforced by types):
        tm = TimeMapper(time_spec)
        engine = SchedulingEngine(tm)
        engine.hydrate(tasks)
        engine.apply_constraints(constraints)
        engine.set_objective()
        solution = engine.solve(params)
    """

    def __init__(self, time_mapper: TimeMapper):
        self.time_mapper = time_mapper
        self.model = cp_model.CpModel()
        self.variables: dict = {"plugins": {}}
        self._objective_terms: list = []
        self._hydrated = False
        self._constraints_applied = False
        self._objective_set = False

    # ── public API ──────────────────────────────────────────────

    def add_objective_term(self, expr) -> None:
        """Plugins call this to append to the objective function pool."""
        self._objective_terms.append(expr)

    def hydrate(self, tasks: list[TaskSpec]) -> None:
        if self._hydrated:
            raise RuntimeError("hydrate() can only be called once")
        if not tasks:
            raise ValidationError("At least one task required")

        domain_max = self.time_mapper.total_slots
        if domain_max == 0:
            raise ValidationError("No available time slots — cannot schedule any tasks")

        seen_ids: set[str] = set()
        for t in tasks:
            if t.id in seen_ids:
                raise ValidationError(f"Duplicate task id: {t.id!r}")
            seen_ids.add(t.id)
            if t.duration < 1:
                raise ValidationError(
                    f"Task {t.id!r} duration must be >= 1, got {t.duration}"
                )

        task_vars: dict = {}
        intervals: list[cp_model.IntervalVar] = []

        for t in tasks:
            start = self.model.NewIntVar(0, domain_max - 1, f"start_{t.id}")
            end = self.model.NewIntVar(1, domain_max, f"end_{t.id}")
            self.model.Add(end - start == t.duration)
            interval = self.model.NewIntervalVar(
                start, t.duration, end, f"interval_{t.id}"
            )
            task_vars[t.id] = {
                "start": start,
                "end": end,
                "duration": t.duration,
                "interval": interval,
                "spec": t,
            }
            intervals.append(interval)

        # Block boundary constraints: prevent tasks spanning across gaps
        for b in self.time_mapper.block_boundaries:
            for tv in task_vars.values():
                bv = self.model.NewBoolVar(
                    f"boundary_b{b}_{tv['spec'].id}"
                )
                self.model.Add(tv["end"] <= b).OnlyEnforceIf(bv)
                self.model.Add(tv["start"] >= b).OnlyEnforceIf(bv.Not())

        # Global NoOverlap
        self.model.AddNoOverlap(intervals)

        self.variables["tasks"] = task_vars
        self._hydrated = True

    def apply_constraints(self, constraints: list[ConstraintSpec]) -> None:
        if not self._hydrated:
            raise RuntimeError("Must call hydrate() before apply_constraints()")
        if self._constraints_applied:
            raise RuntimeError("apply_constraints() can only be called once")

        discover_plugins()

        for cs in constraints:
            plugin = get_plugin(cs.type)
            if plugin is None:
                continue

            converted_params = _blind_scan_params(cs.params, self.time_mapper)

            plugin(
                self.model,
                self.variables,
                converted_params,
                self.time_mapper,
            )

        self._constraints_applied = True

    def set_objective(self) -> None:
        if not self._hydrated:
            raise RuntimeError("Must call hydrate() before set_objective()")
        if self._objective_set:
            raise RuntimeError("set_objective() can only be called once")

        task_starts = [tv["start"] for tv in self.variables["tasks"].values()]
        objective = sum(task_starts)
        for term in self._objective_terms:
            objective += term
        for plugin_terms in self.variables.get("plugins", {}).values():
            if isinstance(plugin_terms, list):
                for term in plugin_terms:
                    objective += term
        self.model.Minimize(objective)
        self._objective_set = True

    def solve(self, params: SolverParams | None = None) -> Solution:
        if not self._objective_set:
            raise RuntimeError("Must call set_objective() before solve()")

        solver = create_solver(params)
        status = solver.Solve(self.model)
        return self._extract(solver, status)

    # ── internal ────────────────────────────────────────────────

    def _extract(self, solver: cp_model.CpSolver, status: int) -> Solution:
        status_map = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "INFEASIBLE",
        }
        status_str = status_map.get(status, "INFEASIBLE")
        solve_time_ms = solver.WallTime() * 1000.0

        if status_str == "INFEASIBLE":
            conflicts: list[str] = []
            try:
                inf = solver.SufficientAssumptionsForInfeasibility()
                if inf:
                    conflicts = [str(x) for x in inf]
            except Exception:
                pass
            return Solution(
                status=status_str,
                solve_time_ms=solve_time_ms,
                objective_value=None,
                tasks={},
                conflicts=conflicts,
            )

        objective_value = solver.ObjectiveValue()
        task_results: dict[str, TaskResult] = {}
        for tid, tv in self.variables["tasks"].items():
            c_start = solver.Value(tv["start"])
            c_end = solver.Value(tv["end"])
            r_start = self.time_mapper.compressed_to_real(c_start)
            r_end = self.time_mapper.compressed_to_real(c_end)
            task_results[tid] = TaskResult(
                id=tid,
                start_slot=r_start,
                end_slot=r_end,
                duration_slots=tv["duration"],
            )

        return Solution(
            status=status_str,
            solve_time_ms=solve_time_ms,
            objective_value=objective_value,
            tasks=task_results,
        )


# ── module-level helpers ────────────────────────────────────────

def _blind_scan_params(params: dict, time_mapper: TimeMapper) -> dict:
    """Deep-scan *params* for ISO 8601 strings and convert to compressed slots."""
    return _blind_scan_value(params, time_mapper)


def _blind_scan_value(value, time_mapper: TimeMapper):
    if is_iso_datetime(value):
        try:
            return time_mapper.resolve_time_ref(value)
        except TimeMappingError:
            pass
    if isinstance(value, dict):
        return {k: _blind_scan_value(v, time_mapper) for k, v in value.items()}
    if isinstance(value, list):
        return [_blind_scan_value(v, time_mapper) for v in value]
    return value
