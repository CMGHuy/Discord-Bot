"""Plan v8 Task V51 Step 1: the hard ceiling on realised loss.

The loss-side counterpart to V10's target floor. That one pushes the win out to
`MIN_TARGET_PCT`; this one pulls the loss in to `MAX_LOSS_PCT`, and together they
set the payoff ratio. At 2.5%/1.75% the payoff is 1.4286R and break-even is
41.2%, against a no-skill rate measured at 43.4%
(`docs/superpowers/results/2026-08-02-v52-barrier-base-rate.md`); the old
0.35R-target book needed 63.2% and got 55.6%.

The property that matters most here is ORDERING: all four sizing builders price
TP1 off the risk distance, so the cap has to bind before the target is derived.
Capping afterwards would leave the target priced off the old, wider distance and
silently change R:R -- which is the failure V51 Step 1 names explicitly.
"""
import pytest

from swingbot import config
from swingbot.core.plan_engine import (
    _atr_plan,
    _elliott_plan,
    _fibonacci_plan,
    _sr_plan,
    build_strategy_plan,
    cap_risk_distance,
    max_loss_distance,
)
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def cap_on(monkeypatch):
    """Pin the cap rather than trusting the shipped default, so these tests
    keep meaning the same thing if the default ever moves."""
    monkeypatch.setattr(config, "MAX_LOSS_CAP_ENABLED", True)
    monkeypatch.setattr(config, "MAX_LOSS_PCT", 1.75)


# -- the primitive ----------------------------------------------------------

def test_cap_pulls_a_too_wide_stop_in():
    assert cap_risk_distance(100.0, 4.0) == pytest.approx(1.75)


def test_cap_never_widens_a_tighter_stop():
    """A ceiling, not a setting -- a stop already inside it is untouched."""
    assert cap_risk_distance(100.0, 0.9) == 0.9


def test_cap_is_a_no_op_when_disabled(monkeypatch):
    """The log-only position: measure what the cap would have changed before
    it changes anything."""
    monkeypatch.setattr(config, "MAX_LOSS_CAP_ENABLED", False)
    assert cap_risk_distance(100.0, 4.0) == 4.0
    # ...and the ceiling is still computable, to log what it WOULD do.
    assert max_loss_distance(100.0) == pytest.approx(1.75)


def test_cap_reads_config_live_not_at_import(monkeypatch):
    """Hot-reloadable Field: a SIGHUP mid-session must take effect on the next
    plan built, not the next restart."""
    monkeypatch.setattr(config, "MAX_LOSS_PCT", 1.0)
    assert cap_risk_distance(100.0, 4.0) == pytest.approx(1.0)


def test_cap_scales_with_entry_price():
    assert cap_risk_distance(20.0, 5.0) == pytest.approx(0.35)
    assert cap_risk_distance(1000.0, 50.0) == pytest.approx(17.5)


# -- one per strategy family (Step 1's requirement) -------------------------
# The four builders size their stop by different mechanisms -- ATR multiple,
# fib structure, wave-2 structure, and a fixed S/R percent -- so each needs its
# own assertion that the ceiling reaches it.

def test_atr_family_respects_the_cap():
    stop, _ = _atr_plan(100.0, 2.0, "bullish", "4w", "MACD")
    assert (100.0 - stop) <= 1.75 + 1e-9


def test_fibonacci_family_respects_the_cap():
    stop, _ = _fibonacci_plan(100.0, 2.0, 108.0, 90.0, "bullish", "4w")
    assert (100.0 - stop) <= 1.75 + 1e-9


def test_sr_family_respects_the_cap():
    stop, _ = _sr_plan(100.0, 2.0, "bullish", "4w")
    assert (100.0 - stop) <= 1.75 + 1e-9


def test_elliott_family_respects_the_cap():
    stop, _ = _elliott_plan(100.0, 2.0, 90.0, "bullish", "4w")
    assert (100.0 - stop) <= 1.75 + 1e-9


