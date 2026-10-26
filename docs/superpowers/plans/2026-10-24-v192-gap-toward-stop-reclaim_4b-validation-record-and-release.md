# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 4b: Stage 2, the VALIDATION shot, the record and the release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below; this part never changes a shared name, signature or path. **Never read a part whole:** `grep -n "^### Task V192-25:" -A 420 <this file>`.
**Previous:** [part 4, V192-20..V192-23](2026-10-24-v192-gap-toward-stop-reclaim_4-runs-docs-and-release.md) — the docs, the pre-TRAIN disclosure, Stage −1 and fold-train (Stages 0 and 1 with the basis). Its header lists the measurement CLIs these tasks consume; its scratch renderer `logs/v192/render_census.py` (V192-22 Step 2) is reused here unchanged.

**Scope of this part (V192-24..V192-26):** Stage 2 walk-forward for the selected `g` (V192-24); the one VALIDATION shot, its permutation and report, then the record every closed funnel ends in: results-doc verdict, ledger row, closed-table row on a non-pass and the knob's help text (V192-25); the version bump, the plan's single full-suite run, the merge and `/close-out` (V192-26).

**Where commands run.** The controller enters the worktree as the session root (`EnterWorktree`). Every command below still names the worktree by absolute path, through `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` set at the top of the same shell call, and uses `git -C "$WT"`: subagent shells reset their working directory between calls, and **`cd` is never used** (it breaks the guard hooks). Never edit the main tree's files from a task, except V192-26's merge, which runs `git -C` on the main tree.

## Rules for every measurement task (V192-24, V192-25)

The same rules as part 4's section of this name, repeated so each task here is self-contained:

- **Invoke the `backtest-gate` skill before every `measure_arms.py` command**, not after.
- **Every producer and judge command carries the three variables on the same line** (index § Global Constraints), plus `--data-source alpaca`:

  ```bash
  MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" <args> --data-source alpaca
  ```

  The judges (`validate_component.py`, `permutation_test.py`, `gap_reclaim_report.py`) take the same three variables: their stamp gates call `measure_arms.cached_universe()`, so a judge without `MEASURE_ARMS_UNIVERSE=cache` compares against a different universe and refuses.
- **The knob lists are frozen.** Component: `--knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=<g>`. Baseline: `--baseline-knob MARKET_ENTRY_NEXT_OPEN=true`. `g` is written `0.1`, `0.25`, `0.5` on the command line and `g010`, `g025`, `g050` in file names. No basis pair runs in this part: next-open vs close fill is never read on VALIDATION.
- **Every producer run passes `--preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md"`**, so every stamp names the committed spec; Stage 3 refuses without it.
- **Dispatch the `backtest-runner` agent for every producer command and every report or permutation run.** Give it the exact command, the worktree path and the progress file: the newest `"$WT"/logs/measure_arms.*.progress` (the census after the two arms writes no percent, so the runner reports "census running" until the process exits). **One runner at a time**, never two, never overlapping each other or a full-suite run. The judges' walk-forward and validation readings are quick and run inline.
- **Frozen code.** Until V192-25's last stage file is written, make no edit under `swingbot/` or `scripts/`, and never merge `main` into the worktree. Before each producer run, `git -C "$WT" status --short -- swingbot/ scripts/` prints nothing.
- **A stage that does not advance closes the funnel**: Stage 2 `FAIL`; Stage 3 `FAIL`. Record it as measured and go straight to V192-25's record steps. Never widen a window, add a cell, change a threshold, the MDE ceiling or the reclaim rule, delete a stage file, or re-run Stage 3. Stage 2 is deterministic; re-running it is allowed only to recover from a crash, never to move a number.
- **Census health.** Each veto sidecar carries `repriced_in_component` and `repriced_absent_from_component`. Record both beside the strata at every stage. An absent count above 1% of their sum means the census and the arm disagree: stop and ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop the funnel and inspect the census against the arm rows (Recommended)" / "Record it and continue"). At or below 1% it is recorded and the funnel continues.
- **Numbers come only from the JSON and text files the commands write**, rendered by the snippets in each task, never retyped. Invoke the `pooled-numbers` skill before quoting any ΔExpR, win rate or N in the results doc, a commit message, the closed table or the ledger.
- **Evidence files are committed** when each is under 50 MB (v139 precedent). A file of 50 MB or more is not committed: append its repo-relative path to the file `git -C "$WT" rev-parse --git-path info/exclude` names (local only, never a committed change) and record its size and `sha256sum` in the results doc.
- **No knob goes live and no default changes**, whatever the verdicts: `MARKET_ENTRY_NEXT_OPEN` stays `"false"` and `GAP_RECLAIM_ATR` `"0"`. Any partner question offers the conservative option first, recommended.

---

# Phase 12 (continued) — Stage 2 and the VALIDATION shot


Order: V192-24 (Stage 2 on the selected `g`), then V192-25 (Stage 3, once, and the record), then V192-26 (release). One `backtest-runner` at a time throughout. A funnel closed in part 4 (Stage −1, 0 or 1) or at Stage 2 enters V192-25 at its record steps (Step 8).

### Task V192-24: Stage 2 walk-forward for the selected g

**Model:** sonnet — runs a finished producer and the existing walk-forward judge on frozen inputs and copies their output through fixed renderers; the judgement is limited to the stop-and-report checks spelt out below.

**Files:**
- Create (written by `measure_arms.py`): `docs/superpowers/results/v192/2026-10-24-v192-walkforward.json`, with its `.provenance.json` and its census `2026-10-24-v192-walkforward.gap_reclaim.json`
- Create (written by `validate_component.py --out-json`): `docs/superpowers/results/v192/2026-10-24-v192-stage2.json`
- Modify: `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (the `## Stage 2 walk-forward (folds 2021 / 2022 / 2023)` section)
- Scratch, never committed: `logs/v192/stage2.txt`, `logs/v192/fold_strata.py`, `logs/v192/stage2-strata.txt`

**Interfaces:**
- Consumes: `docs/superpowers/results/v192/2026-10-24-v192-stage1.json` (`verdict`, `selected`) (V192-23); `measure_arms.py ... --stage walkforward` (V192-14, V192-15), whose blob carries `folds` (each `test_year` `"2021"` / `"2022"` / `"2023"`, `baseline`, `component`) and no whole-window rows; `validate_component.py --stage walkforward --arms F --out-json F` (existing, `scripts/backtest/validate_component.py:148`: prints `PASS|FAIL -- stage 2 walkforward win-rate consistency gate` then one JSON fold row per line, writes `{"verdict", "folds"}`, exits 0 on PASS); `logs/v192/render_census.py` (V192-22 scratch); `acceptance.ArmTrade` (`swingbot/core/backtesting/acceptance.py:28`); `gap_reclaim_clauses.strata_split`, `strata_rows` (V192-16; row keys `stratum`, `n`, `decided`, `win_rate`, `expectancy_r`, `baseline_win_rate`, `baseline_expectancy_r`); `gap_reclaim_census.repriced_keys` (V192-15).
- Produces: `2026-10-24-v192-stage2.json` with `verdict` `PASS` | `FAIL`, which V192-25 reads; the Stage 2 section of the results doc.

