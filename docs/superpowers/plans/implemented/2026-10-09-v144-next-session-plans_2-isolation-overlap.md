# v144 Next-session plans: Part 2, pooled isolation, cohort filter, config, overlap

> Part of [`_0-index`](2026-10-09-v144-next-session-plans_0-index.md), which holds the header, the global constraints, the parallelisation map and the open-point answer. Read those first; they apply to every task here.

# Phase 2 — Pooled isolation and the cohort view

### Task V144-6: Keep every pooled figure on `origin is None`

**Files:**
- Modify: `swingbot/core/tracking/ledger.py` (`is_weak`, `is_main`, module docstring)
- Modify: `swingbot/admin/api_v1/dashboard.py` (the `realized_weak` line, ~291, and its import)
- Modify: `swingbot/core/analytics/journal.py` (`JournalStore.entries`)
- Modify: `swingbot/admin/api_v1/trades.py` (`_noted_ids` ~548, `_note_for` ~574)
- Modify: `swingbot/core/analytics/pnl_calendar.py` (`load_rows`)
- Modify: `swingbot/commands/stats.py` (`soak_cmd`, ~44)
- Modify: `swingbot/admin/api_v1/analytics.py` (`_soak_for` ~118, `analytics_exit_quality`'s journal read ~656, `analytics_plans` ~728)
- Test: `tests/tracking/test_origin_pooling.py`, `tests/admin/test_v144_pooled_readers.py`

**Interfaces:**
- Consumes: `tracking.origin.is_regular`, `in_cohort`, `ALL` (V144-1); journal entries carry `origin` (V144-1).
- Produces:
  - `ledger.is_main(t)` / `is_weak(t)` are False for any outlook record. `split_by_ledger` therefore drops outlook records from both halves.
  - `JournalStore.entries(..., cohort: str | None = None)`: `None` = regular only (pooled), `origin.ALL` = everything, `"next_session"` = that cohort.

- [ ] **Step 1: Write the failing tests**

```python
# tests/tracking/test_origin_pooling.py
"""v144: every pooled figure is byte-identical with and without an outlook trade."""
from swingbot.core.analytics import pnl_calendar
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.analytics.scope import closed_only
from swingbot.core.tracking import ledger
from swingbot.core.tracking.ledger import split_by_ledger
from swingbot.core.tracking.performance import TradeLog


def _open(log, ticker, **kw):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0,
                         stop_loss=95.0, take_profit=110.0, source="strategy", **kw)


def _close(log, trade_id, status, exit_price, pnl):
    trade = log.get_trade_by_id(trade_id)
    trade.update(status=status, exit_price=exit_price, realized_pnl_amount=pnl,
                 closed_at="2026-09-17T20:00:00+00:00")
    log._db_upsert(trade)
    JournalStore().add({"trade_id": trade_id, "ticker": trade["ticker"], "strategy": "MACD",
                        "outcome": status, "r_realized": (exit_price - 100.0) / 5.0,
                        "closed_at": trade["closed_at"], "origin": trade.get("origin")})


def _figures(log):
    trades = log.get_trades(status=None, limit=None)
    closed = closed_only(trades)
    main, weak = split_by_ledger(closed)
    return {
        "stats_main": log.get_stats(),
        "stats_weak": log.get_stats(ledger="weak"),
        "stats_level_unexpanded": log.get_stats(3, expand=False),
        "main_ids": sorted(t["id"] for t in log.get_trades(status=None, limit=None, ledger="main")),
        "split": (sorted(t["id"] for t in main), sorted(t["id"] for t in weak)),
        "journal": sorted(e["trade_id"] for e in JournalStore().entries()),
        "calendar": pnl_calendar.load_rows(trade_log=log),
    }


def test_pooled_figures_ignore_an_outlook_trade():
    log = TradeLog()
    _close(log, _open(log, "AAPL"), "win", 108.0, 80.0)
    _close(log, _open(log, "MSFT"), "loss", 95.0, -50.0)
    _close(log, _open(log, "NVDA", ledger="weak"), "win", 104.0, 40.0)
    _open(log, "AMD")                                         # a regular open trade
    before = _figures(log)

    _close(log, _open(log, "TSLA", origin="next_session"), "win", 110.0, 100.0)
    _open(log, "META", origin="next_session")                 # an open outlook trade
    _close(log, _open(log, "AMZN", ledger="weak", origin="next_session"), "loss", 95.0, -50.0)

    assert _figures(log) == before


def test_the_cohort_is_still_readable_on_request():
    log = TradeLog()
    _close(log, _open(log, "TSLA", origin="next_session"), "win", 110.0, 100.0)
    assert [e["trade_id"] for e in JournalStore().entries(cohort="next_session")]
    assert JournalStore().entries() == []
    assert len(JournalStore().entries(cohort="all")) == 1


def test_ledger_predicates():
    evening = {"origin": "next_session"}
    assert ledger.is_main(evening) is False and ledger.is_weak(evening) is False
    assert ledger.is_weak({"ledger": "weak", "origin": "next_session"}) is False
    assert ledger.is_main({}) is True and ledger.is_weak({"ledger": "weak"}) is True
```

```python
# tests/admin/test_v144_pooled_readers.py
"""v144: the plan-reading pooled figures (soak verdict, plan funnel) skip outlook plans."""
import pytest

from swingbot.core.planning.plan_engine import plan_to_dict
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _plans():
    return [_plan(plan_id="r1", source="strategy", strategy="MACD"),
            _plan(plan_id="o1", source="strategy", strategy="MACD", origin="next_session",
                  valid_session="2026-10-12")]


def test_soak_reads_regular_plans_only(admin_app, monkeypatch):
    seed_store("plans", [plan_to_dict(p) for p in _plans()])
    seen = {}
    monkeypatch.setattr("swingbot.core.edge.strategy_soak.soak_verdict",
                        lambda plans, badge: seen.setdefault("ids", [p.plan_id for p in plans]))
    from swingbot.admin.api_v1.analytics import _soak_for
    _soak_for("MACD")
    assert seen["ids"] == ["r1"]


def test_plan_funnel_reads_regular_plans_only(logged_in, monkeypatch):
    seed_store("plans", [plan_to_dict(p) for p in _plans()])
    seen = {}
    monkeypatch.setattr("swingbot.admin.queries._plan_lifecycle",
                        lambda plans: seen.setdefault("ids", sorted(p.plan_id for p in plans)) and {})
    assert logged_in.get("/api/v1/analytics/plans").status_code == 200
    assert seen["ids"] == ["r1"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_origin_pooling.py` and `python scripts/dev/testrun.py file tests/admin/test_v144_pooled_readers.py`
Expected: FAIL. `_figures` differs after the outlook trades. (`analytics/scope.select` compares the raw `ledger` field and is not a ledger-rule reader. Its origin filter and its byte-identity pin are V144-7's, in `tests/analytics/test_scope_origin.py`.) `entries()` has an unexpected keyword `cohort`. The soak and funnel tests see `["o1", "r1"]` / `["r1", "o1"]`.

- [ ] **Step 3: The ledger rule.** Replace the body of `swingbot/core/tracking/ledger.py` below the constants with:

```python
from swingbot.core.tracking.origin import is_regular


def ledger_for(source: str | None, badge_status: str | None) -> str:
    """Return the frozen ledger for a newly created plan or trade."""
    if source == "strategy" and badge_status == "WEAK":
        return WEAK
    return MAIN


def is_weak(trade: dict) -> bool:
    return trade.get("ledger") == WEAK and is_regular(trade)


def is_main(trade: dict) -> bool:
    return trade.get("ledger") != WEAK and is_regular(trade)


def split_by_ledger(trades: list) -> tuple[list, list]:
    return ([trade for trade in trades if is_main(trade)],
            [trade for trade in trades if is_weak(trade)])
```

Move the `from swingbot.core.tracking.origin import is_regular` import to the top of the module, under the docstring. Extend the module docstring with: `v144: both ledgers are the regular lane only. An outlook trade (origin "next_session") is in neither, so split_by_ledger drops it from both halves, and the cohort is read through tracking/origin.py.`

- [ ] **Step 4: The dashboard's weak panel.** In `swingbot/admin/api_v1/dashboard.py`:
  - Change `from swingbot.core.tracking.ledger import is_main, split_by_ledger` to `from swingbot.core.tracking.ledger import is_main, is_weak, split_by_ledger`.
  - In the `"realized_weak": _realized(...)` argument, change `if not is_main(t) and t.get("status") ...` to `if is_weak(t) and t.get("status") ...`.

  That is one predicate swapped for another and no new branch; `dashboard` stays D (25).

- [ ] **Step 5: `JournalStore.entries` takes a cohort.** In `swingbot/core/analytics/journal.py`:

```python
    def entries(self, *, strategy: str | None = None, tag: str | None = None,
                outcome: str | None = None, since: str | None = None,
                has_note: bool | None = None, cohort: str | None = None) -> list[dict]:
        """Every matching entry, newest first (by `closed_at`, falling back
        to `created_at` for an entry that somehow lacks it). All filters
        are AND-combined; omit a filter (leave it None) to not apply it.

        v144: `cohort` None (the default) is the regular lane only, so every
        pooled reader (E31/E32 overrides, digests, lessons) keeps to it;
        origin.ALL is every entry; "next_session" is that cohort."""
        from swingbot.core.db.codec import normalise
        from swingbot.core.db.repositories.journal import journal_repo
        from swingbot.core.tracking.origin import in_cohort
        rows = normalise(journal_repo().entries(
            strategy=strategy, tag=tag, outcome=outcome, since=since, has_note=has_note
        ))
        return [entry for entry in rows if in_cohort(entry, cohort)]
```

- [ ] **Step 6: Per-trade note lookups read every lane.** In `swingbot/admin/api_v1/trades.py`, in both `_noted_ids` and `_note_for`, change `JournalStore().entries()` to `JournalStore().entries(cohort=ALL)`, and add `from swingbot.core.tracking.origin import ALL` next to each function's existing `from swingbot.core.analytics.journal import JournalStore` line. A note belongs to one trade, whatever its lane.

- [ ] **Step 7: The P&L calendar.** In `swingbot/core/analytics/pnl_calendar.py`, `load_rows`, change `trades = tl.get_trades(status=None, limit=None) or []` to:

```python
    from swingbot.core.tracking.origin import is_regular
    trades = [t for t in (tl.get_trades(status=None, limit=None) or []) if is_regular(t)]
```

The `js.entries()` call already defaults to the regular lane after Step 5.

- [ ] **Step 8: The soak verdict and the plan funnel.**
  1. `swingbot/commands/stats.py`, `soak_cmd`: change the list comprehension to `[plan for plan in PlanStore().all() if plan.source == "strategy" and plan.strategy == strategy and is_regular(plan)]`, and add `from swingbot.core.tracking.origin import is_regular` to the module imports.
  2. `swingbot/admin/api_v1/analytics.py`, `_soak_for`: the same `and is_regular(plan)`, with `from swingbot.core.tracking.origin import is_regular` added to the function's local imports.
  3. `swingbot/admin/api_v1/analytics.py`, `analytics_plans`: change `_plan_lifecycle(PlanStore().all())` to `_plan_lifecycle([plan for plan in PlanStore().all() if is_regular(plan)])`, with the same local import. `_plan_lifecycle` is C (20) and stays untouched: the filter sits in the caller.
  4. `swingbot/admin/api_v1/analytics.py`, the exit-quality route's `entries = [entry for entry in JournalStore().entries() if entry.get("trade_id") in ids]` (~656): change to `JournalStore().entries(cohort=ALL)`. `ids` is already the scoped trade set, so the scope (V144-7's `origin` param) decides the lane. Add `from swingbot.core.tracking.origin import ALL` to that function's local imports.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_origin_pooling.py`, `python scripts/dev/testrun.py file tests/admin/test_v144_pooled_readers.py`, `python scripts/dev/testrun.py file tests/tracking/test_ledger.py`, `python scripts/dev/testrun.py file tests/tracking/test_ledger_stats.py`.
Expected: all PASS. Then `python scripts/dev/testrun.py changed`. Expected: `0 failed`.

- [ ] **Step 10: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/tracking/ledger.py swingbot/core/analytics/journal.py swingbot/core/analytics/pnl_calendar.py swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/analytics.py swingbot/commands/stats.py`
Expected: `dashboard` is still D (25) and `_realized` is still C (16), both legacy. Nothing new.

- [ ] **Step 11: Commit**

```bash
git add swingbot/core/tracking/ledger.py swingbot/admin/api_v1/dashboard.py swingbot/core/analytics/journal.py swingbot/admin/api_v1/trades.py swingbot/core/analytics/pnl_calendar.py swingbot/commands/stats.py swingbot/admin/api_v1/analytics.py tests/tracking/test_origin_pooling.py tests/admin/test_v144_pooled_readers.py
git commit -m "feat(v144): pooled figures keep to origin is None; the cohort is never summed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-7: The admin cohort filter and `/analytics/cohort`

**Files:**
- Modify: `swingbot/core/analytics/scope.py` (`SCOPE_PARAMS`, `BookScope.origin`, `parse_scope`, `select` → table-driven, `echo`)
- Modify: `swingbot/core/analytics/partials.py` (`_matches`)
- Create: `swingbot/core/analytics/cohort.py`
- Modify: `swingbot/admin/api_v1/analytics.py` (new route `analytics_cohort`)
- Test: `tests/analytics/test_scope_origin.py`, `tests/admin/test_api_v1_analytics_cohort.py`

**Interfaces:**
- Consumes: `tracking.origin.ORIGINS`, `in_cohort` (V144-1); `session_expiry.cancel_reason` (V144-3); `analytics.partials.is_filled`; `analytics.metrics.win_rate`, `expectancy_r`.
- Produces:
  - `BookScope.origin: str | None = None`. Every scoped `/analytics/*` route accepts `?origin=next_session`; without it the scope is the regular lane, as today.
  - `echo()` adds `"origin"` only when it is set, so every existing payload stays byte-identical.
  - `cohort.cohort_report(plans, trades, origin) -> dict` with keys `origin, n, issued, filled, fill_rate_pct, closed, win_rate, expectancy_r, cancel_reasons`.
  - `GET /api/v1/analytics/cohort?origin=next_session`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analytics/test_scope_origin.py
"""v144: the scope's origin filter -- default regular, a named cohort on request."""
import pytest

from swingbot.core.analytics.scope import BookScope, ScopeError, echo, parse_scope, select


def _t(trade_id, origin=None, ledger=None):
    t = {"id": trade_id, "status": "win", "closed_at": "2026-08-04T15:00:00+00:00",
         "strategy": "MACD", "horizon_key": "2w", "direction": "bullish",
         "target_sources": ["MACD"]}
    if origin:
        t["origin"] = origin
    if ledger:
        t["ledger"] = ledger
    return t


BOOK = [_t("r"), _t("w", ledger="weak"), _t("o", origin="next_session"),
        _t("ow", origin="next_session", ledger="weak")]


def test_default_scope_is_the_regular_lane():
    assert parse_scope({}).origin is None
    assert [t["id"] for t in select(BOOK, parse_scope({}))] == ["r"]
    assert [t["id"] for t in select(BOOK, parse_scope({"ledger": "both"}))] == ["r", "w"]


def test_a_named_cohort_selects_only_it():
    scope = parse_scope({"origin": "next_session", "ledger": "both"})
    assert [t["id"] for t in select(BOOK, scope)] == ["o", "ow"]


def test_an_unknown_origin_is_rejected():
    with pytest.raises(ScopeError, match="origin must be one of"):
        parse_scope({"origin": "regular"})


def test_echo_adds_origin_only_when_set():
    assert "origin" not in echo(BookScope(), 0)["scope"]
    assert echo(BookScope(origin="next_session"), 2)["scope"]["origin"] == "next_session"
```

```python
# tests/admin/test_api_v1_analytics_cohort.py
"""v144: GET /api/v1/analytics/cohort and the origin scope on a pooled route."""
import pytest

from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _trade
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(admin_app, client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _book():
    filled = _plan(plan_id="o1", origin="next_session", valid_session="2026-10-12", entry_type="stop_entry")
    record_transition(filled, PlanStatus.ACTIVE, reason="stop_entry_fill", at="2026-10-12T14:00:00+00:00")
    missed = _plan(plan_id="o2", origin="next_session", valid_session="2026-10-12", entry_type="stop_entry")
    record_transition(missed, PlanStatus.CANCELLED, reason="never_triggered", at="2026-10-12T20:00:00+00:00")
    regular = _plan(plan_id="r1")
    win = _trade("aaaaaaaaaaaaaaaa", plan_id="o1", status="win")
    win["origin"] = "next_session"
    win["horizon_key"] = "4w"
    regular_win = _trade("bbbbbbbbbbbbbbbb", plan_id="r1", status="win")
    regular_win["horizon_key"] = "4w"
    seed_store("plans", [plan_to_dict(p) for p in (filled, missed, regular)])
    seed_store("trades", [win, regular_win])


def test_requires_auth(client):
    assert_error(client.get("/api/v1/analytics/cohort?origin=next_session"), "auth", 401)


def test_rejects_a_missing_or_unknown_origin(logged_in):
    assert_error(logged_in.get("/api/v1/analytics/cohort"), "invalid", 400)
    assert_error(logged_in.get("/api/v1/analytics/cohort?origin=regular"), "invalid", 400)


def test_reports_the_cohort_alone(logged_in):
    _book()
    body = logged_in.get("/api/v1/analytics/cohort?origin=next_session").get_json()
    assert (body["origin"], body["n"], body["issued"], body["filled"]) == ("next_session", 2, 2, 1)
    assert body["fill_rate_pct"] == 50.0
    assert body["closed"] == 1 and body["win_rate"] == 100.0
    assert body["expectancy_r"] == pytest.approx((108.0 - 101.0) / 6.0)
    assert body["cancel_reasons"] == {"never_triggered": 1}


def test_a_pooled_route_counts_the_regular_lane_unless_asked(logged_in):
    _book()
    assert logged_in.get("/api/v1/analytics/performance").get_json()["n"] == 1
    body = logged_in.get("/api/v1/analytics/performance?origin=next_session").get_json()
    assert body["n"] == 1 and body["scope"]["origin"] == "next_session"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_scope_origin.py` and `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_cohort.py`
Expected: FAIL. There is no `origin` on `BookScope`, and `/analytics/cohort` returns 404.

- [ ] **Step 3: `scope.py`.** Make these edits:

```python
from swingbot.core.tracking.origin import ORIGINS, in_cohort

SCOPE_PARAMS = ("from", "to", "ledger", "strategy", "horizon", "direction", "origin")
```

Add the last field of `BookScope`:

```python
    origin: str | None = None      # v144: None = the regular lane (pooled); a cohort name = only it
```

In `parse_scope`'s `BookScope(...)` add `origin=_choice(args, "origin", ORIGINS, None),`.

Replace `select` (C (14) today) with a table of checks. The behaviour is identical for every pre-v144 scope:

```python
def _checks(scope: BookScope) -> tuple:
    """One predicate per scope field; all must hold. The origin check comes
    first: without `origin`, the scope is the regular lane (v144)."""
    return (
        lambda t: in_cohort(t, scope.origin),
        lambda t: scope.ledger == "both" or (t.get("ledger") or "main") == scope.ledger,
        lambda t: not scope.strategy or primary_strategy_label(t) == scope.strategy,
        lambda t: not scope.horizon or t.get("horizon_key") == scope.horizon,
        lambda t: not scope.direction or t.get("direction") == scope.direction,
    )


def select(closed: list[dict], scope: BookScope) -> list[dict]:
    checks = _checks(scope)
    return [t for t in m.in_date_range(closed, start=scope.start, end=scope.end)
            if all(check(t) for check in checks)]
```

Replace `echo` with:

```python
def echo(scope: BookScope, n: int) -> dict:
    body = {"from": scope.start, "to": scope.end, "ledger": scope.ledger,
            "strategy": scope.strategy, "horizon": scope.horizon, "direction": scope.direction}
    if scope.origin is not None:
        body["origin"] = scope.origin      # v144: only when asked, so old payloads are unchanged
    return {"scope": body, "n": n}
```

- [ ] **Step 4: Plans follow the same scope.** In `swingbot/core/analytics/partials.py`, `_matches`, add as the first statement:

```python
    if not in_cohort(plan, getattr(scope, "origin", None)):
        return False
```

and add `from swingbot.core.tracking.origin import in_cohort` to the module imports.

- [ ] **Step 5: Create `swingbot/core/analytics/cohort.py`**

```python
"""v144: one cohort's own numbers -- the outlook lane's fill rate, win rate,
ExpR of the filled trades and cancellation-reason histogram. Never pooled: the
caller passes the whole book and this reads only `origin == cohort`. Whether
the cohort ever pools is a later, measured decision (spec v144 § Analytics)."""
from __future__ import annotations

from collections import Counter

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics.partials import is_filled
from swingbot.core.analytics.scope import CLOSED_STATUSES
from swingbot.core.planning.session_expiry import cancel_reason
from swingbot.core.tracking.origin import in_cohort


def cohort_report(plans: list, trades: list[dict], origin: str) -> dict:
    issued = [plan for plan in plans if in_cohort(plan, origin)]
    filled = [plan for plan in issued if is_filled(plan)]
    closed = [t for t in trades if in_cohort(t, origin) and t.get("status") in CLOSED_STATUSES]
    reasons = Counter(reason for reason in map(cancel_reason, issued) if reason)
    return {
        "origin": origin, "n": len(issued), "issued": len(issued), "filled": len(filled),
        "fill_rate_pct": round(len(filled) / len(issued) * 100, 2) if issued else None,
        "closed": len(closed), "win_rate": m.win_rate(closed),
        "expectancy_r": m.expectancy_r(closed),
        "cancel_reasons": dict(sorted(reasons.items())),
    }
```

- [ ] **Step 6: The route.** In `swingbot/admin/api_v1/analytics.py`, after `analytics_partials`, add:

```python
@api_v1.route("/analytics/cohort", methods=["GET"])
@require_auth
def analytics_cohort():
    """v144: one origin cohort's own N, fill rate (issued -> filled), win rate
    and ExpR of its closed trades, and its cancellation-reason histogram. The
    cohort is never folded into any other figure this API serves."""
    from swingbot.core.analytics.cohort import cohort_report
    from swingbot.core.planning.plan_store import PlanStore
    from swingbot.core.tracking.origin import ORIGINS

    origin = (request.args.get("origin") or "").strip()
    if origin not in ORIGINS:
        raise ApiError("invalid", f"origin must be one of {list(ORIGINS)}, got {origin!r}", 400)
    return jsonify(cohort_report(PlanStore().all(), _all_trades(TradeLog()), origin))
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_scope_origin.py`, `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_cohort.py`, `python scripts/dev/testrun.py file tests/analytics/test_scope.py`, `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py`, `python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics_partials.py`.
Expected: all PASS. The last three are unedited and pin that every pre-v144 payload is unchanged.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/analytics/scope.py swingbot/core/analytics/partials.py swingbot/core/analytics/cohort.py`
Expected: no output. `select` drops from C (14).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/analytics/scope.py swingbot/core/analytics/partials.py swingbot/core/analytics/cohort.py swingbot/admin/api_v1/analytics.py tests/analytics/test_scope_origin.py tests/admin/test_api_v1_analytics_cohort.py
git commit -m "feat(v144): origin scope on /analytics/*, and /analytics/cohort for the outlook lane

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 3 — Schedule and overlap

### Task V144-8: Config fields and session arithmetic (`outlook_session`)

**Files:**
- Modify: `swingbot/config.py` (two `Field`s after `SIGNAL_CONFIRMATION_SCANS`; both added to `_SEARCH_CLASSES["live_only"]`)
- Modify: `.env.example` (after `SIGNAL_CONFIRMATION_SCANS=1`)
- Create: `swingbot/core/scanning/outlook_session.py`
- Test: `tests/scanning/test_outlook_session.py`

**Interfaces:**
- Consumes: `market.session.RTH_OPEN`, `US_MARKET_TZ`, `now_et`, `nyse_calendar`, `session_close`.
- Produces:
  - `config.NEXT_SESSION_SCAN_ENABLED: bool` (default False), `config.NEXT_SESSION_SCAN_TIME: str` (default `"23:30"`).
  - `outlook_session`: `RUN_WEEKDAYS`, `DEFAULT_SLOT`, `parse_slot(raw) -> time`, `latest_slot_date(now_berlin, slot) -> date | None`, `target_session(run_date) -> date | None`, `signal_session(run_date) -> date | None`, `fire_allowed(now, run_date) -> bool`, `wrapup_due(now, day) -> bool`, `wrapup_candidates(now) -> list[date]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scanning/test_outlook_session.py
"""v144: when the outlook runs, which session it targets, how late it may fire,
and when the wrap-up is due -- all in ET off the session calendar."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot import config
from swingbot.core.scanning import outlook_session as osn

BERLIN = ZoneInfo("Europe/Berlin")
ET = ZoneInfo("America/New_York")
SLOT = dt.time(23, 30)


def _field(key):
    return next(field for field in config.FIELDS if field.key == key)


def test_the_fields_ship_inert_and_live_only():
    enabled, slot = _field("NEXT_SESSION_SCAN_ENABLED"), _field("NEXT_SESSION_SCAN_TIME")
    assert enabled.type == "checkbox" and enabled.default == "false"
    assert slot.default == "23:30"
    assert enabled.search_class == slot.search_class == "live_only"
    assert config.NEXT_SESSION_SCAN_ENABLED is False


@pytest.mark.parametrize("raw,expected", [
    ("23:30", dt.time(23, 30)), ("7:05", dt.time(7, 5)), ("", osn.DEFAULT_SLOT),
    ("23.30", osn.DEFAULT_SLOT), ("25:00", osn.DEFAULT_SLOT), (None, osn.DEFAULT_SLOT),
])
def test_parse_slot(raw, expected):
    assert osn.parse_slot(raw) == expected


@pytest.mark.parametrize("now,expected", [
    (dt.datetime(2026, 10, 11, 23, 30, tzinfo=BERLIN), dt.date(2026, 10, 11)),   # Sunday at the slot
    (dt.datetime(2026, 10, 11, 23, 29, tzinfo=BERLIN), dt.date(2026, 10, 8)),    # Sunday before it: Thursday's
    (dt.datetime(2026, 10, 12, 2, 0, tzinfo=BERLIN), dt.date(2026, 10, 11)),     # Monday small hours: Sunday's
    (dt.datetime(2026, 10, 9, 23, 45, tzinfo=BERLIN), dt.date(2026, 10, 8)),     # Friday never runs
    (dt.datetime(2026, 10, 10, 23, 45, tzinfo=BERLIN), dt.date(2026, 10, 8)),    # Saturday never runs
])
def test_latest_slot_date_is_sunday_to_thursday_only(now, expected):
    assert osn.latest_slot_date(now, SLOT) == expected


@pytest.mark.parametrize("run_date,target", [
    (dt.date(2026, 10, 11), dt.date(2026, 10, 12)),     # Sunday -> Monday
    (dt.date(2026, 10, 15), dt.date(2026, 10, 16)),     # Thursday -> Friday
    (dt.date(2027, 3, 25), None),                       # Thursday before Good Friday
    (dt.date(2026, 11, 25), None),                      # Wednesday before Thanksgiving
    (dt.date(2026, 11, 26), dt.date(2026, 11, 27)),     # Thanksgiving -> the half-day
])
def test_target_session_is_the_next_calendar_day_or_nothing(run_date, target):
    assert osn.target_session(run_date) == target


@pytest.mark.parametrize("run_date,bar", [
    (dt.date(2026, 10, 11), dt.date(2026, 10, 9)),      # Sunday reads Friday's bar
    (dt.date(2026, 10, 12), dt.date(2026, 10, 12)),     # Monday reads Monday's
    (dt.date(2026, 11, 26), dt.date(2026, 11, 25)),     # Thanksgiving reads Wednesday's
])
def test_signal_session_is_the_last_session_on_or_before_the_run_date(run_date, bar):
    assert osn.signal_session(run_date) == bar


def test_a_late_fire_is_allowed_only_before_the_target_sessions_rth_open():
    sunday = dt.date(2026, 10, 11)
    assert osn.fire_allowed(dt.datetime(2026, 10, 12, 15, 29, tzinfo=BERLIN), sunday)
    assert not osn.fire_allowed(dt.datetime(2026, 10, 12, 15, 30, tzinfo=BERLIN), sunday)


def test_the_late_fire_cutoff_follows_et_in_the_dst_mismatch_week():
    sunday = dt.date(2027, 3, 14)                       # Monday 03-15: US on DST, Europe not
    assert osn.fire_allowed(dt.datetime(2027, 3, 15, 14, 29, tzinfo=BERLIN), sunday)
    assert not osn.fire_allowed(dt.datetime(2027, 3, 15, 14, 30, tzinfo=BERLIN), sunday)


def test_the_wrapup_is_due_fifteen_minutes_after_the_official_close():
    monday, half = dt.date(2026, 10, 12), dt.date(2026, 11, 27)
    assert not osn.wrapup_due(dt.datetime(2026, 10, 12, 16, 14, tzinfo=ET), monday)
    assert osn.wrapup_due(dt.datetime(2026, 10, 12, 16, 15, tzinfo=ET), monday)
    assert osn.wrapup_due(dt.datetime(2026, 11, 27, 13, 15, tzinfo=ET), half)


def test_wrapup_candidates_are_the_last_two_sessions():
    assert osn.wrapup_candidates(dt.datetime(2026, 10, 12, 20, 0, tzinfo=ET)) == \
        [dt.date(2026, 10, 9), dt.date(2026, 10, 12)]
    assert osn.wrapup_candidates(dt.datetime(2026, 10, 11, 12, 0, tzinfo=ET)) == \
        [dt.date(2026, 10, 8), dt.date(2026, 10, 9)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_session.py`
Expected: FAIL with `StopIteration` (no such field) and an `ImportError`.

- [ ] **Step 3: The config fields.** In `swingbot/config.py`, directly after the `Field("SIGNAL_CONFIRMATION_SCANS", ...)` entry in the `# --- Scanning & session ---` block, add:

```python
    Field("NEXT_SESSION_SCAN_ENABLED", "NEXT_SESSION_SCAN_ENABLED", "Scanning & Session",
          "Next-session outlook scan", type="checkbox", default="false",
          help="v144: at NEXT_SESSION_SCAN_TIME (Berlin), Sunday to Thursday, scan the watchlist on "
               "the last closed daily bar and post tomorrow's stop-entry plans, each valid for that "
               "one NYSE session only. They are a separate cohort (origin next_session), never "
               "pooled into ExpR, win rate or badges. A wrap-up posts 15 minutes after the close."),
    Field("NEXT_SESSION_SCAN_TIME", "NEXT_SESSION_SCAN_TIME", "Scanning & Session",
          "Outlook scan time (Berlin, HH:MM)", default="23:30",
          help="Europe/Berlin, 24h HH:MM. A malformed value falls back to 23:30 with a warning. "
               "A run missed while the bot was down still fires late, but never after the RTH "
               "open of the session it targets."),
```

In `_SEARCH_CLASSES["live_only"]`, add `"NEXT_SESSION_SCAN_ENABLED", "NEXT_SESSION_SCAN_TIME",` beside `"SESSION_START_HOUR", "SESSION_END_HOUR", "SCAN_INTERVAL_MINUTES",`.

- [ ] **Step 4: `.env.example`.** After the `SIGNAL_CONFIRMATION_SCANS=1` line and its blank line, add:

```
# v144: the next-session outlook. At NEXT_SESSION_SCAN_TIME (Europe/Berlin),
# Sunday to Thursday, post tomorrow's stop-entry plans, each valid for that one
# NYSE session; a wrap-up follows the close. Off by default.
NEXT_SESSION_SCAN_ENABLED=false
NEXT_SESSION_SCAN_TIME=23:30

```

- [ ] **Step 5: Create `swingbot/core/scanning/outlook_session.py`**

```python
"""v144: the outlook's calendar.

When it runs (Sunday to Thursday at the configured Berlin slot), which bar it
reads (the last NYSE session on or before the run date, so Sunday reads Friday),
which session it targets (the NEXT CALENDAR DAY, only if that is a session; it
never skips ahead), how late a missed run may still fire (before the target's
RTH open), and when the wrap-up is due (15 minutes after the official close).
Every session boundary is ET from market.session; no Berlin hour is hard-coded.
"""
from __future__ import annotations

import datetime as dt
import logging

from swingbot.core.market.session import (RTH_OPEN, US_MARKET_TZ, now_et, nyse_calendar,
                                          session_close)

log = logging.getLogger(__name__)

RUN_WEEKDAYS = frozenset({6, 0, 1, 2, 3})      # Sunday .. Thursday (Monday = 0)
DEFAULT_SLOT = dt.time(23, 30)
WRAPUP_DELAY = dt.timedelta(minutes=15)
_LOOKBACK_DAYS = 10


def parse_slot(raw) -> dt.time:
    try:
        hour, minute = (int(part) for part in str(raw).strip().split(":"))
        return dt.time(hour, minute)
    except (TypeError, ValueError):
        log.warning("NEXT_SESSION_SCAN_TIME %r is not HH:MM -- using %s",
                    raw, DEFAULT_SLOT.strftime("%H:%M"))
        return DEFAULT_SLOT


def latest_slot_date(now_berlin: dt.datetime, slot: dt.time) -> dt.date | None:
    """The newest Sunday-Thursday run date whose slot is at or before `now_berlin`."""
    for back in range(7):
        day = now_berlin.date() - dt.timedelta(days=back)
        slot_at = dt.datetime.combine(day, slot, tzinfo=now_berlin.tzinfo)
        if day.weekday() in RUN_WEEKDAYS and now_berlin >= slot_at:
            return day
    return None


def target_session(run_date: dt.date) -> dt.date | None:
    """Tomorrow, if tomorrow is an NYSE session; otherwise None ("no session")."""
    tomorrow = run_date + dt.timedelta(days=1)
    return tomorrow if nyse_calendar().is_session(tomorrow) else None


def signal_session(run_date: dt.date) -> dt.date | None:
    """The bar the outlook reads: the last session on or before the run date."""
    sessions = nyse_calendar().sessions(run_date - dt.timedelta(days=_LOOKBACK_DAYS), run_date)
    return sessions[-1] if sessions else None


def fire_allowed(now: dt.datetime, run_date: dt.date) -> bool:
    """A run may fire late, but never into a session already underway."""
    session = target_session(run_date) or run_date + dt.timedelta(days=1)
    return now_et(now) < dt.datetime.combine(session, RTH_OPEN, tzinfo=US_MARKET_TZ)


def wrapup_due(now: dt.datetime, day: dt.date) -> bool:
    close_at = dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)
    return now_et(now) >= close_at + WRAPUP_DELAY


def wrapup_candidates(now: dt.datetime) -> list[dt.date]:
    """The last two sessions on or before today (ET): today's, and the one a
    restart may still owe a wrap-up for."""
    today = now_et(now).date()
    return nyse_calendar().sessions(today - dt.timedelta(days=_LOOKBACK_DAYS), today)[-2:]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_session.py`, `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`, `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`, `python scripts/dev/testrun.py file tests/admin/test_api_v1_system_settings.py`.
Expected: all PASS.

- [ ] **Step 7: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/outlook_session.py`. Expected: no output.

```bash
git add swingbot/config.py .env.example swingbot/core/scanning/outlook_session.py tests/scanning/test_outlook_session.py
git commit -m "feat(v144): NEXT_SESSION_SCAN_* config (inert) and the outlook session calendar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-9: The ⚠ overlap line on regular alerts (`lane_overlap`)

**Files:**
- Create: `swingbot/core/scanning/lane_overlap.py`
- Modify: `swingbot/core/scanning/scan_run.py` (module import line; one call after `embed = build_embed(...)` in `_sync_run_scan`, ~1091)
- Modify: `swingbot/core/scanning/short_run.py` (module import line; one call after `embed = build_embed(...)` in `_alert_for`)
- Test: `tests/scanning/test_lane_overlap.py`

**Interfaces:**
- Consumes: trade `origin` (V144-1); `TradeLog.get_trades(status="open", ticker=...)`.
- Produces:
  - `lane_overlap.OVERLAP_FIELD = "⚠ Overlap"`.
  - `overlap_line(ticker, *, viewer_origin) -> str | None`: the other lane's open or pending trade on this ticker, worded `⚠ <lane> plan also open on <TICKER> (<direction>, risk $X)`.
  - `append_overlap_field(embed, ticker, *, viewer_origin=None) -> None`, which never raises.

- [ ] **Step 1: Invoke `alert-surface`.** This adds a display-only field to the regular alert. It gates nothing, and the alert's numbers are untouched.

- [ ] **Step 2: Write the failing tests**

```python
# tests/scanning/test_lane_overlap.py
"""v144: each lane's alert shows the other lane's open plan on the ticker -- display only."""
import inspect

import discord

from swingbot.core.scanning import lane_overlap, scan_run, short_run
from swingbot.core.tracking.performance import TradeLog


def _open(log, ticker="AAPL", **kw):
    trade_id = log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                             confidence_level=3, confidence_label="Medium", entry=100.0,
                             stop_loss=98.0, take_profit=105.0, **kw)
    trade = log.get_trade_by_id(trade_id)
    trade["shares"] = 50
    log._db_upsert(trade)
    return trade_id


def test_no_other_lane_means_no_line():
    _open(TradeLog())
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None) is None


def test_the_outlook_card_names_the_regular_plan_and_its_dollar_risk():
    _open(TradeLog())
    assert lane_overlap.overlap_line("AAPL", viewer_origin="next_session") == \
        "⚠ regular plan also open on AAPL (bullish, risk $100)"


def test_the_regular_alert_names_the_outlook_plan():
    _open(TradeLog(), origin="next_session")
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None) == \
        "⚠ outlook plan also open on AAPL (bullish, risk $100)"


def test_unknown_shares_read_as_risk_na():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, origin="next_session"))
    trade["shares"] = None
    log._db_upsert(trade)
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None).endswith("(bullish, risk n/a)")


def test_append_adds_one_field_and_never_raises(monkeypatch):
    _open(TradeLog(), origin="next_session")
    embed = discord.Embed()
    lane_overlap.append_overlap_field(embed, "AAPL")
    assert [(f.name, f.value) for f in embed.fields] == [
        ("⚠ Overlap", "⚠ outlook plan also open on AAPL (bullish, risk $100)")]
    monkeypatch.setattr(lane_overlap, "_other_lane_trades", lambda *a: 1 / 0)
    quiet = discord.Embed()
    lane_overlap.append_overlap_field(quiet, "AAPL")
    assert quiet.fields == []


def test_both_regular_alert_builders_call_it():
    call = "lane_overlap.append_overlap_field(embed, result.ticker)"
    assert call in inspect.getsource(scan_run._sync_run_scan)
    assert call in inspect.getsource(short_run._alert_for)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_lane_overlap.py`
Expected: FAIL with `ImportError: cannot import name 'lane_overlap'`.

- [ ] **Step 4: Create `swingbot/core/scanning/lane_overlap.py`**

```python
"""v144: risk is surfaced, not prevented. When the other lane holds an open or
pending trade on the same ticker, an alert says so with that trade's dollar
risk, so the partner sees the combined exposure before placing a second order.
Display only: it gates, sizes and cancels nothing, and a failure renders no
field rather than breaking an alert. A pending stop-entry plan's placeholder
trade is "open", so "open or pending" is one query.
"""
from __future__ import annotations

import logging

from swingbot.core.tracking.origin import NEXT_SESSION, origin_of

log = logging.getLogger(__name__)

OVERLAP_FIELD = "⚠ Overlap"
_LANE_WORDS = {None: "regular", NEXT_SESSION: "outlook"}


def _other_lane_trades(ticker: str, viewer_origin: str | None) -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    trades = TradeLog().get_trades(status="open", ticker=ticker, limit=None) or []
    return [trade for trade in trades if origin_of(trade) != viewer_origin]


def _risk_text(trade: dict) -> str:
    shares, entry, stop = trade.get("shares"), trade.get("entry"), trade.get("stop_loss")
    if not shares or entry is None or stop is None:
        return "risk n/a"
    return f"risk ${float(shares) * abs(float(entry) - float(stop)):,.0f}"


def overlap_line(ticker: str, *, viewer_origin: str | None) -> str | None:
    try:
        others = _other_lane_trades(ticker, viewer_origin)
    except Exception:
        log.debug("overlap line unavailable for %s", ticker, exc_info=True)
        return None
    if not others:
        return None
    trade = others[0]
    lane = _LANE_WORDS.get(origin_of(trade), str(origin_of(trade)))
    return f"⚠ {lane} plan also open on {ticker} ({trade.get('direction')}, {_risk_text(trade)})"


def append_overlap_field(embed, ticker: str, *, viewer_origin: str | None = None) -> None:
    """Add the ⚠ Overlap field when the other lane is open on `ticker`."""
    line = overlap_line(ticker, viewer_origin=viewer_origin)
    if line:
        embed.add_field(name=OVERLAP_FIELD, value=line, inline=False)
```

- [ ] **Step 5: Wire the two regular builders.** Each gets one unconditional call and no branch. `_sync_run_scan` is F (100) and must not grow.
  1. `scan_run.py`: add `lane_overlap` to the `from . import analyze, dedup, fetch, ...` line (alphabetical, after `fetch`). Directly after the `embed = build_embed(item, explanation, perf_stats, warning, chart_filename, htf_info=item.htf_info, layout=config.ALERT_EMBED_LAYOUT)` statement, add `lane_overlap.append_overlap_field(embed, result.ticker)   # v144: display only`.
  2. `short_run.py`: add `lane_overlap` to the `from . import analyze, dedup, fetch, qualify, ...` line. In `_alert_for`, directly after its `embed = build_embed(...)` statement, add the same line.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_lane_overlap.py`, then `python scripts/dev/testrun.py file tests/scanning/test_short_alert_parity.py` and `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`.
Expected: all PASS.

- [ ] **Step 7: Complexity check and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/lane_overlap.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py`
Expected: `_sync_run_scan` still F (100); nothing new.

```bash
git add swingbot/core/scanning/lane_overlap.py swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py tests/scanning/test_lane_overlap.py
git commit -m "feat(v144): the display-only overlap line between the regular and outlook lanes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
