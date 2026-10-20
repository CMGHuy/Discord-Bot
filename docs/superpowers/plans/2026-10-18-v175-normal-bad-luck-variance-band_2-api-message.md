# v175 Normal bad luck, part 2: API route, book-status message, zone latch and scan hook

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V175-6:" -A 300 docs/superpowers/plans/2026-10-18-v175-normal-bad-luck-variance-band_2-api-message.md`.

**Spec:** [`docs/superpowers/specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md`](../specs/2026-10-18-v175-normal-bad-luck-variance-band-design.md)
**Index:** [`2026-10-18-v175-normal-bad-luck-variance-band_0-index.md`](2026-10-18-v175-normal-bad-luck-variance-band_0-index.md) — Global Constraints, Parallelisation, Task ledger and `$WT`/`$R` live there and bind every task below.

`$SCRATCH` below is the implementing session's scratchpad directory (absolute path, from the session's environment). Commit messages are written to a file there and passed with `git commit -F`, and the V175-6 render script lives there; nothing in `$SCRATCH` is committed.

Tasks: V175-5 (`GET /api/v1/analytics/variance-band`), V175-6 (`Family.BOOK`, `Kind.BOOK_STATUS`, the book-status line), V175-7 (zone latch `post_book_status` and the one-line scan hook).

Consumed from part 1 (`swingbot/core/analytics/variance_band.py`, created by V175-1..V175-3): `variance_band(closed, *, paths=PATHS, outer=OUTER_RESAMPLES, outer_paths=OUTER_PATHS) -> Band`, `ZONES`, `CAVEAT`, `WINDOW`. Nothing else of that module is used here.

