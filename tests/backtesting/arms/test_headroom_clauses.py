# tests/backtesting/arms/test_headroom_clauses.py
"""v135 frozen clause-6 reading: mechanism on the BASELINE arm, flagged vs unflagged."""
import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import dryup_clauses
from swingbot.core.backtesting.arms import headroom_clauses as hc
from swingbot.core.backtesting.arms.engine import run_arm
from tests.backtesting.test_v74_fixture import load_v74_fixture

WINDOW = ("1900-01-01", "2100-12-31")
NEAR, FAR, CLEAR = hc.Reading((0.5, 2.0), 4), hc.Reading((3.0, 2.0), 4), hc.Reading(None, 4)


def _t(i, outcome, strategy="Fibonacci", source="strategy", ticker="T"):
    return ArmTrade(ticker, strategy, "4w", f"2019-02-{i + 1:02d}", outcome,
                    2.0 if outcome == "win" else -1.0, 2.0, source, "bullish")


def test_flagged_losers_pass_flagged_winners_fail():
    baseline = [_t(i, "win" if i < 4 else "loss") for i in range(10)]
    losers = {t.key for t in baseline[8:]}
    winners = {t.key for t in baseline[:2]}
    assert hc.baseline_mechanism(baseline, losers, "strategy").verdict == "PASS"
    assert hc.baseline_mechanism(baseline, winners, "strategy").verdict == "FAIL"
    assert hc.baseline_mechanism(baseline, set(), "strategy").verdict == "FAIL"   # nothing flagged
    assert hc.baseline_mechanism(baseline, losers, "strategy").name == "mechanism"


def test_out_of_scope_trades_are_in_neither_group():
    # In-scope flagged: 1 win + 1 loss (WR 50%). In-scope unflagged: all losses, so the
    # in-scope reading FAILS. If the MACD or confluence winners leaked into "retained" they
    # would lift retained WR above 50% and flip it to a wrong PASS.
    flagged_pair = [_t(0, "win"), _t(1, "loss")]
    unflagged = [_t(i, "loss") for i in range(2, 6)]
    macd = [_t(i, "win", strategy="MACD") for i in range(6, 16)]
    confluence = [_t(i, "win", strategy="confluence", source="confluence") for i in range(16, 26)]
    baseline = flagged_pair + unflagged + macd + confluence
    assert hc.baseline_mechanism(baseline, {t.key for t in flagged_pair}, "strategy").verdict == "FAIL"


@pytest.mark.parametrize("strategy,source,scope,expected", [
    ("Fibonacci", "strategy", "strategy", True),
    ("MACD", "strategy", "strategy", False),
    ("Volume Profile", "strategy", "strategy", False),
    ("Fibonacci", "strategy", "confluence", False),
    ("confluence", "confluence", "confluence", True),
    ("confluence", "confluence", "strategy", False),
])
def test_in_scope_keeps_the_two_components_apart(strategy, source, scope, expected):
    assert hc.in_scope(_t(0, "win", strategy=strategy, source=source), scope) is expected


def test_flags_use_the_gate_comparison_strictly():
    readings = {"at": hc.Reading((1.0, 2.0), 3), "in": hc.Reading((0.99, 2.0), 3),
                "clear": CLEAR, "missing": None}
    assert hc.flagged_keys(readings, 0.5) == {"in"}        # 1.0 is exactly 0.5 x 2.0: not inside
    assert hc.flagged_keys(readings, 0.75) == {"at", "in"}
    assert hc.flagged_keys(readings, 0.0) == set()


def test_no_map_share_counts_empty_maps_and_unreproduced_trades():
    readings = {"a": NEAR, "b": hc.Reading(None, 0), "c": None, "d": CLEAR}
    assert hc.no_map_share(readings, "strategy") == {
        "scope": "strategy", "n": 4, "no_map": 1, "unreadable": 1,
        "share": 0.25, "unreadable_share": 0.25}
    assert hc.no_map_share({}, "confluence")["share"] is None


