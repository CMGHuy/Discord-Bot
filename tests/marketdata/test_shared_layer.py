"""v171 D1/D2/D6: the shared layer against an in-memory repository."""
import contextlib
import inspect
import logging
import os
from datetime import datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.marketdata.shared import budget, counters, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind, cache_key, fresh_request

T0 = datetime(2026, 10, 16, 14, 30, tzinfo=timezone.utc)
Q = DataKind.QUOTE


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return T0 + timedelta(seconds=self.t)

    def mono(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeRepo:
    def __init__(self, clock):
        self.rows, self.clock, self.fail, self.reads = {}, clock, set(), 0

    def _check(self, op):
        if op in self.fail:
            raise TimeoutError(f"{op} timed out")

    def read_entries(self, keys, *, conn):
        self._check("read")
        self.reads += 1
        return {k: dict(self.rows[k]) for k in keys if k in self.rows}

    def write_entries(self, rows, *, conn):
        self._check("write")
        for r in rows:
            self.rows[r["key"]] = {**r, "lease_holder": None, "lease_until": None}

    def try_lease(self, key, holder, seconds, *, kind, symbol, conn):
        self._check("lease")
        row = self.rows.setdefault(key, {"key": key, "fetched_at": None, "lease_holder": None,
                                         "lease_until": None})
        free = row["lease_until"] is None or row["lease_until"] < self.clock.now()
        if free or row["lease_holder"] == holder:
            row.update(lease_holder=holder, lease_until=self.clock.now() + timedelta(seconds=seconds))
            return True
        return False

    def release_lease(self, key, holder, *, conn):
        row = self.rows.get(key)
        if row and row["lease_holder"] == holder:
            row.update(lease_holder=None, lease_until=None)

    def seed(self, sym, value, age_s, lease_holder=None, lease_for=0.0):
        self.rows[cache_key(Q, sym)] = {
            "key": cache_key(Q, sym), "kind": "quote", "symbol": sym, "source": "alpaca",
            "fetched_at": self.clock.now() - timedelta(seconds=age_s), "value": value,
            "lease_holder": lease_holder,
            "lease_until": (self.clock.now() + timedelta(seconds=lease_for)) if lease_holder else None}


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    repo = FakeRepo(clock)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    monkeypatch.setattr(layer, "market_shared_repo", lambda: repo)
    monkeypatch.setattr(layer, "side_connection", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(layer, "_now", clock.now)
    monkeypatch.setattr(layer, "_monotonic", clock.mono)
    monkeypatch.setattr(layer, "_sleep", lambda s: clock.sleep(s))   # late-bound: tests swap it
    monkeypatch.setattr(counters, "flush", lambda force=False: 0)
    counters.reset()
    return repo, clock


def fetcher(values, calls):
    def fetch(symbols):
        calls.append(list(symbols))
        return {s: values[s] for s in symbols if s in values}
    return fetch


def outcomes():
    return sorted((r[3], r[4], r[5]) for r in counters.snapshot_and_clear())


def test_off_mode_is_a_plain_pass_through(env, monkeypatch):
    repo, _ = env
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 1.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert got["AAPL"].value == 1.0 and got["AAPL"].outcome == "fetched"
    assert calls == [["AAPL"]] and repo.reads == 0 and outcomes() == []


def test_count_mode_fetches_every_time_and_counts(env, monkeypatch):
    repo, _ = env
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    calls = []
    for _ in range(2):
        layer.get(Q, ["AAPL", "MSFT"], fetcher({"AAPL": 1.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert len(calls) == 2 and repo.reads == 0
    assert outcomes() == [("scan", "failed", 2), ("scan", "fetched", 2)]


def test_miss_fetches_once_in_one_batch_then_hits(env):
    repo, clock = env
    calls = []
    fetch = fetcher({"AAPL": 1.0, "MSFT": 2.0}, calls)
    layer.get(Q, ["AAPL", "MSFT"], fetch, asker=Asker.SCAN, provider="alpaca")
    clock.sleep(10)
    got = layer.get(Q, ["AAPL", "MSFT"], fetch, asker=Asker.SCAN, provider="alpaca")
    assert calls == [["AAPL", "MSFT"]]
    assert got["MSFT"].outcome == "hit" and got["MSFT"].age_s(clock.now()) == 10.0
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("scan", "fetched", 2), ("scan", "hit", 2)]


@pytest.mark.parametrize("asker,refetch", [
    (Asker.SCAN, False), (Asker.REQUOTE, True), (Asker.ADMIN_PAGE, False)])
def test_each_asker_gets_its_own_window(env, asker, refetch):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=10)
    calls = []
    layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=asker, provider="alpaca")
    assert bool(calls) is refetch


def test_a_fresh_admin_request_bypasses_reuse_and_max_age_overrides(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=3)
    calls = []
    with fresh_request():
        layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.ADMIN_PAGE, provider="alpaca")
    repo.seed("MSFT", 1.0, age_s=3)
    layer.get(Q, ["MSFT"], fetcher({"MSFT": 2.0}, calls), asker=Asker.SCAN, provider="alpaca", max_age_s=1)
    repo.seed("NVDA", 1.0, age_s=0)  # max_age_s=0.0 (V171-19 re-quote): `is not None`, never truthiness
    layer.get(Q, ["NVDA"], fetcher({"NVDA": 2.0}, calls), asker=Asker.REQUOTE, provider="alpaca", max_age_s=0.0)
    assert calls == [["AAPL"], ["MSFT"], ["NVDA"]]


def test_a_waiter_gets_the_holders_result(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="other", lease_for=30)
    original = clock.sleep

    def sleep_then_land(s):
        original(s)
        repo.rows[cache_key(Q, "AAPL")].update(value=9.0, fetched_at=clock.now(),
                                               lease_holder=None, lease_until=None)
    clock.sleep = sleep_then_land
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert calls == [] and got["AAPL"].value == 9.0 and got["AAPL"].outcome == "shared-wait"


def test_deadline_tier_1_fetches_itself_tier_5_gets_the_stale_value(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="hung", lease_for=300)
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.STOP_MONITOR,
                    provider="alpaca", deadline_s=0.5)
    assert calls == [["AAPL"]] and got["AAPL"].value == 2.0
    repo.seed("MSFT", 1.0, age_s=600, lease_holder="hung", lease_for=300)
    got = layer.get(Q, ["MSFT"], fetcher({"MSFT": 2.0}, calls), asker=Asker.ADMIN_PAGE,
                    provider="alpaca", deadline_s=0.5)
    assert calls == [["AAPL"]] and got["MSFT"].value == 1.0 and got["MSFT"].age_s(clock.now()) > 500