@pytest.mark.parametrize("builder,args", [
    (_atr_plan, (100.0, 2.0, "bearish", "4w", "MACD")),
    (_fibonacci_plan, (100.0, 2.0, 110.0, 92.0, "bearish", "4w")),
    (_sr_plan, (100.0, 2.0, "bearish", "4w")),
    (_elliott_plan, (100.0, 2.0, 110.0, "bearish", "4w")),
])
def test_every_family_mirrors_for_bearish(builder, args):
    stop, _ = builder(*args)
    assert (stop - 100.0) <= 1.75 + 1e-9
    assert stop > 100.0


# -- the ordering property (why this is not just a clamp) -------------------

def test_target_is_derived_from_the_capped_distance(monkeypatch):
    """The whole point of capping before the target is priced. With rr=2.0 and
    a 4.0 raw risk, a cap applied AFTER would leave TP1 at entry+8.0 while the
    stop sat 1.75 away -- an R:R of 4.57 that no config asked for. Capping
    first keeps stop, target and size consistent with one number.
    """
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", False)
    monkeypatch.setitem(STRATEGY_RR_OVERRIDE, "MACD", 2.0)
    stop, tp1 = _atr_plan(100.0, 2.0, "bullish", "4w", "MACD")
    risk = 100.0 - stop
    assert risk == pytest.approx(1.75)
    assert (tp1 - 100.0) == pytest.approx(risk * 2.0)     # 3.5, not 8.0


def test_cap_and_floor_compose_into_the_intended_payoff(monkeypatch):
    """2.5% floor over a 1.75% ceiling is the 1.4286R payoff the plan is built
    on. Asserted end to end because the two are configured independently and
    nothing else checks that the pair still multiplies out."""
    monkeypatch.setattr(config, "TARGET_FLOOR_ENABLED", True)
    monkeypatch.setattr(config, "MIN_TARGET_PCT", 2.5)
    stop, tp1 = _atr_plan(100.0, 2.0, "bullish", "4w", "MACD")
    payoff = (tp1 - 100.0) / (100.0 - stop)
    assert payoff == pytest.approx(2.5 / 1.75, rel=1e-6)


# -- the E32 interaction: an R-based TP2 can go inert -----------------------

def test_r_based_tp2_goes_inert_below_the_floor_over_cap_ratio(monkeypatch):
    """A silent no-op the cap introduces, pinned so it is a known property
    rather than a future mystery.

    `_tp2_from_r` only accepts a candidate strictly beyond TP1. Risk is now
    capped at MAX_LOSS_PCT while TP1 is floored at MIN_TARGET_PCT, so a TP2
    priced at `entry + risk x tp2_r` clears TP1 only when

        tp2_r > MIN_TARGET_PCT / MAX_LOSS_PCT   (2.5 / 1.75 = 1.4286)

    Below that it returns None and the plan silently keeps its level-based
    TP2. E32's journal-derived multiples were fitted before the cap existed,
    so some of them are now inert in production -- exactly the class of silent
    sizing no-op docs/claude/known-traps.md warns about. V52 must not grid
    `tp2_r` below this ratio expecting it to do anything.
    """
    from swingbot.core.plan_engine import _tp2_from_r
    entry, stop, tp1 = 100.0, 98.25, 102.5      # 1.75 risk, 2.5% floored TP1
    assert _tp2_from_r(entry, stop, tp1, "bullish", 1.2) is None      # 102.10
    assert _tp2_from_r(entry, stop, tp1, "bullish", 1.4) is None      # 102.45
    beyond = _tp2_from_r(entry, stop, tp1, "bullish", 1.6)            # 102.80
    assert beyond == pytest.approx(102.8)


