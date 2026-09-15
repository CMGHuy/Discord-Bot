# v82 — Earnings awareness: a label, a heads-up, and one pre-registered block

**Version:** ui 1.15.0 · bot 1.7.0
**Bump:** bot minor, ui patch
**Edge:** expectancy
**Depends on:** Plan A (label, notice, wiring) needs v81's code merged to `main`
— it adds a notice type to v81's delivery ledger and edits files v81 F5 edits
(`scan_run.py`, `alert_embeds.py`, the order ticket). Check:
`git log --oneline main --grep="feat(v81)"` is non-empty. Plan B (measurement)
depends on nothing and may start immediately.

## Status

| Part | State |
|---|---|
| Phase A — label, notice, stored fields | not started (Plan A; needs v81 merged) |
| Phase B — measurement | **NO_ELIGIBLE_K**, budget intact — `docs/superpowers/plans/implemented/2026-09-10-v82-earnings-measurement_0-index.md` and the results docs it lists |
| C1 — wiring into `scan_run.py` | not started (Plan A) |
| C2/C3 — rename, frozen class, wf_components note | done in Plan B M3 |
| C4 — default flip | void — default stays 0 |

`Bump:` **bot minor** — the execution feed gains a new message type (the
earnings heads-up) and the alert's earnings line changes rule entirely (hold
window → the session before and the day of the report); a reader of yesterday's
channel sees different messages. **ui patch** — one chip on the Trades list and
the trade detail header. A Stage 3 PASS that flips the block on is its own later
release (`bot patch`: fewer alerts, same shape), never part of this bump.

`Edge:` **expectancy**, earned only by the block (Phase B/C), and only if it
passes the v72 funnel. The label and the notice change no paper trade, so pooled
paper `ExpR` is unchanged by them **by construction**; like v81, what they buy is
the human partner's real-account alignment — they trade real money off these
alerts with resting broker orders, and an earnings gap is the single largest
way a resting stop fills far worse than the paper stop.

## Why — measured 2026-09-10

1. **The blackout gate was never wired, so it was never measured.**
   `edge/gates.py:in_earnings_blackout` exists; `config.py:666` says "not yet
   wired into the scan/alert path"; `scripts/backtest/wf_components.py:91`
   lists it under `INERT_COMPONENTS` ("never wired into the scan or backtest
   path"), and both fold runs (`results/2026-07-26-edge-folds.md:47`,
   `results/2026-08-08-level-lifecycle-folds.md:38`) record it the same way.
   **Its pre-registration budget is untouched** — it is not in the closed table.
2. **The gate cannot be replayed as written.** `in_earnings_blackout` accepts
   `now=` and ignores it (`gates.py:40-47`); `_default_days_to_earnings` and
   `events.get_next_earnings_date` both use `dt.date.today()`. No as-of lookup
   exists.
3. **The existing earnings warning is on the wrong rule and the wrong
   surfaces.** `scan_run.py:636-655` computes `earnings_within_window(ticker,
   max_holding_days)` and `explain.py:141-146` renders "⚠️ Earnings … inside hold
   window". On a 3m–9m horizon nearly every stock has a report inside the hold,
   so the line is noise there. It reaches both alert layouts
   (`alert_embeds.py:217` puts the explanation in the description regardless of
   layout), but **not** the simple alert / order ticket the reader places orders
   from, not the admin, not `!liveplans`, and it is not stored on the plan.
4. **The scan path's lookup is uncached.** `get_next_earnings_date`
   (`events.py:45`) does a live Yahoo `calendar` call per alert;
   `get_next_earnings_datetime` (`events.py:71`) already caches for 6h and
   carries a time of day.
5. **Historical dates are available from the same source the live bot uses.**
   Probe, 2026-09-10, `yf.Ticker(s).get_earnings_dates(limit=40)`: AAPL, NVDA,
   KO 50 rows each back to 2014-07; PLTR 25 rows from its 2020-11 listing. Index
   is ET-aware. Times of day over AAPL/NVDA/KO/JPM/PLTR/CRM: after-close reports
   stamp **16:00**, before-open **06:00–08:00**; estimated far-future dates stamp
   15:00 (and a handful of 02:00/17:00/21:00 outliers).