def test_budget_deferred_serves_the_freshest_cached_value(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=600)

    def denied(symbols):
        raise budget.BudgetDeferred("tier 5")
    got = layer.get(Q, ["AAPL", "NEW"], denied, asker=Asker.ADMIN_PAGE, provider="alpaca")
    assert got["AAPL"].value == 1.0 and got["AAPL"].outcome == "budget-deferred" and "NEW" not in got
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("admin_page", "budget-deferred", 2)]


def test_a_failing_fetch_releases_leases_and_raises(env):
    repo, _ = env

    def boom(symbols):
        raise ConnectionError("provider down")
    with pytest.raises(ConnectionError):
        layer.get(Q, ["AAPL"], boom, asker=Asker.SCAN, provider="alpaca")
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
    assert outcomes() == [("scan", "failed", 1)]


@pytest.mark.parametrize("op", ["read", "lease"])
def test_postgres_errors_fail_open_to_a_direct_fetch(env, caplog, op):
    repo, _ = env
    repo.fail.add(op)
    calls = []
    with caplog.at_level(logging.WARNING):
        got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.STOP_MONITOR,
                        provider="alpaca")
    assert calls == [["AAPL"]] and got["AAPL"].value == 2.0
    assert any("failed open" in r.message for r in caplog.records)


def test_a_blank_reply_never_overwrites_the_last_good_value(env):
    repo, _ = env
    repo.seed("AAPL", 1.0, age_s=600)
    layer.get(Q, ["AAPL"], lambda s: {"AAPL": None}, asker=Asker.SCAN, provider="alpaca")
    assert repo.rows[cache_key(Q, "AAPL")]["value"] == 1.0


def test_spot_metals_are_fetched_but_never_cached(env):
    repo, _ = env
    calls = []
    got = layer.get(Q, ["XAUUSD", "AAPL"], fetcher({"XAUUSD": 4000.0, "AAPL": 1.0}, calls),
                    asker=Asker.SCAN, provider="alpaca")
    assert got["XAUUSD"].value == 4000.0 and calls == [["AAPL", "XAUUSD"]]
    assert not any("XAUUSD" in k for k in repo.rows)


