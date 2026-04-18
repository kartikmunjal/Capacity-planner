from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from .data import DemandScenario, build_demand_forecast
from .optimize import solve_capacity_plan


def run_scenarios(config: dict, budget_cap: float | None = None, supply_limit: float | None = None) -> tuple[pd.DataFrame, list[dict]]:
    scenarios = [
        DemandScenario(name="base", shock_multiplier=1.0),
        DemandScenario(name="shock_up_20", shock_multiplier=1.2),
        DemandScenario(name="shock_down_20", shock_multiplier=0.8),
    ]
    scenario_rows: list[dict] = []
    summaries: list[dict] = []
    base_total_units = 0.0

    for scenario in scenarios:
        demand_df = build_demand_forecast(config, scenario)
        artifacts = solve_capacity_plan(demand_df, config, budget_cap=budget_cap, supply_limit=supply_limit)
        total_units = float(artifacts.plan["deploy_units"].sum())
        grouped = artifacts.plan.groupby("month", as_index=False).agg(
            deploy_units=("deploy_units", "sum"),
            monthly_spend=("monthly_spend", "sum"),
            unmet_demand=("unmet_demand", "sum"),
            average_coverage=("coverage_pct", "mean"),
        )
        for row in grouped.to_dict(orient="records"):
            row["scenario"] = scenario.name
            scenario_rows.append(row)

        summaries.append(
            {
                **asdict(scenario),
                **artifacts.metrics,
                "total_deploy_units": round(total_units, 4),
                "plan_delta_vs_base_units": 0.0,
            }
        )
        if scenario.name == "base":
            base_total_units = total_units

    summary_df = pd.DataFrame(summaries)
    summary_df["plan_delta_vs_base_units"] = summary_df["total_deploy_units"] - base_total_units
    return pd.DataFrame(scenario_rows), summary_df.to_dict(orient="records")


def build_pareto_curve(config: dict) -> pd.DataFrame:
    base_budget = config["planning"]["baseline_budget"]
    supply_limit = config["planning"]["baseline_supply_limit"]
    multipliers = config["planning"]["pareto_budget_multipliers"]
    rows: list[dict] = []

    demand_df = build_demand_forecast(config, DemandScenario("base", 1.0))
    for multiplier in multipliers:
        budget = base_budget * multiplier
        artifacts = solve_capacity_plan(demand_df, config, budget_cap=budget, supply_limit=supply_limit)
        rows.append(
            {
                "budget_multiplier": multiplier,
                "budget_cap": budget,
                "total_spend": artifacts.metrics["total_spend"],
                "coverage_pct": artifacts.metrics["coverage_pct"],
                "sla_achievement_rate": artifacts.metrics["sla_achievement_rate"],
                "objective_value": artifacts.metrics["objective_value"],
                "solve_time_seconds": artifacts.metrics["solve_time_seconds"],
            }
        )

    return pd.DataFrame(rows)
