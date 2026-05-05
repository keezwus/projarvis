from dataclasses import dataclass

META_LOCKED_START = "locked_start"
META_PREVIOUS_START = "previous_start"


@dataclass
class SolverParams:
    max_time_seconds: float = 30.0
    num_workers: int = 0
    random_seed: int | None = None
    verbose: bool = False
