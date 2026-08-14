# Jinja → SPA feature parity: the gap table

Task SR46 of `2026-08-13-v21-spa-refresh.md`. This file **supersedes and
replaces** the five per-group audits SR41–SR45 produced
(`2026-08-13-parity-1-dashboard.md` … `-5-system.md`), which were deleted in
the same commit: a stale duplicate of a gap table is worse than no gap table.

## What was audited

Every Jinja template under `swingbot/admin/templates/`, together with the route
or view-model builder that fills it — `app.py`, `pages.py`, `dashboard.py`,
`api_v1/`. A number computed server-side and merely interpolated by the
template counts as a feature.

Each control, column, tooltip, chart, computed number and empty state is one
row, classified `migrated`, `dropped on purpose`, or `missing`. **Nothing is
unclassified.** Where a feature moved workspace, it is `migrated` — the audit
checked `frontend/src` before writing `missing` in every case.

Six rows appeared in two group files because the same feature is reachable from
two templates (the Close/Cancel row actions, the scale-out legs, the trigger
price, the strategy filter). They are merged here, with both Jinja locations
named on the surviving row.

## Counts

| Status | Rows |
|---|---|
| migrated (including narrowed) | 256 |
| dropped on purpose | 33 |
| **missing** | **121** |
| *(total classified)* | *410* |
| new in the SPA — recorded, not a parity row | 14 |

## The ranking

The `missing` rows split two ways, per SR46 step 3:

| Rank | Rows | Meaning |
|---|---|---|
| **blocks NG57** | 88 | A real capability with no equivalent anywhere in the SPA |
| cosmetic | 33 | A tooltip, a label, or a sentence of explanatory copy |

88 is not 88 tasks. The blocking rows are heavily coupled, and SR47 grouped
them as follows — the count in brackets is how many rows each group absorbs,
and each group became one task (SR48–SR58).

*Counts corrected by SR47.* This section first read
[1][11][20][9][7][5][17][7][5][2][4]. Those were estimated per cluster and
happened to sum to 88, which is why the error was not obvious; bucketing all 88
rows one at a time to write the tasks gave the set below. The task numbering
follows these.

1. **The row actions that never render** [1] → SR48 — `availableActions()`
   (`trade-actions.ts:48-58`) matches `'open'` / `'planned'` / `'pending'`, but
   the collection endpoint always emits the uppercase plan vocabulary
   (`api_v1/trades.py:119`, `:159`). Every row therefore offers only Delete.
   **This is a defect, not a narrowing** — it is the one gap that removed a
   capability rather than relocating it, it affects both the list and the
   detail view, and it is a one-line fix.
2. **Fetched but never rendered** [9] → SR49 — `explanation`, `confirmed_by`,
   `target_sources` / `stop_sources`, `confidence_breakdown`,
   `quality_breakdown`, `status_history`, `legs`, `trigger_price`,
   `breakeven_trigger_fraction`. All are typed on `TradeDetailFields`
   (`models.ts:101-139`) and each appears exactly once in `frontend/src` — in
   `models.ts` itself. Views only. (`tp1_fraction` and `created_at` are the same
   kind of gap but were bucketed elsewhere: the first with the Target 1 label
   it qualifies, the second with the Age column that needs it — SR53.)
3. **The analytics snapshot, unread** [17] → SR50 — `GET /analytics/snapshot`
   forwards `profit_factor`, `sharpe`, `sortino`, `max_drawdown_pct`,
   `streaks`, `equity_curve`, `drawdown`, `r_multiples` and a `by` block over
   ten dimensions (`core/analytics/snapshots.py:37-66`).
   `ApiClient.analyticsSnapshot()` exists (`api-client.ts:156`) and no store
   calls it. One store plus a set of views.
4. **The tuning workflow's missing middle** [10] → SR51 — the grid-results table and
   its Propose action. `POST /tuning/propose` still exists
   (`pages.py:435-479`) and the job already writes its result file, so this is
   a view over data that is produced today. Without it a grid can be launched
   and proposals can be deleted, but a proposal cannot be created by any route.
5. **List filters with no control** [7] → SR52 — strategy, horizon, confidence, tier,
   badge, tag, has-note. `strategy`, `horizon`, `tier` and `has_note` are
   already accepted by `api_v1/trades.py:FILTERS`; `badge`, `confidence` and
   `tag` need the server side too.
6. **Plan-shaped columns** [5] → SR53 — follow score, entry-or-trigger, TP2, age, and
   the lifecycle counts. These are what made the plans board readable for plans
   that have not filled; without them a PENDING row shows mostly nulls.
7. **Analytics figures needing recomputation** [18] → SR54 — the date-range filter and
   everything scoped by it, avg win/loss, total and annualised return, Calmar,
   volatility, trades/month, % in market, the SPY benchmark, the two
   histograms, the calendar drill-down, cumulative P&L by strategy. The
   expensive half: each needs a computation as well as a view.
8. **Journal analytics never on the wire** [7] → SR55 — MFE, MAE, exit efficiency,
   tags, auto-lessons, the weekly digest, top lessons. A coherent set: they
   come back together or not at all, and all need an endpoint first.
9. **Settings navigability** [5] → SR56 — the search box over a hundred fields, the
   only-changed filter, the changed-from-default state, the per-field reset,
   and `.env` file upload. Check whether `SettingField` carries the default
   before sizing the middle three; the Jinja page needed it and the SPA's
   `isChanged()` answers a different question (edited in this draft, not
   differing from default).
10. **Log triage** [2] → SR57 — the level filter and the line-count selector.
11. **Everything else** [7] → SR58 — the dashboard date-scope toggle, the
    market-session indicator, the version footer (`GET /health` already serves
    it, `ApiClient.health()` has no caller), the font-zoom control, the login
    `next` redirect, today's realised amounts on the balance card.

## Missing — blocks NG57

