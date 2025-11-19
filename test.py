from core.optimizer import (
    grid_search_strategy_params_single_asset,
    select_good_region,
    summarize_region,
)

param_grid = {
    "entry.conditions[1].below": [25, 30, 35, 40],
    "exit.stop_loss": ["2%", "3%", "4%"],
    "exit.take_profit": ["8%", "9%", "12%"],
}

df_strat = grid_search_strategy_params_single_asset(
    asset_file="BTCUSDT_1h.csv",
    strategy_name="range_mean_reversion",
    mode="balanced",
    strategy_param_grid=param_grid,
    position_pct=20.0,
    risk_pct=1.0,
    reward_rr=5.0,
    max_candles=8000,
)

print("Total combos:", len(df_strat))
print(df_strat.describe()[["total_return_pct", "sharpe", "max_dd_pct", "total_trades"]])

good = select_good_region(
    df_strat,
    min_sharpe=5.0,
    max_dd_pct=25.0,
    min_trades=80,
    min_return_pct=8.0,
)

print("Good region size:", len(good))
print(good.head(10))
