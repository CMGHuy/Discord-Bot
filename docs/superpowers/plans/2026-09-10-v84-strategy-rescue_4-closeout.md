# Strategy Rescue v2 — Part 4: close-out (R41–R45)

Part of `2026-09-10-v84-strategy-rescue_0-index.md` — read its Global
Constraints first. **Run this part only after every strategy in parts 1–3 has
reached a verdict** (rescued or closed). A strategy still mid-measurement blocks
close-out; a strategy that *failed* does not — a recorded failure is a verdict.

---

### Task R41: Full test suite, once

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: every code change from parts 1–3, all merged to the working branch
- Produces: the single green-suite verdict this plan is allowed to claim

This is the **only** full-suite run in the entire plan. Per
`docs/claude/testing-cost.md`, green means `0 failed` and `0 xfailed`; a
*changed* pass count is not a failure (parts 1–3 add tests, so the count will
rise).

- [ ] **Step 1: Confirm every part is merged**

```bash
git log --oneline main..HEAD | head -40
git status --short
```

Expected: commits from parts 1–3 present, working tree clean. If any part is
still on its own worktree branch, merge it before continuing — a partial run
proves nothing.

- [ ] **Step 2: Dispatch the full suite to the test-runner subagent**

Dispatch the `test-runner` subagent with this instruction:

> Run `python scripts/dev/testrun.py full` in the repo root and report only the
> one-line verdict plus any failing test names with their assertion messages. Do
> not paste passing-test output.

Do **not** run it inline — ~1150 progress lines do not belong in the execution
context.

- [ ] **Step 3: Act on the verdict**

Expected: `0 failed`, `0 xfailed`.

If anything fails: fix the failing test's root cause and re-run **only that
file** with `python scripts/dev/testrun.py file <path>` while iterating, then
re-dispatch the full run once. Never mark this task done on an unread verdict.

- [ ] **Step 4: Commit if anything was fixed**

```bash
git add -u
git commit -m "fix(rescue): <what the suite caught>

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

If nothing needed fixing, skip the commit — do not create an empty one.

---

### Task R42: Results doc for every rescued strategy

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-rescue-<slug>-validation.md` (one per strategy that spent a VALIDATION shot)

**Interfaces:**
- Consumes: each VALIDATION run's `--json` output from parts 1–3
- Produces: the permanent record each closed-pre-registration row cites

- [ ] **Step 1: List which strategies actually spent a shot**

```bash
grep -n '"run_date": "2026-09-10"' swingbot/core/backtesting/validation_registry.json
```

Expected: one row per strategy that reached VALIDATION. Strategies that failed a
free stage will NOT appear — they belong to Task R43, not this one.

- [ ] **Step 2: Write one results doc per rescued strategy**

Each doc must contain, in this order: the pre-registered rule **quoted verbatim
from the spec** (not paraphrased), the exact command that was run, the full
results table, the verdict against the rule, and an honest observations section.

Template — fill every field from the run's actual JSON, invent nothing:

```markdown
# v84 rescue — <Strategy> VALIDATION (2026-09-10)

**Edge:** expectancy (Tier 1: none (integrity))
**Pre-registered rule (spec §4.N, verbatim):** <quote>

## Command

<the exact run_backtest_range.py invocation, including --pass-wr 50>

## Result

| Window | N | Win rate | ExpR | Excl% | Verdict |
|---|---|---|---|---|---|
| 2024-01-01..2025-12-31 | | | | | PASS / FAIL |

## Free stages that preceded this shot

| Stage | Result |
|---|---|
| TRAIN | |
| Stage 1 plateau | |
| Stage 2 walkforward (3 folds) | |

## Observations

<What moved, what didn't, and anything that surprised you. Failures are
recorded here, not fixed. If the win rate improved but expectancy fell, say so
plainly — that is the geometry trade, not a win.>
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-rescue-*.md
git commit -m "docs(v84): VALIDATION results for rescued strategies

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task R43: Results doc for every closed (failed) strategy

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-rescue-<slug>-train.md` (one per strategy that failed a free stage)

**Interfaces:**
- Consumes: the TRAIN/grid/fold output for each strategy that never reached VALIDATION
- Produces: the closed record that prevents this hypothesis being retried

**This task is as important as R42.** A negative result closes a component; an
undocumented negative result invites someone to re-run it in six months.

- [ ] **Step 1: Write one doc per failed strategy**

Same template as R42, with the verdict section replaced by:

```markdown
## Verdict: REJECTED-ON-<STAGE>, no VALIDATION shot spent

<N> of <M> grid configurations cleared the pre-registered rule. The budget was
NOT spent and remains available for a genuinely new mechanism.

**Do not re-run this grid.** Reopening this strategy needs a different
mechanism and a new pre-registration, never a re-read of this table or a looser
threshold.
```

If a grid produced zero qualifying configs, the empty table **is** the answer —
write it out in full with every config and its numbers. Do not omit it as
"nothing to report."

- [ ] **Step 2: Verify no failed strategy has a 2026-09-10 registry row**

```bash
grep -n '"strategy"\|"status"\|"run_date"' swingbot/core/backtesting/validation_registry.json
```

Expected: every strategy documented in this task still carries its pre-existing
WEAK row, untouched. A `run_date: 2026-09-10` row for a strategy that failed a
free stage means a VALIDATION shot was spent against the rules — stop and
investigate before going further.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-rescue-*-train.md
git commit -m "docs(v84): closed negative results, no budget spent

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task R44: Registry reconciliation and final badge count

