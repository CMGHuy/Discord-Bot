# v189 — Book integrity and partial-trade truth: one R, honest labels, every screen agrees on a scaled-out trade

**Version:** ui 1.35.0 · bot 2.14.4 (at writing)
**Bump:** bot patch, ui patch. Stored records for new closes become correct, and the partial-trade figures on Trades, Trade detail, Calendar and Dashboard change to the right values. No new screen or control.
**Edge:** none (integrity). It corrects the measured book (win rate, R) and does not change what is traded. The one behaviour change with edge in it, heat enforcement on current risk, is split out to its own spec (see "Not in this spec").
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, risk-manager
**Status:** spec written 2026-10-23 from a brainstorm with the partner, approved in chat. Second of the four audit specs (v187 safety → **v189** → metric definitions → frontend hygiene). Source findings: `docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md` A1–A8, B1–B5, D4, F1.

## Why

A scaled-out trade (TP1 banked, runner still open or closed later) is stored and shown inconsistently. These findings are from the 2026-10-23 audit; ✔ marks the ones re-verified from code:

- **Display.**
  - ✔ Banked TP1 dollars are shown at (1−f) of their value. The API replaces `shares` with the remaining count (`swingbot/admin/api_v1/trades.py:1229-1231`), and `bankedLegAmount` (`frontend/src/app/ui/plan-cell.ts:358`) and `trade-detail.store.ts:425-427` multiply by the fraction again.
  - ✔ Calendar net R sums leg Rs at full size (`swingbot/core/analytics/pnl_calendar.py:191,326`), so +1R TP1 at 50% plus a +3R runner shows +4R.
  - An open PARTIAL with no quote shows its banked R as its R (`trades.py:329`).
  - "Risk used" counts a PARTIAL at its original risk and includes PENDING placeholders (`swingbot/admin/api_v1/dashboard.py:94`).
  - The Trade-detail price tile says "to T1" over TP2 (`outcome-tiles.ts:84`).
- **Record.**
  - A manual close of a PARTIAL writes no runner leg to `plan.legs_realized` (`swingbot/admin/api_v1/trade_commands.py:143-173`), so the Trades table and the Calendar disagree.
  - Any runner close after TP1 is labelled `win` (`swingbot/core/planning/plan_manager.py:1266`). A time-exit or manual close after TP1 is `closed`, so it drops out of win rate (`metrics.win_rate` counts `win`/`loss` only).
  - The TP1 leg and the fill are written outside the terminal transaction (`plan_manager.py:729`). Close hooks run before commit (`:807`).
  - A reversal can settle P&L on a never-filled placeholder (`swingbot/core/scanning/scan_run.py:907-935` → `performance.py:1308`).
  - `clear_open` and `delete_trade` leave linked plans open (`performance.py:1531`, `trade_commands.py:262,271`).
  - Clearing history drops realized P&L from the balance but keeps the old peak (`account.py:138`).
  - The bot and admin processes overwrite each other's plan writes: `threading.Lock` only, last-writer-wins upsert (`performance.py:39`, `plan_store.py`).
  - The daily recap's R ignores legs (`swingbot/core/tracking/retrospective.py:188`).
  - A NaN quote passes `if not price` (`plan_manager.py:1549,1586`).

**Production, counted read-only on 2026-10-23.**

| What | Count |
|---|---|
| closed trades | 1002, of which 112 multi-leg |
| multi-leg `win` with net R < 0 | 2 |
| multi-leg `closed` with net R > 0 (missing winners) | 10 |
| plans missing the runner leg after a manual close | 10 |
| reversal settled on a never-filled placeholder | 1 |
| weak-ledger trades | 0 |

The partner chose **fix forward only**: these 23 historical records are left as they are and are listed under "Known historical records".

**Why a scaled-out trade can end net negative at all.** After TP1 the runner's stop moves to the v39 floor, `entry + ⅔·(tp1 − entry)` (`exit_sim.runner_floor`, `exit_sim.py:389`), which is above entry. A stop cannot fill better than the open (`gap_stop_fill`, `plan_manager.py:45`). So the net goes negative only when the stock gaps below the original stop: an earnings-sized gap. A time-exit or manual runner close sits at or above the floor and is almost always net positive. That is the common case today's label drops.

## Decisions

### D1 — One trade-level R, one leg contribution