| Workspace | Feature | Where in Jinja | Rank | Where in the SPA / why it is gone |
|---|---|---|---|---|
| Dashboard | Dashboard mode toggle: Today + Open / Today only / All days | `dashboard.html:14-22`, scoping in `dashboard.py:scoped_trades` | **blocks NG57** | — no date-scope control anywhere in the SPA; the Dashboard endpoint has no `mode` parameter |
| Dashboard | Column: Age (time since creation) | `_plans_board.html:81, 109` | **blocks NG57** | — the table has `opened_at` and `held`, both null for a plan that never filled; `created_at` is detail-only |
| Dashboard | Column: TP2 | `_plans_board.html:80, 108` | **blocks NG57** | — `target2` is on `TradeRow` (`models.ts:72`) but has no column and no picker entry |
| Dashboard | Column: Entry **or trigger** price, with the "(trigger)" marker | `_plans_board.html:77, 102-105` *(also `plan_detail.html:16-17`)* | **blocks NG57** | — the list shows `entry`, which is null for a PENDING plan. `trigger_price` is typed on `TradeDetailFields` (`models.ts:118`) but no component renders it, so the actionable number for an unfilled plan is nowhere on screen |
| Dashboard | Filter: badge VALIDATED/WEAK | `_plans_board.html:42-46` | **blocks NG57** | — `badge` is not in `FILTERS` either, so this one needs a server change as well as a control |
| Dashboard | Filter: tier A/B/C | `_plans_board.html:36-41` | **blocks NG57** | — `tier` *is* in `api_v1/trades.py:FILTERS` (line 60); no control sends it |
| Dashboard | Scale-out leg rows ("↳ runner N%: price (R)") | `dashboard_fragment.html:417-427` *(also `_trade_history_rows.html:91-101`)* | **blocks NG57** | Row expansion defers them to the detail view (`trades.ts:277-283`), but the detail view does not render them either: `legs` / `legs_realized` are on the wire (`models.ts:129-130`) and no component reads them — see SR42 |
| Dashboard | Column: Follow score (`analytics.rank.rank_plans`) | `_plans_board.html:76, 101`, `pages.py:_ranked_plan_rows` | **blocks NG57** | — `follow_score` appears nowhere in `frontend/src`; the ranking is not on the wire |
| Dashboard | Today's wins/losses amounts and closed count under the balance | `dashboard_fragment.html:47-52` | **blocks NG57** | — the card has no sub-line; the figures come from `get_daily_summary()` and the `/dashboard` endpoint does not return them |
| Dashboard | Lifecycle strip: five counts (PENDING / ACTIVE / PARTIAL / CLOSED today / CANCELLED today) | `dashboard_fragment.html:22-30`, counts from `pages.py:_plan_rows()["counts"]` | **blocks NG57** | — the status chips exist as filters but carry no counts, and the Dashboard endpoint returns none |
| Dashboard | Session banner: UTC clock + market-session pills | `dashboard_fragment.html:16-19` (filled client-side) | **blocks NG57** | — `SessionStore` in the SPA is the *auth* session; there is no market-session indicator anywhere |
| Dashboard | Filter: confidence Lv1-5 | `dashboard.html:118-123` | **blocks NG57** | — no confidence control; the column shows the level but cannot filter by it |
| Dashboard | Filter: horizon | `dashboard.html:105-111` | **blocks NG57** | — likewise in `FILTERS`, no control |
| Dashboard | Filter: strategy | `dashboard.html:98-104` *(also `journal.html:28-29`)* | **blocks NG57** | — `strategy` is in the API's `FILTERS` set (`api_v1/trades.py:59`) but no control sends it |
| Dashboard | Row action: close trade | `dashboard_fragment.html:411-414` *(also `_plans_board.html:112-121` cancel/close, and `trade_detail.html:58-63`)* | **blocks NG57** | `availableActions()` (`trade-actions.ts:48-58`) switches on `'open'`/`'planned'`/`'pending'`, but `row.status` carries the uppercase plan vocabulary (`api_v1/trades.py:119`, `:159`). `ACTIVE`/`PARTIAL` therefore fall through to `['delete']` and no Close button renders |
| Trades | MFE (max favourable excursion), in R | `:72` | **blocks NG57** | — not on `TradeRow`, not on `TradeDetailFields`, nowhere in the API |
| Trades | Top lessons list | `:16-25`, `pages.py:347` (`top_lessons`) | **blocks NG57** | — likewise |
| Trades | Weekly digest messages | `:8-15`, `pages.py:346` (`weekly_digest`) | **blocks NG57** | — no endpoint and no view |
| Trades | Auto-generated lesson per entry | `:81-83` | **blocks NG57** | — likewise |
| Trades | Entry tags | `:76-80` | **blocks NG57** | — likewise |
| Trades | Exit efficiency % | `:74` | **blocks NG57** | — likewise |
| Trades | MAE (max adverse excursion), in R | `:73` | **blocks NG57** | — likewise absent from the wire |
| Trades | Filter: tag | `:30-35` | **blocks NG57** | — journal tags are not on `TradeRow` at all |
| Trades | Filter: has note / no note | `:43-47` | **blocks NG57** | `has_note` is on `TradeRow` (`models.ts:84`) *and* in `FILTERS` (`trades.py:59`) — client-only work |
| Trades | Quality breakdown table (factor → points) | `:60-74` | **blocks NG57** | `quality_breakdown` on the wire (`models.ts:126`), rendered nowhere — the score shows without its reasons |
| Trades | Lifecycle timeline (created, then every status transition with reason and time) | `:48-58` | **blocks NG57** | `status_history` and `created_at` are on the wire (`models.ts:115, 128`), rendered nowhere. This is the plan's whole audit trail |
| Trades | Break-even trigger, as % of TP1 distance | `:22` | **blocks NG57** | `breakeven_trigger_fraction` on the wire (`models.ts:121`), rendered nowhere |
| Trades | Confidence score breakdown table (8-10 factors) | `:163-173` | **blocks NG57** | `confidence_breakdown` on the wire (`models.ts:131`), rendered nowhere |
| Trades | "Confirmed by" — the other strategies that agreed | `:135-139` | **blocks NG57** | `confirmed_by` on the wire (`models.ts:133`), rendered nowhere |
| Trades | "Why this trade" — the recorded explanation | `:107-114` | **blocks NG57** | `explanation` is on the wire (`models.ts:132`); nothing renders it. The single largest piece of per-trade prose in the old UI |
| Trades | "Target confirmed by" / "Stop confirmed by" sources | `:88-93` | **blocks NG57** | `target_sources` / `stop_sources` are on the wire (`models.ts:134-136`); no component reads them |
| Trades | Follow-score breakdown | `:89-98` | **blocks NG57** | — follow score itself is not on the wire at all (SR41), so neither is its breakdown |
| Analytics | Rolling returns, 30d and 90d | `:470-477` | **blocks NG57** | `rolling_wr` is a win rate, not a return |
| Analytics | Monthly returns heatmap | `:479-484` | **blocks NG57** | `by.month` |
| Analytics | Month drill-down calendar modal | `:486-495` | **blocks NG57** | — |
| Analytics | P&L distribution histogram | `:497-505` | **blocks NG57** | — |
| Analytics | Holding-period distribution histogram | `:506-513` | **blocks NG57** | — |
| Analytics | Pie: win / loss split | `:517-524` | **blocks NG57** | derivable from `relocated.wins` / `losses`, already on the Analytics tab as numbers |
| Analytics | Pie: long / short split | `:525-532` | **blocks NG57** | `by.direction` |
| Analytics | Pie: trades by strategy | `:533-540` | **blocks NG57** | `by.strategy` |
| Analytics | R-multiple distribution | `:576-583` | **blocks NG57** | `r_multiples` |
| Analytics | Pie: holding-period split | `:557-564` | **blocks NG57** | — |
| Analytics | Pie: trades by horizon | `:565-572` | **blocks NG57** | `by.horizon` |
| Analytics | Cumulative P&L by strategy | `:594-601` | **blocks NG57** | — |
| Analytics | By Stock: win rate and P&L per ticker | `:606-612` | **blocks NG57** | `by.ticker` |
| Analytics | By Day of Week table | `:621-627` | **blocks NG57** | `by.dow` |
| Analytics | Day-of-week bar row | `:625` | **blocks NG57** | `by.dow` |
| Analytics | Pie: trades by ticker | `:549-556` | **blocks NG57** | `by.ticker` |
| Analytics | Drawdown (% below peak) | `:460-467` | **blocks NG57** | `drawdown` |
| Analytics | Volatility (ann) | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Daily activity — wins & losses per day | `:442-449` | **blocks NG57** | — |
| Analytics | Equity curve vs SPY benchmark | `:451-459` | **blocks NG57** | The curve is in the snapshot; the SPY series is not served at all |
| Analytics | Date-range filter: All time / Today / This week / This month / This year | `stats.html:402-410` | **blocks NG57** | — nothing on the Analytics tab is date-scoped, and no analytics endpoint takes a range |
| Analytics | Custom from/to date range + Apply | `:412-419` | **blocks NG57** | — |
| Analytics | Avg Win | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Avg Loss | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Profit Factor | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | `overall.profit_factor` is in the snapshot |
| Analytics | Total Return | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Sharpe | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | `overall.sharpe` |
| Analytics | Ann. Return | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Max Drawdown | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | `overall.max_drawdown_pct` |
| Analytics | Calmar | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Trades/Month | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | % In Market | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | — |
| Analytics | Win/loss streaks | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | `overall.streaks` — in the snapshot, never shown even in Jinja |
| Analytics | Account balance over time | `:433-440` | **blocks NG57** | `equity_curve` |
| Analytics | Sortino | `stats.html:1121-1157` (KPI strip) | **blocks NG57** | `overall.sortino` |
| Risk | Results column: Excl% | `:127, 141` | **blocks NG57** | — |
| Risk | "view results" link per finished job | `:168` | **blocks NG57** | — follows from the results table being absent |
| Risk | **Propose** — stage a passing row as a proposal | `:143-149`, `pages.py:tuning_propose` | **blocks NG57** | — the endpoint exists; nothing in `frontend/src` calls it. This is the break in the workflow: proposals can be listed and deleted but never created |
| Risk | Results column: Pass, with the row highlighted | `:128, 134, 142` | **blocks NG57** | — |
| Risk | Results column: ExpR | `:126, 140` | **blocks NG57** | — |
| Risk | **Grid results table** — one row per parameter combination | `:114-155` | **blocks NG57** | — no results view of any kind. The job's stdout is shown; the parsed grid is not |
| Risk | Results column: N | `:124, 138` | **blocks NG57** | — |
| Risk | Results column: Params | `:123, 135-137` | **blocks NG57** | — |
| Risk | Current parameters: **Default params** | `:32-34` | **blocks NG57** | — `default_params` appears nowhere in `frontend/src`; the tab proposes changes to values it never shows |
| Risk | Results column: Win rate | `:125, 139` | **blocks NG57** | — |
| System | Line-count selector (100 / 500 / 1000 / 2000 / 5000) | `:21-31` | **blocks NG57** | `SystemStore` has no `lines` control (`system.store.ts:390, 433` expose only source), so the tail is whatever the server defaults to. The count is *displayed* (`logs-tab.ts:64`) but cannot be changed |
| System | Font/UI zoom control (A−/A+, 80-150%, persisted) | `:59-63, 129-160` | **blocks NG57** | — no text-size control anywhere; the saved `adminFontZoom` has no successor |
| System | "Last updated" from `VERSION.json` | `:68-74` | **blocks NG57** | `GET /health` returns `versions.last_updated` and `ApiClient.health()` exists (`api-client.ts:82`); nothing calls it |
| System | Version tag "UI vN · Bot vN" | `:75-79` | **blocks NG57** | — same endpoint, same gap. With SR48 about to bump `ui` to 1.2.0, the UI will not show its own version |
| System | `next` hidden field — return to the page you were sent from | `:35` | **blocks NG57** | — the SPA always lands on the Dashboard after sign-in, so a deep link followed while signed out loses its destination |
| System | Changed-from-**default** dot | `:48` | **blocks NG57** | The SPA's `.changed` class marks fields edited in the current draft (`isChanged`, `settings-tab.ts:415`), which is a different question. A field that has been saved away from its default looks untouched |
| System | Per-field reset-to-default button | `:52-56, 265-270` | **blocks NG57** | — no way to restore one field; `store.resetDraft()` discards the whole draft |
| System | Search settings by name or description | `:96-97, 250-263` | **blocks NG57** | — over a hundred fields across every section, with no way to find one by name. The largest usability loss in this group |
| System | "Only changed" filter | `:99` | **blocks NG57** | — follows from the changed-from-default state not existing |
| System | Import .env by **file upload** | `:224` | **blocks NG57** | — paste only; a saved `.env` has to be opened and copied first |
| System | Level filter checkboxes: INFO / WARNING / ERROR / DEBUG | `:62-76, 115-132` | **blocks NG57** | — no filtering of any kind over the tail |