**Database rule for this part.** No test written here seeds a store or opens a database: the API test monkeypatches `analytics._closed_book` (and `_all_trades` for the loader's own test), the bot tests monkeypatch `book_status._closed_book` and `book_status.scheduled_repo`. The admin `client`/`admin_app` fixtures are the existing harness (they seed the account row into the per-worker *test* database, never the production replica); they are used as every other admin route test uses them.

# Phase B: API and book-status message (V175-5..V175-7)

### Task V175-5: `GET /api/v1/analytics/variance-band`

**Model:** sonnet — an admin endpoint over `variance_band`, following the module's existing route pattern.

**Files:**
- Modify: `swingbot/admin/api_v1/analytics.py` (new seam `_closed_book` and route `analytics_variance_band`, inserted right after `analytics_calibration`, today at lines 716-728)
- Create: `tests/admin/test_api_v1_analytics_variance_band.py`

**Interfaces:**
- Consumes (V175-3): `swingbot.core.analytics.variance_band.variance_band(closed: list[dict], *, paths: int = PATHS, outer: int = OUTER_RESAMPLES, outer_paths: int = OUTER_PATHS) -> Band`; the `Band` shape of Global Constraints (`status`, `scope`, `asof`, `days`, `weeks`, `pool`, `composition`, `horizons`, `current`, `expr`, optional `dollars`; insufficient = exactly `status`, `scope`, `days`, `weeks`).
- Consumes (existing): `analytics._all_trades(tl: TradeLog) -> list[dict]` (analytics.py:84), `scope.closed_only(trades) -> list[dict]` (scope.py:81), `ApiError(code, message, status)`, `require_auth`.
- Produces: seam `_closed_book() -> list[dict]` in `swingbot/admin/api_v1/analytics.py`; route `analytics_variance_band()` at `GET /api/v1/analytics/variance-band`, body = `Band` (consumed by V175-8's `ApiClient.analyticsVarianceBand`, checked live in V175-11 and V175-14).

**Why this shape.** The band is whole-book by design (spec §2): no `BookScope`, no `select()`, every ledger. The route only loads and forwards; all computation is in the pure module ("UI renders, analytics computes", this module's docstring). It is computed on request, not cached in the snapshot, so the ExpR beside it is re-derived on every call (`pooled-numbers`). Any query parameter is rejected rather than silently ignored, so a client that sends the Analytics scope bar's filters gets a 400 instead of a whole-book answer it would read as filtered.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_analytics_variance_band.py`:

```python
"""v175: GET /api/v1/analytics/variance-band -- the whole-book losing-run band.

No store is seeded and no database is read: `_closed_book` (and, for the
loader's own test, `_all_trades`) is monkeypatched. The band is the real
`variance_band`, run with fewer paths so the shape test stays fast; the
statistics themselves are tested in tests/analytics/test_variance_band_*.py.
"""
import datetime as dt
import functools

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, NUMBER, assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/variance-band"
_R_CYCLE = (1.5, -1.0, -1.0, 2.0, -1.0, 0.5)     # R per close day, repeated
_NULLABLE_INT = (int, type(None))

_FULL_KEYS = {"status", "scope", "asof", "days", "weeks", "pool", "composition",
              "horizons", "current", "expr"}
_CURRENT = {"run": int, "run_age_days": _NULLABLE_INT, "drawdown": NUMBER,
            "drawdown_age_days": _NULLABLE_INT, "run_zone": str, "drawdown_zone": str,
            "zone": str}
_EXPR = {"value": NULLABLE_NUMBER, "n": int, "start": NULLABLE_STR, "end": NULLABLE_STR,
         "ci": (list, type(None)), "not_positive": bool}
_HORIZON = {"horizon": int, "weeks_span": NUMBER, "run": dict, "drawdown": dict}
_RUN_Q = {"p80": int, "p95": int, "p95_lo": int, "p95_hi": int}
_DD_Q = {"p80": NUMBER, "p95": NUMBER, "p95_lo": NUMBER, "p95_hi": NUMBER}


def _trade(i: int, day: dt.date, r: float, *, shares=10.0, plan_id="p", status=None):
    """One closed bullish trade, entry 100 / stop 95 (risk 5), closing at
    15:00 UTC (11:00 New York), so its ET close date is `day`."""
    return {
        "id": f"t{i}", "ticker": "AAPL", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 100.0 + 5.0 * r,
        "status": status or ("win" if r > 0 else "loss"),
        "closed_at": f"{day.isoformat()}T15:00:00+00:00",
        "plan_id": f"{plan_id}{i}" if plan_id else None,
        "shares": shares, "horizon_key": "4w", "ledger": "main",
    }


def _book(days: int = 130, *, shares=10.0) -> list[dict]:
    """One trade per weekday from Mon 2026-01-05: 130 days = 26 ISO weeks."""
    out, day = [], dt.date(2026, 1, 5)
    while len(out) < days:
        if day.weekday() < 5:
            out.append(_trade(len(out), day, _R_CYCLE[len(out) % len(_R_CYCLE)], shares=shares))
        day += dt.timedelta(days=1)
    return out


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def book(monkeypatch):
    """Serve `trades` as the closed book, through a fast real `variance_band`."""
    import swingbot.admin.api_v1.analytics as analytics_api
    from swingbot.core.analytics import variance_band as vb

    fast = functools.partial(vb.variance_band, paths=500, outer=20, outer_paths=200)
    monkeypatch.setattr(vb, "variance_band", fast)

    def _serve(trades):
        monkeypatch.setattr(analytics_api, "_closed_book", lambda: list(trades))
    return _serve


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_any_query_parameter_is_rejected(logged_in, book):
    book(_book())
    assert_error(logged_in.get(_URL + "?strategy=RSI"), "invalid", 400)
    body = logged_in.get(_URL + "?ledger=main").get_json()
    assert "unknown parameter 'ledger'; allowed: []" in str(body)


def test_full_band_shape_is_whole_book(logged_in, book):
    book(_book())
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == _FULL_KEYS | {"dollars"}
    assert body["status"] == "ok" and body["scope"] == "whole_book"
    assert body["pool"] == "v2"
    assert body["days"] == 130 and body["weeks"] == 26
    assert [h["horizon"] for h in body["horizons"]] == [20, 50]
    for i, entry in enumerate(body["horizons"]):
        assert_shape(entry, _HORIZON, where=f"horizons[{i}]")
        assert_shape(entry["run"], _RUN_Q, where=f"horizons[{i}].run")
        assert_shape(entry["drawdown"], _DD_Q, where=f"horizons[{i}].drawdown")
    assert_shape(body["current"], _CURRENT, where="current")
    assert body["current"]["zone"] in ("normal", "rough", "outside")
    assert_shape(body["expr"], _EXPR, where="expr")
    assert body["expr"]["n"] == 130
    assert_shape(body["dollars"], {"median_risk": NUMBER, "drawdown_usd": NUMBER}, where="dollars")
    assert body["dollars"]["median_risk"] == 50.0          # 10 shares x |100 - 95|
    assert set(body["composition"]) == {"days_by_era", "trades_by_horizon"}
    assert body["composition"]["days_by_era"] == {"v2": 130, "legacy": 0}


def test_dollars_key_is_omitted_when_no_trade_has_shares(logged_in, book):
    book(_book(shares=None))
    body = logged_in.get(_URL).get_json()
    assert body["status"] == "ok"
    assert "dollars" not in body
    assert set(body) == _FULL_KEYS


def test_small_book_is_insufficient_with_exact_shape(logged_in, book):
    book([_trade(i, dt.date(2026, 1, 5 + i), -1.0) for i in range(3)])
    body = logged_in.get(_URL).get_json()
    assert body == {"status": "insufficient", "scope": "whole_book", "days": 3, "weeks": 1}


def test_empty_book_is_insufficient_not_an_error(logged_in, book):
    book([])
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "insufficient", "scope": "whole_book", "days": 0, "weeks": 0}


def test_closed_book_keeps_every_ledger_and_drops_open_trades(monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    day = dt.date(2026, 1, 5)
    rows = [dict(_trade(0, day, 1.0), ledger="main"),
            dict(_trade(1, day, -1.0), ledger="weak"),
            dict(_trade(2, day, 0.0, status="closed"), ledger="main"),
            dict(_trade(3, day, 0.0), status="open", closed_at=None)]
    seen = {}

    def fake_all_trades(tl):
        seen["called"] = True
        return rows

    monkeypatch.setattr(analytics_api, "_all_trades", fake_all_trades)
    monkeypatch.setattr(analytics_api, "TradeLog", lambda: object())
    closed = analytics_api._closed_book()
    assert seen == {"called": True}
    assert [t["id"] for t in closed] == ["t0", "t1", "t2"]
```

If `test_full_band_shape_is_whole_book` disagrees with part 1 on a value this fixture pins (`days`, `weeks`, `pool`, `expr.n`, `median_risk`, `days_by_era`), part 1's Global Constraints are the authority: re-check the fixture arithmetic first (130 weekdays from Mon 2026-01-05 = 26 ISO weeks; every trade has a `plan_id`, so the pool is `v2`), and report a real mismatch to the controller instead of loosening the assertion.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_variance_band.py`
Expected: FAIL. `test_requires_auth` gets a 404 instead of a 401, and every test using the `book` fixture or `_closed_book` fails with `AttributeError: ... has no attribute '_closed_book'` (monkeypatching a missing attribute raises).

- [ ] **Step 3: Implement the seam and the route**

In `swingbot/admin/api_v1/analytics.py`, insert directly after the `analytics_calibration` function (before `@api_v1.route("/analytics/registry", ...)`):

```python
def _closed_book() -> list[dict]:
    """v175: the whole closed book -- every ledger, no BookScope.

    The variance band is whole-book by design (it does not follow the
    Analytics scope bar), so this deliberately skips `_scope()`/`select()`.
    A seam: tests monkeypatch it instead of seeding a store."""
    from swingbot.core.analytics.scope import closed_only

    return closed_only(_all_trades(TradeLog()))


@api_v1.route("/analytics/variance-band", methods=["GET"])
@require_auth
def analytics_variance_band():
    """v175: the range of losing-day runs and drawdowns this book's own closed
    trades produce by chance, and where the book sits now against it.

    Computed on request (no snapshot) so the ExpR beside the band is
    re-derived every call. Takes no parameters: a scope filter would be a
    lie here, so any parameter is a 400, never silently ignored."""
    from swingbot.core.analytics import variance_band as vb

    if request.args:
        raise ApiError("invalid", f"unknown parameter {sorted(request.args)[0]!r}; allowed: []", 400)
    return jsonify(vb.variance_band(_closed_book()))
```

Notes for the implementer:
- `vb.variance_band` is looked up on the module at call time (not `from ... import variance_band`), so the test's `monkeypatch.setattr(vb, "variance_band", fast)` takes effect.
- `TradeLog`, `request`, `jsonify`, `ApiError` and `require_auth` are already imported at module top (analytics.py:21-28); add no top-level import.
- Do **not** add the URL to `_PATHS` in `tests/admin/test_api_v1_analytics.py`: that file is outside this task, and the empty-book case is covered here.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_variance_band.py`
Expected: PASS, 7 passed, 0 failed.

Then the module's existing route tests, unchanged:
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/admin/api_v1/analytics.py`
Expected: no line for `_closed_book` or `analytics_variance_band` (both rank A).

- [ ] **Step 6: Commit**

Write the message to a file in the session scratchpad (`$SCRATCH/v175-5-msg.txt`), then commit with `-F`:

```text
feat(admin): GET /api/v1/analytics/variance-band -- whole-book losing-run band (v175)

Computed on request over every ledger's closed trades, no BookScope; any
query parameter is a 400. The `_closed_book` seam keeps the test off the
database.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add swingbot/admin/api_v1/analytics.py tests/admin/test_api_v1_analytics_variance_band.py
git -C $WT commit -F "$SCRATCH/v175-5-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch; the main tree shows no change from this task.

### Task V175-6: `Family.BOOK`, `Kind.BOOK_STATUS` and the book-status line

**Model:** sonnet — a registry entry and a pure copy builder, rendered once per the alert-surface gate.

**Files:**
- Modify: `swingbot/core/presentation/kinds.py` (colour constant near the other stripe colours, lines 23-40; `Family.BOOK` after `SYSTEM` in `Family`, line 79; `Kind.BOOK_STATUS` after `OUTLOOK_WRAPUP`, line 145)
- Modify: `tests/presentation/test_kinds.py` (one new test appended)
- Create: `swingbot/commands/scanning/book_status.py`
- Create: `tests/commands/test_book_status_text.py`

**Interfaces:**
- Consumes (V175-1): `swingbot.core.analytics.variance_band.CAVEAT` (the verbatim caveat string of Global Constraints). Nothing else from part 1; this task can run alongside V175-2..V175-4.
- Consumes (existing): `notices.system_embed(kind, detail="", description=None) -> PushEmbed` (notices.py:29), `tokens.fmt_money(amount, currency) -> str` (tokens.py:109, always signed: `"+$312.34"`), `kinds.title`, `kinds.content_line`, `kinds.stripe`, `kinds.footer`.
- Produces:
  - `kinds.BOOK_INDIGO = 0x6366F1`; `Family.BOOK = FamilySpec("📉", "BOOK", BOOK_INDIGO)`; `Kind.BOOK_STATUS = KindSpec(Family.BOOK, "BOOK STATUS")` (FIXED rule, no emoji override, no colour override, no disclaimer).
  - In `swingbot/commands/scanning/book_status.py`: `ZONE_PHRASE: dict[str, str]` (keys `"rough"`, `"outside"`); `book_status_text(band: dict, currency: str) -> str | None`; `book_status_embed(band: dict, currency: str) -> PushEmbed | None`. V175-7 adds the latch to this same file.

**The copy, exactly.** The embed title is the registry's `📉 BOOK STATUS`, which already carries the badge, so the description is the spec's line without its leading `📉 `:

| zone | description |
|---|---|
| rough | `Book: {k} losing days in a row / {dd}R{usd} down over 50 close days, deeper than 80% of simulated runs, within 95%. Closed trades only.` |
| outside | `Book: {k} losing days in a row / {dd}R{usd} down over 50 close days, beyond 95% of simulated runs. Closed trades only.` |

`{k}` = `current.run`; `{dd}` = `f"{current.drawdown:.1f}"`; `{usd}` = `" (≈ $312.34)"` when `dollars` is present, else `""`; `" " + CAVEAT` is appended when `expr.not_positive`. `normal`, `insufficient`, or any other status gives `None` (nothing to post).

**Why the sign is stripped.** `fmt_money` always prints a sign (`+$312.34`), which would render `(≈ +$312.34) down`, contradicting the spec's `(≈ ${x})`. The helper below still uses `fmt_money` (one money format, thousands separator, two decimals) and strips its sign: `$312.34`, `$1,234.50`. The test pins the spec's form.

- [ ] **Step 1: Load the alert-surface gate**

Invoke the `alert-surface` skill and do its Step 1 (the `doc_section.py docs/claude/known-traps.md ...` read). This task adds a new message kind and touches neither `embeds.py` nor `engine.py`, so the gate that applies is the rendered output: Step 7 below renders the message once and its output goes into the task report.

- [ ] **Step 2: Write the failing tests**

Append to `tests/presentation/test_kinds.py`:

```python
def test_book_status_is_its_own_family_without_an_outcome_mark():
    """v175: the book-status message is not SYSTEM health and not a RESULT."""
    assert Kind.BOOK_STATUS.family is Family.BOOK
    assert kinds.BOOK_INDIGO == 0x6366F1
    assert kinds.title(Kind.BOOK_STATUS, "") == "📉 BOOK STATUS"
    assert kinds.content_line(Kind.BOOK_STATUS, "") == "📉 BOOK · BOOK STATUS"
    assert kinds.stripe(Kind.BOOK_STATUS, level=5, r=-3.0) == kinds.BOOK_INDIGO
    assert kinds.footer(Kind.BOOK_STATUS) == "BOOK"
    assert Kind.BOOK_STATUS.disclaimer is False
    marks = set("".join(kinds.OUTCOME_MARKS.values())) - {"️"}
    assert not set(kinds.title(Kind.BOOK_STATUS, "")) & marks
```

The registry-wide tests already in that file (`test_every_family_is_used`, `test_badge_and_label_pairs_are_unique`, `test_only_new_setup_kinds_carry_the_disclaimer`, `test_no_stripe_colour_is_shared_across_families`, `test_family_badges_never_double_as_outcome_or_direction_marks`, the parametrised title/content-line tests) cover the new family and kind with no edit.

Create `tests/commands/test_book_status_text.py`:

```python
"""v175: the book-status line and its embed -- pure, no store, no channel."""
import re

import pytest

from swingbot.commands.scanning import book_status
from swingbot.core.analytics import variance_band as vb
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

_CAVEAT = "This book's past results are not positive. A run within their range is still a losing run."
_FORBIDDEN = re.compile(r"\b(edge|stop|check|skip|size|review)\b", re.IGNORECASE)


def _band(zone="rough", *, run=4, drawdown=3.24, usd=312.34, not_positive=False):
    band = {
        "status": "ok", "scope": "whole_book", "asof": "2026-10-16", "days": 140, "weeks": 30,
        "pool": "v2",
        "composition": {"days_by_era": {"v2": 140, "legacy": 0}, "trades_by_horizon": {"4w": 180}},
        "horizons": [],
        "current": {"run": run, "run_age_days": 6, "drawdown": drawdown, "drawdown_age_days": 12,
                    "run_zone": zone, "drawdown_zone": "normal", "zone": zone},
        "expr": {"value": 0.21, "n": 180, "start": "2026-03-02", "end": "2026-10-16",
                 "ci": [0.05, 0.37], "not_positive": not_positive},
    }
    if usd is not None:
        band["dollars"] = {"median_risk": 96.4, "drawdown_usd": usd}
    return band


def test_rough_line_is_verbatim_with_dollars():
    assert book_status.book_status_text(_band("rough"), "$") == (
        "Book: 4 losing days in a row / 3.2R (≈ $312.34) down over 50 close days, "
        "deeper than 80% of simulated runs, within 95%. Closed trades only.")


def test_outside_line_is_verbatim_without_dollars():
    band = _band("outside", run=7, drawdown=6.0, usd=None)
    assert book_status.book_status_text(band, "$") == (
        "Book: 7 losing days in a row / 6.0R down over 50 close days, "
        "beyond 95% of simulated runs. Closed trades only.")


def test_dollars_are_unsigned_with_a_thousands_separator():
    text = book_status.book_status_text(_band("outside", usd=1234.5), "€")
    assert "(≈ €1,234.50) down" in text
    assert "+" not in text


def test_caveat_is_appended_only_when_expr_is_not_positive():
    assert book_status.book_status_text(_band(not_positive=False), "$").endswith("Closed trades only.")
    text = book_status.book_status_text(_band(not_positive=True), "$")
    assert text.endswith("Closed trades only. " + _CAVEAT)
    assert vb.CAVEAT == _CAVEAT


@pytest.mark.parametrize("band", [
    _band("normal"),
    {"status": "insufficient", "scope": "whole_book", "days": 40, "weeks": 9},
    {"status": "ok", "current": {"zone": "unknown"}},
])
def test_nothing_to_post_unless_the_zone_is_rough_or_outside(band):
    assert book_status.book_status_text(band, "$") is None
    assert book_status.book_status_embed(band, "$") is None


@pytest.mark.parametrize("zone", ["rough", "outside"])
@pytest.mark.parametrize("not_positive", [False, True])
@pytest.mark.parametrize("usd", [None, 312.34])
def test_copy_has_no_instruction_verb_and_never_says_edge(zone, not_positive, usd):
    text = book_status.book_status_text(_band(zone, not_positive=not_positive, usd=usd), "$")
    assert _FORBIDDEN.search(text) is None, text


def test_zone_phrases_cover_exactly_the_posting_zones():
    assert set(book_status.ZONE_PHRASE) == {"rough", "outside"}


def test_embed_is_a_book_status_push():
    band = _band("rough")
    embed = book_status.book_status_embed(band, "$")
    assert embed.title == "📉 BOOK STATUS"
    assert embed.push_text == "📉 BOOK · BOOK STATUS"
    assert embed.description == book_status.book_status_text(band, "$")
    assert embed.color.value == kinds.BOOK_INDIGO
    assert embed.footer.text == "BOOK"
    assert embed.timestamp is not None
    assert embed.kind is Kind.BOOK_STATUS
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_kinds.py`
Expected: FAIL on `test_book_status_is_its_own_family_without_an_outcome_mark` with `AttributeError: BOOK_STATUS`.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_book_status_text.py`
Expected: FAIL at collection with `ImportError: cannot import name 'book_status'`.

- [ ] **Step 4: Add the family and the kind**

In `swingbot/core/presentation/kinds.py`, after `HEALTH_GREEN = 0x34D399` (line 40):

```python
BOOK_INDIGO = 0x6366F1  # v175: the whole book's losing-run zone, its own family
```

In `class Family(Enum)`, after `SYSTEM = FamilySpec("🩺", "SYSTEM", SYSTEM_SLATE)`:

```python
    BOOK = FamilySpec("📉", "BOOK", BOOK_INDIGO)
```

In `class Kind(Enum)`, after `OUTLOOK_WRAPUP = ...` (the last member, before the `@property` block):

```python
    # BOOK -- v175: one line when the closed book's losing-run zone rises into
    # rough or outside. No outcome mark, no disclaimer, never on a plan embed.
    BOOK_STATUS = KindSpec(Family.BOOK, "BOOK STATUS")
```

Also extend the module docstring's first paragraph by one sentence so the registry stays self-describing: after "...is one Kind (the specific event)." add `v175 adds BOOK, the closed book's losing-run status.`

- [ ] **Step 5: Create the text builder**

Create `swingbot/commands/scanning/book_status.py`:

```python
"""v175: the book-status message -- one line in the alerts channel when the
whole closed book's losing-run zone rises into rough or outside.

This half is pure: it turns a variance band (swingbot/core/analytics/
variance_band.py) into the message text and its BOOK_STATUS embed. The copy
describes and never instructs: no "edge", no stop/check/skip/size/review.
Plan embeds are untouched; this is its own message.
"""
from __future__ import annotations

from swingbot.core.analytics import variance_band as vb
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Kind

from . import notices

#: The zone sentence of the message, per posting zone. `normal` posts nothing.
ZONE_PHRASE: dict[str, str] = {
    "rough": "deeper than 80% of simulated runs, within 95%",
    "outside": "beyond 95% of simulated runs",
}


def _usd(band: dict, currency: str) -> str:
    """' (≈ $312.34)' beside the drawdown, or '' when the band has no dollars.

    fmt_money always signs its figure; a drawdown is already worded as
    "down", so the sign is dropped."""
    dollars = band.get("dollars")
    if not dollars:
        return ""
    money = tokens.fmt_money(abs(dollars["drawdown_usd"]), currency).lstrip("+")
    return f" (≈ {money})"


def book_status_text(band: dict, currency: str) -> str | None:
    """The message line, or None when there is nothing to post (insufficient
    band, or a zone other than rough/outside)."""
    if band.get("status") != "ok":
        return None
    current = band["current"]
    phrase = ZONE_PHRASE.get(current.get("zone"))
    if phrase is None:
        return None
    line = (f"Book: {current['run']} losing days in a row / {current['drawdown']:.1f}R"
            f"{_usd(band, currency)} down over 50 close days, {phrase}. Closed trades only.")
    if band["expr"]["not_positive"]:
        line = f"{line} {vb.CAVEAT}"
    return line


def book_status_embed(band: dict, currency: str):
    """The BOOK_STATUS push embed for `band`, or None when nothing posts."""
    text = book_status_text(band, currency)
    if text is None:
        return None
    return notices.system_embed(Kind.BOOK_STATUS, description=text)
```

(`notices.system_embed` is named for SYSTEM notices but is kind-generic: registry title, push line, stripe and footer all come from the kind. Reusing it keeps one chrome path.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/presentation/test_kinds.py`
Expected: PASS, 0 failed (the registry-wide invariants included).

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_book_status_text.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_system_notices.py`
Expected: PASS, 0 failed (SYSTEM notices unchanged).

- [ ] **Step 7: Render the message once (the alert-surface gate)**

Create `$SCRATCH/render_book_status.py`:

```python
"""Render the v175 book-status embed for the task report. Usage:
python render_book_status.py <worktree path>"""
import sys

sys.path.insert(0, sys.argv[1])

from swingbot.commands.scanning import book_status  # noqa: E402


def band(zone, *, usd, not_positive):
    out = {"status": "ok",
           "current": {"run": 4 if zone == "rough" else 7, "drawdown": 3.24 if zone == "rough" else 6.02,
                       "zone": zone},
           "expr": {"not_positive": not_positive}}
    if usd is not None:
        out["dollars"] = {"median_risk": 96.4, "drawdown_usd": usd}
    return out


for zone, usd, not_positive in (("rough", 312.34, False), ("outside", 580.33, True),
                                ("outside", None, False)):
    embed = book_status.book_status_embed(band(zone, usd=usd, not_positive=not_positive), "$")
    print("content    :", embed.push_text)
    print("title      :", embed.title)
    print("description:", embed.description)
    print("stripe     :", hex(embed.color.value), "| footer:", embed.footer.text)
    print()
```

Run: `python "$SCRATCH/render_book_status.py" "$WT"`
Expected: three blocks; each `content` is `📉 BOOK · BOOK STATUS`, each `title` is `📉 BOOK STATUS`, the stripe is `0x6366f1`, the footer `BOOK`, and the descriptions read exactly as the copy table above (the second ends with the caveat, the third has no `(≈ …)`). Paste the output into the task report: it is the before/after the `alert-surface` gate asks for (before = no such message).

- [ ] **Step 8: Plan embeds are untouched**

Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embed_plan_link.py`
Expected: each PASS, 0 failed, with no edit to any of them (`git -C $WT diff --stat main -- tests/scanning` prints nothing).

- [ ] **Step 9: Complexity**

Run: `python -m radon cc -s -n C $WT/swingbot/commands/scanning/book_status.py $WT/swingbot/core/presentation/kinds.py`
Expected: no output.

- [ ] **Step 10: Commit**

Write `$SCRATCH/v175-6-msg.txt`:

```text
feat(bot): BOOK family and BOOK_STATUS kind, book-status message text (v175)

📉 BOOK STATUS, indigo stripe 0x6366F1, no outcome mark, no disclaimer.
The line states the losing-day run and the 50-close-day drawdown against
the simulated band, with the not-positive caveat when it applies. Pure:
no store, no channel.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add swingbot/core/presentation/kinds.py tests/presentation/test_kinds.py swingbot/commands/scanning/book_status.py tests/commands/test_book_status_text.py
git -C $WT commit -F "$SCRATCH/v175-6-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch; the main tree shows no change from this task.

### Task V175-7: Zone latch `post_book_status` and the one-line scan hook

**Model:** sonnet — async helper with a latch, one added call in a cc-15 function.

**Files:**
- Modify: `swingbot/commands/scanning/book_status.py` (created by V175-6; the latch half is appended)
- Modify: `swingbot/commands/scanning/loops.py` (line 24, the `from . import ...` line; line 240, one added line after `await ops_watch.check_provider_health()`)
- Create: `tests/commands/test_book_status_latch.py`

**Interfaces:**
- Consumes (V175-3): `variance_band.variance_band(closed: list[dict]) -> Band`, `variance_band.ZONES == ("normal", "rough", "outside")`.
- Consumes (V175-6): `book_status.book_status_embed(band: dict, currency: str) -> PushEmbed | None`.
- Consumes (existing): `scheduled_repo().fired_on(job) -> str | None` / `.mark(job, value)` (repositories/scheduled.py:12-17; `fired_on` is `sa.Text`, so a zone string needs no migration), `notices.send_guarded(channel, embed, *, what) -> Message | None` (notices.py:36; swallows send failures and returns None), `swallowed(log, tag, exc, msg="", *args, level=..., exc_info=...)` (infra/swallowed.py:62), `config.CURRENCY_SYMBOL`.
- Produces (all in `swingbot/commands/scanning/book_status.py`): `ZONE_JOB = "variance_band:zone"`; `_closed_book() -> list[dict]`; `stored_zone() -> str`; `next_action(stored: str, zone: str) -> str` (`"post"` | `"reset"` | `"none"`); `async post_book_status(channel) -> bool` (True only when a message posted). V175-14 checks the hook live.

**Latch rules (Global Constraints, restated so the tests can be read against them).** Compute the band once per scan tick, off the event loop. `insufficient` → nothing: no post, no store write. Otherwise compare the band's overall `current.zone` with the stored zone (missing or unknown reads as `normal`), ranked by `ZONES`:

| stored → band zone | action | store write |
|---|---|---|
| rise (normal→rough, normal→outside, rough→outside) | post via `send_guarded` | the new zone, **only** if the send returned a message |
| same | nothing | none |
| fall (outside→rough, outside→normal, rough→normal) | nothing posted | the lower zone |

A failed send leaves the stored zone where it was, so the next tick tries again. A fall re-arms: the next rise posts again. `post_book_status` never raises; any exception is counted under the tag `scan.book_status`.

**Why the hook adds no branch.** `_session_scan_tick` is at radon complexity 15 today (`F 187:0 _session_scan_tick - C (15)`); a legacy function at or above 15 must not get worse (`code-complexity.md`). The hook is one unconditional `await`; every condition lives in `book_status`. It runs after the scan and after `check_provider_health()`, so it fires once per real scan tick (the paused/off-session/no-channel early returns come earlier) with the already-silenced alerts `channel`.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_book_status_latch.py`:

```python
"""v175: the book-status zone latch and its one-line scan hook.

No database: `book_status.scheduled_repo` is a dict-backed fake and
`book_status._closed_book` is monkeypatched. The band is a fixture dict
(`vb.variance_band` patched), except in the one test that runs the real
function on a tiny, insufficient book.
"""
import asyncio
import datetime as dt
import inspect
import threading
import types

import pytest

from swingbot.commands.scanning import book_status
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.analytics import variance_band as vb
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.presentation.kinds import Kind


class _Repo:
    """scheduled_repo() stand-in: fired_on/mark over a dict, marks recorded."""

    def __init__(self, stored=None):
        self.rows = {} if stored is None else {book_status.ZONE_JOB: stored}
        self.marks = []

    def fired_on(self, job):
        return self.rows.get(job)

    def mark(self, job, value):
        self.rows[job] = value
        self.marks.append((job, value))


class _Chan:
    def __init__(self, *, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=len(self.sent))     # a discord.Message stand-in


def _band(zone="rough"):
    return {
        "status": "ok", "scope": "whole_book", "asof": "2026-10-16", "days": 140, "weeks": 30,
        "pool": "v2",
        "composition": {"days_by_era": {"v2": 140, "legacy": 0}, "trades_by_horizon": {"4w": 180}},
        "horizons": [],
        "current": {"run": 5, "run_age_days": 8, "drawdown": 4.1, "drawdown_age_days": 15,
                    "run_zone": zone, "drawdown_zone": "normal", "zone": zone},
        "expr": {"value": 0.21, "n": 180, "start": "2026-03-02", "end": "2026-10-16",
                 "ci": [0.05, 0.37], "not_positive": False},
        "dollars": {"median_risk": 96.4, "drawdown_usd": 395.24},
    }


_INSUFFICIENT = {"status": "insufficient", "scope": "whole_book", "days": 40, "weeks": 9}


@pytest.fixture
def wire(monkeypatch):
    """Fake the store and the band; returns (repo, state). Set state["band"]
    between calls to move the book's zone."""
    def _wire(*, stored=None, band=None):
        repo = _Repo(stored)
        state = {"band": band if band is not None else _band(), "main_thread": None}

        def fake_band(closed):
            state["main_thread"] = threading.current_thread() is threading.main_thread()
            band_now = state["band"]
            if isinstance(band_now, Exception):
                raise band_now
            return band_now

        monkeypatch.setattr(book_status, "scheduled_repo", lambda: repo)
        monkeypatch.setattr(book_status, "_closed_book", lambda: [])
        monkeypatch.setattr(vb, "variance_band", fake_band)
        return repo, state
    return _wire


def _post(chan):
    return asyncio.run(book_status.post_book_status(chan))


@pytest.mark.parametrize("stored,zone,action", [
    ("normal", "rough", "post"), ("normal", "outside", "post"), ("rough", "outside", "post"),
    ("normal", "normal", "none"), ("rough", "rough", "none"), ("outside", "outside", "none"),
    ("outside", "rough", "reset"), ("outside", "normal", "reset"), ("rough", "normal", "reset"),
])
def test_next_action_ranks_zones(stored, zone, action):
    assert book_status.next_action(stored, zone) == action


@pytest.mark.parametrize("value,expected", [
    (None, "normal"), ("2026-10-01", "normal"), ("cleared", "normal"),
    ("normal", "normal"), ("rough", "rough"), ("outside", "outside"),
])
def test_stored_zone_reads_missing_or_unknown_as_normal(monkeypatch, value, expected):
    monkeypatch.setattr(book_status, "scheduled_repo", lambda: _Repo(value))
    assert book_status.stored_zone() == expected


def test_zone_job_key():
    assert book_status.ZONE_JOB == "variance_band:zone"


@pytest.mark.parametrize("stored,zone", [
    (None, "rough"), ("normal", "rough"), ("normal", "outside"), ("rough", "outside"),
])
def test_a_rise_posts_one_book_status_and_stores_the_zone(wire, stored, zone):
    repo, _ = wire(stored=stored, band=_band(zone))
    chan = _Chan()
    assert _post(chan) is True
    assert len(chan.sent) == 1
    embed = chan.sent[0]["embed"]
    assert embed.kind is Kind.BOOK_STATUS
    assert chan.sent[0]["content"] == "📉 BOOK · BOOK STATUS"
    assert repo.rows[book_status.ZONE_JOB] == zone
    assert repo.marks == [(book_status.ZONE_JOB, zone)]


@pytest.mark.parametrize("zone", ["normal", "rough", "outside"])
def test_the_same_zone_again_is_silent_and_writes_nothing(wire, zone):
    repo, _ = wire(stored=zone, band=_band(zone))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_a_fall_stores_the_lower_zone_and_posts_nothing_then_a_rise_posts_again(wire):
    repo, state = wire(stored="outside", band=_band("normal"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == []
    assert repo.rows[book_status.ZONE_JOB] == "normal"

    state["band"] = _band("rough")
    assert _post(chan) is True
    assert len(chan.sent) == 1
    assert repo.rows[book_status.ZONE_JOB] == "rough"

    assert _post(chan) is False                  # still rough: silent
    assert len(chan.sent) == 1


def test_outside_falling_to_rough_is_silent(wire):
    repo, _ = wire(stored="outside", band=_band("rough"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == []
    assert repo.marks == [(book_status.ZONE_JOB, "rough")]


def test_a_failed_send_stores_nothing_so_the_next_tick_retries(wire):
    repo, _ = wire(stored="normal", band=_band("rough"))
    assert _post(_Chan(fail=True)) is False
    assert repo.marks == []
    assert repo.rows[book_status.ZONE_JOB] == "normal"

    chan = _Chan()
    assert _post(chan) is True
    assert len(chan.sent) == 1
    assert repo.rows[book_status.ZONE_JOB] == "rough"


@pytest.mark.parametrize("stored", [None, "normal", "rough", "outside"])
def test_an_insufficient_band_posts_nothing_and_writes_nothing(wire, stored):
    repo, _ = wire(stored=stored, band=dict(_INSUFFICIENT))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_the_band_is_computed_off_the_event_loop(wire):
    _, state = wire(stored="normal", band=_band("normal"))
    _post(_Chan())
    assert state["main_thread"] is False


def test_an_exception_is_counted_and_never_raised(wire):
    swallowed_mod.reset()
    repo, _ = wire(stored="normal", band=RuntimeError("bootstrap exploded"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []
    assert swallowed_mod.snapshot()["scan.book_status"]["count"] == 1
    swallowed_mod.reset()


def test_the_real_band_on_a_tiny_book_is_insufficient_and_silent(monkeypatch):
    repo = _Repo("outside")
    day = dt.date(2026, 1, 5)
    trades = [{"id": f"t{i}", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
               "exit_price": 95.0, "status": "loss", "plan_id": f"p{i}", "shares": 10.0,
               "closed_at": f"{(day + dt.timedelta(days=i)).isoformat()}T15:00:00+00:00"}
              for i in range(3)]
    monkeypatch.setattr(book_status, "scheduled_repo", lambda: repo)
    monkeypatch.setattr(book_status, "_closed_book", lambda: trades)
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_closed_book_reads_every_ledger_and_keeps_closed_trades_only(monkeypatch):
    from swingbot.core.tracking import performance

    seen = {}
    rows = [{"id": "a", "status": "win", "ledger": "main"},
            {"id": "b", "status": "loss", "ledger": "weak"},
            {"id": "c", "status": "closed", "ledger": "main"},
            {"id": "d", "status": "open", "ledger": "main"}]

    class _FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return rows

    monkeypatch.setattr(performance, "TradeLog", _FakeLog)
    assert [t["id"] for t in book_status._closed_book()] == ["a", "b", "c"]
    assert seen == {"status": None, "limit": None, "ledger": None}


def test_the_scan_tick_calls_the_hook_right_after_the_provider_check():
    lines = [line.strip() for line in inspect.getsource(loops_mod._session_scan_tick).splitlines()]
    i = lines.index("await ops_watch.check_provider_health()")
    assert lines[i + 1] == "await book_status.post_book_status(channel)"
    assert sum("book_status" in line for line in lines) == 1
    assert loops_mod.book_status is book_status
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_book_status_latch.py`
Expected: FAIL. The `wire`-based tests, `test_zone_job_key`, `test_stored_zone_...` and `test_closed_book_...` fail with `AttributeError` (`ZONE_JOB`, `scheduled_repo`, `_closed_book` or `stored_zone` missing on `book_status`); `test_next_action_ranks_zones` with `AttributeError: ... 'next_action'`; the hook test with an `AssertionError` (the line after the provider check is blank today).

- [ ] **Step 3: Append the latch to `book_status.py`**

In `swingbot/commands/scanning/book_status.py`, replace the import block with:

```python
from __future__ import annotations

import asyncio
import logging

from swingbot import config
from swingbot.core.analytics import variance_band as vb
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.presentation import tokens
from swingbot.core.presentation.kinds import Kind

from . import notices

log = logging.getLogger(__name__)
```

Extend the module docstring with a second paragraph:

```text
The other half is the latch: post_book_status, called once per scan tick,
posts only when the zone RISES above the one stored under ZONE_JOB in
scheduled_jobs (fired_on is sa.Text, so the zone string needs no migration;
the live_loss_watch latch precedent). A fall stores the lower zone and
posts nothing, so the next rise posts again. The new zone is stored only
after a send returned a message.
```

Then append below `book_status_embed`:

```python
#: scheduled_jobs key holding the last zone posted, or fallen back to.
ZONE_JOB = "variance_band:zone"


def _closed_book() -> list[dict]:
    """The whole closed book, every ledger -- the same population the
    /analytics/variance-band route serves. A seam for tests."""
    from swingbot.core.analytics.scope import closed_only
    from swingbot.core.tracking.performance import TradeLog

    return closed_only(TradeLog().get_trades(status=None, limit=None, ledger=None) or [])


def _rank(zone: str) -> int:
    return vb.ZONES.index(zone)


def stored_zone() -> str:
    """The last stored zone; a missing or unknown value reads as normal."""
    value = scheduled_repo().fired_on(ZONE_JOB)
    return value if value in vb.ZONES else vb.ZONES[0]


def next_action(stored: str, zone: str) -> str:
    """"post" on a rise, "reset" on a fall, "none" when the zone is unchanged."""
    if _rank(zone) > _rank(stored):
        return "post"
    if _rank(zone) < _rank(stored):
        return "reset"
    return "none"


def _compute_band() -> dict:
    return vb.variance_band(_closed_book())


async def _apply(channel, band: dict) -> bool:
    """Post on a rise (storing the zone only after a successful send), store
    the lower zone on a fall, do nothing on the same zone."""
    zone = band["current"]["zone"]
    action = next_action(stored_zone(), zone)
    if action == "reset":
        scheduled_repo().mark(ZONE_JOB, zone)
        log.info("book status: zone fell to %s -- stored, nothing posted", zone)
        return False
    if action != "post":
        return False
    embed = book_status_embed(band, config.CURRENCY_SYMBOL)
    message = await notices.send_guarded(channel, embed, what="book status")
    if message is None:            # send_guarded swallows failures: store only on success
        return False
    scheduled_repo().mark(ZONE_JOB, zone)
    log.info("book status: zone rose to %s -- posted", zone)
    return True


async def post_book_status(channel) -> bool:
    """Once per scan tick: compute the band off the event loop and post the
    book-status line if the zone rose. Never raises; True only when posted."""
    try:
        band = await asyncio.to_thread(_compute_band)
        if band.get("status") != "ok":
            return False
        return await _apply(channel, band)
    except Exception as exc:
        swallowed(log, "scan.book_status", exc,
                  "book status: could not compute or post the variance band",
                  level=logging.ERROR, exc_info=True)
        return False
```

Notes for the implementer:
- `scheduled_repo` and `vb` are looked up as module attributes at call time; the tests patch `book_status.scheduled_repo` and `vb.variance_band`. Do not import `variance_band` by name.
- `_closed_book` imports `TradeLog` inside the function (the test patches `performance.TradeLog`), and mirrors the API seam of V175-5 on purpose: both read every ledger with no `BookScope`, so the panel and the message judge the same trades.
- The tag `scan.book_status` must stay unique (`tests/infra/test_swallowed_ratchet.py` rule 3); `git grep -n '"scan.book_status"'` shows only this site.

- [ ] **Step 4: Add the hook to the scan tick**

In `swingbot/commands/scanning/loops.py`, line 24, add `book_status` to the sibling import (alphabetical):

```python
from . import book_status, cooldown, equity_recorder, notices, ops_watch, outlook, presence, recap, runstate
```

and right after line 240 (`await ops_watch.check_provider_health()`):

```python
    await ops_watch.check_provider_health()
    await book_status.post_book_status(channel)
```

Nothing else in `_session_scan_tick` changes: no `if`, no `try`, no comment-only edits elsewhere in the function.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_book_status_latch.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_book_status_text.py`
Expected: PASS, 0 failed (V175-6's text tests survive the import-block change).

- [ ] **Step 6: The existing scan-tick tests pass unchanged**

These drive `_session_scan_tick` end to end or read its source; the new call runs in them against an empty trade store (insufficient band, nothing posted).

Run: `python $WT/scripts/dev/testrun.py file tests/infra/test_silent_alerts_channel.py`
Run: `python $WT/scripts/dev/testrun.py file tests/commands/test_loops_cooldown.py`
Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_ops_watch.py`
Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py`
Run: `python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`
Expected: each PASS, 0 failed, 0 skipped beyond what the same file skips on `main`. If one fails because of the new call (for example a channel stub that counts sends), do **not** edit that test file (it is outside this task): stop and report the failure to the controller.

Plan embeds, once more after the import change:
Run: `python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: PASS, 0 failed, file unedited.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s $WT/swingbot/commands/scanning/loops.py | grep _session_scan_tick`
Expected: `F 187:0 _session_scan_tick - C (15)`: the score stays 15.

Run: `python -m radon cc -s -n C $WT/swingbot/commands/scanning/book_status.py`
Expected: no output.

- [ ] **Step 8: Commit**

Write `$SCRATCH/v175-7-msg.txt`:

```text
feat(bot): book-status zone latch and one-line scan hook (v175)

post_book_status computes the variance band off the event loop once per
scan tick and posts the BOOK STATUS line only when the zone rises into
rough or outside; the zone is stored under scheduled_jobs
"variance_band:zone" only after a successful send. A fall stores the
lower zone silently; an insufficient band does nothing. Never raises
(swallowed tag scan.book_status). _session_scan_tick gains one await and
no branch (complexity stays 15).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

```bash
git -C $WT add swingbot/commands/scanning/book_status.py swingbot/commands/scanning/loops.py tests/commands/test_book_status_latch.py
git -C $WT commit -F "$SCRATCH/v175-7-msg.txt"
git -C $R status --short
```
Expected: one commit on the branch; the main tree shows no change from this task.

