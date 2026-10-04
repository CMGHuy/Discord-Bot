# v119 pre-registration — first bearish compression release, 10-session SHORT (broad and isolated arms)

Spec: `docs/superpowers/specs/2026-10-01-v119-short-compression-release-design.md`.
Plan: `2026-10-01-v119-short-compression-release` (Task V119-10).
Edge: expectancy.

**Written before any v119 outcome existed.** When this file is committed no
v119 arm JSON, pilot run, MDE run or result document exists, and it contains no
performance figure. The instrument was proven on synthetic fixtures only
(`tests/backtesting/test_measure_compression_short.py`,
`tests/backtesting/test_compression_reachability.py`). Every frozen value is
quoted from the spec, `docs/claude/backtest-methodology.md` or the committed
code; where those do not settle a value the item is marked **UNFROZEN — needs
partner decision**. No selection, MDE, fold or VALIDATION run may start until
every UNFROZEN item and the acceptance amendment below are resolved and the
amendment's instrument is implemented, each in a committed change to this file
or its own plan.

## The hypothesis (frozen by the spec, no grid)

A completed daily bar that is the **first bearish release from a documented
compression state** predicts a short-horizon decline. Compression and release
are the current `squeeze_breakout_confirmation` defaults, unchanged: 20-bar
Bollinger bands (2 sd) inside a 20-period Keltner channel (ATR 10, multiplier
1.5) on the preceding completed bar; the current completed bar is the first
outside state, closes below the preceding lower Bollinger band, and has volume
at least 1.5 x the prior 20-bar average (`short_entries.compression_short_frame`).
The spec forbids a grid over these defaults or an ATR-expansion `m`; each arm is
therefore **one cell**, and nothing is selected.

## Two arms, two independent decisions

