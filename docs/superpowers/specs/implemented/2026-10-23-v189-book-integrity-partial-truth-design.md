# v189 — Book integrity and partial-trade truth: one R, honest labels, every screen agrees on a scaled-out trade

**Version:** ui 1.35.0 · bot 2.14.4 (at writing)
**Bump:** bot patch, ui patch. Stored records for new closes become correct, and the partial-trade figures on Trades, Trade detail, Calendar and Dashboard change to the right values. No new screen or control.
**Edge:** none (integrity). It corrects the measured book (win rate, R) and does not change what is traded. The one behaviour change with edge in it, heat enforcement on current risk, is split out to its own spec (see "Not in this spec").
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, risk-manager
**Status:** spec written 2026-10-23 from a brainstorm with the partner, approved in chat. Second of the four audit specs (v187 safety → **v189** → metric definitions → frontend hygiene). Source findings: `docs/superpowers/results/v187/2026-10-23-repo-audit-findings.md` A1–A8, B1–B5, D4, F1.

**Depends on:** v187 (safety hardening), which must merge first. v189 extends its `PENDING_CANCEL_EVENTS` (A7) and relies on its admin-only gate for `clear_history` (A6).

## Why

A scaled-out trade (TP1 banked, runner still open or closed later) is stored and shown inconsistently. These findings are from the 2026-10-23 audit; ✔ marks the ones re-verified from code:

- **Display.**
  - ✔ Banked TP1 dollars are shown at (1−f) of their value. The API replaces `shares` with the remaining count (`swingbot/admin/api_v1/trades.py:1229-1231`), and `bankedLegAmount` (`frontend/src/app/ui/plan-cell.ts:358`) and `trade-detail.store.ts:425-427` multiply by the fraction again.
  - ✔ Calendar net R sums leg Rs at full size (`swingbot/core/analytics/pnl_calendar.py:191,326`), so a TP1 leg at +2R on 50% plus a runner at +3R shows +5R instead of +2.5R.
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

**Why a scaled-out trade can end net negative at all.** After TP1 the runner's stop moves to the v39 floor, `entry + ⅔·(tp1 − entry)` (`exit_sim.runner_floor`, `exit_sim.py:389`), which is above entry. A stop cannot fill better than the open (`gap_stop_fill`, `plan_manager.py:45`). So the net goes negative only when the stock gaps below the original stop: an earnings-sized gap. A time-exit runner close happens while price is still above the floor, so it is net positive in practice. A manual close uses whatever price the user gives (`_close_plan` applies no floor), so it can be net negative. D2 labels it by its net either way. The time-exit case is the common one today's label drops.

## Decisions

### D1 — One trade-level R, one leg contribution

- `metrics.r_multiple` (`swingbot/core/analytics/metrics.py:173`) stays the **only** trade-level R. It is fraction-weighted across legs.
- Add `metrics.leg_contribution_r(leg) -> float | None` = `leg.fraction × leg.r`, or None when either is missing. Every place that sums legs uses it.
- Delete `retrospective._r_multiple`. Its callers (`retrospective.py:329,524,620,972,983`) use `metrics.r_multiple`.
- Of the ~72 inline R/P&L formulas (audit F1), only those in code this spec already edits are migrated. The rest are left and recorded in the audit doc. Chasing all of them is a refactor with no correctness payoff that this spec can measure.

### D2 — The status of a close with realized legs follows the net R sign

**Scope.** This applies to a trade that **closes with two or more realized legs**: TP1 banked, then the runner closed by stop, gap, time exit or manual close. A trade that never scaled out (one leg, including a manual close of an unscaled ACTIVE trade) keeps today's labels exactly. Its `win_rate` population does not change.

One function, `metrics.net_outcome(trade) -> tuple[status, close_reason | None]`, labels those closes. It compares the **unrounded** blended net R (a helper, `metrics._blended_r_raw`, which `r_multiple` then rounds for display). `r_multiple`'s `round(…, 2)` would otherwise quantise the threshold. The band edges use one named constant, `SCRATCH_EPS_R = 0.01`, and are exclusive:

| Blended net R | `status` | `close_reason` |
|---|---|---|
| `> +0.01` | `win` | as today |
| `< −0.01` | `loss` | as today |
| within ±0.01 | `closed` | `scratch` |

