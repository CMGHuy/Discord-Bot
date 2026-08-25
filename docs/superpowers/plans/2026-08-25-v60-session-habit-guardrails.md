# v60 — Session-habit guardrails: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `PreToolUse` hook that denies the token-wasting patterns
`CLAUDE.md` already forbids in prose, and warns on the judgement calls.

**Spec:** `docs/superpowers/specs/2026-08-25-v60-session-habit-guardrails-design.md`

**Architecture:** One Python entry point, `.claude/hooks/guardrails.py`, whose
rule logic is a **pure function** — `evaluate(payload: dict) -> dict | None` —
so the whole rule set is unit-testable under pytest without a live session.
The script does nothing but read stdin, call `evaluate`, print JSON, exit 0.

**Tech Stack:** Python 3.11+ stdlib only (`json`, `sys`, `re`, `os`, `pathlib`).
No new dependency. pytest for the rule tests.

**Worktree:** not required — this is small, additive, and touches no runtime
code. Work on a topic branch off `main`.

---

## Two deliberate deviations from the spec

**1. Python, not PowerShell.** The spec said PowerShell, to match the three
existing hooks in `.claude/hooks/`. That reasoning is overridden by a stronger
one: these rules are logic that must be *correct*, pytest covers Python and
not PowerShell, and this is already a Python repo. Python also starts faster
than `pwsh -NoProfile` (~100 ms vs ~400 ms), which matters for something on the
critical path of every tool call. The existing hooks stay PowerShell; they do
Windows-shaped work, this does not.

**2. The contract is verified empirically before any rule is written.**
Task 1 exists because two sources disagree about the payload:

| Field | Official docs (fetched 2026-08-25) | This session's own Glob tool schema |
|---|---|---|
| Glob's pattern argument | `tool_input.glob` | `pattern` |

The docs also give `permissionDecision` values inconsistently between pages
(`"allow" / "deny" / "ask"` vs `"allow" / "deny" / "escalate"`), and note the
set is version-dependent. **Do not write a rule against a guessed field name.**
Task 1 captures real payloads from the installed build and every later task
uses what it recorded.