## Missing — cosmetic

These are tooltips, labels and explanatory sentences.

**SR47's decision: fill all 33.** No cosmetic row is dropped, so none moves to
`dropped on purpose`. They are grouped by workspace into SR59–SR63, one task
each — Dashboard 7, Trades 3, Analytics 10, Risk 5, System 8.

Two observations behind that decision. First, the largest cluster by far is
explanatory copy on Analytics (nine rows) — the calibration explainer, the two
threshold rules, the tip icons. That page's numbers are meaningless without
knowing what bar they are judged against, so "drop them all" is a real change
in what the page communicates, not a tidy-up. Second, the watchlist's Yahoo
Finance format tip is the one cosmetic row with a functional consequence: an
add that fails because the symbol format is wrong gives no hint what the right
format was.

| Workspace | Feature | Where in Jinja | Rank | Where in the SPA / why it is gone |
|---|---|---|---|---|
| Dashboard | "What appears here" explainer banner | `dashboard.html:60-68` | cosmetic | — no equivalent copy in any workspace |
| Dashboard | "closed today" qualifier on the count | `dashboard.html:78` | cosmetic | — consequence of the mode toggle being absent |
| Dashboard | The premium card's worked-out explanation (risk amount, caps, absolute cap, `!account sizing` hint) | `dashboard_fragment.html:81-87` | cosmetic | — the chip carries the number and the "max" qualifier, none of the reasoning |
| Dashboard | Shares-snapshot tooltip, incl. sizing-mode mismatch warning | `dashboard_fragment.html:391` | cosmetic | — no equivalent anywhere; `sizing_mode` is a `TradeDetailFields` field with no UI |
| Dashboard | Footer note: 15s refresh, sizing risk %, `!account` hint | `dashboard_fragment.html:443-445` | cosmetic | — no equivalent line |
| Dashboard | Lifecycle strip with per-status tooltips | `_plans_board.html:4-21` | cosmetic | — same gap as the dashboard strip: no counts, and the tooltip copy has no home |
| Dashboard | Section help: the PENDING → … → CLOSED explainer | `_plans_board.html:22-27` | cosmetic | — the lifecycle is not explained anywhere in the SPA |
| Trades | That cell's tooltip: position size at open, or "no sizing snapshot" | `:67` | cosmetic | — `position_value` is a picker-addable column, but the "logged before this feature existed" distinction is gone |
| Trades | "If it gets there" projection (next level up, pullback on reversal) | `:96-104` | cosmetic | — no equivalent panel; it is derived from `target2` and `stop_loss`, both of which the Levels panel already has |
| Trades | "Logged before the admin UI captured full detail" notice | `:177-181` | cosmetic | **Already filled — this row is stale.** Found during SR60: `trade-detail.store.ts:detailAbsent` plus the `no-detail` paragraph in `trade-detail.ts` already say it, in near-identical wording. The audit recorded the gap against the *fields* rendering as dashes; the notice explaining them had in fact landed. No work was needed and none was invented. |
| Analytics | Range summary line | `:420` | cosmetic | — |
| Analytics | Badge-drift section help: the ≥20 trades / >10 points rule | `stats.html:50` | cosmetic | — the threshold is now nowhere in the UI |
| Analytics | Badge-drift tip: what "decay" means | `calibration.html:53`, `stats.html:48` | cosmetic | — |
| Analytics | Tier-calibration tip: how the grading is checked | `stats.html:19` | cosmetic | — no tooltip |
| Analytics | Tier-calibration section help: "thin A/B rows usually mean too few trades" | `stats.html:21` | cosmetic | — the one line that stops an empty table being read as a broken tiering |
| Analytics | "What is calibration?" explainer | `calibration.html:5-15` | cosmetic | — the tab opens straight into a table |
| Analytics | Twelve `?` tip icons explaining each column | `:30-41` | cosmetic | — the column headers carry no explanation anywhere in the SPA |
| Analytics | Card subtitle "out-of-sample validation status per strategy" | `:21-23` | cosmetic | — the panel heading is "Strategy registry" with no gloss |
| Analytics | "Is this strategy's edge still working?" section help | `:10-18` | cosmetic | — no explanatory copy on the Strategies tab |
| Analytics | The 80% target line drawn across that chart | `:106-121` | cosmetic | — nothing states the target the deciles are judged against |
| Risk | TRAIN window dates, printed | `:75-78` | cosmetic | — the SPA says no date input exists but never says which window is in force |
| Risk | "changes take effect on the next !check or scheduled scan" | `:41-42` | cosmetic | — nothing says when an add or remove takes effect |
| Risk | Tip: Yahoo Finance symbol format (`ASML.AS`, `BTC-USD`, `^GSPC`) | `:85-92` | cosmetic | — the one piece of copy on this page that prevents a failed add, and the format is not guessable |
| Risk | "Positions in one cluster tend to lose together" | `:97-100` | cosmetic | — the panel lists the clusters without saying why they matter |
| Risk | "Derived from the account's own equity curve…" | `:125-129` | cosmetic | — the same kind of gap as the clusters note |
| System | "N line(s) hidden by filter" counter | `:75, 127-128` | cosmetic | — follows from the filter being absent |
| System | Required-field validation (`required` on both inputs) | `:38, 42` | cosmetic | — neither input is marked required and the button is not disabled on an empty form |
| System | Field-count badge per section | `:115` | cosmetic | — |
| System | Default-value badge beside the label | `:50` | cosmetic | — the default is never shown, so "what was this before I touched it" has no answer on screen |
| System | "● = changed from default" legend | `:101-103` | cosmetic | — |
| System | "Export omits credentials/tokens entirely; import accepts them" | `:209` | cosmetic | — the asymmetry is not stated, and it is the reason an exported file is safe to hand around |
| System | Per-level colourising of whole lines | `:80-113` | cosmetic | — the `<pre>` is uniform; an ERROR line is not distinguishable at a glance |
| System | Scroll-to-bottom on load, preserved across refresh | `:136, 143-146` | cosmetic | — the tail opens at the top, so the newest lines need a manual scroll |

