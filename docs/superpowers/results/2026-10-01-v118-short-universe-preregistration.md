# v118 pre-registration — SHORT candidate universe (scan-level additive arm)

Spec: `docs/superpowers/specs/implemented/2026-10-01-v118-short-universe-swing-design.md`.
Plan: `docs/superpowers/plans/implemented/2026-10-01-v118-short-universe-swing.md` (Task V118-7).
Edge: volume.

**Written before any v118 outcome existed.** No v118 arm JSON, pilot run or
result document exists when this file is committed, and it contains no
performance figure. The instrument contract it relies on was proven first, on
fixtures only, by `tests/backtesting/test_measure_short_universe.py` and
`tests/scanning/test_short_qualify.py`. Every frozen value below is quoted from
the spec, the plan, `docs/claude/backtest-methodology.md` or the committed code.
None was chosen in this session. Where those sources do not settle a value, the
item is marked **UNFROZEN — needs partner decision**. No selection run, MDE
run, fold run or VALIDATION run may start until every UNFROZEN item is
resolved in an amendment committed to this file.

## Status: historical replay is blocked

`data/universe/sp500_sector_history.csv` does not exist. `universe.historical_short_snapshot(day)`
returns `None` without it, and the replay then records `no_snapshot` for every
decision date. With no snapshot the extra lane adds no rows, so the pilot
component equals its baseline and `measure_arms.py` refuses with
`refused:zero-diff`. **Every v118 historical measurement, the Stage −1 pilot
included, is blocked until a point-in-time sector-history source exists.** That
source must not be built by projecting today's `sp500.json` sectors backwards
(spec, "Current behavior": "Today's `sp500.json` sector field cannot be
projected backward"). No sector-history file was created or invented for this
record.

## Instrument (proven on fixtures, Stage −1 contract)

- Route: the standard producer, `scripts/backtest/measure_arms.py`, with the
  whole-scan population engine `short_universe`
  (`swingbot/core/backtesting/arms/short_universe_engine.py`). No bespoke
  instrument and no `--bespoke-instrument` reason.
- Knob: `SHORT_UNIVERSE_RESEARCH_MODE` (`off|broad|isolated`, default `off`,
  research only — the live bot reads only `SHORT_UNIVERSE_ENABLED`). It is
  classified `REACHABLE`, observed by `short_universe` only
  (`arms/reachability.py`).
- Per decision date the replay (`swingbot/core/scanning/scan_replay.py`) runs
  the live `scan_run.build_extra_candidates` over a `scan_run._short_reference`,
  the live `analyze.scan_extra_candidate` / `analyze._scan_one`, the live per-item
  gates `qualify.qualify_short_item` (direction, confirmation, sector RS, RS gate,
  v2 plan, prior-open), `dedup.dedup_scan_items`, the live sort, and one open
  trade per ticker in posting order. The exit model is `simulate_exit(...,
  scale_out=True)`. Arm rows are `ArmTrade` via `ReplayAlert.arm_trade()`.
  Rows with `not_triggered`/`no_trade` are dropped, as `ConfluenceEngine` does.
- Baseline arm: the same scan with the knob at its default (`off`), i.e. the
  base lane only. Component arm: the knob set to one mode. Both arms run over
  the identical frames, window and code hash, under one `build_stamp`.
- Fixture facts proven by tests: one PIT member is added and an ex-member with
  identical bars is absent. Base rows are identical with the lane off and on.
  An RS-gate failure adds zero rows, and a disallowed mode is excluded with
  `mode_not_allowed`. Decisions are unchanged when bars after the decision date
  are removed (truncation test). The stamped fixture blob reads `REACHABLE` in
  `validate_component.py --stage reachability`. The CLI refuses
  `refused:no-population-engine` when the engine is absent, and
  `refused:bad-knob` for a value outside `off|broad|isolated`.

### Instrument conventions (fixed by the instrument; partner to confirm)

These are how the replay stands in for live inputs it cannot have. They are
not thresholds. They apply to both arms equally.

1. **One scan per completed daily bar.** `SIGNAL_CONFIRMATION_SCANS` therefore
   counts daily bars. Live scans run every `SCAN_INTERVAL_MINUTES`.
2. **No live price.** The scenario's current price is the decision bar's close.
   This is the existing replay convention (`replay_scenarios`).
3. **Confidence track record = none.** `ScanIO.track_record` returns
   `(None, 0)`, so confidence.py uses its own assumed win rate. The live
   journal has no history for 2018–2025, and the spec forbids a fabricated
   value. The alternative, the replay's own closed trades as of the decision
   date, is supported by `ReplaySpec.track_record` but is not the frozen choice.
4. **Open-trade blocking.** A filled trade keeps its ticker open through its
   exit bar. A plan that never triggers blocks nothing after its decision date.
5. **Base sector map is point-in-time.** The base lane's sector RS uses the
   snapshot's as-of sector, never today's `sp500.json`. With no snapshot it
   falls back to ticker-only RS, the live fallback.
6. **Outside the replay:** the strategy-sourced pass (`STRATEGY_ALERTS_MODE`)
   and `MAX_ALERTS_PER_SCAN` (a delivery cap; the paper trade is logged either
   way).

## Frozen values

| Item | Frozen value | Source |
|---|---|---|
| Membership source | `data/universe/sp500_membership.csv` (fja05680/sp500, MIT), half-open `[start, end)` intervals via `pit_membership.load_intervals`; sha256 `183a57080d1414bdfa45a5a15b58aed41f86bf19cb4b9ae4788d24fc38f6dc32`, last changed in commit `9f9c315c` | spec "Measurement"; plan V118-1 |
| Membership date | as of each decision date (`universe.short_snapshot(day, live=False)`), never today's list | spec "Candidate and reference contract" |
| Base population | the standard producer universe: `windows.universe_for(stage, cached_universe())` — first 10 sorted cached tickers at `pilot`, the full cached universe × all 10 `LEGACY_HORIZONS` from `selection` on | `arms/windows.py`; methodology "acceptance funnel" |
| Extra population | PIT S&P 500 members on the decision date that are not in the base universe (base wins ties) and have a frame (`measure_arms.population_symbols()`). A member without a frame is counted `missing_frame` | spec; `short_candidates.extra_symbols` |
| Reference panel | 63-session stock-minus-SPY returns over completed, date-aligned bars, base ∪ extra frames (`build_reference_rels`); `MIN_PANEL_SYMBOLS = 5` | V118-2 code |
| Selector — broad | SPY trend (`get_market_regime`, the scan's own) bearish on the same completed date, and stock percentile in the reference panel `<= RS_LAGGARD_PERCENTILE` (25) | spec mode 1; `short_candidates._broad` |
| Selector — isolated | SPY trend not bearish, and stock 63-session return `<` its mapped sector ETF's on aligned completed bars; missing sector or ETF excludes the candidate with a count | spec mode 2; `short_candidates._isolated` |
| Downstream gates | the live ones, unchanged: bearish scenarios only, confluence/confidence requirements, RS gate (`RS_GATE`, `RS_LAGGARD_PERCENTILE` 25 on `rs_combined`), v2 plan with the 2% cap and v115 clamp, one open trade per ticker | spec "Boundaries"; `qualify.py` |
| Two mode cohorts | two separate producer runs, `SHORT_UNIVERSE_RESEARCH_MODE=broad` and `=isolated`, each with its own baseline/component pair, reported separately; one good mode may not hide a losing other mode | spec "Measurement" |
| Dedup | live `dedup.dedup_scan_items` within each lane per decision date (`DEDUP_TOLERANCE_PCT` as bound at import), then the live sort and one open trade per ticker in posting order; lanes are ticker-disjoint by construction | live scan; plan V118-3 |
| Windows | Stage −1 pilot 2018-06-01..2020-12-31 (10 tickers); Stage 0 MDE / Stage 1 selection on fold-train 2018-06..2020 / ..2021 / ..2022; Stage 2 walk-forward 2021 / 2022 / 2023; Stage 3 VALIDATION 2024-01-01..2025-12-31, **one shot** | methodology; `arms/windows.py` |
| Funnel order | reachability → MDE → TRAIN plateau → fold walk-forward → one VALIDATION, serially, each only if the previous permits | spec; methodology |
| Acceptance rule | every applicable clause of the v72 gate (`acceptance.evaluate`, `VERSION = 2`): (1) mix-standardised ΔWR > 0, one-sided p < 0.05, ticker-cluster bootstrap; (2) ΔExpR lower 95% bound > −0.01R (`NON_INFERIORITY_R`); (3) median planned RR and mean win R each fall ≤ 2% (`GEOMETRY_MAX_DROP_PCT`); (4) accepted-alert cut ≤ 25% (`VOLUME_MAX_CUT_PCT`); (5) permutation p < 0.05, n = 200 (a missing p is a FAIL); (6) mechanism — `SKIPPED` by `acceptance.py` because an additive arm is not a subset feature. A larger SHORT count alone is not a pass | spec "Measurement"; methodology |
| Work-ranking objective | pooled expectancy first; win rate and alert volume reported alongside | spec |
| Borrow fee | disclosed as a **break-even annual fee** (fraction of entry value) at which the added rows' summed R is zero: `f = Σr / Σ(entry/|entry−stop| × days_held/365)`, filled rows only, min 1 day (`scan_replay.break_even_borrow_fee`). No historical borrow availability is claimed | spec "report sensitivity … as a break-even fee" |
| Reporting | every added row separately from base rows (`ReplayAlert`: lane, mode, decision date, entry, stop, target, planned RR, outcome, R, exit date), with counts of added, unchanged, excluded (by stage/reason) and unmeasurable candidates | spec; plan V118-8 |

## UNFROZEN — needs partner decision

1. **Point-in-time sector-history source.** Which source, its licence, and the
   file `data/universe/sp500_sector_history.csv` (`ticker,start_date,end_date,sector`,
   half-open). Without it nothing can run (see Status).
2. **Extra-lane frame coverage.** The standard producer reads
   `data/backtest_cache` (about 77 tickers). Should the PIT S&P 500 members'
   daily history be fetched into that cache first? If not, the extra population
   is the intersection with today's cache. Either way, the delisted-symbol
   survivorship gap that `pit_membership.py` documents remains. This decides the
   population's size.
3. **Gate values in the measuring environment.** The replay reads the live
   gates from `config` at run time. In this session's shell, two of them differ
   from the `config.py` field defaults: `SIGNAL_CONFIRMATION_SCANS` is 2 against
   a default of 1, and `MIN_STOP_DISTANCE_PCT` is 2.0 against 1.75. Decide which
   set defines both arms: the field defaults, or production's `.env` as of a
   named date. The stamp records only the knob delta, not this base set.
4. **Costs.** `simulate_exit` R carries no slippage or commission (`SLIPPAGE_BPS`
   applies only to backtest v1 fills), and the standard producer adds none.
   Decide whether arms are scored cost-free, as every v100 producer arm is, or
   with a stated per-trade deduction.
5. **Plausible borrow-fee range.** The spec asks for sensitivity to "plausible"
   fees. The break-even formula is frozen; the fee range to report against is
   not.
6. **Stage 1 plateau for a categorical knob.** Methodology makes
   `plateau_report()` mandatory and disqualifying at Stage 1. The knob has no
   numeric grid: each mode is one cell with no neighbours. Decide how Stage 1
   applies, or whether it is skipped with a recorded reason.
7. **Instrument conventions 1–6 above.** Confirm them, or amend them before
   any outcome run. Convention 3 (no track record) and convention 1 (daily
   confirmation cadence) are the two most likely to move live-vs-replay parity.

## Compute note

The population engine runs in one process: it is cross-sectional per decision
date, not per ticker, and `--workers` does not parallelise it. In isolated mode
roughly half of the S&P members can be candidates on a given date. Each
candidate is a full `_scan_one` over the horizons, so a full-width run is
expected to be long. Hand it to `backtest-runner` with flushed progress, per
CLAUDE.md.

## Not re-run

No closed pre-registration is touched. `RS_GATE` / `RS_LAGGARD_PERCENTILE`
(v34) stay as shipped. v104 Part B, v113 and the Q-INV row (v98) are different
mechanisms and are not reopened by this record.
