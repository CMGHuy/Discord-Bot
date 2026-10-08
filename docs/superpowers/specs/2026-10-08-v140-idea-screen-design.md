# v140 — Idea screen: a cheap information test before any plan, and a first batch of four published daily-bar effects

**Version:** ui 1.21.1 · bot 2.2.2 (at writing)
**Bump:** none (research tooling and methodology only; nothing in the live path changes)
**Edge:** expectancy — the screen is a tightening, paired with its widening: four candidate entry edges from outside the bot's current feature family, each screened once
**Screen:** exempt (this spec introduces the screen)
**Status:** spec written 2026-10-08; no plan yet.

## Why

On 2026-10-08 the pre-registration ledger held 57 rows: 5 PASS, 3 OPEN, 49
dead (NO-LIFT 35, FAIL 7, UNMEASURABLE 6, WITHDRAWN 1). Where they died: 7
at reachability, 5 at the MDE precheck, 24 at TRAIN selection, 6 at the
walk-forward folds, 6 at VALIDATION. The gates did their job. The cause sits
upstream of them.

1. **The base population carries almost no edge to filter.** Confluence on
   TRAIN is 35.59% WR / +0.0692R, pre-cost (`results/2026-10-03-v129-armZ.md:50`);
   +0.006R on VALIDATION (v68). A filter can only remove trades; it cannot
   discriminate on information the signals do not carry.
2. **Measured effects are 10–100× below the detectable size.** Paired ΔExpR
   typically 0.0002–0.009R against a paired MDE of 0.017–0.05R; ΔWR 0.3–2pp
   against 2–14pp (v122, v123, v128, v129 results docs).
3. **Every idea paid for a full spec + plan before anyone checked whether it
   carried information.** Seven plans were spent on knobs that could not
   change a trade. Ideas came mostly from price-action material (Fibonacci,
   FVG, liquidity, structure) layered on the same thin population.

The stop-geometry cause (the 2% cap binding inside daily noise) is v139's
subject; the instrument's optimism (zero costs on v2, close fills,
survivorship) is v136's. This spec covers neither.

**What this adds:** a screen that answers "does this entry predict anything,
after costs, beyond its own trend state?" in minutes, on ~506 point-in-time
S&P 500 tickers over ten years, and a hard rule that no new entry strategy
or filter gets a spec until it passes. Paired with that tightening, a first
batch of four effects with published evidence on daily bars, none of which
the bot has ever measured.

## Decisions (settled with the partner, 2026-10-08)

| Topic | Decision |
|---|---|
| Statistic | Fixed-ATR trade race vs a matched random baseline decides; forward-return drift and rank correlation are reported, not gating |
| Authority | Hard gate for new `Edge: expectancy` / `Edge: volume` specs; harvest specs cite measured MFE headroom; integrity exempt |
| Universe / window | Point-in-time S&P 500 (`data/backtest_cache_ext`, membership from `sp500_membership.csv`), 2010-01-01..2019-12-31; events count from 2011-01-01 (2010 primes ATR14, SMA200 and the 252-bar max) |
| Pass rule | ΔExpR ≥ +0.10R after costs, lower 95% bound > 0, same sign in ≥ 7 of 9 years (2011–2019), N ≥ 300 events |
| First batch | 52-week-high momentum, uptrend RSI(2) pullback, gap + volume continuation, turn-of-month |
| 2% cap | A dollar-risk rule, not a price distance — confirmed; the screen's ATR stop is consistent with it (sizing is not modelled; R is unit-free) |

## Architecture

New package `swingbot/core/backtesting/screen/`. Research tooling only:
nothing under `swingbot/` outside `backtesting/` imports it (pinned by a
test), consistent with "no ML in the live path".

| Unit | Does | Depends on |
|---|---|---|
| `ideas/__init__.py` | Registry `IDEAS: dict[str, Idea]`. `Idea` is a frozen dataclass: `name`, `events(df) -> pd.Series[bool]`, `time_cap_bars`, `direction` (`"long"` only in this batch), `params` (frozen dict, quoted into the result). | — |
| `ideas/high52w.py`, `ideas/uptrend_pullback.py`, `ideas/gap_volume.py`, `ideas/turn_of_month.py` | One pure trigger each (table below). | pandas, `indicators.py` |
| `indicators.py` | Wilder ATR14, Wilder RSI(n), SMA(n), rolling max — each value at bar *t* uses bars ≤ *t* only. | pandas |
| `race.py` | `race(df, event_idx, cap) -> RaceResult` vectorised per ticker: the fixed trade below. | numpy |
| `null.py` | `matched_null(df, events, eligible, k, seed)` — per event, K random eligible non-event bars from the same ticker, same calendar month, same trend state. | race |
| `forward.py` | Reported-only drift: mean excess forward return in ATR units at h ∈ {5, 10, 20, 60}, event minus matched null; per-year Spearman rank correlation between the event indicator and the h-bar forward return across all eligible bars. | pandas |
| `verdict.py` | Pairs events with their null mean; ΔExpR, week-clustered bootstrap (`instrument/stats.week_cluster_bootstrap`), per-year sign count, N; applies the pass rule. | `instrument/stats` |
| `scripts/backtest/screen_idea.py --idea <name>` | Loads the universe, runs one idea end to end, writes the results doc, appends the ledger row. Refuses an idea already in the ledger (one shot). | everything above |

