"""v211 (spec v209 § Track 2): the frozen daily SHOCK state both shock ideas read."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import ideas, indicators
from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb
from tests.backtesting.screen.helpers import frame, random_walk, shock_context

IDX = pd.bdate_range("2009-06-01", periods=11)
#:           0     1     2     3     4     5     6     7     8     9     10
BREADTH = [0.05, 0.45, 0.20, 0.08, 0.08, 0.30, 0.42, 0.09, 0.41, 0.05, 0.02]
VIX =     [20.0, 21.0, 22.0, 23.0, 22.0, 21.0, 25.0, 24.0, 26.0, 25.0, 24.0]


def _series(values, index=IDX):
    return pd.Series(np.asarray(values, dtype=float), index=index)


def test_the_constants_are_the_frozen_spec_values():
    assert (sb.BREADTH, sb.VIX, sb.CONTEXT) == ("BREADTH_ATR1", "^VIX", ("BREADTH_ATR1", "^VIX"))
    assert (sb.ENTER_BREADTH, sb.RELEASE_BREADTH, sb.LOW_WINDOW) == (0.40, 0.10, 20)
    assert sb.SHOCK_PARAMS == {"breadth": "BREADTH_ATR1", "vix": "^VIX",
                               "enter": 0.40, "release": 0.10}
    assert sb.FAMILY == ("shock_support_break_short", "shock_failed_bounce_short")
    assert sb.SOURCE.startswith("v209 spec § Track 2")


def test_the_family_module_is_not_a_registered_idea():
    assert "_shock_breakdown" not in ideas.IDEA_MODULES
    assert not hasattr(sb, "CAP") and not hasattr(sb, "events")


def test_the_spec_reading_release_day_is_shock_and_re_entry_is_a_new_episode():
    """Bar 3: breadth 0.08 but ^VIX up -> stays SHOCK. Bar 4: 0.08 and ^VIX
    down -> released, still SHOCK. Bar 6 enters episode 2; bar 7 releases it;
    bar 8 (the day after the release) re-enters as episode 3; bar 9 releases;
    bar 10 is NORMAL although ^VIX is down."""
    out = sb.shock_state(_series(BREADTH), _series(VIX))
    assert out["shock"].tolist() == [False, True, True, True, True, False,
                                     True, True, True, True, False]
    assert out["episode"].tolist() == [0, 1, 1, 1, 1, 0, 2, 2, 3, 3, 0]
    assert out.index.equals(IDX)
    assert out["shock"].dtype == bool and out["episode"].dtype == np.int64


def test_the_thresholds_are_inclusive_and_vix_must_strictly_fall():
    idx = IDX[:5]
    out = sb.shock_state(_series([0.40, 0.10, 0.10, 0.39, 0.0], idx),
                         _series([20.0, 20.0, 19.0, 18.0, 17.0], idx))
    # 0.40 enters; 0.10 with ^VIX flat holds; 0.10 with ^VIX down releases
    # (still SHOCK); 0.39 the next day does not re-enter.
    assert out["shock"].tolist() == [True, True, True, False, False]
    assert out["episode"].tolist() == [1, 1, 1, 0, 0]


def test_a_second_spike_inside_an_episode_keeps_the_episode_id():
    idx = IDX[:4]
    out = sb.shock_state(_series([0.50, 0.20, 0.60, 0.20], idx),
                         _series([20.0, 19.0, 18.0, 17.0], idx))
    assert out["shock"].all() and out["episode"].tolist() == [1, 1, 1, 1]


def test_nan_breadth_neither_enters_nor_releases_and_a_missing_vix_is_not_down():
    idx = IDX[:5]
    out = sb.shock_state(_series([np.nan, 0.45, np.nan, 0.05, 0.05], idx),
                         _series([20.0, 21.0, 20.0, np.nan, 19.0], idx))
    # bar 2: NaN breadth holds SHOCK; bar 3: ^VIX[t] missing; bar 4: ^VIX[t-1] missing.
    assert out["shock"].tolist() == [False, True, True, True, True]


def test_the_state_on_t_reads_no_later_bar():
    rng = np.random.default_rng(11)
    breadth = _series(rng.uniform(0.0, 0.6, 400), pd.bdate_range("2009-06-01", periods=400))
    vix = random_walk(400, seed=12, start="2009-06-01")["Close"]
    full = sb.shock_state(breadth, vix)
    assert full["episode"].max() >= 5                         # non-vacuous
    for t in (30, 99, 100, 250, 399):
        part = sb.shock_state(breadth.iloc[: t + 1], vix.iloc[: t + 1])
        pd.testing.assert_frame_equal(part, full.iloc[: t + 1])


def test_ticker_state_never_forward_fills_a_date_the_context_lacks():
    stock_idx = pd.bdate_range("2010-01-04", periods=30)
    ctx = shock_context(stock_idx, [(5, 15)])
    gap = stock_idx[10]
    thin = {k: v.drop(gap) for k, v in ctx.items()}
    out = sb.ticker_state(frame(np.full(30, 50.0), index=stock_idx), thin)
    assert out.index.equals(stock_idx)
    assert not out.loc[gap, "shock"] and out.loc[gap, "episode"] == 0
    assert out["shock"].iloc[5:16].sum() == 10 and out["shock"].iloc[15]
    assert out["shock"].dtype == bool and out["episode"].dtype == np.int64


def test_ticker_state_drops_context_only_dates():
    ctx_idx = pd.bdate_range("2010-01-04", periods=30)
    ctx = shock_context(ctx_idx, [(2, 8)])
    stock = frame(np.full(20, 50.0), index=ctx_idx[5:25])
    out = sb.ticker_state(stock, ctx)
    assert out.index.equals(stock.index)
    assert out["shock"].tolist()[:5] == [True, True, True, True, False]


def test_prior_low_is_the_twenty_bars_before_t_and_prior_atr_is_dated_t_minus_1():
    df = random_walk(120, seed=5)
    low = df["Low"].to_numpy()
    got = sb.prior_low(df).to_numpy()
    assert np.isnan(got[:20]).all()
    assert all(got[t] == low[t - 20:t].min() for t in range(20, 120))
    pd.testing.assert_series_equal(sb.prior_atr(df), indicators.atr(df).shift(1))
