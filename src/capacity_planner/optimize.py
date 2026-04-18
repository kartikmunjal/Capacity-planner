from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import pandas as pd
import pyomo.environ as pyo


@dataclass
class OptimizationArtifacts:
    plan: pd.DataFrame
    sensitivity: pd.DataFrame
    diagnostics: pd.DataFrame
    metrics: dict


def _slack_value(constraint: pyo.ConstraintData) -> float:
    lower_slack = constraint.lslack()
    upper_slack = constraint.uslack()
    candidates = [value for value in (lower_slack, upper_slack) if value is not None]
    if not candidates:
        return 0.0
    return float(min(abs(value) for value in candidates))


def _build_model(
    demand_df: pd.DataFrame,
    config: dict,
    budget_cap: float,
    supply_limit: float,
    integer_batches: bool,
    include_duals: bool,
) -> tuple[pyo.ConcreteModel, dict, dict]:
    planning = config["planning"]
    regions = list(config["regions"].keys())
    months = planning["months"]
    region_params = config["regions"]
    batch_size = planning["deployment_batch_size"]
    unit_capacity = planning["unit_capacity"]
    lead_time = planning["deployment_lead_time_months"]
    sla_penalty = planning["sla_penalty"]
    unmet_penalty = planning["unmet_penalty"]
    operating_cost_weight = planning["operating_cost_weight"]

    demand_lookup = demand_df.set_index(["region", "month"])["base_demand"].to_dict()
    month_position = {month: idx for idx, month in enumerate(months)}

    model = pyo.ConcreteModel("capacity_plan")
    model.R = pyo.Set(initialize=regions, ordered=True)
    model.M = pyo.Set(initialize=months, ordered=True)
    batch_domain = pyo.NonNegativeIntegers if integer_batches else pyo.NonNegativeReals

    model.deploy_batches = pyo.Var(model.R, model.M, domain=batch_domain)
    model.served = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.unmet = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.sla_shortfall = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    if include_duals:
        model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    def deployed_units(model: pyo.ConcreteModel, region: str, month: str):
        return batch_size * model.deploy_batches[region, month]

    def active_units(model: pyo.ConcreteModel, region: str, month: str):
        idx = month_position[month]
        baseline_units = region_params[region]["baseline_units"]
        deployed_before_activation = sum(
            deployed_units(model, region, months[t]) for t in range(max(0, idx - lead_time + 1))
        )
        return baseline_units + deployed_before_activation

    def effective_capacity(model: pyo.ConcreteModel, region: str, month: str):
        elasticity = region_params[region]["elasticity"]
        return unit_capacity * (1 - elasticity) * active_units(model, region, month)

    model.demand_balance = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] + m.unmet[r, mo] == demand_lookup[(r, mo)],
    )

    model.capacity_limit = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] <= effective_capacity(m, r, mo),
    )

    model.service_floor = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] + m.sla_shortfall[r, mo] >= region_params[r]["sla_floor"] * demand_lookup[(r, mo)],
    )

    model.monthly_budget = pyo.Constraint(
        model.M,
        rule=lambda m, mo: sum(region_params[r]["unit_cost"] * deployed_units(m, r, mo) for r in regions) <= budget_cap,
    )

    model.monthly_supply = pyo.Constraint(
        model.M,
        rule=lambda m, mo: sum(deployed_units(m, r, mo) for r in regions) <= supply_limit,
    )

    model.objective = pyo.Objective(
        expr=sum(
            region_params[r]["priority"] * unmet_penalty * model.unmet[r, mo]
            + region_params[r]["priority"] * sla_penalty * model.sla_shortfall[r, mo]
            + 0.01 * region_params[r]["unit_cost"] * deployed_units(model, r, mo)
            + operating_cost_weight * region_params[r]["opex_per_unit"] * active_units(model, r, mo)
            for r in regions
            for mo in months
        ),
        sense=pyo.minimize,
    )

    metadata = {
        "regions": regions,
        "months": months,
        "batch_size": batch_size,
        "lead_time": lead_time,
        "unit_capacity": unit_capacity,
        "region_params": region_params,
        "demand_lookup": demand_lookup,
        "month_position": month_position,
    }
    return model, metadata, {"budget_cap": budget_cap, "supply_limit": supply_limit}