**Resolved (2026-08-25, ruling recorded in this plan's SDD ledger):** live
capture was attempted and is environmentally blocked — `.claude/settings.json`
hooks are read at CLI session startup, not hot-reloaded, so no PreToolUse hook
added mid-session can fire for that same session's own tool calls (confirmed
in both the controller's top-level session and a dispatched subagent). Rather
than block the plan on a fresh CLI restart, the resolved field names in
`tests/hooks/fixtures/payloads.json` come from this session's own live tool
JSON schemas — the exact arguments a PreToolUse hook's `tool_input` mirrors —
which is stronger evidence than the two disagreeing doc pages this task was
built to arbitrate between. **Glob's pattern argument is `pattern`.** Tasks
2-5 proceed on this. Task 5's "live verification" step still requires an
actual fresh session (this plan's execution cannot self-verify it) and is
flagged there.

Known-good from the docs regardless of version, and safe to rely on:

- Deny: exit 0 with `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`. The reason reaches the model.
- Warn: same shape with `"permissionDecision": "allow"` plus a top-level `"additionalContext": "..."`, which the model sees. The call proceeds.
- Silent allow: exit 0, no output.
- **Fail-open is the harness default** — a timeout, a crash, a non-zero exit or malformed JSON all let the call proceed. We still catch exceptions, but we are not the last line of defence.
- `timeout` in settings.json is **seconds** (default 600).
- `matcher` accepts regex, so `"Edit|Write"` is one block.

---

## Global Constraints

- **Never block on uncertainty.** Any unrecognised payload shape, missing field, or internal exception ⇒ return `None` ⇒ silent allow. A guardrail that blocks legitimate work costs more than the habit it prevents.
- **Every deny message names the alternative.** A refusal that only refuses trains nothing and burns a turn.
- **No rule may read a file or run a subprocess.** `evaluate` is pure and works off the payload plus `os.path.getsize` for the size rules. Anything heavier belongs nowhere near the critical path of every tool call.
- Rules encode what `CLAUDE.md` already says. If a rule and `CLAUDE.md` ever disagree, `CLAUDE.md` wins and the rule is what gets fixed.

---

### Task 1: Capture the real payloads

Nothing is written against a guessed contract. This task produces a recorded
fixture set that Tasks 2–4 assert against.

**Files:**
- Create: `.claude/hooks/_capture.py` (temporary; deleted in Task 5)
- Create: `tests/hooks/fixtures/payloads.json`

- [ ] **Step 1: Write the capture script**

```python
# .claude/hooks/_capture.py
"""TEMPORARY -- records real PreToolUse payloads so the guardrail rules are
written against the installed build's actual field names, not the docs'.
Deleted in Task 5 of the v60 plan."""
import json
import pathlib
import sys

OUT = pathlib.Path(__file__).parent.parent.parent / "tests" / "hooks" / "fixtures" / "captured.jsonl"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Wire it temporarily**

Add to `.claude/settings.json` under `hooks`:

```json
"PreToolUse": [
  {
    "matcher": "Glob|Read|Edit|Write|Bash",
    "hooks": [
      { "type": "command", "command": "python .claude/hooks/_capture.py", "timeout": 5 }
    ]
  }
]
```

- [ ] **Step 3: Generate one payload per guarded tool**

In a session with the hook live, make exactly these calls:

```
Glob("swingbot/**/*.py")
Read on any small file
Bash: echo hi
Edit on a scratch file
```

- [ ] **Step 4: Record the field names**

```bash
python -c "import json;[print(d['tool_name'], sorted(d['tool_input'])) for d in map(json.loads, open('tests/hooks/fixtures/captured.jsonl'))]"
```

Write the observed key for Glob's pattern argument into this plan's header
table, replacing the two-source disagreement with the fact. Then curate
`captured.jsonl` into a clean `payloads.json` keyed by tool name — one
representative payload each, secrets and absolute paths scrubbed.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/fixtures/payloads.json .claude/hooks/_capture.py
git commit -m "test(v60): capture real PreToolUse payloads for the guardrail rules"
```

---

### Task 2: The rule engine core

Pure logic, no I/O, no rules yet — the dispatcher plus the two output shapes.

**Files:**
- Create: `.claude/hooks/guardrails.py`
- Create: `tests/hooks/test_guardrails.py`
- Create: `tests/hooks/__init__.py` (empty)

**Interfaces:**
- Produces: `evaluate(payload: dict) -> dict | None` — `None` means silent allow; a dict is the exact JSON to print. Helpers `_deny(reason: str) -> dict` and `_warn(message: str) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/hooks/test_guardrails.py
import importlib.util
import json
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "guardrails",
    pathlib.Path(__file__).parent.parent.parent / ".claude" / "hooks" / "guardrails.py",
)
guardrails = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guardrails)

evaluate, _deny, _warn = guardrails.evaluate, guardrails._deny, guardrails._warn


def test_unknown_tool_is_silently_allowed():
    assert evaluate({"tool_name": "WebFetch", "tool_input": {"url": "x"}}) is None


def test_missing_tool_input_is_silently_allowed():
    assert evaluate({"tool_name": "Glob"}) is None


def test_empty_payload_is_silently_allowed():
    assert evaluate({}) is None


def test_deny_shape_matches_the_contract():
    out = _deny("because")
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"] == "because"


def test_warn_allows_and_carries_context():
    out = _warn("heads up")
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert out["additionalContext"] == "heads up"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: FAIL — file `.claude/hooks/guardrails.py` does not exist

- [ ] **Step 3: Implement the core**

```python
# .claude/hooks/guardrails.py
"""PreToolUse guardrails -- enforce this repo's token rules at the moment of
the mistake rather than relying on CLAUDE.md having been recalled.

Rules encode what CLAUDE.md and .ignore already state. If a rule and
CLAUDE.md ever disagree, CLAUDE.md wins and the rule is what gets fixed.

Design: evaluate() is pure and does no I/O beyond os.path.getsize, so the
whole rule set is unit-tested in tests/hooks/test_guardrails.py without a
live session. Anything unrecognised returns None -- silent allow. A
guardrail that blocks legitimate work costs more than the habit it prevents.
"""
import json
import sys


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}


def _warn(message: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
    }, "additionalContext": message}


# Populated by Tasks 3 and 4: tool name -> list of rule callables.
# Each rule takes tool_input (dict) and returns a decision dict or None.
_RULES: dict = {}


def evaluate(payload: dict):
    """Return the JSON to emit, or None for a silent allow."""
    try:
        tool = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        if not tool or not isinstance(tool_input, dict):
            return None
        for rule in _RULES.get(tool, ()):
            decision = rule(tool_input)
            if decision is not None:
                return decision
        return None
    except Exception:
        return None      # fail open, always


