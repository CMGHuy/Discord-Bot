# v154 Skill layer repair and token cuts: Part 3, plugins, two slash-only helpers, verification

> Part of the v154 plan. Header, Global Constraints, the decisions fixed by the index, the cross-task contracts C1 to C6, the parallelisation map and the `## Results` table are in [`_0-index`](2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md). **Never read this file whole**: `/task-brief V154-10` or `grep -n "^### Task V154-10" -A 200 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md`](../specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md), sections 4 and 5, the Codex mirror section and Testing.

This part covers tasks V154-9 to V154-13: five unused plugins are switched off for the project, `/result-digest` and `/handoff` are added as slash-only skills, the eval suites and a fresh-session listing are re-run by hand against the skills as finally written, and the full suite runs once.

Rules that hold for every task here:

- All commands run from the root of the plan's worktree, in Git Bash, unless a step says otherwise (V154-12 runs its eval suites from a session that is not worktree-isolated; the step says how).
- **Anchor on text, never on a line number.** Line numbers quoted below are from `main` when this part was written and are there only to help you find the place. Locate every edit with `grep -n` on the quoted text first; if an anchor is missing or appears more than once, stop and report it rather than picking a place.
- **Every commit that touches `.claude/skills/` or `.claude/agents/` runs `python scripts/dev/sync_codex.py` first and stages `.agents/` and `.codex/` with it.** `AGENTS.md` gets its mirror text in the same commit as the change it mirrors.
- Stage files by path only, never `git add -A`. Another session may be editing `CLAUDE.md`, `docs/claude/skills-tools.md` and `.claude/agents/plan-writer.md` in the main tree.
- New skill descriptions are double-quoted scalars (V154-2 made that a pinned rule: `tests/hooks/test_codex_mirror.py::test_every_source_description_is_a_double_quoted_scalar`) with no backslash and no inner `"`. Skill bodies carry no bare threshold: `tests/hooks/test_skill_shape.py::_THRESHOLD_RE` rejects a comparison operator followed by a number and a number followed by `pp` or `R`.

# Phase 3: Plugins, helpers and verification

### Task V154-9: Disable five unused plugins

**Model:** sonnet — configuration plus two doc rewordings, but the plugin keys must be read from the machine and the doc wording checked against what stays enabled.

**Files:**
- Modify: `.claude/settings.json` (`enabledPlugins`, five entries added)
- Modify: `docs/claude/skills-tools.md` (the `feature-dev:code-reviewer` bullet, about line 18; the `**Plugins off for this project (v107)**` bullet, about lines 26-34)
- Modify: `AGENTS.md` (one paragraph at the end of `## Skills: the same ones Claude uses`)
- Modify: `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md` (one row of `## Results`)

**Interfaces:**
- Consumes: nothing from earlier tasks. This task is in wave 1 and may run before V154-1.
- Produces: `AGENTS.md` § Skills: the same ones Claude uses ends with the disabled-plugin paragraph (index contract C6). V154-7, V154-10 and V154-11 also edit `AGENTS.md`, in other places; they leave this paragraph alone.

What changes, from the spec § 4: `enabledPlugins` gains `false` for `feature-dev`, `code-simplifier`, `claude-code-setup`, `claude-md-management` and the plugin-marketplace `skill-creator`. `frontend-design`, `code-review`, `commit-commands` and `superpowers` stay enabled and get no entry. The `anthropic-skills:*` skills (including `anthropic-skills:skill-creator`, the other copy) and the claude.ai connectors cannot be disabled locally and are not touched. No test file pins `enabledPlugins` today (`git grep -n enabledPlugins -- tests` is empty) and the index ledger gives this task no test file, so the check in Step 2 is a one-off script whose verdict is recorded in `## Results`.

- [ ] **Step 1: Read the five keys from the installed plugin list**

The keys are never guessed (Global Constraints). Read them from the active config dir:

```bash
python - <<'PYEOF'
import json, os, pathlib
root = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
path = root / "plugins" / "installed_plugins.json"
data = json.loads(path.read_text(encoding="utf-8"))
keys = sorted((data.get("plugins") or data).keys())
print(path)
wanted = ("feature-dev", "code-simplifier", "claude-code-setup",
          "claude-md-management", "skill-creator")
for name in wanted:
    hits = [k for k in keys if k.split("@", 1)[0] == name]
    print(f"{name:22s} {hits}")
PYEOF
```

Expected, as read on 2026-10-10 from every local config dir (`config-meo`, `config-personal`, `config-bo`, `config-work`): each of the five has exactly one hit, and all five end in `@claude-plugins-official`:

```
feature-dev            ['feature-dev@claude-plugins-official']
code-simplifier        ['code-simplifier@claude-plugins-official']
claude-code-setup      ['claude-code-setup@claude-plugins-official']
claude-md-management   ['claude-md-management@claude-plugins-official']
skill-creator          ['skill-creator@claude-plugins-official']
```

If any name has zero hits or more than one, stop and ask the partner which key to use (`AskUserQuestion`); never write a key you did not read. Keep the printed path for Step 7.

- [ ] **Step 2: Run the target-state check and watch it fail**

It loads `.claude/settings.json` and asserts the state this task produces:

```bash
python - <<'PYEOF'
import json, pathlib
settings = json.loads(pathlib.Path(".claude/settings.json").read_text(encoding="utf-8"))
plugins = settings["enabledPlugins"]
off = {"feature-dev@claude-plugins-official", "code-simplifier@claude-plugins-official",
       "claude-code-setup@claude-plugins-official",
       "claude-md-management@claude-plugins-official",
       "skill-creator@claude-plugins-official"}
kept = {"frontend-design", "code-review", "commit-commands", "superpowers"}
missing = sorted(k for k in off if plugins.get(k) is not False)
wrongly_off = sorted(k for k, v in plugins.items()
                     if v is False and k.split("@", 1)[0] in kept)
print("entries:", len(plugins))
print("missing:", missing)
print("wrongly off:", wrongly_off)
assert not missing and not wrongly_off and len(plugins) == 15
print("PLUGIN CHECK PASS")
PYEOF
```

Expected now: `entries: 10`, `missing:` lists all five keys, then `AssertionError`. If Step 1 read a different key for any plugin, put that key in the `off` set before running.

