"""Account-currency conversion for the money the admin API serves (v194 B7).

`realized_pnl_amount` is stored in each ticker's QUOTE currency and stays so:
the account balance (hence 2% sizing and the kill switch) reads it. This
converts read-side: each part at its OWN exit date's rate (a stored
scaled-out trade sums its legs), same currency is identity with no lookup,
and a missing rate is never 1.0 -- the amount becomes None, `fx_missing`
True. Never feed a converted row to a percent or R derivation
(`closed_pnl_pct` divides the amount by `shares * entry`), hence copies.
`fx` is read at call time so `tests/admin/conftest.py` can pin it.
`swingbot.core.marketdata.fx_convert` holds the conversion (v201); this
wrapper only decides whether a request may fetch: never while the admin
refresher is on.
"""
from __future__ import annotations

from datetime import date

from swingbot.core.marketdata import fx_convert
from swingbot.core.marketdata.shared import admin_refresh

MONEY_FIELDS = fx_convert.MONEY_FIELDS
missing_count = fx_convert.missing_count


def to_account_currency(rows: list[dict], *, account: str | None = None) -> list[dict]:
    """Copies of `rows`, amounts in the account currency, `fx_missing` on each."""
    return fx_convert.to_account_currency(rows, account=account,
                                          fetch=not admin_refresh.refresher_on())


def convert_amount(amount: float | None, ticker: str | None, on: date, *,
                   account: str | None = None) -> tuple[float | None, bool]:
    """One loose amount (an open position's live P&L) at `on`'s rate."""
    return fx_convert.convert_amount(amount, ticker, on, account=account,
                                     fetch=not admin_refresh.refresher_on())
