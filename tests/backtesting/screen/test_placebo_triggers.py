"""v230 A1: placebo triggers (causal), planted drift, cells and acceptance."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import placebo
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk

CAL = pd.bdate_range("2010-01-04", periods=600)


def test_trigger_registry_and_scopes():
    assert {n: t.scope for n, t in placebo.TRIGGERS.items()} == {
        "p_high20": "ticker", "p_rsi2_dip": "ticker", "p_gap_up": "ticker",
        "p_sweep20": "ticker", "p_market_down": "market", "p_month_turn": "market"}
    assert all(t.name == n for n, t in placebo.TRIGGERS.items())


@pytest.mark.parametrize("name", ["p_high20", "p_rsi2_dip", "p_gap_up", "p_sweep20",
                                  "p_market_down"])
def test_triggers_read_no_later_bar(name):
    df, index = random_walk(400, seed=11), random_walk(400, seed=12)
    trig = placebo.TRIGGERS[name]
    assert_prefix_stable(lambda d: trig.events(d, index.loc[d.index]), df, [250, 320, 399])


def test_month_turn_reads_only_the_next_session_date():
    trig = placebo.TRIGGERS["p_month_turn"]
    df = random_walk(120, seed=3)
    assert_prefix_stable(lambda d: trig.events(d, d), df, [40, 80], skip_last=True)
    flags = trig.events(df, df)
    month = df.index.year * 12 + df.index.month
    assert flags.to_numpy().tolist() == list(np.r_[month[1:] != month[:-1], True])


def test_high20_fires_on_a_close_above_the_prior_twenty_highs():
    df = frame([100.0] * 25 + [105.0, 105.0])          # High = Close + 1
    flags = placebo.TRIGGERS["p_high20"].events(df, df)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [25]


def test_sweep20_needs_the_low_under_and_the_close_back_above():
    lows = [99.0] * 25 + [97.0, 97.0]
    closes = [100.0] * 25 + [99.5, 98.0]
    df = frame(closes, lows=lows, highs=np.array(closes) + 1)
    flags = placebo.TRIGGERS["p_sweep20"].events(df, df)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [25]


def test_gap_up_compares_with_half_the_prior_atr():
    df = frame([100.0] * 30, opens=[100.0] * 29 + [101.0])   # ATR14 = 2 (High-Low)
    assert placebo.TRIGGERS["p_gap_up"].events(df, df).to_numpy()[-1]
    df = frame([100.0] * 30, opens=[100.0] * 29 + [100.99])
    assert not placebo.TRIGGERS["p_gap_up"].events(df, df).to_numpy()[-1]


def test_market_down_reads_the_index_not_the_ticker():
    idx = pd.bdate_range("2010-01-04", periods=40)
    closes = 100.0 * np.cumprod(np.r_[1.0, np.where(np.arange(39) % 2, 1.001, 0.999)])
    closes[30:] = closes[29] * 0.97
    index = frame(closes, index=idx)
    ticker = frame(np.full(40, 50.0), index=idx)
    flags = placebo.TRIGGERS["p_market_down"].events(ticker, index)
    assert np.flatnonzero(flags.to_numpy()).tolist() == [30]


def test_placebo_idea_is_one_frozen_long_next_open_race():
    index = random_walk(300, seed=2)
    idea = placebo.placebo_idea(placebo.TRIGGERS["p_month_turn"], index)
    assert (idea.name, idea.time_cap_bars, idea.direction, idea.race_shape, idea.entry,
            idea.scope, idea.context) == ("p_month_turn", 10, "long", "fixed", "next_open",
                                          "market", ())
    flags = idea.events(random_walk(300, seed=5))
    assert flags.dtype == bool and len(flags) == 300


def test_plant_drift_ramps_after_the_entry_open_and_keeps_gaps():
    df = frame(np.full(30, 100.0))
    events = np.zeros(30, dtype=bool)
    events[5] = True
    out = placebo.plant_drift(df, events, pd.Series(2.0, index=df.index))
    add_close = (out["Close"] - df["Close"]).to_numpy()
    add_open = (out["Open"] - df["Open"]).to_numpy()
    assert np.allclose(add_close[:6], 0.0) and np.allclose(add_open[:7], 0.0)
    assert add_close[6] == pytest.approx(0.1) and add_close[15] == pytest.approx(1.0)
    assert add_close[29] == pytest.approx(1.0) and add_open[16] == pytest.approx(1.0)
    assert np.allclose(add_open[7:], add_close[6:-1])          # gaps unchanged
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1)).all()
    assert (out["Low"] <= out[["Open", "Close"]].min(axis=1)).all()


def test_plant_universe_and_its_trigger(tmp_path):
    base = placebo.gbm_universe(tmp_path / "base", CAL, (0.01, 0.015, 0.02, 0.03), n_tickers=3)
    out = placebo.plant_universe(base, tmp_path / "planted")
    planted = json.loads((out / placebo.PLANTED_FILE).read_text(encoding="utf-8"))
    assert sorted(planted) == ["G000", "G001", "G002"] and any(planted.values())
    trig = placebo.planted_trigger(out)
    assert (trig.name, trig.scope) == ("p_high20_planted", "ticker")
    for t, days in planted.items():
        pos = placebo.read_frame(base / f"{t}.csv").index.get_indexer(pd.DatetimeIndex(days))
        assert (np.diff(pos) >= placebo.PLANT_SPACING).all()
        for root in (base, out):
            df = placebo.read_frame(root / f"{t}.csv")
            hits = df.index[trig.events(df, df).to_numpy()]
            assert [d.strftime("%Y-%m-%d") for d in hits] == days
    manifest = json.loads((out / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["kind"] == "planted" and manifest["base"] == "gbm"


def test_planted_value_is_the_mean_event_r_gain_on_shared_events():
    base = [{"ticker": "A", "entry_date": "2011-01-04", "r_event": 0.1},
            {"ticker": "A", "entry_date": "2011-02-01", "r_event": -1.0}]
    planted = [{"ticker": "A", "entry_date": "2011-01-04", "r_event": 0.5},
               {"ticker": "B", "entry_date": "2011-01-04", "r_event": 9.0}]
    assert placebo.planted_value(base, planted) == pytest.approx(0.4)
    assert placebo.planted_value(base, []) is None


@pytest.mark.parametrize("name", ["p_high20", "p_rsi2_dip", "p_gap_up", "p_sweep20",
                                  "p_market_down", "p_month_turn"])
def test_empty_trigger_returns_empty_boolean_series(name):
    df = frame([])
    flags = placebo.TRIGGERS[name].events(df, df)
    assert flags.empty and flags.dtype == bool


def test_rsi2_dip_requires_warmed_up_uptrend():
    rising = np.arange(100.0, 305.0)
    rising[-3:] = [299.0, 296.0, 293.0]
    df = frame(rising)
    flags = placebo.TRIGGERS["p_rsi2_dip"].events(df, df)
    assert not flags.iloc[:200].any()
    assert flags.iloc[-1]
    falling = frame(np.arange(305.0, 100.0, -1))
    assert not placebo.TRIGGERS["p_rsi2_dip"].events(falling, falling).any()


def test_plant_drift_skips_nonfinite_atr_and_terminal_events_without_mutating():
    df = frame(np.full(30, 100.0))
    original = df.copy(deep=True)
    events = np.zeros(30, dtype=bool)
    events[[3, 29]] = True
    atr = pd.Series(2.0, index=df.index)
    atr.iloc[3] = np.nan
    pd.testing.assert_frame_equal(placebo.plant_drift(df, events, atr), original)
    pd.testing.assert_frame_equal(df, original)


def test_planted_trigger_rejects_colliding_tickers(tmp_path):
    df = frame(np.full(30, 100.0))
    base = placebo.write_universe(tmp_path / "base", {"A": df, "B": df},
                                  kind="gbm", meta={})
    out = placebo.plant_universe(base, tmp_path / "out")
    with pytest.raises(ValueError, match="collide"):
        placebo.planted_trigger(out)


def test_planted_trigger_unknown_frame_has_no_events(tmp_path):
    base = placebo.gbm_universe(tmp_path / "base", CAL, (0.02,), n_tickers=1)
    out = placebo.plant_universe(base, tmp_path / "out")
    trigger = placebo.planted_trigger(out)
    df = frame(np.full(30, 1.0))
    assert not trigger.events(df, df).any()


def test_plant_metadata_is_atomic_and_precedes_manifest(tmp_path, monkeypatch):
    base = placebo.gbm_universe(tmp_path / "base", CAL, (0.02,), n_tickers=1)
    out = tmp_path / "out"
    replace = type(out).replace

    def observe_replace(path, target):
        target = type(out)(target)
        if target.name == placebo.MANIFEST_FILE:
            assert (out / placebo.PLANTED_FILE).is_file()
            assert not (out / (placebo.PLANTED_FILE + ".tmp")).exists()
            assert sorted(json.loads((out / placebo.PLANTED_FILE).read_text())) == ["G000"]
        return replace(path, target)

    monkeypatch.setattr(type(out), "replace", observe_replace)
    placebo.plant_universe(base, out)
    assert (out / placebo.MANIFEST_FILE).is_file()


def test_failed_plant_metadata_invalidates_existing_completion(tmp_path, monkeypatch):
    base = placebo.gbm_universe(tmp_path / "base", CAL, (0.02,), n_tickers=1)
    out = placebo.plant_universe(base, tmp_path / "out")
    replace = type(out).replace

    def fail_metadata(path, target):
        if type(out)(target).name == placebo.PLANTED_FILE:
            raise OSError("metadata interrupted")
        return replace(path, target)

    monkeypatch.setattr(type(out), "replace", fail_metadata)
    with pytest.raises(OSError, match="metadata interrupted"):
        placebo.plant_universe(base, out)
    assert not (out / placebo.MANIFEST_FILE).exists()
    assert not (out / (placebo.PLANTED_FILE + ".tmp")).exists()


def _cell(delta, low, high, n=500, trigger="p_high20"):
    return placebo.Cell("gbm-200", trigger, "v2", n, 0.1, 0.1 - (delta or 0.0),
                        delta, low, high)


def test_cell_from_rows_and_round_trip():
    rows = [{"ticker": "A", "entry_date": f"2011-{m:02d}-03", "r_event": 0.3,
             "r_null": 0.1} for m in range(1, 13)]
    cell = placebo.cell_from_rows("gbm-200", "p_high20", "v1", rows, n_resamples=200)
    assert (cell.universe, cell.trigger, cell.null) == ("gbm-200", "p_high20", "v1")
    assert (cell.n, cell.mean_r_event, cell.mean_r_null) == (
        12, pytest.approx(0.3), pytest.approx(0.1))
    assert cell.delta == pytest.approx(0.2)
    assert (cell.ci_low, cell.ci_high) == (pytest.approx(0.2), pytest.approx(0.2))
    assert cell.half_width == pytest.approx(0.0)
    assert placebo.Cell.from_dict(json.loads(json.dumps(cell.to_dict()))) == cell


def test_empty_cell_has_no_estimate_and_requires_enlargement():
    cell = placebo.cell_from_rows("gbm-200", "p_high20", "v1", [])
    assert (cell.n, cell.mean_r_event, cell.mean_r_null, cell.delta,
            cell.ci_low, cell.ci_high, cell.half_width) == (0, None, None, None,
                                                          None, None, None)
    assert placebo.accept_cell(cell) == "NOISY"
    assert not placebo.planted_recovered(cell, 0.0)
    assert not placebo.v1_premise_holds([cell])
    assert placebo.Cell.from_dict(json.loads(json.dumps(cell.to_dict()))) == cell


def test_cell_interval_resamples_whole_weeks_not_individual_events():
    rows = [{"ticker": "A", "entry_date": "2011-01-03T09:30:00", "r_event": 2.0,
             "r_null": 1.0},
            {"ticker": "B", "entry_date": "2011-01-04T09:30:00", "r_event": 1.0,
             "r_null": 2.0}]
    cell = placebo.cell_from_rows("gbm-200", "p_high20", "v2", rows,
                                  n_resamples=200, seed=7)
    assert (cell.n, cell.mean_r_event, cell.mean_r_null) == (2, 1.5, 1.5)
    assert (cell.delta, cell.ci_low, cell.ci_high) == (0.0, 0.0, 0.0)
    rows[1]["entry_date"] = "2011-01-10T09:30:00"
    split = placebo.cell_from_rows("gbm-200", "p_high20", "v2", rows,
                                   n_resamples=200, seed=7)
    assert (split.delta, split.ci_low, split.ci_high) == (0.0, -1.0, 1.0)


@pytest.mark.parametrize("delta, low, high, expected", [
    (0.02, 0.0, 0.04, "PASS"),
    (-0.02, -0.04, 0.0, "PASS"),
    (0.020000000000000004, 0.0, 0.04000000000000001, "PASS"),
    (0.03, 0.01, 0.05, "FAIL"),
    (0.0201, 0.0001, 0.0401, "FAIL"),
    (0.0, -0.0201, 0.0201, "NOISY"),
    (0.3, 0.21, 0.39, "FAIL"),
    (-0.3, -0.39, -0.21, "FAIL"),
    (0.03, -0.02, 0.08, "NOISY"),
    (0.06, 0.02, 0.10, "NOISY"),
    (-0.06, -0.10, -0.02, "NOISY"),
    (None, None, None, "NOISY"),
    (0.0, None, 0.01, "NOISY"),
    (0.0, -0.01, None, "NOISY"),
])
def test_accept_cell_boundaries(delta, low, high, expected):
    assert placebo.accept_cell(_cell(delta, low, high)) == expected


def test_accept_cell_without_events_is_noisy_even_with_estimates():
    assert placebo.accept_cell(_cell(0.3, 0.29, 0.31, n=0)) == "NOISY"


def test_v1_premise_holds_only_past_the_tolerance():
    calm = [_cell(0.02, 0.0, 0.04), _cell(-0.02, -0.04, 0.0)]
    assert placebo.v1_premise_holds(calm) is False
    assert placebo.v1_premise_holds(calm + [_cell(-0.0201, -0.05, 0.0)]) is True
    assert placebo.v1_premise_holds([_cell(0.020000000000000004, 0.0, 0.04)]) is False
    assert placebo.v1_premise_holds([]) is False


def test_planted_recovered_is_interval_containment():
    cell = _cell(0.3, 0.28, 0.32)
    assert placebo.planted_recovered(cell, 0.28)
    assert placebo.planted_recovered(cell, 0.32)
    assert placebo.planted_recovered(cell, 0.32000000000000006)
    assert not placebo.planted_recovered(cell, 0.3201)
    assert not placebo.planted_recovered(cell, 0.2799)
    assert not placebo.planted_recovered(cell, None)


def test_acceptance_verdicts():
    good, planted = [_cell(0.0, -0.01, 0.01)], _cell(0.3, 0.29, 0.31)
    assert placebo.acceptance(good, planted, 0.3)["verdict"] == "ACCEPT"
    assert placebo.acceptance(good + [_cell(0.05, 0.04, 0.06)], planted, 0.3)["verdict"] == "STOP"
    assert placebo.acceptance(good + [_cell(0.0, -0.03, 0.03)], planted, 0.3)["verdict"] == "ENLARGE"
    assert placebo.acceptance(good, planted, 0.35)["verdict"] == "STOP"
    assert placebo.acceptance(good, _cell(0.3, 0.2, 0.4), 0.3)["verdict"] == "ENLARGE"
    assert placebo.acceptance(good, None, None)["verdict"] == "ENLARGE"
    out = placebo.acceptance(good, planted, 0.3)
    assert out["cells"] == {"gbm-200/p_high20": "PASS"}
    assert out["planted"] == {"recovered": True, "value": 0.3,
                              "cell": planted.to_dict(), "noisy": False}
    with pytest.raises(ValueError, match="no cells"):
        placebo.acceptance([], planted, 0.3)


def test_acceptance_failure_precedes_missing_or_noisy_planted_cell():
    failed = [_cell(0.3, 0.21, 0.39)]
    assert placebo.acceptance(failed, None, None)["verdict"] == "STOP"
    noisy = _cell(0.3, 0.2, 0.4)
    assert placebo.acceptance(failed, noisy, 0.3)["verdict"] == "STOP"
    duplicate = failed + [_cell(0.0, -0.01, 0.01)]
    assert placebo.acceptance(duplicate, None, None)["verdict"] == "STOP"


@pytest.mark.parametrize("planted, value, expected", [
    ((0.3, 0.28, 0.32), 0.32, "ACCEPT"),
    ((0.3, 0.28, 0.32), None, "STOP"),
    ((0.3, 0.29, 0.31, 0), 0.3, "ENLARGE"),
    ((None, None, None), 0.3, "ENLARGE"),
    ((0.3, 0.2, 0.4), 0.5, "ENLARGE"),
])
def test_acceptance_planted_boundaries(planted, value, expected):
    assert placebo.acceptance([_cell(0.0, -0.01, 0.01)], _cell(*planted), value)["verdict"] == expected
