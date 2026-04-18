from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pyomo.environ as pyo


@dataclass
class OptimizationArtifacts:
    plan: pd.DataFrame
    sensitivity: pd.DataFrame
    metrics: dict


def _slack_value(constraint: pyo.ConstraintData) -> float:
    lower_slack = constraint.lslack()
    upper_slack = constraint.uslack()
    candidates = [value for value in (lower_slack, upper_slack) if value is not None]
    if not candidates:
        return 0.0
    return float(min(abs(value) for value in candidates))


def solve_capacity_plan(
    demand_df: pd.DataFrame,
    config: dict,
    budget_cap: float | None = None,
    supply_limit: float | None = None,
    solver_name: str = "appsi_highs",
) -> OptimizationArtifacts:
    planning = config["planning"]
    regions = list(config["regions"].keys())
    months = planning["months"]
    region_params = config["regions"]
    budget_cap = budget_cap or planning["baseline_budget"]
    supply_limit = supply_limit or planning["baseline_supply_limit"]
    unit_capacity = planning["unit_capacity"]
    sla_penalty = planning["sla_penalty"]
    unmet_penalty = planning["unmet_penalty"]

    demand_lookup = demand_df.set_index(["region", "month"])["base_demand"].to_dict()

    model = pyo.ConcreteModel("capacity_plan")
    model.R = pyo.Set(initialize=regions, ordered=True)
    model.M = pyo.Set(initialize=months, ordered=True)

    model.deploy = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.served = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.unmet = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.sla_shortfall = pyo.Var(model.R, model.M, domain=pyo.NonNegativeReals)
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    month_position = {month: idx for idx, month in enumerate(months)}

    def cumulative_capacity(model: pyo.ConcreteModel, region: str, month: str):
        idx = month_position[month]
        elasticity = region_params[region]["elasticity"]
        deployed = sum(model.deploy[region, months[t]] for t in range(idx + 1))
        return unit_capacity * (1 - elasticity) * deployed

    model.demand_balance = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] + m.unmet[r, mo] == demand_lookup[(r, mo)],
    )

    model.capacity_limit = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] <= cumulative_capacity(m, r, mo),
    )

    model.service_floor = pyo.Constraint(
        model.R,
        model.M,
        rule=lambda m, r, mo: m.served[r, mo] + m.sla_shortfall[r, mo] >= region_params[r]["sla_floor"] * demand_lookup[(r, mo)],
    )

    model.monthly_budget = pyo.Constraint(
        model.M,
        rule=lambda m, mo: sum(region_params[r]["unit_cost"] * m.deploy[r, mo] for r in regions) <= budget_cap,
    )

    model.monthly_supply = pyo.Constraint(
        model.M,
        rule=lambda m, mo: sum(m.deploy[r, mo] for r in regions) <= supply_limit,
    )

    model.objective = pyo.Objective(
        expr=sum(
            region_params[r]["priority"] * unmet_penalty * model.unmet[r, mo]
            + region_params[r]["priority"] * sla_penalty * model.sla_shortfall[r, mo]
            + 0.01 * region_params[r]["unit_cost"] * model.deploy[r, mo]
            for r in regions
            for mo in months
        ),
        sense=pyo.minimize,
    )

    solver = pyo.SolverFactory(solver_name)
    if solver is None or not solver.available(False):
        raise RuntimeError(f"Solver '{solver_name}' is not available. Install highspy to use appsi_highs.")
    results = solver.solve(model, load_solutions=True)
    termination = str(results.solver.termination_condition)

    plan_rows: list[dict] = []
    for region in regions:
        cumulative_units = 0.0
        for month in months:
            deploy = pyo.value(model.deploy[region, month])
            served = pyo.value(model.served[region, month])
            unmet = pyo.value(model.unmet[region, month])
            sla_shortfall = pyo.value(model.sla_shortfall[region, month])
            demand = demand_lookup[(region, month)]
            cumulative_units += deploy
            spend = deploy * region_params[region]["unit_cost"]
            coverage = served / demand if demand else 0.0
            plan_rows.append(
                {
                    "region": region,
                    "month": month,
                    "demand": round(demand, 2),
                    "deploy_units": round(deploy, 4),
                    "cumulative_units": round(cumulative_units, 4),
                    "served_demand": round(served, 2),
                    "unmet_demand": round(unmet, 2),
                    "coverage_pct": round(coverage, 4),
                    "sla_floor": region_params[region]["sla_floor"],
                    "sla_shortfall": round(sla_shortfall, 4),
                    "monthly_spend": round(spend, 2),
                }
            )

    plan_df = pd.DataFrame(plan_rows)

    sensitivity_rows: list[dict] = []
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
            sensitivity_rows.append(
                {
                    "constraint_group": group_name,
                    "region": region,
                    "month": month,
                    "shadow_price": round(float(shadow_price), 6),
                    "slack": round(slack, 6),
                    "is_binding": slack <= 1e-5,
                }
            )

    sensitivity_df = pd.DataFrame(sensitivity_rows)

    total_spend = float(plan_df["monthly_spend"].sum())
    total_demand = float(plan_df["demand"].sum())
    total_served = float(plan_df["served_demand"].sum())
    metrics = {
        "solver_status": str(results.solver.status),
        "termination_condition": termination,
        "objective_value": round(float(pyo.value(model.objective)), 4),
        "total_spend": round(total_spend, 2),
        "total_demand": round(total_demand, 2),
        "coverage_pct": round(total_served / total_demand, 4) if total_demand else 0.0,
        "sla_achievement_rate": round(float((plan_df["coverage_pct"] >= plan_df["sla_floor"]).mean()), 4),
        "binding_constraints": int(sensitivity_df["is_binding"].sum()),
        "solve_time_seconds": float(getattr(results.solver, "time", 0.0) or 0.0),
    }

    return OptimizationArtifacts(plan=plan_df, sensitivity=sensitivity_df, metrics=metrics)

