# v213 — Skills alignment, part 1b: drift fixes (continued) and the repo-wide case

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v213 — Skills alignment](../specs/2026-11-06-v213-skills-alignment.md)
**Index:** [`2026-11-06-v213-skills-alignment_0-index.md`](2026-11-06-v213-skills-alignment_0-index.md) — Goal, Architecture, **Global Constraints**, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

**Tasks:** V213-5..V213-6 (ledger part 1, carried into this file because part 1 would pass the 1500-line cap; V213-1..V213-4 are in `2026-11-06-v213-skills-alignment_1-lint-and-drift.md`).

**Where to run.** Every path and command below is relative to the worktree root
`.claude/worktrees/2026-11-06-v213-skills-alignment` (created in V213-1); the
implementer's session root is that worktree. Never `cd` inside a Bash command.

# Phase B — Drift fixes (continued)

### Task V213-5: `senior-engineer` wiring and complexity, `staff-engineer` three containers, radon wording in three agents

**Model:** haiku — five exact line replacements given verbatim below, plus the mirror sync; no judgement calls.

**Files:**
- Modify: `.claude/skills/senior-engineer/SKILL.md`
- Modify: `.claude/skills/staff-engineer/SKILL.md`
- Modify: `.claude/agents/task-reviewer.md`
- Modify: `.claude/agents/task-implementer.md`
- Modify: `.claude/agents/plan-briefer.md`
- Modify: generated Codex copies written by `python scripts/dev/sync_codex.py` (`.agents/skills/senior-engineer/**`, `.agents/skills/staff-engineer/**`, `.codex/agents/task-reviewer.toml`, `.codex/agents/task-implementer.toml`, `.codex/agents/plan-briefer.toml`)

**Interfaces:**
- Consumes (V213-2): `python scripts/dev/skill_citations.py`.
- Produces: the complexity wording, exact, in all four places: "`scripts/dev/complexity_gate.py` enforces the limit; `python -m radon cc -s -n C <files>` is for iterating" (matches `docs/claude/code-complexity.md`, which names the gate and radon "while iterating"). V213-10 later edits other items of both skills and must keep these lines.

Each replacement below swaps one whole line (or the named lines) for the new text; the line numbers are from the tree the plan was written against — match on the old text, not the number. Item counts do not change (senior-engineer 12, staff-engineer 13).

- [ ] **Step 1: Confirm the drift the lint sees**

```bash
python scripts/dev/skill_citations.py | grep "skills/senior-engineer/\|skills/staff-engineer/"
```

Expected: `.claude/skills/senior-engineer/SKILL.md:27: swingbot/commands/scanning.py -- missing` (and nothing for `staff-engineer`, whose drift the lint cannot see: "Both containers" is a count, not a path).

- [ ] **Step 2: `senior-engineer` — three checklist items**

In `.claude/skills/senior-engineer/SKILL.md` under `## Checklist`:

Old (:23):
```markdown
- Every function the diff writes or changes is under the limit in `docs/claude/code-complexity.md` (`python -m radon cc -s -n C <files>`); a legacy function already over it got no worse.
```
New:
```markdown
- Every function the diff writes or changes is under the limit in `docs/claude/code-complexity.md` (`scripts/dev/complexity_gate.py` enforces the limit; `python -m radon cc -s -n C <files>` is for iterating); a legacy function already over it got no worse.
```

Old (:27):
```markdown
- Wiring lands where it takes effect: sizing and embed fields in `swingbot/core/scanning/engine.py`, not the posting path in `swingbot/commands/scanning.py` (`.claude/skills/task-brief/SKILL.md` step 3b).
```
New:
```markdown
- Wiring lands where it takes effect: sizing and embed fields in the alert loops before `build_embed()` (`swingbot/core/scanning/scan_run.py`, `short_run.py`, `outlook_run.py`), not the posting package `swingbot/commands/scanning/` (`.claude/skills/task-brief/SKILL.md` step 3b).
```

Old (:28):
```markdown
- Embed fields go through the `sections["headline"]` accumulator in `swingbot/core/scanning/embeds.py`, never a raw `add_field`.
```
New:
```markdown
- Embed fields go through the `sections["headline"]` accumulator in `swingbot/core/scanning/alert_embeds.py`, never a raw `add_field`.
```

- [ ] **Step 3: `staff-engineer` — three containers**

In `.claude/skills/staff-engineer/SKILL.md` under `## Checklist`:

Old (:29):
```markdown
- Both containers (`bot.py`, `admin_ui.py`) still start off the one image, and `docs/deploy/DEPLOY_HETZNER.md` needs no undocumented step.
```
New:
```markdown
- The three containers off the one image (`bot`, `admin`, `refresher`) still start, and `docs/deploy/DEPLOY_HETZNER.md` needs no undocumented step.
```

