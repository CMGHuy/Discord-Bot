# v144 Next-session plans: Part 1, model and lifecycle

> Part of [`_0-index`](2026-10-09-v144-next-session-plans_0-index.md), which holds the header, the global constraints, the parallelisation map and the open-point answer. Read those first; they apply to every task here.

# Phase 1 — Model and lifecycle

### Task V144-1: Origin vocabulary, plan fields and trade `origin`

**Files:**
- Create: `swingbot/core/tracking/origin.py`
- Modify: `swingbot/core/planning/plan_types.py` (end of `TradePlanV2`, after `runner_path`)
- Modify: `swingbot/core/tracking/performance.py` (`TradeLog.log_trade` signature + `record`; `TradeLog.open_trade_for_ticker`)
- Modify: `swingbot/core/analytics/journal.py` (`build_entry` only)
- Test: `tests/tracking/test_origin.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `swingbot.core.tracking.origin`: `NEXT_SESSION = "next_session"`, `ORIGINS = (NEXT_SESSION,)`, `ALL = "all"`, `origin_of(record) -> str | None` (dict or object), `is_regular(record) -> bool`, `in_cohort(record, cohort: str | None) -> bool` (`None` = regular only, `ALL` = everything, else that origin).
  - `TradePlanV2.origin: str | None = None`, `TradePlanV2.valid_session: str | None = None` (ISO date), `TradePlanV2.cancel_reason_message: str | None = None`.
  - `TradeLog.log_trade(..., origin=None)` writes `record["origin"]`.
  - `TradeLog.open_trade_for_ticker(ticker, origin=None)`: matches only trades whose `origin` equals the argument (`None` = regular).
  - Journal entries carry `"origin"`.

- [ ] **Step 0: Create the worktree.** Invoke the `worktree-lifecycle` skill. Create branch and worktree `2026-10-09-v144-next-session-plans` under `.claude/worktrees/` from `main`. Every later step runs inside it. Invoke `schema-change` and read `docs/claude/schema-evolution.md` § "The four operations" (an **add** needs no migration).

- [ ] **Step 1: Write the failing tests**

```python
# tests/tracking/test_origin.py
"""v144: the origin vocabulary, the plan fields and the trade-level origin."""
from types import SimpleNamespace

import pytest

from swingbot.core.analytics.journal import build_entry
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.tracking import origin
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan


def test_vocabulary():
    assert origin.NEXT_SESSION == "next_session"
    assert origin.ORIGINS == ("next_session",)


@pytest.mark.parametrize("record,expected", [
    ({}, None), ({"origin": None}, None), ({"origin": "next_session"}, "next_session"),
    (SimpleNamespace(origin="next_session"), "next_session"), (SimpleNamespace(), None),
])
def test_origin_of_reads_dicts_and_objects(record, expected):
    assert origin.origin_of(record) == expected
    assert origin.is_regular(record) is (expected is None)


def test_in_cohort():
    regular, evening = {"id": "r"}, {"id": "e", "origin": "next_session"}
    assert [origin.in_cohort(r, None) for r in (regular, evening)] == [True, False]
    assert [origin.in_cohort(r, "next_session") for r in (regular, evening)] == [False, True]
    assert [origin.in_cohort(r, origin.ALL) for r in (regular, evening)] == [True, True]


def test_plan_fields_default_to_none_and_round_trip():
    plan = _plan()
    assert (plan.origin, plan.valid_session, plan.cancel_reason_message) == (None, None, None)
    plan.origin, plan.valid_session = "next_session", "2026-10-12"
    plan.cancel_reason_message = "No price data for 2026-10-12; plan expired unevaluated"
    back = plan_from_dict(plan_to_dict(plan))
    assert (back.origin, back.valid_session, back.cancel_reason_message) == (
        "next_session", "2026-10-12", plan.cancel_reason_message)


def _open(log, ticker="AAPL", **kw):
    return log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                         confidence_level=3, confidence_label="Medium", entry=100.0,
                         stop_loss=98.0, take_profit=105.0, **kw)


def test_log_trade_records_origin_and_defaults_to_regular():
    log = TradeLog()
    regular = log.get_trade_by_id(_open(log))
    evening = log.get_trade_by_id(_open(log, ticker="MSFT", origin="next_session"))
    assert regular["origin"] is None
    assert evening["origin"] == "next_session"


def test_open_trade_for_ticker_is_scoped_to_one_lane():
    log = TradeLog()
    evening_id = _open(log, origin="next_session")
    assert log.open_trade_for_ticker("AAPL") is None            # the regular lane sees no trade
    assert log.open_trade_for_ticker("AAPL", origin="next_session")["id"] == evening_id
    regular_id = _open(log)
    assert log.open_trade_for_ticker("AAPL")["id"] == regular_id
    assert log.open_trade_for_ticker("AAPL", origin="next_session")["id"] == evening_id