- [ ] **Step 3: Add the five entries to `.claude/settings.json`**

Find the anchor with `grep -n '"pdf-viewer@synced": false' .claude/settings.json`; expected exactly one hit, the last entry of `"enabledPlugins"`. Replace:

```json
    "pdf-viewer@synced": false
  },
```

with:

```json
    "pdf-viewer@synced": false,
    "feature-dev@claude-plugins-official": false,
    "code-simplifier@claude-plugins-official": false,
    "claude-code-setup@claude-plugins-official": false,
    "claude-md-management@claude-plugins-official": false,
    "skill-creator@claude-plugins-official": false
  },
```

Use the keys Step 1 printed if they differ. Change nothing else in the file.

- [ ] **Step 4: Run the check again**

Run the Step 2 script unchanged.

Expected: `entries: 15`, `missing: []`, `wrongly off: []`, `PLUGIN CHECK PASS`.

- [ ] **Step 5: Reword `docs/claude/skills-tools.md`**

Edit 1, the stale review recommendation (spec § 4: it names a plugin this task disables). Find it with `grep -n "feature-dev:code-reviewer" docs/claude/skills-tools.md`; expected exactly one hit. Replace these two lines:

```markdown
- `Explore` subagent for wide code searches; `feature-dev:code-reviewer` or
  `/code-review` for review passes. `backtest-runner` for any backtest/grid/
```

with:

```markdown
- `Explore` subagent for wide code searches; `/code-review` (the
  `code-review` plugin) for review passes. `backtest-runner` for any backtest/grid/
```

Edit 2, the disabled-plugins bullet. Find it with `grep -n "Plugins off for this project (v107)" docs/claude/skills-tools.md`; expected exactly one hit. Replace the whole bullet, from that line through `connector (claude.ai-served) and the built-in skills.`:

```markdown
- **Plugins off for this project (v107)** — `.claude/settings.json`
  `enabledPlugins` disables the claude.ai-synced knowledge-work plugins
  (`small-business`, `legal`, `finance`, `product-management`, `data`,
  `engineering`, `productivity`, `pdf-viewer`, all `@synced`) and the
  `chrome-devtools-mcp`/`playwright` MCP plugins, which also removes their
  MCP servers. Project scope only; user settings are untouched. Need one for
  a session? `claude --settings` or a `settings.local.json` override.
  Not locally disableable: `anthropic-skills:*` and the Claude Docs
  connector (claude.ai-served) and the built-in skills.
```

with:

```markdown
- **Plugins off for this project (v107, v154)** — `.claude/settings.json`
  `enabledPlugins` disables the claude.ai-synced knowledge-work plugins
  (`small-business`, `legal`, `finance`, `product-management`, `data`,
  `engineering`, `productivity`, `pdf-viewer`, all `@synced`), the
  `chrome-devtools-mcp`/`playwright` MCP plugins, which also removes their
  MCP servers, and (v154) the development plugins this repo never uses:
  `feature-dev`, `code-simplifier`, `claude-code-setup`,
  `claude-md-management` and the marketplace copy of `skill-creator`, all
  `@claude-plugins-official`, whose skills and agents were listed in every
  session and every subagent. `frontend-design`, `code-review`,
  `commit-commands` and `superpowers` stay on. Project scope only; user
  settings are untouched. Need one for a session? `claude --settings` or a
  `settings.local.json` override.
  Not locally disableable: `anthropic-skills:*` (including its own
  `skill-creator`) and the Claude Docs connector (claude.ai-served) and the
  built-in skills.
```

If the bullet on disk differs from the text to replace (another session edited it), stop and report the difference instead of merging by hand.

- [ ] **Step 6: Add the mirror paragraph to `AGENTS.md`**

Find the anchor with `grep -n "^lowers a gate\.$" AGENTS.md`; expected exactly one hit, the last line of the expert-role paragraph in `## Skills: the same ones Claude uses`. Confirm with `grep -n "^## Efficient repository navigation" AGENTS.md` that the heading sits two lines below it. Insert one blank line and this paragraph after `lowers a gate.`, so one blank line still separates the new paragraph from `## Efficient repository navigation`:

```markdown
Claude Code plugins switched off for this project in `.claude/settings.json`
`enabledPlugins`, so none of their skills or agents load: the claude.ai-synced
knowledge-work plugins (`small-business`, `legal`, `finance`,
`product-management`, `data`, `engineering`, `productivity`, `pdf-viewer`),
the `chrome-devtools-mcp` and `playwright` MCP plugins, and (v154)
`feature-dev`, `code-simplifier`, `claude-code-setup`, `claude-md-management`
and the marketplace `skill-creator`. Codex has no counterpart to switch off;
do not name their skills or agents (for example `feature-dev:code-reviewer`)
as a next step.
```

Change nothing else in `AGENTS.md`.

- [ ] **Step 7: Record the keys in `## Results`**

In `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md`, under `## Results`, find the row with `grep -n "Plugin keys read from the installed list" docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md` and replace its `_not yet run_` with this cell, filling in the date and the path Step 1 printed:

```markdown
<YYYY-MM-DD>: read from `<path printed in Step 1>`; `feature-dev@claude-plugins-official`, `code-simplifier@claude-plugins-official`, `claude-code-setup@claude-plugins-official`, `claude-md-management@claude-plugins-official`, `skill-creator@claude-plugins-official` (one hit each); Step 4 check `PLUGIN CHECK PASS`, 15 entries
```

Write the keys Step 1 actually printed if they differ from these.

- [ ] **Step 8: Run the hook tests that read these files**

```bash
python scripts/dev/sync_codex.py --check
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_guardrails.py
```

Expected: `Codex mirror is current.`, then `VERDICT: PASS` twice. No skill or agent changed, so do not run `sync_codex.py` without `--check` here.

- [ ] **Step 9: Commit**

```bash
git add .claude/settings.json docs/claude/skills-tools.md AGENTS.md docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md
git status --short
git commit -m "chore(claude): disable five unused plugins for this project (V154-9)"
```

`git status --short` must show only those four paths staged.

---

### Task V154-10: `/result-digest` slash-only skill

**Model:** sonnet — a new skill file, three test-set edits and one pinning test, all given verbatim; the care is in keeping the body free of thresholds and the reply verbatim.

