# v85 Part 7 — Watchlist (wave 2)

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R7-01 … R7-03 are Group W2-BE**, sequential among themselves, parallel with
the Trades and Risk backend strands. **R7-04 … R7-06 are Group W2-UI.**

**This is the largest new backend in the plan.** `GET /watchlist/tickers`
serves symbol, company name, open/closed trade counts and next earnings — no
price, no change, no series, no score (index finding 12). Sheet 1's row is
almost entirely new.

---

## Two things this part must not do

1. **No per-row provider call.** Spec D33: everything comes from the daily
   OHLCV cache in one batch. `get_daily_data_batch(tickers, period)` in
   `swingbot/core/marketdata/data.py:44` is that batch;
   `get_current_price_batch(tickers)` at line 83 is the intraday overlay, and
   `is_us_market_active()` at line 348 is what decides whether to ask for it.
   A loop that calls a single-symbol fetch per row turns a page view into
   ninety network calls.
2. **No change to what the scanner scans.** Spec D35: tags filter the view.
   The scanner keeps scanning every symbol.

---

### Task R7-01: The batched quote, change and sparkline builder

**Files:**
- Create: `swingbot/admin/watchlist_rows.py`
- Create: `tests/admin/test_watchlist_rows.py`

**Interfaces:**
- Consumes: `get_daily_data_batch`, `get_current_price_batch`,
  `is_us_market_active` from `swingbot/core/marketdata/data.py`.
- Produces: `build_market_rows(tickers: list[str]) -> dict[str, dict]`, keyed by
  symbol, each value
  `{"price": float | None, "as_of": str | None, "change_1d_pct": float | None,
    "change_1w_pct": float | None, "change_1m_pct": float | None,
    "spark": list[float]}`. Consumed by R7-02 and R7-04.

**A separate module, not more lines in `api_v1/watchlist.py`.** The endpoint's
job is to serve a payload; this is a computation with seven edge cases and its
own test file. Keeping them apart is what lets the edge cases be tested without
a Flask client.

**`as_of` is the date of the bar the numbers came from** — not "now". Spec D33:
each row shows the date of the bar it was computed from, so a stale cache is
visible rather than silent. This field is the whole reason the page can be
honest about a weekend or a failed refresh.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_watchlist_rows.py`:

```python
import pandas as pd
import pytest

from swingbot.admin.watchlist_rows import build_market_rows


def _frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"Close": closes}, index=idx)


@pytest.fixture
def bars(monkeypatch):
    """Install a canned batch so no test here touches the network."""
    store: dict[str, pd.DataFrame] = {}

    def fake_batch(tickers, period="2y"):
        return {t: store[t] for t in tickers if t in store}

    monkeypatch.setattr("swingbot.admin.watchlist_rows.get_daily_data_batch", fake_batch)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: False)
    return store


def test_price_is_the_last_close_when_the_market_is_shut(bars):
    bars["AAPL"] = _frame([100.0] * 25 + [171.5])
    assert build_market_rows(["AAPL"])["AAPL"]["price"] == pytest.approx(171.5)


def test_as_of_is_the_bar_date_not_today(bars):
    bars["AAPL"] = _frame([100.0] * 26, start="2026-01-01")
    row = build_market_rows(["AAPL"])["AAPL"]
    assert row["as_of"].startswith("2026-02")  # the 26th business day, not today


def test_one_day_change_is_last_close_over_previous(bars):
    bars["AAPL"] = _frame([100.0] * 25 + [110.0])
    assert build_market_rows(["AAPL"])["AAPL"]["change_1d_pct"] == pytest.approx(10.0)


def test_week_and_month_changes_use_five_and_twenty_one_bars(bars):
    bars["AAPL"] = _frame(list(range(100, 130)))  # 30 rising bars
    row = build_market_rows(["AAPL"])["AAPL"]
    assert row["change_1w_pct"] > 0
    assert row["change_1m_pct"] > row["change_1w_pct"]


def test_a_short_history_yields_null_for_the_windows_it_cannot_fill(bars):
    bars["NEW"] = _frame([100.0, 101.0, 102.0])
    row = build_market_rows(["NEW"])["NEW"]
    assert row["change_1d_pct"] is not None
    assert row["change_1w_pct"] is None
    assert row["change_1m_pct"] is None