def _extract_plan(model: pyo.ConcreteModel, metadata: dict) -> pd.DataFrame:
    rows: list[dict] = []
    regions = metadata["regions"]
    months = metadata["months"]
    batch_size = metadata["batch_size"]
    unit_capacity = metadata["unit_capacity"]
    lead_time = metadata["lead_time"]
    region_params = metadata["region_params"]
    demand_lookup = metadata["demand_lookup"]
    month_position = metadata["month_position"]

    for region in regions:
        cumulative_deployed_units = 0.0
        for month in months:
            idx = month_position[month]
            deployed_batches = pyo.value(model.deploy_batches[region, month])
            deployed_units = deployed_batches * batch_size
            demand = demand_lookup[(region, month)]
            served = pyo.value(model.served[region, month])
            unmet = pyo.value(model.unmet[region, month])
            sla_shortfall = pyo.value(model.sla_shortfall[region, month])
            cumulative_deployed_units += deployed_units

            active_deployed_units = sum(
                pyo.value(model.deploy_batches[region, months[t]]) * batch_size for t in range(max(0, idx - lead_time + 1))
            )
            baseline_units = region_params[region]["baseline_units"]
            active_units = baseline_units + active_deployed_units
            effective_capacity = unit_capacity * (1 - region_params[region]["elasticity"]) * active_units
            capex_spend = deployed_units * region_params[region]["unit_cost"]
            opex_spend = active_units * region_params[region]["opex_per_unit"]
            coverage = served / demand if demand else 0.0

            rows.append(
                {
                    "region": region,
                    "month": month,
                    "demand": round(demand, 2),
                    "deploy_batches": round(deployed_batches, 4),
                    "deploy_units": round(deployed_units, 4),
                    "baseline_units": baseline_units,
                    "active_units": round(active_units, 4),
                    "cumulative_units": round(baseline_units + cumulative_deployed_units, 4),
                    "effective_capacity": round(effective_capacity, 2),
                    "served_demand": round(served, 2),
                    "unmet_demand": round(unmet, 2),
                    "coverage_pct": round(coverage, 4),
                    "sla_floor": region_params[region]["sla_floor"],
                    "sla_shortfall": round(sla_shortfall, 4),
                    "capex_spend": round(capex_spend, 2),
                    "opex_spend": round(opex_spend, 2),
                    "total_monthly_cost": round(capex_spend + opex_spend, 2),
                }
            )

    return pd.DataFrame(rows)


def _extract_sensitivity(model: pyo.ConcreteModel) -> pd.DataFrame:
    rows: list[dict] = []
    constraint_groups = {
        "monthly_budget": model.monthly_budget,
        "monthly_supply": model.monthly_supply,
        "capacity_limit": model.capacity_limit,
        "service_floor": model.service_floor,
        "demand_balance": model.demand_balance,
    }
    for group_name, group in constraint_groups.items():
        for key in group:
            constraint = group[key]
            shadow_price = model.dual.get(constraint, 0.0)
            slack = _slack_value(constraint)
            if isinstance(key, tuple):
                region, month = key
            else:
                region, month = "", key
            rows.append(
                {
                    "constraint_group": group_name,
                    "region": region,
                    "month": month,
                    "shadow_price": round(float(shadow_price), 6),
                    "slack": round(slack, 6),
                    "is_binding": slack <= 1e-5,
                }
            )
    return pd.DataFrame(rows)


def _build_diagnostics(plan_df: pd.DataFrame, sensitivity_df: pd.DataFrame, controls: dict) -> pd.DataFrame:
    monthly_plan = plan_df.groupby("month", as_index=False).agg(
        deployed_units=("deploy_units", "sum"),
        capex_spend=("capex_spend", "sum"),
        opex_spend=("opex_spend", "sum"),
        coverage_pct=("coverage_pct", "mean"),
        unmet_demand=("unmet_demand", "sum"),
    )
    budget_diag = sensitivity_df[sensitivity_df["constraint_group"] == "monthly_budget"][
        ["month", "shadow_price", "slack", "is_binding"]
    ].rename(
        columns={
            "shadow_price": "budget_shadow_price",
            "slack": "budget_slack",
            "is_binding": "budget_binding",
        }
    )
    supply_diag = sensitivity_df[sensitivity_df["constraint_group"] == "monthly_supply"][
        ["month", "shadow_price", "slack", "is_binding"]
    ].rename(
        columns={
            "shadow_price": "supply_shadow_price",
            "slack": "supply_slack",
            "is_binding": "supply_binding",
        }
    )
    diagnostics = monthly_plan.merge(budget_diag, on="month").merge(supply_diag, on="month")
    diagnostics["budget_cap"] = controls["budget_cap"]
    diagnostics["supply_limit"] = controls["supply_limit"]
    diagnostics["budget_utilization_pct"] = (diagnostics["capex_spend"] / diagnostics["budget_cap"]).round(4)
    diagnostics["supply_utilization_pct"] = (diagnostics["deployed_units"] / diagnostics["supply_limit"]).round(4)
    diagnostics["primary_driver"] = diagnostics.apply(
        lambda row: "budget"
        if row["budget_binding"] and abs(row["budget_shadow_price"]) >= abs(row["supply_shadow_price"])
        else ("supply" if row["supply_binding"] else "demand/capacity"),
        axis=1,
    )
    return diagnostics


