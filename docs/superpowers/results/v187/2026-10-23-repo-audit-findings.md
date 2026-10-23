# Repo-wide audit — 2026-10-23

Read-only audit by four parallel auditors (partial-trade data path; dashboard/analytics/calendar/risk aggregates; backend correctness and smells; frontend contract, stores and formatting), with the highest-severity claims re-verified by reading code. Nothing was changed in this audit.

**✔** means re-verified by the controller from the code. Every other finding was traced by the auditor that reported it and has not been re-checked by a second reader, so re-read the cited lines before building on it. Line numbers are as of `ef2c5b69`.

The findings are split across four specs, written in this order. The partner chose the order in the 2026-10-23 brainstorm.

| Spec | Scope | Status |
|---|---|---|
| **v187** safety hardening | D below | spec written, panel-reviewed |
| next: book integrity + partial-trade truth | A, B, F1 | not yet written |
| next: one metric definition | C, plus the parity items v187 hands over | not yet written; needs partner decisions (counting unit, day definition) |
| next: frontend hygiene | E | not yet written |
| optional | F2–F3 | not yet written |

## A. Book integrity: the stored record is wrong (also distorts measured ExpR)

A1. **A reversal can settle P&L on a PENDING plan's placeholder trade.** `scan_run.py:907-935` uses `open_trade_for_ticker`, which includes the stop-entry placeholder. Then `close_trade_reversed` (`performance.py:1308`) books `shares × (live − trigger)` into the balance before `_close_linked_plan_safely` cancels the plan. The result is P&L for a position that never existed.
A2. **A manual close of a PARTIAL writes no runner leg to `plan.legs_realized`.** `_close_plan` (`trade_commands.py:143-173`) writes the leg only to the trade's `legs` (via `_apply_exit_price`). Effects:
   - The Trades table (`_expand_plan_row`, `trades.py:557`) shows "leg 1 of 1".
   - The Calendar and Dashboard read the trade's `legs` and show 2.
   - Trade detail prefers `legs_realized` (`trade-detail.store.ts:394`), so its average exit is TP1-only while its result R includes the runner.
A3. **The outcome label on runner closes is wrong in two cases:**
   - `_close_runner` sets `"win"` for any `tp1_*` reason (`plan_manager.py:1266`), even when the net is negative. Example: a gap through the floor fills at the open (`:1486`), giving f=0.5, r1=+1, runner −1.4R, net −0.2R, recorded as a win.
   - A PARTIAL closed by time exit (`:1360`) or manually gets `"closed"`, so `win_rate` drops it even when TP1 was banked.
A4. **The TP1 leg and the fill record are written outside the terminal transaction.**
   - In `_on_event` (`plan_manager.py:729`), `append_leg_by_plan` and `record_plan_fill` run after the plan is saved, and any failure is only logged as a warning. A missed TP1 leg means `settle_legs` prices only the runner, so $ and R are understated for good.
   - Close hooks (`_settle_account_balance` → `balance_history`, `_after_close`, `_refresh_snapshot_safely`) run inside the transaction but before the commit (`_persist_terminal`, `:807`). The snapshot therefore misses the close, and a rollback leaves a stray `balance_history` point.
A5. **The daily recap's R ignores legs.** `tracking/retrospective.py:188 _r_multiple` uses the final `exit_price` only, and feeds `:329,524,620,972,983`. Example: TP1 at +1R with a runner at +0.67R shows as 0.67R.
A6. **Clearing trade history lowers the balance.** The balance is `base + Σ realized` over the trades table (`account.py:138`), while `balance_history` keeps the old peak. The next close then writes a fake drawdown that `throttle.drawdown_pct` reads.
A7. **`clear_open` and legacy-id `delete_trade` remove plan-linked trades but leave their plans open** (`performance.py:1531`, `trade_commands.py:262,271`).
A8. **No locking between the bot and admin processes.** `_LOCK` (`performance.py:39`, `plan_store.py`) is a `threading.Lock`, and `PlanStore.update` is last-writer-wins. An admin close can be overwritten by the bot's next `store.update`, which brings the plan back as PARTIAL.

