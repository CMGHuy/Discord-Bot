# v104 Part 2 — Data and measurement (on `main`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-25-v104-structural-stops-and-shorts_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §1.2, §5

Parts 1a–1c must be merged to `main` before V104-13. Check with `git log --oneline main | grep "(v104)"`: expect commits for V104-1 … V104-12.

## Conventions for every task here

- `<date>` is the run date (`YYYY-MM-DD`), picked once in V104-13 and reused in every file name. Every `results/` path is `docs/superpowers/results/`.
- Every command runs from the repo root on `main`, with no `cd`, and carries `BACKTEST_CACHE_DIR=data/backtest_cache_ext`. On `main`, `data/watchlist.json` is the production watchlist, so no `--tickers` is needed. V104-13 records its hash, and every later run must report the same `universe_n`.
- Collect dumps go to `data/v104_*.json`, stay local and are never staged. Add `data/v104_*.json` to `.gitignore` in V104-13, under the `data/v103_*.json` line.
- **Load `backtest-gate` before every measurement command.** **Load `pooled-numbers` before writing any N / WR / ExpR** into a results doc or commit message. Every figure carries its N and window, and comes from the JSON this part wrote.
- Any run longer than about 2 minutes goes to a background `backtest-runner`. Its progress goes to `<scratchpad>/v104_<unit>.log` (the `[k/N] P%` lines), deleted on success. Answer "how far along" from the last percent.

---

# Phase B — Data and measurement

### Task V104-13: Extend the cache, check the earnings data, record the universe

**Files:**
- Modify: `.gitignore`
- Create: `results/<date>-v104-data.md`

- [ ] **Step 1: Git-ignore the v104 dumps.** In `.gitignore`, directly under `data/v103_*.json`, add `data/v104_*.json`. Run `git status --short data/`. Expected: empty.

- [ ] **Step 2: Extend the extended cache to the last complete session (network).**

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --start 2010-01-01 --end today --force
```

This takes minutes, so dispatch it to `backtest-runner` with a log. Afterwards:

```bash
python - <<'EOF'
import pathlib, pandas as pd
main = {p.stem for p in pathlib.Path("data/backtest_cache").glob("*.csv")}
ext = {p.stem for p in pathlib.Path("data/backtest_cache_ext").glob("*.csv")}
print("missing_in_ext", sorted(main - ext))
spy = pd.read_csv("data/backtest_cache_ext/SPY.csv", index_col=0)
print("SPY", spy.index[0], spy.index[-1], len(spy))
EOF
```

Required: `missing_in_ext` empty; SPY first date ≤ `2010-01-05`; SPY last date = the last complete NYSE session before today. **That last date is `HOLDOUT_END`.** Write it down; V104-15 freezes it.

- [ ] **Step 3: Check the earnings CSVs and hash them.**

```bash
python - <<'EOF'
import csv, hashlib, pathlib
d = pathlib.Path("market_data/earnings")
files = sorted(d.glob("*.csv"))
h = hashlib.sha256()
for f in files:
    h.update(f.name.encode()); h.update(f.read_bytes())
first, last, in_2026 = [], [], 0
for f in files:
    rows = list(csv.DictReader(f.open(encoding="utf-8")))
    if rows:
        first.append(rows[0]["report_date"]); last.append(rows[-1]["report_date"])
        in_2026 += any(r["report_date"].startswith("2026") for r in rows)
print("files", len(files), "sha256", h.hexdigest())
print("earliest", min(first), "latest", max(last), "tickers_with_2026_reports", in_2026)
EOF
```

Required: every non-ETF ticker in the universe has a CSV, and the tickers with 2026 reports cover the non-ETF universe. If a ticker is missing, run `python scripts/data/fetch_earnings_dates.py --tickers <missing>` and repeat the check. **Never back-fill by hand.**

- [ ] **Step 4: Record the universe.**

```bash
python -c "import json,hashlib;n=sorted(json.load(open('data/watchlist.json')));print(len(n));print(hashlib.sha256(','.join(n).encode()).hexdigest());print(','.join(n))"
```

- [ ] **Step 5: Write `results/<date>-v104-data.md`.** Sections:
  - `## Cache`: Step 2's output and the fetch command.
  - `## HOLDOUT_END`: the date, and why (the last complete session before the fetch).
  - `## Earnings`: Step 3's output.
  - `## Universe`: Step 4's count, hash and list. Note that `universe_n` after the liquidity/quality filter is whatever V104-14 reports, and that every later stage must equal it.

