# v154 Skill layer repair and token cuts: Implementation Plan, part 1 (frontmatter and role descriptions)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief V154-2` or `grep -n "^### Task V154-2" -A 330 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md`](../specs/2026-10-10-v154-skill-layer-repair-token-cuts-design.md) (§ 1 and § 2)
**Index:** [`2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md`](2026-10-10-v154-skill-layer-repair-token-cuts_0-index.md): header block, `## Global Constraints`, `## Decisions fixed by this index`, `## Parallelisation`, the task ledger and contracts C1 (the helper) and C2 (importing it). Every task below implicitly includes that index's Global Constraints.

**Tasks in this part:** V154-1, V154-2, V154-3, V154-4. They are strictly serial, in id order: V154-2 and V154-3 import what V154-1 creates, V154-3 can only switch the test readers once V154-2 has quoted every description, and V154-4 edits the same `description:` lines as V154-2.

# Phase 1: Frontmatter repair and role descriptions

Three things hold for every task in this phase.

- **Line endings.** This checkout has `core.autocrlf=true`: 32 of the 34 skill and agent files counted when this plan was written are CRLF in the working tree (35 now: the vendored `etoro-public-api-operations`, added in `cd35dda`, is LF in the index; check its working-tree ending before touching it) and LF in the index. Never rewrite one of them with a tool that normalises line endings. The two one-off scripts below open files with `newline=""` and change exactly one line; use them, or the Edit tool, and nothing else. `git diff --numstat` is the check, because it compares content after normalisation.
- **One-off scripts are not committed.** They go under `.superpowers/tmp/` (`.superpowers/` is git-ignored; `mkdir -p .superpowers/tmp` first) and are run from the worktree root.
- **Anchor on text.** Line numbers quoted here are from `main` @ `4b9edabd`. Find every edit site with `grep -n` on the quoted text.

### Task V154-1: Strict frontmatter helper and the broken-frontmatter fixture

**Model:** sonnet — a small stdlib parser with an exact contract and its own test file; no cross-package judgement.

**Files:**
- Create: `scripts/dev/skill_frontmatter.py`
- Create: `tests/dev/test_skill_frontmatter.py`
- Create: `tests/hooks/fixtures/broken_frontmatter_SKILL.md`

**Interfaces:**
- Consumes: nothing.
- Produces (index contract C1, final; V154-2, V154-3, V154-4, V154-10 and V154-11 are written against it):

```python
class FrontmatterError(ValueError):
    """Frontmatter the real skill/agent loader rejects or misreads."""

def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ({key: value}, body) for a `---`-fenced markdown file."""

def quote_value(value: str) -> str:
    """Return `value` as a double-quoted scalar, `\\` and `"` escaped."""
```

**Why this exists.** Six of the nine role skills carry an unquoted `description:` with an inner `: `. That is not valid YAML, so the real loader lists them under their title-cased name ("Veteran trader") and they never trigger. The suite stayed green because three hand-rolled readers split on the first colon and accept it: `_read_skill` in `tests/hooks/test_skill_shape.py`, `_split_frontmatter` in `scripts/dev/sync_codex.py`, `_read_agent` in `tests/hooks/test_agent_shape.py`. This task builds the one strict reader that replaces all three. It changes none of them yet (V154-2 and V154-3 do), so nothing in the repo imports the new module at the end of this task except its own test.

**Behaviour, in full (index contract C1):**

- `\r\n` is normalised to `\n` before anything else.
- Text that does not start with `---\n` returns `({}, text)`.
- An opening fence with no closing `\n---\n` raises `FrontmatterError`.
- `body` is everything after the closing fence line: `text[4:].partition("\n---\n")[2]`, exactly what `sync_codex._split_frontmatter` returns today, so `.agents/skills/` stays byte-stable.
- Every value is a `str`. `disable-model-invocation: true` gives the string `"true"`; an inline `[a, b]` list stays that literal text. Never a bool, never a list.
- A double-quoted value comes back without its quotes, with `\"` and `\\` unescaped. An unquoted value comes back stripped.
- A `- item` line under a key folds into that key's value, joined with `", "`.
- Raises `FrontmatterError` naming the line on: an unquoted value containing `: ` or ` #`; a quoted value with an unescaped inner `"` or with text after the closing quote; a non-blank line that is neither `key: value` nor a `- item` under a key.
- `parse_frontmatter(f'---\ndescription: {quote_value(v)}\n---\n')[0]["description"] == v` for any single-line `v`.

Three details the contract leaves open, fixed here:

1. **Line numbers are file line numbers.** The opening `---` is line 1, so `frontmatter line 3` is line 3 in the editor. Messages have the form `frontmatter line <n>: <reason>`.
2. **A quoted value with no closing quote raises**, and so does **any backslash escape other than `\"` and `\\`** (`\n`, `\t`, a trailing lone backslash). YAML gives those a meaning this reader does not implement, and passing them through as two characters would be exactly the "misreads" case the helper exists to stop. No frontmatter in the repo uses one.
3. **`key:value` with no space after the colon is not a `key: value` line** and raises. An indented line that is not a `- item` raises too (the old `sync_codex` splitter skipped such lines silently).

- [ ] **Step 1: Create the regression fixture**

It is the frontmatter `veteran-trader` shipped with in v145, verbatim, one of today's six broken ones. Create `tests/hooks/fixtures/broken_frontmatter_SKILL.md` with exactly this content (the `description:` is one long line; do not wrap it, do not quote it):

```markdown
---
name: veteran-trader
description: Use when reviewing a spec, plan, diff or alert from the veteran-trader seat -- whether a setup is tradeable: fills, gaps, liquidity, regime, session timing, and whether an alert can be placed as resting orders before the open -- or when the expert-reviewer agent is dispatched with role=veteran-trader. Not for whether a lift is statistically real (quant-researcher) and not for position sizing or heat caps (risk-manager).
---

# Veteran trader

Fixture, not a skill: the `description:` above is the one that shipped in
v145. Its inner `: ` makes the unquoted scalar invalid YAML, so the loader
listed the skill as "Veteran trader" and it never triggered.
```

Nothing globs `tests/hooks/fixtures/` for skills (`SKILLS_DIR` is `.claude/skills`), so the file is inert until a test reads it by name.

Check the line you care about survived the paste:

```bash
sed -n 3p tests/hooks/fixtures/broken_frontmatter_SKILL.md | grep -c "is tradeable: fills, gaps"
```

Expected: `1`.

- [ ] **Step 2: Write the failing tests**

Create `tests/dev/test_skill_frontmatter.py`. `scripts/dev/` has no `__init__.py`, so the test puts that directory on `sys.path` and imports the module by name (index contract C2):