def test_a_symbol_with_no_bars_yields_a_row_of_nulls_not_an_omission(bars):
    row = build_market_rows(["GHOST"])["GHOST"]
    assert row["price"] is None
    assert row["as_of"] is None
    assert row["spark"] == []


def test_one_bad_symbol_does_not_lose_the_others(bars):
    bars["AAPL"] = _frame([100.0] * 26)
    rows = build_market_rows(["AAPL", "GHOST"])
    assert rows["AAPL"]["price"] is not None
    assert rows["GHOST"]["price"] is None


def test_the_sparkline_is_the_last_thirty_closes(bars):
    bars["AAPL"] = _frame([float(i) for i in range(60)])
    spark = build_market_rows(["AAPL"])["AAPL"]["spark"]
    assert len(spark) == 30
    assert spark[-1] == pytest.approx(59.0)


def test_an_intraday_quote_overrides_the_close_while_the_market_is_open(bars, monkeypatch):
    bars["AAPL"] = _frame([100.0] * 26)
    monkeypatch.setattr("swingbot.admin.watchlist_rows.is_us_market_active", lambda: True)
    monkeypatch.setattr(
        "swingbot.admin.watchlist_rows.get_current_price_batch", lambda t: {"AAPL": 173.25}
    )
    assert build_market_rows(["AAPL"])["AAPL"]["price"] == pytest.approx(173.25)


def test_an_empty_watchlist_makes_no_batch_call(bars, monkeypatch):
    called = []
    monkeypatch.setattr(
        "swingbot.admin.watchlist_rows.get_daily_data_batch",
        lambda tickers, period="2y": called.append(tickers) or {},
    )
    assert build_market_rows([]) == {}
    assert called == []
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py
```

Expected: FAIL — `ModuleNotFoundError: swingbot.admin.watchlist_rows`.

- [ ] **Step 3: Write the module**

Create `swingbot/admin/watchlist_rows.py`:

```python
"""Market columns for the Watchlist, built from the daily cache in one batch.

Spec v85 D33. The rule that shapes this module: **one batch call for the whole
watchlist, never one call per row.** A ninety-symbol watchlist rendered with a
per-row fetch is ninety network round trips on every page view, and the cache
already holds every number this page needs.

`as_of` is the date of the bar the figures came from, not the time the request
was served. A page that prints "as of now" over Friday's close on a Sunday is
the failure this field exists to prevent.
"""

from __future__ import annotations

import pandas as pd

from swingbot.core.marketdata.data import (
    get_current_price_batch,
    get_daily_data_batch,
    is_us_market_active,
)

#: Trading-day offsets for the three change columns. 5 and 21 are a week and a
#: month of *business* days, which is what the cache is indexed by -- calendar
#: arithmetic here would silently straddle holidays.
_WINDOWS = {"change_1d_pct": 1, "change_1w_pct": 5, "change_1m_pct": 21}

_SPARK_BARS = 30


def _pct_change(closes: pd.Series, back: int) -> float | None:
    """Percentage change over `back` bars, or None when history is too short.

    None, never 0.0: a symbol listed three days ago has no one-month change,
    and 0.0 would claim it was flat.
    """
    if len(closes) <= back:
        return None
    prev = float(closes.iloc[-1 - back])
    if prev == 0:
        return None
    return round((float(closes.iloc[-1]) / prev - 1.0) * 100.0, 2)


def _empty_row() -> dict:
    return {
        "price": None,
        "as_of": None,
        "change_1d_pct": None,
        "change_1w_pct": None,
        "change_1m_pct": None,
        "spark": [],
    }


