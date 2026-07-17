# Confluence scenario gates — VALIDATION (Task 41)

## Rule (pre-registered, quoted verbatim)

Per the plan's Global Constraints:

> VALIDATION is run **once per component** (exit model v2, confluence gates,
> each rescue strategy) with pre-registered gates; results reported as-is,
> never retuned after.

> **Acceptance gates:** `win_rate >= 80`, `expectancy_r > 0`, `N >= 15`
> (validation), `scratches+timeouts <= 50%` of closed trades.

The gates under test are `CONFLUENCE_GATES` in
`swingbot/core/backtest_scenarios.py`, adopted in Task 40. As that module's
own comment block states, these are **honestly-labeled unvalidated
defaults, not a tuned winner** — Task 39's TRAIN grid found no
`(min_confluence, min_risk_reward)` pair that qualified under the
pre-registered selection rule, so per the plan's own fallback
("if no pair qualifies, confluence source stays WEAK everywhere and Tasks
41-42 record that honestly") this VALIDATION run tests the least-restrictive
grid config, not a chosen winner. **No parameter was touched based on this
run's results** — this doc reports the real numbers as they came out.

## Setup

- VALIDATION window: `2024-01-01` .. `2025-12-31` (run once)
- Universe: full watchlist — 75 of 78 cached tickers (`CRWV`, `SNDK`, `SPCX`
  have no cached OHLCV and were skipped, same as every other harness run in
  this plan)
- Horizons: all 10 (`2w, 4w, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 9m`) — the full
  `swingbot.core.strategy_types.HORIZONS` set, matching what
  `run_backtest_range.py --scenarios` runs (not the 5-horizon subset Task
  39's grid sampled)
- Gates (`CONFLUENCE_GATES`, verbatim): `min_reward_pct=3.0,
  min_stop_distance_pct=2.0, max_stop_distance_pct=7.0, min_risk_reward=1.5,
  min_confluence=2, cooldown_bars=5`
- `scale_out=True` (same convention as the TRAIN grid and
  `run_scenario_backtest`)
- Aggregation math: identical to `backtest_scenarios._aggregate` /
  `run_backtest_range.py`'s `pool()`/`passes()` — `win_rate` over
  win+loss only, `expectancy_r` over all closed trades (win+loss+scratch+
  timeout), `excluded_share = (scratches+timeouts)/closed`

## Prerequisite fix (before this run)

`scripts/run_backtest_range.py`'s `run_scenario_mode()` (the function behind
`--scenarios`) defined its own local `SCENARIO_GATES` dict that predated
Task 40 and was **missing `min_confluence` and `cooldown_bars`** —
`replay_scenarios()` defaults those to `min_confluence=1`/`cooldown_bars=5`
when absent from the gates dict, so the literal plan command
(`run_backtest_range.py --validation --scenarios`) would have silently
validated against `min_confluence=1`, not the Task-40-adopted `2`. Fixed
(commit `6b4a976`) by importing `CONFLUENCE_GATES` from
`swingbot.core.backtest_scenarios` instead of the stale local dict, which is
now deleted. No test referenced the old constant.

## Execution note (performance)

The literal Step 1 command replays the confluence scan bar-by-bar across
the full watchlist and all 10 horizons — `~27.5s per ticker per horizon`
(Task 37's own measurement), i.e. hours serially. An earlier, uncommitted
session had already attempted exactly this and gotten 56 of 75 tickers done
(alphabetically, through `PEP`) before being abandoned mid-run; its
stdout/stderr log and per-ticker chunk files were left in the working tree.

Before trusting those 56 files, 3 were spot-checked (`AAPL`, `META`, `PEP`)
by independently recomputing them via `replay_scenarios` + `simulate_exit`
with the identical gates/window/`scale_out=True` — **all 3 matched exactly**
(win/loss/scratch/timeout sequence and `r_total` values identical, per
horizon). The remaining 56 chunks were reused as-is.

`scripts/run_confluence_validation.py` (new) resumed from those 56 chunk
files, computed the 19 remaining tickers (`PFE, PLTR, PYPL, QBTS, QCOM,
RKLB, SBUX, SHOP, SI=F, SNOW, SNPS, SOFI, STX, TSLA, UBER, UNH, V, WDC,
WMT`) in parallel via `ProcessPoolExecutor` (same replay/simulate call
shape as `tune_confluence_gates.py`'s `_ticker_worker`, one gate point
instead of a grid), writing each ticker's chunk file as it completed, then
aggregated all 75 ticker chunk files into the table below. This is a
wall-clock optimization only — the gates, window, and per-trade math are
identical to what the serial `run_backtest_range.py --validation
--scenarios` command would have produced.

Full aggregated stats: `docs/superpowers/results/confluence_validation.json`.

## Per-horizon + pooled results

| horizon | N | Win% | ExpR | Scr | TO | Excl% | PASS |
|---|---|---|---|---|---|---|---|
| 2w | 263 | 51.7 | -0.162 | 17 | 1 | 6% | FAIL |
| 4w | 336 | 53.3 | -0.145 | 14 | 1 | 4% | FAIL |
| 2m | 402 | 48.8 | -0.226 | 22 | 0 | 5% | FAIL |
| 3m | 436 | 50.5 | -0.203 | 20 | 0 | 4% | FAIL |
| 4m | 505 | 51.7 | -0.183 | 19 | 1 | 4% | FAIL |
| 5m | 501 | 55.3 | -0.141 | 27 | 0 | 5% | FAIL |
| 6m | 525 | 55.4 | -0.169 | 25 | 1 | 5% | FAIL |
| 7m | 550 | 55.5 | -0.155 | 26 | 1 | 5% | FAIL |
| 8m | 538 | 55.0 | -0.168 | 25 | 1 | 5% | FAIL |
| 9m | 585 | 55.0 | -0.163 | 27 | 1 | 5% | FAIL |
| **POOLED** | **4641** | **53.5** | **-0.171** | **222** | **7** | **5%** | **FAIL** |

(Transcribed from `scripts/run_confluence_validation.py`'s console output,
raw stats in `docs/superpowers/results/confluence_validation.json`.)

## PASS/FAIL vs gates (N floor 15)

Every horizon clears the `N >= 15` floor by a wide margin (min N=263 at 2w)
and every `excl%` is well under the 50% cap (4-6%). Neither of those was
ever in question. The two gates that matter — `win_rate >= 80` and
`expectancy_r > 0` — **fail at every horizon and pooled**:

- Best observed win_rate is 55.5% (7m), far short of the 80% bar.
- Every expectancy_r is negative (-0.141 to -0.226); none is even close to
  crossing zero.

**Pooled: FAIL. No horizon passes. Overall verdict: FAIL.**

## Honest observations

This VALIDATION run **confirms Task 39's TRAIN finding** — it does not
differ from it in any qualitative way:

- TRAIN (25-ticker sample, `min_confluence=2, min_risk_reward=0.0`, 5
  horizons): win rates 54.8-65.1%, all ExpR negative (-0.060 to -0.208),
  pooled WR=61.4%, pooled ExpR=-0.119.
- VALIDATION (75-ticker full universe, same gates, all 10 horizons):
  win rates 48.8-55.5%, all ExpR negative (-0.141 to -0.226), pooled
  WR=53.5%, pooled ExpR=-0.171.

Out-of-sample performance is not better than TRAIN — if anything it is
*worse* on both axes (win rate ~6-10pp lower, expectancy ~0.05R more
negative). This is the expected/consistent direction for an unvalidated,
never-tuned-to-pass config being run on a fresh window, not a surprise or an
anomaly. There is no evidence here that the confluence-scenario source is
usable at any horizon under these gates.

Per the plan's methodology, **no parameter is retuned in response to these
numbers**. The confluence source stays WEAK across every horizon. Tasks 39
through 41 together give a clean, honest, non-cherry-picked answer: the
confluence-scan gates as currently defined do not produce a strategy this
plan's acceptance bar would call VALIDATED, on TRAIN or on VALIDATION.

## Open item for Task 42 (not addressed here, explicitly out of scope)

Task 42's brief calls for "per-primary-strategy pooled records if N >= 15"
in addition to the per-horizon/pooled confluence-source records. The
per-ticker chunk files this run produced (and reused from the earlier
abandoned session) only capture `{"outcome", "r_total"}` per trade — no
`primary_strategy` label is retained — so `confluence_validation.json` as
written here cannot support a per-primary-strategy breakdown without
re-running the replay with that field captured. Flagged here for whoever
picks up Task 42, not fixed as part of this task.
