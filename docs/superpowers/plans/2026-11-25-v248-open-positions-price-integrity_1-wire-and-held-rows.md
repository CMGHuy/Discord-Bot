# v248 — Open-positions price integrity — Part 1: `error_at` on the wire, the shared progress module, held rows priced from prev close

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V248-2" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-25-v248-open-positions-price-integrity-design.md](../specs/2026-11-25-v248-open-positions-price-integrity-design.md) § 1a (server half: the shared progress function and the parity fixture), § 1b (server half: `error_at` from the same query), § 1d (the neutral prev-close bar), § 2 (held rows always priced), and the § Testing rows for 1a, 1b, 2 and the parity fixture.
**Index:** [2026-11-25-v248-open-positions-price-integrity_0-index.md](2026-11-25-v248-open-positions-price-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the binding "Decisions the spec left open" live there; every task below implicitly includes them.
**Brief:** `.superpowers/briefs/2026-11-25-v248-open-positions-price-integrity.md` (§ 3b–3f excerpts, § 7 traps).

Tasks: V248-1 (`error_at` beside the error), V248-2 (`trade_progress.py` + parity fixture), V248-3 (held rows priced from prev close). Run in id order: V248-3 asserts `price_error_at` from V248-1 and calls `trade_progress` from V248-2; V248-2 and V248-3 both edit `swingbot/admin/api_v1/trades.py`.

All three tasks reach Postgres-backed fixtures (`tests/db/`, `tests/admin/`, `tests/admin_market/`): run `/replicate-prod-db` once before the first test run, in the shared `swing-db` container (port 56789). Every command runs from the worktree root.

---

# Phase 1 — The server knows when an error happened and where a price sits

### Task V248-1: `error_at` beside the error from one query; `price_error_at` on trade rows, `error_at` on `/market/updates`

**Model:** sonnet — a repository read widened by one column and threaded through a dataclass, two dict builders and four test files; mechanical but crosses the DB, the door and the polled endpoint.

**Files:**
- Modify: `swingbot/core/db/repositories/market_refresh.py:190-195` (`errors` → new `error_marks`, `errors` delegates)
- Modify: `swingbot/admin/market_values.py:26-34` (`MarketQuote.error_at`), `:58-81` (`_quote`, `_marks`), `:110-121` (`read_quotes`), `:124-132` (`quote_fields`), `:135-140` (`last_close_fields` docstring only), `:214-229` (`read_snapshot` unpacks the new marks shape)
- Modify: `swingbot/admin/api_v1/market_updates.py:85-87` (`_quote_updates` item)
- Modify: `tests/admin_market/conftest.py:41-54` (`FakeMarks`)
- Test: `tests/db/test_market_refresh_repos.py`, `tests/admin_market/test_market_values.py`, `tests/admin_market/test_market_updates.py`

**Interfaces:**
- Consumes: the existing `market_refresh_marks.error_at` column (set to `now` by `clear(error=...)`, nulled by `mark()`; no schema change).
- Produces:
  - `RefreshMarkRepository.error_marks(keys, *, conn=None) -> dict[str, tuple[str, datetime | None]]` — one `SELECT key, error, error_at`; `errors(keys, *, conn=None) -> dict[str, str]` keeps its signature and result and delegates to it (still one query).
  - `MarketQuote.error_at: Optional[str] = None` — ISO-8601 UTC string (`datetime.isoformat()`), last field after `source`, so the positional `MarketQuote(...)` in `trades._row_quote` (`trades.py:1244`) stays valid.
  - `market_values.quote_fields(quote)` adds key `"price_error_at"` (ISO string or None; None when `quote is None`). Every row built from it (trade rows on the door path, watchlist rows, `api_v1/market.py:737`) gains the key.
  - `/api/v1/market/updates` quote item adds key `"error_at"` (ISO string or null).
  - V248-3 asserts `price_error_at` on held rows; V248-10 types `QuoteUpdate.error_at` and `RowQuoteFields.price_error_at` on the client.

**Why.** Spec § 1b: `refresh failed` sits beside a good price because the client cannot tell whether the failure is older than the price. The server already stores `error_at`; it only has to return it, from the query it already runs on every `/market/updates` poll (staff-engineer panel: no second query on a polled endpoint). `_snapshot_marks` (`market_updates.py:113-121`) keeps calling `errors()` — snapshot items need no `error_at`.

- [ ] **Step 1: Write the failing repository test**

Append to `tests/db/test_market_refresh_repos.py` (after `test_clear_keeps_the_row_with_its_error_until_the_next_mark`):

```python
def test_error_marks_carry_the_error_time_and_errors_delegates(db_conn, monkeypatch):
    m = mr.RefreshMarkRepository()
    m.mark(["quote:AAPL", "quote:MSFT"], timeout_s=120, now=T0, conn=db_conn)
    m.clear(["quote:AAPL"], error="no quote", now=T0 + timedelta(seconds=5), conn=db_conn)
    m.clear(["quote:MSFT"], now=T0 + timedelta(seconds=5), conn=db_conn)
    marks = m.error_marks(["quote:AAPL", "quote:MSFT", "quote:X"], conn=db_conn)
    assert marks == {"quote:AAPL": ("no quote", T0 + timedelta(seconds=5))}
    calls = []
    real = m.error_marks
    monkeypatch.setattr(m, "error_marks",
                        lambda keys, *, conn=None: calls.append(list(keys)) or real(keys, conn=conn))
    assert m.errors(["quote:AAPL"], conn=db_conn) == {"quote:AAPL": "no quote"}
    assert calls == [["quote:AAPL"]]                        # one read, not a second query
    m.mark(["quote:AAPL"], timeout_s=120, now=T0 + timedelta(seconds=10), conn=db_conn)
    assert real(["quote:AAPL"], conn=db_conn) == {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/db/test_market_refresh_repos.py`
Expected: FAIL — `AttributeError: 'RefreshMarkRepository' object has no attribute 'error_marks'`.

- [ ] **Step 3: Implement `error_marks` and make `errors` delegate**

In `swingbot/core/db/repositories/market_refresh.py`, replace `errors` (lines 190-195) with:

```python
    def error_marks(self, keys, *, conn=None) -> dict[str, tuple[str, datetime | None]]:
        """{key: (error text, error_at)} for keys whose last refresh failed (v248)."""
        t = self.table
        stmt = sa.select(t.c.key, t.c.error, t.c.error_at).where(
            t.c.key.in_(list(keys)), t.c.error.is_not(None))
        with self._tx(conn) as c:
            return {r.key: (r.error, r.error_at) for r in c.execute(stmt)}

    def errors(self, keys, *, conn=None) -> dict[str, str]:
        return {key: text for key, (text, _at) in self.error_marks(keys, conn=conn).items()}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python scripts/dev/testrun.py file tests/db/test_market_refresh_repos.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Teach the fake the new read**

In `tests/admin_market/conftest.py`, `FakeMarks.errors_by_key` values may now be a plain string (existing tests, including `tests/admin_snapshots/test_market_updates_snapshots.py:52` and `test_snapshot_door.py:100`, keep working) or a `(text, datetime)` tuple. Replace `FakeMarks.errors` with:

```python
    def error_marks(self, keys):
        out = {}
        for k in keys:
            if k in self.errors_by_key:
                v = self.errors_by_key[k]
                out[k] = v if isinstance(v, tuple) else (v, None)
        return out

    def errors(self, keys):
        return {k: text for k, (text, _at) in self.error_marks(keys).items()}
```

- [ ] **Step 6: Write the failing door and updates tests**

In `tests/admin_market/test_market_values.py`, add `"price_error_at"` to `ROW_QUOTE_FIELDS` (lines 10-11), add `from datetime import datetime, timezone` to the imports, and append:

```python
ERR_AT = datetime(2026, 11, 25, 13, 0, tzinfo=timezone.utc)


def test_mark_error_carries_its_time_as_iso(market, session_is):
    market.quote("BAD", 7.0, age_s=30)
    market.marks.errors_by_key["quote:BAD"] = ("no quote", ERR_AT)
    q = mv.read_quotes(["BAD"])["BAD"]
    assert q.error == "no quote" and q.error_at == "2026-11-25T13:00:00+00:00"
    assert mv.quote_fields(q)["price_error_at"] == "2026-11-25T13:00:00+00:00"


def test_error_without_a_time_and_no_error_read_null(market, session_is):
    market.quote("OLD", 7.0, age_s=30)
    market.quote("OK", 9.0, age_s=30)
    market.marks.errors_by_key["quote:OLD"] = "provider 503"      # a fake row without a time
    quotes = mv.read_quotes(["OLD", "OK"])
    assert quotes["OLD"].error == "provider 503" and quotes["OLD"].error_at is None
    assert quotes["OK"].error is None and quotes["OK"].error_at is None
    assert mv.quote_fields(None)["price_error_at"] is None


def test_never_cached_symbol_still_carries_its_error_time(market, session_is):
    market.marks.errors_by_key["quote:NEWX"] = ("no quote", ERR_AT)
    q = mv.read_quotes(["NEWX"], enqueue=False)["NEWX"]
    assert q.price is None and q.error_at == "2026-11-25T13:00:00+00:00"


def test_mark_read_failure_fails_open_without_error_times(market, session_is, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(market.marks, "error_marks", broken)
    market.quote("MSFT", 110.0, age_s=5)
    q = mv.read_quotes(["MSFT"], enqueue=False)["MSFT"]
    assert q.price == 110.0 and q.error is None and q.error_at is None
```

In `tests/admin_market/test_market_updates.py`, change the key-set assertion in `test_since_lists_changed_quotes_and_in_flight_marks` (line 51) to `{"symbol", "price", "as_of", "refreshing", "error", "error_at"}` and append:

```python
def test_quote_item_carries_the_error_time(on_client, market, changes):
    market.quote("DOCU", 80.0, age_s=50_000)
    market.marks.errors_by_key["quote:DOCU"] = ("no quote", NOW)
    changes.append({"key": "quote:DOCU:", "symbol": "DOCU", "fetched_at": NOW,
                    "doc": {}, "updated_at": NOW})
    since = (NOW - timedelta(minutes=1)).isoformat()
    body = on_client.get("/api/v1/market/updates", query_string={"since": since}).get_json()
    [item] = [q for q in body["quotes"] if q["symbol"] == "DOCU"]
    assert item["error"] == "no quote" and item["error_at"] == NOW.isoformat()
```

- [ ] **Step 7: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_market/test_market_values.py` and `python scripts/dev/testrun.py file tests/admin_market/test_market_updates.py`
Expected: FAIL — `AttributeError: 'MarketQuote' object has no attribute 'error_at'`, the `ROW_QUOTE_FIELDS` set mismatch, and the missing `"error_at"` key.

- [ ] **Step 8: Thread `error_at` through the door and the updates item**

In `swingbot/admin/market_values.py`:
- `MarketQuote` gains a last field `error_at: Optional[str] = None` (after `source`).
- `_marks(keys) -> tuple[set[str], dict[str, tuple[str, Optional[datetime]]]]` returns `dict(repo.error_marks(keys))` in place of `dict(repo.errors(keys))`; the fail-open branch is unchanged (`set(), {}`).
- `_quote(symbol, entry, in_flight, mark, now)` — the fourth parameter becomes `mark: Optional[tuple[str, Optional[datetime]]]` (the `error_marks` value or None). Unpack `error, error_at = mark or (None, None)` and pass `error=error`, `error_at=error_at.isoformat() if error_at else None` by keyword in **both** `MarketQuote(...)` constructions (the `entry is None` branch included).
- `read_quotes`: `in_flight, marks = _marks(...)`; pass `marks.get(admin_refresh.quote_mark_key(s))` to `_quote`.
- `read_snapshot` (line 220, the other `_marks` caller): its marks dict now holds `(text, at)` tuples, so the `"error"` value becomes `(marks.get(mark) or (None, None))[0] or read_error` -- snapshot payloads keep a plain string (`tests/admin_snapshots/test_snapshot_door.py:100` pins it).
- `quote_fields`: add `"price_error_at": None` to the `quote is None` dict and `"price_error_at": quote.error_at` to the other.
- `last_close_fields` docstring: replace "it is shown as a close with its date, never as a live price, and nothing derived (P&L, status bar) is computed from it" with "it is shown as a close with its date, never as a live price; v248 prices held trade rows from it as `price_kind = prev_close` with a neutral status bar (`api_v1/trades._price_held_rows`, V248-3)".

In `swingbot/admin/api_v1/market_updates.py` `_quote_updates`, add `"error_at": quotes[s].error_at` to the item dict (lines 85-86).

- [ ] **Step 9: Run them to verify they pass, and the neighbours that read marks**

Run each:
- `python scripts/dev/testrun.py file tests/admin_market/test_market_values.py`
- `python scripts/dev/testrun.py file tests/admin_market/test_market_updates.py`
- `python scripts/dev/testrun.py file tests/admin_snapshots/test_market_updates_snapshots.py`
- `python scripts/dev/testrun.py file tests/admin_snapshots/test_snapshot_door.py`
- `python scripts/dev/testrun.py file tests/admin_market/test_trades_market.py`
- `python scripts/dev/testrun.py file tests/admin_market/test_tape_watchlist_market.py`

Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` — Expected: no new offender.

- [ ] **Step 10: Commit**

```bash
git add swingbot/core/db/repositories/market_refresh.py swingbot/admin/market_values.py swingbot/admin/api_v1/market_updates.py tests/db/test_market_refresh_repos.py tests/admin_market/conftest.py tests/admin_market/test_market_values.py tests/admin_market/test_market_updates.py
git commit -m "feat(v248): error_at beside the refresh error from one query, on rows and /market/updates"
```

### Task V248-2: Shared progress module (`row_progress`, prev-close neutral bar) + parity fixture + `DATA_READERS` row

**Model:** sonnet — a behaviour-preserving move of two arithmetic functions into a pure module plus one new mode, held by a hand-checked JSON fixture; the existing trades API tests guard the move.

**Files:**
- Create: `swingbot/admin/api_v1/trade_progress.py`
- Create: `tests/fixtures/v248/progress_cases.json`
- Create: `tests/admin/test_v248_progress_parity.py`
- Modify: `swingbot/admin/api_v1/trades.py:1261-1308` (`_status_fields` delegates), `:1310-1345` (`_trailing_status_fields` delegates, keeps `_runner_pnl_fields`), `:1358-1376` (`_attach_status_fields`), imports (after line 61)
- Modify: `scripts/dev/select_tests.py:346` (one `DATA_READERS` row after the `tests/fixtures/v229/` row)

**Interfaces:**
- Consumes: `swingbot.core.tracking.performance.trade_proximity(direction, entry, stop_loss, take_profit, current_price) -> dict` (keys `proximity`, `blink_seconds`, `label`; unchanged, still the only source of band urgency and label); `trades._live_r(row, price)` and `trades._runner_pnl_fields(row)` (unchanged).
- Produces (`swingbot/admin/api_v1/trade_progress.py`):
  - `PRICE_LIVE = "live"`, `PRICE_PREV_CLOSE = "prev_close"`, `PREV_CLOSE_LABEL = "At prev close (not live)"`, `TERMINAL_STATUSES = frozenset({"CLOSED", "CANCELLED"})` (equal to `trades._TERMINAL`, pinned by a test).
  - `status_fields(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict` — today's `_status_fields` body.
  - `trailing_bar_fields(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict` — today's `_trailing_status_fields` body **without** the `_runner_pnl_fields` merge.
  - `uses_trailing_bar(row: dict) -> bool` — `bar_kind == "trailing"` and status not terminal.
  - `row_progress(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict` — exactly the five keys `progress_pct`, `entry_pct`, `progress_band`, `blink_seconds`, `status_label`; dispatch: trailing bar → `trailing_bar_fields`; status terminal or `PENDING` → the status chip (`status_label = row["status"]`, the rest None); else `status_fields`.
  - Prev-close rule (index Decision 2), applied inside both bar functions: when `price_kind == PRICE_PREV_CLOSE` and a bar exists (`progress_pct` not None), `progress_band = "neutral"`, `blink_seconds = None`, `status_label = PREV_CLOSE_LABEL`; positions stay computed and clamped as today.
  - `trades._trailing_status_fields(row, price, *, price_kind=trade_progress.PRICE_LIVE)` gains the keyword (V248-3 passes it).
  - `tests/fixtures/v248/progress_cases.json`: a **top-level JSON array** of `{name, row, price, price_kind, expected: {progress_pct, entry_pct, progress_band, blink_seconds, status_label, r_multiple}}`. `row` keys are only those of V248-10's `ProgressInput`: `status, direction, entry, stop_loss, target, bar_kind, runner_best, banked_exit_price, risk_stop, banked_fraction, banked_r`. `r_multiple` is the R the row shows at `price`, by `_attach_unrealized_pnl`'s rule: null when `price` or `entry` is null or the status is terminal or `PENDING`, else `trades._live_r(row, price)`. V248-10's TypeScript spec reads this file.

**Why.** Spec § 1a and index Decision 1: the client must recompute the bar when the overlay replaces the price, so the arithmetic needs one home it can be mirrored from and a fixture both sides must agree on. Moving it out of `trades.py` also keeps `_trailing_status_fields` (C 13) from gaining the prev-close branch. Decision 2 (veteran-trader panel): before the open the real price can sit far from yesterday's close, so a prev-close bar never shows a stop, target or near band. Decision 9: the `DATA_READERS` row names the Python test only.

Every expected number below was produced by today's `trades._attach_status_fields` and `trades._live_r` on these exact rows (prev-close cases: same position numbers, neutral band); do not re-derive them.

- [ ] **Step 1: Create the parity fixture**

Create `tests/fixtures/v248/progress_cases.json` with exactly these 16 cases (`BULL` = `{"status": "ACTIVE", "direction": "bullish", "entry": 100.0, "stop_loss": 90.0, "target": 120.0, "risk_stop": 90.0, "bar_kind": "none"}`; `BEAR` = `{"status": "ACTIVE", "direction": "bearish", "entry": 50.0, "stop_loss": 55.0, "target": 40.0, "risk_stop": 55.0, "bar_kind": "none"}`; `TRAIL` = `{"status": "PARTIAL", "direction": "bearish", "entry": 52.0, "stop_loss": 55.0, "target": null, "risk_stop": 57.0, "bar_kind": "trailing", "runner_best": 45.0, "banked_exit_price": 50.0, "banked_fraction": 0.5, "banked_r": 2.0}` — write each `row` out in full in the JSON, no references). Columns: name · row · price · price_kind → progress_pct, entry_pct, progress_band, blink_seconds, status_label, r_multiple:

| name | row | price | kind | expected |
|---|---|---|---|---|
| `bull_live_toward_target` | BULL | 110.0 | live | 66.7, 33.3, `toward_target`, 1.4, `Trending toward target`, 1.0 |
| `bull_live_near_stop` | BULL | 92.0 | live | 6.7, 33.3, `toward_stop`, 0.92, `Near stop-loss`, -0.8 |
| `bull_live_past_target_clamps` | BULL | 125.0 | live | 100.0, 33.3, `toward_target`, 0.6, `Near target`, 2.5 |
| `bear_live_toward_target` | BEAR | 45.0 | live | 66.7, 33.3, `toward_target`, 1.4, `Trending toward target`, 1.0 |
| `bull_no_price` | BULL | null | live | null, null, null, null, `No live price`, null |
| `bull_prev_close_without_a_price` | BULL | null | prev_close | null, null, null, null, `No live price`, null |
| `bull_missing_stop_degrades` | BULL + `stop_loss: null, risk_stop: null` | 110.0 | live | null, null, null, null, `No live price`, null |
| `bull_malformed_span_degrades` | BULL + `stop_loss: 120.0, target: 90.0, risk_stop: 120.0` | 110.0 | live | null, null, null, null, `No live price`, 0.5 |
| `bull_prev_close_near_stop_is_neutral` | BULL | 92.0 | prev_close | 6.7, 33.3, `neutral`, null, `At prev close (not live)`, -0.8 |
| `bull_prev_close_past_target_is_neutral` | BULL | 125.0 | prev_close | 100.0, 33.3, `neutral`, null, `At prev close (not live)`, 2.5 |
| `pending_has_no_bar` | BULL + `status: "PENDING"` | 110.0 | live | null, null, null, null, `PENDING`, null |
| `closed_has_no_bar` | BULL + `status: "CLOSED"` | 110.0 | live | null, null, null, null, `CLOSED`, null |
| `trailing_short_live` | TRAIL | 50.0 | live | 50.0, 50.0, `neutral`, 2.2, `Trailing`, 1.2 |
| `trailing_short_live_near_stop` | TRAIL | 54.0 | live | 10.0, 50.0, `toward_stop`, 0.92, `Near trailing stop`, 0.8 |
| `trailing_short_prev_close_is_neutral` | TRAIL | 54.0 | prev_close | 10.0, 50.0, `neutral`, null, `At prev close (not live)`, 0.8 |
| `trailing_without_best_keeps_the_chip` | TRAIL + `runner_best: null` | 50.0 | live | null, null, null, null, `PARTIAL`, 1.2 |

One entry, written out, for the shape:

```json
  {
    "name": "bull_prev_close_near_stop_is_neutral",
    "row": {"status": "ACTIVE", "direction": "bullish", "entry": 100.0, "stop_loss": 90.0,
            "target": 120.0, "risk_stop": 90.0, "bar_kind": "none"},
    "price": 92.0,
    "price_kind": "prev_close",
    "expected": {"progress_pct": 6.7, "entry_pct": 33.3, "progress_band": "neutral",
                 "blink_seconds": null, "status_label": "At prev close (not live)",
                 "r_multiple": -0.8}
  }
```

- [ ] **Step 2: Write the failing parity and module tests**

Create `tests/admin/test_v248_progress_parity.py`:

```python
"""v248 V248-2: the status-bar arithmetic lives in trade_progress.py; the
client's ui/position-progress.ts (V248-10) is held to it by the same fixture."""
import copy
import json
from pathlib import Path

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot.admin.api_v1 import trade_progress as tp
from swingbot.admin.api_v1 import trades

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v248" / "progress_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
BAR_KEYS = ("progress_pct", "entry_pct", "progress_band", "blink_seconds", "status_label")


def _shown_r(row, price):
    """The R `_attach_unrealized_pnl` puts on the row at `price`."""
    if price is None or row.get("entry") is None:
        return None
    if row["status"] in tp.TERMINAL_STATUSES or row["status"] == "PENDING":
        return None
    return trades._live_r(row, price)


def test_fixture_is_well_formed():
    names = [c["name"] for c in CASES]
    assert len(names) == 16 and len(set(names)) == 16
    for case in CASES:
        assert set(case) == {"name", "row", "price", "price_kind", "expected"}
        assert set(case["expected"]) == {*BAR_KEYS, "r_multiple"}
        assert case["price_kind"] in (tp.PRICE_LIVE, tp.PRICE_PREV_CLOSE)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_server_matches_the_shared_fixture(case):
    row = copy.deepcopy(case["row"])
    got = tp.row_progress(row, case["price"], price_kind=case["price_kind"])
    assert set(got) == set(BAR_KEYS)
    assert got == {k: case["expected"][k] for k in BAR_KEYS}
    assert _shown_r(row, case["price"]) == case["expected"]["r_multiple"]
    assert row == case["row"]                               # pure: the row is not touched


def test_terminal_set_is_the_trades_one():
    assert tp.TERMINAL_STATUSES == frozenset(trades._TERMINAL)


@pytest.mark.parametrize("price", [80.0, 92.0, 105.0, 119.0, 140.0])
def test_prev_close_never_claims_a_stop_or_target(price):
    row = next(c["row"] for c in CASES if c["name"] == "bull_live_toward_target")
    got = tp.row_progress(row, price, price_kind=tp.PRICE_PREV_CLOSE)
    live = tp.row_progress(row, price)
    assert got["progress_band"] == "neutral" and got["blink_seconds"] is None
    assert got["status_label"] == tp.PREV_CLOSE_LABEL
    assert (got["progress_pct"], got["entry_pct"]) == (live["progress_pct"], live["entry_pct"])


def test_trades_wrappers_delegate():
    bull = next(c["row"] for c in CASES if c["name"] == "bull_live_near_stop")
    trail = next(c["row"] for c in CASES if c["name"] == "trailing_short_live")
    assert trades._status_fields(bull, 92.0) == tp.status_fields(bull, 92.0)
    wrapped = trades._trailing_status_fields(trail, 50.0)
    assert {k: wrapped[k] for k in BAR_KEYS} == tp.trailing_bar_fields(trail, 50.0)
    assert {"stop_pnl_pct", "best_pnl_pct"} <= set(wrapped)        # runner P&L still merged
    chip = trades._trailing_status_fields({**trail, "runner_best": None}, 50.0)
    assert "stop_pnl_pct" not in chip                               # the chip path adds nothing


def test_attach_status_fields_uses_row_progress_for_every_kind():
    rows = [copy.deepcopy(c["row"]) | {"current_price": c["price"]}
            for c in CASES if c["price_kind"] == tp.PRICE_LIVE]
    trades._attach_status_fields(rows)
    for row in rows:
        assert {k: row[k] for k in BAR_KEYS} == tp.row_progress(row, row["current_price"])
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_v248_progress_parity.py`
Expected: FAIL — `ImportError: cannot import name 'trade_progress' from 'swingbot.admin.api_v1'`.

- [ ] **Step 4: Create `trade_progress.py` and make `trades.py` delegate**

Create `swingbot/admin/api_v1/trade_progress.py` with the constants and functions in the Interfaces block. Move `_status_fields`' docstring and body (`trades.py:1262-1308`) into `status_fields` and `_trailing_status_fields`' docstring and body (`:1311-1340`) into `trailing_bar_fields`, unchanged, except that each returns through one private helper:

```python
def _prev_close_bar(fields: dict, price_kind: str) -> dict:
    """Index Decision 2: a bar drawn from yesterday's close is never urgent."""
    if price_kind != PRICE_PREV_CLOSE or fields["progress_pct"] is None:
        return fields
    return {**fields, "progress_band": "neutral", "blink_seconds": None,
            "status_label": PREV_CLOSE_LABEL}
```

Module docstring: one paragraph naming `trades.py` as the caller, `frontend/src/app/ui/position-progress.ts` as the mirror and `tests/fixtures/v248/progress_cases.json` as the contract. Import `trade_proximity` at module top (`trades.py` already imports `swingbot.core.tracking.performance` at top level, so there is no new import cycle).

In `swingbot/admin/api_v1/trades.py`:
- add `from . import trade_progress` after the `from .money import ...` line (61);
- `_status_fields(row, price)` keeps its name and a one-line docstring and returns `trade_progress.status_fields(row, price)`;
- `_trailing_status_fields(row, price, *, price_kind=trade_progress.PRICE_LIVE)` returns `trade_progress.trailing_bar_fields(row, price, price_kind=price_kind)`, plus `out.update(_runner_pnl_fields(row))` only when `out["progress_pct"] is not None` (today's chip path returns before that merge — keep it so);
- `_attach_status_fields(rows)` keeps its docstring; its loop becomes:

```python
    for row in rows:
        price = row.get("current_price")
        if trade_progress.uses_trailing_bar(row):
            row.update(_trailing_status_fields(row, price))
        else:
            row.update(trade_progress.row_progress(row, price))
```

- [ ] **Step 5: Add the `DATA_READERS` row**

In `scripts/dev/select_tests.py`, directly after `("tests/fixtures/v229/", ("tests/scripts/test_deferred_entry_bars.py",)),` (line 346), add:

```python
    # v248: the progress-bar parity cases, read by the server test here and by
    # frontend/src/app/ui/position-progress.spec.ts (ng test, CI only).
    ("tests/fixtures/v248/", ("tests/admin/test_v248_progress_parity.py",)),
```

- [ ] **Step 6: Run the new test, the trades API tests that pin the old behaviour, and the selector guard**

Run each:
- `python scripts/dev/testrun.py file tests/admin/test_v248_progress_parity.py`
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py` (the SR7 status-bar and trailing-runner tests at lines 1060-1330 are the behaviour-preservation check)
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`
- `python scripts/dev/testrun.py file tests/dev/test_select_tests.py`

Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` — Expected: no new offender; `trade_progress.status_fields` and `trailing_bar_fields` stay below 15 (they are today's bodies plus one call), `_trailing_status_fields` drops.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/trade_progress.py swingbot/admin/api_v1/trades.py tests/fixtures/v248/progress_cases.json tests/admin/test_v248_progress_parity.py scripts/dev/select_tests.py
git commit -m "feat(v248): trade_progress module with the prev-close neutral bar and a shared parity fixture"
```


# Phase 2 — A held position always has a price

### Task V248-3: Held rows always priced: live trade, else `last_close` as `prev_close`; neutral STATUS; idempotent

**Model:** sonnet — one new helper in a legacy-heavy module with an idempotency contract (the sort-by-price branch runs the attach passes twice) and a page-meta side effect to keep honest; the tests are written out below.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:1242-1246` (`_row_quote`), `:1358-1376` (`_attach_status_fields` passes `price_kind`), `:1454-1464` (`_attach_door_prices` calls the new helper), new `_price_held_rows` and `_held_price_fields` directly below `_attach_door_prices`
- Test: `tests/admin/test_api_quote_fields.py` (new fixture and tests appended)

**Interfaces:**
- Consumes: V248-1 — `MarketQuote(..., error_at=...)` and `market_values.quote_fields()` emitting `price_error_at`; V248-2 — `trade_progress.PRICE_LIVE`, `PRICE_PREV_CLOSE`, `PREV_CLOSE_LABEL`, `row_progress(row, price, *, price_kind=)`, `uses_trailing_bar(row)`, and `trades._trailing_status_fields(row, price, *, price_kind=)`; existing `market_values.read_quotes`, `last_close_fields(symbols) -> {SYM: {"last_close", "last_close_date"}}`, `trades._OPEN_STATUSES`.
- Produces:
  - `trades._price_held_rows(live: list[dict]) -> None` — for every row whose status is in `_OPEN_STATUSES` (`ACTIVE`, `PARTIAL`): first drops any `price_kind` a previous pass left, then
    - live price present → `price_kind = "live"`, nothing else touched;
    - else `last_close` present → `current_price = last_close`, `price_kind = "prev_close"`, `price_as_of = None`, `price_age_s = None`, `current_price_stale = False`; `price_error`, `price_error_at`, `price_refreshing`, `last_close`, `last_close_date` kept as the door set them;
    - else nothing (no `price_kind` key; `current_price` stays None — the client's `no price yet`, V248-13).
  - Rows that are not held (`PENDING`, `EXPIRED`, …) never get `price_kind`; their `last_close` behaviour is unchanged.
  - Held door rows carry `price_kind: "live" | "prev_close"`; `progress_*`, `pnl_pct` and `r_multiple` come from the shown price (so `at prev close` figures on the client, V248-13); a prev-close row's bar is neutral with `status_label = "At prev close (not live)"`.
  - `_row_quote(row)` hands `_page_market_meta` a `MarketQuote` with `price=None` for a prev-close row, so `market_meta.missing_count` keeps counting it as unpriced and `as_of` never meets a None stamp.
  - The legacy and layer price paths (`_attach_current_prices` with the refresher off, `_attach_layer_prices`) are untouched: no `price_kind` there.

**Why.** Spec § 2 and § 1d: DOCU had a bid/ask but no trade before the open, and the row read `—`. A held position now always shows a price — the live trade, else yesterday's close tagged as such — and never the bid/ask midpoint (anti-goal). Index Decision 3: `price_as_of = None` on a prev-close row, so the client overlay's `isNewer` upgrades it on any priced update (V248-11). Review Focus 1: `list_trades` runs `_attach_current_prices` → `_attach_status_fields` → `_attach_unrealized_pnl` twice on the same dicts when sorting by a priced field, so the helper must be idempotent and must never replace a live price. `list_trades` (E 32, legacy) gets no new branch: all new logic sits in the two helpers.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_api_quote_fields.py` (add the imports at the top of the file, beside the existing ones):

```python
import copy

from swingbot.admin import market_values
from swingbot.admin.api_v1 import trade_progress as tp
from swingbot.admin.api_v1 import trades as trades_api
from swingbot.admin.market_values import MarketQuote

_AS_OF = "2026-11-25T14:40:00+00:00"
_ERR_AT = "2026-11-25T14:41:00+00:00"


def _held(ticker, *, status="ACTIVE", **extra):
    row = {"id": ticker, "ticker": ticker, "status": status, "direction": "bullish",
           "entry": 100.0, "stop_loss": 90.0, "target": 120.0, "risk_stop": 90.0,
           "bar_kind": "none", "open_shares": None}
    row.update(extra)
    return row


def _live(sym, price, *, error=None, error_at=None):
    return MarketQuote(symbol=sym, price=price, as_of=_AS_OF, age_s=30.0, refreshing=False,
                       error=error, source="alpaca-iex", error_at=error_at)


def _bid_ask_only(sym):
    """DOCU before the open: Alpaca has bid/ask (76.57 / 84.18) but no trade."""
    return MarketQuote(symbol=sym, price=None, as_of="2026-11-24T21:00:00+00:00",
                       age_s=63_600.0, refreshing=False, error="no quote",
                       source="alpaca-iex", error_at=_ERR_AT)


@pytest.fixture
def door(monkeypatch):
    """The refresher-on door with a fake cache: quotes and daily closes by symbol."""
    from swingbot.core.market import session
    from swingbot.core.marketdata.shared import admin_refresh
    state = {"quotes": {}, "closes": {}, "close_reads": []}
    monkeypatch.setattr(admin_refresh, "refresher_on", lambda: True)
    monkeypatch.setattr(session, "session_state", lambda now=None: "extended")

    def read_quotes(symbols, **_kw):
        return {s.upper(): state["quotes"][s.upper()] for s in symbols
                if s.upper() in state["quotes"]}

    def last_close_fields(symbols):
        state["close_reads"].append(sorted(s.upper() for s in symbols))
        return {s.upper(): state["closes"][s.upper()] for s in symbols
                if s.upper() in state["closes"]}

    monkeypatch.setattr(market_values, "read_quotes", read_quotes)
    monkeypatch.setattr(market_values, "last_close_fields", last_close_fields)
    monkeypatch.setattr(trades_api, "convert_amount",
                        lambda amount, ticker, on, **_kw: (amount, False))
    return state


def _price(rows):
    trades_api._attach_current_prices(rows)
    trades_api._attach_status_fields(rows)
    trades_api._attach_unrealized_pnl(rows)
    return rows


def test_live_trade_wins_over_last_close(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["closes"]["AAPL"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    [row] = _price([_held("AAPL")])
    assert row["current_price"] == 110.0 and row["price_kind"] == tp.PRICE_LIVE
    assert row["price_as_of"] == _AS_OF and "last_close" not in row
    assert row["status_label"] == "Trending toward target" and row["r_multiple"] == 1.0
    assert door["close_reads"] == [[]]


def test_bid_ask_only_quote_falls_back_to_prev_close_never_the_midpoint(door):
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    [row] = _price([_held("DOCU")])
    assert row["current_price"] == 95.0                      # the close, not (76.57 + 84.18) / 2
    assert row["price_kind"] == tp.PRICE_PREV_CLOSE
    assert row["price_as_of"] is None and row["price_age_s"] is None
    assert row["current_price_stale"] is False
    assert (row["price_error"], row["price_error_at"]) == ("no quote", _ERR_AT)
    assert row["last_close_date"] == "2026-11-24"
    assert (row["progress_band"], row["blink_seconds"]) == ("neutral", None)
    assert row["status_label"] == tp.PREV_CLOSE_LABEL and row["progress_pct"] == 16.7
    assert row["pnl_pct"] == -5.0 and row["r_multiple"] == -0.5


def test_held_row_with_neither_price_stays_unpriced_without_a_kind(door):
    [row] = _price([_held("NEWX")])
    assert row["current_price"] is None and "price_kind" not in row
    assert row["progress_pct"] is None and row["status_label"] == "No live price"
    assert row.get("pnl_pct") is None and row.get("r_multiple") is None


def test_partial_is_held_and_pending_is_not(door):
    for sym in ("PART", "PEND"):
        door["closes"][sym] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    part, pend = _price([_held("PART", status="PARTIAL"), _held("PEND", status="PENDING")])
    assert part["price_kind"] == tp.PRICE_PREV_CLOSE and part["current_price"] == 95.0
    assert "price_kind" not in pend and pend["current_price"] is None
    assert pend["last_close"] == 95.0 and pend["status_label"] == "PENDING"


def test_pricing_twice_is_idempotent_and_never_overwrites_a_live_price(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    rows = _price([_held("AAPL"), _held("DOCU")])
    once = copy.deepcopy(rows)
    _price(rows)                                             # list_trades' sort-by-price branch
    assert rows == once
    assert rows[0]["current_price"] == 110.0 and rows[0]["price_kind"] == tp.PRICE_LIVE


def test_prev_close_counts_as_missing_in_the_page_meta(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0)
    door["quotes"]["DOCU"] = _bid_ask_only("DOCU")
    door["closes"]["DOCU"] = {"last_close": 95.0, "last_close_date": "2026-11-24"}
    rows = _price([_held("AAPL"), _held("DOCU")])
    meta = trades_api._page_market_meta(rows)
    assert meta["missing_count"] == 1 and meta["incomplete"] is True
    assert meta["as_of"] == _AS_OF


def test_held_row_carries_the_full_quote_field_set(door):
    door["quotes"]["AAPL"] = _live("AAPL", 110.0, error="no quote", error_at=_ERR_AT)
    [row] = _price([_held("AAPL")])
    assert {"current_price", "current_price_stale", "price_as_of", "price_age_s",
            "price_refreshing", "price_error", "price_error_at", "price_kind"} <= set(row)
    assert row["price_error_at"] == _ERR_AT
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_quote_fields.py`
Expected: FAIL — `KeyError: 'price_kind'` in the live and prev-close tests, `current_price` None where 95.0 is expected, and `missing_count == 0` in the meta test. The existing detail-quote tests and the neither-price test still pass.

- [ ] **Step 3: Implement `_price_held_rows`, wire it, pass `price_kind` through**

In `swingbot/admin/api_v1/trades.py`:

1. Below `_attach_door_prices`, add:

```python
def _held_price_fields(row: dict) -> dict:
    """The price a held row shows (v248 spec § 2): the live trade, else the
    cached daily close tagged `prev_close`, never the bid/ask midpoint."""
    if row.get("current_price") is not None:
        return {"price_kind": trade_progress.PRICE_LIVE}
    close = row.get("last_close")
    if close is None:
        return {}
    return {"current_price": close, "price_kind": trade_progress.PRICE_PREV_CLOSE,
            "price_as_of": None, "price_age_s": None, "current_price_stale": False}


def _price_held_rows(live: list[dict]) -> None:
    """Give every held (ACTIVE/PARTIAL) door row a price and its `price_kind`.

    `price_as_of = None` on a prev-close row lets the client overlay upgrade it
    on any priced update. Idempotent: `list_trades` may price the same dicts
    twice, and the door's `quote_fields` resets `current_price` before this
    runs again, so a live price is never replaced by a close."""
    for row in live:
        if row.get("status") in _OPEN_STATUSES:
            row.pop("price_kind", None)
            row.update(_held_price_fields(row))
```

2. `_attach_door_prices`: after the `last_close` loop, call `_price_held_rows(live)`; extend its docstring by one sentence ("v248: held rows then always carry a price and its `price_kind`").

3. `_attach_status_fields`: read `kind = row.get("price_kind", trade_progress.PRICE_LIVE)` in the loop and pass `price_kind=kind` to both `_trailing_status_fields(...)` and `trade_progress.row_progress(...)`.

4. `_row_quote`: pass `None` as the price when `row.get("price_kind") == trade_progress.PRICE_PREV_CLOSE`, else `row.get("current_price")` as today (a small `_live_price(row) -> float | None` helper or an inline conditional; the function stays well below 15).

`_attach_unrealized_pnl` is **not** changed: it already computes `pnl_pct`, `r_multiple` and `realized_pnl_amount` from `current_price`, which is now the prev close on those rows.

- [ ] **Step 4: Run them to verify they pass, plus the door-path and API neighbours**

Run each:
- `python scripts/dev/testrun.py file tests/admin/test_api_quote_fields.py`
- `python scripts/dev/testrun.py file tests/admin/test_v248_progress_parity.py`
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`
- `python scripts/dev/testrun.py file tests/admin_market/test_trades_market.py` (the refresher-on list: `missing_count` and `prices_as_of` must be unchanged for an unpriced row)

Expected: each `0 failed`. Then `python scripts/dev/complexity_gate.py` — Expected: no new offender, `list_trades` unchanged.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_quote_fields.py
git commit -m "feat(v248): held rows priced from the prev close with a neutral bar when no live trade exists"
```