**Files:**
- Modify: `swingbot/core/backtesting/validation_registry.json` (only via `--emit-registry`, never by hand)

**Interfaces:**
- Consumes: every VALIDATION emit from parts 1–3
- Produces: the authoritative badge state this plan leaves behind

Parts 1–3 may have run in separate worktrees. Registry emits are same-key merges
on `(source, strategy, horizon)`, so a concurrent emit can silently drop a row.
This task proves the final file is correct.

- [ ] **Step 1: Verify one row per strategy, no duplicates**

```bash
python -c "
import json,collections
rows=json.load(open('swingbot/core/backtesting/validation_registry.json'))
keys=[(r['source'],r['strategy'],r.get('horizon')) for r in rows]
dupes=[k for k,c in collections.Counter(keys).items() if c>1]
print('duplicate keys:', dupes or 'none')
strat=[r for r in rows if r['source']=='strategy']
print('VALIDATED:', sorted(r['strategy'] for r in strat if r['status']=='VALIDATED'))
print('WEAK:', sorted(r['strategy'] for r in strat if r['status']=='WEAK'))
print('total strategy rows:', len(strat))
"
```

Expected: `duplicate keys: none`, and `total strategy rows: 11` — every strategy
present exactly once. A missing strategy means an emit was lost; recover it by
**re-running that strategy's emit**, never by hand-editing the JSON.

- [ ] **Step 2: Confirm every 2026-09-10 row is justified**

For each row with `run_date: 2026-09-10`, confirm a matching results doc exists
from R42. A registry row with no results doc behind it is evidence that looks
like evidence — the exact thing the emit hard-gates exist to prevent.

- [ ] **Step 3: Record the final count**

Write the before/after badge count into the R45 close-out summary. Starting
state for this plan was **2 VALIDATED (MACD, Volume Profile), 9 WEAK**.

- [ ] **Step 4: Commit if any emit was recovered**

```bash
git add swingbot/core/backtesting/validation_registry.json
git commit -m "fix(registry): recover lost emit for <strategy>

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task R45: Methodology rows, VERSION bump, plan close-out

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed-pre-registrations table)
- Modify: `VERSION.json`
- Move: this plan's part files to `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: R42/R43 results docs, R44's final badge count
- Produces: the closed record that stops this campaign being re-run

- [ ] **Step 1: Add one closed-pre-registration row per strategy**

Append to the table in `docs/claude/backtest-methodology.md` (the table ends
with the `DEAD_CAT_BOUNCE_VETO` row plus the legacy-badge-refresh row added on
2026-09-10). One row per strategy — rescued **and** failed alike. Each row
states: the mechanism, the outcome with real numbers, whether the VALIDATION
budget was spent, and the results-doc path.

Row format, matching the table's existing style:

```markdown
| <Mechanism> (v84, <Strategy>) | **<PASS/REJECTED-ON-TRAIN/FAILED VALIDATION>.** <numbers>. <Budget spent or intact>. Reopening needs a genuinely new mechanism | `results/2026-09-10-v84-rescue-<slug>-<stage>.md` |
```

- [ ] **Step 2: Bump VERSION.json**

Resolve the number **now**, at close-out, from the then-current file — never
from a number predicted when the plan was written.

```bash
cat VERSION.json
```

`Bump: bot minor` — increment the `bot` minor version, reset its patch. Leave
the `ui` line untouched; nothing in this plan changed the frontend.

If **no** strategy was rescued (all eight closed with negative results), the bump
is **`none`** — record the outcome in the results docs and skip this step. No
observable behaviour changed, so there is nothing to release.

- [ ] **Step 3: Update the spec's status line**

In `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md`, change
`**Status:** spec, not yet planned` to `**Status:** implemented — see
plans/implemented/2026-09-10-v84-strategy-rescue_*.md`.

- [ ] **Step 4: Move the plan to implemented/**

```bash
git mv docs/superpowers/plans/2026-09-10-v84-strategy-rescue_0-index.md \
       docs/superpowers/plans/2026-09-10-v84-strategy-rescue_1-tier1.md \
       docs/superpowers/plans/2026-09-10-v84-strategy-rescue_2-tier2.md \
       docs/superpowers/plans/2026-09-10-v84-strategy-rescue_3-tier3.md \
       docs/superpowers/plans/2026-09-10-v84-strategy-rescue_4-closeout.md \
       docs/superpowers/plans/implemented/
```

- [ ] **Step 5: Update memory**

The pooled numbers in `docs/claude/edge-priorities.md` describe a VALIDATED
population that this plan changes. Update that table's row, or — if the pooled
figures were not re-derived in this campaign — add an explicit note that they
are stale and name the date they were last true. Do **not** quote them forward
as current.

- [ ] **Step 6: Commit the close-out**

```bash
git add docs/claude/backtest-methodology.md docs/claude/edge-priorities.md \
        VERSION.json docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md \
        docs/superpowers/plans/
git commit -m "docs(v84): close strategy rescue v2 -- <N> rescued, <M> closed

Final badge state: <X> VALIDATED, <Y> WEAK (from 2 VALIDATED, 9 WEAK).
VALIDATION shots spent: <N> of 8 available.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Report honestly**

The close-out summary states what was rescued **and** what was not, with
numbers. Per the spec's success criteria, a campaign that rescues only Tier 1 is
a success — do not frame a partial result as a shortfall, and do not frame a
total failure as anything other than what it is.
