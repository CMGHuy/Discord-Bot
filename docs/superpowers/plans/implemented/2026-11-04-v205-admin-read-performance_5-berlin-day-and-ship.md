# Admin read performance, Layer 1 -- Part 5: Berlin FX days, the full suite, the ship

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md), § "L1-a" (One rule for "the day", What the table holds, Callers, Figures this moves), "Testing", "Rollout and rollback", "Results".
**Index:** [`_0-index.md`](2026-11-04-v205-admin-read-performance_0-index.md) -- Goal, `## Global Constraints`, `## Parallelisation`, the task ledger and every cross-task contract live there. Every task below implicitly includes the Global Constraints.

This part holds V205-16 (`fx_convert` keys every rate on the Berlin day, decides identity on major codes, and the live callers pass Berlin today), V205-17 (the plan's one full-suite run) and V205-18 (deploy, migrate, backfill, measure, record). V205-16 is the second and last task whose output moves on purpose; like V205-15 it edits `money_reference.EXPECTED_MONEY` by hand and never a golden.

`<wt>` below is the plan's worktree root (absolute path). Every command uses it; never `cd`.

**Suite choice for V205-16's tests.** The ledger names `tests/marketdata/test_fx_day.py`, but suite `market-data` (`tests/marketdata/`, `tests/market/`) counted 1146 of 1200 on 2026-11-04 and V205-10..V205-15 add about 49, leaving about 5. V205-16's file has 17 test functions (37 cases), so it lives in **`tests/admin_perf/test_fx_day.py`** (suite `admin-perf`, created by V205-2, far under its cap). The file tests the admin's FX day rule end to end (core helper and the three admin callers), which is what that suite covers. No test is added to `tests/marketdata/` or `tests/admin/`.

# Phase 6 -- Berlin FX days, then the full suite and the ship

### Task V205-16: `fx_convert` on Berlin days; major-code identity; Berlin-today callers; admin FX tests updated

**Model:** opus — the last deliberate output change: a timezone rule on every converted amount, plus hand-derived money references.

**Files:**
- Modify: `swingbot/core/marketdata/fx_convert.py` (imports, `FX_DAY_TZ`, `berlin_today`, `fx_day`, `_berlin_date`, `_scale_only`; `_day` deleted; `_Rates.rate`, `_converted`, module docstring)
- Modify: `swingbot/admin/api_v1/dashboard.py` (`_open_amounts`, line ~320; drop the unused `date` import), `swingbot/admin/api_v1/trades.py` (`_attach_unrealized_pnl`, line ~1341)
- Modify: `swingbot/admin/api_v1/risk.py` (`_distribution_metrics` ~456, the one `signed_weights` caller), `swingbot/admin/api_v1/risk_read_model.py` (`signed_weights` docstring only). If `git -C <wt> ls-files "*risk_read_model.py"` shows v204 moved it into `swingbot/core/`, edit it there.
- Modify: `tests/admin_perf/money_reference.py`, `tests/admin_perf/golden_book.py` (`CLOCK_MODULES` gains `swingbot.core.marketdata.fx_convert`)
- Modify only where an assertion moves (expected: none, see Step 7): `tests/admin/test_api_v1_money.py`, `tests/admin/test_api_v1_risk.py`, `tests/admin/test_risk_read_model.py`, `tests/admin/test_trades_golden_rows.py`, `tests/analytics/test_cancel_replay.py`
- Create: `tests/admin_perf/test_fx_day.py` (**not** `tests/marketdata/`: see "Suite choice" above)

**Interfaces:**
- Consumes: V205-15's `fx.fx_rate` (equal majors return the scale), `fx._major` (existing), V205-10's `_Rates.__init__` (kept), V205-4/4b/15's `golden_book.trades()`, `CLOCK_MODULES` and `money_reference` constants.
- Produces (index "fx_convert after V205-16"): `FX_DAY_TZ`, `berlin_today() -> date`, `fx_day(stamp) -> date`; `_day` is gone.

**The rule** is the Global Constraints' "FX day rule"; an unparseable or out-of-range stamp also gives Berlin today (as `_day` gave UTC today). Identity on **major** codes: scale 1.0 returns the amount untouched (today's shortcut, byte-identical); a minor scale (GBp into GBP) multiplies each leg with no lookup, per-leg rounding kept.

**What moves, by hand** (CET, UTC+1, from 2026-10-25): only T3. Its exit, 2026-11-02 23:30 UTC, is 00:30 Berlin on 11-03, so it takes row 11-03: -30.00 x 0.8680 = **-26.04** (was -25.92). T2 (21:30 Berlin), T4's legs (16:00) and T5 (Berlin today 11-04) keep their day. The Calendar still buckets `closed_at[:10]`, so T3 stays in the 11-02 bucket.