**Why the judge runs without `--gap-reclaim`:** `gate_win_rate` reads only the three fold rows (standardised ΔWR per fold, the existing v72 rule). V192-18 changed only the census-reading stages and the MDE cluster under the flag and left `--stage walkforward` as it is. The veto-specific reading at this stage (strata per fold, census health) is descriptive and comes from Step 5.

- [ ] **Step 1: Pre-flight — a selected g, code frozen, no walk-forward file yet**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
git -C "$WT" status --short                                   # expected: empty
git -C "$WT" status --short -- swingbot/ scripts/             # expected: empty
python -c "import json, sys; b = json.load(open(sys.argv[1])); print(b['verdict'], b['selected'])" "$V/2026-10-24-v192-stage1.json"
ls "$V" | grep -c "walkforward\|stage2\|validation\|stage3"     # expected: 0
```

Expected: both statuses empty; `selected <g>` with `g` one of `0.1`, `0.25`, `0.5`; `0`. Any other Stage 1 verdict means the funnel closed in V192-23: do not run this task, go to V192-25 Step 8. Set `G` to the selected value and `TAG` to its file tag (`0.1` → `g010`, `0.25` → `g025`, `0.5` → `g050`) for the steps below.

- [ ] **Step 2: Walk-forward run for the selected g**

Confirm the frozen-code status. Invoke `backtest-gate`. Dispatch `backtest-runner` with the worktree path, the progress file, the wall-time estimate (`≈ 0.65 × the selected cell's fold-train veto run`, from V192-23's runner reports: three test years against fold-train's 4.6), and, with `<G>` replaced by the selected value:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=<G> --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage walkforward --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-walkforward.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0` and three files: `ls "$WT"/docs/superpowers/results/v192/2026-10-24-v192-walkforward*`. Any non-zero exit is a fault: stop and report the runner's last 20 lines.

- [ ] **Step 3: Sanity checks before anything is read as a result**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
G=<the selected value>
python - "$WT" "$G" <<'PYEOF'
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
g = float(sys.argv[2])
path = v / "2026-10-24-v192-walkforward.json"
blob = json.loads(path.read_text(encoding="utf-8"))
stamp = blob["provenance"]
prov = json.loads(Path(str(path) + ".provenance.json").read_text(encoding="utf-8"))
side = json.loads((v / "2026-10-24-v192-walkforward.gap_reclaim.json").read_text(encoding="utf-8"))
problems = []
if prov["data_source"] != "alpaca": problems.append(f"data_source {prov['data_source']}")
if stamp["stage"] != "walkforward": problems.append(f"stage {stamp['stage']}")
if stamp["knob_delta"] != {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": g}: problems.append(f"knob_delta {stamp['knob_delta']}")
if stamp.get("baseline_knob_delta") != {"MARKET_ENTRY_NEXT_OPEN": True}: problems.append(f"baseline_knob_delta {stamp.get('baseline_knob_delta')}")
if "2026-10-24-v192-gap-toward-stop-reclaim-design.md" not in str(stamp.get("preregistration")): problems.append("preregistration")
if [f["test_year"] for f in blob["folds"]] != ["2021", "2022", "2023"]: problems.append("folds")
if side["knob_delta"] != stamp["knob_delta"]: problems.append("census knob_delta differs from the stamp")
t = side["summary"]["total"]
if t["reclaimed"] + t["gap_no_reclaim"] > t["armed"] or t["ambiguous"] > t["reclaimed"]: problems.append(f"census counts inconsistent {t}")
if any(not f["baseline"] or not f["component"] for f in blob["folds"]): problems.append("an empty fold")
print("\n".join(problems) or "walk-forward sane")
PYEOF
python "$WT/logs/v192/render_census.py" "$WT/docs/superpowers/results/v192/2026-10-24-v192-walkforward.json"
```

Expected: `walk-forward sane`, then the census as markdown ending with its census-health line. Any problem line is a code bug, not a result: stop, report it, run nothing further. An absent share above 1% stops the funnel for the partner's answer (part rules).

The renderer prints `baseline N 0, component N 0` here: the walk-forward blob carries no whole-window rows, only folds. That line is expected; Step 5 prints the per-fold counts.

- [ ] **Step 4: The Stage 2 gate (inline, quick)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/validate_component.py" --data-source alpaca --stage walkforward --arms "$V/2026-10-24-v192-walkforward.json" --title "v192 gap reclaim -- stage 2 walk-forward" --window 2021-01-01..2023-12-31 --out-json "$V/2026-10-24-v192-stage2.json" > "$WT/logs/v192/stage2.txt" 2>&1
echo "exit $?"; cat "$WT/logs/v192/stage2.txt"
```

Expected: `PASS -- stage 2 walkforward win-rate consistency gate` with `exit 0`, or `FAIL -- ...` with `exit 1`, followed by three JSON fold rows. `REFUSED -- gate_win_rate requires exactly 3 folds ...` or a `refused:...` token is a fault (Step 3 checked the folds): stop and report it.

- [ ] **Step 5: Strata per fold (descriptive, scratch)**

The spec reports removed / re-priced / unchanged WR and ExpR at every stage. Create `"$WT/logs/v192/fold_strata.py"` with exactly this content:

```python
"""v192 scratch (never committed): the frozen strata per walk-forward fold, descriptive only."""
import json
import sys
from pathlib import Path


def fmt(value):
    if value is None:
        return "—"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def main(worktree, arms_path):
    sys.path.insert(0, worktree)
    from swingbot.core.backtesting.acceptance import ArmTrade
    from swingbot.core.backtesting.arms import gap_reclaim_census, gap_reclaim_clauses

    arms = Path(arms_path)
    blob = json.loads(arms.read_text(encoding="utf-8"))
    side = json.loads(arms.with_name(f"{arms.stem}.gap_reclaim.json").read_text(encoding="utf-8"))
    repriced = gap_reclaim_census.repriced_keys(side["rows"])
    head = ("fold", "stratum", "n", "decided", "win_rate", "expectancy_r", "baseline_win_rate",
            "baseline_expectancy_r")
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for fold in blob["folds"]:
        baseline = [ArmTrade(**row) for row in fold["baseline"]]
        component = [ArmTrade(**row) for row in fold["component"]]
        split = gap_reclaim_clauses.strata_split(baseline, component, repriced)
        for row in gap_reclaim_clauses.strata_rows(split):
            print("| " + " | ".join([fold["test_year"]] + [fmt(row[k]) for k in head[1:]]) + " |")
        print(f"| {fold['test_year']} | baseline N {len(baseline)}, component N {len(component)} |"
              + " |" * (len(head) - 2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/logs/v192/fold_strata.py" "$WT" "$WT/docs/superpowers/results/v192/2026-10-24-v192-walkforward.json" > "$WT/logs/v192/stage2-strata.txt"; echo "exit $?"; cat "$WT/logs/v192/stage2-strata.txt"
```

Expected: `exit 0` and a table with four strata rows per fold (`removed`, `repriced`, `added`, `unchanged`) plus one count row per fold. These rows decide nothing at Stage 2; the gate is Step 4's.

- [ ] **Step 6: Write the Stage 2 section**

Invoke the `pooled-numbers` skill, then append to the results doc:

```markdown
## Stage 2 walk-forward (folds 2021 / 2022 / 2023, g = <G>)

Both arms on the next-open market fill; the component adds `GAP_RECLAIM_ATR = <G>`. Gate `gate_win_rate` over the three test years (standardised ΔWR per fold), unchanged from v72.

<`logs/v192/stage2.txt` as printed, in a fenced block.>

### Census

<The renderer's output from Step 3, as printed, without its "baseline N 0, component N 0" line.>

### Strata per fold (descriptive)

<`logs/v192/stage2-strata.txt` as printed.>

**Stage 2 verdict:** <PASS | FAIL>. <"Stage 3 runs once on g = <G>." or "The funnel closes at Stage 2; VALIDATION not spent.">
```

Note any evidence file of 50 MB or more (part rule: excluded locally, size and `sha256sum` recorded here).

- [ ] **Step 7: Commit**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
R=docs/superpowers/results/v192/2026-10-24-v192
git -C "$WT" add "$R-walkforward.json" "$R-walkforward.json.provenance.json" "$R-walkforward.gap_reclaim.json" "$R-stage2.json" docs/superpowers/results/2026-10-24-v192-gap-reclaim.md
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v192): Stage 2 walk-forward on g=<G> -- <PASS|FAIL>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected `status` before the commit: only these five files staged. Leave out of `git add` any file over 50 MB (part rule). On `FAIL`, skip V192-25 Steps 1–7 and go to its Step 8, verdict `NO-LIFT` at Stage 2.

