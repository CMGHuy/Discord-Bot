# v194 — UI integrity, part 2b: FX conversion seam and its frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Global Constraints, `### Standard task close`, `## Handoff`, `## Parallelisation` and the task ledger live in the index: [2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md](2026-10-25-v194-ui-tooltips-and-data-truth_0-index.md). Read one task at a time: `grep -n "^### Task V194-6c:" -A 400 <this file>`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-25-v194-ui-tooltips-and-data-truth.md](../specs/2026-10-25-v194-ui-tooltips-and-data-truth.md) § B7

Tasks: V194-6b (backend conversion seam), V194-6c (Analytics toggle and
missing-rate caveats). Both run after V194-6 (part 2), which creates
`swingbot/core/marketdata/fx.py` with `account_currency_code() -> str`,
`quote_currency_code(ticker: str) -> str | None` and
`fx_rate(from_code: str, to_code: str, on: date) -> float | None`.

**Display-only, partner-confirmed (2026-10-25).** The stored
`realized_pnl_amount` stays in the quote currency; sizing, the account
balance, the kill switch, `account_balance`, `equity_30d`, the trade
detail's `risk_amount`/`gap_risk_amount`, the CSV export and every Discord
command keep today's figures.

# Phase B7 — FX conversion

### Task V194-6b: B7 FX — one server-side conversion seam for admin money; `fx_missing` flags

**Model:** opus — a cross-module read-path change on money figures where the percent and R paths must keep reading the stored amount; a wrong seam silently skews `closed_pnl_pct`.

**Files:**
- Create: `swingbot/admin/api_v1/money.py`, `tests/admin/test_api_v1_money.py`
- Modify: `swingbot/admin/api_v1/trades.py`, `swingbot/admin/api_v1/analytics.py`, `swingbot/admin/api_v1/dashboard.py`, `swingbot/core/analytics/pnl_calendar.py`, `tests/admin/test_api_v1_trades.py`, `tests/admin/test_api_v1_analytics.py`
- Modify, beyond the ledger row (no other task edits them): `swingbot/admin/api_v1/calendar.py`, `tests/admin/conftest.py`, `tests/admin/test_api_v1_dashboard.py`, `tests/admin/test_api_v1_calendar.py`, `tests/admin/test_api_analytics.py`

