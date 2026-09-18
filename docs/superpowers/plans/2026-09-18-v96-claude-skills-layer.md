Bump: none
Edge: none (integrity)

# v96 — The skills layer: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-18-v96-claude-skills-layer-design.md`

**Goal:** Turn this repo's 1,724 lines of read-before-you-work prose into a layer that fires — eleven `.claude/skills/` loaders plus three `guardrails.py` deny rules — without creating a third source of truth.

**Architecture:** Two mechanisms, chosen per item. Anything checkable from a tool's input alone becomes a **pure** rule in the existing `guardrails.py` (which denies). Everything requiring judgement becomes a thin `SKILL.md` loader that reads its authority out of `docs/claude/` and never restates it. A new `tests/hooks/test_skill_shape.py` makes the loader contract mechanical rather than aspirational, so every skill task has a real red-green cycle.

**Tech Stack:** Python 3.11 (hook + tests), pytest, Markdown with YAML frontmatter. No new dependencies. No bot or UI code is touched.

## Global Constraints

Copied from the spec; every task's requirements implicitly include these.

- **`guardrails.py`'s `evaluate()` reads no files and spawns no subprocesses.** `os.path.getsize` and `os.getcwd()` remain the only OS calls. A check needing the filesystem or git belongs in a skill, not the hook.
- **Every rule fails open.** Anything unrecognised or malformed returns `None` — silent allow. A guardrail that blocks legitimate work costs more than the habit it prevents.
- **No `SKILL.md` restates a threshold, table, constant or acceptance clause owned by `docs/claude/`.** It cites the file and sends the reader there.
- **New `SKILL.md` files are ≤80 lines.** `gate` (89) and `task-brief` (124) predate this and are grandfathered by name.
- **Tier 2 skills carry `disable-model-invocation: true`.** Tier 1 and Tier 3 do not.
- **Every Tier 1 and Tier 3 skill carries a `## Trigger table`** with at least three should-fire and three should-not-fire entries.
- **Per-task verification is the narrow run** — `python scripts/dev/testrun.py file tests/hooks/<file>.py` (~7s). The full suite runs **once**, as Task S19.
- Commit after every task. Commit subjects use the repo's `type(scope): subject` form.

## Parallelisation

- **Sequential: Phase 0 before everything.** S1 defines the shape contract every later task is tested against.
- **Sequential throughout Phase 1.** S3, S4 and S5 are unrelated in subject matter but all three edit `guardrails.py` and `tests/hooks/test_guardrails.py`. The disjoint-files test is about files, not topics — do not dispatch them concurrently.
- **Sequential: Phase 1 before Phase 2.** Tier 1 deny messages name skills that Phase 2 creates.
- **Group B (parallel), Phase 2:** S6, S7, S8, S9 — one new directory each, no shared file, no contract dependency.
- **Group C (parallel), Phase 3:** S10, S11, S12 — one new directory each.
- **Group D (parallel), Phase 4:** S13, S14, S15, S16 — one new directory each.
- **Sequential: S17 and S18 last**, after the final skill lands — both enumerate what shipped.

---

# Phase 0 — The shape contract

### Task S1: The skill shape gate

**Files:**
- Create: `tests/hooks/test_skill_shape.py`

**Interfaces:**
- Produces: `SKILLS_DIR`, `GRANDFATHERED`, `MAX_SKILL_LINES`, `TIER_1_AND_3`, `TIER_2`, and `_read_skill(name) -> tuple[dict, str]` — every later skill task adds its own name to `TIER_1_AND_3` (model-invocable) or `TIER_2` (slash-only) and is gated by these assertions.

- [ ] **Step 1: Write the failing test**

```python
"""Shape contract for .claude/skills/*/SKILL.md -- v96.

Keeps the skills layer from becoming a third source of truth. The budget and
the no-threshold rule are the spec's, not pytest's; this file only makes them
mechanical. See docs/superpowers/specs/2026-09-18-v96-claude-skills-layer-design.md
"""
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"

# Predate v96's 80-line budget. Not exemptions to copy -- the list never grows.
GRANDFATHERED = {"gate", "task-brief"}

MAX_SKILL_LINES = 80

# Tier 1 and Tier 3 are model-invocable, so they carry a trigger table.
# Tier 2 is slash-only and carries disable-model-invocation instead.
TIER_1_AND_3 = set()          # each skill task appends its own name
TIER_2 = set()                # each ritual task appends its own name

# A bare threshold in a SKILL.md is content that belongs in docs/claude/.
# Dates, version numbers and step numbers are not thresholds.
_THRESHOLD_RE = re.compile(
    r"(?<![\w.-])(?:>=|<=|>|<|=)\s*\d+(?:\.\d+)?%?|"
    r"\b\d+(?:\.\d+)?\s*(?:pp|R)\b"
)


def _skill_dirs():
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


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


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_skill_declares_name_and_description(path):
    meta, _ = _read_skill(path.name)
    assert meta.get("name") == path.name
    assert len(meta.get("description", "")) >= 40


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_new_skills_stay_within_the_line_budget(path):
    if path.name in GRANDFATHERED:
        pytest.skip("predates the v96 budget")
    lines = (path / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_SKILL_LINES


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_new_skills_restate_no_thresholds(path):
    if path.name in GRANDFATHERED:
        pytest.skip("predates the v96 no-restatement rule")
    _, body = _read_skill(path.name)
    hits = _THRESHOLD_RE.findall(body)
    assert not hits, f"{path.name} restates {hits}; cite docs/claude/ instead"


def test_model_invocable_skills_carry_a_trigger_table():
    for name in sorted(TIER_1_AND_3):
        meta, body = _read_skill(name)
        assert "disable-model-invocation" not in meta
        assert "## Trigger table" in body
        assert body.count("Should fire:") >= 3
        assert body.count("Should not fire:") >= 3


def test_ritual_skills_are_slash_only():
    for name in sorted(TIER_2):
        meta, _ = _read_skill(name)
        assert meta.get("disable-model-invocation") == "true"
```

