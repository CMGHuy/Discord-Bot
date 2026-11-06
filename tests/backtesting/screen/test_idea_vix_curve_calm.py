"""vix_curve_calm (2026-11-07): calm VIX/VIX3M curve days, stress on > 1.0, off < 0.95."""
import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen.ideas import vix_curve_calm as idea
from tests.backtesting.screen.helpers import assert_prefix_stable, frame

# ratio path: calm, crosses 1.0 at bar 5 (stress), sits at 0.97 (still stressed),
# drops to 0.94 at bar 9 (calm again), 0.99 stays calm (below the on bar)
RATIOS = [0.85, 0.88, 0.9, 0.95, 0.99, 1.05, 1.1, 0.97, 0.96, 0.94, 0.99, 0.9]
STRESSED = [False] * 5 + [True] * 4 + [False] * 3


def _context(ratios=RATIOS, start="2009-06-01"):
    far = frame(np.full(len(ratios), 20.0), start=start)
    near = frame(np.asarray(ratios) * 20.0, index=far.index)
    return {"^VIX": near, "^VIX3M": far}


def test_frozen_definition():
    assert idea.CONTEXT == ("^VIX", "^VIX3M")
    assert idea.CAP == 10 and idea.RACE == "fixed"
    assert idea.PARAMS["stress_on_above"] == 1.0
    assert idea.PARAMS["stress_off_below"] == 0.95


def test_stress_state_has_hysteresis():
    ratio = pd.Series(RATIOS)
    assert idea.stress_state(ratio, 1.0, 0.95).tolist() == STRESSED


def test_events_are_the_calm_days():
    ctx = _context()
    out = idea.events(ctx["^VIX"], ctx)
    assert out.tolist() == [not s for s in STRESSED]
    assert out.dtype == bool and out.name == "vix_curve_calm"


def test_an_undefined_ratio_is_no_event_and_keeps_the_state():
    ratios = list(RATIOS)
    ratios[7] = np.nan                       # inside the stressed run
    ctx = _context(ratios)
    out = idea.events(ctx["^VIX"], ctx)
    assert not out.iloc[7]
    assert not out.iloc[8]                   # still stressed after the gap
    assert idea.stress_state(pd.Series(ratios), 1.0, 0.95).tolist() == STRESSED


def test_a_zero_far_value_is_undefined_not_infinite():
    ctx = _context()
    ctx["^VIX3M"] = ctx["^VIX3M"].copy()
    ctx["^VIX3M"].iloc[2, ctx["^VIX3M"].columns.get_loc("Close")] = 0.0
    out = idea.events(ctx["^VIX"], ctx)
    assert not out.iloc[2] and out.iloc[3]   # no spurious stress from r = inf


def test_a_stock_date_without_context_is_false():
    ctx = _context()
    stock = frame(np.linspace(50, 60, len(RATIOS)), index=ctx["^VIX"].index)
    thin = {k: v.drop(v.index[1]) for k, v in ctx.items()}
    out = idea.events(stock, thin)
    assert out.iloc[0] and not out.iloc[1]


def test_empty_context_gives_no_events():
    ctx = _context([])
    stock = frame(np.linspace(50, 60, 5), start="2009-06-01")
    assert not idea.events(stock, ctx).any()


def test_reads_no_later_bar():
    ctx = _context()
    assert idea.events(ctx["^VIX"], ctx).any()           # non-vacuous
    assert_prefix_stable(lambda d: idea.events(d, {"^VIX": d,
                                                   "^VIX3M": ctx["^VIX3M"].loc[d.index]}),
                         ctx["^VIX"], [3, 5, 8, 9, 11])
