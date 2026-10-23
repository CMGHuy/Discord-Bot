# v189 — Book integrity and partial-trade truth: one R, honest labels, every screen agrees on a scaled-out trade: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V189-8:" -A 320 docs/superpowers/plans/2026-10-23-v189-book-integrity-partial-truth_3-plan-manager-transactions.md`.

**Bump:** bot patch, ui patch
**Edge:** none (integrity) — it corrects the measured book (win rate, R, balance history) and the partial-trade figures on screen; what is traded and how it is sized do not change. The one change with edge in it (heat enforcement on current risk) is a separate spec.
**Screen:** exempt (integrity)
**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — its `## Corrections from the code brief` section wins over earlier sections.
**Brief:** `.superpowers/briefs/2026-10-23-v189-book-integrity-partial-truth.md`
**Depends on:** v187 (`docs/superpowers/plans/2026-10-23-v187-safety-hardening_0-index.md`) merged to `main`. V189-1 checks this first and stops if `PENDING_CANCEL_EVENTS` is not on `main`.
**Worktree:** implement every task in `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` (branch of the same name, created in V189-1's first step; `docs/claude/document-lifecycle.md`). V189-26 runs the full suite in the worktree and merges to `main`; then `/panel staff-engineer,quant-engineer,risk-manager` (the spec's `Panel:` line) and `/close-out` run on `main`.

## Goal

A scaled-out trade (TP1 banked, runner still open or closed later) is
recorded and shown four different ways today. The Trades row shows the banked
TP1 dollars at half their value, because the API swaps `shares` for the
remaining count and the screen multiplies by the fraction again. The Calendar
adds leg Rs at full size, so a +2R TP1 on half the position plus a +3R runner
reads +5R instead of +2.5R. A manual close of a PARTIAL writes the runner leg
to the trade but not to the plan. Any runner close after TP1 is labelled `win`
whatever it netted, and a time-exit runner close is labelled `closed`, so ten
real winners are missing from the win rate. Underneath that, the TP1 leg and
the fill are written outside the plan's transaction, the bot and admin
processes overwrite each other's whole plan documents, a reversal can book P&L
on an order that never filled, deletes leave plans stepping with no trade, and
clearing history keeps the old drawdown peak. The audit counted 23 production
records already affected; the partner chose to fix forward only.

Once this ships there is one trade-level R (`metrics.r_multiple`) and one
leg contribution (`fraction × r`) that every sum uses. A close with two or
more realized legs is labelled by the sign of its unrounded net R (`win`,
`loss`, or `closed`/`scratch` inside ±0.01R; `closed`/`unscored` when the net
cannot be computed). Every plan write takes the plan row lock, refuses to
overwrite a terminal plan with a stale copy, and never loosens a stop. A TP1
leg, a fill, a terminal close and its balance point commit together or not at
all; a failed exit is retried once and then reported in the ops channel.
Reversals cancel unfilled plans instead of booking them, deletes end their
linked plans, and clearing history becomes an archived full reset that
restarts the drawdown peak at the base balance (refused while the kill switch
is tripped, unless forced). On screen, the Trades row, Trade detail, Calendar
and Dashboard all agree on one golden scaled-out trade: banked $500 and +1.00R
contribution (TP1 +2.00R on 50%), 2.30R blended at a 113 quote, and "Risk of
loss (to stop)" shown beside the enforced heat rather than as headroom.

It works by moving the guards to the narrowest shared points. The row lock,
terminal refusal and tighter-stop merge live inside `PlanStore.update`, so all
28 write sites in the plan manager are covered without editing each. The
transaction gains a per-path `lock_timeout` (1s for the bot, which skips that
plan for one poll; 5s for the admin). `TradeLog` and the account module gain
`conn=` parameters that default to today's behaviour, and the journal and
snapshot hooks move after commit. One golden fixture JSON is read by pytest and
Vitest, so backend and frontend cannot drift.

It leaves alone: the backtest and its labels (`exit_sim.py`, `exit_sim_v2.py`
are never edited; a test pins that the gap case stays `win` there), heat
enforcement (`open_heat` and the scanner gate are unchanged), the Dashboard
win-rate chip (it counts legs), the 23 historical records (no backfill; the
metric-definitions spec owns that), the ~70 inline R formulas outside the code
this spec edits, and `check_bar` (still unwired; it only inherits the shared
helpers). There is no schema change and no Alembic revision.

Success is measured by the tests: every golden case matches its hand-computed
row, calendar, dashboard and frontend figures; the label table holds on all
three close paths; the two-connection races end with the admin's close intact
and the tighter stop kept; a failed leg or balance write leaves no trace; the
reset archive round-trips through the restore script; and the plan's single
full-suite run, complexity gate included, is green.

## Architecture

```
D1/D2  core/analytics/metrics.py
         leg_contribution_r(leg) ; _blended_r_raw(trade) ; r_multiple = round(raw,2) for legs
         banked_contribution_r(legs) ; open_trade_r(trade, quote)
         SCRATCH_EPS_R = 0.01 ; net_outcome(trade) -> (status, close_reason|None) ; LABEL_BASIS_SINCE
         label_counts(closed) -> {"scratch": n, "unscored": n}
       tracking/performance.closed_r_multiple -> metrics ; retrospective._r_multiple deleted
       tracking/performance.expand_trade_legs parts gain fraction + leg_r -> pnl_calendar sums contributions

D3     db/engine.transaction(conn=None, *, lock_timeout_ms=None) ; LockTimeout ; BOT_/ADMIN_LOCK_TIMEOUT_MS
       db/repositories/base.Repository.get_for_update(key, *, conn)
       planning/plan_store.PlanStore.update(plan, *, conn=None) -> bool
           [tx] SELECT ... FOR UPDATE -> refuse stale write over terminal -> tighter stops -> upsert
       planning/account + tracking/performance: conn= on every balance/leg/fill/close write; hooks after commit
       planning/plan_manager:
           _save(plan, conn=None) raises PlanWriteAborted ; _persist_fill / _persist_partial / _persist_terminal (one tx each)
           exit retry once -> PlanPersistFailed + take_exit_failures() -> loops posts to the ops channel
           _step_safely(plan, price, now) ; stop-bearing plans first ; finite-quote guards
           _close_runner / time exit -> net_outcome

D4     tracking/plan_links.py (new): end_linked_plan, cancel_if_unfilled, DeleteResult, EndedPlan, describe_ended
       performance.close_trade_manual / close_trade_reversed / clear_open / delete_trade -> one tx with the plan
       admin/api_v1/trade_commands._close_plan: network first, then one tx (plan lock, trade close, A2 runner leg)
       scanning/scan_run._settle_reversal (extracted from _sync_run_scan): placeholder -> cancel, never P&L
       tracking/account_reset.py (new): archive -> reset + reseed (one tx) -> snapshot ; restore_archive
       scripts/ops/restore_account_reset.py ; vocabulary: cancelled_trade_deleted

D5/D6  admin/api_v1/trades.py rows: entry_shares, banked_contribution_r, open-partial r_multiple
       edge/heat.risk_of_loss_amount ; tracking/equity.position_risk_of_loss
       admin/api_v1/dashboard.py: heat_enforced_pct, risk_of_loss_pct, risk_of_loss_amount ; risk.py rows + column
       admin/api_v1/analytics.py: scratch_n, unscored_n, label_basis_since
       frontend: models, plan-cell, trades, dashboard, trade-detail store/tiles/card, risk page, analytics overview
       golden fixture tests/analytics/golden_partial_trade.json (pytest + Vitest)
```