- [ ] **Step 1: Write the failing tests**

Create `<wt>/tests/admin_perf/test_fx_day.py`:

```python
"""v205 V205-16: amounts convert on their Berlin day. Hand-computed values only.
EU DST 2026 switches: 03-29 and 10-25, 01:00 UTC."""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import pytest

from swingbot.core.marketdata import fx, fx_convert
from tests.admin_perf import golden_book as gb

_QUOTES = {"AAPL": "USD", "SAP.DE": "EUR", "VOD.L": "GBp", "NPN.JO": "ZAc"}
_RATES = {date(2026, 10, 29): 0.9, date(2026, 11, 2): 0.8, date(2026, 11, 3): 0.868,
          date(2026, 8, 4): 0.5}


@pytest.fixture
def asked(monkeypatch):
    """Pins fx as the admin's money tests do; records every rate fx_convert asks for."""
    calls = []

    def fake_rate(from_code, to_code, on, **_):
        calls.append((from_code, to_code, on))
        return _RATES.get(on)

    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker, **_: _QUOTES.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return calls


def _row(ticker, amount, closed_at):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": closed_at}


# --- fx_day ------------------------------------------------------------------

@pytest.mark.parametrize("stamp,day", [
    ("2026-08-03T21:59:00+00:00", date(2026, 8, 3)),    # CEST 23:59
    ("2026-08-03T22:00:00+00:00", date(2026, 8, 4)),    # CEST 00:00
    ("2026-08-03T23:59:00+00:00", date(2026, 8, 4)),    # CEST 01:59
    ("2026-08-03T00:30:00+00:00", date(2026, 8, 3)),    # CEST 02:30
    ("2026-11-02T21:59:00+00:00", date(2026, 11, 2)),   # CET 22:59
    ("2026-11-02T22:00:00+00:00", date(2026, 11, 2)),   # CET 23:00
    ("2026-11-02T23:59:00+00:00", date(2026, 11, 3)),   # CET 00:59
    ("2026-11-02T00:30:00+00:00", date(2026, 11, 2)),   # CET 01:30
])
def test_utc_closes_map_to_their_berlin_day(stamp, day):
    assert fx_convert.fx_day(stamp) == day


@pytest.mark.parametrize("stamp,day", [
    ("2026-03-28T22:59:00+00:00", date(2026, 3, 28)),   # CET 23:59, the night before the switch
    ("2026-03-28T23:00:00+00:00", date(2026, 3, 29)),   # CET 00:00
    ("2026-03-29T22:00:00+00:00", date(2026, 3, 30)),   # CEST 00:00, after the switch
    ("2026-10-24T22:00:00+00:00", date(2026, 10, 25)),  # CEST 00:00
    ("2026-10-25T22:59:00+00:00", date(2026, 10, 25)),  # CET 23:59, after the switch back
    ("2026-10-25T23:00:00+00:00", date(2026, 10, 26)),  # CET 00:00
])
def test_dst_switch_days(stamp, day):
    assert fx_convert.fx_day(stamp) == day


def test_a_naive_stamp_is_utc_and_offsets_and_z_are_honoured():
    assert fx_convert.fx_day("2026-08-03T22:30:00") == date(2026, 8, 4)
    assert fx_convert.fx_day("2026-08-03T22:30:00Z") == date(2026, 8, 4)
    assert fx_convert.fx_day("2026-08-03T21:30:00-02:00") == date(2026, 8, 4)   # 23:30 UTC
    assert fx_convert.fx_day(datetime(2026, 8, 3, 22, 30)) == date(2026, 8, 4)
    assert fx_convert.fx_day(datetime(2026, 8, 3, 21, 30, tzinfo=timezone.utc)) == date(2026, 8, 3)


def test_a_date_or_date_only_string_is_that_date_unshifted():
    assert fx_convert.fx_day("2026-08-03") == date(2026, 8, 3)
    assert fx_convert.fx_day(date(2026, 8, 3)) == date(2026, 8, 3)


@pytest.mark.parametrize("stamp", [None, "", "  ", "not a stamp", 42,
                                   "9999-12-31T23:30:00-02:00"])
def test_absent_or_unreadable_is_berlin_today(stamp, monkeypatch):
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2030, 1, 2))
    assert fx_convert.fx_day(stamp) == date(2030, 1, 2)


def test_berlin_today_is_the_berlin_date_not_the_utc_date(monkeypatch):
    class _At(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 2, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(fx_convert, "datetime", _At)
    assert fx_convert.berlin_today() == date(2026, 11, 3)


def test_the_utc_day_helper_and_its_slice_are_gone():
    assert not hasattr(fx_convert, "_day")
    assert "[:10]" not in inspect.getsource(fx_convert)


# --- conversion --------------------------------------------------------------

def test_a_close_after_berlin_midnight_converts_at_the_next_days_rate(asked):
    [row] = fx_convert.to_account_currency([_row("AAPL", -30.0, "2026-11-02T23:30:00+00:00")])
    assert row["realized_pnl_amount"] == -26.04          # -30.00 x 0.868
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_scale_out_legs_convert_on_their_own_berlin_days(asked):
    trade = next(t for t in gb.trades() if t["id"] == "golden-t4-usd-scaleout")
    [row] = fx_convert.to_account_currency([trade])
    assert row["realized_pnl_amount"] == 61.0            # round(50 x 0.9, 2) + round(20 x 0.8, 2)
    assert asked == [("USD", "EUR", date(2026, 10, 29)), ("USD", "EUR", date(2026, 11, 2))]


def test_the_exact_same_code_stays_untouched_and_asks_nothing(asked):
    [row] = fx_convert.to_account_currency([_row("SAP.DE", 12.345, "2026-11-02T23:30:00+00:00")])
    assert row["realized_pnl_amount"] == 12.345 and row["fx_missing"] is False
    assert asked == []


def test_pence_into_pounds_is_the_scale_with_no_lookup(asked):
    [row] = fx_convert.to_account_currency([_row("VOD.L", 1234.0, "2026-08-03T22:30:00+00:00")],
                                           account="GBP")
    assert row["realized_pnl_amount"] == 12.34           # 1234 x 0.01
    assert asked == []


def test_pence_into_euros_asks_for_the_minor_pair_on_the_berlin_day(asked):
    [row] = fx_convert.to_account_currency([_row("VOD.L", 1234.0, "2026-08-03T22:30:00+00:00")])
    assert row["realized_pnl_amount"] == 617.0           # 1234 x 0.5 (fx_rate owns the 0.01)
    assert asked == [("GBp", "EUR", date(2026, 8, 4))]


@pytest.mark.parametrize("account,value,calls", [
    ("ZAR", 50.0, []),                                    # 5000 x 0.01, no lookup
    ("EUR", 2500.0, [("ZAc", "EUR", date(2026, 8, 4))]),  # 5000 x 0.5
    ("USD", 2500.0, [("ZAc", "USD", date(2026, 8, 4))]),
    ("GBP", 2500.0, [("ZAc", "GBP", date(2026, 8, 4))]),
])
def test_rand_cents_into_each_account_currency(asked, account, value, calls):
    [row] = fx_convert.to_account_currency([_row("NPN.JO", 5000.0, "2026-08-04T12:00:00+00:00")],
                                           account=account)
    assert row["realized_pnl_amount"] == value
    assert asked == calls


def test_convert_amount_keeps_the_given_date(asked):
    assert fx_convert.convert_amount(30.0, "AAPL", date(2026, 8, 4)) == (15.0, False)
    assert asked == [("USD", "EUR", date(2026, 8, 4))]


# --- the callers -------------------------------------------------------------

def test_dashboard_open_amounts_use_berlin_today(asked, monkeypatch):
    from swingbot.admin.api_v1 import dashboard
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2026, 11, 3))
    trade = {"id": "t5", "ticker": "AAPL", "entry": 100.0, "direction": "bullish", "shares": 10}
    assert dashboard._open_amounts([trade], {"t5": 104.0}) == ([34.72], 0)   # 40 x 0.868
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_trades_unrealized_amounts_use_berlin_today(asked, monkeypatch):
    from swingbot.admin.api_v1 import trades
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2026, 11, 3))
    row = {"status": "open", "ticker": "AAPL", "entry": 100.0, "direction": "bullish",
           "open_shares": 10, "current_price": 104.0, "risk_stop": 95.0}
    trades._attach_unrealized_pnl([row])
    assert (row["realized_pnl_amount"], row["fx_missing"]) == (34.72, False)
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_risk_weights_take_the_berlin_day_of_the_check(monkeypatch):
    from swingbot.admin.api_v1 import risk, risk_read_model
    seen = []

    def weights(open_trades, *, on, account=None):
        seen.append(on)
        return {}, "missing_fx"

    def no_bars(symbols):
        raise RuntimeError("no bars in this test")

    monkeypatch.setattr(risk_read_model, "signed_weights", weights)
    monkeypatch.setattr(risk, "_risk_bars", no_bars)
    risk._distribution_metrics([{"ticker": "AAPL"}], "QQQ", "2026-11-02T23:30:00+00:00")
    assert seen == [date(2026, 11, 3)]
```

