# v113 Part 2 — Data, pre-registration and measurement (on `main`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, amendments, Review Focus and Parallelisation live in `2026-09-28-v113-bearish-day-coverage_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-28-v113-bearish-day-coverage-design.md` §5, §6

Phase A (V113-1 … V113-11) must be merged to `main` first. Check: `git log --oneline main | grep "(v113)"` lists the eleven Phase A commits, and `python scripts/backtest/measure_v113.py --help` lists `holdout` and `emit-registry`.

## Conventions for every task here

- `<date>` is the run date (`YYYY-MM-DD`), picked once in V113-12 and reused in every result file name except the pre-registration, whose name the spec fixes: `docs/superpowers/results/2026-09-28-v113-preregistration.md`. Every `results/` path means `docs/superpowers/results/`.
- Every command runs from the repo root on `main`, with no `cd`, and every measurement carries `BACKTEST_CACHE_DIR=data/backtest_cache_ext`. On `main`, `data/watchlist.json` is the production watchlist, so Parts A and B take no `--tickers`; Part D takes exactly `--tickers SH,PSQ,RWM,DOG`.
- Collect dumps go to `data/v113_*.json`, stay local and are never staged (V113-12 git-ignores them). Evaluate and holdout JSONs go to `results/` and are committed.
- **Load `backtest-gate` before every measurement command. Load `pooled-numbers` before writing any N / WR / ExpR** into a results doc or commit message. Every figure carries its N and window and comes from the JSON this part wrote.
- Any run longer than about 2 minutes goes to a background `backtest-runner`, with its progress in `<scratchpad>/v113_<unit>.log` (the `[k/N] P%` lines), deleted on success. Answer "how far along" from the last percent.
- A results markdown never recomputes a verdict: it copies `proceed_to_holdout`, `tier`, clauses and folds from the JSON. **Do not override a closure.**

---

# Phase B — Data and measurement

### Task V113-12: Fetch the four inverse ETFs, write the manifest, record the data

**Files:**
- Modify: `.gitignore`
- Create: `data/universe/inverse_etfs.json`
- Create: `results/<date>-v113-data.md`

**Interfaces:**
- Consumes: `fetch_backtest_data.py --tickers` (V113-9); `measure_fib_confluence._load_frames` (liquidity and data-quality filter, same as every measurement).
- Produces: `data/backtest_cache_ext/{SH,PSQ,RWM,DOG}.csv` (local, untracked); the manifest (read by V113-20 only if D ships); `<date>`; the recorded Part A/B `universe_n` and Part D `universe_n` every later stage must reproduce.

- [ ] **Step 1: Git-ignore the dumps.** In `.gitignore`, directly under `data/v104_*.json`, add `data/v113_*.json`. Run `git status --short data/`. Expected: empty.

- [ ] **Step 2: Fetch (network; dispatch to `backtest-runner` if it runs past 2 minutes).**

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --tickers SH,PSQ,RWM,DOG --start 2010-01-01 --end 2026-09-26
```

(yfinance's `end` is exclusive, so `2026-09-26` includes the 2026-09-25 session, the spec's `HOLDOUT_END`.) Then check:

```bash
python - <<'EOF'
import pathlib, pandas as pd
for t in ("SH", "PSQ", "RWM", "DOG"):
    p = pathlib.Path("data/backtest_cache_ext") / f"{t}.csv"
    df = pd.read_csv(p, index_col=0)
    print(t, df.index[0], df.index[-1], len(df))
print("shared cache touched:", sorted(t for t in ("SH", "PSQ", "RWM", "DOG")
                                      if (pathlib.Path("data/backtest_cache") / f"{t}.csv").exists()))
EOF
```

Required: every first date ≤ `2010-01-05`; every last date `2026-09-25`; `shared cache touched: []`. A ticker that fails to fetch is recorded as such; **never back-fill by hand**.

- [ ] **Step 3: Which of the four survive the live liquidity and data-quality filter.**

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python - <<'EOF'
import sys
sys.path[:0] = ["scripts/backtest", "."]
from measure_fib_confluence import _load_frames
from run_backtest_range import load_cached
from swingbot.core.marketdata.universe import liquidity_reason
kept = _load_frames(None, "SH,PSQ,RWM,DOG")
print("kept", sorted(kept))
for t in ("SH", "PSQ", "RWM", "DOG"):
    print(t, liquidity_reason(load_cached(t), symbol=t))
EOF
```

