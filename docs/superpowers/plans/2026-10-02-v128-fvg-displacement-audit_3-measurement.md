# v128 FVG lift audit, Part 3: pre-registration, funnel, close-out (V128-7 .. V128-15)

> Header, Global Constraints, Review Focus, the spec-assumption table (A1–A12), the file map and `## Parallelisation` live in `2026-10-02-v128-fvg-displacement-audit_0-index.md`. Every task here implicitly includes those constraints. Work in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-02-v128-fvg-displacement-audit`; all paths below are relative to it.

**Shell preamble for every measurement step** (V128-8 .. V128-13). Run from the worktree root:

```bash
export BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache
PRE=docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md
mkdir -p logs/v128
```

**Rules for every measurement step:**
- Invoke `backtest-gate` before each command.
- Make no edit under `swingbot/` from V128-8 onward: `check_stamp` compares code hashes, and `fvg_attribution.py record` refuses on a mismatch. V128-12's merge is the one sanctioned exception, and only Stage 3 arms are produced after it.
- Dispatch every `measure_arms.py` and `fvg_attribution.py record` run to the `backtest-runner` subagent, **one arm per chunk**. Name the worktree, the exact command, and the output path in the dispatch. Progress shows in `logs/measure_arms.*.progress` and `logs/fvg_attribution.*.progress`.
- `logs/` is not committed; results files are.
- **Stop on the first stage that leaves no live candidate.** Finish that stage's results file, commit it, then run V128-14 (closed-table row) and V128-15.

# Phase 3 — Pre-registration

### Task V128-7: Pre-registration record, committed before any arm

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md`

**Interfaces:**
- Consumes: the CLIs created by V128-4 (`validate_component.py --gate harvest`, `--mechanism-json`), V128-5 (`fvg_attribution.py record|report|context`) and V128-6 (`fvg_select.py effects|select`). Also `measure_arms.py --stage {pilot,selection,walkforward,validation} --knob A=v --out P --preregistration P`.
- Produces: the committed record every later task quotes, plus its commit hash (`git log -1 --format=%h -- $PRE`), which every results file cites.

- [ ] **Step 1: Confirm Phases 1–2 are committed and green**

Run: `git log --oneline -6` (expect the six `feat(v128)` commits) and `git status --short` (expect clean).
Run: `python scripts/dev/testrun.py file tests/scripts/test_fvg_select.py` and `python scripts/dev/testrun.py file tests/scripts/test_fvg_attribution.py`
Expected: PASS.

- [ ] **Step 2: Write the record**

Write exactly this. Fill the `<...>` fields from `git rev-parse --short HEAD` and the date at the time of writing; leave no other field open.

~~~markdown
# v128 pre-registration — FVG lift audit: all vs off vs displacement-only

**Status:** frozen before any arm was produced. Recorded at worktree HEAD `<short sha>` on `<YYYY-MM-DD HH:MM> UTC`.
**Spec:** `docs/superpowers/specs/2026-10-02-v128-fvg-displacement-audit-design.md`
**Plan:** `docs/superpowers/plans/2026-10-02-v128-fvg-displacement-audit_0-index.md`
**Edge:** expectancy. Not a re-run of any closed row: FVG has never been lift-tested (v49 measured redundancy only).

## Claim

Removing FVG levels entirely (`off`), or keeping only gaps whose middle candle is a displacement candle (`displacement`), improves the scan under **both** the v72 win-rate gate and the v92 harvest gate.

## Arms (frozen grid; no table from any stage may move it)