**Files:**
- Create: `.claude/skills/result-digest/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_2`, `FORKED` and its comment, one new test at the end)
- Modify: `AGENTS.md` (the "Explicit-only rituals" paragraph in `## Skills: the same ones Claude uses`)
- Regenerated by `python scripts/dev/sync_codex.py`: `.agents/skills/result-digest/SKILL.md`, `.agents/skills/result-digest/agents/openai.yaml`

**Interfaces:**
- Consumes:
  - `_read_skill(name) -> (dict[str, str], str)` in `tests/hooks/test_skill_shape.py`, reading through `parse_frontmatter` since V154-3. A value comes back without its double quotes.
  - Every source `description:` must be a double-quoted scalar (`tests/hooks/test_codex_mirror.py::test_every_source_description_is_a_double_quoted_scalar`, V154-2).
  - `sync_codex.py` re-emits `name` and `description` only, quoting the description through `quote_value` (V154-2), and writes `agents/openai.yaml` for a skill with `disable-model-invocation: true`.
  - `AGENTS.md` already carries V154-9's disabled-plugin paragraph and V154-7's `doc_section.py` bullet; neither is touched here.
- Produces: `"result-digest"` in `TIER_2` and in `FORKED` (as `"result-digest": "haiku"`); the `AGENTS.md` ritual sentence ending `... and `result-digest` (...)` that V154-11 extends; the module constant `DIGEST_DISCLAIMER` in `test_skill_shape.py`.

**What the skill is (spec § 5).** `/result-digest <a.json> <b.json>` runs `scripts/backtest/compare_backtest_json.py` on two `run_backtest_range.py --json` outputs in a forked `haiku` context and returns the script's output **verbatim**, prefixed with the two paths and ending with a fixed disclaimer line. Both files are required: the script reads `sys.argv[1]` and `sys.argv[2]` and has no one-file mode. The script prints no window and a hard-coded `=== v35 AVWAP comparison {label} ===` header, so the skill adds one line saying the header is the script's and the window is whatever the files were run on. It never paraphrases a figure and never says pass. Given a file the script cannot read, it returns the script's error verbatim and no figures.

- [ ] **Step 1: Write the failing tests in `tests/hooks/test_skill_shape.py`**

Three edits; find each anchor with `grep -n` first.

Edit 1, the Tier 2 set (`grep -n "^TIER_2 = " tests/hooks/test_skill_shape.py`, one hit). Replace

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel"}        # each ritual task appends its own name
```

with

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest"}        # each ritual task appends its own name
```

Edit 2, the forked set and its comment (`grep -n "^FORKED = " tests/hooks/test_skill_shape.py`, one hit). Replace

```python
# v107: mechanical slash skills run forked on a cheaper model. task-brief is
# sonnet, not the spec's haiku: its trap preflight is judgement, and a missed
# trap costs a whole implement/review loop.
FORKED = {"gate": "sonnet", "task-brief": "sonnet"}
```

with

```python
# v107: mechanical slash skills run forked on a cheaper model. task-brief is
# sonnet, not the spec's haiku: its trap preflight is judgement, and a missed
# trap costs a whole implement/review loop. v154: result-digest runs one
# script and returns its output untouched, which needs no judgement: haiku.
FORKED = {"gate": "sonnet", "task-brief": "sonnet", "result-digest": "haiku"}
```

Edit 3, append at the very end of the file (after the last line of `test_backup_skills_match_the_v120_final_fixes`, with two blank lines before the new code):

```python
# v154: the fixed line /result-digest ends every reply with. The figures it
# hands back are derived from two files, never the live book.
DIGEST_DISCLAIMER = ("Derived by compare_backtest_json.py from the named files; "
                     "not live-book figures — re-derive per pooled-numbers before "
                     "quoting in a spec, plan or commit.")


def test_result_digest_returns_the_script_output_verbatim():
    """v154: a small model paraphrases figures. The skill runs the one script
    on both files, hands its output back untouched, explains the script's
    hard-coded header and missing window, and ends with the disclaimer."""
    _, body = _read_skill("result-digest")
    assert "python scripts/backtest/compare_backtest_json.py <a.json> <b.json>" in body
    assert "$ARGUMENTS" in body
    assert "**verbatim**" in body
    assert "never call a result a" in body
    assert '"=== v35 AVWAP comparison ===" line is the script\'s own' in body
    assert "the script prints none" in body
    assert "no figures anywhere in the reply" in body
    assert DIGEST_DISCLAIMER in body
```

The `—` in `DIGEST_DISCLAIMER` is an em dash (U+2014), the same character the skill uses; the Edit tool writes it as is.

- [ ] **Step 2: Run the shape tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`

Expected: `VERDICT: FAIL` with `4 failed`. The four are `test_mechanical_skills_run_forked[result-digest]`, `test_ritual_skills_are_slash_only` and `test_result_digest_returns_the_script_output_verbatim` (each a `FileNotFoundError` on `.claude/skills/result-digest/SKILL.md`), and `test_every_skill_is_registered_in_exactly_one_tier` (the tiers name a skill that is not on disk). Any other failure is a mistake in Step 1.

- [ ] **Step 3: Create `.claude/skills/result-digest/SKILL.md`**

Write this file exactly (Write tool; the file starts at `---`):

````markdown
---
name: result-digest
description: "Run scripts/backtest/compare_backtest_json.py on two run_backtest_range.py --json files and return its output verbatim, prefixed with both paths and ending with a derived-figures disclaimer. Invoked explicitly as /result-digest <a.json> <b.json>, never model-triggered."
disable-model-invocation: true
context: fork
model: haiku
---

# Result digest

You are a pipe, not an analyst. You run one script on two files and hand its
output back **verbatim**. You never paraphrase, round, reorder, summarise or
recompute a figure, never add a figure of your own, and never call a result a
pass, a fail, better or worse. Judging a result is `backtest-gate`'s job;
quoting one is `pooled-numbers`'.

## Step 1 — Take exactly two paths

Arguments: `$ARGUMENTS`

They must be exactly two paths to `run_backtest_range.py --json` outputs. The
first fills the script's OFF row, the second its ON row. The script has no
one-file mode. With any other number of arguments, reply with this one line
and stop, running nothing:

`Usage: /result-digest <a.json> <b.json> -- both files are required.`

## Step 2 — Run the script

```bash
python scripts/backtest/compare_backtest_json.py <a.json> <b.json>
```

Pass the two paths exactly as given, in the same order, and no third (label)
argument. Capture its stdout and stderr together, and its exit code.

## Step 3 — Reply with this, and nothing else

```
/result-digest
A (OFF row): <a.json as given>
B (ON row):  <b.json as given>
Header: the "=== v35 AVWAP comparison ===" line is the script's own,
hard-coded; it does not mean these files are an AVWAP run. The window is
whatever the two files were run on; the script prints none.