Record the output verbatim. Part D's `universe_n` is `len(kept)`. **Do not lower a floor** to keep a ticker; if fewer than four survive, Part D runs on the survivors (the script's `_d_frames` still requires the four names on the command line; the filter drops the rest) and the pre-registration states it.


- [ ] **Step 4: Write the manifest** `data/universe/inverse_etfs.json` (spec §5 "record them in the universe manifest"; amendment 5: a new file, because live code reads `etfs.json`):

```json
[
  {"symbol": "SH",  "name": "ProShares Short S&P500",      "sector": "Inverse Index", "etf": true, "inverse": true, "tracks": "S&P 500"},
  {"symbol": "PSQ", "name": "ProShares Short QQQ",         "sector": "Inverse Index", "etf": true, "inverse": true, "tracks": "Nasdaq-100"},
  {"symbol": "RWM", "name": "ProShares Short Russell2000", "sector": "Inverse Index", "etf": true, "inverse": true, "tracks": "Russell 2000"},
  {"symbol": "DOG", "name": "ProShares Short Dow30",       "sector": "Inverse Index", "etf": true, "inverse": true, "tracks": "Dow Jones 30"}
]
```

Check it loads: `python -c "from swingbot.core.marketdata.universe import universe_symbols; print(universe_symbols('inverse_etfs'))"`. Expected: `['SH', 'PSQ', 'RWM', 'DOG']`.

- [ ] **Step 5: Earnings data for Part A and the universe for A/B.** Part A's earnings block reads `market_data/earnings/*.csv`. Hash it with the V104-13 Step 3 snippet (`grep -n "Check the earnings CSVs" -A 22 docs/superpowers/plans/2026-09-25-v104-structural-stops-and-shorts_2-measurement.md`) and compare with v104's recorded final sha256 (`3eeb8012…` in `results/2026-09-28-v104-data.md`). A different hash is fine; record both and the file count. Then record the universe:

```bash
python -c "import json,hashlib;n=sorted(json.load(open('data/watchlist.json')));print(len(n));print(hashlib.sha256(','.join(n).encode()).hexdigest());print(','.join(n))"
BACKTEST_CACHE_DIR=data/backtest_cache_ext python -c "import sys; sys.path[:0]=['scripts/backtest','.']; from measure_fib_confluence import _load_frames; f=_load_frames(None, None); print('universe_n', len(f))"
```

Required: none of SH/PSQ/RWM/DOG is in `data/watchlist.json` (if one is, stop and ask — Part A/B would silently drop it via `_ab_frames` but the universe record would be wrong).

- [ ] **Step 6: Write `results/<date>-v113-data.md`.** Sections:
  - `## Inverse ETFs`: Step 2's fetch command and output table, Step 3's liquidity output, Part D `universe_n`.
  - `## Manifest`: the path and why it is not `etfs.json`.
  - `## HOLDOUT_END`: `2026-09-25`, fixed by the spec and already committed in `measure_v113.py`; the extended cache's other tickers may hold a partial later bar — every holdout window stops at `HOLDOUT_END`.
  - `## Earnings`: Step 5's hash, file count, and the comparison with v104.
  - `## Universe`: watchlist count, hash, list, and the filtered Part A/B `universe_n` every later stage must equal.

- [ ] **Step 7: Commit**