def build_market_rows(tickers: list[str]) -> dict[str, dict]:
    """Price, changes and a 30-bar sparkline for every ticker, keyed by symbol.

    Every requested symbol gets a row. A symbol the cache has nothing for gets
    a row of nulls rather than being dropped -- the Watchlist must still list
    it, and an omitted row would read as "removed from the watchlist".
    """
    if not tickers:
        return {}

    frames = get_daily_data_batch(list(tickers), period="6mo") or {}

    live: dict[str, float] = {}
    if is_us_market_active():
        try:
            live = get_current_price_batch(list(tickers)) or {}
        except Exception:
            # An intraday overlay is a nicety. Losing it must not lose the
            # closes, which are the page's actual content.
            live = {}

    rows: dict[str, dict] = {}
    for symbol in tickers:
        frame = frames.get(symbol)
        if frame is None or getattr(frame, "empty", True) or "Close" not in frame:
            rows[symbol] = _empty_row()
            continue

        closes = frame["Close"].dropna()
        if closes.empty:
            rows[symbol] = _empty_row()
            continue

        row = _empty_row()
        row["price"] = round(float(live.get(symbol) or closes.iloc[-1]), 4)
        row["as_of"] = str(pd.Timestamp(closes.index[-1]).date())
        for field, back in _WINDOWS.items():
            row[field] = _pct_change(closes, back)
        row["spark"] = [round(float(v), 4) for v in closes.iloc[-_SPARK_BARS:]]
        rows[symbol] = row

    return rows
```

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/watchlist_rows.py tests/admin/test_watchlist_rows.py
git commit -m "feat(watchlist): batched price, change and sparkline builder (v85 D33)"
```

---

### Task R7-02: The Signal column — the scanner's own verdict

**Files:**
- Modify: `swingbot/admin/watchlist_rows.py`
- Modify: `swingbot/admin/api_v1/watchlist.py:130-152`
- Test: `tests/admin/test_watchlist_rows.py`, `tests/admin/test_api_watchlist.py`

**Interfaces:**
- Consumes: the plan store the rest of the admin already reads (the same source
  `GET /analytics/plans` uses).
- Produces: `build_signals(tickers) -> dict[str, dict]`, each value
  `{"state": "active" | "pending" | "none", "score": float | None,
    "horizon": str | None, "strategy": str | None}`; and both market and signal
  fields merged onto each row of `GET /watchlist/tickers`. Consumed by R7-04.

**What "the scanner's verdict" actually is here.** Spec D34 asks for the bot's
own opinion rather than a price derivative. The bot does not persist a
per-symbol score — **its opinion is the plan set.** A symbol with a PENDING
plan is one the scanner has found a setup on and is waiting to trigger; an
ACTIVE plan is one it is already in; everything else is "No setup". The plan
carries the confluence/quality score, the horizon and the strategy that
produced it, which is exactly what sheet 1's Signal column shows.

**Do not run a scan to build this column.** A scan is minutes of work over the
whole watchlist. Reading the plan set is a dictionary lookup.

**Do not use `data/universe/rs_cache.json`.** Spec D34 rules relative strength
out for this column by name: it is a price derivative, and the sparkline beside
it already says what price did.

- [ ] **Step 1: Verify the plan-store symbol before writing against it**

Dispatch the `symbol-verifier` subagent: "In this repo, what function or class
does `swingbot/admin/api_v1/analytics.py`'s `/analytics/plans` endpoint use to
load the plan set, and what fields does a plan carry for status, score, horizon
and strategy?" Write the answer into this task's code before continuing. Do not
guess a loader name.

- [ ] **Step 2: Write the failing test**

Add to `tests/admin/test_watchlist_rows.py`:

```python
def test_a_pending_plan_reads_as_a_waiting_setup(plans):
    plans([{"ticker": "AAPL", "status": "PENDING", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    sig = build_signals(["AAPL"])["AAPL"]
    assert sig["state"] == "pending"
    assert sig["score"] == 78
    assert sig["horizon"] == "6w"


def test_an_active_plan_reads_as_in_position(plans):
    plans([{"ticker": "AAPL", "status": "ACTIVE", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "active"


def test_a_symbol_with_no_plan_reads_as_no_setup_not_as_zero(plans):
    plans([])
    sig = build_signals(["AAPL"])["AAPL"]
    assert sig["state"] == "none"
    assert sig["score"] is None


def test_a_closed_plan_does_not_count_as_a_live_setup(plans):
    plans([{"ticker": "AAPL", "status": "CLOSED", "score": 78, "horizon": "6w",
            "strategy": "RSI"}])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "none"


def test_the_best_scoring_plan_wins_when_a_symbol_has_several(plans):
    plans([
        {"ticker": "AAPL", "status": "PENDING", "score": 61, "horizon": "2w", "strategy": "RSI"},
        {"ticker": "AAPL", "status": "PENDING", "score": 84, "horizon": "3m", "strategy": "Fib"},
    ])
    assert build_signals(["AAPL"])["AAPL"]["score"] == 84


def test_an_active_plan_outranks_a_better_scoring_pending_one(plans):
    plans([
        {"ticker": "AAPL", "status": "PENDING", "score": 90, "horizon": "2w", "strategy": "RSI"},
        {"ticker": "AAPL", "status": "ACTIVE", "score": 60, "horizon": "3m", "strategy": "Fib"},
    ])
    assert build_signals(["AAPL"])["AAPL"]["state"] == "active"
```

