# Features — analytics and the admin cockpit

The analytics core, the cockpit it feeds, and the Angular admin SPA.

Part of the features documentation — index at [features.md](features.md).

## Analytics core

Every number the bot shows about its own performance — win rate,
expectancy, calibration, lessons — traces to exactly one function in
`swingbot/core/analytics/`, so a Discord embed, the admin dashboard, and a
CSV export can never quietly disagree:

| Module | Role |
|---|---|
| `metrics.py` | Equity curve, drawdown, win rate, expectancy R, profit factor, streaks, rolling win rate, Sharpe/Sortino — pure functions over trade-record lists. |
| `mfe_mae.py` | Per-trade max favorable/adverse excursion and exit efficiency (how much of the available move a trade actually captured). |
| `aggregate.py` | `stats_by(closed, dimension)` — one `StatRow` per bucket, across 10 dimensions (strategy, horizon, badge, confidence, direction, day-of-week, month, ticker, source, ledger (v93)). |
| `calibration.py` | Quality-score decile calibration, per-confidence-level win-rate calibration, and `badge_drift` — the pre-registered edge-decay rule. |
| `rank.py` | `follow_score` — the one ranking authority (see below). |
| `journal.py` | `JournalStore` — one auto-generated lesson entry per closed trade (MFE/MAE, exit efficiency, tags, a templated `auto_lesson`), plus hand-added notes via `set_note`. |
| `insights.py` | Human-readable rollups over the journal: the weekly lessons digest, the edge-decay report, and the top-recurring-lessons list. Formats only — every number here is delegated to `metrics.py`/`calibration.py`. |
| `snapshots.py` | Assembles everything above into one JSON blob so UIs never recompute on request (see below). |
| `scope.py` | `BookScope` — the one filter (date range, ledger, strategy, horizon, direction) every `/analytics/*` route parses, applies and echoes, so one query string means one population everywhere (v94). |

**`data/analytics_snapshot.json`** is that pre-built blob — win/loss stats,
equity curve, drawdown, rolling win rate, all 10 aggregation dimensions,
calibration, and the R-multiple distribution. It's rebuilt automatically
after every scan cycle and after every batch of trade closes
(`refresh_snapshot()`, wrapped so a failure there can never break a scan or
a close); a consumer calling `load_snapshot(max_age_seconds=...)` gets
`None` back — never a silently stale read — if the file is missing or older
than the staleness guard. The Analytics workspace no longer reads it (v94);
it serves the Dashboard and Discord, where an all-time pre-built blob is the
right artefact.

**`data/journal.json`** holds one entry per closed trade: MFE/MAE, exit
efficiency, auto-generated tags, and an `auto_lesson` sentence templated
from the trade's outcome shape. `scripts/data/backfill_journal.py` journals any
already-closed trade that predates the auto-journal hook (idempotent — safe
to re-run any time). `python scripts/reports/export_analytics.py` writes the
current snapshot + journal out as CSV/JSON for spreadsheet analysis.

**`follow_score`** (badge 40 + quality 40 + regime 10 + freshness 10) is the
single ranking formula for "which plan should I follow right now" —
computed in exactly one place and consumed everywhere a plan gets ranked or
sorted (Discord alerts, `!plans`, `!top`, the digest, `/api/plans`, the
admin board).

**Edge-decay rule (pre-registered, never tuned after seeing live data):**
`drift_alert = live_n >= 20 and live_wr < oos_wr - 10.0`. It only fires once
a strategy has accumulated at least 20 live closes and its live win rate has
fallen more than 10 points below the number it validated at out-of-sample —
loosening either threshold after watching live results would turn an
early-warning signal into a curve-fit one.

## Admin cockpit

**One UI: the Angular SPA.** Release B (2026-08-14) deleted the Jinja UI —
its 20 templates, its routes, the legacy `/api/*` blueprint and the `ADMIN_UI`
flag that used to choose between them. The admin now serves exactly
`/api/v1/*`, the SPA's workspace URLs and its assets, and `/`.

The SPA folds the pages below into **six workspaces**: Dashboard, Trades,
Analytics, Risk, Watchlist and System. Two renames came with that — Cockpit →
**Dashboard** and Universe → **Watchlist** — and both old URLs redirect. Plans
and Trades became one Trades list (a plan and the trade it fills are one
position, not two rows); Strategies, Calibration and Tuning became tabs on
Analytics; the Journal's figures moved to where they are read — excursions
onto the trade detail's Notes tab, the weekly digest onto Analytics.

**The Analytics workspace is six tabs, in the order a trader asks** (spec
v94): **Overview** (am I making money), **Attribution** (where does it come
from), **Execution** (am I executing well), **Edge** (is the edge holding,
is the model calibrated), **Pipeline** (what is coming), **Tuning**
(operations). One control bar under the tab strip scopes every panel —
range, ledger, strategy, horizon, direction, plus an R/%/currency unit
toggle — and reports the closed-trade count it produced. Panels that are
all-time by design (calibration, the strategy registry, the plan funnel)
say so with a badge rather than pretending to be scoped. A cell with fewer
than `MIN_CELL_N` closed trades never shows a rate: the server sends null
and the cell renders blank with its N.

The table below describes what each surface does. It is written in terms of
the pages the Jinja UI had, because that is still the clearest description of
the *capabilities* — the SPA folds them into six workspaces as above, but does
not remove any of them:

