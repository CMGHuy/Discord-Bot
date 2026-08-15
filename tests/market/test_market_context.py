"""P0 market context layer -- see
docs/superpowers/specs/implemented/2026-08-08-v17-market-context-and-level-lifecycle-design.md

The load-bearing tests here are the alignment ones. A market-context gate is
exactly the feature where an off-by-one silently leaks tomorrow's regime into
today's entry: the backtest looks excellent and live underperforms, with
nothing failing anywhere. `test_attach_is_truncation_invariant` and
`test_shifting_spy_changes_the_context` are what make that class of bug
detectable.
"""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv, make_trend_df
from swingbot.core import market_context as mc
from swingbot.core.edge.regime2 import REGIMES, regime_series


def _spy(n=400, daily_pct=0.15):
    return make_trend_df(n, daily_pct)


# --- attach -----------------------------------------------------------------

def test_attach_adds_every_declared_column_and_preserves_the_frame():
    spy = _spy()
    df = make_trend_df(300, 0.10)

    out = mc.attach(df, spy_df=spy)

    assert out.index.equals(df.index)
    for col in mc.CTX_COLUMNS:
        assert col in out.columns
    # original frame untouched -- attach returns a copy
    assert not any(c in df.columns for c in mc.CTX_COLUMNS)
    # OHLCV survives unchanged
    for col in ("Open", "High", "Low", "Close", "Volume"):
        assert out[col].equals(df[col])


def test_attach_labels_match_regime_series_on_shared_dates():
    spy = _spy()
    out = mc.attach(spy.copy(), spy_df=spy)

    expected = regime_series(spy)
    assert out["ctx_regime"].equals(expected)


def test_regime_labels_are_from_the_known_set():
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())
    assert set(out["ctx_regime"].dropna().unique()) <= set(REGIMES)


def test_rv_percentile_is_a_unit_interval():
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())
    rv = out["ctx_rv_pct"].dropna()

    assert len(rv) > 0
    assert rv.between(0.0, 1.0).all()


def test_reserved_cot_column_exists_but_is_empty():
    # P2b declares the column now so the block's shape never changes later.
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())
    assert "ctx_cot_z" in out.columns
    assert out["ctx_cot_z"].isna().all()


# --- alignment --------------------------------------------------------------

def test_ticker_bars_before_spy_history_are_nan_not_backfilled():
    spy = make_trend_df(200, 0.15)                      # starts 2019-01-01
    early = make_ohlcv(np.full(260, 50.0), start="2018-01-01")

    out = mc.attach(early, spy_df=spy)
    pre = out.loc[out.index < spy.index[0], "ctx_regime"]

    assert len(pre) > 0, "fixture must actually straddle SPY's first bar"
    assert pre.isna().all(), "bfill/interpolate would leak the future backwards"


def test_holes_in_the_ticker_index_forward_fill_from_the_last_spy_bar():
    spy = _spy(300)
    df = spy.iloc[::3].copy()          # ticker trades every 3rd day (halts)

    out = mc.attach(df, spy_df=spy)
    expected = regime_series(spy).reindex(df.index)

    assert out["ctx_regime"].equals(expected)


def test_attach_is_truncation_invariant():
    """Context at bar i must not change when the future is deleted.

    This is the structural NO-LOOKAHEAD proof: if any ctx_ column at bar i is
    computed from bars > i, truncating the frame changes the answer.
    """
    spy = _spy(400)
    df = make_trend_df(400, 0.10)
    i = 350

    full = mc.attach(df, spy_df=spy).iloc[i]
    truncated = mc.attach(df.iloc[:i + 1], spy_df=spy.iloc[:i + 1]).iloc[i]

    assert full["ctx_regime"] == truncated["ctx_regime"]
    assert full["ctx_rv_pct"] == pytest.approx(truncated["ctx_rv_pct"], nan_ok=True)


def test_shifting_spy_changes_the_context():
    """Proves attach reads the *aligned* SPY bar rather than a fixed one.

    Without this, a broken implementation that pinned every row to SPY's last
    regime would still pass every other alignment test here.
    """
    spy = _spy(400)
    spiky = make_trend_df(60, -1.2)
    spy.iloc[200:260] = spiky.values                  # a localised regime shift
    df = make_trend_df(400, 0.10)

    base = mc.attach(df, spy_df=spy)["ctx_regime"]
    shifted = mc.attach(df, spy_df=spy.shift(30).bfill())["ctx_regime"]

    assert not base.equals(shifted)