## Migrated

| Workspace | Feature | Where in Jinja | Where in the SPA / why dropped |
|---|---|---|---|
| Dashboard | Refresh status text | `dashboard.html:27` | `sb-connection-status` in `shell/shell.html:76` |
| Dashboard | Unrealized amount in account currency | `dashboard_fragment.html:388-397` | `realized_pnl_amount` covers realised; unrealised amount has no column — `position_value` and `shares` are picker-addable and give the inputs |
| Dashboard | R:R column | `dashboard_fragment.html:379` | `risk_reward` column |
| Dashboard | Stop / Target columns | `dashboard_fragment.html:377-378` | `stop_loss` / `target`, picker-addable |
| Dashboard | Plan cell (entry → target / stop) for compact density | `dashboard_fragment.html:364-375` | `sb-plan-cell` (SR8) |
| Dashboard | Unrealized P&L % | `dashboard_fragment.html:352-362` | `pnl_pct` column with `pnlClass` |
| Dashboard | Current price, live-blink while market is active | `dashboard_fragment.html:333-343` | `now` column. The `price-live` blink class and the market-active gate are not reproduced |
| Dashboard | Entry price | `dashboard_fragment.html:330` | `entry` column |
| Dashboard | Confidence score /100 with tri-colour band | `dashboard_fragment.html:320-328` | Folded into `sb-confidence-cell [score]` (SR10) |
| Dashboard | Confidence Lv1-5 badge | `dashboard_fragment.html:314-318` | `sb-confidence-cell` (SR10) |
| Dashboard | Direction column | `dashboard_fragment.html:307-312` | `sb-direction-arrow` (SR9) |
| Dashboard | Horizon pill + "~N months" tooltip | `dashboard_fragment.html:301-305` | `horizon` column, raw key only, no expanded label |
| Dashboard | Strategy column + "Sources: …" tooltip | `dashboard_fragment.html:296-299` | `strategy` column exists. The target/stop **sources** do not render anywhere: `target_sources` / `stop_sources` are typed on `TradeDetailFields` (`models.ts:134-136`) and no component reads them — see SR42 |
| Dashboard | Tier chip | `dashboard_fragment.html:287` | `tier` column + `sb-quality-chip`, `trades.ts:234-238` |
| Dashboard | Direction glyph inline on the ticker (compact) | `dashboard_fragment.html:286` | `sb-direction-arrow` as its own column (SR9) |
| Dashboard | Ticker cell → trade detail link | `dashboard_fragment.html:283-288` | `dashboard.ts:201-203`, `trades.ts:214-216` |
| Dashboard | Held / time-open column, amber past 30 days | `dashboard_fragment.html:400-404` | `held` column via `held(row.held_hours)`; the >30-day amber is not reproduced |
| Dashboard | Status cell: dot, SL→TP bar, entry tick, progress % | `dashboard_fragment.html:252-280`, `dashboard.py:build_open_trade_views`/`pos_color` | `ui/status-cell.ts`, server-driven via `progress_pct` / `entry_pct` / `progress_band` / `blink_seconds` (SR7) |
| Dashboard | Opened timestamp (Berlin) | `dashboard_fragment.html:406` | `opened_at` column, `dateTime()` |
| Dashboard | "Clear open trades" bulk action | `dashboard_fragment.html:453-461` | `trades.ts:111-113` + confirm dialog |
| Dashboard | Confirm prompt naming the ticker | `_plans_board.html:114, 119` | `actionConsequence()` names the ticker and what will not come back (`trade-actions.ts:33-44`) |
| Dashboard | Row click → plan detail | `_plans_board.html:88` | Row activate → `/trades/:id` |
| Dashboard | Column: Quality score | `_plans_board.html:82, 110` | Row expansion, `trades.ts:287` |
| Dashboard | Column: TP1 | `_plans_board.html:79, 107` | `target` column |
| Dashboard | Column: Status pill | `_plans_board.html:75, 100` | `sb-status-cell` / `status_label` |
| Dashboard | Column: Direction | `_plans_board.html:74, 95-99` | `sb-direction-arrow` |
| Dashboard | Column: Strategy, linking to the Strategies page anchor | `_plans_board.html:73, 94` | `strategy` column; the deep link into the strategy's own section is gone |
| Dashboard | Column: Ticker | `_plans_board.html:72, 93` | `ticker` column |
| Dashboard | Column: Tier / Badge chips | `_plans_board.html:71, 90-91` | `tier` column + chip; `badge` in row expansion (`trades.ts:286`) |
| Dashboard | Empty state ("No plans match the current filters") | `_plans_board.html:61-65` | `data-table` empty state |
| Dashboard | Plan count in the card title | `_plans_board.html:54-58` | Pagination total |
| Dashboard | Filter submit / clear | `_plans_board.html:49-50` | Filters navigate on change; `sb-filter-bar (cleared)` clears |
| Dashboard | Filter: ticker | `_plans_board.html:47-48` | Ticker input |
| Dashboard | Filter: status | `_plans_board.html:30-35` | Status chips |
| Dashboard | Active-filter highlight on the selected card | `_plans_board.html:14` | `sb-filter-chips [selected]`, `trades.ts:158-163` |
| Dashboard | Empty state: "No open trades right now. Run `!check`…" | `dashboard_fragment.html:447-451` | `emptyState` on the Dashboard panel, `dashboard.ts:307-310` (different copy, same role) |
| Dashboard | Density toggle | `dashboard_fragment.html:189-192` | `dashboard.ts:377-385`, own table id, own preference |
| Dashboard | Column: SL | `_plans_board.html:78, 106` | `stop_loss` column |
| Dashboard | Open-trade count in the card title | `dashboard_fragment.html:180-184` | `allLinkLabel()` — "All N open →", `dashboard.ts:420-423` |
| Dashboard | Sortable headers with sort arrows | `dashboard.html:150-163` | `data-table` `sortable` columns; server-side sort via `store.sort()` |
| Dashboard | Per-page selector 10/25/50/All | `dashboard.html:131-141` | `[showPerPage]="true"`, `trades.ts:208-209` (SR15) |
| Dashboard | Density toggle (compact / full) | `dashboard.html:127-130` | `trades.ts:117-136`, per-table density in `ui/table-prefs.ts` |
| Dashboard | Reset filters | `dashboard.html:124-125` | `sb-filter-bar (cleared)`, `trades.ts:165` |
| Dashboard | Filter: direction | `dashboard.html:112-117` | Direction select, `trades.ts:173-179` |
| Dashboard | Filter: ticker (dropdown of every ticker in history) | `dashboard.html:91-97`, options from `dashboard.py:build_filter_options` | Free-text Ticker input, `trades.ts:166-172`. Enumerated options became a text field |
| Dashboard | Filter: outcome (WIN/LOSS/CLOSED) | `dashboard.html:84-90` | Status chips `win` / `loss`, `trades.columns.ts:155-156` (they drive `outcome`, not `status`) |
| Dashboard | Trade History card title + closed-trade count | `dashboard.html:74-80` | Trades table pagination total, `data-table` |
| Dashboard | Export CSV | `dashboard.html:56` | `trades/trades.ts:104-110`, `store.exportUrl()` |
| Dashboard | Stop scan (enabled only while running) | `dashboard.html:48-54` | `system/scan-tab.ts:58-67`, `[disabled]="!store.scanRunning()"` |
| Dashboard | "Run !check now" trigger | `dashboard.html:43-47` | `system/scan-tab.ts:49-57` — `Scan now` |
| Dashboard | Pause / resume scanning | `dashboard.html:40-42` | `system/scan-tab.ts:70-90`, one control in two states |
| Dashboard | Scan-paused badge | `dashboard.html:37` | `system/scan-tab.ts:36` — `Automatic scanning paused` |
| Dashboard | Bot liveness dot + label | `dashboard.html:30-34` | `sb-connection-status [botAlive]`; also `Bot alive / Bot not reporting` in `system/scan-tab.ts:39` |
| Dashboard | Free-text filter by ticker **or strategy** | `dashboard_fragment.html:186-188` | Ticker input in Trades, `trades.ts:166-172`. The strategy half has no control — see the strategy-filter row above |
| Dashboard | Pagination bar (prev / page x of y / next / info) | `dashboard.html:177-183` | `sb-pagination` inside `data-table` |
| Dashboard | "Clear all history" bulk action | `dashboard.html:188-191` | `trades.ts:114-116` + its own confirm dialog |
| Dashboard | Trigger status text | `dashboard.html:55` | `store.scanMessage()` rendered verbatim, `scan-tab.ts:93-98` |
| Dashboard | Chart preview modal on row click | `dashboard.html:201-207` | Row click opens the detail view, whose Chart tab is the Phase 3 chart (`trades/trade-detail.ts`) — a tab rather than a modal |
| Dashboard | Avg holding period | `dashboard_fragment.html:168-174` | Analytics (`avg_holding_days`, labelled "Avg holding") |
| Dashboard | Empty state: "No closed trades yet…" | `dashboard.html:195-197` | `data-table` `emptyState`, `trades.ts:202` |
| Dashboard | Avg open confidence | `dashboard_fragment.html:160-166` | `sb-metric-chip label="Avg confidence"`, `dashboard.ts:130` |
| Dashboard | Worst trade | `dashboard_fragment.html:152-158` | Analytics (`worst_trade_pct`) |
| Dashboard | Best trade | `dashboard_fragment.html:144-150` | Analytics (`best_trade_pct`) |
| Dashboard | Open P&L % | `dashboard_fragment.html:125-131` | `sb-metric-card label="Open P&L"`, `dashboard.ts:111-116` |
| Dashboard | Expectancy (avg R) | `dashboard_fragment.html:117-123` | `sb-metric-chip label="Expectancy"`, `dashboard.ts:134` |
| Dashboard | Avg realized P&L % | `dashboard_fragment.html:136-142` | Analytics `relocated` group (`avg_realized_pct`) |
| Dashboard | Losses | `dashboard_fragment.html:103-107` | Analytics `relocated` group (`losses`) |
| Dashboard | Wins | `dashboard_fragment.html:97-101` | Analytics — the `relocated` group, `analytics.store.ts` (`wins`) |
| Dashboard | Each lifecycle card links to the filtered board | `dashboard_fragment.html:25` | Status chips navigate `/trades?status=…`, `trades.columns.ts:148-159` |
| Dashboard | Open trades count | `dashboard_fragment.html:91-95` | `sb-metric-chip label="Open trades"`, `dashboard.ts:127` |
| Dashboard | Position premium per trade, both sizing modes | `dashboard_fragment.html:67-89`, `dashboard.py:build_sizing_note` | `sb-metric-chip label="Position premium"` + `premiumUnit()` saying "max" in risk-% mode, `dashboard.ts:147-152, 450-452` |
| Dashboard | Equity (30d) change % + sparkline | `dashboard_fragment.html:59-65`, `dashboard.py:build_equity_curve` | The equity chip, `dashboard.ts:141-145`, `store.equityPoints()` / `equityChangePct()` |
| Dashboard | Win rate | `dashboard_fragment.html:109-115` | `sb-metric-chip label="Win rate"`, `dashboard.ts:131` |
| Dashboard | Account balance + today's % change | `dashboard_fragment.html:34-38`, `get_daily_summary()` | `sb-metric-card label="Account balance"`, `dashboard.ts:106-110` |
| Trades | Entry type | `:15` | Plan tab → Opened → Entry type |
| Trades | Direction | `:14` | Plan tab → Per share → Direction |
| Trades | Tier chip, badge chip, status pill | `:9-11` | Tier chip and status indicator are there; the badge chip is not (see the badge row above) |
| Trades | Opened / Closed timestamps with fill prices | `:151-154` | Plan tab → Opened (At / Closed); the fill price is not paired with the timestamp |
| Trades | Realized gain/loss | `:155-159` | Live tab → Amount |
| Trades | Stop loss | `:18` | Plan tab → Levels → Stop |
| Trades | Setup: strategy, direction, confidence label + Lv + score | `:126-134` | Header tags + Plan tab (`direction`, `origin`); confidence as a chip |
| Trades | Trade plan panel (duplicate of Trade facts, plus sources) | `:76-94` | Plan tab → Levels |
| Trades | Heading: ticker — strategy (horizon) | `plan_detail.html:7` | Detail header + tags |
| Trades | TP1 with its fraction ("TP1 (50%)") | `:19-20` | "Target 1"; `tp1_fraction` is on the wire and not rendered, so the split is not shown |
| Trades | Realized R per entry | `:66-68` | `r_multiple` column |
| Trades | Quality score | `:23` | Trades row expansion → Quality (`trades.ts:287`) |
| Trades | Badge stats: status, N, win rate, expectancy, window | `:76-87` | Strategy tab renders the registry's equivalents, and adds the live-vs-OOS comparison (`trade-detail.ts:346-383`) |
| Trades | Filter: outcome (win / loss / scratch / timeout) | `:36-42` | Status chips cover `win` and `loss`; `scratch` and `timeout` have no chip |
| Trades | Clear filters | `:48-49` | `sb-filter-bar (cleared)` |
| Trades | Empty state | `:52-56` | `data-table` empty state |
| Trades | Per-entry outcome chip, ticker, strategy | `:60-65` | The Trades row carries all three |
| Trades | Link to the trade | `:69` | Row and id cell both link |
| Trades | Note display | `:84-86` | Notes tab, `detail.note` |
| Trades | Inline note editing, saved per entry | `:87-94, 100-121` | Notes tab textarea with `saving` / `unsaved` / `error` states (`trade-detail.ts:303-333`) — a better version of the same control, one trade at a time |
| Trades | Realized amount | `:53-55` | Live tab → Now → Amount, `trade-detail.ts:220-225` |
| Trades | TP2 (runner) | `:21` | Plan tab → Levels → Target 2 |
| Trades | Entry / Stop / Target 1 / Target 2 / R:R | `:44-52` | Plan tab → Levels panel, `trade-detail.ts:117-140` |
| Trades | Opened / Closed timestamps, Berlin, UTC in the tooltip | `:80-81` | `opened_at` / `closed_at` via `dateTime()`; no second timezone |
| Trades | VALIDATED / WEAK badge pill + its two tooltips | `:35-37` | The Strategy tab shows the registry's own `status`, `n`, win rate, expectancy and window (`trade-detail.ts:346-383`), which is the same judgement with its evidence. The pill and its copy are gone |
| Trades | Status pill (WIN / LOSS / other) | `:38-40` | `sb-status-indicator` in the header |
| Trades | Ticker link to the detail page | `:32-34` | `ticker` / `num` cells are anchors to `/trades/:id` |
| Trades | Inline direction glyph at compact density | `:35` | `sb-direction-arrow` as its own column (SR9) |
| Trades | Tier chip + "A ≥75 / B 50-74 / C below 50" tooltip | `:36` | `tier` column + `sb-quality-chip`; the threshold tooltip is gone |
| Trades | Strategy cell + "Sources: …" tooltip | `:43-44` | `strategy` column. The sources tooltip has no equivalent — see the `target_sources` row below |
| Trades | Horizon pill + "~N months swing horizon" tooltip | `:45` | `horizon` column, raw key only |
| Trades | Direction cell | `:46-50` | `sb-direction-arrow` |
| Trades | Confidence Lv1-5, colour-coded | `:51` | `sb-confidence-cell` (SR10) |
| Trades | Entry price | `:52` | `entry` column |
| Trades | Exit price, with "no exit price recorded" tooltip | `:53-57` | `exit_price` column; `num()` renders null as a dash without saying why |
| Trades | Outcome glyph W / L / CLOSED + per-outcome tooltip | `:27-31` | Status chips filter on it (`outcome`), `sb-status-cell` renders `status_label` |
| Trades | Realized gain/loss in account currency | `:64-71` | `realized_pnl_amount` column ("Realised") |
| Trades | Realized R-multiple + its explanation tooltip | `:72-77`, `dashboard.py:closed_r` | `r_multiple` column via `rMultiple()`; no tooltip |
| Trades | Held / holding period | `:78-79`, `dashboard.py:closed_days` | `held` column via `held(row.held_hours)` |
| Trades | Row action: delete this trade record | `:85-88` | `availableActions()` returns `delete` in every branch, so this is the one row action that does render (`trades.ts:247-255`) |
| Trades | "Back to dashboard" link | `trade_detail.html:3` | "← Trades", `trade-detail.ts:74` — back to the list the row came from |
| Trades | Visualization card: LONG/SHORT + ticker heading | `:8-13` | The header's ticker, `sb-status-indicator` and the direction/strategy tags (`trade-detail.ts:76-103`) |
| Trades | Chart loading spinner and its "price data may be unavailable" failure copy | `:15-24` | `sb-chart-container` `[loading]` / `[error]` / `[canRetry]`, `trade-detail.ts:278-288` |
| Trades | `<details>` "Interactive chart" | `:25-27` | The Chart tab *is* the interactive chart; it is no longer folded away |
| Trades | Trade facts: strategy + horizon pill | `:34` | Header tags, `trade-detail.ts:88-93` |
| Trades | Realized P&L %, direction-adjusted | `:58-63`, `dashboard.py:closed_pnl` | `pnl_pct` column |
| Analytics | Wins | `stats.html:1121-1157` (KPI strip) | Analytics → Record (`relocated.wins`) |
| Analytics | Trades | `stats.html:1121-1157` (KPI strip) | Analytics → Overall → Trades |
| Analytics | Account Balance | `stats.html:1121-1157` (KPI strip) | Dashboard, `sb-metric-card` |
| Analytics | Tier-calibration empty state | `:26-30` | `data-table` empty state |
| Analytics | Badge-drift empty state | `:55-59` | `data-table` empty state |
| Analytics | Badge drift table: Strategy / Live WR / OOS WR / Δ / Decayed | `:51-80` (also `stats.html:46-69`) | `DRIFT_COLUMNS`, `analytics.ts:252-261` |
| Analytics | Losses | `stats.html:1121-1157` (KPI strip) | Analytics → Record (`relocated.losses`) |
| Analytics | "No closed trades yet" empty state | `:425-429` | Each table's own empty state |
| Analytics | Win Rate | `stats.html:1121-1157` (KPI strip) | Dashboard chip and Analytics → Overall |
| Analytics | By Strategy: win rate and P&L per strategy | `:613-618` | The Strategy registry carries live WR and N per strategy; the P&L column has no equivalent |
| Analytics | Avg Hold | `stats.html:1121-1157` (KPI strip) | Analytics → Record (`relocated.avg_holding_days`) |
| Analytics | Pie: trades by confidence level | `:541-548` | The "By confidence level" table already carries the counts (`CONFIDENCE_COLUMNS`) — the pie is the same data as a shape |
| Analytics | Win rate by confidence level | `:584-591` | "By confidence level" table, `analytics.ts:164-173` |
| Analytics | Raw trade log with 12 columns | `:630-661` | This is the Trades workspace, in full and with more columns |
| Analytics | Trade-log free-text filter (ticker / strategy) | `:635-637` | Ticker input in Trades; the strategy half has no control (SR41) |
| Analytics | Trade-log sortable headers | `:643-654` | Server-side sort on the Trades table |
| Analytics | Trade-log footer count | `:660` | Pagination total |
| Analytics | Tier calibration table: Tier / N / Live WR / Expected band / Pass | `:24-49` (also `stats.html:17-44`) | `TIER_COLUMNS`, `analytics.ts:241-250`. "Expected band" → "Design band", "Pass" → "In band" |
| Analytics | Expectancy | `stats.html:1121-1157` (KPI strip) | Dashboard chip and Analytics → Overall, in R rather than % |
| Analytics | Decile column: win rate | same | `win_rate` |
| Analytics | Column: OOS ExpR | `:35, 57` | `expectancy_r` |
| Analytics | Score-decile chart: realized win rate per decile | `:17-22, 88-122` | The same deciles as a table, `analytics.ts:230-239` / `DECILE_COLUMNS`. The bar chart is gone |
| Analytics | Decile column: N | `:87-91` (JS) | `DECILE_COLUMNS` `n` |
| Analytics | Edge-decay banner naming the flagged strategies | `strategies.html:3-9` | `analytics.ts:178-185`, same sentence, same trigger |
| Analytics | Column: Strategy | `:29, 48` | `STRATEGY_COLUMNS[0]`, `analytics.columns.ts:58` |
| Analytics | Column: Rolling WR sparkline (last 10 closed) | `:30, 52`, `pages.py:_rolling_win_rate_series` | `rolling` column, cell attached in the component (`analytics.columns.ts:59`) |
| Analytics | Column: Badge chip VALIDATED/WEAK | `:31, 53` | `status` column with a chip cell |
| Analytics | Column: OOS N | `:33, 55` | `n` |
| Analytics | Column: OOS WR | `:34, 56` | `win_rate` |
| Analytics | Column: Live N | `:36, 58` | `live_n` |
| Analytics | Column: Live WR | `:37, 59` | `live_wr` |
| Analytics | Column: R:R override | `:32, 54` | `rr_override`, two decimals |
| Analytics | DECAY chip inside the Δ cell | `:62` | The banner plus the drift table's own `drift_alert` column |
| Analytics | Column: Window | `:39, 64` | `window` |
| Analytics | Column: Run date | `:40, 65` | `run_date` |
| Analytics | "n/a" for cells under 5 trades, with the count in the tooltip | `:14-15` | The `n < 5` suppression is preserved; the "too few trades" tooltip is not |
| Analytics | Column: Gate description | `:41, 66` | `gate_description` |
| Analytics | Strategy × horizon grid of live win rates | `_heatmap.html:4-26` | `analytics.ts:198-225`, served by `_json_heatmap` (`api_v1/analytics.py:92-110`) |
| Analytics | Colour ramp by win rate | `:17`, `pages.py:_heatmap_color` | `--heat` custom property per cell, `analytics.ts:215` |
| Analytics | Cell label "NN% (n)" | `:19` | `heatLabel()` |
| Analytics | Column: Δ vs OOS, signed and coloured | `:38, 60-61` | `delta_vs_oos`, `delta()` keeps the sign |
| Risk | Current parameters: R:R | `:30` | Registry `rr_override` |
| Risk | "Current parameters" table: Strategy | `:23, 28` | Strategy registry table, Strategies tab |
| Risk | Section help: what tuning is, the TRAIN/VALIDATION firewall, the pass bar | `tuning.html:4-12` | The launcher's `note` keeps the firewall paragraph (`analytics.ts:267-273`); the acceptance bar (WR ≥80%, positive expectancy, N ≥30) is not stated anywhere |
| Risk | Empty state | `:81` | `data-table` empty state |
| Risk | Column: Company | `:51, 60` | `company_name` |
| Risk | Column: Closed trades | `:53, 68` | `closed_trades` |
| Risk | Column: Open trades | `:52, 61-67` | `open_trades` |
| Risk | Current parameters: Gate | `:31` | Registry `gate_description` |
| Risk | Column: Ticker | `:50, 59` | `symbol`, a link into the ticker detail view |
| Risk | Remove, with a confirm prompt | `:69-75` | Remove button + `sb-confirm-dialog` (`watchlist.ts:128, 141`) |
| Risk | Current parameters: Window | `:35` | Registry `window` |
| Risk | Proposals: current-vs-proposed diff table | `:187-198` | `analytics.ts:355-368` |
| Risk | "Values are code, changed only via reviewed commits" | `:17-19` | The Proposals panel's note says the same thing more concretely (`analytics.ts:337-341`) |
| Risk | Strategy select | `:80-88` | `sb-select`, `analytics.ts:282-287` |
| Risk | Launch TRAIN grid | `:89` | `analytics.ts:288-297` |
| Risk | Launch status / error, incl. the 409 "busy" case | `:90, 105-106` | `store.launchError()` + the `jobActive()` branch, which hides the launcher entirely |
| Risk | Job progress card with state pill | `:47-52` | `sb-chip [label]="jobStateLabel(job)"`, `analytics.ts:306-310` |
| Risk | Job log tail | `:51, 60` | `<pre class="log">`, `analytics.ts:311` |
| Risk | Recent jobs list | `:157-172` | "Earlier jobs", `analytics.ts:319-334` |
| Risk | Proposals: strategy, created-at, job id | `:181-186` | `analytics.ts:347-354` |
| Risk | Ticker count in the card title | `:39-42` | The header's "N watched" |
| Risk | Proposals: TRAIN stats line (N / WR / ExpR) | `:199-203` | `proposal.trainSummary`, `analytics.ts:369` |
| Risk | Proposals: delete, with a confirm prompt | `:204-207` | Delete button + `sb-confirm-dialog` |
| Risk | Proposals empty state | `:179` | "No proposals yet." |
| Risk | Current parameters: Run date | `:36` | Registry `run_date` |
| Risk | Autocomplete shows the company name | `:116` | `hit-name` |
| Risk | Current parameters: Badge | `:29` | Registry `status` |
| Risk | "Already-present tickers are skipped safely, nothing is removed" | `:22-26` | `store.addResult()` reports what happened afterwards rather than promising it beforehand |
| Risk | Ticker autocomplete, debounced, stale-response guarded | `:94-150` | `store.suggestions()`, `watchlist.ts:66-85` |
| Risk | Kill-switch engaged banner at the top of the page | `risk.html:16-25` | Shell-level: `KILLSWITCH ENGAGED` in the topbar (`shell.html:72-74`), true in every workspace, plus the Killswitch panel |
| Risk | That banner's reason | `:21` | `killswitchDetail()`, `risk.ts:79-81` |
| Risk | "Release is manual and never clears itself" | `:22` | The Killswitch panel's `kill-explain` copy (`risk.ts:71`) |
| Risk | Portfolio heat: cap % | `:37` | "of N% cap", `risk.ts:130` |
| Risk | Portfolio heat: utilisation % | `:38-39` | `store.heatUtilisationPct()` on the meter |
| Risk | Utilisation bar, clamped at 100%, colour by band | `:40-45` | `role="meter"` track; only the width is clamped, so an over-cap figure still reads correctly (`risk.ts:137-155`) |
| Risk | "At or above the cap, new entries are blocked" | `:50-53` | `heatNote()` |
| Risk | Sector heat table, sorted by exposure | `:56-77` | Sector heat panel, `risk.ts:193-204` |
| Risk | Sector heat bars | `:67-72` | Same panel |
| Risk | Sector heat empty state | `:79` | "No sector exposure." |
| Risk | Correlated clusters table | `:83-96` | Clusters panel, `risk.ts:208-223` |
| Risk | Portfolio heat: open heat % | `:35-36` | `store.openHeatPct()`, `risk.ts:127-129` |
| Risk | Drawdown throttle: risk multiplier ×N | `:108-113` | "Drawdown throttle at ×N", `risk.ts:169-171` |
| Risk | Clusters empty state | `:102` | "No correlated clusters among open positions." |
| Risk | Add one ticker | `watchlist.html:5-12` | The single Add input, `watchlist.ts:52-98` |
| Risk | Bulk add / restore, behind a disclosure | `:14-34` | Folded into the same input — "AAPL, or paste a list" (`watchlist.ts:62`). One control instead of two |
| Risk | Scan health: latest duration in seconds | `:180-182` | Same panel |
| Risk | Scan health: duration sparkline, last 50 scans | `:177-182` | `sb-sparkline` labelled "Recent scan durations, in seconds" |
| Risk | Scan health empty state | `:184` | Same panel |
| Risk | "A hard stop on new entries; open positions keep being monitored" | `:134-138` | `kill-explain` |
| Risk | Kill-switch release | `:153-155` | Same panel, the two states of one control |
| Risk | Kill-switch engage with a confirm prompt | `:158-161` | `sb-confirm-dialog` in the workspace |
| Risk | Kill switch: status, reason, action | `:140-166` | Killswitch panel |
| Risk | Drawdown throttle: PAUSED / Throttled / Normal | `:115-121` | The three states, `risk.ts:162-175` |
| Risk | Scan health: slowdown warning ("more than 2x the median of the prior 20") | `:171-176` | `store.scanSlowdown()`, `risk.ts:242-246` |
| System | Password placeholder "blank = keep current" | `:78` | "stored value hidden — type to replace", `settings-tab.ts:96` |
| System | "↺ restart" badge on non-hot-reloadable fields | `:51` | "restart required", `settings-tab.ts:89-94` |
| System | Save & reload bot | `:134` | The save bar, `settings-tab.ts:107-148` |
| System | Save hint: hot reload vs restart | `:135` | Per-field "restart required" plus the diff's `restartRequired()` list (`settings-tab.ts:182-187`) |
| System | Diff preview before saving | `:140-181`, `_settings_diff.html` | "Pending changes" panel, `settings-tab.ts:156-188` — a panel rather than a modal |
| System | Diff table: Setting / Current / New | `_settings_diff.html:4-15` | `settings-tab.ts:158-181` |
| System | Diff "Nothing changed." | `_settings_diff.html:2` | "No changes" in the save bar |
| System | Diff modal Confirm & Save / Cancel | `settings.html:147-150` | Save and Discard in the bar |
| System | "Docker socket not mounted" explanation | `:241-245` | `restartAvailable()` hides the button and explains why (`scan-tab.ts:119-128`) |
| System | Audit entry timestamp + per-key diff | `:191-196` | Same shape |
| System | Export .env | `:206` | Export/import panel, `settings-tab.ts:229-263` |
| System | Import .env by pasting text | `:221-223` | The import textarea, placeholder "KEY=value, one per line — as exported." |
| System | Restart bot container + confirm | `:232-247` | The Scan tab's Bot process panel (`scan-tab.ts:104-135`), with a confirm dialog |
| System | Source tabs: Bot / Admin UI | `logs.html:4-19` | Two pressed-state buttons, `logs-tab.ts:23-33` |
| System | Refresh button | `:35` | `logs-tab.ts:34-42` |
| System | Raw view in a new tab | `:36` | A real anchor to the raw endpoint, `logs-tab.ts:45` |
| System | `min` / `max` / `step` on numeric fields | `:83-85` | Passed through to `sb-text-input` |
| System | Recent changes audit, collapsed, with a count | `:183-201` | "Recent changes" panel, `settings-tab.ts:208-227` — always expanded, no count in the heading |
| System | Checkbox / select / password / number / text control types | `:64-92` | `controlOf(field)` switch, `settings-tab.ts:55-82` |
| System | Log out button in the sidebar footer | `:64-67` | Moved into the profile menu (`profile-menu.ts:55-58`), deliberately one control rather than two |
| System | Field help text, HTML-safe for `POSITION_SIZING_MODE` | `:58-62` | `field.help` rendered as text; the one field with markup in its help loses its formatting |
| System | Clear log + confirm | `:37-40` | Clear button + `sb-confirm-dialog` |
| System | Page title "`<page>` — Swing Bot Admin" | `base.html:6` | The document title is static; it does not name the current workspace |
| System | Favicons (png/ico/32/16) and apple-touch-icon | `:14-18` | SR6's identity assets |
| System | Inter webfont | `:19` | Same font, loaded by the SPA build |
| System | `tokens.css` + `style.css` | `:20-21` | SR2 rewrote the palette into the SPA's own `tokens.css` |
| System | Brand: avatar + "Swing Bot" + 📈 | `:40-49` | The sidebar mark: avatar, "swingbot", "paper" tag (`shell.html:11-24`) |
| System | Nav items with active highlight | `:50-58` | `routerLinkActive`, `shell.html:26-44` |
| System | Hamburger toggle for the mobile sidebar | `:85, 95-127` | The overlay menu button, `shell.html:4-8`, plus the scrim and Escape handling |
| System | "Env var: KEY" fallback when there is no help | `:61` | The key is always shown, `settings-tab.ts:88` |
| System | Page header `<h1>{{ title }}` | `:86` | Each workspace renders its own `<h1>` |
| System | "Swing Bot Admin" heading | `:30` | The wordmark and its subtitle |
| System | Error banner | `:31-33` | `@if (error())` with `role="alert"` |
| System | Username field, `autocomplete="username"`, autofocus | `:36-39` | Same attributes (`login.html:6-15`) |
| System | Password field, `autocomplete="current-password"` | `:40-43` | Same |
| System | Sign in button | `:44` | Plus a `submitting()` state the form post could not have |
| System | Fields grouped into sections | `settings.html:107-131` | One `sb-panel` per section, `settings-tab.ts:46-103` |
| System | Section description | `:113` | `section.description`, `settings-tab.ts:48-50` |
| System | Field label | `:49` | Every control takes a `label` |
| System | Flash banner (`msg` + ok/err) | `:88-90` | `sb-toast-host` (`shell.html:88`), plus per-panel `role="status"` / `role="alert"` lines |
| System | Log file path | `:59` | The panel heading is the path, and `.meta` repeats it |