`_pin_admin_refresher_off` (autouse via the conftest) keeps `fetch=True`: one-argument quote, three-argument rate.

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_fx_day.py`
Expected: FAIL, `AttributeError: ... has no attribute 'fx_day'`.

- [ ] **Step 3: Implement the rule in `fx_convert.py`**

In `<wt>/swingbot/core/marketdata/fx_convert.py`, add `from zoneinfo import ZoneInfo` below the `datetime` import. Replace `_day` (the whole function) with:

```python
#: The FX day's calendar (spec L1-a): one rate per pair per Berlin day.
FX_DAY_TZ = ZoneInfo("Europe/Berlin")


def berlin_today() -> date:
    """Today in Berlin: the FX day of a live amount (open P&L, heat weights)."""
    return datetime.now(FX_DAY_TZ).date()


def fx_day(stamp) -> date:
    """The Berlin date an amount converts on (v205): an aware stamp in Berlin,
    a naive one read as UTC first, a date or date-only string unshifted, and
    Berlin today when the stamp is absent or unreadable (a live amount)."""
    if isinstance(stamp, datetime):
        return _berlin_date(stamp)
    if isinstance(stamp, date):
        return stamp
    text = str(stamp or "").strip()
    if not text:
        return berlin_today()
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        return _berlin_date(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except (ValueError, OverflowError):
        return berlin_today()


def _berlin_date(stamp: datetime) -> date:
    aware = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)
    return aware.astimezone(FX_DAY_TZ).date()


