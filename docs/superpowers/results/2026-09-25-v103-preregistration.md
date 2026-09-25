# v103 pre-registration -- Fibonacci level-stop (A) and continuation (C)

Registered 2026-09-25, before any cell is backtested. Committed on the v103 branch
(`2026-09-24-v103-fib-level-stop-and-continuation`) on top of `33b9ae63`. Scripts under test:
`scripts/backtest/measure_fib_v103.py` and `scripts/backtest/fib_funnel.py`, last changed at `c5e2cbc0`.
Spec: `docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md`.
Every constant below was read from those files (or the plan's Global Constraints), not from memory.

## Cells entering Stage 1 (from `2026-09-25-v103-stage0.md`)

Stage 0 closes a mechanism x direction when the loosest cell has fewer than 30 signals
(TRAIN_EXT 2010-01-01..2023-12-31, universe 73). `closed_at_stage0` is `[]` for both mechanisms, so
**nothing is closed** and all four cells enter:

| mechanism | direction | loosest cell | Stage 0 signals |
|---|---|---|---:|
| A | bullish | b = 0.1 | 1017 |
| A | bearish | b = 0.1 | 384 |
| C | bullish | d_max = 0.786 | 2102 |
| C | bearish | d_max = 0.786 | 267 |

These are signal counts, an upper bound on decided trades.

## Mechanism definitions

- **A** (`Fibonacci`): the stop sits `b` ATRs past the tested retracement level. A signal whose stop
  exceeds the 2% planned-loss cap (`risk_limits.HARD_MAX_PLANNED_LOSS_PCT = 2.0`, read through
  `capped_planned_loss_pct(h["max_risk_pct"])`) is **dropped, never capped**. Grid `b in {0.1, 0.25, 0.5}`,
  loosest 0.1. The `b = 0` cell is the reference baseline (today's swing stop): reported, never a candidate.
  Flags `FIB_LEVEL_STOP_ATR` / `FIB_LEVEL_STOP_DIRECTIONS` (`"bullish,bearish"` when b > 0, `""` at b = 0).
- **C** (`Fibonacci Continuation`): entry on the break back through the swing extreme after a held
  retracement, `d_min = 0.382 <= depth <= d_max`, `min_pullback_bars = 2`, grid `d_max in {0.5, 0.618, 0.786}`,
  loosest 0.786, extension targets, **no plan when the stop exceeds the cap**. No baseline cell.
- No regime condition and no horizon mask on either. All ten horizons (`2w`..`9m`) are pooled.

## Windows

- `TRAIN_EXT = 2010-01-01..2023-12-31`.
- `FOLD_YEARS = 2013..2023` (11 folds), anchored: fold Y trains on 2010-01-01..Y-1 and tests on year Y.
- `VALIDATION = 2024-01-01..2025-12-31`, read only by the `validation` command.

## Clauses and constants (`fib_funnel.py`)

`WR_FLOOR = 50.0`, `MIN_N_TRAIN = 30`, `MIN_N_VALIDATION = 15`, `MAX_SCRATCH_SHARE = 0.5`
(scratch+timeout share), `FOLD_MIN_N = 15`, `FOLD_POSITIVE_SHARE = 2/3`, `MIN_QUALIFYING_FOLDS = 3`,
`TRAIN_START_YEAR = 2010`, `BOOTSTRAP_SEED = 42`, `BOOTSTRAP_RESAMPLES = 10_000`
(`swingbot.core.backtesting.acceptance`).

- **Tier 1 (badge tier):** win rate >= 50, ExpR > 0, decided N >= 30 on TRAIN_EXT (>= 15 on VALIDATION),
  scratch+timeout share <= 0.5.
- **Tier 2:** ExpR > 0, **and** the ExpR bootstrap lower bound > 0, plus the same N and scratch floors.
  **No win-rate floor.** The bootstrap is `acceptance.cluster_bootstrap` over **ticker clusters** with an
  **empty baseline arm**, 10,000 resamples, seed 42, lower bound = the **2.5th percentile**
  (`100 * ALPHA / 2`).

## Stage 1 (per mechanism x direction, TRAIN_EXT, all cells collected once)

- **Plateau rule:** a cell counts only if it passes the tier **and** every grid neighbour passes the same tier.
- **Winner order:** the highest-ExpR Tier 1 plateau cell; otherwise the highest-ExpR Tier 2 plateau cell;
  otherwise none.
- VALIDATION scores on the tier Stage 1 assigned and **never changes it**.

## Stage 2 (11 anchored folds)

Per fold, re-select from the grid the cell with the highest ExpR on 2010..Y-1 among cells with N >= 30
(none qualifies means the fold is **unselected**, contributes no test result and is counted in the report).
Score the selected cell on year Y. Verdict clears when **>= 3 folds have test N >= 15 and >= 2/3 of those
have ExpR > 0**. A mechanism x direction proceeds to VALIDATION only when **Stage 1 has a winner and
Stage 2 clears**.

## Populations and arithmetic

- A-bullish: the live gate (`STRATEGY_GATES["Fibonacci"] = {"directions": ("bullish",)}`).
- A-bearish: unmasked (`gate_override(strategy, _unmasked_gates(strategy))`) plus the v93 laggard rule.
- C-bullish: unmasked (C ships `{"directions": ()}`).
- C-bearish: unmasked plus the v93 laggard rule.
- Arithmetic for every cell: `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`, `frictions=True`,
  `one_at_a_time=True`, `apply_level_lifecycle` as today.

## Data

- Extended cache `data/backtest_cache_ext` (2010-2025), checked in V103-9: nothing missing against
  `data/backtest_cache`, SPY 2010-01-04..2025-12-30. Every run sets `BACKTEST_CACHE_DIR=data/backtest_cache_ext`;
  the shared cache is never written.
- **Universe:** the production watchlist as held in the main tree's `data/watchlist.json`, 77 names, sorted,
  sha256 of the comma-joined list `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`, of which 73
  survive the liquidity/data-quality filter. The v103 worktree's own `data/watchlist.json` is a 3-ticker fixture, so
  worktree runs pass the 77 names explicitly through `--tickers` (the flag's help says "smoke runs only", but the
  list equals the default universe; a first run on the fixture gave `universe_n 3` and was discarded):
  `AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT`.
- **Survivorship bias is stated, not corrected.** The watchlist is today's, so it favours names that survived and
  grew. That biases WR and ExpR **upward in the early years**.

## Horizon disclosure

V103-9's concentration caveat: **none.** At every loosest cell the top-2-horizon share is below 80% (A bullish 60%,
A bearish 40%, C bullish 50%, C bearish 58%; `2026-09-25-v103-stage0.md`). No horizon mask, and the spec adds no
horizon clause.

## The one-shot rule

At most **one `validation` run per mechanism x direction (at most four in all)**, only at the committed evaluate
output's `validation_cell`, never at another cell, and **never again after a FAIL**. The script enforces it: both
this pre-registration and the evaluate JSON must be committed and unchanged, and it refuses to run when its
`--out` file already exists. This document enforces it too.

## Registry-row rule (decided before any score)

`emit-registry` writes one row per mechanism, and its population must equal the population the wired live gate
lets through.

- **C:** the row pools C's passing directions.
- **A:** writes the `Fibonacci` row, replacing today's (`WEAK`, N=246, 2020-2023, run 2026-09-10; quoted from the
  plan, used for no decision here), **only when** A's passing directions equal every direction
  `STRATEGY_GATES["Fibonacci"]` admits after wiring. Otherwise (for example A-bearish passes while bullish
  Fibonacci keeps its swing stop) the row would describe a subset of the live population: no A row is emitted, the
  existing row stays, and the mismatch is recorded in `docs/claude/backtest-methodology.md`.

## Not re-run

v101 #1/#2/#4, v102 confluence, the v84 1.0 extension, v31 horizon splits, and v17 `REGIME_ALLOW`.

## Tooling note

If v100 has merged, v103's funnel is self-contained and does not go through `validate_component.py`.