## Dropped on purpose

| Workspace | Feature | Where in Jinja | Where in the SPA / why dropped |
|---|---|---|---|
| Dashboard | Auto-refresh checkbox, "every Ns" | `dashboard.html:23-25` | Spec 3: SSE push replaces polling, so there is no interval to switch off. `EventStream` + `ConnectionStatus` in the shell |
| Dashboard | "Refresh now" button | `dashboard.html:26` | Same decision — with push there is nothing to hurry |
| Dashboard | Row-number `#` column | `dashboard.html:149` | SR16 replaced the ordinal with the trade's short id as a link (`trades.ts:214-216`) — an ordinal is meaningless once sort and page move |
| Dashboard | Fourteen equal-weight cards | whole `stat-row` | Design-system Decision 2 / spec v14 Decision 5: three cards + six chips, hierarchy by size. Re-adding a card here is a design change |
| Dashboard | Per-page selector | `dashboard_fragment.html:193-203` | The Dashboard panel is capped at six (`OPEN_POSITIONS_CAP`) and deliberately has no pager — paging a summary is the Trades workspace in disguise. Per-page lives in Trades |
| Dashboard | VALIDATED/WEAK badge deliberately absent from this table | `dashboard_fragment.html:289-293` | Same decision holds: `badge` is in row expansion (`trades.ts:286`) and the detail view, not a list column |
| Dashboard | Row action: open detail in new tab | `dashboard_fragment.html:409-410` | The ticker/id cell is a real anchor, so the browser's own "open in new tab" covers it |
| Dashboard | Whole page as a separate destination | `plans.html` | Spec v14 Decision 4 — Trades is the one entity |
| Dashboard | ETag-polled fragment refresh | `plans.html:5-41` | Replaced by SSE push (`api/event-stream.ts`) |
| Trades | Entries / Weekly digest view switch | `:3-6` | Only the entries half has a successor; the digest is recorded below |
| Trades | Journal as its own destination | `journal.html` | Spec v14 Decision 4 |
| Trades | Empty state: "No trade has been linked to this plan yet" | `:115-120` | Same reason — a PENDING row simply has null execution fields |
| Trades | Plan chart PNG + lightbox | `:26-46` | Same decision as the trade chart — the Chart tab replaces both |
| Trades | Support/resistance wording (`level_word` / `opposite_word`, direction-aware) | `:46, 99, 103`, computed in `app.py:trade_detail` | The SPA labels them "Target 1" / "Target 2" / "Stop" regardless of direction — one vocabulary rather than two |
| Trades | Linked trade: id, status, legs | `:100-114` | Plan and trade are one row and one page in the SPA, so there is nothing to link to. The legs half is recorded as missing above |
| Trades | Server-rendered PNG chart | `:19-24` | Phase 3 replaced it with the live `sb-trade-chart` on the Chart tab; SR40 walked the two against each other |
| Trades | Row action: open detail in a new tab | `:83-84` | The id cell is a real anchor, so the browser provides this |
| Trades | VALIDATED/WEAK deliberately omitted from this table | `:38-41` | Same decision holds — `badge` is row-expansion and detail only |
| Trades | Continuous row numbering across pages (`row_offset`) | `_trade_history_rows.html:26` | SR16 replaced the ordinal with the trade's short id (`trades.ts:214-216`) — a number that changes when you sort is not an identifier |
| Trades | Chart lightbox: pinch-zoom, drag-pan, double-tap reset, orientation lock | `:182-431` | A lightbox is what a static raster needs. The Chart tab's chart zooms and pans natively |
| Analytics | Seventeen `?` tip icons explaining each chart | throughout | Nothing to explain where the chart itself is gone; where the chart migrated, the tooltip is folded into the row above |
| Analytics | Row anchor `#strategy-<slug>` (deep-link target) | `:46` | Its only inbound link was the plans board's strategy cell, and that page is gone (SR41) |
| Analytics | Included on **both** `/strategies` and `/performance` | `strategies.html:73`, `stats.html:71` | One home, on the Strategies tab. Rendering the same table on two pages is the duplication the workspace model exists to end |
| Analytics | Per-row "🛠 Tune" link | `:49` | Tuning is a tab in the same workspace, not another page — the deep link has no destination to point at |
| Analytics | Per-row "📓 Journal" link | `:50` | The Journal page is gone (SR42) |
| Risk | Column: row number | `:49, 58` | Same decision as the trades tables — an ordinal that moves with the sort is not information |
| Risk | 3-second polling of `/api/jobs/<id>` | `:56-71` | Replaced by the `jobs` SSE event, stated in the panel itself (`analytics.ts:312-315`) |
| Risk | Full-page reload when the job ends | `:66, 107` | The log stays put and the launcher returns on its own |
| Risk | Seven `?` tip icons | throughout | Where the feature migrated, the panel notes carry the explanation; where it did not, there is nothing to annotate |
| System | Auto-refresh checkbox, every N seconds | `:32-34, 150-152` | Stated in the component: a log that refreshes on a timer looks live without being live, and scrolls a traceback away mid-read (`logs-tab.ts:11-14`) |
| System | Bot avatar on the login card | `login.html:26-29` | The SPA login is a wordmark ("swingbot" / "admin"), `login.html:3-4`. SR6 put the avatar in four places and this was not one of them |
| System | Section icon | `:111` | The SPA has an icon sprite (SR20) and does not decorate headings with emoji |
| System | "Hard reload bot" from the logs page | `:49-58` | Restart is one control on the Scan tab. Two restart buttons is the duplication the workspace model removes — though this one was placed on Logs deliberately, which SR46 may want to weigh |