6. **A pending plan's heads-up has nowhere to fire today.** `trade_monitor`
   returns early when there are no open trades (`commands/scanning/loops.py:531-533`);
   v81's `run_notice_sweep` exists precisely to run in that branch.

## Decisions taken in the brainstorm (human partner, 2026-09-10)

- **Label now, measure a block.** The label ships regardless; the block is
  pre-registered through the v72 funnel and defaults on only on a Stage 3 PASS.
- **The label shows only on the trading session before the report and on the
  report day** — trading sessions, not calendar days (a Monday report labels on
  Friday and Monday).
- **It replaces the hold-window line**; there is no entry-time warning for long
  holds any more.
- **Open and pending plans get a pushed heads-up** on the session before the
  report, through the execution feed.
- **Historical data source: Yahoo**, cached to CSV — the same source as live, so
  the measured rule is the rule that runs.

This is item 3 of a four-spec sequence the partner chose the same day:
**v82 earnings awareness → book autopsy → exit harvest → plan dossier** (see
"Follow-on").

## Design

### D1. One source of truth — `swingbot/core/market/earnings_calendar.py` (new)

Every earnings question in the bot and the instrument goes through this module;
nothing else computes days-to-earnings.

- `Report` — frozen dataclass: `date: dt.date`, `timing: "before_open" |
  "after_close" | "unconfirmed"`.
- `classify_timing(ts_et: dt.datetime) -> str` — ET time of day `< 09:30` →
  `before_open`; `>= 16:00` → `after_close`; anything in between →
  `unconfirmed`. The 15:00 estimated-date stamp therefore reads `unconfirmed`,
  never "before the close".
- `reaction_session(report, calendar) -> dt.date` — the first session whose
  **open** can price the report: the report date for `before_open`, the next
  session for `after_close` **and for `unconfirmed`** (after-close is the modal
  stamp in the probe; the count of unconfirmed rows is reported by the
  instrument, never silently absorbed).
- `next_report(ticker, asof: dt.datetime, *, source) -> Report | None` — the
  earliest report whose reaction session is on or after `asof`'s session.
  ETFs → `None` (`universe.is_etf`, as today). Two sources behind one signature:
  `LiveSource` (wraps `events.get_next_earnings_datetime`, 6h cache) and
  `CsvSource` (reads `market_data/earnings/<SYM>.csv`, Phase B).
- `sessions_to_reaction(ticker, asof, *, source, calendar) -> int | None` —
  forward session count from `asof`'s session to the reaction session (next
  session = 1, same session = 0). **The live gate (C1) and the instrument (B3)
  both call this; the exposure rule exists once.**
- `earnings_label(ticker, now, *, source=LiveSource) -> Label | None` —
  trading sessions from `now`'s session to the **report date** ∈ {0, 1} → a
  `Label(date, timing, sessions)`; else `None`.

`in_earnings_blackout` is re-expressed over `sessions_to_reaction` with its
`now=` honoured; `_default_days_to_earnings` is deleted. `earnings_within_window`
loses its only caller (D3) and is deleted with its test.

### D2. Trading sessions — `swingbot/core/market/session.py`

- `NYSE_HOLIDAYS: frozenset[dt.date]` — full-day closures 2018 through
  **2030**, matching `opex.LAST_YEAR_COVERED`, following `opex.py:53`'s
  `_FRIDAY_HOLIDAYS` precedent (static, commented source), not a new
  dependency. `opex.py` is **not edited**; a test asserts
  `_FRIDAY_HOLIDAYS` equals this table's 2026+ Fridays, so the two cannot
  disagree.