def main() -> int:
    try:
        decision = evaluate(json.load(sys.stdin))
        if decision is not None:
            print(json.dumps(decision))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/
git commit -m "feat(v60): guardrail rule engine core, fail-open by construction"
```

---

### Task 3: The deny rules

**Files:**
- Modify: `.claude/hooks/guardrails.py`
- Modify: `tests/hooks/test_guardrails.py`

**Interfaces:**
- Consumes: `_deny` and `_RULES` from Task 2; the real field names recorded in Task 1.
- Produces: four rules registered under `Glob`, `Bash`, `Read`, `Edit`/`Write`.

- [ ] **Step 1: Write the failing tests**

Replace `GLOB_PATTERN_KEY` with the key Task 1 actually observed.

```python
GLOB_PATTERN_KEY = "pattern"   # <- set from Task 1's capture, do not guess


def test_unscoped_glob_is_denied():
    out = evaluate({"tool_name": "Glob", "tool_input": {GLOB_PATTERN_KEY: "**/*.py"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "swingbot/**/*.py" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_scoped_glob_is_allowed():
    assert evaluate({"tool_name": "Glob", "tool_input": {GLOB_PATTERN_KEY: "swingbot/**/*.py"}}) is None


def test_glob_with_explicit_path_is_allowed():
    assert evaluate({"tool_name": "Glob",
                     "tool_input": {GLOB_PATTERN_KEY: "**/*.py", "path": "swingbot"}}) is None


def test_recursive_grep_from_root_is_denied():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "grep -r 'def foo' ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git grep" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_scoped_grep_is_allowed():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "grep -r 'def foo' swingbot/core"}}) is None


def test_grep_without_r_is_allowed():
    assert evaluate({"tool_name": "Bash", "tool_input": {"command": "grep foo file.txt"}}) is None