- **Callers.** `_close_runner` (replacing the `tp1_*` → `win` rule at `plan_manager.py:1266`), the time-exit close (`:1360`), and the manual close (`trade_commands._close_plan`).
- **Single-leg trades are unchanged.** `resolve_outcome` and `win_rate` are untouched; they already read `status`.
- **When net R can't be trusted, no label is invented.** If the blend cannot be computed (a missing risk basis) or is not finite (a NaN leg `r` or exit price), the trade is labelled `closed` with `close_reason=unscored`, and a warning names the trade id. It does **not** fall back to today's `tp1_*` → `win` rule: that rule is the bug, and NaN would otherwise land silently in the scratch band.
- **Live and backtest now label differently (stated, not fixed here).** The backtest labels a scaled-out trade by event: "a TP1 touch is a win … whatever the net r" (`swingbot/core/planning/exit_sim_v2.py:12-14`). It splits scratch from loss at `round(gross_r, 3) < 0` (`:127`), with no win branch and no named constant. Changing those labels would reach the closed acceptance gates, which are never re-run (`backtest-methodology.md`), so **D2 is live-only**. The rare gap-below-stop trade is therefore `loss` live and `win` in the backtest, and the live and backtest win rates for scaled-out trades are no longer the same statistic. The metric-definitions spec owns reconciling them, including whether `SCRATCH_EPS_R` becomes the shared constant. A test pins the divergence on the golden gap case, so it can't change silently.

### D3 — The record is written whole or not at all

1. **TP1 leg and fill share the plan write's transaction.**
   - **The real write sites.** The plan writes happen in `_step`, not in `_on_event`:
     - the fill at `plan_manager.py:951-954`;
     - TP1 → PARTIAL at `:1024`;
     - the `check_bar` paths at `:1415-1429`.

     `_on_event` (`:729`) runs afterwards and swallows every exception (`:803-805`).
   - **The fix.**
     - `append_leg_by_plan` and `record_plan_fill` (`performance.py:792,804`) gain a `conn=` parameter.
     - Each is called inside the same transaction as the plan transition that produced it. The plan is never PARTIAL without its trade leg, and never ACTIVE without its fill record.
     - `_on_event` stops making those two calls.
   - **On failure.** The whole transition rolls back and is logged at ERROR. The plan stays in its previous state, and the next poll or bar check re-evaluates it from current prices. If price has pulled back by then, the TP1 touch is not taken. **This is accepted:** a consistent record that missed a touch is better than today's half-write, which shows PARTIAL with no leg and understates P&L forever. The ERROR line makes every occurrence visible.
2. **What runs inside the transaction and what after commit.**
   - **Inside.** The balance write (`apply_realized_pnl` → `account_balance_history`) stays inside the transaction, through the account repository's `conn=` (`swingbot/core/db/repositories/account.py:22-29`). It has to:
     - Its arithmetic, `base + Σ realized + pnl_amount`, is only correct while the trade row is not yet saved (`account.py:366-401`, `:72-103`).
     - The trade row takes `realized_pnl_amount` and `account_balance_after` from its return value (`performance.py:931-935`).
     - A rollback then removes the balance point together with the close, so a retried close cannot duplicate it.
   - **After commit.** Only `_after_close` (journal) and `_refresh_snapshot_safely` move there. `_persist_terminal` (`:807`) collects them as callbacks. Both are rebuildable: a crash between commit and callback leaves at most a stale snapshot or a missing journal entry, never a wrong balance.
   - **The admin path follows the same rule.** `close_trade_manual` (`performance.py:1470-1492`) today commits on its own and runs its own hooks before `_close_plan` updates the plan (`trade_commands.py:159-170`). It gains `conn=` and runs inside `_close_plan`'s transaction, with its hooks after commit. The reversal path's `_close_linked_plan_safely` (`performance.py:118-140,1344`) does the same.
