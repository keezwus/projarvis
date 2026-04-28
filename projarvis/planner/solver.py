from ortools.sat.python import cp_model
from projarvis.planner.models import SolverParams


def create_solver(params: SolverParams | None = None) -> cp_model.CpSolver:
    """Build a configured CpSolver from SolverParams."""
    p = params or SolverParams()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = p.max_time_seconds
    solver.parameters.num_workers = p.num_workers
    if p.random_seed is not None:
        solver.parameters.random_seed = p.random_seed
    if p.verbose:
        solver.parameters.log_search_progress = True
    return solver