### Task V192-25: Stage 3 VALIDATION, reports, results record, ledger row

**Model:** sonnet — runs the one VALIDATION shot and the record through fixed commands and templates; the judgement is limited to choosing the terminal verdict from the table in Step 8 and the stop-and-ask checks spelt out below.

This task has two halves. **Steps 1–7 run only when Stage 2 passed** (the one VALIDATION shot). **Steps 8–13 always run**: every closed funnel ends here, whichever stage closed it (part 4's V192-22 and V192-23 and this part's V192-24 all point at Step 8).

**Files:**
- Create (Stage 3 only, written by the commands): `docs/superpowers/results/v192/2026-10-24-v192-validation.json` with its `.provenance.json` and its census `2026-10-24-v192-validation.gap_reclaim.json` (`measure_arms.py`); `2026-10-24-v192-permutation.json` (`permutation_test.py --out-json`); `2026-10-24-v192-stage3.json` (`validate_component.py --out-json`); `2026-10-24-v192-report.json` and `2026-10-24-v192-report.md` (`gap_reclaim_report.py`)
- Modify: `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md` (sections `## Stage 3 VALIDATION (2024-01-01..2025-12-31, g = <G>)` when it ran, and `## Verdict`); `docs/superpowers/results/preregistration-ledger.jsonl` (one row, through `scripts/reports/preregistration_ledger.py`, never by hand)
- Modify, on any verdict but `PASS`: `docs/claude/backtest-methodology.md` (one row at the end of the `### Closed pre-registrations — do not re-run these` table), `AGENTS.md` (one clause, the Codex mirror of that row)
- Modify, on every verdict: `swingbot/config.py` (the `GAP_RECLAIM_ATR` field's `help` gains the recorded verdict), `tests/planning/test_v192_config.py` (one test)
- Scratch, never committed: `logs/v192/stage3.txt`, `logs/v192/prediction.txt`, `logs/v192/ledger_fields.py`, `logs/v192/ledger.txt`

**Interfaces:**
- Consumes: `2026-10-24-v192-stage2.json` (`verdict`) (V192-24), `2026-10-24-v192-stage1.json` (`verdict`, `selected`), `2026-10-24-v192-stage0.json` (`verdict`), the `-selection.json` blobs (V192-23), the Stage −1 verdict line (V192-22); `measure_arms.py ... --stage validation` (refuses `refused:no-preregistration` without `--preregistration`; it does **not** refuse an existing output, so the once-only rule is this task's Step 1); `permutation_test.py --arms F --gap-reclaim --n 200 --seed 42 --out-json F --data-source alpaca` (V192-18; JSON keys `observed_delta_win_rate_pp`, `p_value`, `n`, `n_valid`, `seed`, `shift_range`, `removed`, `repriced`, `added`, `statistic`, `instrument`, `verdict`); `validate_component.py --gap-reclaim --stage validation --permutation-p P --out-json F` (V192-18: `evaluate_gap_reclaim` with the sidecar's re-priced keys, `cluster="week"`, a SKIPPED clause fails; prints the acceptance markdown; exits 0 on PASS); `gap_reclaim_report.py --arms F --out-json F --out-md F` (V192-18; `--basis` is refused on VALIDATION; JSON `n` = `{"baseline", "component"}`, `delta_win_rate_pp` / `delta_expectancy_r` = `{"point", "lo", "hi"}`, `strata` = `strata_rows` rows); `scripts/reports/preregistration_ledger.py --id --hypothesis --instrument v1 --n --exp-r --p --verdict --record --data-source alpaca` (exists; prints `<id>: verdict <V>, p=<p>, BH q=<q> across <m> ledger p-values (<k> rows). Reported, not gating.`); `config.FIELDS`, `Field.help` (`swingbot/config.py:75`); `_field(attr)` in `tests/planning/test_v192_config.py` (V192-2).
- Produces: the recorded verdict (results doc `## Verdict`, ledger row `v192-gap-reclaim`, closed-table row on a non-pass), which V192-26 and `/close-out` read.

**Stage 3 — the one VALIDATION shot (Steps 1–7, only after a Stage 2 PASS).**

- [ ] **Step 1: Pre-flight — Stage 2 passed, the shot unspent, the pre-registration unchanged**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
git -C "$WT" status --short                                   # expected: empty
git -C "$WT" status --short -- swingbot/ scripts/             # expected: empty
python -c "import json, sys; print(json.load(open(sys.argv[1]))['verdict'])" "$V/2026-10-24-v192-stage2.json"   # expected: PASS
python -c "import json, sys; print(json.load(open(sys.argv[1]))['selected'])" "$V/2026-10-24-v192-stage1.json"  # the selected g
ls "$V" | grep -c "validation\|permutation\|stage3\|v192-report"   # expected: 0
git -C "$WT" log --format=%h -1 -- docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md
grep -n "last changed in" "$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md"
```

Expected: both statuses empty; `PASS`; the selected `g`; `0`; the spec's latest hash equals the `<spec hash>` the results doc's header recorded in V192-21. Set `G` and `TAG` as in V192-24 Step 1.

Stop conditions, each reported before anything runs:
- Stage 2 is not `PASS`: this half does not run; go to Step 8.
- Any VALIDATION file already exists: the shot may have been spent outside this task. Never run it again; report it and go to Step 8 only on the partner's answer.
- The spec changed after the frozen block: the pre-registration moved under the shot. Stop and ask the partner (`AskUserQuestion`, one question, recommended option first: "Stop: review the spec change against the frozen block before any VALIDATION run (Recommended)" / "Proceed: the change is editorial (typo or link) and touches no frozen value").

- [ ] **Step 2: The VALIDATION run, once**

Confirm the frozen-code status. Invoke `backtest-gate` and state in the dispatch that this is the one shot and is never re-run. Dispatch `backtest-runner` with the worktree path, the progress file, the wall-time estimate (`≈ 0.45 × the selected cell's fold-train veto run`: two years against 4.6), and, with `<G>` replaced:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/measure_arms.py" --knob MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=<G> --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --stage validation --out "$WT/docs/superpowers/results/v192/2026-10-24-v192-validation.json" --preregistration "$WT/docs/superpowers/specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0` and three files: `ls "$WT"/docs/superpowers/results/v192/2026-10-24-v192-validation*`. If the process dies before writing the JSON, do not start it again: ask the partner (`AskUserQuestion`, one question, recommended option first: "Count the shot as spent and record UNMEASURABLE at Stage 3 (Recommended)" / "Run the identical command once more: it wrote no output, so no number was seen"). If the JSON exists but the census sidecar does not (the census only warns on failure), report it: the judge in Step 5 refuses `refused:no-gap-reclaim-sidecar`, and the partner decides.

- [ ] **Step 3: Sanity checks and census health**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
G=<the selected value>
python - "$WT" "$G" <<'PYEOF'
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
g = float(sys.argv[2])
path = v / "2026-10-24-v192-validation.json"
blob = json.loads(path.read_text(encoding="utf-8"))
stamp = blob["provenance"]
prov = json.loads(Path(str(path) + ".provenance.json").read_text(encoding="utf-8"))
side = json.loads((v / "2026-10-24-v192-validation.gap_reclaim.json").read_text(encoding="utf-8"))
problems = []
if prov["data_source"] != "alpaca": problems.append(f"data_source {prov['data_source']}")
if stamp["stage"] != "validation": problems.append(f"stage {stamp['stage']}")
if stamp["knob_delta"] != {"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": g}: problems.append(f"knob_delta {stamp['knob_delta']}")
if stamp.get("baseline_knob_delta") != {"MARKET_ENTRY_NEXT_OPEN": True}: problems.append(f"baseline_knob_delta {stamp.get('baseline_knob_delta')}")
if "2026-10-24-v192-gap-toward-stop-reclaim-design.md" not in str(stamp.get("preregistration")): problems.append("preregistration")
if side["knob_delta"] != stamp["knob_delta"]: problems.append("census knob_delta differs from the stamp")
t = side["summary"]["total"]
if t["reclaimed"] + t["gap_no_reclaim"] > t["armed"] or t["ambiguous"] > t["reclaimed"]: problems.append(f"census counts inconsistent {t}")
if not blob["baseline"] or not blob["component"]: problems.append("an empty arm")
print("\n".join(problems) or "validation sane")
PYEOF
python "$WT/logs/v192/render_census.py" "$WT/docs/superpowers/results/v192/2026-10-24-v192-validation.json"
```

Expected: `validation sane` and the census ending with its census-health line. A problem line is a code bug: stop and report it; the shot stays spent whatever the fix. An absent share above 1% stops for the partner's answer (part rules).

- [ ] **Step 4: The permutation null, re-priced trades held fixed (runner)**

Invoke `backtest-gate`. Dispatch `backtest-runner` with:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/permutation_test.py" --arms "$V/2026-10-24-v192-validation.json" --gap-reclaim --n 200 --seed 42 --out-json "$V/2026-10-24-v192-permutation.json" --data-source alpaca; echo "exit $?"
python -c "import json, sys; b = json.load(open(sys.argv[1])); print({k: b[k] for k in ('observed_delta_win_rate_pp', 'p_value', 'n', 'n_valid', 'removed', 'repriced', 'added', 'verdict')}); print(b['instrument'])" "$V/2026-10-24-v192-permutation.json"
```

Expected: `exit 0`; `n` 200; `instrument` names re-priced trades held fixed. `n_valid` below `n` is reported as printed. A `refused:...` token is a fault: stop and report it.

- [ ] **Step 5: The Stage 3 gate (inline, quick)**

`p_value` comes from the file. When it is `null`, the flag is left out: the permutation clause is then SKIPPED, and a SKIPPED clause fails (frozen).

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
G=<the selected value>
P=$(python -c "import json, sys; p = json.load(open(sys.argv[1]))['p_value']; print('' if p is None else repr(p))" "$V/2026-10-24-v192-permutation.json")
PARGS=${P:+--permutation-p $P}
echo "permutation args: $PARGS"
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/backtest/validate_component.py" --data-source alpaca --gap-reclaim --stage validation --arms "$V/2026-10-24-v192-validation.json" $PARGS --title "v192 gap reclaim g=$G -- stage 3 VALIDATION" --window 2024-01-01..2025-12-31 --out-json "$V/2026-10-24-v192-stage3.json" > "$WT/logs/v192/stage3.txt" 2>&1
echo "exit $?"; cat "$WT/logs/v192/stage3.txt"
python -c "import json, sys; b = json.load(open(sys.argv[1])); print(b['verdict'], b.get('cluster')); [print(c['name'], c['verdict'], c.get('detail')) for c in b['clauses']]" "$V/2026-10-24-v192-stage3.json"
```

Expected: six clauses (`win_rate`, `profit_floor`, `geometry`, `volume`, `permutation`, `mechanism`), cluster `week`, verdict `PASS` (exit 0) or `FAIL` (exit 1). The verdict is `PASS` only when all six clauses pass; any `SKIPPED` clause with a `PASS` verdict is a code bug: stop and report it. A `refused:...` token is a fault: stop and report it (the shot stays spent).

- [ ] **Step 6: The VALIDATION report and the prediction check (runner, then inline)**

No `--basis` here: next-open vs close fill is never read on VALIDATION. Dispatch `backtest-runner` with:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
V="$WT/docs/superpowers/results/v192"
MEASURE_ARMS_UNIVERSE=cache HISTORY_STORE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/market_data BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python "$WT/scripts/reports/gap_reclaim_report.py" --arms "$V/2026-10-24-v192-validation.json" --out-json "$V/2026-10-24-v192-report.json" --out-md "$V/2026-10-24-v192-report.md" --data-source alpaca; echo "exit $?"
```

Expected: `exit 0` and both files. Then the prediction check, from the report only:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT" <<'PYEOF' | tee "$WT/logs/v192/prediction.txt"
import json, sys
from pathlib import Path
v = Path(sys.argv[1]) / "docs/superpowers/results/v192"
rep = json.loads((v / "2026-10-24-v192-report.json").read_text(encoding="utf-8"))
point = lambda x: x["point"] if isinstance(x, dict) else x
strata = {row["stratum"]: row for row in rep["strata"]}
removed, unchanged = strata["removed"], strata["unchanged"]
dwr, dexp = point(rep["delta_win_rate_pp"]), point(rep["delta_expectancy_r"])
parts = [
    ("decided win rate +1.5pp or more (standardised dWR)", dwr, dwr is not None and dwr >= 1.5),
    ("dExpR > 0", dexp, dexp is not None and dexp > 0),
    ("removed WR < unchanged WR", (removed["win_rate"], unchanged["win_rate"]),
     None not in (removed["win_rate"], unchanged["win_rate"]) and removed["win_rate"] < unchanged["win_rate"]),
    ("removed ExpR <= 0", removed["expectancy_r"],
     removed["expectancy_r"] is not None and removed["expectancy_r"] <= 0),
]
for name, value, met in parts:
    print(f"{'MET   ' if met else 'MISSED'} {name}: {value}")
print("prediction:", "met" if all(m for _, _, m in parts) else "missed")
PYEOF
```

Expected: four lines and `prediction: met` or `prediction: missed`. The prediction decides nothing: the gate is Step 5's. A missed prediction is recorded as missed whatever the verdict.

- [ ] **Step 7: Write the Stage 3 section and commit the shot**

Invoke the `pooled-numbers` skill, then append to the results doc:

```markdown
## Stage 3 VALIDATION (2024-01-01..2025-12-31, g = <G>)

The one shot, run once on <date>. Both arms on the next-open market fill; the component adds `GAP_RECLAIM_ATR = <G>`. All six v72 clauses, mechanism and volume from the frozen strata, intervals `week_cluster_bootstrap`, a SKIPPED clause fails.

### Census

<The Step 3 renderer output, as printed.>

### Permutation null (re-priced trades held fixed)

<The Step 4 printed dict and instrument line, in a fenced block.>

### Gate

<`logs/v192/stage3.txt` as printed.>

### Report (descriptive: splits, dollars, ambiguous sensitivity, regime)

<`2026-10-24-v192-report.md` pasted as rendered.>

### Prediction

<`logs/v192/prediction.txt` as printed, in a fenced block.>

**Stage 3 verdict:** <PASS | FAIL>.
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
R=docs/superpowers/results/v192/2026-10-24-v192
git -C "$WT" add "$R-validation.json" "$R-validation.json.provenance.json" "$R-validation.gap_reclaim.json" "$R-permutation.json" "$R-stage3.json" "$R-report.json" "$R-report.md" docs/superpowers/results/2026-10-24-v192-gap-reclaim.md
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v192): Stage 3 VALIDATION on g=<G> -- <PASS|FAIL>, prediction <met|missed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected `status`: only these eight files staged. Leave out of `git add` any file over 50 MB (part rule). From here on the frozen-code rule is lifted: the stage files are written.

