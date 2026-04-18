from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR, OUTPUT_DIR, load_config
from .data import DemandScenario, build_demand_forecast, write_demand_forecast
from .optimize import solve_capacity_plan
from .scenario import build_pareto_curve, run_scenarios


def run_pipeline(output_dir: Path | None = None) -> dict:
    config = load_config()
    output_root = output_dir or OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    demand_df = build_demand_forecast(config, DemandScenario(name="base", shock_multiplier=1.0))
    write_demand_forecast(demand_df, DATA_DIR / "demand_forecast.csv")

    artifacts = solve_capacity_plan(demand_df, config)
    artifacts.plan.to_csv(output_root / "optimal_plan.csv", index=False)
    artifacts.sensitivity.to_csv(output_root / "sensitivity_report.csv", index=False)

    scenario_comparison_df, scenario_summary = run_scenarios(config)
    scenario_comparison_df.to_csv(output_root / "scenario_comparison.csv", index=False)

    pareto_df = build_pareto_curve(config)
    pareto_df.to_csv(output_root / "pareto_curve.csv", index=False)

    summary = {
        "base_run": artifacts.metrics,
        "scenario_summary": scenario_summary,
        "generated_files": [
            str(DATA_DIR / "demand_forecast.csv"),
            str(output_root / "optimal_plan.csv"),
            str(output_root / "sensitivity_report.csv"),
            str(output_root / "scenario_comparison.csv"),
            str(output_root / "pareto_curve.csv"),
        ],
    }
    (output_root / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    results = run_pipeline()
    print(json.dumps(results, indent=2))

