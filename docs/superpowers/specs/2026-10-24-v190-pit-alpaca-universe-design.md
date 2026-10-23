# v190 — Point-in-time S&P 500 on Alpaca bars: an 11× wider training universe, TRAIN 2017–2023, a fresh 2026 holdout

**Version:** ui 1.35.1 · bot 2.15.0 (at writing)
**Bump:** bot patch. The window constants move into one module and the backtest entry points gain a store switch and a holdout guard. Nothing the live bot alerts on or the admin UI shows changes, except the TRAIN/VALIDATION labels where calibration prints them.
**Edge:** none (integrity). It buys statistical power and removes survivorship from the funnel's population. It does not change what is traded, and its re-baseline is a description that decides nothing.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, quant-researcher
**Status:** spec written 2026-10-24 from a brainstorm with the partner (2026-10-23), design approved in chat. The partner's answers are marked *(partner)*; Claude's calls are marked *(Claude's call)* and listed again at the end.

## Why

The funnel that decides every pre-registration (Stage 0 MDE → Stage 1 TRAIN → folds → validation) runs on the watchlist store: about 75 tickers, TRAIN 2020-01-01..2023-12-31. The idea screen (Stage −2) runs on a different population, the point-in-time S&P 500 2010–2019 from the yfinance cache `data/backtest_cache_ext` (848 members, 626 cached). The two disagree in size by an order of magnitude, and most deaths in the ledger are the small one being unable to see anything:

- v129 arm B: UNDERPOWERED at Stage 0, 168 rows per cell on 50 tickers, paired MDE 0.1755R against the 0.10R ceiling.
- v122 dry-up gate, v135 headroom veto, v180 Turtle Soup structural arm: NO-LIFT at Stage 0 on 72–75 tickers.
- The 2026-10-08 ledger review (49 of 57 pre-registrations dead) ranked "effects 10–100× below MDE on 72 tickers" third among root causes.
- The screen's one strong pass (`screen-uptrend_pullback`, N = 26,912, ΔExpR +0.37R, 9/9 years) and `turtle_soup` (SCREEN-PASS) were measured on the wide population. Nothing downstream can follow them there.

Alpaca's SIP history (the source the live bot and the v162 store already use) serves bars from 2016-01-04 for S&P members that were later **delisted**. A 2026-10-23 probe returned full series up to the exit date for TWTR, XLNX, ATVI, SIVB, FRC, CELG and CTXS. So the funnel can run on the point-in-time index from 2016 on the same vendor it already trusts, with survivorship removed. No paid data is needed.

The probe also found the trap this spec has to handle. **MON's bars run to 2022-12 although Monsanto left in mid-2018**: the symbol was reused. Some names in the membership file will have bars that belong to a different issuer.

Validation is spent: 2024–2025 is tainted for selection (`backtest-methodology.md` § Windows). Bars from 2026-01-01 have informed no selection decision yet, so the partner chose to fence them off now, before the wider universe makes reading them tempting.

## Goals

1. **A local point-in-time history store.** Alpaca daily, hourly and 15-min bars for all 848 `sp500_pit` members from 2016-01-04, under `data/market_data_pit/`, on this laptop *(partner: download to the local repo, not the Hetzner VM)*. All three timeframes *(partner)*.
2. **Integrity before use.** A per-member coverage report against membership spans, the existing vendor identity check against `backtest_cache_ext`, and a reused-symbol check. A name or span that fails is excluded with a stated reason, never silently dropped or kept.
3. **An explicit switch, never a silent widening.** Backtest entry points read the PIT store only when asked. A run that does not ask sees exactly the universe it sees today.
4. **TRAIN = 2017-01-01..2023-12-31** *(partner)*, with 2016 as indicator warm-up, defined once in a single windows module instead of ~20 literals.
5. **HOLDOUT = 2026-01-01 onward** *(partner)*. No tuning, selection or screen reads it. Each component gets one pre-registered shot, enforced by a guard.
6. **A describe-only, powered re-baseline** *(partner)*. Every live strategy and confluence runs on the PIT store over the new TRAIN, with N, WR and ExpR per strategy and horizon, the per-year split and the paired MDE each now reaches, next to today's watchlist baseline. It is recorded as a description of the new instrument, and it is the baseline later pre-registrations cite.

## Non-goals

- **No badge re-scoring** and no change to which strategies alert *(partner: describe only, decide nothing)*. A later spec may pre-register moving badges to the PIT basis.
- **No change to the live watchlist** or anything the bot scans or posts.
- **No production change.** The PIT store does not go to the VM, and the VM gets no cron for it *(partner)*. The live `data/market_data/` store on the VM and here stays as it is.
- **No paid data, no 2010–2015 on Alpaca bars** (Alpaca starts in 2016). The idea screen keeps its 2010–2019 yfinance population; moving the screen is a separate decision.
- **No re-run of any closed pre-registration**, on the new store or otherwise. Every closed row stays closed (v162 rule: a new dataset resets no budget).
- Not here, queued for their own specs: the screened exit shape as a mandatory funnel arm, the RSI(2) uptrend pullback strategy, the badge-basis decision.

## Anti-goals (a failure even if everything "works")

- Any default backtest, report or measurement script whose ticker list grows because the PIT store exists. `training_data.available_tickers()` returns every manifest ticker, and a dozen scripts take it as their universe. Writing PIT names into `data/market_data/` would have done exactly this, which is why the store has its own root.
- A PIT run without membership masking. That is a survivor-free store used as a lookahead universe.
- Any number from the re-baseline quoted as a lift, used to select a cell, or used to argue a badge up or down.
- Reading a single 2026 bar in a tuning or selection run.

## Design

### §1 The store: `data/market_data_pit/`

- Same layout and manifests as the v162 store (`<root>/<timeframe>/<TICKER>.csv`, `_manifest.json` per timeframe). Written by the existing `scripts/data/fetch_alpaca_history.py` with `--root data/market_data_pit --tickers <848 members> --backtest-dir data/backtest_cache_ext`. Git-ignored (`.gitignore`, landed with this spec).
- **Three passes, daily first** *(Claude's call)*: daily for all members, then hourly, then 15-min. The first pass measured about a minute per ticker for daily plus the start of hourly, so the 15-min pass is the long one (expect a day or more of wall time). Daily alone unblocks §5, and each pass resumes where a killed run stopped (atomic writes, per-ticker manifests).
- **Guards unchanged**: the US-regular-session refusal, the 3 GB free-disk floor, 120 requests a minute. The key is shared with the live bot on the VM, and the 120/min ceiling was designed to sit beside the live scan.
- **Refresh on demand**: `--mode update` against the same root, run locally when a study needs fresher bars. There is no schedule. The live bot never reads this store.
- The plan adds a thin wrapper (`scripts/data/fetch_pit_history.py` or a `--universe sp500_pit` flag on the fetcher; the builder picks) so the 848-name list comes from `data/universe/sp500_pit.json`, not a pasted comma list. It must produce the same files as the manual run already in progress.
- The initial backfill was started on 2026-10-24 (daily pass first) before this spec committed. The plan's first data task verifies and completes it instead of starting over.

### §2 Integrity: coverage, vendor identity, reused symbols

A report script (`scripts/data/check_pit_store.py`) writes `data/market_data_pit/_integrity.json` and a Markdown summary into `docs/superpowers/results/`. Per member:

1. **Coverage.** For each membership span clipped to 2016-01-04..today: expected trading sessions (`swingbot/core/market/session.py` calendar), daily bars present, share present, and the first and last bar. A span under 95% coverage *(Claude's call)* is listed. Its signal dates are masked out, and the rest of the ticker stays usable.
2. **Vendor identity.** The fetcher already runs `identity.identity_check` against `backtest_cache_ext` and records a status in the manifest. The report lists every non-`ok` status. Names with no yfinance reference (the ~220 the ext cache lacks, mostly delisted) are reported as `no-reference`, not as failures.
3. **Reused symbol.** The MON case. Flag a ticker when, within its membership span ± 320 sessions (the warm-up the regime gate reads), either:
   - its Alpaca series diverges from the yfinance reference by more than the identity check's tolerance where both exist, or
   - with no reference, it has a session-to-session break that looks like an issuer change: an absolute close-to-close move over 50% together with a ≥ 10× shift in 50-day median volume or price level that does not revert within 20 sessions *(Claude's call; thresholds are the builder's to calibrate against MON and the probe names, recorded in the frozen block of the report, never tuned on outcomes)*.

   A flagged span is cut at the break (bars on the far side excluded), with the reason recorded. The mask already stops signals after a member's exit, but bars *before* a member joined feed its indicators, so a symbol reused before entry would contaminate them.
4. **Renamed members** (FB→META style). The membership file and Alpaca may use different symbols. The report lists every member with no bars at all. The plan maps renames found that way through one small committed table (`data/universe/symbol_aliases.json`), and lists the rest as `no-bars`.

**Exclusions are data, not code.** Each excluded name or span lands in `_integrity.json` with its reason, and `training_data` reads it the way it reads `excluded` today. `training_data.exclusion_lines()` prints them on every PIT run.

### §3 Selecting the store: one explicit switch

- `training_data`'s selection gains a store choice: the watchlist store (`data/market_data/`, the default, unchanged) or the PIT store. It is selected by `--store pit` on the backtest entry points that already take `--data-source`, or by `TRAINING_STORE=pit`. A `*_pit` universe name (`--universe sp500_pit`) **implies** the PIT store. Asking for the PIT store with a non-`_pit` universe is refused *(Claude's call: a survivor-free store without the mask is the anti-goal above)*.
- Every result's provenance sidecar records `store: watchlist | pit` beside `data_source`.
- Regression pin: a test runs the default selection with the PIT store present on disk and asserts `available_tickers()` and a smoke backtest's universe are byte-identical to the run without it.

### §4 Windows: one module, new TRAIN, a guarded HOLDOUT

- New `swingbot/core/backtesting/windows.py` holds `WARMUP_START = 2016-01-04`, `TRAIN = 2017-01-01..2023-12-31`, `VALIDATION_TAINTED = 2024-01-01..2025-12-31` and `HOLDOUT_START = 2026-01-01`, plus the fold-train span. The current `2018-06-01..2022-12-31` widens to start at 2017-01-01 *(Claude's call)*.
- **Who reads it.** The generic entry points: `run_backtest_range.py --train/--validation`, `tune_strategy.py`, `wf_run.py`/`backtest_wf.py` folds, the calibration window labels (`swingbot/core/analytics/calibration.py:283`), and any report that labels a window generically.
- **Who does not.** The `measure_*`, `parity_*` and other scripts that implement one closed or recorded pre-registration keep their frozen literals, because they describe what was run *(Claude's call)*. A test lists them as exempt, so a new script can't copy a literal unnoticed.
- **Events count from 2017-01-01, and only on bars whose indicators are computable.** The regime gate needs about 320 bars, so in practice a ticker's first counted signal falls around Q2 2017. The re-baseline reports each strategy's first counted date, so nobody mistakes seven calendar years for seven years of events.
- **The 2020–2023 era stays addressable** (`--window train-2020`) so the re-baseline can put both side by side. Closed ledger rows keep the window they were run on.
- **Holdout guard.** Any backtest, tuning, screen or measurement path that would read a bar dated on or after `HOLDOUT_START` refuses, unless it is passed `--holdout <ledger-id>` naming a pre-registration whose frozen block is committed. The run writes a holdout-spend record (ledger id, commit, timestamp, store), and a second spend of the same id refuses. Live scanning, charts, the admin UI and paper-trade bookkeeping are not backtest paths and are untouched. The guard sits where windows resolve into a date range, not in the bar loader.

### §5 The re-baseline (describe-only)

- **Runs:** every live strategy (registry, both directions where they exist) and confluence, at their current frozen settings, with `--universe sp500_pit --store pit`, TRAIN 2017–2023, through the current instrument (v136 costs and fills as they stand). Long runs go to `backtest-runner`, chunked per strategy.
- **Comparison leg:** the same code on the watchlist store over TRAIN-2020 (2020–2023), so the table shows what the instrument change does: N ×, WR, ExpR, per-year.
- **Power line.** For each strategy and horizon: the paired ticker-cluster-bootstrap MDE Stage 0 would compute on each leg, and whether it now clears the 0.10R ceiling.
- **Output:** `docs/superpowers/results/2026-10-v190-pit-rebaseline.md` plus JSON, modelled on `scripts/reports/v162_rebaseline_report.py`. Every difference carries its paired 95% interval and the standing line *"describes a data change; never a lift; selects nothing"*. One ledger row tagged as a description, like v162's.

### §6 Documentation

- `docs/claude/backtest-methodology.md` § Windows: the new TRAIN, the HOLDOUT rule and guard, the store switch, and the statement that closed rows stay closed on the PIT store.
- `docs/claude/known-traps.md`: the third store, and why a default universe must never widen.
- The training-data section of `architecture.md`.
- `AGENTS.md` condensed mirror in the same commit as each `docs/claude/` change.

## Constraints

- Local only: no VM change, no cron *(partner)*. Free sources only; the Alpaca key in the local `.env` is never printed or logged *(partner)*.
- Every changed function stays under complexity 15. Every behaviour ships its own tests, edge and empty cases included (empty store, ticker with no bars, span with zero coverage, a holdout id spent twice).
- Tests never need the real store: they use small fixture stores under `tmp_path`.
- The full suite runs once, as the plan's final task.

## Left to the builder

- Wrapper shape for the 848-name fetch (§1).
- Exact reused-symbol thresholds, calibrated against MON plus the probe names and frozen in the report before any strategy result is read (§2.3).
- Where the store choice lives inside `training_data._selection()` and how `--store` threads through each entry point (§3).
- How the holdout-spend record is stored (a committed JSONL under `docs/superpowers/results/` is the obvious fit).

## Claude's calls, for the partner to check

1. Three fetch passes, daily first.
2. 95% coverage floor per membership span; below it, that span's signal dates are masked.
3. Reused-symbol detection by divergence from yfinance where a reference exists, otherwise a price/volume issuer-change break.
4. The PIT store is refused with a non-`_pit` universe.
5. Fold-train widens to start 2017-01-01.
6. Single-experiment `measure_*`/`parity_*` scripts keep their frozen window literals.
7. `Bump: bot patch` (window labels in calibration move; nothing else observable).
