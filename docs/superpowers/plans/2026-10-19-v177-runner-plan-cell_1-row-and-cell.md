# v177 — Plan cell for trailing runners and closed partial trades. Part 1: row fields, cell, wiring (V177-1..V177-3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V177-2:" -A 400 docs/superpowers/plans/2026-10-19-v177-runner-plan-cell_1-row-and-cell.md`.

**Bump:** ui patch, bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-19-v177-runner-plan-cell-design.md](../specs/2026-10-19-v177-runner-plan-cell-design.md) (this part: § Where it changes, § Tooltips, § Layout, § Edge cases, § Testing, § Code facts the plan must honour)
**Index:** [2026-10-19-v177-runner-plan-cell_0-index.md](2026-10-19-v177-runner-plan-cell_0-index.md) carries the Goal, `## Global Constraints`, the Backend / PlanCell / Gate contracts, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v177-runner-plan-cell` (created in V177-1 Step 1). Never `cd` in Bash: use `git -C $WT …` and `python $WT/scripts/dev/testrun.py file tests/<…>` (the script runs from its own repo root, so test paths are relative to `$WT`). Frontend commands run from PowerShell:

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/plan-cell.spec.ts
Pop-Location
```

A 60 s "Timeout waiting for worker … no tests" from `ng test` is machine load: re-run the same command once (`docs/claude/testing-cost.md`). All file paths below are relative to `$WT`.

**Order.** V177-1 first (its Step 1 creates the worktree). V177-2 may run beside V177-1 once that worktree exists (disjoint files). V177-3 runs after both.

**RKLB numbers used throughout.** Short; entry 60.67, TP1 58.33, original stop 61.85, best price since TP1 49.94, trailing stop 52.437. `best_pnl_pct = round((49.94 − 60.67) × −1 / 60.67 × 100, 2) = 17.69`; `stop_pnl_pct = round((52.437 − 60.67) × −1 / 60.67 × 100, 2) = 13.57`; line-1 distances `|58.33 − 60.67| / 60.67 = 3.857 % → 3.9%`, `|61.85 − 60.67| / 60.67 = 1.945 % → 1.9%`; closed runner at 52.44: `bankedLegPct(60.67, 52.44, 'bearish') = 13.565 → +13.6%`.

---

# Phase 1 — Row fields, cell and wiring

### Task V177-1: Backend row fields: `tp1`, price-free percentages, runner exit, leg clearing, contract

**Model:** opus — a complexity-pinned row builder (`_row_from_plan` at 15), an exact-key wire contract and four row origins (plan, leg, remainder, legacy) that must agree

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (`_row_from_plan` :223-326 return statement; new helpers after `_row_from_plan`; `_row_from_leg` :373-421 `row.update`; `_row_from_trade` :446-519 dict; `_trailing_status_fields` :944-975 last `out.update`)
- Modify: `tests/admin/test_trades_partial_row.py` (import line :4; new builders and tests appended at the end)
- Modify: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW` :37-134, after `"headroom_r"`; two tests appended after `test_trailing_runner_without_a_best_price_keeps_the_plain_chip` :1200-1207)

**Interfaces:**
- Consumes: from `main`: `_row_from_plan(plan, trade, noted) -> dict`, `_row_from_leg(plan, trade, leg, leg_index, noted) -> dict`, `_expand_plan_row(plan, trade, noted) -> list[dict]`, `_row_from_trade(t, noted) -> dict`, `_trailing_status_fields(row, price) -> dict`, `_trailing_pnl_ends(row, stop, best, is_bull) -> dict` (all in `swingbot/admin/api_v1/trades.py`); test helpers `partial_plan(**kw)`, `closed_scaled_out_plan(**kw)` (`tests/admin/test_trades_partial_row.py`), `_trailing_short(best=52.0)`, `_runner_row(client)`, fixtures `seed`, `logged_in`, `priced`, `NULLABLE_NUMBER`, `NULLABLE_STR` (`tests/admin/test_api_v1_trades.py`, `tests/admin/api_v1_contract.py`).
- Produces (consumed by V177-3, V177-6; index § Backend contract):
  - `_runner_cell_fields(plan: dict, trade: dict | None, row: dict) -> dict` with exactly `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason`.
  - `_runner_best_or_fill(row: dict) -> float | None`; `_runner_pnl_fields(row: dict) -> dict` (`stop_pnl_pct`, `best_pnl_pct`); `_runner_exit_fields(plan: dict, trade: dict | None) -> dict`; `_runner_exit_reason(leg: dict) -> str | None`; `_closed_manually_after_tp1(plan: dict, legs: list) -> bool`; module dict `_RUNNER_CELL_CLEARED`. One private helper beyond the ledger, `_is_trailing_runner(row: dict) -> bool`, is used only inside this file.
  - Wire: every trades row (list, detail, close/cancel response, leg rows, legacy rows) carries `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price` (number | null) and `runner_exit_reason` (string | null).
  - The worktree `$WT` on branch `2026-10-19-v177-runner-plan-cell`.

**Decisions this task pins (from the index; do not reopen).**
- `tp1` is gated on "PARTIAL and `bar_kind == "trailing"`" only, not on stop/best being numbers: spec § Edge cases says a missing best price or stop drops line 2 and keeps line 1, and line 1 needs `tp1`.
- `best_pnl_pct`/`stop_pnl_pct` are now written by the row builder for every trailing PARTIAL row, priced or not. `_trailing_status_fields`' priced path keeps writing them through the same `_runner_pnl_fields`, so the value is identical on both passes (the attach passes can run twice per request; this stays idempotent). Its chip path (no price, no best, span ≤ 0) is unchanged: it returns no pct keys, so the builder's values survive.
- `_row_from_leg` clears `tp1`/`best_pnl_pct`/`stop_pnl_pct` on **every** leg row, keeps `bar_kind` (the Trades page's trailing icon reads it) and keeps the runner-exit fields (both rows of a closed partial trade show the runner exit).

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill. Reuse the worktree if `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `2026-10-19-v177-runner-plan-cell`; otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch --quiet origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-19-v177-runner-plan-cell -b 2026-10-19-v177-runner-plan-cell main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell log --oneline -1
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend ci
```

Expected: the log line is the current `main` HEAD (the commit carrying this plan); `npm ci` ends without `ERR!`. Every later step runs in `$WT`. V177-2 may start now.

- [ ] **Step 2: Sync the database replica**

Run `/replicate-prod-db` once in this session before the first DB-backed test run (CLAUDE.md; the API tests below seed the Postgres test database through `seed_store`). If the test database is down: `docker compose --profile test up -d db-test` from `$R`. Skip this step if it already ran in this session.

- [ ] **Step 3: Write the failing row-builder tests**

In `tests/admin/test_trades_partial_row.py`, change the import line (:4) to:

```python
from swingbot.admin.api_v1.trades import _expand_plan_row, _row_from_plan, _row_from_trade
```

Append at the end of the file:

```python
# --- v177: the Plan cell's runner fields ----------------------------------

RUNNER_CELL_KEYS = ("tp1", "best_pnl_pct", "stop_pnl_pct",
                    "runner_exit_price", "runner_exit_reason")


def rklb_runner(**kw):
    """The live RKLB short that motivated v177: TP1 banked, no TP2, the stop
    trailing down behind a best price of 49.94."""
    fields = {"ticker": "RKLB", "direction": "bearish", "entry_price": 60.67,
              "trigger_price": 60.67, "stop_loss": 61.85, "tp1": 58.33,
              "working_stop": 52.437, "runner_high_close": 49.94,
              "legs_realized": [{"fraction": 0.5, "exit_price": 58.33, "r": 1.98,
                                 "reason": "tp1",
                                 "closed_at": "2026-10-10T14:00:00+00:00"}]}
    fields.update(kw)
    return partial_plan(**fields)


def manually_closed_partial(**kw):
    """A PARTIAL plan closed from the admin UI: `_close_plan` records the
    CLOSED transition with reason "manual" and appends NO runner leg."""
    plan = partial_plan(status="CLOSED", **kw)
    plan["legs_realized"] = [
        {"fraction": 0.5, "exit_price": 121.0, "r": 2.1, "reason": "tp1",
         "closed_at": "2026-09-02T14:00:00+00:00"},
    ]
    plan["status_history"] = [
        {"status": "PARTIAL", "reason": "tp1", "at": "2026-09-02T14:00:00+00:00"},
        {"status": "CLOSED", "reason": "manual", "at": "2026-09-04T16:00:00+00:00"},
    ]
    return plan


def _cell(row):
    return {key: row[key] for key in RUNNER_CELL_KEYS}


