"""v109 NO-LOOKAHEAD / detection-parity proof for spot metals.

A spot frame is its futures frame times ONE constant ratio. That must leave
every entry signal, level and scenario identical up to the price scale --
otherwise XAUUSD alerts would differ from GC=F alerts for a reason other than
the basis, and the spec's "detection is unchanged by construction" would be
false. The committed v74 fixtures (500 real daily bars) are lifted to a
metals-like price scale so the signals are real, not vacuous.

If a strategy fails here, do NOT loosen the assertion: that strategy reads an
absolute price somewhere, and the controller must decide (BLOCKED).
"""
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import entry_filters, levels
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.marketdata import spot_metals as sm

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "v74"
RATIO = 4151.70 / 4175.30          # the 2026-09-28 measured gold basis
READING = sm.SpotRatio("XAUUSD", 4151.70, "GC=F", 4175.30, RATIO)


def _futures_like(name: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / f"{name}.csv", index_col=0, parse_dates=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype("float64")
    df[["Open", "High", "Low", "Close"]] *= 20.0   # ~3000-4000, a gold-like scale
    return df


def _signals(df, strategy):
    out = []
    for horizon in HORIZONS:
        bull, bear = entry_filters.ENTRY_FUNCS[strategy](df, horizon)
        out.append((horizon,
                    bull.fillna(False).astype(bool).tolist(),
                    bear.fillna(False).astype(bool).tolist()))
    return out


@pytest.mark.parametrize("name", ["AAPL", "XOM"])
@pytest.mark.parametrize("strategy", sorted(entry_filters.ENTRY_FUNCS))
def test_entry_signals_identical_on_scaled_bars(name, strategy):
    raw = _futures_like(name)
    assert _signals(sm.scale_frame(raw, READING), strategy) == _signals(raw, strategy)


def test_the_parity_fixtures_are_not_vacuous():
    total = 0
    for name in ("AAPL", "XOM"):
        raw = _futures_like(name)
        for strategy in entry_filters.ENTRY_FUNCS:
            total += sum(sum(b) + sum(s) for _, b, s in _signals(raw, strategy))
    assert total >= 50, "fixtures must fire real signals for parity to mean anything"


def _plan(df, horizon):
    h = HORIZONS[horizon]
    price = float(df["Close"].iloc[-1])
    supports, resistances = levels.build_level_map(df, h, price)
    floor = levels.atr_floor_pct(df, price, h)
    scenarios = levels.build_scenarios(price, supports, resistances, min_reward_pct=1.0,
                                       atr_floor=floor, min_stop_distance_pct=0.5,
                                       max_stop_distance_pct=15.0)
    return price, supports, resistances, floor, scenarios


def _scaled(values):
    return [None if v is None else v * RATIO for v in values]


@pytest.mark.parametrize("name,horizon", [("XOM", "4w"), ("XOM", "3m"), ("AAPL", "4w")])
def test_levels_and_scenarios_are_the_futures_ones_times_the_ratio(name, horizon):
    raw = _futures_like(name)
    p0, s0, r0, f0, sc0 = _plan(raw, horizon)
    p1, s1, r1, f1, sc1 = _plan(sm.scale_frame(raw, READING), horizon)
    assert p1 == pytest.approx(p0 * RATIO, rel=1e-12)
    assert [lv.price for lv in s1] == pytest.approx(_scaled([lv.price for lv in s0]), rel=1e-9)
    assert [lv.price for lv in r1] == pytest.approx(_scaled([lv.price for lv in r0]), rel=1e-9)
    assert [len(lv.sources) for lv in s1] == [len(lv.sources) for lv in s0]
    assert [len(lv.sources) for lv in r1] == [len(lv.sources) for lv in r0]
    assert f1 == pytest.approx(f0, rel=1e-9)
    assert [s.direction for s in sc1] == [s.direction for s in sc0]
    for a, b in zip(sc0, sc1):
        assert [b.entry, b.stop_loss, b.take_profit] == pytest.approx(
            _scaled([a.entry, a.stop_loss, a.take_profit]), rel=1e-9)
        assert (b.target2_price is None) == (a.target2_price is None)
        if a.target2_price is not None:
            assert b.target2_price == pytest.approx(a.target2_price * RATIO, rel=1e-9)
        assert b.risk_reward_ratio == a.risk_reward_ratio
        assert b.stop_distance_pct == pytest.approx(a.stop_distance_pct, rel=1e-9)


def test_the_scenario_fixture_builds_both_directions():
    *_, scenarios = _plan(_futures_like("XOM"), "3m")
    assert sorted(s.direction for s in scenarios) == ["bearish", "bullish"]
