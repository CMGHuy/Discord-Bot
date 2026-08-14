# Jinja → SPA parity audit, group 1: Dashboard and Plans

Task SR41 of `2026-08-13-v21-spa-refresh.md`. Templates audited:
`dashboard.html`, `dashboard_fragment.html`, `plans.html`, `_plans_board.html`,
together with the routes that build their context (`swingbot/admin/dashboard.py`,
`swingbot/admin/pages.py:_plan_rows`/`plans_page`/`plans_fragment`).

Three statuses only — `migrated`, `dropped on purpose`, `missing`. Nothing is
left unclassified. Ranking of the `missing` rows is SR46's job, not this file's.

**Scope note.** `_trade_history_rows.html`, which `dashboard.html` includes for
Trade History's first paint, belongs to SR42. Only Trade History's *chrome*
(toolbar, headers, pager, bulk actions) is audited here; its row content is
SR42's.

---

## `dashboard.html` — the page shell

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Dashboard mode toggle: Today + Open / Today only / All days | `dashboard.html:14-22`, scoping in `dashboard.py:scoped_trades` | **missing** | — no date-scope control anywhere in the SPA; the Dashboard endpoint has no `mode` parameter |
| Auto-refresh checkbox, "every Ns" | `dashboard.html:23-25` | dropped on purpose | Spec 3: SSE push replaces polling, so there is no interval to switch off. `EventStream` + `ConnectionStatus` in the shell |
| "Refresh now" button | `dashboard.html:26` | dropped on purpose | Same decision — with push there is nothing to hurry |
| Refresh status text | `dashboard.html:27` | migrated | `sb-connection-status` in `shell/shell.html:76` |
| Bot liveness dot + label | `dashboard.html:30-34` | migrated | `sb-connection-status [botAlive]`; also `Bot alive / Bot not reporting` in `system/scan-tab.ts:39` |
| Scan-paused badge | `dashboard.html:37` | migrated | `system/scan-tab.ts:36` — `Automatic scanning paused` |
| Pause / resume scanning | `dashboard.html:40-42` | migrated | `system/scan-tab.ts:70-90`, one control in two states |
| "Run !check now" trigger | `dashboard.html:43-47` | migrated | `system/scan-tab.ts:49-57` — `Scan now` |
| Stop scan (enabled only while running) | `dashboard.html:48-54` | migrated | `system/scan-tab.ts:58-67`, `[disabled]="!store.scanRunning()"` |
| Trigger status text | `dashboard.html:55` | migrated | `store.scanMessage()` rendered verbatim, `scan-tab.ts:93-98` |
| Export CSV | `dashboard.html:56` | migrated | `trades/trades.ts:104-110`, `store.exportUrl()` |
| "What appears here" explainer banner | `dashboard.html:60-68` | **missing** | — no equivalent copy in any workspace |
| Trade History card title + closed-trade count | `dashboard.html:74-80` | migrated | Trades table pagination total, `data-table` |
| "closed today" qualifier on the count | `dashboard.html:78` | **missing** | — consequence of the mode toggle being absent |
| Filter: outcome (WIN/LOSS/CLOSED) | `dashboard.html:84-90` | migrated | Status chips `win` / `loss`, `trades.columns.ts:155-156` (they drive `outcome`, not `status`) |
| Filter: ticker (dropdown of every ticker in history) | `dashboard.html:91-97`, options from `dashboard.py:build_filter_options` | migrated | Free-text Ticker input, `trades.ts:166-172`. Enumerated options became a text field |
| Filter: strategy | `dashboard.html:98-104` | **missing** | — `strategy` is in the API's `FILTERS` set (`api_v1/trades.py:59`) but no control sends it |
| Filter: horizon | `dashboard.html:105-111` | **missing** | — likewise in `FILTERS`, no control |
| Filter: direction | `dashboard.html:112-117` | migrated | Direction select, `trades.ts:173-179` |
| Filter: confidence Lv1-5 | `dashboard.html:118-123` | **missing** | — no confidence control; the column shows the level but cannot filter by it |
| Reset filters | `dashboard.html:124-125` | migrated | `sb-filter-bar (cleared)`, `trades.ts:165` |
| Density toggle (compact / full) | `dashboard.html:127-130` | migrated | `trades.ts:117-136`, per-table density in `ui/table-prefs.ts` |
| Per-page selector 10/25/50/All | `dashboard.html:131-141` | migrated | `[showPerPage]="true"`, `trades.ts:208-209` (SR15) |
| Row-number `#` column | `dashboard.html:149` | dropped on purpose | SR16 replaced the ordinal with the trade's short id as a link (`trades.ts:214-216`) — an ordinal is meaningless once sort and page move |
| Sortable headers with sort arrows | `dashboard.html:150-163` | migrated | `data-table` `sortable` columns; server-side sort via `store.sort()` |
| Pagination bar (prev / page x of y / next / info) | `dashboard.html:177-183` | migrated | `sb-pagination` inside `data-table` |
| "Clear all history" bulk action | `dashboard.html:188-191` | migrated | `trades.ts:114-116` + its own confirm dialog |
| Empty state: "No closed trades yet…" | `dashboard.html:195-197` | migrated | `data-table` `emptyState`, `trades.ts:202` |
| Chart preview modal on row click | `dashboard.html:201-207` | migrated | Row click opens the detail view, whose Chart tab is the Phase 3 chart (`trades/trade-detail.ts`) — a tab rather than a modal |