def test_rklb_short_runner_carries_tp1_and_both_signed_percentages():
    row = _row_from_plan(rklb_runner(), None, set())
    assert row["tp1"] == 58.33
    assert row["best_pnl_pct"] == 17.69
    assert row["stop_pnl_pct"] == 13.57
    assert (row["runner_exit_price"], row["runner_exit_reason"]) == (None, None)
    # The view fields every other surface agrees on are untouched (v73).
    assert row["stop_loss"] == 52.437
    assert row["target"] is None
    assert row["risk_stop"] == 61.85


def test_long_runner_percentages_are_signed_the_other_way():
    row = _row_from_plan(partial_plan(runner_high_close=130.0), None, set())
    assert row["tp1"] == 120.0
    assert row["best_pnl_pct"] == 30.0
    assert row["stop_pnl_pct"] == 13.33


def test_a_runner_with_no_best_price_yet_measures_from_the_tp1_fill():
    row = _row_from_plan(partial_plan(), None, set())       # runner_high_close absent
    assert row["runner_best"] is None
    assert row["best_pnl_pct"] == 21.0                       # the 121.0 TP1 fill
    assert row["stop_pnl_pct"] == 13.33


def test_a_derived_floor_keeps_both_percentages_and_its_stop_kind():
    row = _row_from_plan(partial_plan(working_stop=None, runner_high_close=130.0), None, set())
    assert row["stop_kind"] == "derived_floor"
    assert row["tp1"] == 120.0
    assert row["stop_pnl_pct"] == 13.33
    assert row["best_pnl_pct"] == 30.0


def test_a_runner_with_a_tp2_gets_none_of_the_runner_cell_fields():
    row = _row_from_plan(partial_plan(tp2=140.0, runner_high_close=130.0), None, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)


def test_an_active_plan_gets_none_of_the_runner_cell_fields():
    row = _row_from_plan(partial_plan(status="ACTIVE", legs_realized=[]), None, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)


def test_the_tp1_leg_row_of_a_still_partial_plan_clears_the_line_two_fields():
    trade = {"id": "t1", "shares": 10, "status": "open"}
    leg_row, runner_row = _expand_plan_row(rklb_runner(), trade, set())
    assert leg_row["status"] == "CLOSED"
    assert leg_row["bar_kind"] == "trailing"                 # the Trades page's leg icon
    assert _cell(leg_row) == dict.fromkeys(RUNNER_CELL_KEYS)
    assert runner_row["status"] == "PARTIAL"
    assert (runner_row["tp1"], runner_row["best_pnl_pct"], runner_row["stop_pnl_pct"]) == (
        58.33, 17.69, 13.57)


def test_both_rows_of_a_closed_partial_trade_carry_the_runner_exit():
    trade = {"id": "t1", "shares": 10, "status": "win", "exit_price": 130.0}
    rows = _expand_plan_row(closed_scaled_out_plan(), trade, set())
    assert [(r["runner_exit_price"], r["runner_exit_reason"]) for r in rows] == [
        (130.0, "tp1_runner_tp2"), (130.0, "tp1_runner_tp2")]
    assert [r["exit_price"] for r in rows] == [121.0, 130.0]  # each leg keeps its own fill
    for r in rows:
        assert (r["tp1"], r["best_pnl_pct"], r["stop_pnl_pct"]) == (None, None, None)


def test_a_give_back_close_reports_giveback_not_the_trail_reason():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1].update({"exit_price": 126.0, "reason": "tp1_runner_trail",
                                     "stop_source": "giveback", "giveback_pct": 5.0})
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert [(r["runner_exit_price"], r["runner_exit_reason"]) for r in rows] == [
        (126.0, "giveback"), (126.0, "giveback")]


def test_a_floor_stop_close_passes_its_leg_reason_through():
    plan = closed_scaled_out_plan()
    plan["legs_realized"][1].update({"exit_price": 113.5, "reason": "tp1_runner_be",
                                     "stop_source": "floor"})
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "win"}, set())
    assert rows[1]["runner_exit_reason"] == "tp1_runner_be"


def test_an_active_stop_out_has_no_runner_exit():
    plan = partial_plan(status="CLOSED", legs_realized=[
        {"fraction": 1.0, "exit_price": 90.0, "r": -1.0, "reason": "loss"}])
    rows = _expand_plan_row(plan, {"id": "t1", "shares": 10, "status": "loss"}, set())
    assert len(rows) == 1
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_manual_close_after_tp1_reads_the_trades_own_exit_price():
    trade = {"id": "t1", "shares": 10, "status": "win", "exit_price": 125.5}
    rows = _expand_plan_row(manually_closed_partial(), trade, set())
    assert len(rows) == 1                                     # no runner leg was written
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (125.5, "manual")
    assert rows[0]["exit_price"] == 121.0                     # the leg row keeps the TP1 fill


