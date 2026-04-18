from __future__ import annotations

import dash
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, dash_table, dcc, html

from .config import OUTPUT_DIR, load_config
from .data import DemandScenario, build_demand_forecast
from .linked_inputs import apply_linked_asset_overrides
from .optimize import solve_capacity_plan
from .pipeline import run_pipeline


SCENARIO_PRESETS = {
    "base": 1.0,
    "growth_shock": 1.2,
    "contraction": 0.8,
}


def _ensure_outputs() -> None:
    if not (OUTPUT_DIR / "optimal_plan.csv").exists():
        run_pipeline()


def _run_plan(budget_cap: float, supply_limit: float, scenario_name: str, shock_percent: float):
    config, _ = apply_linked_asset_overrides(load_config())
    if scenario_name == "custom":
        shock_multiplier = 1 + (shock_percent / 100.0)
    else:
        shock_multiplier = SCENARIO_PRESETS[scenario_name]
    demand_df = build_demand_forecast(config, DemandScenario(name=scenario_name, shock_multiplier=shock_multiplier))
    return solve_capacity_plan(demand_df, config, budget_cap=budget_cap, supply_limit=supply_limit), shock_multiplier


def _metric_card(title: str, value: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.Div(title, style={"fontSize": "12px", "letterSpacing": "0.08em", "textTransform": "uppercase", "color": "#6b7280"}),
            html.Div(value, style={"fontSize": "28px", "fontWeight": "700", "color": "#111827", "marginTop": "6px"}),
            html.Div(subtitle, style={"fontSize": "13px", "color": "#4b5563", "marginTop": "4px"}),
        ],
        style={
            "background": "linear-gradient(180deg, #ffffff 0%, #f4f7fb 100%)",
            "border": "1px solid #dbe5f0",
            "borderRadius": "18px",
            "padding": "18px",
            "boxShadow": "0 16px 30px rgba(15, 23, 42, 0.06)",
        },
    )