def _scale_only(quote: str, account: str) -> float | None:
    """The minor-unit scale when both codes share a major currency
    (GBp -> GBP: 0.01, EUR -> EUR: 1.0); None when a rate is needed."""
    src, src_scale = fx._major(quote)
    dst, dst_scale = fx._major(account)
    return src_scale / dst_scale if src == dst else None
```

The `datetime` test precedes the `date` test (a `datetime` is a `date`). In `_Rates` (keep V205-10's `__init__` as it is), replace `rate` with:

```python
    def rate(self, quote: str, on: date) -> float | None:
        """The multiplier for `quote` on `on`; equal majors are the scale, never a lookup."""
        if (quote, on) not in self._rates:
            scale = _scale_only(quote, self.account)
            self._rates[(quote, on)] = (scale if scale is not None
                                        else rate(quote, self.account, on, fetch=self.fetch))
        return self._rates[(quote, on)]
```

In `_converted`, replace the two lines `if quote == rates.account:` / `return amount, False` with:

```python
    if _scale_only(quote, rates.account) == 1.0:
        return amount, False
```

and replace both `_day(...)` calls with `fx_day(...)` (`fx_day(row.get("closed_at"))`, `fx_day(leg.get("closed_at"))`). `convert_amount` keeps building `"closed_at": on.isoformat()`: a date-only string passes unshifted. In the module docstring, "exit date's rate" becomes "exit's Berlin-day rate (v205)" and "same currency" becomes "same major currency".

- [ ] **Step 4: The callers pass Berlin today**

In `<wt>/swingbot/admin/api_v1/dashboard.py`: add `from swingbot.core.marketdata import fx_convert` to the imports (after the `swingbot.core.tracking.performance` line). In `_open_amounts`, change `convert_amount(raw, t.get("ticker"), date.today())` to `convert_amount(raw, t.get("ticker"), fx_convert.berlin_today())`. Delete `from datetime import date` (its other mentions, lines 181/344/422, are prose).

In `<wt>/swingbot/admin/api_v1/trades.py`: add `from swingbot.core.marketdata import fx_convert` to the imports. In `_attach_unrealized_pnl`, change `row.get("ticker"), date.today())` to `row.get("ticker"), fx_convert.berlin_today())`. The `date` import stays (line 137 uses it).

In `<wt>/swingbot/admin/api_v1/risk.py`: add `from swingbot.core.marketdata import fx_convert` to the imports. In `_distribution_metrics`, change `on=datetime.fromisoformat(checked).date()` to `on=fx_convert.fx_day(checked)`.

In `<wt>/swingbot/admin/api_v1/risk_read_model.py`, give `signed_weights` this docstring (no code change):

```python
    """Signed position weights by ticker, valued in the account currency at
    `on`'s rate. `on` is the FX day: the caller passes the Berlin date of its
    check stamp (`fx_convert.fx_day`, v205), never a UTC date."""