def _constraint_row_count(model: pyo.ConcreteModel) -> int:
    return sum(len(component) for component in model.component_objects(pyo.Constraint, active=True))


def solve_capacity_plan(
    demand_df: pd.DataFrame,
    config: dict,
    budget_cap: float | None = None,
    supply_limit: float | None = None,
    solver_name: str = "appsi_highs",
) -> OptimizationArtifacts:
    planning = config["planning"]
    budget_cap = budget_cap or planning["baseline_budget"]
    supply_limit = supply_limit or planning["baseline_supply_limit"]

    mip_model, metadata, controls = _build_model(
        demand_df=demand_df,
        config=config,
        budget_cap=budget_cap,
        supply_limit=supply_limit,
        integer_batches=True,
        include_duals=False,
    )

    solver = pyo.SolverFactory(solver_name)
    if solver is None or not solver.available(False):
        raise RuntimeError(f"Solver '{solver_name}' is not available. Install highspy to use appsi_highs.")

    solve_start = perf_counter()
    mip_results = solver.solve(mip_model, load_solutions=True)
    solve_time_seconds = perf_counter() - solve_start

    plan_df = _extract_plan(mip_model, metadata)

    relaxed_model, _, _ = _build_model(
        demand_df=demand_df,
        config=config,
        budget_cap=budget_cap,
        supply_limit=supply_limit,
        integer_batches=False,
        include_duals=True,
    )
    relaxed_results = solver.solve(relaxed_model, load_solutions=True)
    sensitivity_df = _extract_sensitivity(relaxed_model)
    diagnostics_df = _build_diagnostics(plan_df, sensitivity_df, controls)

    total_capex = float(plan_df["capex_spend"].sum())
    total_opex = float(plan_df["opex_spend"].sum())
    total_cost = float(plan_df["total_monthly_cost"].sum())
    total_demand = float(plan_df["demand"].sum())
    total_served = float(plan_df["served_demand"].sum())
    total_deploy_units = float(plan_df["deploy_units"].sum())
    metrics = {
        "solver_status": str(mip_results.solver.status),
        "termination_condition": str(mip_results.solver.termination_condition),
        "diagnostics_basis": "shadow prices from LP relaxation; deployment plan from integer batch solution",
        "objective_value": round(float(pyo.value(mip_model.objective)), 4),
        "lp_relaxation_objective": round(float(pyo.value(relaxed_model.objective)), 4),
        "total_capex": round(total_capex, 2),
        "total_opex": round(total_opex, 2),
        "total_cost": round(total_cost, 2),
        "total_demand": round(total_demand, 2),
        "coverage_pct": round(total_served / total_demand, 4) if total_demand else 0.0,
        "sla_achievement_rate": round(float((plan_df["coverage_pct"] >= plan_df["sla_floor"]).mean()), 4),
        "binding_constraints": int(sensitivity_df["is_binding"].sum()),
        "solve_time_seconds": round(solve_time_seconds, 6),
        "solver_rows": _constraint_row_count(relaxed_model),
        "deployment_batches_total": round(float(plan_df["deploy_batches"].sum()), 4),
        "deployment_units_total": round(total_deploy_units, 4),
        "budget_utilization_peak": round(float(diagnostics_df["budget_utilization_pct"].max()), 4),
        "supply_utilization_peak": round(float(diagnostics_df["supply_utilization_pct"].max()), 4),
        "relaxed_solver_status": str(relaxed_results.solver.status),
    }

    return OptimizationArtifacts(
        plan=plan_df,
        sensitivity=sensitivity_df,
        diagnostics=diagnostics_df,
        metrics=metrics,
    )