**The record (Steps 8–13, every funnel ends here).**

- [ ] **Step 8: Name the terminal stage and the ledger verdict**

The first row whose condition holds decides; the files are the evidence, never memory:

| Funnel closed at | Condition (from the files) | Ledger verdict | VALIDATION |
|---|---|---|---|
| Stage −1 | every cell's reachability reading is not `REACHABLE` (results doc `**Stage −1 verdict:**`) | `UNMEASURABLE` | not spent |
| Stage 0 | `2026-10-24-v192-stage0.json` `verdict` is `closed` | `NO-LIFT` | not spent |
| Stage 1 | `2026-10-24-v192-stage1.json` `verdict` is `no-eligible-cell` or `spike` | `NO-LIFT` | not spent |
| Stage 2 | `2026-10-24-v192-stage2.json` `verdict` is `FAIL` | `NO-LIFT` | not spent |
| Stage 3 | `2026-10-24-v192-stage3.json` `verdict` is `FAIL` (or a crashed shot the partner counted as spent: `UNMEASURABLE`) | `FAIL` | spent |
| — | `2026-10-24-v192-stage3.json` `verdict` is `PASS` | `PASS` | spent |

Create `"$WT/logs/v192/ledger_fields.py"` with exactly this content; it prints the terminal stage and the ledger fields from the files:

```python
"""v192 scratch (never committed): the terminal stage and the ledger row's n / exp_r / p, from the stage files."""
import json
import sys
from pathlib import Path


def load(v, name):
    path = v / f"2026-10-24-v192-{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def fold_train_n(v):
    blob = load(v, "g010-selection")
    return None if blob is None else len(blob["baseline"])


def terminal(v):
    stage3, stage2, stage1, stage0 = (load(v, n) for n in ("stage3", "stage2", "stage1", "stage0"))
    if stage3 is not None:
        report, perm = load(v, "report"), load(v, "permutation")
        dexp = report["delta_expectancy_r"]
        return ("Stage 3", stage3["verdict"], report["n"]["baseline"],
                dexp["point"] if isinstance(dexp, dict) else dexp, perm["p_value"])
    for stage, blob, closing in (("Stage 2", stage2, ("FAIL",)),
                                 ("Stage 1", stage1, ("no-eligible-cell", "spike")),
                                 ("Stage 0", stage0, ("closed",))):
        if blob is not None and blob["verdict"] in closing:
            return (stage, "NO-LIFT", fold_train_n(v), None, None)
    if stage0 is None:
        return ("Stage -1", "UNMEASURABLE", None, None, None)
    raise SystemExit("no closing stage found: the funnel has not ended -- run the next stage first")


if __name__ == "__main__":
    stage, verdict, n, exp_r, p = terminal(Path(sys.argv[1]) / "docs/superpowers/results/v192")
    print(f"stage={stage} verdict={verdict} n={n} exp_r={exp_r} p={p}")
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/logs/v192/ledger_fields.py" "$WT"
```