```python
"""scripts/dev/skill_frontmatter.py reads what the skill loader reads and
rejects what it rejects (v154 section 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import (  # noqa: E402
    FrontmatterError, parse_frontmatter, quote_value)

BROKEN_FIXTURE = ROOT / "tests" / "hooks" / "fixtures" / "broken_frontmatter_SKILL.md"


def _doc(*lines: str, body: str = "# Title\n") -> str:
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def test_text_without_an_opening_fence_has_no_frontmatter():
    assert parse_frontmatter("# Just a doc\n") == ({}, "# Just a doc\n")


def test_crlf_is_normalised_before_anything_else():
    meta, body = parse_frontmatter("---\r\nname: gate\r\n---\r\n# Gate\r\n")
    assert meta == {"name": "gate"}
    assert body == "# Gate\n"


def test_an_opening_fence_with_no_closing_fence_raises():
    with pytest.raises(FrontmatterError, match="line 1.*no closing ---"):
        parse_frontmatter("---\nname: gate\n# Gate\n")


def test_body_is_everything_after_the_closing_fence_line():
    text = _doc("name: gate", body="\n# Gate\n\n---\n\nrule below a rule\n")
    assert parse_frontmatter(text)[1] == "\n# Gate\n\n---\n\nrule below a rule\n"


def test_a_double_quoted_value_comes_back_without_its_quotes():
    meta, _ = parse_frontmatter(_doc(
        'description: "is it tradeable: fills, gaps #1 and a \\"quote\\" and a \\\\"'))
    assert meta["description"] == 'is it tradeable: fills, gaps #1 and a "quote" and a \\'


def test_an_unquoted_value_is_stripped():
    meta, _ = parse_frontmatter(_doc("name:    gate   ", "tools: Bash, Read, Grep"))
    assert meta == {"name": "gate", "tools": "Bash, Read, Grep"}


def test_every_value_is_a_string():
    meta, _ = parse_frontmatter(_doc(
        "disable-model-invocation: true", "context: fork",
        "skills: [superpowers:writing-plans, no-lookahead]", "empty:"))
    assert meta == {"disable-model-invocation": "true", "context": "fork",
                    "skills": "[superpowers:writing-plans, no-lookahead]",
                    "empty": ""}


def test_dash_items_fold_into_the_key_above_them():
    meta, _ = parse_frontmatter(_doc(
        "name: task-reviewer", "skills:", "  - no-lookahead",
        "  - senior-engineer", "model: sonnet"))
    assert meta["skills"] == "no-lookahead, senior-engineer"
    assert meta["model"] == "sonnet"


def test_blank_frontmatter_lines_are_skipped():
    assert parse_frontmatter(_doc("name: gate", "", "model: sonnet"))[0] == {
        "name": "gate", "model": "sonnet"}


@pytest.mark.parametrize("line, reason", [
    ("description: whether a setup is tradeable: fills and gaps", "': '"),
    ("description: follows the ### Task ids convention", "' #'"),
    ('description: "an unescaped "inner" quote"', "after the closing quote"),
    ('description: "closed" and then more', "after the closing quote"),
    ('description: "never closed', "no closing quote"),
    ('description: "a \\n newline escape"', "unsupported escape"),
    ("just some words", "not a `key: value` line"),
    ("  continued: on an indented line", "not a `key: value` line"),
    ("name:gate", "not a `key: value` line"),
])
def test_what_the_loader_rejects_or_misreads_raises(line, reason):
    with pytest.raises(FrontmatterError) as err:
        parse_frontmatter(_doc("name: x", line))
    assert "frontmatter line 3" in str(err.value)
    assert reason in str(err.value)


def test_a_dash_item_before_any_key_raises():
    with pytest.raises(FrontmatterError, match="line 2.*before any key"):
        parse_frontmatter(_doc("- orphan", "name: x"))


def test_quote_value_escapes_backslash_then_quote():
    assert quote_value('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'
    assert quote_value("") == '""'


@pytest.mark.parametrize("value", [
    "plain text",
    "is it tradeable: fills, gaps",
    "the ### Task ids convention",
    'a "quoted" word',
    "a back\\slash and a trailing one\\",
    "em dash — and a 2% cap",
    "",
])
def test_quote_value_round_trips_through_the_parser(value):
    text = f"---\ndescription: {quote_value(value)}\n---\n"
    assert parse_frontmatter(text)[0]["description"] == value


def test_the_frontmatter_that_shipped_broken_is_rejected():
    """Six role skills shipped with this shape in v145 and never triggered."""
    with pytest.raises(FrontmatterError) as err:
        parse_frontmatter(BROKEN_FIXTURE.read_text(encoding="utf-8"))
    assert "frontmatter line 3" in str(err.value)
    assert "': '" in str(err.value)


def test_quoting_the_broken_description_is_the_whole_repair():
    lines = BROKEN_FIXTURE.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    prefix = "description: "
    assert lines[2].startswith(prefix)
    value = lines[2][len(prefix):]
    lines[2] = prefix + quote_value(value)
    meta, body = parse_frontmatter("\n".join(lines))
    assert meta == {"name": "veteran-trader", "description": value}
    assert "tradeable: fills" in meta["description"]
    assert body.startswith("\n# Veteran trader\n")
```

Reading notes for the escapes above, since they are easy to get wrong when retyping: in a normal (non-raw) Python string `'\\"'` is the two characters backslash, quote. So the frontmatter text in `test_a_double_quoted_value_comes_back_without_its_quotes` is `"is it tradeable: fills, gaps #1 and a \"quote\" and a \\"` and the expected value ends in one backslash.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/dev/test_skill_frontmatter.py`

Expected: a failing verdict whose cause is a collection error, `ModuleNotFoundError: No module named 'skill_frontmatter'`. Any other failure means the fixture or the test file is wrong; fix that before going on.

- [ ] **Step 4: Write the helper**

Create `scripts/dev/skill_frontmatter.py`:

```python
"""Strict reader for the frontmatter of .claude/skills/*/SKILL.md and
.claude/agents/*.md -- the one parser behind scripts/dev/sync_codex.py,
tests/hooks/test_skill_shape.py and tests/hooks/test_agent_shape.py.

The three lenient `line.split(":", 1)` readers it replaces accepted
frontmatter the real loader rejects: an unquoted `description:` holding an
inner `: ` is not valid YAML, the skill then lists under its title-cased name
and never triggers, and the suite stayed green (v154). This reader raises
instead. Stdlib only: PyYAML is not a dependency of this repo.

Every value comes back as a `str` -- `disable-model-invocation: true` is the
string "true", an inline `[a, b]` list is that literal text.
"""
from __future__ import annotations

import re

_FENCE = "---\n"
_CLOSE = "\n---\n"
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")
# What YAML reads as something other than text inside an unquoted scalar:
# `: ` starts a nested mapping (a parse error), ` #` starts a comment (the
# rest of the value is silently dropped).
_UNQUOTED_TRAPS = (": ", " #")
_ESCAPABLE = ('"', "\\")


class FrontmatterError(ValueError):
    """Frontmatter the real skill/agent loader rejects or misreads."""


