from types import SimpleNamespace

from swingbot.commands.backtest import (
    ALL_STRATEGIES,
    _format_backtest_table,
    _format_per_strategy_winrate,
    _format_setup_list,
)


def _summary(**overrides):
    values = {
        "strategy": ALL_STRATEGIES[0],
        "horizon_key": "4w",
        "total_signals": 5,
        "evaluated": 5,
        "scratches": 0,
        "timeouts": 0,
        "wins": 4,
        "losses": 1,
        "win_rate": 81.2,
        "expectancy_r": 0.4,
        "max_drawdown_pct": 12.34,
        "avg_holding_days": 5.0,
        "trades": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_backtest_summary_percentages_and_r_multiples_use_the_shared_format():
    summary = _summary()

    table = _format_backtest_table("Backtest", [summary])
    pooled = _format_per_strategy_winrate([summary])

    assert "+81.2%" in table
    assert "0.4R" in table
    assert "−12.3%" in table
    assert "+80.0%" in pooled
    assert "0.4R" in pooled


def test_backtest_setup_prices_keep_sub_dollar_precision():
    trade = SimpleNamespace(
        entry_date="2026-08-01",
        exit_date="2026-08-08",
        direction="bullish",
        entry=0.4321,
        stop_loss=0.4012,
        take_profit=1234.5,
        outcome="win",
        r_multiple=1.25,
    )

    body = _format_setup_list("Setups", [_summary(trades=[trade])])

    assert "0.4321" in body
    assert "0.4012" in body
    assert "1234.50" in body
    assert "1.2R" in body