3. **Every plan write is guarded, not only status changes.**
   - **Why all writes.** `PlanStore.update` upserts the whole plan document (`plan_store.py:55-59`). The bot also writes without a status change: `first_seen_price` (`plan_manager.py:680`) and the stop ratchet and giveback updates (`:1194,1206,1221,1241`). Each writes a copy read earlier in the poll (`:650`). Any of them can bring back a plan the admin closed in between, which is audit A8.
   - **So every `PlanStore.update` call:**
     - runs in a transaction that does `SELECT status … FOR UPDATE` on the plan row;
     - **refuses to write** when the stored status is terminal (`CLOSED` or `CANCELLED`) and the incoming document is not the same terminal write.

     A terminal plan can no longer be overwritten by a stale copy, whatever field changed.
   - **Stops never loosen through a stale write.** Inside the same locked update, for an ACTIVE or PARTIAL plan, the written `stop_loss` and `working_stop` are each the **tighter** of the stored and the incoming value (the existing `tighter_stop`, per direction). A stale copy can therefore never move a stop back away from price. Every other field is written as given. A test races the bot holding a stale, looser stop against a fresh ratchet, and asserts the tighter stop survives.
   - **How the caller learns of an abort.**
     - `PlanStore.update` returns `False` and logs at INFO with the plan id and both statuses.
     - `_step` then returns **no events** for that plan.
     - `_persist_terminal` does not close the trade.
     - `poll` and `_close_runner` publish nothing for it (`plan_manager.py:684-686,1265-1268`), so an aborted close sends no Discord notice.
   - **Deadlock rules.**
     - The Postgres row lock is taken first, and no Python `threading.Lock` (`plan_store.py:14,56`, `performance.py:39,866`) is held while waiting on it.
     - Lock timeouts are set per path (`swingbot/core/db/engine.py`; `side_engine.py:66` already sets one).
       - The bot's poll and bar-check writes use `lock_timeout = 1s` and **skip** that plan for this cycle on timeout. One stuck admin transaction can therefore delay a single plan by one poll, never stall the whole loop. Plans with a stop are stepped before PENDING plans.
       - The admin path uses `5s`.
     - **Exits are not left to a price re-test.** A rolled-back or timed-out transition that would have **exited** a position (a stop, gap or time exit, on the poll or the `check_bar` path) is retried once at once, with the same observed price or bar. If that also fails, it is logged at ERROR and posted to the ops/system notice, naming the plan and the observed exit price, so a missed stop is never silent. A missed TP1 needs no retry. A missed stop would flatter the book, which is the asymmetry this rule closes. Both paths are tested.
     - Multi-plan locks (`clear_open`) take rows `ORDER BY plan_id`.
     - The admin `_close_plan` does its network calls (`_override_stamp`, `stamp_runner_path`, `trade_commands.py:152,169`) **before** taking the lock.
   - No schema change. The `close_trade_manual` docstring's claim of cross-process protection becomes true and is reworded to say how.

### D4 — Book fixes

- **A1, reversal vs placeholder.** In `scan_run.py:907-935`, when the open trade found is the placeholder of a PENDING plan (the plan has no fill transition), the reversal cancels the plan through the normal cancel path, which discards the placeholder. `close_trade_reversed` is never called for it, so no P&L is booked.
- **A2, manual close of a PARTIAL.** `_close_plan` appends the runner leg (fraction = the remaining fraction, exit price, r, `closed_at`, reason `manual`) to `plan.legs_realized`, as well as to the trade's `legs`. The Trades table, Calendar and Trade detail then read the same legs.
- **A6, clear history is a full reset, archived first.** `clear_history` (admin `/trades/clear-history` and the Discord command, admin-only since v187) does three things in order:
  1. **Archive.** Write the closed trades, every terminal plan (`CLOSED` or `CANCELLED`, with its `legs_realized`) and every `account_balance_history` row to one JSON file under `data/archives/account-reset-<UTC timestamp>.json`, on the persistent data volume. The reset stops if this write fails. The response and log name the file.
  2. **Reset, in one transaction.**
     - Delete the closed trades and the terminal plans. Plans go too, so plan-based views agree with trade-based ones (`pnl_calendar.py:278`, `snapshots.py:121`).
     - Delete `account_balance_history`.
     - **Reseed** one history point at `base_balance` with the reset timestamp. That is the starting point the throttle, kill switch (`scan_run.py:818-819`, `edge/portfolio_state.py:58-59`), `growth.py:53` and the equity chart read, so the drawdown peak restarts at `base_balance`.
  3. **Refresh** the snapshot after commit.

  Open trades and live plans are untouched. The command's confirmation text says it resets the account's realized P&L and drawdown history, and names the archive. It also states:
  - the current throttle rung and kill-switch state;
  - that the reset restarts the drawdown peak, and so lifts any throttle;
  - that new trades will be sized off `base_balance`.

  **The reset is refused while the kill switch is tripped**, unless the caller passes an explicit override: `force=true` on the endpoint, or `!trades clear history force`. A tripped kill switch is never cleared as a side effect. A test asserts the throttle state after a reset, and the refusal while tripped. **Rollback** is a documented restore: `scripts/ops/restore_account_reset.py <archive>`, written in this spec's plan, re-inserts the archived rows in one transaction. It refuses if a later reset has run since. `docs/deploy/DEPLOY_HETZNER.md` gets the one-paragraph procedure.