def quote_value(value: str) -> str:
    """Return `value` as a double-quoted scalar, `\\` and `"` escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fail(lineno: int, reason: str) -> FrontmatterError:
    return FrontmatterError(f"frontmatter line {lineno}: {reason}")


def _unquote(raw: str, lineno: int) -> str:
    """Value of a scalar that opens with a double quote."""
    out, i = [], 1
    while i < len(raw):
        char = raw[i]
        if char == '"':
            if raw[i + 1:].strip():
                raise _fail(lineno, 'text after the closing quote -- write an '
                                    'inner double quote as \\"')
            return "".join(out)
        if char == "\\":
            escaped = raw[i + 1:i + 2]
            if escaped not in _ESCAPABLE:
                raise _fail(lineno, f"unsupported escape \\{escaped} -- only "
                                    '\\" and \\\\ are read')
            out.append(escaped)
            i += 2
            continue
        out.append(char)
        i += 1
    raise _fail(lineno, "quoted value has no closing quote")


def _scalar(raw: str, lineno: int) -> str:
    if raw.startswith('"'):
        return _unquote(raw, lineno)
    for trap in _UNQUOTED_TRAPS:
        if trap in raw:
            raise _fail(lineno, f"unquoted value contains {trap!r} -- wrap the "
                                "whole value in double quotes")
    return raw


def _read_line(meta: dict[str, str], key: str | None, line: str,
               lineno: int) -> str:
    """Fold one frontmatter line into `meta`; return the key it belongs to."""
    stripped = line.strip()
    if stripped.startswith("- "):
        if key is None:
            raise _fail(lineno, f"list item before any key: {stripped!r}")
        meta[key] = ", ".join(filter(None, [meta[key], stripped[2:].strip()]))
        return key
    match = _KEY_RE.match(line)
    if match is None:
        raise _fail(lineno, f"not a `key: value` line: {line!r}")
    key = match.group(1)
    meta[key] = _scalar((match.group(2) or "").strip(), lineno)
    return key


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return ({key: value}, body) for a `---`-fenced markdown file.

    Line numbers in errors are file line numbers: the opening fence is line 1.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith(_FENCE):
        return {}, text
    head, close, body = text[len(_FENCE):].partition(_CLOSE)
    if not close:
        raise _fail(1, "opening --- has no closing --- line")
    meta: dict[str, str] = {}
    key = None
    for lineno, line in enumerate(head.split("\n"), start=2):
        if line.strip():
            key = _read_line(meta, key, line, lineno)
    return meta, body
```

How it fits together: `parse_frontmatter` cuts the head out between the fences and walks it line by line, numbering from 2 because the fence is line 1. `_read_line` decides whether a line is a `- item` (folded into the current key) or a `key: value` (matched by `_KEY_RE`, which demands whitespace after the colon or nothing at all). `_scalar` routes a value that opens with `"` to `_unquote` and applies the two unquoted traps to everything else. `_unquote` walks the characters once: a `"` must be the last non-blank thing on the line, a backslash must be followed by `"` or `\`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/dev/test_skill_frontmatter.py`

Expected: green, `29 passed`, `0 failed`.

- [ ] **Step 6: See what the strict reader makes of the repo today**

This is the red baseline V154-2 turns green. It changes nothing:

```bash
python - <<'PY'
import pathlib, sys
sys.path.insert(0, "scripts/dev")
from skill_frontmatter import FrontmatterError, parse_frontmatter
files = (sorted(pathlib.Path(".claude/skills").glob("*/SKILL.md"))
         + sorted(pathlib.Path(".claude/agents").glob("*.md")))
bad = 0
for path in files:
    try:
        parse_frontmatter(path.read_text(encoding="utf-8"))
    except FrontmatterError as exc:
        bad += 1
        print(path.as_posix(), "->", exc)
print(len(files), "files,", bad, "rejected")
PY
```

Expected: `35 files, 7 rejected` (25 skills + the vendored `etoro-public-api-operations` = 26 skills, plus 9 agents; the vendored description is unquoted but holds no inner `: ` or ` #`, so it is not rejected). The seven are the six role skills with an inner `: ` (`financial-advisor`, `quant-engineer`, `senior-engineer`, `staff-engineer`, `technical-analyst`, `veteran-trader`, each `frontmatter line 3: unquoted value contains ': '`) and `.claude/agents/plan-writer.md` (`unquoted value contains ' #'`, from the `### Task ids` in its description). A different set is worth one line in your report (a description changed on `main` since this plan was written) but does not block the task: V154-2 quotes whatever is there.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C scripts/dev/skill_frontmatter.py`

Expected: no output (every function is rank A or B; the highest are `_read_line` and `parse_frontmatter` at 5).

- [ ] **Step 8: Commit**

```bash
git add scripts/dev/skill_frontmatter.py tests/dev/test_skill_frontmatter.py tests/hooks/fixtures/broken_frontmatter_SKILL.md
git commit -m "feat(v154): strict frontmatter reader for skills and agents, with the broken-frontmatter fixture"
```

No skill or agent file is touched, so there is no `sync_codex.py` run in this commit.

### Task V154-2: Quote every skill and agent description; `sync_codex.py` parses and re-emits through the helper

**Model:** sonnet — a mechanical one-line change across 35 files plus a four-site edit of one script, with a byte-stability check that needs care but no design.

**Files:**
- Modify: `scripts/dev/sync_codex.py`
- Modify: `tests/hooks/test_codex_mirror.py`
- Modify: `.claude/skills/alert-surface/SKILL.md`
- Modify: `.claude/skills/backtest-gate/SKILL.md`
- Modify: `.claude/skills/backup-pull/SKILL.md`
- Modify: `.claude/skills/close-out/SKILL.md`
- Modify: `.claude/skills/deploy/SKILL.md`
- Modify: `.claude/skills/edge-module/SKILL.md`
- Modify: `.claude/skills/etoro-public-api-operations/SKILL.md` (vendored, added in `cd35dda`; its description is unquoted at `SKILL.md:3` and `tests/hooks/test_skill_shape.py` keeps it in `VENDORED`. Quote the description only and change nothing else in the vendor file — a reinstall of the vendor skill must re-quote it)
- Modify: `.claude/skills/financial-advisor/SKILL.md`
- Modify: `.claude/skills/fundamental-analyst/SKILL.md`
- Modify: `.claude/skills/gate/SKILL.md`
- Modify: `.claude/skills/mirror-prod/SKILL.md`
- Modify: `.claude/skills/new-doc/SKILL.md`
- Modify: `.claude/skills/no-lookahead/SKILL.md`
- Modify: `.claude/skills/panel/SKILL.md`
- Modify: `.claude/skills/pooled-numbers/SKILL.md`
- Modify: `.claude/skills/quant-engineer/SKILL.md`
- Modify: `.claude/skills/quant-researcher/SKILL.md`
- Modify: `.claude/skills/risk-manager/SKILL.md`
- Modify: `.claude/skills/schema-change/SKILL.md`
- Modify: `.claude/skills/senior-engineer/SKILL.md`
- Modify: `.claude/skills/stable-snapshot/SKILL.md`
- Modify: `.claude/skills/staff-engineer/SKILL.md`
- Modify: `.claude/skills/task-brief/SKILL.md`
- Modify: `.claude/skills/technical-analyst/SKILL.md`
- Modify: `.claude/skills/veteran-trader/SKILL.md`
- Modify: `.claude/skills/worktree-lifecycle/SKILL.md`
- Modify: `.claude/agents/backtest-runner.md`
- Modify: `.claude/agents/expert-reviewer.md`
- Modify: `.claude/agents/plan-briefer.md`
- Modify: `.claude/agents/plan-writer.md`
- Modify: `.claude/agents/prod-inspector.md`
- Modify: `.claude/agents/symbol-verifier.md`
- Modify: `.claude/agents/task-implementer.md`
- Modify: `.claude/agents/task-reviewer.md`
- Modify: `.claude/agents/test-runner.md`
- Regenerated by `python scripts/dev/sync_codex.py`, never by hand: the 26 `.agents/skills/<name>/SKILL.md` copies (one line each). `.codex/agents/*.toml` come out byte-identical.

`tests/hooks/test_codex_mirror.py` is not in the index ledger's file list for this task. It is added here because it is the only place that already loads `sync_codex` and it is where the new behaviour (quoted re-emit, strict read, path in the error) can be pinned; no other task touches that file.

**Interfaces:**
- Consumes (created by V154-1, `scripts/dev/skill_frontmatter.py`): `FrontmatterError`, `parse_frontmatter(text) -> (dict[str, str], str)`, `quote_value(value) -> str`.
- Produces:
  - Every `description:` in `.claude/skills/*/SKILL.md` (26, including the vendored `etoro-public-api-operations`) and `.claude/agents/*.md` (9) is a double-quoted scalar. The text inside the quotes is unchanged, character for character.
  - `sync_codex._split_frontmatter(text)` keeps its name and its `(meta, body)` return shape and delegates to `parse_frontmatter`, so it now raises `FrontmatterError` on what the loader rejects and returns descriptions without their quotes.
  - `sync_codex.FrontmatterError`, `sync_codex.parse_frontmatter`, `sync_codex.quote_value` are importable names of the loaded module (the mirror test uses them).
  - Generated `.agents/skills/<name>/SKILL.md` line 3 is `description: <quote_value(description)>`.

**What must not change.** No description's wording (V154-4 trims the nine role descriptions; this task only adds quotes). No `name:`, `tools:`, `model:`, `skills:`, `context:` or `disable-model-invocation:` line. No line ending. No `.codex/agents/*.toml` byte: an agent's description reaches TOML through `_toml_string`, and the parser hands it the same text as before, minus the quotes it never used to have.

**`.claude/agents/plan-writer.md` was edited by another session on 2026-10-10** (commit `8d265529`, "cap plan part writers at 2 at once", and possibly again since). This plan therefore quotes no agent description text anywhere. Before Step 6, read the line as it is now:

```bash
grep -n "^description:" .claude/agents/plan-writer.md
```

Whatever that prints is what gets wrapped; the script takes the text from the file, never from this plan. If, when this branch is later merged, `main` carries a different `plan-writer.md` description, resolve the conflict by taking `main`'s wording, then re-run the Step 6 script and `python scripts/dev/sync_codex.py` and re-run Step 9.

- [ ] **Step 1: Confirm the starting point**

```bash
git grep -n "^def _split_frontmatter\|_split_frontmatter(" -- scripts/dev/sync_codex.py
git grep -c '^description: "' -- '.claude/skills/*/SKILL.md' '.claude/agents/*.md' | wc -l
```

Expected: three lines from `sync_codex.py` (the `def`, the call in `_skill_outputs`, the call in `_agent_outputs`), then `0` (no description is quoted yet). If the second number is not `0`, some files are already quoted: carry on, the Step 6 script skips them.

- [ ] **Step 2: Write the failing tests**

In `tests/hooks/test_codex_mirror.py`, replace the import block at the top

```python
import importlib.util
import json
import pathlib
```

with

```python
import importlib.util
import json
import pathlib
import re

import pytest
```

and append this at the end of the file (two blank lines after the last existing test):

```python
# v154: every description is a double-quoted scalar, read and re-emitted
# through scripts/dev/skill_frontmatter.py.
_FIXTURE = _ROOT / "tests" / "hooks" / "fixtures" / "broken_frontmatter_SKILL.md"
_QUOTED_DESCRIPTION = re.compile(r'^description: ".*"$', re.M)


def _sources():
    return (sorted((_ROOT / ".claude" / "skills").glob("*/SKILL.md"))
            + sorted((_ROOT / ".claude" / "agents").glob("*.md")))


def test_every_source_description_is_a_double_quoted_scalar():
    unquoted = [p.relative_to(_ROOT).as_posix() for p in _sources()
                if not _QUOTED_DESCRIPTION.search(p.read_text(encoding="utf-8"))]
    assert not unquoted, unquoted


def test_generated_skill_description_is_quoted_and_reads_back_the_same():
    for skill in (_ROOT / ".claude" / "skills").glob("*/SKILL.md"):
        name = skill.parent.name
        meta, _ = sync_codex._split_frontmatter(skill.read_text(encoding="utf-8"))
        copy = (_ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        expected = "description: " + sync_codex.quote_value(meta["description"])
        assert copy.splitlines()[2] == expected, name
        assert sync_codex._split_frontmatter(copy)[0]["description"] == meta["description"], name


def test_split_frontmatter_is_the_strict_reader():
    with pytest.raises(sync_codex.FrontmatterError, match="frontmatter line 3"):
        sync_codex._split_frontmatter(_FIXTURE.read_text(encoding="utf-8"))


def test_a_broken_source_is_reported_with_its_path(tmp_path, monkeypatch):
    skill = tmp_path / ".claude" / "skills" / "broken" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(sync_codex, "ROOT", tmp_path)
    with pytest.raises(sync_codex.FrontmatterError,
                       match=r"^\.claude/skills/broken/SKILL\.md: frontmatter line 3"):
        sync_codex._skill_outputs(skill)


def test_main_reports_broken_frontmatter_without_a_traceback(monkeypatch, capsys):
    def broken():
        raise sync_codex.FrontmatterError("x/SKILL.md: frontmatter line 3: nope")

    monkeypatch.setattr(sync_codex, "expected_files", broken)
    assert sync_codex.main(["--check"]) == 1
    out = capsys.readouterr().out
    assert "invalid frontmatter: x/SKILL.md: frontmatter line 3: nope" in out
```

What each one pins: the sources are quoted (so the next inner colon is harmless); the generated copy is quoted and reads back to the same text (Codex has a YAML parser too); `_split_frontmatter` is the strict reader, proven on the fixture from V154-1; a broken source names its file; and the CLI prints one line instead of a traceback.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`

Expected: `5 failed, 7 passed`. The five new tests fail: `test_every_source_description_is_a_double_quoted_scalar` lists all 35 files, and the other four die on `AttributeError: module 'sync_codex' has no attribute 'quote_value'` or `'FrontmatterError'`. The seven existing tests still pass.

- [ ] **Step 4: Route `sync_codex.py` through the helper**

Four edits in `scripts/dev/sync_codex.py`. Find each by its text.

Edit 1, the imports. Replace

```python
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
```

with

```python
import json
import pathlib
import sys

# tests/hooks/test_codex_mirror.py loads this file by path, so the sibling
# helper is importable only once this directory is on sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from skill_frontmatter import (  # noqa: E402
    FrontmatterError, parse_frontmatter, quote_value)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
```

Edit 2, the splitter and the skill emitter. Replace

```python
def _split_frontmatter(text: str):
    """Return ({key: value}, body) for a `---`-fenced markdown file."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith(" "):
            meta[key.strip()] = value.strip()
    return meta, body


