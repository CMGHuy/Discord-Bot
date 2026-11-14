"""v212 portfolio_replay options: notional caps scale carried risk (R stays
on the plan's stop), per-reason skips, a cluster callback, taken keys, and
today's dict exactly when no option is set."""
import pytest

from swingbot.core.backtesting.backtest_wf import portfolio_replay

LEGACY_KEYS = {"equity_curve", "final_multiple", "max_dd_pct", "trades_taken",
               "trades_skipped", "trades_per_month", "r_multiples_taken", "per_strategy_wr",
               "reversals", "reversals_r_delta"}


def _sig(ticker="AAA", date="2021-01-04", exit_date="2021-01-08", r=1.0, **kw):
    return {"ticker": ticker, "date": date, "exit_date": exit_date, "r_multiple": r,
            "direction": "bullish", "outcome": "win" if r > 0 else "loss",
            "strategy": "S/R Confluence", "stop_pct": 1.0, "key": f"{ticker}|{date}", **kw}


def _run(signals, **kw):
    return portfolio_replay(signals, throttles=False, sector_cap_pct=100.0, **kw)


def test_no_option_returns_todays_dict_exactly():
    signals = [_sig(), _sig("BBB", r=-1.0)]
    out = _run(signals)
    assert set(out) == LEGACY_KEYS
    assert out == _run(signals, max_position_pct=None, max_position_value=None,
                       cluster_fn=None, track_keys=False)
    assert out["final_multiple"] == pytest.approx(1.01 * 0.99)


@pytest.mark.parametrize("kw,multiple", [
    ({"max_position_value": 1000.0}, 1.001),      # $10k notional cut to $1k: risk 0.1%
    ({"max_position_pct": 50.0}, 1.005),          # cut to $5k: risk 0.5%
    ({"max_position_pct": 50.0, "max_position_value": 1000.0}, 1.001),   # the tighter wins
    ({"max_position_value": 0.0}, 1.01),          # 0 = off, as account._uncut_size_caps
    ({"max_position_pct": 200.0}, 1.01),          # cap above the notional: no cut
])
def test_notional_caps_scale_the_carried_risk(kw, multiple):
    out = _run([_sig()], **kw)
    assert out["final_multiple"] == pytest.approx(multiple)
    assert out["r_multiples_taken"] == [1.0]                 # R stays on the plan's stop
    assert out["notional_capped"] == (0 if multiple == 1.01 else 1)


def test_a_signal_without_stop_pct_is_never_capped():
    sig = _sig()
    del sig["stop_pct"]
    out = _run([sig], max_position_value=1000.0)
    assert (out["final_multiple"], out["notional_capped"]) == (pytest.approx(1.01), 0)


def test_heat_runs_on_the_cut_risk():
    signals = [_sig(), _sig("BBB")]                       # both open the same day
    assert _run(signals, heat_cap_pct=1.5)["trades_taken"] == 1
    out = _run(signals, heat_cap_pct=1.5, max_position_value=5000.0)   # 0.5% each
    assert out["trades_taken"] == 2


def test_skip_reasons_name_each_cap():
    two = [_sig(), _sig("BBB")]
    assert _run(two, heat_cap_pct=1.5, track_keys=True)["skip_reasons"] == {"heat": 1}
    sectors = {"AAA": "Tech", "BBB": "Tech"}
    out = portfolio_replay(two, throttles=False, sectors=sectors, sector_cap_pct=1.5,
                           track_keys=True)
    assert out["skip_reasons"] == {"sector": 1}
    assert _run(two, max_open=1, track_keys=True)["skip_reasons"] == {"max_open": 1}
    same = [_sig(), _sig(date="2021-01-05")]
    assert _run(same, track_keys=True)["skip_reasons"] == {"one_per_ticker": 1}


def test_the_cluster_callback_skips_and_sees_the_open_book():
    seen = []

    def cluster_fn(open_pos, sig, eff_risk):
        seen.append(([p["ticker"] for p in open_pos], sig["ticker"], eff_risk))
        return bool(open_pos)

    out = _run([_sig(), _sig("BBB")], cluster_fn=cluster_fn)
    assert (out["trades_taken"], out["skip_reasons"]) == (1, {"cluster": 1})
    assert seen == [([], "AAA", 1.0), (["AAA"], "BBB", 1.0)]


def test_taken_keys_follow_take_order_and_exits_free_capacity():
    signals = [_sig(), _sig("BBB"), _sig("CCC", date="2021-01-11", exit_date="2021-01-15")]
    out = _run(signals, max_open=1, track_keys=True)
    assert out["taken_keys"] == ["AAA|2021-01-04", "CCC|2021-01-11"]
    assert (out["trades_skipped"], out["notional_capped"]) == (1, 0)


def test_a_throttle_skip_is_named():
    out = portfolio_replay([_sig()], throttles=False, risk_pct=0.0, track_keys=True)
    assert (out["trades_skipped"], out["skip_reasons"]) == (1, {"throttle": 1})


def test_a_non_positive_stop_pct_is_never_capped():
    out = _run([_sig(stop_pct=-1.0)], max_position_value=1000.0)
    assert (out["final_multiple"], out["notional_capped"]) == (pytest.approx(1.01), 0)


def test_capacity_reasons_follow_fill_heat_order():
    two = [_sig(), _sig("BBB")]
    sectors = {"AAA": "Tech", "BBB": "Tech"}
    both = portfolio_replay(two, throttles=False, sectors=sectors, heat_cap_pct=1.5,
                            sector_cap_pct=1.5, track_keys=True)
    assert both["skip_reasons"] == {"heat": 1}             # heat before sector
    out = _run(two, max_open=1, cluster_fn=lambda o, s, r: bool(o))
    assert out["skip_reasons"] == {"cluster": 1}           # cluster before max_open
    out = _run(two, max_open=1, cluster_fn=lambda o, s, r: False)
    assert out["skip_reasons"] == {"max_open": 1}          # a False callback never skips


def test_skip_reasons_count_each_skip():
    three = [_sig(), _sig("BBB"), _sig("CCC")]
    assert _run(three, heat_cap_pct=1.5, track_keys=True)["skip_reasons"] == {"heat": 2}


def test_a_cap_equal_to_the_notional_cuts_nothing():
    out = _run([_sig()], max_position_value=10_000.0)      # notional is exactly $10k
    assert (out["final_multiple"], out["notional_capped"]) == (pytest.approx(1.01), 0)