<the script's complete output, verbatim, inside a fenced block>

Derived by compare_backtest_json.py from the named files; not live-book figures — re-derive per pooled-numbers before quoting in a spec, plan or commit.
```

If the script exits non-zero (a missing file, unreadable JSON, a file that is
not a `--json` output), the fenced block holds its error output verbatim and
there are no figures anywhere in the reply. Do not explain the error, retry
with other paths or repair the files.

## The gate

The reply is the block above: both paths, the header line, the script's
output or error untouched, and the closing disclaimer line exactly as written.
````

Constraints the file must keep (the shape tests check them): at most 80 lines (it is 60); no comparison operator followed by a number and no number followed by `pp` or `R` anywhere in the body (`_THRESHOLD_RE`), so do not paste a sample of the script's output into it; the `description:` value stays inside double quotes with no inner `"`.

- [ ] **Step 4: Name the skill in `AGENTS.md`**

Find the ritual sentence with `grep -n "sequence), \`stable-snapshot\` (pin a known-good point) and \`backup-pull\` (off-VM" AGENTS.md` (expected one hit, in the paragraph that starts `Explicit-only rituals, never implicitly triggered`). Replace these two lines

```markdown
sequence), `stable-snapshot` (pin a known-good point) and `backup-pull` (off-VM
backup pull). `new-doc` (new spec or plan) and `close-out` (plan close-out) may
```

with these four

```markdown
sequence), `stable-snapshot` (pin a known-good point), `backup-pull` (off-VM
backup pull) and `result-digest` (two backtest `--json` files through
`compare_backtest_json.py`, output returned verbatim, never judged). `new-doc`
(new spec or plan) and `close-out` (plan close-out) may
```

The next line (`also be run implicitly: ...`) and everything else in `AGENTS.md` are unchanged.

- [ ] **Step 5: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`

Expected last line: `Codex mirror is current.` Then:

```bash
git status --short
head -3 .agents/skills/result-digest/SKILL.md
```

`git status --short` shows `tests/hooks/test_skill_shape.py` and `AGENTS.md` modified, and `.claude/skills/result-digest/` and `.agents/skills/result-digest/` untracked, and nothing else this task did. The `head` prints `---`, `name: result-digest` and the `description:` line with the value in double quotes. `.agents/skills/result-digest/agents/openai.yaml` exists (slash-only skills are never implicitly invoked by Codex). If `sync_codex.py` rewrites any other skill, another skill commit is in flight: skill commits are serial, so stop and let that one land first. A line `AGENTS.md never mentions \`result-digest\`` means Step 4's backticks are wrong.

- [ ] **Step 6: Run the narrow tests**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py tests/hooks/test_codex_mirror.py`

Expected: `VERDICT: PASS`, nothing failed. `test_skill_shape.py` now checks the new skill's name, description length, 80-line budget, absence of thresholds, `context: fork` with `model: haiku`, `disable-model-invocation: true` and the verbatim contract; `test_codex_mirror.py` checks the generated copy, the quoted description, the `openai.yaml` policy and the `AGENTS.md` mention.

- [ ] **Step 7: Run the command the skill runs, on two throwaway files**

This checks the skill's claims about the script: the header text, the OFF/ON order, and that a missing file gives an error and no figures.

```bash
python - <<'PY'
import json
import pathlib
import subprocess
import sys
import tempfile

row = {"wins": 6, "n_eval": 10, "closed": 12, "expectancy_r": 0.1, "win_rate": 60.0}
with tempfile.TemporaryDirectory() as tmp:
    a = pathlib.Path(tmp) / "a.json"
    b = pathlib.Path(tmp) / "b.json"
    a.write_text(json.dumps({"RSI": row}), encoding="utf-8")
    b.write_text(json.dumps({"RSI": dict(row, wins=7)}), encoding="utf-8")
    script = "scripts/backtest/compare_backtest_json.py"
    ok = subprocess.run([sys.executable, script, str(a), str(b)],
                        capture_output=True, text=True)
    bad = subprocess.run([sys.executable, script, str(a), str(pathlib.Path(tmp) / "missing.json")],
                         capture_output=True, text=True)
print("ok exit", ok.returncode, "| first line:", ok.stdout.splitlines()[0])
print("ok has OFF then ON rows:", ok.stdout.index("OFF") < ok.stdout.index("ON "))
print("bad exit", bad.returncode, "| stdout empty:", bad.stdout == "",
      "| last stderr line:", bad.stderr.strip().splitlines()[-1][:40])
PY
```

Expected:

```
ok exit 0 | first line: === v35 AVWAP comparison  ===
ok has OFF then ON rows: True
bad exit 1 | stdout empty: True | last stderr line: FileNotFoundError: [Errno 2] No such fil
```

If the first line differs, the script's header has changed since this part was written: stop and report it, because the skill's `Header:` line quotes it.

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/result-digest/SKILL.md .agents/skills/result-digest/SKILL.md .agents/skills/result-digest/agents/openai.yaml tests/hooks/test_skill_shape.py AGENTS.md
git status --short
git commit -m "feat(skills): /result-digest returns compare_backtest_json.py output verbatim (V154-10)"
```

`git status --short` must show those five paths staged (`A` for the three new files, `M` for the other two) and nothing else staged. The skill, its Codex copy and its `AGENTS.md` mention travel in one commit.

---

### Task V154-11: `/handoff` slash-only skill

**Model:** sonnet — a new skill file, one set edit and one pinning test, all given verbatim; the care is in the skill telling apart a decision already taken from a question still open.