---

## `dashboard_fragment.html` — the polled panels

### Session banner and lifecycle strip

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Session banner: UTC clock + market-session pills | `dashboard_fragment.html:16-19` (filled client-side) | **missing** | — `SessionStore` in the SPA is the *auth* session; there is no market-session indicator anywhere |
| Lifecycle strip: five counts (PENDING / ACTIVE / PARTIAL / CLOSED today / CANCELLED today) | `dashboard_fragment.html:22-30`, counts from `pages.py:_plan_rows()["counts"]` | **missing** | — the status chips exist as filters but carry no counts, and the Dashboard endpoint returns none |
| Each lifecycle card links to the filtered board | `dashboard_fragment.html:25` | migrated | Status chips navigate `/trades?status=…`, `trades.columns.ts:148-159` |

### Stat cards

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Account balance + today's % change | `dashboard_fragment.html:34-38`, `get_daily_summary()` | migrated | `sb-metric-card label="Account balance"`, `dashboard.ts:106-110` |
| Today's wins/losses amounts and closed count under the balance | `dashboard_fragment.html:47-52` | **missing** | — the card has no sub-line; the figures come from `get_daily_summary()` and the `/dashboard` endpoint does not return them |
| Equity (30d) change % + sparkline | `dashboard_fragment.html:59-65`, `dashboard.py:build_equity_curve` | migrated | The equity chip, `dashboard.ts:141-145`, `store.equityPoints()` / `equityChangePct()` |
| Position premium per trade, both sizing modes | `dashboard_fragment.html:67-89`, `dashboard.py:build_sizing_note` | migrated | `sb-metric-chip label="Position premium"` + `premiumUnit()` saying "max" in risk-% mode, `dashboard.ts:147-152, 450-452` |
| The premium card's worked-out explanation (risk amount, caps, absolute cap, `!account sizing` hint) | `dashboard_fragment.html:81-87` | **missing** | — the chip carries the number and the "max" qualifier, none of the reasoning |
| Open trades count | `dashboard_fragment.html:91-95` | migrated | `sb-metric-chip label="Open trades"`, `dashboard.ts:127` |
| Wins | `dashboard_fragment.html:97-101` | migrated | Analytics — the `relocated` group, `analytics.store.ts` (`wins`) |
| Losses | `dashboard_fragment.html:103-107` | migrated | Analytics `relocated` group (`losses`) |
| Win rate | `dashboard_fragment.html:109-115` | migrated | `sb-metric-chip label="Win rate"`, `dashboard.ts:131` |
| Expectancy (avg R) | `dashboard_fragment.html:117-123` | migrated | `sb-metric-chip label="Expectancy"`, `dashboard.ts:134` |
| Open P&L % | `dashboard_fragment.html:125-131` | migrated | `sb-metric-card label="Open P&L"`, `dashboard.ts:111-116` |
| Avg realized P&L % | `dashboard_fragment.html:136-142` | migrated | Analytics `relocated` group (`avg_realized_pct`) |
| Best trade | `dashboard_fragment.html:144-150` | migrated | Analytics (`best_trade_pct`) |
| Worst trade | `dashboard_fragment.html:152-158` | migrated | Analytics (`worst_trade_pct`) |
| Avg open confidence | `dashboard_fragment.html:160-166` | migrated | `sb-metric-chip label="Avg confidence"`, `dashboard.ts:130` |
| Avg holding period | `dashboard_fragment.html:168-174` | migrated | Analytics (`avg_holding_days`, labelled "Avg holding") |
| Risk used vs cap | — (not on the Jinja dashboard) | n/a | New in the SPA (`dashboard.ts:117-123`); recorded so the count of cards is not read as a loss |
| Fourteen equal-weight cards | whole `stat-row` | dropped on purpose | Design-system Decision 2 / spec v14 Decision 5: three cards + six chips, hierarchy by size. Re-adding a card here is a design change |