- [ ] **Step 2: Run it and read what fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`

Expected: the two existing skills pass `test_every_skill_declares_name_and_description` and **skip** the budget and threshold tests. The two set-driven tests pass vacuously (empty sets). If `gate` or `task-brief` fails the name/description assertion, fix the assertion — not those files.

- [ ] **Step 3: Commit**

```bash
git add tests/hooks/test_skill_shape.py
git commit -m "test(skills): shape contract for .claude/skills SKILL.md files"
```

---

### Task S2: Spike — can `claude plugin eval` target a repo-local skills dir?

**Files:**
- Modify: `docs/superpowers/specs/2026-09-18-v96-claude-skills-layer-design.md` (§7 only)

Timebox: 20 minutes. The spec deliberately does not assume the answer.

- [ ] **Step 1: Find out**

```powershell
claude plugin eval --help
```

Look for an argument that accepts a directory of skills rather than a packaged plugin manifest. If one exists, write a throwaway two-case eval against `.claude/skills/gate` and run it.

- [ ] **Step 2: Record the answer in the spec, either way**

Replace §7's "That is unverified" paragraph with what you found, in one of two forms:

- **Works:** name the exact command, and note that the trigger tables in each skill become the eval corpus. Add a follow-up task to this plan's Phase 4 wiring them up.
- **Does not work:** say so and say why in one clause. The trigger tables stay a documented manual check performed at review. **This is a complete, acceptable outcome** — do not build a bespoke eval harness to rescue it; that is a new hypothesis needing its own spec.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-18-v96-claude-skills-layer-design.md
git commit -m "docs(v96): record whether claude plugin eval can target repo-local skills"
```

---

# Phase 1 — Hook rules

Sequential. All three tasks edit the same two files.

### Task S3: `branch-safety` — the repo's one unenforced hard rule

**Files:**
- Modify: `.claude/hooks/guardrails.py`
- Test: `tests/hooks/test_guardrails.py`

**Interfaces:**
- Produces: `_rule_protected_branch_delete(ti) -> dict | None`, registered on `"Bash"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/hooks/test_guardrails.py`:

```python
def _bash(cmd):
    return evaluate({"tool_name": "Bash", "tool_input": {"command": cmd}})


def test_deleting_a_backup_branch_is_denied():
    out = _bash("git branch -D 2026-08-16-v36-backup")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "git-safety.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_deleting_a_stable_branch_is_denied():
    assert _bash("git branch -d stable-1.9") is not None


def test_remote_deleting_a_backup_branch_is_denied():
    assert _bash("git push origin --delete backup-pre-v67") is not None


def test_colon_refspec_delete_of_a_backup_branch_is_denied():
    assert _bash("git push origin :backup-pre-v67") is not None


def test_force_pushing_a_backup_branch_is_denied():
    assert _bash("git push --force origin backup-pre-v67") is not None


def test_deleting_an_ordinary_branch_is_allowed():
    assert _bash("git branch -D 2026-09-10-v81-execution-feed") is None


def test_merely_listing_backup_branches_is_allowed():
    assert _bash("git branch --list '*backup*'") is None


def test_branch_rule_fails_open_on_a_non_string_command():
    assert evaluate({"tool_name": "Bash", "tool_input": {"command": None}}) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: the six deny tests FAIL (`evaluate` returns `None`); the two allow tests already pass.

- [ ] **Step 3: Implement the rule**

Add to `.claude/hooks/guardrails.py`, above the `_RULES` table:

```python
# CLAUDE.md marks this a hard rule with no exceptions, and it was the only such
# rule with no mechanical enforcement at all before v96.
_BRANCH_DESTRUCTIVE_RE = re.compile(
    r"git\s+branch\s+(?:[^|;&]*\s)?(?:-[a-zA-Z]*[dD][a-zA-Z]*|--delete)(?=\s|$)"
    r"|git\s+push\s+[^|;&]*(?:--delete(?=\s|$)|\s:\S)"
    r"|git\s+push\s+[^|;&]*(?:--force(?:-with-lease)?|-f)(?=\s|$)"
    r"|git\s+update-ref\s+-d(?=\s|$)"
)
_PROTECTED_REF_RE = re.compile(r"backup|(?:^|[\s/:])stable-", re.IGNORECASE)