The admin UI (`python admin_ui.py`) is a decision cockpit built entirely on
top of the analytics core above — every figure is computed once, never
recomputed per-view:

| Page | What it's for |
|---|---|
| **Plans** (`/plans`) | The live plan board — every `TradePlanV2` ranked by `follow_score`, filterable by status/confidence level/badge/ticker, with cancel/close actions and a detail page (chart, timeline, quality breakdown, linked trade). |
| **Strategies** (`/strategies`) | Registry provenance per strategy (badge, R:R override, OOS N/WR/expectancy, validation window/run date), a strategy×horizon live win-rate heatmap, drift chips, and rolling-WR sparklines. |
| **Calibration** (`/calibration`) | Does a higher quality score actually win more? Score-decile chart vs the 80% target line, per-confidence-level win rate, and the badge-drift table (see the edge-decay rule above). |
| **Journal** (`/journal`) | Browses `JournalStore` entries (MFE/MAE, exit efficiency, tags, auto-lesson) with tag/outcome/strategy filters and inline note editing, plus a Weekly digest tab. |
| **Tuning** (`/tuning`) | A workbench over `scripts/backtest/tune_strategy.py`: current per-strategy parameters, a grid-launch form, live job-progress streaming, and a results/proposal browser. See the TRAIN-only guardrail below — this page can only ever *propose* a parameter change. |

**Job system.** `swingbot/admin/jobs.py`'s `JobManager` runs at most one
tuning grid at a time as a background subprocess; live progress streams to
the Tuning page via polling. Job logs live under `logs/jobs/<job_id>.log`,
grid results under `data/tuning_results/<job_id>.json`
(`scripts/backtest/tune_strategy.py --json`), and a proposed parameter change (never
auto-applied) under `data/tuning_proposals/`.

**TRAIN-only guardrail.** The tuning workbench physically cannot touch the
2024-01-01..2025-12-31 validation window — `assert_train_only` rejects any
grid launch whose date range overlaps it (including flag-injection and
non-padded-date bypass attempts, both explicitly tested). Validation stays
a deliberate, manual CLI act (`run_backtest_range.py --validation`), never
something the UI can trigger. A tuning proposal is a JSON file for a human
to review; nothing in this plan's code path ever writes it into
`DEFAULT_PARAMS`.

**Settings audit trail.** Every saved change appends a masked before/after
diff to `data/settings_audit.jsonl`, shown on the Settings page's "Recent
changes" panel. Sensitive fields (bot token, webhook URLs, credentials) are
masked (`•••`) in both the save-confirmation diff and the audit log — never
logged or exported in the clear. `.env` profile export omits sensitive
fields entirely (not just masked); import applies any recognized field it's
handed, sensitive or not (pasting a real credential back in is the whole
point of import), skipping only keys the schema doesn't recognize at all.

## Route data readiness

Every authenticated SPA workspace is lazy-loaded with a route-scoped resolver. The resolver waits only for the data visible on arrival, so the first rendered workspace has either fresh content or its established inline Retry state; supporting tables and optional chart panels continue independently. A route change is cancellable, and a non-auth request failure still activates the destination while an expired session returns to login with the requested URL preserved.

If resolution takes more than one second, the shell keeps its sidebar and topbar visible while a non-interactive workspace overlay names the loading destination. Relevant live events and successful domain mutations coalesce before re-running the active resolver. Draft settings and trade notes never get overwritten by these refreshes: they surface a data-changed notice and reload only after an explicit user action.
## Admin UI

The admin UI's look is driven by one design-token layer, not scattered
per-page CSS: `frontend/src/styles/tokens.css` is the single palette, type
and spacing source (direction C, "TradingView Blue", spec v80). The bot's
Discord chart PNGs share that palette: `swingbot/core/charts/chart_style.THEME`
copies the tokens it names, and `tests/charts/test_chart_theme.py` compares
the two byte for byte, so an admin colour change names the chart constant
that must follow it. The same test keeps every chart overlay clear of the
gain and loss colours. The old `swingbot/admin/static/tokens.css` mirror was
deleted in v80, having outlived the Jinja pages it styled.

Fonts (Inter and JetBrains Mono) are vendored under `static/vendor/` and
self-hosted — no runtime CDN calls, so the admin UI works fully offline.
Charting is `lightweight-charts` 5.x, installed via npm and bundled by the
Angular build; the vendored 4.2.3 copy went with the Jinja UI that loaded it
from a `<script>` tag.

| Surface | What it does |
|---|---|
| `/api/v1/market/ohlcv/<ticker>` | Auth-guarded, read-only OHLCV JSON for the interactive chart: falls back to the local CSV cache when a live fetch fails; an optional trade id adds that trade's entry/stop/target levels to the response. (The legacy `/api/ohlcv/<ticker>` went with the Jinja UI.) |
| Trade-detail chart | Every trade detail renders an interactive `lightweight-charts` candlestick with entry/SL/TP price lines, replacing the old static PNG-only view. |
| Dashboard quick-chart | Clicking a ticker opens the same interactive chart without leaving the page. |

**The SPA's tables** are one component with a compact/full density toggle,
a column picker, drag-to-reorder with a keyboard path, and per-table column
preferences persisted server-side rather than in `localStorage` — so a layout
follows the account, not the browser. Density, visible columns and page size
are all preferences; the range and filter controls are query parameters,
because they change what the server computes rather than how it is drawn.
