from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from .config import AppConfig
from .models import PlanState


def this_monday() -> datetime:
    now = datetime.now()
    days_since_monday = now.weekday()
    return now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=days_since_monday
    )


def _this_monday_iso() -> str:
    return this_monday().isoformat()


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def init_git_repo(state_dir: str) -> None:
    path = Path(state_dir)
    path.mkdir(parents=True, exist_ok=True)

    if not (path / ".git").exists():
        _git(str(path), "init")
        _git(str(path), "config", "init.defaultBranch", "main")

    _git(str(path), "config", "user.name", "projarvis")
    _git(str(path), "config", "user.email", "projarvis@local")


def load(config: AppConfig) -> PlanState:
    state_dir = Path(config.state_dir)
    state_file = state_dir / "state.json"

    if not state_file.exists():
        return PlanState(
            horizon_start=_this_monday_iso(),
            horizon_weeks=config.horizon.weeks,
            weekly_available=dict(config.availability),
            random_seed=config.engine.random_seed,
        )

    raw = state_file.read_text(encoding="utf-8")
    return PlanState.model_validate_json(raw)


def save(config: AppConfig, state: PlanState) -> None:
    state_dir = Path(config.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"

    init_git_repo(str(state_dir))

    state.revision += 1

    content = state.model_dump_json(indent=2)
    _atomic_write(state_file, content)

    _git(str(state_dir), "add", "state.json")
    result = _git(str(state_dir), "commit", "-m", "save")

    if result.returncode != 0:
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            return
        raise RuntimeError(
            f"git commit failed: {result.stderr.strip() or result.stdout.strip()}"
        )


def git_log(config: AppConfig, n: int = 20) -> str:
    state_dir = str(Path(config.state_dir))
    result = _git(state_dir, "log", f"-{n}", "--oneline")
    return result.stdout.strip()


def git_diff(config: AppConfig, ref1: str, ref2: str) -> str:
    state_dir = str(Path(config.state_dir))
    result = _git(state_dir, "diff", f"{ref1}..{ref2}", "--", "state.json")
    return result.stdout.strip()


def checkout_whatif(config: AppConfig) -> None:
    state_dir = str(Path(config.state_dir))
    result = _git(state_dir, "rev-parse", "--verify", "whatif")
    if result.returncode == 0:
        _git(state_dir, "checkout", "whatif")
    else:
        _git(state_dir, "checkout", "-B", "whatif", "main")


def checkout_main(config: AppConfig) -> None:
    state_dir = str(Path(config.state_dir))
    _git(state_dir, "checkout", "main")


def merge_whatif(config: AppConfig) -> None:
    state_dir = str(Path(config.state_dir))
    _git(state_dir, "checkout", "main")
    result = _git(state_dir, "merge", "whatif")
    if result.returncode != 0:
        _git(state_dir, "merge", "--abort")
        raise RuntimeError(
            f"Merge whatif failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    _git(state_dir, "branch", "-D", "whatif")


def diff_main_whatif(config: AppConfig) -> str:
    state_dir = str(Path(config.state_dir))
    result = _git(state_dir, "diff", "main..whatif", "--", "state.json")
    return result.stdout.strip()


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
