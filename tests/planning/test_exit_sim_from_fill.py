"""v232: exit_sim.simulate_exit_from_fill -- the v1 exit walk from a given fill.

Parity: handed the engine's own entry bar and price, and the engine's own
fill-bar setting for the entry type, the wrapper returns exactly what
simulate_exit returns. Layer 1 (scripts/reports/reconcile/layer1.py) always
passes fill_bar_check=False: the fill day is the day the daily walk never sees.
"""
import pytest

from swingbot.core.market.strategy_types import COMPRESSION_SHORT, TURTLE_SOUP
from swingbot.core.planning.exit_sim import _walk_for, simulate_exit, simulate_exit_from_fill
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
                strategy="Fibonacci", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
                stop_loss=95.0, tp1=106.0, tp1_fraction=0.5, tp2=110.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


SIGNAL = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
PATHS = {
    "win": [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 103.0, 100.0, 102.5),
            (102.5, 107.0, 102.0, 106.5), (106.5, 109.0, 106.0, 108.5),
            (108.5, 111.0, 108.0, 110.5), (110.5, 111.0, 104.0, 104.5)] + [FLAT] * 8,
    "loss": [SIGNAL, (100.0, 100.5, 98.0, 99.0), (99.0, 99.5, 94.0, 94.5)] + [FLAT] * 8,
    "timeout": [SIGNAL] + [FLAT] * 14,
}


def _mirror(bars):
    """Reflect a path around 100, so a bearish plan sees what a bullish one sees."""
    return [(200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c) for o, h, l, c in bars]


BEAR = dict(direction="bearish", stop_loss=105.0, tp1=94.0, tp2=90.0)
# (case id, plan overrides, mirrored path?, the engine's own fill-bar setting)
CASES = [
    ("market", {}, False, False),
    ("market_short", BEAR, True, False),
    ("stop_entry", dict(entry_type="stop_entry", trigger_price=100.4), False, False),
    ("limit", dict(entry_type="limit", trigger_price=99.5, expiry_bars=1), False, True),
    ("compression_short", dict(BEAR, strategy=COMPRESSION_SHORT, entry_type="stop_entry",
                               trigger_price=99.6, stop_ceiling_pct=10.0), True, True),
]


def _engine_and_wrapper(bars, kw, *, scale_out, fill_bar_check, signal=0, **extra):
    df = make_ohlcv(bars)
    engine = simulate_exit(df, signal, _plan(**kw), scale_out=scale_out, **extra)
    assert engine.entry_index is not None, engine.outcome
    wrapped = simulate_exit_from_fill(df, engine.entry_index, engine.entry_price, _plan(**kw),
                                      scale_out=scale_out, fill_bar_check=fill_bar_check,
                                      **extra)
    return engine, wrapped


@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_with_simulate_exit_for_every_entry_type(case, path, scale_out):
    _, kw, mirrored, check = case
    bars = _mirror(PATHS[path]) if mirrored else PATHS[path]
    engine, wrapped = _engine_and_wrapper(bars, kw, scale_out=scale_out, fill_bar_check=check)
    assert vars(wrapped) == vars(engine)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_holds_under_a_plan_hold_cap(case):
    _, kw, mirrored, check = case
    bars = _mirror(PATHS["timeout"]) if mirrored else PATHS["timeout"]
    engine, wrapped = _engine_and_wrapper(bars, dict(kw, hold_cap_bars=3), scale_out=False,
                                          fill_bar_check=check)
    assert engine.outcome == "timeout"
    assert vars(wrapped) == vars(engine)


def test_parity_with_an_explicit_max_holding_days():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], {}, scale_out=True,
                                          fill_bar_check=False, max_holding_days=2)
    assert engine.exit_index == 2
    assert vars(wrapped) == vars(engine)


LIMIT = dict(entry_type="limit", trigger_price=99.5, expiry_bars=1)
STOPPED_FILL_BAR = [SIGNAL, (100.0, 100.5, 94.0, 96.0)] + PATHS["win"][2:]


def test_limit_fill_bar_stop_matches_the_engine_when_checked():
    engine, wrapped = _engine_and_wrapper(STOPPED_FILL_BAR, LIMIT, scale_out=False,
                                          fill_bar_check=True)
    assert (engine.outcome, engine.exit_index, engine.r_total) == ("loss", 1, -1.0)
    assert vars(wrapped) == vars(engine)


def test_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(STOPPED_FILL_BAR)
    res = simulate_exit_from_fill(df, 1, 99.5, _plan(**LIMIT), scale_out=False)
    assert res.entry_index == 1 and res.exit_index != 1