- One class, `SessionCalendar(sessions)`, with two constructors:
  `nyse_calendar()` (live) and `SessionCalendar.from_bar_index(index)`
  (the instrument's cached SPY bars, exact for history). `sessions_between`
  rolls an `asof` date **back** to its session (a Saturday reads as Friday)
  and a target **forward** (a Saturday report reacts on Monday).
- A guard test fails once `today` is within 90 days of the table's last
  covered date — the table runs out loudly, not silently — and a second test
  asserts the table matches the cached SPY bar index from 2018-06-01 to the
  cache's end.

### D3. The label — every surface calls `earnings_label`, none recompute

Wording (sessions = 1 never says "tomorrow", because Friday → Monday is one
session):

- report day: `⚠️ Earnings today — after close` / `before open` / `time not confirmed`
- session before: `⚠️ Earnings Mon Sep 14 (next session) — after close`

| Surface | Change |
|---|---|
| Discord alert, both layouts | `scan_run.py:636-655` calls `earnings_label` instead of `earnings_within_window`; `explain.py:141-146` renders the label line instead of the hold-window line |
| v81 order ticket (`execution_embeds`) | the same line, below the order block |
| `!liveplans` (`commands/plans.py:_plan_line`) | suffix `· ⚠️ ER today` / `· ⚠️ ER next session` |
| `/api/v1` plan and trade rows (`admin/queries.py:62`), trade detail | `earnings: {date, timing, sessions} \| null`, computed **per request** from the live source — never from the stored date, because companies reschedule |
| Trades list (`trades.columns.ts`, Ticker cell) | warning chip `ER today` / `ER next` — no new column |
| Trade detail header (`trade-detail.ts:106-109`) | the same chip beside the tier/quality chips |

The admin computes labels for at most the rows on the current page, through the
6h cache; a cold cache for a page of 50 rows warms in the background the way
`watchlist._next_earnings` already does (`warm_earnings_cache_background`) and
returns `null` for that request rather than blocking it.

### D4. The heads-up notice

- `plan_manager.run_earnings_sweep(now) -> list[PlanEvent]`, called from
  `trade_monitor` **beside `run_notice_sweep`**, so it runs in the
  no-open-trades branch too.
- On the first sweep inside the regular session (`session.is_regular_session`)
  of the session before a ticker's **report date**, every PENDING / ACTIVE /
  PARTIAL plan on that ticker emits one `earnings_ahead` event, delivered
  through v81's ledger (`NOTICE_EVENTS` gains `"earnings_ahead"`).
- **Wording states the bot's plan is unchanged**, with the working levels:
  `NVDA reports Tue Sep 15 after close. Bot plan unchanged — stop 128.40 and
  target 141.20 stay as they are.` It is information, never an instruction the
  paper book is not following.
- **Once per plan per report:** `TradePlanV2.earnings_notified_for: str | None`
  holds the report date (ISO) already notified. A plan whose own alert already
  carried the label is stamped at alert time and gets no notice.
- **A stale heads-up is dropped, not resent.** v81 re-sends undelivered notices
  for `NOTICE_RESEND_DAYS = 5`; an `earnings_ahead` notice is instead dropped
  (one warning) once its reaction session has opened.

### D5. Stored on the plan

`TradePlanV2` gains two optional fields, default `None`:

- `next_earnings_date: str | None` — the report date known at plan creation.
  An audit field: it lets the book autopsy split closed trades by earnings
  exposure. Nothing renders it.
- `earnings_notified_for: str | None` — D4's dedup stamp.

`plan_to_dict` (`dataclasses.asdict`) and `plan_from_dict` (known fields,
defaults for missing — `plan_types.py:92-104`) round-trip both with no
migration; a pre-v82 plan loads with `None`. **v67 note:** tasks P2-07/P2-08
(`plans` repository and dual write) must carry both columns — Plan A adds that
note to v67's `_2b` part.

### D6. Failure handling

- Yahoo returns nothing / raises → `None` → no label, no notice, never an
  exception into a scan or the sweep (wrapped like `refresh_snapshot`).
- Misses are counted: `earnings_lookup_failed` joins the scan-summary counters
  next to `filtered_by_rr` (`scan_run.py:290`), so a Yahoo outage shows as a
  number, not as a quiet absence of labels.

## Phase B — the pre-registration

**Committed before any TRAIN look.** Everything in this section is frozen by
this spec's commit; changing any of it is a new pre-registration.

### B1. Hypothesis

Setups signalled shortly before an earnings reaction session underperform,
because the plan has had no time to reach break-even or TP1 before the gap
decides it. Removing them raises win rate without costing expectancy.

### B2. Exposure rule

A signal bar at session `s` for ticker `T` is **exposed at K** iff
`1 <= sessions_to_reaction(T, s) <= K` (D1). It keys on the **signal bar** —
where the live gate acts, at plan creation — never on the fill. A signal bar on
the reaction session itself (0) is not exposed: that bar's open already priced
the report. ETFs and bars with no known report are **not exposed** (fail-open,
identical to live) and stay in both arms.

**Grid:** `K ∈ {1, 2, 3, 5}`.

### B3. Instrument — `scripts/backtest/measure_earnings_blackout.py` (new)

- **Data:** `scripts/data/fetch_earnings_dates.py` writes
  `market_data/earnings/<SYM>.csv` (`report_ts_et, timing`) for every ticker in
  `data/backtest_cache` (89 at 2026-09-10), and prints per-ticker coverage.
- **Populations — both that the live gate touches**, one arms file per stage,
  each row an `ArmTrade`:
  - the confluence replay: `replay_scenarios` → `simulate_exit(scale_out=True)`
    → `arm_trade_from_plan` (the `make_v68_fixture.py` shape);
  - the strategy backtests: `run_backtest(..., exit_model="v2", scale_out=True,
    tp2_mode="levels", frictions=True)` per strategy → `arm_trade_from_backtest`,
    keyed on the **signal** bar — `BacktestTrade.entry_date` is already the
    signal bar, `str(df.index[i].date())` with `i` drawn from the entry-signal
    index (`backtest.py:268-270`, `:339`, `:415`), the same bar
    `replay_scenarios` yields as `i`.
  All 10 horizons, `SAMPLE_EVERY = 1`, all cached tickers.
- **One pass, post-hoc filter.** Each row records `sessions_to_reaction` once;
  the K arms are arithmetic over that table (v68's one-pass argument).
- **Two replay runs, never three.** Run 1 covers 2018-06-01..2023-12-31 once;
  Stages 0–2 read date slices of it. Run 2 covers 2024-01-01..2025-12-31 and is
  started **only** after Stage 2 passes.
- **Cost, stated so nobody is surprised:** scaled from the v72 smoke
  (6465.5s per fold-year, 72 tickers × 10 horizons, confluence leg), Run 1's
  confluence leg is ~12h at 89 tickers and Run 2's ~4.5h; the strategy leg is
  measured by the instrument's own dry run and written into the plan before
  dispatch. Both runs go to `backtest-runner`, resumable per ticker, printing a
  flushed percent figure to a progress log deleted on completion.

### B4. Stages (v72 funnel; no constant changes)

Stage numbering follows `backtest-methodology.md`; 0 and 1 both read only
fold-train, so their order is immaterial to contamination.

1. **Stage 1 — selection.** On the **earliest fold's train window,
   2018-06-01..2020-12-31** only — it precedes all three fold-test years, so no
   test year informs the choice. `K` is **eligible** iff (a) the removed rows'
   win rate < the retained rows' win rate **and** the removed rows'
   expectancy <= 0 (clause 6's mechanism), (b) alert-volume cut <= 25%
   (clause 4), (c) `ΔExpR >= −0.01R` (clause 2's margin). Among eligible `K`,
   select the greatest mix-standardised `ΔWR`; ties → the smaller `K`. The
   selected `K` must pass `plateau_report` (`PLATEAU_TOLERANCE_R = 0.03`) over
   the grid's expectancies. **No eligible K, or a spike → the measurement is
   finished, negative.**
2. **Stage 0 — MDE,** on the selected `K`: `validate_component.py --stage mde`
   with the Stage 1 train effect, `observed_days` = the train window's length,
   `target_days = 730`. Below MDE → **refused, budget intact.** Plausible at
   K = 1–2, where only ~1.6–3% of stock signals are exposed (≈ K/63 of sessions).
3. **Stage 2 — walk-forward,** selected `K` only, fold-test 2021 / 2022 / 2023:
   `gate_win_rate` — >= 2 of 3 folds improving, no fold worse than
   `GATE_MAX_WR_DEGRADATION_PP = 1.0`, per-fold N >= 30.
4. **Stage 3 — VALIDATION, one shot,** 2024-01-01..2025-12-31: all six clauses;
   a missing permutation p is a FAIL. **The permutation is a calendar shift,
   not `permutation_test.py`** (that script shifts entries through
   `run_folds` and cannot see a post-hoc filter): n = 200, seed 42, each
   permutation draws one shift `s ~ U[20, 200)` sessions and moves every
   ticker's reaction positions by `s` (mod calendar length); covered rows'
   distances are recomputed; the statistic is mix-standardised ΔWR; `p` = the
   share of permuted ΔWR `>=` the real ΔWR.

### B5. Integrity guards

- **Coverage floor:** known reports must cover >= 90% of stock signal bars in a
  stage's window. Below it the stage stops and records "instrument
  insufficient" — **budget intact**, no verdict on the hypothesis.
- **Recorded limitations,** quoted in every results doc: report dates are
  normally announced weeks ahead, but a late reschedule is mild lookahead; the
  universe is today's cached tickers (survivorship); `unconfirmed` rows are
  counted per stage.
- **No other search can touch it.** `EARNINGS_BLACKOUT_DAYS` sits in
  `_SEARCH_CLASSES["searchable"]` today (`config.py:893`) — a v75-style grid
  could sweep it. C2 moves the renamed field to **`frozen`** (`config.py:900`,
  beside the R:R band: a value fixed by pre-registration, not a tuning knob), so
  no config grid sweeps it outside this pre-registration.
- **Every outcome is written down:** `docs/superpowers/results/` per stage, and
  a row in `backtest-methodology.md`'s closed-pre-registrations table on PASS,
  FAIL, REFUSED or instrument-insufficient alike.

## Phase C — wiring (Plan A)

- **C1.** The blackout gate is wired in `scan_run.py` directly after the RS gate
  (`:416-426`), same shape: blocked items `continue`, counted as
  `filtered_by_earnings` in the scan summary. It calls
  `sessions_to_reaction(..., source=LiveSource)` — the B2 rule verbatim.
- **C2.** `EARNINGS_BLACKOUT_DAYS` is renamed `EARNINGS_BLACKOUT_SESSIONS`
  (the unit changed; a field named "days" that counts sessions is a trap). Default
  **0**, max 5, help text rewritten, moved from `_SEARCH_CLASSES["searchable"]`
  to `"frozen"` (B5). It was
  never wired, so no behaviour changes; the plan checks production's `.env` for
  the old key and mirrors any removal back per `working-conventions.md`.
- **C3.** `wf_components.py`'s `INERT_COMPONENTS` entry is replaced with a
  pointer to B3's instrument (the replay harness still does not call
  `scan_run.py`; the instrument is the measurement, not `wf_components`).
- **C4.** The default flips from 0 to the selected `K` **only** on a Stage 3
  PASS, in its own release commit. Blocked plans never reach the execution
  feed; their count is visible in the scan summary.

## Parallelisation

Two plans from this spec.

- **Plan B — measurement (starts now; no v81 dependency).**
  - **Sequential:** B-foundation first — `earnings_calendar.py`, `session.py`'s
    holiday table and `SessionCalendar`, the `in_earnings_blackout` rewrite. Every
    later task in both plans consumes `sessions_to_reaction`/`earnings_label`.
  - **Group B1 (parallel after foundation):** `fetch_earnings_dates.py`;
    `measure_earnings_blackout.py` — disjoint files, and the instrument consumes
    the CSV *format* frozen in this spec, not the fetch script.
  - **Sequential:** Run 1 after both; Stages 1 → 0 → 2 in that order; Run 2 and
    Stage 3 only after Stage 2 passes.
- **Plan A — awareness and wiring (after v81 merges and after Plan B's
  foundation).**
  - **Group A1 (parallel):** `explain.py` + `scan_run.py` label call and C1
    gate (one task — same file); `commands/plans.py`; `admin/queries.py` +
    frontend chip (API field before the chip, one task); `TradePlanV2` fields +
    v67 note.
  - **Sequential:** the ticket line after v81 (edits `execution_embeds`);
    `run_earnings_sweep` after the `TradePlanV2` fields (consumes
    `earnings_notified_for`) and after the ticket (shares the renderer); C2/C3
    after C1.

## Verification

- Pure-function tests with a fixed `now`: Friday → Monday report is 1 session;
  a holiday is skipped; `before_open` / `after_close` / `unconfirmed` (incl. the
  15:00 stamp); reaction session per timing; ETF → `None`; `now=` honoured.
- Calendar agreement: `NYSE_HOLIDAYS` vs the SPY bar index, 2018–2025.
- Sweep: fires once per plan per report; skips CLOSED; runs with zero open
  trades; a plan whose alert carried the label is not re-notified; a notice past
  its reaction session is dropped, not resent.
- The hold-window line is gone (`explain` test); the ticket and `!liveplans`
  carry the label on the two sessions only.
- Frontend spec for the chip; API test for `earnings: null` on a cold cache.
- Instrument: a fixture ticker with hand-placed reports produces the expected
  exposed rows at each K; arms JSON loads through `validate_component.load_arms`.
- **One full suite run per plan, as its final task** (`document-conventions.md`).

## Planning findings (Plan B, 2026-09-10) — part of the pre-registration

Recorded in the commit that adds the measurement plan
(`docs/superpowers/plans/implemented/2026-09-10-v82-earnings-measurement_0-index.md`),
before any data was fetched or replayed. Where these differ from the sections
above, these win.

1. **Stage 3's permutation** is the calendar shift written into B4 above.
2. **The rename moves into Plan B.** `EARNINGS_BLACKOUT_DAYS` is not just a
   config field: `ScanParams.earnings_blackout_days` (`scan_params.py:31,76`),
   `.env.example:410-412`, `wf_components.py:91` and
   `test_knob_observability.py:13` (whose `EXEMPT` must be `searchable`) all
   carry it. Plan B's M3 renames it to `EARNINGS_BLACKOUT_SESSIONS` everywhere,
   moves it to `frozen`, and rewrites `in_earnings_blackout` over B2's rule —
   unwired, default 0, so no behaviour change. **Plan A keeps only C1 (wiring)
   and C4.** Plan B's own release is `ui patch` (the Settings field's label and
   unit change); the spec-level `Bump:` above remains Plan A's.
3. **Live lookups need past reports too.** `get_next_earnings_datetime`
   filters to timestamps `>= now`, so on a before-open report's own day it has
   already dropped that report. `LiveSource` reads a new cached
   `events.get_earnings_datetimes(ticker)` (recent past and upcoming).
4. **The exposure arithmetic exists once:**
   `earnings_calendar.next_reaction_distance(asof_pos, reaction_positions)` and
   `is_exposed(distance, k)`. The live gate, `sessions_to_reaction` and the
   instrument all call them.
5. **Confluence rows are relabelled `confluence:<strategy>`.** `ArmTrade.key` is
   `(ticker, strategy, horizon, entry_date)` and `stratum` is
   `(strategy, horizon)`; a confluence plan carries a real strategy name, so
   without the prefix it could pair with, or pool into, a strategy backtest's
   row.
6. **`BacktestTrade.entry_date` is already the signal bar**
   (`backtest.py:268-270`, `:339`, `:415`).
7. **Coverage is measured over stock trade rows** (each row is one signal bar
   for one strategy/horizon); a stock row is covered when its signal session
   lies inside its ticker's first-to-last known reaction session.
8. **Stage 1 runs before Stage 0** — the MDE check needs the selected K's
   train effect. Both read only 2018-06-01..2020-12-31 (945 days observed,
   730 targeted).
9. **The VALIDATION lock is enforced in code:** the instrument refuses to
   replay 2024–25 unless handed a Stage 2 results doc reading
   `**Overall: PASS**`, and refuses to permute if the SPY calendar changed
   since that replay.
10. **Frictions differ by leg** — confluence exits through `simulate_exit`
    (no frictions), strategies through `run_backtest(frictions=True)`.
    Mix-standardisation within strata keeps each leg's win rate internal;
    recorded as a limitation in every results doc.
11. **`data/backtest_cache/` is untracked**, so a worktree has no SPY bars: the
    SPY-agreement test skips there and runs on `main` after the merge.

## Follow-on (recorded, not in scope)

- **Book autopsy (next spec).** Split the 2026-09-10 production book (N=782,
  WR 53.5%, ExpR −0.136R, 80% confluence-sourced — v78 §1) by source, before/after
  v64 (2026-08-28), hold time, and — once D5 has accumulated — earnings exposure.
  A lead found while designing this spec: `trade_monitor` runs
  `check_near_tp_timeout`, which **closes a stalled trade early as a win at the
  live price** (`loops.py:506-509`, `:562-570`). It is a candidate explanation for
  the ~2h median hold against 2w–9m horizons and the 0.429 median exit
  efficiency on winners; the autopsy should split the book by that close reason
  before the exit-harvest spec is written.
- **Exit harvest,** then **plan dossier** (the latter after v81 merges; it edits
  the ticket).