```bash
git add .gitignore data/universe/inverse_etfs.json docs/superpowers/results/<date>-v113-data.md
git commit -m "docs(v113): SH/PSQ/RWM/DOG cached to 2026-09-25, inverse-ETF manifest, universe and earnings recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-13: Pre-registration — its own commit, before any TRAIN number exists

**Files:**
- Create: `docs/superpowers/results/2026-09-28-v113-preregistration.md`

**Interfaces:**
- Consumes: the committed `measure_v113.py`, `funnel.py`, `measure_v104.py` constants; V113-12's data record.
- Produces: the pre-registration every `holdout` command requires (`require_committed`).

- [ ] **Step 1: Confirm nothing has been measured.** `git ls-files docs/superpowers/results | grep v113` must list only `<date>-v113-data.md`, and `ls data/v113_*.json` must find nothing. If a v113 TRAIN number exists anywhere, stop: the pre-registration can no longer be written blind.

- [ ] **Step 2: Collect the values from the committed files, not from this plan.**

```bash
grep -n "^[A-Z_]* = \|^[A-Z_]*: " scripts/backtest/measure_v113.py scripts/backtest/funnel.py scripts/backtest/measure_v104.py
grep -n "^FADE_\|DEFAULT_PARAMS\[FADE\]" swingbot/core/market/short_entries.py
python -c "import sys; sys.path[:0]=['scripts/backtest','.']; import measure_v113 as m; c=m.d_cells(); print(len(c)); print(c)"
python -c "from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS; print(HORIZONS['1w']); print(MIN_BARS['1w'])"
python -c "from swingbot.core.planning.params import PLAN_SHAPES, EXIT_V2_PARAMS; print(PLAN_SHAPES); print(EXIT_V2_PARAMS['Downtrend Overbought Fade'])"
```

- [ ] **Step 3: Write the pre-registration.** It must state:
  - **Header:** plan and spec links; "committed before any v113 TRAIN number existed".
  - **The `1w` horizon:** the full `HORIZONS["1w"]` dict and `MIN_BARS["1w"]` from Step 2; masked by default; the strategy-plan reward floor (2.0% on `1w`, none elsewhere — index amendment 1); per-strategy tables with no `1w` row use their existing fallbacks (index amendment 4: MACD `(12, 26, 9)`, MA Ribbon `(10, 20, 50)`, Break & Retest 10 bars / 1.0%, VWAP hold 2 bars).
  - **Part A:** the signal (Step 2's `FADE_*` constants), the plan (limit at `close_t` for one bar, stop ×1.02, target `entry − m × (stop − entry)`, one leg, no break-even move, 7-bar time stop from entry), the fill model and the fill-bar rule (index amendment 3), the grid `m ∈ {1.0, 1.25, 1.5}`, the v104 dollar-risk sizing (always in scope). Stage 1: standard tiers per `m`, plateau winner (`funnel.stage1`: value and both neighbours clear; winner = best Tier, then highest ExpR). Stage 2: `funnel.stage2` per-fold reselection, ≥ 3 qualifying folds (N ≥ 15), ≥ ⅔ ExpR > 0.
  - **Part B:** the 22 cells (`PART_B`), each on `1w` only with the cell admitted by `cells` and every other pair on its live mask; no grid. Bar: every Tier 1 clause **and** bootstrap lower bound > 0, on TRAIN and again on the holdout; Stage 2 `fixed_folds` with the same fold rule. Reported per cell, never selecting: cap-bind rate (planned risk within 0.001 pp of the 2% ceiling) and floor-drop rate (plans the 2% floor dropped ÷ plans it judged, counted at the builder, before the bearish laggard rule).
  - **Part D:** the four tickers and Step 3's survivors from V113-12; the exact `d_cells()` list from Step 2 (its length and every pair); masks unchanged; one pooled cell, standard tiers; Stage 2 `fixed_folds`; breakdowns by strategy and ticker reported only. No registry row (amendment 5).
  - **Populations:** v2 exits, scale-out on (a whole-position target takes the single leg), TP2 levels where a strategy's exit params allow, frictions flag on; the live bearish laggard rule on every bearish population (A and bearish B cells); `apply_level_lifecycle` as it ships.
  - **Windows:** `TRAIN = 2010-01-01..2025-12-31`; the 13 anchored folds 2013..2025; `HOLDOUT = 2026-01-01..2026-09-25`.
  - **Tiers:** Tier 1 and Tier 2 with every constant from Step 2 (`WR_FLOOR`, `MIN_N_TRAIN`, `MIN_N_VALIDATION`, `MAX_SCRATCH_SHARE`, `FOLD_MIN_N`, `FOLD_POSITIVE_SHARE`, `MIN_QUALIFYING_FOLDS`, `BOOTSTRAP_SEED`, 10,000 resamples, 2.5th percentile).
  - **Stage 3:** one shot per cell; `N < 15` → `sealed-thin`, unspent, one retry only when `HOLDOUT_END ≥ 2026-12-31`; the clauses of the cell's assigned bar (A: its Stage 1 tier; B: Tier 1 + lower bound; D: its Stage 1 tier).
  - **Multiple testing:** 24 Stage 1 cells (A counts once, its plateau spans 3 grid values); no correction; Part B's stricter bar is the spec's answer to its 22 tries.
  - **Ship rules (spec §7) and this plan's amendments 2, 5 and 6:** what a pass ships, what an A pass does not ship yet and why, and that alerts stay behind soak.
  - **Data:** V113-12's cache record, earnings hash and universe hash; survivorship bias biases longs up and shorts down (and inverse-ETF longs, which are economically shorts, down).
  - **Not re-run (spec "Out of scope"):** 2x/3x inverse ETFs, options, pair trades, any market-regime gate, any v93/v101–v104 bearish cell on its original horizons.

- [ ] **Step 4: Commit it alone**

```bash
git add docs/superpowers/results/2026-09-28-v113-preregistration.md
git commit -m "docs(v113): pre-register Part A (fade, m grid), Part B (22 cells on 1w, Tier 1 + lower bound) and Part D (inverse-ETF longs) -- TRAIN 2010-2025, 13 folds, one 2026 holdout shot each

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run: `git status --short docs/superpowers/results/ scripts/backtest/measure_v113.py`. It must list nothing: `holdout` refuses a pre-registration with uncommitted changes.