_ensure_outputs()
config, linked_metadata = apply_linked_asset_overrides(load_config())
default_budget = config["planning"]["baseline_budget"]
default_supply = config["planning"]["baseline_supply_limit"]

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        "minHeight": "100vh",
        "background": "radial-gradient(circle at top left, #fff1d6 0%, #eef5ff 42%, #f7fafc 100%)",
        "padding": "28px",
        "fontFamily": "Georgia, 'Times New Roman', serif",
        "color": "#102033",
    },
    children=[
        html.Div(
            [
                html.Div("Project 1", style={"fontSize": "13px", "letterSpacing": "0.16em", "textTransform": "uppercase", "color": "#9a3412"}),
                html.H1("Network Capacity Deployment Optimizer", style={"margin": "8px 0 10px", "fontSize": "48px", "lineHeight": "1.05"}),
                html.P(
                    "Research-style planning lab for monthly network deployment under budget, supply, elasticity, and SLA pressure.",
                    style={"maxWidth": "900px", "fontSize": "18px", "lineHeight": "1.6", "color": "#334155"},
                ),
                html.P(
                    f"Linked asset baseline: {'enabled' if linked_metadata['linked_asset_input_used'] else 'not found'}",
                    style={"fontSize": "14px", "color": "#9a3412"},
                ),
            ],
            style={"marginBottom": "26px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Div("Budget cap", style={"fontWeight": "700", "marginBottom": "10px"}),
                        dcc.Slider(id="budget-slider", min=250000, max=650000, step=10000, value=default_budget),
                        html.Div(id="budget-value", style={"marginTop": "8px", "color": "#475569"}),
                    ]
                ),
                html.Div(
                    [
                        html.Div("Supply limit", style={"fontWeight": "700", "marginBottom": "10px"}),
                        dcc.Slider(id="supply-slider", min=20, max=120, step=4, value=default_supply),
                        html.Div(id="supply-value", style={"marginTop": "8px", "color": "#475569"}),
                    ]
                ),
                html.Div(
                    [
                        html.Div("Scenario", style={"fontWeight": "700", "marginBottom": "10px"}),
                        dcc.Dropdown(
                            id="scenario-select",
                            options=[
                                {"label": "Base", "value": "base"},
                                {"label": "+20% shock", "value": "growth_shock"},
                                {"label": "-20% contraction", "value": "contraction"},
                                {"label": "Custom", "value": "custom"},
                            ],
                            value="base",
                            clearable=False,
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.Div("Custom demand shock", style={"fontWeight": "700", "marginBottom": "10px"}),
                        dcc.Slider(id="shock-slider", min=-30, max=30, step=5, value=0),
                        html.Div(id="shock-value", style={"marginTop": "8px", "color": "#475569"}),
                    ]
                ),
            ],
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
                "gap": "18px",
                "padding": "20px",
                "background": "rgba(255,255,255,0.82)",
                "border": "1px solid #d6e2ee",
                "borderRadius": "22px",
                "backdropFilter": "blur(8px)",
                "boxShadow": "0 18px 40px rgba(15, 23, 42, 0.08)",
            },
        ),
        html.Div(id="metric-cards", style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "16px", "marginTop": "22px"}),
        html.Div(
            [
                dcc.Graph(id="plan-heatmap", style={"background": "#fff", "borderRadius": "20px"}),
                dcc.Graph(id="coverage-chart", style={"background": "#fff", "borderRadius": "20px"}),
            ],
            style={"display": "grid", "gridTemplateColumns": "1.2fr 1fr", "gap": "18px", "marginTop": "22px"},
        ),
        html.Div(
            [
                dcc.Graph(id="driver-chart", style={"background": "#fff", "borderRadius": "20px"}),
                dcc.Graph(id="scenario-delta-chart", style={"background": "#fff", "borderRadius": "20px"}),
            ],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "18px", "marginTop": "18px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Binding Constraints"),
                        dash_table.DataTable(
                            id="binding-table",
                            page_size=10,
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_header={"backgroundColor": "#f8fafc", "fontWeight": "700"},
                            style_cell={"textAlign": "left", "padding": "8px", "fontSize": "13px"},
                        ),
                    ],
                    style={"background": "#fff", "borderRadius": "20px", "padding": "18px", "border": "1px solid #e2e8f0"},
                ),
                html.Div(
                    [
                        html.H2("Monthly Diagnostics"),
                        dash_table.DataTable(
                            id="diagnostics-table",
                            page_size=12,
                            sort_action="native",
                            style_table={"overflowX": "auto"},
                            style_header={"backgroundColor": "#f8fafc", "fontWeight": "700"},
                            style_cell={"textAlign": "left", "padding": "8px", "fontSize": "13px"},
                        ),
                    ],
                    style={"background": "#fff", "borderRadius": "20px", "padding": "18px", "border": "1px solid #e2e8f0"},
                ),
            ],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "18px", "marginTop": "18px"},
        ),
    ],
)


