# v178 Runner give-back levels. Part 3: the record and the close-out (V178-11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V178-11:" -A 300 docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_3-record-and-close-out.md`.

**Spec:** [`docs/superpowers/specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md`](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md) (this part: § The test, stage by stage — **Counting**; § Code facts the plan must honour — the guardrail paragraph; § Phases; header `**Panel:**`)
**Index:** [`2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md`](2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, the script contract, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree, branch `main`); `$WT` = `$R/.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration`. **Never `cd`**: use `git -C $R` and absolute paths. `$DOC` = `docs/superpowers/results/2026-10-19-v178-giveback-levels.md`, created in V178-8 and extended by V178-9 / V178-10.

**Consumed from part 2 (outputs on disk, never re-run here):**
- V178-8: `docs/superpowers/results/v178/pilot-close.json` (`n`, `arms`, `control_b_changed`, `survivors`); the gate verdict `UNMEASURABLE` when `survivors` is empty.
- V178-9: `docs/superpowers/results/v178/funnel-close.json` (`summary`: `n`, `stopped_at`, `stage3_arm`, `best_arm`, `ledger_p`, `holm`, `cells_looked_at`); `docs/superpowers/results/v178/sensitivity-high_low.json` (`summary.cells_looked_at`, only if V178-9 Step 5 ran); the gate verdict `NO-LIFT` when `stage3_arm` is unset.
- V178-10: `docs/superpowers/results/v178/validation-readings.json` (`arm`, `n`, `permutation_p`, `arm_vs_a`), `docs/superpowers/results/v178/validation-gate.json` / `.md` (`verdict`, `clauses`); the stage-3 verdict `PASS` / `FAIL`, or `NOT-RUN (partner)` when the partner declined the shot.
- V178-7: the release commit `release(bot): <version> -- simulator-only adaptive runner give-back modes (v178, inert by default)`, its `chore(bot)` regeneration commit, and the merge commit `merge(v178): adaptive give-back simulator modes, funnel, blocks, measurement script`.

**No full suite in this part.** It ran once, in V178-7, before the merge; this task changes docs, the ledger and one constant, and verifies with narrow runs only.

**Guardrail note for the implementer.** `.claude/hooks/guardrails.py` denies any Bash command whose text names one of the two grid/range backtest scripts together with a closed knob, by plain substring. No command in this task names either script; edit the methodology row and the hook with the Edit tool, not through a shell heredoc that quotes this plan.

---

# Phase 6: Record and close-out (on `main`)

### Task V178-11: Results doc, ledger row, closed row, /panel, /close-out

**Model:** sonnet — copies readings already on disk into fixed templates and runs two rituals; the one trap (an all-caps token in the closed row that the guardrail constant lacks) is pinned by an existing test.

**Runs** after whichever of V178-8, V178-9 or V178-10 ended the funnel (index `## Parallelisation`). Nothing here re-runs, re-reads or re-reports a window: every number comes from the JSON files listed under "Consumed from part 2". A number that is not in those files is not written.

**Files:**
- Modify: `$DOC` = `docs/superpowers/results/2026-10-19-v178-giveback-levels.md` (created in V178-8): a `**Verdict:**` header line, `## Verdict`, `## Ledger row`, later `## Panel review at close-out`
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row, appended by `scripts/reports/preregistration_ledger.py`, never by hand)
- Modify: `docs/claude/backtest-methodology.md` (one row appended to `### Closed pre-registrations — do not re-run these`)
- Modify: `.claude/hooks/guardrails.py` (`CLOSED_PREREGISTRATION_KNOBS` gains `"GIVEBACK_MODE"`, `"GIVEBACK_K"`, `"GIVEBACK_F"`)
- Modify (by `/panel`): `docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md` (`## Panel review at close-out`)
- Move (by `/close-out`): every `docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_*.md` part → `docs/superpowers/plans/implemented/`; the spec → `docs/superpowers/specs/implemented/`
- Test (existing, unchanged): `tests/hooks/test_guardrails.py`, `tests/backtesting/test_preregistration_ledger_file.py`, `tests/hooks/test_doc_sections.py`, `tests/scout/test_scout_merge_parse.py`, `tests/hooks/test_codex_mirror.py`