### Open trades table

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Open-trade count in the card title | `dashboard_fragment.html:180-184` | migrated | `allLinkLabel()` — "All N open →", `dashboard.ts:420-423` |
| Free-text filter by ticker **or strategy** | `dashboard_fragment.html:186-188` | migrated (narrowed) | Ticker input in Trades, `trades.ts:166-172`. The strategy half has no control — see the strategy-filter row above |
| Density toggle | `dashboard_fragment.html:189-192` | migrated | `dashboard.ts:377-385`, own table id, own preference |
| Per-page selector | `dashboard_fragment.html:193-203` | dropped on purpose | The Dashboard panel is capped at six (`OPEN_POSITIONS_CAP`) and deliberately has no pager — paging a summary is the Trades workspace in disguise. Per-page lives in Trades |
| Status cell: dot, SL→TP bar, entry tick, progress % | `dashboard_fragment.html:252-280`, `dashboard.py:build_open_trade_views`/`pos_color` | migrated | `ui/status-cell.ts`, server-driven via `progress_pct` / `entry_pct` / `progress_band` / `blink_seconds` (SR7) |
| Ticker cell → trade detail link | `dashboard_fragment.html:283-288` | migrated | `dashboard.ts:201-203`, `trades.ts:214-216` |
| Direction glyph inline on the ticker (compact) | `dashboard_fragment.html:286` | migrated | `sb-direction-arrow` as its own column (SR9) |
| Tier chip | `dashboard_fragment.html:287` | migrated | `tier` column + `sb-quality-chip`, `trades.ts:234-238` |
| VALIDATED/WEAK badge deliberately absent from this table | `dashboard_fragment.html:289-293` | dropped on purpose | Same decision holds: `badge` is in row expansion (`trades.ts:286`) and the detail view, not a list column |
| Strategy column + "Sources: …" tooltip | `dashboard_fragment.html:296-299` | migrated (narrowed) | `strategy` column exists; the target/stop **sources** tooltip does not — sources are `TradeDetailFields`, shown in the detail view |
| Horizon pill + "~N months" tooltip | `dashboard_fragment.html:301-305` | migrated (narrowed) | `horizon` column, raw key only, no expanded label |
| Direction column | `dashboard_fragment.html:307-312` | migrated | `sb-direction-arrow` (SR9) |
| Confidence Lv1-5 badge | `dashboard_fragment.html:314-318` | migrated | `sb-confidence-cell` (SR10) |
| Confidence score /100 with tri-colour band | `dashboard_fragment.html:320-328` | migrated | Folded into `sb-confidence-cell [score]` (SR10) |
| Entry price | `dashboard_fragment.html:330` | migrated | `entry` column |
| Current price, live-blink while market is active | `dashboard_fragment.html:333-343` | migrated (narrowed) | `now` column. The `price-live` blink class and the market-active gate are not reproduced |
| Unrealized P&L % | `dashboard_fragment.html:352-362` | migrated | `pnl_pct` column with `pnlClass` |
| Plan cell (entry → target / stop) for compact density | `dashboard_fragment.html:364-375` | migrated | `sb-plan-cell` (SR8) |
| Stop / Target columns | `dashboard_fragment.html:377-378` | migrated | `stop_loss` / `target`, picker-addable |
| R:R column | `dashboard_fragment.html:379` | migrated | `risk_reward` column |
| Unrealized amount in account currency | `dashboard_fragment.html:388-397` | migrated (narrowed) | `realized_pnl_amount` covers realised; unrealised amount has no column — `position_value` and `shares` are picker-addable and give the inputs |
| Shares-snapshot tooltip, incl. sizing-mode mismatch warning | `dashboard_fragment.html:391` | **missing** | — no equivalent anywhere; `sizing_mode` is a `TradeDetailFields` field with no UI |
| Held / time-open column, amber past 30 days | `dashboard_fragment.html:400-404` | migrated (narrowed) | `held` column via `held(row.held_hours)`; the >30-day amber is not reproduced |
| Opened timestamp (Berlin) | `dashboard_fragment.html:406` | migrated | `opened_at` column, `dateTime()` |
| Row action: open detail in new tab | `dashboard_fragment.html:409-410` | dropped on purpose | The ticker/id cell is a real anchor, so the browser's own "open in new tab" covers it |
| Row action: close trade | `dashboard_fragment.html:411-414` | **missing** | `availableActions()` (`trade-actions.ts:48-58`) switches on `'open'`/`'planned'`/`'pending'`, but `row.status` carries the uppercase plan vocabulary (`api_v1/trades.py:119`, `:159`). `ACTIVE`/`PARTIAL` therefore fall through to `['delete']` and no Close button renders |
| Scale-out leg rows ("↳ runner N%: price (R)") | `dashboard_fragment.html:417-427` | migrated | Detail view — `legs` / `legs_realized` are `TradeDetailFields`; row expansion says so explicitly (`trades.ts:277-283`) |
| Footer note: 15s refresh, sizing risk %, `!account` hint | `dashboard_fragment.html:443-445` | **missing** | — no equivalent line |
| Empty state: "No open trades right now. Run `!check`…" | `dashboard_fragment.html:447-451` | migrated | `emptyState` on the Dashboard panel, `dashboard.ts:307-310` (different copy, same role) |
| "Clear open trades" bulk action | `dashboard_fragment.html:453-461` | migrated | `trades.ts:111-113` + confirm dialog |