def test_journal_entry_copies_origin():
    trade = {"id": "t1", "ticker": "AAPL", "status": "win", "entry": 100.0, "stop_loss": 98.0,
             "exit_price": 104.0, "direction": "bullish", "origin": "next_session"}
    assert build_entry(trade, None)["origin"] == "next_session"
    trade.pop("origin")
    assert build_entry(trade, None)["origin"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/tracking/test_origin.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.tracking.origin'`.

- [ ] **Step 3: Create `swingbot/core/tracking/origin.py`**

```python
"""v144: which lane issued a plan or trade.

`origin` is frozen at creation, like `ledger`. `None` is the regular lane, and
every record written before v144 reads as regular because it has no key at all.
Every pooled figure (ExpR, win rate, the snapshot, the dashboard, the journal
overrides, the soak verdict) keeps to `is_regular`; a cohort view asks
`in_cohort(record, NEXT_SESSION)`. Pure: no imports, so planning, tracking,
analytics and the admin can all read it.
"""
from __future__ import annotations

NEXT_SESSION = "next_session"
ORIGINS = (NEXT_SESSION,)
ALL = "all"


def origin_of(record) -> str | None:
    """The origin of a trade/journal dict or a plan object; None = regular."""
    if isinstance(record, dict):
        return record.get("origin")
    return getattr(record, "origin", None)


def is_regular(record) -> bool:
    return origin_of(record) is None


def in_cohort(record, cohort: str | None) -> bool:
    """`cohort` None = the regular lane only; ALL = every record; else that origin."""
    if cohort == ALL:
        return True
    return origin_of(record) == cohort
```

- [ ] **Step 4: Add the three plan fields.** In `swingbot/core/planning/plan_types.py`, after the `runner_path: dict | None = None` line (the last field of `TradePlanV2`), add:

```python
    # v144: the lane that issued this plan (tracking/origin.py). None = the
    # regular lane; "next_session" = the 23:30 outlook. Frozen at creation.
    origin: str | None = None
    # v144: the one NYSE session (ISO date) an outlook plan may fill in. Set only
    # on outlook plans; PlanManager._eligible_session reads it first. Promoted to
    # a column (v144_001) for the per-session query.
    valid_session: str | None = None
    # v144: the one-line reason an outlook plan was cancelled (the catalogue
    # message in planning/session_expiry.py). None for every other plan.
    cancel_reason_message: str | None = None
```

- [ ] **Step 5: `log_trade` and `open_trade_for_ticker`.** In `swingbot/core/tracking/performance.py`:

  1. Change the last line of the `log_trade` signature from `risk_features=None, ledger=None, entry_context=None) -> str:` to `risk_features=None, ledger=None, entry_context=None, origin=None) -> str:`.
  2. In its `record = {...}` literal, directly after `"ledger": ledger or "main",  # v93: frozen at creation`, add one line: `"origin": origin,       # v144: None = regular lane; frozen at creation`. That is an unconditional key with no branch: `log_trade` is C(15) and must not grow.
  3. Replace the body of `open_trade_for_ticker` (keep the docstring and append one paragraph) with:

```python
    def open_trade_for_ticker(self, ticker: str, origin: str | None = None) -> dict | None:
        """...existing docstring, unchanged...

        v144: scoped to one lane. `origin` None (the default, every pre-v144
        caller) sees only regular trades, so an outlook trade never blocks or
        reverses a regular one; the outlook run passes "next_session".
        """
        return next(
            (t for t in self._all()
             if t["ticker"] == ticker and t["status"] == "open" and t.get("origin") == origin),
            None,
        )
```

- [ ] **Step 6: Journal copy.** In `swingbot/core/analytics/journal.py`, inside the dict that `build_entry` returns, after `"cohort_run_date": (trade.get("cohort_stats") or {}).get("run_date"),` add `"origin": trade.get("origin"),     # v144: copied, so pooled journal readers can drop the cohort`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/tracking/test_origin.py`
Expected: PASS.
Then run `python scripts/dev/testrun.py changed` to cover the other tests that reach `performance.py`, `plan_types.py` and `journal.py`. Expected: `0 failed`.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/tracking/origin.py swingbot/core/tracking/performance.py swingbot/core/analytics/journal.py`
Expected: `TradeLog.log_trade` still reports C (15). Nothing else new at C or worse.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/tracking/origin.py swingbot/core/planning/plan_types.py swingbot/core/tracking/performance.py swingbot/core/analytics/journal.py tests/tracking/test_origin.py
git commit -m "feat(v144): origin vocabulary, outlook plan fields, trade-level origin

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-2: Promote `plans.valid_session` (`v144_001`) and `PlanStore.for_session`

**Files:**
- Create: `swingbot/core/db/migrations/versions/v144_001_plans_valid_session.py`
- Modify: `swingbot/core/db/schema.py` (`plans` table, its promoted tuple, `PROMOTION_REASONS["plans"]`)
- Modify: `swingbot/core/db/repositories/plans.py` (`PlanRepository.for_session`)
- Modify: `swingbot/core/planning/plan_store.py` (`_normalised`, `_all`, `PlanStore.for_session`)
- Test: `tests/db/test_v144_valid_session.py`

**Interfaces:**
- Consumes: `TradePlanV2.valid_session` (V144-1).
- Produces:
  - `PlanRepository.for_session(valid_session: str, *, conn=None) -> list[dict]`, oldest `created_at` first.
  - `PlanStore.for_session(day) -> list[TradePlanV2]`; `day` is a `datetime.date` or an ISO string.

- [ ] **Step 1: Write the failing tests**

```python
# tests/db/test_v144_valid_session.py
"""v144: plans.valid_session is a promoted, indexed column with one reason."""
import datetime as dt

from swingbot.core.db import schema
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan


def _row(plan_id, valid_session=None, created_at="2026-10-09T21:30:00+00:00"):
    row = {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
           "status": PlanStatus.PENDING, "created_at": created_at}
    if valid_session is not None:
        row["valid_session"] = valid_session
    return row


def test_valid_session_is_a_nullable_indexed_promoted_column():
    table = schema.METADATA.tables["plans"]
    assert table.c.valid_session.nullable is True
    assert "valid_session" in schema.promoted_for("plans")
    assert "valid_session" in schema.PROMOTION_REASONS["plans"]
    assert any(index.name == "plans_valid_session_idx" for index in table.indexes)


def test_for_session_returns_only_that_sessions_plans_oldest_first(db_conn):
    repo = PlanRepository()
    repo.insert(_row("late", "2026-10-12", "2026-10-09T21:40:00+00:00"), conn=db_conn)
    repo.insert(_row("early", "2026-10-12", "2026-10-09T21:30:00+00:00"), conn=db_conn)
    repo.insert(_row("other", "2026-10-13"), conn=db_conn)
    repo.insert(_row("regular"), conn=db_conn)
    assert [r["plan_id"] for r in repo.for_session("2026-10-12", conn=db_conn)] == ["early", "late"]


def test_a_regular_row_reads_back_without_the_key(db_conn):
    repo = PlanRepository()
    repo.insert(_row("regular"), conn=db_conn)
    assert "valid_session" not in repo.get("regular", conn=db_conn)


def test_plan_store_for_session_accepts_a_date_or_a_string():
    store = PlanStore()
    store.add(_plan(plan_id="o1", origin="next_session", valid_session="2026-10-12"))
    store.add(_plan(plan_id="r1"))
    assert [p.plan_id for p in store.for_session(dt.date(2026, 10, 12))] == ["o1"]
    assert [p.plan_id for p in store.for_session("2026-10-12")] == ["o1"]
    assert store.get("o1").valid_session == "2026-10-12"
    assert store.get("r1").valid_session is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_v144_valid_session.py`
Expected: FAIL with `AttributeError` (no `valid_session` column).

- [ ] **Step 3: Declare the column in `swingbot/core/db/schema.py`.** In the `plans = register(sa.Table("plans", ...))` call:

  1. After `sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),` add `sa.Column("valid_session", sa.Text),`. Text, not Date: `plan_to_dict` writes the ISO string and the column hands it back unchanged, and ISO dates order lexically.
  2. After `sa.Index("plans_ticker_idx", "ticker"),` add `sa.Index("plans_valid_session_idx", "valid_session"),`.
  3. Change the promoted tuple to `("plan_id", "ticker", "strategy", "horizon_key", "status", "created_at", "valid_session"),`.
  4. In `PROMOTION_REASONS["plans"]`, after the `"created_at"` entry, add `"valid_session": "plans_valid_session_idx; the v144 wrap-up and outlook read one session's plans",`.

- [ ] **Step 4: Write the revision** `swingbot/core/db/migrations/versions/v144_001_plans_valid_session.py`:

```python
"""plans.valid_session: the v144 outlook plan's one NYSE session, indexed

A promote (docs/claude/schema-evolution.md): the column, a backfill from doc for
any row that already carries the field, and the index. The downgrade copies the
column back into doc before dropping it, so no value is lost either way.

Revision ID: v144_001
Revises: v116_002
"""
import sqlalchemy as sa
from alembic import op

revision = "v144_001"
down_revision = "v116_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plans", sa.Column("valid_session", sa.Text(), nullable=True))
    op.execute("UPDATE plans SET valid_session = doc->>'valid_session' "
               "WHERE doc ? 'valid_session' AND doc->>'valid_session' IS NOT NULL")
    op.create_index("plans_valid_session_idx", "plans", ["valid_session"])


def downgrade() -> None:
    op.execute("UPDATE plans SET doc = jsonb_set(doc, '{valid_session}', to_jsonb(valid_session)) "
               "WHERE valid_session IS NOT NULL")
    op.drop_index("plans_valid_session_idx", table_name="plans")
    op.drop_column("plans", "valid_session")
```

- [ ] **Step 5: The repository query.** In `swingbot/core/db/repositories/plans.py`, after `by_ticker`, add:

```python
    def for_session(self, valid_session: str, *, conn=None) -> list[dict]:
        """v144: every plan whose valid_session is this ISO date, oldest first."""
        return self.list_all(conn=conn, where=plans.c.valid_session == valid_session,
                             order_by=plans.c.created_at.asc())
```

- [ ] **Step 6: The store method.** In `swingbot/core/planning/plan_store.py`, pull the `created_at` normalisation out of `_all` into a module-level helper and reuse it:

```python
def _normalised(record: dict) -> dict:
    """A plans row with created_at as the ISO string TradePlanV2 stores."""
    if isinstance(record.get("created_at"), datetime):
        record["created_at"] = record["created_at"].isoformat()
    return record
```

`_all` becomes:

```python
    @staticmethod
    def _all() -> dict[str, dict]:
        """Map plan ids to records from the plans table."""
        from swingbot.core.db.repositories.plans import plans_repo
        return {record["plan_id"]: _normalised(record) for record in plans_repo().list_all()}
```

and add after `all`:

```python
    def for_session(self, day) -> list[TradePlanV2]:
        """v144: the outlook plans valid for one NYSE session (`day`: a date or
        an ISO string), oldest first. One indexed query, not a full scan."""
        from swingbot.core.db.repositories.plans import plans_repo
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        return [plan_from_dict(_normalised(record)) for record in plans_repo().for_session(key)]
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_v144_valid_session.py`, then `python scripts/dev/testrun.py file tests/db/test_migrations.py` (one head, `v144_001` id shape, migrations == `schema.py`), then `python scripts/dev/testrun.py file tests/db/test_schema_contract.py` and `python scripts/dev/testrun.py file tests/planning/test_plan_store_db.py`.
Expected: all PASS. Then `python -m alembic heads` prints `v144_001 (head)`.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v144_001_plans_valid_session.py swingbot/core/db/repositories/plans.py swingbot/core/planning/plan_store.py tests/db/test_v144_valid_session.py
git commit -m "feat(v144): promote plans.valid_session (v144_001) and PlanStore.for_session

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-3: The cancellation-reason classifier (`session_expiry`)

**Files:**
- Create: `swingbot/core/planning/session_expiry.py`
- Test: `tests/planning/test_session_expiry.py`

**Interfaces:**
- Consumes: `market.session.RTH_OPEN`, `US_MARKET_TZ`, `session_close`; `market.indicators.atr`.
- Produces:
  - Codes: `NEVER_TRIGGERED`, `NO_SESSION_DATA`, `INVALIDATED`, `RISK_CAP`.
  - Event detail keys: `REASON_CODE = "reason_code"`, `REASON_MESSAGE = "reason_message"`.
  - Types: `SessionBar(high, low, source)`, `Verdict(code, message)`.
  - Bar helpers: `hourly_session_bar(hourly, day) -> SessionBar | None`, `daily_session_bar(daily, day) -> SessionBar | None`, `session_bar(day, *, hourly, daily) -> SessionBar | None`, `atr_before(daily, day) -> float | None`.
  - Messages: `classify_expiry(plan, day, *, hourly, daily) -> Verdict`, `in_session_message(plan, transition, detail) -> str | None`, `code_for(transition) -> str | None`.
  - Reader: `cancel_reason(plan) -> str | None`, the reason on the plan's CANCELLED transition. V144-7's cohort report and V144-10's wrap-up both read it.

- [ ] **Step 1: Invoke `no-lookahead`.** The classifier reads D's own bars only after D has closed; the ATR is taken from bars strictly before D.

- [ ] **Step 2: Write the failing tests**

```python
# tests/planning/test_session_expiry.py
"""v144: an outlook plan's cancellation reason, from session D's own bars."""
import datetime as dt

import pandas as pd

from swingbot.core.planning import session_expiry as se
from tests.planning.test_plan_engine_model import _plan

D = dt.date(2026, 10, 12)          # Monday, full session, EDT (UTC-4)
HALF = dt.date(2026, 11, 27)       # Friday after Thanksgiving, 13:00 ET close


def _bull(**kw):
    base = dict(source="confluence", entry_type="stop_entry", direction="bullish",
                trigger_price=102.0, stop_loss=100.5, tp1=106.0, origin="next_session",
                valid_session=D.isoformat(), created_at="2026-10-09")
    base.update(kw)
    return _plan(**base)


def _daily(d_high=101.40, d_low=100.80, last=D):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=20)
    rows = [(100.0, 100.75, 99.25, 100.0, 1e6)] * 19 + [(101.0, d_high, d_low, 101.2, 1e6)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=days)


def _hourly(day, last_utc_hour, high=101.10, low=100.90):
    starts = pd.date_range(f"{day} 13:30", f"{day} {last_utc_hour}", freq="h", tz="UTC")
    return pd.DataFrame({"Open": 101.0, "High": high, "Low": low, "Close": 101.0, "Volume": 1e5},
                        index=starts)


def test_hourly_bar_is_used_only_when_it_reaches_the_last_rth_hour():
    full = _hourly(D, "19:30")                      # 15:30 ET start: covers the close
    assert se.hourly_session_bar(full, D) == se.SessionBar(101.10, 100.90, "hourly")
    partial = _hourly(D, "17:30")                   # 13:30 ET: the 4h refresh window
    assert se.hourly_session_bar(partial, D) is None
    assert se.hourly_session_bar(None, D) is None


def test_half_day_coverage_is_judged_against_the_1300_close():
    assert se.hourly_session_bar(_hourly(HALF, "17:30"), HALF) is not None   # 12:30 ET (EST, UTC-5)


def test_session_bar_falls_back_to_the_daily_bar_then_to_nothing():
    daily = _daily()
    assert se.session_bar(D, hourly=_hourly(D, "17:30"), daily=daily) == se.SessionBar(101.40, 100.80, "daily")
    assert se.session_bar(D, hourly=None, daily=_daily(last=D - dt.timedelta(days=3))) is None
    assert se.session_bar(D, hourly=None, daily=None) is None


def test_atr_comes_from_bars_strictly_before_d():
    assert abs(se.atr_before(_daily(), D) - 1.5) < 1e-6


def test_never_triggered_states_the_distance_in_percent_and_atr():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=_daily())
    assert verdict == se.Verdict(se.NEVER_TRIGGERED,
                                 "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger")


def test_a_short_reads_the_low():
    plan = _bull(direction="bearish", trigger_price=98.0, stop_loss=99.5, tp1=94.0)
    verdict = se.classify_expiry(plan, D, hourly=None, daily=_daily(d_high=99.4, d_low=98.6))
    assert verdict.message == "Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger"


def test_a_reach_the_polls_missed_still_says_what_happened():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=_daily(d_high=102.05))
    assert verdict.code == se.NEVER_TRIGGERED
    assert verdict.message == "High 102.05 reached the 102.00 trigger between polls; no live print filled it"


def test_no_atr_drops_the_atr_clause():
    hourly = _hourly(D, "19:30", high=101.40)
    verdict = se.classify_expiry(_bull(), D, hourly=hourly, daily=None)
    assert verdict.message == "High 101.40 stopped 0.6% short of the 102.00 trigger"


def test_no_bar_at_all_is_no_session_data():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=None)
    assert verdict == se.Verdict(se.NO_SESSION_DATA,
                                 "No price data for 2026-10-12; plan expired unevaluated")


def test_in_session_messages_and_codes():
    plan = _bull()
    assert se.in_session_message(plan, "cancelled_invalidated", {"live_price": 100.4}) == \
        "Traded 100.40 through the 100.50 stop before triggering; the setup broke"
    gap = {"entry_price": 104.1, "stop_loss": 100.5, "planned_loss_pct": 3.4582, "max_planned_loss_pct": 2.0}
    assert se.in_session_message(plan, "cancelled_risk_cap", gap) == \
        "Gapped to 104.10 past the 102.00 trigger; the stop distance (3.5%) is over the 2% cap"
    touch = dict(gap, entry_price=102.0, planned_loss_pct=2.4)
    assert se.in_session_message(plan, "cancelled_risk_cap", touch).startswith("Triggered at 102.00;")
    assert se.in_session_message(plan, "filled", {}) is None
    assert se.in_session_message(plan, "cancelled_expired", {}) is None
    assert (se.code_for("cancelled_invalidated"), se.code_for("cancelled_risk_cap"),
            se.code_for("filled")) == (se.INVALIDATED, se.RISK_CAP, None)


def test_cancel_reason_reads_the_cancelled_transition():
    plan = _bull()
    assert se.cancel_reason(plan) is None
    plan.status_history = [{"status": "CANCELLED", "reason": "never_triggered", "at": "x"}]
    assert se.cancel_reason(plan) == "never_triggered"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_session_expiry.py`
Expected: FAIL with `ImportError` (no `session_expiry`).

- [ ] **Step 4: Write `swingbot/core/planning/session_expiry.py`**

```python
"""v144: why an outlook (next_session) plan was cancelled, in one line.

Two cancellations happen DURING session D through the existing live transitions
(cancelled_invalidated, cancelled_risk_cap); `in_session_message` only words
them. Two are decided AT D's close by `classify_expiry`, from D's own bars:
`never_triggered` (the common case, with the distance in percent and ATR) and
`no_session_data`.

Data source at close. The hourly cache cannot be trusted to be fresh:
market_data_refresh wakes every MARKET_DATA_REFRESH_MINUTES and
data_refresh.is_stale uses the file mtime against a 4h hourly window, so the
CSV can miss D's last bars. `hourly_session_bar` is used only when it reaches
D's last RTH hour; otherwise D's daily bar (RTH-only, so its high/low is the
RTH extreme). NO-LOOKAHEAD: this runs after D closed, and the ATR is read from
bars strictly before D.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pandas as pd

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, session_close

NEVER_TRIGGERED = "never_triggered"
NO_SESSION_DATA = "no_session_data"
INVALIDATED = "invalidated"
RISK_CAP = "risk_cap"

REASON_CODE = "reason_code"
REASON_MESSAGE = "reason_message"

_IN_SESSION_CODES = {"cancelled_invalidated": INVALIDATED, "cancelled_risk_cap": RISK_CAP}
_ATR_PERIOD = 14


@dataclass(frozen=True)
class SessionBar:
    high: float
    low: float
    source: str          # "hourly" | "daily"


@dataclass(frozen=True)
class Verdict:
    code: str
    message: str


def _et_index(frame) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")      # the hourly cache is written in UTC
    return index.tz_convert(US_MARKET_TZ)


def hourly_session_bar(hourly, day: dt.date) -> SessionBar | None:
    """D's RTH high/low from hourly bars, or None unless the bars reach D's
    last RTH hour (a bar starting within an hour of D's official close)."""
    if hourly is None or len(hourly) == 0:
        return None
    index = _et_index(hourly)
    open_at = dt.datetime.combine(day, RTH_OPEN, tzinfo=US_MARKET_TZ)
    close_at = dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)
    mask = (index >= open_at) & (index < close_at)
    if not mask.any() or index[mask].max() < close_at - dt.timedelta(hours=1):
        return None
    rows = hourly.loc[mask]
    return SessionBar(float(rows["High"].max()), float(rows["Low"].min()), "hourly")


def daily_session_bar(daily, day: dt.date) -> SessionBar | None:
    """D's daily bar (RTH-only), or None when the frame has no row dated D."""
    if daily is None or len(daily) == 0:
        return None
    rows = daily.loc[pd.DatetimeIndex(daily.index).date == day]
    if len(rows) == 0:
        return None
    return SessionBar(float(rows["High"].iloc[-1]), float(rows["Low"].iloc[-1]), "daily")


def session_bar(day: dt.date, *, hourly, daily) -> SessionBar | None:
    return hourly_session_bar(hourly, day) or daily_session_bar(daily, day)


def atr_before(daily, day: dt.date) -> float | None:
    """ATR(14) on the bars strictly before D; None when there are too few."""
    from swingbot.core.market.indicators import atr
    if daily is None or len(daily) == 0:
        return None
    prior = daily.loc[pd.DatetimeIndex(daily.index).date < day]
    if len(prior) <= _ATR_PERIOD:
        return None
    value = float(atr(prior, _ATR_PERIOD).iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def _never_triggered_message(plan, bar: SessionBar, atr_value: float | None) -> str:
    bull = plan.direction == "bullish"
    word, extreme = ("High", bar.high) if bull else ("Low", bar.low)
    trigger = float(plan.trigger_price)
    gap = (trigger - extreme) if bull else (extreme - trigger)
    if gap <= 0:
        return (f"{word} {extreme:.2f} reached the {trigger:.2f} trigger between polls; "
                "no live print filled it")
    atr_part = f" ({gap / atr_value:.1f} ATR)" if atr_value else ""
    return f"{word} {extreme:.2f} stopped {gap / trigger * 100:.1f}%{atr_part} short of the {trigger:.2f} trigger"


def classify_expiry(plan, day: dt.date, *, hourly, daily) -> Verdict:
    """The close-time reason for an outlook plan still PENDING at D's close."""
    bar = session_bar(day, hourly=hourly, daily=daily)
    if bar is None:
        return Verdict(NO_SESSION_DATA, f"No price data for {day.isoformat()}; plan expired unevaluated")
    return Verdict(NEVER_TRIGGERED, _never_triggered_message(plan, bar, atr_before(daily, day)))


def _risk_cap_message(plan, detail: dict) -> str:
    fill, trigger = float(detail["entry_price"]), float(plan.trigger_price)
    lead = (f"Gapped to {fill:.2f} past the {trigger:.2f} trigger" if abs(fill - trigger) > 1e-9
            else f"Triggered at {fill:.2f}")
    return (f"{lead}; the stop distance ({float(detail['planned_loss_pct']):.1f}%) "
            f"is over the {float(detail['max_planned_loss_pct']):g}% cap")


def in_session_message(plan, transition: str, detail: dict) -> str | None:
    """Words for the two in-session cancellations; None for anything else."""
    if transition == "cancelled_invalidated":
        return (f"Traded {float(detail['live_price']):.2f} through the {float(plan.stop_loss):.2f} "
                "stop before triggering; the setup broke")
    if transition == "cancelled_risk_cap":
        return _risk_cap_message(plan, detail)
    return None


def code_for(transition: str) -> str | None:
    return _IN_SESSION_CODES.get(transition)


def cancel_reason(plan) -> str | None:
    """The reason recorded on the plan's CANCELLED transition, or None."""
    return next((entry.get("reason") for entry in reversed(plan.status_history or [])
                 if entry.get("status") == "CANCELLED"), None)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_session_expiry.py`
Expected: PASS. If `test_atr_comes_from_bars_strictly_before_d` is off by a smoothing artefact, read `swingbot/core/market/indicators.py:atr`. The fixture's true range is a constant 1.5 on every prior bar, so any ATR definition returns 1.5. A mismatch means `prior` is wrong, not the fixture.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/planning/session_expiry.py`
Expected: no output (every function is below C).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/session_expiry.py tests/planning/test_session_expiry.py
git commit -m "feat(v144): session_expiry -- the outlook plan's cancellation reason from D's bars

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-4: Generalise the one-session window to outlook plans

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py`:
  - imports
  - `_eligible_session` (line ~255)
  - new `_has_session_window` and `_cached_hourly`
  - `PlanManager.__init__`
  - `_step` (line ~662)
  - `_compression_window` → `_session_window` (line ~685), plus `_expire_window` and `_window_reason`
  - `_step_pending` (line ~714)
  - new `_annotate_outlook` and `_frame_or_none`
  - `_on_event`'s `log_trade(...)` call
  - `_manager()`
- Test: `tests/planning/test_next_session_window.py`

**Interfaces:**
- Consumes: V144-1 (`origin`, `valid_session`, `cancel_reason_message`, `NEXT_SESSION`). V144-3 (`classify_expiry`, `in_session_message`, `code_for`, `REASON_CODE`, `REASON_MESSAGE`).
- Produces:
  - `PlanManager(..., hourly_frame_fn=None)`: `ticker -> hourly DataFrame | None`, disk only.
  - Outlook expiry: `status_history` reason = catalogue code, and the `cancelled_expired` detail carries `reason_code` / `reason_message`. In-session invalidated/risk_cap events of outlook plans gain the same two keys.
  - `plan.cancel_reason_message` is set on every outlook cancellation.

- [ ] **Step 1: Invoke `no-lookahead`.** Re-read `_compression_window`'s docstring. The window behaviour (pre-open prints never fill, at-least-once expiry, `expires_at` = the real close) is reused unchanged.

- [ ] **Step 2: Write the failing tests**

```python
# tests/planning/test_next_session_window.py
"""v144: an outlook plan rests for exactly its valid_session (RTH open to the
official close, computed in ET) and is cancelled with a catalogue reason.
Regular plans and the compression short are untouched."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
D = dt.date(2026, 10, 12)


def _outlook(**kw):
    base = dict(plan_id="o1", source="confluence", entry_type="stop_entry", direction="bullish",
                trigger_price=102.0, stop_loss=100.5, tp1=106.0, tp2=None, expiry_bars=5,
                created_at="2026-10-09", origin="next_session", valid_session=D.isoformat())
    base.update(kw)
    return _plan(**base)


def _daily(d_high=101.40):
    days = pd.bdate_range(end=pd.Timestamp(D), periods=20)
    rows = [(100.0, 100.75, 99.25, 100.0, 1e6)] * 19 + [(101.0, d_high, 100.8, 101.2, 1e6)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=days)


def _poll(price, when, plan=None, daily=None):
    store = PlanStore()
    store.add(plan or _outlook())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", price)]).get_price,
                      daily_frame_fn=lambda t: daily, hourly_frame_fn=lambda t: None)
    events = mgr.poll(now=when)
    return store.get((plan or _outlook()).plan_id), events


def test_a_pre_open_print_through_the_trigger_never_fills():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 12, 9, 0, tzinfo=ET))
    assert plan.status == PlanStatus.PENDING and events == []


def test_the_day_before_d_never_fills():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 9, 15, 0, tzinfo=ET))
    assert plan.status == PlanStatus.PENDING and events == []


def test_an_rth_print_through_the_trigger_fills():
    plan, events = _poll(102.3, dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    assert plan.status == PlanStatus.ACTIVE and plan.entry_price == 102.3
    assert [e.transition for e in events] == ["filled"]


def test_after_the_close_it_is_cancelled_never_triggered_with_the_distance():
    plan, events = _poll(101.0, dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET), daily=_daily())
    assert plan.status == PlanStatus.CANCELLED
    assert plan.status_history[-1]["reason"] == "never_triggered"
    assert plan.status_history[-1]["at"] == "2026-10-12T16:00:00-04:00"   # the real close
    message = "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger"
    assert plan.cancel_reason_message == message
    (event,) = events
    assert event.transition == "cancelled_expired"
    assert event.detail["reason_code"] == "never_triggered" and event.detail["reason_message"] == message
    assert event.detail["eligible_session"] == "2026-10-12" and event.detail["cancel_resting_order"] is True


def test_no_bar_for_d_is_no_session_data():
    plan, _ = _poll(101.0, dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET), daily=None)
    assert plan.status_history[-1]["reason"] == "no_session_data"


def test_a_late_poll_the_next_morning_still_records_the_real_close():
    plan, _ = _poll(101.0, dt.datetime(2026, 10, 13, 8, 30, tzinfo=ET), daily=_daily())
    assert plan.status_history[-1]["at"] == "2026-10-12T16:00:00-04:00"


def test_a_filled_outlook_plan_is_not_cancelled_at_the_close():
    store = PlanStore()
    store.add(_outlook())
    feed = FakePriceFeed([("AAPL", 102.3), ("AAPL", 103.0)])
    mgr = PlanManager(store, feed.get_price, daily_frame_fn=lambda t: _daily(), hourly_frame_fn=lambda t: None)
    mgr.poll(now=dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    mgr.poll(now=dt.datetime(2026, 10, 12, 16, 5, tzinfo=ET))
    assert store.get("o1").status == PlanStatus.ACTIVE


def test_invalidated_in_session_carries_its_message():
    plan, events = _poll(100.4, dt.datetime(2026, 10, 12, 11, 0, tzinfo=ET))
    assert plan.status_history[-1]["reason"] == "invalidated"
    assert events[0].detail["reason_code"] == "invalidated"
    assert plan.cancel_reason_message == \
        "Traded 100.40 through the 100.50 stop before triggering; the setup broke"


def test_risk_cap_at_the_fill_carries_its_message():
    plan, events = _poll(103.0, dt.datetime(2026, 10, 12, 9, 31, tzinfo=ET))
    assert plan.status_history[-1]["reason"] == "risk_cap"
    assert events[0].detail["reason_message"].startswith("Gapped to 103.00 past the 102.00 trigger;")


def test_a_half_day_closes_at_1300_et():
    half = dict(valid_session="2026-11-27", created_at="2026-11-25")
    open_plan, _ = _poll(101.0, dt.datetime(2026, 11, 27, 12, 30, tzinfo=ET), plan=_outlook(**half))
    assert open_plan.status == PlanStatus.PENDING
    shut, _ = _poll(101.0, dt.datetime(2026, 11, 27, 13, 5, tzinfo=ET), plan=_outlook(plan_id="o2", **half))
    assert shut.status == PlanStatus.CANCELLED
    assert shut.status_history[-1]["at"] == "2026-11-27T13:00:00-05:00"


def test_the_dst_mismatch_week_opens_at_1430_berlin():
    week = dict(valid_session="2027-03-15", created_at="2027-03-12")
    early, _ = _poll(102.3, dt.datetime(2027, 3, 15, 14, 25, tzinfo=BERLIN), plan=_outlook(**week))
    assert early.status == PlanStatus.PENDING
    filled, _ = _poll(102.3, dt.datetime(2027, 3, 15, 14, 35, tzinfo=BERLIN), plan=_outlook(plan_id="o2", **week))
    assert filled.status == PlanStatus.ACTIVE


def _regular():
    return _plan(plan_id="r1", source="confluence", entry_type="stop_entry", direction="bullish",
                 trigger_price=102.0, stop_loss=100.5, tp1=106.0, tp2=None, created_at="2026-10-09")


@pytest.mark.parametrize("with_outlook", [False, True])
def test_a_regular_plan_steps_identically_beside_an_outlook_plan(with_outlook):
    store = PlanStore()
    store.add(_regular())
    if with_outlook:
        store.add(_outlook())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 102.3)]).get_price,
                      daily_frame_fn=lambda t: None, hourly_frame_fn=lambda t: None)
    events = mgr.poll(now=dt.datetime(2026, 10, 12, 10, 0, tzinfo=ET))
    regular = store.get("r1")
    assert [(e.transition, e.detail) for e in events if e.plan_id == "r1"] == \
        [("filled", {"entry_price": 102.3, "live_price": 102.3})]
    assert (regular.status, regular.entry_price, regular.cancel_reason_message) == (PlanStatus.ACTIVE, 102.3, None)


def test_a_regular_plan_keeps_its_bar_count_expiry():
    store = PlanStore()
    store.add(_regular())
    mgr = PlanManager(store, FakePriceFeed([("AAPL", 101.0)]).get_price, bar_count_fn=lambda t, c: 6)
    (event,) = mgr.poll(now=dt.datetime(2026, 10, 19, 10, 0, tzinfo=ET))
    assert event.transition == "cancelled_expired" and event.detail == {"bars_waited": 6}
    assert store.get("r1").status_history[-1]["reason"] == "expired"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_next_session_window.py`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'hourly_frame_fn'`.

- [ ] **Step 4: Imports.** In `plan_manager.py`, change `from datetime import datetime, timedelta, timezone` to `from datetime import date, datetime, timedelta, timezone`, and add after the `plan_types` import:

```python
from swingbot.core.planning import session_expiry
from swingbot.core.tracking.origin import NEXT_SESSION
```

- [ ] **Step 5: `_eligible_session` reads `valid_session` first.** Replace the function with:

```python
def _eligible_session(plan: TradePlanV2):
    """The one NYSE session (a date) that may fill a resting one-session plan.

    v144: an outlook plan names it (`valid_session`, an ISO date). Otherwise
    v119's compression rule: the first session strictly after the signal day. A
    date-only ``created_at`` is stored as UTC midnight, so midnight (read in UTC,
    whatever offset the database session handed it back in) is that calendar
    date; any other stamp is converted to its ET date. None when a stamp is
    unreadable or the calendar ends first (the caller then falls back to the
    normal path)."""
    if plan.valid_session is not None:
        try:
            return date.fromisoformat(str(plan.valid_session))
        except ValueError:
            return None
    try:
        created = datetime.fromisoformat(str(plan.created_at))
    except ValueError:
        return None
    if created.tzinfo is None:
        signal_day = created.date()
    else:
        utc = created.astimezone(timezone.utc)
        signal_day = utc.date() if utc.time() == datetime.min.time() \
            else created.astimezone(US_MARKET_TZ).date()
    return nyse_calendar().next_session(signal_day)


def _has_session_window(plan: TradePlanV2) -> bool:
    """v144: a plan that rests for one named session -- an outlook plan, or the
    v119 compression short. Every other plan keeps its bar-count expiry."""
    return plan.valid_session is not None or plan.strategy == COMPRESSION_SHORT


def _cached_hourly(ticker):
    """v144: the hourly cache on disk (never a fetch); session_expiry judges coverage."""
    from swingbot.core.marketdata.data_store import load_from_disk
    return load_from_disk(ticker, "hourly")
```

- [ ] **Step 6: The constructor.** Add `hourly_frame_fn=None` as the last keyword of `PlanManager.__init__` (after `runner_bars_fn=None`), and at the end of its body:

```python
        # v144: ticker -> hourly bars from disk, for the outlook expiry reason
        # (session_expiry). None = hourly unused, the daily bar decides.
        self.hourly_frame_fn = hourly_frame_fn
```

- [ ] **Step 7: `_step` annotates outlook cancellations.** In `_step`, change `return self._step_pending(plan, price, now)` to `return self._annotate_outlook(plan, self._step_pending(plan, price, now))`.

- [ ] **Step 8: Replace `_compression_window` with `_session_window` and two helpers.** Delete `_compression_window` (no test or other module references it: `git grep -n _compression_window` shows only `plan_manager.py`) and add in its place:

```python
    def _session_window(self, plan: TradePlanV2, now) -> list[PlanEvent] | None:
        """v119, generalised in v144: a resting one-session plan (an outlook plan
        or the compression short) lives for exactly its eligible session, counted
        on the session calendar. None = the session is open, run the normal fill
        checks; a list (maybe empty) = nothing further to do this poll.

        The window ends at the session's official close (13:00 ET on a half-day,
        see session_close). Delivery of the expiry is at-least-once and may be
        delayed to the next poll that runs with a price (quiet hours or a missing
        quote); ``expires_at`` still records the real close. The plan turns
        CANCELLED on that poll, so the event is emitted once, and the pending
        notice is re-sent until acknowledged."""
        eligible = _eligible_session(plan)
        if eligible is None:
            return None
        et = now_et(now)
        close = session_close(eligible)
        if et.date() < eligible or (et.date() == eligible and et.time() < RTH_OPEN):
            return []                    # same-bar / pre-open prints never fill
        if et.date() == eligible and et.time() < close:
            return None
        return self._expire_window(plan, eligible, close)

    def _expire_window(self, plan: TradePlanV2, eligible, close) -> list[PlanEvent]:
        closed_at = datetime.combine(eligible, close, tzinfo=US_MARKET_TZ).isoformat()
        reason, extra = self._window_reason(plan, eligible)
        record_transition(plan, PlanStatus.CANCELLED, reason=reason, at=closed_at)
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "cancelled_expired", {
            "bars_waited": 1, "cancel_resting_order": True,
            "eligible_session": eligible.isoformat(), "expires_at": closed_at, **extra})]

    def _window_reason(self, plan: TradePlanV2, eligible) -> tuple[str, dict]:
        """("expired", {}) for the compression short, unchanged; for an outlook
        plan the session_expiry verdict from D's own bars."""
        if plan.origin != NEXT_SESSION:
            return "expired", {}
        verdict = session_expiry.classify_expiry(
            plan, eligible, hourly=self._frame_or_none(self.hourly_frame_fn, plan.ticker),
            daily=self._frame_or_none(self.daily_frame_fn, plan.ticker))
        plan.cancel_reason_message = verdict.message
        return verdict.code, {session_expiry.REASON_CODE: verdict.code,
                              session_expiry.REASON_MESSAGE: verdict.message}

    @staticmethod
    def _frame_or_none(fn, ticker):
        if fn is None:
            return None
        try:
            return fn(ticker)
        except Exception:
            log.debug("outlook expiry: no frame for %s", ticker, exc_info=True)
            return None

    def _annotate_outlook(self, plan: TradePlanV2, events: list[PlanEvent]) -> list[PlanEvent]:
        """v144: an outlook plan's in-session cancellation (invalidated / risk_cap)
        gains its catalogue code and message, on the event and the plan."""
        if plan.origin != NEXT_SESSION:
            return events
        for event in events:
            message = session_expiry.in_session_message(plan, event.transition, event.detail)
            if message is None:
                continue
            plan.cancel_reason_message = message
            event.detail[session_expiry.REASON_CODE] = session_expiry.code_for(event.transition)
            event.detail[session_expiry.REASON_MESSAGE] = message
            self.store.update(plan)
        return events