def _skill_outputs(skill_md: pathlib.Path) -> dict:
    meta, body = _split_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = skill_md.parent.name
    source = skill_md.relative_to(ROOT).as_posix()
    text = (f"---\nname: {meta.get('name', name)}\n"
            f"description: {meta.get('description', '')}\n---\n"
```

with

```python
def _split_frontmatter(text: str):
    """Return ({key: value}, body) for a `---`-fenced markdown file.

    Strict -- scripts/dev/skill_frontmatter.py raises FrontmatterError on
    frontmatter the real loader rejects. A quoted value comes back unquoted."""
    return parse_frontmatter(text)


def _read_source(path: pathlib.Path):
    """`_split_frontmatter` of one source file; an error names the file."""
    try:
        return _split_frontmatter(path.read_text(encoding="utf-8"))
    except FrontmatterError as exc:
        raise FrontmatterError(
            f"{path.relative_to(ROOT).as_posix()}: {exc}") from None


def _skill_outputs(skill_md: pathlib.Path) -> dict:
    meta, body = _read_source(skill_md)
    name = skill_md.parent.name
    source = skill_md.relative_to(ROOT).as_posix()
    text = (f"---\nname: {meta.get('name', name)}\n"
            f"description: {quote_value(meta.get('description', ''))}\n---\n"
```

The rest of `_skill_outputs` (the banner line, the `openai.yaml` branch with its `== "true"` comparison) is untouched: values are still strings.

Edit 3, the agent emitter's first line. Replace

```python
def _agent_outputs(agent_md: pathlib.Path) -> dict:
    meta, body = _split_frontmatter(agent_md.read_text(encoding="utf-8"))
```

with

```python
def _agent_outputs(agent_md: pathlib.Path) -> dict:
    meta, body = _read_source(agent_md)
```

Edit 4, `main`. Replace

```python
def main(argv: list) -> int:
    if "--check" not in argv:
        write()
    problems = check()
    for line in problems:
```

with

```python
def main(argv: list) -> int:
    try:
        if "--check" not in argv:
            write()
        problems = check()
    except FrontmatterError as exc:
        print(f"invalid frontmatter: {exc}")
        return 1
    for line in problems:
```

`write()` builds `expected_files()` before it deletes or writes anything, so a broken source stops the run with nothing half-written.

- [ ] **Step 5: See the strict reader fail on today's files**

Run: `python scripts/dev/sync_codex.py --check`

Expected, exit code 1, one line:

```
invalid frontmatter: .claude/skills/financial-advisor/SKILL.md: frontmatter line 3: unquoted value contains ': ' -- wrap the whole value in double quotes
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`

Expected: `7 failed, 5 passed`. The count went up, and that is the point: every test that walks the real skills now raises `FrontmatterError` naming `financial-advisor`, which is the failure the old splitter hid. The three new tests that need no real skill file pass (`test_split_frontmatter_is_the_strict_reader`, `test_a_broken_source_is_reported_with_its_path`, `test_main_reports_broken_frontmatter_without_a_traceback`).

- [ ] **Step 6: Quote the 35 descriptions**

Re-read `plan-writer.md`'s description first (the `grep` in the note above). Then save this as `.superpowers/tmp/v154_quote_descriptions.py` (`mkdir -p .superpowers/tmp`; the directory is git-ignored and the script is not committed):

```python
"""One-off for V154-2: wrap every `description:` value in double quotes.

Run from the worktree root. Not committed. Rewrites only the one line, keeps
each file's line endings, and is safe to run twice.
"""
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path("scripts/dev").resolve()))
from skill_frontmatter import parse_frontmatter, quote_value  # noqa: E402