def test_a_manual_close_whose_price_fetch_failed_shows_no_runner_exit():
    trade = {"id": "t1", "shares": 10, "status": "closed", "exit_price": None}
    rows = _expand_plan_row(manually_closed_partial(), trade, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_manual_close_with_no_linked_trade_shows_no_runner_exit():
    rows = _expand_plan_row(manually_closed_partial(), None, set())
    assert (rows[0]["runner_exit_price"], rows[0]["runner_exit_reason"]) == (None, None)


def test_a_legacy_trade_emits_every_runner_cell_key_as_none():
    trade = {"id": "L1", "ticker": "AAPL", "status": "win", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
             "opened_at": "2026-09-01T09:00:00+00:00",
             "closed_at": "2026-09-03T15:00:00+00:00"}
    row = _row_from_trade(trade, set())
    assert _cell(row) == dict.fromkeys(RUNNER_CELL_KEYS)
```

- [ ] **Step 4: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py`
Expected: the new tests FAIL with `KeyError: 'tp1'` (or `'runner_exit_price'`); the 17 existing tests still pass.

- [ ] **Step 5: Add the helpers to `trades.py`**

In `swingbot/admin/api_v1/trades.py`, the last statements of `_row_from_plan` today are `view = plan_view(_AttrPlan(plan), price=None)` followed by `return {` … `"leg_total": 1,` / `}`. Change `return {` to `row = {`, and replace the closing `}` of that dict with:

```python
    }
    # v177 -- the Plan cell's runner fields. One call and no branch here:
    # this function is pinned at complexity 15, every condition lives in the
    # helpers below.
    row.update(_runner_cell_fields(plan, trade, row))
    return row
```

Insert directly after `_row_from_plan` (before `def _leg_closed_at`):

```python
# v177 -- the Plan cell's runner fields. Derived from what the plan already
# holds; nothing is stored. `tp1` and the two percentages feed the two-line
# cell of a PARTIAL runner with no TP2; `runner_exit_*` feed the closed cell
# of a plan that banked TP1 and then closed its runner.
_RUNNER_CELL_CLEARED = {"tp1": None, "best_pnl_pct": None, "stop_pnl_pct": None}
_NO_RUNNER_EXIT = {"runner_exit_price": None, "runner_exit_reason": None}


def _is_trailing_runner(row: dict) -> bool:
    """A PARTIAL plan whose runner trails with no TP2 (`plan_view` gives it
    `bar_kind == "trailing"`)."""
    return row.get("status") == "PARTIAL" and row.get("bar_kind") == "trailing"


def _runner_best_or_fill(row: dict) -> float | None:
    """The runner's best price since TP1, or the TP1 fill until a tick has
    recorded one -- a freshly banked runner still has a best price to show."""
    for key in ("runner_best", "banked_exit_price"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            return value
    return None


def _runner_pnl_fields(row: dict) -> dict:
    """Per-share P&L % from the original entry at the runner's stop and at its
    best price. The one entry point for the status bar and the Plan cell, and
    independent of the live price, so the cell keeps line 2 when the feed is
    down."""
    stop, best = row.get("stop_loss"), _runner_best_or_fill(row)
    numbers = all(isinstance(v, (int, float)) for v in (stop, best))
    if not (_is_trailing_runner(row) and numbers):
        return {"stop_pnl_pct": None, "best_pnl_pct": None}
    return _trailing_pnl_ends(row, stop, best, row.get("direction") != "bearish")


def _runner_exit_reason(leg: dict) -> str | None:
    """What closed the runner. A v176 give-back stop rides a trail-stop leg
    reason, so `stop_source` names it."""
    if leg.get("stop_source") == "giveback":
        return "giveback"
    return leg.get("reason")


def _closed_manually_after_tp1(plan: dict, legs: list) -> bool:
    """A PARTIAL plan closed from the admin UI: `_close_plan` records a
    "manual" CLOSED transition and writes no runner leg, so TP1 is the only
    leg."""
    history = plan.get("status_history") or []
    return (plan.get("status") == "CLOSED"
            and len(legs) == 1 and legs[0].get("reason") == "tp1"
            and bool(history) and history[-1].get("reason") == "manual")


def _runner_exit_fields(plan: dict, trade: dict | None) -> dict:
    """The runner's actual exit on a CLOSED plan that banked TP1 first.

    An automated runner close appends its own leg (the last one). A manual
    close appends none, so the trade's own `exit_price` is the runner's exit;
    it is read here, before `_row_from_leg` overwrites the row's `exit_price`
    with the leg fill. An ACTIVE stop-out (one leg, `fraction: 1.0`) never
    banked TP1 and gets nothing.
    """
    if plan.get("status") != "CLOSED":
        return dict(_NO_RUNNER_EXIT)
    legs = plan.get("legs_realized") or []
    if len(legs) >= 2 and legs[-1].get("reason") != "tp1":
        return {"runner_exit_price": legs[-1].get("exit_price"),
                "runner_exit_reason": _runner_exit_reason(legs[-1])}
    price = (trade or {}).get("exit_price")
    if _closed_manually_after_tp1(plan, legs) and price is not None:
        return {"runner_exit_price": price, "runner_exit_reason": "manual"}
    return dict(_NO_RUNNER_EXIT)


def _runner_cell_fields(plan: dict, trade: dict | None, row: dict) -> dict:
    """Exactly the five v177 keys, for `_row_from_plan` to merge."""
    out = {"tp1": plan.get("tp1") if _is_trailing_runner(row) else None}
    out.update(_runner_pnl_fields(row))
    out.update(_runner_exit_fields(plan, trade))
    return out
```

- [ ] **Step 6: Clear the line-2 fields on leg rows**

In `_row_from_leg`, the `row.update({` call ends with `"leg_index": leg_index,` then `})`. Add the cleared keys as the last entry of that dict:

```python
        "leg_index": leg_index,
        # v177 -- a leg row is always CLOSED: the two-line runner cell never
        # applies to it, even on the TP1 leg of a still-PARTIAL plan. Keep
        # `bar_kind` (the Trades page's leg icon) and the runner-exit fields
        # (both rows of a closed partial trade show the runner's exit).
        **_RUNNER_CELL_CLEARED,
    })
```

- [ ] **Step 7: Emit the keys on legacy rows**

In `_row_from_trade`, after `"runner_best": None,` add:

```python
        # v177 -- the Plan cell's runner fields. A legacy trade never scales
        # out, so none apply; emitted as null so both origins share one shape.
        "tp1": None,
        "best_pnl_pct": None,
        "stop_pnl_pct": None,
        "runner_exit_price": None,
        "runner_exit_reason": None,
```

- [ ] **Step 8: Route the status bar through the shared helper**

In `_trailing_status_fields`, replace the line

```python
    out.update(_trailing_pnl_ends(row, stop, best, is_bull))
```

with

```python
    # Same entry point as the Plan cell (`_row_from_plan` already wrote these
    # keys; on this priced path `runner_best` is a number, so the value is
    # identical and a second attach pass stays idempotent).
    out.update(_runner_pnl_fields(row))
```

`is_bull` is still used above it (span, pos, ent), so no unused-variable warning.

- [ ] **Step 9: Run the row-builder tests**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py`
Expected: all pass (17 existing + 15 new), `0 failed`.

- [ ] **Step 10: Write the failing contract and API tests**

In `tests/admin/test_api_v1_trades.py`, append directly after `test_trailing_runner_without_a_best_price_keeps_the_plain_chip`:

```python
def test_trailing_runner_keeps_its_percentages_when_the_price_feed_is_down(seed, logged_in, priced):
    """v177: the Plan cell's line 2 must survive a dead feed -- the bar falls
    back to its chip, the two percentages do not."""
    plan, trade = _trailing_short(best=52.0)
    seed(plans=[plan], trades=[trade])
    priced(None)

    row = _runner_row(logged_in)
    assert row["progress_pct"] is None
    assert row["tp1"] == 58.33
    assert row["stop_pnl_pct"] == pytest.approx(2.75, abs=0.01)
    assert row["best_pnl_pct"] == pytest.approx(14.29, abs=0.01)


def test_trailing_runner_without_a_best_price_measures_from_the_tp1_fill(seed, logged_in, priced):
    plan, trade = _trailing_short(best=None)
    seed(plans=[plan], trades=[trade])
    priced(55.5)

    row = _runner_row(logged_in)
    assert row["progress_pct"] is None                 # the bar still needs a best price
    assert row["best_pnl_pct"] == pytest.approx(10.99, abs=0.01)   # the 54.0 TP1 fill
    assert row["stop_pnl_pct"] == pytest.approx(2.75, abs=0.01)
```

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
Expected: the two new tests pass (Steps 5-8 are in), and every `assert_collection(…, TRADE_ROW, …)` contract test FAILS with an "unexpected keys" message naming `tp1`, `best_pnl_pct`, `stop_pnl_pct`, `runner_exit_price`, `runner_exit_reason` — the wire grew, the contract has not yet.

- [ ] **Step 11: Declare the keys in the row contract**

In `TRADE_ROW`, directly after `"headroom_r": NULLABLE_NUMBER,` add:

```python
    # v177 -- the Plan cell's runner fields, on every origin (null where they
    # do not apply). The two percentages used to appear only on priced
    # trailing rows; they are now written by the row builder itself.
    "tp1": NULLABLE_NUMBER,
    "best_pnl_pct": NULLABLE_NUMBER,
    "stop_pnl_pct": NULLABLE_NUMBER,
    "runner_exit_price": NULLABLE_NUMBER,
    "runner_exit_reason": NULLABLE_STR,
```

- [ ] **Step 12: Run the API contract files**

Run, one at a time:
- `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py`
- `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_trade_detail.py`
- `python $WT/scripts/dev/testrun.py file tests/admin/test_cohort_api.py`

Expected: all pass, `0 failed`. `test_detail_row_fields_match_the_list_exactly` passes unchanged. If a contract test still reports a missing key, the row origin it names is a builder Steps 5-7 missed.

- [ ] **Step 13: Run the surface-agreement and view tests (unchanged expectations)**

Run:
- `python $WT/scripts/dev/testrun.py file tests/presentation/test_surface_agreement.py`
- `python $WT/scripts/dev/testrun.py file tests/presentation/test_plan_view_partial.py`

Expected: both pass with no edit (the row's `stop_loss`, `target`, `banked_exit_price` are unchanged; `plan_view.py` is not touched).

- [ ] **Step 14: Complexity gate and syntax**

Run: `python $WT/scripts/dev/complexity_gate.py --repo $WT`
Expected: exit 0, no finding. `_row_from_plan` stays at 15 (the change added no branch); every new helper is well below 15. If `_row_from_plan` reads 16, a conditional slipped into it: move it into `_runner_cell_fields`.

Run: `python -m py_compile $WT/swingbot/admin/api_v1/trades.py`
Expected: no output.

- [ ] **Step 15: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell add swingbot/admin/api_v1/trades.py tests/admin/test_trades_partial_row.py tests/admin/test_api_v1_trades.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell commit -m "feat(v177): trades rows carry tp1, price-free runner percentages and the runner exit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V177-2: PlanCell runner and closed-runner forms + `TradeRow` fields

**Model:** sonnet — one presentational component with an exact text/tooltip contract fixed in the index, plus one type addition

**Files:**
- Modify: `frontend/src/app/ui/plan-cell.ts` (template :22-31, styles :32-61, new inputs after `currency` :107, `targetText` :139-141, `tooltip` :149-174, new exports after `formatR` :185)
- Modify: `frontend/src/app/ui/plan-cell.spec.ts` (import line :5; new `describe` blocks appended at the end)
- Modify: `frontend/src/app/api/models.ts` (`TradeRow`, after `best_pnl_pct?` :170)

**Interfaces:**
- Consumes: from `main`: `PlanCell` inputs `entry`, `target`, `stop`, `trigger`, `stopKind`, `targetIsBankedTp1`, `bankedEntry`; protected `first`, `risePct`, `dropPct`, `fmt`, `fmtPct`; private `movePct`; `bankedLegPct(entry, bankedEntry, direction)`; `num`, `pct`, `share`, `money`, `rMultiple` from `./format`. From V177-1 only the field names in the index's § Backend contract (no code).
- Produces (consumed by V177-3, V177-4; index § PlanCell contract):
  - `PlanCell` inputs, each `input<… | null>(null)`: `planTp1: number`, `planStop: number`, `trailBest: number`, `trailBestPct: number`, `trailExitPct: number`, `runnerExit: number`, `runnerExitPct: number`, `runnerExitReason: string`.
  - `export function runnerExitLabel(reason: string | null): string` in `plan-cell.ts`.
  - DOM: runner mode root `span.plan.runner` (no `title`), children `span.line.l1[title]` and `span.line.l2[title]`, line 2 led by `span.trail`; closed-runner mode keeps the single `span.plan[title]` root.
  - `TradeRow.tp1?: number | null`, `TradeRow.runner_exit_price?: number | null`, `TradeRow.runner_exit_reason?: string | null`.

**Rules this task must keep.**
- With none of the eight new inputs set, the DOM, text and tooltip are exactly today's: every existing case in `plan-cell.spec.ts` passes without an edit. The `[class.loss]` bindings added to the legacy `.target`/`.rise` evaluate to `false` there, which adds no class.
- `querySelector('[title]')` returns the first titled element; in runner mode that is line 1 (the root carries no title), in every other mode the legacy root.
- No colour literal, no `.pos`/`.neg`/`.muted` selector (`primitives.spec.ts`): colours via `var(--pos)`, `var(--neg)`, `var(--text-faint)`, `var(--text-secondary)`; the small label size via the existing `--text-micro` token. Spacing is literal text inside `.sep`, never margins.
- Each line is its own block with `white-space: nowrap`.

- [ ] **Step 1: Write the failing cell tests**

In `frontend/src/app/ui/plan-cell.spec.ts`, change the import line (:5) to:

```ts
import { PlanCell, bankedLegAmount, bankedLegPct, runnerExitLabel } from './plan-cell';
```

Append at the end of the file:

```ts
/* -- v177: the runner's two-line cell and the closed runner's exit ------- */

function renderWith(inputs: Record<string, unknown>): HTMLElement {
  const f = TestBed.createComponent(PlanCell);
  for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

const text = (el: Element | null): string => el!.textContent!.replace(/\s+/g, ' ').trim();

/** The live RKLB short: TP1 banked at 58.33, the stop trailing at 52.437
 *  behind a best price of 49.94. Today's inputs plus the v177 ones. */
const RKLB_RUNNER = {
  entry: 60.67, target: null, stop: 52.437, stopKind: 'trailing',
  targetIsBankedTp1: true, bankedEntry: 58.33,
  planTp1: 58.33, planStop: 61.85,
  trailBest: 49.94, trailBestPct: 17.69, trailExitPct: 13.57,
};

const LONG_RUNNER = {
  entry: 100, target: null, stop: 113.3333333, stopKind: 'trailing',
  targetIsBankedTp1: true, bankedEntry: 121,
  planTp1: 120, planStop: 90,
  trailBest: 130, trailBestPct: 30, trailExitPct: 13.33,
};

const PAPER_LEVEL = "The bot's paper level: your broker's resting orders are not synced, update your stop yourself.";

describe('PlanCell runner (two lines)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('reads the original plan on line 1 for the RKLB short', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.line.l1')))
      .toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
  });

  it('reads best price -> trailing stop with signed per-share gains on line 2', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.line.l2')))
      .toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('leads line 2 with the muted Trail label', () => {
    expect(text(renderWith(RKLB_RUNNER).querySelector('.l2 .trail'))).toBe('Trail');
  });

  it('puts the tooltips on the lines, not on the root', () => {
    const el = renderWith(RKLB_RUNNER);
    expect(el.querySelector('.plan.runner')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('[title]')).toBe(el.querySelector('.line.l1'));
  });

  it('explains line 1 as the original plan', () => {
    expect(renderWith(RKLB_RUNNER).querySelector('.l1')!.getAttribute('title')).toBe(
      'Original plan (TP1 already filled): entry → TP1 / original stop. '
      + 'Percentages are the distance from the entry to each level.');
  });

  it('explains line 2: unrealised peak, per share, before costs, paper level', () => {
    expect(renderWith(RKLB_RUNNER).querySelector('.l2')!.getAttribute('title')).toBe(
      'Trailing stop. Best price so far → price the trailing stop would exit at. '
      + '+17.7% is the peak since TP1 (unrealised); +13.6% is the profit if the stop '
      + 'fills at 52.44, per share from the original entry, before costs and tax. '
      + `A short gains when price falls. ${PAPER_LEVEL}`);
  });

  it('reads a long runner the same way, with the long sentence', () => {
    const el = renderWith(LONG_RUNNER);
    expect(text(el.querySelector('.l1'))).toBe('100.00 → 120.00 / 90.00 (20.0% - 10.0%)');
    expect(text(el.querySelector('.l2'))).toBe('Trail 130.00 → 113.33 (+30.0% / +13.3%)');
    expect(el.querySelector('.l2')!.getAttribute('title')).toContain('A long gains when price rises.');
  });

  it('names a derived floor "Locked-in floor" in the line 2 tooltip', () => {
    const title = renderWith({ ...RKLB_RUNNER, stopKind: 'derived_floor' })
      .querySelector('.l2')!.getAttribute('title')!;
    expect(title.startsWith(
      'Locked-in floor. Best price so far → price the locked-in floor would exit at. ')).toBe(true);
    expect(title).toContain('is the profit if the stop fills at 52.44');
  });

  it('keeps an explicit minus on the loss side of line 2', () => {
    const el = renderWith({ ...RKLB_RUNNER, trailExitPct: -2.5 });
    expect(text(el.querySelector('.l2'))).toBe('Trail 49.94 → 52.44 (+17.7% / -2.5%)');
    expect(el.querySelector('.l2 .lock')!.classList).toContain('loss');
    expect(el.querySelector('.l2 .peak')!.classList).not.toContain('loss');
  });

  it('shows line 1 alone when a line 2 number is missing, never a dash', () => {
    for (const missing of ['trailBest', 'trailBestPct', 'trailExitPct', 'stop']) {
      const el = renderWith({ ...RKLB_RUNNER, [missing]: null });
      expect(el.querySelector('.l1')).not.toBeNull();
      expect(el.querySelector('.l2')).toBeNull();
    }
  });

  it('never prints TP2', () => {
    expect(renderWith(RKLB_RUNNER).textContent).not.toContain('TP2');
  });

  it('stays a single legacy line when planTp1 is not set', () => {
    const el = renderWith({ ...RKLB_RUNNER, planTp1: null });
    expect(el.querySelector('.runner')).toBeNull();
    expect(el.querySelector('.line')).toBeNull();
    expect(text(el)).toBe('60.67 → 58.33 ✓ / 52.44 (3.9% - 13.6%)');
  });
});

