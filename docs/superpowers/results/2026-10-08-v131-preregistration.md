# v131 pre-registration — Fibonacci Limit (resting buy limit inside the retracement zone)

Spec: `docs/superpowers/specs/implemented/2026-10-04-v131-fib-zone-limit-entry-design.md` (last changed in `5e6d5870`).
Plan index: `docs/superpowers/plans/implemented/2026-10-04-v131-fib-zone-limit-entry_0-index.md`.

Committed before any v131 number existed. No v131 result JSON, `data/v131_*.json` or registry row exists at this commit. This document contains no performance figure; the only figures quoted are the spec's v103 reference numbers.

`scripts/backtest/measure_fib_limit.py` was last changed in `8a12e1d7` (2026-10-08); the code is merged on `main` (merge `00127e37`).

## The measurement (verbatim from the spec)

<!-- spec-quote-begin -->
## The measurement (`scripts/backtest/measure_fib_limit.py`)

The pre-registration document
(`docs/superpowers/results/YYYY-MM-DD-v131-preregistration.md`) quotes this
section, is committed before Stage 0 runs, and the script refuses to run
without it (the v103 `require_committed` pattern).

- **Data:** TRAIN 2010-01-01..2025-12-31, extended cache
  `data/backtest_cache_ext`, universe 74, bullish, all ten horizons.
- **Holdout:** 2026-01-01 to the cache end at the time of the shot. It is
  read only by the Stage 3 call, guarded by the v113 one-shot ledger pattern
  (`check_shot_allowed`).
- **Grid:** six cells, `L ∈ {0.5, 0.618}` × `N ∈ {3, 5, 10}`. Neighbours are
  adjacent values on one axis.
- **Reference arm:** today's `Fibonacci` (market entry on the bounce bar), same
  window and universe, v2 + scale-out. It is reported and never selected.
  Before any cell is read, its TRAIN 2010-01-01..2023-12-31 slice must
  reproduce v103's reference (N=815, WR 36.81%, ExpR +0.2219, universe 73).
  Any difference is explained in a committed note first.

### Stages

| Stage | Window | Rule |
|---|---|---|
| 0 volume (free) | TRAIN | The loosest cell `L=0.5, N=10` needs ≥ 30 fills. Otherwise the mechanism closes as volume-dead, budget intact. |
| 1 selection | TRAIN | Each cell is scored on `funnel.py`'s Tier 1 (WR ≥ 50, ExpR > 0, N ≥ 30, scratch+timeout share ≤ 0.5) and Tier 2 (ExpR > 0, ticker-cluster bootstrap lower bound > 0). The plateau rule applies: a cell and every grid neighbour clear the same tier, Tier 1 tried first, and the winner is the highest ExpR inside the plateau. **Profit clauses, all required of the winner:** (a) ExpR > the reference arm's ExpR; (b) fills ≥ 50% of the reference arm's trade count; (c) WR ≥ the reference arm's WR − 2.0pp. No winner closes the mechanism, budget intact. |
| 2 folds (free) | TRAIN, 13 anchored fold years 2013–2025 | `funnel.py`'s rule: `fold_pick` re-selects on `2010..year−1` with N ≥ 30, a fold qualifies at N ≥ 15, and the stage clears with ≥ 3 qualifying folds and ≥ ⅔ of them positive. Fail closes the mechanism, budget intact. |
| 3 holdout (one shot) | 2026-01-01..cache end | Only the winner, scored at the tier it held on TRAIN, plus profit clause (a) against the reference arm on the same holdout. **Sealed-thin** if fills < 15: the shot is unspent, with one retry once the cache reaches 2026-12-31 (the v104/v113 precedent). |

Total R (`N × ExpR`) is reported for every cell and the reference. It never
gates; the partner chose ExpR plus a volume floor.

**Badge.** Computed alongside and never gating. The `Fibonacci Limit` row
becomes `VALIDATED` only if the winner holds Tier 1 on the holdout. A Tier 2
pass ships the mechanism and leaves the badge `WEAK`. Today's `Fibonacci` row
is not touched.

### Disclosures (never select anything)

- Fill rate per cell, and the split between expired and cancelled unfilled
  orders.
- **Adverse-selection signature:** the share of fills stopped out within 3
  bars of the fill, per cell and for the reference arm.
- How often the 2% cap binds, priced from the limit versus from the reference
  arm's close.
- Same-bar new-high-and-fill count.
- Horizon concentration: the top-2 horizon share against the 80% disclosure
  line.
- Total R per cell.

### Features recorded for B

Each fill's `entry_context` (`edge/context.py` `FEATURE_KEYS`, computed at the
arming bar) is written into the results JSON with the fill bar index, fill
price and outcome. `stop_pct`, `stop_atr` and `planned_rr` are recomputed
from the limit price, not the close, so B reads the geometry the trade
actually had.