def _rule_protected_branch_delete(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        return None
    if not _BRANCH_DESTRUCTIVE_RE.search(cmd):
        return None
    if not _PROTECTED_REF_RE.search(cmd):
        return None
    return _deny(
        "Hard rule, no exceptions: a branch whose name contains `backup`, and any "
        "`stable-*` branch, is off limits to every destructive git command -- "
        "including force push. Run `git rev-list --count main..<branch>` first; "
        "non-zero means stop. Then ask the human partner. Do not decide this one. "
        "Evidence and the full checklist: docs/claude/git-safety.md."
    )
```

Register it **first** on `Bash` so the deny precedes the warn rules:

```python
    "Bash": [_rule_protected_branch_delete, _rule_recursive_grep_from_root,
             _rule_bare_pytest, _rule_cat_big_doc],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: PASS, and the pre-existing 44 cases still pass.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(guardrails): deny destructive git commands against backup and stable-* branches"
```

---

### Task S4: `closed-preregistration` — a closed knob back in a grid

**Files:**
- Modify: `.claude/hooks/guardrails.py`
- Test: `tests/hooks/test_guardrails.py`

**Interfaces:**
- Consumes: `_bash(cmd)` from Task S3.
- Produces: `CLOSED_PREREGISTRATION_KNOBS` (a `frozenset`) and `_rule_closed_preregistration(ti) -> dict | None`, registered on `"Bash"` after `_rule_protected_branch_delete`.

Matching is on **knob tokens, not strategy names** — the table closes specific mechanisms, and several rows name a strategy whose other hypotheses stay open.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_closed_knob_in_a_grid_is_denied():
    out = _bash('python scripts/backtest/tune_strategy.py --strategy "RSI" '
                '--grid DEAD_CAT_BOUNCE_VETO=true,false')
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "backtest-methodology.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_closed_knob_as_an_env_assignment_is_denied():
    assert _bash("EARNINGS_BLACKOUT_SESSIONS=3 python scripts/backtest/run_backtest_range.py --train") is not None


def test_an_open_strategy_name_alone_is_allowed():
    assert _bash('python scripts/backtest/tune_strategy.py --strategy "Break & Retest" '
                 '--grid min_pullback_atr=0.5,1.0') is None


def test_a_closed_knob_outside_a_backtest_command_is_allowed():
    assert _bash("grep -n DEAD_CAT_BOUNCE_VETO swingbot/config.py") is None


def test_closed_preregistration_rule_fails_open_on_a_missing_command():
    assert evaluate({"tool_name": "Bash", "tool_input": {}}) is None


def test_every_closed_knob_constant_appears_in_the_methodology_doc():
    doc = (_REPO_ROOT / "docs" / "claude" / "backtest-methodology.md").read_text(encoding="utf-8")
    missing = [k for k in guardrails.CLOSED_PREREGISTRATION_KNOBS if k not in doc]
    assert not missing, f"constant lists knobs the doc does not: {missing}"
    assert len(guardrails.CLOSED_PREREGISTRATION_KNOBS) >= 8


def test_every_all_caps_knob_in_the_closed_table_is_in_the_constant():
    """The drift direction that actually bites: a new closed row lands in the
    doc and the hook never learns about it. Lower-case knobs
    (min_level_touches, confirm_bars) are out of reach of this half -- the
    forward assertion above is their only cover."""
    doc = (_REPO_ROOT / "docs" / "claude" / "backtest-methodology.md").read_text(encoding="utf-8")
    table = doc.split("### Closed pre-registrations", 1)[1]
    found = set(re.findall(r"`([A-Z][A-Z0-9_]{4,})`", table))
    missing = found - set(guardrails.CLOSED_PREREGISTRATION_KNOBS)
    assert not missing, (
        f"backtest-methodology.md closes {sorted(missing)} but guardrails.py does "
        "not list them. Add them to CLOSED_PREREGISTRATION_KNOBS."
    )
```

`test_guardrails.py` already defines `_REPO_ROOT` — reuse it. It does **not** import `re` (its current imports are `importlib.util`, `json`, `os`, `pathlib`), so add `import re` at the top in this task.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: FAIL with `AttributeError: module 'guardrails' has no attribute 'CLOSED_PREREGISTRATION_KNOBS'`.

- [ ] **Step 3: Implement the rule**

```python
# Knobs whose pre-registration is closed (docs/claude/backtest-methodology.md,
# "Closed pre-registrations"). Deliberately NOT strategy names: the table closes
# mechanisms, and a strategy closed for one gate stays open for another.
# tests/hooks/test_guardrails.py asserts this list against the doc in both
# directions -- add a row there and the suite fails until this catches up.
CLOSED_PREREGISTRATION_KNOBS = frozenset({
    "REGIME_ALLOW",
    "REGIME_GATES_ENABLED",
    "DATA_DRIVEN_STOPS_ENABLED",
    "RS_GATE",
    "RS_LEADER_PERCENTILE",
    "RS_LAGGARD_PERCENTILE",
    "AVWAP_LEVELS_ENABLED",
    "LEVEL_TOUCH_STRENGTH",
    "EFFECTIVE_CONFLUENCE_ENABLED",
    "DEAD_CAT_BOUNCE_VETO",
    "EARNINGS_BLACKOUT_SESSIONS",
    "FIB_TARGET_1_0_EXTENSION",
    "COHORT_POOR",
})
_BACKTEST_SCRIPT_RE = re.compile(r"(?:tune_strategy|run_backtest_range)\.py")


def _rule_closed_preregistration(ti: dict):
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not _BACKTEST_SCRIPT_RE.search(cmd):
        return None
    hit = next((k for k in sorted(CLOSED_PREREGISTRATION_KNOBS) if k in cmd), None)
    if hit is None:
        return None
    return _deny(
        f"`{hit}` has a CLOSED pre-registration -- see the table in "
        "docs/claude/backtest-methodology.md. Re-running it does not produce a "
        "new result; it spends a shot the repo already spent and invites fitting "
        "the answer to the knob. A genuinely new mechanism over the same knob is "
        "a NEW pre-registration and needs its own spec. If this really is that, "
        "say so to the human partner and let them authorise it -- do not clear "
        "this yourself."
    )
```

Register after the branch rule:

```python
    "Bash": [_rule_protected_branch_delete, _rule_closed_preregistration,
             _rule_recursive_grep_from_root, _rule_bare_pytest, _rule_cat_big_doc],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: PASS. If `test_every_all_caps_knob_in_the_closed_table_is_in_the_constant` fails, the doc closes a knob the constant is missing — **add it to the constant.** Do not loosen the regex to make it green.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(guardrails): deny backtest runs that put a closed pre-registration knob back in a grid"
```

---

### Task S5: `plan-doc-shape` — keep plans greppable

**Files:**
- Modify: `.claude/hooks/guardrails.py`
- Test: `tests/hooks/test_guardrails.py`

**Interfaces:**
- Produces: `_rule_plan_doc_shape(ti) -> dict | None`, registered on `"Write"`.

`## Phase` instead of `# Phase` makes a plan return **zero** for `grep -n "^# Phase"` — the exact failure `document-conventions.md` records for v24 and v25.

- [ ] **Step 1: Write the failing tests**

```python
def _write(path, content=""):
    return evaluate({"tool_name": "Write",
                     "tool_input": {"file_path": path, "content": content}})


_GOOD_PLAN = "docs/superpowers/plans/2026-09-18-v96-claude-skills-layer.md"


def test_a_misnumbered_plan_filename_is_denied():
    out = _write("docs/superpowers/plans/skills-layer.md", "# Phase 0 - x\n")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "document-conventions.md" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_two_hash_phase_heading_is_denied():
    assert _write(_GOOD_PLAN, "## Phase 0 - conventions\n") is not None


def test_a_conforming_plan_write_is_allowed():
    assert _write(_GOOD_PLAN, "# Phase 0 - conventions\n\n### Task S1: x\n") is None


def test_a_split_part_filename_is_allowed():
    assert _write("docs/superpowers/plans/2026-08-29-v67-json-to-postgres_1a-foundation-core.md",
                  "# Phase 1 - x\n") is None


def test_a_closed_out_plan_under_implemented_is_allowed():
    assert _write("docs/superpowers/plans/implemented/2026-09-16-v92-exit-quality-harvest.md",
                  "# Phase 1 - x\n") is None


def test_writes_outside_the_doc_dirs_are_untouched():
    assert _write("swingbot/config.py", "## Phase 0\n") is None


def test_plan_doc_shape_fails_open_on_a_non_string_path():
    assert _write(None, "## Phase 0\n") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: the two deny tests FAIL; the five allow tests already pass.

- [ ] **Step 3: Implement the rule**

```python
# docs/superpowers/{specs,plans}/ have two unconditional shape rules
# (document-conventions.md): the vN-numbered filename, and `# Phase` with ONE
# hash so `grep -n "^# Phase"` can find it. v24 and v25 shipped with two and
# were invisible to the tool that exists to keep plans out of context.
_DOC_DIR_RE = re.compile(r"docs/superpowers/(?:specs|plans)/", re.IGNORECASE)
_DOC_NAME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}-v\d+-[a-z0-9][a-z0-9-]*"
    r"(?:_[0-9a-z]+(?:-[a-z0-9-]+)?)?\.md$"
)
_TWO_HASH_PHASE_RE = re.compile(r"^##\s+Phase\s", re.MULTILINE)