```

- [ ] **Step 5: Run the new tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_fx_day.py`
Expected: `0 failed`, `0 xfailed` (17 test functions, 37 cases with parameters).

- [ ] **Step 6: The goldens' clock and money references**

In `<wt>/tests/admin_perf/golden_book.py`, insert `"swingbot.core.marketdata.fx_convert",` into `CLOCK_MODULES` between `"swingbot.core.analytics.rank",` and `"swingbot.core.planning.account",` (sorted). Change the comment line `#: clock from a module missing here. V205-16 appends swingbot.core.marketdata.fx_convert.` to `#: clock from a module missing here. fx_convert reads Berlin today since V205-16.`

In `<wt>/tests/admin_perf/money_reference.py`, replace the docstring's rule paragraph that V205-15 wrote ("V205-15's rule: ... (2026-11-04).") with:

```text
V205-16's rule: the fx_daily_rates row (FX_DAILY_ROWS) for the amount's
FX day, the Berlin date of its stamp (fx_convert.fx_day); an open position
converts at Berlin today, 2026-11-04. The Calendar buckets the UTC date.
```

Change exactly these three constants (every other line stays as V205-15 left it):

```python
T3_AAPL_LOSS = -26.04     # -30.00 x 0.8680 (exit 2026-11-02 23:30 UTC = 2026-11-03 00:30 Berlin: row 2026-11-03, close 2026-11-02)
DAY_2026_11_02 = -8.76    # T3 + T4 leg 2 = -26.04 + 17.28 (Calendar bucket = UTC date 2026-11-02)
MONTH_2026_11 = 154.64    # -8.76 + 163.40
```

Any other literal `EXPECTED_MONEY` value built on T3's old rate (0.8640) is recomputed by hand with 0.8680; expressions over the constants need no edit. Never compute through `fx`, `fx_convert` or `fx_daily`.

This hits the database: run `/replicate-prod-db` first if this worktree has not yet.

Run: `python <wt>/scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py`
Expected: `0 failed`, `0 xfailed`; the frozen goldens pass **unchanged**, the money references with the new values. A failing golden means `fx_convert.py` is wrong, never the golden.

Run: `python <wt>/scripts/dev/testrun.py suite admin-perf` -- expected `0 failed` (budgets unchanged: `fx_day` issues no SQL).

- [ ] **Step 7: The existing FX seams**

Run each: `python <wt>/scripts/dev/testrun.py file tests/admin/test_api_v1_money.py`, `... file tests/admin/test_api_v1_risk.py`, `... file tests/admin/test_risk_read_model.py`, `... file tests/admin/test_trades_golden_rows.py`, `... file tests/analytics/test_cancel_replay.py`, `... file tests/marketdata/test_fx_persisted.py`, `... file tests/marketdata/test_fx_quote_batch.py`.
Expected: `0 failed` with **no edit** (checked 2026-11-04: each stamp they convert keeps its date in Berlin; date-only strings are unshifted). The only legitimate edit is an expected day that moved to the stamp's Berlin date, with a comment (`# 23:30 UTC = 00:30 CET next day`); any other failure is a defect here.

- [ ] **Step 8: Complexity and import hygiene**

Run: `python -m radon cc -s <wt>/swingbot/core/marketdata/fx_convert.py` (`fx_day` at most `A5`, `_converted` no worse than `B7`), `python <wt>/scripts/dev/complexity_gate.py` (clean), and `git -C <wt> grep -n "import" -- swingbot/core/marketdata/fx_convert.py` (no `swingbot.admin`, no `flask`).

- [ ] **Step 9: Commit (three scoped commits)**

```bash
git -C <wt> add swingbot/core/marketdata/fx_convert.py tests/admin_perf/test_fx_day.py
git -C <wt> commit -m "feat(marketdata): convert on the Berlin FX day, identity on major codes (v205 V205-16)"
git -C <wt> add swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/trades.py swingbot/admin/api_v1/risk.py swingbot/admin/api_v1/risk_read_model.py
git -C <wt> commit -m "fix(admin): live amounts and heat weights use Berlin today (v205 V205-16)"
git -C <wt> add tests/admin_perf/golden_book.py tests/admin_perf/money_reference.py
git -C <wt> commit -m "test(admin): fx_convert on the frozen clock; T3 moves to its Berlin day by hand (v205 V205-16)"
```

If Step 7 needed an edit, stage that test file with the third commit.

### Task V205-17: Full suite

**Model:** sonnet — runs the gates and routes any failure back to the task that owns the file; no new design.