## Global Constraints

- Implementation starts only after v187 is merged on `main`; build on its `PENDING_CANCEL_EVENTS`, `NOTICE_EVENTS`, `_fill_pending`, `_step_limit` and admin decorators exactly as merged (re-read them with `git grep -n` before editing; never re-create them).
- **D2 is live-only.** Never edit `swingbot/core/planning/exit_sim.py`, `exit_sim_v2.py` or `lifecycle.py` (closed acceptance gates; `tests/analytics/test_override_verdict.py` hashes them). The parity pin is a test.
- `SCRATCH_EPS_R = 0.01`, band edges exclusive; `net_outcome` compares the **unrounded** blend and only labels closes with **two or more** realized legs. Single-leg closes keep today's labels exactly.
- Not computable or not finite → `("closed", "unscored")` plus a warning naming the trade id. Never fall back to the `tp1_*` → `win` rule.
- Every new `conn=` / `after_commit=` parameter defaults to `None` = today's behaviour, so existing monkeypatched doubles (`_all`, `_db_upsert(trade, conn=None)`, `_settle_account_balance(self, trade)`) keep working unless a task updates them.
- Lock order everywhere: plan row (`FOR UPDATE`) → trade row → account rows. No `threading.Lock` (`plan_store._LOCK`, `performance._LOCK`) is held while waiting on a row lock. Multi-plan locks take rows `ORDER BY plan_id`. Network calls happen before any lock.
- Lock timeouts: `BOT_LOCK_TIMEOUT_MS = 1000` for the plan manager and scanner paths, `ADMIN_LOCK_TIMEOUT_MS = 5000` for admin and Discord-command paths.
- The balance write (`apply_realized_pnl`) stays inside the close transaction; only `_after_close` (journal) and `_refresh_snapshot_safely` run after commit.
- `banked_r` keeps its meaning (the TP1 leg's own R). The trade-level banked figure is the new `banked_contribution_r`.
- Heat enforcement (`heat.open_heat`, `scan_run` heat gate, `analyze.py:252`) is unchanged; B4 is display only. Risk-page rows still sum to `open_heat`.
- `entry_shares` and `banked_contribution_r` are **optional** in `models.ts` (nine spec files build full `TradeRow` literals).
- Complexity < 15 for every function written or changed; baselined functions may only shrink (`_on_event` 15, `poll` 20, `_step_active` 21, `_row_from_plan` 15, `list_trades` 34, `_sync_run_scan` 96). Check with `python scripts/dev/complexity_gate.py` in every task that touches one of them.
- No schema change, no Alembic revision, no backfill of historical records.
- Run `/replicate-prod-db` once in V189-1, before the first test run (every pytest test uses the autouse Postgres fixture). Per-task runs are `python scripts/dev/testrun.py file <test>`; frontend runs are `cd frontend && npx ng test --watch=false` plus `npm run lint`. The full suite runs once, in V189-26.
- New tests go in existing directories (`tests/analytics/`, `tests/db/`, `tests/planning/`, `tests/tracking/`, `tests/admin/`, `tests/scanning/`, `tests/edge/`, `tests/presentation/`, `tests/commands/`, `tests/scripts/`); no `tests/suites.toml` edit.
- Do not touch `CLAUDE.md` or `.claude/`. `docs/claude/known-traps.md` is edited only in V189-25, which also checks the `AGENTS.md` mirror (`tests/hooks/test_codex_mirror.py`).
- Work in the worktree; one scoped commit per task (backend and frontend never in one commit). Nothing is deployed by this plan.

## Spec clarifications (plan-writer decisions, 2026-10-23)

1. **Missing risk basis.** Spec § Testing's line "a missing risk basis falls back to today's rule with a warning" predates the panel; D2's body (and the panel's applied advisory) wins: `closed`/`unscored` plus a warning.
2. **A7 notice delivery.** `_queue_notify`'s `plan_transition` records reach `notify_closed_trades`, which posts only `win`/`loss`/`closed` trade statuses and drops plan records (`lifecycle_embeds.py:241`). The real follow-channel path is the plan's durable `pending_notice` slot, re-emitted by `PlanManager.resend_notices` and routed through `NOTICE_EVENTS`. `end_linked_plan(..., notice=True)` therefore writes `pending_notice` in the delete transaction: `cancelled_trade_deleted` for a PENDING plan, `closed` with `{"reason": "trade_deleted"}` for ACTIVE/PARTIAL. The test pins the slot for both cases and that `resend_notices` emits it.
3. **Same terminal write.** `PlanStore.update` refuses only when the stored status is terminal and the incoming status differs. Incoming == stored terminal is allowed, so the notice, ack and `first_seen_price` writers that touch a just-closed plan keep working.
4. **Tighter-stop merge** applies when both stored and incoming status are ACTIVE or PARTIAL (or stored ACTIVE → incoming PARTIAL). `None` on one side keeps the other. The merged values are written back onto the in-memory plan too.
5. **Exit failure notice.** There is no ops-notice API in core. `PlanManager` records failed exits; `take_exit_failures()` drains them and `commands/scanning/loops.py` posts each to `_ops_channel()` after the manager tick.
6. **A1 cancel.** A reversal against an unfilled placeholder cancels the plan with transition reason `reversed` and deletes the placeholder in the same locked transaction; no new event and no P&L.
7. **Dashboard JSON.** `risk_used_pct` (which was `open_heat`) is renamed `heat_enforced_pct`; `risk_of_loss_pct` and `risk_of_loss_amount` are added. The frontend follows in V189-23.
8. **`TradeLog.clear_history(*, force=False) -> int`** stays as a thin wrapper over `account_reset.reset_closed_history`; the admin endpoint and Discord handler call `reset_closed_history` directly for the full result.
9. **`LABEL_BASIS_SINCE`** is `None` until V189-26 sets it to the merge date (`date -u +%F`); deploy follows the merge. If the deploy slips past that date, the controller amends it in the deploy commit.
10. **`check_bar`** inherits `_save`, `_persist_partial` and `_persist_terminal` (so it is correct for free) but gets no dedicated tests; V189-25 fills the empty `known-traps.md` section.
11. **`_on_event`'s non-persisted `closed` mapping** is left as is: it is reached only when `trade_log` is None, where `_on_event` does nothing.

## Contracts

### Metrics (V189-1, V189-2, V189-20)

```python
# swingbot/core/analytics/metrics.py
SCRATCH_EPS_R: float = 0.01
LABEL_BASIS_SINCE: str | None = None          # ISO date, set in V189-26
def leg_contribution_r(leg: dict) -> float | None          # fraction * r; None if either missing
def _blended_r_raw(trade: dict) -> float | None            # r_multiple's body, unrounded (legs and single)
def r_multiple(trade: dict) -> float | None                # round(raw, 2) when legs, raw otherwise (unchanged results)
def banked_contribution_r(legs: list[dict] | None) -> float | None   # sum of contributions; None if no legs or any None
def open_trade_r(trade: dict, quote: float | None) -> float | None
    # banked_contribution_r(trade["legs"]) + (1 - sum fractions) * signed (quote - entry) / |entry - stop_loss|; None if quote None/non-finite
def net_outcome(trade: dict) -> tuple[str, str | None]
    # >= 2 legs expected. raw > +EPS -> ("win", None); raw < -EPS -> ("loss", None);
    # |raw| <= EPS -> ("closed", "scratch"); raw None / non-finite -> ("closed", "unscored") + log.warning naming trade.get("id") or trade.get("plan_id")
def label_counts(closed: list[dict]) -> dict[str, int]    # {"scratch": n, "unscored": n} by close_reason (V189-20)
```

`performance.closed_r_multiple(t)` returns `metrics.r_multiple(t)` (V189-1).

### Golden fixture (V189-2; read by V189-4, V189-10, V189-11, V189-18, V189-19, V189-21, V189-22)

`tests/analytics/golden_partial_trade.json` (Vitest reads it as `'../tests/analytics/golden_partial_trade.json'` from `process.cwd()`):

```json
{
  "trade": {"ticker": "GOLD", "direction": "bullish", "shares": 100, "tp1_fraction": 0.5,
            "entry": 100.0, "stop_loss": 95.0, "tp1": 110.0, "tp2": 120.0, "risk_per_share": 5.0,
            "tp1_leg": {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}},
  "tolerance": 0.005,
  "closed_cases": [
    {"name": "floor",  "runner_exit": 106.66666666666667, "runner_r": 1.3333, "net_r": 1.6667, "realized_pnl_amount": 833.33, "pnl_pct": 8.33,  "status": "win",  "close_reason": null},
    {"name": "gap",    "runner_exit": 88.0,  "runner_r": -2.4, "net_r": -0.2, "realized_pnl_amount": -100.0, "pnl_pct": -1.0, "status": "loss", "close_reason": null, "backtest_label": "win"},
    {"name": "time_exit", "runner_exit": 112.0, "runner_r": 2.4, "net_r": 2.2, "realized_pnl_amount": 1100.0, "pnl_pct": 11.0, "status": "win", "close_reason": null},
    {"name": "manual", "runner_exit": 115.0, "runner_r": 3.0, "net_r": 2.5, "realized_pnl_amount": 1250.0, "pnl_pct": 12.5, "status": "win", "close_reason": null}
  ],
  "open_cases": [
    {"name": "quote_113", "quote": 113.0, "shares": 50, "entry_shares": 100, "r_multiple": 2.3, "banked_r": 2.0,
     "banked_contribution_r": 1.0, "banked_amount": 500.0, "unrealized_pnl_amount": 650.0,
     "working_stop": 106.66666666666667, "risk_of_loss_amount": 0.0, "open_profit_to_stop": 316.67},
    {"name": "no_quote", "quote": null, "shares": 50, "entry_shares": 100, "r_multiple": null, "banked_r": 2.0,
     "banked_contribution_r": 1.0, "banked_amount": 500.0, "unrealized_pnl_amount": null,
     "working_stop": 106.66666666666667, "risk_of_loss_amount": 0.0, "open_profit_to_stop": null}
  ],
  "missing_leg_r_case": {"legs": [{"fraction": 0.5, "exit_price": 110.0}, {"fraction": 0.5, "exit_price": 115.0}], "net_r": 2.5},
  "calendar_day": {"golden_case": "manual",
                   "other_trade": {"ticker": "LOSS", "direction": "bullish", "shares": 100, "entry": 50.0, "stop_loss": 48.0, "exit_price": 48.0, "status": "loss"},
                   "net_r": 1.5, "net_pnl_amount": 1050.0, "trade_count": 3, "win_rate": 66.66666666666667},
  "label_table": [
    {"net_r": 0.02, "status": "win", "close_reason": null},
    {"net_r": 0.005, "status": "closed", "close_reason": "scratch"},
    {"net_r": 0.0, "status": "closed", "close_reason": "scratch"},
    {"net_r": -0.005, "status": "closed", "close_reason": "scratch"},
    {"net_r": -0.02, "status": "loss", "close_reason": null}
  ]
}
```

V189-2 verifies `calendar_day.trade_count` and `win_rate` against `pnl_calendar`'s existing day semantics before committing the file; any different reading of those two keys is a stop-and-ask, not an edit. **Resolved by V189-2 (part 1):** `pnl_calendar` makes each leg its own row, so the golden manual-close day is 3 rows (TP1 leg win, runner leg win, −1R loss): `trade_count` 3, `win_rate` 66.67. That is the only reading consistent with `net_r` 1.5 and `net_pnl_amount` 1050.

### Locks and the guarded store (V189-5, V189-6)

```python
# swingbot/core/db/engine.py
BOT_LOCK_TIMEOUT_MS = 1000
ADMIN_LOCK_TIMEOUT_MS = 5000
class LockTimeout(Exception): ...   # raised from transaction() when Postgres reports SQLSTATE 55P03
@contextmanager
def transaction(conn=None, *, lock_timeout_ms: int | None = None)
    # owned tx: SET LOCAL lock_timeout = '<ms>ms' when given; passthrough conn: unchanged (caller set it)
# swingbot/core/db/repositories/base.py
def Repository.get_for_update(self, key_value, *, conn) -> dict | None   # SELECT ... FOR UPDATE; conn required
# swingbot/core/planning/plan_store.py
class PlanStore:
    def __init__(self, *, lock_timeout_ms: int = ADMIN_LOCK_TIMEOUT_MS)
    lock_timeout_ms: int
    def lock_for_update(self, plan_id: str, *, conn) -> TradePlanV2 | None
    def update(self, plan: TradePlanV2, *, conn=None) -> bool
        # False (+ INFO "plan store: refused stale write to %s (stored %s, incoming %s)") when stored terminal and incoming status differs
        # raises KeyError when the row is absent; LockTimeout propagates
```

### TradeLog and account (V189-7, V189-11, V189-12, V189-14)

```python
# swingbot/core/planning/account.py
def _sum_realized_pnl(*, conn=None) -> float
def load_account_config(*, conn=None) -> dict
def save_account_config(config: dict, *, conn=None) -> None
def apply_realized_pnl(pnl_amount: float, meta: dict = None, *, conn=None) -> dict
# swingbot/core/tracking/performance.py
def run_after_commit(callbacks: list) -> None        # each zero-arg callable; exceptions logged at WARNING and swallowed
TradeLog._settle_account_balance(self, t: dict, *, conn=None) -> None   # conn given: failures RAISE (roll the close back)
TradeLog.append_leg_by_plan(self, plan_id: str, leg: dict, *, conn=None) -> None
TradeLog.record_plan_fill(self, plan_id: str, fill_price: float, *, conn=None) -> str | None
TradeLog.discard_plan_placeholder(self, plan_id: str, *, conn=None) -> bool
TradeLog.close_plan_trade(self, plan_id, leg, status, *, conn=None, close_reason: str | None = None,
                          after_commit: list | None = None) -> dict | None     # returns the closed trade
TradeLog.close_trade_manual(self, trade_id, reason="manual", *, exit_price=None, conn=None,
                            after_commit: list | None = None) -> bool          # V189-11: net_outcome when >= 2 legs
TradeLog.close_trade_reversed(self, trade_id: str, exit_price: float) -> dict | None   # V189-12: one tx with its plan
def _close_linked_plan_safely(plan_id: str, reason: str, *, conn=None) -> None          # V189-12
TradeLog.delete_trade(self, trade_id) -> DeleteResult                           # V189-14
TradeLog.clear_open(self) -> DeleteResult                                       # V189-14
TradeLog.clear_history(self, *, force: bool = False) -> int                     # V189-15 wrapper
```

### Plan manager (V189-8, V189-9, V189-10)

```python
# swingbot/core/planning/plan_manager.py
class PlanWriteAborted(Exception): ...    # stale write refused; INFO; step emits nothing
class PlanPersistFailed(Exception): ...   # transaction rolled back after logging ERROR; step emits nothing
PlanManager.__init__: sets store.lock_timeout_ms = BOT_LOCK_TIMEOUT_MS when the store has the attribute
PlanManager._save(self, plan, *, conn=None) -> None                  # store.update; False -> PlanWriteAborted(plan.plan_id)
PlanManager._persist_fill(self, plan, fill: float) -> str | None     # one tx: _save + trade_log.record_plan_fill(conn=); returns trade id
PlanManager._persist_partial(self, plan, leg: dict) -> None          # one tx: _save + trade_log.append_leg_by_plan(conn=)
PlanManager._persist_terminal(self, plan, leg, status, close_reason: str | None = None) -> bool
    # one tx: _save + close_plan_trade(conn=, close_reason=, after_commit=cbs); run_after_commit(cbs) after commit
    # any exception other than PlanWriteAborted: retry once at once; second failure -> ERROR log, _exit_failures entry, PlanPersistFailed
PlanManager.take_exit_failures(self) -> list[dict]   # drains [{"plan_id","ticker","exit_price","reason","error"}]   (V189-9)
PlanManager._step_safely(self, plan, price: float, now) -> list[PlanEvent] | None   # None = skip this plan (V189-9)
PlanManager._ordered(self, plans: list) -> list      # non-PENDING first, stable (V189-9)
def _usable_price(price) -> bool                     # math.isfinite(price) and price > 0 (V189-9)
PlanManager._plan_outcome(self, plan) -> tuple[str, str | None]   # metrics.net_outcome on the plan's legs (V189-10)
# swingbot/commands/scanning/loops.py (V189-9)
async def _post_exit_failures(failures: list[dict]) -> None
    # "⚠️ Exit not recorded: {ticker} plan `{plan_id}` -- observed {reason} exit at {exit_price}. The book still shows the position open; check it by hand."
```

`event.detail["trade_id"]` is set by `_persist_fill`'s caller (the fill branch of v187's `_fill_pending`), so `_on_event`'s `log_trade` fallback runs only when `_persist_fill` returned `None`.