def _rule_plan_doc_shape(ti: dict):
    path = ti.get("file_path")
    if not isinstance(path, str):
        return None
    norm = path.replace("\\", "/")
    if not _DOC_DIR_RE.search(norm):
        return None
    name = norm.rsplit("/", 1)[-1]
    if not _DOC_NAME_RE.match(name):
        return _deny(
            f"`{name}` does not match YYYY-MM-DD-vN-<name>.md. Every spec and plan "
            "is numbered at creation from one repo-wide counter, recomputed "
            "immediately before the commit. See docs/claude/document-conventions.md."
        )
    content = ti.get("content")
    if isinstance(content, str) and _TWO_HASH_PHASE_RE.search(content):
        return _deny(
            "`## Phase` uses two hashes. `CLAUDE.md` documents "
            '`grep -n "^# Phase"` as the way to orient in a plan, so a two-hash '
            "heading returns zero and the plan is invisible to the tooling that "
            "keeps it out of context. Use one hash, however wrong it looks beside "
            "the `##` sections around it. See docs/claude/document-conventions.md."
        )
    return None
```

Register it ahead of the existing worktree rule on `Write`:

```python
    "Write": [_rule_worktree_write, _rule_plan_doc_shape],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/guardrails.py tests/hooks/test_guardrails.py
git commit -m "feat(guardrails): deny spec/plan writes that break the naming or phase-heading shape"
```

---

# Phase 2 — Tier 1 integrity gates

Group B: S6, S7, S8, S9 are parallel-safe — one new directory each.

Each task in this phase follows the same five steps. They are written out per task rather than cross-referenced, because a subagent sees only its own task.

### Task S6: `backtest-gate`

**Files:**
- Create: `.claude/skills/backtest-gate/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"backtest-gate"` to `TIER_1_AND_3`)

**Interfaces:**
- Consumes: `TIER_1_AND_3` from Task S1; `_rule_closed_preregistration`'s deny text from Task S4 (the skill explains what the hook denies).

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

In `tests/hooks/test_skill_shape.py`: `TIER_1_AND_3 = {"backtest-gate"}`

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — `FileNotFoundError`, the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, **verbatim** — this string is the deliverable, not prose around it:

```
Use when about to run, re-run, or interpret any backtest, grid, walk-forward, fold or validation script (scripts/backtest/run_backtest_range.py, scripts/backtest/tune_strategy.py, --train, --validation, --grid, --exit-model, --scale-out) -- BEFORE the command, not after. Also when a result is about to be called a pass. Not for reading a backtest result already in context, and not for the test suite (use /gate).
```

Body, in this order:

1. **`## Step 1 — Read the authority.** `docs/claude/backtest-methodology.md` — the six-clause acceptance gate, the four-stage funnel, the TRAIN/VALIDATION windows, the frozen constants, and the closed pre-registration table. Read it before anything else. Do not restate its numbers here.
2. **`## Step 2 — Is this shot already spent?** Check the closed table by name. `guardrails.py` denies the ALL-CAPS knobs mechanically, but it cannot see a lower-case knob or a strategy-plus-mechanism pair. The hook is a floor, not the check.
3. **`## Step 3 — Which stage is this?** Name the funnel stage out loud before running. A VALIDATION run with no registered TRAIN result is not a validation.
4. **`## Step 4 — Run it off this context.** Anything past ~2 minutes goes to the `backtest-runner` subagent, chunked per strategy, with flushed per-unit progress; past 15 minutes that must resolve to a percent figure in a log deleted on completion.
5. **`## The gate`** — pass means every pre-registered clause cleared, on the pre-registered N, in the pre-registered window. A clause relaxed after seeing the result is a new hypothesis.
6. **`## Known wrong turns`** — a table with at least: *"N came in under the floor, so widen the window"* → that is a new pre-registration; *"the direction is right, just not significant"* → a direction is not a result; *"re-run to confirm"* → confirming is what VALIDATION was for.
7. **`## Trigger table`** — three+ should-fire (about to run `tune_strategy.py`; about to say a grid cell passed; asked whether a flag should ship default-on) and three+ should-not-fire (reading a `results/*.md` already open; running the pytest suite; asking what a horizon means).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS. If the threshold test fails, you restated a number that `backtest-methodology.md` owns — delete it and cite the doc.