LINE_RE = re.compile(r"^description: (.*?)(\r?)$", re.M)
PREFIX = "description: "


def committed_value(path: pathlib.Path) -> str:
    """The description as committed at HEAD, quotes removed if it had any."""
    old = subprocess.run(["git", "show", f"HEAD:{path.as_posix()}"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    line = next(l for l in old.replace("\r\n", "\n").split("\n")
                if l.startswith(PREFIX))
    value = line[len(PREFIX):].strip()
    if value.startswith('"'):
        return parse_frontmatter(f"---\n{line}\n---\n")[0]["description"]
    return value


def quote_one(path: pathlib.Path) -> bool:
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    match = LINE_RE.search(text)
    if match is None or match.start() > text.index("\n---", 3):
        sys.exit(f"{path}: no description line inside the frontmatter")
    value = match.group(1).strip()
    if value.startswith('"'):
        return False
    line = f"{PREFIX}{quote_value(value)}{match.group(2)}"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text[:match.start()] + line + text[match.end():])
    return True


def main() -> None:
    files = (sorted(pathlib.Path(".claude/skills").glob("*/SKILL.md"))
             + sorted(pathlib.Path(".claude/agents").glob("*.md")))
    quoted = sum(quote_one(path) for path in files)
    for path in files:
        now = parse_frontmatter(path.read_text(encoding="utf-8"))[0]["description"]
        if now != committed_value(path):
            sys.exit(f"{path}: description text changed -- it must not")
    print(f"{quoted} quoted this run; {len(files)} files parse strictly, "
          "every description text unchanged from HEAD")


if __name__ == "__main__":
    main()
```

It finds the `description:` line inside the frontmatter, wraps the value with `quote_value` (which escapes `\` and `"`; no description holds either today), keeps the line's own `\r` if it has one, and then proves two things for all 35 files: the strict reader accepts the file, and the value it reads equals the value committed at `HEAD`.

Run it from the worktree root:

```bash
python .superpowers/tmp/v154_quote_descriptions.py
```

Expected: `35 quoted this run; 35 files parse strictly, every description text unchanged from HEAD`. Run it a second time: `0 quoted this run; ...` (it is idempotent).

- [ ] **Step 7: Check the edit is one line per file and nothing else**

```bash
git diff --numstat -- .claude/skills .claude/agents | awk '{print $1, $2}' | sort | uniq -c
git diff -- .claude/agents/plan-writer.md | grep "^[-+]description"
```

Expected: `35 1 1` (35 files, each one line added and one removed; a CRLF-to-LF rewrite of a whole file would show as a large count here, and is a stop). The second command shows the old line and the same line wrapped in `"`, with the wording you read before Step 6.

- [ ] **Step 8: Regenerate the Codex mirror and check it is byte-stable apart from the quoting**

```bash
python scripts/dev/sync_codex.py
git diff --numstat -- .agents .codex | awk '{print $1, $2}' | sort | uniq -c
git diff --numstat -- .codex | wc -l
head -3 .agents/skills/veteran-trader/SKILL.md
```

Expected: `Codex mirror is current.`; then `26 1 1` (the 26 generated skill copies, one line each); then `0` (no `.toml` changed); then a frontmatter whose third line starts `description: "Use when reviewing a spec, plan, diff or alert from the veteran-trader seat -- whether a setup is tradeable: fills, gaps,` and ends with a closing `"`.

`git status` may list more `.agents/` and `.codex/` files than that as modified: the generator writes LF and this checkout expects CRLF, which is stat noise, not content. `git diff --numstat` is the truth.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py tests/hooks/test_role_skills.py tests/dev/test_skill_frontmatter.py`

Expected: green, `0 failed`. `test_codex_mirror.py` is now `12 passed`. `test_skill_shape.py` and `test_agent_shape.py` still use their own lenient readers until V154-3 and still pass: a quoted description is longer than 40 characters and still contains `Run as /<name>, or by Claude itself`.

- [ ] **Step 10: Complexity**

Run: `python -m radon cc -s -n C scripts/dev/sync_codex.py tests/hooks/test_codex_mirror.py`

Expected: no output. `_split_frontmatter` drops from 5 to 1; `main` goes from 4 to 5.

- [ ] **Step 11: Commit**

One commit: the mirror test is red at every point between "the reader is strict" and "everything is quoted and regenerated", so the pieces cannot land separately.

```bash
git add scripts/dev/sync_codex.py tests/hooks/test_codex_mirror.py .claude/skills .claude/agents .agents .codex
git status --short | grep -v "^M  \(\.claude/skills/[a-z-]*/SKILL\.md\|\.claude/agents/[a-z-]*\.md\|\.agents/skills/[a-z-]*/SKILL\.md\|scripts/dev/sync_codex\.py\|tests/hooks/test_codex_mirror\.py\)$"
git commit -m "fix(v154): quote every skill and agent description; sync_codex reads and re-emits through the strict helper"
```

Expected from the middle command: no output (nothing staged outside the 35 sources, the 26 generated copies, the script and the test). Anything it prints is a file this task should not have touched: unstage it (`git restore --staged <path>`) and work out why before committing.

### Task V154-3: `test_skill_shape.py` and `test_agent_shape.py` read frontmatter through the helper

**Model:** haiku — two reader functions are replaced by a one-line call with the exact old and new text given; nothing to decide.

**Files:**
- Modify: `tests/hooks/test_skill_shape.py`
- Modify: `tests/hooks/test_agent_shape.py`
- Test: the same two files (they are test modules; the change is to their readers).

**Interfaces:**
- Consumes:
  - `parse_frontmatter(text) -> (dict[str, str], str)` and `FrontmatterError` from `scripts/dev/skill_frontmatter.py` (V154-1).
  - `tests/hooks/fixtures/broken_frontmatter_SKILL.md` (V154-1).
  - Every `description:` already double-quoted (V154-2). **Do not start this task before V154-2 is committed:** the strict reader rejects seven of the unquoted files and both modules would fail at every test.
- Produces:
  - `_read_skill(name)` in `test_skill_shape.py` and `_read_agent(name)` in `test_agent_shape.py` keep their names, their one argument and their `(meta, body)` return shape. Every existing test that calls them is unchanged.
  - The import pattern later tasks copy into a test module (index contract C2):

```python
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402
```

**What changes for callers, and why none of them notice.** Values come back without their quotes, which is what every assertion already assumed (`len(...) >= 40`, `== "true"`, `"Run as /<name>, or by Claude itself" in ...`, `meta.get("model")`). `body` no longer starts with the newline that followed the closing `---`; every use of `body` in both files is a substring test or a regex scan, so that is invisible. Two behaviours get stricter on purpose: frontmatter the loader rejects now raises `FrontmatterError` instead of passing, and a file with no frontmatter gives `({}, text)`, so its test fails on the `name` assertion instead of on a tuple-unpack error.

Do not touch `tests/hooks/test_role_skills.py` here: its `_body` helper splits on `---` only to reach the body and is fine. V154-4 adds the helper import to that file.

- [ ] **Step 1: Write the failing tests**

Append this at the end of `tests/hooks/test_skill_shape.py` (two blank lines after the last existing test). Add nothing else to the file yet:

```python
# v154: the reader is scripts/dev/skill_frontmatter.py, which rejects what the
# real loader rejects. The fixture is the frontmatter six role skills shipped
# with in v145 -- they listed under their title-cased name and never triggered
# while the old colon splitter here kept the suite green.
BROKEN_FIXTURE = _REPO_ROOT / "tests" / "hooks" / "fixtures" / "broken_frontmatter_SKILL.md"


def test_the_reader_rejects_the_frontmatter_that_shipped_broken():
    with pytest.raises(FrontmatterError, match="frontmatter line 3"):
        parse_frontmatter(BROKEN_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_description_is_read_without_its_quotes(path):
    description = _read_skill(path.name)[0]["description"]
    assert description and description[0] != '"' and description[-1] != '"'
```

Append this at the end of `tests/hooks/test_agent_shape.py`:

```python
# v154: agents are read through the same strict reader as skills.
@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.stem)
def test_every_agent_description_is_read_without_its_quotes(path):
    description = _read_agent(path.stem)[0]["description"]
    assert description and description[0] != '"' and description[-1] != '"'


def test_dash_item_skills_fold_into_one_value():
    meta, _ = parse_frontmatter(
        "---\nname: x\nskills:\n  - no-lookahead\n  - senior-engineer\n---\n")
    assert _skills(meta) == {"no-lookahead", "senior-engineer"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py`

Expected: `37 failed`. In `test_skill_shape.py`, 27: `test_the_reader_rejects_the_frontmatter_that_shipped_broken` with `NameError: name 'FrontmatterError' is not defined`, and all 26 cases of `test_every_description_is_read_without_its_quotes`, because the old colon splitter hands back the value with its quotes on. In `test_agent_shape.py`, 10: the nine agents for the same reason, and `test_dash_item_skills_fold_into_one_value` with `NameError: name 'parse_frontmatter' is not defined`. Every pre-existing test still passes.

- [ ] **Step 3: Switch `test_skill_shape.py` to the helper**

Edit 1, the top of the file. Replace

```python
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
```

with

```python
import pathlib
import re
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev"))

from skill_frontmatter import FrontmatterError, parse_frontmatter  # noqa: E402

```

(The new block ends with a blank line, so there is still exactly one blank line before `SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"`.)

Edit 2, the reader. Replace the whole function

```python
def _read_skill(name):
    """Return (frontmatter dict, body) for one skill. Frontmatter is the
    simple `key: value` subset this repo's skills actually use."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body
```

with

```python
def _read_skill(name):
    """Return (frontmatter dict, body) for one skill, through the strict
    reader the Codex mirror also uses: frontmatter the real loader rejects
    raises FrontmatterError here instead of passing quietly."""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    return parse_frontmatter(text)
```

Change nothing else in the file: not the tier sets, not `_THRESHOLD_RE`, not `FORKED`, not any assertion (V154-10 and V154-11 add to `TIER_2` and `FORKED` later).

- [ ] **Step 4: Switch `test_agent_shape.py` to the helper**

Edit 1, the top of the file. Replace

```python
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
```

with

```python
import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

```

Edit 2, the reader. Replace the whole function

```python
def _read_agent(name):
    """Return (frontmatter dict, body) -- the simple `key: value` subset,
    plus YAML `- item` lines collected under the preceding list key."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, fm, body = text.split("---", 2)
    meta, key = {}, None
    for line in fm.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and key:
            meta[key] = ", ".join(filter(None, [meta[key], stripped[2:]]))
        elif ":" in line and not line.startswith(" "):
            key, v = (s.strip() for s in line.split(":", 1))
            meta[key] = v
    return meta, body
```

with

```python
def _read_agent(name):
    """Return (frontmatter dict, body) for one agent, through the strict
    reader skills use. `- item` lines fold into the key above them, joined
    with ", "; an inline `[a, b]` list stays that literal text."""
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return parse_frontmatter(text)
```

`_skills(meta)` just below it is unchanged: it strips `[]` and splits on commas, which reads both the inline form the agents use today (`skills: [no-lookahead, senior-engineer]`) and the folded `- item` form.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py`

Expected: green, `141 passed`, `0 failed` (106 in `test_skill_shape.py`, 35 in `test_agent_shape.py`; the vendored `etoro-public-api-operations` adds one case to each `_skill_dirs()`-parametrised test over the 104 counted when this plan was written. A pass count off by a skill or two is not a failure; `0 failed` is the gate).

If instead every test errors with `FrontmatterError ... unquoted value contains`, V154-2 is not in this branch: stop and report, do not loosen the reader.

- [ ] **Step 6: Confirm no lenient splitter is left**

```bash
git grep -n 'split(":", 1)\|partition(":")' -- tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py scripts/dev/sync_codex.py
git grep -n "parse_frontmatter" -- tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py scripts/dev/sync_codex.py
```

Expected: the first command prints nothing. The second prints an import and at least one call in each of the three files.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py`

Expected: one line at most, `test_backup_skills_match_the_v120_final_fixes - C (12)`. It is a pre-existing function this task does not touch and it is under the limit of 15. `_read_skill` and `_read_agent` are both rank A (1).

- [ ] **Step 8: Commit**

```bash
git add tests/hooks/test_skill_shape.py tests/hooks/test_agent_shape.py
git commit -m "test(v154): skill and agent shape tests read frontmatter through the strict helper"
```

No file under `.claude/skills/` or `.claude/agents/` is touched, so there is no `sync_codex.py` run in this commit.

### Task V154-4: Nine role descriptions at most 260 characters, pinned

**Model:** opus — the nine descriptions are the trigger text every session and subagent reads; choosing what each seat keeps inside a hard cap is a wording judgement that a missed fire case later pays for.

**Files:**
- Modify: `tests/hooks/test_role_skills.py`
- Modify: `.claude/skills/quant-researcher/SKILL.md`
- Modify: `.claude/skills/risk-manager/SKILL.md`
- Modify: `.claude/skills/financial-advisor/SKILL.md`
- Modify: `.claude/skills/veteran-trader/SKILL.md`
- Modify: `.claude/skills/technical-analyst/SKILL.md`
- Modify: `.claude/skills/fundamental-analyst/SKILL.md`
- Modify: `.claude/skills/staff-engineer/SKILL.md`
- Modify: `.claude/skills/quant-engineer/SKILL.md`
- Modify: `.claude/skills/senior-engineer/SKILL.md`
- Regenerated by `python scripts/dev/sync_codex.py`, never by hand: the nine matching `.agents/skills/<role>/SKILL.md` copies.

**Interfaces:**
- Consumes:
  - `parse_frontmatter`, `quote_value` from `scripts/dev/skill_frontmatter.py` (V154-1).
  - Quoted `description:` lines (V154-2) and the C2 import pattern (V154-3).
  - `ROLES` (the nine role names) and `_text(path)` in `tests/hooks/test_role_skills.py`, both existing.
- Produces:
  - `MAX_ROLE_DESCRIPTION = 260` and `_description(name)` in `tests/hooks/test_role_skills.py`.
  - The final role trigger text that V154-12 runs the nine eval suites against.

**The rule (spec § 2, index Global Constraints).** Each description keeps the seat, the three to five things it checks, and its "Not for ... (other-role)" hand-offs, and drops the clause `or when the expert-reviewer agent is dispatched with role=<x>`: the agent invokes the skill by name and never needed it. The cap is 260 characters of the **parsed value**, the text inside the quotes, not the line. Roles stay model-invocable. **The cap is never raised**; a fire case that misses is fixed by rewording inside it.

**Only line 3 of each file changes.** No skill body, no `## Trigger table`, no eval case, no `name:` line.

The table shows what each seat keeps. Lengths are of the value.

| Role | Today | New | Checks kept | Hand-offs kept |
|---|---|---|---|---|
| `quant-researcher` | 504 | 250 | ExpR or win-rate lift, grid winner, pre-registration, screen verdict, badge tier | `quant-engineer`, `veteran-trader` |
| `risk-manager` | 379 | 250 | the 2% dollar-risk cap, position sizing, portfolio heat, correlated exposure, stop placement | `veteran-trader`, `financial-advisor` |
| `financial-advisor` | 466 | 249 | retail account fit, tax drag of swing turnover, alert frequency, how performance and risk are shown | `risk-manager` |
| `veteran-trader` | 423 | 256 | tradeability, fills, gaps, liquidity, regime, session timing, resting orders before the open | `quant-researcher`, `risk-manager` |
| `technical-analyst` | 437 | 251 | support/resistance, chart and candlestick patterns, FVG, Fibonacci, trendlines, indicator logic | `quant-researcher`, `quant-engineer` |
| `fundamental-analyst` | 416 | 254 | earnings dates, catalysts, macro events, sector concentration, point-in-time fundamentals, universe membership | `technical-analyst`, `risk-manager` |
| `staff-engineer` | 407 | 254 | `swingbot/core` package seams, schema migrations, production VM ops, blast radius, maintenance cost | `senior-engineer`, `quant-engineer` |
| `quant-engineer` | 507 | 255 | lookahead, numerics, the two OHLCV caches, live/replay/backtest parity, reproducible results | `quant-researcher`, `senior-engineer` |
| `senior-engineer` | 528 | 252 | correctness, complexity, test quality, code that reads like its module, behaviour-preserving refactors | `staff-engineer`, `quant-engineer` |

Four things in that table are deliberate and worth knowing before you change a word:

- **`financial-advisor` has one hand-off, not two.** It has exactly one today (`risk-manager`); the spec's "its two hand-offs" does not hold for this seat and none is invented. It keeps "Never personal advice.", shortened from "Educational review of the bot's output, never personal financial advice": the skill body still says so in full (`grep -n "personal" .claude/skills/financial-advisor/SKILL.md`).
- **`quant-engineer` loses "Loads no-lookahead for feature code."** and **`senior-engineer` loses "task-reviewer preloads it."** Both are facts held elsewhere: the `quant-engineer` checklist says "Load the `no-lookahead` skill for any feature, entry-signal or indicator change", and `.claude/agents/task-reviewer.md` lists `senior-engineer` under `skills:`. Neither is a trigger.
- **Wording follows the fire cases.** Each role has three `fire-*` eval prompts under `.claude/skills/<role>/evals/`. The terms those prompts turn on are kept: "the 2% dollar-risk cap" and "correlated exposure" (`risk-manager`), "tax drag of swing turnover" (`financial-advisor`), "tradeability" and "resting orders" (`veteran-trader`), "replay" (`quant-engineer`), "reads like its module", "complexity", "test quality" and "behaviour-preserving" (`senior-engineer`), "point-in-time" and "sector concentration" (`fundamental-analyst`).
- **The values hold no `: `, no double quote and no backslash.** They are quoted now, so an inner colon would be legal; they are still written without one so the line reads the same in every YAML reader.

- [ ] **Step 1: Read the fire cases before judging the wording**

```bash
for f in .claude/skills/{quant-researcher,risk-manager,financial-advisor,veteran-trader,technical-analyst,fundamental-analyst,staff-engineer,quant-engineer,senior-engineer}/evals/fire-*/prompt.md; do echo "## ${f#.claude/skills/}"; tail -n +5 "$f"; done
```

27 one-sentence prompts. For each role, check that the new description in Step 4 would plausibly be picked for its three. You may reword a description if you see a miss, inside these limits: at most 260 characters, the phrase `the <role> seat` present, at least one `Not for ... (<other-role>)`, the word `expert-reviewer` absent, no double quote. If you do, change the value in the Step 4 script's `ROLE` dict (the script is the only place the text lives) and say which role and why in your report. The eval suites themselves are not run here; that is V154-12, after every skill edit in the plan has landed.

- [ ] **Step 2: Write the failing tests**

In `tests/hooks/test_role_skills.py`, three edits and one append. Find each by its text.

Edit 1, the top of the file. Replace

```python
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
```

with

```python
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

```

(`ROOT` is already `Path(__file__).resolve().parents[2]`, the form index contract C2 asks for. The new block ends with a blank line, so `SKILLS_DIR = ROOT / ".claude" / "skills"` follows as before.)

Edit 2, the constant. Replace

```python
CASE_FILES = ("prompt.md", "graders/skill-fired.md")
```

with

```python
CASE_FILES = ("prompt.md", "graders/skill-fired.md")
# Characters of the parsed description value -- the text inside the quotes.
MAX_ROLE_DESCRIPTION = 260
```

Edit 3, a reader next to `_body`. Replace

```python
def _body(name):
    return _text(SKILLS_DIR / name / "SKILL.md").split("---", 2)[2]
```

with

```python
def _body(name):
    return _text(SKILLS_DIR / name / "SKILL.md").split("---", 2)[2]


def _description(name):
    return parse_frontmatter(_text(SKILLS_DIR / name / "SKILL.md"))[0]["description"]
```

Append at the end of the file (two blank lines after the last existing test):

```python
# v154 section 2: a role description is listed in every session and every
# subagent, so it is capped. A missed fire case is fixed by rewording inside
# the cap, never by raising it.
@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_description_fits_the_listing_cap(role):
    value = _description(role)
    assert len(value) <= MAX_ROLE_DESCRIPTION, len(value)


@pytest.mark.parametrize("role", sorted(ROLES))
def test_role_description_keeps_its_seat_and_a_hand_off(role):
    value = _description(role)
    assert f"the {role} seat" in value
    assert "Not for" in value
    assert [other for other in ROLES if other != role and f"({other})" in value]
    # expert-reviewer invokes the skill by name; the clause bought nothing.
    assert "expert-reviewer" not in value
```

The first test is the pin the spec asks for. The second keeps a later reword honest about the three things the spec says a description keeps or drops; it does not pin any wording.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py`

Expected: `18 failed, 50 passed`. All nine cases of `test_role_description_fits_the_listing_cap` fail with a length between 379 and 528, and all nine cases of `test_role_description_keeps_its_seat_and_a_hand_off` fail on `"expert-reviewer" not in value`.

- [ ] **Step 4: Write the nine descriptions**

Save this as `.superpowers/tmp/v154_role_descriptions.py` (git-ignored, not committed). It rewrites only the `description:` line of each of the nine files, keeps each file's line endings, refuses to write anything if any value is over the cap, and reads each value back through the strict parser:

```python
"""One-off for V154-4: write the nine trimmed role descriptions.

Run from the worktree root. Not committed. Rewrites only the `description:`
line of each role skill and keeps the file's line endings.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path("scripts/dev").resolve()))
from skill_frontmatter import parse_frontmatter, quote_value  # noqa: E402

MAX_ROLE_DESCRIPTION = 260
LINE_RE = re.compile(r"^description: (.*?)(\r?)$", re.M)

ROLE = {
    "quant-researcher": "Use when judging, from the quant-researcher seat, whether a statistical claim holds -- ExpR or win-rate lift, a grid winner, a pre-registration, a screen verdict, a badge tier. Not for lookahead bugs (quant-engineer) or tradeability (veteran-trader).",
    "risk-manager": "Use when reviewing a spec, plan or diff from the risk-manager seat -- the 2% dollar-risk cap, position sizing, portfolio heat, correlated exposure, stop placement. Not for stops surviving market noise (veteran-trader) or tax drag (financial-advisor).",
    "financial-advisor": "Use when reviewing a spec, plan, diff or admin screen from the financial-advisor seat -- retail account fit, tax drag of swing turnover, alert frequency, how performance and risk are shown. Never personal advice. Not for caps in code (risk-manager).",
    "veteran-trader": "Use when reviewing a spec, plan, diff or alert from the veteran-trader seat -- tradeability, fills, gaps, liquidity, regime, session timing, resting orders before the open. Not for statistical lift (quant-researcher) or sizing and heat caps (risk-manager).",
    "technical-analyst": "Use when reviewing a spec, plan or diff from the technical-analyst seat -- support/resistance, chart and candlestick patterns, FVG, Fibonacci, trendlines, indicator logic. Not for whether it pays (quant-researcher) or replay plumbing (quant-engineer).",
    "fundamental-analyst": "Use when reviewing a spec, plan or diff from the fundamental-analyst seat -- earnings dates, catalysts, macro events, sector concentration, point-in-time fundamentals, universe membership. Not for patterns (technical-analyst) or heat caps (risk-manager).",
    "staff-engineer": "Use when reviewing a spec, plan or diff from the staff-engineer seat -- swingbot/core package seams, schema migrations, production VM ops, blast radius, maintenance cost. Not for line-level quality (senior-engineer) or backtest plumbing (quant-engineer).",
    "quant-engineer": "Use when reviewing a spec, plan or diff from the quant-engineer seat -- lookahead, numerics, the two OHLCV caches, live/replay/backtest parity, reproducible results. Not for statistical meaning (quant-researcher) or general code quality (senior-engineer).",
    "senior-engineer": "Use when reviewing a diff or plan task from the senior-engineer seat -- correctness, complexity, test quality, code that reads like its module, behaviour-preserving refactors. Not for cross-package design (staff-engineer) or lookahead (quant-engineer).",
}


def write_one(role: str, value: str) -> int:
    path = pathlib.Path(".claude/skills") / role / "SKILL.md"
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    match = LINE_RE.search(text)
    if match is None or match.start() > text.index("\n---", 3):
        sys.exit(f"{path}: no description line inside the frontmatter")
    line = f"description: {quote_value(value)}{match.group(2)}"
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text[:match.start()] + line + text[match.end():])
    read_back = parse_frontmatter(path.read_text(encoding="utf-8"))[0]["description"]
    if read_back != value:
        sys.exit(f"{path}: read back a different value")
    return len(read_back)


def main() -> None:
    too_long = {role: len(value) for role, value in ROLE.items()
                if len(value) > MAX_ROLE_DESCRIPTION}
    if too_long:
        sys.exit(f"over {MAX_ROLE_DESCRIPTION} characters, nothing written: {too_long}")
    for role, value in ROLE.items():
        print(f"{write_one(role, value):4d}  {role}")


if __name__ == "__main__":
    main()
```

Run it from the worktree root:

```bash
python .superpowers/tmp/v154_role_descriptions.py
```

Expected (lengths, then role):

```
 250  quant-researcher
 250  risk-manager
 249  financial-advisor
 256  veteran-trader
 251  technical-analyst
 254  fundamental-analyst
 254  staff-engineer
 255  quant-engineer
 252  senior-engineer
```

If you reworded a value in Step 1 its number differs; it must still be 260 or less, and the script exits without writing when it is not.

- [ ] **Step 5: Check the edit is one line in each of nine files**

```bash
git diff --numstat -- .claude/skills | awk '{print $1, $2}' | sort | uniq -c
git diff -- .claude/skills | grep -c "^+description: \""
git diff -- .claude/skills | grep "^+description" | grep -c "expert-reviewer"
```

Expected: `9 1 1`, then `9`, then `0`.

- [ ] **Step 6: Regenerate the Codex mirror**

```bash
python scripts/dev/sync_codex.py
git diff --numstat -- .agents .codex | awk '{print $1, $2}' | sort | uniq -c
```

Expected: `Codex mirror is current.`, then `9 1 1` (the nine generated role copies; no `.toml`).

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_role_skills.py tests/hooks/test_skill_shape.py tests/hooks/test_codex_mirror.py`

Expected: green, `0 failed` (`test_role_skills.py` is `68 passed`, `test_skill_shape.py` `104 passed`, `test_codex_mirror.py` `12 passed`). `test_skill_shape.py::test_every_skill_declares_name_and_description` still holds: every new value is far above its 40-character floor.

- [ ] **Step 8: Complexity**

Run: `python -m radon cc -s -n C tests/hooks/test_role_skills.py`

Expected: no output.

- [ ] **Step 9: Commit**

```bash
git add tests/hooks/test_role_skills.py .claude/skills .agents .codex
git status --short | grep -v "^M  \(\.claude/skills/[a-z-]*/SKILL\.md\|\.agents/skills/[a-z-]*/SKILL\.md\|tests/hooks/test_role_skills\.py\)$"
git commit -m "fix(v154): nine role descriptions trimmed to the 260-character cap and pinned; expert-reviewer clause dropped"
```

Expected from the middle command: no output. In your report, give the nine final lengths and name any description you reworded in Step 1, so V154-12 knows which text the eval suites are judging.