### Plan links (V189-12, V189-14)

```python
# swingbot/core/tracking/plan_links.py (new, V189-12)
LINKED_TERMINAL: dict    # {PENDING: CANCELLED, ACTIVE: CLOSED, PARTIAL: CLOSED}
TRADE_DELETED_EVENT = "cancelled_trade_deleted"
@dataclass(frozen=True)
class EndedPlan: plan_id: str; ticker: str; status_before: str; status_after: str
@dataclass(frozen=True)
class DeleteResult:
    removed: int
    ended: tuple[EndedPlan, ...] = ()
    def __bool__(self) -> bool            # removed > 0
def end_linked_plan(plan_id: str, reason: str, *, conn, notice: bool = False) -> EndedPlan | None
    # PlanStore().lock_for_update -> LINKED_TERMINAL -> record_transition(reason, at=now) -> optional pending_notice -> update(conn=)
def cancel_if_unfilled(plan_id: str, reason: str) -> bool
    # own tx (BOT_LOCK_TIMEOUT_MS): lock plan; PENDING -> end_linked_plan + discard_plan_placeholder(conn=); True. Else False.
def describe_ended(result: DeleteResult) -> str     # "" when nothing ended (V189-14)
# swingbot/core/scanning/scan_run.py (V189-12)
def _settle_reversal(trade_log, existing_trade: dict, live_price: float) -> dict | None
def _log_heat_block(ticker: str, enforced_pct: float, add_pct: float, cap_pct: float) -> None   # V189-19
    # INFO "heat blocked (enforced %.2f%% + %.2f%% > cap %.2f%%) %s"
```

