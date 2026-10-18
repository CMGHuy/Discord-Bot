"""v157 FC7: run_arm, get_engine and both arms engines carry an optional
instrument down to simulate_exit; None keeps v1. ArmTrade rows keep the
signal date; their r_multiple is the walk's (net, under v2) r_total."""
import pandas as pd
import pytest

from swingbot.core.backtesting.arms import confluence_engine, engine, strategy_engine
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.market.strategy_types import MIN_BARS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
SIGNAL = (100.0, 100.5, 99.5, 100.0)
DRIFT = (101.0, 102.0, 100.5, 101.5)
TARGET = (102.0, 111.0, 101.5, 110.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _window(df, first):
    return str(df.index[first].date()), str(df.index[-1].date())


def _spy(monkeypatch, module):
    seen = []
    real = module.simulate_exit

    def spy(df, index, plan, **kwargs):
        seen.append(kwargs.get("instrument"))
        return real(df, index, plan, **kwargs)

    monkeypatch.setattr(module, "simulate_exit", spy)
    return seen


# --- construction ------------------------------------------------------------------

@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_hands_the_instrument_to_the_engine(engine_id):
    assert engine.get_engine(engine_id, instrument=V2).instrument is V2
    assert engine.get_engine(engine_id).instrument is None


def test_strategy_engine_keeps_its_positional_arguments():
    built = StrategyEngine(("RSI",), None, V2)
    assert (built.strategies, built.compression_context, built.instrument) == (("RSI",), None, V2)


@pytest.mark.parametrize("instrument", [None, V2], ids=["v1", "v2"])
def test_run_arm_forwards_the_instrument_to_every_engine(monkeypatch, instrument):
    seen = []

    class Fake:
        def __init__(self, engine_id):
            self.engine_id = engine_id

        def run_ticker(self, ticker, df, horizons, signal_window, params):
            return [self.engine_id]

    def fake_get_engine(engine_id, *, instrument=None):
        seen.append((engine_id, instrument))
        return Fake(engine_id)

    monkeypatch.setattr(engine, "get_engine", fake_get_engine)
    kwargs = {} if instrument is None else {"instrument": instrument}
    out = engine.run_arm("T", None, ("strategy", "confluence"), ("4w",),
                         ("2024-01-01", "2024-12-31"), {}, **kwargs)
    assert out == ["strategy", "confluence"]
    assert seen == [("strategy", instrument), ("confluence", instrument)]


# --- the confluence engine -------------------------------------------------------

def _confluence(monkeypatch, instrument):
    df = make_ohlcv([SIGNAL, DRIFT, TARGET, DRIFT])

    def one_scenario(ticker, signal_df, horizon_key, params=None):
        yield 0, _plan()

    monkeypatch.setattr(confluence_engine, "replay_scenarios", one_scenario)
    seen = _spy(monkeypatch, confluence_engine)
    trades = ConfluenceEngine(instrument=instrument).run_ticker(
        "T", df, ("4w",), _window(df, 0), None)
    return df, seen, trades


def test_confluence_engine_walks_under_the_instrument(monkeypatch):
    df, seen, [trade] = _confluence(monkeypatch, V2)
    assert seen == [V2]
    assert trade.entry_date == str(df.index[0].date())        # ArmTrade keeps the signal date
    assert trade.r_multiple == simulate_exit(df, 0, _plan(), scale_out=True,
                                             instrument=V2).r_total


def test_confluence_engine_default_is_v1(monkeypatch):
    df, seen, [trade] = _confluence(monkeypatch, None)
    assert seen == [None]
    assert trade.r_multiple == simulate_exit(df, 0, _plan(), scale_out=True).r_total


def test_confluence_v2_r_differs_from_v1_on_the_same_plan(monkeypatch):
    _, _, [v1] = _confluence(monkeypatch, None)
    _, _, [v2] = _confluence(monkeypatch, V2)
    assert v2.r_multiple != v1.r_multiple      # next-open fill and costs, not the signal close


# --- the strategy engine ---------------------------------------------------------

def _strategy(monkeypatch, instrument):
    signal = MIN_BARS["4w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, DRIFT, TARGET] + [100.0] * 8)

    def one_signal(self, frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(StrategyEngine, "_entries", one_signal)
    monkeypatch.setattr(StrategyEngine, "_candidate_plan", lambda self, *a, **k: (_plan(), {}))
    monkeypatch.setattr(strategy_engine, "exit_params_for", lambda strategy: {"tp2": None})
    seen = _spy(monkeypatch, strategy_engine)
    trades = StrategyEngine(strategies=("RSI",), instrument=instrument).run_ticker(
        "T", df, ("4w",), _window(df, signal), None)
    return df, signal, seen, trades


def test_strategy_engine_walks_under_the_instrument(monkeypatch):
    df, signal, seen, [trade] = _strategy(monkeypatch, V2)
    assert seen == [V2]
    assert trade.entry_date == str(df.index[signal].date())
    assert trade.r_multiple == simulate_exit(df, signal, _plan(), scale_out=True,
                                             instrument=V2).r_total


def test_strategy_engine_default_is_v1(monkeypatch):
    df, signal, seen, [trade] = _strategy(monkeypatch, None)
    assert seen == [None]
    assert trade.r_multiple == simulate_exit(df, signal, _plan(), scale_out=True).r_total