Expected: one line `stage=<...> verdict=<...> n=<...> exp_r=<...> p=<...>` that agrees with the table above. At Stage 3, `n` is the VALIDATION baseline N, `exp_r` the point ΔExpR and `p` the permutation p; before Stage 3, `n` is the fold-train next-open baseline N and the other two are `null` (the v180 precedent). A Stage 3 crash the partner counted as spent prints the "has not ended" error: record it by hand as `stage=Stage 3 verdict=UNMEASURABLE n=None exp_r=None p=None` and quote the partner's answer in the results doc.

- [ ] **Step 9: The ledger row**

Invoke the `pooled-numbers` skill. With the Step 8 values (`None` written as `null`):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python "$WT/scripts/reports/preregistration_ledger.py" --id v192-gap-reclaim --hypothesis "Market plans fill at the next open; when that open sits at or beyond E -/+ g x ATR14 toward the stop, wait for a same-session reclaim of the planned entry (stop order at E, one adverse tick) or cancel at the close; g in 0.10/0.25/0.50, both arms on the next-open fill, frozen strata removed/re-priced/added/unchanged, a SKIPPED clause fails, re-priced-fixed permutation (v192)" --instrument v1 --n <n> --exp-r <exp_r> --p <p> --verdict <verdict> --record docs/superpowers/results/2026-10-24-v192-gap-reclaim.md --data-source alpaca | tee "$WT/logs/v192/ledger.txt"
tail -1 "$WT/docs/superpowers/results/preregistration-ledger.jsonl"
```

Expected: `v192-gap-reclaim: verdict <V>, p=<p>, BH q=<q> across <m> ledger p-values (<k> rows). Reported, not gating.` and the new last line of the ledger in the worktree. A `refused: ...` (exit 2) means the id exists or a field is malformed: stop and report it; never edit the ledger by hand.

- [ ] **Step 10: The verdict section**

Append to the results doc:

```markdown
## Verdict

**<VERDICT> at <terminal stage>; VALIDATION <spent | not spent, remains available>.** Selected cell: <g = <G> | none>.

- Funnel: Stage −1 <REACHABLE cells / closed cells>; Stage 0 <resolvable / refused>; Stage 1 <selected g | no-eligible-cell | spike | not run>; Stage 2 <PASS | FAIL | not run>; Stage 3 <PASS | FAIL | not run>.
- Prediction (selected cell, VALIDATION): <the four lines of `logs/v192/prediction.txt` | "not tested: VALIDATION not spent">.
- Multiple comparisons: <`logs/v192/ledger.txt` as printed>. Three `g` cells searched; the source, direction and horizon splits are descriptive and rescue nothing.
- Licence: none. `MARKET_ENTRY_NEXT_OPEN` stays `false` and `GAP_RECLAIM_ATR` stays `0` <on a PASS: "until the partner decides; the veto needs `MARKET_ENTRY_NEXT_OPEN` on, which changes every market plan's fill and needs its own pre-registered non-inferiority check (next open vs close fill) before both are flipped. That check keeps VALIDATION unspent for the basis: this record read the basis on fold-train only.">.
- <On any verdict but PASS:> Reopen clause: a fill rule other than a same-session reclaim of the planned entry after a next-open gap toward the stop of `g × ATR14`. Another grid, window, reclaim length or MDE ceiling is not a new mechanism.
```

- [ ] **Step 11: On any verdict but PASS — the closed-table row and its Codex mirror**

Skip this step on `PASS`. Otherwise write the row to `"$WT/logs/v192/closed-row.md"` (scratch), one line, three cells, figures copied from the files:

```markdown
| Gap-toward-stop reclaim veto on market plans — fill at the next open; when that open sits at or beyond `E ∓ g × ATR14` toward the stop, wait for a same-session reclaim of `E` (stop order at `E`, one adverse tick) or cancel at the close; `g` ∈ {0.10, 0.25, 0.50}, both arms on the next-open fill, knobs `MARKET_ENTRY_NEXT_OPEN` + `GAP_RECLAIM_ATR` (v192) | **<VERDICT> at <terminal stage>; VALIDATION <spent | not spent, remains available>.** <The closing reading in one or two sentences, figures from the stage files: e.g. the refused MDE lines, the Stage 1 cell lines, the failing fold rows, or the failing clauses with their values.> Alpaca bars, instrument v1, `cached_universe()`. Both knobs ship merged and inert. Reopening needs a fill rule other than a same-session reclaim of the planned entry after a next-open gap toward the stop of `g × ATR14`; another grid, window, reclaim length or MDE ceiling is not a new mechanism. | `results/2026-10-24-v192-gap-reclaim.md`, ledger `v192-gap-reclaim` |
```

Then append it as the last row of the table under `### Closed pre-registrations — do not re-run these` in `"$WT/docs/claude/backtest-methodology.md"` (rows may have been added by other plans since this one was written, so the script finds the end of the table, never a fixed line):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT/docs/claude/backtest-methodology.md" "$WT/logs/v192/closed-row.md" <<'PYEOF'
import sys
from pathlib import Path
doc, row_file = Path(sys.argv[1]), Path(sys.argv[2])
lines = doc.read_text(encoding="utf-8").splitlines(keepends=True)
start = next(i for i, l in enumerate(lines) if l.startswith("### Closed pre-registrations"))
first = next(i for i in range(start, len(lines)) if lines[i].startswith("|"))
end = next((i for i in range(first, len(lines)) if not lines[i].startswith("|")), len(lines))
row = row_file.read_text(encoding="utf-8").strip() + "\n"
assert row.startswith("| ") and "v192" in row, "the row file must hold the one v192 row"
lines.insert(end, row)
doc.write_text("".join(lines), encoding="utf-8")
print(f"inserted at line {end + 1}")
PYEOF
```

Then mirror it for Codex: in `"$WT/AGENTS.md"`, in the paragraph that says a fill-timing veto "must clear Stage -1 reachability (v192)", replace `(v192)` with `(v192; the v192 gap-toward-stop reclaim veto itself closed <VERDICT> at <terminal stage>, see the closed table)`. Check both edits:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" diff --stat -- docs/claude/backtest-methodology.md AGENTS.md   # expected: 1 insertion each side as described
python "$WT/scripts/dev/doc_section.py" "$WT/docs/claude/backtest-methodology.md" "Closed pre-registrations — do not re-run these" | tail -1 | cut -c1-120
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py   # session root: the worktree, as in parts 1-3
```

