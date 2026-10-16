"""Backfill guards (v162 spec §2).

The Alpaca key's budget (200 requests a minute) is shared with the live scan,
so the backfill spaces its calls at RATE_PER_MINUTE and backs off on 429/5xx.
An auth error stops the run. The regular session is off limits unless forced.
The disk also holds the PITR repository and the nightly dumps, so a run that
would leave less than MIN_FREE_BYTES free is refused before it writes.
"""
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence, TypeVar

from swingbot.core.market.session import is_regular_session
from swingbot.core.marketdata.providers.alpaca_provider import AlpacaAuthError, AlpacaMiss

T = TypeVar("T")

RATE_PER_MINUTE = 120
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
MIN_FREE_BYTES = 3 * 1024 ** 3
GIB = 1024 ** 3
#: bars a year per ticker: 252 sessions x 64 (15min, 04:00-20:00 ET) / 7 (hourly RTH) / 1
ROWS_PER_YEAR = {"15min": 252 * 64, "hourly": 252 * 7, "daily": 252}
#: CSV bytes per row: a "YYYY-MM-DD HH:MM:SS" stamp plus five floats; daily has a shorter stamp
BYTES_PER_ROW = {"15min": 72, "hourly": 72, "daily": 64}


class TokenBucket:
    """At most `rate_per_minute` acquisitions in any 60 seconds. The capacity
    is one token: idle time is never banked into a burst, so the live scan
    always keeps its share of the key's budget."""

    def __init__(self, rate_per_minute: int = RATE_PER_MINUTE, *,
                 clock=time.monotonic, sleep=time.sleep):
        if rate_per_minute <= 0:
            raise ValueError(f"rate_per_minute must be positive, got {rate_per_minute}")
        self.interval = 60.0 / rate_per_minute
        self.calls = 0
        self._clock, self._sleep = clock, sleep
        self._next = None

    def acquire(self) -> None:
        now = self._clock()
        if self._next is not None and now < self._next:
            self._sleep(self._next - now)
            now = self._next
        self._next = now + self.interval
        self.calls += 1


def status_of(exc: BaseException) -> int | None:
    """The HTTP status behind an AlpacaMiss: AlpacaProvider._call keeps the
    original exception on __cause__."""
    for candidate in (exc.__cause__, exc):
        status = getattr(candidate, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _retryable(exc: BaseException) -> bool:
    status = status_of(exc)
    return status is None or status == 429 or status >= 500


def call_with_backoff(fn: Callable[[], T], *, limiter: TokenBucket,
                      sleep=time.sleep, retries: int = MAX_RETRIES) -> T:
    """fn() under the rate limit. 429/5xx/unknown back off 2 s x 2^attempt,
    at most `retries` times; other misses and auth errors raise at once."""
    for attempt in range(retries + 1):
        limiter.acquire()
        try:
            return fn()
        except AlpacaAuthError:
            raise
        except AlpacaMiss as exc:
            if attempt >= retries or not _retryable(exc):
                raise
            sleep(BACKOFF_BASE_SECONDS * 2 ** attempt)
    raise AssertionError("unreachable: the last attempt returns or raises")


class HoursGuardError(RuntimeError):
    """The US regular session is open and --force-hours was not given."""


def assert_outside_hours(now: datetime | None = None, *, force: bool = False) -> None:
    if force:
        return
    if is_regular_session(now or datetime.now(timezone.utc)):
        raise HoursGuardError(
            "the US regular session is open (Mon-Fri 09:30-16:00 ET); the backfill shares the "
            "Alpaca key with the live scan -- run it outside hours or pass --force-hours")


class DiskGuardError(RuntimeError):
    """The run would leave less than MIN_FREE_BYTES free on the store's disk."""


def estimate_bytes(n_tickers: int, timeframes: Sequence[str], years: float) -> int:
    per_ticker_year = sum(ROWS_PER_YEAR[tf] * BYTES_PER_ROW[tf] for tf in timeframes)
    return int(per_ticker_year * n_tickers * max(years, 0.0))


def _nearest_existing(path: Path) -> Path:
    path = Path(path)
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def check_disk(path: Path, needed_bytes: int, *, usage=shutil.disk_usage) -> None:
    free = usage(_nearest_existing(path)).free
    if free - needed_bytes < MIN_FREE_BYTES:
        raise DiskGuardError(
            f"free space {free / GIB:.2f} GiB minus this run's estimate {needed_bytes / GIB:.2f} GiB "
            f"would leave less than {MIN_FREE_BYTES // GIB} GiB; the disk also holds the PITR "
            f"repository and the nightly dumps")


class Progress:
    """Silent for `after_seconds` (15 minutes), then one line per new integer
    percent: `[ NN%] done/total label`."""

    def __init__(self, total: int, *, clock=time.monotonic,
                 after_seconds: float = 900.0, out=print):
        self.total = max(int(total), 1)
        self.done = 0
        self._clock, self._after, self._out = clock, after_seconds, out
        self._start = clock()
        self._last_pct = None

    def step(self, label: str) -> None:
        self.done += 1
        if self._clock() - self._start < self._after:
            return
        pct = min(100, self.done * 100 // self.total)
        if pct == self._last_pct:
            return
        self._last_pct = pct
        self._out(f"[{pct:3d}%] {self.done}/{self.total} {label}")
