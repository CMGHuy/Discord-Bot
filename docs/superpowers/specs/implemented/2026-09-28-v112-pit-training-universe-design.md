# v112 — Point-in-time S&P 500 training universe + confluence-scan re-check

**Version:** ui 1.21.0 · bot 1.10.4
**Bump:** none (amended at close-out 2026-10-04: predicted `bot patch`, but only backtest tooling and data shipped, no runtime change)
**Status (close-out 2026-10-04):** code and data shipped (merge `7395369c`). The Runbook was never run: there is no `v112-confluence-recheck` results file, so the pre-registered reading is unspent and still open. Closed by the partner's decision, not because the runbook resolved.
**Edge:** none (integrity) — it buys measurement power (N), not edge. The
confluence re-check it enables is the input to a later `Edge: expectancy` plan.

## Why

Two questions from the partner (2026-09-28): *can win rate rise without giving
up expectancy*, and *is the training data enough*.

1. **Win rate without giving up expectancy** only comes from discrimination:
   removing populations that lose more than average. The biggest candidate on
   record is the confluence scan. `results/2026-07-pooled-validation.md` has it
   at WR 53.5%, ExpR −0.171R, N=4641 (VALIDATION 2024–25, pooled over 10
   horizons). That was the book's largest population and its only negative
   one. **That figure is stale**
   (`edge-priorities.md`: badge refresh 2026-09-10, v84), and 2024–25 is
   tainted for selection. It has to be re-derived on TRAIN before anyone
   builds on it.
2. **Data size.** The extended cache is 73–74 watchlist tickers, 2010–2025.
   v92's Stage 0 minimum detectable effect was **+0.24R**, so the harness can
   only see large effects. A +3pp win-rate lift at WR≈50% needs roughly 3,400
   independent evaluated trades per arm. Widening to the S&P 500 is about 6–7×
   the setups. That is only honest if it is point-in-time: today's constituent
   list backtests 2010–2023 on the survivors, a hindsight selection that
   flatters every long-side result.

## What ships

| Piece | Where |
|---|---|
| Historical membership, `ticker,start_date,end_date` (half-open `[start,end)`, empty end = still a member), 1262 rows since 1996 | `data/universe/sp500_membership.csv`: a copy of `sp500_ticker_start_end.csv` from github.com/fja05680/sp500 (MIT, © Farrell J. Aultman), taken 2026-09-28 and current through 2026-08-18 |
| Loader, `is_member`, `members_between`, `membership_map(universe, symbols)` | `swingbot/core/marketdata/pit_membership.py` |
| `sp500_pit` universe: 848 symbols ever in the index 2010-01-01..2026-09-25 (503 current, 345 leavers) | `data/universe/sp500_pit.json`, built by `scripts/data/build_pit_universe.py` |
| Signal-date mask in the confluence replay | `backtest_scenarios.run_scenario_backtest(..., membership=)` → `_signal_in_scope` |
| Entry-date mask on the strategy path; the end-of-history liquidity floor is skipped for `_pit` runs | `run_backtest_range.py`: `_membership_for_run`, `member_trades`, `_exclusion_reason` |
| `--training-universe NAME` caches watchlist, benchmark and universe into the backtest cache, and writes `_coverage_<name>.json` | `scripts/data/fetch_backtest_data.py` |

**Opt-in by name only.** Masking is keyed off the `_pit` suffix. `watchlist`,
`sp500`, `etfs` and every other universe behave byte-for-byte as before, so no
closed pre-registration's numbers can move. `_replay_ticker` still accepts the
legacy 9-tuple.

**Why the liquidity floor is skipped for `_pit` runs.** `liquidity_reason`
reads the last 20 bars of the whole cached history. A name that later
collapsed and left the index fails that check, so dropping it reintroduces
the survivorship bias the mask exists to remove. Index membership on the
signal date is the point-in-time liquidity screen instead. Data-quality
exclusions still apply.

## Residual bias this does NOT remove (say it in every result)

- **Delisted or acquired names Yahoo no longer serves.** Most of the 345
  leavers will fail to fetch. `_coverage_sp500_pit.json` lists them, and every
  result must quote `cached/members` next to N. Fixing this needs a paid
  delisted-history source (Norgate, EODData, EODHD); that's the partner's call.
- **Ticker renames.** For example, `FB`'s membership rows are under `FB`, but
  Yahoo serves that history as `META`, whose rows start at the rename. Those
  signals are masked out: N is lost, but no bias is added.
- **End-of-history data-quality checks.** `data_quality_issues` still reads the
  last `QUALITY_CHECK_LOOKBACK_BARS`. A cash-acquired name often closes flat at
  the deal price for weeks, trips the frozen-feed rule and is dropped whole.
  The run's `excluded (bad data)` block lists these names. Count them in the
  result rather than loosening the check here.
- **Survivor-weighted sectors.** Leavers skew toward decliners, so the cached
  subset is still somewhat long-friendly. Compare the `sp500` run (survivors,
  unmasked) with the `sp500_pit` run: the gap estimates the bias.

## Runbook (production VM or the dev machine; Yahoo is unreachable from the cloud sandbox)

Every run below is TRAIN_EXT 2010-01-01..2023-12-31 only. No VALIDATION, no
2024–25 window, no holdout. They are repeatable and spend no budget. Past a
few minutes, dispatch runs to `backtest-runner` per `CLAUDE.md`. At 848
tickers × 10 horizons, run the confluence replay per universe as its own job.

```bash
# 1. Re-derive the confluence-scan pooled row on today's 74-ticker extended cache
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/run_backtest_range.py \
    --from 2010-01-01 --to 2023-12-31 --scenarios --scale-out

# 2. Widen the extended cache (existing files are skipped; new tickers get the
#    same 2010 start as the v102 ext cache, so warm-up is identical)
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py \
    --start 2010-01-01 --end 2026-09-25 --training-universe sp500_pit

# 3. Same replay, point-in-time universe, then the survivor-only universe for the bias gap
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/run_backtest_range.py \
    --from 2010-01-01 --to 2023-12-31 --scenarios --scale-out --universe sp500_pit
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/run_backtest_range.py \
    --from 2010-01-01 --to 2023-12-31 --scenarios --scale-out --universe sp500
```

Record all three tables as-is in
`docs/superpowers/results/2026-MM-DD-v112-confluence-recheck.md`, with
`cached/members` from the coverage file.

**Pre-registered reading, fixed before any run:** if the pooled
`confluence/pooled` ExpR is negative on **both** run 1 and the `sp500_pit`
run, the next spec (v113+) pre-registers muting or gating confluence-scan
alerts (`Edge: expectancy`, judged by the v72 gate's mechanism clause). If
either run is ≥ 0, the July finding is treated as a 2024–25 artefact and no
gating plan is opened on this evidence.

## Tests

- `tests/marketdata/test_pit_membership.py`: interval semantics (exclusive
  end, re-joins, open end), opt-in by `_pit` only, and the committed files'
  sanity checks.
- `tests/scripts/test_training_universe.py`: entry-date and signal-date masks,
  the legacy tuple, liquidity skip vs data-quality kept, fetch-list union, and
  the coverage file.

## Parallelisation

Code and data landed as one change; the runbook's steps 1 and 2 are
independent and can run concurrently. Step 3 needs step 2. Its two replays
are independent of each other.