| Arm | Producer knob | Mode rule (shared decision `compression_context.decide_compression_entry`) |
|---|---|---|
| broad | `COMPRESSION_SHORT_RESEARCH_MODE=broad` | SPY trend (`get_market_regime` on SPY cut to the stock's signal date) is bearish |
| isolated | `COMPRESSION_SHORT_RESEARCH_MODE=isolated` | SPY trend not bearish **and** the stock's trailing 63-session return is below its mapped sector ETF's, on date-aligned completed bars |

A candidate of the other mode is excluded `mode_not_allowed` in each run, so the
two cohorts are disjoint. Each arm is produced, gated and decided on its own;
**no pooled result may admit, rescue or fail the other arm.**

## Instrument

- Producer: `scripts/backtest/measure_arms.py` (standard v100 producer), engine
  `strategy` (`arms/strategy_engine.py`). No bespoke instrument.
- Baseline arm: the knob at its default `off` — every existing strategy, no
  compression short. Component arm: the knob set to one mode — the same rows
  plus the compression short in its scoped `("bearish", "2w")` research cell
  (`strategy_engine.RESEARCH_CELL`). The live `STRATEGY_GATES` mask stays
  `{"directions": ()}`; no other strategy's gates change. The fixture proves the
  baseline rows are a subset of the component rows (no other strategy's row moves).
- Plan constructor: the live one, `build_strategy_plan`, on bars `<= signal`.
  Exit: `simulate_exit(..., scale_out=True)`, which for this strategy walks a
  single whole-position leg with the live fill policy (`exit_sim._compression_fill`)
  and the 10-session cap (`exit_sim._hold_cap_bars`, fill bar = session 1).
- Stamped rows: `ArmTrade` (no mode or signal-date field; schema unchanged).
  Supplemental diagnostics (`StrategyEngine.compression_signals`,
  `compression_reasons`, `compression_reasons_by_mode`,
  `compression_exit_reasons`; packaged by `compression_research.measure_compression_short`)
  carry signal date, entry date, exit date, mode, exit reason, price basis and
  exclusion totals. They are reported beside the arm, never merged into it.
- As-of inputs: `compression_research.offline_context()` — cached SPY,
  `data/universe/sp500_membership.csv` (point-in-time membership),
  `data/universe/sp500_sector_history.csv` (dated sector) mapped to its SPDR ETF
  through the live table (`fetch._etf_symbol_of_sector`), and an observed-as-of
  earnings snapshot archive. A missing input rejects the candidate with its
  reason (`not_pit_member`, `missing_sector`, `unaligned_sector`,
  `earnings_unknown`, `earnings_stale`, ...). Today's facts are never projected
  backward; the final-report CSVs under `market_data/earnings` are **not** an
  as-of calendar and are never read.

## Frozen values

| Item | Frozen value | Source |
|---|---|---|
| Strategy / horizon | `First Bearish Compression Release`, bearish only, `2w` strategy horizon only; legacy `1w` cells and `HORIZONS["1w"]` untouched | spec "Intent"; `RESEARCH_CELL` |
| Signal timing | completed daily bar only; decision instant 17:00 ET on the signal date (`compression_context.decision_time_for`); stock, SPY and sector ETF aligned to the same completed date | spec "Frozen entry hypothesis" |
| Entry | resting `stop_entry` one $0.01 tick below the release bar's low (`builders.strategy_entry_reference`), valid for the next session only (`expiry_bars = 1`); no same-bar fill | spec "Pending entry" |
| Gap fill | fill at the worse of trigger and open; planned loss re-checked on the actual fill against the plan's stop ceiling — over it, the plan is cancelled (`gap_risk_cancel`, excluded, counted) | spec; `exit_sim._compression_fill` |
| Expiry | untriggered next session: cancelled (`expired`, excluded, counted) | spec |
| Stop | release-bar high + `STRUCTURE_BUFFER_ATR` x ATR(14); a stop beyond the horizon's hard ceiling rejects the plan (`over_cap_stop`), never clamps | spec; `short_builders.compression_structure` |
| Target | one whole-position target: the nearest confirmed lower support (`levels.build_level_map` on bars <= signal) whose reward:risk from the trigger lies in `[MIN_RISK_REWARD_RATIO, MAX_RISK_REWARD_RATIO]` = `[1.5, 2.5]`; no support in band = no plan (`no_support`), no synthetic ATR target | spec; `compression_structure` |
| Management | no scale-out, no runner, no break-even move (`tp1_fraction 1.0`, `breakeven_trigger_fraction 1.0`, `tp2` off) | spec; `PLAN_SHAPES` |
| Time exit | the 10th regular session of the position (fill session = 1) closes at that bar's daily `Close`, labelled `daily_close_proxy`; it is a research proxy for the official closing auction and proves nothing about live auction fills | spec "Hard 10-session exit" |
| Same-bar ordering | stop before target (engine-wide); a fill bar that reaches the stop is a loss | `exit_sim._fill_bar_exit` |
| Earnings exclusion | a known report whose reaction session falls in sessions 1–10 after the signal bar excludes the setup; the snapshot must be observed at or before the decision and at most 5 sessions old (`MAX_SNAPSHOT_AGE_SESSIONS`); missing, failed or stale = excluded, never "no earnings" | spec; `earnings_clear_for_ten_sessions` |
| Membership | S&P 500 member on the signal date by `sp500_membership.csv` (sha256 `183a57080d1414bdfa45a5a15b58aed41f86bf19cb4b9ae4788d24fc38f6dc32`); a ticker with no interval is not a member | spec "Measurement" |
| Population | **UNFROZEN — see item 3.** Proposed: the producer universe (`windows.universe_for(stage, cached_universe())`: first 10 sorted cached watchlist tickers at `pilot`, the full cached universe from `selection` on) intersected with membership on each signal date | methodology; `arms/windows.py` |
| One trade at a time | per (ticker, strategy, horizon), as every StrategyEngine cell | `StrategyEngine.iter_trades` |
| Costs | R as the standard producer scores every arm: no slippage or commission deducted, identically in both arms. The result reports, beside it, a disclosure-only net figure at the config defaults `SLIPPAGE_BPS = 5` per side and `COMMISSION_PER_TRADE = 1.0` per side over `COMMISSION_RISK_BASIS = 100.0` | `exit_sim`; config defaults |
| Borrow | not modelled and not claimed. Disclosed as the **break-even annual borrow fee** at which the cohort's summed R is zero: `f = Σr / Σ(entry/|entry − stop| × max(1, calendar days held)/365)` over filled rows (`CompressionMeasurement.break_even_borrow_fee`). No historical locate or borrow availability is assumed; the fee does not enter any gate | spec "Measurement" |
| Windows | Stage −1 pilot 2018-06-01..2020-12-31 (10 tickers); Stage 0 MDE and Stage 1 on fold-train 2018-06..2020 / ..2021 / ..2022; Stage 2 walk-forward 2021 / 2022 / 2023; Stage 3 VALIDATION 2024-01-01..2025-12-31, **one shot per arm** | methodology; `arms/windows.py` |
| Selection rule | none: one frozen cell per arm, no grid. Stage 1 is a single-cell evaluation of each arm's badge clauses on fold-train, not a choice between cells | spec "Frozen entry hypothesis" |

## Two required admission checks (per arm, both must pass before default-on)

1. **Strategy badge, `2w` cell** — on the arm's added compression rows only:
   `win_rate >= 50` (win = target touched, over win+loss), `expectancy_r > 0`
   (over all closed trades), TRAIN `N >= 30`, VALIDATION `N >= 15`, scratches +
   timeouts `<= 50%` of closed trades. Timeouts include every tenth-session
   close; that clause is not waived for a strategy whose exit is a time cap.
2. **v72 additive feature gate** for the incremental alert population, every
   applicable clause, with the instrument amended below for clauses 1 and 5 and
   the MDE statistic, and **no other change**: clause 2 profit (ΔExpR lower 95%
   bound > −0.01R, ticker-cluster bootstrap), clause 3 geometry (median planned
   RR and mean win R each fall <= 2%, pooled, **applied — a geometry failure is
   not waived because the plan shape differs**), clause 4 volume (cut <= 25%;
   an additive arm satisfies it by construction, reported anyway), clause 6
   mechanism (`SKIPPED` by `acceptance.py`: not a subset feature).

The v92 harvest gate does **not** apply: this is an entry-population change, not
an exit-only study. A later paired exit comparison on identical entries would
need its own pre-registration.

## Faithfulness review of the stamped arms — and the acceptance amendment

Checked clause by clause against `acceptance.py` (`VERSION = 2`) before any
outcome:

- **Clause 1 is blind to this arm.** `delta_standardised_win_rate` weights
  strata by the **baseline's** decided-trade mix, and `standardised_win_rate`
  drops every stratum missing from those weights. The compression short is a new
  `(strategy, horizon)` stratum that the baseline never contains, and the knob
  moves no other row (proven on the fixture), so ΔWR is **exactly 0 in every
  bootstrap draw, whatever the cohort's win rate**. The clause would FAIL by
  construction. For a filter the baseline-mix weighting removes a mix shift the
  feature should not get credit for; for an additive new strategy the mix shift
  *is* the feature.
- **Clause 5** (permutation, `p < 0.05` on ΔWR) inherits the same zero.
- **Stage 0 MDE** (`validate_component.py --stage mde`) uses the same statistic
  in `mde_paired`; with a statistic that is identically zero the paired MDE is
  degenerate and a claimed effect of 0 would read `RESOLVABLE`. It must not be
  used for this arm as is.
- Clauses 2, 3, 4 and 6 read pooled quantities and represent the additive arm
  faithfully. The badge check reads the cohort's own rows and is faithful.

**Therefore the stamped v72 arms do not faithfully represent this signal.**
Pre-registered acceptance amendment (applies to v119 only, both arms, adopted
before any outcome existed; it relaxes no threshold):

- **A1 — clause 1 instrument.** Pooled (unstandardised) ΔWR over decided trades,
  `WR(component) − WR(baseline)`, with the same ticker-cluster bootstrap (one
  draw shared by both arms), `BOOTSTRAP_RESAMPLES = 10 000`, seed 42. Pass:
  point > 0 **and** one-sided p < 0.05. Because the arms differ only by the
  added rows, this tests whether the added cohort's win rate exceeds the book's,
  weighted by its share — the question "does adding these alerts improve the
  book's win rate".
- **A2 — clause 5 instrument.** `permutation_test.py`'s circular entry shift
  (`ENTRY_SHIFT`, honoured by `StrategyEngine.iter_trades`), n = 200, seed 42,
  statistic = the A1 pooled ΔWR. Pass: p < 0.05 at VALIDATION; a missing p is a
  FAIL.
- **A3 — Stage 0 MDE statistic.** `mde_paired` with the A1 statistic; the TRAIN
  effect compared against it is the A1 point estimate on fold-train.
- **A4 — no other change.** Thresholds, windows, the bootstrap, clauses 2/3/4/6
  and the badge check are as frozen above.

A1–A3 need instrument code (a pooled ΔWR statistic selectable in
`validate_component.py` and the permutation harness) with its own tests, in its
own reviewed change. **Until that change is committed, no MDE, selection, fold
or VALIDATION run may start for either arm.** The Stage −1 pilot measures
reachability only and does not touch any clause, so it is not blocked by the
amendment — only by the input availability below.

## Inputs a historical run requires

Both arms need, for every signal date in the window: the cached stock frame,
cached SPY, PIT membership, and an earnings calendar snapshot **as observed on
or before that date**. The isolated arm additionally needs the dated sector
mapping and the cached sector-ETF frame. If any of these is absent for the
pilot window the measurement is recorded `unmeasurable` and stops before MDE;
the absence is never repaired by backfilling present-day facts into 2018–2025.

## UNFROZEN — needs partner decision

1. **As-of earnings source** for 2018–2025 (what was on the calendar on each
   signal date), its provenance and file format. Final report dates are not it.
2. **Point-in-time sector history** (`data/universe/sp500_sector_history.csv`,
   `ticker,start_date,end_date,sector`, half-open) and cached sector-ETF frames
   (the same gap that stopped v118).
3. **Population survivorship.** The producer universe is today's cached
   watchlist; membership is applied per signal date, but which members are
   studied is still chosen today. Confirm this population, or name a PIT-wide one.
4. **Gate values in the measuring environment** (as v118 item 3): the field
   defaults or production's `.env` as of a named date. The stamp records only
   the knob delta.
5. **The A1–A3 amendment** and its implementation (above).

## Stage ladder (serial; each stage only if the previous one permits)

Stage −1 reachability (pilot, per arm, `measure_arms.py --stage pilot --knob
COMPRESSION_SHORT_RESEARCH_MODE=<mode> --preregistration <this file>`, then
`validate_component.py --stage reachability`) → Stage 0 MDE (A3) → Stage 1
fold-train single-cell evaluation (badge clauses; no plateau to report because
there is no grid — recorded as a reason, not a pass) → Stage 2 walk-forward
folds (`gate_win_rate`: ≥ 2 of 3 folds improving, none worse than −1.0pp,
per-fold N ≥ 30) → Stage 3 one VALIDATION shot per arm (both admission checks).
Reachability is never evidence of edge. The live mask stays closed unless
evidence, live/replay parity, Discord delivery and the broker MOC workflow gate
(spec) all pass.

## Not re-run

No closed pre-registration is touched. Bearish Break & Retest (v104 Part A),
Bull Trap, Vol Expansion Breakdown and Earnings Gap Drift (v104 Part B),
Downtrend Overbought Fade and the legacy `1w` cells (v113) stay closed; the
compression state plus its first release is a different trigger (spec
"Correction and status").
