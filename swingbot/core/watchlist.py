"""Simple JSON-backed watchlist of tickers."""
import json
import logging
import os

from swingbot import config

log = logging.getLogger("swing-bot.watchlist")

DEFAULT_PATH = os.path.join(config.DATA_DIR, "watchlist.json")

# The live watchlist is runtime state, edited from Discord and the admin UI,
# so `d8cbd22` untracked it -- deploy/deploy.sh runs `git reset --hard`, which
# would otherwise revert your edits on every push. That left a fresh clone
# falling back to a 3-ticker stub, silently scanning almost nothing. This seed
# IS tracked (data/universe/ is static reference data, never written at
# runtime) so a new deployment starts on the real universe instead.
SEED_PATH = os.path.join(config.DATA_DIR, "universe", "watchlist_seed.json")

# Last-resort stub if the seed file is missing too (e.g. a partial checkout).
_FALLBACK = ["AAPL", "MSFT", "SPY"]


def load_watchlist(path: str = DEFAULT_PATH) -> list[str]:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    # First run: seed from the tracked universe file, never overwriting an
    # existing live watchlist (guarded by the exists() check above).
    seed = _FALLBACK
    try:
        with open(SEED_PATH, "r") as f:
            loaded = json.load(f)
        if isinstance(loaded, list) and loaded:
            seed = loaded
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        log.warning(
            "watchlist seed %s unreadable; falling back to %d-ticker stub",
            SEED_PATH, len(_FALLBACK),
        )
    save_watchlist(seed, path)
    return seed


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