# --- accessor ---------------------------------------------------------------

def test_get_returns_none_when_the_gate_flag_is_off(monkeypatch):
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", False, raising=False)
    df = make_trend_df(300, 0.10)      # no context attached at all

    assert mc.get(df, "ctx_regime") is None


def test_get_raises_when_the_flag_is_on_and_context_is_missing(monkeypatch):
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    df = make_trend_df(300, 0.10)

    with pytest.raises(mc.MissingContextError):
        mc.get(df, "ctx_regime")


def test_get_returns_the_series_when_present(monkeypatch):
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())

    got = mc.get(out, "ctx_regime")
    assert got is not None
    assert got.index.equals(out.index)


def test_get_rejects_an_undeclared_column(monkeypatch):
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())

    with pytest.raises(ValueError):
        mc.get(out, "ctx_not_a_real_column")


def test_has_context_is_true_only_after_attach():
    df = make_trend_df(300, 0.10)
    assert not mc.has_context(df)
    assert mc.has_context(mc.attach(df, spy_df=_spy()))


def test_a_partial_context_block_does_not_count_as_context():
    # A frame rebuilt without going through attach can lose columns; that must
    # read as "no context", never as "context, some of it missing".
    out = mc.attach(make_trend_df(300, 0.10), spy_df=_spy())
    mangled = out.drop(columns=["ctx_rv_pct"])

    assert not mc.has_context(mangled)


def test_attach_rejects_a_spy_frame_without_close():
    with pytest.raises(ValueError):
        mc.attach(make_trend_df(300, 0.10), spy_df=pd.DataFrame({"Open": [1.0]}))


# --- end-to-end wiring ------------------------------------------------------
#
# The point of P0. Before this, apply_regime_gate was correct but starved:
# nothing in `run_backtest -> _vectorized_entries -> entries_for` or in live
# `evaluate_all` ever supplied a regimes series, so the gate masked nothing no
# matter how REGIME_ALLOW was configured (edge-engine-v4, task E24/E33).

def _entries(df, strategy="RSI Divergence"):
    # RSI Divergence at 4w is one of the few strategies that actually fires on
    # the shared market_df walk (bull=7, bear=4); plain "RSI" fires zero times,
    # which would make the masking assertions below pass vacuously.
    from swingbot.core.entry_filters import entries_for
    return entries_for(strategy, df, "4w")


def test_gate_masks_entries_when_context_comes_from_the_frame(monkeypatch, market_df):
    from swingbot.core import strategy_types

    # A smooth exponential trend never dips, so RSI dip-buying never fires and
    # the assertion below would pass vacuously -- market_df is a real walk.
    spy = _spy(len(market_df))
    df = mc.attach(market_df, spy_df=spy)

    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", False, raising=False)
    ungated_bull, ungated_bear = _entries(df)

    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    monkeypatch.setitem(strategy_types.REGIME_ALLOW, "RSI Divergence", ("bear_volatile",))
    gated_bull, gated_bear = _entries(df)

    # the SPY fixture is a steady quiet uptrend -> bull_quiet on every bar, so
    # allowing only bear_volatile must remove every entry
    assert (ungated_bull.sum() + ungated_bear.sum()) > 0, "fixture produced no entries to gate"
    assert gated_bull.sum() == 0
    assert gated_bear.sum() == 0


def test_gate_is_inert_without_a_regime_allow_entry(monkeypatch, market_df):
    spy = _spy(len(market_df))
    df = mc.attach(market_df, spy_df=spy)

    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", False, raising=False)
    base = _entries(df)
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    gated = _entries(df)          # no REGIME_ALLOW key for this strategy

    assert base[0].equals(gated[0])
    assert base[1].equals(gated[1])


def test_entries_fail_closed_on_a_frame_that_never_saw_attach(monkeypatch):
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", True, raising=False)
    bare = make_trend_df(500, 0.10)

    with pytest.raises(mc.MissingContextError):
        _entries(bare)


def test_entries_are_untouched_when_the_flag_is_off_and_context_is_absent(monkeypatch):
    # The default production state today: flag off, no context anywhere.
    monkeypatch.setattr("swingbot.config.REGIME_GATES_ENABLED", False, raising=False)
    bull, bear = _entries(make_trend_df(500, 0.10))

    assert bull.index.equals(bear.index)