**Files:**
- Modify: none planned. A defect found here is fixed **in the owning task's files only** (table in Step 3) and committed as that task's fix. No golden, no `max_tests` cap and no `complexity_baseline.json` entry is ever edited to make a gate pass.

**Interfaces:**
- Consumes: every commit of V205-1..V205-16 on the worktree branch.
- Produces: the gate evidence V205-18 and `/close-out` rely on: `python <wt>/scripts/dev/testrun.py full` at `0 failed`, `0 xfailed`; `complexity_gate.py` clean; `plan_lint.py` clean on every v205 plan file.

- [ ] **Step 1: Preconditions**

```bash
git -C <wt> status --short
git -C <wt> log --oneline main..HEAD | grep -c "V205-"
git -C <main-tree> status --short -- swingbot tests scripts
```

`<main-tree>` is the first path `git -C <wt> worktree list` prints. Expected: the worktree is clean; the log shows commits for every task V205-1..V205-16 (V205-4b and V205-12b included; count the ids, not the commits); the main tree shows no `swingbot/`, `tests/` or `scripts/` change (a subagent that wrote there by mistake is reported to the controller, never reverted by this task). Then run `/replicate-prod-db` (the shared `swing-db` container, port 56789), so the database-backed tests see the current replica.

- [ ] **Step 2: The one full-suite run**

Dispatch the `test-runner` agent with: "Run `python <wt>/scripts/dev/testrun.py full` in `<wt>`; report the pass/fail/xfail counts, each failing test id with its first assertion line, and the complexity gate's verdict." If running it directly instead, keep the output out of context:

```bash
python <wt>/scripts/dev/testrun.py full > <scratchpad>/v205_full.log 2>&1; echo "exit=$?"
tail -n 15 <scratchpad>/v205_full.log
```

Expected: `0 failed`, `0 xfailed` and the complexity gate clean (`testrun.py full` runs it). A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 3: Route each failure to its owner**

| Failing test path | Owning task(s) |
|---|---|
| `tests/scripts/test_admin_endpoint_timing.py` | V205-1 |
| `tests/db/test_engine_hooks.py`, `tests/admin_perf/test_sql_tally.py` | V205-2 |
| `tests/admin_perf/test_server_timing.py`, `tests/test_config_v205_keys.py` | V205-3 |
| `tests/admin_perf/test_golden_endpoints.py` | V205-4/4b; a money value: V205-15/16 |
| `tests/admin_perf/test_budgets.py` | V205-5, V205-9 |
| `tests/infra/test_read_memo.py`, `tests/infra/test_read_memo_stores.py` | V205-6, V205-7 |
| `tests/admin_perf/test_memo_isolation.py` | V205-8 |
| `tests/admin_perf/test_read_scope_routes.py` | V205-9 |
| `tests/marketdata/test_fx_quote_batch.py` | V205-10 |
| `tests/db/test_v205_fx_daily_rates.py`, `tests/db/test_migrations.py`, `tests/db/test_v200_discord_issued_at.py`, `tests/db/test_unknown_field_round_trip.py` | V205-11 |
| `tests/marketdata/test_fx_daily.py` / `test_fx_daily_lookup.py` | V205-12 / V205-12b |
| `tests/marketdata/test_fx_snap.py`, `tests/refresher/test_fx_snap_step.py` | V205-13, V205-14 |
| `tests/scripts/test_backfill_fx_daily_rates.py` | V205-14 |
| `tests/marketdata/test_fx.py`, `tests/marketdata/test_fx_persisted.py` | V205-15 |
| `tests/admin_perf/test_fx_day.py`, an FX assertion under `tests/admin/` or `tests/analytics/` | V205-16 |
| `tests/infra/test_swallowed_ratchet.py` | the task that added the offending `swallowed(...)` tag (`git -C <wt> log -S "<tag>" --oneline`) |
| `tests/hooks/test_codex_mirror.py` | V205-6 or V205-12 (an `architecture.md` row without its `AGENTS.md` mirror) |
| `tests/dev/test_suites.py` | the task whose tests pushed a suite past `max_tests`: move them to a directory in a suite with room (same commit as the suite registration), never raise the cap |
| anything else | `git -C <wt> log --oneline main..HEAD -- <the files the traceback names>` names the owner |

For each failure: read the owning task (`grep -n "^### Task V205-<n>" -A 200 <its part file>`), fix the code in that task's files so the test's intent holds, then re-run **only** that file: `python <wt>/scripts/dev/testrun.py file <test path>` -- expected `0 failed`. Commit each fix on its own:

```bash
git -C <wt> add <the fixed files>
git -C <wt> commit -m "fix(<area>): <what was wrong> (v205 V205-<owner>, found by V205-17)"
```

