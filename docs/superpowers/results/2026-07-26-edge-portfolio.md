# Edge Engine v4 — Task E51: Portfolio-level replay of the baseline system

Generated 2026-07-26, portfolio replay run took ~96 minutes (started 20:27,
finished ~22:03) collecting signals + replaying; Monte Carlo step is
sub-second (bootstrap resample, no data I/O).

**This is the baseline system, not "the adopted system."** Task E33's
fold sweep (`docs/superpowers/results/2026-07-26-edge-folds.md`) concluded
**zero components pass the pre-registered gate** —
`docs/superpowers/results/adopted_components.json` is committed as `{}`.
So every number in this doc is the existing, already-shipped strategy set
under real portfolio-level capital constraints — no new filter, sizing
model, or level source is contributing to it. If a future task adopts a
component, this doc's numbers are the "before" to compare against, not a
result that already includes something new.

## What changed to make this runnable (Task E51 code addition)

The plan's Step 2 assumed `wf_run.py --portfolio` already writes
`data/replay_r_sequence.json` for `ruin.simulate` to read. It did not, and
`portfolio_replay()` had no notion of a per-trade R-multiple list — only
portfolio-level aggregates (`equity_curve`, `final_multiple`, `max_dd_pct`,
`trades_taken`, `trades_skipped`, `trades_per_month`). Fixed additively:

- `portfolio_replay()` (`swingbot/core/backtest_wf.py`) now also returns
  `"r_multiples_taken"` — the R-multiple of every trade actually opened
  (i.e. `sig["r_multiple"]` at the moment `open_pos.append(...)` runs),
  in the same chronological order the replay loop already processes
  signals in. Skipped signals (heat/sector cap, paused throttle)
  contribute nothing to this list, by construction — it is exactly the
  fixed R-distribution `ruin.simulate()` wants to bootstrap from.
- `scripts/wf_run.py --portfolio` writes that list to
  `data/replay_r_sequence.json` (new `--r-sequence-json` flag, default
  path, pass `''` to skip).
- Two new tests in `tests/test_wf_portfolio.py` pin: (a) the list length
  equals `trades_taken` and excludes heat-cap-skipped signals, (b) order
  is preserved and a late-opened trade (freed heat) appends after the
  earlier ones.

