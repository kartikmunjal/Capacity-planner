# Modeling Assumptions

This document records the operating assumptions behind the network capacity deployment optimizer.

## Demand

- Demand is synthetic and generated across 5 regions and 12 months.
- Forecast shape combines base demand, growth trend, and seasonal amplitude.
- Elasticity reduces effective capacity because additional network availability can induce incremental demand.

## Capacity and deployment

- Regional `baseline_units` represent already-installed network capacity.
- New deployment decisions are made in integer batches.
- Each deployed batch becomes active after a one-month lead time.
- Effective served capacity is `unit_capacity * (1 - elasticity) * active_units`.

## Costing

- Monthly deployment spending is constrained by a budget cap.
- Monthly deployment quantity is constrained by a supply limit.
- Capex is based on region-level unit cost.
- Opex is based on active installed units and region-level operating cost.

## Service levels and optimization

- SLA floors are modeled as minimum regional coverage targets.
- SLA shortfall is allowed but penalized heavily to preserve comparability under stress scenarios.
- The objective minimizes weighted unmet demand, weighted SLA shortfall, deployment cost, and operating cost.
- Shadow prices are taken from an LP relaxation, while the deployment plan itself comes from the integer model.

## Linked input from Project 2

- If `../Network-Asset-Reconciliation/outputs/capacity_planner_inputs.csv` exists, Project 1 overrides regional baseline units, unit cost, and priority using reconciled asset data.
- This linked input is treated as a higher-quality operating baseline than the default synthetic YAML assumptions.

