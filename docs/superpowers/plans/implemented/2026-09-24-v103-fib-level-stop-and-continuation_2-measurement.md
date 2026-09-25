# v103 Part 2 — Data and measurement (on `main`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-24-v103-fib-level-stop-and-continuation_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md`

Part 1 (`_1a-code.md`, `_1b-code.md`) must be merged to `main` before V103-9. Check it with `git log --oneline main | grep "feat(v103)"`: expect commits for V103-1..8.

## Parallelisation

- **Strict chain:** V103-9 → 10 → 11 → 12 → 13 → 14. Each task reads the previous task's committed output.
- **Inside V103-11:** the A and C `collect` runs are separate processes over a read-only cache, writing different files. Dispatch them as two background `backtest-runner` agents at once.
- **Inside V103-12:** up to four shots. Each is one process with its own output file, so they may also run concurrently.

## Conventions for every task here

- `<date>` is the run date (`YYYY-MM-DD`). Pick it once in V103-9 and reuse it in every file name. Every `docs/superpowers/results/` path below is under that directory.
- Every command runs from the repo root, with no `cd`. Measurement commands carry `BACKTEST_CACHE_DIR=data/backtest_cache_ext` (Global Constraints). Without it the script exits with the shared guard, and that is the guard doing its job.
- Collect files (`data/v103_collect_<M>.json`) stay local and are never staged. Stage files by explicit path, never `git add -A` or `git add data/`.
- **Load `pooled-numbers` before writing any N / WR / ExpR figure** into a results doc or commit message. Every figure carries its N and window. Figures come from the JSON the script wrote in this task, never from memory or an older doc.
- **Load `backtest-gate` before every measurement command** in V103-9, 11 and 12.

---

# Phase B — Data and measurement

### Task V103-9: Cache readiness and Stage 0 counts (A and C)

**Files:**
- Modify: `.gitignore`
- Create: `docs/superpowers/results/<date>-v103-stage0-A.json`, `<date>-v103-stage0-C.json`, `<date>-v103-stage0.md`

- [ ] **Step 1: Git-ignore the extended cache and the collect dumps**

v102 assumed `data/backtest_cache_ext/` (22 MB of CSVs) and `data/v102_collect.json` were git-ignored. They are not: `git status` lists both as untracked. In `.gitignore`, directly under the `data/backtest_cache/` line, add:

```gitignore
# v102's extended 2010-2025 OHLCV cache (BACKTEST_CACHE_DIR); rebuilt by
# scripts/data/fetch_backtest_data.py --start 2010-01-01 --end 2025-12-31.
data/backtest_cache_ext/
```

After the `data/v33_*.json` block, add:

```gitignore
# v102/v103 Fibonacci funnel collect dumps -- rebuilt by the scripts' `collect`
# subcommand. The committed evaluate/validation JSONs under
# docs/superpowers/results/ are the record.
data/v102_*.json
data/v103_*.json
```

Run: `git status --short data/`. Expected: empty output.

- [ ] **Step 2: Check the extended cache still covers the universe (no fetch)**

v102 fetched and checked the cache (`results/2026-09-24-v102-ext-cache-check.md`). Re-fetch only if this check fails.

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

Required: `missing_in_ext` is empty, SPY's first date is ≤ `2010-01-05` and its last date is ≥ `2025-12-30`. If `missing_in_ext` is not empty, run v102-4's fetch (`BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/data/fetch_backtest_data.py --start 2010-01-01 --end 2025-12-31`, with `--force` for the missing names) and repeat this step.

- [ ] **Step 3: Load `backtest-gate`, then run Stage 0 for both mechanisms**