- [ ] **Step 4: Check the description against its own negatives**

Read the four should-not-fire entries and ask, for each, whether the description as written would match it. If one would, tighten the description — not the trigger table.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/backtest-gate/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): backtest-gate -- the acceptance gate fires before the run, not after"
```

---

### Task S7: `no-lookahead`

**Files:**
- Create: `.claude/skills/no-lookahead/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"no-lookahead"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when editing or reviewing entry-signal, feature or indicator computation under swingbot/core/market/, swingbot/core/edge/, swingbot/core/scanning/ or swingbot/core/planning/ -- anything that decides what a bar knew at the time. Catches lookahead bias, which inflates every downstream backtest silently. Not for chart rendering, embeds, admin UI or persistence code.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/architecture.md` — the NO-LOOKAHEAD rule and the entry-signal single source. Then `docs/claude/known-traps.md` for the two OHLCV caches, which are where lookahead usually enters.
2. **`## Step 2 — Name the bar.** For the value you are computing, state which bar index it is allowed to see and which it is not. If you cannot say it in one sentence, the function is doing two things.
3. **`## Step 3 — Trace the shifts.** Every rolling, `shift`, `resample` and merge on a datetime index is a place a future value leaks backwards. Check each one against Step 2's sentence.
4. **`## Step 4 — Prove it with a truncation test.** Compute the feature over the full series, then over the series truncated at bar *k*. The value at bar *k* must be identical. A feature that changes when the future is removed was reading it.
5. **`## The gate`** — the truncation test exists, is committed, and passes. Reasoning about the code is not the gate.
6. **`## Known wrong turns`** — *"it is only the close of the same bar"* → the scanner runs intrabar; *"the backtest agrees with live"* → both can read the same leak; *"centred window, but small"* → centred is lookahead by construction.
7. **`## Trigger table`** — three+ should-fire (adding an indicator; changing a resample rule; reviewing an entry filter) and three+ should-not-fire (editing `embeds.py`; changing a Discord message; renaming a config field).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

