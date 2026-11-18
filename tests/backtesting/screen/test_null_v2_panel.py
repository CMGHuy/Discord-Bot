"""v230 A2 stage 1: the v2 panel, the dates x tickers cross-section and the
stage checkpoints. Every panel value at bar t reads bars <= t, except race
completeness (pos + cap <= n - 1), exactly as v1."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, null, null_v2
from swingbot.core.backtesting.screen import race as race_mod
from tests.backtesting.screen.helpers import assert_prefix_stable, random_walk

CAP = 10
QUIET = {"out": lambda *a, **k: None}


def _ctx(df, condition=None):
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    prior_high = df["High"].shift(1).rolling(20).max()
    ctx = {"raw": (df["Close"] > prior_high).to_numpy(dtype=bool),
           "member": np.ones(len(df), dtype=bool),
           "warm": race_mod.warm_mask(atr, sma200), "atr": atr,
           "trend": null.trend_state(df, sma200)}
    if condition is not None:
        ctx["condition"] = condition
    return ctx


def _panel(df, **kw):
    return null_v2.ticker_panel("AAA", df, _ctx(df), cap=CAP, **kw)


def test_panel_copies_v1_eligibility_trend_events_and_atr_pct():
    df = random_walk(600, seed=3)
    ctx = _ctx(df)
    p = null_v2.ticker_panel("AAA", df, ctx, cap=CAP)
    assert p.ticker == "AAA"
    assert (p.dates == df.index.to_numpy()).all()
    assert (p.event == ctx["raw"]).all()
    assert (p.trend == ctx["trend"]).all()
    expected = null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], CAP)
    assert (p.eligible == expected).all()
    assert not p.eligible[p.event].any()
    assert p.atr_pct[400] == pytest.approx(ctx["atr"].iloc[400] / df["Close"].iloc[400])
    assert p.control is None and p.level_bars is None


def test_avoid_condition_leaves_the_pool_and_control_is_stored():
    df = random_walk(600, seed=3)
    base = _panel(df)
    bar = int(np.flatnonzero(base.eligible)[0])
    condition = np.zeros(len(df), dtype=bool)
    condition[bar] = True
    control = np.arange(len(df)) % 2 == 0
    p = null_v2.ticker_panel("AAA", df, _ctx(df, condition), cap=CAP, control=control)
    assert not p.eligible[bar]
    assert (p.eligible == (base.eligible & ~condition)).all()
    assert (p.control == control).all()


def test_level_bars_hold_open_high_low_and_the_previous_atr():
    df = random_walk(600, seed=3)
    atr = indicators.atr(df).to_numpy()
    bars = _panel(df, keep_bars=True).level_bars
    assert bars.shape == (len(df), 4)
    assert np.isnan(bars[0, 3])
    assert bars[300].tolist() == pytest.approx(
        [df["Open"].iloc[300], df["High"].iloc[300], df["Low"].iloc[300], atr[299]])


@pytest.mark.parametrize("field", ["trend", "atr_pct", "event"])
def test_panel_values_read_no_later_bar(field):
    df = random_walk(600, seed=5)
    assert_prefix_stable(lambda d: getattr(_panel(d), field).astype(float), df, [250, 333, 480, 599])


def test_eligibility_changes_under_truncation_only_through_completeness():
    df = random_walk(600, seed=5)
    full = _panel(df).eligible
    for t in (250, 333, 480):
        part = _panel(df.iloc[: t + 1]).eligible
        complete = np.arange(t + 1) + CAP <= t
        assert (part == (full[: t + 1] & complete)).all()


def test_terciles_cut_on_eligible_values_and_place_every_finite_ticker():
    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 2.5, np.nan]) / 100
    eligible = np.array([True] * 9 + [False, False])
    assert null_v2.atr_terciles(values, eligible).tolist() == [
        0, 0, 0, 1, 1, 1, 2, 2, 2, 0, -1]


def test_terciles_without_an_eligible_ticker_are_all_off():
    out = null_v2.atr_terciles(np.array([0.01, 0.02]), np.array([False, False]))
    assert out.dtype == np.int8 and out.tolist() == [-1, -1]


def _bare(ticker, dates, atr, control=None):
    n = len(dates)
    return null_v2.TickerPanel(ticker, pd.DatetimeIndex(dates).to_numpy(),
                               np.ones(n, dtype=bool), np.ones(n, dtype=bool),
                               np.full(n, atr), np.zeros(n, dtype=bool), control)


def test_cross_section_unions_dates_sorts_tickers_and_marks_absent_bars():
    days = pd.bdate_range("2015-01-05", periods=4)
    panels = {"BBB": _bare("BBB", days[1:], 0.02), "AAA": _bare("AAA", days, 0.01),
              "CCC": _bare("CCC", days[:3], 0.03)}
    xs = null_v2.cross_section(panels)
    assert xs.tickers == ("AAA", "BBB", "CCC")
    assert list(xs.dates) == list(days)
    assert xs.pos[:, 1].tolist() == [-1, 0, 1, 2]
    assert xs.pos[:, 2].tolist() == [0, 1, 2, -1]
    assert not xs.eligible[0, 1] and not xs.eligible[3, 2]
    assert xs.tercile[1].tolist() == [0, 1, 2]
    assert xs.tercile[0, 1] == -1
    assert xs.control is None


def test_cross_section_control_defaults_false_for_panels_without_one():
    days = pd.bdate_range("2015-01-05", periods=3)
    panels = {"AAA": _bare("AAA", days, 0.01, control=np.array([True, False, True])),
              "BBB": _bare("BBB", days, 0.02)}
    xs = null_v2.cross_section(panels)
    assert xs.control[:, 0].tolist() == [True, False, True]
    assert not xs.control[:, 1].any()


def test_cross_section_of_nothing_is_empty():
    xs = null_v2.cross_section({})
    assert xs.tickers == () and len(xs.dates) == 0 and xs.pos.shape == (0, 0)


def test_stage_checkpoint_round_trips_atomically_and_lists_done_keys(tmp_path):
    cp = null_v2.StageCheckpoint(tmp_path)
    assert cp.load("BRK.B") is None and cp.done() == set()
    cp.save("BRK.B", {"x": 1})
    assert cp.load("BRK.B") == {"x": 1}
    assert cp.done() == {"BRK.B"}
    assert not list(tmp_path.glob("*.tmp"))


def test_stage_checkpoint_without_a_directory_is_a_no_op():
    cp = null_v2.StageCheckpoint(None)
    cp.save("AAA", 1)
    assert cp.load("AAA") is None and cp.done() == set()


def test_open_stage_writes_its_manifest_and_refuses_another_run(tmp_path):
    manifest = {"idea": "x", "scope": "ticker", "tickers": ("AAA", "BBB")}
    null_v2.open_stage(tmp_path, "panel", manifest, **QUIET)
    saved = json.loads((tmp_path / "panel" / "manifest.json").read_text(encoding="utf-8"))
    assert saved == {"idea": "x", "scope": "ticker", "tickers": ["AAA", "BBB"],
                     "null_version": "v2", "stage": "panel"}
    null_v2.open_stage(tmp_path, "panel", manifest, **QUIET)        # same run resumes
    with pytest.raises(ValueError, match="another run"):
        null_v2.open_stage(tmp_path, "panel", {**manifest, "scope": "market"}, **QUIET)


def test_open_stage_refuses_an_unknown_stage_and_a_v1_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        null_v2.open_stage(tmp_path, "rank", {"idea": "x"}, **QUIET)
    (tmp_path / "manifest.json").write_text(json.dumps({"idea": "x"}), encoding="utf-8")
    with pytest.raises(ValueError, match="v1"):
        null_v2.open_stage(tmp_path, "panel", {"idea": "x"}, **QUIET)
    other = tmp_path / "other"
    other.mkdir()
    (other / "AAA.pkl").write_bytes(b"")
    with pytest.raises(ValueError, match="v1"):
        null_v2.open_stage(other, "panel", {"idea": "x"}, **QUIET)
    assert null_v2.open_stage(None, "draw", {"idea": "x"}, **QUIET).done() == set()


def test_resumable_map_skips_finished_keys_and_never_saves_none(tmp_path):
    calls = []

    def fn(key):
        calls.append(key)
        return None if key == "CCC" else key.lower()

    cp = null_v2.StageCheckpoint(tmp_path)
    first = null_v2.resumable_map(["AAA", "BBB", "CCC"], fn, checkpoint=cp, **QUIET)
    assert first == {"AAA": "aaa", "BBB": "bbb"}
    calls.clear()
    again = null_v2.resumable_map(["AAA", "BBB", "CCC"], fn, checkpoint=cp, **QUIET)
    assert again == first and calls == ["CCC"]