**Interfaces:**
- Consumes (V194-6): `fx.account_currency_code() -> str`, `fx.quote_currency_code(ticker: str) -> str | None`, `fx.fx_rate(from_code: str, to_code: str, on: date) -> float | None`; existing `expand_realized_legs` (`swingbot/core/tracking/performance.py:485`).
- Produces: `to_account_currency(rows: list[dict], *, account: str | None = None) -> list[dict]`; `convert_amount(amount: float | None, ticker: str | None, on: date, *, account: str | None = None) -> tuple[float | None, bool]`; `missing_count(rows: list[dict]) -> int`; `MONEY_FIELDS = ("realized_pnl_amount",)` (all in `swingbot/admin/api_v1/money.py`); row field `fx_missing: bool` on every `/trades` row and every calendar row; `fx_missing_count: int` on `/analytics/performance`, `/analytics/equity-curve`, `/analytics/by-dimension`, `/dashboard` (top level and inside `realized` / `realized_weak`), `/calendar/pnl` (the month's rows) and `/calendar/pnl/day`. V194-10 consumes `to_account_currency`; V194-6c consumes the fields.

**The one trap.** `closed_pnl_pct` (`swingbot/core/tracking/performance.py:290-327`) divides `realized_pnl_amount` by `shares * entry` for a trade with `legs`, and `entry` is in the quote currency. So a converted amount must **never** reach a percent or R derivation: `to_account_currency` returns copies, and each route feeds the copies only to money sums and walks while its percent and R figures keep reading the stored rows. For the same reason the dashboard and calendar convert *after* `expand_realized_legs` (it recomputes each leg from `shares * move` and the last leg as `trade total - earlier legs`, which would mix currencies if the trade were converted first).

- [ ] **Step 1: Confirm the money-path map.** Run `git grep -n "realized_pnl_amount" -- swingbot/admin/api_v1 swingbot/core/analytics/pnl_calendar.py`. Every hit must be one of the paths below. Stop and report any hit not in this map:

| Route | Loader it reads | Money figures | Conversion point |
|---|---|---|---|
| `/trades`, `/trades/<id>` | `build_rows()`, `_row_from_plan`, `_row_from_trade` | row `realized_pnl_amount` (closed and leg rows; the live amount on open rows) | `to_account_currency` on rows; `convert_amount` in `_attach_unrealized_pnl` |
| `/dashboard` | `_realized_parts` (expanded legs); `_open_figures` | `realized.amount`, `realized_weak.amount`, `open_pnl_amount` | inside `_realized`; new `_open_amounts` |
| `/analytics/performance` | `_all_trades` → `closed_only` | `total_return_pct`, `annualised_return_pct`, `calmar`, `profit_factor`, `calendar`, `window_balance` | converted copies of `all_closed` |
| `/analytics/equity-curve` | same | `cum_pnl`, `cum_pct`, `window_balance` | same |
| `/analytics/by-dimension` | same | row `total_pnl`, `profit_factor` | same |
| `/calendar/pnl`, `/calendar/pnl/day` | `pnl_calendar.load_rows` → `joined_rows` (expanded legs) | `pnl_amount` and every sum of it | `convert` callable passed to `load_rows` |

  Left alone, on purpose: `account_balance` and `equity_30d` (the sizing balance), the detail's `risk_amount`/`gap_risk_amount` (2% sizing, dollar risk), `/trades/export.csv` (raw store export), `/calendar/pnl/day/sparklines` (no money), `swingbot/admin/api_v1/equity.py` (the recorded balance series). The `/risk` money drawdown is V194-10's.

- [ ] **Step 2: Write the failing unit tests.** Create `tests/admin/test_api_v1_money.py`:

```python
"""v194 B7 -- admin money in the account currency (api_v1/money.py); rates faked at the fx seam."""
from datetime import date

import pytest

from swingbot.admin.api_v1 import money
from swingbot.core.marketdata import fx
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}

#: USD -> EUR closes by day. 2026-09-01 has no rate on purpose.
_RATES = {date(2026, 8, 3): 0.9, date(2026, 8, 4): 0.8}
_QUOTES = {"AAPL": "USD", "ASML.AS": "EUR"}


@pytest.fixture
def rates(monkeypatch):
    """A EUR account; returns the rate lookups made. API tests list it AFTER
    `seed`/`logged_in` so it overrides admin_app's identity pin."""
    asked = []

    def fake_rate(from_code, to_code, on):
        asked.append((from_code, to_code, on))
        return _RATES.get(on)

    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: _QUOTES.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return asked


def _closed(trade_id="a" * 16, *, ticker="AAPL", closed_at="2026-08-03T20:00:00+00:00",
            pnl=50.0, legs=(), exit_price=105.0):
    return {
        "id": trade_id, "plan_id": None, "ticker": ticker,
        "strategy": "S/R Confluence", "horizon_key": "4w",
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0,
        "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED",
        "quality_score": 72, "source": "confluence", "legs": list(legs),
        "opened_at": "2026-08-01T14:00:00+00:00", "status": "win",
        "closed_at": closed_at, "exit_price": exit_price,
        "realized_pnl_amount": pnl, "shares": 10, "position_value": 1000.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def test_a_usd_close_converts_at_its_exit_dates_rate(rates):
    [row] = money.to_account_currency([_closed()])
    assert row["realized_pnl_amount"] == 45.0
    assert row["fx_missing"] is False
    assert rates == [("USD", "EUR", date(2026, 8, 3))]


def test_a_eur_quoted_close_is_unchanged_and_asks_no_rate(rates):
    [row] = money.to_account_currency([_closed(ticker="ASML.AS")])
    assert row["realized_pnl_amount"] == 50.0
    assert rates == []


def test_a_usd_account_converts_nothing(rates):
    [row] = money.to_account_currency([_closed()], account="USD")
    assert row["realized_pnl_amount"] == 50.0
    assert rates == []


def test_a_missing_rate_is_flagged_and_counted_never_one(rates):
    rows = money.to_account_currency([
        _closed(closed_at="2026-09-01T20:00:00+00:00"),   # no rate that day
        _closed("b" * 16, ticker="ZZZZ"),                  # unknown quote currency
        _closed("c" * 16),
    ])
    assert [r["realized_pnl_amount"] for r in rows] == [None, None, 45.0]
    assert [r["fx_missing"] for r in rows] == [True, True, False]
    assert money.missing_count(rows) == 2


def test_an_unsettled_row_stays_none_and_unflagged(rates):
    [row] = money.to_account_currency([_closed(pnl=None)])
    assert row["realized_pnl_amount"] is None
    assert row["fx_missing"] is False
    assert rates == []


def test_conversion_copies_and_rewrites_only_the_money_fields(rates):
    original = _closed()
    [row] = money.to_account_currency([original])
    assert original["realized_pnl_amount"] == 50.0 and "fx_missing" not in original
    assert set(row) - set(original) == {"fx_missing"}
    assert {k for k in original if row[k] != original[k]} == set(money.MONEY_FIELDS)


def test_each_leg_of_a_scaled_out_trade_converts_at_its_own_exit_date(rates):
    legs = [
        {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
         "closed_at": "2026-08-03T15:00:00+00:00"},
        {"fraction": 0.5, "exit_price": 104.0, "r": 0.8, "reason": "runner_trail",
         "closed_at": "2026-08-04T15:00:00+00:00"},
    ]
    trade = _closed(legs=legs, pnl=70.0, exit_price=104.0,
                    closed_at="2026-08-04T15:00:00+00:00")
    [row] = money.to_account_currency([trade])
    # 5 sh x +10 = 50 at 0.9, then 5 sh x +4 = 20 at 0.8.
    assert row["realized_pnl_amount"] == 61.0
    assert row["legs"] == legs


def test_convert_amount_prices_a_live_amount_on_the_given_day(rates):
    assert money.convert_amount(30.0, "AAPL", date(2026, 8, 4)) == (24.0, False)
    assert money.convert_amount(30.0, "AAPL", date(2026, 9, 1)) == (None, True)
    assert money.convert_amount(None, "AAPL", date(2026, 8, 4)) == (None, False)
```

- [ ] **Step 3: Run them to see them fail.** `python scripts/dev/testrun.py file tests/admin/test_api_v1_money.py`. Expected: collection error, `cannot import name 'money'`.

- [ ] **Step 4: Create `swingbot/admin/api_v1/money.py`.**

```python
"""Account-currency conversion for the money the admin API serves (v194 B7).

`realized_pnl_amount` is stored in each ticker's QUOTE currency and stays so:
the account balance (hence 2% sizing and the kill switch) reads it. This
converts read-side: each part at its OWN exit date's rate (a stored
scaled-out trade sums its legs), same currency is identity with no lookup,
and a missing rate is never 1.0 -- the amount becomes None, `fx_missing`
True. Never feed a converted row to a percent or R derivation
(`closed_pnl_pct` divides the amount by `shares * entry`), hence copies.
`fx` is read at call time so `tests/admin/conftest.py` can pin it.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from swingbot.core.marketdata import fx
from swingbot.core.tracking.performance import expand_realized_legs

#: The row fields a conversion rewrites. One: every admin money figure is a
#: sum or a walk of it (an open row carries its live amount in it too).
MONEY_FIELDS = ("realized_pnl_amount",)


def _day(stamp) -> date:
    """The date an ISO stamp names; today (UTC) when absent (a live amount)."""
    if stamp:
        try:
            return date.fromisoformat(str(stamp)[:10])
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


class _Rates:
    """One call's memo: each ticker's quote, each (currency, day) rate, once."""

    def __init__(self, account: str):
        self.account = account
        self._quotes: dict[str, str | None] = {}
        self._rates: dict[tuple[str, date], float | None] = {}

    def quote(self, ticker) -> str | None:
        key = str(ticker or "").upper().strip()
        if key not in self._quotes:
            self._quotes[key] = fx.quote_currency_code(key) if key else None
        return self._quotes[key]

    def rate(self, quote: str, on: date) -> float | None:
        if (quote, on) not in self._rates:
            self._rates[(quote, on)] = fx.fx_rate(quote, self.account, on)
        return self._rates[(quote, on)]


def _at(amount, quote: str, on: date, rates: _Rates) -> tuple[float | None, bool]:
    rate = rates.rate(quote, on)
    if rate is None:
        return None, True
    return round(float(amount) * rate, 2), False


def _priced_legs(row: dict) -> list[dict]:
    """A stored scaled-out trade's realized legs, each with an amount; else []."""
    if not row.get("legs"):
        return []
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


def to_account_currency(rows: list[dict], *, account: str | None = None) -> list[dict]:
    """Copies of `rows`, amounts in the account currency, `fx_missing` on each."""
    rates = _Rates(account or fx.account_currency_code())
    out = []
    for row in rows:
        value, missing = _converted(row, rates)
        out.append({**row, "realized_pnl_amount": value, "fx_missing": missing})
    return out


def convert_amount(amount: float | None, ticker: str | None, on: date, *,
                   account: str | None = None) -> tuple[float | None, bool]:
    """One loose amount (an open position's live P&L) at `on`'s rate."""
    row = {"realized_pnl_amount": amount, "ticker": ticker, "closed_at": on.isoformat()}
    return _converted(row, _Rates(account or fx.account_currency_code()))


def missing_count(rows: list[dict]) -> int:
    """How many rows a money figure left out for want of a rate."""
    return sum(1 for row in rows if row.get("fx_missing"))
```

  Run the Step 3 command: the eight unit tests pass.

- [ ] **Step 5: Pin identity for every other admin test.** In `tests/admin/conftest.py` `admin_app` (`:62-127`), after the `_RELOAD_MODULES` loop (`:121-122`) and before `app = ...`, add:

```python
    # v194 B7: admin money converts to the account currency through
    # swingbot.core.marketdata.fx. Pinned to "every ticker quotes in the
    # account currency" -- identity, no rate, no network -- so each route's
    # existing figures stand. tests/admin/test_api_v1_money.py fakes real rates.
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: fx.account_currency_code())
```

- [ ] **Step 6: Trades rows.** In `swingbot/admin/api_v1/trades.py`:
  - imports (`:52-54`): add `from .money import convert_amount, to_account_currency`.
  - `list_trades` (`:1029-1100`), `:1036`: `rows = build_rows()` → `rows = to_account_currency(build_rows())` (before filtering and sorting, so `sort=realized_pnl_amount` orders by the account-currency figure).
  - `get_trade` (`:929-970`): `:952` `row = _row_from_plan(plan, trade, noted)` → `row = to_account_currency([_row_from_plan(plan, trade, noted)])[0]`; `:963` `row = _row_from_trade(trade, noted)` → `row = to_account_currency([_row_from_trade(trade, noted)])[0]`.
  - `_attach_unrealized_pnl` (`:1221-1256`): `:1250-1251` (`row["realized_pnl_amount"] = dash.unrealized_pnl_amount(entry, direction, row.get("open_shares"), price)`) becomes
```python
            row["realized_pnl_amount"], row["fx_missing"] = convert_amount(
                dash.unrealized_pnl_amount(entry, direction, row.get("open_shares"), price),
                row.get("ticker"), date.today())
```
  (`date` is already imported at `:36`.) In `tests/admin/test_api_v1_trades.py` `TRADE_ROW` (`:35`), after `"realized_pnl_amount": NULLABLE_NUMBER,` (`:115`) add `"fx_missing": bool,  # v194 B7 -- no rate for the exit date; the amount is then null`. `tests/admin/test_api_v1_trade_detail.py` and `tests/admin/test_cohort_api.py` import `TRADE_ROW` and follow.

- [ ] **Step 7: Analytics.** In `swingbot/admin/api_v1/analytics.py`, import inside each of the three routes (the module's local-import style): `from .money import missing_count, to_account_currency`.
  - `analytics_performance` (`:142-276`): after `closed = select(all_closed, scope)` (`:174`) add
```python
    # v194 B7: money figures read converted copies; win rate, R and every
    # percent below keep reading the stored rows (see api_v1/money.py).
    money_closed = to_account_currency(all_closed)
    money_scoped = select(money_closed, scope)
```
    `:187` `window_balance = m.balance_at(all_closed, start, base_balance)` → `m.balance_at(money_closed, start, base_balance)`; in `derived`, `total_return_pct`, `annualised_return_pct`, `calmar` and `profit_factor` take `money_scoped` instead of `scoped`; `"calendar": m.calendar_returns(scoped, window_balance)` → `m.calendar_returns(money_scoped, window_balance)`; before `**echo(scope, len(scoped)),` add `"fx_missing_count": missing_count(money_scoped),`.
  - `analytics_equity_curve` (`:281-363`): `:332` `closed = closed_only(all_raw)` → `closed = to_account_currency(closed_only(all_raw))` (every figure here is money or R, and `m.r_multiple` never reads the amount); before `**echo(scope, len(scoped)),` add `"fx_missing_count": missing_count(scoped),`.
  - `analytics_by_dimension` (`:368-463`): `:416` → `scoped = select(to_account_currency(closed_only(_all_trades(TradeLog()))), scope)`; the final `jsonify` gains `"fx_missing_count": missing_count(scoped),`.
  - Shape tests: in `tests/admin/test_api_v1_analytics.py` (`:83-96`) and `tests/admin/test_api_analytics.py` (`:188-199`) add `"fx_missing_count": int,` to the performance spec dict.

- [ ] **Step 8: Dashboard.** In `swingbot/admin/api_v1/dashboard.py`: imports (`:32-43`) gain `from datetime import date` and `from .money import convert_amount, missing_count, to_account_currency`.
  - `_realized` (`:225-249`): `:238` `amounts = [a for a in (t.get("realized_pnl_amount") for t in closed)` → `amounts = [a for a in (t.get("realized_pnl_amount") for t in money)` with `money = to_account_currency(closed)` on the line above it; the `pcts` line keeps reading `closed`; the returned dict gains `"fx_missing_count": missing_count(money),`. The docstring gains: "Amounts are in the account currency (v194 B7); `pct` reads the stored rows."
  - New helper above `_open_figures`:
```python
def _open_amounts(open_trades: list[dict], prices: dict) -> tuple[list[float], int]:
    """Each held position's live money P&L in the account currency (v194 B7),
    over the same positions `build_open_trade_views` prices; plus how many
    were left out for want of today's rate."""
    amounts, missing = [], 0
    for t in open_trades:
        price = prices.get(t["id"])
        if not price or not t.get("entry"):
            continue
        raw = dash.unrealized_pnl_amount(t.get("entry"), t.get("direction"), t.get("shares"), price)
        value, flagged = convert_amount(raw, t.get("ticker"), date.today())
        missing += flagged
        if value is not None:
            amounts.append(value)
    return amounts, missing
```
  - `_open_figures` (`:283-308`): `:295` `amounts = views["unrealized_amounts"]` → `amounts, fx_missing = _open_amounts(open_trades, views["price"])`; the returned dict gains `"_fx_missing": fx_missing,`.
  - `dashboard` (`:311-365`): `:336` `**_open_figures(all_raw, account_cfg),` → `**open_figures,` with, before the `return`, `open_figures = _open_figures(all_raw, account_cfg)`, `open_missing = open_figures.pop("_fx_missing")` and `realized = _realized(closed_scoped)`; `:362` → `"realized": realized,`; add `"fx_missing_count": open_missing + realized["fx_missing_count"],` (main ledger only, like the card it sits on).
  - Tests: `tests/admin/test_api_v1_dashboard.py` `DASHBOARD` (`:31-62`) gains `"fx_missing_count": int,`; the realized spec at `:477-480` gains `"fx_missing_count": int,`.

- [ ] **Step 9: Calendar.** In `swingbot/core/analytics/pnl_calendar.py`:
  - `ROW_KEYS` (`:35-42`): `"outcome", "pnl_amount", "r_multiple",` → `"outcome", "pnl_amount", "fx_missing", "r_multiple",` (inserted mid-tuple: `tests/analytics/test_pnl_calendar.py:385` pins the last ten keys).
  - `_row_for` (`:169-216`): after `"pnl_amount": ...,` (`:206`) add `"fx_missing": bool(part.get("fx_missing")),`.
  - `joined_rows` (`:219-244`) gains a keyword `convert=None`: signature `def joined_rows(trades: list[dict], entries: list[dict], *, convert=None) -> list[dict]:`, and `:241` `for part in expand_realized_legs(t):` → `parts = expand_realized_legs(t)` then `for part in (convert(parts) if convert else parts):`. Docstring: "`convert` maps a trade's realized parts to display money (the admin passes `to_account_currency`); it runs after the leg split, never before it."
  - `load_rows` (`:270-292`): signature `def load_rows(*, trade_log=None, journal=None, convert=None)`, `:292` → `return joined_rows(trades, entries, convert=convert)`.
  In `swingbot/admin/api_v1/calendar.py`: import `from .money import missing_count, to_account_currency` in `calendar_pnl` and `calendar_pnl_day`; `:88` `everything = pc.load_rows()` → `pc.load_rows(convert=to_account_currency)`; the `calendar_pnl` payload gains `"fx_missing_count": missing_count([r for r in rows if r["day"].startswith(grid["month"])]),` (the month the totals describe); `:145` `pc.load_rows()` → `pc.load_rows(convert=to_account_currency)`; the day payload gains `"fx_missing_count": missing_count(day_rows),`. Sparklines (`:186`) stay as they are. `tests/admin/test_api_v1_calendar.py`: the month spec (`:72-76`) and the day spec (`:177-185`) gain `"fx_missing_count": int,`; the `trades[0]` spec (`:200-213`) gains `"fx_missing": bool,`.

- [ ] **Step 10: Route tests.** Append to `tests/admin/test_api_v1_money.py`:

```python
@pytest.fixture
def seed(admin_app):
    return lambda trades: seed_store("trades", list(trades))


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _book():
    """One USD close with a rate (+50 -> 45.00) and one without (2026-08-05)."""
    return [_closed(), _closed("b" * 16, pnl=30.0, closed_at="2026-08-05T20:00:00+00:00")]


def test_trade_rows_are_in_the_account_currency(seed, logged_in, rates):
    seed(_book())
    rows = {r["id"]: r for r in logged_in.get("/api/v1/trades?per_page=200").get_json()["items"]}
    assert rows["a" * 16]["realized_pnl_amount"] == 45.0
    assert rows["a" * 16]["pnl_pct"] == 5.0           # percent reads the stored row
    assert rows["b" * 16]["realized_pnl_amount"] is None
    assert rows["b" * 16]["fx_missing"] is True


def test_dashboard_realized_converts_and_counts_the_left_out(seed, logged_in, rates):
    seed(_book())
    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert body["realized"]["amount"] == 45.0
    assert body["realized"]["pct"] == 5.0
    assert body["realized"]["fx_missing_count"] == 1
    assert body["fx_missing_count"] == 1


def test_analytics_money_converts_and_counts(seed, logged_in, rates):
    seed(_book())
    dim = logged_in.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()
    assert dim["rows"][0]["total_pnl"] == 45.0
    assert dim["fx_missing_count"] == 1
    curve = logged_in.get("/api/v1/analytics/equity-curve").get_json()
    assert [p["cum_pnl"] for p in curve["points"]] == [45.0, 45.0]
    assert curve["fx_missing_count"] == 1
    assert logged_in.get("/api/v1/analytics/performance").get_json()["fx_missing_count"] == 1


def test_calendar_converts_and_counts_the_month_and_the_day(seed, logged_in, rates):
    seed(_book())
    month = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert month["totals"]["net_pnl_amount"] == 45.0
    assert month["fx_missing_count"] == 1
    day = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-05").get_json()
    assert day["fx_missing_count"] == 1
    assert day["total_ccy"] is None
    assert day["trades"][0]["fx_missing"] is True
```

  Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_money.py`: all twelve pass. Then run, one file at a time, `tests/admin/test_api_v1_trades.py`, `tests/admin/test_api_v1_trade_detail.py`, `tests/admin/test_api_v1_dashboard.py`, `tests/admin/test_api_v1_analytics.py`, `tests/admin/test_api_analytics.py`, `tests/admin/test_api_v1_calendar.py`, `tests/analytics/test_pnl_calendar.py`: all green (the identity pin keeps every figure; only the new keys are new).

Close: standard (test: tests/admin/test_api_v1_money.py). Deviation: the commit is `feat(v194): admin money in the account currency, missing rates flagged (V194-6b)` and its body names the files added beyond the ledger row (`calendar.py`, `tests/admin/conftest.py`, the three shape-test files).

### Task V194-6c: B7 frontend — Analytics money toggle labelled `connection.currency()`; missing-rate caveat where `fx_missing_count > 0`

**Model:** sonnet — two components and optional model fields following an existing pattern (Calendar's `metrics`); no new state.

**Files:**
- Modify: `frontend/src/app/api/models.ts`, `frontend/src/app/workspaces/analytics/scope-bar.ts`, `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`, `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/calendar/calendar.spec.ts`
- Modify, beyond the ledger row (no other task edits it): `frontend/src/app/workspaces/analytics/analytics.ts` (it is the only place that binds `sb-scope-bar`'s inputs)

**Interfaces:**
- Consumes (V194-6b): response fields `fx_missing_count: int` on `/analytics/performance`, `/analytics/equity-curve`, `/analytics/by-dimension`, `/dashboard` (top level and `realized`), `/calendar/pnl`, `/calendar/pnl/day`; row field `fx_missing: bool` on `/trades` rows. Existing: `ConnectionStore.currency` (`frontend/src/app/stores/connection.store.ts:111`), Calendar's `metrics` pattern (`frontend/src/app/workspaces/calendar/calendar.ts:489-497`).
- Produces: `fx_missing_count?: number` on `AnalyticsPerformance`, `AnalyticsEquityCurve`, `AnalyticsByDimension`, `Dashboard` (and `Dashboard.realized`), `PnlCalendar`, `CalendarDayTrades`; `TradeRow.fx_missing?: boolean`; `fxMissingText(n: number): string` and `fxMissingOf(...payloads: ({ fx_missing_count?: number } | null | undefined)[]): number` (both exported from `scope-bar.ts`); `ScopeBar.fxMissing` (`input(0)`). V194-11 and V194-16 consume `fx_missing_count`.

Layout: the caveat is a wrapping line of micro text in a `flex-wrap` row (scope bar) or a block paragraph (Calendar), so it reflows at 390, 768 and 1440 with no fixed width; the Calendar month caveat sits *outside* the collapsible `sb-panel`, so the phone digest never hides it.

- [ ] **Step 1: Model fields.** In `frontend/src/app/api/models.ts` (all optional, per Global Constraints):
  - `TradeRow` (`:69`), after `realized_pnl_amount: number | null;` (`:144`):
    ```ts
      /** v194 B7: no exchange rate for the exit date; `realized_pnl_amount` is then null. */
      fx_missing?: boolean;
    ```
  - `Dashboard` (`:402`): after `open_pnl_amount: number | null;` add `/** v194 B7: closes and positions left out of the money figures for want of a rate (main ledger). */ fx_missing_count?: number;`; inside `realized: { ... }` after `losses: number;` add `fx_missing_count?: number;`.
  - `AnalyticsEquityCurve` (`:554`), `AnalyticsByDimension` (`:578`), `AnalyticsPerformance` (`:584`), `PnlCalendar` (`:2043`), `CalendarDayTrades` (`:2057`): each gains, as its last member,
    ```ts
      /** v194 B7: rows left out of the money figures (no exchange rate for the exit date). */
      fx_missing_count?: number;
    ```
    (`PnlCalendar`'s counts the requested month's rows.)

- [ ] **Step 2: Write the failing scope-bar tests.** In `frontend/src/app/workspaces/analytics/scope-bar.spec.ts`:
  - imports: `provideZonelessChangeDetection` → `provideZonelessChangeDetection, signal` (from `@angular/core`); add `import { ConnectionStore } from '../../stores/connection.store';`; `import { ScopeBar } from './scope-bar';` → `import { ScopeBar, fxMissingOf, fxMissingText } from './scope-bar';`.
  - above `const create`, add `const connection = { currency: signal('€') };`.
  - `beforeEach`: `TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });` → `connection.currency.set('€');` then `TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection(), { provide: ConnectionStore, useValue: connection }] });`.
  - insert before the file's last line (the `});` closing `describe('ScopeBar')`):

```ts
  it('labels the money toggle with the account currency, keeping the value key (v194 B7)', () => {
    for (const symbol of ['€', '$', '£']) {
      connection.currency.set(symbol);
      const { el } = create({ unit: 'money' });
      const labels = [...el.querySelectorAll('sb-segmented button')].map((b) => b.textContent!.trim());
      expect(labels).toEqual(['R', '%', symbol]);
      // A saved `unit: 'money'` preference still selects the money segment.
      expect(el.querySelector('sb-segmented button[aria-pressed="true"]')!.textContent!.trim()).toBe(symbol);
    }
  });

  it('names how many closes the money figures left out, and only when some were', () => {
    expect(create().el.querySelector('.fx-caveat')).toBeNull();
    const { el } = create({ fxMissing: 2 });
    const caveat = el.querySelector('.fx-caveat')!;
    expect(caveat.getAttribute('role')).toBe('note');
    expect(caveat.textContent!.trim()).toBe(fxMissingText(2));
    // Tuning shows no population and no money: no caveat either.
    expect(create({ fxMissing: 2, tuning: true }).el.querySelector('.fx-caveat')).toBeNull();
  });
});