- [ ] **Step 6: Commit**

```bash
git add .gitignore docs/superpowers/results/<date>-v104-data.md
git commit -m "docs(v104): extended cache to <HOLDOUT_END>, earnings data and universe recorded

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-14: Stage 0 — short signal counts (B1, B2, B3)

**Files:**
- Create: `results/<date>-v104-stage0-B1.json`, `-B2.json`, `-B3.json`, `results/<date>-v104-stage0.md`

- [ ] **Step 1: Load `backtest-gate`.** Stage 0 counts signals on TRAIN only. It runs no backtest and reads no holdout rows: `_count` filters to `TRAIN`.

- [ ] **Step 2: Run the three counts.** Dispatch them concurrently to `backtest-runner` if any one takes over 2 minutes:

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py count --mechanism B1 --out docs/superpowers/results/<date>-v104-stage0-B1.json
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py count --mechanism B2 --out docs/superpowers/results/<date>-v104-stage0-B2.json
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py count --mechanism B3 --out docs/superpowers/results/<date>-v104-stage0-B3.json
```

All three JSONs must report the same `universe_n`. Record it; it is the universe for every later stage.

- [ ] **Step 3: Read the counts.**

```bash
python - <<'EOF'
import json, glob
for path in sorted(glob.glob("docs/superpowers/results/*-v104-stage0-B?.json")):
    d = json.load(open(path, encoding="utf-8"))
    print(d["mechanism"], "universe_n", d["universe_n"], "closed", d["closed_at_stage0"])
    for key, c in d["counts"].items():
        top2 = sum(sorted(c["by_horizon"].values(), reverse=True)[:2])
        print(f"  {key:18} total={c['total']:5} top2={top2 / c['total'] if c['total'] else 0:.0%} by_year={c['by_year']}")
EOF
```

`closed_at_stage0` is the decision: fewer than 30 at the loosest cell closes that earnings setting. **Do not recompute it or override it.** B3's entry ignores the horizon, so its ten horizons count the same bars ten times. Write that down; it is disclosure, not a gate.

- [ ] **Step 4: Write `results/<date>-v104-stage0.md`.** Sections:
  - `## Counts`: per mechanism, a table of cell × earnings → total, top-2 horizon share and per-year counts, with the loosest cell marked.
  - `## Concentration`: any cell whose top-2 horizon share is ≥ 80%, stated plainly.
  - `## Thin years`: years with 0–5 signals at the loosest cell.
  - `## Decision`: per mechanism × earnings setting, `ENTERS Stage 1` or `NO-LIFT at Stage 0 (N=<n> < 30)`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v104-stage0-B1.json docs/superpowers/results/<date>-v104-stage0-B2.json docs/superpowers/results/<date>-v104-stage0-B3.json docs/superpowers/results/<date>-v104-stage0.md
git commit -m "docs(v104): Stage 0 short signal counts -- <per mechanism x earnings: enters | NO-LIFT>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-15: Pre-registration and the `HOLDOUT_END` freeze (committed before any backtest)

**Files:**
- Create: `results/<date>-v104-preregistration.md`
- Modify: `scripts/backtest/measure_v104.py` (the `HOLDOUT_END` line only)

- [ ] **Step 1: Freeze the holdout end.** In `scripts/backtest/measure_v104.py`, change `HOLDOUT_END: str | None = None` to `HOLDOUT_END: str | None = "<HOLDOUT_END from V104-13>"`. Change no other line.