- **A7, deletes close or cancel linked plans by status.** `clear_open` and legacy-id `delete_trade` end the linked plan in the same transaction (reason `trade_deleted`), using the mapping `_close_linked_plan_safely` already uses (`performance.py:130-132`):
  - a **PENDING** plan is **cancelled**, with event `cancelled_trade_deleted` added to v187's `PENDING_CANCEL_EVENTS`;
  - an **ACTIVE** or **PARTIAL** plan is **closed** (no P&L is settled: the trade is being deleted, not exited).

  A plan is never left stepping without its trade. The delete confirmation (endpoint response and Discord reply) names every ACTIVE or PARTIAL position it ends. It states that monitoring and stop/TP alerts stop for them, and that any banked TP1 dollars leave the balance with the trade. `cancelled_trade_deleted` reaches the follow-channel cancel notice through `PENDING_CANCEL_EVENTS`, and a test pins that.
- **A1 race.** The "has this plan filled?" check, and the cancel, run inside the same locked transaction as D3.3. A fill recorded by the poll in the meantime is therefore seen, and the trade is then treated as the real position it is.
- **D4 from the audit, NaN quotes.** Every quote guard in `poll()` and `monitor_quotes` / `_price_batch_fn` (`plan_manager.py:1549,1586`) uses `math.isfinite(price) and price > 0`.

### D5 — Partial trades on screen