### Vocabulary (V189-13)

| Site | `cancelled_trade_deleted` |
|---|---|
| `plan_manager.PENDING_CANCEL_EVENTS` | member |
| `plan_manager._TRANSITION_LOG` | `("trade deleted", "live_price")` (detail `live_price` is `None`) |
| `instructions._CANCEL_LEADS` | `""` |
| `instructions._cancel_why` | `The trade record was deleted before the order filled. Nothing was opened and the plan is no longer monitored.` |
| `instructions._BUILDERS` | `_cancelled` |
| `lifecycle_embeds._EVENT_KINDS` / `execution_embeds` kind map | `Kind.CANCEL` |
| `lifecycle_embeds._EVENT_FIELDS` | `_trade_deleted_fields` |
| `session_expiry._IN_SESSION_CODES` | `TRADE_DELETED = "trade_deleted"` |
| `follow_notify._BY_TRANSITION` | `"closed_other"` |
| `follow_notify._CLOSED_OTHER_KIND` | `Kind.INVALIDATED` |
| `follow_notify._CANCEL_LABELS` | `"trade record deleted before fill"` |

Event detail: `{"reason": "trade_deleted", "live_price": None}`.

### Account reset (V189-15, V189-16, V189-17)

```python
# swingbot/core/tracking/account_reset.py (new)
RESET_REASON = "account_reset"
class ResetRefused(Exception): ...          # kill switch tripped and not forced
class ArchiveFailed(Exception): ...         # archive write failed; nothing deleted
@dataclass(frozen=True)
class ResetResult:
    removed_trades: int; removed_plans: int; archive_path: str
    throttle_multiplier: float; throttle_paused: bool; kill_on: bool; base_balance: float; reset_at: str
def archive_dir() -> Path                                   # Path(config.DATA_DIR) / "archives"
def collect_archive(*, conn) -> dict
    # {"version": 1, "reset_at", "base_balance", "trades": [...closed], "plans": [...CLOSED/CANCELLED],
    #  "account_balance_history": [...], "starred_plans": [...], "plan_followers": [...], "plan_notifications": [...]}
def reset_closed_history(*, force: bool = False, now: datetime | None = None) -> ResetResult
    # refuse if kill on and not force -> write archive (ArchiveFailed aborts) -> one tx (ADMIN timeout):
    # delete closed trades + terminal plans + all history, reseed {"ts": reset_at, "balance": base, "pnl_amount": 0.0,
    # "reason": RESET_REASON, "archive": <file name>}, save config balance = base -> after commit refresh snapshot
def describe_reset(result: ResetResult) -> str
REFUSED_TEXT: str
def restore_archive(path: str | Path, *, apply: bool = False) -> dict    # V189-17; refuses (ValueError) after a later reset
# repositories
PlanRepository.delete_terminal(self, *, conn) -> int
AccountRepository.clear_history(self, *, conn) -> int
```

