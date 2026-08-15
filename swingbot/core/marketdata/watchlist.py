"""Simple JSON-backed watchlist of tickers."""
import json
import os

from swingbot import config

DEFAULT_PATH = os.path.join(config.DATA_DIR, "watchlist.json")


def load_watchlist(path: str = DEFAULT_PATH) -> list[str]:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    # Seed with a few common, liquid tickers on first run
    default = ["AAPL", "MSFT", "SPY"]
    save_watchlist(default, path)
    return default


def save_watchlist(tickers: list[str], path: str = DEFAULT_PATH):
    with open(path, "w") as f:
        json.dump(sorted(set(t.upper() for t in tickers)), f, indent=2)


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
