"""v201: the refresher's symbol set -- open trades, open plans and the
watchlist as quotes; the fixed market tape as its own index tuple."""
from dataclasses import dataclass
from typing import Iterable

from swingbot.core.marketdata.shared import tape


@dataclass(frozen=True)
class SymbolSet:
    quotes: tuple[str, ...]
    index: tuple[str, ...]


def _open_trade_tickers() -> list:
    from swingbot.core.db.repositories.trades import trades_repo
    return [row.get("ticker") for row in trades_repo().open_trades()]


def _open_plan_tickers() -> list:
    from swingbot.core.db.repositories.plans import plans_repo
    return [plan.get("ticker") for plan in plans_repo().open_plans()]


def _watchlist() -> list:
    from swingbot.core.marketdata import watchlist
    return watchlist.load_watchlist()


def _clean(tickers: Iterable) -> set[str]:
    out = {str(t).strip().upper() for t in tickers if t}
    return {t for t in out if t and t not in tape.TAPE_FIXED}


def symbol_set() -> SymbolSet:
    quotes = (_clean(_open_trade_tickers()) | _clean(_open_plan_tickers())
              | _clean(_watchlist()))
    return SymbolSet(tuple(sorted(quotes)), tuple(tape.TAPE_FIXED))