Add the `plans` fixture in the style the other admin tests use to install plan
records.

Add to `tests/admin/test_api_watchlist.py`:

```python
def test_the_tickers_payload_carries_market_and_signal_fields(client, watchlist):
    watchlist(["AAPL"])
    row = client.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    for key in ("price", "as_of", "change_1d_pct", "change_1w_pct",
                "change_1m_pct", "spark", "signal"):
        assert key in row


def test_existing_fields_are_not_dropped(client, watchlist):
    watchlist(["AAPL"])
    row = client.get("/api/v1/watchlist/tickers").get_json()["tickers"][0]
    for key in ("symbol", "company_name", "open_trades", "closed_trades",
                "next_earnings_date"):
        assert key in row
```

- [ ] **Step 3: Run them to make sure they fail**

```bash
python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py
python scripts/dev/testrun.py file tests/admin/test_api_watchlist.py
```

Expected: FAIL — `build_signals` is undefined, and the payload lacks the fields.

- [ ] **Step 4: Implement `build_signals` and merge both into the payload**

In `watchlist_rows.py`, add `build_signals(tickers)`: load the plan set once,
group live plans (`ACTIVE`, `PARTIAL`, `PENDING`) by ticker, and pick per
symbol — ACTIVE-family first, then highest score. In
`api_v1/watchlist.py:list_tickers`, call both builders once each and merge onto
the existing dict comprehension. **Both builders take the whole ticker list;
neither is called inside the loop.**

- [ ] **Step 5: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_watchlist_rows.py
python scripts/dev/testrun.py file tests/admin/test_api_watchlist.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/watchlist_rows.py swingbot/admin/api_v1/watchlist.py tests/admin/test_watchlist_rows.py tests/admin/test_api_watchlist.py
git commit -m "feat(watchlist): Signal column from the live plan set (v85 D34)"
```

---

### Task R7-03: View-only tags, stored as a preference

**Files:**
- Modify: `swingbot/admin/api_v1/system.py:523-570` (the preferences payload)
- Modify: `frontend/src/app/stores/preferences.store.ts`
- Test: `tests/admin/test_api_system.py`, `frontend/src/app/stores/preferences.store.spec.ts`

**Interfaces:**
- Consumes: the existing preferences GET/PUT pair.
- Produces: a `watchlistTags` preference, shape
  `Record<string, string[]>` (symbol → tag names). Consumed by R7-05.

**Why not the watchlist file — spec D35 says this explicitly.**
`data/watchlist.json` is read by the **bot** on every scan, and a tag is a pure
view concern that the bot must never see. Widening a file the trading
process parses, to carry something only the UI reads, is the kind of coupling
this plan exists to avoid. Tags go in `PreferencesStore` instead — still an
existing store, still no new top-level JSON file, so D26 holds exactly as
written.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_system.py`:

```python
def test_watchlist_tags_round_trip_through_preferences(client):
    client.put("/api/v1/system/preferences", json={"watchlistTags": {"AAPL": ["Tech"]}})
    assert client.get("/api/v1/system/preferences").get_json()["watchlistTags"] == {
        "AAPL": ["Tech"]
    }


def test_tags_default_to_empty_rather_than_missing(client):
    assert client.get("/api/v1/system/preferences").get_json().get("watchlistTags") == {}


def test_tags_do_not_reach_the_watchlist_file(client, tmp_path):
    before = (tmp_path / "watchlist.json").read_text() if (tmp_path / "watchlist.json").exists() else None
    client.put("/api/v1/system/preferences", json={"watchlistTags": {"AAPL": ["Tech"]}})
    after = (tmp_path / "watchlist.json").read_text() if (tmp_path / "watchlist.json").exists() else None
    assert before == after
```