describe('fxMissingText', () => {
  it('is empty for none and counts trades, singular and plural', () => {
    expect(fxMissingText(0)).toBe('');
    expect(fxMissingText(1)).toBe('1 closed trade left out of money figures: no exchange rate for its exit date');
    expect(fxMissingText(3)).toBe('3 closed trades left out of money figures: no exchange rate for their exit dates');
  });
});

describe('fxMissingOf', () => {
  it('reads the largest count among the payloads present, 0 for none', () => {
    expect(fxMissingOf()).toBe(0);
    expect(fxMissingOf(null, undefined, {})).toBe(0);
    expect(fxMissingOf(null, { fx_missing_count: 2 }, { fx_missing_count: 1 })).toBe(2);
  });
```

  (The block closes `describe('ScopeBar')` itself; the file's existing last `});` then closes `describe('fxMissingOf')`.)

- [ ] **Step 3: Run it to see it fail.** `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/analytics/scope-bar.spec.ts`. Expected: FAIL — `fxMissingText` is not exported, and the money label reads `$`.

- [ ] **Step 4: Implement in `scope-bar.ts`.**
  - `:1` → `import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';`; after the `models` import add `import { ConnectionStore } from '../../stores/connection.store';`.
  - template `:52`: `[options]="unitOptions"` → `[options]="unitOptions()"`.
  - template, inside `@if (!tuning()) { ... }` of the scope line (`:54-60`), after the `allTimePanels` block:
    ```html
          @if (fxMissing() > 0) {
            <span class="fx-caveat" role="note">{{ fxText() }}</span>
          }
    ```
  - styles (`:63-67`) gain `.fx-caveat { font-size: var(--text-micro); color: var(--warn); min-width: 0; overflow-wrap: anywhere; }`.
  - class: after `readonly tuning = input(false);` add
    ```ts
      /** v194 B7: closed trades the money figures left out for want of an
       *  exchange rate (the payloads' `fx_missing_count`). */
      readonly fxMissing = input(0);
      private readonly connection = inject(ConnectionStore);
    ```
  - `:91` `protected readonly unitOptions = [{ value: 'r', label: 'R' }, { value: 'pct', label: '%' }, { value: 'money', label: '$' }];` →
    ```ts
      /** The money side carries the account's own symbol (v194 B7): the server
       *  converts every money figure to the account currency. The value key
       *  stays `'money'`, so saved preferences survive. Mirrors Calendar's
       *  `metrics`. */
      protected readonly unitOptions = computed(() => [
        { value: 'r', label: 'R' }, { value: 'pct', label: '%' },
        { value: 'money', label: this.connection.currency() },
      ]);
      protected readonly fxText = computed(() => fxMissingText(this.fxMissing()));
    ```
  - after the class, append:
    ```ts
    /** v194 B7: the caveat when money figures left closed trades out for want
     *  of an exchange rate on their exit date; '' for none. Calendar uses it too. */
    export function fxMissingText(n: number): string {
      if (!(n > 0)) return '';
      return n === 1
        ? '1 closed trade left out of money figures: no exchange rate for its exit date'
        : `${n} closed trades left out of money figures: no exchange rate for their exit dates`;
    }

    /** The largest left-out count among the scoped payloads a tab fetched. They
     *  answer one scope, so they count the same population; 0 when none says. */
    export function fxMissingOf(...payloads: ({ fx_missing_count?: number } | null | undefined)[]): number {
      return Math.max(0, ...payloads.map((p) => p?.fx_missing_count ?? 0));
    }
    ```
  In `frontend/src/app/workspaces/analytics/analytics.ts`: `:7` `import { ScopeBar } from './scope-bar';` → `import { ScopeBar, fxMissingOf } from './scope-bar';`; the `<sb-scope-bar` element (`:45-49`) gains `[fxMissing]="fxMissing()"` after `[asOf]="store.asOf()"`; after `protected readonly store = inject(AnalyticsStore);` (`:64`) add
    ```ts
      /** v194 B7: how many scoped closes the tab's money figures left out. */
      protected readonly fxMissing = computed(() =>
        fxMissingOf(this.store.performance(), this.store.equityCurve(), this.store.byDimension()));
    ```
  Run the Step 3 command: PASS.