describe('PlanCell closed runner', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  const RKLB_CLOSED = {
    entry: 60.67, target: 58.33, stop: 61.85,
    runnerExit: 52.44, runnerExitPct: bankedLegPct(60.67, 52.44, 'bearish'),
    runnerExitReason: 'tp1_runner_trail',
  };

  it('shows the runner exit in the target slot with a signed gain', () => {
    const el = renderWith(RKLB_CLOSED);
    expect(text(el)).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(el.querySelector('.runner')).toBeNull();
  });

  it('names what closed the runner in the tooltip', () => {
    expect(renderWith(RKLB_CLOSED).querySelector('[title]')!.getAttribute('title')).toBe(
      'Entry 60.67 · Runner exit (trailing stop): 52.44, +13.6% per share from the original entry · Stop 61.85');
  });

  it('reads a give-back close as such', () => {
    const title = renderWith({ ...RKLB_CLOSED, runnerExitReason: 'giveback' })
      .querySelector('[title]')!.getAttribute('title')!;
    expect(title).toContain('Runner exit (give-back stop): 52.44');
  });

  it('signs and colours a runner exit on the loss side of the entry', () => {
    const el = renderWith({ entry: 100, target: 120, stop: 90,
      runnerExit: 97, runnerExitPct: -3, runnerExitReason: 'tp1_runner_be' });
    expect(text(el)).toBe('100.00 → 97.00 / 90.00 (-3.0% - 10.0%)');
    expect(el.querySelector('.rise')!.classList).toContain('loss');
    expect(el.querySelector('.target')!.classList).toContain('loss');
  });

  it('never prints TP2, even when TP2 closed the runner', () => {
    expect(renderWith({ ...RKLB_CLOSED, runnerExitReason: 'tp1_runner_tp2' }).textContent)
      .not.toContain('TP2');
  });

  it('adds no loss class to the legacy cell', () => {
    const el = renderWith({ entry: 178, target: 195, stop: 170 });
    expect(el.querySelector('.target')!.classList).not.toContain('loss');
    expect(el.querySelector('.rise')!.classList).not.toContain('loss');
  });
});