**Interfaces:**
- Consumes: the part-2 outputs above; existing `scripts/reports/preregistration_ledger.py` (`--id --date --hypothesis --instrument --n --exp-r --p --verdict --record --data-source`; `n` / `exp-r` / `p` accept `null`; a duplicate id exits 2 `refused`); `swingbot/core/backtesting/instrument/stats.py:VERDICTS` (`PASS`, `FAIL`, `NO-LIFT`, `UNMEASURABLE`, …); `guardrails.CLOSED_PREREGISTRATION_KNOBS` (`.claude/hooks/guardrails.py:249`); the `panel` and `close-out` skills.
- Produces: ledger row id `v178-giveback-levels`; the closed-table row naming `GIVEBACK_MODE`, `GIVEBACK_K`, `GIVEBACK_F`; those three names in `CLOSED_PREREGISTRATION_KNOBS` (from then on `_rule_closed_preregistration` denies a grid/range backtest command naming them; `measure_*.py` commands stay unchecked).

**The verdict table (frozen; `p` follows the spec's § Counting rule):**

| What ended the funnel | Result verdict (`$DOC`) | Ledger `--verdict` | `--n` | `--p`, and the name the record gives it |
|---|---|---|---|---|
| V178-8: `pilot-close.json` `survivors` empty | `UNMEASURABLE` (stage −1, every candidate 0 changed outcomes) | `UNMEASURABLE` | pilot `n` | `null` ("no p: nothing reached stage 0") |
| V178-9: `summary.stopped_at == "stage0"` | `NO-LIFT` (stage 0, every arm refused; the spec's base case) | `NO-LIFT` | `summary.n` | `summary.ledger_p` ("pooled fold-train p of the best arm `<best_arm>`") |
| V178-9: `stopped_at` is `stage1` or `stage2`, `stage3_arm` unset | `NO-LIFT` (stage 1 / stage 2) | `NO-LIFT` | `summary.n` | `summary.ledger_p` (same name) |
| V178-10: the partner declined the shot | `NOT-RUN (partner)` at stage 3; stages 0–2 passed by `<stage3_arm>`; VALIDATION unspent | `NO-LIFT` (V178-10 Step 1's option: "record NO-LIFT at stage 2 unspent") | `summary.n` | `summary.ledger_p` (same name; stage 3 did not run) |
| V178-10: `validation-gate.json` `verdict` | `PASS` or `FAIL` (stage 3) | `PASS` / `FAIL` (same) | `validation-readings.json` `n` | `validation-readings.json` `permutation_p` ("stage-3 permutation p, the p the harvest gate read") |

`cells_looked_at`: `sensitivity-high_low.json` `summary.cells_looked_at` when that file exists, otherwise `funnel-close.json` `summary.cells_looked_at`; `"pilot only"` for `UNMEASURABLE`.

- [ ] **Step 1: Read the record fields from disk (one command, no judgement)**

Run (append the single argument `declined` after `python -` if and only if the partner said no in V178-10 Step 1):

```bash
python - <<'EOF'
import json, sys
from pathlib import Path
D = Path("E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/v178")
def load(name):
    p = D / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
pilot, fun, sens = load("pilot-close.json"), load("funnel-close.json"), load("sensitivity-high_low.json")
val, gate = load("validation-readings.json"), load("validation-gate.json")
declined = sys.argv[1:] == ["declined"]
if pilot is None:
    sys.exit("stop: V178-8 has not run")
if not pilot["survivors"]:
    out = {"verdict": "UNMEASURABLE", "ledger": "UNMEASURABLE", "n": pilot["n"], "p": None,
           "p_name": "no p: nothing reached stage 0", "cells": "pilot only", "arm": None}
else:
    if fun is None:
        sys.exit("stop: V178-9 has not reported")
    s = fun["summary"]
    cells = (sens or fun)["summary"]["cells_looked_at"]
    base = {"n": s["n"], "p": s["ledger_p"], "cells": cells,
            "p_name": f"pooled fold-train p of the best arm {s['best_arm']}"}
    if s["stage3_arm"] is None:
        out = {"verdict": "NO-LIFT", "ledger": "NO-LIFT", "arm": s["best_arm"],
               "stopped_at": s["stopped_at"], **base}
    elif declined and val is None:
        out = {"verdict": "NOT-RUN (partner)", "ledger": "NO-LIFT", "arm": s["stage3_arm"], **base}
    elif val is None or gate is None:
        sys.exit("stop: stage3_arm is set but V178-10 has neither run nor been declined")
    else:
        v = "PASS" if gate["verdict"] == "PASS" else "FAIL"
        out = {"verdict": v, "ledger": v, "arm": val["arm"], "n": val["n"], "p": val["permutation_p"],
               "p_name": "stage-3 permutation p, the p the harvest gate read", "cells": cells}
print(json.dumps(out, indent=1))
EOF
```

Expected: one JSON object whose fields match one row of the verdict table. Any `stop:` line: the task does not start; go back to the named task. Keep this output: Steps 2–5 copy from it.

- [ ] **Step 2: Write the verdict into `$DOC`**

1. Under the existing `**Looks:**` header line add `**Verdict:** <verdict> — <one clause: where the funnel stopped, e.g. "every arm refused at stage 0">.`
2. Append `## Verdict` with, in this order:
   - the verdict and the stage that produced it, in one sentence;
   - the ledger fields: `n`, `p` and its name from Step 1 (four decimals), the Holm-adjusted p per arm from `funnel-close.json` `summary.holm` (not for `UNMEASURABLE`), `cells_looked_at`;
   - what stays: "The live fixed 5% (v176) stays. `GIVEBACK_MODE` defaults to `pct`; the range and profit-share modes ship merged and inert (V178-7)." For `PASS` add: "A pass licenses only Phase B's own spec and panel (live parity); nothing live changes until then." For `NOT-RUN (partner)` add: "The partner declined the VALIDATION shot on `<arm>` on <date>; VALIDATION is unspent."
   - the reopening condition, verbatim: "Reopening needs a mechanism other than a runner stop at the best close since TP1 minus k × ATR(14) for k ∈ {0.75, 1.0, 1.25}, or minus max(f × open profit, 1.0 × ATR(14)) for f ∈ {0.25, 0.33, 0.50}. Another k or f, a horizon-scaled multiple, or a different floor is a new pre-registration (spec § Out of scope)."
   - the v92 overlap disclosure and the liquid-universe limit, one line each, copied from the Global Constraints (the frozen block already carries them; the verdict section repeats them because it is the part readers quote).
3. Check: every R number in the section appears in a `docs/superpowers/results/v178/*.json` file (`grep -o` each one); none is re-derived by hand.

- [ ] **Step 3: Append the ledger row (the CLI, never a hand edit)**

Fill `<…>` from Step 1 (`null` where Step 1 printed `null`; `<date>` = today, `YYYY-MM-DD`; `<cells>` = Step 1 `cells`):

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/reports/preregistration_ledger.py \
  --id v178-giveback-levels --date <date> \
  --hypothesis "Runner give-back levels, six arms vs the live fixed 5% off the best close since TP1: range k in {0.75,1.0,1.25} x ATR14 and profit share f in {0.25,0.33,0.50} floored at 1.0 x ATR14, paired on TRAIN through the harvest funnel, <cells> cells looked at (v178)" \
  --instrument v1 --n <n> --exp-r null --p <p> --verdict <ledger> \
  --record docs/superpowers/results/2026-10-19-v178-giveback-levels.md --data-source yfinance
```

Expected: `v178-giveback-levels: verdict <ledger>, p=<p>, …` with a BH q-value; exit 0. Exit 2 `refused` (duplicate id) means a row already exists: stop and report it; never edit or delete a ledger row. Append to `$DOC` a `## Ledger row` section with the printed line verbatim and "the BH q-value is printed for context and never gates (`backtest-methodology.md`)".

- [ ] **Step 4: Verify the ledger file and commit the record**

Run: `python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: PASS (`test_the_committed_ledger_loads_and_validates` and `test_every_record_points_at_a_file_in_the_repo` read the new row; the record path exists since V178-8).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/results/preregistration-ledger.jsonl
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v178): results -- verdict <verdict>, ledger row v178-giveback-levels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

The ledger row lands before the closed row: `test_every_closed_table_version_has_a_ledger_row` fails on a closed row whose version has no ledger row.

- [ ] **Step 5: Append the closed row and watch the guardrail test fail**

With the Edit tool, append **one line** directly after the table's current last row (today the file's last line, `docs/claude/backtest-methodology.md:313`; confirm with `tail -n 2` first), no blank line between: `tests/scout/test_scout_merge_parse.py:test_closed_names_reads_the_table_and_stops_at_the_first_non_table_line` stops reading at the first non-table line, so a gap hides the row. Three cells, no `|` inside any cell.

Component cell (every verdict):

```
| Runner give-back levels, simulator-only module constants: `GIVEBACK_MODE` = range with `GIVEBACK_K` ∈ {0.75, 1.0, 1.25} × ATR(14), and `GIVEBACK_MODE` = profit_share with `GIVEBACK_F` ∈ {0.25, 0.33, 0.50} of open profit floored at 1.0 × ATR(14); runner stop off the best close since TP1, each arm paired against the live fixed 5% (v178) |
```

Outcome cell, by verdict (bold lead, then the readings from `$DOC` § Verdict, then the closing sentences):
- `UNMEASURABLE`: `**UNMEASURABLE at Stage −1 (zero changed outcomes for every candidate); VALIDATION not spent, remains available.**` Pilot window, `n`, per-arm changed (all 0), `control_b_changed`. Stages 0–3 never ran.
- `NO-LIFT`, stage 0: `**REFUSED at Stage 0 for all six arms; VALIDATION not spent, remains available.**` Pooled fold-train window, 75 tickers, paired N, per arm ΔExpR / paired MDE / changed (R0.75, R1.00, R1.25, S0.25, S0.33, S0.50), best arm and its p, Holm. Stages 1–3 never ran.
- `NO-LIFT`, stage 1 or 2: `**CLOSED at Stage <1|2>; VALIDATION not spent, remains available.**` Stage-0 readings as above for the arms that cleared it, then the stage that closed them (family same-sign result, or per fold ΔExpR / changed / improving).
- `NOT-RUN (partner)`: `**Passed Stages 0–2 with <arm>; the partner declined the VALIDATION shot (<date>); recorded NO-LIFT, VALIDATION not spent.**` Stage-2 mean ΔExpR and folds improving.
- `FAIL`: `**FAIL at Stage 3, VALIDATION spent.**` `<arm>`: the failing clause(s) with value and threshold, ΔExpR vs A with CI, permutation p.
- `PASS`: `**PASS at Stage 3, VALIDATION spent.**` `<arm>`: every clause, ΔExpR vs A with CI, permutation p, then "Licenses only Phase B's own spec and panel; do not re-run."

Every outcome cell ends with: cells looked at = `<cells>`; "The fixed 5% stays live; the modes ship merged and inert (default pct)." (`PASS`: "… until Phase B"); "Adjacent to the closed v92 adaptive-trail row (nearest cell trigger_r=2.50, mult=1.50), ruled a new test by the partner and disclosed."; then the reopening sentence from Step 2. Record cell: `` `results/2026-10-19-v178-giveback-levels.md`, ledger `v178-giveback-levels` ``.

**Backtick rule:** inside the whole closed section, any backticked token matching `[A-Z][A-Z0-9_]{4,}` must be in `CLOSED_PREREGISTRATION_KNOBS` (`tests/hooks/test_guardrails.py:393`). Backtick only `GIVEBACK_MODE`, `GIVEBACK_K`, `GIVEBACK_F`; write RUNNER_GIVEBACK_PCT, GIVEBACK_FLOOR_ATR, GATE_MAX_DEGRADATION_R and SLIPPAGE_BPS (if named at all) without backticks, and refer to v92 by "the v92 adaptive-trail row", not its knob name.

Run: `python -m pytest E:/Documents/Private/Projects/Discord-Bot/tests/hooks/test_guardrails.py::test_every_all_caps_knob_in_the_closed_table_is_in_the_constant -v`
Expected: FAIL with `backtest-methodology.md closes ['GIVEBACK_F', 'GIVEBACK_K', 'GIVEBACK_MODE'] but guardrails.py does not list them.` Any other name in that list: remove its backticks from the row; do not add it to the constant.

- [ ] **Step 6: Add the three knobs to the constant**

With the Edit tool, in `.claude/hooks/guardrails.py`, append inside `CLOSED_PREREGISTRATION_KNOBS` after `"HEADROOM_MIN_R",`:

```python
    "GIVEBACK_MODE",   # v178: simulator-only runner give-back levels, closed
    "GIVEBACK_K",
    "GIVEBACK_F",
```

No other change to the hook. `.codex/hooks.json` runs this same file, so there is no Codex hook mirror to edit. A guardrail edit is live only after `/hooks` review; until then follow the rule by hand.

- [ ] **Step 7: Run the narrow tests that read the table, the ledger and the mirror**

```bash
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/hooks/test_guardrails.py
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/scout/test_scout_merge_parse.py
python E:/Documents/Private/Projects/Discord-Bot/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. `test_every_closed_knob_constant_appears_in_the_methodology_doc` and `test_every_all_caps_knob_in_the_closed_table_is_in_the_constant` both pass (both directions); `test_every_closed_table_version_has_a_ledger_row` finds `v178-giveback-levels`; `test_closed_names_against_the_real_methodology_doc` parses the new row. **Codex mirror:** `AGENTS.md` carries no closed-table rows and no knob list (`grep -n "GIVEBACK\|CLOSED_PREREGISTRATION" E:/Documents/Private/Projects/Discord-Bot/AGENTS.md` prints nothing), so it needs no edit; if `test_codex_mirror.py` fails anyway, fix the mirror it names (`python scripts/dev/sync_codex.py` for skills/agents, a condensed `AGENTS.md` line for `docs/claude/`) in this same commit. A failing test is fixed and re-run alone, never by a wider run.

- [ ] **Step 8: Commit the closed row and the constant together**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/claude/backtest-methodology.md .claude/hooks/guardrails.py
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v178): closed pre-registration row -- runner give-back levels <verdict>; guardrail knows GIVEBACK_MODE/K/F

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Add `AGENTS.md` to this commit only if Step 7 required a mirror edit.)

- [ ] **Step 9: Run `/panel` with the spec's roles, before `/close-out`**

Read the roles from disk: `grep -n "^\*\*Panel:\*\*" E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md` (expected: `risk-manager, veteran-trader, quant-researcher`). Resolve the plan's diff from V178-7's merge:

```bash
MERGE=$(git -C E:/Documents/Private/Projects/Discord-Bot log --merges -1 --format=%H --grep="^merge(v178)")
echo "$MERGE^1...$MERGE^2"
```

Invoke the `panel` skill (Skill tool) with args `risk-manager,veteran-trader,quant-researcher <MERGE>^1...<MERGE>^2 docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/results/v178/ docs/claude/backtest-methodology.md`. A panel finding can change wording in `$DOC`, the closed row or the index; it never changes a reading, re-runs a stage or spends VALIDATION (one look). Record `## Panel review at close-out` in `$DOC` (one line per finding: role, number, applied / declined and why) and follow-ups in the index under `## Panel review at close-out` (the v176 pattern, commit 304c95ae). An unresolved `BLOCKING` finding stops the task here: ask the partner through `AskUserQuestion`, one question, recommended option first. If the closed row changed, re-run Step 7's first two commands.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md docs/claude/backtest-methodology.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v178): panel review at close-out -- <one clause: what changed>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 10: Confirm the bump is already on `main` (V178-7), then run `/close-out` without its panel and bump steps**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot log -1 --format="%h %s" -- VERSION.json
git -C E:/Documents/Private/Projects/Discord-Bot log -1 --format="%h %s" -- swingbot/admin/version_history.json
git -C E:/Documents/Private/Projects/Discord-Bot rev-list --count main..2026-10-19-v178-runner-giveback-levels-preregistration
```

Expected: `<sha1> release(bot): <version> -- simulator-only adaptive runner give-back modes (v178, inert by default)`, `<sha2> chore(bot): <version> -- … (v178, inert by default)`, and `0` (the branch is fully merged). Either log line naming something other than v178 means V178-7's bump did not land or another release came after it: stop and report; do not bump here. A non-zero count: stop, the branch carries unmerged work (`docs/claude/git-safety.md`).

Invoke the `close-out` skill (Skill tool) with args:

`plan docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md. Step 2 is done: /panel ran in V178-11 (commit <panel sha>), do not run it again. Steps 3 and 4 do not apply: the bot patch bump was applied in V178-7 (release commit <sha1>, regeneration commit <sha2>) and VERSION.json on disk already carries it; make no second release or chore commit. Run Step 5 (Bump: bot patch and Edge: harvest are what was delivered; amend only if not), Step 6 into implemented/ (the code reached main in V178-7, merged inert; move every _0.._N part and the spec), Step 7 (remove the worktree .claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration and its merged branch with git branch -d).`

Expected: one `docs(v178): close out -- runner give-back levels, <verdict>` commit with the `git mv` of every `2026-10-19-v178-runner-giveback-levels-preregistration_*.md` part into `docs/superpowers/plans/implemented/` and the spec into `docs/superpowers/specs/implemented/`; `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` no longer shows the v178 worktree; `git -C E:/Documents/Private/Projects/Discord-Bot branch --list "*v178*"` prints nothing. No `VERSION.json` change in the close-out commit, and no full-suite run (it ran in V178-7).

- [ ] **Step 11: Final check**

```bash
grep -c '"id": "v178-giveback-levels"' E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/results/preregistration-ledger.jsonl
git -C E:/Documents/Private/Projects/Discord-Bot status --short -- docs/ .claude/hooks/
git -C E:/Documents/Private/Projects/Discord-Bot log --oneline -6
```

Expected: `1`; no v178 file left modified or untracked (`logs/v178/` is not tracked); the log shows, newest first, the close-out, the panel review, the closed row + guardrail, and the verdict + ledger commits.
