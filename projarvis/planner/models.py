from dataclasses import dataclass


@dataclass
class SolverParams:
    max_time_seconds: float = 30.0
    num_workers: int = 0
    random_seed: int | None = None
    verbose: bool = False