```

- [ ] **Step 9: `_step_pending` asks for any session window.** Replace its first branch:

```python
        if plan.strategy == COMPRESSION_SHORT:
            window = self._compression_window(plan, now)
            if window is not None:
                return window
        elif self.bar_count_fn is not None:
```

with:

```python
        if _has_session_window(plan):
            window = self._session_window(plan, now)
            if window is not None:
                return window
        elif self.bar_count_fn is not None:
```

Leave the rest of `_step_pending` byte-identical. A regular plan has neither `valid_session` nor the compression strategy, so it takes the unchanged `elif` path.

- [ ] **Step 10: Pass the origin when `_on_event` logs a fill with no placeholder.** In `_on_event`, in the `self.trade_log.log_trade(...)` call, after `risk_features=plan.risk_features` add `, origin=plan.origin`. That is a keyword pass-through only: `_on_event` is C(15).

- [ ] **Step 11: Wire the production manager.** In `_manager()`, add `hourly_frame_fn=_cached_hourly` to the `PlanManager(...)` call, after `runner_bars_fn=rp.cached_daily_bars`.

- [ ] **Step 12: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_next_session_window.py`
Expected: PASS.
Then, unedited, the v119 suites: `python scripts/dev/testrun.py file tests/planning/test_compression_short_fill.py` and `python scripts/dev/testrun.py file tests/planning/test_compression_time_exit.py`. Expected: PASS without any test edit.
Then `python scripts/dev/testrun.py changed`. Expected: `0 failed`.