def test_a_checked_fill_at_the_stop_is_a_flat_scratch():
    df = make_ohlcv(PATHS["win"])
    res = simulate_exit_from_fill(df, 1, 95.0, _plan(), scale_out=False, fill_bar_check=True)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0,
                                                                "gap_through_stop")


# --- v180 Turtle Soup: the gap-aware walk ------------------------------------

TS = dict(strategy=TURTLE_SOUP, stop_loss=97.0, tp1=106.0, tp1_fraction=1.0, tp2=None,
          stop_ceiling_pct=10.0)
TS_GAP_STOP = [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 101.0, 99.5, 100.0),
               (96.0, 97.5, 95.0, 96.5)] + [FLAT] * 6
TS_FILL_BAR_STOP = [SIGNAL, (100.0, 101.0, 96.5, 99.0), (99.0, 106.5, 98.5, 106.0)] + [FLAT] * 6


def test_turtle_soup_gap_stop_books_the_open_not_the_stop():
    df = make_ohlcv(TS_GAP_STOP)
    engine = simulate_exit(df, 0, _plan(**TS))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False,
                                      fill_bar_check=True)
    assert (engine.entry_index, engine.entry_price, engine.r_total) == (1, 100.0, -1.333)
    assert vars(wrapped) == vars(engine)
    plain = _walk_for(_plan(**TS), False)(df, 1, 100.0, _plan(**TS), 10)
    assert plain.r_total != engine.r_total          # why the wrapper routes v180


def test_turtle_soup_checked_fill_bar_is_walked_as_session_one():
    df = make_ohlcv(TS_FILL_BAR_STOP)
    engine = simulate_exit(df, 0, _plan(**TS))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False,
                                      fill_bar_check=True)
    assert (engine.outcome, engine.exit_index) == ("loss", 1)
    assert vars(wrapped) == vars(engine)


def test_turtle_soup_unchecked_fill_bar_is_skipped_and_df_untouched():
    df = make_ohlcv(TS_FILL_BAR_STOP)
    before = df.copy()
    res = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("win", 1, 2, 2.0)
    assert df.equals(before)


@pytest.mark.parametrize("check", [False, True])
def test_turtle_soup_hold_cap_counts_the_fill_session(check):
    df = make_ohlcv(PATHS["timeout"])
    engine = simulate_exit(df, 0, _plan(**TS, hold_cap_bars=3))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS, hold_cap_bars=3),
                                      scale_out=False, fill_bar_check=check)
    assert engine.exit_index == 3                    # fill bar 1 is session 1 of 3
    assert vars(wrapped) == vars(engine)


# --- v192 waiting plan: the next-open fill-bar order -------------------------

WAIT = dict(source="confluence", strategy="S/R Confluence", stop_loss=98.5, tp1=103.0,
            tp2=105.0, waits_next_open=True)
WAIT_PATHS = {
    "fill_bar_stop": [SIGNAL, (100.0, 100.5, 98.0, 99.0)] + [FLAT] * 6,
    "fill_bar_tp1": [SIGNAL, (100.0, 103.5, 99.5, 103.2), (103.2, 104.0, 102.5, 103.8),
                     (103.8, 105.5, 103.5, 105.2)] + [FLAT] * 6,
    "clean": PATHS["win"],
    "timeout": PATHS["timeout"],
}


@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(WAIT_PATHS))
def test_v192_waiting_plan_parity(path, scale_out):
    engine, wrapped = _engine_and_wrapper(WAIT_PATHS[path], WAIT, scale_out=scale_out,
                                          fill_bar_check=True)
    assert (engine.entry_index, engine.entry_price) == (1, 100.0)
    assert vars(wrapped) == vars(engine)


def test_v192_fill_bar_stop_and_tp1_are_the_engines():
    stop, _ = _engine_and_wrapper(WAIT_PATHS["fill_bar_stop"], WAIT, scale_out=False,
                                  fill_bar_check=True)
    tp1, _ = _engine_and_wrapper(WAIT_PATHS["fill_bar_tp1"], WAIT, scale_out=False,
                                 fill_bar_check=True)
    assert (stop.outcome, stop.exit_index, stop.r_total) == ("loss", 1, -1.0)
    assert (tp1.outcome, tp1.exit_index) == ("win", 1)


def test_v192_hold_cap_parity():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], dict(WAIT, hold_cap_bars=3),
                                          scale_out=False, fill_bar_check=True)
    assert engine.exit_index == 3
    assert vars(wrapped) == vars(engine)


def test_v192_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(WAIT_PATHS["fill_bar_stop"])
    res = simulate_exit_from_fill(df, 1, 100.0, _plan(**WAIT), scale_out=False)
    assert res.exit_index != 1