## B. Partial trades on screen

B1. ✔ **Banked TP1 dollars are shrunk by (1−f).**
   - `_strip_internal_fields` (`trades.py:1229-1231`) replaces the public `shares` with `open_shares` on PARTIAL rows.
   - `bankedLegAmount` (`plan-cell.ts:358`, whose comment says it expects the ORIGINAL count) multiplies that by `fraction` again, and is called from `trades.ts:425` and `dashboard.ts:382`. `trade-detail.store.ts:425-427` does the same.
   - Example: 100 sh, f=0.5, +10/sh truly banks $500 but shows $250.
B2. ✔ **Calendar net R sums leg Rs unweighted.** `pnl_calendar.py:191` gives each leg its own full R, and `:326` (also `:561,603,651`) sums them. Example: TP1 +1R at 50% plus a runner at +3R shows **+4R** instead of +2R.
B3. **With no live quote, an open PARTIAL shows its banked R as its R.** `_row_from_plan` sets `r_multiple = closed_r(t)` (`trades.py:329`), and only `_attach_unrealized_pnl` overwrites it.
B4. **"Risk used" and Risk heat count a PARTIAL at its full original risk** (`dashboard.py:94`, `risk.py:63`, `heat.trade_risk_pct` prefers the stamped `risk_pct`), and include PENDING placeholders.
B5. **Trade detail:**
    - The price tile says "to T1" but reads `t.target`, which is TP2 by then (`outcome-tiles.ts:84`).
    - `dollarAtRisk` (`trade-detail.store.ts:553`) uses the original per-share risk after the stop has moved up.

Checked and correct: open shares, live unrealized $ on the runner, closed whole-trade % and R, `settle_legs` $, leg rows for automated closes, calendar and equity dollars, stop/target fields on a PARTIAL, the Partials analytics tab, and model field names.

## C. Metric definitions disagree across screens

C1. **Counting unit.** The Dashboard counts each leg as a trade (`dashboard.py:217`, deliberate since v79). Analytics counts whole trades (`analytics.py:173`). In the same book, ExpR can flip sign between the two.
C2. **Three definitions of a day.** The Dashboard 1D uses the Berlin day (`dashboard.py:222` → `is_today_berlin`). The ranges and the chart use the New York day (`equity-range.model.ts:343`). The Calendar and Analytics use the UTC date slice (`pnl_calendar.day_of`, `metrics.in_date_range`). The Calendar's "today" uses the browser-local date (`calendar.ts:502`).
C3. **The Calendar and the headline balance include the weak ledger** (`pnl_calendar.load_rows`, `account._sum_realized_pnl` at `account.py:72`), which breaks v93. The curves and Analytics are main-only.
C4. ✔ **Snapshot loaders return empty data on a stale snapshot.** The pattern is `load_snapshot(3600) or refresh_snapshot()`, and `refresh_snapshot()` returns `None`. It appears at `api_v1/dashboard.py:54`, `api_v1/analytics.py:43` and `admin/queries.py:209`.
C5. **"x% today" is not today's change.** It is first-to-last over the last 30 points of a per-close equity curve, labelled "today" (`portfolio-value.ts:32`, `trading-performance.ts`).
C6. ✔ **Risk max-drawdown-R is computed in the wrong order.** `r_multiples(closed)` comes back newest-opened first (`repositories/trades.py:20`). `max_drawdown_r` (`risk_metrics.py:174`) starts its peak at the first value, not 0. The money drawdown in `overview.ts:58` makes the same peak-start error.
C7. **Analytics Overview Wins/Losses don't match the Win-rate tile.** They come from unscoped, leg-expanded `get_stats`, with `losses = closed − wins` (`performance.py:1128`). `avg_holding_days` ignores the ledger. The `by_confidence` denominator includes "closed".
C8. **Smaller items:**
    - The open P&L % is an unweighted mean (`dashboard.py:302`).
    - `holding_period_split` buckets are inclusive at both ends.
    - The Calendar winner/loser counts use the sign of R while its win rate uses the outcome.
    - `dashboard.py:323` computes stats and drops them.
    - `ExposureByHorizon` is dead code.