- [ ] **Step 4: The three agents**

`.claude/agents/task-reviewer.md`, step 3 of the review (two lines, :24-25). Old:
```markdown
3. **Complexity.** `python -m radon cc -s -n C <changed .py files>` — any
   function at C or worse that the diff created or made worse is a finding.
```
New:
```markdown
3. **Complexity.** `scripts/dev/complexity_gate.py` enforces the limit;
   `python -m radon cc -s -n C <files>` is for iterating. Run radon on the
   changed `.py` files — any function at C or worse that the diff created or
   made worse is a finding.
```

`.claude/agents/task-implementer.md` (:35-36). Old:
```markdown
- Every function you write or change stays below cyclomatic complexity 15:
  `python -m radon cc -s -n C <files>` must print nothing for your changes.
```
New:
```markdown
- Every function you write or change stays below cyclomatic complexity 15:
  `scripts/dev/complexity_gate.py` enforces the limit;
  `python -m radon cc -s -n C <files>` is for iterating, and must print
  nothing for your changes.
```

`.claude/agents/plan-briefer.md`, item 3 Excerpts (:30-32). Old:
```markdown
   `path:start-end` so a writer can cite line ranges. Current complexity of
   any function to be changed (`python -m radon cc -s <file>`) — note which
   are already ≥ 15.
```
New:
```markdown
   `path:start-end` so a writer can cite line ranges. Current complexity of
   any function to be changed (`scripts/dev/complexity_gate.py` enforces the
   limit; `python -m radon cc -s -n C <files>` is for iterating) — note which
   are already ≥ 15.
```

- [ ] **Step 5: Verify**

```bash
python scripts/dev/skill_citations.py | grep "skills/senior-engineer/\|skills/staff-engineer/\|agents/task-reviewer\|agents/task-implementer\|agents/plan-briefer"
git grep -n "radon cc" -- .claude/skills/senior-engineer/SKILL.md .claude/agents/task-reviewer.md .claude/agents/task-implementer.md .claude/agents/plan-briefer.md
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py
python scripts/dev/testrun.py file tests/hooks/test_handoff_wiring.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
git status --porcelain
```

Expected: the lint `grep` prints nothing; each `radon cc` line found sits next to `complexity_gate.py` (the joined wording "enforces the limit; … is for iterating"); every `testrun.py` call `VERDICT: PASS`; `git status` lists the five sources and their regenerated copies only.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/senior-engineer/SKILL.md .claude/skills/staff-engineer/SKILL.md .claude/agents/task-reviewer.md .claude/agents/task-implementer.md .claude/agents/plan-briefer.md .agents/skills/senior-engineer/ .agents/skills/staff-engineer/ .codex/agents/task-reviewer.toml .codex/agents/task-implementer.toml .codex/agents/plan-briefer.toml
git commit -m "docs(v213): senior/staff seats and three agents point at today's code

V213-5. senior-engineer wiring goes to the alert loops and alert_embeds.py;
complexity reads 'complexity_gate.py enforces the limit; radon is for
iterating' in the seat and in task-reviewer, task-implementer, plan-briefer;
staff-engineer counts the three containers (bot, admin, refresher).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If `git status` showed a generated file not in that list, add it by its explicit path; a listed path that did not change is harmless.

### Task V213-6: Clear the remaining findings; the repo-wide case lands

**Model:** sonnet — reconciling the real lint output against a known list, judging fix versus allowlist for each line, across many small files; mechanical edits but the judgement must be right.

**Files:**
- Modify: `.claude/skills/quant-researcher/SKILL.md`
- Modify: `.claude/skills/technical-analyst/SKILL.md`
- Modify: `.claude/skills/panel/SKILL.md`
- Modify: `.claude/skills/handoff/SKILL.md`
- Modify: `.claude/agents/plan-writer.md`
- Modify: `tests/hooks/skill_citation_allowlist.txt`
- Modify: `tests/hooks/test_skill_citations.py` (adds `test_repo_has_no_stale_citations`)
- Modify: generated Codex copies written by `python scripts/dev/sync_codex.py` (`.agents/skills/{quant-researcher,technical-analyst,panel,handoff}/**`, `.codex/agents/plan-writer.toml`)

**Interfaces:**
- Consumes (V213-2): `sc.repo_report(ROOT) -> list[str]`, the CLI, the allowlist format `skill|token|reason`; (V213-3..V213-5) their fixes are on the branch.
- Produces: the repo-wide case `test_repo_has_no_stale_citations`, live from this commit on; every later task keeps it green (Global Constraints: from V213-6 on, every task runs `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`). V213-7 and V213-9 later edit `quant-researcher`, `technical-analyst` and `panel` and must keep the cites below intact.