---

### Task V113-14: Part A — collect and score the fade on TRAIN

**Files:**
- Create: `results/<date>-v113-partA.json`, `results/<date>-v113-partA.md`

**Interfaces:**
- Consumes: `measure_v113 collect-a` / `evaluate` (V113-10); the committed pre-registration (V113-13).
- Produces: the Part A evaluate JSON (`proceed_to_holdout`, `validation_cell`, `tier`) that V113-17 reads.

- [ ] **Step 1: Load `backtest-gate`.** This is TRAIN only; the collect refuses rows after 2025-12-31 (`assert_rows_before`).

- [ ] **Step 2: Collect and score** (dispatch to `backtest-runner`, log `<scratchpad>/v113_partA.log`):

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py collect-a --out data/v113_partA.json
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py evaluate --rows data/v113_partA.json --out docs/superpowers/results/<date>-v113-partA.json
```

Required: `universe_n` equals V113-12's Part A/B figure.

- [ ] **Step 3: Read it.**

```bash
python - <<'EOF'
import json, glob
d = json.load(open(glob.glob("docs/superpowers/results/*-v113-partA.json")[0], encoding="utf-8"))
for key, cell in d["stage1"]["cells"].items():
    s = cell["stats"]
    print(f"m={key:5} n={s['n']:5} wr={s['win_rate']} exp={s['expectancy_r']} lb={cell['lower_bound']} tier={cell['tier']} floor={d['floor'][key]} cap={d['cap_bind'][key]}")
print("plateau t1", d["stage1"]["plateau_tier1"], "t2", d["stage1"]["plateau_tier2"], "winner", d["stage1"]["winner"], d["stage1"]["winner_tier"])
print("stage2", d["stage2"]["verdict"])
print("proceed", d["proceed_to_holdout"], d["validation_cell"], d["tier"])
EOF
```

- [ ] **Step 4: Write `results/<date>-v113-partA.md`.** Load `pooled-numbers`. Sections: `## Cells` (per `m`: N, WR, ExpR, lower bound, tier, scratch+timeout share, floor-drop rate, cap-bind rate), `## Plateau and winner`, `## Folds` (13 rows: test year, selected `m`, N, ExpR), `## Decision` — copy `proceed_to_holdout`; if false, name the clause or stage that closed it (e.g. "Stage 1: no `m` cleared a tier; best WR 41.2% at N=312"). Note the break-even arithmetic at `m = 1.0` (50% WR) only as context, never as a verdict.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v113-partA.json docs/superpowers/results/<date>-v113-partA.md
git commit -m "docs(v113): Part A fade on TRAIN -- <winner m and tier | NO-LIFT at Stage 1/2 and why>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-15: Part B — the 22 legacy cells on `1w`, in strategy chunks

