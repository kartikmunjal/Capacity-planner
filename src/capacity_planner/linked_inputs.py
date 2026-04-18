from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import LINKED_ASSET_INPUT_PATH


def resolve_linked_asset_input(explicit_path: Path | None = None) -> Path | None:
    candidate = explicit_path or LINKED_ASSET_INPUT_PATH
    return candidate if candidate.exists() else None


def apply_linked_asset_overrides(config: dict, linked_input_path: Path | None = None) -> tuple[dict, dict]:
    path = resolve_linked_asset_input(linked_input_path)
    if path is None:
        return config, {"linked_asset_input_used": False, "linked_asset_input_path": None, "regions_overridden": []}

    linked_df = pd.read_csv(path)
    updated = {
        "planning": dict(config["planning"]),
        "regions": {region: dict(values) for region, values in config["regions"].items()},
    }
    overridden_regions: list[str] = []
    for _, row in linked_df.iterrows():
        region = row["region"]
        if region not in updated["regions"]:
            continue
        updated["regions"][region]["baseline_units"] = int(row["planning_baseline_units"])
        updated["regions"][region]["unit_cost"] = float(row["recommended_unit_cost"])
        updated["regions"][region]["priority"] = round(
            float(updated["regions"][region]["priority"]) * float(row["priority_multiplier"]),
            4,
        )
        updated["regions"][region]["linked_data_confidence_score"] = round(float(row["data_confidence_score"]), 4)
        updated["regions"][region]["linked_unmatched_ratio"] = round(float(row["unmatched_ratio"]), 4)
        overridden_regions.append(region)

    return updated, {
        "linked_asset_input_used": True,
        "linked_asset_input_path": str(path),
        "regions_overridden": overridden_regions,
    }