def test_edit_inside_a_worktree_is_denied():
    out = evaluate({"tool_name": "Edit",
                    "tool_input": {"file_path": "/repo/.claude/worktrees/x/swingbot/config.py"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_edit_in_the_main_tree_is_allowed():
    assert evaluate({"tool_name": "Edit",
                     "tool_input": {"file_path": "/repo/swingbot/config.py"}}) is None


def test_reading_a_huge_implemented_plan_is_denied(tmp_path):
    big = tmp_path / "implemented" / "2026-07-11-v3-cockpit.md"
    big.parent.mkdir(parents=True)
    big.write_text("x" * 200_000)
    out = evaluate({"tool_name": "Read", "tool_input": {"file_path": str(big)}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "task-brief" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_reading_a_small_implemented_plan_is_allowed(tmp_path):
    small = tmp_path / "implemented" / "tiny.md"
    small.parent.mkdir(parents=True)
    small.write_text("hello")
    assert evaluate({"tool_name": "Read", "tool_input": {"file_path": str(small)}}) is None


def test_reading_a_live_plan_is_allowed(tmp_path):
    live = tmp_path / "plans" / "2026-08-25-v61-thing.md"
    live.parent.mkdir(parents=True)
    live.write_text("x" * 200_000)
    assert evaluate({"tool_name": "Read", "tool_input": {"file_path": str(live)}}) is None
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: the 11 new tests fail; Task 2's 5 still pass

- [ ] **Step 3: Implement**

The rule functions go where Task 2's `_RULES: dict = {}` placeholder sits, and
the `_RULES = {...}` literal below **replaces** that empty dict — it must
appear after the functions it references. `evaluate` resolves `_RULES` at call
time, so its position above them is fine.

`GLOB_PATTERN_KEYS` carries both candidate names so the rule is correct
whichever the build sends.

```python
import os
import re

GLOB_PATTERN_KEYS = ("pattern", "glob")
_IMPLEMENTED_PLAN_MAX_BYTES = 100_000
_GREP_ROOT_RE = re.compile(r"^\s*(grep|rg)\b(?=.*\s-\w*r)")


def _rule_unscoped_glob(ti: dict):
    if ti.get("path"):
        return None
    for key in GLOB_PATTERN_KEYS:
        pattern = ti.get(key)
        if isinstance(pattern, str) and pattern.startswith("**/"):
            return _deny(
                "Glob does not honour .ignore, so an unscoped pattern returns the three "
                ".claude/worktrees/ copies of this repo -- ~500 matches for 232 real files, "
                "and it points you at the wrong branch. Scope it by hand, e.g. "
                'Glob("swingbot/**/*.py"), or pass path=.'
            )
    return None


def _rule_recursive_grep_from_root(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _GREP_ROOT_RE.match(cmd):
        return None
    # Scoped to a real subdirectory is fine; only bare '.' or no path is not.
    tail = cmd.split()
    targets = [a for a in tail[1:] if not a.startswith("-")]
    if len(targets) >= 2 and targets[-1] not in (".", "./"):
        return None
    return _deny(
        "Plain `grep -r` from the repo root does not respect .ignore -- it crawls "
        "~2,600 files / 160 MB including three worktree copies and times out at 20s "
        "returning nothing. Use the Grep tool (it honours .ignore) or `git grep -n` "
        "for tracked files only."
    )


def _rule_worktree_write(ti: dict):
    path = ti.get("file_path")
    if isinstance(path, str) and ".claude/worktrees/" in path.replace("\\", "/"):
        return _deny(
            "Never edit files under .claude/worktrees/ from a main-tree session -- "
            "that edits a different branch and the change is invisible here. Work in "
            "that worktree's own session instead."
        )
    return None


def _rule_huge_implemented_plan(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    if "implemented" not in path.replace("\\", "/"):
        return None
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= _IMPLEMENTED_PLAN_MAX_BYTES:
        return None
    return _deny(
        f"That file is {size // 1024} KB (~{size // 4 // 1000}K tokens) and reading it "
        "whole would consume a large share of this session. Pull the one task instead: "
        '/task-brief <id>, or grep -n "^### Task <id>" -A 120 <plan>. '
        'Use grep -c "^### Task" to orient first.'
    )


_RULES = {
    "Glob": [_rule_unscoped_glob],
    "Bash": [_rule_recursive_grep_from_root],
    "Read": [_rule_huge_implemented_plan],
    "Edit": [_rule_worktree_write],
    "Write": [_rule_worktree_write],
    "NotebookEdit": [_rule_worktree_write],
}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: 16 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(v60): deny rules -- unscoped Glob, grep -r from root, worktree writes, huge plans"
```

---

### Task 4: The warn rules

**Files:**
- Modify: `.claude/hooks/guardrails.py`
- Modify: `tests/hooks/test_guardrails.py`

**Interfaces:**
- Consumes: `_warn`, `_RULES` from Tasks 2–3.
- Produces: two additional rules appended to the `Bash` and `Read` lists.

- [ ] **Step 1: Write the failing tests**

```python
def test_bare_pytest_warns_but_allows():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "python -m pytest"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "testrun.py" in out["additionalContext"]


def test_pytest_with_a_file_is_silent():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "python -m pytest tests/test_edge_gates.py -v"}}) is None


def test_testrun_wrapper_is_silent():
    assert evaluate({"tool_name": "Bash",
                     "tool_input": {"command": "python scripts/dev/testrun.py fast"}}) is None


def test_cat_on_progress_md_warns():
    out = evaluate({"tool_name": "Bash",
                    "tool_input": {"command": "cat .superpowers/sdd/progress.md"}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "tail" in out["additionalContext"]


def test_cat_on_readme_warns():
    out = evaluate({"tool_name": "Bash", "tool_input": {"command": "cat README.md"}})
    assert "documentation index" in out["additionalContext"]


def test_deny_wins_over_warn_when_both_match():
    # grep -r from root inside a command that also mentions pytest
    out = evaluate({"tool_name": "Bash",
                    "tool_input": {"command": "grep -r pytest ."}})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
```

- [ ] **Step 2: Run to confirm they fail**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: the 6 new tests fail; the previous 16 pass

- [ ] **Step 3: Implement**

Rules run in list order and the first non-`None` wins, so appending the warn
rules **after** the deny rules gives deny precedence for free — which is what
`test_deny_wins_over_warn_when_both_match` pins.

```python
_BARE_PYTEST_RE = re.compile(r"python\s+-m\s+pytest\s*(-\w+\s*)*$")
_BIG_DOCS = {
    "README.md": "README.md is a short overview + documentation index. Read the "
                 "topic file it points at instead -- docs/strategy/strategy.md, "
                 "docs/setup.md, docs/commands.md, docs/features/features.md.",
    "progress.md": "progress.md is 173 KB. tail it, never cat it.",
}


def _rule_bare_pytest(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _BARE_PYTEST_RE.search(cmd.strip()):
        return None
    return _warn(
        "A bare `python -m pytest` puts ~1150 progress lines into context. "
        "`python scripts/dev/testrun.py fast` is ~27s and prints a one-line verdict; "
        "`... file tests/test_foo.py` is ~7s. For a full run, dispatch the test-runner "
        "subagent so none of the output reaches this context. Continuing anyway."
    )


def _rule_cat_big_doc(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd.strip().startswith("cat "):
        return None
    for name, advice in _BIG_DOCS.items():
        if name in cmd:
            return _warn(advice + " Continuing anyway.")
    return None


_RULES["Bash"].append(_rule_bare_pytest)
_RULES["Bash"].append(_rule_cat_big_doc)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/hooks/test_guardrails.py -v`
Expected: 22 passed

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(v60): warn rules -- bare pytest, cat on the big docs"
```

---

### Task 5: Wire it in and verify live

**Files:**
- Modify: `.claude/settings.json`
- Delete: `.claude/hooks/_capture.py`, `tests/hooks/fixtures/captured.jsonl`

- [ ] **Step 1: Replace the capture hook with the real one**

Swap the Task 1 temporary block for:

```json
"PreToolUse": [
  {
    "matcher": "Glob|Read|Edit|Write|NotebookEdit|Bash",
    "hooks": [
      {
        "type": "command",
        "command": "python .claude/hooks/guardrails.py",
        "timeout": 5
      }
    ]
  }
]
```

`timeout` is in **seconds**. Five is far above the expected cost and the
harness fails open on timeout regardless.

- [ ] **Step 2: Validate the JSON before restarting**

```bash
python -c "import json; json.load(open('.claude/settings.json')); print('settings.json OK')"
```
Expected: `settings.json OK`. A malformed settings file disables **all** hooks,
including the `SessionStart` cursor — verify before relying on it.

- [ ] **Step 3: Live verification, one call per rule**

In a fresh session, confirm each of these behaves as stated:

| Call | Expected |
|---|---|
| `Glob("**/*.py")` | denied, message names `Glob("swingbot/**/*.py")` |
| `Glob("swingbot/**/*.py")` | proceeds silently |
| `Bash: grep -r foo .` | denied, message names `git grep` |
| `Bash: python -m pytest` | proceeds, warning mentions `testrun.py` |
| `Read` a live plan in `plans/` | proceeds silently |
| `Read` an `implemented/` plan >100 KB | denied, message names `/task-brief` |

If a deny does not fire, check `tool_name`/field names against Task 1's
capture before changing any rule — a silent no-op is far more likely to be a
field-name mismatch than a logic bug.

- [ ] **Step 4: Remove the capture scaffolding**

```bash
git rm .claude/hooks/_capture.py
rm -f tests/hooks/fixtures/captured.jsonl
```

`payloads.json` stays — it is the record of the verified contract.

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json .claude/hooks tests/hooks
git commit -m "feat(v60): enable the PreToolUse guardrails; drop capture scaffolding"
```

---

### Task 6: Document it

**Files:**
- Modify: `CLAUDE.md` (the "Repo tooling (`.claude/`)" paragraph)
- Modify: `.codex/AGENTS.md`

- [ ] **Step 1: Add one line to CLAUDE.md's tooling paragraph**

After the sentence listing `/task-brief` and `/gate`, add:

```markdown
`.claude/hooks/guardrails.py` is a `PreToolUse` hook that **denies** the
patterns this file forbids in prose — unscoped `Glob`, `grep -r` from the
repo root, `Read` on a 100 KB+ `implemented/` plan, writes under
`.claude/worktrees/` — and warns on bare `pytest` and `cat` of the big docs.
Rules live in one pure `evaluate()` function, unit-tested in
`tests/hooks/test_guardrails.py`. It fails open by construction: if it and
this file ever disagree, this file wins and the hook is what gets fixed.
```

- [ ] **Step 2: Mirror to `.codex/AGENTS.md`, condensed**

Per `CLAUDE.md`, sync is one-way, Claude-authored, and condensed to that
file's register — two sentences, not the block above.

- [ ] **Step 3: Verify the whole rule suite once more**

```bash
python -m pytest tests/hooks/ -v
```
Expected: 22 passed

No full-suite run is needed: nothing here is imported by `swingbot/` or
`bot.py`, and `tests/hooks/` is the only coverage this code has.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md .codex/AGENTS.md
git commit -m "docs(v60): record the guardrail hook in CLAUDE.md and AGENTS.md"
```