- [ ] **Step 13: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py`
Expected:
- `_step_pending` is still B (10).
- `_on_event` is still C (15).
- `_session_window`, `_expire_window`, `_window_reason`, `_annotate_outlook`, `_frame_or_none` and `_eligible_session` do not appear at C.
- The other C/D lines are the pre-existing ones (`_step_active`, `poll`, `_feed_bookkeeping`, `_step_partial`, `_check_bar_active`).

- [ ] **Step 14: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_next_session_window.py
git commit -m "feat(v144): one-session window for outlook plans, with catalogue cancel reasons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V144-5: Cancel notices state the catalogue reason

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (new `_outlook_cancel_fields`, `_fields_for`; `build_plan_event_embed` uses `_fields_for`)
- Modify: `swingbot/core/presentation/instructions.py` (`instruction_for`'s cancel branch)
- Test: `tests/scanning/test_outlook_cancel_notices.py`

**Interfaces:**
- Consumes: `session_expiry.REASON_CODE`, `REASON_MESSAGE` (V144-3).
- Produces: every cancel notice whose event detail carries `reason_message` shows that message as its "Why". A detail without the key renders byte-identically to today.

- [ ] **Step 1: Invoke `alert-surface`.**

- [ ] **Step 2: Write the failing tests**

```python
# tests/scanning/test_outlook_cancel_notices.py
"""v144: an outlook plan's cancel notice says why, in the catalogue's words."""
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.scanning.lifecycle_embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