Point the third test at whatever path the test fixtures use for the watchlist
file in that module.

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_system.py
```

Expected: FAIL — the key is dropped by the preferences schema.

- [ ] **Step 3: Add the key at both ends**

Add `watchlistTags` to the preferences schema on the server (defaulting to
`{}`) and to `PreferencesStore` on the client, following exactly how the
existing preference keys are declared in each. No new endpoint.

- [ ] **Step 4: Run both suites and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_system.py
cd frontend && npx ng test --include src/app/stores/preferences.store.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/system.py frontend/src/app/stores/preferences.store.ts tests/admin/test_api_system.py frontend/src/app/stores/preferences.store.spec.ts
git commit -m "feat(watchlist): view-only tags as a preference, not in the bot's watchlist file

data/watchlist.json is read by the bot on every scan, and a tag is a view
concern the trading process must never parse (spec D35)."
```

---

### Task R7-04: The recomposed row

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`

**Interfaces:**
- Consumes: the widened payload from R7-02, `ui/sparkline.ts`, `ui/chip.ts`.
- Produces: nothing new.

**The row is** Symbol · Name · Price · 1D% · 1W% · 1M% · 30-day sparkline ·
Signal. The existing open/closed trade counts and next-earnings columns stay —
they are this app's own columns and sheet 1 simply did not know about them.

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`:

```typescript
it('renders price and the three change columns', () => {
  const row = firstRow({ price: 171.5, change_1d_pct: 1.94, change_1w_pct: 3.12, change_1m_pct: 6.2 });
  expect(row.textContent).toContain('171.50');
  expect(row.textContent).toContain('+1.94%');
  expect(row.textContent).toContain('+6.20%');
});

it('renders a missing price as no-value, never as zero', () => {
  const row = firstRow({ price: null });
  expect(row.querySelector('.price')!.textContent!.trim()).toBe('—');
});

it('renders the sparkline from the payload series', () => {
  const row = firstRow({ spark: [1, 2, 3, 4] });
  expect(row.querySelector('sb-sparkline')).not.toBeNull();
});

it('omits the sparkline rather than drawing a flat line for no series', () => {
  const row = firstRow({ spark: [] });
  expect(row.querySelector('sb-sparkline')).toBeNull();
});

it('shows the bar date the row was computed from', () => {
  const row = firstRow({ as_of: '2026-09-10' });
  expect(row.querySelector('.as-of')!.textContent).toContain('2026-09-10');
});

it('marks a row whose bar date is not the latest in the table', () => {
  const el = rows([{ symbol: 'A', as_of: '2026-09-10' }, { symbol: 'B', as_of: '2026-09-04' }]);
  expect(el[1].classList).toContain('lagging');
});

it('renders the signal score with its horizon when a setup is live', () => {
  const row = firstRow({ signal: { state: 'pending', score: 78, horizon: '6w', strategy: 'RSI' } });
  expect(row.querySelector('.signal')!.textContent).toContain('78');
  expect(row.querySelector('.signal')!.textContent).toContain('6w');
});

it('says No setup rather than rendering a zero score', () => {
  const row = firstRow({ signal: { state: 'none', score: null, horizon: null, strategy: null } });
  expect(row.querySelector('.signal')!.textContent!.trim()).toBe('No setup');
});

it('distinguishes in-position from waiting by more than colour', () => {
  const row = firstRow({ signal: { state: 'active', score: 78, horizon: '6w', strategy: 'RSI' } });
  expect(row.querySelector('.signal')!.textContent).toContain('In position');
});

it('keeps the columns this app already had', () => {
  const row = firstRow({ open_trades: 2, next_earnings_date: '2026-10-02' });
  expect(row.textContent).toContain('2026-10-02');
});
```