**Files:**
- Create: `.claude/skills/handoff/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (`TIER_2`, one new test at the end)
- Modify: `AGENTS.md` (the ritual sentence V154-10 wrote in `## Skills: the same ones Claude uses`)
- Regenerated by `python scripts/dev/sync_codex.py`: `.agents/skills/handoff/SKILL.md`, `.agents/skills/handoff/agents/openai.yaml`

**Interfaces:**
- Consumes:
  - `_read_skill(name) -> (dict[str, str], str)` in `tests/hooks/test_skill_shape.py`, reading through `parse_frontmatter` since V154-3.
  - `TIER_2` as V154-10 left it (it ends `"result-digest"}`) and the `AGENTS.md` ritual sentence V154-10 wrote (`... backup pull) and `result-digest` (two backtest `--json` files through ...`). V154-10 must be committed before this task starts.
  - The `## Handoff` convention in `docs/claude/skills-tools.md` § Plan writing, the paragraph that starts `**Handing a plan to another session or account.**`.
- Produces: `"handoff"` in `TIER_2`; the test `test_handoff_writes_the_plan_handoff_block_in_the_main_context`.

**What the skill is (spec § 5).** `/handoff` runs in the main context, because the decisions it records live in the conversation and a forked context cannot see them. It writes the plan's `## Handoff` block as `skills-tools.md` § Plan writing defines it: partner answers, `BLOCKED:` resolutions and deviations from the spec go into a `## Handoff` section of the index (single file: of the plan), and the session commits what is on disk. It is slash-only (`disable-model-invocation: true`), joins `TIER_2`, and has no `context` or `model` key. The shape of the block follows the one real example, the v146 index's `## Handoff` (a one-line lead, then numbered items with a bold lead clause each, placed directly above `## Parallelisation`).

- [ ] **Step 1: Write the failing tests in `tests/hooks/test_skill_shape.py`**

Two edits; find each anchor with `grep -n` first.

Edit 1, the Tier 2 set (`grep -n '"result-digest"}' tests/hooks/test_skill_shape.py`, one hit). Replace

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest"}        # each ritual task appends its own name
```

with

```python
TIER_2 = {"close-out", "new-doc", "deploy", "stable-snapshot", "backup-pull", "panel",
          "result-digest", "handoff"}        # each ritual task appends its own name
```

Edit 2, append at the very end of the file (after `test_result_digest_returns_the_script_output_verbatim`, with two blank lines before the new code):

```python
def test_handoff_writes_the_plan_handoff_block_in_the_main_context():
    """v154: /handoff records decisions taken in the conversation, so it
    never forks, and it writes the block skills-tools.md § Plan writing
    defines -- appending to it, never rewriting what is already there."""
    meta, body = _read_skill("handoff")
    assert "context" not in meta and "model" not in meta
    assert "`## Handoff`" in body
    assert "docs/claude/skills-tools.md" in body
    assert "Handing a plan to another session or account" in body
    assert "AskUserQuestion" in body
    assert "never rewrite, renumber or delete" in body
    assert "write nothing" in body
```

- [ ] **Step 2: Run the shape tests and watch them fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`

Expected: `VERDICT: FAIL` with `3 failed`: `test_ritual_skills_are_slash_only` and `test_handoff_writes_the_plan_handoff_block_in_the_main_context` (each a `FileNotFoundError` on `.claude/skills/handoff/SKILL.md`), and `test_every_skill_is_registered_in_exactly_one_tier` (the tiers name a skill that is not on disk). Any other failure is a mistake in Step 1.

- [ ] **Step 3: Create `.claude/skills/handoff/SKILL.md`**

Write this file exactly (Write tool; the file starts at `---`):

````markdown
---
name: handoff
description: "Write the in-progress plan's ## Handoff block -- every partner answer, BLOCKED resolution and spec deviation taken in this conversation, plus where to resume -- so another session or account carries on. Invoked explicitly as /handoff, never model-triggered."
disable-model-invocation: true
---

# Handoff

This runs in the main context on purpose: the decisions it records live in
this conversation, which a forked context cannot see. The convention is
`docs/claude/skills-tools.md` § Plan writing, the paragraph "Handing a plan
to another session or account"; read that paragraph first
(`grep -n "Handing a plan to another session" -A 16 docs/claude/skills-tools.md`),
never the whole file.

## Step 1 — Find the plan

The plan comes from the argument (`/handoff v154`, or a path). With no
argument, it is the plan this conversation has been writing or implementing.
If that is not exactly one plan, ask with `AskUserQuestion`, recommended
option first; never guess. A split plan takes the block in its `_0-index.md`,
a single-file plan in the plan itself. Never read a plan whole:
`grep -n "^## \|^### Task" <file>` gives you its sections and tasks.

## Step 2 — Collect what the next session needs

From this conversation only:

- every partner answer that settled something, with its date and the
  question it settled;
- every `BLOCKED:` resolution;
- every deviation from the spec, and why;
- where to resume: the first ledger id with no `### Task` on disk (plan
  writing), or the first task with no commit in the plan's worktree (plan
  implementing, from `git log --oneline`), with the worktree path if any.

Something not yet decided is not a handoff item. It is a question for the
partner now, through `AskUserQuestion`. If there is nothing to record, say so
and write nothing.

## Step 3 — Write the block

- If the file already has a `## Handoff` section, append numbered items after
  its last item. Never rewrite, renumber or delete an existing item: a later
  decision that changes an earlier one says which item it supersedes.
- If it has none, create `## Handoff` directly above `## Parallelisation`
  (directly above `## Task ledger` when there is no such section), opening
  with the line "Deviations from the spec and decisions taken while writing
  this plan. Each is final for every part."
- One item per decision: a bold lead clause stating it, then the reason and,
  for a partner answer, "*Partner confirmed <date>: ...*".
- The last item you add is the resume pointer: "**Resume at <id>.**" and the
  command that does it.

## Step 4 — Show it and commit it

Show the partner `git diff -- <file>`. Then, per the convention's "Commit as
you go", commit that file alone in the checkout it lives in: run
`git status --short` first (another session may share the tree), stage the
one path, and commit as `docs(vN): handoff -- <one clause>`.

## The gate

The block holds only decisions already taken in this conversation, each final
as written. Writing an item down never makes a new decision; an open question
goes to the partner, not into the plan.
````

