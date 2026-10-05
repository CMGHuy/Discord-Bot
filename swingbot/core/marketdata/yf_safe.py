"""Process-wide serialisation of ``yfinance.download``.

The pinned yfinance 0.2.66 builds ``download()`` on module globals
(``shared._DFS``/``shared._ERRORS``) that every call resets and then fills.
Two threads downloading at once in the same process corrupt each other's
results. Production showed three distinct symptoms:
"dictionary changed size during iteration", "No objects to concatenate",
and a frame carrying another ticker's columns. That last one flattened to
duplicate ``Open``/``High`` columns and 500'd ``/api/v1/market/chart``.
scanning/fetch.py avoids the race for the scan by downloading in spawned
processes. Every in-process caller (price batches, the admin chart,
data_store, the backtest cache) goes through ``download`` here instead.

The upstream fix landed in yfinance 1.4.0. Drop this lock only after
upgrading past that and re-verifying.

``yf.download`` is looked up at call time, so tests that monkeypatch
``yfinance.download`` still intercept every call.
"""
import logging
import threading

import yfinance as yf

log = logging.getLogger(__name__)

_DOWNLOAD_LOCK = threading.Lock()


class DownloadBusy(RuntimeError):
    """The download lock could not be taken inside the caller's wait limit.

    Expected under load, not a fault: the caller renders without the data and
    the next refresh retries. `no_retry` stops `with_retry` multiplying the
    wait by its attempt count.
    """
    no_retry = True


#: Wait limit applied when a caller passes none. `None` (every process but the
#: admin web process, v132) means wait as long as it takes -- the scanner and
#: backtests must never lose a download to a busy lock.
_default_lock_timeout: float | None = None


def set_default_lock_timeout(seconds: float | None) -> None:
    global _default_lock_timeout
    _default_lock_timeout = seconds


def download(*args, lock_timeout: float | None = None, **kwargs):
    limit = lock_timeout if lock_timeout is not None else _default_lock_timeout
    if not _DOWNLOAD_LOCK.acquire(timeout=-1 if limit is None else limit):
        raise DownloadBusy(f"yfinance download lock busy for {limit:g}s")
    try:
        frame = yf.download(*args, **kwargs)
    finally:
        _DOWNLOAD_LOCK.release()
    if frame is None or getattr(frame, "empty", False):
        log.debug("yfinance download returned no rows: tickers=%r",
                  kwargs.get("tickers", args[0] if args else None))
    return frame