For each should-not-fire entry, ask whether the description would match it. Tighten the description if so.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/no-lookahead/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): no-lookahead -- truncation test before an indicator ships"
```

---

### Task S8: `pooled-numbers`

**Files:**
- Create: `.claude/skills/pooled-numbers/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"pooled-numbers"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when about to state a pooled expectancy, ExpR, win rate, sample size N, R-multiple or strategy badge tier -- in a message, a spec, a plan or a commit. Requires re-deriving the figure from the live book rather than quoting one from a document. Not for a figure the user just supplied, and not for a number being read back from a file open in this context.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/edge-priorities.md` for what pooled means here and why expectancy leads; `docs/claude/backtest-methodology.md` for which window a figure belongs to.
2. **`## Step 2 — Every pooled figure in a document is stale until re-derived.** The 2026-09-10 badge refresh demoted three strategies and invalidated every pooled figure quoted against the old registry. A number in a spec records what was true when it was written.
3. **`## Step 3 — Re-derive, and say from what.** Name the source, the window and the N alongside the figure. A pooled number without its N is not a claim, it is a mood.
4. **`## Step 4 — Say which dimensions have no N.** Slicing the book far enough produces confident nonsense. If a dimension's N is too small to support the claim, say so in the same sentence as the figure.
5. **`## The gate`** — the figure, its N, its window and its source all appear together, or the figure does not appear.
6. **`## Known wrong turns`** — *"the spec says ExpR is X"* → the spec says what it was; *"roughly, from memory"* → a remembered R-multiple is a fabricated one; *"the badge says VALIDATED"* → check the registry's `run_date`.
7. **`## Trigger table`** — three+ should-fire (summarising performance; writing an `Edge:` header's justification; answering "is this strategy working") and three+ should-not-fire (the user quotes a number and asks a follow-up; reading a `results/` file aloud; discussing a hypothetical).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS. This skill is the likeliest to trip the threshold test — it must contain **no** example figures.

- [ ] **Step 4: Check the description against its own negatives**

For each should-not-fire entry, ask whether the description would match it. Tighten if so.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/pooled-numbers/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): pooled-numbers -- re-derive before quoting, with N and window"
```

---

### Task S9: `mirror-prod`

**Files:**
- Create: `.claude/skills/mirror-prod/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"mirror-prod"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when about to change anything on the Hetzner production VM (167.233.26.185, scripts/ops/ssh-hetzner.sh, docker compose restart, editing .env, a hotfix applied live). Production changes must be mirrored back into this repo and committed before the task counts as done. Not for read-only production commands -- logs, docker ps, status checks.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/working-conventions.md` for what "mirrored" means and why; `docs/deploy/DEPLOY_HETZNER.md` for the VM itself.
2. **`## Step 2 — Production is never this machine.** Confirm you are targeting the VM deliberately, not by habit.
3. **`## Step 3 — Write down the change before making it.** The exact file, the exact edit. A live fix you cannot describe is a live fix you cannot mirror.
4. **`## Step 4 — Mirror it back, same session.** Apply the identical change to the repo, run the narrow test for the file you touched, and commit. A `.env` change mirrors into the schema in `swingbot/config.py` and the deploy doc, not just the VM.
5. **`## The gate`** — `git log` shows the mirroring commit. Until it does, the task is open, regardless of production being healthy.
6. **`## Known wrong turns`** — *"it is a one-line config tweak"* → those are exactly the ones that vanish; *"I will mirror it after the next deploy"* → the next deploy overwrites it; *"production is fine now"* → production being fine is not the deliverable.
7. **`## Trigger table`** — three+ should-fire (about to SSH and edit; restarting a container after a change; hand-patching a file on the VM) and three+ should-not-fire (tailing logs; `docker ps`; reading a container's env to answer a question).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

Read-only production commands are the whole false-positive surface here. Confirm the description's negative clause covers `docker logs`, `docker ps` and `tail`.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/mirror-prod/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): mirror-prod -- a live fix is not done until it is committed here"
```

---

# Phase 3 — Tier 2 rituals

Group C: S10, S11, S12 are parallel-safe. All three are slash-only, so they carry `disable-model-invocation: true` and go into `TIER_2`, not `TIER_1_AND_3`.

### Task S10: `/close-out`

**Files:**
- Create: `.claude/skills/close-out/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"close-out"` to `TIER_2`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter: `disable-model-invocation: true`, plus a description naming it as the plan close-out ritual.

Body — an ordered, executable checklist, with the reasoning left in the docs:

1. **`## Step 1 — Read the authority.** `docs/claude/document-lifecycle.md` and `docs/claude/working-conventions.md`.
2. **`## Step 2 — Resolve the bump from disk.** Read `VERSION.json`. Never a plan header, never memory, never an earlier task's note. Increment only the line named by the plan's `Bump:`; leave the other untouched. `Bump: none` means no release commit at all.
3. **`## Step 3 — Stamp and regenerate.** Set that line's `*_updated` to now in the existing format, then run `python scripts/dev/build_version_matrix.py` and commit the regenerated history **in the same commit as the bump**. The local gate runs before the bump, so nothing else catches a missed regeneration.
4. **`## Step 4 — Amend a wrong prediction, do not hide it.** If the plan predicted a level or an `Edge:` the work did not deliver, amend the header in this commit and say why in one clause.
5. **`## Step 5 — Move the document.** `implemented/` for work that reached `main`; `no-lift/` for a plan whose code deliberately did not.
6. **`## Step 6 — Remove the worktree.** Per `document-lifecycle.md`'s naming. Never delete a branch containing `backup` — `guardrails.py` denies it, and that deny is correct.
7. **`## The gate`** — `VERSION.json`, the regenerated history and the moved plan are in the log; the worktree is gone; no full-suite run happens after a clean merge.

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS, including `test_ritual_skills_are_slash_only`.

- [ ] **Step 4: Dry-check against the last real close-out**

Read `git log --oneline -8`. The v96 close-out sequence in this skill must match the shape of the `release(bot): 1.9.4` / `chore(bot): regenerate version_history.json` pair. If it does not, the skill is wrong, not the history.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/close-out/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): /close-out -- resolve the bump from disk and regenerate history in one commit"
```

---

### Task S11: `/new-doc`

**Files:**
- Create: `.claude/skills/new-doc/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"new-doc"` to `TIER_2`)

This skill carries the version-collision check that deliberately did **not** become a hook rule — it needs the filesystem and `git log`, which `evaluate()` may not touch.

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter: `disable-model-invocation: true`, plus a description naming it as spec/plan creation.

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/document-conventions.md`.
2. **`## Step 2 — Compute the number immediately before the commit**, with the canonical command — `find` over both directories (closed docs live one level down) plus `git log --oneline --all`, because an informal `vN` in a commit subject with no doc file has burned a number before. Not once at the start of the session: concurrent sessions share this counter.
3. **`## Step 3 — Write the header block.** `Version:` on a spec only; `Bump:` as a level with no numbers in it; `Edge:` as one of the four values. A plan built from an already-numbered spec reuses that spec's number and links back with `**Spec:**`.
4. **`## Step 4 — Keep it addressable.** `### Task <id>:` and `# Phase N —` with one hash. `guardrails.py` denies a two-hash phase heading and a non-conforming filename; treat both denies as correct.
5. **`## Step 5 — Respect the length cap.** Over the cap, split into `_N` parts sharing the parent's number. Split, never compress — a compressed task is a task that gets re-derived wrong later.
6. **`## Step 6 — Add `## Parallelisation`.** Name the groups and, more importantly, the reason on every sequential edge. Be honest about a group of one.
7. **`## Step 7 — Commit on `main`.** Specs and plans are never written on a branch; branch only to implement one. If the number collided while you were writing, rename **before** your commit, never after one has landed.
8. **`## The gate`** — the file name matches the convention, the counter was recomputed in the same minute as the commit, and the plan ends with a single full-suite verification task.

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Verify the counter command works verbatim**

Run the command exactly as the skill writes it. It must print a single `vN`. A command that needs adjusting to run is a command that will be adjusted wrongly at 2am.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/new-doc/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): /new-doc -- recompute the repo-wide counter immediately before the commit"
```

---

### Task S12: `/deploy`

**Files:**
- Create: `.claude/skills/deploy/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"deploy"` to `TIER_2`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Read `docs/deploy/DEPLOY_HETZNER.md` and `docs/deploy/DOCKER.md` first; the skill is the executable sequence, the docs stay the authority.

Frontmatter: `disable-model-invocation: true`.

Body:

1. **`## Step 1 — Read the authority.** `docs/deploy/DEPLOY_HETZNER.md`, then `docs/deploy/DOCKER.md` for the two-containers-off-one-image shape.
2. **`## Step 2 — Decide: config or code.** A `.env` change hot-reloads via SIGHUP. Code needs a rebuild. Restarting for a config change and reloading for a code change are the two ways this goes wrong.
3. **`## Step 3 — Build and deploy**, with the exact commands from the deploy doc, including the Node stage that builds the Angular SPA.
4. **`## Step 4 — Verify on the VM**, not locally: both containers up, the bot's scan loop alive, the admin API answering.
5. **`## Step 5 — Mirror anything you changed by hand.** Invoke `mirror-prod`. A deploy that included a live edit is not finished at the deploy.
6. **`## The gate`** — both containers healthy, and nothing was changed on the VM that is not in `git log`.

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check every command against the deploy doc**