Constraints the file must keep (the shape tests check them): at most 80 lines (it is 66); no comparison operator followed by a number and no number followed by `pp` or `R` anywhere in the body (`_THRESHOLD_RE`); the `description:` value stays inside double quotes with no inner `"` (the `#` and the `--` inside the quotes are fine: only an unquoted value may not contain ` #`).

- [ ] **Step 4: Name the skill in `AGENTS.md`**

Find the anchor with `grep -n "backup pull) and \`result-digest\` (two backtest" AGENTS.md`; expected one hit, the line V154-10 wrote in the paragraph that starts `Explicit-only rituals, never implicitly triggered`. Replace these two lines

```markdown
backup pull) and `result-digest` (two backtest `--json` files through
`compare_backtest_json.py`, output returned verbatim, never judged). `new-doc`
```

with these three

```markdown
backup pull), `result-digest` (two backtest `--json` files through
`compare_backtest_json.py`, output returned verbatim, never judged) and
`handoff` (write the plan's `## Handoff` block before a session stops). `new-doc`
```

The line after (`(new spec or plan) and \`close-out\` (plan close-out) may`) and everything else in `AGENTS.md` are unchanged.

- [ ] **Step 5: Regenerate the Codex mirror**

Run: `python scripts/dev/sync_codex.py`

Expected last line: `Codex mirror is current.` Then:

```bash
git status --short
head -3 .agents/skills/handoff/SKILL.md
```

`git status --short` shows `tests/hooks/test_skill_shape.py` and `AGENTS.md` modified, and `.claude/skills/handoff/` and `.agents/skills/handoff/` untracked, and nothing else this task did. The `head` prints `---`, `name: handoff` and the `description:` line with the value in double quotes. `.agents/skills/handoff/agents/openai.yaml` exists. If `sync_codex.py` rewrites any other skill, another skill commit is in flight: stop and let it land first. A line `AGENTS.md never mentions \`handoff\`` means Step 4's backticks are wrong.

- [ ] **Step 6: Run the narrow tests**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py tests/hooks/test_codex_mirror.py`

Expected: `VERDICT: PASS`, nothing failed.

- [ ] **Step 7: Check the block shape against the one real example**

The skill's Step 3 copies the v146 index's lead line. Confirm it is still there, word for word:

```bash
git grep -n "^Deviations from the spec and decisions taken while writing this plan. Each is final for every part.$" -- 'docs/superpowers/plans/*v146*'
```

Expected: one hit in the v146 `_0-index.md`, on the line after its `## Handoff` heading. No hit means that file moved or changed (for example to `implemented/`: the pathspec still matches it there); if the line itself was reworded, stop and report it rather than editing the skill to a guess.

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/handoff/SKILL.md .agents/skills/handoff/SKILL.md .agents/skills/handoff/agents/openai.yaml tests/hooks/test_skill_shape.py AGENTS.md
git status --short
git commit -m "feat(skills): /handoff writes the plan's ## Handoff block (V154-11)"
```

`git status --short` must show those five paths staged (`A` for the three new files, `M` for the other two) and nothing else staged.

---

### Task V154-12: Manual eval re-run of thirteen skill suites and the fresh-session listing check

**Model:** opus — reading eval verdicts and, if a fire case is missed, rewording a role's trigger text within a hard cap without losing its seat or its hand-offs is judgement.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md` (three rows of `## Results`)
- Modify only if a role fire case is missed: that role's `.claude/skills/<role>/SKILL.md` (`description:` line only), regenerated `.agents/skills/<role>/SKILL.md`

**Interfaces:**
- Consumes:
  - The nine role descriptions as V154-4 left them, pinned at `MAX_ROLE_DESCRIPTION = 260` by `tests/hooks/test_role_skills.py` (V154-4).
  - The four Step 1 blocks of `backtest-gate`, `pooled-numbers`, `alert-surface` and `no-lookahead` as V154-8 wrote them.
  - The disabled plugins from V154-9 and the two slash-only skills from V154-10 and V154-11.
  - `parse_frontmatter` from `scripts/dev/skill_frontmatter.py` (V154-1), imported with the `sys.path` pattern of contract C2.
- Produces: the recorded verdicts in the index's `## Results` rows `Fresh session lists all nine role descriptions`, `Nine role eval suites` and `Four edited Tier 1/3 eval suites (...)`.

**Why this task is manual.** The eval suites are real child `claude` runs on the partner's credential (`docs/claude/skills-tools.md` § Proving a skill fires: the eval suites; the 52-case sweep there cost about $3.50 and 8 minutes). This run is about 80 cases across thirteen suites, so expect roughly $5 and 15 minutes. It runs once, after every skill edit of this plan has landed, so it judges the skills as finally written. CI never runs it.

**Where it runs.** A worktree-isolated session's Bash tool refuses any command containing the word `eval` (repo memory, worktree eval command block), so Step 4 runs from a session that is not worktree-isolated (the main-tree session after `ExitWorktree` with action `keep`). The child runs still need the worktree's `.claude/` (the old role descriptions are what the main tree carries), so every eval command sets the child's working directory to the worktree with `env --chdir`, never with `cd` (a persistent `cd` breaks the guardrail hooks). Steps 1 to 3 run inside the worktree session as usual: their commands contain no `eval`.

- [ ] **Step 1: Confirm every skill edit has landed**

```bash
git log --oneline -12
python scripts/dev/sync_codex.py --check
python scripts/dev/testrun.py file tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py tests/hooks/test_codex_mirror.py
```

Expected: the log shows the commits of V154-4, V154-8, V154-10 and V154-11 (their messages end `(V154-4)`, `(V154-8)`, `(V154-10)`, `(V154-11)`); `Codex mirror is current.`; `VERDICT: PASS`. `git status --short` shows nothing staged and no change under `.claude/`. Any gap: stop, that task comes first.

- [ ] **Step 2: Note the worktree's absolute path**

```bash
git rev-parse --show-toplevel
```

Write the printed path down: Step 4 needs it as `WT`. It is under `.claude/worktrees/` of the main tree.

- [ ] **Step 3: Fresh-session listing check (inside the worktree)**

A child session started in the worktree prints the descriptions it was given. Run (one command; the prompt is one string):