Expected: the v192 row is the table's last line; the mirror test `0 failed`.

- [ ] **Step 12: The knob's help names the recorded verdict (test first)**

Append to `"$WT/tests/planning/test_v192_config.py"`:

```python
def test_gap_reclaim_help_names_the_recorded_v192_verdict():
    gap = _field("GAP_RECLAIM_ATR")
    assert "v192 result:" in gap.help
    assert "results/2026-10-24-v192-gap-reclaim.md" in gap.help
    assert any(v in gap.help for v in ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE"))
    assert gap.default == "0"
    assert _field("MARKET_ENTRY_NEXT_OPEN").default == "false"
```

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python scripts/dev/testrun.py file tests/planning/test_v192_config.py   # session root: the worktree, as in parts 1-3
```

Expected: the new test FAILS (`"v192 result:" in gap.help`), every other test passes.

Then in `"$WT/swingbot/config.py"`, extend the `GAP_RECLAIM_ATR` field's `help` string after `"Frozen grid 0.10 / 0.25 / 0.50."` with one more literal: `" v192 result: <VERDICT> at <terminal stage> (docs/superpowers/results/2026-10-24-v192-gap-reclaim.md); stays 0 until the partner decides."`. No other change in the file; the default stays `"0"`.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python scripts/dev/testrun.py file tests/planning/test_v192_config.py   # session root: the worktree, as in parts 1-3
python scripts/dev/testrun.py file tests/infra/test_config_flags.py   # session root: the worktree, as in parts 1-3
git -C "$WT" diff --stat -- swingbot/
```

Expected: both files `0 failed`; the diff touches `swingbot/config.py` only, a few lines.

- [ ] **Step 13: Commit the record (two commits)**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" add docs/superpowers/results/2026-10-24-v192-gap-reclaim.md docs/superpowers/results/preregistration-ledger.jsonl
git -C "$WT" add docs/claude/backtest-methodology.md AGENTS.md 2>/dev/null   # non-PASS only; nothing to add on a PASS
git -C "$WT" status --short
git -C "$WT" commit -m "docs(v192): result -- gap-toward-stop reclaim <VERDICT> at <terminal stage>; ledger row v192-gap-reclaim

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$WT" add swingbot/config.py tests/planning/test_v192_config.py
git -C "$WT" commit -m "docs(config): GAP_RECLAIM_ATR help names the recorded v192 verdict; knobs stay off

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$WT" status --short                                   # expected: empty
```

Expected: two commits; the first stages only the results doc, the ledger and (non-PASS) the two docs. Nothing under `logs/` is committed.

# Phase 13 — Release

### Task V192-26: Version bump, full suite, merge

**Model:** sonnet — release mechanics with fixed commands and one judgement call (stopping on a conflict or a red suite); no product code.

This task is the plan's single full-suite run, then the release, the merge to `main` and `/close-out`. The order matters, and nothing is skipped or reordered:
1. Check the branch is complete.
2. Sync `main` into the branch.
3. Replicate the production database, then run the full suite.
4. Bump the version.
5. Merge.
6. Close out.

No full suite runs after the merge (CLAUDE.md). The code merges whatever the verdict: both knobs ship inert, the flag-off golden (V192-1) pins today's behaviour, and the merged code is what the closed-table row and the knob's help refer to.

**Files:**
- Modify: `VERSION.json` (the `bot` line and its `bot_updated` stamp)
- Modify: `swingbot/admin/version_history.json` (regenerated by `scripts/dev/build_version_matrix.py`, never hand-edited)
- Moves at close-out (done by `/close-out`, listed so the reviewer expects them):
  - The plan files → `docs/superpowers/plans/implemented/`: `_0-index`, `_1-foundations-and-replay`, `_1b-builders-and-replay`, `_2-live-path`, `_2b-alert-and-integration`, `_3-measurement-code`, `_3b-judges-and-reports`, `_4-runs-docs-and-release` and this `_4b` part (implemented, not `no-lift/`, on every verdict: the code reached `main`).
  - The spec → `docs/superpowers/specs/implemented/`.

**Interfaces:**
- Consumes: every commit of V192-1..V192-25 on branch `2026-10-24-v192-gap-toward-stop-reclaim`, including the record commits from V192-25 Step 13.
- Produces: the merged branch on `main`, with two release commits (`release(bot)`, `chore(bot)`), and the close-out commits.

Paths: `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim`, `BR=2026-10-24-v192-gap-toward-stop-reclaim`, `MAIN=E:/Documents/Private/Projects/Discord-Bot`. Run every command in this task with `git -C` / absolute paths, never by `cd`-ing between trees.

- [ ] **Step 1: Check the branch is complete and the main tree untouched**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MAIN=E:/Documents/Private/Projects/Discord-Bot
git -C "$WT" status --short                 # expected: empty
git -C "$WT" log --oneline main..HEAD       # expected: the V192-1..V192-25 commits, ending with the docs(config) help commit
grep -c "^## Verdict" "$WT/docs/superpowers/results/2026-10-24-v192-gap-reclaim.md"   # expected: 1
grep -c '"id": "v192-gap-reclaim"' "$WT/docs/superpowers/results/preregistration-ledger.jsonl"   # expected: 1
git -C "$MAIN" status --short -- swingbot scripts tests VERSION.json docs/claude AGENTS.md   # expected: no v192 path
```

If the record is missing (`0` on either count), V192-25's record steps have not run: stop. If the main tree shows a v192 path (a subagent edited the wrong tree), stop. Compare that diff with the branch's commit for the same file. Revert it in the main tree only if it matches, and report it.

- [ ] **Step 2: Bring `main` into the branch, so the suite runs on what will merge**

