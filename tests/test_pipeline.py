import pandas as pd

from pathlib import Path

from capacity_planner.config import load_config
from capacity_planner.data import DemandScenario, build_demand_forecast
from capacity_planner.linked_inputs import apply_linked_asset_overrides
from capacity_planner.optimize import solve_capacity_plan
from capacity_planner.pipeline import run_pipeline


def test_forecast_shape():
    config = load_config()
    forecast = build_demand_forecast(config, DemandScenario(name="base"))
    assert forecast.shape[0] == 60
    assert sorted(forecast["region"].unique().tolist()) == sorted(config["regions"].keys())


def test_budget_and_supply_constraints_hold():
    config = load_config()
    forecast = build_demand_forecast(config, DemandScenario(name="base"))
    artifacts = solve_capacity_plan(forecast, config)
    budget_cap = config["planning"]["baseline_budget"]
    supply_limit = config["planning"]["baseline_supply_limit"]

    monthly = artifacts.plan.groupby("month", as_index=False).agg(
        capex_spend=("capex_spend", "sum"),
        deploy_units=("deploy_units", "sum"),
    )
    assert (monthly["capex_spend"] <= budget_cap + 1e-6).all()
    assert (monthly["deploy_units"] <= supply_limit + 1e-6).all()


def test_higher_budget_does_not_reduce_coverage():
    config = load_config()
    forecast = build_demand_forecast(config, DemandScenario(name="base"))
    low_budget = solve_capacity_plan(forecast, config, budget_cap=config["planning"]["baseline_budget"] * 0.8)
    high_budget = solve_capacity_plan(forecast, config, budget_cap=config["planning"]["baseline_budget"] * 1.2)
    assert high_budget.metrics["coverage_pct"] >= low_budget.metrics["coverage_pct"]


def test_pipeline_writes_new_outputs(tmp_path: Path):
    summary = run_pipeline(output_dir=tmp_path)
    expected = {
        "optimal_plan.csv",
        "sensitivity_report.csv",
        "constraint_diagnostics.csv",
        "scenario_comparison.csv",
        "scenario_summary.csv",
        "pareto_curve.csv",
        "run_summary.json",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    assert summary["base_run"]["termination_condition"] == "optimal"


def test_linked_asset_overrides_apply(tmp_path: Path):
    linked_path = tmp_path / "capacity_planner_inputs.csv"
    pd.DataFrame(
        [
            {
                "region": "Pacific",
                "planning_baseline_units": 21,
                "recommended_unit_cost": 7777.0,
                "priority_multiplier": 1.2,
                "data_confidence_score": 0.91,
                "unmatched_ratio": 0.08,
            }
        ]
    ).to_csv(linked_path, index=False)
    config, metadata = apply_linked_asset_overrides(load_config(), linked_path)
    assert metadata["linked_asset_input_used"] is True
    assert config["regions"]["Pacific"]["baseline_units"] == 21
    assert config["regions"]["Pacific"]["unit_cost"] == 7777.0
    assert config["regions"]["Pacific"]["priority"] > load_config()["regions"]["Pacific"]["priority"]