Stage 0 is free: it counts entry signals on TRAIN_EXT only, runs no backtest and reads no VALIDATION data.

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py count --mechanism A --out docs/superpowers/results/<date>-v103-stage0-A.json
BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py count --mechanism C --out docs/superpowers/results/<date>-v103-stage0-C.json
```

Each prints `v103 count done`. If either run goes past 2 minutes, stop it and dispatch it to `backtest-runner` instead, with progress in a log that is deleted on success.

- [ ] **Step 4: Read the closures and the horizon spread**

```bash
python - <<'EOF'
import json, glob
for path in sorted(glob.glob("docs/superpowers/results/*-v103-stage0-[AC].json")):
    d = json.load(open(path, encoding="utf-8"))
    print(d["mechanism"], "universe_n", d["universe_n"], "closed_at_stage0", d["closed_at_stage0"])
    for key, c in d["counts"].items():
        hz = c["by_horizon"]
        top2 = sum(sorted(hz.values(), reverse=True)[:2])
        share = top2 / c["total"] if c["total"] else 0.0
        print(f"  {key:16} total={c['total']:5}  top2_horizon_share={share:.0%}  by_year={c['by_year']}")
EOF
```

The decision is already in `closed_at_stage0`: at the loosest cell (A `0.1`, C `0.786`), fewer than 30 signals closes that mechanism × direction. **Do not recompute or override it.** Signal counts are an upper bound on decided trades.

- [ ] **Step 5: Write `docs/superpowers/results/<date>-v103-stage0.md`**

Sections:
- `## Cache`: Step 2's output, and whether a re-fetch was needed.
- `## Counts`: one table per mechanism. Rows are `cell|direction` (A includes the `0|…` reference baseline). Columns are total, the top-2-horizon share, and the per-year counts. Mark the loosest cell.
- `## Per-horizon`: the `by_horizon` counts for each mechanism's loosest cell, per direction. **Concentration caveat:** where one cell's top-2-horizon share is ≥ 80%, say so plainly. v102's filter turned out to be a de-facto 2w/4w mask, and a PASS on such a cell would not be a cross-horizon result. This is disclosed, not gated: the spec forbids a horizon mask and adds no horizon clause.
- `## Thin years`: the years with 0–5 signals at the loosest cell, per mechanism × direction. That is where the Stage 2 folds will be thin.
- `## Decision`: per mechanism × direction, `ENTERS Stage 1` or `NO-LIFT at Stage 0 (N=<total> < 30 at <loosest>)`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore docs/superpowers/results/<date>-v103-stage0-A.json docs/superpowers/results/<date>-v103-stage0-C.json docs/superpowers/results/<date>-v103-stage0.md
git commit -m "docs(v103): Stage 0 signal counts -- <per mechanism x direction: enters Stage 1 | NO-LIFT>

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

If all four mechanism × direction cells close here, skip V103-10..12 and go to V103-13's NO-LIFT path.

---

### Task V103-10: Pre-registration (committed before any cell is backtested)

**Files:**
- Create: `docs/superpowers/results/<date>-v103-preregistration.md`