---

## `plans.html` + `_plans_board.html` — the plans board

The whole page is `dropped on purpose` **as a page** — spec v14 Decision 4
collapses Plans, Journal and the two dashboard tables into one Trades
workspace, and `trades.columns.ts:148-159` adds the `PENDING` chip precisely so
the board's purpose survives. What follows classifies its *contents*, since
"the page is gone" is not an answer about the features on it.

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Whole page as a separate destination | `plans.html` | dropped on purpose | Spec v14 Decision 4 — Trades is the one entity |
| ETag-polled fragment refresh | `plans.html:5-41` | dropped on purpose | Replaced by SSE push (`api/event-stream.ts`) |
| Lifecycle strip with per-status tooltips | `_plans_board.html:4-21` | **missing** | — same gap as the dashboard strip: no counts, and the tooltip copy has no home |
| Active-filter highlight on the selected card | `_plans_board.html:14` | migrated | `sb-filter-chips [selected]`, `trades.ts:158-163` |
| Section help: the PENDING → … → CLOSED explainer | `_plans_board.html:22-27` | **missing** | — the lifecycle is not explained anywhere in the SPA |
| Filter: status | `_plans_board.html:30-35` | migrated | Status chips |
| Filter: tier A/B/C | `_plans_board.html:36-41` | **missing** | — `tier` *is* in `api_v1/trades.py:FILTERS` (line 60); no control sends it |
| Filter: badge VALIDATED/WEAK | `_plans_board.html:42-46` | **missing** | — `badge` is not in `FILTERS` either, so this one needs a server change as well as a control |
| Filter: ticker | `_plans_board.html:47-48` | migrated | Ticker input |
| Filter submit / clear | `_plans_board.html:49-50` | migrated | Filters navigate on change; `sb-filter-bar (cleared)` clears |
| Plan count in the card title | `_plans_board.html:54-58` | migrated | Pagination total |
| Empty state ("No plans match the current filters") | `_plans_board.html:61-65` | migrated | `data-table` empty state |
| Column: Tier / Badge chips | `_plans_board.html:71, 90-91` | migrated | `tier` column + chip; `badge` in row expansion (`trades.ts:286`) |
| Column: Ticker | `_plans_board.html:72, 93` | migrated | `ticker` column |
| Column: Strategy, linking to the Strategies page anchor | `_plans_board.html:73, 94` | migrated (narrowed) | `strategy` column; the deep link into the strategy's own section is gone |
| Column: Direction | `_plans_board.html:74, 95-99` | migrated | `sb-direction-arrow` |
| Column: Status pill | `_plans_board.html:75, 100` | migrated | `sb-status-cell` / `status_label` |
| Column: Follow score (`analytics.rank.rank_plans`) | `_plans_board.html:76, 101`, `pages.py:_ranked_plan_rows` | **missing** | — `follow_score` appears nowhere in `frontend/src`; the ranking is not on the wire |
| Column: Entry **or trigger** price, with the "(trigger)" marker | `_plans_board.html:77, 102-105` | **missing** | — the list shows `entry`, which is null for a PENDING plan. `trigger_price` is a `TradeDetailFields` field, so the actionable number for an unfilled plan is only in the detail view |
| Column: SL | `_plans_board.html:78, 106` | migrated | `stop_loss` column |
| Column: TP1 | `_plans_board.html:79, 107` | migrated | `target` column |
| Column: TP2 | `_plans_board.html:80, 108` | **missing** | — `target2` is on `TradeRow` (`models.ts:72`) but has no column and no picker entry |
| Column: Age (time since creation) | `_plans_board.html:81, 109` | **missing** | — the table has `opened_at` and `held`, both null for a plan that never filled; `created_at` is detail-only |
| Column: Quality score | `_plans_board.html:82, 110` | migrated | Row expansion, `trades.ts:287` |
| Row click → plan detail | `_plans_board.html:88` | migrated | Row activate → `/trades/:id` |
| Action: cancel a PENDING plan | `_plans_board.html:112-116` | **missing** | Same defect as Close above — `availableActions('PENDING')` falls through to `['delete']` because the function matches lowercase `'pending'` |
| Action: close an ACTIVE/PARTIAL plan | `_plans_board.html:117-121` | **missing** | Same row as the dashboard's Close action; recorded once there |
| Confirm prompt naming the ticker | `_plans_board.html:114, 119` | migrated | `actionConsequence()` names the ticker and what will not come back (`trade-actions.ts:33-44`) |

---

## Tally for this group

| Status | Count |
|---|---|
| migrated (incl. narrowed) | 62 |
| dropped on purpose | 10 |
| **missing** | 21 |
| new in the SPA (not a parity row) | 1 |

The `missing` rows cluster into five themes, which is what SR46 will rank:

1. **Filters with no control** — strategy, horizon, confidence, tier, badge.
   `strategy`, `horizon` and `tier` are already accepted by
   `api_v1/trades.py:FILTERS`, so those three are client-only work. `badge` and
   `confidence` need the server side too.
2. **Plan-shaped columns** — follow score, entry-or-trigger, TP2, age. These are
   what made the plans board readable for plans that have not filled.
3. **Row actions that silently do not render** — Close and Cancel, from the
   case mismatch in `availableActions()`. This one is a defect, not a
   deliberate narrowing, and it is the only row here that removes a capability
   the user had rather than relocating it.
4. **Date scoping** — the mode toggle and everything phrased against it.
5. **Explanatory copy** — the "what appears here" banner, the lifecycle
   explainer, the premium reasoning, the sizing-mode mismatch warning, the
   footer note, the session banner.
