"""V180-8: the Turtle Soup diagnostics. Signal rows join the engine's events (V180-7) with the sweep
geometry and the screen's own race; the blocks are descriptive and never gate. The world is V180-7's."""
import json

import numpy as np
import pytest

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import turtle_soup_report as rep
from swingbot.core.backtesting.screen import race as screen_race
from swingbot.core.backtesting.screen.ideas import turtle_soup as screen_idea
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.scan_params import ScanParams
from tests.backtesting.test_turtle_soup_engine import (FULL_PATH, PILOT, SIGNAL_DAY, SIGNAL_POS, TARGET,
                                                        path, pin_world)
from tests.helpers import make_ohlcv

ALWAYS = {"TS1": [("2000-01-01", "9999-12-31")]}


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    pin_world(monkeypatch)


def _params():
    return ScanParams.from_config()


def _measure(frame=FULL_PATH, intervals=ALWAYS, spy=None):
    return rep.measure({"TS1": frame}, PILOT, _params(), spy=spy, intervals=intervals)


def test_constants():
    assert (rep.EARLY_STOP_SESSIONS, rep.SCREEN_CAP, rep.BADGE_MIN_N) == (2, 10, 15)
    assert rep.SCREEN_CAP == screen_idea.CAP
    assert rep.STATUSES == ("trade", "risk_cap", "no_level_in_band", "plan_other",
                            "cancelled_open_through_stop", "cancelled_risk_cap_fill",
                            "not_triggered", "position_open")


def test_a_trade_row_carries_geometry_event_and_screen_race():
    measured = _measure()
    (row,) = measured["rows"]
    atr_t = float(atr(FULL_PATH.iloc[:SIGNAL_POS + 1], 14).iloc[-1])
    assert (row["ticker"], row["signal_date"], row["signal_index"], row["status"]) == \
        ("TS1", SIGNAL_DAY, SIGNAL_POS, "trade")
    assert (row["prior_low"], row["low"]) == (98.0, 97.6)
    assert row["atr14"] == pytest.approx(atr_t)
    assert row["sweep_depth_atr"] == pytest.approx((98.0 - 97.6) / atr_t)
    assert row["tp1"] == TARGET and row["exit_reason"] == "tp1" and row["r_net"] < row["r_gross"]
    raced = screen_race.race(FULL_PATH, [SIGNAL_POS], rep.SCREEN_CAP)
    assert row["screen_outcome"] == str(raced.outcome[0]) == "target"
    assert row["screen_r"] == pytest.approx(float(raced.r[0]))
    assert measured["signals"] == 1 and measured["trades"] == 1
    assert measured["exit_mix"] == {"n": 1, "win_rate": 100.0, "shares": {
        "target": 1.0, "stop": 0.0, "gap": 0.0, "time_cap": 0.0, "other": 0.0}}
    assert measured["early_stop_share"] == 0.0
    assert measured["universe"] == {"n": 1, "outside_sp500": 0, "share": 0.0}


def test_the_sidecar_record_is_json_serialisable():
    json.dumps(_measure())


def test_an_open_through_the_stop_is_listed_as_its_cancel():
    (row,) = _measure(frame=path(fill_open=97.0))["rows"]
    assert row["status"] == "cancelled_open_through_stop" and "entry_date" not in row


@pytest.mark.parametrize("resistances", [(), (110.0,)])
def test_a_plan_none_is_split_into_no_level_in_band(monkeypatch, resistances):
    pin_world(monkeypatch, resistances)
    (row,) = _measure()["rows"]
    assert row["status"] == "no_level_in_band"


def test_a_wide_sweep_stop_is_listed_as_risk_cap():
    frame = FULL_PATH.copy()
    frame.iloc[SIGNAL_POS, frame.columns.get_loc("Low")] = 96.0     # stop ~95.7: > 3% from the 99.9 close
    measured = _measure(frame=frame)
    (row,) = measured["rows"]
    assert row["status"] == "risk_cap"
    assert measured["drops"]["by_status"]["risk_cap"]["count"] == 1
    assert measured["drops"]["by_status"]["risk_cap"]["share"] == 1.0


def test_a_signal_inside_an_open_trade_is_listed_as_position_open():
    (row,) = rep.signal_rows("TS1", FULL_PATH, [], PILOT, params=_params())
    assert row["status"] == "position_open" and row["signal_date"] == SIGNAL_DAY


