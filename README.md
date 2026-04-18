# Network Capacity Deployment Optimizer

This project frames network capacity planning as a research-style constrained optimization problem. It generates a synthetic 12-month regional WiFi offload forecast, solves for an optimal deployment schedule with Pyomo, compares scenario outcomes under demand shocks, and exposes the results through a Dash app.

## Research framing

The model is designed around the operational question:

> Given a budget, a monthly supply cap, and service level commitments, where and when should network infrastructure be deployed?

The formulation uses:

- 5 regions across 12 months
- seasonality, growth, and induced-demand elasticity in the forecast
- baseline installed capacity by region
- monthly budget and supply constraints
- one-month deployment lead time
- batched integer deployment decisions
- capex plus operating-cost tracking
- SLA coverage floors by region and month
- region priority weights in the objective

## Repository layout

- `config/constraints.yaml`: planning assumptions and regional parameters
- `src/capacity_planner/data.py`: synthetic demand generator
- `src/capacity_planner/optimize.py`: Pyomo model, solve routine, and sensitivity extraction
- `src/capacity_planner/scenario.py`: scenario reruns and Pareto experiments
- `src/capacity_planner/pipeline.py`: reproducible CLI pipeline
- `src/capacity_planner/app.py`: interactive Dash app
- `tests/test_pipeline.py`: smoke coverage for the core workflow

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install .[dev]
capacity-planner-pipeline
capacity-planner-app
```

The Dash app runs on `http://localhost:8050`.

## Outputs

Running the pipeline produces:

- `data/demand_forecast.csv`
- `outputs/optimal_plan.csv`
- `outputs/sensitivity_report.csv`
- `outputs/constraint_diagnostics.csv`
- `outputs/scenario_comparison.csv`
- `outputs/scenario_summary.csv`
- `outputs/pareto_curve.csv`
- `outputs/run_summary.json`

## Linked Input From Project 2

If the sibling repository `../Network-Asset-Reconciliation` has produced `outputs/capacity_planner_inputs.csv`, this project auto-ingests it during pipeline runs and in the Dash app.

The linked export overrides:

- `baseline_units` by region
- `unit_cost` by region
- `priority` via a reconciliation-derived multiplier

This turns Project 1 from a fully synthetic planning model into one that can start from a reconciled regional asset baseline.

## Model notes

- Deployment choices are integer batches, while shadow prices are reported from an LP relaxation for diagnostics.
- Elasticity is modeled as demand lift that offsets a portion of newly added effective capacity.
- Baseline regional capacity prevents the model from pretending the network starts from zero.
- A one-month activation lag models procurement and deployment lead time.
- SLA shortfall is allowed but heavily penalized so infeasible cases can still be compared under stress scenarios.

## Dash surface

The second-pass app adds:

- scenario presets plus a custom demand shock mode
- heatmap of deployment units by region and month
- coverage vs SLA chart
- budget and supply utilization chart
- scenario delta chart against the base plan
- binding-constraint and monthly-diagnostics tables

## Docker

```bash
docker build -t capacity-planner .
docker run --rm -p 8050:8050 capacity-planner
```