Write `firstRow(overrides)` and `rows(list)` helpers on top of the spec's
existing render helper.

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/watchlist/watchlist.spec.ts
```

Expected: FAIL on the new assertions.

- [ ] **Step 3: Render the row**

Add the columns to the table, reusing `ui/sparkline.ts` and `ui/chip.ts`. The
`lagging` class is computed by comparing each row's `as_of` to the maximum
`as_of` in the table — a symbol the cache did not refresh must not sit silently
beside eighty that did.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/watchlist/watchlist.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/watchlist
git commit -m "feat(watchlist): price, changes, sparkline and signal on every row (v85 D33/D34)"
```

---

### Task R7-05: Tag chips, search and freshness in the control bar

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/watchlist.ts`
- Test: `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`

**Interfaces:**
- Consumes: `sb-control-bar` (R2-02), `sb-freshness` (R2-06), the
  `watchlistTags` preference (R7-03).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('renders All plus one chip per tag in use', () => {
  const labels = chipLabels({ tags: { AAPL: ['Tech'], XOM: ['Energy'] } });
  expect(labels).toEqual(['All', 'Energy', 'Tech']);
});

it('filters the table to the chosen tag', () => {
  const f = render({ tags: { AAPL: ['Tech'] }, symbols: ['AAPL', 'XOM'] });
  chip(f, 'Tech').click();
  expect(visibleSymbols(f)).toEqual(['AAPL']);
});

it('does not narrow what the scanner scans', () => {
  const f = render({ tags: { AAPL: ['Tech'] }, symbols: ['AAPL', 'XOM'] });
  chip(f, 'Tech').click();
  expect(f.componentInstance.store.tickers().length).toBe(2);
});

it('offers a way to add a tag to a symbol', () => {
  expect((render().nativeElement as HTMLElement).querySelector('.add-tag')).not.toBeNull();
});

it('shows one freshness marker for the table, from the newest bar date', () => {
  const el = render({ rows: [{ as_of: '2026-09-10' }, { as_of: '2026-09-04' }] }).nativeElement as HTMLElement;
  expect(el.querySelector('sb-freshness')).not.toBeNull();
});

it('keeps the symbol search', () => {
  expect((render().nativeElement as HTMLElement).querySelector('input[type="search"]')).not.toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/watchlist/watchlist.spec.ts
```

Expected: FAIL on the new assertions.

- [ ] **Step 3: Wire the control bar**

Chips and search in the `filters` slot, add-tag and freshness in `scope`. Tag
chips are derived from the preference — the chip list is whatever tags are in
use, sorted, with `All` first. Filtering is a client-side view filter over the
already-fetched rows; **no request changes**, which is what keeps D35 true.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/watchlist/watchlist.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/watchlist
git commit -m "feat(watchlist): tag chips, search and freshness in the control bar (v85 D35)"
```

---

### Task R7-06: Ticker detail, and the narrow-width pass

**Files:**
- Modify: `frontend/src/app/workspaces/watchlist/ticker-detail.ts`
- Test: `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts`

**Interfaces:**
- Consumes: the panel language, `sb-freshness`.
- Produces: nothing.

- [ ] **Step 1: Run the existing spec and note it green**

```bash
cd frontend && npx ng test --include src/app/workspaces/watchlist/ticker-detail.spec.ts
```

Expected: PASS. This is the baseline — if anything is red before you start, fix
that first or the diff is unreadable.

- [ ] **Step 2: Apply the panel language and add freshness**

Panels become `sb-panel`; the metric grid becomes
`repeat(auto-fit, minmax(140px, 1fr))`; every in-page heading goes (the top bar
owns it); each fetching panel gets `sb-freshness`. No binding, `computed` or
store call changes — if one is required, stop: that is a new task, not this one.

- [ ] **Step 3: Run both watchlist specs and the guard**

```bash
cd frontend && npx ng test --include "src/app/workspaces/watchlist/**/*.spec.ts"
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: the watchlist specs PASS; the guard no longer names either watchlist
file.

- [ ] **Step 4: Screenshot both pages at both widths**

Screenshot `/watchlist` and one `/watchlist/:symbol` at 1440px and 390px.
Confirm at 390px: the eight-column table scrolls inside its own container, the
page body does not scroll sideways, no column is hidden, and the sparkline
still renders at its reduced width.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/watchlist
git commit -m "style(watchlist): ticker detail in the v85 panel language"
```
