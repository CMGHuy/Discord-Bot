"""V238-2: arms.net_basis books one closed trade on a requested R basis. "net" re-prices
the row through frictions.net_r_legs (planned risk, both sides slipped, one commission,
borrow on shorts over calendar days held); "gross" is the walk's r_total. A basis is
refused under any non-v1 instrument."""
import types

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import net_basis
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.edge.frictions import borrow_r, net_r_legs
from swingbot.core.planning.exit_sim import ExitResult

FRIDAY_START = pd.bdate_range("2024-01-05", periods=8)     # 2024-01-05 is a Friday


@pytest.fixture(autouse=True)
def _costs(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _frame():
    return pd.DataFrame({"Close": range(len(FRIDAY_START))}, index=FRIDAY_START)


def _result(entry_index=0, exit_index=1, legs=None, r_total=1.5):
    legs = legs or [{"fraction": 1.0, "exit_price": 108.0, "r": 1.6, "reason": "tp1"}]
    return ExitResult(outcome="win", runner_outcome=None, entry_index=entry_index,
                      exit_index=exit_index, entry_price=100.0, r_total=r_total, legs=legs)


def _long():
    return types.SimpleNamespace(stop_loss=95.0, direction="bullish")


# --- holding_days ----------------------------------------------------------------------

def test_holding_days_counts_calendar_days_over_a_weekend():
    df = _frame()
    assert net_basis.holding_days(df, _result(0, 0)) == 0
    assert net_basis.holding_days(df, _result(0, 1)) == 3          # Friday -> Monday
    assert net_basis.holding_days(df, _result(0, 5)) == 7
    assert type(net_basis.holding_days(df, _result(0, 5))) is int


# --- booked_r --------------------------------------------------------------------------

def test_gross_basis_is_the_walk_r_total():
    assert net_basis.booked_r(_long(), _result(r_total=1.234), _frame(), r_basis="gross") == 1.234


def test_net_basis_prices_every_leg_through_net_r_legs():
    legs = [{"fraction": 0.5, "exit_price": 105.0, "r": 1.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 112.0, "r": 2.4, "reason": "runner_tp2"}]
    result = _result(0, 3, legs=legs, r_total=1.7)              # gross: 0.5 x 1.0 + 0.5 x 2.4
    expected = net_r_legs(100.0, 95.0, "bullish", legs, days=net_basis.holding_days(_frame(), result))
    assert net_basis.booked_r(_long(), result, _frame(), r_basis="net") == expected
    assert expected < result.r_total


def test_net_basis_charges_a_bearish_row_borrow_over_days_held():
    plan = types.SimpleNamespace(stop_loss=105.0, direction="bearish")
    legs = [{"fraction": 1.0, "exit_price": 92.0, "r": 1.6, "reason": "tp1"}]
    short_hold = net_basis.booked_r(plan, _result(0, 1, legs=legs), _frame(), r_basis="net")
    long_hold = net_basis.booked_r(plan, _result(0, 5, legs=legs), _frame(), r_basis="net")
    assert short_hold - long_hold == pytest.approx(borrow_r(100.0, 5.0, 7) - borrow_r(100.0, 5.0, 3), abs=1e-12)


def test_net_basis_never_charges_a_bullish_row_borrow():
    one = net_basis.booked_r(_long(), _result(0, 1), _frame(), r_basis="net")
    seven = net_basis.booked_r(_long(), _result(0, 5), _frame(), r_basis="net")
    assert one == seven


@pytest.mark.parametrize("basis", [None, "bogus", "NET"])
def test_booked_r_refuses_anything_but_net_or_gross(basis):
    with pytest.raises(ValueError, match="r_basis"):
        net_basis.booked_r(_long(), _result(), _frame(), r_basis=basis)


# --- check_basis -----------------------------------------------------------------------

@pytest.mark.parametrize("basis", [None, "net", "gross"])
def test_check_basis_accepts_the_known_bases_under_v1(basis):
    assert net_basis.check_basis(basis, instrument=None) is None
    assert net_basis.check_basis(basis, instrument=resolve("v1")) is None


def test_check_basis_refuses_an_unknown_basis():
    with pytest.raises(ValueError, match="r_basis"):
        net_basis.check_basis("bogus", instrument=None)


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_check_basis_refuses_any_basis_under_a_costed_instrument(basis):
    with pytest.raises(ValueError, match="instrument"):
        net_basis.check_basis(basis, instrument=resolve("v2"))
    assert net_basis.check_basis(None, instrument=resolve("v2")) is None


def test_r_bases_are_net_then_gross():
    assert net_basis.R_BASES == ("net", "gross")