describe('runnerExitLabel', () => {
  it('names every known runner close', () => {
    expect(runnerExitLabel('tp1_runner_trail')).toBe('trailing stop');
    expect(runnerExitLabel('giveback')).toBe('give-back stop');
    expect(runnerExitLabel('tp1_runner_be')).toBe('floor stop');
    expect(runnerExitLabel('tp1_runner_tp2')).toBe('TP2');
    expect(runnerExitLabel('manual')).toBe('manual close');
    expect(runnerExitLabel('tp1_runner_progress_stall')).toBe('progress stall');
    expect(runnerExitLabel('time_exit')).toBe('time exit');
  });

  it('falls back to "runner exit" for anything else', () => {
    expect(runnerExitLabel(null)).toBe('runner exit');
    expect(runnerExitLabel('something_new')).toBe('runner exit');
    expect(runnerExitLabel('constructor')).toBe('runner exit');
  });
});
```

Why the legacy-line expectation in "stays a single legacy line": with `planTp1` unset, the cell is today's trailing-runner cell (banked fill `58.33 ✓` in the target slot, the trailing stop in the stop slot, unsigned distances `|58.33 − 60.67| / 60.67 = 3.9%`, `|52.437 − 60.67| / 60.67 = 13.6%`).

- [ ] **Step 2: Run them to verify they fail**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/plan-cell.spec.ts
Pop-Location
```

Expected: FAIL — compile error `'runnerExitLabel' is not exported` (or, once that exists, NG0303 "Can't set value of the 'planTp1' input"). The existing cases cannot run until the file compiles; that is expected.

- [ ] **Step 3: Implement the inputs, template, styles and tooltips**

In `frontend/src/app/ui/plan-cell.ts`, replace the `template:` value (:22-31) with:

```ts
  template: `
    @if (runnerMode()) {
      <span class="plan runner">
        <span class="line l1" [title]="planTooltip">
          <span class="entry">{{ fmt(first()) }}</span>
          <span class="sep">{{ ' → ' }}</span>
          <span class="target">{{ fmt(planTp1()) }}</span>
          <span class="sep">{{ ' / ' }}</span>
          <span class="stop">{{ fmt(planStop()) }}</span>
          <span class="sep">{{ ' (' }}</span><span class="rise">{{ fmtPct(planRisePct()) }}</span><span class="sep">{{ ' - ' }}</span><span class="drop">{{ fmtPct(planDropPct()) }}</span><span class="sep">{{ ')' }}</span>
        </span>
        @if (trail(); as t) {
          <span class="line l2" [title]="trailTooltip()">
            <span class="trail">Trail</span><span class="sep">{{ ' ' }}</span>
            <span class="best">{{ fmt(t.best) }}</span>
            <span class="sep">{{ ' → ' }}</span>
            <span class="exit">{{ fmt(t.exit) }}</span>
            <span class="sep">{{ ' (' }}</span><span class="peak" [class.loss]="t.bestPct < 0">{{ signedPct(t.bestPct) }}</span><span class="sep">{{ ' / ' }}</span><span class="lock" [class.loss]="t.exitPct < 0">{{ signedPct(t.exitPct) }}</span><span class="sep">{{ ')' }}</span>
          </span>
        }
      </span>
    } @else {
      <span class="plan" [title]="tooltip()">
        <span class="entry" [class.pending]="showsTrigger()">{{ fmt(first()) }}</span>
        <span class="sep">{{ ' → ' }}</span>
        <span class="target" [class.loss]="runnerLoss()">{{ targetText() }}</span>
        <span class="sep">{{ ' / ' }}</span>
        <span class="stop">{{ fmt(stop()) }}</span>
        <span class="sep">{{ ' (' }}</span><span class="rise" [class.loss]="runnerLoss()">{{ riseText() }}</span><span class="sep">{{ ' - ' }}</span><span class="drop">{{ fmtPct(dropPct()) }}</span><span class="sep">{{ ')' }}</span>
      </span>
    }
  `,
```

In the `styles:` value, directly after the `.drop   { color: var(--neg); }` line (:53), add:

```css
    /* v177 -- a trailing runner with no TP2 reads on two lines: the original
       plan, then the trail. Each line is its own block and never wraps, so
       the 375px no-wrap rule (dashboard.ts) holds per line; the second line
       adds height, not width. */
    .plan.runner { display: inline-block; }
    .line { display: block; white-space: nowrap; }
    /* A small muted label, so line 2 is never read as a second plan. */
    .trail { color: var(--text-faint); font-size: var(--text-micro); }
    .best  { color: var(--text-secondary); }
    .exit  { color: var(--neg); }
    .peak, .lock { color: var(--pos); }
    /* A signed figure on the loss side of the entry (a gap through the stop,
       a runner closed below its fill) keeps the loss colour with its minus. */
    .target.loss, .rise.loss, .peak.loss, .lock.loss { color: var(--neg); }
```

In the class body, directly after `readonly currency = input<string | null>(null);` (:107), add:

```ts

  /* -- v177: a trailing runner's two lines, a closed runner's exit -------- */

  /** The plan's ORIGINAL TP1. Non-null switches the cell to two lines:
   *  line 1 the original plan, line 2 the trail. */
  readonly planTp1 = input<number | null>(null);
  /** The plan's ORIGINAL stop (`risk_stop`), line 1's stop slot. */
  readonly planStop = input<number | null>(null);
  /** Best price since TP1 (or the TP1 fill until one is recorded). Line 2
   *  exits at `stop` (the live trailing stop or locked-in floor). */
  readonly trailBest = input<number | null>(null);
  /** Per-share % from the original entry at `trailBest` -- signed. */
  readonly trailBestPct = input<number | null>(null);
  /** Per-share % from the original entry if `stop` fills -- signed. */
  readonly trailExitPct = input<number | null>(null);
  /** A closed runner's actual exit price. Non-null puts it in the target
   *  slot with a signed `runnerExitPct` in the rise slot. */
  readonly runnerExit = input<number | null>(null);
  readonly runnerExitPct = input<number | null>(null);
  /** What closed the runner, a leg reason (see `runnerExitLabel`). */
  readonly runnerExitReason = input<string | null>(null);

  protected readonly runnerMode = computed(() => this.planTp1() !== null);
  protected readonly planRisePct = computed(() => this.movePct(this.planTp1()));
  protected readonly planDropPct = computed(() => this.movePct(this.planStop()));

  /** Line 2's numbers, or null when any is missing: the line is then
   *  omitted rather than drawn with a dash for a number that exists. */
  protected readonly trail = computed((): TrailLine | null => {
    const best = this.trailBest();
    const exit = this.stop();
    const bestPct = this.trailBestPct();
    const exitPct = this.trailExitPct();
    if (this.entry() === null || best === null || exit === null || bestPct === null || exitPct === null) {
      return null;
    }
    return { best, exit, bestPct, exitPct };
  });

  protected readonly planTooltip = PLAN_LINE_TOOLTIP;

  protected readonly trailTooltip = computed(() => {
    const t = this.trail();
    if (t === null) return '';
    const floor = this.stopKind() === 'derived_floor';
    const head = floor ? 'Locked-in floor' : 'Trailing stop';
    const level = floor ? 'the locked-in floor' : 'the trailing stop';
    return `${head}. Best price so far → price ${level} would exit at. `
      + `${pct(t.bestPct, 1)} is the peak since TP1 (unrealised); `
      + `${pct(t.exitPct, 1)} is the profit if the stop fills at ${this.fmt(t.exit)}, `
      + 'per share from the original entry, before costs and tax. '
      + `${this.isShortRunner() ? SHORT_GAINS : LONG_GAINS} ${PAPER_LEVEL}`;
  });

  /** Direction is not an input: a short's TP1 sits below its entry. */
  private readonly isShortRunner = computed(() => {
    const tp1 = this.planTp1();
    const entry = this.entry();
    return tp1 !== null && entry !== null && tp1 < entry;
  });

  protected readonly riseText = computed(() =>
    this.runnerExit() !== null ? this.signedPct(this.runnerExitPct()) : this.fmtPct(this.risePct()),
  );

  protected readonly runnerLoss = computed(() =>
    this.runnerExit() !== null && (this.runnerExitPct() ?? 0) < 0,
  );
```

Replace `targetText` (:139-141) with:

```ts
  protected readonly targetText = computed(() => {
    const exit = this.runnerExit();
    if (exit !== null) return this.fmt(exit);
    return this.bankedFill() !== null ? `${this.fmt(this.bankedFill())} ✓` : this.fmt(this.target());
  });
```

In `tooltip` (:149), make the closed runner its first case — insert as the first statement of the computed body, above the `// Names the role` comment:

```ts
    const runnerExit = this.runnerExit();
    if (runnerExit !== null) return this.closedRunnerTooltip(runnerExit);
```

Directly after the `tooltip` computed (after its closing `});`), add:

```ts

  private closedRunnerTooltip(exit: number): string {
    return `Entry ${this.fmt(this.entry())} · Runner exit (${runnerExitLabel(this.runnerExitReason())}): `
      + `${this.fmt(exit)}, ${this.signedPct(this.runnerExitPct())} per share from the original entry`
      + ` · Stop ${this.fmt(this.stop())}`;
  }
```

After `fmtPct` (:180-182), add:

```ts

  /** Signed, one decimal: a gain or loss per share, not a distance. */
  protected signedPct(v: number | null): string {
    return pct(v, 1);
  }
```

After the `formatR` const (:185), add:

```ts

interface TrailLine {
  best: number;
  exit: number;
  bestPct: number;
  exitPct: number;
}

const PLAN_LINE_TOOLTIP = 'Original plan (TP1 already filled): entry → TP1 / original stop. '
  + 'Percentages are the distance from the entry to each level.';
const SHORT_GAINS = 'A short gains when price falls.';
const LONG_GAINS = 'A long gains when price rises.';
const PAPER_LEVEL = "The bot's paper level: your broker's resting orders are not synced, update your stop yourself.";

const RUNNER_EXIT_LABELS: Readonly<Record<string, string>> = {
  tp1_runner_trail: 'trailing stop',
  giveback: 'give-back stop',
  tp1_runner_be: 'floor stop',
  tp1_runner_tp2: 'TP2',
  manual: 'manual close',
  tp1_runner_progress_stall: 'progress stall',
  time_exit: 'time exit',
};

/** What closed a runner, in words, for the closed cell's tooltip. The cell
 *  itself prints numbers only; an unknown leg reason reads "runner exit". */
export function runnerExitLabel(reason: string | null): string {
  return reason !== null && Object.hasOwn(RUNNER_EXIT_LABELS, reason)
    ? RUNNER_EXIT_LABELS[reason]
    : 'runner exit';
}
```

`PLAN_LINE_TOOLTIP`, `SHORT_GAINS`, `LONG_GAINS` and `PAPER_LEVEL` are module consts declared below the class; the class reads them only inside computeds and a field initialiser that runs at construction, after the module has loaded, so the order is safe (the same pattern `formatR` already uses).

Also extend the class doc comment (:15-17) with one paragraph, after the existing last sentence:

```ts
 *
 * v177: a PARTIAL runner with no TP2 reads on two lines (`planTp1` set) --
 * the original plan, then `Trail best → exit (peak% / exit%)` -- and a
 * closed partial trade shows the runner's exit in the target slot
 * (`runnerExit` set). The callers decide which through `runnerCellInputs`.
```

- [ ] **Step 4: Add the `TradeRow` fields**

In `frontend/src/app/api/models.ts`, directly after `best_pnl_pct?: number | null;` (:170), add:

```ts
  /** v177 -- the plan's ORIGINAL TP1, on a PARTIAL trailing-runner row only
   *  (the Plan cell's line 1); null everywhere else, leg rows included. */
  tp1?: number | null;
  /** v177 -- a CLOSED plan that banked TP1 and then closed its runner: the
   *  runner's actual exit price and what closed it (the runner leg's reason,
   *  `giveback`, or `manual`). Null on every other row. */
  runner_exit_price?: number | null;
  runner_exit_reason?: string | null;
```

The fields are optional so the `tradeRow()`/`row()` fixtures in `dashboard.spec.ts` and `trades.spec.ts` (which do not list them) keep compiling.

- [ ] **Step 5: Run the cell tests**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/plan-cell.spec.ts
Pop-Location
```

Expected: every test passes, every existing case unchanged plus the new ones; `0 failed`.

- [ ] **Step 6: Run the primitive gates and lint**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts --include src/app/ui/status-cell.spec.ts
npm run lint
Pop-Location
```

Expected: all pass (`gallery.spec.ts` renders the cell with no new inputs; `status-cell.spec.ts` reads `stop_pnl_pct`/`best_pnl_pct` unchanged). `npm run lint` ends with no error and no new entry in `eslint-suppressions.json`. A `primitives.spec.ts` failure naming `plan-cell.ts` means a colour literal or a `.pos`/`.neg`/`.muted` selector slipped in: use the tokens above.

- [ ] **Step 7: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell add frontend/src/app/ui/plan-cell.ts frontend/src/app/ui/plan-cell.spec.ts frontend/src/app/api/models.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell commit -m "feat(v177): PlanCell reads a trailing runner on two lines and a closed runner's exit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V177-3: Wire Dashboard and Trades templates through the status gate

**Model:** opus — two components that must give the same answer, a status gate whose one mistake (a TP1-leg row drawing the runner cell) is silent, and the first specs that render a Plan cell from a `TradeRow`

**Files:**
- Create: `frontend/src/app/ui/runner-cell.ts`
- Create: `frontend/src/app/ui/runner-cell.spec.ts`
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.ts` (import :30; `#planCell` template :317-333; exposed helpers :951-952)
- Modify: `frontend/src/app/workspaces/trades/trades.ts` (import :49; `#planCell` template :404-419; exposed helpers :919-920)
- Modify: `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (new `describe` appended after `Dashboard v85 layout`)
- Modify: `frontend/src/app/workspaces/trades/trades.spec.ts` (new helper and `describe` appended at the end)
- Modify: `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` (one test appended inside `describe('positions table')`)

**Interfaces:**
- Consumes: V177-2: `PlanCell` inputs `planTp1`, `planStop`, `trailBest`, `trailBestPct`, `trailExitPct`, `runnerExit`, `runnerExitPct`, `runnerExitReason`; DOM classes `.plan.runner`, `.line.l1`, `.line.l2`; `TradeRow.tp1?`, `TradeRow.runner_exit_price?`, `TradeRow.runner_exit_reason?`. From `main`: `bankedLegPct(entry, bankedEntry, direction)` (`ui/plan-cell.ts`), `TradeRow.risk_stop?`, `runner_best?`, `best_pnl_pct?`, `stop_pnl_pct?`, `banked_exit_price`; `tradeColumns()` (`workspaces/trades/trades.columns.ts`). V177-1's wire behaviour: `tp1`/`best_pnl_pct`/`stop_pnl_pct` are null on every leg row; `runner_exit_*` are null unless the plan is CLOSED after a runner close.
- Produces (consumed by V177-4; index § Gate contract):
  - `frontend/src/app/ui/runner-cell.ts` exports `interface RunnerCellInputs { planTp1; planStop; trailBest; trailBestPct; trailExitPct; runnerExit; runnerExitPct: number | null; runnerExitReason: string | null }`, `const NO_RUNNER_CELL: RunnerCellInputs` (every field null), `function runnerCellInputs(row: TradeRow): RunnerCellInputs`.
  - Both `Dashboard` and `Trades` expose `protected readonly runnerCellInputs = runnerCellInputs;` and their `#planCell` templates bind `@let rc = runnerCellInputs(row);` and pass the eight `rc.*` values.

**The gate (index § Gate contract, verbatim).** `status === 'PARTIAL' && bar_kind === 'trailing' && tp1 != null` → runner fields (`planTp1 = tp1`, `planStop = risk_stop`, `trailBest = runner_best ?? banked_exit_price`, `trailBestPct = best_pnl_pct`, `trailExitPct = stop_pnl_pct`); `status === 'CLOSED' && runner_exit_price != null` → closed fields (`runnerExit = runner_exit_price`, `runnerExitPct = bankedLegPct(entry, runner_exit_price, direction)`, `runnerExitReason = runner_exit_reason`); otherwise `NO_RUNNER_CELL`. The status check is what keeps the TP1-leg row of a still-PARTIAL plan (status `CLOSED`, `bar_kind` still `trailing`) on today's cell even if a field leaked; V177-1 also nulls the fields there, so both layers hold.

- [ ] **Step 1: Write the failing gate tests**

