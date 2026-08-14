# Jinja → SPA parity audit, group 3: Analytics

Task SR43 of `2026-08-13-v21-spa-refresh.md`. Templates audited: `stats.html`
(2071 lines, most of it Chart.js), `strategies.html`, `calibration.html`,
`_heatmap.html`, together with the routes and builders behind them
(`pages.py:strategies_page`/`calibration_page`/`_registry_rows`/
`_strategy_horizon_heatmap`/`_rolling_win_rate_series`, and the
`swingbot/core/analytics` snapshot that `stats.html`'s JS reads).

Three statuses only — `migrated`, `dropped on purpose`, `missing`. Nothing is
left unclassified.

**The finding that decides this group's ranking.** `stats.html`'s twenty KPIs
and twelve charts are almost all `missing`, which reads like an enormous gap
until you check where their numbers come from. `GET /analytics/snapshot`
(`api_v1/analytics.py:44-48`) forwards the whole analytics snapshot verbatim,
and that snapshot already carries `profit_factor`, `sharpe`, `sortino`,
`max_drawdown_pct`, `total_pnl`, `streaks`, `equity_curve`, `drawdown`,
`rolling_wr`, `r_multiples` and a `by` block grouped along ten dimensions —
strategy, horizon, tier, badge, confidence, direction, dow, month, ticker,
source (`core/analytics/snapshots.py:37-66`, `aggregate.py:88-89`).
`ApiClient.analyticsSnapshot()` exists (`api-client.ts:156`) and **no store
calls it**. So each row below is tagged with which of the two kinds of gap it
is:

- *(snapshot)* — the number is already served and merely unrendered.
- *(recompute)* — `stats.html` derived it in browser JS from the raw trade
  list; nothing serves it, so it needs a computation as well as a view.

---

## `strategies.html` — the strategy registry

The closest thing to a clean migration in the whole audit.

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Edge-decay banner naming the flagged strategies | `strategies.html:3-9` | migrated | `analytics.ts:178-185`, same sentence, same trigger |
| "Is this strategy's edge still working?" section help | `:10-18` | **missing** | — no explanatory copy on the Strategies tab |
| Card subtitle "out-of-sample validation status per strategy" | `:21-23` | **missing** | — the panel heading is "Strategy registry" with no gloss |
| Column: Strategy | `:29, 48` | migrated | `STRATEGY_COLUMNS[0]`, `analytics.columns.ts:58` |
| Per-row "🛠 Tune" link | `:49` | dropped on purpose | Tuning is a tab in the same workspace, not another page — the deep link has no destination to point at |
| Per-row "📓 Journal" link | `:50` | dropped on purpose | The Journal page is gone (SR42) |
| Column: Rolling WR sparkline (last 10 closed) | `:30, 52`, `pages.py:_rolling_win_rate_series` | migrated | `rolling` column, cell attached in the component (`analytics.columns.ts:59`) |
| Column: Badge chip VALIDATED/WEAK | `:31, 53` | migrated | `status` column with a chip cell |
| Column: R:R override | `:32, 54` | migrated | `rr_override`, two decimals |
| Column: OOS N | `:33, 55` | migrated | `n` |
| Column: OOS WR | `:34, 56` | migrated | `win_rate` |
| Column: OOS ExpR | `:35, 57` | migrated | `expectancy_r` |
| Column: Live N | `:36, 58` | migrated | `live_n` |
| Column: Live WR | `:37, 59` | migrated | `live_wr` |
| Column: Δ vs OOS, signed and coloured | `:38, 60-61` | migrated | `delta_vs_oos`, `delta()` keeps the sign |
| DECAY chip inside the Δ cell | `:62` | migrated | The banner plus the drift table's own `drift_alert` column |
| Column: Window | `:39, 64` | migrated | `window` |
| Column: Run date | `:40, 65` | migrated | `run_date` |
| Column: Gate description | `:41, 66` | migrated | `gate_description` |
| Twelve `?` tip icons explaining each column | `:30-41` | **missing** | — the column headers carry no explanation anywhere in the SPA |
| Row anchor `#strategy-<slug>` (deep-link target) | `:46` | dropped on purpose | Its only inbound link was the plans board's strategy cell, and that page is gone (SR41) |

---

## `_heatmap.html` — strategy × horizon win rate

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Strategy × horizon grid of live win rates | `_heatmap.html:4-26` | migrated | `analytics.ts:198-225`, served by `_json_heatmap` (`api_v1/analytics.py:92-110`) |
| Colour ramp by win rate | `:17`, `pages.py:_heatmap_color` | migrated | `--heat` custom property per cell, `analytics.ts:215` |
| Cell label "NN% (n)" | `:19` | migrated | `heatLabel()` |
| "n/a" for cells under 5 trades, with the count in the tooltip | `:14-15` | migrated (narrowed) | The `n < 5` suppression is preserved; the "too few trades" tooltip is not |
| Included on **both** `/strategies` and `/performance` | `strategies.html:73`, `stats.html:71` | dropped on purpose | One home, on the Strategies tab. Rendering the same table on two pages is the duplication the workspace model exists to end |

---

## `calibration.html` — is the score predictive?

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| "What is calibration?" explainer | `calibration.html:5-15` | **missing** | — the tab opens straight into a table |
| Score-decile chart: realized win rate per decile | `:17-22, 88-122` | migrated (narrowed) | The same deciles as a table, `analytics.ts:230-239` / `DECILE_COLUMNS`. The bar chart is gone |
| The 80% target line drawn across that chart | `:106-121` | **missing** | — nothing states the target the deciles are judged against |
| Decile column: N | `:87-91` (JS) | migrated | `DECILE_COLUMNS` `n` |
| Decile column: win rate | same | migrated | `win_rate` |
| Decile column: expectancy R | — | n/a | New in the SPA (`DECILE_COLUMNS` `expectancy_r`) |
| Tier calibration table: Tier / N / Live WR / Expected band / Pass | `:24-49` (also `stats.html:17-44`) | migrated | `TIER_COLUMNS`, `analytics.ts:241-250`. "Expected band" → "Design band", "Pass" → "In band" |
| Tier ExpR | — | n/a | New in the SPA (`TIER_COLUMNS` `expectancy_r`) |
| Tier-calibration empty state | `:26-30` | migrated | `data-table` empty state |
| Badge drift table: Strategy / Live WR / OOS WR / Δ / Decayed | `:51-80` (also `stats.html:46-69`) | migrated | `DRIFT_COLUMNS`, `analytics.ts:252-261` |
| Badge drift OOS N and Live N | — | n/a | New in the SPA (`DRIFT_COLUMNS` `oos_n`, `live_n`) |
| Badge-drift empty state | `:55-59` | migrated | `data-table` empty state |
| Tier-calibration tip: how the grading is checked | `stats.html:19` | **missing** | — no tooltip |
| Tier-calibration section help: "thin A/B rows usually mean too few trades" | `stats.html:21` | **missing** | — the one line that stops an empty table being read as a broken tiering |
| Badge-drift tip: what "decay" means | `calibration.html:53`, `stats.html:48` | **missing** | — |
| Badge-drift section help: the ≥20 trades / >10 points rule | `stats.html:50` | **missing** | — the threshold is now nowhere in the UI |

---

## `stats.html` — the performance page

### Chrome

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Date-range filter: All time / Today / This week / This month / This year | `stats.html:402-410` | **missing** *(recompute)* | — nothing on the Analytics tab is date-scoped, and no analytics endpoint takes a range |
| Custom from/to date range + Apply | `:412-419` | **missing** *(recompute)* | — |
| Range summary line | `:420` | **missing** | — |
| "No closed trades yet" empty state | `:425-429` | migrated | Each table's own empty state |

### KPI strip (`stats.html:1121-1157`)

| Feature | Status | Where in the SPA / why dropped |
|---|---|---|
| Account Balance | migrated | Dashboard, `sb-metric-card` |
| Trades | migrated | Analytics → Overall → Trades |
| Wins | migrated | Analytics → Record (`relocated.wins`) |
| Losses | migrated | Analytics → Record (`relocated.losses`) |
| Win Rate | migrated | Dashboard chip and Analytics → Overall |
| Avg Win | **missing** *(recompute)* | — |
| Avg Loss | **missing** *(recompute)* | — |
| Profit Factor | **missing** *(snapshot)* | `overall.profit_factor` is in the snapshot |
| Expectancy | migrated | Dashboard chip and Analytics → Overall, in R rather than % |
| Total Return | **missing** *(recompute)* | — |
| Ann. Return | **missing** *(recompute)* | — |
| Sharpe | **missing** *(snapshot)* | `overall.sharpe` |
| Sortino | **missing** *(snapshot)* | `overall.sortino` |
| Max Drawdown | **missing** *(snapshot)* | `overall.max_drawdown_pct` |
| Calmar | **missing** *(recompute)* | — |
| Volatility (ann) | **missing** *(recompute)* | — |
| Avg Hold | migrated | Analytics → Record (`relocated.avg_holding_days`) |
| Trades/Month | **missing** *(recompute)* | — |
| % In Market | **missing** *(recompute)* | — |
| Win/loss streaks | **missing** *(snapshot)* | `overall.streaks` — in the snapshot, never shown even in Jinja |

### Charts

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| Account balance over time | `:433-440` | **missing** *(snapshot)* | `equity_curve` |
| Daily activity — wins & losses per day | `:442-449` | **missing** *(recompute)* | — |
| Equity curve vs SPY benchmark | `:451-459` | **missing** *(recompute)* | The curve is in the snapshot; the SPY series is not served at all |
| Drawdown (% below peak) | `:460-467` | **missing** *(snapshot)* | `drawdown` |
| Rolling returns, 30d and 90d | `:470-477` | **missing** *(recompute)* | `rolling_wr` is a win rate, not a return |
| Monthly returns heatmap | `:479-484` | **missing** *(snapshot)* | `by.month` |
| Month drill-down calendar modal | `:486-495` | **missing** *(recompute)* | — |
| P&L distribution histogram | `:497-505` | **missing** *(recompute)* | — |
| Holding-period distribution histogram | `:506-513` | **missing** *(recompute)* | — |
| Pie: win / loss split | `:517-524` | **missing** *(snapshot)* | derivable from `relocated.wins` / `losses`, already on the Analytics tab as numbers |
| Pie: long / short split | `:525-532` | **missing** *(snapshot)* | `by.direction` |
| Pie: trades by strategy | `:533-540` | **missing** *(snapshot)* | `by.strategy` |
| Pie: trades by confidence level | `:541-548` | migrated (narrowed) | The "By confidence level" table already carries the counts (`CONFIDENCE_COLUMNS`) — the pie is the same data as a shape |
| Pie: trades by ticker | `:549-556` | **missing** *(snapshot)* | `by.ticker` |
| Pie: holding-period split | `:557-564` | **missing** *(recompute)* | — |
| Pie: trades by horizon | `:565-572` | **missing** *(snapshot)* | `by.horizon` |
| R-multiple distribution | `:576-583` | **missing** *(snapshot)* | `r_multiples` |
| Win rate by confidence level | `:584-591` | migrated | "By confidence level" table, `analytics.ts:164-173` |
| Cumulative P&L by strategy | `:594-601` | **missing** *(recompute)* | — |
| Seventeen `?` tip icons explaining each chart | throughout | dropped on purpose | Nothing to explain where the chart itself is gone; where the chart migrated, the tooltip is folded into the row above |

### Breakdown tables and the trade log

| Feature | Where in Jinja | Status | Where in the SPA / why dropped |
|---|---|---|---|
| By Stock: win rate and P&L per ticker | `:606-612` | **missing** *(snapshot)* | `by.ticker` |
| By Strategy: win rate and P&L per strategy | `:613-618` | migrated (narrowed) | The Strategy registry carries live WR and N per strategy; the P&L column has no equivalent |
| By Day of Week table | `:621-627` | **missing** *(snapshot)* | `by.dow` |
| Day-of-week bar row | `:625` | **missing** *(snapshot)* | `by.dow` |
| Raw trade log with 12 columns | `:630-661` | migrated | This is the Trades workspace, in full and with more columns |
| Trade-log free-text filter (ticker / strategy) | `:635-637` | migrated (narrowed) | Ticker input in Trades; the strategy half has no control (SR41) |
| Trade-log sortable headers | `:643-654` | migrated | Server-side sort on the Trades table |
| Trade-log footer count | `:660` | migrated | Pagination total |

---

## Tally for this group

| Status | Count |
|---|---|
| migrated (incl. narrowed) | 34 |
| dropped on purpose | 6 |
| **missing** | 45 |
| new in the SPA (not a parity row) | 4 |

This is the largest `missing` count of the five groups, and the most uneven.
Splitting it the way SR46 will need to:

1. **Already served, merely unrendered** *(snapshot)* — 15 rows: profit factor,
   Sharpe, Sortino, max drawdown, streaks, the equity and drawdown series, the
   monthly heatmap, R-multiples, and the five `by`-dimension breakdowns. One
   store calling an endpoint that already exists unlocks all of them.
2. **Needs a computation as well as a view** *(recompute)* — 17 rows: the
   date-range filter and everything scoped by it, avg win/loss, total and
   annualised return, Calmar, volatility, trades/month, % in market, the SPY
   benchmark, the histograms, the calendar drill-down and cumulative P&L by
   strategy.
3. **Explanatory copy** — 13 rows: the calibration explainer, the strategies
   section help, the two threshold rules (tier bands, the decay rule), the 80%
   target line, and the tip icons. Cheap individually; they are what made this
   page legible to someone who did not build it.
