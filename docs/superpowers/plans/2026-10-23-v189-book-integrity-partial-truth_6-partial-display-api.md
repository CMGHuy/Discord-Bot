# v189 — Book integrity and partial-trade truth: Implementation Plan, part 6 of 7 — partial trades on the API: rows, risk of loss, label basis

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier. **Never read this part whole**: `grep -n "^### Task V189-19:" -A 520 <this file>`.

**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — D5 (B1, B3, B4), D6, § Testing (golden trade: trades row, dashboard realized parts and risk figures); `## Corrections from the code brief` 2 (the Dashboard win rate counts legs, so the D6 tile is Analytics only) wins over earlier sections.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — `## Global Constraints`, `## Spec clarifications` 7 (dashboard JSON rename), `## Contracts` § Display and § Golden fixture, `## Parallelisation`, the task ledger.
**Worktree:** `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth`. Every path below is relative to it; every command runs from it. Agent shells drop variables between calls, so `cd "$WT"` means `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth; cd "$WT" && ...` in the same command.

**Consumed from earlier parts (re-read each as merged with `git grep -n` before use):**

- V189-1 (part 1): `metrics.banked_contribution_r(legs) -> float | None`, `metrics.open_trade_r(trade, quote) -> float | None` (unrounded; `trade` needs `entry`, `stop_loss`, `direction`, optional `legs`), `performance.closed_r_multiple` delegating to `metrics.r_multiple`.
- V189-2 (part 1): `metrics.LABEL_BASIS_SINCE` (None), `metrics.net_outcome`, the golden fixture `tests/analytics/golden_partial_trade.json`, and the helpers `load_golden`, `closed_case`, `open_case`, `golden_closed_trade(case, *, closed_at=None, trade_id="golden-1", runner_reason="manual")`, `golden_open_trade(*, trade_id="golden-open")` in `tests/analytics/test_golden_partial_trade_metrics.py`.
- V189-12 (part 4): `scan_run._settle_reversal` extracted out of `_sync_run_scan` (so `_sync_run_scan` is already below 96 when V189-19 edits it). V189-19 adds no branch to `_sync_run_scan`.

**Decisions this part writes down (within the spec, not new scope):**

1. **An open plan has at most one realized leg, its TP1 leg** (`_step_active` and `_check_bar_active` are the only writers of a leg on a plan that stays open). So the row's own `banked_fraction` / `banked_r` (the first leg, `plan_view`'s `banked`) are the whole realized part of an open PARTIAL, and `_attach_unrealized_pnl` can call `metrics.open_trade_r` with that one leg rebuilt from the row. No transient legs key is put on the row: `trade_commands._plan_row` serialises `_row_from_plan` without `_strip_internal_fields`, so a transient key would leak there.
2. **A row with no banked leg keeps today's live R** (`dash.unrealized_r`), including a PARTIAL plan whose `legs_realized` is empty (`test_unrealized_pnl_uses_the_original_stop_not_the_working_stop` pins it).
3. **`position_risk_of_loss(trade, plan)` takes the plan as a stored record (`dict`)**, the shape `equity.load_plans_by_id()` returns, or `None` for a trade with no plan. The index writes `plan.working_stop`; that is `plan.get("working_stop")` here. Nothing outside this part calls it.
4. **Risk of loss spans both ledgers, like enforced heat** (it is portfolio exposure and sits beside `open_heat`). `risk_of_loss_pct` is `None` when the balance is not positive.
5. **`label_counts` counts `status == "closed"` rows by exact `close_reason`** (`"scratch"`, `"unscored"`), over the same scoped `closed` list `win_rate` reads.

**Test files outside the ledger rows.** Three existing contract tests assert an exact key set (`assert_shape` fails on an undeclared key), so adding a key to a payload means declaring it there in the same task: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW`, and the one PARTIAL live-R test whose expected value changes by design) in V189-18; `tests/admin/test_api_v1_risk.py` (the position-row shape) in V189-19; `tests/admin/test_api_v1_analytics.py` and `tests/admin/test_api_analytics.py` (the performance top-level shape) in V189-20.

---

# Phase F — Partial trades on the API

### Task V189-18: Trades API rows: entry_shares, banked contribution, blended open R

**Model:** sonnet — three small helpers and two new row keys in one API module, pinned by the shared golden fixture; the only judgement call (which leg feeds the blend) is decided in this part's header.

**Spec:** D5 B1 (`entry_shares`; `shares` keeps meaning the remaining count), B3 (`banked_r` keeps its meaning; new `banked_contribution_r`; open PARTIAL `r_multiple` null without a quote, blended with one); § Testing (golden trades-row figures); index § Contracts / Display; this part's decisions 1 and 2.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (imports `:40-50`; `_row_from_plan` `:256-369`; new helpers after `_runner_cell_fields` `:447-452`; `_row_from_leg` `:499-558`; `_row_from_trade` `:583-667`; `_attach_unrealized_pnl` `:1221-1255`)
- Modify: `tests/admin/test_trades_partial_row.py` (`test_banked_leg_fields_survive_projection`; one new test)
- Modify: `tests/admin/test_api_v1_trades.py` (`TRADE_ROW` `:34-130`; `test_partial_r_multiple_is_still_measured_against_the_original_stop` `:1372-1381`) — outside the ledger row, see the part header
- Create: `tests/admin/test_trades_golden_rows.py`

**Interfaces:**
- Consumes: `metrics.banked_contribution_r(legs)`, `metrics.open_trade_r(trade, quote)` (V189-1); the golden helpers (V189-2); `tests.admin.test_trades_partial_row.partial_plan(**kw)` (exists).
- Produces (read by V189-21 and V189-22 in part 7): every trades row (plan, leg and legacy; list and detail) carries `entry_shares: float | None` (the original position size: the linked trade's `shares`, `None` without a trade) and `banked_contribution_r: float | None` (`Σ fraction × r` over the plan's realized legs on a plan row that has a banked leg; `None` on leg rows, legacy rows and rows with nothing banked). An open PARTIAL row's `r_multiple` is `None` until priced and `round(metrics.open_trade_r(...), 2)` once priced. `banked_r`, `shares`, `open_shares` are unchanged.

- [ ] **Step 1: Write the failing golden row tests**

Create `tests/admin/test_trades_golden_rows.py`:

```python
"""v189 B1/B3: the golden scaled-out trade on the Trades API rows.

Every expected figure comes from `tests/analytics/golden_partial_trade.json`
(hand-computed: 100 sh, f 0.5, entry 100, stop 95 so 1R = $5/share, TP1 +2R
on 50% = +1.0R and $500). The Vitest specs read the same file (V189-21/22),
so the API and the screen cannot drift.
"""
import pytest

import swingbot.admin.app  # noqa: F401 -- initializes API routes before importing one endpoint
from swingbot.admin.api_v1.trades import (_attach_unrealized_pnl, _expand_plan_row,
                                          _row_from_plan, _row_from_trade,
                                          _strip_internal_fields)
from tests.admin.test_trades_partial_row import partial_plan
from tests.analytics.test_golden_partial_trade_metrics import (closed_case,
                                                               golden_closed_trade,
                                                               golden_open_trade,
                                                               load_golden, open_case)

G = load_golden()
TOL = G["tolerance"]
OPEN = [c["name"] for c in G["open_cases"]]
CLOSED = [c["name"] for c in G["closed_cases"]]
PLAN_ID = "golden-plan"