| Candidate id | `measure_arms.py` knobs |
|---|---|
| baseline | none (`FVG_LEVELS_MODE=all`) |
| `off` | `--knob FVG_LEVELS_MODE=off` |
| `disp-1.0` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.0` |
| `disp-1.5` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.5` |
| `disp-2.0` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=2.0` |

Displacement (causal): with `m = bar_index − 1`, `|C[m] − O[m]| ≥ k·ATR14[m]` (`indicators.atr(df, 14)`). A bullish gap needs `C[m] ≥ L[m] + ⅔(H[m] − L[m])`; a bearish gap needs `C[m] ≤ L[m] + ⅓(H[m] − L[m])`. A non-finite or ≤ 0 ATR is not displacement. The filter runs after the freshest-3-per-side truncation. A filtered gap leaves both the vote and the candidate prices; charts are unchanged.

## Stages, instruments and pass rules

A candidate advances only if it passes **both** gates at a stage. A candidate refused at Stage −1 or Stage 0 under either gate is ineligible at Stage 1. Its selection arm is still produced and scored, because its ΔExpR is the plateau neighbour value for an adjacent `k`.

| Stage | Producer (`measure_arms.py --stage`) | Judge | Pass |
|---|---|---|---|
| −1 reachability | `pilot` (2018-06-01..2020-12-31, first 10 cached tickers) | `validate_component.py --stage reachability`, run once with `--gate win_rate` and once with `--gate harvest`. The stage ignores `--gate`, so both runs give the same verdict | `REACHABLE` (changed outcomes > 0) |
| 0 MDE | `selection` (fold-train 2018-06-01..2022-12-31, full universe, all horizons) | `validate_component.py --stage mde`, paired MDE. `--gate win_rate --train-effect-pp <pooled ΔWR>` and `--gate harvest --train-effect-r <pooled ΔExpR>`, both printed by `fvg_select.py effects` | `RESOLVABLE` under both |
| 1 selection | the same `selection` arms (pooled top level) | `fvg_select.py select` | verdict `selected` |
| 2 walk-forward | `walkforward` (test years 2021 / 2022 / 2023) | `validate_component.py --stage walkforward`, `--gate win_rate` (`gate_win_rate`) and `--gate harvest` (`backtest_wf.gate`) | `PASS` under both |
| 3 VALIDATION | `validation` (2024-01-01..2025-12-31), the single Stage-1 winner, **one shot, total** | `validate_component.py --stage validation`. `--gate win_rate --permutation-p <ΔWR p> --mechanism-json <clause 6>` and `--gate harvest --permutation-p <ΔExpR p>` | `PASS` under both. A missing p is a FAIL |

## Frozen resolutions (the spec assumed tooling that did not exist; resolved here before any arm)

- **R1, harvest walk-forward rule.** `acceptance_harvest.py` has none, and v92 reused the funnel "as-is". The v92 Stage 2 rule is therefore the existing pre-registered expectancy fold gate, `backtest_wf.gate()`: ≥ 2 of 3 test folds with ΔExpR > 0, no fold below −0.05R, and per-fold N ≥ 30. N is the min closed-trade count (win/loss/scratch/timeout) of the two arms. No new constant.
- **R2, Stage 1 clauses and window.** Scored on the pooled fold-train arms (the selection blob's top level, 2018-06-01..2022-12-31). The fold-train-applicable clauses are v72 `win_rate`, `profit_floor`, `geometry`, `volume` and `mechanism` (clause 6 per R5), evaluated with `acceptance.evaluate(stage="walkforward")`, plus v92 `expectancy_gain`, `win_rate_floor` and `volume`, evaluated with `evaluate_harvest(stage="walkforward", structurally_immune_to_wr=False)`. Permutation is validation-only. Every listed clause must be `PASS`; `SKIPPED` does not count as a pass.
- **R3, plateau.** `backtest_wf.plateau_report("FVG_DISPLACEMENT_ATR_K", [1.0, 1.5, 2.0], <pooled ΔExpR per k>, k)` must return `is_plateau: True` (tolerance 0.03R), **and** at least one grid neighbour of `k` must be eligible. `off` is a one-point arm: `plateau_report` would return `is_plateau: True` vacuously, so it is not called. `off` is eligible on its clauses alone (v35's AVWAP on/off precedent). A missing ΔExpR on `k` or a neighbour fails the plateau.
- **R4, one winner.** Among contenders (eligible `off`; eligible `k` that pass R3), take the largest pooled ΔExpR, compared at 4 decimal places. On a tie, the smaller v72 alert cut (2 decimal places). Then `displacement` over `off`. Then the smaller `k` (it keeps more gaps, so it is the smaller change). No contender: `no-eligible-cell` if nothing is eligible, else `spike`.
- **R5, clause 6 (the spec's frozen amendment), as computed.** Scored on the **baseline** arm by `fvg_attribution.py` from one replay of the baseline confluence arm per stage.
  - **Confluence trade, vote:** at the signal bar's window, `FVG` is among the families `count_confirming_strategies(..., take_profit, 5.0)` returns with every gap, and absent once the candidate's filtered FVG candidates are removed.
  - **Confluence trade, price:** at the bar whose level map the replay actually used (`levels_asof`), the scenario's stop cluster or the plan's TP1 cluster contains an FVG member whose price is a filtered gap's midpoint.
  - **Entry:** confluence plans enter at the signal bar's close, never at a level, so entry provenance is structurally empty.
  - **Strategy trade:** there is no confluence vote, and the TP2/lifecycle level provenance is not recorded, so a pairing proxy applies. "Price" holds iff the key is absent from the candidate arm, or its outcome or `r_multiple` differs.
  - Removed = vote or price; retained = every other baseline trade. PASS iff removed WR < retained WR and removed ExpR ≤ 0. Either population lacking decided trades is a FAIL.
- **R6, clause 5 / v92 `not_luck`.** v72 clause 5 uses v122's `permutation_test.py --arms <validation arms> --n 200 --seed 42` (ΔWR p). v92 clause 4 is on ΔExpR, which v122's extension does not produce. V128-12 adds `--statistic expectancy` to the same function: same null-arm construction (per-ticker circular label shift in [20, 200), replacements kept), with the share of null ΔExpR ≥ observed. It is not a second instrument. If v122's extension is not on `main` at Stage 3, the plan stops before VALIDATION with the budget unspent.
- **R7, Stage 0 claims.** The claimed TRAIN effects are the pooled selection-window ΔWR (pp) and ΔExpR (R), as printed. A `null` or ≤ 0 claim is passed as `0`, which is refused, correctly.
- **R8, reporting.** Every stage writes one results file with an attribution table per live candidate (vote-only / price-only / both / unaffected, removed vs retained WR/ExpR, per direction, top-2 horizon share flagged above 80%, replacement count). That table is diagnostic and never a gate. Stage 1 adds the FVG-in-families context slice, labelled confounded.
- **R9, one shot.** The validation arms file is produced once. A crash in any scoring step after it may be re-run on that same file; the file is never regenerated, and nothing is retuned after it.

## Outcomes

PASS (both gates at Stage 3): `FVG_LEVELS_MODE` defaults to the winner (and `FVG_DISPLACEMENT_ATR_K` to its `k`), in its own commit, released as a bot patch. Any other outcome: default stays `all`, code merged inert. Either way, a row is added to `docs/claude/backtest-methodology.md` § Closed pre-registrations.
~~~

- [ ] **Step 3: Commit before any arm exists**

```bash
ls logs/v128/*.json 2>/dev/null && echo "STOP: arms already exist -- the record is no longer a pre-registration"
git add docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md
git commit -m "docs(v128): pre-registration -- FVG lift audit, frozen grid and tooling resolutions"
git log -1 --format=%h -- docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md
```

Expected: no `STOP` line, and one short hash, which is the record's hash for every results file.

# Phase 4 — Funnel

### Task V128-8: Stage −1, reachability on the pilot

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-stage-neg1.md`
- Arms (not committed): `logs/v128/pilot-{off,disp-1.0,disp-1.5,disp-2.0}.json`, `logs/v128/provenance-pilot.json`, `logs/v128/attr-pilot-<cid>.md`

**Interfaces:**
- Consumes: the V128-7 record (committed); `measure_arms.py`, `validate_component.py --stage reachability --gate {win_rate,harvest}`, `fvg_attribution.py record|report`.
- Produces: the set of candidates still live after Stage −1, written in the results file as `LIVE: <ids>` and `REFUSED: <id> (<token>)`.

- [ ] **Step 1: Preconditions**

```bash
git log -1 --format=%h -- $PRE                      # record committed
git status --short -- swingbot/ scripts/backtest/     # expect no output
python -c "import sys; sys.path[:0]=['scripts/backtest','scripts/data','.']; from measure_arms import cached_universe; u=cached_universe(); print(len(u), u[:10])"
```

Run the same `python -c ...` in the main tree (`E:/Documents/Private/Projects/Discord-Bot`) with the same `BACKTEST_CACHE_DIR`. The two counts must match. If the worktree command errors (for example, the watchlist store is unreachable without the main tree's `.env`) or the counts differ, **stop and ask the controller**. Do not copy `.env` into the worktree yourself.

- [ ] **Step 2: Produce the four pilot arms** (`backtest-runner`, one chunk per line)

```bash
python scripts/backtest/measure_arms.py --stage pilot --knob FVG_LEVELS_MODE=off --preregistration $PRE --out logs/v128/pilot-off.json
python scripts/backtest/measure_arms.py --stage pilot --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.0 --preregistration $PRE --out logs/v128/pilot-disp-1.0.json
python scripts/backtest/measure_arms.py --stage pilot --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.5 --preregistration $PRE --out logs/v128/pilot-disp-1.5.json
python scripts/backtest/measure_arms.py --stage pilot --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=2.0 --preregistration $PRE --out logs/v128/pilot-disp-2.0.json
```

Exit 1 with `refused:zero-diff` refuses that candidate with the budget intact. The file is still written. Any other non-zero exit is an instrument error: stop and report it.

- [ ] **Step 3: Score each arm under both gate flags**

```bash
for cid in off disp-1.0 disp-1.5 disp-2.0; do for gate in win_rate harvest; do
  python scripts/backtest/validate_component.py --stage reachability --gate $gate --arms logs/v128/pilot-$cid.json --title "v128 $cid pilot ($gate)" --window "2018-06-01..2020-12-31"
done; done
```

Pass per candidate: `REACHABLE` under both. Record the `knobs ... changed outcomes: N` line for each.

- [ ] **Step 4: Baseline identity check**

```bash
python -c "import json; b=[json.dumps(json.load(open(f'logs/v128/pilot-{c}.json'))['baseline']) for c in ('off','disp-1.0','disp-1.5','disp-2.0')]; print('baselines identical' if len(set(b))==1 else 'BASELINE DRIFT')"
```

Expected: `baselines identical`. `BASELINE DRIFT` means the code changed between chunks: stop and report it.

- [ ] **Step 5: Attribution** (`record` to `backtest-runner`)

```bash
python scripts/backtest/fvg_attribution.py record --arms logs/v128/pilot-off.json --out logs/v128/provenance-pilot.json
for cid in off disp-1.0 disp-1.5 disp-2.0; do
  python scripts/backtest/fvg_attribution.py report --arms logs/v128/pilot-$cid.json --provenance logs/v128/provenance-pilot.json --candidate $cid --out-md logs/v128/attr-pilot-$cid.md
done
```

- [ ] **Step 6: Write the results file**

`docs/superpowers/results/2026-10-02-v128-fvg-stage-neg1.md` holds:
- Title, run date (UTC), the record's hash, `git rev-parse --short HEAD`, and the stamp's `engine_hash.baseline` (first 12 characters).
- The pre-registered Stage −1 rule, quoted from the record.
- A table with one row per candidate: knobs, baseline N, component N, changed outcomes, `win_rate` verdict, `harvest` verdict.
- `LIVE: <ids>` and `REFUSED: <id> (<token>)` lines.
- The four attribution blocks pasted from `logs/v128/attr-pilot-*.md`.
- An observations section: what was measured, stated plainly. Failures are recorded, not fixed.

- [ ] **Step 7: Decide and commit**

```bash
git add docs/superpowers/results/2026-10-02-v128-fvg-stage-neg1.md
git commit -m "docs(v128): Stage -1 reachability -- <LIVE ids or 'all refused'>"
```

If `LIVE` is empty, **STOP the funnel**: go to V128-14 (outcome `UNREACHABLE at Stage −1`), then V128-15. Otherwise continue to V128-9.

### Task V128-9: Stage 0, fold-train arms and MDE under both gates

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-stage0.md`
- Arms (not committed): `logs/v128/selection-<cid>.json` (all four), `logs/v128/provenance-selection.json`, `logs/v128/attr-selection-<cid>.md`, `logs/v128/mechanism-selection-<cid>.json`

**Interfaces:**
- Consumes: Stage −1's `LIVE`/`REFUSED` lists; `fvg_select.py effects`; `validate_component.py --stage mde --gate {win_rate,harvest}`; `fvg_attribution.py record|report --mechanism-json`.
- Produces: `RESOLVABLE: <ids>` and `REFUSED: <id> (<stage>/<gate>)`, plus four `mechanism-selection-<cid>.json` files (`dataclasses.asdict(ClauseResult)`) for V128-10.

- [ ] **Step 1: Preconditions**

`git status --short -- swingbot/` is empty, and `stage-neg1.md` is committed with `LIVE` non-empty.

- [ ] **Step 2: Produce all four selection arms** (`backtest-runner`, one chunk per line; full universe, all horizons)

All four are produced even if Stage −1 refused one (record R8: a refused `k` is still a plateau neighbour).

```bash
python scripts/backtest/measure_arms.py --stage selection --knob FVG_LEVELS_MODE=off --preregistration $PRE --out logs/v128/selection-off.json
python scripts/backtest/measure_arms.py --stage selection --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.0 --preregistration $PRE --out logs/v128/selection-disp-1.0.json
python scripts/backtest/measure_arms.py --stage selection --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.5 --preregistration $PRE --out logs/v128/selection-disp-1.5.json
python scripts/backtest/measure_arms.py --stage selection --knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=2.0 --preregistration $PRE --out logs/v128/selection-disp-2.0.json
```

Then run Step 4 of V128-8 with `selection-` in place of `pilot-`. Expected: `baselines identical`.

- [ ] **Step 3: Print the claimed TRAIN effects**

```bash
for cid in off disp-1.0 disp-1.5 disp-2.0; do echo "$cid $(python scripts/backtest/fvg_select.py effects --arms logs/v128/selection-$cid.json)"; done
```

- [ ] **Step 4: MDE under both gates, for every candidate that is live after Stage −1**

For each live `<cid>`, using its printed `delta_win_rate_pp` (`<dWR>`) and `delta_expectancy_r` (`<dExpR>`). A `null` or a value ≤ 0 is passed as `0`.

```bash
python scripts/backtest/validate_component.py --stage mde --gate win_rate --arms logs/v128/selection-<cid>.json --train-effect-pp <dWR> --title "v128 <cid> MDE (win_rate)" --window "2018-06-01..2022-12-31"
python scripts/backtest/validate_component.py --stage mde --gate harvest --arms logs/v128/selection-<cid>.json --train-effect-r <dExpR> --title "v128 <cid> MDE (harvest)" --window "2018-06-01..2022-12-31"
```

A candidate is `RESOLVABLE` only if both print `RESOLVABLE`. `REFUSED` under either gate refuses it, with the budget intact.

- [ ] **Step 5: Attribution and the clause-6 inputs** (`record` to `backtest-runner`)

```bash
python scripts/backtest/fvg_attribution.py record --arms logs/v128/selection-off.json --out logs/v128/provenance-selection.json
for cid in off disp-1.0 disp-1.5 disp-2.0; do
  python scripts/backtest/fvg_attribution.py report --arms logs/v128/selection-$cid.json --provenance logs/v128/provenance-selection.json --candidate $cid --out-md logs/v128/attr-selection-$cid.md --mechanism-json logs/v128/mechanism-selection-$cid.json
done
```

- [ ] **Step 6: Write the results file and decide**

`docs/superpowers/results/2026-10-02-v128-fvg-stage0.md` holds the same header block as Stage −1, the Stage 0 rule quoted from the record, and a table with one row per candidate: baseline N, component N, ΔWR pp, ΔExpR R, paired MDE (pp), paired MDE (R), `win_rate` verdict, `harvest` verdict. Add the `RESOLVABLE` / `REFUSED` lines, the four attribution blocks, and observations.

```bash
git add docs/superpowers/results/2026-10-02-v128-fvg-stage0.md
git commit -m "docs(v128): Stage 0 MDE -- <RESOLVABLE ids or 'all refused'>"
```

If no candidate is `RESOLVABLE`, **STOP**: go to V128-14 (outcome `REFUSED at Stage 0, budget intact`), then V128-15.

### Task V128-10: Stage 1, selection (fold-train only)

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-stage1.md`, `docs/superpowers/results/2026-10-02-v128-fvg-stage1.json`

**Interfaces:**
- Consumes: the four `selection-<cid>.json` arms and `mechanism-selection-<cid>.json` files (V128-9); the refused ids from Stages −1 and 0.
- Produces: `winner: <cid>` or a stop verdict (`no-eligible-cell` / `spike`).

- [ ] **Step 1: Run the judge**

Pass one `--refused <cid>` for every candidate refused at Stage −1 or Stage 0.

```bash
python scripts/backtest/fvg_select.py select \
  --arm off=logs/v128/selection-off.json --arm disp-1.0=logs/v128/selection-disp-1.0.json \
  --arm disp-1.5=logs/v128/selection-disp-1.5.json --arm disp-2.0=logs/v128/selection-disp-2.0.json \
  --mechanism off=logs/v128/mechanism-selection-off.json --mechanism disp-1.0=logs/v128/mechanism-selection-disp-1.0.json \
  --mechanism disp-1.5=logs/v128/mechanism-selection-disp-1.5.json --mechanism disp-2.0=logs/v128/mechanism-selection-disp-2.0.json \
  [--refused <cid> ...] \
  --out-json docs/superpowers/results/2026-10-02-v128-fvg-stage1.json --out-md logs/v128/stage1-table.md
```

Pass: exit 0 with verdict `selected`. Exit 1 is `no-eligible-cell` or `spike` (or `refused:baseline-drift`, an instrument error: stop and report it).

- [ ] **Step 2: Context slice (diagnostic, Stage 1 only)**

```bash
python scripts/backtest/fvg_attribution.py context --arms logs/v128/selection-off.json --provenance logs/v128/provenance-selection.json --out-md logs/v128/context-selection.md
```

- [ ] **Step 3: Write the results file and decide**

`docs/superpowers/results/2026-10-02-v128-fvg-stage1.md` holds:
- The header block.
- Record rules R2, R3 and R4, quoted verbatim.
- `logs/v128/stage1-table.md`, which gives every cell's eligibility, failed clauses (prefixed `v72:` / `v92:`), ΔExpR, ΔWR, alert cut and plateau lines.
- For each cell, the frozen clause-6 line from `attr-selection-<cid>.md`.
- The context slice, with its "confounded, diagnostic only" label kept.
- The verdict and winner.
- Observations. If the winning cell's top-2 horizon share of removed trades is above 80%, say so explicitly.

```bash
git add docs/superpowers/results/2026-10-02-v128-fvg-stage1.md docs/superpowers/results/2026-10-02-v128-fvg-stage1.json
git commit -m "docs(v128): Stage 1 selection -- <winner or verdict>"
```

If the verdict is not `selected`, **STOP**: go to V128-14 (outcome `NO-LIFT at Stage 1`, with the verdict), then V128-15.

### Task V128-11: Stage 2, walk-forward under both gates

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-stage2.md`, `docs/superpowers/results/2026-10-02-v128-fvg-stage2-win_rate.json`, `docs/superpowers/results/2026-10-02-v128-fvg-stage2-harvest.json`
- Arms (not committed): `logs/v128/walkforward-<W>.json`, `logs/v128/provenance-walkforward.json`, `logs/v128/attr-walkforward-<W>.md`

**Interfaces:**
- Consumes: the Stage 1 winner `<W>` and its knobs (V128-7 record table).
- Produces: `PASS` or `FAIL` under each gate for `<W>`.

- [ ] **Step 1: Produce the walk-forward arm** (`backtest-runner`)

```bash
python scripts/backtest/measure_arms.py --stage walkforward <W's knobs from the record table> --preregistration $PRE --out logs/v128/walkforward-<W>.json
```

- [ ] **Step 2: Score under both gates**

```bash
python scripts/backtest/validate_component.py --stage walkforward --gate win_rate --arms logs/v128/walkforward-<W>.json --title "v128 <W> walk-forward (win_rate)" --window "fold-test 2021 / 2022 / 2023" --out-json docs/superpowers/results/2026-10-02-v128-fvg-stage2-win_rate.json
python scripts/backtest/validate_component.py --stage walkforward --gate harvest --arms logs/v128/walkforward-<W>.json --title "v128 <W> walk-forward (harvest)" --window "fold-test 2021 / 2022 / 2023" --out-json docs/superpowers/results/2026-10-02-v128-fvg-stage2-harvest.json
```

Pass: both print `PASS`.

- [ ] **Step 3: Attribution** (`record` to `backtest-runner`)

```bash
python scripts/backtest/fvg_attribution.py record --arms logs/v128/walkforward-<W>.json --out logs/v128/provenance-walkforward.json
python scripts/backtest/fvg_attribution.py report --arms logs/v128/walkforward-<W>.json --provenance logs/v128/provenance-walkforward.json --candidate <W> --out-md logs/v128/attr-walkforward-<W>.md
```

The report pools the three disjoint test folds.

- [ ] **Step 4: Write the results file and decide**

`docs/superpowers/results/2026-10-02-v128-fvg-stage2.md` holds:
- The header block.
- Both Stage 2 rules: `gate_win_rate` (≥ 2 of 3 folds improving, none worse than −1.0pp, per-fold N ≥ 30) and record R1.
- A per-fold table: test year, ΔWR pp, N (decided), ΔExpR R, N (closed).
- Both verdicts, the attribution block, and observations.

```bash
git add docs/superpowers/results/2026-10-02-v128-fvg-stage2*.md docs/superpowers/results/2026-10-02-v128-fvg-stage2-*.json
git commit -m "docs(v128): Stage 2 walk-forward -- <W> win_rate <PASS|FAIL>, harvest <PASS|FAIL>"
```

Unless both are `PASS`, **STOP**: go to V128-14 (outcome `NO-LIFT at Stage 2, VALIDATION not spent, remains available`), then V128-15.

### Task V128-12: Stage 3 entry: hard check for v122's instrument, then the ΔExpR statistic

**Files:**
- Modify: `scripts/backtest/permutation_test.py` (v122's `--arms` mode gains `--statistic`)
- Create: `tests/backtesting/test_permutation_test_expectancy.py`
- Create: `tests/fixtures/v128/permutation_arms_witness.json` (captured on v122's unchanged code)
- Create on a pause only: `docs/superpowers/results/2026-10-02-v128-fvg-stage3.md` (the resume point)

**Interfaces:**
- Consumes (v122 V122-10, must be on `main`): `arm_pair_permutation(baseline, component, n_perm: int = 200, seed: int = 42) -> dict` with first key `observed_delta_win_rate_pp`, plus `_arms_main(args)`, `_parser()` and `main(argv=None)`.
- Produces: `arm_pair_permutation(..., statistic: str = "win_rate")` and `permutation_test.py --arms P --statistic {win_rate,expectancy}`. `expectancy` returns `observed_delta_expectancy_r` in place of `observed_delta_win_rate_pp`, with every other key the same. The default output is byte-identical (witness).

- [ ] **Step 1: HARD CHECK — is v122's permutation extension on `main`?**

```bash
M=E:/Documents/Private/Projects/Discord-Bot
git -C $M grep -n "def arm_pair_permutation" main -- scripts/backtest/permutation_test.py
git -C $M grep -n "def _arms_main" main -- scripts/backtest/permutation_test.py
git -C $M grep -n '"--arms"' main -- scripts/backtest/permutation_test.py
```

All three must print a match. **If any prints nothing: PAUSE.**
1. Write `docs/superpowers/results/2026-10-02-v128-fvg-stage3.md` containing exactly: `PAUSED before VALIDATION -- v122's permutation_test.py --arms extension is not on main (checked <UTC timestamp>). Stage 3 budget UNSPENT. Winner <W> (Stage 1), Stage 2 PASS under both gates. Resume at V128-12 Step 1 once v122 V122-10 has merged.`
2. Commit it: `git commit -m "docs(v128): Stage 3 paused -- waiting on v122 permutation extension, budget unspent"`.
3. Stop the plan and report the resume point to the controller. Do **not** add a closed-table row; this is not an outcome.

- [ ] **Step 2: Bring v122's instrument into the branch**

Invoke `worktree-lifecycle` (another session may be merging). Then, in the worktree:

```bash
git merge --no-edit main
python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py
python scripts/dev/testrun.py file tests/market/test_fvg_displacement.py
python scripts/dev/testrun.py file tests/market/test_levels_fvg_mode.py
```

Expected: a clean merge and all three PASS. A conflicted merge is new code: resolve it, then run `python scripts/dev/testrun.py fast` once before continuing. From here `code_hash()` differs from Stages −1..2. That is expected: Stage 3 arms are produced fresh in V128-13, and its results file records both hashes.

Read the landed function: `grep -n "def arm_pair_permutation" -A 22 scripts/backtest/permutation_test.py`. Steps 5's three edits assume V122-10's text: one `observed = delta_standardised_win_rate(...)` line, one `null = [delta_standardised_win_rate(...) ...]` comprehension, and a return dict starting `"observed_delta_win_rate_pp": observed`. If the landed body differs so those edits do not apply one-for-one, **stop and report BLOCKED** to the controller. Do not rewrite v122's instrument.

- [ ] **Step 3: Write the tests**

```python
# tests/backtesting/test_permutation_test_expectancy.py
"""v128: v122's --arms permutation gains a dExpR statistic (v92 not_luck); default output unchanged."""
import json
import runpy
from dataclasses import asdict
from pathlib import Path

import numpy as np

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms.provenance import build_stamp

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "backtest" / "permutation_test.py"
WITNESS = ROOT / "tests" / "fixtures" / "v128" / "permutation_arms_witness.json"


def _pair(remove_outcome):
    """25 tickers x 40 trades, aperiodic wins; the component drops every `remove_outcome`
    trade in the second half and admits one replacement per ticker (v122's fixture shape)."""
    baseline, component = [], []
    for t in range(25):
        wins = np.random.default_rng(t).random(40) < 0.4
        for i in range(40):
            outcome = "win" if wins[i] else "loss"
            trade = ArmTrade(f"T{t}", "Fibonacci", "4w", f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}",
                             outcome, 2.0 if wins[i] else -1.0, 2.0, "strategy", "bullish")
            baseline.append(trade)
            if not (i >= 20 and outcome == remove_outcome):
                component.append(trade)
        component.append(ArmTrade(f"T{t}", "Fibonacci", "4w", "2024-03-20", "win", 2.0, 2.0,
                                  "confluence", "bullish"))
    return baseline, component


def _ns():
    return runpy.run_path(str(SCRIPT))


def test_default_statistic_output_is_unchanged():
    assert _ns()["arm_pair_permutation"](*_pair("loss"), n_perm=200, seed=42) == \
        json.loads(WITNESS.read_text(encoding="utf-8"))


def test_explicit_win_rate_equals_the_default():
    ns = _ns()
    pair = _pair("loss")
    assert ns["arm_pair_permutation"](*pair, statistic="win_rate") == ns["arm_pair_permutation"](*pair)


def test_expectancy_statistic_detects_removed_losers():
    out = _ns()["arm_pair_permutation"](*_pair("loss"), n_perm=200, seed=42, statistic="expectancy")
    assert out["observed_delta_expectancy_r"] > 0 and out["p_value"] < 0.05
    assert "observed_delta_win_rate_pp" not in out and out["n"] == 200


def test_expectancy_statistic_does_not_flatter_removed_winners():
    out = _ns()["arm_pair_permutation"](*_pair("win"), n_perm=200, seed=42, statistic="expectancy")
    assert out["p_value"] > 0.05


def test_cli_statistic_flag(tmp_path, capsys):
    baseline, component = _pair("loss")
    blob = {"baseline": [asdict(t) for t in baseline], "component": [asdict(t) for t in component],
            "provenance": build_stamp(stage="validation", signal_window=("2024-01-01", "2025-12-31"),
                                      universe=["T0"], horizons=("4w",), engines=("strategy",), knob_delta={},
                                      engine_hash_baseline="h", engine_hash_component="h", changed_outcomes=1)}
    path = tmp_path / "arms.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    assert _ns()["main"](["--arms", str(path), "--statistic", "expectancy"]) == 0
    assert "observed_delta_expectancy_r" in json.loads(capsys.readouterr().out)
```

- [ ] **Step 4: Capture the witness on v122's UNCHANGED script**

```bash
python - <<'EOF'
import json, pathlib, runpy
from tests.backtesting.test_permutation_test_expectancy import _pair
out = runpy.run_path("scripts/backtest/permutation_test.py")["arm_pair_permutation"](*_pair("loss"), n_perm=200, seed=42)
pathlib.Path("tests/fixtures/v128/permutation_arms_witness.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print(out)
EOF
git diff --quiet -- scripts/backtest/permutation_test.py && echo "permutation_test.py untouched -- witness is pre-change"
python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_expectancy.py
```

Expected: the witness test PASSES. The three `statistic=` tests and the CLI test FAIL with `TypeError: arm_pair_permutation() got an unexpected keyword argument 'statistic'` and `error: unrecognized arguments: --statistic`.

- [ ] **Step 5: Implement (three edits to v122's code)**

Add above `def arm_pair_permutation`:

```python
#: v128: the statistic the null distribution is built on. win_rate is v122's (v72 clause 5);
#: expectancy serves v92's not_luck clause. Same null-arm construction for both.
_STATISTICS = {"win_rate": ("delta_standardised_win_rate", "observed_delta_win_rate_pp"),
               "expectancy": ("delta_expectancy_r", "observed_delta_expectancy_r")}


def _statistic(name: str):
    from swingbot.core.backtesting import acceptance
    function, key = _STATISTICS[name]
    return getattr(acceptance, function), key
```

In `arm_pair_permutation`:
- Change the signature to `def arm_pair_permutation(baseline, component, n_perm: int = 200, seed: int = 42, statistic: str = "win_rate") -> dict:`.
- Add `stat, observed_key = _statistic(statistic)` as its first line.
- Replace `delta_standardised_win_rate(` with `stat(` in the `observed = ...` line and in the `null = [...]` comprehension.
- Replace `"observed_delta_win_rate_pp": observed` in the return dict with `observed_key: observed`. It stays the first key.

Leave `delta_standardised_win_rate` in the function's local import line only if it is still used there; otherwise drop it from that import.

In `_arms_main`, pass `statistic=args.statistic` to `arm_pair_permutation`. In `_parser()`, add `p.add_argument("--statistic", choices=sorted(_STATISTICS), default="win_rate")`.

- [ ] **Step 6: Run the tests and complexity check**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_expectancy.py` and `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py`
Expected: both PASS. v122's own witness and `--arms` tests stay green.
Run: `python -m radon cc -s -n C scripts/backtest/permutation_test.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/permutation_test.py tests/backtesting/test_permutation_test_expectancy.py tests/fixtures/v128/permutation_arms_witness.json
git commit -m "feat(v128): permutation_test.py --arms --statistic expectancy -- dExpR p for v92 not_luck"
```

### Task V128-13: Stage 3, the one VALIDATION shot

**Files:**
- Create: `docs/superpowers/results/2026-10-02-v128-fvg-stage3.md` (replacing a pause note, if one exists), `docs/superpowers/results/2026-10-02-v128-fvg-stage3-win_rate.md`/`.json`, `docs/superpowers/results/2026-10-02-v128-fvg-stage3-harvest.md`/`.json`
- Arms (not committed): `logs/v128/validation-<W>.json`, `logs/v128/perm-wr.json`, `logs/v128/perm-expr.json`, `logs/v128/provenance-validation.json`, `logs/v128/mechanism-validation-<W>.json`, `logs/v128/attr-validation-<W>.md`

**Interfaces:**
- Consumes: the record (V128-7), Stage 1's `<W>`, Stage 2's double PASS, and V128-12's `--statistic`.
- Produces: the Stage 3 verdict: `PASS` iff both gates `PASS`.

- [ ] **Step 1: Preconditions**

Re-read `$PRE` in full. Then check:
- `git status --short -- swingbot/ scripts/backtest/` is empty.
- `git log --oneline -1 -- scripts/backtest/permutation_test.py` is V128-12's commit.
- `stage1.json` names `<W>`, and both `stage2-*.json` say `PASS`.
- `ls logs/v128/validation-*.json` prints nothing. If a validation arms file already exists, the shot was already taken: do not produce another. Score that file (Steps 3–6), or stop and report.

- [ ] **Step 2: Produce the validation arm, once** (`backtest-runner`)

```bash
python scripts/backtest/measure_arms.py --stage validation <W's knobs from the record table> --preregistration $PRE --out logs/v128/validation-<W>.json
```

From this moment the budget is spent. Never regenerate this file (R9).

- [ ] **Step 3: Both permutation p-values**

```bash
python scripts/backtest/permutation_test.py --arms logs/v128/validation-<W>.json --n 200 --seed 42 > logs/v128/perm-wr.json
python scripts/backtest/permutation_test.py --arms logs/v128/validation-<W>.json --n 200 --seed 42 --statistic expectancy > logs/v128/perm-expr.json
```

- [ ] **Step 4: Frozen clause 6 on the validation baseline** (`record` to `backtest-runner`)

```bash
python scripts/backtest/fvg_attribution.py record --arms logs/v128/validation-<W>.json --out logs/v128/provenance-validation.json
python scripts/backtest/fvg_attribution.py report --arms logs/v128/validation-<W>.json --provenance logs/v128/provenance-validation.json --candidate <W> --out-md logs/v128/attr-validation-<W>.md --mechanism-json logs/v128/mechanism-validation-<W>.json
```

- [ ] **Step 5: Score under both gates**

`<p_wr>` and `<p_expr>` are the `p_value` fields of the two JSON files. If either is `null`, omit that run's `--permutation-p` flag entirely: the clause then FAILs, as pre-registered.

```bash
python scripts/backtest/validate_component.py --stage validation --gate win_rate --arms logs/v128/validation-<W>.json --permutation-p <p_wr> --mechanism-json logs/v128/mechanism-validation-<W>.json --title "v128 <W> VALIDATION (v72 win_rate)" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-02-v128-fvg-stage3-win_rate.md --out-json docs/superpowers/results/2026-10-02-v128-fvg-stage3-win_rate.json
python scripts/backtest/validate_component.py --stage validation --gate harvest --arms logs/v128/validation-<W>.json --permutation-p <p_expr> --title "v128 <W> VALIDATION (v92 harvest)" --window "2024-01-01..2025-12-31" --out-md docs/superpowers/results/2026-10-02-v128-fvg-stage3-harvest.md --out-json docs/superpowers/results/2026-10-02-v128-fvg-stage3-harvest.json
```

A crash in Steps 3–5 may be re-run on the same arms file (R9). A verdict is final. Never re-run a step to change one.

- [ ] **Step 6: Write the results file**

`docs/superpowers/results/2026-10-02-v128-fvg-stage3.md` holds:
- The header block, with both the Stage 1–2 and the Stage 3 `engine_hash` and the merge commit that brought v122 in.
- The Stage 3 rule, quoted.
- Links to the two gate docs.
- Both permutation JSONs, pasted.
- The attribution block, including the clause-6 line.
- The overall verdict: `PASS` iff both gate docs say `**Overall: PASS**`.
- Observations.

```bash
git add docs/superpowers/results/2026-10-02-v128-fvg-stage3*.md docs/superpowers/results/2026-10-02-v128-fvg-stage3-*.json
git commit -m "docs(v128): Stage 3 VALIDATION -- <W> <PASS|FAIL> (budget spent)"
```

Go to V128-14 either way.

# Phase 5 — Close-out

### Task V128-14: Closed-table row, Codex mirror check, default flip on PASS only

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (one row in § "Closed pre-registrations — do not re-run these")
- Modify on PASS only, in a separate commit: `swingbot/config.py` (the two `Field` defaults and help text), `swingbot/scan_params.py` (the two dataclass defaults), `.env.example` (the two values), `tests/test_config_fvg_mode.py` (`test_fvg_fields_exist_with_documented_defaults`)

**Interfaces:**
- Consumes: the last committed stage results file.
- Produces: the closed row and, on PASS, the new defaults.

- [ ] **Step 1: Append the closed-table row**

Add one row at the end of the table in `docs/claude/backtest-methodology.md` § "Closed pre-registrations — do not re-run these", in this shape, with measured numbers only:

```markdown
| FVG level source mode, `FVG_LEVELS_MODE` ∈ {`off`, `displacement@k` for `k` ∈ {1.0, 1.5, 2.0}} vs `all` (v128) | **<UNREACHABLE at Stage −1 / REFUSED at Stage 0 / NO-LIFT at Stage 1 (<no-eligible-cell or spike>) / NO-LIFT at Stage 2 / FAILED VALIDATION / PASS>; VALIDATION <not spent, remains available / spent>.** Scored under both the v72 and v92 gates (frozen resolutions R1–R9 in the record). Per candidate at the last stage reached: N, ΔWR pp, ΔExpR R, alert cut %, frozen clause 6 (removed WR vs retained WR, removed ExpR), refusals and their tokens. Top-2 horizon share of removed trades<, flagged if above 80%>. Default `<all / winner and k>`; code merged <inert / live>. Reopening needs a mechanism other than "middle-candle body ≥ k·ATR14 closing in the gap-side third" — the liquidity-sweep and structure halves of the sequence belong to the follow-on spec | `results/2026-10-02-v128-fvg-preregistration.md`, `results/2026-10-02-v128-fvg-stage<last>.md` |
```

- [ ] **Step 2: Codex mirror check**

Run: `grep -n "Closed pre-registrations\|AVWAP_LEVELS_ENABLED (v35)" AGENTS.md`
Expected: no output. On 2026-10-02, `AGENTS.md` does not mirror the closed table, so no mirror edit is needed. If the command does print a match (the table has since been mirrored), add a condensed one-line row in `AGENTS.md`, include it in this commit, and run `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py` (expect PASS).

- [ ] **Step 3: Commit the row**

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v128): close the FVG lift audit pre-registration -- <outcome>"
```

(Add `AGENTS.md` to the `git add` only if Step 2 edited it.)

- [ ] **Step 4: On PASS only — flip the default, in its own commit**

Skip this step for every other outcome: the default stays `all` and the code merges inert.

Let `<mode>` be `off` or `displacement`, and, for displacement, `<k>` the winning `k`.
- `swingbot/config.py`: set `FVG_LEVELS_MODE` `default="<mode>"`. For displacement, also set `FVG_DISPLACEMENT_ATR_K` `default="<k>"`. In the help text, replace "all (default): every unfilled gap, unchanged from before v128." with "all: every unfilled gap (the pre-v128 behaviour)." Mark the winner "(default since <date>, v128 VALIDATION PASS -- see docs/superpowers/results/2026-10-02-v128-fvg-stage3.md)". Keep `_MODE_FALLBACK` at `all`.
- `swingbot/scan_params.py`: set the matching dataclass defaults.
- `.env.example`: set `FVG_LEVELS_MODE=<mode>` (and `FVG_DISPLACEMENT_ATR_K=<k>`), and update the comment's "Default all" sentence.
- `tests/test_config_fvg_mode.py::test_fvg_fields_exist_with_documented_defaults`: expect `"<mode>"` and `"<k>"` (or `"1.5"` for `off`).

`fvg.find_fair_value_gaps`'s own `mode="all"` default and both witnesses stay as they are. The witnesses pin `all` explicitly.

Run each: `python scripts/dev/testrun.py file tests/test_config_fvg_mode.py`, `python scripts/dev/testrun.py file tests/test_env_example_sync.py`, `python scripts/dev/testrun.py file tests/market/test_levels_fvg_mode.py`. Expected: PASS.

```bash
git add swingbot/config.py swingbot/scan_params.py .env.example tests/test_config_fvg_mode.py
git commit -m "feat(v128): FVG_LEVELS_MODE defaults to <mode><@k> -- passed its one VALIDATION shot under both gates"
```

Production: if the Hetzner `.env` sets `FVG_LEVELS_MODE` explicitly, that line wins over the new default. Check with `bash scripts/ops/ssh-hetzner.sh "grep -n FVG_ /opt/swing-bot/.env"` (read-only). Any change there goes through the `mirror-prod` skill.

- [ ] **Step 5: Lifecycle hand-off note**

Moving the spec and plan to `implemented/` or `no-lift/` happens at close-out (`document-lifecycle.md`). The partner types `/close-out` (the Skill tool cannot invoke it). Record the outcome in the final report so the controller can prompt for it.

### Task V128-15: Full-suite verification, then the release bump

**Files:**
- Modify (after green): `VERSION.json`, `swingbot/admin/version_history.json`

**Interfaces:**
- Consumes: everything this plan committed on the branch.
- Produces: a green branch with its `release(bot)` commit, ready for the controller to merge.

- [ ] **Step 1: One full-suite run**

Dispatch the `test-runner` subagent in the worktree to run `python scripts/dev/testrun.py full` once, over everything V128-1..V128-14 changed. Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`testing-cost.md`). **If it is not green, fix forward from the failures it names**; they are this plan's regressions. If a fix touches `swingbot/` after any stage was measured, note in that stage's results file that the measured `engine_hash` predates the fix, and why the fix cannot change scan output (prove it with the two v128 witness tests).

- [ ] **Step 2: Release bump** (working-conventions: the bump goes last, after green)

1. Read `VERSION.json` from disk. Never use a number from this plan or from memory.
2. Increment `bot` at the **patch** level. Leave `ui` untouched.
3. Set `bot_updated` to now, UTC, as `YYYY-MM-DD HH-MM-SS`. Compute it from `date -u` (Git Bash has no timezone data).
4. Regenerate the version history:

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add VERSION.json swingbot/admin/version_history.json
git commit -m "release(bot): <new version> -- FVG level-source mode (<inert, default all | default <mode><@k>>)"
```

Expected: the narrow test PASSES.

- [ ] **Step 3: Hand off**

Report to the controller: the branch name, the last commit, the outcome and the stage reached, and the closed-row text. Merging to `main` follows `worktree-lifecycle` and `superpowers:finishing-a-development-branch`. Do not run either suite again after a conflict-free merge.
