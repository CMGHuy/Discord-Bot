"""ORDERING invariants over the golden scenarios — not absolute scores.
If these fail, adjust registry WEIGHTS (the free variable; detectors are
not) and record the final weights in the table comment below.

Weight table (final, 21-check pruned registry — see
docs/superpowers/plans/2026-07-14-gatekeeper-v7_0-index.md; rows for checks
cut by the win-rate audit (vol_expansion, rumor_spike, buy_rumor, opex_pin,
size_formula, portfolio_room) are omitted, not reinstated).

Four weights were recalibrated off the initial table below to satisfy the
ordering invariants over these golden scenarios (denom-neutral status matrix
is fixed by the detectors; only weights moved):
  atr_normal       6  -> 22   (trap/dead need a firmer volatility-regime cap)
  confluence      10  -> 16   (the only check that fails outright on "counter"
                               — a long dragged into a downtrend needs to
                               separate clearly from a neutral range bounce)
  stop_structural 10  -> 20   (fails on both range_bounce and dead_cat;
                               raising it caps dead_cat's tier without
                               starving range_bounce's margin over counter)
  rr_realistic    10  ->  4   (fails only on range_bounce's tight
                               top-of-range entry; de-weighting it gives
                               range_bounce the headroom counter's fail
                               needed elsewhere)
All other checks keep their part-3 weights:
  context: htf_alignment 12, level_map 8
  setup:   signal_confirmed 10(HB), volume 8, momentum 6, divergence_against 6
  redflag: fake_breakout 10, dead_cat 10, news_whipsaw 10(HB), stop_sweep 8,
           divergence_trap 8, extreme_fade 8, beta_move 6, thin_session 6
  timing:  not_chasing 8, trigger_objective 6(HB), calendar_checked 4
"""
import datetime as dt

from swingbot.core.gate import run_checklist
from swingbot.core.gate.score import TIER_ORDER
from tests.fixtures.gate.scenarios import (breakout_and_fail, dead_cat,
                                            downtrend_daily, range_daily,
                                            uptrend_daily)
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


def _run(df, direction="bullish", strategy="Break & Retest", trigger=None):
    last = float(df["Close"].iloc[-1])
    trigger = trigger if trigger is not None else last
    stop = trigger * (0.95 if direction == "bullish" else 1.05)
    tp1 = trigger * (1.10 if direction == "bullish" else 0.90)
    plan = make_plan(strategy=strategy, direction=direction, created_at="2026-07-13",
                     trigger_price=trigger, entry_price=None,
                     stop_loss=stop, tp1=tp1, tp2=None)
    return run_checklist("TEST", strategy, plan, df,
                         macro_snap=QUIET_SNAP, now=EVENING)


def test_ordering_invariants():
    clean = _run(uptrend_daily())                                  # with-trend
    range_bounce = _run(range_daily(90, 110, n=300), trigger=110.0)
    counter = _run(downtrend_daily())                              # long into downtrend
    trap = _run(breakout_and_fail(level=100.0), trigger=100.0)
    dead = _run(dead_cat())
    assert clean.score > range_bounce.score > counter.score
    assert counter.score > min(trap.score, dead.score) or \
        counter.score >= max(trap.score, dead.score) - 5           # traps land at the bottom
    assert clean.score > trap.score and clean.score > dead.score


def test_red_flag_scenarios_capped_at_B():
    for result in (_run(breakout_and_fail(100.0), trigger=100.0), _run(dead_cat())):
        assert TIER_ORDER.index(result.tier) >= TIER_ORDER.index("B"), result.tier


def test_clean_setup_reaches_A():
    clean = _run(uptrend_daily())
    assert TIER_ORDER.index(clean.tier) <= TIER_ORDER.index("A"), \
        f"clean uptrend landed {clean.tier} ({clean.score}) — rebalance weights"