Admin `POST /api/v1/trades/clear-history` accepts `?force=true` (or JSON `{"force": true}`): 200 `{"removed", "removed_plans", "archive", "throttle": {"multiplier", "paused"}, "kill_switch": bool, "notice"}`; 409 `kill_switch_tripped`; 500 `archive_failed`. Discord: `!trades clear history [force]`, `/trades-clear-history force:<bool>`.

### Display (V189-18, V189-19, V189-20)

Trades API row: `entry_shares: float | None` (original size), `banked_contribution_r: float | None`; `r_multiple` of an open PARTIAL = `metrics.open_trade_r` (None without quote). Dashboard JSON: `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`, `risk_cap_pct`. Risk page row: `risk_of_loss_pct`, `risk_of_loss_amount` beside `risk_pct`. Analytics performance: `scratch_n`, `unscored_n`, `label_basis_since`.

```python
# swingbot/core/edge/heat.py
def risk_of_loss_amount(entry, working_stop, direction: str, open_shares) -> float
    # open_shares * max(0, entry - stop) bull / max(0, stop - entry) bear; 0.0 on missing or non-finite input
# swingbot/core/tracking/equity.py
def position_risk_of_loss(trade: dict, plan) -> float | None
    # None for an unfilled (PENDING) plan's placeholder; else risk_of_loss_amount(entry, plan.working_stop or plan.stop_loss
    # (trade stop_loss when no plan), direction, open_shares(trade shares, plan legs))
```

Frontend: `TradeRow.entry_shares?: number | null`, `TradeRow.banked_contribution_r?: number | null`; dashboard model `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`; risk row `risk_of_loss_pct`, `risk_of_loss_amount`; analytics performance `scratch_n`, `unscored_n`, `label_basis_since`. `frontend/src/app/ui/testing/golden-partial-trade.ts` exports `GOLDEN_FIXTURE_PATH` and `loadGoldenPartialTrade(): GoldenPartialTrade`.

## Review Focus

- V189-6: the race tests use two real connections; the stale-terminal refusal and the tighter-stop merge both hold; `update` never holds `_LOCK` while waiting on the row.
- V189-7/8: a failing leg, fill or balance write leaves no plan transition, no trade change and no balance point; hooks run after commit only.
- V189-9: `poll` complexity at or below 20; an exit is retried once with the same price; a missed exit reaches the ops channel.
- V189-10/11: the label table over all three close paths; single-leg closes unchanged.
- V189-12: `_sync_run_scan` complexity strictly below 96 after the extraction; no P&L on a placeholder.
- V189-15: archive written before anything is deleted; reseed point present; kill switch never cleared.
- V189-18..24: every golden figure matches the fixture on both sides.