A failure in a test that no v205 commit touches, and whose code no v205 commit reaches, is reported to the controller with its id and first assertion line; it is not fixed here. Do not re-run the full suite after a fix (`CLAUDE.md`: a failed test is fixed and re-run alone).

- [ ] **Step 4: Static gates**

```bash
python <wt>/scripts/dev/complexity_gate.py
python <wt>/scripts/dev/plan_lint.py <wt>/docs/superpowers/plans/2026-11-04-v205-admin-read-performance_0-index.md
git -C <wt> diff --stat main...HEAD -- frontend VERSION.json version_history.json
python -m alembic -c <wt>/alembic.ini heads
```

Expected: the gate clean; `plan_lint` reports no problem for any v205 file; the `diff --stat` prints nothing (Layer 1 touches no frontend file, and the bump belongs to `/close-out`); exactly one head, `v205_001`. If Step 3 made fixes, re-run `complexity_gate.py` after the last one.

- [ ] **Step 5: Report**

Hand the controller: the pass/fail/xfail counts from Step 2, each Step 3 fix as `<test id> -> V205-<owner> -> <commit sha>`, and the Step 4 verdicts. No commit belongs to this task unless Step 3 made fixes.

### Task V205-18: Deploy, migrate, backfill, measure; spec `## Results`

**Model:** sonnet — runs committed scripts on production in a fixed order and records what they print; every judgement is a threshold already set by the spec.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md` (`## Results`: append `### After v205 (script)` and the verdict), on `main`.

**Interfaces:**
- Consumes: V205-1's `scripts/ops/admin_endpoint_timing.py` and V205-14's `scripts/ops/backfill_fx_daily_rates.py`, both **unchanged** and run from the deployed image; the `M` and `D` arguments recorded in the spec's `### Before v205 (script)` line; `docs/deploy/DEPLOY_HETZNER.md` § "v205: daily FX rates" (V205-14) and § "Rolling back".
- Produces: the spec's `### After v205 (script)` table and verdict; then `/close-out` with `Bump: bot patch`.

**Rules for this task.** It runs only after the controller has merged the worktree branch into `main` and pushed it (V205-17 green first). Production changes only by deploying committed `main`: no live edit, no `.env` edit, no hand-copied file. Every remote command goes through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` from the main tree, with no command substitution inside the quotes (the wrapper expands it locally). Credentials stay in the container environment; nothing that prints them is run. Every output goes to a file in the scratchpad and only its tail is read. Commands below run from the main tree's root (`<main-tree>`).

- [ ] **Step 1: The deploy ran**

```bash
git -C <main-tree> fetch origin
git -C <main-tree> rev-parse --short=12 origin/main
gh run list --workflow deploy.yml --branch main --limit 1
gh run watch <run id from the line above> --exit-status > <scratchpad>/v205_deploy_run.txt 2>&1; echo "exit=$?"
```

Expected: the run for `origin/main`'s sha ends `exit=0`. A failed run is reported to the controller with its failing job and step (`gh run view <id> --log-failed | tail -n 40`); nothing is deployed by hand around it.

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git rev-parse --short=12 HEAD && docker compose images admin bot refresher" > <scratchpad>/v205_images.txt 2>&1
cat <scratchpad>/v205_images.txt
```

Expected: the VM's `HEAD` equals `origin/main`'s 12-character sha, and all three services run tag `sha-<that sha>`.

- [ ] **Step 2: The migration is at head**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current" > <scratchpad>/v205_alembic.txt 2>&1
tail -n 3 <scratchpad>/v205_alembic.txt
```

Expected: `v205_001 (head)`, or a later head if another plan merged after v205. If it shows an earlier revision (`deploy.sh` runs the upgrade after `up --wait`, so a failed step leaves it behind), run the runbook's manual step once, then re-check:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic upgrade head" > <scratchpad>/v205_upgrade.txt 2>&1
tail -n 5 <scratchpad>/v205_upgrade.txt
```

- [ ] **Step 3: Backfill (dry run first)**

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/backfill_fx_daily_rates.py --dry-run" > <scratchpad>/v205_backfill_dry.txt 2>&1
tail -n 10 <scratchpad>/v205_backfill_dry.txt
```

Expected: one `<PAIR> planned=<n>` line per pair in use and a total, with nothing written. A total of 0 with pairs in use, or a traceback, stops the task: report it to the controller (the code is V205-14's; the fix ships as a new commit on `main` and a new deploy).

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/backfill_fx_daily_rates.py" > <scratchpad>/v205_backfill.txt 2>&1
tail -n 3 <scratchpad>/v205_backfill.txt
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/backfill_fx_daily_rates.py" > <scratchpad>/v205_backfill_again.txt 2>&1
tail -n 3 <scratchpad>/v205_backfill_again.txt
```

