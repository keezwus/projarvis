import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text())
