from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DATA_DIR


@dataclass(frozen=True)
class DemandScenario:
    name: str
    shock_multiplier: float = 1.0


def build_demand_forecast(config: dict, scenario: DemandScenario = DemandScenario("base")) -> pd.DataFrame:
    months = config["planning"]["months"]
    records: list[dict] = []
    month_index = np.arange(len(months))

    for region, params in config["regions"].items():
        base = params["base_demand"]
        growth = params["growth_rate"]
        amplitude = params["seasonal_amplitude"]
        elasticity = params["elasticity"]
        phase_shift = (sum(ord(ch) for ch in region) % 12) / 12

        seasonal_curve = 1 + amplitude * np.sin((2 * np.pi * (month_index / 12)) + (2 * np.pi * phase_shift))
        trend_curve = (1 + growth) ** month_index
        demand = base * seasonal_curve * trend_curve * scenario.shock_multiplier

        for idx, month in enumerate(months):
            records.append(
                {
                    "scenario": scenario.name,
                    "region": region,
                    "month": month,
                    "month_number": idx + 1,
                    "base_demand": round(float(demand[idx]), 2),
                    "priority": params["priority"],
                    "elasticity": elasticity,
                    "sla_floor": params["sla_floor"],
                    "unit_cost": params["unit_cost"],
                }
            )

    return pd.DataFrame.from_records(records)


def write_demand_forecast(df: pd.DataFrame, output_path: Path | None = None) -> Path:
    path = output_path or DATA_DIR / "demand_forecast.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path