**This spec's results document reports no split on any recorded feature.**
B mines them under its own pre-registration. Reporting them here would let
them steer A's verdict.

### Outputs

- `docs/superpowers/results/YYYY-MM-DD-v131-preregistration.md`, committed
  before Stage 0.
- `docs/superpowers/results/YYYY-MM-DD-v131-train.md` (Stages 0–2), plus raw JSON.
- `docs/superpowers/results/YYYY-MM-DD-v131-holdout.md`, only if Stage 3 runs.
- One closed-pre-registrations row in `docs/claude/backtest-methodology.md`
  whatever the outcome.

Runs go to `backtest-runner`, chunked per horizon, with flushed per-ticker
progress and a percent figure past 15 minutes.

<!-- spec-quote-end -->

## The mechanism as implemented

Summary of the spec's "The mechanism" section (the verbatim measurement above governs):

- **Arming (all at the close of bar `t`, from `df.iloc[:t+1]`, bullish only):** (1) valid up-leg on the rolling `fib_lookback` max High / min Low, low before high (`argmax_pos > argmin_pos`); (2) swing-high bar at least 3 bars old; (3) retracement `(swing_high − close) / (swing_high − swing_low)` ≥ 0.236 and < `L`; (4) MA200 above and rising over 20 bars, close > MA50, ATR ≥ 0.7% of close, ATR ≤ 1.4× its 60-bar mean; (5) no live order on this ticker and horizon, and this leg (identified by its swing-high bar) has not already armed. Dropped from `fibonacci_entries`: the RSI band, the volume gate, the 5-bar pullback test, the bounce-bar shape.
- **Plan (priced at `t` from the limit):** entry `limit_price = swing_high − L × (swing_high − swing_low)`; stop `swing_low − 0.25 × ATR14[t]` through `_bounded_stop`/`stop_ceiling` measured from the limit (2% cap); TP1 `select_structural_target` over `fib_target_candidates`, R from the limit, inside the 1.5–2.5R band, no candidate at or above 1.5R means no order; exits are today's Fibonacci shape (v2, scale-out, `trail_atr_mult` 3.0, no TP2); order life `N` bars, `t+1 .. t+N`.
- **Fill and cancel:** fill on the first bar in `t+1 .. t+N` with `Low < limit_price`, strictly; fill price `min(Open, limit_price)`; pre-fill cancel on the first bar whose `High > swing_high` (frozen); a bar that both makes a new high and trades through the limit is a fill; fill-bar rule: a fill at or beyond the stop scores a scratch, otherwise the stop is checked on the fill bar and the target from the next bar; R from the fill price.

Values frozen from the committed code (read at this commit):