- [ ] **Step 5: Write the failing Calendar tests.** Append to `frontend/src/app/workspaces/calendar/calendar.spec.ts`:

```ts
/* -- v194 B7 -- money left out for want of an exchange rate ----------------- */

describe('Calendar missing-rate caveat', () => {
  it('names the month\'s left-out closes beside the totals, and only then', async () => {
    const plain = seed();
    await plain.whenStable();
    plain.detectChanges();
    expect(el(plain).querySelector('.fx-caveat')).toBeNull();

    const fixture = seed({ ...RESPONSE, fx_missing_count: 2 });
    await fixture.whenStable();
    fixture.detectChanges();
    const caveat = el(fixture).querySelector('.fx-caveat')!;
    expect(caveat.getAttribute('role')).toBe('note');
    expect(caveat.textContent!.trim()).toBe(fxMissingText(2));
    // Outside the collapsible panel, so the phone digest cannot hide it.
    expect(caveat.closest('sb-panel')).toBeNull();
  });

  it('names the day\'s left-out closes in the drawer', async () => {
    const fixture = seed();
    await fixture.whenStable();
    fixture.detectChanges();
    fixture.componentInstance.store.selectDay('2026-08-03');
    TestBed.inject(HttpTestingController)
      .expectOne((r) => r.url === '/api/v1/calendar/pnl/day')
      .flush({ as_of: '2026-08-10T12:00:00Z', date: '2026-08-03', trades: [TRADE], trade_count: 1,
        winners: 0, losers: 0, total_r: null, total_ccy: null,
        win_rate: null, avg_trade_r: null, worst_drawdown_r: null,
        contributors: [], detractors: [],
        context: { percentile: null, history_days: 0,
          vs_avg_day: { pnl_amount: null, r: null },
          vs_weekday_avg: { pnl_amount: null, r: null } },
        breakdown: { strategy: [], horizon: [], direction: [], exit_reason: [] },
        fx_missing_count: 1 });
    await fixture.whenStable();
    fixture.detectChanges();
    const caveats = [...el(fixture).querySelectorAll('.fx-caveat')].map((c) => c.textContent!.trim());
    expect(caveats).toEqual([fxMissingText(1)]);
  });
});
```

  and add `import { fxMissingText } from '../analytics/scope-bar';` to the spec's imports. Run `npm --prefix "$WT/frontend" test -- --watch=false --include src/app/workspaces/calendar/calendar.spec.ts`. Expected: FAIL — no `.fx-caveat`.