def test_signals_outside_the_window_and_short_frames_have_no_row():
    assert rep.signal_rows("TS1", FULL_PATH, [], ("2019-03-15", "2020-12-31"), params=_params()) == []
    assert rep.signal_rows("TS1", FULL_PATH.iloc[:29], [], PILOT, params=_params()) == []


def test_a_last_bar_signal_reads_no_later_bar():
    event = {"ticker": "TS1", "signal_date": SIGNAL_DAY, "status": "not_triggered"}
    (cut,) = rep.signal_rows("TS1", FULL_PATH.iloc[:SIGNAL_POS + 1], [event], PILOT, params=_params())
    (full,) = rep.signal_rows("TS1", FULL_PATH, [event], PILOT, params=_params())
    assert cut["status"] == "not_triggered"
    assert (cut["screen_outcome"], cut["screen_r"]) == (None, None)
    for key in ("prior_low", "low", "atr14", "sweep_depth_atr"):
        assert cut[key] == pytest.approx(full[key])


def test_screen_outcomes_skips_a_race_that_would_read_past_the_frame():
    assert set(rep.screen_outcomes(FULL_PATH, [SIGNAL_POS, len(FULL_PATH) - 3])) == {SIGNAL_POS}
    assert rep.screen_outcomes(FULL_PATH, []) == {}


def _row(status, depth=0.5, screen=(None, None), **extra):
    return {"ticker": extra.pop("ticker", "TS1"), "signal_date": extra.pop("signal_date", "2019-01-02"),
            "status": status, "sweep_depth_atr": depth,
            "screen_outcome": screen[0], "screen_r": screen[1], **extra}


def test_drop_shares_reports_every_status_with_its_screen_race():
    rows = [_row("trade", screen=("target", 1.9)), _row("risk_cap", screen=("stop", -1.03)),
            _row("risk_cap"), _row("no_level_in_band", screen=("timeout", 0.2))]
    drops = rep.drop_shares(rows)
    assert drops["signals"] == 4 and set(drops["by_status"]) == set(rep.STATUSES)
    assert drops["by_status"]["risk_cap"] == {"count": 2, "share": 0.5, "screen": {
        "raced": 1, "expectancy_r": pytest.approx(-1.03), "win_rate": 0.0, "outcomes": {"stop": 1}}}
    assert drops["by_status"]["no_level_in_band"]["screen"]["win_rate"] is None
    assert drops["by_status"]["plan_other"] == {"count": 0, "share": 0.0, "screen": {
        "raced": 0, "expectancy_r": None, "win_rate": None, "outcomes": {}}}
    assert rep.drop_shares([])["by_status"]["trade"]["share"] is None


def test_sweep_depth_splits_kept_and_dropped():
    rows = [_row("trade", 0.1), _row("trade", 0.3), _row("risk_cap", 1.0),
            _row("cancelled_risk_cap_fill", 2.0), _row("position_open", 9.0)]
    summary = rep.sweep_depth_summary(rows)
    assert summary["kept"]["n"] == 2 and summary["kept"]["mean"] == pytest.approx(0.2)
    assert summary["dropped"]["n"] == 2 and summary["dropped"]["max"] == 2.0
    assert summary["all"]["n"] == 5 and summary["all"]["median"] == pytest.approx(1.0)
    assert rep.sweep_depth_summary([])["kept"] == {
        "n": 0, "mean": None, "p25": None, "median": None, "p75": None, "max": None}


def _trade(reason, outcome, hold=4, r=1.0, **extra):
    return _row("trade", exit_reason=reason, outcome=outcome, hold_sessions=hold, r_net=r, **extra)


def test_early_stops_and_exit_mix():
    rows = [_trade("stop", "loss", hold=1, r=-1.0), _trade("gap_stop", "loss", hold=2, r=-1.4),
            _trade("stop", "loss", hold=3, r=-1.0), _trade("tp1", "win", r=1.8),
            _trade("time_exit", "timeout", hold=10, r=0.3), _trade("gap_target", "scratch", hold=1, r=0.0),
            _trade("acceptance_exit", "loss", hold=5, r=-0.6), _row("risk_cap")]
    assert rep.early_stop_share(rows) == pytest.approx(2 / 7)
    mix = rep.exit_mix(rows)
    assert mix["n"] == 7 and mix["win_rate"] == pytest.approx(100 * 1 / 5)
    assert mix["shares"] == pytest.approx(
        {"target": 1 / 7, "stop": 2 / 7, "gap": 2 / 7, "time_cap": 1 / 7, "other": 1 / 7})
    assert rep.early_stop_share([_row("risk_cap")]) is None
    assert rep.exit_mix([])["win_rate"] is None


