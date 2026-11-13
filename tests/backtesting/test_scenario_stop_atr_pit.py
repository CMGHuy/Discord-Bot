"""v226 V226-1: a replayed plan's entry_context["stop_atr"] (and stop_pct)
is point-in-time -- multiplying every bar after the signal leaves it
unchanged, and it equals abs(signal close - stop) / ATR14 on the frame cut
at the signal bar (spec § The grouping: measured from the SIGNAL CLOSE, not
the planned entry or trigger)."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.edge.context import entry_context
from swingbot.core.market.indicators import atr
from tests.helpers import make_ohlcv

# The replay is the slow part (same tier as test_scenario_rows.py).
pytestmark = pytest.mark.slow

GATES = {"min_reward_pct": 1.0, "min_stop_distance_pct": 0.5,
         "max_stop_distance_pct": 15.0, "min_risk_reward": 0.0,
         "min_confluence": 1, "cooldown_bars": 5}
PRICES = ["Open", "High", "Low", "Close"]


def _structured_df():
    """Trend up, then a 60-bar box -- the test_scenario_rows.py fixture,
    copied so the files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.fixture(autouse=True)
def _legacy_scorer(monkeypatch):
    # Production runs the legacy scorer (UNIFIED_CONFIDENCE defaults false).
    monkeypatch.setattr(config, "UNIFIED_CONFIDENCE", False)


@pytest.fixture(scope="module")
def df():
    return _structured_df()


@pytest.fixture(scope="module")
def hits(df):
    out = bs.replay_scenarios_detailed("AAPL", df, "4w", gates=GATES)
    assert len(out) >= 2, "fixture must produce at least two hits"
    return out


def _cut(df, hits) -> int:
    """The bar after the middle hit: hits before it are compared, every bar
    from it on is spiked."""
    return min(hits[len(hits) // 2].i + 1, len(df) - 1)


def _spiked(df, start: int, factor: float = 3.0):
    out = df.copy()
    out.loc[out.index >= out.index[start], PRICES] *= factor
    return out


def _stop_fields(hits, cut: int) -> dict:
    """{(bar, direction): (stop_atr, stop_pct)} for every hit before `cut`."""
    return {(hit.i, hit.plan.direction): (hit.plan.entry_context.get("stop_atr"),
                                          hit.plan.entry_context.get("stop_pct"))
            for hit in hits if hit.i < cut}


def _direct(frame, hit) -> dict:
    plan = hit.plan
    return entry_context(frame, direction=plan.direction, horizon_key="4w",
                         stop=plan.stop_loss, target=plan.tp1, entry=plan.trigger_price)


def test_replayed_stop_atr_ignores_every_bar_after_the_signal(df, hits):
    cut = _cut(df, hits)
    before = _stop_fields(hits, cut)
    assert before, "fixture must produce a hit before the cut"
    assert all(atr_v is not None and pct is not None for atr_v, pct in before.values())

    spiked_hits = bs.replay_scenarios_detailed("AAPL", _spiked(df, cut), "4w", gates=GATES)

    assert _stop_fields(spiked_hits, cut) == before


def test_stop_atr_is_the_signal_close_distance_in_atr14_units(df, hits):
    hit = hits[len(hits) // 2]
    window = df.iloc[:hit.i + 1]
    close = float(window["Close"].iloc[-1])
    expected = abs(close - hit.plan.stop_loss) / float(atr(window, 14).iloc[-1])

    assert hit.plan.entry_context["stop_atr"] == pytest.approx(expected, abs=1e-6)


def test_stop_atr_from_the_truncated_spiked_frame_matches_the_replay(df, hits):
    hit = hits[len(hits) // 2]
    spiked = _spiked(df, min(hit.i + 1, len(df) - 1))

    direct = _direct(spiked.iloc[:hit.i + 1], hit)

    assert direct["stop_atr"] == hit.plan.entry_context["stop_atr"]
    assert direct["stop_pct"] == hit.plan.entry_context["stop_pct"]


def test_the_check_is_sensitive_to_the_signal_bar_itself(df, hits):
    """Control: spiking FROM the signal bar (inclusive) must move stop_atr,
    so the two tests above would catch a frame that leaked."""
    hit = hits[len(hits) // 2]
    spiked = _spiked(df, hit.i)

    direct = _direct(spiked.iloc[:hit.i + 1], hit)

    assert direct["stop_atr"] != hit.plan.entry_context["stop_atr"]