## Parallelisation

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V189-1 | none | first task: checks v187 is merged, creates the worktree, runs `/replicate-prod-db`; owns `metrics.py` and `performance.closed_r_multiple` |
| V189-2 | V189-3, V189-5, V189-25 | after V189-1: same file `metrics.py`, consumes `_blended_r_raw` |
| V189-3 | V189-2, V189-4, V189-5, V189-6 | after V189-1: consumes `metrics.r_multiple`; disjoint file `retrospective.py` |
| V189-4 | V189-3, V189-5, V189-6 | after V189-1 (same file `performance.py`, consumes `leg_contribution_r`) and V189-2 (golden fixture) |
| V189-5 | V189-2, V189-3, V189-4 | after V189-1's worktree step; disjoint files `engine.py`, `repositories/base.py` |
| V189-6 | V189-3, V189-4, V189-2 | after V189-5: consumes `transaction(lock_timeout_ms=)`, `get_for_update`, `LockTimeout` |
| V189-7 | V189-6, V189-18 | after V189-4 (same file `performance.py`) and V189-5 (`transaction`) |
| V189-8 | V189-18, V189-20 | after V189-6 (`update -> bool`, `lock_for_update`) and V189-7 (`conn=` / `after_commit=`); owns `plan_manager.py` |
| V189-9 | V189-18, V189-20 | after V189-8: same file `plan_manager.py`; consumes `PlanPersistFailed`, `_persist_terminal` |
| V189-10 | V189-18, V189-20 | after V189-9 (same file) and V189-2 (`net_outcome`), V189-7 (`close_reason=`) |
| V189-11 | V189-13, V189-18, V189-20 | after V189-7 (`performance.py`, `after_commit`), V189-6 (`lock_for_update`), V189-2 (`net_outcome`) |
| V189-12 | V189-13, V189-18, V189-20 | after V189-11: same file `performance.py` |
| V189-13 | V189-11, V189-12, V189-18 | after V189-10: same file `plan_manager.py` (`PENDING_CANCEL_EVENTS`, `_TRANSITION_LOG`) |
| V189-14 | V189-18, V189-20 | after V189-12 (`plan_links.py`, `performance.py`), V189-13 (event), V189-11 (`trade_commands.py`) |
| V189-15 | V189-18, V189-20 | after V189-14: same file `performance.py` (`clear_history`) |
| V189-16 | V189-17, V189-18 | after V189-15 (`reset_closed_history`) and V189-14 (`trade_commands.py`, `commands/trades.py`) |
| V189-17 | V189-16, V189-18 | after V189-15: same file `account_reset.py` |
| V189-18 | any of V189-7..V189-17, V189-20 | after V189-2: consumes `banked_contribution_r`, `open_trade_r`, the golden fixture; disjoint file `api_v1/trades.py` |
| V189-19 | V189-16, V189-17, V189-20 | after V189-12: same file `scan_run.py` (heat-blocked line) |
| V189-20 | V189-8..V189-19 | after V189-2 (same file `metrics.py`); disjoint `api_v1/analytics.py` |
| V189-21 | V189-19, V189-20 | after V189-18 (API fields) and V189-2 (fixture); owns `models.ts`, `plan-cell.ts`, `trades.ts`, `dashboard.ts` |
| V189-22 | V189-19, V189-20, V189-23, V189-25 | after V189-21: consumes `entry_shares` and the fixture loader; disjoint files (trade-detail store, card, tiles) |
| V189-23 | V189-22, V189-25 | after V189-19 (API keys) and V189-21 (same files `models.ts`, `dashboard.ts`) |
| V189-24 | V189-22, V189-25 | after V189-20 (API keys) and V189-23 (same file `models.ts`) |
| V189-25 | V189-2..V189-24 | after V189-1's worktree step; disjoint docs only |
| V189-26 | none | after every other task: sets `LABEL_BASIS_SINCE`, single full-suite run, complexity gate, merge |