- [ ] **Step 2: Write the pre-registration.** Copy every value verbatim from the committed files: `grep -n "^[A-Z_]* = \|^[A-Z_]*: " scripts/backtest/measure_v104.py scripts/backtest/funnel.py`, the `MECHANISMS` and `PART_A` blocks, and the index's Global Constraints. Do not copy from this plan. It must state:
  - **Candidates:** the 15 Part A cells (strategy, direction, admitted horizons); the B mechanisms and earnings settings entering Stage 1 (from V104-14), plus the Stage 0 count of each closed one.
  - **Definitions:** Part A in/out arms (`STRUCTURAL_STOP_SCOPE` = `""` vs `"<strategy>:<direction>"`); B1/B2/B3 exactly as spec §3 with the index amendments; the earnings axis with its ≤ 1-bar entry block and the hold cap at the bar before the reaction.
  - **Windows:** `TRAIN`, the 13 anchored folds 2013..2025, and `HOLDOUT = 2026-01-01..<HOLDOUT_END>`.
  - **Clauses:** Tier 1 and Tier 2 with every constant; Part A Stage 1 (tier **and** in-arm ExpR > out-arm ExpR on TRAIN); Part A Stage 2 (`fixed_folds`: ≥ 3 folds with N ≥ 15, ≥ ⅔ ExpR > 0); Part B Stages 1–2 (plateau within an earnings setting; winner by tier, then ExpR; per-fold reselection); Stage 3 (the assigned tier, N ≥ 15, and for Part A in-arm ExpR ≥ out-arm ExpR on the holdout).
  - **The thin-holdout rule** (spec §5.4) and **the one-shot rule** (spec §5.6), each as the script enforces it.
  - **Multiple testing:** up to 18 shots; about 0.45 false passes expected at the 2.5% bound; no correction.
  - **Registry rule:** index amendment 2.
  - **Populations:** live gates for Part A; the bearish-only gate override for B; the laggard rule on every bearish population; v2 exits, scale-out, TP2 levels and frictions on; `apply_level_lifecycle` as fixed by V104-2.
  - **Data:** V104-13's cache, HOLDOUT_END, the earnings sha256 and the universe hash. Survivorship bias is stated: it biases longs up and shorts down.
  - **Not re-run:** spec §8's list.

- [ ] **Step 3: Commit both together, before V104-16**

```bash
git add scripts/backtest/measure_v104.py docs/superpowers/results/<date>-v104-preregistration.md
git commit -m "docs(v104): pre-register Part A (15 cells) and Part B shorts -- TRAIN 2010-2025, 13 folds, one 2026 holdout shot each; HOLDOUT_END=<date>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run: `git status --short docs/superpowers/results/ scripts/backtest/measure_v104.py`. It must list nothing: `holdout` refuses a pre-registration with uncommitted changes.

---

### Task V104-16: Part A — collect and evaluate the 15 cells

**Files:**
- Create (local, never staged): `data/v104_collect_A_<slug>.json` × 15
- Create: `results/<date>-v104-partA-<slug>.json` × 15, `results/<date>-v104-partA.md`

`<slug>` is `measure_v104.slug(strategy) + "-" + direction`, e.g. `break-and-retest-bearish`.

- [ ] **Step 1: Load `backtest-gate`, and confirm the pre-registration is committed.** `git log --oneline -1 -- docs/superpowers/results/<date>-v104-preregistration.md` must print V104-15's commit. If it prints nothing, **stop**.

- [ ] **Step 2: Collect.** Dispatch the 15 cells to `backtest-runner` agents, **at most 4 at once**. Each brief:

> From the repo root on `main`, with no `cd`: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py collect-a --strategy "<strategy>" --direction <direction> --out data/v104_collect_A_<slug>.json > <scratchpad>/v104_A_<slug>.log 2>&1`. Progress lines are `[k/N] P% A <strategy> <direction> <arm> <TICKER>`. On success, return the final line, `universe_n` from the JSON, and `len(arms["in"])` and `len(arms["out"])`, then delete the log. On failure, return the last 40 log lines and keep the log. Run no other subcommand.