def test_knob_context_and_window_read_the_stamp():
    blob = {"provenance": {"knob_delta": {"HEADROOM_SCOPE": "confluence", "HEADROOM_MIN_R": 0.75},
                           "signal_window": ["2018-06-01", "2022-12-31"]}}
    assert hc.knob_context(blob) == ("confluence", 0.75)
    assert hc.signal_window(blob) == ("2018-06-01", "2022-12-31")
    for delta in ({"MIN_REWARD_PCT": 4.0}, {"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.75},
                  {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": 0.0},
                  {"HEADROOM_SCOPE": "strategy", "HEADROOM_MIN_R": True},
                  {"HEADROOM_SCOPE": "strategy"}):
        assert hc.knob_context({"provenance": {"knob_delta": delta}}) is None


def test_scoped_readings_replay_each_cell_once_and_reuse_the_cache(monkeypatch):
    trades = [_t(0, "win"), _t(1, "loss"), _t(2, "loss", strategy="RSI"),
              _t(3, "win", strategy="MACD"), _t(4, "win", ticker="GONE")]
    calls, frames, ticks = [], [], []

    def fake_cell(ticker, frame, strategy, horizon_key, window, params):
        calls.append((ticker, strategy, horizon_key, window))
        return {t.key: NEAR for t in trades[:3] if t.strategy == strategy and t.entry_date != "2019-02-02"}

    def frame_for(ticker):
        frames.append(ticker)
        return None if ticker == "GONE" else object()
    monkeypatch.setattr(hc, "strategy_cell_readings", fake_cell)
    cache = {}
    readings = hc.scoped_readings(trades, frame_for, "strategy", WINDOW, cache=cache,
                                  progress=lambda done, total: ticks.append((done, total)))
    assert set(readings) == {t.key for t in (trades[0], trades[1], trades[2], trades[4])}
    assert readings[trades[0].key] == NEAR
    assert readings[trades[1].key] is None            # the replay did not reproduce it
    assert readings[trades[4].key] is None            # no cached frame for the ticker
    assert sorted(calls) == [("T", "Fibonacci", "4w", WINDOW), ("T", "RSI", "4w", WINDOW)]
    assert ticks == [(1, 2), (2, 2)]
    hc.scoped_readings(trades, frame_for, "strategy", WINDOW, cache=cache)
    assert len(calls) == 2                             # second pass served from the cache


def test_the_shared_mechanism_scorer_is_v122s_own():
    assert dryup_clauses.mechanism_result is dryup_clauses._mechanism_result


@pytest.fixture(scope="module")
def frame():
    return load_v74_fixture()["AAPL"]


@pytest.mark.slow
def test_strategy_readings_reproduce_every_scoped_baseline_trade(frame):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    scoped = [t for t in base if hc.in_scope(t, "strategy")]
    assert scoped, "fixture must hold in-scope strategy trades or the test proves nothing"
    readings = hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW)
    assert set(readings) == {t.key for t in scoped}
    assert all(reading is not None for reading in readings.values())
    assert any(reading.n_levels > 0 for reading in readings.values())


@pytest.mark.slow
def test_confluence_readings_reproduce_every_baseline_trade(frame):
    base = run_arm("AAPL", frame, ("confluence",), ("4w",), WINDOW, {})
    assert base, "fixture must hold confluence trades or the test proves nothing"
    readings = hc.scoped_readings(base, lambda ticker: frame, "confluence", WINDOW)
    assert set(readings) == {t.key for t in base}
    assert all(reading is not None and reading.n_levels > 0 for reading in readings.values())


@pytest.mark.slow
def test_the_reading_replays_the_baseline_even_when_the_operator_has_the_gate_on(frame, monkeypatch):
    base = run_arm("AAPL", frame, ("strategy",), ("4w",), WINDOW, {})
    clean = hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW)
    monkeypatch.setattr(config, "HEADROOM_SCOPE", "strategy")
    monkeypatch.setattr(config, "HEADROOM_MIN_R", 1.0)
    assert hc.scoped_readings(base, lambda ticker: frame, "strategy", WINDOW) == clean
    assert config.HEADROOM_SCOPE == "strategy" and config.HEADROOM_MIN_R == 1.0   # restored
