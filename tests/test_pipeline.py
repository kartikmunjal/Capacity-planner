from capacity_planner.config import load_config
from capacity_planner.data import DemandScenario, build_demand_forecast


def test_forecast_shape():
    config = load_config()
    forecast = build_demand_forecast(config, DemandScenario(name="base"))
    assert forecast.shape[0] == 60
    assert sorted(forecast["region"].unique().tolist()) == sorted(config["regions"].keys())