```bash
claude -p --model sonnet "Do not use any tool. Print exactly eleven lines and nothing else. Lines 1 to 9: for each of these skill names, in this order, print the name, one tab character, then the description shown for that skill in your list of available skills, copied exactly; print MISSING in place of the description if the name is not in the list. Names: financial-advisor, fundamental-analyst, quant-engineer, quant-researcher, risk-manager, senior-engineer, staff-engineer, technical-analyst, veteran-trader. Line 10: PLUGINS: then the names of every listed skill or agent whose name starts with feature-dev:, code-simplifier:, claude-code-setup:, claude-md-management: or skill-creator:, comma-separated, or NONE. Line 11: SLASH: then whichever of result-digest and handoff appear in your list of available skills, or NONE." > "${TMPDIR:-/tmp}/v154-listing.txt"
cat "${TMPDIR:-/tmp}/v154-listing.txt"
```

Then compare each printed description with the value the source file parses to:

```bash
python - "${TMPDIR:-/tmp}/v154-listing.txt" <<'PYEOF'
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("scripts/dev").resolve()))
from skill_frontmatter import parse_frontmatter

ROLES = ["financial-advisor", "fundamental-analyst", "quant-engineer",
         "quant-researcher", "risk-manager", "senior-engineer",
         "staff-engineer", "technical-analyst", "veteran-trader"]
listed, tails = {}, {}
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    name, sep, desc = line.partition("\t")
    if sep and name.strip() in ROLES:
        listed[name.strip()] = desc.strip()
    for tag in ("PLUGINS:", "SLASH:"):
        if line.startswith(tag):
            tails[tag] = line[len(tag):].strip()
problems = []
for role in ROLES:
    text = pathlib.Path(f".claude/skills/{role}/SKILL.md").read_text(encoding="utf-8")
    want = parse_frontmatter(text)[0]["description"]
    got = listed.get(role, "MISSING")
    title = role.replace("-", " ").capitalize()
    ok = got not in ("MISSING", title) and got[:60] == want[:60]
    print(f"{'ok ' if ok else 'BAD'} {role:20s} {len(want):3d}  {got[:70]}")
    if not ok:
        problems.append(role)
print("PLUGINS:", tails.get("PLUGINS:"), "| SLASH:", tails.get("SLASH:"))
if tails.get("PLUGINS:") != "NONE":
    problems.append("disabled plugins still listed")
if tails.get("SLASH:") != "NONE":
    problems.append("a slash-only skill is in the model's listing")
print("LISTING PASS" if not problems else f"LISTING FAIL {problems}")
PYEOF
```

Expected: nine `ok` rows, none showing the title-cased name (`Financial advisor`, `Quant engineer`, ... was the v145 failure), every length at most 260, `PLUGINS: NONE | SLASH: NONE`, and `LISTING PASS`.

