from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from .data import DemandScenario, build_demand_forecast
from .optimize import solve_capacity_plan


def run_scenarios(config: dict, budget_cap: float | None = None, supply_limit: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    scenarios = [
        DemandScenario(name="base", shock_multiplier=1.0),
        DemandScenario(name="shock_up_20", shock_multiplier=1.2),
        DemandScenario(name="shock_down_20", shock_multiplier=0.8),
    ]
    comparison_rows: list[dict] = []
    summary_rows: list[dict] = []
    base_plan: pd.DataFrame | None = None
    base_summary: dict | None = None

    for scenario in scenarios:
        demand_df = build_demand_forecast(config, scenario)
        artifacts = solve_capacity_plan(demand_df, config, budget_cap=budget_cap, supply_limit=supply_limit)
        monthly = artifacts.diagnostics.copy()
        monthly["scenario"] = scenario.name
        comparison_rows.extend(monthly.to_dict(orient="records"))

        summary_row = {
            **asdict(scenario),
            **artifacts.metrics,
            "average_monthly_unmet_demand": round(float(artifacts.plan.groupby("month")["unmet_demand"].sum().mean()), 2),
            "regions_below_sla": int((artifacts.plan["coverage_pct"] < artifacts.plan["sla_floor"]).sum()),
            "plan_delta_vs_base_units": 0.0,
            "cost_delta_vs_base": 0.0,
        }
        summary_rows.append(summary_row)

        if scenario.name == "base":
            base_plan = artifacts.plan[["region", "month", "deploy_units", "coverage_pct", "unmet_demand"]].copy()
            base_summary = summary_row
            continue

        if base_plan is not None:
            delta = artifacts.plan.merge(
                base_plan,
                on=["region", "month"],
                suffixes=("", "_base"),
            )
            comparison_rows.extend(
                delta.assign(
                    scenario=scenario.name,
                    month=delta["month"],
                    region=delta["region"],
                    deploy_delta=delta["deploy_units"] - delta["deploy_units_base"],
                    coverage_delta=delta["coverage_pct"] - delta["coverage_pct_base"],
                    unmet_delta=delta["unmet_demand"] - delta["unmet_demand_base"],
                    budget_utilization_pct=None,
                    supply_utilization_pct=None,
                    primary_driver="scenario_delta",
                )[
                    [
                        "scenario",
                        "month",
                        "region",
                        "deploy_delta",
                        "coverage_delta",
                        "unmet_delta",
                        "budget_utilization_pct",
                        "supply_utilization_pct",
                        "primary_driver",
                    ]
                ].to_dict(orient="records")
            )

    summary_df = pd.DataFrame(summary_rows)
    if base_summary is not None:
        summary_df["plan_delta_vs_base_units"] = summary_df["deployment_units_total"] - base_summary["deployment_units_total"]
        summary_df["cost_delta_vs_base"] = summary_df["total_cost"] - base_summary["total_cost"]

    return pd.DataFrame(comparison_rows), summary_df


def build_pareto_curve(config: dict) -> pd.DataFrame:
    base_budget = config["planning"]["baseline_budget"]
    supply_limit = config["planning"]["baseline_supply_limit"]
    multipliers = config["planning"]["pareto_budget_multipliers"]
    demand_df = build_demand_forecast(config, DemandScenario("base", 1.0))
    rows: list[dict] = []

    for multiplier in multipliers:
        budget = base_budget * multiplier
        artifacts = solve_capacity_plan(demand_df, config, budget_cap=budget, supply_limit=supply_limit)
        rows.append(
            {
                "budget_multiplier": multiplier,
                "budget_cap": budget,
                "coverage_pct": artifacts.metrics["coverage_pct"],
                "sla_achievement_rate": artifacts.metrics["sla_achievement_rate"],
                "total_cost": artifacts.metrics["total_cost"],
                "total_capex": artifacts.metrics["total_capex"],
                "total_opex": artifacts.metrics["total_opex"],
                "objective_value": artifacts.metrics["objective_value"],
                "solve_time_seconds": artifacts.metrics["solve_time_seconds"],
            }
        )

    return pd.DataFrame(rows)
