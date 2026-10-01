"""Account config in the account table."""
import pytest

from swingbot.core.planning import account as acct


def test_set_balance_round_trips_through_the_table():
    acct.set_balance(5000.0)
    assert acct.load_account_config()["balance"] == 5000.0


def test_defaults_still_layer_under_a_stored_config():
    acct.set_balance(5000.0)
    cfg = acct.load_account_config()
    assert cfg["balance"] == 5000.0
    assert "risk_pct" in cfg


def test_balance_history_accumulates_as_rows():
    acct.set_balance(1000.0)
    acct.apply_realized_pnl(100.0, meta={"reason": "test"})
    points = acct.get_balance_history()
    assert len(points) >= 1
    assert points[-1]["balance"] == pytest.approx(1100.0)