## New in the SPA

Recorded so the row counts are not read as a net loss. These have no Jinja
counterpart and are not parity rows.

| Workspace | Feature | Where in Jinja | Where in the SPA / why dropped |
|---|---|---|---|
| Dashboard | Risk used vs cap | — (not on the Jinja dashboard) | New in the SPA (`dashboard.ts:117-123`); recorded so the count of cards is not read as a loss |
| Trades | Per-share risk / reward | — | New in the SPA (`trade-detail.ts:142-161`) |
| Trades | Working stop, sizing mode, entry type | — | New on the Plan tab; `working_stop` / `sizing_mode` / `entry_type` are the three detail fields that *are* rendered |
| Analytics | Decile column: expectancy R | — | New in the SPA (`DECILE_COLUMNS` `expectancy_r`) |
| Analytics | Tier ExpR | — | New in the SPA (`TIER_COLUMNS` `expectancy_r`) |
| Analytics | Badge drift OOS N and Live N | — | New in the SPA (`DRIFT_COLUMNS` `oos_n`, `live_n`) |
| Risk | Exposure by position (per-position table) | — | New in the SPA (`risk.ts:181-190`) |
| Risk | "already watched" marker on a suggestion | — | New in the SPA (`watchlist.ts:75-80`) |
| System | Sidebar collapse to a rail, persisted | — | New in the SPA (SR21) |
| System | Killswitch banner in the topbar | — | New at shell level (`shell.html:72-74`) — the Jinja killswitch banner was on `/risk` only |
| System | Connection status | — | New; there was no connection state to show when every page was a full reload |
| System | Hot-reload result reported after saving | — | New (`store.saved()`, `settings-tab.ts:191-207`) — the Jinja page redirected with a flash |
| System | "Settings changed elsewhere while you were editing" | — | New (`store.settingsStale()`, `settings-tab.ts:28-41`) |
| System | Empty-log state | — | New ("This log is empty.", `logs-tab.ts:66`) |