Create `frontend/src/app/ui/runner-cell.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { TradeRow } from '../api/models';
import { bankedLegPct } from './plan-cell';
import { NO_RUNNER_CELL, runnerCellInputs } from './runner-cell';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'RKLB',
    direction: 'bearish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 60.67, stop_loss: 61.85, target: 58.33, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 10, open_shares: null, position_value: null,
    current_price: null, current_price_stale: false, exit_price: null, realized_pnl_amount: null,
    pnl_pct: null, r_multiple: null, held_hours: null, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  };
}

/** The RKLB runner row as V177-1's backend serves it on the PARTIAL tab. */
const RKLB_RUNNER_ROW: Partial<TradeRow> = {
  status: 'PARTIAL', status_label: 'PARTIAL', stop_loss: 52.437, target: null,
  target_is_banked_tp1: true, stop_kind: 'trailing', bar_kind: 'trailing',
  banked_fraction: 0.5, banked_exit_price: 58.33, banked_r: 1.98,
  risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
  best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2,
};

describe('runnerCellInputs', () => {
  it('feeds the two-line cell from a PARTIAL trailing runner row', () => {
    expect(runnerCellInputs(row(RKLB_RUNNER_ROW))).toEqual({
      ...NO_RUNNER_CELL,
      planTp1: 58.33, planStop: 61.85,
      trailBest: 49.94, trailBestPct: 17.69, trailExitPct: 13.57,
    });
  });

  it('uses the TP1 fill as the best price until a tick has recorded one', () => {
    const rc = runnerCellInputs(row({ ...RKLB_RUNNER_ROW, runner_best: null }));
    expect(rc.trailBest).toBe(58.33);
  });

  it('passes a missing percentage through as null, so the cell drops line 2', () => {
    const rc = runnerCellInputs(row({ ...RKLB_RUNNER_ROW, best_pnl_pct: undefined }));
    expect(rc.planTp1).toBe(58.33);
    expect(rc.trailBestPct).toBeNull();
  });

  it('leaves a PARTIAL runner with a TP2 on today\'s cell', () => {
    expect(runnerCellInputs(row({ ...RKLB_RUNNER_ROW, bar_kind: 'progress', tp1: null })))
      .toEqual(NO_RUNNER_CELL);
  });

  it('leaves the TP1-leg row of a still-PARTIAL plan on today\'s cell', () => {
    // Status CLOSED, bar_kind still 'trailing' (the leg icon reads it); the
    // backend nulls tp1 and the percentages, and the runner has not closed.
    const leg = row({ ...RKLB_RUNNER_ROW, status: 'CLOSED', tp1: null,
      best_pnl_pct: null, stop_pnl_pct: null, runner_exit_price: null, leg_index: 0 });
    expect(runnerCellInputs(leg)).toEqual(NO_RUNNER_CELL);
  });

  it('never draws the runner cell on a CLOSED row, even if tp1 leaked', () => {
    expect(runnerCellInputs(row({ ...RKLB_RUNNER_ROW, status: 'CLOSED' }))).toEqual(NO_RUNNER_CELL);
  });

  it('feeds the closed cell from a CLOSED row with a runner exit', () => {
    const rc = runnerCellInputs(row({ runner_exit_price: 52.44, runner_exit_reason: 'tp1_runner_trail' }));
    expect(rc).toEqual({
      ...NO_RUNNER_CELL,
      runnerExit: 52.44,
      runnerExitPct: bankedLegPct(60.67, 52.44, 'bearish'),
      runnerExitReason: 'tp1_runner_trail',
    });
    expect(rc.runnerExitPct!).toBeCloseTo(13.565, 3);
  });

  it('signs a long runner closed below its entry as a loss', () => {
    const rc = runnerCellInputs(row({ direction: 'bullish', entry: 100, stop_loss: 90, target: 120,
      runner_exit_price: 97, runner_exit_reason: 'tp1_runner_be' }));
    expect(rc.runnerExitPct!).toBeCloseTo(-3, 6);
  });

  it('carries a missing reason as null', () => {
    expect(runnerCellInputs(row({ runner_exit_price: 52.44 })).runnerExitReason).toBeNull();
  });

  it('ignores a runner exit on a row that is not CLOSED', () => {
    expect(runnerCellInputs(row({ status: 'ACTIVE', runner_exit_price: 52.44 }))).toEqual(NO_RUNNER_CELL);
  });

  it('leaves PENDING, ACTIVE and legacy rows on today\'s cell', () => {
    for (const status of ['PENDING', 'ACTIVE', 'CANCELLED']) {
      expect(runnerCellInputs(row({ status }))).toEqual(NO_RUNNER_CELL);
    }
    expect(runnerCellInputs(row({ origin: 'legacy' }))).toEqual(NO_RUNNER_CELL);
  });

  it('returns null, never undefined, for every field', () => {
    expect(Object.values(NO_RUNNER_CELL).every((v) => v === null)).toBe(true);
    expect(Object.keys(NO_RUNNER_CELL).sort()).toEqual([
      'planStop', 'planTp1', 'runnerExit', 'runnerExitPct', 'runnerExitReason',
      'trailBest', 'trailBestPct', 'trailExitPct',
    ]);
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/runner-cell.spec.ts
Pop-Location
```

Expected: FAIL — `Cannot find module './runner-cell'` (or a resolve error naming it).

- [ ] **Step 3: Implement the gate**

Create `frontend/src/app/ui/runner-cell.ts`:

```ts
import { TradeRow } from '../api/models';
import { bankedLegPct } from './plan-cell';

/**
 * v177 -- which Plan cell a trades row gets, decided in one place.
 *
 * The Dashboard's positions table and the Trades page render the same
 * `TradeRow` through an identical `#planCell` template, so they must give
 * the same answer; both call this. The gate is keyed on `row.status`: the
 * TP1-leg row of a still-PARTIAL plan is a CLOSED row that keeps
 * `bar_kind: 'trailing'` (for its leg icon), and it must keep today's cell.
 */
export interface RunnerCellInputs {
  planTp1: number | null;
  planStop: number | null;
  trailBest: number | null;
  trailBestPct: number | null;
  trailExitPct: number | null;
  runnerExit: number | null;
  runnerExitPct: number | null;
  runnerExitReason: string | null;
}

/** Every input null: the cell renders exactly as it did before v177. */
export const NO_RUNNER_CELL: RunnerCellInputs = Object.freeze({
  planTp1: null,
  planStop: null,
  trailBest: null,
  trailBestPct: null,
  trailExitPct: null,
  runnerExit: null,
  runnerExitPct: null,
  runnerExitReason: null,
});

export function runnerCellInputs(row: TradeRow): RunnerCellInputs {
  if (row.status === 'PARTIAL' && row.bar_kind === 'trailing' && row.tp1 != null) {
    return {
      ...NO_RUNNER_CELL,
      planTp1: row.tp1,
      planStop: row.risk_stop ?? null,
      // Same fallback as the backend's percentages: the TP1 fill until a
      // tick has recorded a best price.
      trailBest: row.runner_best ?? row.banked_exit_price ?? null,
      trailBestPct: row.best_pnl_pct ?? null,
      trailExitPct: row.stop_pnl_pct ?? null,
    };
  }
  if (row.status === 'CLOSED' && row.runner_exit_price != null) {
    return {
      ...NO_RUNNER_CELL,
      runnerExit: row.runner_exit_price,
      runnerExitPct: bankedLegPct(row.entry, row.runner_exit_price, row.direction),
      runnerExitReason: row.runner_exit_reason ?? null,
    };
  }
  return NO_RUNNER_CELL;
}
```

- [ ] **Step 4: Run the gate tests**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/runner-cell.spec.ts
Pop-Location
```

Expected: all pass, `0 failed`.

- [ ] **Step 5: Write the failing template-wiring tests**

In `frontend/src/app/workspaces/trades/trades.spec.ts`, append at the end of the file:

```ts
/* -- v177: the Plan cell's runner forms on the Trades page -------------- */

/** The RKLB plan as V177-1 serves it: the realized TP1 leg (a CLOSED row
 *  of a still-PARTIAL plan), the open runner, and a second plan whose
 *  runner has closed. */
const RUNNER_ROWS: TradeRow[] = [
  row({ id: 'p1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
        stop_loss: 52.437, target: null, target_is_banked_tp1: true,
        stop_kind: 'trailing', bar_kind: 'trailing', exit_price: 58.33,
        risk_stop: 61.85, runner_best: 49.94, tp1: null, best_pnl_pct: null,
        stop_pnl_pct: null, runner_exit_price: null, runner_exit_reason: null,
        leg_index: 0, leg_total: 2 }),
  row({ id: 'p1', status: 'PARTIAL', status_label: 'PARTIAL', direction: 'bearish',
        entry: 60.67, stop_loss: 52.437, target: null, target_is_banked_tp1: true,
        stop_kind: 'trailing', bar_kind: 'trailing', banked_fraction: 0.5,
        banked_exit_price: 58.33, banked_r: 1.98, exit_price: null,
        risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
        best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2 }),
  row({ id: 'c1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
        stop_loss: 61.85, target: 58.33, exit_price: 52.44, tp1: null,
        runner_exit_price: 52.44, runner_exit_reason: 'tp1_runner_trail',
        leg_index: 1, leg_total: 2 }),
];

/** Trades with `items` in its store, the way the footer tests seed it. */
function renderRows(items: TradeRow[]): HTMLElement {
  const fixture = render();
  patchState(unprotected(TestBed.inject(TradesStore)), {
    data: { items, total: items.length, page: 1, per_page: 12 },
    query: { page: 1, per_page: 12 },
  });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const cellText = (el: Element): string => el.textContent!.replace(/\s+/g, ' ').trim();

describe('Trades — the Plan cell for runners (v177)', () => {
  it('renders one Plan cell per row', () => {
    expect(renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')).toHaveLength(3);
  });

  it('keeps today\'s single-line cell on the TP1-leg row of a still-PARTIAL plan', () => {
    const [leg] = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell');
    expect(leg.querySelector('.runner')).toBeNull();
    expect(leg.querySelector('.line')).toBeNull();
  });

  it('reads the open runner on two lines', () => {
    const runner = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')[1];
    expect(cellText(runner.querySelector('.l1')!)).toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
    expect(cellText(runner.querySelector('.l2')!)).toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('shows the closed runner\'s exit in the target slot', () => {
    const closed = renderRows(RUNNER_ROWS).querySelectorAll('sb-plan-cell')[2];
    expect(cellText(closed)).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(closed.querySelector('[title]')!.getAttribute('title'))
      .toContain('Runner exit (trailing stop): 52.44');
  });
});
```

