"""Backfill guards (spec §2): 120 requests a minute beside the live scan,
backoff on 429/5xx, auth errors stop the run, no run in the regular session
without --force-hours, a 3 GiB free-space floor, a percent after 15 minutes."""
from collections import namedtuple
from datetime import datetime, timezone

import pytest

from alpaca_history import guards
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss


class FakeClock:
    """A monotonic clock whose sleep advances it and records each wait."""
    def __init__(self, t=1000.0):
        self.t, self.sleeps = t, []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 6))
        self.t += seconds


def _bucket(rate=guards.RATE_PER_MINUTE):
    clock = FakeClock()
    return guards.TokenBucket(rate, clock=clock, sleep=clock.sleep), clock


def _miss(status):
    """An AlpacaMiss shaped like AlpacaProvider._call raises it."""
    cause = Exception(f"http {status}")
    if status is not None:
        cause.status_code = status
    exc = AlpacaMiss(str(cause))
    exc.__cause__ = cause
    return exc


# --- token bucket ---------------------------------------------------------------

def test_first_call_is_free_then_calls_are_spaced_half_a_second():
    bucket, clock = _bucket()
    for _ in range(4):
        bucket.acquire()
    assert clock.sleeps == [0.5, 0.5, 0.5]
    assert bucket.calls == 4 and bucket.interval == 0.5


def test_never_more_than_the_rate_in_one_minute():
    bucket, clock = _bucket()
    start = clock.t
    for _ in range(guards.RATE_PER_MINUTE + 1):
        bucket.acquire()
    assert clock.t - start >= 60.0          # call 121 waits for the window to roll


def test_idle_time_is_not_banked_as_a_burst():
    bucket, clock = _bucket()
    bucket.acquire()
    clock.t += 30.0                          # idle
    bucket.acquire()
    bucket.acquire()
    assert clock.sleeps == [0.5]


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        guards.TokenBucket(0)


# --- backoff --------------------------------------------------------------------

def test_status_of_reads_the_cause_then_the_exception():
    assert guards.status_of(_miss(429)) == 429
    own = AlpacaMiss("x"); own.status_code = 503
    assert guards.status_of(own) == 503
    assert guards.status_of(_miss(None)) is None


def _flaky(errors, result="bars"):
    calls = []

    def fn():
        calls.append(1)
        if errors:
            raise errors.pop(0)
        return result
    return fn, calls


@pytest.mark.parametrize("status", [429, 500, 503, None])
def test_retryable_errors_back_off_exponentially(status):
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(status), _miss(status)])
    assert guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep) == "bars"
    assert backoff.sleeps == [2.0, 4.0]
    assert len(calls) == 3 and bucket.calls == 3       # one token per attempt


@pytest.mark.parametrize("status", [400, 404, 422])
def test_client_errors_are_not_retried(status):
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(status)])
    with pytest.raises(AlpacaMiss):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == 1 and backoff.sleeps == []


def test_auth_error_stops_at_once():
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([AlpacaAuthError("forbidden")])
    with pytest.raises(AlpacaAuthError):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == 1 and backoff.sleeps == []


def test_retries_are_bounded():
    bucket, _ = _bucket()
    backoff = FakeClock()
    fn, calls = _flaky([_miss(429) for _ in range(10)])
    with pytest.raises(AlpacaMiss):
        guards.call_with_backoff(fn, limiter=bucket, sleep=backoff.sleep)
    assert len(calls) == guards.MAX_RETRIES + 1
    assert backoff.sleeps == [2.0, 4.0, 8.0, 16.0, 32.0]


# --- market hours ----------------------------------------------------------------

def test_refuses_during_the_regular_session():
    wednesday_11_et = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(guards.HoursGuardError, match="--force-hours"):
        guards.assert_outside_hours(wednesday_11_et)


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc),   # Wed 17:00 ET, after the close
    datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc),   # Wed 09:00 ET, before the open
    datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc),   # Sunday
])
def test_allows_outside_the_regular_session(now):
    guards.assert_outside_hours(now)


def test_force_hours_overrides():
    guards.assert_outside_hours(datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc), force=True)


# --- disk ------------------------------------------------------------------------

Usage = namedtuple("Usage", "total used free")
GIB = 1024 ** 3


def test_estimate_is_linear_in_tickers_and_years():
    one = guards.estimate_bytes(1, ["daily"], 1.0)
    assert one == 252 * 64
    assert guards.estimate_bytes(10, ["daily"], 2.0) == 20 * one


def test_full_watchlist_estimate_is_about_a_gigabyte():
    estimate = guards.estimate_bytes(77, ["15min", "hourly", "daily"], 10.8)
    assert 0.8 * GIB < estimate < 1.5 * GIB          # spec §1: about 1.2 GB


def test_disk_guard_passes_with_room(tmp_path):
    guards.check_disk(tmp_path, 1 * GIB, usage=lambda p: Usage(0, 0, 5 * GIB))


def test_disk_guard_refuses_below_the_floor(tmp_path):
    with pytest.raises(guards.DiskGuardError, match="3 GiB"):
        guards.check_disk(tmp_path, int(2.5 * GIB), usage=lambda p: Usage(0, 0, 5 * GIB))


def test_disk_guard_asks_about_the_nearest_existing_directory(tmp_path):
    asked = []
    guards.check_disk(tmp_path / "market_data" / "15min", 0,
                      usage=lambda p: asked.append(p) or Usage(0, 0, 10 * GIB))
    assert asked == [tmp_path]


# --- progress --------------------------------------------------------------------

def test_progress_is_silent_for_fifteen_minutes_then_prints_each_new_percent():
    clock, lines = FakeClock(), []
    progress = guards.Progress(200, clock=clock, out=lines.append)
    progress.step("AAPL/daily")
    clock.t += 899
    progress.step("AAPL/hourly")
    assert lines == []
    clock.t += 2
    progress.step("AAPL/15min")          # 3/200 = 1%
    progress.step("MSFT/daily")          # 4/200 = 2%
    progress.step("MSFT/hourly")         # 5/200 = 2%, no new line
    assert lines == ["[  1%] 3/200 AAPL/15min", "[  2%] 4/200 MSFT/daily"]