Each command in the skill must appear in, or be derivable from, `DEPLOY_HETZNER.md`. Any that is not is either an invention or a documentation gap — if the latter, fix the doc in this task.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/deploy/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): /deploy -- the Hetzner sequence, with the config-vs-code fork made explicit"
```

---

# Phase 4 — Tier 3 briefings and close

Group D: S13–S16 are parallel-safe. **This phase is built to be truncated** — the spec's committed scope ends at S13, and S14–S16 may be dropped without leaving anything half-finished. S17–S19 run regardless.

### Task S13: `edge-module`

**Files:**
- Create: `.claude/skills/edge-module/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"edge-module"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when adding or changing a strategy or edge module under swingbot/core/edge/ or swingbot/core/market/strategy_types.py -- registry entry, badge tier, entry-signal wiring, or where it plugs into the scan pipeline. Not for tuning an existing strategy's parameters (use backtest-gate) and not for changing how a strategy is displayed.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/architecture.md` — the module map, the entry-signal single source, the badges and the registry.
2. **`## Step 2 — Verify every symbol before you use it.** Plans and briefs invent symbols here routinely. `git grep -n "def <symbol>" -- "swingbot/**/*.py"`, or dispatch `symbol-verifier`.
3. **`## Step 3 — Register once.** A strategy that computes but is not registered is invisible; one registered twice scores twice.
4. **`## Step 4 — A new module ships WEAK.** A badge tier is a measured claim, not a default. Earning a better one means a pre-registration — invoke `backtest-gate`.
5. **`## Step 5 — Check the entry signal has one source.** Two paths computing the same entry is how live and backtest diverge.
6. **`## Known wrong turns`** — *"it works in the backtest so it is wired"* → the replay harness never calls the scan engine; *"I will badge it after we see live results"* → live results are not a pre-registration.
7. **`## Trigger table`** — three+ should-fire (adding a strategy; changing a registry entry; wiring a new edge module) and three+ should-not-fire (renaming a chart label; changing an alert embed; tuning an existing parameter).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

Parameter tuning is the overlap with `backtest-gate`. Confirm the negative clause sends it there.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/edge-module/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): edge-module -- registry, badge and entry-signal wiring in one place"
```

---

### Task S14: `alert-surface`

**Files:**
- Create: `.claude/skills/alert-surface/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"alert-surface"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when editing the alert surface -- swingbot/core/scanning/engine.py, scan_embeds, embeds.py, or anything rendering a Discord alert or trade plan. This area has two OHLCV caches, legacy shims that silently no-op, and empty tables that are measured answers rather than stubs. Not for chart image generation and not for the admin UI.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/known-traps.md`, in full — it is the shortest path to not breaking this area.
2. **`## Step 2 — An empty table is an answer.** Before "fixing" a blank section, find out whether it is measuring zero. Filling it with a placeholder destroys a real result.
3. **`## Step 3 — Which cache?** There are two OHLCV caches with different freshness. Name which one your change reads before you change it.
4. **`## Step 4 — Confirm the edit is live.** Legacy shims here accept a call and do nothing. After the change, verify the rendered output differs, not just that the function was called.
5. **`## The gate`** — a rendered before/after, not a passing unit test alone.
6. **`## Known wrong turns`** — *"the table is empty, so it is a stub"*; *"the function returned without error"*; *"the cache looked stale so I cleared both"*.
7. **`## Trigger table`** — three+ should-fire (editing an embed; changing scan output; adding an alert field) and three+ should-not-fire (editing a chart renderer; changing an Angular component; editing a strategy).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

