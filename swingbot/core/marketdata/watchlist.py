"""Simple JSON-backed watchlist of tickers."""
import os

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json

DEFAULT_PATH = os.path.join(config.DATA_DIR, "watchlist.json")


def load_watchlist(path: str = DEFAULT_PATH) -> list[str]:
    if os.path.exists(path):
        # A crash mid-write (power loss, OOM kill, docker restart) before
        # this module wrote atomically could leave a torn file on disk from
        # a still-running bot; read_json degrades to a fresh seed rather
        # than raising and taking the whole scan loop down with it.
        # `is None`, not falsy: an intentionally cleared watchlist reads
        # back as `[]`, which must stay empty rather than re-seed.
        loaded = read_json(path, default=None)
        return loaded if loaded is not None else _seed(path)
    return _seed(path)


def _seed(path: str) -> list[str]:
    # Seed with a few common, liquid tickers on first run
    default = ["AAPL", "MSFT", "SPY"]
    save_watchlist(default, path)
    return default


def save_watchlist(tickers: list[str], path: str = DEFAULT_PATH):
    atomic_write_json(path, sorted(set(t.upper() for t in tickers)))


def add_ticker(ticker: str, path: str = DEFAULT_PATH) -> list[str]:
    wl = load_watchlist(path)
    ticker = ticker.upper()
    if ticker not in wl:
        wl.append(ticker)
        save_watchlist(wl, path)
    return wl


def remove_ticker(ticker: str, path: str = DEFAULT_PATH) -> list[str]:
    wl = load_watchlist(path)
    ticker = ticker.upper()
    if ticker in wl:
        wl.remove(ticker)
        save_watchlist(wl, path)
    return wl


def clear_watchlist(path: str = DEFAULT_PATH) -> list[str]:
    save_watchlist([], path)
    return []
