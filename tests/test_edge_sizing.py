import pytest

from swingbot.core.edge.sizing import (
    KELLY_FRACTION_CAP, RISK_CEILING_PCT, RISK_FLOOR_PCT,
    kelly_fraction, kelly_risk_pct,
)


def test_kelly_fraction_golden():
    # f* = p - q/b with b = avg_win/avg_loss.
    # WR 0.80, avg win 0.4R, avg loss 1.0R: b = 0.4 -> f* = 0.8 - 0.2/0.4 = 0.30
    assert kelly_fraction(0.80, 0.4, 1.0) == pytest.approx(0.30)


def test_kelly_zero_when_no_edge():
    # WR 0.70 at b = 0.4 -> f* = 0.7 - 0.3/0.4 = -0.05 -> clamp to 0
    assert kelly_fraction(0.70, 0.4, 1.0) == 0.0
    assert kelly_fraction(0.50, 0.0, 1.0) == 0.0   # degenerate avg win


def test_quarter_kelly_capped_to_ceiling():
    # f* = 0.30 -> quarter-Kelly = 7.5% of equity -> way past the 2% ceiling
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    assert kelly_risk_pct(stats) == RISK_CEILING_PCT


def test_zero_edge_floors():
    stats = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}
    # f* = 0.6 - 0.4/0.3 = negative -> floor
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_small_sample_floors():
    stats = {"win_rate": 0.90, "avg_win_r": 0.5, "avg_loss_r": 1.0, "n": 12}
    assert kelly_risk_pct(stats) == RISK_FLOOR_PCT


def test_constants_frozen():
    assert KELLY_FRACTION_CAP == 0.25
    assert RISK_FLOOR_PCT == 0.25 and RISK_CEILING_PCT == 2.0


def test_high_atr_ticker_gets_less_risk():
    from swingbot.core.edge.sizing import vol_target_risk_pct
    calm = vol_target_risk_pct(1.0)    # 1% daily ATR
    wild = vol_target_risk_pct(3.0)    # 3% daily ATR
    assert wild < calm
    # golden: atr 1% -> budget 0.7% vol, notional 70% of equity,
    # stop 2*ATR = 2% -> risk = 70% * 2% = 1.4% of equity
    assert calm == pytest.approx(1.4)
    # atr 3% -> notional 23.33%, stop capped at 3% -> 0.7%
    assert wild == pytest.approx(0.7)


def test_more_open_positions_shrinks_the_budget():
    from swingbot.core.edge.sizing import vol_target_risk_pct
    alone = vol_target_risk_pct(1.0, open_positions=0)
    crowded = vol_target_risk_pct(1.0, open_positions=3)
    assert crowded < alone


def test_effective_risk_takes_the_min():
    from swingbot.core.edge.sizing import effective_risk_pct
    assert effective_risk_pct(1.0, kelly_risk=2.0, vol_risk=1.4) == 1.0
    assert effective_risk_pct(1.0, kelly_risk=0.5, vol_risk=1.4) == 0.5
    assert effective_risk_pct(1.0) == 1.0                      # nothing else supplied
    assert effective_risk_pct(1.0, throttle_mult=0.5) == 0.5   # throttle multiplies last
    assert effective_risk_pct(1.0, throttle_mult=0.0) == 0.0   # kill = truly zero


def _cfg(mode):
    # max_position_value_absolute/max_risk_amount_absolute explicitly
    # disabled (0) -- compute_position_size falls back to the real
    # project's app_config defaults ($1000 / $100) for any key this dict
    # doesn't supply, which would silently cap every shares figure below
    # to 10 and make these golden numbers wrong.
    return {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": mode,
            "max_open_positions": 5, "max_position_pct": 100.0,
            "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


def test_default_mode_unchanged():
    from swingbot.core.account import compute_position_size
    # entry 100, stop 98 -> $2 risk/share; 1% of 10k = $100 -> 50 shares.
    out = compute_position_size(100.0, 98.0, _cfg("risk_pct"))
    assert out["shares"] == 50


def test_kelly_mode_uses_strategy_stats():
    from swingbot.core.account import compute_position_size
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    # kelly says 2.0% but min(config 1.0, kelly 2.0) = 1.0 -> same 50 shares
    out = compute_position_size(100.0, 98.0, _cfg("kelly"), strategy_stats=stats)
    assert out["shares"] == 50
    # weak stats: kelly floors at 0.25% -> min(1.0, 0.25) -> $25 risk -> 12.5 shares
    # (the plan's own brief said "12 shares" here -- $25 / $2 stop distance is
    # exactly 12.5, not 12; verified against the real compute_position_size
    # output rather than trusting the brief's arithmetic)
    weak = {"win_rate": 0.60, "avg_win_r": 0.3, "avg_loss_r": 1.0, "n": 200}
    out = compute_position_size(100.0, 98.0, _cfg("kelly"), strategy_stats=weak)
    assert out["shares"] == 12.5


def test_vol_target_mode_shrinks_wild_tickers():
    from swingbot.core.account import compute_position_size
    out = compute_position_size(100.0, 98.0, _cfg("vol_target"), ticker_atr_pct=3.0)
    # vol-target 0.7% -> min(1.0, 0.7) -> $70 risk -> 35 shares
    assert out["shares"] == 35


def test_min_of_all_takes_the_smallest():
    from swingbot.core.account import compute_position_size
    stats = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
    out = compute_position_size(100.0, 98.0, _cfg("min_of_all"),
                                strategy_stats=stats, ticker_atr_pct=3.0)
    assert out["shares"] == 35  # min(1.0 config, 2.0 kelly, 0.7 vol) = 0.7


def test_new_modes_without_inputs_fall_back_to_config_risk():
    from swingbot.core.account import compute_position_size
    out = compute_position_size(100.0, 98.0, _cfg("min_of_all"))
    assert out["shares"] == 50


def test_set_sizing_mode_accepts_the_three_edge_modes(tmp_path):
    from swingbot.core.account import set_sizing_mode
    path = str(tmp_path / "account.json")
    assert set_sizing_mode("kelly", path=path)["sizing_mode"] == "kelly"
    assert set_sizing_mode("vol_target", path=path)["sizing_mode"] == "vol_target"
    assert set_sizing_mode("min_of_all", path=path)["sizing_mode"] == "min_of_all"
    with pytest.raises(ValueError):
        set_sizing_mode("not_a_real_mode", path=path)