A `BAD` row whose printed text is a faithful but reflowed copy (the child re-typed it with a changed first word, for example) is a child-model copy error, not a loader failure: re-run this step once. A `BAD` row showing the title-cased name or `MISSING` twice running is a real failure: the description does not load. Stop and report it with the file's `description:` line; do not go on to Step 4. A non-`NONE` `PLUGINS:` means V154-9's keys did not take: report it. A non-`NONE` `SLASH:` is recorded and reported, not fixed here (the spec's claim that slash-only skills add nothing to the listing is what it tests).

- [ ] **Step 4: Run the thirteen eval suites (from a session that is not worktree-isolated)**

Leave the worktree session with `ExitWorktree`, action `keep` (never `remove`). In the main-tree session, run this with the Bash tool's `run_in_background: true` (it outlasts the foreground timeout), putting the Step 2 path in `WT`:

```bash
WT="<absolute worktree path from Step 2>"
for s in quant-researcher risk-manager financial-advisor veteran-trader technical-analyst fundamental-analyst staff-engineer quant-engineer senior-engineer backtest-gate pooled-numbers alert-surface no-lookahead; do
  env --chdir="$WT" claude plugin eval ".claude/skills/$s" --runs 1 --no-publish --trust-plugin --ablation none > "${TMPDIR:-/tmp}/v154-suite-$s.txt" 2>&1
  echo "$s exit $?"
done
```

It prints one `<suite> exit <code>` line as each suite finishes, which is the progress signal. When it is done, read each suite's result: the summary at the end of `${TMPDIR:-/tmp}/v154-suite-<suite>.txt` (`tail -25` it, never `cat` the whole file) lists every case with its grader verdict; the full results also land in `$WT/.claude/skills/<suite>/evals/results/` (gitignored).

Expected: all thirteen `exit 0`, and every case passing: a `fire-*` case shows the skill used (grader `min: 1`), a `no-fire-*` case shows it unused (`min: 0`, `max: 0`). The v145 baseline for the nine role suites was 54 of 54 cases.

- [ ] **Step 5: If a case fails, fix it within the rules, then re-run only that suite**

Return to the worktree session first (`EnterWorktree` on the existing worktree path; never `isolation: "worktree"`, which would create a new one).

- **A role `fire-*` case missed, or a role `no-fire-*` case fired:** reword that role's `description:` value only. Keep the seat, its three to five checks and its two "Not for ... (other-role)" hand-offs; name the missed question in the checks (the v145 fix for `quant-engineer` and `senior-engineer` was exactly that), or sharpen a "Not for" clause for a false fire. The value stays at most 260 characters: **never raise `MAX_ROLE_DESCRIPTION`** (Global Constraints). Keep it a double-quoted scalar with no inner `"` and no backslash. Then:

  ```bash
  python scripts/dev/testrun.py file tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py
  python scripts/dev/sync_codex.py
  python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
  git add .claude/skills/<role>/SKILL.md .agents/skills/<role>/SKILL.md
  git status --short
  git commit -m "fix(skills): <role> description names <the missed question> so its eval fires (V154-12)"
  ```

  Expected: `VERDICT: PASS` both times and `Codex mirror is current.`; only the two paths staged. Then leave the worktree again and re-run Step 4's loop with only that suite in the list. Two rewordings of the same role that still miss: stop and ask the partner (`AskUserQuestion`), recommended option first, with the case prompt and both descriptions.
- **A case in `backtest-gate`, `pooled-numbers`, `alert-surface` or `no-lookahead` fails:** this plan changed only their Step 1 and the quoting of their description, and rewording their descriptions is out of scope. Do not edit them. Stop and report the case, its prompt and the result summary to the partner.
- **A suite errors before running any case** (an `exit` other than 0 with no case lines in its file): read the tail of its output file. A credential or network error is re-run as is; anything else is reported, not worked around.

Re-run Step 3 after any rewording: the listing must still pass.

- [ ] **Step 6: Record the verdicts in `## Results`**

In `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md`, under `## Results`, replace `_not yet run_` in these three rows, with today's date and the counts read from the outputs (never from memory or this plan):

- `Fresh session lists all nine role descriptions`: `<YYYY-MM-DD>: LISTING PASS, nine of nine descriptions listed; PLUGINS: NONE; SLASH: <what it printed>` (plus `after <n> re-run(s)` if Step 3 was repeated).
- `Nine role eval suites`: `<YYYY-MM-DD>: <passed>/<total> cases, all nine suites exit 0` and, for each rewording, `<role> reworded once (<case id>)`.
- `Four edited Tier 1/3 eval suites (...)`: `<YYYY-MM-DD>: <passed>/<total> cases, all four suites exit 0`.

A row whose check did not pass records what it showed and `reported to partner <date>`, never a pass.

- [ ] **Step 7: Commit the results (inside the worktree)**

```bash
git add docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md
git status --short
git commit -m "docs(v154): record eval re-run and fresh-session listing (V154-12)"
```

`git status --short` must show only the index staged.

---

### Task V154-13: Full-suite verification

**Model:** haiku — fixed commands with a literal green rule; a red result is handed to `superpowers:systematic-debugging` at the owning task's tier, not fixed here.

**Files:**
- Modify: `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md` (the `Full suite` row of `## Results`)

**Interfaces:**
- Consumes: every commit of V154-1 to V154-12. The Python files this plan wrote or changed: `scripts/dev/skill_frontmatter.py` (V154-1), `scripts/dev/sync_codex.py` (V154-2), `scripts/dev/doc_section.py` (V154-6), `scripts/dev/select_tests.py` (V154-7), and the test modules `tests/dev/test_skill_frontmatter.py`, `tests/dev/test_doc_section.py`, `tests/dev/test_select_tests.py`, `tests/hooks/test_codex_mirror.py`, `tests/hooks/test_skill_shape.py`, `tests/hooks/test_agent_shape.py`, `tests/hooks/test_role_skills.py`, `tests/hooks/test_doc_sections.py`.
- Produces: the plan's green verdict in `## Results`, which `/close-out` reads.

This is the plan's one full-suite run (Global Constraints). Green means `0 failed` **and** `0 xfailed`; a changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 1: Confirm the tree is complete and clean**

```bash
git status --short
git log --oneline -20
python scripts/dev/sync_codex.py --check
```

Expected: `git status --short` prints nothing; the log shows a commit for every task V154-1 to V154-12 (V154-7 has two); `Codex mirror is current.`. Anything uncommitted or missing: stop, the owning task is not done.

- [ ] **Step 2: Syntax and complexity of the Python this plan touched**

```bash
python -m py_compile scripts/dev/skill_frontmatter.py scripts/dev/sync_codex.py scripts/dev/doc_section.py scripts/dev/select_tests.py
python -m radon cc -s -n C scripts/dev/skill_frontmatter.py scripts/dev/sync_codex.py scripts/dev/doc_section.py scripts/dev/select_tests.py tests/dev/test_skill_frontmatter.py tests/dev/test_doc_section.py tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py tests/hooks/test_role_skills.py tests/hooks/test_doc_sections.py tests/hooks/test_codex_mirror.py
```

Expected: `py_compile` prints nothing. `radon` prints a line only for a function scored C or worse, with its score in parentheses; every printed score must be below 15. The brief measured the highest pre-existing scores in these files at `_missing_mentions` B (9) and `test_backup_skills_match_the_v120_final_fixes` C (12); neither may have grown. A score of 15 or more: stop and hand the function back to its owning task for a split into named helpers (`docs/claude/code-complexity.md`), behaviour unchanged.

- [ ] **Step 3: Lint the plan files**

```bash
python scripts/dev/plan_lint.py docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md
```

Expected: `PLAN LINT: PASS  4 file(s), 0 problem(s)` (the linter checks the index and its three parts). A problem here is a plan-document defect: report it, do not edit task text.

- [ ] **Step 4: Run the full suite through the `test-runner` subagent**

Dispatch the `test-runner` agent (so none of the progress output reaches this context) with this instruction:

```
Run `python scripts/dev/testrun.py full` from <absolute worktree path, from `git rev-parse --show-toplevel`>. Report the one-line verdict exactly as printed (passed, failed, xfailed, skipped counts and wall time), and for any failure or xfail, the test node id and the last 15 lines of its traceback. Do not fix anything.
```

Expected: `VERDICT: PASS` with `0 failed` and `0 xfailed`.

- [ ] **Step 5: If it is red, debug before touching anything**

Use `superpowers:systematic-debugging`. Find the owning task from the failing test's path (the ledger's files column), fix it in that task's files at that task's `Model:` tier, re-run the narrow test (`python scripts/dev/testrun.py file <test>`) until it passes, commit the fix as `fix(v154): <what> (V154-<owning id>)` with the paths staged by name, then repeat Step 4. Never mark a test xfail or skip, and never edit an assertion to match new output unless the owning task's text says that output is the intended one. Two full runs that are red on the same test after a fix: stop and report to the partner.

- [ ] **Step 6: Record the verdict in `## Results`**

In `docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md`, under `## Results`, replace `_not yet run_` in the `Full suite` row with the verdict line as the subagent reported it:

```markdown
<YYYY-MM-DD>: `VERDICT: PASS` -- <passed> passed, 0 failed, 0 xfailed, <skipped> skipped, <wall time> (`testrun.py full`, worktree HEAD `<short sha>`)
```

Fill the counts from the report, never from an earlier run. Take the short sha from `git rev-parse --short HEAD` before this commit.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/plans/2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md
git status --short
git commit -m "docs(v154): record full-suite verdict (V154-13)"
```

`git status --short` must show only the index staged. The plan is then ready for `/close-out` (merge, `Bump: none`, move to `implemented/`, remove the worktree), which is the controller's step, not this task's.

