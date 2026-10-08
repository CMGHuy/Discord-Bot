# v141 — Market-day report: LONG win rate and alert volume against the market's daily move

**Version:** ui 1.21.1 · bot 2.2.2 (at writing)
**Bump:** none (a report script and a pure analytics module; nothing in the live path changes)
**Edge:** none (integrity) — measurement only. It sets no threshold and changes no behaviour.
**Screen:** exempt (descriptive; registers nothing and spends no budget)
**Status:** spec written 2026-10-08; no plan yet.

## Why

Two things the partner sees in the alert channel and cannot currently check:

1. **Win rate.** LONG trades seem to win on days the market rises and lose on
   days it falls.
2. **Volume.** The bot seems to issue more LONG alerts on green days and go
   almost silent on red ones.

Nothing in the repo measures either. `swingbot/core/edge/regime2.py` classifies
the *slow* regime (SPY vs its 200-EMA × realized volatility), and that was
tested as an entry gate and closed with no gate justified
(`docs/claude/backtest-methodology.md`, the `REGIME_ALLOW` row: 0 of 44 cells
on TRAIN). The *daily* move is a different variable on a different timescale;
this is not a re-run of that closed pre-registration.

## What this is, and the two things that follow it

This spec is step 1 of three. The other two get their own spec when reached.

| Step | What | Depends on |
|---|---|---|
| 1 (this spec) | A descriptive report | — |
| 2 | An admin-UI panel showing the cuts that turned out to matter | step 1's result — no panel is built around a null |
| 3 | A gate or sizing rule on a **lagged** market variable | step 1 showing an effect; its own pre-registration through the v72 gate |

**Step 1 must not contact VALIDATION (2024-01-01..2025-12-31).** Step 3 needs
that budget intact.

## Three traps the report is built around

**Which day a trade belongs to.** Trades *closed* on a red day show a low win
rate almost by construction — stops are hit when everything falls. The
informative cut is the day a trade was *opened*, whose outcome resolves days
later. The report's headline tables attribute by open day; a close-day table
is included and labelled mechanical.

**Same-day SPY is not known at alert time.** "SPY closed +1% today" describes;
it cannot gate. The report therefore carries three forms of the market
variable and says which are usable: same-day (descriptive only), prior-day and
trailing-5-day (both known before the scan).

**Trades on one day are not independent.** Ten LONGs opened on one green day
are close to one observation. Every interval in the report is computed over
*days* (a day-level bootstrap), and every row shows its distinct-day count
beside its trade count.

## The market variable

- **Instrument:** SPY, daily bars, close-to-close percentage return.
- **Forms:** `same_day` (return of day *t*), `prior_day` (day *t−1*),
  `trailing_5d` (close *t−1* over close *t−6*). Day *t* is the trade's open
  day, or the scan's trading day for the volume half.
- **Buckets, fixed here and not tunable:** `< −1%`, `−1% .. 0`, `0 .. +1%`,
  `> +1%`. A return of exactly 0 goes to the upper of its two buckets. The
  same four cut points apply to all three forms; `trailing_5d` is reported on
  them as-is, not rescaled.
- **Slow-regime split:** every table is also shown split by `regime2`'s trend
  call (bull / bear, from `regime_series`) on day *t−1*, so a daily effect is
  not the slow regime in disguise.

## Win-rate half

Per (market form × bucket), for LONG trades:

- trade count `N`, distinct open days `D`
- win rate, with a 95% day-level bootstrap interval
- `ExpR`, with the same interval
- Spearman rank correlation between the day's market return and the day's
  mean trade R, one figure per market form

Win and R use the book's existing definitions (`swingbot/core/analytics/metrics.py`
— `win_rate`, `r_multiple`); the report does not define its own.

SHORT trades get the same tables as a mirror. A bucket with `D < 10` prints
its counts and `—` for the rates; it is not hidden.

## Volume half

**The denominator is every trading day in the window, including days with
zero alerts.** A silent day is the thing being looked for; a statistic keyed
on trades cannot see it.

Per (market form × bucket), for LONG:

- trading days `D`
- mean and median alerts per day
- share of days with zero alerts
- the same, split by strategy

## Cause

If volume falls on red days, the report says at which stage.

**Backtest (TRAIN).** Per day, two counts: raw entry signals fired, and trades
actually taken. The backtest does not replay the live scan's confidence,
relative-strength or dedup stages, so this is a two-level answer — *fewer
setups* versus *same setups, fewer taken* — and the report says so.

**Live.** Each scan's telemetry row (`data/scan_telemetry.jsonl`, written by
`scan_run.py`) carries `signals`, `alerts` and, since V118-5 (2026-10-02), a
per-direction funnel snapshot with stable stages (`short_funnel.STAGES`:
candidate, aligned, scenario, geometry, confidence, rs, plan, trade_decision,
dedup, send). The report aggregates scans to trading days and reports, per
bucket, the pass rate at each stage for the bullish direction.

The funnel has about a week of history at writing. The live cause table prints
its day count and is expected to be thin; `signals` and `alerts` go back
further and carry the live volume half on their own. The plan's first task
confirms which fields the bullish base lane actually populates and how far
back each goes, before anything is built on them.

## Data

| Source | Window | Used for |
|---|---|---|
| Backtest trades, per strategy, `run_backtest_daterange` | TRAIN 2020-01-01..2023-12-31 only | win rate, volume, two-level cause |
| Live paper book (trade log, production Postgres) | everything closed to date | win rate, volume |
| Live scan telemetry (production) | everything to date | volume, staged cause |

Backtest and live are shown side by side and **never pooled**. The live half
reads production read-only, through `scripts/ops/ssh-hetzner.sh`; it writes
nothing there.

SPY bars come from the existing CSV cache (`scripts/data/fetch_backtest_data.py`)
for the backtest half and from the bot's own market-data layer for the live half.

## Shape in the code

- **`swingbot/core/analytics/market_day.py`** — pure functions, no I/O:
  market-return forms from a SPY frame, bucketing, per-bucket trade stats,
  per-bucket day-volume stats, the day-level bootstrap. Takes plain lists and
  frames; returns plain dicts. Step 2's panel reuses it.
- **`scripts/reports/market_day_report.py`** — loads the three sources, calls
  the module, writes one markdown results file under
  `docs/superpowers/results/`. Flags: `--backtest`, `--live`, `--out`.
- **Tests:** unit tests for the module on hand-built fixtures (bucket edges,
  the zero-alert-day denominator, the prior-day shift not leaking day *t*,
  a bucket below the `D` floor). The script gets one smoke test on fixtures.

The bootstrap uses a fixed seed so the results file is reproducible.

## What the report does not do

- It selects nothing. Four fixed buckets × three forms × two directions is a
  descriptive grid; with that many cells some will look significant by chance,
  and the results file says so at the top.
- It does not touch VALIDATION, register a pre-registration, or move any
  strategy badge.
- It recommends no rule. If an effect shows on a lagged form, the results file
  names it as a candidate for step 3 and stops.

## Open point for the plan

Whether "alerts per day" on the backtest side should count per-strategy
backtest entries or a replay of the confluence scan (`scan_replay.py`). The
spec assumes per-strategy entries, because that is what the trade tables
already use; the plan's first task checks whether the replay is cheap enough
to add as a second volume column.
