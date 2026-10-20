"""v171 D6: one budget per provider shared by every process; money first."""
import contextlib
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.db import side_engine
from swingbot.core.marketdata.shared import budget
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, PROVIDER_YF, Asker, fresh_request


class FakeRepo:
    def __init__(self, raise_on=None):
        self.takes, self.records, self.raise_on = [], [], raise_on
        self.state = (0, None)

    def take_token(self, provider, capacity, per_minute, reserve, *, conn):
        if self.raise_on == "take":
            raise TimeoutError("statement timeout")
        self.takes.append((provider, capacity, per_minute, reserve))
        return True

    def breaker_state(self, provider, *, conn):
        if self.raise_on == "state":
            raise TimeoutError("statement timeout")
        return self.state

    def breaker_record(self, provider, ok, failures_to_open, cooldown_s, *, conn):
        self.records.append((provider, ok, failures_to_open, cooldown_s))


@pytest.fixture
def fake(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ALPACA_BUDGET_PER_MINUTE", 150)
    monkeypatch.setattr(config, "YF_BUDGET_PER_MINUTE", 60)
    monkeypatch.setattr(budget, "market_shared_repo", lambda: repo)
    monkeypatch.setattr(budget, "side_connection", lambda: contextlib.nullcontext(None))
    return repo


def test_reserves_by_tier():
    assert budget.RESERVE_FRACTION == {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.25, 5: 0.50}


def test_capacity_per_provider(fake):
    assert budget.capacity(PROVIDER_ALPACA) == 150.0 and budget.capacity(PROVIDER_YF) == 60.0
    with pytest.raises(ValueError):
        budget.capacity("polygon")


@pytest.mark.parametrize("asker,reserve", [
    (Asker.STOP_MONITOR, 0.0), (Asker.REQUOTE, 0.0), (Asker.SCAN, 0.0),
    (Asker.BACKGROUND, 37.5), (Asker.ADMIN_DASHBOARD, 75.0), (Asker.ADMIN_PAGE, 75.0)])
def test_take_passes_the_tier_reserve(fake, asker, reserve):
    assert budget.take(PROVIDER_ALPACA, asker) is True
    assert fake.takes == [(PROVIDER_ALPACA, 150.0, 150.0, reserve)]


def test_fresh_admin_reload_runs_at_tier_5(fake):
    with fresh_request():
        budget.take(PROVIDER_YF, Asker.ADMIN_PAGE)
    assert fake.takes == [(PROVIDER_YF, 60.0, 60.0, 30.0)]


@pytest.mark.parametrize("mode", ["off", "count"])
def test_off_and_count_never_touch_the_store(fake, monkeypatch, mode):
    monkeypatch.setattr(config, "MARKETDATA_LAYER", mode)
    assert budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) is True
    assert budget.breaker_allows(PROVIDER_ALPACA) is True
    budget.breaker_record(PROVIDER_ALPACA, False)
    assert fake.takes == [] and fake.records == []


def test_store_errors_fail_open(fake):
    fake.raise_on = "take"
    assert budget.take(PROVIDER_ALPACA, Asker.STOP_MONITOR) is True
    fake.raise_on = "state"
    assert budget.breaker_allows(PROVIDER_ALPACA) is True


def test_breaker_reads_the_shared_open_window(fake):
    fake.state = (3, datetime.now(timezone.utc) + timedelta(seconds=120))
    assert budget.breaker_allows(PROVIDER_ALPACA) is False
    fake.state = (3, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert budget.breaker_allows(PROVIDER_ALPACA) is True


def test_breaker_record_uses_the_alpaca_breaker_knobs(fake, monkeypatch):
    monkeypatch.setattr(config, "ALPACA_BREAKER_FAILURES", 4)
    monkeypatch.setattr(config, "ALPACA_BREAKER_COOLDOWN_SECONDS", 90)
    budget.breaker_record(PROVIDER_ALPACA, False)
    assert fake.records == [(PROVIDER_ALPACA, False, 4, 90.0)]


@pytest.fixture
def shared_db(db_committed, db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(config, "ALPACA_BUDGET_PER_MINUTE", 10)   # refill 1 token / 6 s
    side_engine.reset()
    yield db_committed
    side_engine.reset()


def test_admin_storm_never_takes_budget_from_tiers_1_to_3(shared_db):
    admin = sum(budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) for _ in range(100))
    with fresh_request():
        admin += sum(budget.take(PROVIDER_ALPACA, Asker.ADMIN_PAGE) for _ in range(100))
    background = sum(budget.take(PROVIDER_ALPACA, Asker.BACKGROUND) for _ in range(100))
    money = [budget.take(PROVIDER_ALPACA, a)
             for a in (Asker.STOP_MONITOR, Asker.REQUOTE, Asker.SCAN, Asker.STOP_MONITOR, Asker.SCAN)]
    assert admin == 5                 # 10 -> 5: half the bucket stays for tiers 1-4
    assert background == 2            # 5 -> 3: a quarter (2.5) stays for tiers 1-3
    assert all(money[:3])             # tiers 1-3 still get tokens after the storm
