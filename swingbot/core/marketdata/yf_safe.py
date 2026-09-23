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
import threading

import yfinance as yf

_DOWNLOAD_LOCK = threading.Lock()


def download(*args, **kwargs):
    with _DOWNLOAD_LOCK:
        return yf.download(*args, **kwargs)