The measurement is finished and recorded, so the frozen-code rule no longer applies.

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" rev-list --count HEAD..main    # commits on main the branch lacks
```

If the count is 0, go to Step 3.

Otherwise, run `git -C "$WT" merge --no-edit main` (message `merge: main into v192 before release`).
- On a conflict, stop. Run `git -C "$WT" merge --abort` and report the conflicting paths: another session's work is involved (`worktree-lifecycle` Step 3), and the partner decides.
- `docs/superpowers/results/preregistration-ledger.jsonl` and the closed table in `docs/claude/backtest-methodology.md` are append-only files other plans also append to. A conflict there is still a stop: report it, never resolve it by dropping either side.

- [ ] **Step 3: Replicate the production database, then run the full suite once, through `test-runner`**

The suite includes the V192-3 plan-store round trip, which runs against the shared `swing-db` and must not be left skipped (index § Global Constraints). Invoke the `replicate-prod-db` skill first (read-only on the VM, into the one shared `swing-db` container; CLAUDE.md).

Then dispatch the `test-runner` agent with this exact instruction:

> In `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim`, run `python scripts/dev/testrun.py full` and report only the verdict line, the failed/xfailed test ids if any, the skipped count for `tests/db/test_plans_repository.py`, and the complexity-gate result.

Expected: `0 failed`, `0 xfailed`, no skip in `tests/db/test_plans_repository.py`, complexity gate clean. A changed pass count is not a failure (`testing-cost.md`). No frontend spec runs: v192 changes no file under `frontend/`.

On any failure:
1. Fix it in the file of the task that owns the failing behaviour.
2. Re-run that test alone (`python scripts/dev/testrun.py file <test>`, session root the worktree).
3. Commit `fix(v192): <what> -- <why>`.

Never re-run the full suite for the fix. If a failure is in code no v192 task touched and also fails on `main`, it is pre-existing. Record its id in the task report and carry on; the plan does not fix it. A fix under `swingbot/` that changes a replay or arm path after the runs means the recorded rows no longer match the code: stop and report it before committing, because the partner decides whether the record needs a note.

- [ ] **Step 4: Bump the version, resolved from `VERSION.json` now**

Read `"$WT/VERSION.json"`, never this plan's numbers. After Step 2 it equals `main`'s file. The plan header says **Bump: bot patch**: `bot` `X.Y.Z` → `X.Y.(Z+1)`; `ui` unchanged. At writing `bot` was `2.15.3`. Use the value on disk.

The stamp format is `YYYY-MM-DD HH-MM-SS` in Europe/Berlin time, as in the existing file. Git Bash has no timezone data, so take it from Python:

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
python - "$WT/VERSION.json" <<'PYEOF'
import datetime, json, pathlib, sys, zoneinfo
p = pathlib.Path(sys.argv[1])
v = json.loads(p.read_text(encoding="utf-8"))
major, minor, patch = (int(x) for x in v["bot"].split("."))
v["bot"] = f"{major}.{minor}.{patch + 1}"
v["bot_updated"] = datetime.datetime.now(zoneinfo.ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H-%M-%S")
p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")
print("bot", v["bot"])
PYEOF
git -C "$WT" diff VERSION.json
```

Expected: `bot <next patch>`; the diff shows exactly the `bot` and `bot_updated` lines changed.

Commit `VERSION.json` alone, then regenerate the history and commit it alone (close-out order):

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
git -C "$WT" add VERSION.json
git -C "$WT" commit -m "release(bot): <bot version> -- market-on-open entry and the gap-toward-stop reclaim veto, both inert; v192 measured <VERDICT> at <terminal stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python "$WT/scripts/dev/build_version_matrix.py"
git -C "$WT" status --short                 # expected: only swingbot/admin/version_history.json
git -C "$WT" add swingbot/admin/version_history.json
git -C "$WT" commit -m "chore(bot): <bot version> -- market-on-open entry and the gap-toward-stop reclaim veto, both inert; v192 measured <VERDICT> at <terminal stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

`<VERDICT>` and `<terminal stage>` are copied from the results doc's `## Verdict` line. If `build_version_matrix.py` writes relative to the working directory and the status shows the history changed in the main tree instead, stop: run it from the worktree session root (`python scripts/dev/build_version_matrix.py`) and revert the main-tree file only if its diff is this regeneration.

- [ ] **Step 5: Merge into `main`**

```bash
WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim
MAIN=E:/Documents/Private/Projects/Discord-Bot
BR=2026-10-24-v192-gap-toward-stop-reclaim
git worktree list                                  # the v192 worktree is listed; note any other live worktree
git -C "$MAIN" branch --show-current               # expected: main
git -C "$MAIN" rev-list --count "$BR"..main        # expected: 0
```

A non-zero count means `main` moved since Step 2. Repeat Step 2 in the worktree.
- If the new `main` commits include a `VERSION.json` bump, the merge conflicts on it. Abort the merge, drop nothing, and redo Step 4 on top of `main`'s values in a new release/chore pair, so the history stays release-then-chore.
- Re-run only the tests that the merged-in `main` commits reach: `python scripts/dev/testrun.py changed` (session root the worktree). This is not the full suite.

Then merge from the main tree:

```bash
MAIN=E:/Documents/Private/Projects/Discord-Bot
BR=2026-10-24-v192-gap-toward-stop-reclaim
git -C "$MAIN" merge --no-ff "$BR" -m "merge(v192): market-on-open entry and the gap-toward-stop reclaim veto (both inert), measurement code, results <VERDICT> at <terminal stage>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C "$MAIN" log --oneline -1                    # expected: the merge(v192) commit
git -C "$MAIN" rev-list --count main.."$BR"        # expected: 0
```

If the merge stops on a conflict in the main tree, run `git -C "$MAIN" merge --abort` and report it; do not resolve it there. Do not run the full suite after the merge. Deploying to production is not part of this plan: it is a separate, partner-triggered step (`mirror-prod`), and it changes nothing live because both knobs default off.

- [ ] **Step 6: Run `/close-out`**

Invoke the `close-out` skill (standing permission, CLAUDE.md). Notes for its steps:
- **Panel:** the spec carries `**Panel:** quant-researcher, veteran-trader, quant-engineer`. Run `/panel` with those three roles over `<merge>^1...$BR`, together with the results doc `docs/superpowers/results/2026-10-24-v192-gap-reclaim.md`. An unresolved `BLOCKING` finding stops the close-out.
- **Bump:** already made in Step 4, with its two commits on `main`. Confirm that `VERSION.json` on `main` shows the bumped `bot` value and that `swingbot/admin/version_history.json` was regenerated after it. Do not bump again.
- **Prediction:** check `Bump: bot patch` and `Edge: expectancy` against what shipped (two inert knobs and a pending state for market plans: a patch). Record in the index header whether the pre-registered prediction was met, missed, or not tested (VALIDATION not spent), copied from the results doc's `## Verdict`.
- **Move:** `git mv` the nine plan files (`_0-index`, `_1`, `_1b`, `_2`, `_2b`, `_3`, `_3b`, `_4`, `_4b`) into `docs/superpowers/plans/implemented/`, and the spec into `docs/superpowers/specs/implemented/`. `implemented/`, not `no-lift/`, on every verdict: the code reached `main` (`document-lifecycle.md`).
- **Worktree:** confirm `git rev-list --count main..$BR` is `0`. The branch name contains no `backup` and does not start with `stable-`. Then remove the worktree and delete the branch.

Expected at the end: `git worktree list` no longer shows the v192 worktree. `git -C "$MAIN" log --oneline -6` shows the merge, the two release/chore commits and the close-out move commit.