| # | Change |
|---|---|
| B1 | The trades API row gains **`entry_shares`**, the original position size, before any leg. `shares` keeps its meaning: the remaining shares on an open PARTIAL. `bankedLegAmount` takes `entry_shares`, and so do `trades.ts:425`, `dashboard.ts:382` and `trade-detail.store.ts:425-427`. Its doc comment already says "original". `models.ts` adds the field. |
| B2 | `pnl_calendar` uses `metrics.leg_contribution_r` for a leg part's R (`:191`), so day, month and streak sums (`:326,561,603,651`) add contributions. With the golden trade, TP1 (+2R on 50%) plus a runner (+3R) shows **+2.5R**. A whole single-leg trade is unchanged. Dollar figures were already right. |
| B3 | An open PARTIAL with no live quote returns `r_multiple: null`. **`banked_r` already exists** (`trades.py:317`, `models.ts:120`, `plan-cell.ts`) and keeps its meaning: the TP1 leg's own R (+2R in the golden trade). A new **`banked_contribution_r`** = `Σ leg_contribution_r` over the realized legs (+1.00R) carries the trade-level figure. That avoids a silent change of meaning on a live field. With a quote, `r_multiple` is the blended figure: `banked_contribution_r` + open fraction × (quote − entry) / initial risk per share, signed per direction. At quote 113 that is 1.0 + 0.5 × 2.6 = **2.30R**. The Trades row and Trade detail show the banked part as "banked +1.00R (TP1 +2.00R on 50%)", never as the trade's R. |
| B4 | **Dashboard:** the figure is **relabelled "Risk of loss (to stop)"**. It is never shown as a gauge against `PORTFOLIO_HEAT_CAP_PCT`. Beside it, **"Heat (enforced)"** shows `open_heat`, the figure the scanner gates on, so the admin view never shows headroom the scanner does not grant. Both carry the hint "assumes a fill at the stop; a gap through it loses more". When the heat cap blocks an alert (`scan_run.py:1165-1168`, `item.heat_blocked`), a **new** INFO line `heat blocked (enforced X% + Y% > cap Z%)` names the enforced heat. No such line exists today. **Risk page:** `risk._positions` rows are documented to sum to `open_heat`, and the page's utilisation gauge (`risk.py:341-355`) pairs with it. That invariant and the gauge stay on **enforced heat**. Each row gains a **Risk of loss** column beside its enforced figure. The current "Risk used" on the Dashboard (`dashboard.py:94` `_risk_used`) and the Risk page rows (`risk.py:63`) show **risk of loss**: Σ over **filled** open trades of open shares × the per-trade distance from entry to the current working stop, measured against the loss side (bull: entry − stop; bear: stop − entry) and **floored at 0 per trade**. A PARTIAL at the runner floor, or a break-even stop, contributes 0. This is the risk the partner chose ("current risk to stop"): money below entry that can still be lost. It is **not** the open profit at risk; see B5. PENDING placeholders are excluded (the `held_now` filter). **Display only.** `heat.open_heat` enforcement at `swingbot/core/scanning/analyze.py:252` is unchanged here. |
| B5 | The Trade-detail price tile labels the target it reads: "to T1" before TP1, "to T2" after (`outcome-tiles.ts:84`). The "$ at risk" tile (`trade-detail.store.ts:553`) shows **two labelled figures** so neither reads as the other: **"Risk of loss"** (B4's definition) and **"Open profit to stop"** = open shares × (quote − working stop), signed per direction and floored at 0, shown only with a live quote. For the golden trade at 113 they are $0 and 50 × 6.33 = **$316.67**. |

### D6 — The label change is visible, not a silent step

D2 moves 10-for-2 scaled-out closes toward `win` (2026-10-23 counts), and it is not backfilled. The reported win rate for scaled-out trades will therefore step up at deploy. That is a change of label basis, not an improvement.
- `metrics.LABEL_BASIS_SINCE` records the deploy date, set in the release task.
- The Analytics win-rate tile shows the `scratch` and `unscored` counts beside the rate.
- The tile carries the hint "scaled-out trades are labelled by net R from <date>; earlier ones by TP1 touch".

ExpR is unaffected by labels, so it stays the comparison to quote across the deploy date.

## Testing

- **One golden partial trade, every screen.** 100 shares, f = 0.5, entry 100, stop 95 (1R = 5), TP1 110, TP2 120. Each exit path is a test case:
  - runner stopped at the floor (106.67);
  - runner gapped to an open of 88 (net < 0 → `loss`);
  - time exit at 112;
  - manual close at 115;
  - open with a quote of 113;
  - open with no quote.

  For each case, assert against hand-computed values:
  - the trades API row (`shares`, `entry_shares`, `r_multiple`, `banked_r`, `banked_contribution_r`, `realized_pnl_amount`, `pnl_pct`, status);
  - the calendar day (`net_r`, `net_pnl_amount`, `trade_count`, win rate);
  - the dashboard realized parts and Risk used;
  - the frontend banked amount ($500 for the TP1 leg), via the store and cell specs.

  The fixture is shared by the backend and frontend tests, so the two cannot drift. Its expected values were verified by the quant-engineer panel. 1R = $5/share; each leg is 50 shares; the TP1 leg is +2R, contributing 1.0R and $500:

  | Case | Runner r | Net R | Realized $ | `pnl_pct` | Label |
  |---|---|---|---|---|---|
  | Floor 106.67 | +1.333 | 1.67 | 833.33 | 8.33% | win |
  | Gap to open 88 | −2.4 | −0.20 | −100 | −1.00% | loss |
  | Time exit 112 | +2.4 | 2.20 | 1100 | 11.00% | win |
  | Manual close 115 | +3.0 | 2.50 | 1250 | 12.50% | win |
  | Open, quote 113 | live +2.6 | `r_multiple` 2.30, `banked_contribution_r` 1.00, `banked_r` 2.00 | 500 banked, 650 unrealised | — | open |
  | Open, no quote | — | `r_multiple` null, `banked_contribution_r` 1.00, `banked_r` 2.00 | 500 banked | — | open |

  - **`pnl_pct` basis.** Realized dollars over the entry notional of the **whole** position (100 × 100 = $10,000), which is today's `closed_pnl_pct` basis.
  - **Risk of loss** is $0 in both open cases. **Open profit to stop** at 113 is $316.67.
  - The calendar assertion uses a day holding the golden manual-close trade plus a −1R single-leg loss. The calendar counts **each leg** as a row (the leg-vs-trade unit is the metric spec's question), so the day has 3 rows with a win rate of 66.67%, not a degenerate 0 or 100.
  - **A seventh case** supplies a leg with `r` absent, to exercise `r_multiple`'s derive-from-exit-price branch.
  - **The parity pin.** The gap case's backtest label (`exit_sim_v2`) is asserted to stay `win`.
- **D2.** A label table over net R of +0.02, +0.005, 0, −0.005 and −0.02, across all three close paths. A missing risk basis falls back to today's rule with a warning.
- **D3.**
  - A failing `append_leg_by_plan` rolls back the TP1 transition.
  - A rolled-back close writes no `balance_history` point.
  - The snapshot rebuilt after a close includes it.
  - Two connections race an admin close against a bot `store.update`: the plan ends `CLOSED`, and the abort is logged. The race is run twice: once with a status-changing bot write, and once with a write that changes no status (stop ratchet, `first_seen_price`).
  - An aborted write emits no events and no Discord notice.
  - The balance point written inside the transaction equals today's arithmetic (no double count).
  - A lock wait past `lock_timeout` aborts the step cleanly.
  - A6: the archive file holds every deleted row. History is reseeded with one point at `base_balance`. A failed archive write leaves everything untouched. The restore script round-trips the archive, and refuses after a later reset.
  - A7: PENDING → `cancelled_trade_deleted` (placeholder discarded); ACTIVE/PARTIAL → closed with no P&L settled.
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

Pooled win rate and ExpR computed over history before this spec's deploy carry these. **Owner of the backfill decision: the metric-definitions spec (third audit spec).** It changes how win rate and ExpR are pooled anyway, so it must either backfill these 23 records through a data migration (`schema-evolution.md`: no read-time upcasting) or state in its header why the mixed labelling is acceptable.

## Not in this spec

- **Heat enforcement on current risk.** The partner chose current risk to stop as the heat definition. Making `open_heat` *enforce* it frees heat budget as trades de-risk. That changes how many alerts are sized: `Edge: volume`, measured in walk-forward (`backtest_wf.py` models the heat cap) before shipping. It gets its own spec. This spec changes only the display (B4).
- **Metric definitions.** The leg-vs-trade counting unit, the day definition, the ledger, the snapshot, the drawdown order, and the live/backtest parity items go to the metric spec.
- **Frontend hygiene** goes to the frontend spec.

## Corrections from the code brief (2026-10-23)

The plan brief (`.superpowers/briefs/2026-10-23-v189-book-integrity-partial-truth.md`) checked every claim above against the code. Where this section and an earlier one differ, **this section wins**.

1. **`check_bar` has no production caller.** Only `poll` is live. D3's `check_bar` write sites and its exit-retry path are implemented only as far as shared helpers make them correct for free. They get no dedicated tests, and `known-traps.md` records that `check_bar` is test-only.
2. **The Dashboard win rate counts legs.** It uses `performance._leg_status` per leg, so D2's trade-level status moves Analytics, `get_stats`, the journal and the retrospective only. Whether the Dashboard counts legs or trades is the metric spec's counting-unit question, and v189 does not change it.
3. **Calendar leg parts carry no fraction.** `expand_trade_legs` emits rows with `legs: None`. B2 adds `fraction` to each leg part it emits, so `leg_contribution_r` can read it.
4. **Transactions today.**
   - `_settle_account_balance` and `apply_realized_pnl` take no `conn=` and commit separately.
   - `_after_close` and `_refresh_snapshot_safely` run inside `close_plan_trade`, before commit.
   - `TradeLog` reads use their own connection.

   Every new `conn=` parameter defaults to `None` (today's behaviour), so existing tests that monkeypatch `_all`, `_db_upsert(conn=None)` and `_settle_account_balance(self, trade)` keep working. The D3.2 paths pass a connection explicitly.
5. **Every write goes through `PlanStore.update`.** `plan_manager.py` has **28** `store.update` sites (brief §4), including notice, outlook, structure, pyramid and ack writers. D3.3's lock, terminal guard and tighter-stop merge live **inside `PlanStore.update`**, so all 28 are covered without editing each one. `tighter_stop` lives at `exit_sim.py:357`.
6. **Deleting terminal plans cascades.** The foreign keys delete the plans' `starred_plans`, `plan_followers` and `plan_notifications` rows. The A6 archive includes those rows, and the restore script re-inserts them. `journal_entries` are the partner's notes, so `clear_history` keeps them.
7. **A7 delivery path.** `clear_open` and `delete_trade` are `TradeLog` methods with no `PlanManager` involved, so they emit no `PlanEvent`. They end the linked plan through the same helper the admin cancel uses, and queue the follow notice through `_queue_notify`. A test pins that the notice is queued for both the PENDING (`cancelled_trade_deleted`) and the ACTIVE/PARTIAL case.
8. **Complexity.** Several functions this spec touches are baselined at or above 15 and may only shrink: `_on_event` 15, `poll` 20, `_step_active` 21, `_row_from_plan` 15, `list_trades` 34, `_sync_run_scan` 96. `closed_r_multiple` sits at 14. The A1 reversal block moves out of `_sync_run_scan` into a named helper. `closed_r_multiple` is reduced to a call to `metrics._blended_r_raw` (D1).
9. **Archives stay out of git.** `data/archives/` is not git-ignored today and will hold account data. It is added to `.gitignore` in the same commit that first writes it. `./data` is mounted at `/app/data` in both containers. `restore_account_reset.py` follows the `scripts/ops/` convention: a dry run by default, `--apply` to write, tested under `tests/scripts/`. The restore paragraph goes at the end of `## PostgreSQL (the only store)` in `docs/deploy/DEPLOY_HETZNER.md`.
10. **Frontend.** `entry_shares` and `banked_contribution_r` are optional in `models.ts`, because nine spec files build full `TradeRow` literals. The golden fixture is one JSON file read by both pytest and Vitest, in the `tests/charts/resolved_tokens.json` pattern (`ui/testing/resolve-token.ts`).
11. **Order.** Implementation starts after v187 merges. Both plans edit `plan_manager.py`, `commands/trades.py`, `planning/account.py`, the five event-vocabulary files, and the command-gate tests.

## Panel review

Run 2026-10-23, serially: staff-engineer (opus), quant-engineer (sonnet), risk-manager (sonnet).

**BLOCKING**
- staff-engineer: the row-lock guard only covered status-changing writes. Whole-document upserts (ratchet, giveback, `first_seen_price`) could still revive a closed plan. Applied: every `PlanStore.update` is locked and refuses a stale overwrite of a terminal row (D3.3).
- staff-engineer: moving the balance write after commit would double-count, because `apply_realized_pnl` relies on the trade being unsaved, and a crash would leave a missing history point. Applied: the balance write stays in the transaction; only the journal and snapshot run after commit (D3.2).
- staff-engineer: the full reset permanently deleted `account_balance_history` with no rollback and no reseed. Applied: archive first (the reset aborts if archiving fails), then reseed at `base_balance`, with a restore script and deploy-doc paragraph (D4 A6).
- risk-manager: a stale non-terminal write could loosen a freshly ratcheted stop. Applied: the locked update keeps the tighter of the stored and incoming stops, with a race test (D3.3).

**ADVISORY**
- staff-engineer: the TP1/fill write sites were misnamed, and the retry claim was false. Applied: real sites named, `conn=` added, and the lost-touch case stated as accepted with an ERROR log (D3.1).
- staff-engineer: how an abort reaches callers. Applied: `update` returns False, and the step emits no events and no notice.
- staff-engineer: deadlock risk from threading locks plus no `lock_timeout`. Applied: lock order, timeouts, `ORDER BY plan_id`, and network calls before the lock.
- staff-engineer: the admin `_close_plan` can't be one transaction as written. Applied: `close_trade_manual` and `_close_linked_plan_safely` take `conn=`.
- staff-engineer: undeclared v187 dependency, and vague A7. Applied: a **Depends on** line, and a status-by-status mapping.
- staff-engineer: the reset left closed plans behind. Applied: terminal plans are archived and deleted too.
- staff-engineer: the backfill had no owner. Applied: the metric-definitions spec owns it.
- quant-engineer: live vs backtest labels diverge. Applied: D2 is live-only and the divergence is stated and pinned by a test. Changing `exit_sim_v2` would reach the closed acceptance gates.
- quant-engineer: no shared tolerance constant. Applied: `SCRATCH_EPS_R`, live-only. The backtest constant is handed to the metric spec.
- quant-engineer: rounding quantised the threshold. Applied: the comparison uses the unrounded blend.
- quant-engineer: NaN fell into the scratch band. Applied: `unscored` plus a warning.
- quant-engineer: the fallback to the old rule. Applied: `closed`/`unscored` instead.
- quant-engineer: the claim that a manual close is never negative. Applied: reworded.
- quant-engineer: the scope of single-leg trades. Applied: only closes with two or more legs are relabelled.
- quant-engineer: "current risk" read as give-back. Applied: two labelled figures, **Risk of loss** and **Open profit to stop**.
- quant-engineer: B3 formula unstated. Applied: the formula, and 2.30R at 113.
- quant-engineer: `pnl_pct` basis, a degenerate win rate, and a missing-r case. Applied: whole-position notional basis, a two-trade day, and a seventh case.
- quant-engineer: the Why example didn't match the golden trade. Applied.
- risk-manager: stop exits lost on rollback flatter the book. Applied: exits retry at once with the same observed price, then ERROR plus an ops notice.
- risk-manager: the reset silently clears the kill switch and raises size. Applied: the confirmation states the throttle state and sizing effect, and the reset is refused while the kill switch is tripped unless forced.
- risk-manager: "Risk used" would show headroom the scanner denies. Applied: relabelled "Risk of loss (to stop)", shown beside "Heat (enforced)", no gauge, and the rejection log names the enforced heat.
- risk-manager: gap risk is not shown. Applied: a hint on both figures.
- risk-manager: the win rate steps up at deploy. Applied: D6 adds the label-basis date and the scratch/unscored counts.
- risk-manager: deleting ends monitoring silently. Applied: the confirmation names the positions and states the effects. The cancel notice is test-pinned.
- risk-manager: A1 fill race. Applied: the fill check runs in the locked transaction.
- risk-manager: one stuck lock stalls the poll. Applied: a 1s skip-and-requeue on the bot path, with stop-bearing plans first.

## Panel review (pre-close-out, 2026-10-30)

staff-engineer, quant-engineer and risk-manager reviewed the merged diff (`1dce1450^1...1dce1450^2`): no BLOCKING finding. Every ADVISORY is carried forward, none applied in v189.

- staff-engineer: pre-action "Clear open positions" dialog is generic; the ended positions are named in the notice and Discord reply (spec met) -- rejected: not a breach, UX follow-up.
- staff-engineer: reset archives under `data/archives/` are outside `pg_dump` and `/backup-pull`, have no owner and no retention rule -- carried forward.
- staff-engineer: the reset's EXCLUSIVE lock on plans/trades/balance history lasts through the archive write and read-back, stalling scans and alert issuance; not written in known-traps -- carried forward.
- quant-engineer: `LABEL_BASIS_SINCE` is the merge date (2026-10-30), the deploy follows; amend in the deploy commit if it slips -- carried forward.
- quant-engineer: `r_multiple` rounds to 2 dp only for legged trades; no finite check on the expectancy path (NaN leg R makes the mean NaN); `_close_runner` stores 0.0 runner R for malformed risk; `closed_r_multiple` now yields an R for a zero exit price/entry -- carried forward.
- quant-engineer: live and backtest win rates are on different bases from the label date; ExpR unaffected -- carried forward to the metric-definitions spec.
- risk-manager: a reset restarts the drawdown ladder and loss-streak damper (accepted by the spec); the confirmation and the restore dry run should name the throttle/drawdown state they lift or bring back -- carried forward.
- risk-manager: dashboard `_risk_figures` swallows failures silently instead of `swallowed()`; `position_risk_of_loss` prices a trade whose `plan_id` has no plan row as held -- carried forward.
- risk-manager (unverified): check that a PARTIAL runner open across a reset keeps its TP1 leg rows -- carried forward, to verify.