MESSAGE = "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger"


def _outlook():
    return _plan(source="confluence", entry_type="stop_entry", trigger_price=102.0, stop_loss=100.5,
                 tp1=106.0, tp2=None, status="CANCELLED", origin="next_session", valid_session="2026-10-12")


def _expired(**extra):
    return PlanEvent("p1", "cancelled_expired", {
        "bars_waited": 1, "cancel_resting_order": True, "eligible_session": "2026-10-12",
        "expires_at": "2026-10-12T16:00:00-04:00", **extra})


def _why(embed):
    return next(field.value for field in embed.fields if field.name == "Why")


def test_the_feed_instruction_quotes_the_reason():
    event = _expired(reason_code="never_triggered", reason_message=MESSAGE)
    assert ins.instruction_for(_outlook(), event).lines == (MESSAGE,)


def test_the_lifecycle_embed_quotes_the_reason_and_code():
    event = _expired(reason_code="never_triggered", reason_message=MESSAGE)
    assert _why(build_plan_event_embed(_outlook(), event)) == f"{MESSAGE} (never_triggered)"


def test_an_in_session_cancel_uses_it_too():
    event = PlanEvent("p1", "cancelled_invalidated", {
        "live_price": 100.4, "reason_code": "invalidated",
        "reason_message": "Traded 100.40 through the 100.50 stop before triggering; the setup broke"})
    assert _why(build_plan_event_embed(_outlook(), event)).endswith("(invalidated)")