**Fix or allowlist — the rule for every line the CLI prints.** A citation to something that exists today under another path or heading is drift: fix it in the skill (any file under `.claude/skills/**` or `.claude/agents/**` is in scope; name each extra file in the commit body). A mention that is deliberately of something removed, uncommitted, vendored, hypothetical (eval prompts) or runtime-only gets one allowlist line with its reason. Never allowlist drift to make the test pass.

- [ ] **Step 1: Take the current list**

```bash
python scripts/dev/skill_citations.py > "$TMP/v213-6-before.txt"; echo "exit=$?"; cat "$TMP/v213-6-before.txt"
```

Expected: `exit=1`. With V213-3..V213-5 done, the list should hold only the lines dispositioned below (about 38 lines plus the summary); anything else goes through the rule above in Step 5.

- [ ] **Step 2: Add the repo-wide case (failing)**

Append to `tests/hooks/test_skill_citations.py`:

```python
# --- the repository --------------------------------------------------------

def test_repo_has_no_stale_citations():
    """Every skill, agent and eval prompt cites what exists today (v213 § A).

    A failure line reads `<file>:<line>: <token> -- <reason>`. Fix the skill;
    allowlist (tests/hooks/skill_citation_allowlist.txt) only a deliberate
    mention of something removed, uncommitted, vendored or hypothetical. A
    `dead allowlist line` means the mention is gone: delete that line.
    """
    report = sc.repo_report(ROOT)
    assert not report, "\n".join(report)
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: FAIL, one test: `test_repo_has_no_stale_citations`.

- [ ] **Step 3: Fix the real drift**

`.claude/skills/quant-researcher/SKILL.md`, `## Checklist` (three lines; match on the old text):

- In the `SCREEN-PASS` item, `` (`backtest-methodology.md` § Stage −2) `` becomes `` (`backtest-methodology.md` § Funnel stages, Stage −2) `` (Stage −2 is a bullet under `## Funnel stages`, not a heading).
- The closed-pre-registration item, old:
  ```markdown
  - No knob, window or cell from `backtest-methodology.md` § Closed pre-registrations is re-run, re-gridded or re-windowed under a new name.
  ```
  new:
  ```markdown
  - No knob, window or cell is re-run, re-gridded or re-windowed under a new name if `backtest-methodology.md` § Closed pre-registrations — do not re-run these lists it.
  ```
- In the `week_cluster_bootstrap` item, `` (`instrument/stats.py`) `` becomes `` (`swingbot/core/backtesting/instrument/stats.py`) ``.

`.claude/skills/technical-analyst/SKILL.md`, `## Checklist`, old:
```markdown
- Closed ideas in `docs/claude/backtest-methodology.md` § Closed pre-registrations (FVG modes, Fibonacci stops, S/R touch gates) do not return as a new pattern under a new name.
```
new:
```markdown
- Closed ideas (FVG modes, Fibonacci stops, S/R touch gates) do not return as a new pattern under a new name: `docs/claude/backtest-methodology.md` § Closed pre-registrations — do not re-run these.
```

`.claude/skills/panel/SKILL.md`, `## Step 1 — Read the authority`: `` `docs/claude/skills-tools.md` § Expert roles holds the roster `` becomes `` `docs/claude/skills-tools.md` § Expert roles (v145) holds the roster `` (rewrap the line if it passes the paragraph's width; words otherwise unchanged).

`.claude/skills/handoff/SKILL.md`, intro: `` `docs/claude/skills-tools.md` § Plan writing, the paragraph `` becomes `` `docs/claude/skills-tools.md` § Plan writing (two phases), the paragraph ``.

`.claude/agents/plan-writer.md`, `## mode=index` step 3: `` `document-conventions.md` § The plan's Goal section) `` becomes `` `document-conventions.md` § The plan's Goal section explains, it does not label) ``.

The em dash in "— do not re-run these" is U+2014, as in the heading `### Closed pre-registrations — do not re-run these` of `docs/claude/backtest-methodology.md`; the minus in "Stage −2" is U+2212, as in the doc.

- [ ] **Step 4: Write the allowlist lines**

Append to `tests/hooks/skill_citation_allowlist.txt` (below its header):