def golden_plan(status: str = "PARTIAL", legs: list[dict] | None = None) -> dict:
    """The golden trade's plan: TP1 banked, the runner's stop at the v39 floor."""
    g = G["trade"]
    if legs is None:
        legs = [dict(g["tp1_leg"], closed_at="2026-08-02T14:00:00+00:00")]
    return partial_plan(plan_id=PLAN_ID, ticker=g["ticker"], status=status,
                        direction=g["direction"], entry_price=g["entry"],
                        trigger_price=g["entry"], stop_loss=g["stop_loss"],
                        tp1=g["tp1"], tp2=g["tp2"], tp1_fraction=g["tp1_fraction"],
                        working_stop=open_case("quote_113")["working_stop"],
                        legs_realized=legs)


def priced_rows(plan: dict, trade: dict, quote: float | None, *, passes: int = 1) -> list[dict]:
    """`list_trades`' order: expand, price the open rows, attach live P&L
    (`passes` times, as a sort on r_multiple does), strip transient keys."""
    rows = _expand_plan_row(plan, trade, set())
    for row in rows:
        if row["status"] not in ("CLOSED", "CANCELLED"):
            row["current_price"] = quote
    for _ in range(passes):
        _attach_unrealized_pnl(rows)
    _strip_internal_fields(rows)
    return rows


def open_trade() -> dict:
    return dict(golden_open_trade(), plan_id=PLAN_ID)


@pytest.mark.parametrize("name", OPEN)
def test_open_runner_row_matches_the_golden_case(name):
    case = open_case(name)
    runner = priced_rows(golden_plan(), open_trade(), case["quote"])[-1]
    assert runner["status"] == "PARTIAL"
    assert runner["shares"] == case["shares"]                    # remaining, as today
    assert runner["entry_shares"] == case["entry_shares"]        # B1: the original size
    assert runner["banked_r"] == pytest.approx(case["banked_r"])  # the TP1 leg's own R, unchanged
    assert runner["banked_contribution_r"] == pytest.approx(case["banked_contribution_r"])
    assert runner["realized_pnl_amount"] == (
        None if case["unrealized_pnl_amount"] is None
        else pytest.approx(case["unrealized_pnl_amount"], abs=0.01))
    if case["r_multiple"] is None:
        assert runner["r_multiple"] is None                      # never the banked R alone
    else:
        assert runner["r_multiple"] == pytest.approx(case["r_multiple"], abs=TOL)


@pytest.mark.parametrize("name", OPEN)
def test_banked_dollars_are_priced_on_entry_shares(name):
    """B1: the banked leg is fraction x ORIGINAL size. On `shares` (the
    remaining 50) it reads $250, the (1 - f) bug the screens showed."""
    case = open_case(name)
    runner = priced_rows(golden_plan(), open_trade(), case["quote"])[-1]
    move = runner["banked_exit_price"] - runner["entry"]
    assert move * runner["entry_shares"] * runner["banked_fraction"] == pytest.approx(
        case["banked_amount"])
    assert move * runner["shares"] * runner["banked_fraction"] != pytest.approx(
        case["banked_amount"])


def test_the_banked_tp1_leg_row_is_its_own_closed_trade():
    leg = priced_rows(golden_plan(), open_trade(), open_case("quote_113")["quote"])[0]
    assert leg["status"] == "CLOSED"
    assert (leg["shares"], leg["entry_shares"]) == (50.0, 100)
    assert leg["r_multiple"] == pytest.approx(2.0)
    assert leg["realized_pnl_amount"] == pytest.approx(500.0)
    assert (leg["banked_r"], leg["banked_contribution_r"]) == (None, None)


def test_a_second_attach_pass_keeps_the_blended_r():
    """A sort on r_multiple prices every row first, then the page again."""
    runner = priced_rows(golden_plan(), open_trade(), 113.0, passes=2)[-1]
    assert runner["r_multiple"] == pytest.approx(2.3, abs=TOL)
    assert runner["shares"] == 50.0


