# Features

## Event loop responsiveness

All the heavy work — Yahoo Finance fetches, pandas/indicator computation,
matplotlib chart rendering, backtesting — runs in a background thread via
`asyncio.to_thread()`, never directly on Discord's event loop. Without
this, a scan or backtest that takes more than ~10 seconds blocks the
gateway heartbeat and Discord can flag the bot as unresponsive
(`discord.gateway Shard ID None heartbeat blocked`). A scan lock
(`asyncio.Lock`) also ensures the automatic session scan and a manual
`!check` can't run their file-writing work at the same time. This applies
to every command that fetches data or renders a chart: `!check`,
`!ticker`, `!backtest`, `!backtestwatchlist`, `!charts`, `!scrapeall`,
`!download`, `!pnl`, `!trade`, `!tradecharts`, `!watchlist add`.

## Plan Engine v2: validated trade plans with badges and scale-out

Every trade plan the bot emits can be produced by one shared engine
(`swingbot/core/plan_engine.py`) whose exit behavior was backtested under a
train/validation split — so live behavior equals backtested behavior by
construction. Rollout is gated by three flags (all in `.env` / the admin
UI's "Plan Engine v2" section, hot-reloadable):

| Flag | Values | Meaning |
|---|---|---|
| `PLAN_ENGINE_V2` | `off` / `shadow` / `on` | `off` = legacy behavior. `shadow` = v2 plans are computed and logged to `data/shadow_plans.jsonl` during scans but not posted (parity evidence for the cutover — compare with `python scripts/reports/shadow_parity_report.py`). `on` = alerts price and emit v2 plans. |
| `SCALE_OUT_ENABLED` | `true`/`false` | At TP1, close 50% and move the stop to break-even; the runner rides toward TP2 with a chandelier ATR trail. Enable only after `PLAN_ENGINE_V2=on` has run cleanly. |
| `INTRADAY_MANAGER_V2` | `true`/`false` | The 60s monitor manages the full plan lifecycle (PENDING → ACTIVE → PARTIAL → CLOSED): entry triggers, break-even moves, TP1 partials, runner trail, invalidation — with a Discord alert per transition. `!plans` shows the live board. |

**Defaults ship fully live** (`PLAN_ENGINE_V2=on`, `SCALE_OUT_ENABLED=true`,
`INTRADAY_MANAGER_V2=true`) so a fresh deployment runs the validated engine
immediately with no staged rollout required. If you'd rather stage it
yourself: `shadow` for ≥5 scan sessions (compare against legacy numbers via
`python scripts/reports/shadow_parity_report.py`) → `on` for ≥5 clean sessions →
enable scale-out + manager.

**Badges: what they legally claim.** Every v2 plan is stamped from
`swingbot/core/validation_registry.json`:

- ✅ **VALIDATED** — this plan's signal source cleared `win_rate ≥ 80%,
  expectancy > 0, N ≥ 15, scratches+timeouts ≤ 50%` on the **held-out
  2024–2025 window it was never tuned on** (tuning used 2020–2023 only,
  and each source got exactly one validation shot). The badge line shows
  the actual N / win-rate / expectancy behind the claim.
- ⚠️ **WEAK** — the source did not clear that bar out-of-sample. Weak
  plans are **never suppressed**; they carry a caution block with the real
  numbers instead. A win rate printed on a badge is always an
  out-of-sample number, never a train number.

The registry regenerates only from validation runs
(`python scripts/backtest/run_backtest_range.py --validation --exit-model v2
--scale-out --emit-registry swingbot/core/validation_registry.json
--run-date <date>`), never by hand.

**Rescue outcomes.** Round 1 validated 6 of 11 strategies out-of-sample;
each of the other 5 got one pre-registered rescue attempt (a new opt-in
gate, TRAIN-only tuning, then a single validation-window look, no
retuning after). Only **RSI** cleared the bar (range-regime gate,
100% WR / N=30), bringing the total to **7 of 11 VALIDATED**. RSI
Divergence and MA Ribbon's gates never qualified on TRAIN; Elliott Wave
and EMA Crossover both passed TRAIN comfortably but missed the 80%
out-of-sample floor by a few points and stay WEAK. Full scoreboard and
pooled numbers: `docs/superpowers/results/2026-07-v2-final-report.md`.

## Analytics core

Every number the bot shows about its own performance — win rate,
expectancy, calibration, lessons — traces to exactly one function in
`swingbot/core/analytics/`, so a Discord embed, the admin dashboard, and a
CSV export can never quietly disagree:

| Module | Role |
|---|---|
| `metrics.py` | Equity curve, drawdown, win rate, expectancy R, profit factor, streaks, rolling win rate, Sharpe/Sortino — pure functions over trade-record lists. |
| `mfe_mae.py` | Per-trade max favorable/adverse excursion and exit efficiency (how much of the available move a trade actually captured). |
| `aggregate.py` | `stats_by(closed, dimension)` — one `StatRow` per bucket, across 10 dimensions (strategy, horizon, tier, badge, confidence, direction, day-of-week, month, ticker, source). |
| `calibration.py` | Quality-score decile calibration, tier-vs-design-band checks, and `badge_drift` — the pre-registered edge-decay rule. |
| `rank.py` | `follow_score` — the one ranking authority (see below). |
| `journal.py` | `JournalStore` — one auto-generated lesson entry per closed trade (MFE/MAE, exit efficiency, tags, a templated `auto_lesson`), plus hand-added notes via `set_note`. |
| `insights.py` | Human-readable rollups over the journal: the weekly lessons digest, the edge-decay report, and the top-recurring-lessons list. Formats only — every number here is delegated to `metrics.py`/`calibration.py`. |
| `snapshots.py` | Assembles everything above into one JSON blob so UIs never recompute on request (see below). |

**`data/analytics_snapshot.json`** is that pre-built blob — win/loss stats,
equity curve, drawdown, rolling win rate, all 10 aggregation dimensions,
calibration, and the R-multiple distribution. It's rebuilt automatically
after every scan cycle and after every batch of trade closes
(`refresh_snapshot()`, wrapped so a failure there can never break a scan or
a close); a consumer calling `load_snapshot(max_age_seconds=...)` gets
`None` back — never a silently stale read — if the file is missing or older
than the staleness guard.

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

The table below describes what each surface does. It is written in terms of
the pages the Jinja UI had, because that is still the clearest description of
the *capabilities* — the SPA folds them into six workspaces as above, but does
not remove any of them:

The admin UI (`python admin_ui.py`) is a decision cockpit built entirely on
top of the analytics core above — every figure is computed once, never
recomputed per-view:

| Page | What it's for |
|---|---|
| **Plans** (`/plans`) | The live plan board — every `TradePlanV2` ranked by `follow_score`, filterable by status/tier/badge/ticker, with cancel/close actions and a detail page (chart, timeline, quality breakdown, linked trade). |
| **Strategies** (`/strategies`) | Registry provenance per strategy (badge, R:R override, OOS N/WR/expectancy, validation window/run date), a strategy×horizon live win-rate heatmap, drift chips, and rolling-WR sparklines. |
| **Calibration** (`/calibration`) | Does a higher quality score actually win more? Score-decile chart vs the 80% target line, tier-vs-design-band pass/fail, and the badge-drift table (see the edge-decay rule above). |
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

## Admin UI

The admin UI's look is driven by one design-token layer, not scattered
per-page CSS: `static/tokens.css` is the single palette/spacing source of
truth, `swingbot/admin/chart_style.THEME` mirrors those same colors for
server-rendered PNG charts, and a test keeps the two in sync so they can
never quietly drift apart. **`tokens.css` survived the Jinja deletion for
exactly that reason** — it stopped being read by templates and became the
source the Angular build imports, and deleting it would have left the *bot's*
Discord chart colours with no single source.

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

## The growth playbook

Written for future-you, reading this in a drawdown, wondering if any of it
still works.

**The equation.** Every closed trade multiplies equity by
`1 + risk_pct/100 * expectancy_r` (`swingbot/core/edge/growth.py`). Risk 1%
per trade at +0.10R expectancy and equity grows ~0.1% per trade —
compounding to 10x takes `ln(10) / ln(1.001)` ≈ 2303 closed trades. There is
no shortcut past this arithmetic. `!growth` (`growth_report()`) prints it
straight from your actual closed-trade history: current expectancy, trades
per month, current multiple, and the ETA to your target at the pace you're
actually trading at — never a projection dressed up as a promise.

**The three honest levers**, and which feature moves which:
- **Expectancy** — the strategy/entry-filter layer (`entry_filters.py`,
  `strategy_types.py`'s `STRATEGY_GATES`/`STRATEGY_RR_OVERRIDE`), the
  quality scoring in `quality.py` that tiers signals, and the validation
  registry (`swingbot/core/registry.py`) that badges which strategies have
  actually earned trust out-of-sample. Nothing here can invent edge that
  isn't real — E33's component-adoption process ran, found zero components
  that cleared the pre-registered fold gate, and adopted zero. That's not a
  failure of the process; it's the process refusing to fabricate edge.
- **Frequency** — the universe you scan (`SCAN_UNIVERSE`, `scripts/
  build_universe.py`), alert-flood control (`cap_alerts`/
  `MAX_ALERTS_PER_SCAN`) so a wider universe doesn't drown you, and the
  weekend deep scan (`weekend_deep_scan`) surfacing forming setups for
  Monday. More valid signals per month directly shortens the ETA above —
  but only if expectancy holds up at the wider scope (see E80's honest
  finding: Support/Resistance's edge carried over to an ETF-only universe,
  Break & Retest's didn't).
- **Survival** — heat/sector/correlation caps (`edge/heat.py`,
  `edge/correlation.py`), the drawdown throttle and kill switch below, and
  per-horizon capacity budgeting (`horizon_check`). A 10x path that gets
  wiped out at 3x isn't a 10x path. This lever doesn't make you money; it's
  what lets the other two levers keep compounding instead of restarting
  from zero.

**The drawdown throttle ladder** (`edge/throttle.py`'s `DD_LADDER`, frozen
constants) exists so a losing streak's math doesn't get compounded by a
tilted operator's judgment on top of it:

| Current drawdown | Position size multiplier |
|---|---|
| < 8% | 1.00x (normal) |
| > 8% | 0.75x |
| > 12% | 0.50x |
| > 16% | 0.25x |
| > 20% | 0.00x (paused — no new entries) |

Once paused, entries don't resume at the first green day — drawdown has to
recover back *below 15%* first (`RESUME_DD_PCT`, hysteresis against
whipsawing the throttle on/off around the 20% line). **Do not override
this by hand.** A drawdown is exactly the moment every cognitive bias
pushes toward "one more trade to get it back" — the ladder is code
specifically so that decision never has to be made under pressure. If you
genuinely believe a rung is wrong, that's a deliberate `.env` edit to
`DD_LADDER`'s constants (a code change, reviewed sober, not a live
override), never a one-off bypass during an actual drawdown. The weekly
risk report calls out any operator override, on purpose.

**The quarterly re-validation ritual** (`scripts/backtest/quarterly_revalidation.py`,
Task E96): the first weekend of January, April, July, and October, run it,
read every line it prints, and prune anything it flags DEGRADED. It's
deliberately a human-run script, not a cron job — a re-validation result
that nobody reads is worse than not re-validating at all. Put a real
calendar reminder on those four weekends; this system's edge is measured
against 2018-2023 data; it will not stay valid forever without someone
periodically checking that it still is.

**Reading the Monte Carlo fan** (`!portfolio`'s fan chart,
`edge/ruin.simulate` over your real closed-trade R-multiples): the shaded
band is P25–P75 of simulated equity paths, the dotted outer lines are
P5/P95, and the solid line is the median. The chart title gives you
`p(10x)`, `P95 max drawdown`, and `p(halve)` (probability equity ever
drops below 0.5x — `RUIN_THRESHOLD`) in one line. **The P5 path is a real
future too** — not a scare tactic, not a worst-case decoration. It's drawn
from the same distribution as the median path, just less likely. If you
wouldn't be able to stay in the system through the P5 path, you're sized
too aggressively for your own actual risk tolerance, regardless of what
the median promises.

**Why this will never promise 100% win rate, and what it promises
instead.** No strategy in the validation registry clears 100% WR, and one
that claimed to would be reporting on too small a sample to trust (see
`docs/superpowers/results/2026-07-validation.md`'s honest note that three
strategies which passed TRAIN flipped to FAIL on out-of-sample data). The
actual promise this system makes is narrower and more defensible:
pre-registered evidence (a strategy is trusted only after clearing gates
it didn't know about in advance, on data it hadn't seen), a visible ETA
(`!growth` never hides the sample size or dresses up a small-N result as
confident), and bounded ruin (the heat caps and throttle ladder mean a bad
month costs you a throttled month, not the account). That's the whole
deal: an honest number and a system that can't quietly become a bigger bet
than you agreed to.