```text

# --- uncommitted by design: the WSL-key SSH wrapper never enters git (root CLAUDE.md)
prod-inspector|scripts/ops/ssh-hetzner.sh|uncommitted by design; the only way to reach the VM
backup-pull|scripts/ops/ssh-hetzner.sh|uncommitted by design; the only way to reach the VM
replicate-prod-db|scripts/ops/ssh-hetzner.sh|uncommitted by design; the only way to reach the VM
stable-snapshot|scripts/ops/ssh-hetzner.sh|uncommitted by design; the only way to reach the VM
trade-scout|scripts/ops/ssh-hetzner.sh|uncommitted by design; the only way to reach the VM

# --- deleted shims named on purpose (v27 restructure removed them 2026-08-15)
symbol-verifier|core/scan_engine.py|deleted shim, listed so a brief naming it is caught
symbol-verifier|core/scan_embeds.py|deleted shim, listed so a brief naming it is caught
symbol-verifier|core/confidence.py|deleted shim, listed so a brief naming it is caught
symbol-verifier|core/regime.py|deleted shim, listed so a brief naming it is caught
symbol-verifier|core/trade_plan.py|deleted shim, listed so a brief naming it is caught
alert-surface|core/scan_embeds.py|deleted shim, named as the trap it was
alert-surface|core/scan_engine.py|deleted shim, named as the trap it was
task-brief|core/scan_engine.py|trap 3e lists the deleted shims verbatim
task-brief|core/scan_embeds.py|trap 3e lists the deleted shims verbatim
task-brief|core/confidence.py|trap 3e lists the deleted shims verbatim
task-brief|core/regime.py|trap 3e lists the deleted shims verbatim
task-brief|core/trade_plan.py|trap 3e lists the deleted shims verbatim

# --- vendored skill: MCP client config paths on the user's machine, not in this repo
etoro-public-api-operations|~/.claude.json|vendored; a client config path outside the repo
etoro-public-api-operations|~/.cursor/mcp.json|vendored; a client config path outside the repo
etoro-public-api-operations|.cursor/mcp.json|vendored; a client config path outside the repo
etoro-public-api-operations|.vscode/mcp.json|vendored; a client config path outside the repo
etoro-public-api-operations|~/.codeium/windsurf/mcp_config.json|vendored; a client config path outside the repo

# --- eval hypotheticals: a prompt about a file or knob that does not exist
edge-module|swingbot/core/edge/vwap_reclaim.py|eval prompt proposes a new module
replicate-prod-db|tests/charts/test_render.py|eval prompt names a hypothetical unit test
mirror-prod|SCAN_INTERVAL_SECONDS|eval prompt names a hypothetical .env knob
no-lookahead|SCAN_INTERVAL_SECONDS|eval prompt names a hypothetical knob
no-lookahead|SCAN_INTERVAL_SECS|eval prompt names a hypothetical knob

# --- runtime output on the VM, never tracked
stable-snapshot|backups/deploys.jsonl|runtime log written on the VM, never tracked
```

- [ ] **Step 5: Reconcile with the real output**

```bash
python scripts/dev/skill_citations.py; echo "exit=$?"
```

For each line still printed: a finding gets a fix (Step 3's rule) or one allowlist line in the section that fits, with its reason; a `dead allowlist line` is deleted (that mention is gone or resolves). Re-run until it prints `skill citations: clean` and `exit=0`. List every line you added, removed or fixed beyond Steps 3 and 4 for the commit body.

- [ ] **Step 6: Verify**

```bash
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py
python scripts/dev/testrun.py file tests/hooks/test_agent_shape.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
git status --porcelain
```

Expected: every call `VERDICT: PASS`; `git status` lists the five sources, the allowlist, the test file and their regenerated copies. If `test_select_tests.py::test_no_path_a_test_reads_is_classified_inert` fails because the repo-wide case now reads `tests/hooks/skill_citation_allowlist.txt`, `docs/claude/*.md` or the tracked Python, stop and return `BLOCKED:` naming the path (a `DATA_READERS` row in `scripts/dev/select_tests.py` is outside this plan's file list).

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/quant-researcher/SKILL.md .claude/skills/technical-analyst/SKILL.md .claude/skills/panel/SKILL.md .claude/skills/handoff/SKILL.md .claude/agents/plan-writer.md tests/hooks/skill_citation_allowlist.txt tests/hooks/test_skill_citations.py .agents/skills/quant-researcher/ .agents/skills/technical-analyst/ .agents/skills/panel/ .agents/skills/handoff/ .codex/agents/plan-writer.toml
git commit -m "test(v213): repo-wide citation case lands; remaining findings cleared

V213-6. Fixed: quant-researcher (Funnel stages cite, closed-pre-registration
heading, full stats.py path), technical-analyst (closed heading), panel and
handoff (skills-tools.md headings), plan-writer (Goal-section heading).
Allowlisted with reasons: the uncommitted ssh-hetzner.sh wrapper, deleted
v27 shims named on purpose, vendored eToro MCP config paths, eval
hypotheticals, a VM runtime log. The repo-wide case is green from here on.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Add any extra file Step 5 touched by its explicit path, and name it in the commit body.