@pytest.mark.parametrize("name", CLOSED)
def test_closed_whole_position_row_matches_the_golden_case(name):
    case = closed_case(name)
    trade = dict(golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00"),
                 plan_id=PLAN_ID)
    row = _row_from_plan(golden_plan("CLOSED", legs=trade["legs"]), trade, set())
    assert row["outcome"] == case["status"]
    assert (row["shares"], row["entry_shares"]) == (100, 100)
    assert row["r_multiple"] == pytest.approx(case["net_r"], abs=TOL)
    assert row["realized_pnl_amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    assert row["pnl_pct"] == pytest.approx(case["pnl_pct"], abs=TOL)
    # banked_contribution_r travels with banked_r: both or neither.
    assert (row["banked_r"] is None) == (row["banked_contribution_r"] is None)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_leg_rows_sum_to_the_trades_realized_dollars(name):
    case = closed_case(name)
    trade = dict(golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00"),
                 plan_id=PLAN_ID)
    rows = _expand_plan_row(golden_plan("CLOSED", legs=trade["legs"]), trade, set())
    assert [r["shares"] for r in rows] == [50.0, 50.0]
    assert [r["entry_shares"] for r in rows] == [100, 100]
    assert rows[0]["r_multiple"] == pytest.approx(2.0)
    assert rows[1]["r_multiple"] == pytest.approx(case["runner_r"], abs=TOL)
    assert sum(r["realized_pnl_amount"] for r in rows) == pytest.approx(
        case["realized_pnl_amount"], abs=0.01)


def test_a_bearish_runner_blends_with_the_sign_flipped():
    """The golden trade mirrored: entry 100, stop 105, TP1 90 (+2R on 50%),
    quote 87 is +2.6R live, so 1.0 + 0.5 x 2.6 = 2.30R."""
    plan = partial_plan(plan_id=PLAN_ID, direction="bearish", entry_price=100.0,
                        trigger_price=100.0, stop_loss=105.0, tp1=90.0, tp2=80.0,
                        working_stop=93.33333333333333, tp1_fraction=0.5,
                        legs_realized=[{"fraction": 0.5, "exit_price": 90.0, "r": 2.0,
                                        "reason": "tp1"}])
    trade = dict(open_trade(), direction="bearish", stop_loss=105.0)
    runner = priced_rows(plan, trade, 87.0)[-1]
    assert runner["banked_contribution_r"] == pytest.approx(1.0)
    assert runner["r_multiple"] == pytest.approx(2.3, abs=TOL)


def test_a_banked_leg_without_r_has_no_blended_r():
    """A leg written without `r` cannot be weighted: the row says so (None)
    rather than showing the whole position's live R (2.6) as the trade's."""
    plan = golden_plan(legs=[{"fraction": 0.5, "exit_price": 110.0, "reason": "tp1"}])
    runner = priced_rows(plan, open_trade(), 113.0)[-1]
    assert runner["banked_contribution_r"] is None
    assert runner["r_multiple"] is None


def test_an_active_row_keeps_the_whole_position_live_r():
    plan = golden_plan("ACTIVE", legs=[])
    plan["working_stop"] = None
    row = priced_rows(plan, open_trade(), 113.0)[0]
    assert row["r_multiple"] == pytest.approx(2.6)               # (113 - 100) / 5, as today
    assert (row["entry_shares"], row["shares"]) == (100, 100)
    assert row["banked_contribution_r"] is None


def test_a_legacy_row_carries_entry_shares_and_no_banked_contribution():
    trade = {"id": "L1", "ticker": "AAPL", "status": "open", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "shares": 7,
             "opened_at": "2026-09-01T09:00:00+00:00"}
    row = _row_from_trade(trade, set())
    assert (row["entry_shares"], row["banked_contribution_r"]) == (7, None)
```

- [ ] **Step 2: Extend the existing partial-row tests**

In `tests/admin/test_trades_partial_row.py`, replace `test_banked_leg_fields_survive_projection` with:

```python
def test_banked_leg_fields_survive_projection():
    """`banked_r` keeps its meaning, the TP1 leg's own R (v189 B3); the
    trade-level banked figure is the new `banked_contribution_r` = 0.5 x 2.1."""
    row = _row_from_plan(partial_plan(), None, set())
    assert (row["banked_fraction"], row["banked_exit_price"], row["banked_r"]) == (0.5, 121.0, 2.1)
    assert row["banked_contribution_r"] == pytest.approx(1.05)
```

and add, below it:

```python
def test_an_unpriced_partial_row_has_no_r_multiple():
    """v189 B3: without a quote an open PARTIAL has no trade R. It used to
    show the banked blend (here 1.05) as if it were the trade's R."""
    trade = {"id": "t1", "shares": 10, "status": "open", "entry": 100.0,
             "stop_loss": 90.0, "direction": "bullish",
             "legs": [{"fraction": 0.5, "exit_price": 121.0, "r": 2.1}]}
    row = _row_from_plan(partial_plan(), trade, set())
    assert row["r_multiple"] is None
    assert row["entry_shares"] == 10
```

Add `import pytest` at the top of the file (after the module docstring) if it is not there.

In `tests/admin/test_api_v1_trades.py`:

- In `TRADE_ROW`, after `"banked_r": NULLABLE_NUMBER,` add:

```python
    # v189 B3 -- the realized legs' contribution to the trade's R
    # (sum of fraction x r); `banked_r` stays the TP1 leg's own R.
    "banked_contribution_r": NULLABLE_NUMBER,
```

  and after `"open_shares": NULLABLE_NUMBER,` add:

```python
    # v189 B1 -- the ORIGINAL position size. `shares` is the remaining count
    # on an open PARTIAL row (v79), so a banked-leg dollar figure scales by this.
    "entry_shares": NULLABLE_NUMBER,
```

- In `test_partial_r_multiple_is_still_measured_against_the_original_stop`, replace the final assertion with:

```python
    # v189 B3: the trade's blended R. Banked 0.5 x 1.5 = 0.75, plus the open
    # half's live move against the ORIGINAL risk: 0.5 x (115 - 101) / (101 - 95).
    assert runner["r_multiple"] == pytest.approx(0.75 + 0.5 * (115.0 - 101.0) / 6.0, abs=0.01)
```

  and change its docstring to `"""Live R on a PARTIAL is the blended trade R; its open part is still measured against the original stop."""`.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_trades_golden_rows.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py
```

Expected: FAIL — `KeyError: 'entry_shares'` / `'banked_contribution_r'`; `test_an_unpriced_partial_row_has_no_r_multiple` fails with `1.05 is not None`; the `quote_113` case fails with `2.6 != 2.3`.

- [ ] **Step 4: Implement the row fields in `swingbot/admin/api_v1/trades.py`**

Add the import beside the other `swingbot.core` imports (first check `git grep -n "metrics" swingbot/admin/api_v1/trades.py` shows no other `metrics` name; there is none on `main` today):

```python
from swingbot.core.analytics import metrics
```

Add these helpers directly after `_runner_cell_fields`:

```python
def _banked_contribution(plan: dict, view) -> float | None:
    """v189 B3: the realized legs' share of the trade's R, `Σ fraction x r`
    (+1.00R for a +2R TP1 on half). Present exactly when `banked_r` is;
    `banked_r` keeps meaning the TP1 leg's own R."""
    if view.banked is None:
        return None
    return metrics.banked_contribution_r(plan.get("legs_realized") or [])


def _plan_row_r(plan: dict, trade: dict | None) -> float | None:
    """A closed plan's R is its trade's blended R. An open plan has none
    until `_attach_unrealized_pnl` prices it: the banked blend alone is not
    the trade's R (v189 B3)."""
    if trade is None or plan.get("status") not in _TERMINAL:
        return None
    return dash.closed_r(trade)


def _live_r(row: dict, price: float) -> float | None:
    """Live R for an open row. A row with a banked TP1 leg gets the blended
    trade R, `metrics.open_trade_r` over that one leg (an open plan has
    realized at most its TP1 leg) -- None when the leg has no `r`. A row
    with nothing banked keeps the whole position's live R. Both measure
    against the ORIGINAL stop (`risk_stop`)."""
    entry, stop, direction = row.get("entry"), row.get("risk_stop"), row.get("direction")
    if row.get("banked_fraction") is None:
        return dash.unrealized_r(entry, stop, direction, price)
    banked_leg = {"fraction": row["banked_fraction"], "r": row.get("banked_r")}
    blended = metrics.open_trade_r(
        {"entry": entry, "stop_loss": stop, "direction": direction, "legs": [banked_leg]}, price)
    return None if blended is None else round(blended, 2)
```

In `_row_from_plan`'s `row = {...}` literal (no new branch: the function is baselined at complexity 15 and drops to 14):

- after `"banked_r": view.banked.r if view.banked else None,` add `"banked_contribution_r": _banked_contribution(plan, view),`
- after `"shares": t.get("shares"),` add `"entry_shares": t.get("shares"),` with a one-line comment: the ORIGINAL size, because `shares` becomes the remaining count on an open PARTIAL row in `_strip_internal_fields` (v189 B1).
- replace `"r_multiple": dash.closed_r(t) if trade else None,` with `"r_multiple": _plan_row_r(plan, trade),`

In `_row_from_leg`'s `row.update({...})`, after `"banked_r": None,` add `"banked_contribution_r": None,` (a leg row is a closed trade of its own; `entry_shares` is inherited from `_row_from_plan` unchanged).

In `_row_from_trade`'s literal, after `"banked_r": None,` add `"banked_contribution_r": None,` and after `"shares": t.get("shares"),` add `"entry_shares": t.get("shares"),`.

In `_attach_unrealized_pnl`, replace

```python
            row["r_multiple"] = dash.unrealized_r(entry, row.get("risk_stop"), direction, price)
```

with

```python
            row["r_multiple"] = _live_r(row, price)
```

and add to its docstring: `` v189 B3: a row with a banked TP1 leg gets the blended trade R (`_live_r`). ``

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_trades_golden_rows.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_trades_partial_row.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_commands.py
```

Expected: all PASS. If another admin test fails on an undeclared `entry_shares` / `banked_contribution_r` key, declare the key in that test's shape (it is the same row contract); never drop the key.

- [ ] **Step 6: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `_row_from_plan` is 14 (baseline 15), `_attach_unrealized_pnl` stays 7, the three helpers are at most 3. If the gate reports that `_row_from_plan` now sits below its recorded baseline, run `python scripts/dev/complexity_gate.py --update` (it only shrinks entries) and stage `scripts/dev/complexity_baseline.json` in the commit below.

- [ ] **Step 7: Commit**

```bash
cd "$WT" && git add swingbot/admin/api_v1/trades.py tests/admin/test_trades_golden_rows.py tests/admin/test_trades_partial_row.py tests/admin/test_api_v1_trades.py && git commit -m "feat(api): trades rows carry entry_shares, banked_contribution_r and the blended open R (v189 B1/B3)"
```

### Task V189-19: Risk of loss beside enforced heat; heat-blocked log line

**Model:** opus — a new risk definition shown beside the enforced one on two payloads, a JSON key rename the frontend follows later, and a log line inside the baselined `_sync_run_scan`; a wrong sign or a dropped PENDING filter misstates the account's exposure.

**Spec:** D5 B4 (risk of loss = Σ over filled open trades of open shares × distance from entry to the current working stop on the loss side, floored at 0 per trade, PENDING placeholders excluded; "Heat (enforced)" = `open_heat` beside it; the Risk page keeps its rows summing to `open_heat` and gains a Risk-of-loss column; a new INFO line when the heat cap blocks an alert; display only); § Testing (dashboard realized parts and risk figures for the golden trade); index clarification 7; this part's decisions 3 and 4.

**Files:**
- Modify: `swingbot/core/edge/heat.py` (new function after `open_heat` `:23-24`; `import math`)
- Modify: `swingbot/core/tracking/equity.py` (new function after `held_now` `:163-180`)
- Modify: `swingbot/admin/api_v1/dashboard.py` (module docstring `:12-15`; `_risk_used` `:70-98` replaced; the payload `:330-338`)
- Modify: `swingbot/admin/api_v1/risk.py` (`_positions` `:56-82`; one new helper)
- Modify: `swingbot/core/scanning/scan_run.py` (one module-level helper; one call inside the heat gate of `_sync_run_scan`, found with `git grep -n "heat_chk = heat_mod.heat_check" swingbot/core/scanning/scan_run.py`)
- Modify: `tests/admin/test_api_v1_dashboard.py` (`DASHBOARD` `:30-36`; `test_risk_used_skips_the_full_portfolio_collector` `:253-277`; `_PARITY_KEYS` `:643-645`; module docstring `:9`)
- Modify: `tests/admin/test_api_v1_risk.py` (the position-row shape in `test_position_rows_sum_to_open_heat` `:187-191`) — outside the ledger row, see the part header
- Create: `tests/edge/test_risk_of_loss.py`, `tests/admin/test_risk_of_loss_api.py`

**Interfaces:**
- Consumes: the golden helpers (V189-2); `tests.admin.test_api_v1_trades._plan`, `_trade` (exist); `equity.open_shares`, `equity.load_plans_by_id`, `equity._LIVE_PLAN_STATUSES` (exist); `dashboard._realized_parts`, `dashboard._realized` (exist).
- Produces (read by V189-23 in part 7):
  - `heat.risk_of_loss_amount(entry, working_stop, direction: str, open_shares) -> float` — `open_shares × max(0, entry − stop)` bullish, `× max(0, stop − entry)` bearish, rounded to cents; `0.0` on a missing or non-finite input or a direction that is neither.
  - `equity.position_risk_of_loss(trade: dict, plan: dict | None) -> float | None` — `None` when the plan is not ACTIVE/PARTIAL (a PENDING placeholder, or a terminal plan); a trade with no plan uses its own `stop_loss` and `shares`; otherwise `plan["working_stop"] or plan["stop_loss"]` and `open_shares(trade shares, plan legs)`.
  - `scan_run._log_heat_block(ticker: str, enforced_pct: float, add_pct: float, cap_pct: float) -> None` — INFO `heat blocked (enforced %.2f%% + %.2f%% > cap %.2f%%) %s`.
  - Dashboard JSON: `risk_used_pct` is gone; `heat_enforced_pct` (= `heat.open_heat` over every open trade, both ledgers, as before), `risk_of_loss_amount` (cents), `risk_of_loss_pct` (`amount / balance × 100`, 3 dp; `None` when the balance is not positive), `risk_cap_pct` (unchanged). Every value but the cap degrades to `None` on a failure, as `_risk_used` did.
  - Risk page position row: `risk_of_loss_amount: float | None`, `risk_of_loss_pct: float | None` beside the unchanged `risk_pct`; both `None` for a PENDING placeholder. `heat.open_pct` and `utilisation_pct` are unchanged.

`heat.open_heat`, `heat.heat_check`, the scanner gate and `analyze.py:252` are not edited: B4 is display only (index Global Constraints).

- [ ] **Step 1: Write the failing core tests**

Create `tests/edge/test_risk_of_loss.py`:

```python
"""v189 B4: risk of loss to the stop -- what a fill at the current working
stop would still lose below entry, floored at 0 per position. Shown beside
enforced heat, never instead of it (display only)."""
import ast
import logging
import math
from pathlib import Path

import pytest

from swingbot.core.edge.heat import risk_of_loss_amount
from swingbot.core.scanning import scan_run
from swingbot.core.tracking.equity import position_risk_of_loss
from tests.analytics.test_golden_partial_trade_metrics import (golden_open_trade,
                                                               load_golden, open_case)

G = load_golden()["trade"]


def test_a_long_stop_below_entry_loses_shares_times_distance():
    assert risk_of_loss_amount(100.0, 95.0, "bullish", 100) == 500.0


def test_a_short_stop_above_entry_loses_shares_times_distance():
    assert risk_of_loss_amount(100.0, 105.0, "bearish", 40) == 200.0


@pytest.mark.parametrize("entry, stop, direction", [
    (100.0, 106.66666666666667, "bullish"),   # the golden runner floor
    (100.0, 100.0, "bullish"),                # break-even
    (100.0, 93.0, "bearish"),                 # a short's stop ratcheted into profit
])
def test_a_stop_at_or_past_entry_risks_nothing(entry, stop, direction):
    assert risk_of_loss_amount(entry, stop, direction, 50) == 0.0


@pytest.mark.parametrize("entry, stop, direction, shares", [
    (None, 95.0, "bullish", 100), (100.0, None, "bullish", 100),
    (100.0, 95.0, "bullish", None), (math.nan, 95.0, "bullish", 100),
    (100.0, math.inf, "bearish", 100), (100.0, 95.0, "bullish", math.nan),
    (100.0, 95.0, "sideways", 100),
])
def test_missing_or_non_finite_inputs_are_zero_never_nan(entry, stop, direction, shares):
    assert risk_of_loss_amount(entry, stop, direction, shares) == 0.0


def _plan(status: str, *, working_stop=None, legs=None) -> dict:
    return {"plan_id": "golden-plan", "status": status, "direction": G["direction"],
            "entry_price": G["entry"], "stop_loss": G["stop_loss"],
            "working_stop": working_stop, "legs_realized": legs or []}


@pytest.mark.parametrize("name", [c["name"] for c in load_golden()["open_cases"]])
def test_the_golden_runner_at_its_floor_risks_nothing(name):
    case = open_case(name)
    plan = _plan("PARTIAL", working_stop=case["working_stop"], legs=[dict(G["tp1_leg"])])
    assert position_risk_of_loss(golden_open_trade(), plan) == case["risk_of_loss_amount"]


def test_an_active_plan_without_a_working_stop_uses_its_risk_stop():
    assert position_risk_of_loss(golden_open_trade(), _plan("ACTIVE")) == 500.0   # 100 x (100 - 95)


def test_a_break_even_stop_risks_nothing():
    assert position_risk_of_loss(golden_open_trade(), _plan("ACTIVE", working_stop=100.0)) == 0.0


def test_a_partial_counts_only_its_open_shares():
    """50 shares still held after TP1, stop back at the risk stop: 50 x 5."""
    plan = _plan("PARTIAL", legs=[dict(G["tp1_leg"])])
    assert position_risk_of_loss(golden_open_trade(), plan) == 250.0


@pytest.mark.parametrize("status", ["PENDING", "CLOSED", "CANCELLED"])
def test_a_plan_that_is_not_held_has_no_risk_of_loss(status):
    assert position_risk_of_loss(golden_open_trade(), _plan(status)) is None


def test_a_trade_with_no_plan_uses_its_own_stop_and_size():
    assert position_risk_of_loss(golden_open_trade(), None) == 500.0


def test_the_heat_block_line_names_the_enforced_heat(caplog):
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._log_heat_block("AAPL", 5.4, 1.0, 6.0)
    assert "heat blocked (enforced 5.40% + 1.00% > cap 6.00%) AAPL" in caplog.text


def test_the_scan_heat_gate_logs_every_block():
    """The confluence lane's heat gate is inline in `_sync_run_scan`; pin
    that the branch which flags `item.heat_blocked` also logs the line."""
    tree = ast.parse(Path(scan_run.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_sync_run_scan")
    gate = next(n for n in ast.walk(fn)
                if isinstance(n, ast.If) and "heat_chk" in ast.unparse(n.test))
    called = {ast.unparse(c.func) for c in ast.walk(gate) if isinstance(c, ast.Call)}
    assert "_log_heat_block" in called
```

- [ ] **Step 2: Write the failing API tests**

Create `tests/admin/test_risk_of_loss_api.py`:

```python
"""v189 B4 on the wire: the Dashboard's risk-of-loss figure beside enforced
heat, the Risk page's per-row risk-of-loss column, and the golden trade's
realized parts on the Dashboard.

The book: the golden PARTIAL runner (stop at its floor, risk of loss $0,
enforced 100 x 5 = $500 = 5%), an ACTIVE long (100 sh, entry 50, stop 48:
$200 both ways = 2%) and a PENDING plan's placeholder (100 sh, entry 20,
stop 19: enforced 1%, no risk of loss -- nothing is held). Balance 10,000.
"""
import pytest

from swingbot.core.edge import heat
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.analytics.test_golden_partial_trade_metrics import (closed_case,
                                                               golden_closed_trade,
                                                               golden_open_trade,
                                                               load_golden, open_case)
from tests.store_seed import seed_store

G = load_golden()["trade"]
GOLDEN_PID = "11111111-1111-4111-8111-111111111111"
ACTIVE_PID = "22222222-2222-4222-8222-222222222222"
PENDING_PID = "33333333-3333-4333-8333-333333333333"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch",
                        lambda *a, **k: {}, raising=False)


@pytest.fixture(autouse=True)
def fresh_risk_cache():
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1 import risk
    risk._invalidate_cache()
    yield
    risk._invalidate_cache()


@pytest.fixture
def logged_in(client):
    from swingbot.admin import app as admin_app

    response = client.post("/api/v1/session", json={
        "username": admin_app.ADMIN_USERNAME, "password": admin_app.ADMIN_PASSWORD})
    assert response.status_code == 200
    return client


def _pair(pid, tid, ticker, status, *, entry, stop, working_stop=None, legs=()):
    plan = _plan(pid, ticker=ticker, status=status)
    plan.update({"entry_price": entry, "trigger_price": entry, "stop_loss": stop,
                 "tp1": entry * 1.1, "tp2": entry * 1.2, "working_stop": working_stop,
                 "legs_realized": [dict(leg) for leg in legs]})
    trade = _trade(tid, plan_id=pid, ticker=ticker, status="open")
    trade.update({"entry": entry, "stop_loss": stop, "take_profit": entry * 1.1, "shares": 100})
    return plan, trade


@pytest.fixture
def book(admin_app):
    golden = _pair(GOLDEN_PID, "a" * 16, G["ticker"], "PARTIAL", entry=G["entry"],
                   stop=G["stop_loss"], working_stop=open_case("quote_113")["working_stop"],
                   legs=[G["tp1_leg"]])
    active = _pair(ACTIVE_PID, "b" * 16, "MSFT", "ACTIVE", entry=50.0, stop=48.0)
    pending = _pair(PENDING_PID, "c" * 16, "NVDA", "PENDING", entry=20.0, stop=19.0)
    seed_store("account", {"base_balance": 10000.0, "balance": 10000.0, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})
    seed_store("plans", [golden[0], active[0], pending[0]])
    seed_store("trades", [golden[1], active[1], pending[1]])
    return {"golden": golden, "active": active, "pending": pending}


def test_dashboard_shows_risk_of_loss_beside_enforced_heat(book, logged_in):
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert "risk_used_pct" not in body
    # Enforced heat is unchanged: every open trade, placeholder and original size included.
    expected_heat = heat.open_heat([t for _, t in book.values()], 10000.0)
    assert body["heat_enforced_pct"] == pytest.approx(expected_heat)
    assert body["heat_enforced_pct"] == pytest.approx(8.0)            # 5 + 2 + 1
    # Risk of loss: the golden runner at its floor $0, the ACTIVE long $200, the placeholder none.
    assert body["risk_of_loss_amount"] == pytest.approx(200.0)
    assert body["risk_of_loss_pct"] == pytest.approx(2.0)
    assert body["risk_cap_pct"] is not None


def test_the_golden_runner_alone_has_no_risk_of_loss(admin_app, logged_in):
    plan, trade = _pair(GOLDEN_PID, "a" * 16, G["ticker"], "PARTIAL", entry=G["entry"],
                        stop=G["stop_loss"],
                        working_stop=open_case("quote_113")["working_stop"],
                        legs=[G["tp1_leg"]])
    seed_store("plans", [plan])
    seed_store("trades", [trade])
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert body["risk_of_loss_amount"] == open_case("quote_113")["risk_of_loss_amount"]
    assert body["heat_enforced_pct"] > 0                       # enforced heat still counts it


def test_risk_page_rows_carry_risk_of_loss_and_still_sum_to_open_heat(book, logged_in):
    body = logged_in.get("/api/v1/risk").get_json()
    rows = {r["ticker"]: r for r in body["positions"]}
    assert (rows[G["ticker"]]["risk_of_loss_amount"], rows[G["ticker"]]["risk_of_loss_pct"]) == (0.0, 0.0)
    assert rows["MSFT"]["risk_of_loss_amount"] == pytest.approx(200.0)
    assert rows["MSFT"]["risk_of_loss_pct"] == pytest.approx(2.0)
    assert (rows["NVDA"]["risk_of_loss_amount"], rows["NVDA"]["risk_of_loss_pct"]) == (None, None)
    # The enforced rows keep their invariant and the gauge stays on enforced heat.
    assert sum(r["risk_pct"] for r in body["positions"]) == pytest.approx(
        body["heat"]["open_pct"], abs=0.01)


def test_golden_manual_close_is_two_realized_parts_on_the_dashboard():
    """Spec § Testing: the Dashboard's realized parts for the golden trade
    closed by hand at 115 -- the TP1 leg ($500) and the runner ($750)."""
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1.dashboard import _realized, _realized_parts

    case = closed_case("manual")
    parts = _realized_parts([golden_closed_trade(case, closed_at="2026-08-05T15:00:00+00:00")], "all")
    assert len(parts) == 2
    realized = _realized(parts)
    assert realized["amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    assert (realized["wins"], realized["losses"]) == (2, 0)


def test_golden_open_runner_has_its_banked_leg_as_one_realized_part():
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1.dashboard import _realized, _realized_parts

    parts = _realized_parts([golden_open_trade()], "all")
    assert len(parts) == 1
    assert _realized(parts)["amount"] == pytest.approx(open_case("quote_113")["banked_amount"])
```

- [ ] **Step 3: Update the existing dashboard and risk contract tests**

In `tests/admin/test_api_v1_dashboard.py`:

- In `DASHBOARD`, replace `"risk_used_pct": NULLABLE_NUMBER,` with:

```python
    # v189 B4 -- enforced heat (what the scanner gates on) and, beside it,
    # risk of loss to the working stop. `risk_used_pct` was the first one.
    "heat_enforced_pct": NULLABLE_NUMBER,
    "risk_of_loss_pct": NULLABLE_NUMBER,
    "risk_of_loss_amount": NULLABLE_NUMBER,
```

- In `test_risk_used_skips_the_full_portfolio_collector`, change `assert body["risk_used_pct"] == expected` to `assert body["heat_enforced_pct"] == expected` (the rest stands: the dashboard must still never call `collect_portfolio_state`).
- In `_PARITY_KEYS`, replace `"risk_used_pct"` with `"heat_enforced_pct", "risk_of_loss_pct", "risk_of_loss_amount"`.
- In the module docstring, replace `risk_used_pct` with `heat_enforced_pct · risk_of_loss_pct`.

In `tests/admin/test_api_v1_risk.py`, in `test_position_rows_sum_to_open_heat`'s `assert_shape(body["positions"][0], {...})`, after `"risk_pct": NULLABLE_NUMBER,` add:

```python
        # v189 B4 -- beside the enforced figure, never summed into it.
        "risk_of_loss_amount": NULLABLE_NUMBER, "risk_of_loss_pct": NULLABLE_NUMBER,
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/edge/test_risk_of_loss.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_risk_of_loss_api.py
```

Expected: FAIL — `ImportError: cannot import name 'risk_of_loss_amount'` (and `position_risk_of_loss`); the API file fails on `'risk_used_pct' not in body` and the missing keys. The two realized-parts tests may already pass: they pin existing behaviour on the golden trade (spec § Testing) and must stay green.

- [ ] **Step 5: Implement the two core functions**

In `swingbot/core/edge/heat.py`, add `import math` beside the other imports and, after `open_heat`:

```python
def risk_of_loss_amount(entry, working_stop, direction: str, open_shares) -> float:
    """v189 B4: what a fill at the current working stop would still lose
    below entry -- ``open_shares x (entry - stop)`` long, ``(stop - entry)``
    short, floored at 0 (a stop at or past entry risks nothing; a gap
    through it can lose more, which the screens say in their hint).

    Display only: `open_heat` (original risk, every open trade) stays what
    the scanner enforces. 0.0 on a missing or non-finite input or a
    direction that is neither ``bullish`` nor ``bearish``.
    """
    values = (entry, working_stop, open_shares)
    if any(v is None for v in values) or direction not in ("bullish", "bearish"):
        return 0.0
    entry, stop, shares = (float(v) for v in values)
    if not all(math.isfinite(v) for v in (entry, stop, shares)):
        return 0.0
    distance = entry - stop if direction == "bullish" else stop - entry
    return round(max(0.0, distance) * max(0.0, shares), 2)
```

In `swingbot/core/tracking/equity.py`, after `held_now`:

```python
def position_risk_of_loss(trade: dict, plan: dict | None) -> float | None:
    """v189 B4: one open trade's risk of loss to its current working stop.

    `plan` is the stored plan record (`load_plans_by_id()[trade["plan_id"]]`)
    or None for a trade with no plan, which is priced on its own stop and
    size. A plan that is not ACTIVE/PARTIAL is not held (a PENDING
    placeholder, or a terminal plan): None, never 0.0, so a caller can tell
    "nothing at risk" from "nothing held". A held plan uses its working stop,
    else its risk stop, and the shares still open after any banked leg.
    """
    from swingbot.core.edge.heat import risk_of_loss_amount

    if plan is None:
        return risk_of_loss_amount(trade.get("entry"), trade.get("stop_loss"),
                                   trade.get("direction"), trade.get("shares"))
    if plan.get("status") not in _LIVE_PLAN_STATUSES:
        return None
    stop = plan.get("working_stop") or plan.get("stop_loss")
    held = open_shares(trade.get("shares"), plan.get("legs_realized") or [])
    return risk_of_loss_amount(trade.get("entry"), stop, trade.get("direction"), held)
```

(A PARTIAL plan written before v39 may lack `working_stop`; this falls back to the risk stop, which overstates its risk of loss -- the conservative side for a display figure. No plan written by today's code lacks it.)

- [ ] **Step 6: Implement the heat-blocked line in `swingbot/core/scanning/scan_run.py`**

Add, as a module-level function near the other small helpers above `_sync_run_scan`:

```python
def _log_heat_block(ticker: str, enforced_pct: float, add_pct: float, cap_pct: float) -> None:
    """v189 B4: name the ENFORCED heat whenever the portfolio cap flags an
    alert, so the log never reads as headroom the dashboard's risk-of-loss
    figure might suggest."""
    log.info("heat blocked (enforced %.2f%% + %.2f%% > cap %.2f%%) %s",
             enforced_pct, add_pct, cap_pct, ticker)
```

In `_sync_run_scan`, inside the existing branch (no new branch; complexity unchanged):

```python
        if not heat_chk["allowed"]:
            item.heat_blocked = heat_chk
            _log_heat_block(result.ticker, heat_chk["open_heat"],
                            account_cfg.get("risk_pct", 1.0), heat_chk["cap"])
```

- [ ] **Step 7: Implement the dashboard figures in `swingbot/admin/api_v1/dashboard.py`**

Replace `_risk_used` with:

```python
def _risk_figures(all_trades: list[dict]) -> dict:
    """Enforced heat, risk of loss beside it, and the cap (v189 B4).

    `heat_enforced_pct` is `heat.open_heat` over every open trade, both
    ledgers, at original size, placeholders included: exactly what the
    scanner gates on, so the admin view never shows headroom the scanner
    does not grant. `risk_of_loss_*` is the money below entry a fill at each
    held position's working stop would still lose (`position_risk_of_loss`),
    unheld placeholders excluded; it is never shown as a gauge against the
    cap. Not `collect_portfolio_state` (its per-ticker fetches cost ~3.7s).

    Degrades to None for everything but the cap: every other collector on
    the Risk page treats heat as best-effort, and this is the landing page.
    """
    cap = float(getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0))
    out = {"heat_enforced_pct": None, "risk_of_loss_pct": None,
           "risk_of_loss_amount": None, "risk_cap_pct": cap}
    try:
        from swingbot.core.edge import heat
        from swingbot.core.planning import account as account_module
        from swingbot.core.tracking.equity import load_plans_by_id, position_risk_of_loss
        cfg = account_module.load_account_config()
        balance = cfg.get("balance", cfg.get("base_balance", 0.0))
        open_trades = [t for t in all_trades if t.get("status") == "open"]
        plans = load_plans_by_id()
        amounts = [position_risk_of_loss(t, plans.get(t.get("plan_id"))) for t in open_trades]
        amount = round(sum(a for a in amounts if a is not None), 2)
        out.update({
            "heat_enforced_pct": heat.open_heat(open_trades, balance),
            "risk_of_loss_amount": amount,
            "risk_of_loss_pct": round(amount / balance * 100.0, 3) if balance and balance > 0 else None,
        })
    except Exception:
        pass
    return out
```

In `dashboard()`, delete `heat, cap = _risk_used(all_raw)` and replace the two payload lines `"risk_used_pct": heat,` / `"risk_cap_pct": cap,` with `**_risk_figures(all_raw),`. In the module docstring's `primary` line, replace `risk_used_pct` with `heat_enforced_pct · risk_of_loss_pct`.

The frontend still reads `risk_used_pct` until V189-23 (part 7) renames it; nothing deploys between the two (index Global Constraints), and backend and frontend commit separately.

- [ ] **Step 8: Implement the Risk page column in `swingbot/admin/api_v1/risk.py`**

Add above `_positions`:

```python
def _risk_of_loss_fields(trade: dict, plan: dict | None, balance: float) -> dict:
    """v189 B4: the row's risk of loss beside its enforced `risk_pct`. Never
    summed into `risk_pct`: those rows still add up to `heat.open_pct`, and
    the utilisation gauge stays on enforced heat."""
    from swingbot.core.tracking.equity import position_risk_of_loss

    amount = position_risk_of_loss(trade, plan)
    pct = round(amount / balance * 100.0, 3) if amount is not None and balance > 0 else None
    return {"risk_of_loss_amount": amount, "risk_of_loss_pct": pct}
```

In `_positions`, add `from swingbot.core.tracking.equity import load_plans_by_id` to its imports, read `plans = load_plans_by_id()` inside the existing `try` (after `open_trades = ...`), and add `**_risk_of_loss_fields(t, plans.get(t.get("plan_id")), balance),` as the last entry of each row dict. Append to its docstring: `Each row also carries its risk of loss to the working stop (v189 B4), shown beside risk_pct and never added to it.`

- [ ] **Step 9: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/edge/test_risk_of_loss.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_risk_of_loss_api.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py
cd "$WT" && python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_cap_invariants.py
cd "$WT" && python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
```

Expected: all PASS. The last two prove the scanner's heat inputs and the heat-blocked embed are unchanged.

- [ ] **Step 10: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `_sync_run_scan` is unchanged by this task (one call added inside an existing branch); `_risk_figures` is about 6, `risk_of_loss_amount` 7, `position_risk_of_loss` 4, `_risk_of_loss_fields` 3, `_positions` stays under 15.

- [ ] **Step 11: Commit**

```bash
cd "$WT" && git add swingbot/core/edge/heat.py swingbot/core/tracking/equity.py swingbot/admin/api_v1/dashboard.py swingbot/admin/api_v1/risk.py swingbot/core/scanning/scan_run.py tests/edge/test_risk_of_loss.py tests/admin/test_risk_of_loss_api.py tests/admin/test_api_v1_dashboard.py tests/admin/test_api_v1_risk.py && git commit -m "feat(risk): risk of loss to the stop beside enforced heat; heat-blocked log line (v189 B4)"
```

### Task V189-20: Analytics carries the label basis and scratch/unscored counts

**Model:** sonnet — one counting helper and three keys on an existing payload, fully pinned by hand-computed tests; the only judgement is reading the scoped `closed` list, which the tests fix.

**Spec:** D6 (the label change is visible, not a silent step: `metrics.LABEL_BASIS_SINCE` records the deploy date; the Analytics win-rate tile shows the `scratch` and `unscored` counts beside the rate; the hint text is the frontend's, V189-24); D2 (the `closed`/`scratch` and `closed`/`unscored` labels these counts read); `## Corrections from the code brief` 2 (the D6 tile is Analytics Overview only — the Dashboard counts legs and is not touched); this part's decision 5.

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (new function directly after `win_rate`, found with `git grep -n "^def win_rate" swingbot/core/analytics/metrics.py`)
- Modify: `swingbot/admin/api_v1/analytics.py` (`analytics_performance` `:142-278`: docstring, one assignment, three keys after `"win_rate_n"` `:208`)
- Modify: `tests/admin/test_api_v1_analytics.py` (`test_performance_top_level_shape` `:75-96`) — outside the ledger row, see the part header
- Modify: `tests/admin/test_api_analytics.py` (`test_distributions_and_series_are_present_and_scoped` `:180-200`; the `api_v1_contract` import `:18`) — outside the ledger row, see the part header
- Create: `tests/admin/test_analytics_label_basis.py`

**Interfaces:**
- Consumes: `metrics.LABEL_BASIS_SINCE: str | None` and `metrics.net_outcome(trade) -> tuple[str, str | None]` (V189-2); the golden helper `golden_closed_trade(case, *, closed_at=None, trade_id="golden-1", runner_reason="manual")` (V189-2); `tests.admin.test_api_v1_trades._trade` (exists); `tests.store_seed.seed_store`, `tests.admin.api_v1_contract.NULLABLE_STR`, `assert_shape` (exist); `scope.closed_only` with `CLOSED_STATUSES = ("win", "loss", "closed")` (exists).
- Produces (read by V189-24 in part 7):
  - `metrics.label_counts(closed: list[dict]) -> dict[str, int]` — `{"scratch": n, "unscored": n}`: rows with `status == "closed"` and `close_reason` exactly `"scratch"` / `"unscored"`. Both keys always present; `0` on an empty list. A `win`/`loss`/`open` row never counts, whatever its `close_reason`.
  - `/api/v1/analytics/performance` top level gains `scratch_n: int`, `unscored_n: int` (over the same scoped `closed` list as `win_rate`), and `label_basis_since: str | None` (= `metrics.LABEL_BASIS_SINCE`, read at request time so V189-26's date reaches it without a code change here). Nothing else in the payload moves; `win_rate` and `win_rate_n` keep excluding `closed` rows.

`win_rate`, `expectancy_r`, `TradeLog.get_stats`, the Dashboard and the Calendar are not edited: D6 is display only and ExpR is label-free (spec D6, last line).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_analytics_label_basis.py`:

```python
"""v189 D6: the win-rate label basis is visible. Scaled-out closes are
labelled by net R from LABEL_BASIS_SINCE (D2, not backfilled), so the
Analytics performance payload carries the date and the scratch/unscored
counts the win rate leaves out -- the step at deploy reads as a change of
basis, not an improvement. Every expected value is hand-computed."""
import pytest

from swingbot.core.analytics import metrics
from tests.admin.api_v1_contract import NULLABLE_STR, assert_shape
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_golden_partial_trade_metrics import golden_closed_trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


def _row(trade_id: str, status: str, close_reason=None, **over) -> dict:
    t = _trade(trade_id, plan_id=None, status=status)
    t["close_reason"] = close_reason
    t["horizon_key"] = "4w"
    t.update(over)
    return t


# -- metrics.label_counts ----------------------------------------------------

def test_an_empty_book_counts_zero_of_each():
    assert metrics.label_counts([]) == {"scratch": 0, "unscored": 0}


def test_counts_closed_rows_by_exact_close_reason():
    closed = [
        {"status": "closed", "close_reason": "scratch"},
        {"status": "closed", "close_reason": "scratch"},
        {"status": "closed", "close_reason": "unscored"},
        {"status": "closed", "close_reason": "manual"},
        {"status": "closed", "close_reason": None},
        {"status": "closed"},
    ]
    assert metrics.label_counts(closed) == {"scratch": 2, "unscored": 1}


def test_a_win_loss_or_open_row_never_counts_whatever_its_close_reason():
    closed = [{"status": "win", "close_reason": "scratch"},
              {"status": "loss", "close_reason": "unscored"},
              {"status": "open", "close_reason": "scratch"}]
    assert metrics.label_counts(closed) == {"scratch": 0, "unscored": 0}


def test_near_misses_of_the_vocabulary_do_not_count():
    closed = [{"status": "closed", "close_reason": "Scratch"},
              {"status": "closed", "close_reason": "scratch "},
              {"status": "closed", "close_reason": "timeout"}]
    assert metrics.label_counts(closed) == {"scratch": 0, "unscored": 0}


def test_the_golden_trade_closed_at_net_zero_is_one_scratch():
    """Runner out at 90: 0.5 x +2R + 0.5 x -2R = 0.00R, inside the band.
    The label `net_outcome` gives it is the one `label_counts` counts."""
    trade = golden_closed_trade({"runner_exit": 90.0, "status": "closed",
                                 "close_reason": "scratch"})
    assert metrics.net_outcome(trade) == ("closed", "scratch")
    assert metrics.label_counts([trade]) == {"scratch": 1, "unscored": 0}


# -- /api/v1/analytics/performance -------------------------------------------

@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _perf(client, query=""):
    return client.get("/api/v1/analytics/performance" + query).get_json()


def test_the_payload_declares_the_label_basis_keys(seed, logged_in):
    seed()
    body = _perf(logged_in)
    assert_shape({k: body[k] for k in ("scratch_n", "unscored_n", "label_basis_since")},
                 {"scratch_n": int, "unscored_n": int, "label_basis_since": NULLABLE_STR},
                 where="performance")
    assert body["scratch_n"] == 0 and body["unscored_n"] == 0


def test_counts_sit_beside_a_win_rate_that_leaves_them_out(seed, logged_in):
    """2 wins, 1 loss, 2 scratches, 1 unscored, 1 manual close: the rate is
    2 / 3 over win_rate_n 3; the four `closed` rows are reported, not rated."""
    seed(trades=[
        _row("a" * 16, "win"), _row("b" * 16, "win"), _row("c" * 16, "loss"),
        _row("d" * 16, "closed", "scratch"), _row("e" * 16, "closed", "scratch"),
        _row("f" * 16, "closed", "unscored"), _row("g" * 16, "closed", "manual"),
    ])
    body = _perf(logged_in)
    assert body["win_rate_n"] == 3
    assert body["win_rate"] == pytest.approx(200 / 3)
    assert body["scratch_n"] == 2 and body["unscored_n"] == 1


def test_counts_follow_the_scope(seed, logged_in):
    """`_trade` closes on 2026-08-04; `?from=2026-08-01&horizon=4w` keeps
    only the first row (the second is 2w, the third closed in July)."""
    seed(trades=[
        _row("a" * 16, "closed", "scratch"),
        _row("b" * 16, "closed", "scratch", horizon_key="2w"),
        _row("c" * 16, "closed", "unscored", closed_at="2026-07-10T15:00:00+00:00"),
    ])
    unscoped = _perf(logged_in)
    assert unscoped["scratch_n"] == 2 and unscoped["unscored_n"] == 1
    scoped = _perf(logged_in, "?from=2026-08-01&horizon=4w")
    assert scoped["scratch_n"] == 1 and scoped["unscored_n"] == 0


def test_open_trades_are_not_counted(seed, logged_in):
    seed(trades=[_row("a" * 16, "open", "scratch")])
    body = _perf(logged_in)
    assert body["scratch_n"] == 0 and body["unscored_n"] == 0


def test_label_basis_since_is_the_metrics_constant(seed, logged_in):
    """None before the release task, the merge date after it -- either way
    the payload carries the constant itself, never a copy."""
    seed()
    assert _perf(logged_in)["label_basis_since"] == metrics.LABEL_BASIS_SINCE


def test_label_basis_since_echoes_the_constant_at_request_time(seed, logged_in, monkeypatch):
    seed()
    monkeypatch.setattr(metrics, "LABEL_BASIS_SINCE", "2026-10-24")
    assert _perf(logged_in)["label_basis_since"] == "2026-10-24"
```

No test here pins the constant's value: V189-26 sets it, and only metrics.py is in its row.

- [ ] **Step 2: Declare the keys in the two exact-shape contract tests**

`assert_shape` fails on an undeclared key, so both top-level performance shapes gain the three keys in this task.

In `tests/admin/test_api_v1_analytics.py`, `test_performance_top_level_shape`, add after the `"streaks": dict,` entry (`NULLABLE_STR` is already imported there):

```python
        # v189 D6 -- the label basis beside the win rate.
        "scratch_n": int, "unscored_n": int, "label_basis_since": NULLABLE_STR,
```

In `tests/admin/test_api_analytics.py`, change the import line `:18` to

```python
from tests.admin.api_v1_contract import NULLABLE_NUMBER, NULLABLE_STR, assert_error, assert_shape
```

and add the same three-key entry after `"streaks": dict,` in `test_distributions_and_series_are_present_and_scoped`.

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_analytics_label_basis.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py
```

Expected: FAIL — `AttributeError: module 'swingbot.core.analytics.metrics' has no attribute 'label_counts'` on the metrics tests, `KeyError: 'scratch_n'` on the payload tests, and `test_performance_top_level_shape` failing on the missing keys. `test_label_basis_since_is_the_metrics_constant` fails with `KeyError` too.

- [ ] **Step 4: Implement `metrics.label_counts(closed: list[dict]) -> dict[str, int]`**

In `swingbot/core/analytics/metrics.py`, directly after `win_rate`. Start from `{"scratch": 0, "unscored": 0}` and increment the key equal to `t.get("close_reason")` for each `t` with `t.get("status") == "closed"` whose reason is one of the two keys. Docstring:

```
v189 D6: how many closes the win rate leaves out because D2 labelled them
by net R -- `closed`/`scratch` (net R within ±SCRATCH_EPS_R) and
`closed`/`unscored` (net R not computable). Exact `close_reason` match on
`status == "closed"` rows only; both keys always present, 0 when none.
Shown beside `win_rate` so the step at LABEL_BASIS_SINCE reads as a change
of label basis, not an improvement.
```

- [ ] **Step 5: Put the three keys on the performance payload**

In `swingbot/admin/api_v1/analytics.py`, `analytics_performance`: add `labels = m.label_counts(closed)` after the `stats.update(...)` line, and directly after the `"win_rate_n": ...` entry:

```python
        # v189 D6 -- the closes the rate leaves out, and the date their basis
        # changed. Read through `m.` at request time: V189-26 sets the date.
        "scratch_n": labels["scratch"],
        "unscored_n": labels["unscored"],
        "label_basis_since": m.LABEL_BASIS_SINCE,
```

Append to the docstring, after the paragraph ending "…not projections of `closed`.":

```
    `scratch_n`/`unscored_n` count the scoped `closed` rows that D2 (v189)
    labelled `closed`/`scratch` or `closed`/`unscored` -- excluded from
    `win_rate` and `win_rate_n` -- and `label_basis_since` is the date from
    which scaled-out closes are labelled by net R (None until deployed).
```

No `from ...metrics import LABEL_BASIS_SINCE`: a by-name import would freeze the value the release task changes and break the monkeypatch test.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_analytics_label_basis.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_analytics.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_analytics.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_golden_partial_trade_metrics.py
```

Expected: all PASS. The last proves V189-2's fixture and `net_outcome` are untouched.

- [ ] **Step 7: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `label_counts` is about 4; `analytics_performance` gains no branch (one assignment, three dict entries).

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add swingbot/core/analytics/metrics.py swingbot/admin/api_v1/analytics.py tests/admin/test_analytics_label_basis.py tests/admin/test_api_v1_analytics.py tests/admin/test_api_analytics.py && git commit -m "feat(analytics): label basis date and scratch/unscored counts beside the win rate (v189 D6)"
```