At most two `task-implementer`s at once; two tasks that share a file never run together. Backend tasks V189-1..V189-20 and frontend tasks V189-21..V189-24 commit separately.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-23-v189-book-integrity-partial-truth_1-metrics-and-calendar.md` | V189-1..V189-4 | worktree and prod-db replica; one R and leg contribution; net-R labels and the golden fixture with the backtest parity pin; retrospective on `metrics.r_multiple`; Calendar sums contributions |
| 2 | `2026-10-23-v189-book-integrity-partial-truth_2-locked-writes.md` | V189-5..V189-7 | per-path lock timeouts and `get_for_update`; the guarded `PlanStore.update` with race tests; `conn=` through TradeLog and the account balance, hooks after commit |
| 3 | `2026-10-23-v189-book-integrity-partial-truth_3-plan-manager-transactions.md` | V189-8..V189-9 | TP1 leg and fill in the plan's transaction; abort semantics; exit retry and ops notice; stop-first ordering, lock skip and finite-quote guards; net-R labels on runner and time-exit closes |
| 3b | `2026-10-23-v189-book-integrity-partial-truth_3b-net-labels.md` | V189-10 | runner and time-exit closes labelled by net R (`_plan_outcome`) |
| 4 | `2026-10-23-v189-book-integrity-partial-truth_4-book-fixes.md` | V189-11..V189-12 | manual close in one transaction with the A2 runner leg; plan links, reversal against a placeholder |
| 4b | `2026-10-23-v189-book-integrity-partial-truth_4b-delete-vocabulary.md` | V189-13..V189-14 | `cancelled_trade_deleted` vocabulary; deletes end linked plans with honest confirmations |
| 5 | `2026-10-23-v189-book-integrity-partial-truth_5-account-reset.md` | V189-15..V189-17 | archived full reset with reseed and kill-switch refusal; admin and Discord surfaces with `force`; restore script and deploy-doc paragraph |
| 6 | `2026-10-23-v189-book-integrity-partial-truth_6-partial-display-api.md` | V189-18..V189-20 | trades rows (`entry_shares`, `banked_contribution_r`, blended open R); risk of loss beside enforced heat and the heat-blocked line; analytics label-basis counts |
| 7 | `2026-10-23-v189-book-integrity-partial-truth_7-frontend-and-release.md` | V189-21..V189-26 | frontend banked amount and labels, trade detail tiles, dashboard and risk page, analytics win-rate hint; known-traps and audit-doc notes; label-basis date, full suite and merge |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V189-1 | Worktree, prod-db replica; one trade-level R and the leg contribution | 1 | opus | M `swingbot/core/analytics/metrics.py`, `swingbot/core/tracking/performance.py`; C `tests/analytics/test_metrics_leg_contribution.py` | worktree branch `2026-10-23-v189-book-integrity-partial-truth`; `leg_contribution_r(leg) -> float \| None`, `_blended_r_raw(trade) -> float \| None`, `banked_contribution_r(legs) -> float \| None`, `open_trade_r(trade, quote) -> float \| None`; `closed_r_multiple` delegates to `r_multiple` |
| V189-2 | Net-R labels for scaled-out closes; golden fixture; backtest parity pin | 1 | sonnet | M `swingbot/core/analytics/metrics.py`; C `tests/analytics/golden_partial_trade.json`, `tests/analytics/test_net_outcome.py`, `tests/analytics/test_golden_partial_trade_metrics.py` | `SCRATCH_EPS_R = 0.01`, `LABEL_BASIS_SINCE = None`, `net_outcome(trade) -> tuple[str, str \| None]`; the golden fixture (shape in § Contracts) |
| V189-3 | Retrospective uses metrics.r_multiple; delete its private copy | 1 | sonnet | M `swingbot/core/tracking/retrospective.py`; C `tests/tracking/test_retrospective_legged_r.py` | `retrospective._r_multiple` removed |
| V189-4 | Calendar sums leg contributions | 1 | opus | M `swingbot/core/tracking/performance.py` (`expand_trade_legs`), `swingbot/core/analytics/pnl_calendar.py`; C `tests/analytics/test_pnl_calendar_contributions.py` | leg parts carry `fraction` and `leg_r` keys |
| V189-5 | Per-path lock timeouts and a FOR UPDATE read | 2 | sonnet | M `swingbot/core/db/engine.py`, `swingbot/core/db/repositories/base.py`; C `tests/db/test_lock_timeout.py` | `BOT_LOCK_TIMEOUT_MS`, `ADMIN_LOCK_TIMEOUT_MS`, `LockTimeout`, `transaction(conn=None, *, lock_timeout_ms=None)`, `Repository.get_for_update(key, *, conn)` |
| V189-6 | Guarded PlanStore.update: row lock, stale-terminal refusal, tighter stops | 2 | opus | M `swingbot/core/planning/plan_store.py`; C `tests/planning/test_plan_store_guard.py`, `tests/db/test_plan_store_race.py` | `PlanStore(*, lock_timeout_ms=ADMIN_LOCK_TIMEOUT_MS)`, `PlanStore.lock_for_update(plan_id, *, conn) -> TradePlanV2 \| None`, `PlanStore.update(plan, *, conn=None) -> bool` |
| V189-7 | One transaction for TradeLog and the balance; hooks after commit | 2 | opus | M `swingbot/core/planning/account.py`, `swingbot/core/tracking/performance.py`, `tests/tracking/test_close_trade_manual_exit_price.py` (doubles only if needed); C `tests/tracking/test_tradelog_conn.py` | `conn=` on `_sum_realized_pnl`, `load_account_config`, `save_account_config`, `apply_realized_pnl`, `_settle_account_balance`, `append_leg_by_plan`, `record_plan_fill`, `discard_plan_placeholder`; `close_plan_trade(..., close_reason=None, after_commit=None) -> dict \| None`; `run_after_commit(callbacks)` |
| V189-8 | Plan manager: TP1 leg and fill commit with the plan; aborts emit nothing | 3 | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_plan_manager_atomic_writes.py` | `PlanWriteAborted`, `PlanPersistFailed`, `_save`, `_persist_fill`, `_persist_partial`, `_persist_terminal(plan, leg, status, close_reason=None)` with after-commit hooks; `_on_event` no longer writes legs or fills |
| V189-9 | Exit retry and ops notice; lock skip, stop-first order, finite quotes | 3 | opus | M `swingbot/core/planning/plan_manager.py`, `swingbot/commands/scanning/loops.py`; C `tests/planning/test_plan_manager_exit_retry.py`, `tests/planning/test_plan_manager_quote_guard.py` | `take_exit_failures() -> list[dict]`, `_step_safely`, `_ordered`, `_usable_price`; `loops._post_exit_failures(failures)` |
| V189-10 | Runner and time-exit closes labelled by net R | 3b | opus | M `swingbot/core/planning/plan_manager.py`; C `tests/planning/test_plan_manager_net_labels.py` | `_plan_outcome(plan) -> tuple[str, str \| None]`; `_close_runner` / `_close_time_exit` pass `close_reason` |
| V189-11 | Manual close in one transaction; the runner leg reaches the plan | 4 | opus | M `swingbot/core/tracking/performance.py`, `swingbot/admin/api_v1/trade_commands.py`; C `tests/admin/test_close_plan_atomic.py`, `tests/tracking/test_manual_close_labels.py` | `close_trade_manual(..., conn=None, after_commit=None)` labels by `net_outcome` when >= 2 legs; `_close_plan` network-first then one tx |
| V189-12 | Plan links; a reversal never books a never-filled placeholder | 4 | opus | C `swingbot/core/tracking/plan_links.py`, `tests/tracking/test_plan_links.py`, `tests/scanning/test_reversal_placeholder.py`; M `swingbot/core/tracking/performance.py`, `swingbot/core/scanning/scan_run.py` | `LINKED_TERMINAL`, `EndedPlan`, `DeleteResult`, `TRADE_DELETED_EVENT`, `end_linked_plan`, `cancel_if_unfilled`; `_close_linked_plan_safely(plan_id, reason, *, conn=None)`; `scan_run._settle_reversal` |
| V189-13 | The cancelled_trade_deleted event across the vocabulary | 4b | sonnet | M `swingbot/core/planning/plan_manager.py`, `swingbot/core/presentation/instructions.py`, `swingbot/core/scanning/lifecycle_embeds.py`, `swingbot/core/scanning/execution_embeds.py`, `swingbot/core/planning/session_expiry.py`, `swingbot/commands/scanning/follow_notify.py`; C `tests/presentation/test_trade_deleted_cancel_vocab.py` | `cancelled_trade_deleted` in `PENDING_CANCEL_EVENTS`; `session_expiry.TRADE_DELETED`; `_trade_deleted_fields` |
| V189-14 | Deletes end their linked plans and say so | 4b | opus | M `swingbot/core/tracking/plan_links.py`, `swingbot/core/tracking/performance.py`, `swingbot/admin/api_v1/trade_commands.py`, `swingbot/commands/trades.py`, `tests/commands/parity_cases/trades.py`, `tests/tracking/test_tradelog_db_bulk.py`, `tests/admin/test_api_v1_trade_commands.py`; C `tests/tracking/test_delete_ends_linked_plans.py`, `tests/admin/test_delete_ends_plans_api.py` | `TradeLog.clear_open() -> DeleteResult`, `TradeLog.delete_trade(id) -> DeleteResult`, `describe_ended(result) -> str`; JSON `ended`, `notice` |
| V189-15 | Clear history becomes an archived full reset | 5 | opus | C `swingbot/core/tracking/account_reset.py`, `tests/tracking/test_account_reset.py`; M `swingbot/core/db/repositories/plans.py`, `swingbot/core/db/repositories/account.py`, `swingbot/core/tracking/performance.py`, `.gitignore`, `tests/tracking/test_tradelog_db_bulk.py` | `ResetResult`, `ResetRefused`, `ArchiveFailed`, `RESET_REASON`, `archive_dir`, `collect_archive`, `reset_closed_history(*, force=False, now=None)`, `describe_reset`, `REFUSED_TEXT`; `PlanRepository.delete_terminal`, `AccountRepository.clear_history` |
| V189-16 | Reset surfaces: endpoint force, Discord force, confirmation text | 5 | sonnet | M `swingbot/admin/api_v1/trade_commands.py`, `swingbot/commands/trades.py`, `tests/commands/parity_cases/trades.py`, `tests/commands/test_reply_parity.py`, `tests/admin/test_api_v1_trade_commands.py`; C `tests/admin/test_clear_history_reset_api.py`, `tests/commands/test_trades_clear_history_force.py` | endpoint `?force=true`; `handle_trades_clear_history(reply, force: bool = False)` |
| V189-17 | Restore script and the deploy-doc procedure | 5 | sonnet | C `scripts/ops/restore_account_reset.py`, `tests/scripts/test_restore_account_reset.py`; M `swingbot/core/tracking/account_reset.py`, `docs/deploy/DEPLOY_HETZNER.md` | `restore_archive(path, *, apply=False) -> dict` |
| V189-18 | Trades API rows: entry_shares, banked contribution, blended open R | 6 | sonnet | M `swingbot/admin/api_v1/trades.py`, `tests/admin/test_trades_partial_row.py`, `tests/admin/test_api_v1_trades.py`; C `tests/admin/test_trades_golden_rows.py` | row keys `entry_shares`, `banked_contribution_r`; open-PARTIAL `r_multiple` = `open_trade_r` |
| V189-19 | Risk of loss beside enforced heat; heat-blocked log line | 6 | opus | M `swingbot/core/edge/heat.py`, `swingbot/core/tracking/equity.py`, `swingbot/admin/api_v1/dashboard.py`, `swingbot/admin/api_v1/risk.py`, `swingbot/core/scanning/scan_run.py`, `tests/admin/test_api_v1_dashboard.py`, `tests/admin/test_api_v1_risk.py`; C `tests/edge/test_risk_of_loss.py`, `tests/admin/test_risk_of_loss_api.py` | `heat.risk_of_loss_amount`, `equity.position_risk_of_loss`, `scan_run._log_heat_block`; dashboard keys `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`; risk row keys `risk_of_loss_pct`, `risk_of_loss_amount` |
| V189-20 | Analytics carries the label basis and scratch/unscored counts | 6 | sonnet | M `swingbot/core/analytics/metrics.py`, `swingbot/admin/api_v1/analytics.py`, `tests/admin/test_api_v1_analytics.py`, `tests/admin/test_api_analytics.py`; C `tests/admin/test_analytics_label_basis.py` | `metrics.label_counts(closed) -> dict[str, int]`; payload keys `scratch_n`, `unscored_n`, `label_basis_since` |
| V189-21 | Frontend: banked amount on entry shares; banked label; golden loader | 7 | sonnet | M `frontend/src/app/api/models.ts`, `frontend/src/app/ui/plan-cell.ts`, `frontend/src/app/ui/plan-cell.spec.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`; C `frontend/src/app/ui/testing/golden-partial-trade.ts`, `frontend/src/app/ui/plan-cell.golden.spec.ts` | `TradeRow.entry_shares?`, `TradeRow.banked_contribution_r?`; `GOLDEN_FIXTURE_PATH`, `loadGoldenPartialTrade()`; `bankedLegAmount(entry, bankedEntry, bankedFraction, entryShares, direction)` |
| V189-22 | Frontend: trade detail banked stats, risk of loss, open profit to stop, T1/T2 | 7 | sonnet | M `frontend/src/app/stores/trade-detail.store.ts`, `frontend/src/app/workspaces/trades/position-card.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/outcome-tiles.ts`; C `frontend/src/app/stores/trade-detail.golden.spec.ts` | store signals `riskOfLoss`, `openProfitToStop` (replace `dollarAtRisk`) |
| V189-23 | Frontend: dashboard risk-of-loss and enforced-heat tiles; risk page column | 7 | sonnet | M `frontend/src/app/api/models.ts`, `frontend/src/app/stores/dashboard.store.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/stores/risk.store.ts`; C `frontend/src/app/workspaces/dashboard/dashboard-risk.spec.ts` | dashboard model `heat_enforced_pct`, `risk_of_loss_pct`, `risk_of_loss_amount`; risk row `risk_of_loss_pct`, `risk_of_loss_amount` |
| V189-24 | Frontend: win-rate tile shows the label basis and scratch/unscored counts | 7 | sonnet | M `frontend/src/app/api/models.ts`, `frontend/src/app/stores/analytics.store.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`; C `frontend/src/app/workspaces/analytics/tabs/overview-label-basis.spec.ts` | `AnalyticsPerformance.scratch_n?`, `unscored_n?`, `label_basis_since?` |
| V189-25 | Known traps and audit doc record what v189 left | 7 | haiku | M `docs/claude/known-traps.md`, `docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md`, `AGENTS.md` (only if the mirror test requires it) | none |
| V189-26 | Label-basis date, full suite, complexity gate, merge | 7 | sonnet | M `swingbot/core/analytics/metrics.py` (`LABEL_BASIS_SINCE`) | merged branch on `main` |
