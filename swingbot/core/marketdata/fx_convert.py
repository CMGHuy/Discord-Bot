"""Account-currency conversion of stored money amounts (v194 B7; moved to core in v201).

`realized_pnl_amount` is stored in each ticker's QUOTE currency and stays so:
the account balance (hence 2% sizing and the kill switch) reads it. This
converts read-side: each part at its OWN exit date's rate (a stored
scaled-out trade sums its legs), same currency is identity with no lookup,
and a missing rate is never 1.0 -- the amount becomes None, `fx_missing`
True. Never feed a converted row to a percent or R derivation
(`closed_pnl_pct` divides the amount by `shares * entry`), hence copies.
`fx` is read at call time so `tests/admin/conftest.py` can pin it.
`fetch=False` (v201, the admin refresher is on) never touches the network:
quote codes come from the refresher's store and rates from the cache file.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from swingbot.core.marketdata import fx

#: The row fields a conversion rewrites. One: every admin money figure is a
#: sum or a walk of it (an open row carries its live amount in it too).
MONEY_FIELDS = ("realized_pnl_amount",)


def quote_code(ticker, *, fetch: bool = True) -> str | None:
    """fetch=True calls the one-argument form so seams pinned as `lambda ticker:` keep working."""
    return fx.quote_currency_code(ticker) if fetch else fx.quote_currency_code(ticker, fetch=False)


def rate(from_code: str, to_code: str, on, *, fetch: bool = True) -> float | None:
    """fetch=True calls the three-argument form (seams pinned without `refresh`)."""
    return fx.fx_rate(from_code, to_code, on) if fetch else fx.fx_rate(from_code, to_code, on, refresh=False)


def _day(stamp) -> date:
    """The date an ISO stamp names; today (UTC) when absent (a live amount)."""
    if stamp:
        try:
            return date.fromisoformat(str(stamp)[:10])
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


def _stored_quotes(tickers) -> dict[str, str | None]:
    """Upper-cased ticker -> stored quote code, one `fx.stored_codes` query (none when empty)."""
    keys = [key for key in (str(t or "").upper().strip() for t in tickers) if key]
    return fx.stored_codes(keys) if keys else {}


class _Rates:
    """One call's memo: each ticker's quote, each (currency, day) rate, once."""

    def __init__(self, account: str, fetch: bool = True, tickers=()):
        self.account = account
        self.fetch = fetch
        # v205 L1-b: never-fetch reads resolve every ticker of the call in one query;
        # fetch=True keeps the one-argument per-ticker seam (`quote_code`).
        self._quotes: dict[str, str | None] = {} if fetch else _stored_quotes(tickers)
        self._rates: dict[tuple[str, date], float | None] = {}

    def quote(self, ticker) -> str | None:
        key = str(ticker or "").upper().strip()
        if key not in self._quotes:
            self._quotes[key] = quote_code(key, fetch=self.fetch) if key else None
        return self._quotes[key]

    def rate(self, quote: str, on: date) -> float | None:
        if (quote, on) not in self._rates:
            self._rates[(quote, on)] = rate(quote, self.account, on, fetch=self.fetch)
        return self._rates[(quote, on)]


def _at(amount, quote: str, on: date, rates: _Rates) -> tuple[float | None, bool]:
    multiplier = rates.rate(quote, on)
    if multiplier is None:
        return None, True
    return round(float(amount) * multiplier, 2), False


def _priced_legs(row: dict) -> list[dict]:
    """A stored scaled-out trade's realized legs, each with an amount; else []."""
    if not row.get("legs"):
        return []
    from swingbot.core.tracking.performance import expand_realized_legs
    parts = expand_realized_legs(row)
    if len(parts) < 2 or any(p.get("realized_pnl_amount") is None for p in parts):
        return []
    return parts


def _converted(row: dict, rates: _Rates) -> tuple[float | None, bool]:
    """`(amount in the account currency, fx_missing)` for one row."""
    amount = row.get("realized_pnl_amount")
    if amount is None:
        return None, False
    quote = rates.quote(row.get("ticker"))
    if quote is None:
        return None, True
    if quote == rates.account:
        return amount, False
    legs = _priced_legs(row)
    if not legs:
        return _at(amount, quote, _day(row.get("closed_at")), rates)
    total = 0.0
    for leg in legs:
        value, missing = _at(leg["realized_pnl_amount"], quote, _day(leg.get("closed_at")), rates)
        if missing:
            return None, True
        total += value
    return round(total, 2), False


def to_account_currency(rows: list[dict], *, account: str | None = None,
                        fetch: bool = True) -> list[dict]:
    """Copies of `rows`, amounts in the account currency, `fx_missing` on each.
    `fetch=False` never touches the network (an unknown quote or rate flags the row)."""
    rates = _Rates(account or fx.account_currency_code(), fetch,
                   tickers=[row.get("ticker") for row in rows])
    out = []
    for row in rows:
        value, missing = _converted(row, rates)
        out.append({**row, "realized_pnl_amount": value, "fx_missing": missing})
    return out


def convert_amount(amount: float | None, ticker: str | None, on: date, *,
                   account: str | None = None, fetch: bool = True) -> tuple[float | None, bool]:
    """One loose amount (an open position's live P&L) at `on`'s rate."""
    row = {"realized_pnl_amount": amount, "ticker": ticker, "closed_at": on.isoformat()}
    return _converted(row, _Rates(account or fx.account_currency_code(), fetch))


def missing_count(rows: list[dict]) -> int:
    """How many rows a money figure left out for want of a rate."""
    return sum(1 for row in rows if row.get("fx_missing"))