- [ ] **Step 6: Implement in `calendar.ts`.**
  - imports: add `import { fxMissingText } from '../analytics/scope-bar';`.
  - template: after `</sb-panel>` closing the totals panel (`:124`):
    ```html
      @if (monthFxMissing() > 0) {
        <p class="fx-caveat" role="note">{{ fxText(monthFxMissing()) }}</p>
      }
    ```
  - template, drawer: after `<p class="day-caption">{{ paperCaption }}</p>` (`:246`):
    ```html
        @if ((detail.fx_missing_count ?? 0) > 0) {
          <p class="fx-caveat" role="note">{{ fxText(detail.fx_missing_count!) }}</p>
        }
    ```
  - styles, after the `.day-caption, .day-sample-note` rule (`:454`): `.fx-caveat { margin: 0 0 var(--space-8); color: var(--warn); font-size: var(--text-micro); overflow-wrap: anywhere; }`.
  - class, after `protected readonly currency = computed(() => this.connection.currency());` (`:489`):
    ```ts
      /** v194 B7: the month's closes the money figures left out (no exchange
       *  rate for the exit date), and the caveat copy shared with Analytics. */
      protected readonly monthFxMissing = computed(() => this.store.data()?.fx_missing_count ?? 0);
      protected readonly fxText = fxMissingText;
    ```
  Run the Step 5 command: PASS.

- [ ] **Step 7: Check the three widths.** With the replica-backed local instance from V194-4 (or `/replicate-prod-db` if none is up), a Playwright script that logs in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` (loaded in the script, never printed) opens `/analytics` and `/calendar` at 390, 768 and 1440 and screenshots the scope line and the totals: the money segment reads the account symbol, and no control overflows. A caveat appears only if the replica has closes without a rate; record which in the commit body.

Close: standard (test: frontend/src/app/workspaces/analytics/scope-bar.spec.ts); also run the narrow `calendar.spec.ts` before the whole-frontend run. One frontend commit `feat(v194): money toggle in the account currency; caveat for closes without an exchange rate (V194-6c)` naming the six files above, its body noting `analytics.ts` is beyond the ledger row.