def test_encode_and_decode_wrap_the_stored_value(env):
    repo, _ = env
    layer.get(Q, ["AAPL"], lambda s: {"AAPL": 1.5}, asker=Asker.SCAN, provider="alpaca",
              encode=lambda v: {"p": v}, decode=lambda d: d["p"])
    assert repo.rows[cache_key(Q, "AAPL")]["value"] == {"p": 1.5}
    got = layer.get(Q, ["AAPL"], lambda s: {}, asker=Asker.SCAN, provider="alpaca",
                    decode=lambda d: d["p"])
    assert got["AAPL"].value == 1.5
    assert layer.last_cached(Q, ["AAPL"])["AAPL"].value == {"p": 1.5}


def test_lease_for_bar_writers(env, monkeypatch):
    repo, _ = env
    with layer.lease(DataKind.DAILY_BARS, "AAPL", asker=Asker.BACKGROUND) as held:
        assert held is True
        assert repo.rows[cache_key(DataKind.DAILY_BARS, "AAPL")]["lease_holder"].startswith(layer.HOLDER_ID)
    assert repo.rows[cache_key(DataKind.DAILY_BARS, "AAPL")]["lease_holder"] is None
    repo.try_lease(cache_key(DataKind.DAILY_BARS, "MSFT"), "other", 300, kind="daily", symbol="MSFT", conn=None)
    with layer.lease(DataKind.DAILY_BARS, "MSFT", asker=Asker.BACKGROUND, deadline_s=0.3) as held:
        assert held is False
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "count")
    with layer.lease(DataKind.DAILY_BARS, "MSFT", asker=Asker.BACKGROUND) as held:
        assert held is True


def test_get_deadline_defaults_to_10s_and_holder_id_is_unique_per_process():
    assert inspect.signature(layer.get).parameters["deadline_s"].default == 10.0
    assert inspect.signature(layer.lease).parameters["deadline_s"].default == 30.0
    host_pid, suffix = layer.HOLDER_ID.rsplit(":", 1)
    assert host_pid.endswith(f":{os.getpid()}") and len(suffix) == 8


def _land_on_sleep(repo, clock, value):
    original = clock.sleep

    def sleep_then_land(s):
        original(s)
        repo.rows[cache_key(Q, "AAPL")].update(value=value, fetched_at=clock.now(),
                                               lease_holder=None, lease_until=None)
    clock.sleep = sleep_then_land


def test_a_window_zero_waiter_takes_the_holders_write(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="other", lease_for=30)
    _land_on_sleep(repo, clock, 9.0)
    calls = []
    with fresh_request():
        got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.ADMIN_PAGE,
                        provider="alpaca")
    assert calls == [] and got["AAPL"].value == 9.0 and got["AAPL"].outcome == "shared-wait"


def test_mixed_case_symbols_fetch_once_and_return_both(env):
    repo, _ = env
    calls = []
    got = layer.get(Q, ["aapl", "AAPL"], fetcher({"aapl": 1.0}, calls), asker=Asker.SCAN,
                    provider="alpaca")
    assert calls == [["aapl"]] and got["aapl"].value == 1.0 and got["AAPL"].value == 1.0
    assert repo.rows[cache_key(Q, "AAPL")]["symbol"] == "AAPL"


def test_a_read_error_while_waiting_goes_straight_to_the_deadline_rule(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="hung", lease_for=300)
    original = clock.sleep

    def sleep_then_break(s):
        original(s)
        repo.fail.add("read")
    clock.sleep = sleep_then_break
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.ADMIN_PAGE,
                    provider="alpaca")
    assert calls == [] and clock.t == pytest.approx(0.1)
    assert got["AAPL"].value == 1.0 and got["AAPL"].outcome == "shared-wait"


def test_a_foreign_lease_expiring_mid_wait_is_claimed_and_fetched(env):
    repo, clock = env
    repo.seed("AAPL", 1.0, age_s=600, lease_holder="dead", lease_for=0.25)
    calls = []
    got = layer.get(Q, ["AAPL"], fetcher({"AAPL": 2.0}, calls), asker=Asker.SCAN, provider="alpaca")
    assert calls == [["AAPL"]] and got["AAPL"].outcome == "fetched" and clock.t < 1.0
    assert repo.rows[cache_key(Q, "AAPL")]["lease_holder"] is None
