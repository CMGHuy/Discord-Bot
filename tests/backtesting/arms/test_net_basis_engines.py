"""V238-2b: get_engine, run_arm and both per-ticker engines carry r_basis. None (the
default) is today's booking, byte for byte, and today's call (no r_basis keyword); a
requested basis books every row -- Turtle Soup included -- through arms.net_basis."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import confluence_engine, engine, net_basis, strategy_engine
from swingbot.core.backtesting.arms import turtle_soup_research as tsr
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.market.strategy_types import MIN_BARS, TURTLE_SOUP
from swingbot.core.planning.exit_sim import ExitResult, simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

SIGNAL = (100.0, 100.5, 99.5, 100.0)
DRIFT = (101.0, 102.0, 100.5, 101.5)
TARGET = (102.0, 111.0, 101.5, 110.0)
FRIDAY_START = pd.bdate_range("2024-01-05", periods=8)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


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


def _frame():
    return pd.DataFrame({"Close": range(len(FRIDAY_START))}, index=FRIDAY_START)


def _result():
    return ExitResult(outcome="win", runner_outcome=None, entry_index=0, exit_index=1,
                      entry_price=100.0, r_total=1.5,
                      legs=[{"fraction": 1.0, "exit_price": 108.0, "r": 1.6, "reason": "tp1"}])


# --- engine seam -----------------------------------------------------------------------

@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_hands_the_basis_to_the_engine(engine_id):
    assert engine.get_engine(engine_id, r_basis="net").r_basis == "net"
    assert engine.get_engine(engine_id).r_basis is None


@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_refuses_a_basis_under_a_costed_instrument(engine_id):
    with pytest.raises(ValueError, match="instrument"):
        engine.get_engine(engine_id, instrument=resolve("v2"), r_basis="net")


@pytest.mark.parametrize("basis,forwarded", [(None, {}), ("net", {"r_basis": "net"}),
                                             ("gross", {"r_basis": "gross"})])
def test_run_arm_forwards_the_basis_only_when_set(monkeypatch, basis, forwarded):
    seen = []

    class Fake:
        def run_ticker(self, ticker, df, horizons, signal_window, params):
            return []

    def fake_get_engine(engine_id, *, instrument=None, **kwargs):
        seen.append(kwargs)
        return Fake()

    monkeypatch.setattr(engine, "get_engine", fake_get_engine)
    kwargs = {} if basis is None else {"r_basis": basis}
    engine.run_arm("T", None, ("strategy", "confluence"), ("4w",), ("2024-01-01", "2024-12-31"), {}, **kwargs)
    assert seen == [forwarded, forwarded]


# --- the confluence engine -------------------------------------------------------------

def _confluence(monkeypatch, r_basis):
    df = make_ohlcv([SIGNAL, DRIFT, TARGET, DRIFT])

    def one_scenario(ticker, signal_df, horizon_key, params=None):
        yield 0, _plan()

    monkeypatch.setattr(confluence_engine, "replay_scenarios", one_scenario)
    window = (str(df.index[0].date()), str(df.index[-1].date()))
    [trade] = ConfluenceEngine(r_basis=r_basis).run_ticker("T", df, ("4w",), window, None)
    return df, trade, simulate_exit(df, 0, _plan(), scale_out=True)


def test_confluence_default_books_the_gross_r_total(monkeypatch):
    _, trade, walk = _confluence(monkeypatch, None)
    assert trade.r_multiple == walk.r_total


def test_confluence_gross_basis_books_the_r_total(monkeypatch):
    _, trade, walk = _confluence(monkeypatch, "gross")
    assert trade.r_multiple == walk.r_total


def test_confluence_net_basis_books_the_net_row(monkeypatch):
    df, trade, walk = _confluence(monkeypatch, "net")
    assert trade.r_multiple == net_basis.booked_r(_plan(), walk, df, r_basis="net")
    assert trade.r_multiple < walk.r_total                        # same prices and risk, costs only subtract


# --- the strategy engine ---------------------------------------------------------------

def _strategy(monkeypatch, r_basis):
    signal = MIN_BARS["4w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, DRIFT, TARGET] + [100.0] * 8)

    def one_signal(self, frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(StrategyEngine, "_entries", one_signal)
    monkeypatch.setattr(StrategyEngine, "_candidate_plan", lambda self, *a, **k: (_plan(), {}))
    monkeypatch.setattr(strategy_engine, "exit_params_for", lambda strategy: {"tp2": None})
    window = (str(df.index[signal].date()), str(df.index[-1].date()))
    [trade] = StrategyEngine(strategies=("RSI",), r_basis=r_basis).run_ticker("T", df, ("4w",), window, None)
    return df, trade, simulate_exit(df, signal, _plan(), scale_out=True)


def test_strategy_default_books_the_gross_r_total(monkeypatch):
    _, trade, walk = _strategy(monkeypatch, None)
    assert trade.r_multiple == walk.r_total


def test_strategy_net_basis_books_the_net_row(monkeypatch):
    df, trade, walk = _strategy(monkeypatch, "net")
    assert trade.r_multiple == net_basis.booked_r(_plan(), walk, df, r_basis="net")
    assert trade.r_multiple < walk.r_total


def test_strategy_engine_keeps_its_positional_arguments_with_a_basis():
    built = StrategyEngine(("RSI",), None, None, r_basis="gross")
    assert (built.strategies, built.instrument, built.r_basis) == (("RSI",), None, "gross")


def _turtle_events(monkeypatch):
    events = []
    monkeypatch.setattr(tsr, "trade_event",
                        lambda ticker, df, date, plan, result, r_net: events.append(r_net) or {"r": r_net})
    return events


def test_turtle_soup_default_stays_on_its_own_net_function(monkeypatch):
    events = _turtle_events(monkeypatch)
    monkeypatch.setattr(tsr, "net_r", lambda plan, result: 0.123)
    r = StrategyEngine(strategies=("RSI",))._booked_r("T", _frame(), "2024-01-05",
                                                      _plan(strategy=TURTLE_SOUP), _result())
    assert r == 0.123 and events == [0.123]


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_turtle_soup_under_a_basis_is_booked_like_every_other_row(monkeypatch, basis):
    events = _turtle_events(monkeypatch)
    monkeypatch.setattr(tsr, "net_r", lambda plan, result: pytest.fail("the v180 path ran"))
    plan, result = _plan(strategy=TURTLE_SOUP), _result()
    r = StrategyEngine(strategies=("RSI",), r_basis=basis)._booked_r("T", _frame(), "2024-01-05", plan, result)
    assert r == net_basis.booked_r(plan, result, _frame(), r_basis=basis)
    assert events == [r]


def test_a_non_turtle_row_under_a_basis_logs_no_turtle_event(monkeypatch):
    events = _turtle_events(monkeypatch)
    StrategyEngine(strategies=("RSI",), r_basis="net")._booked_r("T", _frame(), "2024-01-05", _plan(), _result())
    assert events == []