C9. **Live/backtest parity items handed over by v187:**
    - Pending invalidation fires on every tick live, but on the close in the backtest (`lifecycle.py:144`).
    - The limit risk-cap cancel exists live only.
    - A gap-through-stop is a 0R scratch in the backtest but no trade live.
    - Polling granularity makes live limit fill rates differ.

## D. Safety → v187

D1. ✔ The Discord commands that change state have no permission check.
D2. ✔ The 2% cap is not enforced in `risk_pct` mode, and the setters don't validate.
D3. Live limit entries fill as if they were stop entries (latent: limit strategies are masked).
D4. NaN quotes can pass the `if not price` guards (`plan_manager.py:1549,1586`). This is suspected and not traced; it goes to the integrity spec.

## E. Frontend

E1. ✔ Watchlist autocomplete dies after one error. `watchlist.store.ts:138` has no `catchError` inside the `switchMap`.
E2. **Duplicate and out-of-order requests:**
    - The Dashboard fetches 2–3× per visit: the resolver plus the `onInit` load (`dashboard.routes.ts:16`, `dashboard.store.ts:435`).
    - `trades.store.ts:146` `resolve()` has no `latestRequest` guard, so an older response can overwrite a newer filter.
E3. **Formatters** (`ui/format.ts:12-71`) print `NaN`, `∞%`, `-0.00%`, and use a mix of ASCII and U+2212 minus signs.
E4. **Date-only strings shift a day west of UTC.** `format.ts:140` does `new Date("YYYY-MM-DD")`. Callers: `watchlist.ts:149` (earnings) and `analytics.columns.ts:92,228`.
E5. **`EquityCandlesStore` (root) keeps refetching** on scan events after the Dashboard has been left (`equity-candles.store.ts:183`).
E6. **Gates table on phones:** an 11-column raw table under `overflow:hidden` (`reports/gates-tab.ts:88`); `attribution-tab.ts:77,128` has the same problem. `watchlist-panel.ts` links are about 4px tap targets.
E7. **Contract drift:**
    - `realized_weak` is missing from `Dashboard` in `models.ts`.
    - `default_expiry_bars` is unused.
    - The `TradeQuery.tier` filter is retired.
E8. **Smells:**
    - 11 dead `dashboard.store` fields.
    - Components inject `ApiClient` directly (`dashboard.ts:826`, `row-actions.ts:105`, `trades.ts:1142`, `trade-detail.ts:845`, `shell.ts:325`).
    - Duplicated `formatR`, `sign()` and percent helpers.
    - About 75 raw `toFixed` calls.

The v186 working tree, uncommitted at audit time and owned by another session:
- `realized-pnl.ts:88-89` declares `about` twice, which does not compile.
- `panel-help.ts` calls 1D "the New York day" (it is Berlin).
- `avgConfidence` help says "selected period" (it is open positions, unscoped).
- `todayRealized` can go stale or be overwritten.
- The 'currency' literal is `€`.
- There is spinner noise for screen readers.

## F. Smells

F1. **The R/P&L formula is written out about 72 times in the backend,** under three named variants: `metrics.r_multiple`, `performance.closed_r_multiple` and `retrospective._r_multiple`. A5 is the drift this caused.
F2. **Each 60s `poll()` decodes the full tables several times.** `PlanStore.get/update/open_plans` each call `list_all()`, and `TradeLog._all()` reads the whole trades table per lookup.
F3. **Complexity hotspots:** `trade_chart.generate_trade_chart` (191), `retrospective.build_daily_retrospective` (106), `scan_run._sync_run_scan` (96). The largest modules are `performance.py` (1787 lines) and `plan_manager.py` (1703 lines).