**Files:**
- Create: `results/<date>-v113-partB-<slug>-<direction>.json` × 22, `results/<date>-v113-partB.md`

**Interfaces:**
- Consumes: `measure_v113 collect-b` / `evaluate` (V113-10); the pre-registration.
- Produces: 22 evaluate JSONs (`proceed_to_holdout`, `tier`) that V113-17 reads.

- [ ] **Step 1: Load `backtest-gate`.**

- [ ] **Step 2: Run the 11 strategy chunks**, up to 4 `backtest-runner` agents at a time, each running both directions of one strategy (log `<scratchpad>/v113_partB_<slug>.log`). Slugs: EMA Crossover `ema-crossover`, VWAP `vwap`, Fibonacci `fibonacci`, Support/Resistance `support-resistance`, RSI `rsi`, MACD `macd`, Elliott Wave `elliott-wave`, MA Ribbon `ma-ribbon`, Break & Retest `break-and-retest`, RSI Divergence `rsi-divergence`, Volume Profile `volume-profile`. One chunk:

```bash
for d in bullish bearish; do
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py collect-b --strategy "<Strategy>" --direction $d --out data/v113_partB_<slug>_$d.json
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py evaluate --rows data/v113_partB_<slug>_$d.json --out docs/superpowers/results/<date>-v113-partB-<slug>-$d.json
done
```

Required: all 22 JSONs report the same `universe_n` as V113-12.

- [ ] **Step 3: Read them.**

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob("docs/superpowers/results/*-v113-partB-*.json")):
    d = json.load(open(p, encoding="utf-8"))
    s = d["scored"]["stats"]
    failing = [k for k, v in d["clauses"].items() if not v]
    print(f"{d['strategy']:20} {d['direction']:8} n={s['n']:5} wr={s['win_rate']} exp={s['expectancy_r']} "
          f"lb={d['scored']['lower_bound']} fail={failing} folds={d['stage2']['qualifying']}/{d['stage2']['positive']} "
          f"cap={d['cap_bind_rate']} floor={d['floor']['floor_drop_rate']} proceed={d['proceed_to_holdout']}")
EOF
```

- [ ] **Step 4: Write `results/<date>-v113-partB.md`.** Load `pooled-numbers`. A 22-row table: strategy, direction, N, WR, ExpR, lower bound, failing clauses, folds qualifying/positive, cap-bind rate, floor-drop rate, decision. Then `## Empty or thin cells`: every cell with N < 30, stating whether its cap-bind or floor-drop rate explains it ("arithmetic, not a market verdict", spec §4). Then `## Proceeding`: the cells with `proceed_to_holdout: true`, or "none".

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v113-partB-*.json docs/superpowers/results/<date>-v113-partB.md
git commit -m "docs(v113): Part B 22 cells on 1w, TRAIN -- <k>/22 proceed to the holdout (<list or none>)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-16: Part D — live bullish masks on the four inverse ETFs

**Files:**
- Create: `results/<date>-v113-partD.json`, `results/<date>-v113-partD.md`

**Interfaces:**
- Consumes: `measure_v113 collect-d` / `evaluate` (V113-10); V113-12's cache; the pre-registration.
- Produces: the Part D evaluate JSON that V113-17 reads.

- [ ] **Step 1: Load `backtest-gate`.**

