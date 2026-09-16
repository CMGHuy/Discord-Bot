"""Account config at each stage, and the explicit-path escape hatch."""
import os

import pytest

from swingbot import config
from swingbot.core.planning import account as acct


@pytest.fixture
def db_url(db_engine, monkeypatch):
    """Route repository-owned connections to the disposable test database."""
    monkeypatch.setattr(
        config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False)
    )
    from swingbot.core.db.engine import reset_engine
    reset_engine()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    acct.set_balance(5000.0)
    assert os.path.exists(os.path.join(data_dir, "account.json"))
    assert acct.load_account_config()["balance"] == 5000.0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:dual")
    acct.set_balance(5000.0)
    assert os.path.exists(os.path.join(data_dir, "account.json"))
    from swingbot.core.db.repositories.account import AccountRepository
    assert AccountRepository().load(conn=db_committed)["balance"] == 5000.0


def test_db_stage_writes_no_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(5000.0)
    assert not os.path.exists(os.path.join(data_dir, "account.json"))
    assert acct.load_account_config()["balance"] == 5000.0


def test_an_explicit_path_always_uses_the_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    path = os.path.join(data_dir, "elsewhere.json")
    acct.set_balance(1234.0, path=path)
    assert os.path.exists(path)
    assert acct.load_account_config(path=path)["balance"] == 1234.0
    from swingbot.core.db.repositories.account import AccountRepository
    assert AccountRepository().load(conn=db_committed) == {}


def test_defaults_still_layer_under_a_stored_config(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(5000.0)
    cfg = acct.load_account_config()
    assert cfg["balance"] == 5000.0
    assert "risk_pct" in cfg


def test_balance_history_accumulates_as_rows(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(1000.0)
    acct.apply_realized_pnl(100.0, meta={"reason": "test"})
    points = acct.get_balance_history()
    assert len(points) >= 1
    assert points[-1]["balance"] == pytest.approx(1100.0)
