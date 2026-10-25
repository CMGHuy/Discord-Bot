"""v187 D2: a brand-new account row seeded from .env is validated."""
import logging

import pytest

from swingbot import config as app_config
from swingbot.core.planning import account as acct


class _Repo:
    def __init__(self):
        self.saved = []

    def load(self):
        return None            # no stored row: the seed branch runs

    def save(self, cfg):
        self.saved.append(dict(cfg))


@pytest.fixture
def repo(monkeypatch):
    from swingbot.core.db.repositories import account as repo_mod
    fake = _Repo()
    monkeypatch.setattr(repo_mod, "account_repo", lambda: fake)
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return fake


def test_every_seed_key_falls_back_to_a_valid_field_default():
    for key, env_key in acct._SEED_ENV_KEYS.items():
        acct._validated(key, float(acct._field_default(env_key)))


def test_risk_field_default_is_one_percent_and_capped_at_two():
    field = next(f for f in app_config.FIELDS if f.key == "RISK_PER_TRADE_PCT")
    assert (field.default, field.max) == ("1.0", 2)
    assert "informational only" not in field.help.lower()


def test_a_ten_percent_env_risk_seeds_the_default_and_warns(repo, monkeypatch, caplog):
    monkeypatch.setattr(app_config, "RISK_PER_TRADE_PCT", 10.0)
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        cfg = acct.load_account_config()
    assert cfg["risk_pct"] == 1.0 and repo.saved[-1]["risk_pct"] == 1.0
    [record] = [r for r in caplog.records if "RISK_PER_TRADE_PCT" in r.getMessage()]
    assert "10.0" in record.getMessage() and "1.0" in record.getMessage()


@pytest.mark.parametrize("attr,key,bad", [
    ("ACCOUNT_BALANCE", "base_balance", -5.0),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 0),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", float("nan")),
    ("POSITION_SIZE_PCT_OF_ACCOUNT", "position_pct", 150.0),
    ("MAX_POSITION_VALUE_ABSOLUTE", "max_position_value_absolute", -1.0),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", float("inf")),
])
def test_each_invalid_seed_value_falls_back(repo, monkeypatch, attr, key, bad):
    monkeypatch.setattr(app_config, attr, bad)
    cfg = acct.load_account_config()
    assert cfg[key] == acct._validated(key, float(acct._field_default(attr)))


def test_a_valid_seed_is_kept_and_does_not_warn(repo, monkeypatch, caplog):
    monkeypatch.setattr(app_config, "RISK_PER_TRADE_PCT", 1.5)
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        cfg = acct.load_account_config()
    assert cfg["risk_pct"] == 1.5
    assert not [r for r in caplog.records if "RISK_PER_TRADE_PCT" in r.getMessage()]


def test_a_stored_row_is_not_rewritten_by_the_seed_check(monkeypatch):
    from swingbot.core.db.repositories import account as repo_mod
    stored = {"base_balance": 10_000.0, "risk_pct": 10.0, "balance_history": []}
    fake = _Repo()
    fake.load = lambda: dict(stored)
    monkeypatch.setattr(repo_mod, "account_repo", lambda: fake)
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    assert acct.load_account_config()["risk_pct"] == 10.0   # the sizing backstop covers it