def test_a_regular_expiry_renders_as_before():
    plan = _plan(entry_type="stop_entry", trigger_price=102.0, expiry_bars=5, status="CANCELLED")
    event = PlanEvent("p1", "cancelled_expired", {"bars_waited": 6})
    assert ins.instruction_for(plan, event).lines == ("not triggered within 5 sessions",)
    assert _why(build_plan_event_embed(plan, event)).startswith("Never triggered — 6 bar(s) waited")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_cancel_notices.py`
Expected: FAIL. The first test gets `('not triggered within 5 sessions',)`, and the lifecycle `Why` starts with `Never triggered`.

- [ ] **Step 4: The feed instruction.** In `instruction_for`, the cancel branch begins:

```python
    if transition in ("cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap"):
        if short_notice.is_compression(plan) and transition != "cancelled_invalidated":
```

Change the inner `if` to a check on the stated reason first:

```python
    if transition in ("cancelled_expired", "cancelled_invalidated", "cancelled_risk_cap"):
        if detail.get("reason_message"):
            why = detail["reason_message"]          # v144: an outlook plan states its reason
        elif short_notice.is_compression(plan) and transition != "cancelled_invalidated":
```

The remaining `elif`/`else` arms are unchanged. `instruction_for` goes from C (12) to C (13).

- [ ] **Step 5: The lifecycle embed.** In `lifecycle_embeds.py`, after `_risk_cap_fields`, add:

```python
def _outlook_cancel_fields(embed, plan, d) -> None:
    """v144: an outlook plan's cancellation, in the catalogue's words and code."""
    embed.description = plan_levels_block(plan, plan.trigger_price)
    embed.add_field(name="Why", value=f"{d['reason_message']} ({d['reason_code']})", inline=False)
```

After the `_EVENT_FIELDS = {...}` dict, add:

```python
def _fields_for(event):
    """The field builder for one event: a stated reason (v144) wins."""
    if event.detail.get("reason_message"):
        return _outlook_cancel_fields
    return _EVENT_FIELDS.get(event.transition)
```

In `build_plan_event_embed`, change `fields = _EVENT_FIELDS.get(event.transition)` to `fields = _fields_for(event)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_outlook_cancel_notices.py`, then `python scripts/dev/testrun.py file tests/presentation/test_instructions.py`, `python scripts/dev/testrun.py file tests/scanning/test_lifecycle_push.py` and `python scripts/dev/testrun.py file tests/scanning/test_compression_instructions.py`.
Expected: all PASS.

- [ ] **Step 7: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/presentation/instructions.py swingbot/core/scanning/lifecycle_embeds.py`
Expected: `instruction_for` reports C (13), and nothing new appears.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py swingbot/core/presentation/instructions.py tests/scanning/test_outlook_cancel_notices.py
git commit -m "feat(v144): outlook cancel notices state the catalogue reason

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
