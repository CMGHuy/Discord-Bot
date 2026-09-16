"""Simple JSON-backed watchlist of tickers."""
import os

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json

DEFAULT_PATH = os.path.join(config.DATA_DIR, "watchlist.json")


def _resolve(path: str | None) -> tuple[bool, str]:
    from swingbot.core.db import stages
    if path is not None:
        return False, path
    return stages.reads_db("watchlist"), os.path.join(config.DATA_DIR, "watchlist.json")


def load_watchlist(path: str | None = None) -> list[str]:
    use_db, file_path = _resolve(path)
    if use_db:
        from swingbot.core.db.repositories.watchlist import watchlist_repo
        return watchlist_repo().tickers()
    if os.path.exists(file_path):
        # A crash mid-write (power loss, OOM kill, docker restart) before
        # this module wrote atomically could leave a torn file on disk from
        # a still-running bot; read_json degrades to a fresh seed rather
        # than raising and taking the whole scan loop down with it.
        # `is None`, not falsy: an intentionally cleared watchlist reads
        # back as `[]`, which must stay empty rather than re-seed.
        loaded = read_json(file_path, default=None)
        return loaded if loaded is not None else _seed(file_path)
    seeded = _seed(file_path)
    if path is None:
        from swingbot.core.db import stages
        if stages.writes_db("watchlist"):
            from swingbot.core.db.repositories.watchlist import watchlist_repo
            watchlist_repo().replace(seeded)
    return seeded


def _seed(path: str) -> list[str]:
    # Seed with a few common, liquid tickers on first run
    default = ["AAPL", "MSFT", "SPY"]
    save_watchlist(default, path)
    return default


def save_watchlist(tickers: list[str], path: str | None = None):
    from swingbot.core.db import stages
    _, file_path = _resolve(path)
    result = sorted(set(t.upper() for t in tickers))
    if path is not None or stages.writes_json("watchlist"):
        atomic_write_json(file_path, result)
    if path is None and stages.writes_db("watchlist"):
        from swingbot.core.db.repositories.watchlist import watchlist_repo
        return watchlist_repo().replace(result)
    return result


def add_ticker(ticker: str, path: str | None = None) -> list[str]:
    from swingbot.core.db import stages
    if path is None and stages.reads_db("watchlist"):
        from swingbot.core.db.repositories.watchlist import watchlist_repo
        return watchlist_repo().add(ticker)
    wl = load_watchlist(path)
    ticker = ticker.upper()
    if ticker not in wl:
        wl.append(ticker)
        save_watchlist(wl, path)
    return wl


def remove_ticker(ticker: str, path: str | None = None) -> list[str]:
    from swingbot.core.db import stages
    if path is None and stages.reads_db("watchlist"):
        from swingbot.core.db.repositories.watchlist import watchlist_repo
        return watchlist_repo().remove(ticker)
    wl = load_watchlist(path)
    ticker = ticker.upper()
    if ticker in wl:
        wl.remove(ticker)
        save_watchlist(wl, path)
    return wl


def clear_watchlist(path: str | None = None) -> list[str]:
    return save_watchlist([], path)