| Item | Value |
|---|---|
| `DEFAULT_PARAMS['Fibonacci Limit']` (defaults only; every cell sets L and N) | `{'L': 0.618, 'N': 5}` |
| `DEFAULT_PARAMS['Fibonacci']` (reference arm) | `{'ratios': (0.382, 0.5, 0.618), 'rsi_bull': (35, 58), 'rsi_bear': (42, 65)}` |
| `FIB_LIMIT_MIN_RETRACE` | 0.236 |
| `FIB_LIMIT_MIN_AGE` | 3 |
| `ATR_FLOOR_PCT` | 0.007 |
| `ATR_CALM_MULT` | 1.4 |
| `STRUCTURE_BUFFER_ATR` | 0.25 |
| `PLAN_SHAPES['Fibonacci Limit']` | `{'entry_type': 'limit', 'expiry_bars': 5, 'tp1_fraction': 0.5, 'breakeven_trigger_fraction': 0.5, 'limit_price': 'fib_zone'}` (`expiry_bars` is overridden by the cell's N) |
| `EXIT_V2_PARAMS['Fibonacci Limit']` | `{'trail_atr_mult': 3.0, 'tp2': False}` |
| `EXIT_V2_PARAMS['Fibonacci']` | `{'trail_atr_mult': 3.0, 'tp2': False}` |
| R:R band (`MIN_RISK_REWARD_RATIO`, `MAX_RISK_REWARD_RATIO`) | 1.5, 2.5 |
| `LEGACY_HORIZONS` | 2w, 4w, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 9m |
| `fib_lookback` per horizon | 2w 15, 4w 42, 2m 84, 3m 126, 4m 168, 5m 210, 6m 252, 7m 294, 8m 336, 9m 378 |

Script constants: TRAIN 2010-01-01..2025-12-31; reproduction window 2010-01-01..2023-12-31; v103 reference `N=815, WR 36.81%, ExpR +0.2219, universe 73`; holdout start 2026-01-01; sealed-thin reopen 2026-12-31; fold years 2013..2025; L in {0.5, 0.618}, N in {3, 5, 10}; loosest cell L=0.5, N=10; Stage 0 minimum 30 fills; clause (b) share 0.5; clause (c) slack 2.0pp; minimum holdout fills 15; early-stop bars 3; cap tolerance 0.001pp; top-2 line 0.8. `funnel.py`: WR floor 50.0, minimum N (TRAIN) 30, fold minimum N 15, scratch+timeout share at most 0.5, fold positive share 2/3, at least 3 qualifying folds, bootstrap seed 42.

## Decisions the spec left open

The plan index's ten "Decisions this plan makes where the spec is silent", verbatim:

1. **The cancel level and strict fill travel on the plan.** The spec's limit-price function returns a price only, but the simulator needs the frozen swing high and the strict-fill rule. `LIMIT_PRICERS` entries are `LimitPricer(price, cancel_level, strict_fill)`; `PLAN_SHAPES["Fibonacci Limit"]["limit_price"]` names `"fib_zone"`, whose `price` is `fib_limit_price_at` (the spec's `(df, idx, horizon, direction) -> float | None`). Two `TradePlanV2` fields carry the result (`limit_cancel_level`, `limit_strict_fill`); added fields land in `plans.doc` with no Alembic revision (`schema-evolution.md` "add").
2. **The setup's order book.** "No live order" is tracked inside `fibonacci_limit_setups` from bars ≤ `t`: an order armed at `a` is live through bar `a+N` unless a bar trades below its limit (filled — from then on `run_backtest`'s `one_at_a_time` blocks new entries while the trade is open) or above its cancel level. The market layer cannot see the planner, so an arm whose plan is rejected (stop dropped, no ≥ 1.5R target) still consumes its leg and its N-bar slot. Conservative; disclosed.
3. **The level lifecycle applies as it ships** (`LEVEL_LIFECYCLE_STOPS_ENABLED` is on by default) to both the cells and the reference, through the same `apply_level_lifecycle` call every strategy plan takes.
4. **Windows are by signal (arming) date**, as `funnel.year_rows` and `run_backtest_range.window_trades` read `entry_date`. A TRAIN order may fill and exit on a 2026 bar.
5. **"Fills"** (Stage 0, clause (b), the sealed-thin rule) = filled orders that produced a closed trade; the reference's "trade count" = its closed trades. Tier N is decided trades (`arm_rule.pooled_stats`).
6. **Stopped out within 3 bars** = outcome `loss` with exit bar − fill bar ≤ 3 (the reference's fill bar is its signal bar). **Cap binds** = planned risk ≥ the ceiling − 0.001pp (the v113 tolerance).
7. **Cache end** for the holdout = the latest bar date across the loaded frames at the shot.
8. **The features record** is a gzip JSON (`<date>-v131-train-fills.json.gz`): every TRAIN fill of every cell. Only `stop_pct`, `stop_atr` and `planned_rr` are re-priced from the limit, as the spec names; `gap_fragile` (derived from the close-based `stop_pct`) is left as `entry_context` recorded it.
9. **The masked entry function short-circuits.** The live strategy pass calls every `ENTRY_FUNCS` entry; while `admits("Fibonacci Limit", "bullish", hk)` is False the function returns all-False without walking the order book, so the live scan pays nothing.
10. **Registry row on a pass.** On a passing holdout, `emit-registry` writes one `Fibonacci Limit` row (VALIDATED for a Tier 1 winner, WEAK for Tier 2); `STRATEGY_GATES` stays masked — unmasking is the live-wiring follow-on spec's job.

Config values as they ship (read at this commit): `LEVEL_LIFECYCLE_STOPS_ENABLED` True; `STRUCTURAL_STOP_SCOPE` empty; `FIB_LEVEL_STOP_ATR` 0.0 and `FIB_LEVEL_STOP_DIRECTIONS` empty (Fibonacci level stop off); `FIB_SR_CONFLUENCE_ATR` 0.0 (confluence filter off); `FIB_TARGET_1_0_EXTENSION` False; `DATA_DRIVEN_STOPS_ENABLED` False; `REGIME_GATES_ENABLED` False. The Fibonacci level stop and confluence filter shape the reference arm only.

## Populations

- v2 exits, scale-out on, TP2 levels mode (Fibonacci and Fibonacci Limit have `tp2 False`, so no TP2).
- Frictions flag on (the v2 path is frictionless; the flag only matters to v1).
- `one_at_a_time` on.
- Bullish only.
- The ten `LEGACY_HORIZONS`: 2w, 4w, 2m, 3m, 4m, 5m, 6m, 7m, 8m, 9m.

## Universe and data

Universe 74 — unchanged from the spec.

- Extended cache `data/backtest_cache_ext` (`BACKTEST_CACHE_DIR=data/backtest_cache_ext`); latest bar across the loaded frames at this commit: 2026-09-28 (informational; the holdout end is read again at the shot).
- Survivorship bias biases longs up; it applies to the cells and the reference alike.
- **Deviation from the plan's Step 2 (approved by the partner).** The plan specified `_load_frames(None, None)`, which reads the DB watchlist. Its host does not resolve from this machine, and the local swing-db watchlist carries `XAUUSD`/`XAGUSD` where `data/watchlist.json` carries `GC=F`/`SI=F`. The universe is therefore frozen as the tickers of `data/watchlist.json` (77 rows; sha256 `f545ec0c691cb6fabb180778743369db10a18b513afbd7f070d0f74bd15da586`) that `measure_fib_confluence._load_frames(None, <those 77 tickers>)` loads from the extended cache. That call returns exactly 74 frames. Dropped (no usable cache frame): `CRWV`, `SI=F`, `SPCX`.
- The script labels `--tickers` "smoke runs only"; here it is the frozen universe, and every command that loads frames carries it.

The 74 tickers (sorted):

`AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SNDK,SNOW,SNPS,SOFI,STX,TSLA,UBER,UNH,V,WDC,WMT`

## Commands

`$D` = 2026-10-08; `$P` = `docs/superpowers/results/2026-10-08-v131-preregistration.md`. Every command runs from `E:/Documents/Private/Projects/Discord-Bot` on `main`. `<TICKERS>` is the frozen 74-ticker list above, verbatim:

`AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SNDK,SNOW,SNPS,SOFI,STX,TSLA,UBER,UNH,V,WDC,WMT`

**Universe check (V131-10 Step 2).** The sorted list must equal the one above exactly (74 frames, latest bar 2026-09-28 or later):

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python -c "import sys, json; sys.path[:0]=['scripts/backtest','.']; from measure_fib_confluence import _load_frames; w=json.load(open('data/watchlist.json')); t=','.join(r if isinstance(r,str) else r['ticker'] for r in w); f=_load_frames(None, t); print(len(f)); print(','.join(sorted(f))); print(max(str(x.index[-1].date()) for x in f.values()))"
```

**V131-10 Stages 0-2 (TRAIN).** Collect, one horizon at a time in the order `9m 8m 7m 6m 5m 4m 3m 2m 4w 2w`:

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python -u scripts/backtest/measure_fib_limit.py collect --horizon <hz> --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --tickers <TICKERS> --out data/v131_collect_<hz>.json > logs/v131_collect_<hz>.log 2>&1
python scripts/backtest/measure_fib_limit.py stage0 --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --rows data/v131_collect_*.json --out docs/superpowers/results/2026-10-08-v131-stage0.json
python scripts/backtest/measure_fib_limit.py reproduce --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --rows data/v131_collect_*.json --out docs/superpowers/results/2026-10-08-v131-reproduction.json
python scripts/backtest/measure_fib_limit.py features --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --rows data/v131_collect_*.json --out docs/superpowers/results/2026-10-08-v131-train-fills.json.gz
python scripts/backtest/measure_fib_limit.py evaluate --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --rows data/v131_collect_*.json --stage0 docs/superpowers/results/2026-10-08-v131-stage0.json --reproduction docs/superpowers/results/2026-10-08-v131-reproduction.json --reproduction-note docs/superpowers/results/2026-10-08-v131-reproduction.md --out docs/superpowers/results/2026-10-08-v131-evaluate.json
```

(`--reproduction-note` is dropped when the reproduction matched. `stage0`, `reproduce`, `features` and `evaluate` read the collected rows and load no frames, so they carry no `--tickers`.) `<hz>` runs over the ten horizons; `universe_n` in each collect output must equal 74.

**V131-11 Stage 3 (the one holdout shot, only if Stage 2 proceeded):**

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python -u scripts/backtest/measure_fib_limit.py holdout --preregistration docs/superpowers/results/2026-10-08-v131-preregistration.md --tickers <TICKERS> --evaluate docs/superpowers/results/<V131-10 $D>-v131-evaluate.json --out docs/superpowers/results/2026-10-08-v131-holdout.json > logs/v131_holdout.log 2>&1
python scripts/backtest/measure_fib_limit.py emit-registry --holdout-json docs/superpowers/results/2026-10-08-v131-holdout.json --registry swingbot/core/backtesting/validation_registry.json --run-date 2026-10-08
```

(`emit-registry` runs only on a passing holdout, after the holdout JSON is committed.)

## Multiple testing

Six cells (L in {0.5, 0.618} by N in {3, 5, 10}), no multiple-testing correction. The guard is the plateau rule (a cell and every grid neighbour clear the same tier), the three profit clauses and the 13-fold check. The reference arm is reported and never selected.

## Not re-run

v84, v101, v102, v103 A/C, v104 and v113 B are not re-run: this is entry mechanics, a new mechanism (spec "Non-goals"). v124 is untouched.