Chart generation and the admin UI are the adjacent surfaces. Confirm both are excluded.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/alert-surface/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): alert-surface -- the two caches, the silent shims, and empty-as-an-answer"
```

---

### Task S15: `schema-change`

**Files:**
- Create: `.claude/skills/schema-change/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"schema-change"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when changing the Postgres schema, a store's read or write path, or a data migration -- the JSON-to-Postgres strangler is per-store and partially complete, so some stores are migrated and some are not. Not for reading data, not for analytics queries, and not for the JSON files under data/ that no longer back a migrated store.
```

Body:

1. **`## Step 1 — Establish which stores are migrated.** The strangler is per-store, not a monolith. Check the current state in code; do not assume from a plan.
2. **`## Step 2 — Load the Postgres practices skill** (`supabase:supabase-postgres-best-practices`) before writing DDL, per its own trigger.
3. **`## Step 3 — `parity_report` is the only verifier to trust.** An import that ran without error is not an import that was correct.
4. **`## Step 4 — Round-trip before cutover.** Write, read back, compare — on real data, not a fixture.
5. **`## The gate`** — `parity_report` clean, and the round-trip committed as a test.
6. **`## Known wrong turns`** — *"the import printed no errors"*; *"the row counts match"* → counts match while fields are silently dropped; *"the JSON is still there as a backup"* → until a writer overwrites it.
7. **`## Trigger table`** — three+ should-fire (adding a column; changing a store's writer; writing a data migration) and three+ should-not-fire (a read-only analytics query; a dashboard change; reading a `data/*.json` for context).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

Analytics reads are the main false-positive surface. Confirm they are excluded.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/schema-change/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): schema-change -- parity_report is the verifier, not a clean import"
```

---

### Task S16: `worktree-lifecycle`

**Files:**
- Create: `.claude/skills/worktree-lifecycle/SKILL.md`
- Modify: `tests/hooks/test_skill_shape.py` (add `"worktree-lifecycle"` to `TIER_1_AND_3`)

- [ ] **Step 1: Add the name to the tier set, and watch it fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: FAIL — the skill does not exist yet.

- [ ] **Step 2: Write the skill**

Frontmatter `description`, verbatim:

```
Use when creating, entering, merging or removing a git worktree in this repo, or before merging a branch another concurrent session may be working on. Multiple sessions share this working tree, so a merge or a cross-worktree edit can silently overwrite another session's work. Not for ordinary commits on the current branch.
```

Body:

1. **`## Step 1 — Read the authority.** `docs/claude/document-lifecycle.md` for naming and removal, `docs/claude/working-conventions.md` for the concurrent-session rules.
2. **`## Step 2 — Never edit a worktree from the main tree.** `guardrails.py` denies it; the deny is correct. The edit lands on another branch and is invisible from here.
3. **`## Step 3 — Before merging, check whether anyone else is in it.** Concurrent sessions are normal in this repo. Pause and confirm with the human partner rather than merging on the assumption that the branch is idle.
4. **`## Step 4 — Removal belongs to close-out**, not to "I am done for today". Invoke `/close-out`.
5. **`## The gate`** — the worktree list matches the live plan list; nothing orphaned.
6. **`## Known wrong turns`** — *"the branch looks merged"* → run `git rev-list --count main..<branch>`; *"it has backup in the name but it is stale"* → hard rule, ask; *"I will just edit the file directly, it is the same repo"* → it is not.
7. **`## Trigger table`** — three+ should-fire (creating a worktree; merging a feature branch; cleaning up after a plan) and three+ should-not-fire (committing on the current branch; `git status`; reading a file).

- [ ] **Step 3: Run the shape gate**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py`
Expected: PASS.

- [ ] **Step 4: Check the description against its own negatives**

Ordinary commits are the false-positive surface. Confirm they are excluded.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/worktree-lifecycle/SKILL.md tests/hooks/test_skill_shape.py
git commit -m "feat(skills): worktree-lifecycle -- naming, the concurrent-session pause, and teardown"
```

---

### Task S17: The inventory table

**Files:**
- Modify: `docs/claude/skills-tools.md`
- Modify: `CLAUDE.md` (one line)

- [ ] **Step 1: Add the inventory to `skills-tools.md`**

A table with one row per shipped skill: name, tier, invocation (model-invocable / slash-only), and the `docs/claude/` file it loads. Plus a short paragraph stating the division of labour — a hook denies, a skill teaches — and the three hook rules by name.

- [ ] **Step 2: Amend `CLAUDE.md` in one line**

`CLAUDE.md` is at **199 lines** and the ceiling is "under 200", so this is an **amendment, not an addition** — rewrite the existing sentence in the "Repo tooling (`.claude/`)" paragraph that describes `guardrails.py`, so it also says the rules now include protected-branch deletion, closed-pre-registration knobs and malformed spec/plan writes, and that the integrity-tier skills fire unprompted. **Do not add a line and do not add a table.** If it will not fit in the existing sentence, move something out into `skills-tools.md` and leave a pointer — that is the documented procedure, not a last resort.

- [ ] **Step 3: Verify the ceiling holds**

Run: `python -c "print(sum(1 for _ in open('CLAUDE.md', encoding='utf-8')))"`
Expected: under 200. If not, move content into `skills-tools.md` and leave a pointer.

- [ ] **Step 4: Commit**

```bash
git add docs/claude/skills-tools.md CLAUDE.md
git commit -m "docs(claude): inventory the v96 skills layer and the three new guardrail rules"
```

---

### Task S18: The Codex mirror

**Files:**
- Modify: `.codex/AGENTS.md`

- [ ] **Step 1: Add a condensed mirror**

Condensed, not copied — the sync is one-way and Claude-authored. Codex needs two things: that the integrity-tier rules exist, and that `guardrails.py` will deny protected-branch deletion, closed-pre-registration knobs and malformed spec/plan writes, with a pointer to `docs/claude/` for each. A Codex session hitting an unexplained deny is the failure this prevents.

- [ ] **Step 2: Verify you changed nothing upstream**

Run: `git diff --name-only`
Expected: `.codex/AGENTS.md` only. A Codex-facing edit never justifies changing `CLAUDE.md` or `docs/claude/*.md`.

- [ ] **Step 3: Commit**

```bash
git add .codex/AGENTS.md
git commit -m "docs(codex): mirror the v96 guardrail rules and integrity-tier skills"
```

---

### Task S19: Full-suite verification

- [ ] **Step 1: Run the full suite once, over everything this plan implemented**

Run `python scripts/dev/testrun.py full`, or dispatch the `test-runner` subagent so the output stays out of context.

Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure — this plan adds tests.

**If it is not green, fix forward from those failures.** They are this plan's regressions and the task is not done until the run is green. No `frontend/` files were touched, so `npm test` is not part of this plan's verification.

- [ ] **Step 2: Confirm the hook's invariant survived**

Run: `git diff main -- .claude/hooks/guardrails.py | Select-String "open\(|subprocess|Path\(|read_text"`
Expected: no matches inside `evaluate()`'s call graph. The three new rules are pure functions of their tool input; only `tests/hooks/test_guardrails.py` reads `backtest-methodology.md`.

- [ ] **Step 3: Commit anything the fix-forward produced**

```bash
git add -A
git commit -m "test(v96): full-suite verification for the skills layer"
```
