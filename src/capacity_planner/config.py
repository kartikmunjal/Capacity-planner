from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "constraints.yaml"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
LINKED_ASSET_INPUT_PATH = ROOT.parent / "Network-Asset-Reconciliation" / "outputs" / "capacity_planner_inputs.csv"


def load_config(config_path: Path | None = None) -> dict:
    path = config_path or CONFIG_PATH
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
