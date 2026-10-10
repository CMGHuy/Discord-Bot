# v155 Research ritual skills: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V155-2` or `grep -n "^### Task V155-2" -A 300 <part file>`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [`docs/superpowers/specs/2026-10-10-v155-research-ritual-skills-design.md`](../specs/2026-10-10-v155-research-ritual-skills-design.md)
**Brief:** `.superpowers/briefs/2026-10-10-v155-research-ritual-skills.md` (line numbers from `main` @ `2b612ca6`)

**Goal:** Put a hook behind the idea screen's one-shot rule (`_rule_screen_rerun` in `.claude/hooks/guardrails.py`) and give the idea screen, the pre-registration and the data check each a slash-only ritual skill (`/screen`, `/prereg`, `/data-check`), mirrored to Codex.

**Architecture:** The hook rule tokenises a Bash command into shell segments with `shlex`, reads `screen_idea.py` flags only from the segment that runs the script, and denies a re-run of a screened idea (ledger row or results doc), a full-universe `--dry-run`, a real run with a non-default `--ledger` or `--results-dir`, a quoted wrapper and an untokenisable line. Segment splitting, flag extraction and the ledger/results lookups are separate helpers so each stays under complexity 15; the ledger path and results dir are module-level constants tests monkeypatch, and a drift test pins the hook's ledger path to `stats.LEDGER_PATH` because the hook stays stdlib-only. The three skills are checklists that read their authority with `scripts/dev/doc_section.py` (v154), restate no threshold, and are mirrored by `scripts/dev/sync_codex.py`.

**Tech Stack:** Python 3.11 stdlib (`shlex`, `glob`, `json`, `os`), pytest, Claude Code skill frontmatter (strict parser from v154), `scripts/dev/sync_codex.py`.

## Global Constraints