@app.callback(
    Output("budget-value", "children"),
    Output("supply-value", "children"),
    Output("shock-value", "children"),
    Output("metric-cards", "children"),
    Output("plan-heatmap", "figure"),
    Output("coverage-chart", "figure"),
    Output("driver-chart", "figure"),
    Output("scenario-delta-chart", "figure"),
    Output("binding-table", "data"),
    Output("binding-table", "columns"),
    Output("diagnostics-table", "data"),
    Output("diagnostics-table", "columns"),
    Input("budget-slider", "value"),
    Input("supply-slider", "value"),
    Input("scenario-select", "value"),
    Input("shock-slider", "value"),
)
def update_dashboard(budget_cap: float, supply_limit: float, scenario_name: str, shock_percent: float):
    artifacts, shock_multiplier = _run_plan(budget_cap, supply_limit, scenario_name, shock_percent)

    base_artifacts, _ = _run_plan(budget_cap, supply_limit, "base", 0)
    plan_df = artifacts.plan.copy()
    diagnostics_df = artifacts.diagnostics.copy()
    sensitivity_df = artifacts.sensitivity.copy()
    base_plan = base_artifacts.plan[["region", "month", "deploy_units"]].rename(columns={"deploy_units": "base_deploy_units"})
    plan_df = plan_df.merge(base_plan, on=["region", "month"], how="left")
    plan_df["deploy_delta_vs_base"] = plan_df["deploy_units"] - plan_df["base_deploy_units"]

    heatmap_source = plan_df.pivot(index="region", columns="month", values="deploy_units")
    heatmap = px.imshow(
        heatmap_source,
        color_continuous_scale=["#fff7ed", "#fdba74", "#c2410c"],
        aspect="auto",
        title="Deployment batches translated to units by region-month",
        labels={"x": "Month", "y": "Region", "color": "Units"},
    )
    heatmap.update_layout(paper_bgcolor="white", plot_bgcolor="white")

    coverage_df = plan_df.copy()
    coverage_df["coverage_pct"] = coverage_df["coverage_pct"] * 100
    coverage_df["sla_floor_pct"] = coverage_df["sla_floor"] * 100
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
        title="Coverage trajectory vs SLA floor",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    coverage_chart.update_layout(paper_bgcolor="white", plot_bgcolor="white", yaxis_title="Percent")

    driver_chart = go.Figure()
    driver_chart.add_bar(
        x=diagnostics_df["month"],
        y=diagnostics_df["budget_utilization_pct"] * 100,
        name="Budget util.",
        marker_color="#2563eb",
    )
    driver_chart.add_bar(
        x=diagnostics_df["month"],
        y=diagnostics_df["supply_utilization_pct"] * 100,
        name="Supply util.",
        marker_color="#f97316",
    )
    driver_chart.update_layout(
        title="Monthly constraint utilization",
        barmode="group",
        paper_bgcolor="white",
        plot_bgcolor="white",
        yaxis_title="Percent",
    )

    delta_df = plan_df.groupby("region", as_index=False).agg(
        deploy_delta_vs_base=("deploy_delta_vs_base", "sum"),
        unmet_demand=("unmet_demand", "sum"),
    )
    scenario_delta_chart = px.bar(
        delta_df,
        x="region",
        y="deploy_delta_vs_base",
        color="deploy_delta_vs_base",
        color_continuous_scale=["#dbeafe", "#60a5fa", "#1d4ed8"],
        title="Plan delta versus base scenario",
    )
    scenario_delta_chart.update_layout(paper_bgcolor="white", plot_bgcolor="white", coloraxis_showscale=False)

    binding_df = sensitivity_df[sensitivity_df["is_binding"]].copy().head(20)
    binding_columns = [{"name": column, "id": column} for column in binding_df.columns]
    diagnostics_columns = [{"name": column, "id": column} for column in diagnostics_df.columns]

    metric_cards = [
        _metric_card("Scenario", scenario_name.replace("_", " ").title(), f"Shock multiplier {shock_multiplier:.2f}x"),
        _metric_card("Coverage", f"{artifacts.metrics['coverage_pct'] * 100:.1f}%", "Weighted annual served demand"),
        _metric_card("SLA Hit Rate", f"{artifacts.metrics['sla_achievement_rate'] * 100:.1f}%", "Region-month combinations at or above floor"),
        _metric_card("Capex", f"${artifacts.metrics['total_capex']:,.0f}", "Deployment spend only"),
        _metric_card("Opex", f"${artifacts.metrics['total_opex']:,.0f}", "Active network operating cost"),
        _metric_card("Solve Time", f"{artifacts.metrics['solve_time_seconds']:.3f}s", artifacts.metrics["diagnostics_basis"]),
    ]

    return (
        f"${budget_cap:,.0f} per month",
        f"{supply_limit:.0f} units per month",
        f"{shock_percent:+.0f}% custom shock",
        metric_cards,
        heatmap,
        coverage_chart,
        driver_chart,
        scenario_delta_chart,
        binding_df.to_dict(orient="records"),
        binding_columns,
        diagnostics_df.round(4).to_dict(orient="records"),
        diagnostics_columns,
    )


def main() -> None:
    app.run(host="0.0.0.0", port=8050, debug=False)


if __name__ == "__main__":
    main()
