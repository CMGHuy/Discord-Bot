"""v182 level-mode race (spec Part B): a resting stop order filled on the
event bar, risk from ATR14[t-1], only the stop counts on the fill bar,
entry slippage LEVEL_SLIPPAGE_FACTOR x base."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.screen import indicators, race as race_mod, sides
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)   # bar 0: ATR14[t-1] is read here
C_HAND = 256.0                         # a power of two: reflection is exact on 1/8 prices


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _mirror(df, c):
    out = df.copy()
    out["Open"], out["Close"] = c - df["Open"], c - df["Close"]
    out["High"], out["Low"] = c - df["Low"], c - df["High"]
    return out


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)          # risk 1.5 x 2 = 3


def _level(df, level, direction="short", **kw):
    """Race the event on bar 1 with order level ``level``, to the last bar."""
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    atr = kw.pop("atr", _atr(df))
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), level), atr, direction)
    return race_mod.race(df, [1], len(df) - 2, atr=atr, fill=fill, direction=direction, **kw)


HAND = {   # name: (bars from the event bar on, short level, outcome, entry, gross R, exit bar)
    "inside": ([(100.0, 100.5, 98.0, 98.5), QUIET], 99.0, "timeout", 99.0, -1.0 / 3.0, 2),
    "gap_fill": ([(98.0, 98.5, 97.0, 97.5), (97.5, 98.0, 97.0, 97.5)], 99.0,
                 "timeout", 98.0, 0.5 / 3.0, 2),
    "fill_bar_stop": ([(100.0, 102.5, 98.0, 100.0), QUIET], 99.5, "stop", 99.5, -1.0, 1),
    "fill_bar_target_ignored": ([(100.0, 100.5, 92.0, 93.0), (93.5, 94.0, 92.5, 93.0)], 99.0,
                                "target", 99.0, 2.0, 2),
    "gap_stop_next_bar": ([(100.0, 100.5, 98.0, 98.5), (103.0, 104.0, 102.5, 103.5)], 99.0,
                          "gap_stop", 99.0, -4.0 / 3.0, 2),
}


def test_level_constants_are_the_spec_values():
    assert race_mod.LEVEL_SLIPPAGE_FACTOR == 2.0
    assert race_mod.REPRICE_SLIPPAGE_FACTOR == 3.0


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_level_race_on_hand_built_frames(name):
    bars, level, outcome, entry, gross, exit_bar = HAND[name]
    out = _level(_frame(bars), level)
    assert out.outcome.tolist() == [outcome]
    assert out.entry.tolist() == [entry]                 # the real fill price
    assert out.risk.tolist() == [3.0]
    assert out.gross_r.tolist() == [pytest.approx(gross, rel=1e-12)]
    assert out.exit_pos.tolist() == [exit_bar]


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_level_on_p_is_long_level_on_the_reflected_frame_exactly(name):
    bars, level, *_ = HAND[name]
    df = _frame(bars)
    short = _level(df, level)
    long = _level(_mirror(df, C_HAND), C_HAND - level, direction="long")
    assert short.outcome.tolist() == long.outcome.tolist()
    assert short.exit_pos.tolist() == long.exit_pos.tolist()
    assert short.gross_r.tolist() == long.gross_r.tolist()


def test_risk_reads_the_atr_known_when_the_order_was_placed():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    out = _level(df, 99.0, atr=atr)
    assert out.risk.tolist() == [3.0]                    # 1.5 x ATR14[0], not ATR14[1]


@pytest.mark.parametrize("direction", ["short", "long"])
def test_level_at_the_open_is_the_next_open_race_shifted_one_bar(direction):
    """Spec Part B item 3: level = open and no fill-bar touch reproduces the
    next-open race of the bar before, one bar longer."""
    df = random_walk(600, seed=21)
    atr = indicators.atr(df)
    cap = 20
    o, h, l = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low"))
    a = atr.to_numpy(dtype=float)
    p = np.arange(20, len(df) - 1 - cap)
    risk = race_mod.STOP_ATR * a[p - 1]
    sign = -1.0 if direction == "short" else 1.0
    stop, target = o[p] - sign * risk, o[p] + sign * race_mod.REWARD_RISK * risk
    quiet = (h[p] < np.maximum(stop, target)) & (l[p] > np.minimum(stop, target))
    p = p[quiet]
    assert p.size > 100                                            # non-vacuous
    zero = {"slippage_bps": 0.0, "commission": 0.0, "direction": direction, "atr": atr}
    level = race_mod.race(df, p, cap, fill=o[p], **zero)
    shifted = race_mod.race(df, p - 1, cap + 1, **zero)
    assert level.outcome.tolist() == shifted.outcome.tolist()
    assert level.exit_pos.tolist() == shifted.exit_pos.tolist()
    assert level.gross_r.tolist() == shifted.gross_r.tolist()
    assert level.r.tolist() == shifted.r.tolist()                  # 2 x 0 bps = 0
    assert level.entry.tolist() == o[p].tolist()


def test_level_entry_pays_the_factor_on_the_entry_fill_only():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), 99.0), _atr(df), "short")
    for factor, entry_bps in ((race_mod.LEVEL_SLIPPAGE_FACTOR, 10.0),
                              (race_mod.REPRICE_SLIPPAGE_FACTOR, 15.0)):
        out = race_mod.race(df, [1], 1, atr=_atr(df), fill=fill, direction="short",
                            slippage_bps=5.0, commission=0.02, level_factor=factor)
        days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
        expected = sides.net_r(np.array([99.0]), np.array([100.0]), np.array([3.0]),
                               direction="short", days=days, slippage_bps=5.0,
                               entry_bps=entry_bps, commission=0.02)
        assert out.r.tolist() == expected.tolist()


def test_level_factor_multiplies_the_configured_base(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 7.0)
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET])
    fill, _ = race_mod.level_fills(df, np.array([1]), np.full(len(df), 99.0), _atr(df), "short")
    out = race_mod.race(df, [1], 1, atr=_atr(df), fill=fill, direction="short", commission=0.0)
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([99.0]), np.array([100.0]), np.array([3.0]),
                           direction="short", days=days, slippage_bps=None,
                           entry_bps=14.0, commission=0.0)
    assert out.r.tolist() == expected.tolist()


def test_level_fills_short_take_the_lower_of_open_and_level():
    df = _frame([(100.0, 100.5, 98.0, 98.5), (98.0, 98.5, 97.0, 97.5)])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    fill, depth = race_mod.level_fills(df, np.array([1, 2]), np.array([np.nan, 99.0, 99.0]),
                                       atr, "short")
    assert fill.tolist() == [99.0, 98.0]
    assert depth.tolist() == [0.5, 0.0]          # (100 - 99) / ATR14[0]; a gap fill is 0


def test_level_fills_long_mirror_take_the_higher_of_open_and_level():
    df = _frame([(100.0, 102.0, 99.5, 101.5), (102.0, 103.0, 101.5, 102.5)])
    atr = pd.Series([2.0, 4.0, 8.0], index=df.index)
    fill, depth = race_mod.level_fills(df, np.array([1, 2]), np.array([np.nan, 101.0, 101.0]),
                                       atr, "long")
    assert fill.tolist() == [101.0, 102.0]
    assert depth.tolist() == [0.5, 0.0]


@pytest.mark.parametrize("level", [np.nan, 97.0, 98.0])   # 98.0: a touch is not a fill
def test_level_fills_refuse_an_order_that_did_not_fill(level):
    df = _frame([(100.0, 100.5, 98.0, 98.5)])
    with pytest.raises(ValueError, match="fill"):
        race_mod.level_fills(df, np.array([1]), np.full(len(df), level), _atr(df), "short")


def test_a_level_event_on_bar_zero_is_refused():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError, match=r"ATR14\[t-1\]"):
        race_mod.level_fills(df, np.array([0]), np.full(len(df), 100.5), _atr(df), "short")
    with pytest.raises(ValueError, match=r"ATR14\[t-1\]"):
        race_mod.race(df, [0], 1, atr=_atr(df), fill=np.array([100.0]), direction="short")


def test_level_candidates_read_warm_up_at_the_bar_before():
    events = np.array([True, True, True, True, False, False, False, False])
    member = np.ones(8, dtype=bool)
    warm = np.array([False, False, True, False, True, True, True, True])
    cand, counts = race_mod.candidate_events(events, member, warm, 2, entry="level")
    assert cand.tolist() == [3] and counts["dropped_warmup"] == 3
    cand, counts = race_mod.candidate_events(events, member, warm, 2)
    assert cand.tolist() == [2] and counts["dropped_warmup"] == 3


def _book(df, events, levels, cap, *, atr=None, warm=None, **kw):
    n = len(df)
    atr = _atr(df) if atr is None else atr
    warm = np.ones(n, dtype=bool) if warm is None else warm
    return race_mod.run_book(df, events, cap, member=np.ones(n, dtype=bool), warm=warm,
                             atr=atr, direction="short", levels=levels, **kw)


def test_level_event_with_nan_prior_atr_is_dropped_as_warmup():
    df = random_walk(120, seed=3)
    atr = indicators.atr(df).copy()
    atr.iloc[59] = np.nan
    warm = race_mod.warm_mask(atr, pd.Series(1.0, index=df.index))
    events = np.zeros(len(df), dtype=bool)
    events[[60, 90]] = True
    levels = (df["Low"] + 0.25).to_numpy()
    booked, counts = _book(df, events, levels, 10, atr=atr, warm=warm)
    assert counts["dropped_warmup"] == 1
    assert booked.event_pos.tolist() == [90]
    assert np.isfinite(booked.r).all() and np.isfinite(booked.risk).all()


def test_level_event_near_the_end_drops_as_window():
    df = random_walk(120, seed=3)
    events = np.zeros(len(df), dtype=bool)
    events[[60, 115]] = True
    booked, counts = _book(df, events, (df["Low"] + 0.25).to_numpy(), 10)
    assert counts["dropped_window"] == 1
    assert booked.event_pos.tolist() == [60]


def test_entry_bar_stop_lets_the_next_bar_trade():
    df = _frame([(100.0, 102.5, 98.0, 100.0), (100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    events = np.array([False, True, True, False, False])
    levels = np.array([np.nan, 99.5, 99.0, np.nan, np.nan])
    booked, counts = _book(df, events, levels, 2, slippage_bps=0.0, commission=0.0)
    assert booked.event_pos.tolist() == [1, 2]
    assert booked.exit_pos.tolist() == [1, 4]
    assert booked.outcome.tolist() == ["stop", "timeout"]
    assert counts["skipped_overlap"] == 0


def test_run_book_level_needs_the_fixed_shape():
    df = _frame([(100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    with pytest.raises(ValueError, match="fixed"):
        _book(df, np.array([False, True, False, False]), np.full(4, 99.0), 1, shape="trail")


def _spy_race(monkeypatch):
    seen = []

    def fake(df, cand, cap, **kwargs):
        seen.append(kwargs)
        return race_mod.RaceResult.empty()

    monkeypatch.setattr(race_mod, "race_for", lambda shape: fake)
    return seen


def test_run_book_without_levels_passes_no_level_keyword(monkeypatch):
    seen = _spy_race(monkeypatch)
    df = random_walk(100, seed=1)
    for direction in ("long", "short"):
        race_mod.run_book(df, np.zeros(100, dtype=bool), 5, member=np.ones(100, bool),
                          warm=np.ones(100, bool), atr=indicators.atr(df), direction=direction)
    assert len(seen) == 2
    assert all(not ({"fill", "level_factor"} & set(kw)) for kw in seen)


def test_run_book_threads_the_fills_and_the_factor(monkeypatch):
    seen = _spy_race(monkeypatch)
    df = _frame([(100.0, 100.5, 98.0, 98.5), (100.0, 100.5, 98.0, 98.5), QUIET, QUIET])
    events = np.array([False, True, True, False, False])
    levels = np.array([np.nan, 99.0, 99.25, np.nan, np.nan])
    _book(df, events, levels, 2, level_factor=race_mod.REPRICE_SLIPPAGE_FACTOR)
    assert seen[0]["fill"].tolist() == [99.0, 99.25]
    assert seen[0]["level_factor"] == 3.0 and seen[0]["direction"] == "short"