- [ ] **Step 2: Collect and score** (`backtest-runner` if long; log `<scratchpad>/v113_partD.log`):

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py collect-d --tickers SH,PSQ,RWM,DOG --out data/v113_partD.json
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py evaluate --rows data/v113_partD.json --out docs/superpowers/results/<date>-v113-partD.json
```

Required: `universe_n` equals V113-12's Part D figure, and the JSON's `cells` equals the pre-registered `d_cells()` list.

- [ ] **Step 3: Read it.**

```bash
python - <<'EOF'
import json, glob
d = json.load(open(glob.glob("docs/superpowers/results/*-v113-partD.json")[0], encoding="utf-8"))
s = d["scored"]
print("pooled", s["stats"], "lb", s["lower_bound"], "tier", s["tier"])
print("stage2", d["stage2"], "proceed", d["proceed_to_holdout"], d["tier"])
for name, stats in d["by_strategy"].items(): print("  strategy", name, stats)
for name, stats in d["by_ticker"].items(): print("  ticker", name, stats)
EOF
```

- [ ] **Step 4: Write `results/<date>-v113-partD.md`.** Load `pooled-numbers`. Sections: `## Pooled cell` (N, WR, ExpR, lower bound, tier, scratch share), `## Folds`, `## Breakdowns (reported, not selecting)` — by strategy and by ticker, with a sentence that no breakdown may be used to narrow the cell, `## Decision` copied from the JSON. If 2026 looks like a thin year for inverse longs (few TRAIN-style signals in 2025), say so: it predicts a sealed-thin holdout (spec §5 known risk).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v113-partD.json docs/superpowers/results/<date>-v113-partD.md
git commit -m "docs(v113): Part D inverse-ETF longs on TRAIN -- <tier and proceed | NO-LIFT and why>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V113-17: Stage 3 — the 2026 holdout, one shot per proceeding cell

**Files:**
- Create: `results/<date>-v113-holdout-<candidate>.json` (one per proceeding cell), `results/<date>-v113-holdout.md`

**Interfaces:**
- Consumes: V113-14/15/16's committed evaluate JSONs; the committed pre-registration; `measure_v113 holdout` (V113-11).
- Produces: holdout payloads (`status`, `passes`, `rows`) that Phase C reads.

- [ ] **Step 1: Load `backtest-gate`.** List what proceeds:

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob("docs/superpowers/results/*-v113-part*.json")):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("proceed_to_holdout"):
        print(p, d["part"], d["strategy"], d["direction"], "tier", d["tier"])
EOF
```

If nothing proceeds, skip to Step 4 and write "no holdout shot spent".

- [ ] **Step 2: One shot each.** The candidate slug is `a-fade`, `b-<slug>-<direction>` or `d-inverse-etfs` (the script derives it and refuses a spent shot). For A or B:

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py holdout --evaluate <evaluate JSON> --preregistration docs/superpowers/results/2026-09-28-v113-preregistration.md --out docs/superpowers/results/<date>-v113-holdout-<candidate>.json
```

For D add `--tickers SH,PSQ,RWM,DOG`. **Never re-run a shot that wrote a file**, whatever it says; a `sealed-thin` result is final until `HOLDOUT_END ≥ 2026-12-31`.

- [ ] **Step 3: Read them.**

```bash
python - <<'EOF'
import json, glob
for p in sorted(glob.glob("docs/superpowers/results/*-v113-holdout-*.json")):
    d = json.load(open(p, encoding="utf-8"))
    print(d["candidate"], d["status"], d.get("n") or d.get("stats"), d.get("clauses"), "passes", d.get("passes"))
EOF
```

- [ ] **Step 4: Write `results/<date>-v113-holdout.md`.** Load `pooled-numbers`. Per candidate: status, N, WR, ExpR, lower bound, each clause, PASS / FAIL (naming the failing clause) / SEALED-THIN (N only, retry date). Then `## What Phase C does`: the passing candidates by part — B passes go to V113-18, an A pass to V113-19 (recorded, not unmasked — amendment 2), a D pass to V113-20.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v113-holdout-*.json docs/superpowers/results/<date>-v113-holdout.md
git commit -m "docs(v113): 2026 holdout -- <per candidate: PASS | FAIL (<clause>) | sealed-thin (N=<n>) | none spent>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(If no holdout JSON exists, stage only the `.md`.)