### The fixed trade (`race.py`)

- Event on bar *t* (signal known at *t*'s close). Entry = open of *t+1*.
- `risk = 1.5 × ATR14[t]`; stop = entry − risk; target = entry + 2 × risk
  (3 × ATR14; reward:risk 2.0). Long only.
- Bars *t+1 … t+cap* are walked. On each bar: if the **open** is at or
  below the stop, exit at the open (a gap loss, can exceed −1R); else if
  the open is at or above the target, exit at the open; else if the low
  touches the stop, exit at the stop (checked first); else if the high
  touches the target, exit at the target. After bar *t+cap*, exit at its
  close.
- R = (exit − entry) / risk, then costs: entry and exit each worsened by
  `SLIPPAGE_BPS` (default 5 bps, `edge/frictions.apply_frictions`), plus
  `commission_r()` (0.02R at the default basis).
- An event whose race would read a bar after 2019-12-31, or that lacks a
  full ATR14/SMA200 warm-up, is dropped and counted (`dropped_window`,
  `dropped_warmup`) — the screen never reads 2020+.
- **One open race per ticker:** an event on a bar inside a running race is
  skipped and counted (`skipped_overlap`).

### The matched baseline (`null.py`)

- Eligible bar: ticker is an S&P 500 member at *t*
  (`pit_membership.is_member`), warm-up complete, race completes inside
  the window, and *t* is not an event bar.
- Trend state = `close[t] > SMA200[t]`.
- For each kept event: draw **K = 20** eligible bars without replacement from
  the same ticker, same `YYYY-MM`, same trend state; race each with the
  idea's cap. Fewer than 5 candidates → the event is dropped and counted
  (`dropped_no_match`). Seed 42, deterministic per (idea, ticker).
- Null bars are not subject to the one-open-race rule (they are a
  counterfactual, not a book).

### The triggers (frozen; one parameter set each, no grid)

| Idea | Event at close of *t* | Cap | Source |
|---|---|---|---|
| `high52w` | `close ≥ 0.95 × max(high, 252 bars)` and `SMA50 > SMA200`; first true bar after ≥ 20 consecutive false bars | 60 | George & Hwang (2004) |
| `uptrend_pullback` | `close > SMA200` and Wilder `RSI(2) < 10` | 10 | Connors & Alvarez (2008) |
| `gap_volume` | `open ≥ close[t−1] + 1.0 × ATR14[t−1]`, `volume ≥ 2 × mean(volume, 50 bars ending t−1)`, `close ≥ open` | 20 | earnings/news gap drift; volume as the news proxy |
| `turn_of_month` | *t* is the last trading day of its calendar month (from the ticker's own bar dates) | 4 | Ariel (1987); Lakonishok & Smidt (1988) |

## The verdict (`verdict.py`)

Per kept event *i*: `d_i = R_event_i − mean(R_null_i)`. Over all events:

1. **ΔExpR = mean(d) ≥ +0.10R.**
2. **Lower 95% bound > 0** — `week_cluster_bootstrap` over the events'
   ISO entry weeks, 10,000 resamples, seed 42, statistic `mean(d)`.
3. **Same sign in ≥ 7 of 9 calendar years (2011–2019)** — a year counts when its
   events' `mean(d) > 0`; a year with no events counts against.
4. **N ≥ 300 kept events.**

All four hold → `SCREEN-PASS`. N < 300 → `SCREEN-UNDERPOWERED` (closed like
a fail: an effect that rare on ~506 tickers cannot move the book). Anything
else → `SCREEN-FAIL`. Forward drift and rank correlation are printed beside
the verdict and never read by it.

**Why +0.10R.** Measured TRAIN→out-of-sample shrinkage has run 50–60%
(v103 A: +0.818 → +0.313). The funnel's paired MDE on the watchlist is
0.017–0.05R. An effect smaller than 0.10R at the screen is unlikely to
survive both shrinkage and the move from a fixed ATR trade to the bot's
own plan geometry.

**Disclosure in every result:** N kept and every drop/skip counter; the
point-in-time members missing from the cache (213 of 719 for 2010–2019 at
writing — survivorship that remains);
mean `R_event` and mean `R_null` separately; stop/target/timeout/gap mix for
both; per-year table of `mean(d)` and N; the forward-drift table.

## Discipline

- **One shot per idea.** `screen_idea.py` refuses an idea whose ledger id
  (`screen-<name>`) already exists. A changed parameter is a new idea with a
  new name and its own row; the BH q-value prints as today.
- **A fail is closed.** It is never re-screened with new parameters, and no
  spec is written for it.
- **A pass buys a spec, not a verdict.** The idea then runs the unchanged
  funnel (v72 for a filter such as `turn_of_month`; the badge path for a
  strategy). The screen replaces no funnel stage, and its 2010–2019 window
  overlaps only the funnel's own selection window (2018-06..2019).
- **Ledger:** `instrument/stats.VERDICTS` gains `SCREEN-PASS`,
  `SCREEN-FAIL`, `SCREEN-UNDERPOWERED`; `INSTRUMENTS` gains `screen-v1`.
  Existing rows are untouched.

## Enforcement — the `Screen:` header line

Every spec numbered **above v140** carries a `**Screen:**` header line
under `**Edge:**`:

| `Edge:` | Required `Screen:` value |
|---|---|
| `expectancy` or `volume`, adding an entry strategy or a filter | `<ledger-id> SCREEN-PASS` — the id must exist in the ledger with that verdict |
| `expectancy` moving stops/targets, or `harvest` | `harvest-headroom <path>` — a results doc quoting the measured MFE headroom (`scripts/reports/runner_headroom.py`, `analytics/exit_quality.py`) the change claims to capture; the path must exist |
| `none (integrity)` | `exempt (integrity)` |

`tests/hooks/test_spec_screen_header.py` parses every spec under
`docs/superpowers/specs/` (including `implemented/` and `no-lift/`) whose
number is greater than 140, and fails when the line is missing, a
cited ledger id is absent or not `SCREEN-PASS`, a cited headroom path does
not exist, or `exempt` appears with an `Edge:` other than `none`. Earlier
specs (v139 included) are grandfathered by number.

Documentation, all in one commit with their Codex mirror:

- `docs/claude/backtest-methodology.md` — a "Stage −2: screen" row ahead of
  the funnel table and a short section: what it measures, the pass rule,
  one shot, a pass buys a spec only.
- `docs/claude/document-conventions.md` — the `Screen:` header line.
- `CLAUDE.md` — one sentence in "Prioritise expectancy and win rate" (stays
  under 200 lines).
- `AGENTS.md` — the condensed mirror.
- `.claude/skills/new-doc/SKILL.md` and `.claude/agents/plan-writer.md` —
  the header line, then `python scripts/dev/sync_codex.py`.

## What follows a result

- Each screen writes `docs/superpowers/results/<date>-screen-<idea>.md` and
  appends its ledger row.
- Each `SCREEN-PASS` gets its own later spec (strategy or filter) carrying
  the `Screen:` line, with live-trigger/screen-trigger parity pinned by a test
  there. Not in this plan.
- Zero passes is a measured answer: these well-known effects do not survive
  costs on S&P 500 daily bars at this geometry. The next batch then moves to
  a different information source (earnings calendars, sector flows), not to
  looser bars.

## Testing

- `indicators`: values against hand-computed fixtures; a truncation guard
  (the series computed on `df[:t+1]` equals the full-frame series up to *t*).
- `race`: fixtures for stop-first on a bar touching both, target, gap
  through the stop at the open (R < −1), gap over the target, time-cap exit
  at close, costs in R, drop at the window edge, one-open-race skip.
- `null`: matches ticker, month and trend state; never samples an event
  bar; same seed → same draw; fewer than 5 candidates → dropped.
- Each idea: a lookahead guard (events on `df[:t+1]` equal the full-frame
  events up to *t*) and a known-answer fixture.
- `verdict`: each clause's boundary in both directions; UNDERPOWERED at 299
  vs 300; a year with no events counts against.
- `screen_idea.py`: refuses a second run of a ledgered idea; refuses a
  window end after 2019-12-31.
- Header test: pass, missing line, unknown ledger id, non-pass id, missing
  headroom path, `exempt` on a non-integrity spec, grandfathered spec.
- Import guard: no module under `swingbot/` outside `backtesting/` imports
  `swingbot.core.backtesting.screen`.

## Parallelisation

- **Sequential first:** `indicators.py` and the `Idea` registry (every other
  unit consumes them); then `race.py` (null and verdict consume it).
- **Group A (parallel, after race):** `null.py`, `forward.py`, the four idea
  modules — disjoint files; ideas consume only `indicators` and the registry.
- **Group B (parallel with Group A):** the ledger enum extension
  (`instrument/stats.py`), the header test plus the documentation changes —
  no shared files with the screen package.
- **Sequential last:** `verdict.py` (consumes null), then `screen_idea.py`,
  then the four screen runs **one at a time** via `backtest-runner` (shared
  ledger file), then results close-out, then the full suite.

## Out of scope

- Short-side ideas (every short population measured so far is negative).
- Building any passing idea into a strategy or gate (its own spec).
- Position sizing, the 2% dollar-risk rule, the funnel's thresholds, the
  badge win-rate floor, cross-horizon trade counting.
- Re-screening, or re-running, any closed pre-registration.