def test_the_inertness_threshold_moves_with_the_two_settings(monkeypatch):
    """It is the RATIO that matters, not either number -- widening the cap
    revives multiples that a tighter one made inert."""
    from swingbot.core.plan_engine import _tp2_from_r
    # cap widened to 5.0 -> ratio 0.5, so even tp2_r=1.2 clears the floor
    assert _tp2_from_r(100.0, 95.0, 102.5, "bullish", 1.2) == pytest.approx(106.0)


# -- every emitted plan, through the real builder ---------------------------

def _ramp_df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


STRATEGIES = ["MACD", "RSI", "EMA Crossover", "Fibonacci", "Support/Resistance",
              "VWAP", "MA Ribbon", "Break & Retest"]


@pytest.mark.parametrize("strategy", STRATEGIES)
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("horizon_key", ["2w", "4w", "3m", "9m"])
def test_every_strategy_plan_respects_the_cap(strategy, direction, horizon_key):
    plan = build_strategy_plan(_ramp_df(), 79, ticker="AAPL", strategy=strategy,
                               horizon_key=horizon_key, direction=direction)
    if plan is None:
        pytest.skip(f"{strategy} has no valid structure at this bar")
    entry = plan.trigger_price
    assert abs(entry - plan.stop_loss) / entry <= config.MAX_LOSS_PCT / 100 + 1e-9


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_plan_direction_invariant_survives_the_cap(direction):
    """stop < entry < tp1 (mirrored for bearish). The cap only ever moves the
    stop TOWARD entry, so it cannot break this -- assert it anyway, because
    every downstream consumer assumes it."""
    plan = build_strategy_plan(_ramp_df(), 79, ticker="AAPL", strategy="MACD",
                               horizon_key="4w", direction=direction)
    if direction == "bullish":
        assert plan.stop_loss < plan.trigger_price < plan.tp1
    else:
        assert plan.stop_loss > plan.trigger_price > plan.tp1


# -- sizing follows the capped distance -------------------------------------

def _cfg():
    # Supply every key: compute_position_size falls back to the project's
    # app_config defaults for anything missing, which would cap shares and
    # make these numbers wrong (see tests/test_edge_sizing.py).
    return {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct",
            "max_open_positions": 5, "max_position_pct": 100.0,
            "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


def test_position_size_follows_the_capped_stop_so_risk_per_trade_is_unchanged():
    """Step 1's second half. Sizing reads the plan's stop, so a capped stop
    must produce MORE shares at the SAME dollar risk -- a cap that tightened
    the stop without re-sizing would silently shrink risk per trade.

    Equality holds only to share-rounding precision: shares round to 2dp, so
    $100 of risk over a 1.75 stop is 57.14 shares (99.995), not 57.142857.
    """
    from swingbot.core.account import compute_position_size
    wide = compute_position_size(100.0, 96.0, _cfg())      # 4.00 away
    tight = compute_position_size(100.0, 98.25, _cfg())    # 1.75 away, capped
    assert tight["shares"] > wide["shares"]
    assert tight["shares"] * 1.75 == pytest.approx(wide["shares"] * 4.0, rel=1e-3)


def test_cap_makes_the_position_value_guard_more_likely_to_bind():
    """A consequence worth pinning rather than discovering live: holding dollar
    risk constant while shrinking the stop grows position VALUE, so the
    max_position_pct guard binds on trades that previously cleared it. When it
    does, realised risk falls below target -- the sizing is still correct, but
    'risk per trade is constant' stops being true at the boundary.
    """
    from swingbot.core.account import compute_position_size
    cfg = _cfg() | {"max_position_pct": 30.0}      # $3,000 of a $10k balance
    wide = compute_position_size(100.0, 96.0, cfg)
    tight = compute_position_size(100.0, 98.25, cfg)
    assert wide["shares"] == pytest.approx(25.0)   # $2,500 position, uncapped
    assert tight["shares"] == pytest.approx(30.0)  # would be 57.1; value-capped
    assert tight["shares"] * 1.75 < wide["shares"] * 4.0