def test_regime_split_reads_spy_against_its_200_day_sma_on_the_signal_day():
    spy = make_ohlcv([100.0] * 200 + [120.0] * 20 + [80.0] * 30, start="2018-01-02")

    def day(i):
        return spy.index[i].date().isoformat()

    rows = [_trade("tp1", "win", r=1.8, signal_date=day(205)),     # 120 > SMA200 100.6
            _trade("stop", "loss", r=-1.0, signal_date=day(240)),  # 80 < SMA200 99.9
            _trade("tp1", "win", r=2.0, signal_date=day(100))]     # SMA200 not warm yet
    split = rep.regime_split(rows, spy)
    assert split["above"] == {"n": 1, "expectancy_r": 1.8, "win_rate": 100.0}
    assert split["below"] == {"n": 1, "expectancy_r": -1.0, "win_rate": 0.0}
    assert split["unknown"]["n"] == 1
    assert rep.regime_split(rows, None)["unknown"]["n"] == 3


def test_clustering_counts_signals_per_day():
    rows = [_row("trade", signal_date="2019-01-02")] * 3 + [_row("risk_cap", signal_date="2019-01-03")]
    assert rep.clustering(rows) == {"days": 2, "max": 3, "p95": pytest.approx(float(np.percentile([3, 1], 95)))}
    assert rep.clustering([]) == {"days": 0, "max": 0, "p95": None}


def test_universe_share_counts_added_trades_outside_the_sp500():
    rows = [_trade("tp1", "win", ticker="TS1"), _trade("tp1", "win", ticker="ZZZ"), _row("risk_cap", ticker="ZZZ")]
    assert rep.universe_share(rows, ALWAYS) == {"n": 2, "outside_sp500": 1, "share": 0.5}


@pytest.mark.parametrize("intervals", [{}, None])
def test_universe_share_is_unknown_without_membership_data(intervals):
    rows = [_trade("tp1", "win")]
    assert rep.universe_share(rows, intervals) == {"n": 1, "outside_sp500": None, "share": None}


def _arm(outcomes):
    return [ArmTrade(f"T{i}", TURTLE_SOUP, "2w", "2024-03-01", outcome, r, 2.0, direction="bullish")
            for i, (outcome, r) in enumerate(outcomes)]


def test_badge_check_passes_on_the_floor():
    badge = rep.badge_check(_arm([("win", 1.8)] * 8 + [("loss", -1.0)] * 7))
    assert badge["verdict"] == "PASS" and badge["n"] == 15 and badge["min_n"] == 15
    assert badge["win_rate"] == pytest.approx(100 * 8 / 15)
    assert badge["clauses"] == {"win_rate": True, "expectancy_r": True, "n": True, "scratch_timeout_share": True}


@pytest.mark.parametrize("outcomes, failing", [
    ([("win", 1.8)] * 7 + [("loss", -1.0)] * 7, "n"),                              # 14 decided
    ([("win", 1.8)] * 7 + [("loss", -1.0)] * 8, "win_rate"),                       # 46.7%
    ([("win", 0.5)] * 8 + [("loss", -1.0)] * 7, "expectancy_r"),
    ([("win", 1.8)] * 8 + [("loss", -1.0)] * 7 + [("timeout", 0.1)] * 10 + [("scratch", 0.0)] * 6,
     "scratch_timeout_share"),                                                      # 16 of 31 closed
])
def test_badge_check_fails_each_clause(outcomes, failing):
    badge = rep.badge_check(_arm(outcomes))
    assert badge["verdict"] == "FAIL" and badge["clauses"][failing] is False


def test_badge_check_respects_min_n():
    assert rep.badge_check(_arm([("win", 1.8)] * 2 + [("loss", -1.0)]), min_n=3)["clauses"]["n"] is True
