# Scaled-out leg accounting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-v79-scaled-out-leg-accounting-design.md`

**Goal:** Make a scaled-out (TP1 + runner) position's two legs count and
display as two separate outcomes everywhere the app lists or counts trades,
without changing the single-ledger-record storage model or what gates real
open-position management.

**Architecture:** One new shared function per module — `expand_trade_legs`
in `performance.py` for stats, `_expand_plan_row`/`_row_from_leg` in
`trades.py` for the admin API's row list — both derive leg-rows at read
time from the existing `legs`/`legs_realized` arrays already on the ledger
record and the plan. No schema change, no migration. A small, separately
useful fix (still-open rows showing their true remaining share count)
lands alongside it in `_attach_unrealized_pnl`.

**Tech Stack:** Python 3.11 / Flask (backend), Angular 21 / `@ngrx/signals`
(frontend), pytest, Vitest.

## Global Constraints

- One `TradeLog` record per position stays the unit of truth — same `id`,
  same `plan_id` linkage, same file. No new trade records, no new plan
  records.
- `status` on the ledger record (`TradeLog`) keeps meaning "is there still
  live risk on this ticker." Every live-monitoring path that reads it
  (`TradeLog.update_open_trades`, `TradeLog.close_if_live_price_hit`,
  `PlanManager.poll()`'s open-plan filters) is untouched by this plan.
- A leg's outcome is the sign of its own `r`: `r >= 0` → win, `r < 0` →
  loss. Kept inside the existing `open`/`win`/`loss`/`closed` vocabulary —
  no new status value.
- Applies retroactively over existing trade history (it's a derived view,
  computed at read time) — no separate "legacy" code path.
- The backtest simulator (`plan_engine._scale_out_exit_walk`) is NOT
  touched by this plan.

---

### Task 1: Stamp `closed_at` on each realized leg

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py:327-335` (`_step_active`'s
  TP1-leg append), `swingbot/core/planning/plan_manager.py:412-421`
  (`_close_runner`), and `swingbot/core/planning/plan_manager.py:570-577`
  (`_check_bar_active`'s own TP1-leg append — the unwired overnight-gap
  path `known-traps.md` documents as "mirror bar checks only to keep their
  tests honest"; `_check_bar_partial` needs no separate change since it
  already calls the same `_close_runner` this task fixes)
- Test: `tests/planning/test_plan_manager_partial.py`

**Interfaces:**
- Produces: every dict appended to `plan.legs_realized` (and, via the
  existing event pipeline, to `TradeLog`'s matching `trade["legs"]`) now
  carries a `"closed_at"` key — an ISO-8601 UTC timestamp string, the same
  value written to that transition's `status_history` entry.

Every realized leg (a `dict` with `fraction`/`exit_price`/`r`/`reason`) has
no timestamp of its own today — only the plan's `status_history` records
when each transition happened. Task 4 needs a per-leg close time to build
a leg-row's `closed_at`/`opened_at`-relative fields, and reconstructing it
from `status_history` by position is a real but avoidable fallback (Task 4
still needs that fallback for pre-existing historical data with no
`closed_at` on the leg). Stamping it going forward is a small, direct fix.

- [ ] **Step 1: Write the failing test**

Add to `tests/planning/test_plan_manager_partial.py`, which already defines
`_partial_env(tmp_path, prices, tp2=None, atr_fn=None)` — it walks a fresh
plan through the TP1 fill (asserting `tp1_partial`) before feeding it
`prices`, exactly the pattern `test_runner_closes_at_breakeven` (the first
test in this file) already uses:

```python
def test_legs_realized_carry_their_own_close_timestamp(tmp_path):
    store, mgr = _partial_env(tmp_path, [99.9])   # closes at the runner floor
    mgr.poll()
    legs = store.get("p1").legs_realized
    assert len(legs) == 2
    assert legs[0].get("closed_at") and legs[1].get("closed_at")
    assert legs[0]["closed_at"] <= legs[1]["closed_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
Expected: FAIL — `KeyError: 'closed_at'`

- [ ] **Step 3: Implement**

In `_step_active` (line 327-333, the TP1-leg-append block):

```python
            at = self._now()
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1", "closed_at": at}
            plan.legs_realized.append(leg)
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            plan.runner_floor_session = session_date(now)
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
```

(Replace the existing `record_transition(..., at=self._now())` call so both
share one `at` value instead of two separate clock reads.)

In `_close_runner` (line 412-421):

```python
    def _close_runner(self, plan: TradePlanV2, fill: float, reason: str,
                      risk: float, sign: int) -> list[PlanEvent]:
        r2 = (fill - plan.entry_price) * sign / risk if risk > 0 else 0.0
        at = self._now()
        leg = {"fraction": 1.0 - plan.tp1_fraction, "exit_price": fill,
               "r": r2, "reason": reason, "closed_at": at}
        plan.legs_realized.append(leg)
        record_transition(plan, PlanStatus.CLOSED, reason=reason, at=at)
        self.store.update(plan)
        return [PlanEvent(plan.plan_id, "closed",
                          {"reason": reason, "exit_price": fill, "leg": leg})]
```

In `_check_bar_active` (line 570-577 — unwired, mirrored only to keep its
own tests honest, per `docs/claude/known-traps.md`):

```python
            at = self._now()
            leg = {"fraction": plan.tp1_fraction, "exit_price": fill,
                   "r": r1, "reason": "tp1", "closed_at": at}
            plan.legs_realized.append(leg)
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
            record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial",
                              at=at)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
Expected: PASS, all tests in the file (this touches shared code paths every
other test in the file also exercises)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_partial.py
git commit -m "feat(v79): stamp closed_at on each realized leg"
```

---

### Task 2: `expand_trade_legs` and leg-accurate stats

**Files:**
- Modify: `swingbot/core/tracking/performance.py` — add `expand_trade_legs`
  near `settle_legs`/`closed_pnl_pct` (around line 199-256), and wire it
  into `get_stats` (line 727) and `get_extended_stats` (line 758)
- Test: `tests/tracking/test_tradelog_v2.py`

**Interfaces:**
- Consumes: nothing new — operates on the same trade `dict` shape every
  other function in this file already reads (`status`, `shares`, `entry`,
  `direction`, `stop_loss`, `exit_price`, `legs`).
- Produces: `expand_trade_legs(trade: dict) -> list[dict]`. A trade with no
  `legs` (or an empty list) returns `[trade]` unchanged. A trade with
  realized legs returns one synthetic row per leg (`status` `"win"`/`"loss"`
  from the leg's own `r` sign, `shares` scaled by the leg's `fraction`,
  `exit_price`/`entry`/`direction`/`stop_loss` set so `closed_pnl_pct`/
  `closed_r_multiple` (both already in this file) compute correctly against
  it with NO `legs` key of their own), plus — if `trade["status"] == "open"`
  — one further row for the still-open remainder (`status="open"`, `shares`
  scaled by the unrealized fraction, no `exit_price`).

- [ ] **Step 1: Write the failing test**

Add to `tests/tracking/test_tradelog_v2.py`:

```python
from swingbot.core.tracking.performance import expand_trade_legs


def test_expand_trade_legs_passes_through_a_trade_with_no_legs():
    trade = {"status": "win", "shares": 10, "entry": 100.0,
             "direction": "bullish", "stop_loss": 95.0, "exit_price": 110.0}
    assert expand_trade_legs(trade) == [trade]


def test_expand_trade_legs_splits_a_fully_closed_scaled_out_trade():
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 118.0, "r": 3.6, "reason": "tp1_runner_tp2"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert [r["shares"] for r in rows] == [5.0, 5.0]
    assert [r["exit_price"] for r in rows] == [110.0, 118.0]
    assert [r["status"] for r in rows] == ["win", "win"]


def test_expand_trade_legs_adds_the_open_remainder():
    trade = {
        "status": "open", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": None,
        "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}],
    }
    rows = expand_trade_legs(trade)
    assert len(rows) == 2
    assert rows[0]["status"] == "win" and rows[0]["shares"] == 5.0
    assert rows[1]["status"] == "open" and rows[1]["shares"] == 5.0
    assert rows[1]["exit_price"] is None


def test_expand_trade_legs_classifies_a_negative_r_leg_as_loss():
    trade = {
        "status": "closed", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 98.0,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 98.0, "r": -0.4, "reason": "manual"},
        ],
    }
    rows = expand_trade_legs(trade)
    assert [r["status"] for r in rows] == ["win", "loss"]


def test_get_extended_stats_counts_each_leg_as_its_own_outcome():
    trade = {
        "status": "win", "shares": 10, "entry": 100.0, "direction": "bullish",
        "stop_loss": 95.0, "exit_price": 118.0, "confidence_level": None,
        "legs": [
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
            {"fraction": 0.5, "exit_price": 90.0, "r": -0.5, "reason": "manual"},
        ],
    }
    log = TradeLog(path="/nonexistent")  # never read; `trades=` overrides
    stats = log.get_stats(trades=[trade])
    assert stats["total"] == 2 and stats["wins"] == 1 and stats["losses"] == 1
```

(`TradeLog` is already imported at the top of this file per the existing
`test_extended_stats_uses_leg_aware_closed_r_multiple` test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
Expected: FAIL — `ImportError: cannot import name 'expand_trade_legs'`

- [ ] **Step 3: Implement**

Add to `swingbot/core/tracking/performance.py`, near `settle_legs` (after
`closed_r_multiple`, before `_apply_exit_price` — around line 306):

```python
def expand_trade_legs(trade: dict) -> list[dict]:
    """Split a scaled-out trade into one synthetic row per realized leg,
    plus (if the position is still open) one more for the unrealized
    remainder. A trade with no legs returns `[trade]` unchanged -- this is
    what makes the function a safe drop-in wherever this file already
    walks a trade list.

    Each returned row carries no `legs` key of its own, so
    `closed_pnl_pct`/`closed_r_multiple` fall through to their plain
    single-exit formula when called on it -- the correct behaviour for one
    already-realized leg, not the fraction-weighted blend those two
    functions use for a still-nested multi-leg trade.
    """
    legs = trade.get("legs") or []
    if not legs:
        return [trade]

    shares = trade.get("shares")
    entry = trade.get("entry")
    direction = trade.get("direction")
    stop_loss = trade.get("stop_loss")
    rows = []
    for leg in legs:
        leg_shares = (
            round(shares * leg.get("fraction", 0), 4) if shares is not None else None
        )
        rows.append({
            **trade,
            "legs": None,
            "shares": leg_shares,
            "exit_price": leg.get("exit_price"),
            "closed_at": leg.get("closed_at") or trade.get("closed_at"),
            "status": "win" if (leg.get("r") or 0) >= 0 else "loss",
            "entry": entry,
            "direction": direction,
            "stop_loss": stop_loss,
        })

    if trade.get("status") == "open":
        realized_fraction = sum(leg.get("fraction", 0) for leg in legs)
        remaining_fraction = max(0.0, 1.0 - realized_fraction)
        rows.append({
            **trade,
            "legs": None,
            "shares": (
                round(shares * remaining_fraction, 4) if shares is not None else None
            ),
            "exit_price": None,
            "status": "open",
        })

    return rows
```

Wire it into `get_stats` (line 727-753) and `get_extended_stats` (line
758-813) — both take the same shape of `base`/`trades` list before
filtering by `confidence_level`, so expand right after that filter, before
anything else reads `trades`:

```python
    def get_stats(self, confidence_level: int = None, trades: list | None = None) -> dict:
        self.refresh()
        base = self._trades if trades is None else trades
        trades = base if confidence_level is None else [
            t for t in base if t["confidence_level"] == confidence_level
        ]
        trades = [row for t in trades for row in expand_trade_legs(t)]
        # ... rest of the function unchanged from here
```

```python
    def get_extended_stats(self, confidence_level: int = None, trades: list | None = None) -> dict:
        self.refresh()
        base = self._trades if trades is None else trades
        trades = base if confidence_level is None else [
            t for t in base if t["confidence_level"] == confidence_level
        ]
        trades = [row for t in trades for row in expand_trade_legs(t)]
        # ... rest of the function unchanged from here
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py`
Expected: PASS

- [ ] **Step 5: Run the broader tracking suite (this changes counting for every scaled-out trade in it)**

Run: `python scripts/dev/testrun.py file tests/tracking`
Expected: PASS. If `test_extended_stats_uses_leg_aware_closed_r_multiple`
or any other existing test fails, read the failure: a fixture asserting the
OLD single-blended-outcome count needs updating to the new leg-split count
(most fixtures using `TP1_FRACTION`'s fixed 0.5/0.5 split will still show
the SAME `expectancy_r` value by coincidence of equal weighting — only
count-based assertions like `total`/`r_multiples_count` need changing).
Fix forward; do not revert Step 3.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/tracking/performance.py tests/tracking/test_tradelog_v2.py
git commit -m "feat(v79): expand_trade_legs and leg-accurate win-rate/expectancy stats"
```

---

### Task 3: Show the true remaining share count on a still-open row

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py:767-796` (`_attach_unrealized_pnl`)
- Test: `tests/admin/test_api_v1_trades.py`

**Interfaces:**
- Consumes: `row["open_shares"]` (already computed by `_row_from_plan` via
  the existing `_open_shares` helper, line 146-164) and `row["shares"]`
  (already read).
- Produces: after this task, `row["shares"]` on a still-open row equals
  `row["open_shares"]` — the Trades table's `Shares` column (which reads
  `row.shares`, `frontend/src/app/workspaces/trades/trades.columns.ts:118`)
  shows the true remaining size on a partially-realized position instead of
  the original full size.

`_attach_unrealized_pnl`'s own `dash.unrealized_pnl_amount` call needs the
ORIGINAL `shares` plus `_legs` to do its own fraction math internally
(confirmed by reading `swingbot/admin/dashboard.py:190-208` — it multiplies
`shares * leg.fraction` for the realized part and `shares *
remaining_fraction` for the unrealized part). The `shares` override must
happen AFTER that call, in the same pass, or the dollar P&L would double-
discount the realized fraction.

- [ ] **Step 1: Write the failing test**

Add to `tests/admin/test_api_v1_trades.py` (reuses this file's `_plan`/
`_trade`/`seed`/`logged_in` fixtures already defined near the top):

```python
def test_a_partial_row_shows_the_remaining_share_count(seed, logged_in, monkeypatch):
    """The Shares column must show what's still exposed to price movement,
    not the original size at open -- v79."""
    pid = "44444444-4444-4444-8444-444444444444"
    plan = _plan(pid, status="PARTIAL")
    plan["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0,
                              "r": 1.0, "reason": "tp1", "closed_at": "2026-08-02T10:00:00+00:00"}]
    seed(plans=[plan], trades=[_trade("ffffffffffffffff", plan_id=pid)])

    # No live price fetch needed for this assertion; disable it so the test
    # doesn't hit the network -- follow this file's existing pattern for
    # stubbing get_current_price if one exists elsewhere in this file or in
    # tests/admin/conftest.py, otherwise monkeypatch
    # `swingbot.admin.api_v1.trades._attach_current_prices` to a no-op.
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)

    row = logged_in.get("/api/v1/trades").get_json()["items"][0]
    assert row["shares"] == row["open_shares"] == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — `assert 10 == 5.0`

- [ ] **Step 3: Implement**

In `_attach_unrealized_pnl` (`swingbot/admin/api_v1/trades.py:767-796`),
add one line at the end of the loop body:

```python
    for row in rows:
        if row["status"] in _TERMINAL or row["status"] == "PENDING":
            continue
        price = row.get("current_price")
        entry, direction = row.get("entry"), row.get("direction")
        if price is None or entry is None:
            continue
        row["pnl_pct"] = dash.unrealized_pnl(entry, direction, price)
        row["r_multiple"] = dash.unrealized_r(entry, row.get("_risk_stop"), direction, price)
        row["realized_pnl_amount"] = dash.unrealized_pnl_amount(
            entry, direction, row.get("shares"), row.get("_legs"), price)
        if row.get("open_shares") is not None:
            row["shares"] = row["open_shares"]
```

This is a no-op for any row that hasn't realized a leg (`open_shares ==
shares` already, per `_open_shares`'s formula with an empty `legs_realized`
list) — it only changes anything for a row with at least one realized leg.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_api_v1_trades.py
git commit -m "feat(v79): show remaining share count on a partially-realized row"
```

---

### Task 4: Split a scaled-out plan's row into one per leg

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` — add `_row_from_leg` and
  `_expand_plan_row` near `_row_from_plan` (after line 280), change
  `build_rows()` (line 426-449) to call `_expand_plan_row` instead of
  `_row_from_plan` directly, add `leg_index`/`leg_total` to `TRADE_ROW`'s
  contract in `tests/admin/test_api_v1_trades.py` (line 36-112) and to
  `_row_from_plan`/`_row_from_trade`'s return dicts (defaulting both rows
  to `leg_index=0`, `leg_total=1`)
- Test: `tests/admin/test_trades_partial_row.py`, `tests/admin/test_api_v1_trades.py`

**Interfaces:**
- Consumes: `expand_trade_legs`-style leg breakdown, but built directly
  from `plan.get("legs_realized")` (not `expand_trade_legs`, which
  operates on bare trade dicts — this function needs the plan's own fields
  too, so it stays a separate, plan-aware function in this module, per the
  spec's "Consumers" section).
- Produces: `_expand_plan_row(plan: dict, trade: dict | None, noted: set) -> list[dict]`.
  A plan with no realized legs returns `[_row_from_plan(plan, trade, noted)]`
  unchanged (existing behavior, byte-for-byte). A plan with realized legs
  returns one `_row_from_leg(...)` row per leg (`status="CLOSED"`) plus,
  if the plan isn't `CLOSED` yet, one more row from the existing
  `_row_from_plan(...)` (the still-open runner, unchanged apart from the
  new `leg_index`/`leg_total` fields — Task 3 already fixed its `shares`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/admin/test_trades_partial_row.py` (reuses this file's
`partial_plan` fixture):

```python
from swingbot.admin.api_v1.trades import _expand_plan_row


def closed_scaled_out_plan(**kw):
    base = partial_plan(status="CLOSED", **kw)
    base["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 121.0, "r": 2.1, "reason": "tp1",
         "closed_at": "2026-09-02T14:00:00+00:00"},
        {"fraction": 0.5, "exit_price": 130.0, "r": 3.0, "reason": "tp1_runner_tp2",
         "closed_at": "2026-09-05T15:00:00+00:00"},
    ]
    return base


def test_a_plan_with_no_realized_legs_expands_to_its_one_existing_row():
    plan = partial_plan(status="ACTIVE", legs_realized=[])
    rows = _expand_plan_row(plan, None, set())
    assert len(rows) == 1
    assert rows[0]["leg_index"] == 0 and rows[0]["leg_total"] == 1


def test_a_partial_plan_expands_to_a_closed_leg_and_an_open_remainder():
    plan = partial_plan()  # status PARTIAL, one realized leg per the fixture
    trade = {"id": "t1", "shares": 10, "status": "open"}
    rows = _expand_plan_row(plan, trade, set())
    assert len(rows) == 2
    assert rows[0]["status"] == "CLOSED" and rows[0]["outcome"] == "win"
    assert rows[0]["shares"] == 5.0
    assert rows[0]["exit_price"] == 121.0
    assert rows[1]["status"] == "PARTIAL"
    assert rows[1]["leg_index"] == 1 and rows[1]["leg_total"] == 2


def test_a_fully_closed_scaled_out_plan_expands_to_two_closed_rows():
    plan = closed_scaled_out_plan()
    trade = {"id": "t1", "shares": 10, "status": "win"}
    rows = _expand_plan_row(plan, trade, set())
    assert len(rows) == 2
    assert [r["status"] for r in rows] == ["CLOSED", "CLOSED"]
    assert [r["shares"] for r in rows] == [5.0, 5.0]
    assert [r["exit_price"] for r in rows] == [121.0, 130.0]
    assert rows[0]["closed_at"] == "2026-09-02T14:00:00+00:00"
    assert rows[1]["closed_at"] == "2026-09-05T15:00:00+00:00"


def test_a_negative_r_leg_is_a_loss_not_a_win():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1]["r"] = -0.4
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[1]["outcome"] == "loss"


def test_a_leg_with_no_stamped_closed_at_falls_back_to_status_history():
    plan = closed_scaled_out_plan()
    del plan["legs_realized"][0]["closed_at"]
    plan["status_history"] = [
        {"status": "ACTIVE", "reason": "market_entry", "at": "2026-09-01T09:00:00+00:00"},
        {"status": "PARTIAL", "reason": "tp1_partial", "at": "2026-09-02T14:00:00+00:00"},
        {"status": "CLOSED", "reason": "tp1_runner_tp2", "at": "2026-09-05T15:00:00+00:00"},
    ]
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[0]["closed_at"] == "2026-09-02T14:00:00+00:00"
```

Add to `tests/admin/test_api_v1_trades.py` (end-to-end, through the real
endpoint):

```python
def test_status_filter_returns_the_closed_leg_and_the_open_remainder_separately(
    seed, logged_in, monkeypatch,
):
    monkeypatch.setattr("swingbot.admin.api_v1.trades._attach_current_prices", lambda rows: None)
    pid = "55555555-5555-4555-8555-555555555555"
    plan = _plan(pid, status="PARTIAL")
    plan["legs_realized"] = [{"fraction": 0.5, "exit_price": 110.0, "r": 1.0,
                              "reason": "tp1", "closed_at": "2026-08-02T10:00:00+00:00"}]
    seed(plans=[plan], trades=[_trade("gggggggggggggggg", plan_id=pid)])

    closed = logged_in.get("/api/v1/trades?status=CLOSED").get_json()
    partial = logged_in.get("/api/v1/trades?status=PARTIAL").get_json()
    assert closed["total"] == 1 and closed["items"][0]["id"] == pid
    assert partial["total"] == 1 and partial["items"][0]["id"] == pid
    assert closed["items"][0]["shares"] == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py`
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: FAIL — `ImportError: cannot import name '_expand_plan_row'`, then
(once that's added) `AssertionError`/`KeyError: 'leg_index'` from
`assert_collection` in the second file until `TRADE_ROW` is updated too.

- [ ] **Step 3: Implement**

First, add `"leg_index": int` and `"leg_total": int` to `TRADE_ROW` in
`tests/admin/test_api_v1_trades.py` (line ~70, beside the `banked_*`
fields):

```python
    "banked_fraction": NULLABLE_NUMBER,
    "banked_exit_price": NULLABLE_NUMBER,
    "banked_r": NULLABLE_NUMBER,
    # v79 -- which row this is out of how many, when a scaled-out position
    # has been split into one row per leg. 0/1 for every row that isn't.
    "leg_index": int,
    "leg_total": int,
```

Then in `swingbot/admin/api_v1/trades.py`, add `"leg_index": 0, "leg_total": 1,`
to the returned dict of BOTH `_row_from_plan` (end of the dict literal,
line ~279, right before the closing `}`) and `_row_from_trade` (same, line
~348).

Add the new functions after `_row_from_plan` (after line 280):

```python
def _leg_closed_at(plan: dict, leg: dict, leg_index: int) -> str | None:
    """A leg's own close time, falling back to the plan's status_history
    for data predating v79's per-leg `closed_at` stamp (Task 1). Legs are
    always appended in the order their transitions happen -- leg 0 is
    always the TP1 leg (the transition into PARTIAL), any later leg is
    always the runner's own close (the transition into CLOSED) -- so the
    positional match is exact, not a guess."""
    if leg.get("closed_at"):
        return leg["closed_at"]
    history = plan.get("status_history") or []
    wanted_status = "PARTIAL" if leg_index == 0 else "CLOSED"
    for entry in history:
        if entry.get("status") == wanted_status:
            return entry.get("at")
    return plan.get("created_at")


def _row_from_leg(plan: dict, trade: dict, leg: dict, leg_index: int, noted: set) -> dict:
    """One row for a single REALIZED leg of a scaled-out plan's position --
    the TP1 leg (leg_index 0) or the runner leg (leg_index 1). Built from
    _row_from_plan's row (so every other field -- ticker, strategy, badge,
    quality_score, ... -- stays identical to what the whole-position row
    already carried) with overrides for what actually happened on just
    this leg."""
    row = _row_from_plan(plan, trade, noted)
    entry = plan.get("entry_price")
    is_bull = plan.get("direction") == "bullish"
    shares = (
        round(trade["shares"] * leg.get("fraction", 0), 4)
        if trade.get("shares") is not None else None
    )
    exit_price = leg.get("exit_price")
    leg_trade = {"entry": entry, "exit_price": exit_price, "direction": plan.get("direction")}
    closed_at = _leg_closed_at(plan, leg, leg_index)
    row.update({
        "status": "CLOSED",
        "outcome": "win" if (leg.get("r") or 0) >= 0 else "loss",
        "shares": shares,
        "open_shares": None,
        "exit_price": exit_price,
        "realized_pnl_amount": (
            round(shares * (exit_price - entry) * (1 if is_bull else -1), 2)
            if shares is not None and entry is not None and exit_price is not None
            else None
        ),
        "pnl_pct": dash.closed_pnl(leg_trade),
        "r_multiple": dash.closed_r(leg_trade),
        "banked_fraction": None,
        "banked_exit_price": None,
        "banked_r": None,
        "closed_at": closed_at,
        "today": _in_today_scope("CLOSED", closed_at),
        "leg_index": leg_index,
    })
    return row


def _expand_plan_row(plan: dict, trade: dict | None, noted: set) -> list[dict]:
    """Split a scaled-out plan's position into one row per realized leg,
    plus (if the runner is still open) one more row for the remainder --
    v79's leg-accurate Trades table. A plan that never scaled out returns
    exactly the one row _row_from_plan already built, unchanged."""
    legs = plan.get("legs_realized") or []
    if not legs:
        return [_row_from_plan(plan, trade, noted)]

    t = trade or {}
    still_open = plan.get("status") != "CLOSED"
    total = len(legs) + (1 if still_open else 0)
    rows = [_row_from_leg(plan, t, leg, i, noted) for i, leg in enumerate(legs)]
    if still_open:
        remainder = _row_from_plan(plan, trade, noted)
        remainder["leg_index"] = len(legs)
        rows.append(remainder)
    for row in rows:
        row["leg_total"] = total
    return rows
```

Change `build_rows()` (line 438):

```python
    rows = []
    for p in plans:
        rows.extend(_expand_plan_row(p, by_plan_id.get(p.get("plan_id")), noted))
```

(replacing the single list-comprehension line that called `_row_from_plan`
directly.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py`
Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: PASS

- [ ] **Step 5: Run the full admin test directory (this changes row counts across every trades-list consumer)**

Run: `python scripts/dev/testrun.py file tests/admin`
Expected: PASS. Read any failure before changing test expectations — a
fixture with `legs_realized` populated (grep the file for
`legs_realized.*fraction` to find them) whose row-count assertion assumed
one row per plan needs updating to the new count; anything else failing is
a real regression, fix the implementation instead.

- [ ] **Step 6: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin/test_trades_partial_row.py tests/admin/test_api_v1_trades.py
git commit -m "feat(v79): split a scaled-out plan's row into one per leg"
```

---

### Task 5: Frontend row-key fix

**Files:**
- Modify: `frontend/src/app/api/models.ts:68-134` (`TradeRow` interface),
  `frontend/src/app/workspaces/trades/trades.ts:520` (`rowKey`)
- Test: `frontend/src/app/workspaces/trades/trades.spec.ts` (create the
  file if it does not already exist — check first with
  `Glob("frontend/src/app/workspaces/trades/*.spec.ts")`)

**Interfaces:**
- Consumes: the API's new `leg_index`/`leg_total` fields (Task 4).
- Produces: `TradeRow.leg_index: number` and `TradeRow.leg_total: number`
  (non-nullable — the backend now always sends both); the Trades table's
  `rowKey` returns a value unique per row even when two rows share one
  `id`.

Two rows from one scaled-out position now share one `id` (Task 4). The
`sb-data-table`'s `rowKey` input (currently just `row.id`,
`frontend/src/app/workspaces/trades/trades.ts:520`) needs a synthetic key
so Angular's `@for` track and pagination don't collide. Clicking either
row still navigates to `/trades/:id` using the real `id` — that call site
is untouched, since there is exactly one detail page for the whole
position either way.

- [ ] **Step 1: Add the two fields to the model**

`frontend/src/app/api/models.ts`, inside `TradeRow` (after `bars_to_expiry`,
the last field, line 133):

```typescript
  bars_to_expiry: number | null;
  /** Which row this is out of how many, when a scaled-out position has
   *  been split into one row per leg (v79). 0/1 for every row that
   *  isn't split. */
  leg_index: number;
  leg_total: number;
}
```

- [ ] **Step 2: Write the failing test**

Create (or add to) `frontend/src/app/workspaces/trades/trades.spec.ts`:

```typescript
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { Trades } from './trades';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', outcome: 'win', ticker: 'AAPL',
    direction: 'bullish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 5, open_shares: null, position_value: null,
    current_price: null, exit_price: 110, realized_pnl_amount: 50,
    pnl_pct: 10, r_multiple: 2, held_hours: 1, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  };
}

describe('Trades rowKey', () => {
  it('is unique for two leg-rows sharing one id', () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
      ],
    });
    const f = TestBed.createComponent(Trades);
    const rowKey = (f.componentInstance as unknown as { rowKey: (r: TradeRow) => string }).rowKey;
    const a = row({ leg_index: 0, leg_total: 2 });
    const b = row({ leg_index: 1, leg_total: 2 });
    expect(rowKey(a)).not.toBe(rowKey(b));
  });
});
```

If `Trades` requires additional providers to construct (check by running
the test first and reading the error — `TradesStore`/`PreferencesStore`
dependencies are `providedIn: 'root'` per this repo's convention, so
`provideHttpClient()`/`provideHttpClientTesting()` should be enough, same
as `shell.spec.ts`'s pattern), add them following that same file's style.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include='**/trades.spec.ts'`
Expected: FAIL — `rowKey(a)` equals `rowKey(b)` (both `'t1'`)

- [ ] **Step 4: Implement**

`frontend/src/app/workspaces/trades/trades.ts:520`:

```typescript
  protected readonly rowKey = (row: TradeRow) => `${row.id}:${row.leg_index}`;
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include='**/trades.spec.ts'`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/trades/trades.spec.ts
git commit -m "feat(v79): unique row key for split-leg trade rows"
```

---

### Task 6: Full-suite verification

Run once, over everything this plan touched:

Run: `python scripts/dev/testrun.py full` (or dispatch the `test-runner`
subagent)
Expected: `0 failed`, `0 xfailed`.

Run: `cd frontend && npm test`
Expected: all green.

**If either is not green, fix forward from those failures** — they are
this plan's regressions, and the task is not done until both runs are.

- [ ] Run `python scripts/dev/testrun.py full`, confirm `0 failed`/`0 xfailed`
- [ ] Run `cd frontend && npm test`, confirm all green
- [ ] Commit any fixes with `fix(v79): <what was wrong>`

## Parallelisation

- **Sequential throughout**, matching the spec. Task 2 (`expand_trade_legs`)
  and Task 4 (`_expand_plan_row`) are independent of EACH OTHER (different
  files, different data source — trade dict vs. plan+trade pair — no
  shared symbol), so Group `{Task 2, Task 4}` could run in parallel IF
  Task 1 (which both implicitly depend on for `closed_at` — Task 4's
  fallback path is exercised either way, but the happy path needs it) has
  already landed. Task 3 is independent of both (different function,
  different concern) and could also join that group. Task 5 depends on
  Task 4's `leg_index`/`leg_total` fields existing on the wire — sequential
  after it. Task 6 is last, after everything.
  - **Group (parallel, after Task 1): Task 2, Task 3, Task 4.**
  - **Sequential:** Task 1 before the group (leg timestamps). Task 5 after
    Task 4 (consumes its new API fields). Task 6 last.