- `metrics.r_multiple` (`swingbot/core/analytics/metrics.py:173`) stays the **only** trade-level R. It is fraction-weighted across legs.
- Add `metrics.leg_contribution_r(leg) -> float | None` = `leg.fraction × leg.r`, or None when either is missing. Every place that sums legs uses it.
- Delete `retrospective._r_multiple`. Its callers (`retrospective.py:329,524,620,972,983`) use `metrics.r_multiple`.
- Of the ~72 inline R/P&L formulas (audit F1), only those in code this spec already edits are migrated. The rest are left and recorded in the audit doc. Chasing all of them is a refactor with no correctness payoff that this spec can measure.

### D2 — The status of a close with realized legs follows the net R sign

One function, `metrics.net_outcome(trade) -> tuple[status, close_reason | None]`, labels every close that has at least one realized leg:

| Blended net R | `status` | `close_reason` |
|---|---|---|
| `> +0.01` | `win` | as today |
| `< −0.01` | `loss` | as today |
| within ±0.01 | `closed` | `scratch` |

- **Callers.** `_close_runner` (replacing the `tp1_*` → `win` rule at `plan_manager.py:1266`), the time-exit close (`:1360`), and the manual close (`trade_commands._close_plan`).
- **Single-leg trades are unchanged.** `resolve_outcome` and `win_rate` are untouched; they already read `status`.
- **Net R is `metrics.r_multiple`.** When R cannot be computed (a missing risk basis), the status falls back to today's rule and logs a warning naming the trade.

### D3 — The record is written whole or not at all

1. **TP1 leg and fill inside the transaction.** `append_leg_by_plan` and `record_plan_fill` move into the same transaction as the plan write that triggered them (`_on_event`, `plan_manager.py:729`). A failure rolls back the plan transition too, and the next poll retries it. Today a missed leg understates P&L permanently.
2. **Side effects after commit.**
   - `_persist_terminal` (`:807`) collects the balance write (`apply_realized_pnl` → `balance_history`), `_after_close` and `_refresh_snapshot_safely` as callbacks, and runs them only after the transaction commits.
   - The snapshot then sees the close.
   - A rollback leaves no `balance_history` point, so a retried close cannot write a duplicate.
3. **Row lock on every plan state write.**
   - Every plan state change (`PlanStore.update` on a status change, the admin `_close_plan`, `delete_trade`, `clear_open`) runs in one transaction that does `SELECT … FOR UPDATE` on the plan row, re-reads its status, and **aborts without writing** if the stored status is already terminal (`CLOSED` or `CANCELLED`) while the caller expected it open.
   - The abort is logged at INFO with the plan id and both statuses.
   - No schema change. The bot's poll and the admin request serialise in Postgres.
   - The `close_trade_manual` docstring's claim of cross-process protection becomes true and is reworded to say how.

### D4 — Book fixes