Expected: the first prints `written=<n>` with `n` at most the dry run's total (the refresher's 08:00 snap may already have written today's rows). The second prints `written=0` (insert-if-absent).

- [ ] **Step 4: Read-only checks**

Create `<scratchpad>/v205_fx_rows.py`:

```python
"""Read-only: fx_daily_rates per pair and source (v205 V205-18)."""
from sqlalchemy import text

from swingbot.core.db.engine import get_engine

SQL = ("select base, account, source, count(*), min(day), max(day) from fx_daily_rates "
       "group by base, account, source order by base, account, source")
with get_engine().connect() as conn:
    for row in conn.execute(text(SQL)):
        print(*row)
```

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -" < <scratchpad>/v205_fx_rows.py > <scratchpad>/v205_fx_rows.txt 2>&1
cat <scratchpad>/v205_fx_rows.txt
bash scripts/ops/ssh-hetzner.sh "grep -h 'fx snap failed' /opt/swing-bot/logs/*.log | tail -n 5" > <scratchpad>/v205_snap_log.txt 2>&1
bash scripts/ops/ssh-hetzner.sh "grep -i slash /opt/swing-bot/logs/*.log | tail -n 5" > <scratchpad>/v205_slash.txt 2>&1
tail -n 5 <scratchpad>/v205_snap_log.txt <scratchpad>/v205_slash.txt
```

Expected: each pair's `backfill` rows end at today's Berlin date or the day before; a `snap` row exists for today once the refresher has run after 08:00 Berlin. `fx snap failed` lines, if any, are dated before the migration finished (the runbook's deploy window); a later one is reported to the controller. The slash-command sync shows its usual success line (runbook § "After every deploy or rollback").

- [ ] **Step 5: Measure**

Take `M` and `D` from the spec's `### Before v205 (script)` line and substitute them literally:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python scripts/ops/admin_endpoint_timing.py --month M --date D --runs 2" > <scratchpad>/v205_after.md 2>&1
tail -n 20 <scratchpad>/v205_after.md
```

Expected: 16 rows, every status `200`, and the `db ms` / `statements` columns now filled from the `Server-Timing` header. A non-200 row is recorded as measured and reported, never retried into a 200. If the admin answers 5xx on any row, stop and report to the controller with the row and the matching `/opt/swing-bot/logs` lines. A rollback (§ "Rolling back": redeploy the previous `sha-` image) happens only on the partner's go.

- [ ] **Step 6: Record the results and the verdict**

Append under the spec's `## Results`, after `### Before v205 (script)`:

```markdown
### After v205 (script)

Measured <YYYY-MM-DD HH:MM> Berlin with `scripts/ops/admin_endpoint_timing.py --month M --date D --runs 2`
inside the `admin` container (image `sha-<12>`), after the backfill (dry run planned=<n>,
written=<n>, re-run written=0; `fx_daily_rates`: <pairs> pairs, <rows> rows).

<the table from v205_after.md, pasted unchanged>

**Verdict against the Layer 1 Goal (every endpoint under 1.5 s):** <met | not met>.
Slowest row: `<name>` run <r> at <ms> ms (before: <ms> ms). <If not met: each row at or
over 1500 ms with its db ms and statement count, which is where the Layer 2 plan starts.>
<If every row is under 500 ms: "Layer 1 already meets the Layer 2 target; whether Layer 2
is still written is the partner's call (spec § Three plans).">
On purpose (L1-a): converted money amounts now use the close before the exit's Berlin day.
```

Fill every `<...>` from the Step 3–5 outputs. "Met" means every one of the 16 rows is under 1500 ms; one row at or over it means "not met". The verdict is never rounded in either direction.

```bash
git -C <main-tree> add docs/superpowers/specs/2026-11-04-v205-admin-read-performance-design.md
git -C <main-tree> commit -m "docs(v205): after-deploy timings and Layer 1 verdict (V205-18)"
```

- [ ] **Step 7: Close out**

Invoke the `close-out` skill (Skill tool, `close-out`) for plan v205. It applies `Bump: bot patch` (the plan's `Bump:` line; the spec's `ui patch` belongs to Part 3), regenerates `version_history.json`, moves the plan files to `implemented/` and removes the worktree. The spec stays in `specs/`: the Layer 2 and Part 3 plans build from it (precedent: v202's close-out, `4b7160af`).