- [ ] **Step 1: Write it.** Copy every value verbatim from the index's Global Constraints and from the constants in `scripts/backtest/fib_funnel.py` and `measure_fib_v103.py`. Read them from the files (`grep -n "^[A-Z_]* = " scripts/backtest/fib_funnel.py`, and the `MECHANISMS` block), not from this plan. It must state:
  - **Mechanism × direction cells entering Stage 1** (from V103-9), and the Stage 0 count of each closed one.
  - **Mechanism definitions:** A = stop `b` ATRs past the tested retracement level, a signal whose stop exceeds the 2% cap is dropped, never capped, grid `b ∈ {0.1, 0.25, 0.5}`, and the `b = 0` reference (today's swing stop, reported, never a candidate). C = entry on the break back through the swing extreme after a held retracement, depth `d_min = 0.382 ≤ depth ≤ d_max`, `min_pullback_bars = 2`, grid `d_max ∈ {0.5, 0.618, 0.786}`, extension targets, no plan when the stop exceeds the cap.
  - **Windows:** `TRAIN_EXT`, `FOLD_YEARS` (2013..2023, anchored at 2010-01-01), and `VALIDATION`.
  - **Tier 1 and Tier 2 clauses**, with every constant: `WR_FLOOR`, `MIN_N_TRAIN`, `MIN_N_VALIDATION`, `MAX_SCRATCH_SHARE`, and for the bootstrap `BOOTSTRAP_RESAMPLES = 10_000`, seed `42`, lower bound = 2.5th percentile, ticker clusters, empty baseline arm.
  - **Stage 1:** the plateau rule (grid neighbours pass the same tier), the winner order (Tier 1 plateau, then Tier 2 plateau, then none), and that VALIDATION scores on the tier Stage 1 assigned and never changes it.
  - **Stage 2:** per-fold re-selection on 2010..Y−1 (highest ExpR with N ≥ 30), what counts as an unselected fold, and the verdict (≥ 3 folds with test N ≥ 15, ≥ 2/3 of them ExpR > 0). A mechanism × direction proceeds only when Stage 1 has a winner **and** Stage 2 clears.
  - **Populations:** A-bullish on the live gate; A-bearish unmasked + laggard; C-bullish unmasked; C-bearish unmasked + laggard. Arithmetic: v2 exits, scale-out, TP2 levels, frictions, `apply_level_lifecycle` as today.
  - **Data:** the extended cache and V103-9's cache check. Survivorship bias is stated, not corrected, and it biases WR and ExpR upward in the early years.
  - **Horizon disclosure:** V103-9's concentration caveat, if any, copied here. No horizon mask.
  - **The one-shot rule:** at most one `validation` run per mechanism × direction (at most four in all), only at the committed evaluate output's `validation_cell`, never at another cell, and never again after a FAIL. The script enforces it (committed pre-registration and evaluate files, refusing an existing output), and so does this document.
  - **The registry-row rule** (decided now, before any score): `emit-registry` writes one row per mechanism. Its population must be the population the wired live gate lets through.
    - **C:** the row pools C's passing directions.
    - **A:** writes the `Fibonacci` row, replacing today's (`WEAK`, N=246, 2020–2023, run 2026-09-10), **only when** A's passing directions equal every direction `STRATEGY_GATES["Fibonacci"]` admits after wiring. Otherwise, for example when A-bearish passes and bullish Fibonacci keeps its swing stop, the row would describe a subset of the live population. In that case no A row is emitted, the existing row stays, and the mismatch is recorded in `backtest-methodology.md`.
  - **Not re-run:** v101 #1/#2/#4, v102 confluence, the v84 1.0 extension, v31 horizon splits, and v17 `REGIME_ALLOW`.
  - **If v100 has merged:** v103's funnel is self-contained and does not go through `validate_component.py`.

- [ ] **Step 2: Commit on `main` before V103-11**

```bash
git add docs/superpowers/results/<date>-v103-preregistration.md
git commit -m "docs(v103): pre-register Fibonacci level-stop (A) and continuation (C) -- TRAIN_EXT, 11 folds, two tiers, one shot per mechanism x direction

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

Run: `git status --short docs/superpowers/results/`. It must list nothing for this file. `validation` refuses a pre-registration with uncommitted changes.

---

### Task V103-11: Stages 1–2 — collect once per mechanism, evaluate

**Files:**
- Create (local, never staged): `data/v103_collect_A.json`, `data/v103_collect_C.json`
- Create: `docs/superpowers/results/<date>-v103-stage12-A.json`, `<date>-v103-stage12-C.json`, `<date>-v103-stage12.md`

- [ ] **Step 1: Load `backtest-gate`, then confirm the pre-registration is committed**

Run: `git log --oneline -1 -- docs/superpowers/results/<date>-v103-preregistration.md`. Expected: V103-10's commit. With no output, **stop**: nothing may be backtested before it is committed.

- [ ] **Step 2: Collect.** For every mechanism with at least one direction entering Stage 1, dispatch one `backtest-runner` in the background. If both mechanisms qualify, dispatch both at once. Each run takes tens of minutes: A backtests 4 cells (`0` + grid) and C backtests 3, × ≤ 2 directions × the universe × 10 horizons, over 14 years. The brief for mechanism `<M>`:

> From the repo root, with no `cd`: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py collect --mechanism <M> --stage0 docs/superpowers/results/<date>-v103-stage0-<M>.json --out data/v103_collect_<M>.json > <scratchpad>/v103_collect_<M>.log 2>&1`. Progress lines read `[k/N] P% <M> <cell> <direction> <TICKER>`. Answer "how far along" from the last log line's percent. On success, return the final line plus `universe_n`, `elapsed_s` and `closed_at_stage0` from the JSON, then delete the log. On failure, return the last 40 log lines and keep the log.

Check the returned `universe_n` equals V103-9's `universe_n` for that mechanism. A mismatch means the universe changed between stages: **stop**, and record the cause before evaluating.

- [ ] **Step 3: Evaluate** (fast; no backtest)

```bash
python scripts/backtest/measure_fib_v103.py evaluate --rows data/v103_collect_A.json --out docs/superpowers/results/<date>-v103-stage12-A.json
python scripts/backtest/measure_fib_v103.py evaluate --rows data/v103_collect_C.json --out docs/superpowers/results/<date>-v103-stage12-C.json
```

Skip the line for a mechanism that closed in both directions at Stage 0.

- [ ] **Step 4: Print the verdict fields**

```bash
python - <<'EOF'
import json, glob
for path in sorted(glob.glob("docs/superpowers/results/*-v103-stage12-[AC].json")):
    ev = json.load(open(path, encoding="utf-8"))
    for d in ("bullish", "bearish"):
        x = ev[d]
        if x.get("closed_at") == "stage0":
            print(ev["mechanism"], d, "closed at Stage 0"); continue
        s1, s2 = x["stage1"], x["stage2"]
        print(ev["mechanism"], d, "baseline", x["baseline"])
        for k, c in s1["cells"].items():
            print(f"   cell {k}: {c['stats']}  lb={c['lower_bound']}  tier={c['tier']}")
        print("   plateau t1", s1["plateau_tier1"], "t2", s1["plateau_tier2"],
              "winner", s1["winner"], "tier", s1["winner_tier"])
        for f in s2["folds"]:
            print("   fold", f["test_year"], f["tol"], f["stats"])
        print("   stage2", s2["verdict"], "=> proceed", x["proceed_to_validation"],
              "cell", x["validation_cell"], "tier", x["tier"])
EOF
```

`proceed_to_validation`, `validation_cell` and `tier` are the decision. **Never override them by hand.** A cell that looks close but did not clear is NO-LIFT.

- [ ] **Step 5: Write `docs/superpowers/results/<date>-v103-stage12.md`.** Load `pooled-numbers` first. Per mechanism × direction:
  - The A reference (`b = 0`): N / WR / ExpR / scratch+timeout share. It is reported, never a candidate. C has no reference arm.
  - Every grid cell: N / WR / ExpR / scratch share / bootstrap lower bound / the Tier 1 and Tier 2 clauses / the tier.
  - The plateaus, the winner and its tier, or "no winner".
  - Stage 2: the fold table (test year, selected cell, test N, test ExpR) and the verdict (qualifying, positive, unselected).
  - **A's drop rate:** for A, the share of the `b = 0` population each cell dropped, `1 − N_cell / N_ref`. A mechanism that "wins" by keeping 10% of trades is a filter, and the doc must say so.
  - `## Verdict`: `PROCEED-VALIDATION at <cell> (Tier <t>)` or `NO-LIFT at Stage 1|2`.

- [ ] **Step 6: Commit** (the evaluate JSONs must be committed before V103-12: `validation` refuses an uncommitted one)

```bash
git add docs/superpowers/results/<date>-v103-stage12-*.json docs/superpowers/results/<date>-v103-stage12.md
git commit -m "docs(v103): Stages 1-2 on TRAIN_EXT -- <per mechanism x direction verdict>

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

If nothing proceeds, skip V103-12 and go to V103-13's NO-LIFT path.

---

### Task V103-12: Stage 3 — VALIDATION (one shot per proceeding mechanism × direction)

**Files:**
- Create: `docs/superpowers/results/<date>-v103-validation-<M>-<d>.json` (one per shot), `<date>-v103-validation.md`

- [ ] **Step 1: Load `backtest-gate`, then check that no shot is spent**

Run: `ls docs/superpowers/results/ | grep -- "-v103-validation-"`. Expected: no output. Any existing `-v103-validation-<M>-<d>.json` from **any date** means that shot is spent. **Stop and do not re-run it.** The script only refuses an existing file at the same path, so a different `<date>` would slip past it. This check closes that gap.

- [ ] **Step 2: Run each proceeding mechanism × direction exactly once.** Dispatch each shot to `backtest-runner` (they may run concurrently):

> From the repo root, with no `cd`: `BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py validation --mechanism <M> --direction <d> --evaluate docs/superpowers/results/<date>-v103-stage12-<M>.json --preregistration docs/superpowers/results/<date>-v103-preregistration.md --out docs/superpowers/results/<date>-v103-validation-<M>-<d>.json > <scratchpad>/v103_val_<M>_<d>.log 2>&1`. Return the final line and the JSON's `cell` and `verdict`, then delete the log. On a refusal (`SystemExit`), return the message verbatim and **do not retry with changed arguments**.

A refusal means a precondition failed: an uncommitted file, a cell that did not proceed, a wrong mechanism, or a spent shot. Fix the precondition (usually a missing commit). Never work around the refusal.

- [ ] **Step 3: Write `docs/superpowers/results/<date>-v103-validation.md`.** Load `pooled-numbers` first. Per shot: the cell and tier, N / WR / ExpR / scratch share / lower bound, each clause with its value, and `PASS` or `FAIL`. **A FAIL is final:** no re-run, no other cell, no other tier. Add one line per shot comparing TRAIN_EXT and VALIDATION at the same cell (N, WR, ExpR), because a large drop is information even on a PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<date>-v103-validation-*.json docs/superpowers/results/<date>-v103-validation.md
git commit -m "docs(v103): VALIDATION -- <per mechanism x direction PASS/FAIL>

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task V103-13: Wiring (any PASS) or close-out (NO-LIFT)

Do the PASS path for each passing mechanism, then the NO-LIFT steps for everything that did not pass. Both can apply: A may pass while C closes.

**PASS path.** Work on a short worktree branch (`worktree-lifecycle` skill), then merge. Iterate with `testrun.py file`, and run `testrun.py fast` once at the end of the path.

**A passed** (in ≥ 1 direction):

- [ ] **A1: Flags.** In `swingbot/config.py`, set the `default` of the `FIB_LEVEL_STOP_ATR` `Field` to the winner `b` as a string (e.g. `"0.25"`), and set `FIB_LEVEL_STOP_DIRECTIONS` to the passing directions (e.g. `"bullish"`). Prefix both help texts with `Validated in v103 (<date>): <direction(s)> at b=<b>, Tier <t>.` Set the same two values in `.env.example`.
- [ ] **A2: Gate.** If A-bearish passed, `STRATEGY_GATES["Fibonacci"]` (in `swingbot/core/market/strategy_types.py`, today `{"directions": ("bullish",)}`) must admit bearish. Today's gate already admits bullish, so admitting bearish too means **removing the key**. Replace its comment with:

```python
    # "Fibonacci": gate removed in v103 (<date>). Bearish admitted under the
    # level-stop (FIB_LEVEL_STOP_ATR=<b>): TRAIN_EXT 2010-2023 N=<n> WR=<wr> ExpR=<e>;
    # VALIDATION 2024-25 N=<n> WR=<wr> ExpR=<e> (Tier <t>). Bullish: <A result or "swing stop, v93 gate">.
```

  If only A-bullish passed, the gate stays as it is. Update only its comment, with the A-bullish figures.
- [ ] **A3: Pin the parity witnesses off.** The sizing-parity harness compares against a frozen pre-v31 copy. With A on by default, the harness would report A's deliberate stop change as a mismatch. It exists to answer "did the extraction change sizing?", so pin A off in both places, exactly as `LEVEL_LIFECYCLE_STOPS_ENABLED` is pinned:
  - In `tests/backtesting/test_sizing_parity.py`, inside the autouse fixture `_lifecycle_off`, after its `monkeypatch.setattr(...LEVEL_LIFECYCLE_STOPS_ENABLED...)` line, add:

```python
    # v103 mechanism A moves the Fibonacci stop to the tested level by design;
    # the frozen side predates it. Pinned off for the same reason as above.
    monkeypatch.setattr("swingbot.config.FIB_LEVEL_STOP_ATR", 0.0, raising=False)
```

  - In `scripts/reports/parity_sizing.py` `main()`, after `config.LEVEL_LIFECYCLE_STOPS_ENABLED = False`, add `config.FIB_LEVEL_STOP_ATR = 0.0` with the same one-line reason.
- [ ] **A4: Other tests that assert today's Fibonacci stop.** Run `python scripts/dev/testrun.py fast`. For each failure that names a Fibonacci stop or plan:
  - If the test is a frozen **no-behaviour-change witness** (its docstring says it pins a pre-change result, like `test_v74_no_behaviour_change.py`), pin `FIB_LEVEL_STOP_ATR` to `0.0` with `monkeypatch` and a one-line reason.
  - Otherwise it asserts production behaviour. Update the expected stop to the value `entry_filters.fib_level_stop_at(...)` returns for that bar, computed by the helper in the test rather than hard-coded.

  Never loosen an assertion or add an `xfail`. If the right category is unclear, stop and ask.
- [ ] **A5: Pin test.** In `tests/market/test_fib_level_stop.py` (created in V103-1), add:

```python
def test_v103_validated_defaults():
    from swingbot import config
    from swingbot.core.market.strategy_types import STRATEGY_GATES
    assert config.FIB_LEVEL_STOP_ATR == <b>
    assert config.FIB_LEVEL_STOP_DIRECTIONS == "<directions>"
    assert STRATEGY_GATES.get("Fibonacci", {}).get("directions", ("bullish", "bearish")) == <admitted tuple>
```

  Run it together with `tests/test_env_example_sync.py` and `tests/backtesting/test_sizing_parity.py`.

**C passed** (in ≥ 1 direction):

- [ ] **C1: Gate and parameter.** In `strategy_types.py`, set `STRATEGY_GATES["Fibonacci Continuation"]` to `{"directions": (<passing>,)}`, or remove the key if both directions passed. Its comment gives the TRAIN_EXT and VALIDATION figures with N, window and tier. In `entry_filters.py`, set `DEFAULT_PARAMS["Fibonacci Continuation"]["d_max"]` to the winner.
- [ ] **C2: Strategy lists.** Add `"Fibonacci Continuation"` at the end of `backtest.ALL_STRATEGIES`. In `swingbot/commands/backtest.py` `STRATEGY_MAP`, add `"fibcont": "Fibonacci Continuation", "fibc": "Fibonacci Continuation",`. In `swingbot/commands/slash.py` `STRATEGY_CHOICES`, add `app_commands.Choice(name="Fibonacci Continuation", value="fibcont"),` after the Volume Profile choice, and append `, Fibonacci Continuation` to the strategies help line (line ~116). Then run `git grep -n '"Volume Profile"' -- swingbot frontend/src` and add C to every other list that enumerates all strategies.
- [ ] **C3: Parity exclusion.** The frozen `legacy_trade_plan_at` has no C. In `tests/backtesting/test_sizing_parity.py`, replace `@pytest.mark.parametrize("strategy", ALL_STRATEGIES)` with `@pytest.mark.parametrize("strategy", PARITY_STRATEGIES)` and define, below the imports:

```python
# The frozen side predates v103's Fibonacci Continuation and must never learn it.
PARITY_STRATEGIES = tuple(s for s in ALL_STRATEGIES if s != "Fibonacci Continuation")
```

  Update the docstring's "all 11 strategies" to "the 11 pre-v103 strategies". Apply the same exclusion in `scripts/reports/parity_sizing.py` wherever it iterates `ALL_STRATEGIES`.
- [ ] **C4: Registry count.** After the registry emit (step R below), `tests/backtesting/test_registry.py::test_all_eleven_strategies_present` fails at 12. Rename it `test_all_twelve_strategies_present` and assert `== 12`.
- [ ] **C5: Pin test.** In `tests/market/test_fib_continuation.py`, add a test asserting the validated `d_max` and that `STRATEGY_GATES` admits exactly the passing directions. Run it with `tests/backtesting/test_backtest_engine.py` and `tests/backtesting/test_sizing_parity.py`.

**Both mechanisms:**

- [ ] **R: Registry rows**, only through the script and never by hand, under V103-10's registry-row rule. One command per passing mechanism:

```bash
python scripts/backtest/measure_fib_v103.py emit-registry --validation-json <that mechanism's passing validation JSONs> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
```

  For A, check the rule first. If A's passing directions differ from the directions the wired `Fibonacci` gate admits, **do not emit**, and say so in the methodology row.
- [ ] **Soak, not alerts.** Leave `STRATEGY_ALERTS_MODE` alone. Going live stays behind v93's `!soak` rule, and the methodology row says so.
- [ ] **Docs and merge.** Add one closed row per mechanism to `docs/claude/backtest-methodology.md` (the table with the v101/v102 rows): the cell, the tier, the TRAIN_EXT and VALIDATION figures with N, the results links, and "live behind `!soak`". Then run `python scripts/dev/testrun.py fast` once, commit (`feat(v103): wire <mechanism(s)> -- validated <cell>, Tier <t>`, with the trailer), and merge per `worktree-lifecycle` after checking `git log main` for other sessions' commits.

**NO-LIFT path** (every mechanism × direction that did not pass):

- [ ] **N1: Methodology row.** Per mechanism, add a closed row to `docs/claude/backtest-methodology.md`, matching the v101/v102 rows' style: the stage each direction ended at, per-direction figures with N and window, whether VALIDATION was spent (and FAIL) or remains unspent, any horizon-concentration caveat, and what reopening would need. Reopening A needs a stop rule other than "b ATR past the tested level for b ∈ {0.1, 0.25, 0.5}". Reopening C needs a trigger other than "break of the swing extreme after a 0.382–d_max hold".
- [ ] **N2: Inert code stays.** Keep A's flags at their off defaults and C masked (`{"directions": ()}`), out of `ALL_STRATEGIES`. That is the same treatment as `FIB_SR_CONFLUENCE_ATR` and `FIB_TARGET_1_0_EXTENSION`. Keep `fib_funnel.py` and `measure_fib_v103.py`.
- [ ] **N3: Commit.** `docs(v103): close <mechanism x direction list> no-lift at Stage <n>`, with the trailer.

---

### Task V103-14: Full-suite verification and close-out

- [ ] **Step 1:** Dispatch `test-runner` for `python scripts/dev/testrun.py full`. Require `0 failed` and `0 xfailed`. If a failure passes in isolation and sits in code v103 never touched, report it with both outputs and don't call the suite green.
- [ ] **Step 2 (PASS path only):** bump `VERSION.json` `bot` **minor** per `docs/claude/working-conventions.md`, resolving the number from the then-current file. Regenerate and commit `version_history.json` (memory `version-bump-needs-regeneration`).
- [ ] **Step 3: Move the documents.** If anything shipped, `git mv` the spec and all four plan parts (`_0-index`, `_1a-code`, `_1b-code`, `_2-measurement`) to `implemented/`. If nothing shipped, move them to `no-lift/`. Under the spec's headers, add `**Status:** <Shipped A-<dirs> b=<b> / C-<dirs> d_max=<d> | Closed no-lift> <date>; VALIDATION spent: <list or none>.`
- [ ] **Step 4:** Remove the Part 1 and wiring worktrees, and delete their merged branches per `docs/claude/git-safety.md`. `git rev-list --count main..<branch>` must be 0 first. Never touch a `backup`/`stable-*` branch.
- [ ] **Step 5:** Commit: `docs(v103): close out -- <shipped | no-lift>`, with the trailer.
