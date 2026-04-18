from __future__ import annotations

import dash
import pandas as pd
import plotly.express as px
from dash import Input, Output, dash_table, dcc, html

from .config import OUTPUT_DIR, load_config
from .data import DemandScenario, build_demand_forecast
from .optimize import solve_capacity_plan
from .pipeline import run_pipeline


def _initial_plan() -> pd.DataFrame:
    output_file = OUTPUT_DIR / "optimal_plan.csv"
    if not output_file.exists():
        run_pipeline()
    return pd.read_csv(output_file)


def _run_interactive_plan(budget_cap: float, supply_limit: float, shock_multiplier: float) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    config = load_config()
    demand_df = build_demand_forecast(config, DemandScenario(name="interactive", shock_multiplier=shock_multiplier))
    artifacts = solve_capacity_plan(demand_df, config, budget_cap=budget_cap, supply_limit=supply_limit)
    return artifacts.plan, artifacts.sensitivity, artifacts.metrics


app = dash.Dash(__name__)
server = app.server
config = load_config()
default_budget = config["planning"]["baseline_budget"]
default_supply = config["planning"]["baseline_supply_limit"]
_initial_plan()

app.layout = html.Div(
    style={"maxWidth": "1280px", "margin": "0 auto", "padding": "24px", "fontFamily": "Helvetica, Arial, sans-serif"},
    children=[
        html.H1("Network Capacity Deployment Optimizer"),
        html.P("Interactive planning surface for budget, supply, and demand shock analysis."),
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "24px", "marginBottom": "24px"},
            children=[
                html.Div(
                    [
                        html.Label("Monthly budget cap"),
                        dcc.Slider(id="budget-slider", min=250000, max=650000, step=10000, value=default_budget),
                        html.Div(id="budget-value"),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Monthly supply limit"),
                        dcc.Slider(id="supply-slider", min=30, max=120, step=5, value=default_supply),
                        html.Div(id="supply-value"),
                    ]
                ),
                html.Div(
                    [
                        html.Label("Demand shock"),
                        dcc.Slider(id="shock-slider", min=-20, max=20, step=5, value=0),
                        html.Div(id="shock-value"),
                    ]
                ),
            ],
        ),
        dcc.Graph(id="plan-heatmap"),
        dcc.Graph(id="coverage-chart"),
        html.H2("Binding constraints"),
        dash_table.DataTable(
            id="binding-table",
            page_size=10,
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "left", "padding": "8px"},
        ),
        html.Div(id="metric-panel", style={"marginTop": "24px"}),
    ],
)


@app.callback(
    Output("budget-value", "children"),
    Output("supply-value", "children"),
    Output("shock-value", "children"),
    Output("plan-heatmap", "figure"),
    Output("coverage-chart", "figure"),
    Output("binding-table", "data"),
    Output("binding-table", "columns"),
    Output("metric-panel", "children"),
    Input("budget-slider", "value"),
    Input("supply-slider", "value"),
    Input("shock-slider", "value"),
)
def update_dashboard(budget_cap: float, supply_limit: float, shock_percent: float):
    shock_multiplier = 1 + (shock_percent / 100.0)
    plan_df, sensitivity_df, metrics = _run_interactive_plan(budget_cap, supply_limit, shock_multiplier)

    heatmap_source = plan_df.pivot(index="region", columns="month", values="deploy_units")
    heatmap = px.imshow(
        heatmap_source,
        color_continuous_scale="Blues",
        aspect="auto",
        labels={"x": "Month", "y": "Region", "color": "Deploy units"},
        title="Deployment plan heatmap",
    )

    coverage_df = plan_df.copy()
    coverage_df["sla_floor_pct"] = coverage_df["sla_floor"] * 100
    coverage_df["coverage_pct"] = coverage_df["coverage_pct"] * 100
    coverage_long = coverage_df.melt(
        id_vars=["region", "month"],
        value_vars=["coverage_pct", "sla_floor_pct"],
        var_name="metric",
        value_name="value",
    )
    coverage_chart = px.line(
        coverage_long,
        x="month",
        y="value",
        color="region",
        line_dash="metric",
        markers=True,
        title="Coverage vs SLA floor",
    )

    binding_df = sensitivity_df[sensitivity_df["is_binding"]].head(20)
    binding_columns = [{"name": column, "id": column} for column in binding_df.columns]

    metric_panel = html.Div(
        [
            html.P(f"Solver termination: {metrics['termination_condition']}"),
            html.P(f"Total spend: ${metrics['total_spend']:,.0f}"),
            html.P(f"Coverage: {metrics['coverage_pct'] * 100:.2f}%"),
            html.P(f"SLA achievement rate: {metrics['sla_achievement_rate'] * 100:.2f}%"),
            html.P(f"Binding constraints: {metrics['binding_constraints']}"),
            html.P(f"Solve time: {metrics['solve_time_seconds']:.4f} seconds"),
        ]
    )

    return (
        f"${budget_cap:,.0f}",
        f"{supply_limit:.0f} units",
        f"{shock_percent:+.0f}%",
        heatmap,
        coverage_chart,
        binding_df.to_dict(orient="records"),
        binding_columns,
        metric_panel,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