In `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, append directly after the closing `});` of `describe('Dashboard v85 layout', …)`:

```ts
/* -- v177: the Plan cell's runner forms on the positions table ---------- */

/** Loaded, then the positions table's own trades request answered with
 *  `items`. The table is projected only after the dashboard payload lands,
 *  so its request is issued after `loaded()`'s first flush. One `#planCell`
 *  template serves every tab, so the tab only changes which rows arrive. */
async function loadedWithRows(items: TradeRow[]): Promise<HTMLElement> {
  const fixture = await loaded();
  const backend = TestBed.inject(HttpTestingController);
  for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
    req.flush({ items, total: items.length, page: 1, per_page: 10 });
  }
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('Dashboard Plan cell for runners (v177)', () => {
  const runner = tradeRow({
    id: 'p1', status: 'PARTIAL', status_label: 'PARTIAL', direction: 'bearish',
    entry: 60.67, stop_loss: 52.437, target: null, target_is_banked_tp1: true,
    stop_kind: 'trailing', bar_kind: 'trailing', banked_fraction: 0.5,
    banked_exit_price: 58.33, banked_r: 1.98, exit_price: null,
    risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
    best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2,
  });
  const tp1Leg = tradeRow({
    id: 'p1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
    stop_loss: 52.437, target: null, target_is_banked_tp1: true,
    stop_kind: 'trailing', bar_kind: 'trailing', exit_price: 58.33,
    risk_stop: 61.85, runner_best: 49.94, tp1: null, best_pnl_pct: null,
    stop_pnl_pct: null, runner_exit_price: null, leg_index: 0, leg_total: 2,
  });
  const closedRunner = tradeRow({
    id: 'c1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
    stop_loss: 61.85, target: 58.33, exit_price: 52.44, tp1: null,
    runner_exit_price: 52.44, runner_exit_reason: 'giveback', leg_index: 1, leg_total: 2,
  });

  it('reads a PARTIAL trailing runner on two lines', async () => {
    const [cell] = (await loadedWithRows([runner])).querySelectorAll('sb-plan-cell');
    expect(cell.querySelector('.l1')!.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
    expect(cell.querySelector('.l2')!.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('keeps today\'s cell on the TP1-leg row of a PARTIAL plan', async () => {
    const [cell] = (await loadedWithRows([tp1Leg])).querySelectorAll('sb-plan-cell');
    expect(cell.querySelector('.runner')).toBeNull();
  });

  it('shows a closed runner\'s exit and names the give-back stop', async () => {
    const [cell] = (await loadedWithRows([closedRunner])).querySelectorAll('sb-plan-cell');
    expect(cell.textContent!.replace(/\s+/g, ' ').trim()).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(cell.querySelector('[title]')!.getAttribute('title'))
      .toContain('Runner exit (give-back stop): 52.44');
  });
});
```

In `frontend/src/app/workspaces/dashboard/positions-table.spec.ts`, add `import { tradeColumns } from '../trades/trades.columns';` below the existing `PositionsTable` import, and append inside `describe('positions table', …)` after the last test:

```ts
  it('keeps the Plan column floor the two-line runner cell was measured against (v177)', () => {
    // Line 2 adds height, not width: the column keeps its 12rem floor and
    // stays inline from xs on every tab, PARTIAL and CLOSED included.
    const plan = tradeColumns().find((c) => c.key === 'plan')!;
    expect(plan.width).toBe('12rem');
    expect(plan.inlineFrom).toBe('xs');
  });
```

- [ ] **Step 6: Run them to verify the wiring tests fail**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts
Pop-Location
```

Expected: the "two lines" and "closed runner" cases FAIL (no `.l1` element; the closed cell still reads `58.33` in the target slot) in both files; the TP1-leg and Plan-column-floor cases already pass (they pin today's behaviour); every pre-existing test passes. If `sb-plan-cell` is not found at all (`renders one Plan cell per row` fails with length 0, or `cell` is `undefined` in the dashboard cases), the rows have not reached the table: in `trades.spec.ts` confirm `TradesStore` is the instance `render()` provided; in `dashboard.spec.ts` log `backend.match(() => true).map((r) => r.request.urlWithParams)` after `loaded()` to see the positions table's request and flush that one. Fix the harness, not the assertion.

- [ ] **Step 7: Wire the two templates**

In `frontend/src/app/workspaces/dashboard/dashboard.ts`:

1. Below the `PlanCell` import (:30) add:

```ts
import { runnerCellInputs } from '../../ui/runner-cell';
```

2. Replace the `#planCell` template (:317-333) with:

```html
    <ng-template #planCell let-row>
      <!-- v177: runnerCellInputs keys the two-line runner cell and the
           closed runner's exit on row.status -- identical in trades.ts. -->
      @let rc = runnerCellInputs(row);
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
        [stopKind]="row.stop_kind"
        [targetIsBankedTp1]="row.target_is_banked_tp1"
        [floorR]="row.floor_r" [priceR]="row.price_r" [headroomR]="row.headroom_r"
        [bankedFraction]="row.banked_fraction"
        [bankedR]="row.banked_r"
        [bankedEntry]="row.banked_exit_price"
        [bankedPct]="bankedLegPct(row.entry, row.banked_exit_price, row.direction)"
        [bankedAmount]="bankedLegAmount(row.entry, row.banked_exit_price, row.banked_fraction, row.shares, row.direction)"
        [planTp1]="rc.planTp1" [planStop]="rc.planStop"
        [trailBest]="rc.trailBest" [trailBestPct]="rc.trailBestPct" [trailExitPct]="rc.trailExitPct"
        [runnerExit]="rc.runnerExit" [runnerExitPct]="rc.runnerExitPct" [runnerExitReason]="rc.runnerExitReason"
        [currency]="connection.currency()"
      />
    </ng-template>
```

3. After `protected bankedLegAmount = bankedLegAmount;` (:952) add:

```ts
  protected readonly runnerCellInputs = runnerCellInputs;
```

In `frontend/src/app/workspaces/trades/trades.ts`, make the same three edits: the import below the `PlanCell` import (:49); the identical `#planCell` block above replacing :404-419 (comment text: `identical in dashboard.ts`); and `protected readonly runnerCellInputs = runnerCellInputs;` after `protected bankedLegAmount = bankedLegAmount;` (:920).

- [ ] **Step 8: Run the wiring tests**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/runner-cell.spec.ts --include src/app/ui/plan-cell.spec.ts --include src/app/workspaces/trades/trades.spec.ts --include src/app/workspaces/dashboard/dashboard.spec.ts --include src/app/workspaces/dashboard/positions-table.spec.ts --include src/app/workspaces/dashboard/dashboard.helpers.spec.ts
Pop-Location
```

Expected: all pass, `0 failed`.

- [ ] **Step 9: Gates and lint**

```powershell
Push-Location E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell/frontend
npx ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/async-coverage.spec.ts --include src/app/ui/breakpoint-guard.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/workspaces/gallery/gallery.spec.ts
npm run lint
Pop-Location
```

Expected: all pass; lint clean with no new `eslint-suppressions.json` entry. If a gate spec path does not exist, drop it from the command (they are listed from the v166 plan's gate set) — never skip `primitives.spec.ts`.

- [ ] **Step 10: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell add frontend/src/app/ui/runner-cell.ts frontend/src/app/ui/runner-cell.spec.ts frontend/src/app/workspaces/dashboard/dashboard.ts frontend/src/app/workspaces/trades/trades.ts frontend/src/app/workspaces/dashboard/dashboard.spec.ts frontend/src/app/workspaces/trades/trades.spec.ts frontend/src/app/workspaces/dashboard/positions-table.spec.ts
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v177-runner-plan-cell commit -m "feat(v177): Dashboard and Trades pass the runner Plan cell through one status gate" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