Each returned `universe_n` must equal V104-14's. A mismatch means **stop**, and record the cause.

- [ ] **Step 3: Evaluate** (fast, no backtest). Run it for each cell:

```bash
python scripts/backtest/measure_v104.py evaluate --rows data/v104_collect_A_<slug>.json --out docs/superpowers/results/<date>-v104-partA-<slug>.json
```

- [ ] **Step 4: Print the decisions**

```bash
python - <<'EOF'
import json, glob
for path in sorted(glob.glob("docs/superpowers/results/*-v104-partA-*.json")):
    e = json.load(open(path, encoding="utf-8"))
    s_in, s_out = e["in_scope"]["stats"], e["baseline"]
    print(f"{e['strategy']:20} {e['direction']:8} OUT n={s_out['n']} wr={s_out['win_rate']} exp={s_out['expectancy_r']}"
          f" | IN n={s_in['n']} wr={s_in['win_rate']} exp={s_in['expectancy_r']} lb={e['in_scope']['lower_bound']}"
          f" tier={e['in_scope']['tier']} beats={e['beats_baseline']} folds={e['stage2']} -> proceed={e['proceed_to_holdout']} tier={e['tier']}")
EOF
```

`proceed_to_holdout` and `tier` are the decision. **Never override them by hand.**

- [ ] **Step 5: Write `results/<date>-v104-partA.md`.** Load `pooled-numbers` first. Include:
  - One table row per cell: out-arm N / WR / ExpR / scratch share; in-arm N / WR / ExpR / scratch share / bootstrap lower bound / tier; the ΔExpR; Stage 2 qualifying, positive and unselected; and the decision.
  - A column for **the in-arm's median `risk_pct`** (from the collect rows), so the reader sees how wide "structural" actually got.
  - A column for **drop rate** = `1 − N_in / N_out`. A cell that "wins" by dropping most of its trades is a filter, and the doc says so.
  - `## Verdict`: the list of `PROCEED-HOLDOUT <cell> (Tier t)` and `NO-LIFT at Stage 1|2 <cell>`.

- [ ] **Step 6: Commit** (the evaluate JSONs must be committed before V104-18)

```bash
git add docs/superpowers/results/<date>-v104-partA-*.json docs/superpowers/results/<date>-v104-partA.md
git commit -m "docs(v104): Part A Stages 1-2 on TRAIN 2010-2025 -- <n> of 15 proceed to the holdout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-17: Part B — collect and evaluate the shorts

**Files:**
- Create (local): `data/v104_collect_<M>.json`
- Create: `results/<date>-v104-partB-<M>.json`, `results/<date>-v104-partB.md`

- [ ] **Step 1: Load `backtest-gate`, and confirm the pre-registration commit** as in V104-16 Step 1.

- [ ] **Step 2: Collect** each mechanism with at least one open earnings setting. Run the three concurrently as `backtest-runner` agents:

> `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py collect-b --mechanism <M> --stage0 docs/superpowers/results/<date>-v104-stage0-<M>.json --out data/v104_collect_<M>.json > <scratchpad>/v104_<M>.log 2>&1`. Return the final line and `universe_n`, then delete the log. On failure, return the last 40 lines.

`universe_n` must equal V104-14's.

- [ ] **Step 3: Evaluate**

```bash
python scripts/backtest/measure_v104.py evaluate --rows data/v104_collect_<M>.json --out docs/superpowers/results/<date>-v104-partB-<M>.json
```

- [ ] **Step 4: Print the decisions**

```bash
python - <<'EOF'
import json, glob
for path in sorted(glob.glob("docs/superpowers/results/*-v104-partB-B?.json")):
    e = json.load(open(path, encoding="utf-8"))
    print(e["mechanism"], e["strategy"], "-> proceed", e["proceed_to_holdout"], "cell", e["validation_cell"])
    for setting, r in e["by_earnings"].items():
        if "closed_at" in r:
            print("  ", setting, "closed at Stage 0"); continue
        s1, s2 = r["stage1"], r["stage2"]
        for k, c in s1["cells"].items():
            print(f"   {setting:11} cell {k}: {c['stats']} lb={c['lower_bound']} tier={c['tier']}")
        print("   ", setting, "plateau t1", s1["plateau_tier1"], "t2", s1["plateau_tier2"],
              "winner", s1["winner"], "tier", s1["winner_tier"], "stage2", s2["verdict"])