- **A1, reversal vs placeholder.** In `scan_run.py:907-935`, when the open trade found is the placeholder of a PENDING plan (the plan has no fill transition), the reversal cancels the plan through the normal cancel path, which discards the placeholder. `close_trade_reversed` is never called for it, so no P&L is booked.
- **A2, manual close of a PARTIAL.** `_close_plan` appends the runner leg (fraction = the remaining fraction, exit price, r, `closed_at`, reason `manual`) to `plan.legs_realized`, as well as to the trade's `legs`. The Trades table, Calendar and Trade detail then read the same legs.
- **A6, clear history is a full reset.** `clear_history` (admin `/trades/clear-history` and the Discord command, admin-only since v187) runs in one transaction that:
  - deletes the closed trades;
  - wipes `balance_history`;
  - resets the drawdown peak the throttle reads (`throttle.drawdown_pct`'s source), so the balance returns to `base_balance`.

  Open trades are untouched. The command's confirmation text says it resets the account's realized P&L and drawdown history.
- **A7, deletes cancel linked plans.** `clear_open` and legacy-id `delete_trade` cancel the linked plan (reason `trade_deleted`) in the same transaction. A plan is never left stepping without its trade. `trade_deleted` is added to the pending-cancel and terminal vocabulary that v187 introduces (`PENDING_CANCEL_EVENTS`), or to its active-plan equivalent, whichever applies.
- **D4 from the audit, NaN quotes.** Every quote guard in `poll()` and `monitor_quotes` / `_price_batch_fn` (`plan_manager.py:1549,1586`) uses `math.isfinite(price) and price > 0`.

### D5 — Partial trades on screen

| # | Change |
|---|---|
| B1 | The trades API row gains **`entry_shares`**, the original position size, before any leg. `shares` keeps its meaning: the remaining shares on an open PARTIAL. `bankedLegAmount` takes `entry_shares`, and so do `trades.ts:425`, `dashboard.ts:382` and `trade-detail.store.ts:425-427`. Its doc comment already says "original". `models.ts` adds the field. |
| B2 | `pnl_calendar` uses `metrics.leg_contribution_r` for a leg part's R (`:191`), so day, month and streak sums (`:326,561,603,651`) add contributions. A whole single-leg trade is unchanged. Dollar figures were already right. |
| B3 | An open PARTIAL with no live quote returns `r_multiple: null`, and a new **`banked_r`** field holds `Σ leg_contribution_r` of the realized legs. With a quote, `r_multiple` stays today's live figure. The Trades row and Trade detail show banked R as "banked +0.50R", never as the trade's R. |
| B4 | "Risk used" on the Dashboard (`dashboard.py:94` `_risk_used`) and the Risk page rows (`risk.py:63`) show **current risk**: Σ over **filled** open trades of open shares × distance from entry to the current working stop, floored at 0. A PARTIAL at the runner floor, or a break-even stop, contributes 0. PENDING placeholders are excluded (the `held_now` filter). **Display only.** `heat.open_heat` enforcement at `swingbot/core/scanning/analyze.py:252` is unchanged here. |
| B5 | The Trade-detail price tile labels the target it reads: "to T1" before TP1, "to T2" after (`outcome-tiles.ts:84`). "$ at risk" (`trade-detail.store.ts:553`) = open shares × current-stop distance, floored at 0, with the same definition as B4. |

## Testing

- **One golden partial trade, every screen.** 100 shares, f = 0.5, entry 100, stop 95 (1R = 5), TP1 110, TP2 120. Each exit path is a test case:
  - runner stopped at the floor (106.67);
  - runner gapped to an open of 88 (net < 0 → `loss`);
  - time exit at 112;
  - manual close at 115;
  - open with a quote of 113;
  - open with no quote.

  For each case, assert against hand-computed values:
  - the trades API row (`shares`, `entry_shares`, `r_multiple`, `banked_r`, `realized_pnl_amount`, `pnl_pct`, status);
  - the calendar day (`net_r`, `net_pnl_amount`, `trade_count`, win rate);
  - the dashboard realized parts and Risk used;
  - the frontend banked amount ($500 for the TP1 leg), via the store and cell specs.

  The fixture is shared by the backend and frontend tests, so the two cannot drift.
- **D2.** A label table over net R of +0.02, +0.005, 0, −0.005 and −0.02, across all three close paths. A missing risk basis falls back to today's rule with a warning.
- **D3.**
  - A failing `append_leg_by_plan` rolls back the TP1 transition.
  - A rolled-back close writes no `balance_history` point.
  - The snapshot rebuilt after a close includes it.
  - Two connections race an admin close against a bot `store.update`: the plan ends `CLOSED`, and the abort is logged.
- **D4.**
  - A reversal against a placeholder books no P&L and cancels the plan.
  - A manual close of a PARTIAL writes the runner leg to both stores.
  - Clear history resets the balance, the history and the drawdown peak.
  - `clear_open` cancels its plans.
  - A NaN quote is ignored.
- **Database tests.** Run `/replicate-prod-db` before the first database-backed test run (partner rule). While iterating, run `testrun.py changed`. Run the full suite once, as the plan's final task.

## Known historical records (fix forward only)

The partner chose not to backfill. As of 2026-10-23, production holds:

- 2 multi-leg trades labelled `win` with net R < 0;
- 10 multi-leg trades labelled `closed` with net R > 0, which are missing from win rate;
- 10 plans whose `legs_realized` lacks the manual runner leg;
- 1 reversal trade settled on a never-filled placeholder. Its P&L is in the balance.

Pooled win rate and ExpR computed over history before this spec's deploy carry these. A later spec may backfill them through a data migration (`schema-evolution.md`: no read-time upcasting).

## Not in this spec

- **Heat enforcement on current risk.** The partner chose current risk to stop as the heat definition. Making `open_heat` *enforce* it frees heat budget as trades de-risk. That changes how many alerts are sized: `Edge: volume`, measured in walk-forward (`backtest_wf.py` models the heat cap) before shipping. It gets its own spec. This spec changes only the display (B4).
- **Metric definitions.** The leg-vs-trade counting unit, the day definition, the ledger, the snapshot, the drawdown order, and the live/backtest parity items go to the metric spec.
- **Frontend hygiene** goes to the frontend spec.
