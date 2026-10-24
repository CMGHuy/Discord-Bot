# v190 — Instrument v3: the point-in-time S&P 500 on Alpaca bars, research 2017–2025 on purged folds, 2026 holdout

**Version:** ui 1.35.1 · bot 2.15.0 (at writing)
**Bump:** bot patch. Adds a backtest instrument version, a training-data store and an integrity mode. The calibration window labels are extended additively, so no existing registry row changes its label. Nothing the live bot scans, alerts on or posts changes, and neither does anything the admin UI already shows.
**Edge:** none (integrity). It buys statistical power and removes survivorship from the funnel's population. It does not change what is traded, and its re-baseline is a description that decides nothing.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer, quant-researcher
**Status:** spec written 2026-10-24 from a brainstorm with the partner (2026-10-23/24), design approved in chat, and revised the same day after the staff-engineer panel found the existing v2 instrument contract (see `## Panel review`). The partner's answers are marked *(partner)*; Claude's calls are marked *(Claude's call)* and listed again at the end.

## Why

v158 built the instrument this repo's funnel should be running on. `--instrument v2` (`swingbot/core/backtesting/instrument/contract.py:112-126`) specifies:

- the point-in-time S&P 500 universe (`sp500_pit`, 848 members) with causal membership masking;
- research 2010-01-01..2025-12-31, tested with purged anchored yearly folds (test years 2014–2025, 270-day embargo);
- a sealed holdout from 2026-01-01, with frames cut at `research_end` (`run_backtest_range._instrument_frame`, `run_backtest_range.py:423-429`);
- v2 fills and costs and a causal liquidity floor.

It needs bars back to 2009-06-01 (`warmup_start`), and those exist only in the yfinance cache `data/backtest_cache_ext` (626 of 848 members cached).

Then v162 moved training data to the Alpaca SIP store. That store holds only the ~77 watchlist names and starts on 2016-01-04, so it cannot meet v2's coverage. The result is that **the funnel runs on instrument v1 and the watchlist**. The latest pre-registration, v180 Turtle Soup (`docs/superpowers/results/2026-10-23-v180-turtle-soup-result.md`), ran on instrument v1, Alpaca bars and about 134 watchlist-era tickers, with fold-train 2018-06-01..2022-12-31. Its own record calls the result a non-replication of the screen and says that "data source, universe and window all changed and this record does not say which explains it".

The ledger shows the cost:

- v129 arm B: UNDERPOWERED at Stage 0, 168 rows per cell on 50 tickers, MDE 0.1755R against the 0.10R ceiling.
- v122, v135 and v180: NO-LIFT at Stage 0 on 72–134 tickers.
- The 2026-10-08 review of 49 dead pre-registrations ranked "effects 10–100× below MDE" third among root causes.
- Meanwhile the idea screen runs on the wide PIT population (2010–2019 yfinance), where `screen-uptrend_pullback` passed at N = 26,912.

Alpaca serves bars from 2016-01-04 for S&P members that were later **delisted**. A 2026-10-23 probe returned full series up to the exit date for TWTR, XLNX, ATVI, SIVB, FRC, CELG and CTXS. So v2's contract can run on the vendor v162 chose, from 2016, with survivorship removed and no paid data. The probe also found the trap: **MON's bars run to 2022-12 although Monsanto left in mid-2018**, because the symbol was reused.

## Goals

1. **A local point-in-time Alpaca store.** Daily, hourly and 15-min bars *(partner: all three)* for all 848 `sp500_pit` members from 2016-01-04, in `data/market_data_pit/` on this laptop *(partner: the local repo, not the Hetzner VM)*.
2. **Integrity before use.** Coverage against membership spans, the existing vendor identity check, a reused-symbol check and rename mapping. Every excluded ticker, span or bar range carries a stated reason. Nothing is dropped or kept silently.
3. **Instrument v3** *(partner)*: v2's contract (fills, costs, PIT masking, causal liquidity floor, purge, embargo, holdout guard) with:
   - store = the PIT Alpaca store;
   - `warmup_start` = 2016-01-04;
   - research 2017-01-01..2025-12-31 on purged anchored yearly folds (test years 2021–2025);
   - `holdout_start` = 2026-01-01.
4. **No silent change to existing runs.** v1 and v2 runs read exactly the data they read today, and the default ticker list of every script is unchanged.
5. **A describe-only, powered re-baseline** *(partner)*: every live strategy under v3 (confluence is not run: `--scenarios` is refused under every non-v1 instrument until scan replay is wired, a follow-on spec; partner 2026-10-24), next to the same code under v1 on the watchlist, with N, WR, ExpR, the per-year and per-fold splits, and the MDE each now reaches. It is recorded as a description of the new instrument and decides nothing.

## Non-goals

- **No badge re-scoring** and no change to which strategies alert *(partner: describe only)*. A later spec may pre-register moving badges or the default instrument to v3. It may cite **only the re-baseline's power columns** (N, N ratio, MDE, coverage, first counted date), never its WR or ExpR. Any v3 badge rule is frozen before the re-baseline is read, or is scored on the 2026 holdout alone (quant-researcher finding 1).
- **No change to the default instrument.** `--instrument` stays `v1` by default (`instrument/cli.py:23-26`). Making v3 the default for new pre-registrations is a methodology decision for a follow-up, informed by the re-baseline.
- **No change to v1 or v2**: not their windows, their data, or their closed rows.
- **No production change.** The PIT store does not go to the VM, and there is no cron *(partner)*.
- **No paid data, no 2010–2015 on Alpaca bars.** The idea screen keeps its 2010–2019 yfinance population.
- **No re-run of any closed pre-registration** on v3 or the new store. The v162 rule holds: a new dataset or instrument resets no budget.
- Queued for their own specs: the screened exit shape as a mandatory funnel arm, the RSI(2) uptrend pullback strategy, and the default-instrument and badge-basis decisions.

## Anti-goals (a failure even if everything "works")

- Any existing run, default ticker list or report widening because the PIT store exists. `training_data.available_tickers()` returns every manifest ticker and a dozen scripts take it as their universe, which is why the store has its own root, and why it is selected only by instrument v3, never by universe name.
- A v3 run reading a bar dated on or after 2026-01-01, including inside a trade's exit walk.
- The survivorship fix undone by admission rules: delisted names quietly excluded because they lack a yfinance reference.
- Any re-baseline number quoted as a lift, used to select a cell, or used to argue a badge.

## Design

### §1 The store: `data/market_data_pit/`

- Same layout and manifests as the v162 store: `<root>/<timeframe>/<TICKER>.csv`, with **one** `_manifest.json` per timeframe, rewritten after each ticker. Written by `scripts/data/fetch_alpaca_history.py --root data/market_data_pit --backtest-dir data/backtest_cache_ext`. Git-ignored (`24612ce5`).
- **Three member passes, daily first** *(Claude's call)*, **then one context pass**: SPY, the regime ticker and every `data/universe/etfs.json` symbol, all three timeframes (§4). The daily pass and the context pass's daily bars unblock §5; the 15-min pass is the long one (a day or more of wall time). Each pass resumes after a kill.
- **One fetcher per root at a time.** Each process loads and rewrites the whole per-timeframe manifest (`fetch_alpaca_history.py:159-165`, `store_io.py:101-112`), so two processes on one root lose each other's entries. The plan's first data task waits for the backfill started 2026-10-24 to finish, then verifies and completes it. It never runs a concurrent pass or `--mode update` beside it.
- **Guards unchanged**: the US-regular-session refusal, the 3 GB disk floor, 120 requests a minute (the key is shared with the live bot on the VM).
- **Refresh on demand** with `--mode update`, locally, no schedule.
- **Member list from the universe file.** A `--universe sp500_pit` flag on the fetcher reads `data/universe/sp500_pit.json` instead of a pasted list, plus any rename aliases (§2.4). It writes the same files as the manual run.
- **Worktrees.** The store is git-ignored, so a worktree has none. The root resolves the way `history_store.store_root()` resolves the v162 store from a worktree (`history_store.py:38-45`). If that fallback is missing today, the plan adds it for both stores and documents it in `known-traps.md`.

### §2 Integrity: coverage, vendor identity, reused symbols, renames

A `--pit` mode on the existing `scripts/data/check_history_store.py` (which already takes `--root` and runs row-count, gap and hash checks, `check_history_store.py:180-194`). It writes `data/market_data_pit/_integrity.json` and a Markdown summary under `docs/superpowers/results/`. Its output feeds two separate mechanisms, named in §3: **frame trims** (bars removed before any indicator reads them) and **signal-span cuts** (dates removed from the membership mask).

1. **Coverage → date-range cuts, causal.** For each membership span clipped to 2016-01-04..2025-12-31, the report records expected sessions (the dates SPY has a daily bar in the PIT store; `swingbot/core/market/session.py` starts at 2018-01-01 and cannot cover 2016–2017), daily bars present, the first and last bar, and every run of missing sessions. **No whole-span verdict**, because a span-level share is lookahead: a 2017 date's admission would depend on bars missing in 2024, and the ragged tails of delisted names would push them out of the mask, rebuilding survivorship (quant-engineer finding 1). Instead:
   - each run of more than 5 consecutive missing sessions *(Claude's call)* is listed as a cut range;
   - a signal date is admitted only when the trailing 60 sessions up to and including it hold at least 95% of their expected bars *(Claude's call)*. That rule uses only bars on or before the date.

   Every cut range is listed in `_integrity.json` with its reason.
2. **Vendor identity → admission.** The fetcher records each ticker's identity status against `backtest_cache_ext` (`scripts/data/alpaca_history/identity.py:30-32`).
   - On the PIT store, `ok` and `flagged: no-reference` are both admitted. The ~220 members without a yfinance reference are mostly the delisted names that remove survivorship, and they get the reused-symbol check instead.
   - `flagged: short-overlap` and `flagged: price-mismatch` stay excluded with their reason.
   - The fetcher's bars-before-reference trim (`fetch_alpaca_history.py:209-213`) is reported per ticker as bars dropped, so that cut is visible too.
   - `identity.reference_frame` falls back to the mutable root `market_data/daily` cache when `backtest_cache_ext` lacks a file (`identity.py:73-79`). On the PIT store the reference is `backtest_cache_ext` only, no fallback. `_integrity.json` records each ticker's reference source and sha256. An aliased member's reference is read under its membership symbol.
   - The admission rule is a separate exclusion function for the PIT store. A pin keeps the watchlist store's `_manifest_exclusions` rejecting `flagged: no-reference` exactly as today (`training_data.py:64-73`), since both stores share the status strings.
3. **Reused symbol → frame trim.** The MON case. The yfinance reference ends at Monsanto's exit, so the divergence check sees nothing after the reuse. The break test therefore runs on **every** member, over the whole stored series. A break looks like an issuer change:
   - an absolute close-to-close move over 50%,
   - together with a ≥ 10× shift in 50-day median volume or in price level,
   - that does not revert within 20 sessions.

   *(Claude's call. The builder calibrates the thresholds against MON and the probe names, and freezes them in the report before any strategy result is read. They are never tuned on outcomes.)*

   Price and volume alone miss a reuse by an issuer of similar size, and they cannot use the yfinance reference for the ~220 `no-reference` names. So the report also records, for **every** member, the first and last Alpaca bar against the membership start and end:
   - A series that starts more than 20 sessions before the first membership start, or continues more than 20 sessions after the last membership end, is flagged *(Claude's call)*. The break test runs on that stretch with priority, whatever the price or volume does.
   - So does a series that continues more than 20 sessions past its yfinance reference's last bar.

   **Which side is kept** follows the membership spans, not the break:
   - A break after the last membership end keeps the bars before it, so a trade still open at exit walks only the member's own bars.
   - A break before the first membership start keeps the bars after it, so warm-up indicators never read the earlier issuer.
   - A break inside a span is listed for the builder to resolve by hand in the frozen report, never automatically.

   Both kept sides are tested. A break within 20 bars of the series' first or last bar cannot run the no-revert test. It is resolved by the start/end-gap rule above, or listed as `unresolved` and excluded.

   **Splits are not breaks.** The PIT store is fetched with `Adjustment.ALL`, recorded in provenance (`training_data.py:163-164`). The calibration set includes at least one forward split and one reverse split, both of which must not trip the detector.

   A confirmed break **trims the frame**: the dropped side's bars are removed in `training_data` before indicators or exit walks read them.
4. **Renames.** Members whose membership symbol has no Alpaca bars (FB→META style) are listed as `no-bars`. The ones the report can map go into one committed table, `data/universe/symbol_aliases.json` (membership symbol → Alpaca symbol, with a date range). Any left unmapped stay listed.

### §3 Selecting the store, and where the cuts land

- **The store choice belongs to the instrument.** `InstrumentSpec` gains a `store` field: `None` (v1 and v2 keep today's selection, `TRAINING_DATA_SOURCE`/`HISTORY_STORE_DIR` unchanged) or `"pit"` (v3). There is no new environment variable, because a stray one on the VM would break the admin Tuning page that reads `training_data` (staff-engineer finding 5). The `*_pit` universe name does **not** imply the store: v2 already pins `sp500_pit` (`run_backtest_range.py:470-488`), and v2 must not move stores.
- **`training_data` admission on the PIT store** follows §2.2. The existing `_manifest_exclusions` (`training_data.py:64-73`) keeps its current rule for the watchlist store.
- **Frame trims** (§2.3) are applied in `training_data.load_daily`, and in `history_store.load` (the intraday read path; `training_data` has no intraday loader), for the PIT store, from `_integrity.json`.
- **Signal-date cuts** (§2.1: the listed cut ranges, and dates failing the trailing-60-session coverage rule) are removed from the membership spans `pit_membership.membership_map` returns, so they reach the signal mask `run_backtest_range._spans_for` already applies. Both are causal: each is decided from bars on or before the date.
- **Provenance** records `store: watchlist | pit` and the `_integrity.json` sha256 beside `data_source` on every result.
- **Regression pins:**
  - With the PIT store on disk, the default selection, a v1 smoke run and a v2 smoke run have byte-identical ticker lists and outputs to a run without it.
  - A v3 smoke run on a fixture store applies one frame trim and one span cut.

### §4 Instrument v3

- A new `_SPECS["v3"]` in `instrument/contract.py`. It is built from v2 (same fills, costs, liquidity floor, purge, embargo) and differs only in:
  - `store="pit"`, `warmup_start="2016-01-04"`;
  - `research_start="2017-01-01"`, `research_end="2025-12-31"`, `holdout_start="2026-01-01"`;
  - `fold_test_years=2021..2025`, five folds. `folds.MIN_TRAIN_YEARS = 4` (`instrument/folds.py:33,61-63`) makes 2021 the earliest legal test year after a 2017 research start. Lowering that constant would lower a gate v2 shares, so it stays (quant-engineer finding 2). The regime gate's ~320-bar warm-up already eats into 2017, so even the 2021 fold has a little under four effective training years. The re-baseline states this.
- **Context frames come from the same store.** SPY (`config.MARKET_REGIME_TICKER`) and the sector and broad ETFs in `data/universe/etfs.json` are not S&P members. Without them `_market_frame()` returns nothing, and the as-of context is disabled or, with regime gates on, every entry is blocked (`run_backtest_range.py:104-129,132-148`). So the PIT store also holds every `etfs.json` symbol and the regime ticker, all three timeframes, fetched in a pass of their own after the member passes (one fetcher per root). A v3 run with any of them missing refuses rather than running without context. The ETF and SPY frames are cut at `research_end` like the ticker frames; today only the ticker frames are cut (`run_backtest_range.py:830`). A test asserts the as-of build reads no bar after `research_end`.
- **Intraday frames too.** If a v3 run reads the hourly or 15-min loaders, they apply the same `research_end` cut and the same §2.3 frame trims. A v3 test asserts that no intraday bar dated on or after 2026-01-01 is reachable.
- **Holdout guard.** The existing one: `cli.window_for`/`check_inside_research` refuse windows past research, and `_instrument_frame` cuts each frame at `research_end`, so no exit walk reads a 2026 bar. v3 inherits both.
- **The plan audits every instrument branch.** It goes through the 17 `spec.version` comparisons in `swingbot/` and `scripts/` (all are `== "v1"` / `!= "v1"`, so v3 already takes the v2 path; the two `resolve("v2")` hard-codes in analytics stay v2, and the 13 `require_v1` scripts keep refusing v3 as they refuse v2). A branch meaning "every instrument after v1" becomes `!= "v1"` or `live_constructor`. A branch that truly means v2 alone stays, with a comment. A test asserts v3 takes the v2 path at each site.
- **Coverage gate.** `instrument/coverage.py` and `scripts/data/check_cache_coverage.py` check v3 against the PIT store and `warmup_start` 2016-01-04.
- **Events count only on computable bars.** The regime gate needs about 320 bars, so a ticker's first counted signal falls around Q2 2017. The re-baseline reports each strategy's first counted date.
- **Calibration labels, additive only.** `_WINDOW_KINDS` (`swingbot/core/analytics/calibration.py:283-286`) gains the v3 research string. The two existing strings and their labels stay, pinned by a test on an existing-row fixture, so no production registry row changes label when this deploys.
- **Methodology.** `backtest-methodology.md` § Windows records v3 beside v1 and v2. The one-shot rules for v1's VALIDATION window and every closed row are unchanged. The § Windows entry also states:
  - **v3's fold years overlap v1's windows.** 2021–2023 lie inside v1 TRAIN, which tuned every live strategy's current settings. 2024–2025 is v1 VALIDATION, tainted and for many components already spent. For every strategy, filter or knob that exists today, all five v3 folds are **in-sample or tainted**. Their out-of-fold figures are never read as out-of-sample, and a component whose v1 VALIDATION shot is spent gets no gating use of the 2024 or 2025 folds.
  - **The 2026 holdout budget is shared by v2 and v3.** A 2026 shot spent under v2 is spent under v3. The v104 Part A retries keep their frozen 74-ticker universe and do not move to v3's 848 names.
- **The funnel does not accept v3 yet.** Stage 2 is wired for exactly three folds with an absolute `GATE_MIN_IMPROVING_FOLDS = 2` (`swingbot/core/backtesting/backtest_wf.py:30,240`). The Funnel stages table hard-codes 2021/22/23 for Stage 2 and 2024–25 for Stage 3. On five folds, "2 improving" would be looser than "2 of 3". So `validate_component.py` gains an `--instrument` flag (it has none today) and **refuses `v3`** with a message naming the follow-up methodology spec that must map the stages first. This spec freezes no v3 stage thresholds (quant-researcher finding 3).

### §5 The re-baseline (describe-only)

- **Legs.** Long runs go to `backtest-runner`, chunked per strategy. Every leg runs every live strategy (registry, both directions where they exist) at its current frozen settings; confluence is left out, because `--scenarios` is refused under v2/v3 (`_V2_UNWIRED`), and the report says so (partner 2026-10-24).
  - **Leg A:** `--instrument v3`.
  - **Leg C:** `--instrument v3` restricted to the watchlist tickers that are PIT members. This separates universe width from window, store and costs, the confound v180's record could not resolve (quant-researcher finding 6).
  - **Leg B:** `--instrument v1` on the watchlist store, TRAIN 2020–2023 (what the funnel runs today).
- **Population named.** N and MDE columns use v3's **fold-train** population, the population Stage 0 reads, on legs A and C, and TRAIN on leg B. Fold-test N is shown separately. Per fold, the table prints **effective fold-train N** as well as fold-test N, so a thin 2021 fold reads as thin.
- **Power columns (citable later):** N per leg and the A/B and C/B ratios; coverage; each strategy's first counted date; and the MDE. The MDE formula is frozen here: unpaired `mde_expectancy_r` at the observed N. The paired form needs a component arm a single-arm baseline does not have (`acceptance_harvest.py:99-122`). It is reported twice: with the ticker-cluster bootstrap, and with `week_cluster_bootstrap`, because same-week trades across 848 names are correlated and ticker clustering alone overstates the power gain. Each bootstrap names its own seed (`WEEK_BOOTSTRAP_SEED` for the week design only).
- **Descriptive columns (never citable for selection):** WR and ExpR after v2/v3 costs (leg B's v1 zero-cost figure labelled as such), with per-year and per-fold splits.
- **Forking paths.** The report prints the cell count (strategies × directions × horizons × legs), carries **no per-cell pass/fail or significance mark** against the 0.10R ceiling, and reports concentration: the share of N and of ExpR in the top two horizons. Horizon splits stay closed (v31, v101 row). Any cell later pre-registered counts this family.
- **Reproducibility.** Order: integrity report frozen → re-baseline run → result recorded. No `--mode update` runs on either store in between. `_integrity.json` records the detector thresholds, the detector code's git sha, and the manifest sha256 of all three timeframes (provenance records only the daily one today, `training_data.py:157-165`). Both legs' MDE bootstraps record their seed (`WEEK_BOOTSTRAP_SEED`).
- **Output:** `docs/superpowers/results/2026-10-v190-v3-rebaseline.md` plus JSON, modelled on `scripts/reports/v162_rebaseline_report.py`, with the standing line *"describes an instrument change; never a lift; selects nothing"* and the § Windows note that every v3 fold is in-sample or tainted for today's strategies. `docs/superpowers/results/preregistration-ledger.jsonl` has no precedent for a description row (v162 wrote none). This spec adds one with `p: null`, which `stats.ledger_qvalues` (`instrument/stats.py:226-230`) already leaves out of the BH family, pinned by a test. That needs `v3` in `stats.INSTRUMENTS` and a `DESCRIPTION` value in `stats.VERDICTS` (both closed sets).

### §6 Documentation and test plumbing

- `backtest-methodology.md` § Windows (v3); `known-traps.md` (the third store, the one-fetcher-per-root rule, worktree resolution, why a universe name never selects a store); the training-data section of `architecture.md`; and the `AGENTS.md` condensed mirror in the same commit as each `docs/claude/` change.
- `scripts/dev/select_tests.py` `DATA_READERS` gains rows for `data/market_data_pit/` (including `_integrity.json`) and `data/universe/symbol_aliases.json`.

## Constraints

- Local only, free sources, and the Alpaca key in the local `.env` is never printed or logged *(partner)*.
- Every changed function stays under complexity 15. Every behaviour ships its tests, edge and empty cases included: empty store, member with no bars, zero-coverage span, a break at the first or last bar, an alias with no bars, v3 refusing a 2026 window.
- Tests use fixture stores under `tmp_path`, never the real store.
- The full suite runs once, as the plan's final task.

## Left to the builder

- The exact reused-symbol thresholds, calibrated and frozen as in §2.3.
- How `store="pit"` threads from the instrument into `training_data`'s selection (one call when the instrument resolves, not per script). ProcessPool workers re-select the store by source name only (`cache_dir_source.pool_kwargs`), so the store choice must travel to workers explicitly.
- Whether a v3 run also needs the hourly and 15-min stores. Daily is enough for §5, and intraday-trigger strategies read the intraday loader the same way.

## Claude's calls, for the partner to check

1. Three member passes, daily first, then a context pass (SPY, regime ticker, `etfs.json`); one fetcher per root.
2. Coverage cuts at date level: runs of more than 5 missing sessions are cut, and a signal date needs at least 95% of the trailing 60 sessions present.
3. Reused-symbol detection: a price/volume break test on every member, plus series-start/end gaps of more than 20 sessions against membership; the kept side follows the membership spans.
4. `flagged: no-reference` is admitted on the PIT store (separate exclusion function; the watchlist store is unchanged).
5. The store is selected by the instrument (`store` field), never by the universe name or a new environment variable.
6. v3 fold test years 2021–2025, keeping `MIN_TRAIN_YEARS = 4`.
7. `Bump: bot patch`.

## Panel review

Spec review, 2026-10-24. Roles run serially: staff-engineer, quant-engineer, quant-researcher.

- quant-engineer 1 (BLOCKING): a span-level 95% coverage cut is lookahead and pushes delisted names out -- applied: date-range cuts plus a causal trailing-60-session rule (§2.1, §3).
- quant-engineer 2 (BLOCKING): fold years 2019..2025 violate `MIN_TRAIN_YEARS = 4` -- applied: 2021..2025, constant unchanged (§4).
- quant-engineer 3 (BLOCKING): SPY and the context ETFs are not in an 848-member store -- applied: a context pass in §1; v3 refuses without them; their frames are cut at `research_end` (§4).
- quant-engineer 4: `no-reference` names get no reuse check; similar-sized reuse missed; edge breaks -- applied: start/end gaps against membership for every member, and an edge-break rule (§2.3).
- quant-engineer 5: which side is kept; splits -- applied: the kept side follows membership; `Adjustment.ALL` recorded; split cases in calibration (§2.3).
- quant-engineer 6: the reference falls back to the mutable `market_data/daily` -- applied: `backtest_cache_ext` only on the PIT store, source and sha recorded (§2.2).
- quant-engineer 7: reproducibility -- applied: frozen order, no updates between steps, all three manifest hashes, detector sha, seeds (§5).
- quant-engineer 8: intraday frames escape the holdout cut -- applied (§4).
- quant-engineer 9: the PIT admission needs its own exclusion function and a watchlist pin -- applied (§2.2).
- quant-researcher 1 (BLOCKING): the per-strategy WR/ExpR table pre-reads any later v3 badge or default rule -- applied: follow-ups may cite power columns only; badge rules are frozen first or scored on the holdout (Non-goals).
- quant-researcher 2 (BLOCKING): v3 folds 2021–2025 overlap v1 TRAIN and tainted VALIDATION -- applied: in-sample/tainted for all current components; no gating use of 2024/2025 by spent components (§4).
- quant-researcher 3: Stage 2 is wired for 3 folds; "2 of 5" would be looser -- applied: `validate_component` refuses v3 until a methodology spec maps the stages (§4).
- quant-researcher 4: ticker-cluster MDE overstates power; seed mix-up -- applied: week-cluster MDE beside it, a seed per design (§5).
- quant-researcher 5: the paired MDE is undefined for one arm -- applied: unpaired `mde_expectancy_r`, frozen (§5).
- quant-researcher 6: legs A/B confound four changes; population unnamed -- applied: leg C (v3 on watchlist members); fold-train named (§5).
- quant-researcher 7: forking paths across cells; horizon splits closed -- applied: cell count, no per-cell marks, concentration (§5).
- quant-researcher 8: no v162 ledger precedent; BH family -- applied: `p: null`, excluded by tag, reference corrected (§5).
- quant-researcher 9: the 2026 holdout budget is shared with v2; v104 retries -- applied (§4).
- quant-researcher 10: effective fold-train N per fold -- applied (§5).

No BLOCKING finding is left open.

Plan-briefer corrections (2026-10-24), applied: expected sessions from SPY's bars (the session calendar starts 2018); `validate_component` needs a new `--instrument` flag; intraday reads go through `history_store.load`; 17 branch sites, not 24; worker processes need the store choice passed; ledger closed sets gain `v3` and `DESCRIPTION`.

- staff-engineer 1: a third window authority beside `InstrumentSpec` -- applied: the spec is now instrument v3; `windows.py` dropped.
- staff-engineer 2: `*_pit` implying the store would move v2 runs -- applied: the store is chosen by the instrument (§3), with a v2 byte-identity pin.
- staff-engineer 3: `flagged: no-reference` names excluded by `_manifest_exclusions` -- applied: §2.2 admits them on the PIT store; the bars-before-reference trim is reported.
- staff-engineer 4: span cuts had no seam -- applied: frame trims in `training_data`, signal-span cuts through `pit_membership` (§3).
- staff-engineer 5: a second environment switch beside `HISTORY_STORE_DIR`; worktree resolution -- applied: no new variable (§3); worktree resolution in §1.
- staff-engineer 6: calibration labels would move on production rows -- applied: additive mapping with a pin (§4).
- staff-engineer 7: the holdout guard would miss exit walks -- applied: v3 inherits `_instrument_frame`'s cut at `research_end` (§4).
- staff-engineer 8: `check_pit_store.py` would duplicate `check_history_store.py` -- applied: a `--pit` mode (§2).
- staff-engineer 9: `DATA_READERS` rows -- applied (§6).
- staff-engineer 10: concurrent fetchers lose manifest entries; "per-ticker manifests" was wrong -- applied (§1).
- staff-engineer 11: `Bump:` depends on 6 -- applied: patch holds with the additive mapping.
- staff-engineer 12: the rule as written misses MON; trades open at exit walk into reused bars -- applied: the break test runs on every member, and a break trims the frame (§2.3).