EOF
```

- [ ] **Step 5: Write `results/<date>-v104-partB.md`.** Load `pooled-numbers`. Per mechanism × earnings setting include:
  - every cell's N / WR / ExpR / scratch / lower bound / tier;
  - the plateaus and the winner;
  - the fold table (test year, selected cell, test N, test ExpR) and the verdict;
  - **the `hold` vs `exit_before` comparison at the same grid value.** This is the earnings measurement the partner asked for. Report it even where neither proceeds.

  End with `## Verdict`.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/results/<date>-v104-partB-*.json docs/superpowers/results/<date>-v104-partB.md
git commit -m "docs(v104): Part B Stages 1-2 on TRAIN 2010-2025 -- <per mechanism: PROCEED cell | NO-LIFT stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If no Part A cell and no Part B mechanism proceeds, skip V104-18 and go to V104-20's NO-LIFT path.

---

### Task V104-18: Stage 3 — the 2026 holdout (one shot per proceeding candidate)

**Files:**
- Create: `results/<date>-v104-holdout-<candidate>.json` (one per shot), `results/<date>-v104-holdout.md`

`<candidate>` is `a-<slug>` or `b-<mechanism lower>`. The script derives it, and the `--out` name must use the same string.

- [ ] **Step 1: Load `backtest-gate`, and list prior shots.** Run `ls docs/superpowers/results/ | grep -- "-v104-holdout-"`. For every candidate with a prior file from **any** date: if that file's `status` is not `sealed-thin`, the shot is spent. **Do not run it.** The script refuses as well; this check is the second lock.

- [ ] **Step 2: Run each proceeding candidate exactly once.** Candidates may run concurrently, each on its own `backtest-runner`:

> `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py holdout --evaluate docs/superpowers/results/<date>-v104-part<A|B>-<x>.json --preregistration docs/superpowers/results/<date>-v104-preregistration.md --out docs/superpowers/results/<date>-v104-holdout-<candidate>.json > <scratchpad>/v104_h_<candidate>.log 2>&1`. Return the final line and the JSON's `status`, and when scored its `stats`, `lower_bound`, `clauses` and `passes`. Delete the log. On a refusal (`SystemExit`), return the message **verbatim and do not retry with changed arguments**.

A refusal means a precondition failed (usually an uncommitted file). Fix the precondition. **Never work around a refusal.**

- [ ] **Step 3: Write `results/<date>-v104-holdout.md`.** Load `pooled-numbers`. Per shot:
  - the candidate and tier;
  - `status`: for `sealed-thin`, **only** N, plus "shot unspent; one retry when HOLDOUT_END ≥ 2026-12-31" (no other figure exists to report);
  - for scored shots, N / WR / ExpR / scratch / lower bound, each clause with its value, and for Part A the baseline arm's N / WR / ExpR;
  - `PASS` or `FAIL`;
  - one line comparing TRAIN and holdout at the same cell (N, WR, ExpR).

  Then `## Multiple testing`: the number of scored shots, the expected false passes at 2.5% per shot (`0.025 × shots`), and the observed passes. `## Verdict`: the list. **A FAIL is final.**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<date>-v104-holdout-*.json docs/superpowers/results/<date>-v104-holdout.md
git commit -m "docs(v104): 2026 holdout -- <PASS list | FAIL list | sealed-thin list>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