- **v154 must be merged on `main` before any v155 task starts.** V155-1 Step 1 checks it: `scripts/dev/skill_frontmatter.py` and `scripts/dev/doc_section.py` exist, `tests/hooks/test_skill_shape.py` has `"result-digest"` and `"handoff"` in `TIER_2`, and `docs/claude/backtest-methodology.md` has `## Funnel stages` and `## Evidence, registry and ledger`. If any check fails, **stop and report**. Do not create the v154 files here.
- **Implemented in a worktree** (`.claude/worktrees/2026-10-10-v155-research-ritual-skills/`, branch `v155-research-ritual-skills`), per `docs/claude/document-lifecycle.md`.
- **Test files for the new rule are written with the Write/Edit tools, never a shell heredoc.** `_rule_closed_preregistration` denies any Bash command that contains a backtest script name next to a closed knob name, and the test strings for this plan put script names in the command text. The same applies to any shell step that would echo or `cat` such text.
- **After V155-2 lands, no shell command in the implementing session quotes a `screen_idea` command line containing `--idea`** (for example inside a `git commit -m "..."`). The new rule treats that as a wrapped run and denies it. Write commit messages that name the rule, not a command line.
- **The hook stays stdlib-only.** `guardrails.py` imports nothing from `swingbot` and nothing outside the standard library. Its 5 s timeout (`.codex/hooks.json`) is unchanged, and so is `.codex/hooks.json`.
- **The hook fails open.** `evaluate()` already wraps every rule in try/except. A missing or unreadable ledger reads as "no row", and a results dir that does not exist reads as "no doc". The two exceptions are written into the rule: a line that mentions `screen_idea` but cannot be tokenised is denied, and so is a wrapped run.
- **Only an exact ledger id `screen-<idea>` denies.** Prefix or similar names are `/screen` step 5's judgement, never the hook's.
- **No change to `scripts/backtest/screen_idea.py`, `scripts/reports/preregistration_ledger.py`, `scripts/data/validate_data.py`, the ledger schema or any threshold.** This plan runs no screen, no backtest and no pre-registration.
- **Skill bodies restate no thresholds** (`tests/hooks/test_skill_shape.py::_THRESHOLD_RE`): they name the doc section that owns a number, never the number. Each new `SKILL.md` stays at or under 80 lines. Each `description:` is a double-quoted scalar (v154's strict parser rejects the unquoted form).
- **All three skills are slash-only** (`disable-model-invocation: true`) and join `TIER_2`. `MODEL_RUN_RITUALS` is unchanged, so "the slash-only set" `TIER_2 - MODEL_RUN_RITUALS` gains all three. Only `data-check` joins `FORKED` (`"data-check": "haiku"`).
- **Every commit that touches `.claude/skills/` runs `python scripts/dev/sync_codex.py` and stages `.agents/` with it.** `AGENTS.md` gains its mirror text in the same commit as the change it mirrors. Codex mirror detail: `docs/claude/working-conventions.md` § Codex mirror.
- **Docs that list hook rules by name gain `_rule_screen_rerun` in the same commit as the rule:** `docs/claude/skills-tools.md` (hook-rules paragraph) and `AGENTS.md` (hook sentence).
- **Anchor on text, not line numbers.** The brief's numbers are from `2b612ca6`, and v154 edits `AGENTS.md`, `docs/claude/skills-tools.md`, `docs/claude/backtest-methodology.md` and `tests/hooks/test_skill_shape.py` before this plan runs. Every task finds its anchor with `grep -n` on the quoted text first.
- **Use the corrected cites** in any text this plan writes: empty-ledger return `stats.py:182-183`; the doc-write and ledger-append crash window sits inside `publish` (about `screen_idea.py:395-400`).
- **No new `scripts/dev/select_tests.py` row.** `.claude/`, `AGENTS.md`, `.agents/` and `docs/claude/` already route to `tests/hooks/`.
- Every Python function written or changed stays below cyclomatic complexity 15 (`python -m radon cc -s -n C .claude/hooks/guardrails.py`). Today's maximum in that file is C(11).
- Per-task verification uses the narrow run: `python scripts/dev/testrun.py file <test>`. The full suite runs once, in V155-6. Green means `0 failed` and `0 xfailed`.
- Out of scope: any new statistical method, any new screen idea, any run of a screen, a `validate_data.py` mode for `data/backtest_cache_ext`, eval suites for the three skills (they are slash-only, so there is no trigger to prove), and prediction skills.

## Decisions fixed by this index

These fill gaps the spec leaves to the plan, and every part is written against them.

1. **Task id prefix `V155-`.** Six tasks in two parts. The estimate is about 1,400 task lines, which is too close to the 1,500-line cap for one part file, so the hook tasks and the skill tasks go in separate parts.
2. **Hook purity.** The `guardrails.py` module docstring stops claiming that `evaluate()` reads no files. It says instead that `_rule_screen_rerun` reads the pre-registration ledger and globs results docs, through module-level constants that tests point at `tmp_path`. V155-1 makes this change.
3. **The hook's ledger path is its own constant**, `SCREEN_LEDGER_PATH`, built with `os.path` from the hook's location. `tests/hooks/test_guardrails.py::test_screen_ledger_path_matches_stats_ledger_path` pins it to `stats.LEDGER_PATH`.
4. **Constants are read at call time** (module globals looked up inside the helpers, never bound as default arguments), so `monkeypatch.setattr(guardrails, "SCREEN_LEDGER_PATH", ...)` takes effect.
5. **`--ledger` is resolved against the repo root** (`_HOOK_REPO_ROOT`), not against the session cwd or a `cd` earlier in the chain. An absolute value is compared as given. The comparison is `os.path.normcase(os.path.normpath(...))` on both sides.
6. **Abbreviated flags count.** `screen_idea.py`'s parser keeps argparse's default `allow_abbrev=True`, so `--dry` and `--led` are real spellings. `_screen_flags` resolves a `--x` token by unique prefix against `_SCREEN_OPTIONS`; an ambiguous or unknown prefix is ignored, which matches what argparse does with it (argparse rejects it).
7. **Wrapped-run detection** (spec § 1, last paragraph) applies to a single token that mentions `screen_idea` and also contains `--idea` but is not itself the script path or module name. The `--idea` condition is how the ssh wrapper and `pwsh -Command "..."` are caught without denying `git grep -n "screen_idea"` or a commit message that names the file. `--idea` is a required flag, so a wrapped run always carries it.
8. **Script and module tokens.** A token is the screen script when, with `\` replaced by `/`, it ends with `screen_idea.py`, equals `screen_idea`, or ends with `.screen_idea` (`python -m scripts.backtest.screen_idea`). Flags are read from the tokens after it in the same segment.
9. **A segment that runs the script without `--idea` is allowed.** That covers `--help`, and argparse rejects the rest.
10. **The order of checks per segment:** dry-run without tickers → deny; dry-run with tickers → allow; non-default `--ledger` → deny; non-default `--results-dir` → deny (controller addition, contract C2); exact ledger row → deny; results doc → deny; otherwise allow. The first deny across segments wins.
11. **Each skill reads its authority by section:** `/screen` reads `"Funnel stages"`, `/prereg` reads `"Funnel stages"` and `"Evidence, registry and ledger"` (both in `backtest-methodology.md`), and `/data-check` reads `"Two OHLCV caches"` and `"Full-history cache"` (in `known-traps.md`). Each skill also says that exit code 2 from `doc_section.py` means "read the whole file".
12. **`/data-check`'s last reply line is fixed text** (contract C4), so the disclosure cannot be paraphrased away.

## Parallelisation

All tasks run in one worktree. The files each task touches decide what can run at the same time.

- **V155-1 can run in parallel with V155-4.** Their files do not overlap (`guardrails.py` and `test_guardrails.py` against the `/prereg` skill files), and neither depends on the other's contract.
- **Sequential edges, each with its reason:**
  - V155-1 → V155-2: V155-2's rule calls `_command_segments`, `_screen_flags`, `_is_default_ledger`, `_screen_ledger_row` and `_screen_results_doc`, which V155-1 creates, and both tasks edit `guardrails.py` and `test_guardrails.py`.
  - V155-2 → V155-3: `/screen` text refers to the hook rule (spec § Parallelisation), and both tasks edit `AGENTS.md` and `docs/claude/skills-tools.md`.
  - V155-2 → V155-4 and V155-2 → V155-5: same two files (`AGENTS.md`, `docs/claude/skills-tools.md`). The sections differ, but the work is serialised so that one file never needs a merge.
  - V155-3 → V155-4 → V155-5: all three edit `TIER_2` in `tests/hooks/test_skill_shape.py` and the same `AGENTS.md` ritual paragraph, and each one regenerates `.agents/skills/` through `sync_codex.py`. They commit one at a time, in id order.
  - V155-6 runs last, as the single full-suite run.
- **If V155-4 runs early, in parallel with V155-1,** it keeps its id-order commit slot. It commits only after V155-2 and V155-3 have committed, and it rebases its `TIER_2` and `AGENTS.md` edits onto theirs.
- **For a single implementer, the recommended order is id order:** V155-1 through V155-6.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-10-v155-research-ritual-skills_1-hook-rule.md` | V155-1 .. V155-2 | Spec § 1 and the hook half of Testing: the v154 precondition, hook constants and helpers, docstring, drift test, `_rule_screen_rerun` and its registration, the hook-rule docs in `skills-tools.md` and `AGENTS.md` |
| 2 | `2026-10-10-v155-research-ritual-skills_2-skills-verification.md` | V155-3 .. V155-6 | Spec § 2 to § 4, the Codex mirror and the rest of Testing: `/screen`, `/prereg`, `/data-check`, their `TIER_2`/`FORKED` registration, the skills-table rows, `AGENTS.md` names, `sync_codex.py`, the full suite |

## Task ledger

| Id | Title | Part | Model | Files created / modified | Creates for later tasks |
|---|---|---|---|---|---|
| V155-1 | v154 precondition; hook constants, segment and flag helpers, ledger and results lookups, docstring, drift test | 1 | sonnet | Modify `.claude/hooks/guardrails.py`, `tests/hooks/test_guardrails.py`; record in `## Results` | `_HOOK_REPO_ROOT`, `SCREEN_LEDGER_PATH`, `SCREEN_RESULTS_DIR`, `_SCREEN_SEPARATORS`, `_SCREEN_OPTIONS`, `_command_segments`, `_is_screen_token`, `_is_wrapped_screen`, `_screen_flags`, `_is_default_ledger`, `_screen_ledger_row`, `_screen_results_doc` (contract C1) |
| V155-2 | `_rule_screen_rerun`, registered in `_RULES["Bash"]`; hook-rule docs | 1 | sonnet | Modify `.claude/hooks/guardrails.py`, `tests/hooks/test_guardrails.py`, `docs/claude/skills-tools.md` (hook-rules paragraph), `AGENTS.md` (hook sentence); record radon in `## Results` | `_rule_screen_rerun(ti: dict) -> dict \| None`, `_screen_deny_reason(flags: dict) -> str \| None`, the deny texts including the non-default `--results-dir` deny (contract C2) |
| V155-3 | `/screen` slash-only skill | 2 | sonnet | Create `.claude/skills/screen/SKILL.md`; modify `tests/hooks/test_skill_shape.py` (`TIER_2`), `docs/claude/skills-tools.md` (skills table), `AGENTS.md` (ritual paragraph); regenerated `.agents/skills/screen/**` | `"screen"` in `TIER_2` (contract C3) |
| V155-4 | `/prereg` slash-only skill | 2 | sonnet | Create `.claude/skills/prereg/SKILL.md`; modify `tests/hooks/test_skill_shape.py` (`TIER_2`), `docs/claude/skills-tools.md` (skills table), `AGENTS.md` (ritual paragraph); regenerated `.agents/skills/prereg/**` | `"prereg"` in `TIER_2` |
| V155-5 | `/data-check` slash-only forked skill | 2 | sonnet | Create `.claude/skills/data-check/SKILL.md`; modify `tests/hooks/test_skill_shape.py` (`TIER_2`, `FORKED`), `docs/claude/skills-tools.md` (skills table), `AGENTS.md` (ritual paragraph); regenerated `.agents/skills/data-check/**` | `"data-check"` in `TIER_2` and `FORKED` (contract C3); the fixed disclosure line (contract C4) |
| V155-6 | Full-suite verification | 2 | haiku | Record in `## Results` | The plan's green verdict |

## Cross-task contracts

### C1. Hook helpers in `.claude/hooks/guardrails.py` (created by V155-1)

New imports: `glob`, `shlex` (stdlib). Nothing else.

```python
_HOOK_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCREEN_RESULTS_DIR = os.path.join(_HOOK_REPO_ROOT, "docs", "superpowers", "results")
SCREEN_LEDGER_PATH = os.path.join(SCREEN_RESULTS_DIR, "preregistration-ledger.jsonl")
_SCREEN_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})
_SCREEN_OPTIONS = ("--idea", "--cache-dir", "--membership", "--start", "--end",
                   "--date", "--ledger", "--results-dir", "--tickers", "--dry-run")

def _command_segments(cmd: str) -> list[list[str]] | None:
    """Shell segments of `cmd` as token lists.

    Joins backslash-newline continuations, splits on newlines, tokenises each
    line with shlex.shlex(line, posix=True, punctuation_chars=True) and
    whitespace_split=True, then splits the token list on _SCREEN_SEPARATORS.
    Empty segments are dropped. A line that raises ValueError is skipped,
    unless it contains "screen_idea", in which case the function returns None.
    """

def _is_screen_token(tok: str) -> bool:
    """`tok` with `\\` replaced by `/` ends with "screen_idea.py", equals
    "screen_idea", or ends with ".screen_idea"."""

def _is_wrapped_screen(tok: str) -> bool:
    """not _is_screen_token(tok) and "screen_idea" in tok and "--idea" in tok."""

def _screen_flags(tokens: list[str]) -> dict | None:
    """None when no token of the segment is a screen token. Otherwise
    {"idea": str | None, "dry_run": bool, "tickers": bool, "ledger": str | None,
     "results_dir": str | None},
    read from the tokens after the first screen token. Accepts `--opt value`
    and `--opt=value`, and resolves a unique prefix of an entry in
    _SCREEN_OPTIONS (argparse allow_abbrev). "tickers" is True when --tickers
    is present with a value."""

def _is_default_ledger(value: str) -> bool:
    """normcase(normpath(join(_HOOK_REPO_ROOT, value))) ==
    normcase(normpath(SCREEN_LEDGER_PATH)); an absolute value survives join."""

def _is_default_results_dir(value: str) -> bool:
    """The same comparison against SCREEN_RESULTS_DIR."""

def _screen_ledger_row(idea: str) -> dict | None:
    """The first JSONL row of SCREEN_LEDGER_PATH whose "id" == f"screen-{idea}"
    exactly. A missing or unreadable file gives None, and a line that is not
    valid JSON is skipped."""

def _screen_results_doc(idea: str) -> str | None:
    """sorted(glob.glob(os.path.join(SCREEN_RESULTS_DIR,
    f"*-screen-{glob.escape(idea)}.md")))[0], or None when there is no match."""
```

The drift test is `test_screen_ledger_path_matches_stats_ledger_path`. It asserts `Path(guardrails.SCREEN_LEDGER_PATH).resolve() == stats.LEDGER_PATH.resolve()`, with `from swingbot.core.backtesting.instrument import stats`.

### C2. The rule (created by V155-2)

```python
def _screen_deny_reason(flags: dict) -> str | None:   # the check order of Decision 10
    # dry run: tickers -> None, else deny; then non-default --ledger -> deny;
    # then non-default --results-dir -> deny; then ledger row, then results doc
def _rule_screen_rerun(ti: dict) -> dict | None:
    # cmd not a str, or "screen_idea" not in cmd -> None
    # _command_segments(cmd) is None -> deny (untokenisable; checked first,
    #   because the wrapped check needs tokens)
    # _has_wrapped_screen(segments): any token _is_wrapped_screen -> deny (wrapped)
    # for each segment: flags = _screen_flags(seg); flags None or flags["idea"] None -> skip
    #   reason = _screen_deny_reason(flags); reason -> _deny(reason)
    # -> None
```

The rule is registered in `_RULES["Bash"]` immediately after `_rule_closed_preregistration`.

Every deny text starts with `screen_idea:` and ends with ` -- one shot per idea; see docs/claude/backtest-methodology.md "Funnel stages".`, and it contains the fragment below that tests assert on:

| Case | Fragment |
|---|---|
| wrapped | `inside a quoted wrapper` |
| untokenisable | `could not tokenise` |
| full-universe dry run | `--dry-run without --tickers` |
| non-default ledger | `--ledger other than the default` |
| non-default results dir (controller addition: a fresh dir hides the results doc a crashed run left behind) | `--results-dir other than the default` |
| ledger row | `screen-<idea> is already in the ledger (<date>, <verdict>, <record>)` |
| results doc, no row | `results doc <path relative to _HOOK_REPO_ROOT, / separators> exists with no ledger row` |

### C3. `tests/hooks/test_skill_shape.py` after this plan

The existing literals are extended and never rewritten. After v154 they end `..."panel", "result-digest", "handoff"}` and `FORKED = {"gate": "sonnet", "task-brief": "sonnet", "result-digest": "haiku"}`.

- V155-3 appends `"screen"` to `TIER_2`.
- V155-4 appends `"prereg"` to `TIER_2`.
- V155-5 appends `"data-check"` to `TIER_2` and adds `"data-check": "haiku"` to `FORKED`.

`MODEL_RUN_RITUALS` is unchanged. No new test function is needed: the existing parametrised tests cover all three skills.

Skill frontmatter, in this exact key order:

| Skill | Keys |
|---|---|
| `screen` | `name: screen`, `description: "<quoted, at least 40 chars>"`, `disable-model-invocation: true` |
| `prereg` | `name: prereg`, `description: "..."`, `disable-model-invocation: true` |
| `data-check` | `name: data-check`, `description: "..."`, `disable-model-invocation: true`, `context: fork`, `model: haiku` |

### C4. `/data-check`'s fixed last line

Every reply ends with this exact line:

```
Not checked: data/backtest_cache_ext (the idea-screen cache read by scripts/backtest/screen_idea.py); no validate_data.py mode covers it.
```

### C5. `AGENTS.md` and `docs/claude/skills-tools.md` additions (one owner each)

| Task | File and anchor | Text added |
|---|---|---|
| V155-2 | `AGENTS.md`, the sentence that lists the guardrails hook rules (brief: about l.291-298) | `_rule_screen_rerun`, with a one-clause gloss (it denies a re-run or a full-universe dry run of a screened idea) |
| V155-2 | `docs/claude/skills-tools.md`, the hook-rules paragraph (brief: l.72-80) | the same name and gloss |
| V155-3 | `AGENTS.md`, the "Explicit-only rituals" paragraph, after v154's `` `handoff` `` | `` `screen` `` with a one-clause gloss |
| V155-4 | same paragraph, after `` `screen` `` | `` `prereg` `` with a one-clause gloss |
| V155-5 | same paragraph, after `` `prereg` `` | `` `data-check` `` with a one-clause gloss |
| V155-3, V155-4, V155-5 | `docs/claude/skills-tools.md`, the skills table (brief: l.85-97) | one row each, in the table's existing column shape |

## Results

The tasks named below fill this in. Nothing here is a threshold, and no row is a pass on its own.

| Check | Task | Result |
|---|---|---|
| v154 precondition (four checks) | V155-1 | _not yet run_ |
| Drift test `SCREEN_LEDGER_PATH` == `stats.LEDGER_PATH` | V155-1 | _not yet run_ |
| `radon cc -s -n C .claude/hooks/guardrails.py` (no function rated C(15) or above) | V155-2 | _not yet run_ |
| `python scripts/dev/sync_codex.py --check` after the last skill | V155-5 | _not yet run_ |
| Full suite | V155-6 | _not yet run_ |
