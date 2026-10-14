"""Load Python settings. Tests check shared limits against the managed firmware."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config(path=None):
    """Return a fresh settings dictionary; editing it does not edit the file."""
    selected = Path(path) if path else PROJECT_ROOT / "configs" / "bench.json"
    with selected.open(encoding="utf-8") as stream:
        return json.load(stream)
