"""Simple Postgres-backed watchlist of tickers."""


def load_watchlist() -> list[str]:
    from swingbot.core.db.repositories.watchlist import watchlist_repo
    return watchlist_repo().tickers()


def save_watchlist(tickers: list[str]):
    from swingbot.core.db.repositories.watchlist import watchlist_repo
    return watchlist_repo().replace(sorted(set(t.upper() for t in tickers)))


def add_ticker(ticker: str) -> list[str]:
    from swingbot.core.db.repositories.watchlist import watchlist_repo
    return watchlist_repo().add(ticker)


def remove_ticker(ticker: str) -> list[str]:
    from swingbot.core.db.repositories.watchlist import watchlist_repo
    return watchlist_repo().remove(ticker)


def clear_watchlist() -> list[str]:
    return save_watchlist([])