Also confirmed (per the controller's pre-flagged gap): `--portfolio` does
**not** read `--component-json` — that flag only applies to the
non-portfolio grid-run branch. Irrelevant here since the adopted set is
`{}` anyway; ran as `python scripts/wf_run.py --portfolio --json
data/replay_result.json` with no component overrides.

## Setup

- Universe: `watchlist` — 78 symbols (`data/backtest_cache/`), 11
  strategies × 10 horizons, exit model v2 + scale-out, `tp2_mode=levels`,
  frictions ON — same tooling/config `collect_portfolio_signals` and
  `_default_run` use everywhere else in this plan (E22 baseline
  comparability).
- Window: `2021-01-01`..`2023-12-31` (the 3 anchored folds' combined test
  span — `wf_run.py --portfolio`'s own `--start`/`--end` defaults).
- Dedup: same-ticker near-duplicate guard mirroring the live scanner's
  `has_open_trade`/`has_similar_open_trade` (see `collect_portfolio_signals`
  docstring) — 1413 signals survived from the raw per-(symbol, strategy,
  horizon) trade pool.
- `portfolio_replay()` parameters used (all defaults — the call was
  `portfolio_replay(signals)`): `start_balance=10000`, `risk_pct=1.0`,
  `heat_cap_pct=6.0` (matches the frozen `PORTFOLIO_HEAT_CAP_PCT=6.0`),
  `sector_cap_pct=3.0`, `throttles=True` (drawdown throttle ladder from
  E45, via `edge.throttle.current_throttle`).
- **Note on quarter-Kelly:** this replay sizes every trade at a flat 1%
  risk, not through `edge.sizing.kelly_risk_pct`. The `KELLY_FRACTION_CAP
  = 0.25` rail lives in the live sizing path (`account.compute_position_
  size`), which `portfolio_replay` does not call — it takes `risk_pct` as
  a given input. Nothing here raises effective risk above the 6% heat cap
  or the throttle ladder; the Monte Carlo step below separately explores
  0.5/1.0/1.5% flat risk levels, all well under a quarter-Kelly ceiling
  for this system's observed edge.

## Portfolio replay results (the honest growth expectation)

| metric | value |
|---|---:|
| Signals collected (post-dedup) | 1413 |
| Trades taken | 547 |
| Trades skipped (heat/sector cap or throttle pause) | 866 |
| **Skipped-signal fraction** | **61.3%** |
| Trades / month | 15.2 |
| Final multiple (start $10,000) | 2.196x |
| Elapsed span | 2021-01-04 → 2024-01-05 (~36.0 months / 3.00 years — trailing exits push slightly past the 2023-12-31 window edge) |
| **CAGR** | **~30.0%** |
| Max drawdown | **9.88%** |

**The skipped-signal fraction is the headline most per-signal expectancy
work never shows.** Of 1413 signals the strategies actually generated
across the 3-year window, 866 (61.3%) never became a position — the
account was already at its 6% heat cap, a sector's 3% sub-cap, or paused
by the drawdown throttle. Per-signal expectancy answers "is the edge
real"; this replay answers "what would the account actually have done,"
and the answer is: a majority of the raw signal flow is structurally
unusable at this heat/sector budget. Wider heat caps or more capital
concurrency (not tested here — out of scope for E51) are the levers that
would recover some of that 61.3%, not a "better" filter.

## Monte Carlo (Task E51 Step 2 — bootstrap from the 547 taken trades' R-multiples)

`ruin.simulate(r_multiples, risk_pct=..., n_trades=1000, n_paths=2000,
seed=42)` resamples WITH REPLACEMENT from the 547 realized R-multiples this
replay's `r_multiples_taken` produced (written to
`data/replay_r_sequence.json`). **`n_trades=1000` is a fixed simulation
horizon, not this replay's 3-year window** — at 15.2 trades/month it
represents roughly 5.5 years of trading at the same pace, not the 3 years
above. Do not read the two final-multiple figures (2.196x over 3 years vs.
the Monte Carlo's 1.0%-risk 4.25x median) as contradictory; they are
different horizons by construction.

| risk_pct | p50 final multiple | p05 final multiple | max DD p50 | max DD p95 | `p_ruin` | `p_10x` |
|---:|---:|---:|---:|---:|---:|---:|
| 0.5% | 2.08x | 1.70x | 3.5% | 5.4% | 0.0% | 0.0% |
| 1.0% | 4.25x | 2.86x | 7.0% | 10.7% | 0.1% | 0.1% |
| 1.5% | 8.56x | 4.74x | 10.3% | 15.6% | 0.0% | 36.1% |

(`p_ruin`: fraction of paths whose equity ever fell below 0.5x start.
`p_10x`: fraction of paths whose equity ever reached 10x start, within the
1000-trade horizon.)

**Reading this honestly:**

- At the risk level this replay actually ran (1.0%), reaching 10x within
  ~1000 trades (~5.5 years at this system's real trade pace) happens in
  only **0.1%** of bootstrapped paths. The median outcome is 4.25x — solid
  compounding, nowhere near a 10x storyline.
- Pushing to 1.5% risk gets `p_10x` to 36.1%, but that is not a free lever:
  `max_dd_p95` moves from 10.7% to 15.6%, and this Monte Carlo is an
  idealized single-position resample — it does **not** re-apply the 6%
  heat cap or sector caps across a hypothetical multi-position book at
  1.5% per trade the way `portfolio_replay()` does at 1.0%. Reading 1.5%
  as "safe because `p_ruin` stayed near 0%" ignores that the real account
  would hit its heat cap sooner at a higher per-trade risk, which this
  simplified bootstrap cannot see.
- `p_ruin` stays at or near 0% across all three levels — the 547-trade
  realized distribution (mean R modestly positive, a meaningful cluster of
  0.0 scratches and a tail of -1.0 stops, but few outsized losers) does not
  produce a fat enough left tail to threaten a 50% drawdown at any of these
  risk levels over this many trades.

**The `!growth` ETA to 10x should be quoted from this table, not from
per-signal expectancy** (per the plan's own instruction for this task):
at the system's currently-run 1.0% flat risk, 10x is a low-probability
event within a normal multi-year horizon (`p_10x` = 0.1%); at 1.5% it
becomes plausible-but-not-favored (`p_10x` = 36.1%) at the cost of
materially deeper drawdowns and a heat-cap interaction this simplified
model does not capture. Neither number licenses promising a 10x timeline
— which is exactly the plan's own stated non-goal (see the plan's
preamble: "It will not promise a 10x timeline").

## Caveats

- **Baseline only, zero adopted components** (E33: `adopted_components.json`
  is `{}`). This doc is the "before" number, not a result of any Edge
  Engine v4 component landing in the live scan path.
- The 547-trade R-distribution is drawn from a single 3-year window
  (2021-2023) under one exit model (v2 + scale-out, `tp2_mode=levels`).
  It has not been folded, and it is NOT the 2024-2025 validation window
  (still untouched per the plan's non-negotiable budget rule).
- The Monte Carlo bootstrap treats trades as i.i.d. draws with replacement
  — it does not model correlation between concurrently-open positions
  (the real portfolio replay's heat/sector caps already constrain that at
  the 1.0% level; the Monte Carlo step does not carry those caps forward
  to the 0.5%/1.5% comparisons).
- `max_dd_pct = 9.88%` in the real replay is well inside the drawdown
  throttle ladder's designed range (E45); the throttle contributed to
  keeping the real replay's realized R-distribution from degrading during
  the 2022 window rather than the flat 1% risk alone.

## Verification

- `python -m pytest tests/test_wf_portfolio.py -v` — 6 passed (4 existing
  + 2 new for `r_multiples_taken`).
- `python -m pytest tests/ -q` — 1050 collected (995 passed, 54 skipped, 1
  failed). The 1 failure is the documented pre-existing
  `tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`
  (wall-clock dependent, carried since Task E7) — not a regression from
  this task. (Test count is higher than CLAUDE.md's "841 passed" baseline
  line because several tasks landed in this repo since that line was last
  updated; the single known failure is unchanged.)
- `python -m py_compile` clean across `bot.py`, `admin_ui.py`, and every
  `swingbot/**/*.py`.

## Raw artifacts

- `data/replay_result.json` — full `portfolio_replay()` output including
  the equity curve and `r_multiples_taken` (547 entries), gitignored (data/).
- `data/replay_r_sequence.json` — the 547 R-multiples alone, as consumed
  by `ruin.simulate`, gitignored (data/).
