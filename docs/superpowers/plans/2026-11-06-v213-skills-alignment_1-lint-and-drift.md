# v213 — Skills alignment, part 1: citation lint and drift fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v213 — Skills alignment](../specs/2026-11-06-v213-skills-alignment.md)
**Index:** [`2026-11-06-v213-skills-alignment_0-index.md`](2026-11-06-v213-skills-alignment_0-index.md) — Goal, Architecture, **Global Constraints**, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

**Tasks:** V213-1..V213-6 (Part A scanner, Part B drift).

**Where to run.** Every path and command below is relative to the worktree root
`.claude/worktrees/2026-11-06-v213-skills-alignment` (created in V213-1 Step 1);
the implementer's session root is that worktree. Never `cd` inside a Bash
command; use `git -C <path>` when a command must target another tree.

# Phase A — Citation scanner

### Task V213-1: Citation scanner core: scan set, tokens, path rule, allowlist, output format

**Model:** sonnet — new pure module plus its test file, several interacting tokenising rules to get exactly right; not a cross-module design call.

**Files:**
- Create: `scripts/dev/skill_citations.py`
- Create: `tests/hooks/test_skill_citations.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (V213-2 and V213-6 rely on these exact names):
  - `@dataclass(frozen=True) Finding(file: str, line: int, token: str, reason: str)` with `format() -> str` returning `f"{file}:{line}: {token} -- {reason}"` (`file` repo-relative, forward slashes).
  - `scan(root: Path, files: list[Path], tracked: set[str], code_text: str) -> list[Finding]` — path rule only in this task (`code_text` is accepted and unused until V213-2); every finding, in `files` order, then line order.
  - `scan_set(root: Path, tracked: set[str]) -> list[Path]` — tracked `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`, `.claude/skills/*/evals/*/prompt.md` that exist on disk, sorted by repo-relative path.
  - `prose_lines(lines: list[str]) -> Iterator[tuple[int, str]]` — 1-based numbers; fence lines and lines inside a fence skipped.
  - `span_words(line: str) -> list[str]` — every inline backtick span split on whitespace, each word cleaned; template words dropped.
  - `REASON_MISSING = "missing"`, `REASON_AMBIGUOUS = "ambiguous"`.
  - `@dataclass(frozen=True) AllowEntry(skill: str, token: str, reason: str, line: int)`.
  - `load_allowlist(path: Path) -> list[AllowEntry]` (missing file gives `[]`; a malformed line raises `ValueError`).
  - `skill_of(rel: str) -> str` — the skill folder for `.claude/skills/<x>/...`, else the file stem (agents).
  - `apply_allowlist(findings: list[Finding], entries: list[AllowEntry]) -> tuple[list[Finding], list[AllowEntry]]` — (remaining findings, dead entries); matching is on `(skill_of(finding.file), finding.token)` against `(entry.skill, entry.token)`, exactly.
  - Private `_Context(root, tracked, code_text)` dataclass, `_word_reason(word, ctx)`, `_line_findings(rel, number, line, ctx)`, `_file_findings(path, ctx)` — V213-2 extends `_Context`, `_word_reason` and `_file_findings`.

**Resolution rule, as implemented.** The spec: a path "passes when exactly one candidate is in `tracked`", candidates `<word>`, `swingbot/<word>`, `swingbot/core/<word>` in that order. Count the tracked candidates over all three: one passes, none is `missing`, two or more is `ambiguous`. Comparison is case-exact against `tracked`, so a wrong-case citation fails on Windows as it does on Linux CI.

- [ ] **Step 1: Create the worktree**

```bash
git worktree list
git worktree add .claude/worktrees/2026-11-06-v213-skills-alignment -b 2026-11-06-v213-skills-alignment main
```

Skip the `add` if `git worktree list` already shows the worktree (resume in it). Every later step runs with the worktree as its root.

- [ ] **Step 2: Write the failing tests**

Create `tests/hooks/test_skill_citations.py`:

```python
"""v213 § A: the citation lint over skills, agents and eval prompts.

Unit cases build tiny repos on tmp_path and call the pure scanner in
scripts/dev/skill_citations.py directly. Fixture names below are made up on
purpose and must never be cited by a real skill: this file is part of the
code text the config-name rule searches.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the module.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import skill_citations as sc  # noqa: E402


def _write(root: Path, rel: str, text: str, *, crlf: bool = False) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", "\r\n") if crlf else text
    path.write_bytes(data.encode("utf-8"))
    return path


def _skill(root: Path, text: str, name: str = "demo", *, crlf: bool = False) -> Path:
    return _write(root, f".claude/skills/{name}/SKILL.md", text, crlf=crlf)


def _scan(root: Path, text: str, tracked=(), code_text: str = "", *, crlf: bool = False):
    path = _skill(root, text, crlf=crlf)
    return sc.scan(root, [path], set(tracked), code_text)


def _rows(findings):
    return [(f.line, f.token, f.reason) for f in findings]


# --- paths -----------------------------------------------------------------

def test_missing_path_is_reported(tmp_path):
    assert _rows(_scan(tmp_path, "see `scripts/dev/gone.py`\n")) == [
        (1, "scripts/dev/gone.py", sc.REASON_MISSING)]


def test_tracked_root_path_passes(tmp_path):
    assert _scan(tmp_path, "see `scripts/dev/here.py`\n", {"scripts/dev/here.py"}) == []


@pytest.mark.parametrize("word, tracked", [
    ("commands/x.py", "swingbot/commands/x.py"),
    ("scanning/x.py", "swingbot/core/scanning/x.py")])
def test_path_found_only_by_one_fallback_root_passes(tmp_path, word, tracked):
    assert _scan(tmp_path, f"see `{word}`\n", {tracked}) == []


def test_two_fallback_candidates_are_ambiguous(tmp_path):
    tracked = {"swingbot/scanning/x.py", "swingbot/core/scanning/x.py"}
    assert _rows(_scan(tmp_path, "see `scanning/x.py`\n", tracked)) == [
        (1, "scanning/x.py", sc.REASON_AMBIGUOUS)]


def test_wrong_case_path_is_missing(tmp_path):
    findings = _scan(tmp_path, "see `swingbot/Config.py`\n", {"swingbot/config.py"})
    assert _rows(findings) == [(1, "swingbot/Config.py", sc.REASON_MISSING)]


@pytest.mark.parametrize("span", [
    "swingbot/<name>.py", "swingbot/**/*.py", "docs/{a,b}.md", "$ROOT/x.py",
    "k=v/a.py", "https://example.com/a.md", "logs/<plan>-rows/{x}.jsonl"])
def test_template_words_are_skipped(tmp_path, span):
    assert _scan(tmp_path, f"run `{span}`\n") == []


@pytest.mark.parametrize("span", [
    "scripts/a.py::test_x", "scripts/a.py:12", "scripts/a.py:12-30",
    "scripts/a.py),", "scripts/a.py.", "scripts/a.py::Klass::method"])
def test_symbol_and_line_suffixes_are_stripped(tmp_path, span):
    assert _scan(tmp_path, f"see `{span}`\n", {"scripts/a.py"}) == []


def test_several_paths_in_one_multi_word_span(tmp_path):
    text = "run `python scripts/a.py scripts/gone.py tests/x.py`\n"
    assert _rows(_scan(tmp_path, text, {"scripts/a.py", "tests/x.py"})) == [
        (1, "scripts/gone.py", sc.REASON_MISSING)]


def test_two_citations_on_one_line_are_two_tokens(tmp_path):
    text = "see `scripts/a.py` and `scripts/b.py`\n"
    assert _rows(_scan(tmp_path, text)) == [
        (1, "scripts/a.py", sc.REASON_MISSING), (1, "scripts/b.py", sc.REASON_MISSING)]


def test_fenced_blocks_are_skipped(tmp_path):
    text = ("```bash\npython `scripts/a.py`\n```\n"
            "~~~\n`scripts/b.py`\n~~~\n"
            "`scripts/c.py`\n")
    assert _rows(_scan(tmp_path, text)) == [(7, "scripts/c.py", sc.REASON_MISSING)]


def test_prose_lines_numbers_from_one_and_skips_fences():
    lines = ["a", "```", "b", "~~~", "still fenced", "```", "c"]
    assert list(sc.prose_lines(lines)) == [(1, "a"), (7, "c")]


def test_crlf_file_behaves_like_lf(tmp_path):
    findings = _scan(tmp_path, "intro\n`scripts/a.py`\n", crlf=True)
    assert _rows(findings) == [(2, "scripts/a.py", sc.REASON_MISSING)]


@pytest.mark.parametrize("word", [
    ".superpowers/briefs/x.md", "logs/run.jsonl", "data/journal.json", "market_data/x.json"])
def test_runtime_prefixes_are_skipped(tmp_path, word):
    assert _scan(tmp_path, f"see `{word}`\n") == []


@pytest.mark.parametrize("word", ["foo.py", "swingbot/core/", "swingbot/x.csv", "a/b"])
def test_words_that_are_not_paths_are_ignored(tmp_path, word):
    assert _scan(tmp_path, f"see `{word}`\n") == []


def test_span_words_cleans_and_drops_templates():
    line = "x `python scripts/a.py:3 <id>` y `docs/b.md),`"
    assert sc.span_words(line) == ["python", "scripts/a.py", "docs/b.md"]


# --- scan set and order ----------------------------------------------------

def test_scan_set_covers_skills_agents_and_eval_prompts(tmp_path):
    rels = [".claude/skills/x/SKILL.md", ".claude/skills/x/evals/fire-a/prompt.md",
            ".claude/skills/x/evals/fire-a/graders/skill-fired.md", ".claude/agents/y.md",
            ".agents/skills/x/SKILL.md", ".claude/skills/x/notes.md"]
    for rel in rels:
        _write(tmp_path, rel, "text\n")
    _write(tmp_path, ".claude/agents/untracked.md", "text\n")
    tracked = set(rels) | {".claude/agents/deleted.md"}
    got = [p.relative_to(tmp_path).as_posix() for p in sc.scan_set(tmp_path, tracked)]
    assert got == [".claude/agents/y.md", ".claude/skills/x/SKILL.md",
                   ".claude/skills/x/evals/fire-a/prompt.md"]


def test_findings_keep_file_order_then_line_order(tmp_path):
    first = _write(tmp_path, ".claude/skills/b/SKILL.md", "`scripts/b1.py`\n\n`scripts/b2.py`\n")
    second = _write(tmp_path, ".claude/agents/a.md", "`scripts/a1.py`\n")
    got = [(f.file, f.line) for f in sc.scan(tmp_path, [first, second], set(), "")]
    assert got == [(".claude/skills/b/SKILL.md", 1), (".claude/skills/b/SKILL.md", 3),
                   (".claude/agents/a.md", 1)]


@pytest.mark.parametrize("rel, skill", [
    (".claude/skills/task-brief/SKILL.md", "task-brief"),
    (".claude/skills/edge-module/evals/fire-x/prompt.md", "edge-module"),
    (".claude/agents/prod-inspector.md", "prod-inspector")])
def test_skill_of(rel, skill):
    assert sc.skill_of(rel) == skill


# --- allowlist -------------------------------------------------------------

ALLOWLIST = """# reviewed mentions of removed or uncommitted things

demo|scripts/kept.py|deleted on purpose, named as history
   # an indented comment
demo|scripts/never.py|no longer cited anywhere
"""


def test_allowlist_skips_comments_and_blank_lines(tmp_path):
    path = _write(tmp_path, "allow.txt", ALLOWLIST)
    entries = sc.load_allowlist(path)
    assert [(e.skill, e.token, e.line) for e in entries] == [
        ("demo", "scripts/kept.py", 3), ("demo", "scripts/never.py", 5)]
    assert entries[0].reason == "deleted on purpose, named as history"


def test_missing_allowlist_is_empty(tmp_path):
    assert sc.load_allowlist(tmp_path / "absent.txt") == []


@pytest.mark.parametrize("bad", ["demo|only-two", "demo||reason", "no separators"])
def test_malformed_allowlist_line_raises(tmp_path, bad):
    path = _write(tmp_path, "allow.txt", f"{bad}\n")
    with pytest.raises(ValueError, match="allow.txt:1"):
        sc.load_allowlist(path)


def test_allowlisted_token_is_removed_and_dead_line_reported(tmp_path):
    findings = _scan(tmp_path, "`scripts/kept.py` `scripts/other.py`\n")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, dead = sc.apply_allowlist(findings, entries)
    assert [f.token for f in remaining] == ["scripts/other.py"]
    assert [(e.token, e.line) for e in dead] == [("scripts/never.py", 5)]


def test_one_allowlist_line_covers_every_occurrence_in_its_skill(tmp_path):
    findings = _scan(tmp_path, "`scripts/kept.py`\n\n`scripts/kept.py`\n")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, _ = sc.apply_allowlist(findings, entries)
    assert remaining == []


def test_allowlist_matches_the_skill_exactly(tmp_path):
    path = _write(tmp_path, ".claude/skills/other/SKILL.md", "`scripts/kept.py`\n")
    findings = sc.scan(tmp_path, [path], set(), "")
    entries = sc.load_allowlist(_write(tmp_path, "allow.txt", ALLOWLIST))
    remaining, _ = sc.apply_allowlist(findings, entries)
    assert [f.token for f in remaining] == ["scripts/kept.py"]


# --- output ----------------------------------------------------------------

def test_output_format_is_exact(tmp_path):
    (finding,) = _scan(tmp_path, "x\n\nsee `scripts/gone.py`\n")
    assert finding.format() == ".claude/skills/demo/SKILL.md:3: scripts/gone.py -- missing"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: FAIL — collection error `ModuleNotFoundError: No module named 'skill_citations'`.

- [ ] **Step 4: Write the module**

Create `scripts/dev/skill_citations.py`:

```python
"""Citation lint for skills, agents and eval prompts (v213 spec § A).

A skill that cites a moved file sends every brief and review built on it to
the wrong place, and no other test reads what a skill cites. ``scan`` reads
the prose of each file (never fenced blocks) and reports every backticked
citation that no longer resolves. It is a pure function of its arguments, so
tests/hooks/test_skill_citations.py runs it on tmp_path fixtures.

What it cannot see (facades that still exist, bare file names, function
names, drifted file:line numbers, fenced commands) stays with /close-out
Step 5b.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

REASON_MISSING = "missing"
REASON_AMBIGUOUS = "ambiguous"

PATH_SUFFIXES = (".py", ".md", ".json", ".jsonl", ".sh", ".toml", ".ts", ".mjs", ".html")
RUNTIME_PREFIXES = (".superpowers/", "logs/", "data/", "market_data/")
TEMPLATE_MARKS = ("<", ">", "*", "{", "}", "$", "=", "://")
# The repo root first, then the two fallback roots (spec § A, rule 1).
CANDIDATE_ROOTS = ("", "swingbot/", "swingbot/core/")
FENCES = ("```", "~~~")
TRAILING = ",.;:)"
SPAN_RE = re.compile(r"`([^`]+)`")
SYMBOL_SUFFIX_RE = re.compile(r"::.*$")
LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
SCAN_PATTERNS = (
    re.compile(r"^\.claude/skills/[^/]+/SKILL\.md$"),
    re.compile(r"^\.claude/agents/[^/]+\.md$"),
    re.compile(r"^\.claude/skills/[^/]+/evals/[^/]+/prompt\.md$"),
)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    token: str
    reason: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.token} -- {self.reason}"


@dataclass(frozen=True)
class AllowEntry:
    skill: str
    token: str
    reason: str
    line: int


@dataclass
class _Context:
    root: Path
    tracked: set[str]
    code_text: str


def scan_set(root: Path, tracked: set[str]) -> list[Path]:
    """Tracked skills, agents and eval prompts that exist on disk, sorted."""
    rels = sorted(rel for rel in tracked if any(rx.match(rel) for rx in SCAN_PATTERNS))
    return [root / rel for rel in rels if (root / rel).is_file()]


def _fence_marker(line: str) -> str | None:
    stripped = line.lstrip()
    for fence in FENCES:
        if stripped.startswith(fence):
            return fence
    return None


def prose_lines(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield (1-based number, line) for every line outside a fenced block."""
    open_fence: str | None = None
    for number, line in enumerate(lines, start=1):
        marker = _fence_marker(line)
        if open_fence is None:
            if marker:
                open_fence = marker
                continue
            yield number, line
        elif marker == open_fence:
            open_fence = None


def _clean_word(word: str) -> str:
    word = word.rstrip(TRAILING)
    word = SYMBOL_SUFFIX_RE.sub("", word)
    word = LINE_SUFFIX_RE.sub("", word)
    return word.rstrip(TRAILING)


def _is_template(word: str) -> bool:
    return any(mark in word for mark in TEMPLATE_MARKS)


def span_words(line: str) -> list[str]:
    """Every word of every inline backtick span, cleaned; templates dropped."""
    words = []
    for span in SPAN_RE.findall(line):
        for raw in span.split():
            word = _clean_word(raw)
            if word and not _is_template(word):
                words.append(word)
    return words


def _is_path(word: str) -> bool:
    return ("/" in word and word.endswith(PATH_SUFFIXES)
            and not word.startswith(RUNTIME_PREFIXES))


def _path_reason(word: str, tracked: set[str]) -> str | None:
    hits = [root + word for root in CANDIDATE_ROOTS if root + word in tracked]
    if len(hits) == 1:
        return None
    return REASON_AMBIGUOUS if hits else REASON_MISSING


def _word_reason(word: str, ctx: _Context) -> str | None:
    if _is_path(word):
        return _path_reason(word, ctx.tracked)
    return None


def _line_findings(rel: str, number: int, line: str, ctx: _Context) -> list[Finding]:
    found = []
    for word in span_words(line):
        reason = _word_reason(word, ctx)
        if reason:
            found.append(Finding(rel, number, word, reason))
    return found


def _file_findings(path: Path, ctx: _Context) -> list[Finding]:
    rel = path.relative_to(ctx.root).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[Finding] = []
    for number, line in prose_lines(lines):
        found.extend(_line_findings(rel, number, line, ctx))
    return sorted(found, key=lambda finding: finding.line)


def scan(root: Path, files: list[Path], tracked: set[str], code_text: str) -> list[Finding]:
    """Every finding in ``files`` (in that order, then by line); never stops early."""
    ctx = _Context(root, tracked, code_text)
    findings: list[Finding] = []
    for path in files:
        findings.extend(_file_findings(path, ctx))
    return findings


def skill_of(rel: str) -> str:
    """The skill folder of a skill or eval file; the file stem of an agent."""
    parts = rel.split("/")
    if parts[:2] == [".claude", "skills"] and len(parts) > 2:
        return parts[2]
    return Path(rel).stem


def _allow_entry(path: Path, number: int, line: str) -> AllowEntry:
    parts = [part.strip() for part in line.split("|", 2)]
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"{path.name}:{number}: expected skill|token|reason, got {line!r}")
    return AllowEntry(parts[0], parts[1], parts[2], number)


def load_allowlist(path: Path) -> list[AllowEntry]:
    """``skill|token|reason`` lines; blank and ``#`` lines ignored; no file is empty."""
    if not path.is_file():
        return []
    entries = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(_allow_entry(path, number, line))
    return entries


def apply_allowlist(findings: list[Finding],
                    entries: list[AllowEntry]) -> tuple[list[Finding], list[AllowEntry]]:
    """(findings no entry covers, entries that matched no finding)."""
    allowed = {(entry.skill, entry.token) for entry in entries}
    seen = {(skill_of(finding.file), finding.token) for finding in findings}
    remaining = [f for f in findings if (skill_of(f.file), f.token) not in allowed]
    dead = [entry for entry in entries if (entry.skill, entry.token) not in seen]
    return remaining, dead
```

`path.read_text` plus `splitlines()` makes a CRLF file read exactly like an LF one (no trailing `\r` on a token).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: `VERDICT: PASS`, 0 failed.

- [ ] **Step 6: Complexity and neighbours**

```bash
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
```

Expected: the gate reports no offender in `scripts/dev/skill_citations.py` (every function under complexity 15); `test_skill_shape.py` `VERDICT: PASS`.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/skill_citations.py tests/hooks/test_skill_citations.py
git commit -m "feat(v213): citation lint core -- scan set, tokens, path rule, allowlist

V213-1. Pure scanner over skills, agents and eval prompts; unit cases on
tmp_path fixtures. Config-name and doc-section rules follow in V213-2.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V213-2: Config-name and doc-section rules, repo helpers, CLI

**Model:** sonnet — extends V213-1's module with two more rules, a paragraph builder and a `git ls-files` CLI; contained to two files plus an empty allowlist.

**Files:**
- Modify: `scripts/dev/skill_citations.py`
- Modify: `tests/hooks/test_skill_citations.py`
- Create: `tests/hooks/skill_citation_allowlist.txt`

**Interfaces:**
- Consumes (V213-1): `Finding`, `scan`, `scan_set`, `prose_lines`, `span_words`, `load_allowlist`, `apply_allowlist`, `skill_of`, `_Context`, `_word_reason`, `_line_findings`, `_file_findings`, `_path_reason`, `_is_path`.
- Produces (V213-3 and V213-6 rely on these):
  - `REASON_UNKNOWN_NAME = "unknown name"`, `REASON_MISSING_DOC = "missing doc"`, `REASON_MISSING_HEADING = "missing heading"`.
  - `doc_headings(text: str) -> list[str]` — `##` to `####` lines outside fences, `#`s stripped, lower-cased.
  - `paragraphs(lines: list[str]) -> Iterator[tuple[int, str]]` — (first line number, lines joined with single spaces); a blank line, a fence or a line whose stripped text starts with `- ` ends the paragraph.
  - `tracked_paths(root: Path) -> set[str]` (`git ls-files -z`, cwd=root).
  - `read_code_text(root: Path, tracked: set[str]) -> str` — every tracked `*.py` under `swingbot/`, `scripts/`, `tests/` that exists, joined by newlines.
  - `ALLOWLIST_REL = "tests/hooks/skill_citation_allowlist.txt"`.
  - `repo_report(root: Path) -> list[str]` — remaining findings formatted, then each dead entry as `tests/hooks/skill_citation_allowlist.txt:<n>: <skill>|<token> -- dead allowlist line`.
  - `main(argv: list[str] | None = None) -> int` — `--root` (default the repo root); prints the report then one summary line; exit 1 when the report is non-empty, else 0.

**Decided at index time (see the index's Architecture):** a Markdown list item (stripped line starting `- `) begins a new paragraph; a `missing doc` token is the doc as written; a `missing heading` token is `<doc> § <cite>` with `cite` stripped (case kept); a section finding's line is the paragraph's first line.

- [ ] **Step 1: Write the failing tests**

Add `import subprocess` to the imports of `tests/hooks/test_skill_citations.py` (after `import sys`), then append:

```python
# --- config names ----------------------------------------------------------

def test_unknown_config_name_is_reported(tmp_path):
    findings = _scan(tmp_path, "set `NOT_A_REAL_KNOB`\n", code_text="OTHER_FIXTURE_KNOB = 1")
    assert _rows(findings) == [(1, "NOT_A_REAL_KNOB", sc.REASON_UNKNOWN_NAME)]


def test_known_config_name_passes(tmp_path):
    code = "DEMO_FIXTURE_KNOB: int = 3\n"
    assert _scan(tmp_path, "set `DEMO_FIXTURE_KNOB`.\n", code_text=code) == []


def test_config_name_matches_a_whole_word_only(tmp_path):
    findings = _scan(tmp_path, "`DEMO_KNOB`\n", code_text="DEMO_KNOB_EXTRA = 1")
    assert _rows(findings) == [(1, "DEMO_KNOB", sc.REASON_UNKNOWN_NAME)]


@pytest.mark.parametrize("word", ["README", "ExpR", "A_b", "_PRIVATE", "HTTP2"])
def test_words_that_are_not_config_names_are_ignored(tmp_path, word):
    assert _scan(tmp_path, f"`{word}`\n") == []


def test_config_name_found_only_in_a_scripts_file_passes(tmp_path):
    _write(tmp_path, "scripts/dev/tool.py", "DEMO_SCRIPT_TABLE = ()\n")
    tracked = {"scripts/dev/tool.py"}
    code = sc.read_code_text(tmp_path, tracked)
    assert _scan(tmp_path, "`DEMO_SCRIPT_TABLE`\n", tracked, code) == []


def test_read_code_text_reads_only_tracked_python_under_the_code_roots(tmp_path):
    files = {"swingbot/a.py": "IN_SWINGBOT_X = 1", "tests/b.py": "IN_TESTS_X = 1",
             "scripts/c.py": "IN_SCRIPTS_X = 1", "frontend/d.py": "OUT_FRONTEND_X = 1",
             "swingbot/e.md": "OUT_MD_X", "swingbot/untracked.py": "OUT_UNTRACKED_X"}
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    tracked = (set(files) - {"swingbot/untracked.py"}) | {"swingbot/deleted.py"}
    code = sc.read_code_text(tmp_path, tracked)
    for name in ("IN_SWINGBOT_X", "IN_TESTS_X", "IN_SCRIPTS_X"):
        assert name in code
    for name in ("OUT_FRONTEND_X", "OUT_MD_X", "OUT_UNTRACKED_X"):
        assert name not in code


# --- doc sections ----------------------------------------------------------

FENCE = "`" * 3   # built, so no bare fence line sits inside this plan or file
DOC = (
    "# Title\n\n## Funnel stages\n\ntext\n\n"
    "### Closed pre-registrations — do not re-run these\n\n#### Deep heading\n\n"
    f"{FENCE}md\n## Fenced heading\n{FENCE}\n"
)
DOC_REL = "docs/claude/methods.md"


def _doc_scan(tmp_path, text):
    _write(tmp_path, DOC_REL, DOC)
    return _scan(tmp_path, text, {DOC_REL})


def test_doc_headings_are_levels_two_to_four_outside_fences():
    assert sc.doc_headings(DOC) == [
        "funnel stages", "closed pre-registrations — do not re-run these", "deep heading"]


@pytest.mark.parametrize("text", [
    "see `docs/claude/methods.md` § Funnel stages, stage two.\n",
    "see `methods.md` § Funnel stages\n",
    "see `methods.md` § Closed pre-registrations\n",
    "see `methods.md` § Closed pre-registrations — do not re-run these lists it.\n",
    "see `methods.md` § Deep heading).\n",
    "see `methods.md` § FUNNEL STAGES\n"])
def test_section_citation_to_a_real_heading_passes(tmp_path, text):
    assert _doc_scan(tmp_path, text) == []


def test_section_cite_wrapped_across_two_lines_passes(tmp_path):
    text = "see `methods.md` § Closed\npre-registrations — do not re-run these.\n"
    assert _doc_scan(tmp_path, text) == []


def test_missing_heading_is_reported_on_the_paragraphs_first_line(tmp_path):
    text = "intro\n\nfirst line\nsee `methods.md` § Stage two of the funnel.\n"
    assert _rows(_doc_scan(tmp_path, text)) == [
        (3, "methods.md § Stage two of the funnel", sc.REASON_MISSING_HEADING)]


@pytest.mark.parametrize("cite", ["Fenced heading", "Title"])
def test_fenced_and_level_one_headings_are_not_headings(tmp_path, cite):
    findings = _doc_scan(tmp_path, f"`methods.md` § {cite}\n")
    assert [f.reason for f in findings] == [sc.REASON_MISSING_HEADING]


def test_list_item_starts_a_new_paragraph(tmp_path):
    text = "- see `methods.md` § Closed pre-registrations\n- a second bullet\n"
    assert _doc_scan(tmp_path, text) == []


def test_missing_doc_with_a_slash_is_reported_by_both_rules(tmp_path):
    findings = _scan(tmp_path, "`docs/claude/gone.md` § Anything\n")
    assert _rows(findings) == [(1, "docs/claude/gone.md", sc.REASON_MISSING),
                               (1, "docs/claude/gone.md", sc.REASON_MISSING_DOC)]


def test_bare_doc_resolves_from_docs_claude(tmp_path):
    assert _rows(_scan(tmp_path, "`gone.md` § Anything\n")) == [
        (1, "gone.md", sc.REASON_MISSING_DOC)]


def test_paragraphs_break_on_blank_fence_and_list_item():
    lines = ["a", "b", "", "- c", "  d", "- e", "```", "f", "```", "g"]
    assert list(sc.paragraphs(lines)) == [(1, "a b"), (4, "- c d"), (6, "- e"), (10, "g")]


def test_eval_prompt_is_in_the_scan_set_and_scanned(tmp_path):
    rel = ".claude/skills/demo/evals/fire-x/prompt.md"
    _write(tmp_path, rel, "---\nmax_turns: 4\n---\n\nReview `swingbot/core/edge/imaginary.py`.\n")
    files = sc.scan_set(tmp_path, {rel})
    assert _rows(sc.scan(tmp_path, files, {rel}, "")) == [
        (5, "swingbot/core/edge/imaginary.py", sc.REASON_MISSING)]


# --- repo helpers and CLI --------------------------------------------------

def _git_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        _write(root, rel, text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def test_tracked_paths_reads_the_git_index(tmp_path):
    _git_repo(tmp_path, {"a/b.py": "x\n", ".claude/skills/x/SKILL.md": "x\n", "docs/ü.md": "x\n"})
    _write(tmp_path, "untracked.py", "x\n")
    assert sc.tracked_paths(tmp_path) == {"a/b.py", ".claude/skills/x/SKILL.md", "docs/ü.md"}


def test_repo_report_lists_findings_then_dead_lines(tmp_path):
    allow = "# header\nx|scripts/kept.py|named on purpose\nx|scripts/never.py|stale\n"
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/gone.py` `scripts/kept.py`\n",
                         sc.ALLOWLIST_REL: allow})
    assert sc.repo_report(tmp_path) == [
        ".claude/skills/x/SKILL.md:1: scripts/gone.py -- missing",
        "tests/hooks/skill_citation_allowlist.txt:3: x|scripts/never.py -- dead allowlist line"]


def test_main_exits_zero_on_a_clean_repo(tmp_path, capsys):
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/here.py`\n",
                         "scripts/here.py": "x = 1\n"})
    assert sc.main(["--root", str(tmp_path)]) == 0
    assert "clean" in capsys.readouterr().out


def test_main_exits_one_and_prints_each_finding(tmp_path, capsys):
    _git_repo(tmp_path, {".claude/skills/x/SKILL.md": "`scripts/gone.py`\n"})
    assert sc.main(["--root", str(tmp_path)]) == 1
    assert ".claude/skills/x/SKILL.md:1: scripts/gone.py -- missing" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: FAIL — `AttributeError: module 'skill_citations' has no attribute 'REASON_UNKNOWN_NAME'` (and the other new names); the V213-1 cases still pass.

- [ ] **Step 3: Extend the module**

In `scripts/dev/skill_citations.py`:

(a) Append this paragraph to the module docstring, before the closing `"""`:

```text
CLI: python scripts/dev/skill_citations.py [--root <repo>] prints every
finding the allowlist does not cover, then every dead allowlist line, then a
summary; exit 1 when anything is listed.
```

(b) Replace the import block with:

```python
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
```

(c) Below `REASON_AMBIGUOUS = "ambiguous"` add:

```python
REASON_UNKNOWN_NAME = "unknown name"
REASON_MISSING_DOC = "missing doc"
REASON_MISSING_HEADING = "missing heading"

ALLOWLIST_REL = "tests/hooks/skill_citation_allowlist.txt"
REPO_ROOT = Path(__file__).resolve().parents[2]
CODE_ROOTS = ("swingbot/", "scripts/", "tests/")
DOC_ROOT = "docs/claude/"
CITE_TRAILING = ".,;:) "
CONFIG_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
SECTION_RE = re.compile(r"`?(?P<doc>[\w./-]+\.md)`?\s*§\s*(?P<cite>[^`]+)")
HEADING_RE = re.compile(r"^#{2,4}\s+(?P<text>.*\S)\s*$")
```

(d) Replace `_Context` with:

```python
@dataclass
class _Context:
    root: Path
    tracked: set[str]
    code_text: str
    names: dict[str, bool] = field(default_factory=dict)       # word -> found in code
    headings: dict[str, list[str]] = field(default_factory=dict)  # doc rel -> headings
```

(e) Replace `_word_reason` with the two functions below:

```python
def _name_reason(word: str, ctx: _Context) -> str | None:
    if word not in ctx.names:
        ctx.names[word] = re.search(rf"\b{re.escape(word)}\b", ctx.code_text) is not None
    return None if ctx.names[word] else REASON_UNKNOWN_NAME


def _word_reason(word: str, ctx: _Context) -> str | None:
    if _is_path(word):
        return _path_reason(word, ctx.tracked)
    if CONFIG_NAME_RE.match(word):
        return _name_reason(word, ctx)
    return None
```

(f) Add the doc-section rule after `_line_findings`:

```python
def doc_headings(text: str) -> list[str]:
    """``##``-``####`` headings outside fenced blocks, ``#``s stripped, lower-cased."""
    headings = []
    for _, line in prose_lines(text.splitlines()):
        match = HEADING_RE.match(line)
        if match:
            headings.append(match.group("text").lower())
    return headings


def paragraphs(lines: list[str]) -> Iterator[tuple[int, str]]:
    """(first line, joined text) per paragraph; blank, fence and ``- `` items break it."""
    buffer: list[str] = []
    first = last = 0
    for number, line in prose_lines(lines):
        stripped = line.strip()
        if buffer and (not stripped or number != last + 1 or stripped.startswith("- ")):
            yield first, " ".join(buffer)
            buffer = []
        if stripped:
            first = first if buffer else number
            buffer.append(stripped)
        last = number
    if buffer:
        yield first, " ".join(buffer)


def _doc_rel(doc: str) -> str:
    return doc if "/" in doc else DOC_ROOT + doc


def _headings_of(rel: str, ctx: _Context) -> list[str]:
    if rel not in ctx.headings:
        ctx.headings[rel] = doc_headings((ctx.root / rel).read_text(encoding="utf-8"))
    return ctx.headings[rel]


def _cite_matches(cite: str, headings: list[str]) -> bool:
    wanted = cite.lower()
    return any(wanted.startswith(h) or h.startswith(wanted) for h in headings)


def _section_finding(rel: str, first: int, match: re.Match, ctx: _Context) -> Finding | None:
    doc = match.group("doc")
    doc_rel = _doc_rel(doc)
    if doc_rel not in ctx.tracked or not (ctx.root / doc_rel).is_file():
        return Finding(rel, first, doc, REASON_MISSING_DOC)
    cite = match.group("cite").strip().rstrip(CITE_TRAILING)
    if _cite_matches(cite, _headings_of(doc_rel, ctx)):
        return None
    return Finding(rel, first, f"{doc} § {cite}", REASON_MISSING_HEADING)


def _section_findings(rel: str, lines: list[str], ctx: _Context) -> list[Finding]:
    found = []
    for first, text in paragraphs(lines):
        for match in SECTION_RE.finditer(text):
            finding = _section_finding(rel, first, match, ctx)
            if finding:
                found.append(finding)
    return found
```

(g) Replace `_file_findings` with (the sort is stable, so on one line path and name findings come before section findings):

```python
def _file_findings(path: Path, ctx: _Context) -> list[Finding]:
    rel = path.relative_to(ctx.root).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[Finding] = []
    for number, line in prose_lines(lines):
        found.extend(_line_findings(rel, number, line, ctx))
    found.extend(_section_findings(rel, lines, ctx))
    return sorted(found, key=lambda finding: finding.line)
```

(h) Append the repo helpers and CLI at the end of the module:

```python
def tracked_paths(root: Path) -> set[str]:
    """``git ls-files`` of ``root`` (forward slashes; ``-z`` so no path is quoted)."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         capture_output=True, check=True).stdout
    return {rel for rel in out.decode("utf-8").split("\0") if rel}


def read_code_text(root: Path, tracked: set[str]) -> str:
    """Every tracked ``*.py`` under swingbot/, scripts/ and tests/, joined."""
    parts = []
    for rel in sorted(tracked):
        path = root / rel
        if rel.endswith(".py") and rel.startswith(CODE_ROOTS) and path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def repo_report(root: Path) -> list[str]:
    """Findings the allowlist does not cover, then its dead lines, formatted."""
    tracked = tracked_paths(root)
    findings = scan(root, scan_set(root, tracked), tracked, read_code_text(root, tracked))
    remaining, dead = apply_allowlist(findings, load_allowlist(root / ALLOWLIST_REL))
    lines = [finding.format() for finding in remaining]
    lines += [f"{ALLOWLIST_REL}:{entry.line}: {entry.skill}|{entry.token} -- dead allowlist line"
              for entry in dead]
    return lines


def _utf8_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint what skills, agents and eval prompts cite.")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    args = parser.parse_args(argv)
    _utf8_stdout()   # findings carry § and em dashes; a cp1252 console would raise
    report = repo_report(args.root.resolve())
    for line in report:
        print(line)
    print(f"skill citations: {len(report)} problem(s)" if report else "skill citations: clean")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create the allowlist with its header only**

Create `tests/hooks/skill_citation_allowlist.txt`:

```text
# v213 citation-lint allowlist (scripts/dev/skill_citations.py; spec § A).
#
# One line per skill and token:  skill|token|reason
#   skill  = the skill folder, or the agent file stem
#   token  = the finding's token exactly as the lint prints it
#   reason = why the mention stays: deleted on purpose and named as history,
#            uncommitted by design, vendored, an eval hypothetical, a runtime path
# One line covers every occurrence in that skill. A line that matches no
# finding is a dead line and fails tests/hooks/test_skill_citations.py.
# Never add a line for real drift: fix the skill instead.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: `VERDICT: PASS`, 0 failed.

- [ ] **Step 6: Smoke the CLI and the neighbours**

```bash
python scripts/dev/skill_citations.py > "$TMP/v213-cli.txt"; echo "exit=$?"; tail -n 1 "$TMP/v213-cli.txt"
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
```

Expected: `exit=1` and a summary line `skill citations: <n> problem(s)` (the repo is not clean yet; V213-3 records the list, V213-6 clears it). The complexity gate reports no offender in `scripts/dev/skill_citations.py`. `test_select_tests.py` `VERDICT: PASS`; if `test_no_path_a_test_reads_is_classified_inert` fails over the new allowlist file, stop and return `BLOCKED:` (a `DATA_READERS` row in `scripts/dev/select_tests.py` is outside this plan's file list).

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/skill_citations.py tests/hooks/test_skill_citations.py tests/hooks/skill_citation_allowlist.txt
git commit -m "feat(v213): citation lint -- config names, doc sections, repo report and CLI

V213-2. Config names must appear in tracked Python under swingbot/,
scripts/, tests/; doc.md § cites must start with (or prefix) a heading;
a list item opens a new paragraph. Allowlist starts with its header only.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase B — Drift fixes

### Task V213-3: Red proof, then `task-brief` drift (intro, 3a, 3b/3c, 3g, new 3i-3l, Bash for step 4)

**Model:** sonnet — prose rewrite of a grandfathered skill against code anchors that must be re-verified in the worktree; one file plus a pin test, no code.

**Files:**
- Modify: `.claude/skills/task-brief/SKILL.md`
- Modify: `tests/hooks/test_handoff_wiring.py` (the trap-letter pin gains `i` to `l`)
- Modify: generated Codex copies written by `python scripts/dev/sync_codex.py` (`.agents/skills/task-brief/SKILL.md`)

**Interfaces:**
- Consumes (V213-2): `python scripts/dev/skill_citations.py` (CLI, exit 1 on findings), `sc.repo_report(ROOT)`.
- Produces: the red list (count plus every line) in this commit's message body; 3e's deleted-shim list stays verbatim (V213-6 allowlists its five tokens).

**Code anchors (re-check each in the worktree before writing; a mismatch means the text below is adjusted to what the tree shows):**

```bash
git grep -n "build_embed(" -- swingbot/core/scanning/scan_run.py swingbot/core/scanning/short_run.py swingbot/core/scanning/outlook_run.py
git grep -n "def build_embed" -- swingbot/core/scanning/alert_embeds.py
git grep -n 'sections\["headline"\]' -- swingbot/core/scanning/alert_embeds.py
git grep -n "io.monitor_scan(\|def _live_monitor_scan\|update_open_trades\|_check_near_close(ticker\|liquidity_reason(\|data_quality_issues(\|for horizon_key in horizons_to_scan" -- swingbot/core/scanning/analyze.py
git grep -n "map_tickers" -- swingbot/core/scanning/scan_run.py
git grep -n "def get_next_earnings_date\|def earnings_within_window" -- swingbot/core/market/events.py
git grep -n "def days_to_earnings" -- swingbot
```

Expected on the tree the plan was written against: `build_embed(` at `scan_run.py:1255`, `short_run.py:307`, `outlook_run.py:260`; `def build_embed` at `alert_embeds.py:173`; `sections["headline"]` from `alert_embeds.py:216`; in `analyze.py` `def _live_monitor_scan` :772 (calls `trade_log.update_open_trades` :774 then `_check_near_close` :780), `io.monitor_scan(...)` :1049, `universe.liquidity_reason` near :1064, `universe.data_quality_issues` :1075, `for horizon_key in horizons_to_scan:` :1104; `fetch.map_tickers` near `scan_run.py:718`; both earnings functions exist; `days_to_earnings` has no definition.

- [ ] **Step 1: Prove the repo-wide case red and record the list**

Append the repo-wide case temporarily (it lands for real in V213-6):

```bash
cat >> tests/hooks/test_skill_citations.py <<'EOF'


def test_repo_has_no_stale_citations():
    report = sc.repo_report(ROOT)
    assert not report, "\n".join(report)
EOF
python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py
python scripts/dev/skill_citations.py > "$TMP/v213-red.txt"; echo "exit=$?"; wc -l < "$TMP/v213-red.txt"
git checkout -- tests/hooks/test_skill_citations.py
```

Expected: `VERDICT: FAIL` with exactly one failure, `test_repo_has_no_stale_citations`; the CLI prints `exit=1`. Keep `$TMP/v213-red.txt` for the commit body (Step 7). The index's dry run found about 40 lines; the CLI's list is the truth. `git status --porcelain tests/hooks/` must be empty after the checkout.

- [ ] **Step 2: Extend the trap pin (failing test)**

In `tests/hooks/test_handoff_wiring.py`, `test_task_brief_fills_only_the_two_slots`, replace

```python
    for check in "abcdefgh":
        assert f"**3{check}." in skill, f"trap check 3{check} must stay"
```

with

```python
    for check in "abcdefghijkl":
        assert f"**3{check}." in skill, f"trap check 3{check} must stay"
    assert "every 3a-3l result" in skill
    assert "358-822 KB" not in skill, "the pre-v196 plan sizes are gone"
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_handoff_wiring.py`
Expected: FAIL on `**3i.`.

- [ ] **Step 3: Rewrite the intro and 3a**

In `.claude/skills/task-brief/SKILL.md` replace the paragraph under `# Task brief with trap preflight` (from `Plan files here are 358-822 KB` to `writes it into the task's handoff file.`) with:

```markdown
**A plan file is not ground truth about the current code.** It was written
against an older tree, and briefs built from plans have shipped wrong module
paths, invented symbols and wiring that was a silent no-op — every one caught
by hand before dispatch. This skill does that pass mechanically, and writes it
into the task's handoff file.
```

In 3a, change the fence of the `git grep -n "def <symbol>"` block from `powershell` to `bash` (the command is the same in both shells) and replace the three-row table with the one row that is still invented (the JSON-era rows are gone: every store is Postgres-only, 3i):

```markdown
| Plan says | Reality |
|---|---|
| `market_events.days_to_earnings` | `events.get_next_earnings_date` / `earnings_within_window` in `swingbot/core/market/events.py` |
```

- [ ] **Step 4: Rewrite 3b, 3c and 3g**

Replace the whole 3b paragraph with:

```markdown
**3b. Wiring target.** If the task wires sizing, embeds or alert fields, the brief
will likely name the posting package `swingbot/commands/scanning/` (`alerts.py`,
`loops.py`). **That is a silent no-op** — it only posts and re-renders alerts
that are already built. Sizing and embed-building happen in the alert loops,
right before `build_embed()`: `swingbot/core/scanning/scan_run.py` (long scan),
`swingbot/core/scanning/short_run.py` (shorts) and
`swingbot/core/scanning/outlook_run.py` (outlook). `build_embed` itself lives in
`swingbot/core/scanning/alert_embeds.py`. Find today's call sites with
`git grep -n "build_embed(" -- swingbot/core/scanning` rather than trusting a
line number. Correct the brief before dispatch and say so.
```

Replace the whole 3c paragraph with:

```markdown
**3c. Embed fields** go through the `sections["headline"]` accumulator in
`swingbot/core/scanning/alert_embeds.py`, never a raw `embed.add_field()`
(breaks `SECTION_ORDER`).
```

Replace the whole 3g paragraph with:

```markdown
**3g. Scan-loop ordering.** Ticker screens go *after* the open-trade monitor and
*before* the new-signal horizon loop, all inside `_scan_one` in
`swingbot/core/scanning/analyze.py`: first `io.monitor_scan` (live:
`_live_monitor_scan`, which runs `trade_log.update_open_trades` then
`_check_near_close`), then the screens (`universe.liquidity_reason`,
`universe.data_quality_issues`), then `for horizon_key in horizons_to_scan:`.
`swingbot/core/scanning/scan_run.py` only maps `_scan_one` over the tickers
(`fetch.map_tickers`); a screen placed there runs outside that order.
```

Leave 3d, 3e (its deleted-shim list verbatim), 3f and 3h as they are.

- [ ] **Step 5: Add 3i to 3l, Bash for Step 4, the new range in Step 5**

Insert after the 3h paragraph, before `## Step 4`:

```markdown
**3i. Stores are Postgres-only.** Every store reads and writes Postgres; a task
that writes a JSON file under `data/` as a store writes to nothing the bot
reads. A shape change follows `docs/claude/schema-evolution.md` (the
`schema-change` skill). A task whose tests reach the database runs
`/replicate-prod-db` first, against the one shared `swing-db` container, never
a per-task container or database.

**3j. Test placement.** A new `tests/` directory joins exactly one suite in
`tests/suites.toml` in the same commit. A new data file a test reads gets a
`DATA_READERS` row in `scripts/dev/select_tests.py`. Pytest admin-login
fixtures never use the main-tree `.env` admin credentials: those override the
fixture's own and the login returns 401 (V177). A Playwright or local-instance
check still logs in with the `.env` values (root `CLAUDE.md`).

**3k. Short work never downgrades longs.** A SHORT-targeted task keeps long
plans byte-identical and pins that with a regression test (the same input gives
the same long plan before and after the change).

**3l. UI tasks are checked at three widths.** A task that changes a screen is
checked with Playwright at 390, 768 and 1440 px (`docs/claude/ui-design.md`),
never with claude-in-chrome.
```

In `## Step 4 — Check the tree is safe to work in`, keep the PowerShell block and add directly below it:

````markdown
From Git Bash (no `cd`; point `git -C` at the worktree):

```bash
git -C <wt> log --oneline -3
git -C <wt> status --porcelain
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300"
```
````

In `## Step 5 — Fill the two slots`, change `every 3a-3h result` to `every 3a-3l result`.

- [ ] **Step 6: Verify**

```bash
python scripts/dev/testrun.py file tests/hooks/test_handoff_wiring.py
python scripts/dev/skill_citations.py | grep "skills/task-brief/"
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
git status --porcelain
```

Expected: `test_handoff_wiring.py` `VERDICT: PASS`; the lint lists for `task-brief` only 3e's five deleted shims (`core/scan_engine.py`, `core/scan_embeds.py`, `core/confidence.py`, `core/regime.py`, `core/trade_plan.py`, reason `missing`), nothing from 3a-3l; `test_codex_mirror.py` and `test_skill_shape.py` `VERDICT: PASS`; `git status` shows only the skill, the test and the regenerated `.agents/` copy.

- [ ] **Step 7: Commit**

Write the message to a file so the red list goes in whole:

```bash
{
  printf 'docs(v213): task-brief points at today'"'"'s wiring; traps 3i-3l\n\n'
  printf 'V213-3. Intro drops the pre-v196 sizes; 3a keeps the one still-invented\n'
  printf 'symbol; 3b/3c point at the alert loops and alert_embeds.py; 3g re-derived\n'
  printf 'from analyze._scan_one; new 3i-3l; Bash for Step 4.\n\n'
  printf 'Red proof before Part B (repo-wide case red locally, %s lines):\n' "$(wc -l < "$TMP/v213-red.txt")"
  cat "$TMP/v213-red.txt"
  printf '\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n'
} > "$TMP/v213-3-msg.txt"
git add .claude/skills/task-brief/SKILL.md tests/hooks/test_handoff_wiring.py .agents/skills/task-brief/SKILL.md
git commit -F "$TMP/v213-3-msg.txt"
```

If `git status` in Step 6 showed another generated file, add it by its explicit path too.

### Task V213-4: `gate` becomes the pre-push gate, with a structural gate test

**Model:** sonnet — rewrite of one slash-only skill plus a new structural test, and four one-line description fixes in docs; nothing executable changes.

**Files:**
- Modify: `.claude/skills/gate/SKILL.md`
- Create: `tests/hooks/test_gate_skill.py`
- Modify: `AGENTS.md` (the `gate` description in the explicit-only rituals list)
- Modify: `docs/claude/skills-tools.md` (the Repo tooling line)
- Modify: `docs/claude/document-lifecycle.md` (the Repo tooling line)
- Modify: `docs/claude/testing-cost.md` (the inner-loop paragraph)
- Modify: generated Codex copies written by `python scripts/dev/sync_codex.py` (`.agents/skills/gate/**`)

**Interfaces:**
- Consumes: `scripts/dev/skill_frontmatter.py` `parse_frontmatter(text) -> tuple[dict[str, str], str]` (values are strings: `disable-model-invocation: true` reads as `"true"`).
- Produces: seven headings `## Step 1 — …` to `## Step 7 — …` (em dash) in the spec's order: CPU, syntax, complexity gate, diff-selected tests, frontend specs, scoped commits, push and CI watch. `gate` stays grandfathered in `tests/hooks/test_skill_shape.py` (`GRANDFATHERED`, `FORKED["gate"] == "sonnet"`), keeps `disable-model-invocation: true` and `context: fork`.

- [ ] **Step 1: Write the failing test**

Create `tests/hooks/test_gate_skill.py`:

```python
"""v213 § B: /gate is the pre-push gate -- pinned by structure, not wording.

The seven `## Step` headings come in the spec's order, and their bodies name
the complexity gate, the diff-selected run and the CI watch in that order.
`testrun.py full` may appear only on a line that says it is never run here or
is CI's; the description never mentions a full suite.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# scripts/dev has no __init__.py: put it on sys.path, then import the helper.
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from skill_frontmatter import parse_frontmatter  # noqa: E402

GATE = ROOT / ".claude" / "skills" / "gate" / "SKILL.md"
STEP_RE = re.compile(r"^## Step (\d+) — (.+)$", re.MULTILINE)
# One word each step title must carry, in the spec's order.
TITLE_WORDS = ("cpu", "syntax", "complexity", "tests", "frontend", "commit", "ci")
# What the step bodies must name, in this order (spec § B, gate steps 3, 4, 7).
ORDERED_MARKERS = ("complexity_gate.py", "testrun.py changed", "§ Pipeline watch")


def _gate() -> tuple[dict[str, str], str]:
    return parse_frontmatter(GATE.read_text(encoding="utf-8"))


def _steps(body: str) -> list[tuple[int, str, str]]:
    """(number, title, heading plus body) per `## Step` heading, in file order."""
    matches = list(STEP_RE.finditer(body))
    steps = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        steps.append((int(match.group(1)), match.group(2), body[match.start():end]))
    return steps


def test_seven_steps_numbered_in_order():
    assert [number for number, _, _ in _steps(_gate()[1])] == list(range(1, 8))


def test_step_titles_follow_the_spec_order():
    titles = [title.lower() for _, title, _ in _steps(_gate()[1])]
    for title, word in zip(titles, TITLE_WORDS, strict=True):
        assert word in title, (title, word)


def test_gate_commands_appear_in_step_order():
    steps = _steps(_gate()[1])
    firsts = []
    for marker in ORDERED_MARKERS:
        hits = [number for number, _, text in steps if marker in text]
        assert hits, f"no step names {marker}"
        firsts.append(hits[0])
    assert firsts == sorted(set(firsts)), firsts


def test_full_suite_appears_only_as_never_or_ci():
    for line in GATE.read_text(encoding="utf-8").splitlines():
        if "testrun.py full" in line:
            assert "never" in line.lower() or "CI" in line, line


def test_description_does_not_mention_a_full_suite():
    description = _gate()[0]["description"].lower()
    assert "full" not in description, description


def test_frontend_step_runs_the_specs_without_cd():
    (_, _, text), = [step for step in _steps(_gate()[1]) if step[0] == 5]
    assert "ng-test.mjs" in text and "--include" in text
    assert "cd frontend" not in text


def test_gate_stays_slash_only_and_forked():
    meta, _ = _gate()
    assert meta["disable-model-invocation"] == "true"
    assert meta["context"] == "fork"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_gate_skill.py`
Expected: FAIL — `test_seven_steps_numbered_in_order` (five steps today), `test_description_does_not_mention_a_full_suite`, the order and frontend cases; `test_gate_stays_slash_only_and_forked` passes.

- [ ] **Step 3: Rewrite the gate skill**

Replace the whole of `.claude/skills/gate/SKILL.md` with:

`````markdown
---
name: gate
description: "Pre-push gate -- CPU check, syntax pass, complexity gate, diff-selected tests, frontend specs when frontend/ changed, scoped commits, then push and watch the CI run until it is green."
disable-model-invocation: true
context: fork
model: sonnet
---

# Pre-push gate

Green means **`0 failed`** and **`0 xfailed`**, nothing subtler. A changed
pass count is not a failure; a new `xfailed` is a quarantine someone added, so
find out why.

This gate never runs the whole suite locally: the CI pipeline runs it on every
push (root `CLAUDE.md`: no plan or merge runs the full suite locally). The gate
runs what reaches the diff, commits in scoped pieces, pushes, then watches CI
until it is green. Paste the verdict line of every step; a step with no pasted
line did not run.

## Step 1 — Do not fight another session for the CPU

```powershell
Get-Process python -ErrorAction SilentlyContinue |
  Where-Object CPU -gt 300 |
  Select-Object Id, StartTime, CPU
```

A hit means a multi-hour walk-forward run is live. Wait, or run only the
touched file. Contention does not change counts, but it wrecks timings.

## Step 2 — Syntax pass

No `make` on Windows:

```powershell
python -m py_compile bot.py admin_ui.py
python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('swingbot', quiet=2) else 1)"
```

## Step 3 — Complexity gate

```bash
python scripts/dev/complexity_gate.py
```

Every function the diff wrote or changed stays under the limit in
`docs/claude/code-complexity.md`, and a legacy function already over it got no
worse. A new offender is a FAIL: split it into named helpers. `--update` only
ever shrinks the baseline; never use it to admit a new offender.

## Step 4 — Diff-selected tests

```bash
python scripts/dev/testrun.py changed
```

`changed` runs the tests that reach the diff and widens when unsure
(`--dry-run` prints the selection). While iterating on one file use
`python scripts/dev/testrun.py file <test>`. Output is parked in
`.pytest-last-run.log`; stdout is one verdict line:

- `VERDICT: PASS` — proceed.
- `VERDICT: FAIL` — yours. Fix it and re-run that test alone
  (`testrun.py file <test>` or `pytest <path>::<test>`); load
  `superpowers:systematic-debugging` before proposing a fix.
- `VERDICT: UNKNOWN` — the output could not be parsed: a tooling problem,
  **never** a success.

Never run bare `pytest` for a gate (`pytest.ini` sets `-q`, which prints no
summary counts line), and never `testrun.py full` here: that run is CI's.

## Step 5 — Frontend specs, when `frontend/` changed

Skip this step when `git diff --name-only` lists nothing under `frontend/`.
Otherwise run the spec of every changed component. The wrapper runs
`ng test --watch=false` from `frontend/` without a `cd`, which the repo hooks
forbid:

```bash
node frontend/scripts/ng-test.mjs frontend --include <spec path under frontend/>
```

A worker start timeout under load is cured by one re-run
(`docs/claude/testing-cost.md`).

## Step 6 — Stage narrowly, commit in scoped pieces

Concurrent sessions share this tree, and uncommitted generated state has been
silently wiped before.

```bash
git add <explicit paths>      # never git add -A
```

Several scoped commits, never one large one: each carries one meaningful
change with its own tests (`docs/claude/working-conventions.md`). Commit
generated artifacts (especially `validation_registry.json`) at once, and a
skill, agent or `docs/claude/` change ships its Codex mirror
(`python scripts/dev/sync_codex.py`) in the same commit.

## Step 7 — Push, then watch CI until green

Push, then follow the run it started
(`docs/claude/working-conventions.md` § Pipeline watch):

```bash
git push
gh run list --branch <branch> --limit 1 --json databaseId,status,conclusion
gh run watch <id> --exit-status
```

Red: `gh run view <id> --log-failed`, fix each failing test, re-run it alone,
commit scoped, push, and watch the new run; repeat until green. A deploy-job
failure touches production: stop and tell the partner. Never state PASS
without pasting the run's conclusion.
`````

(The five-backtick fence above only wraps the file for this plan; the file itself starts at `---`.)

- [ ] **Step 4: Fix the live descriptions of `/gate`**

- `AGENTS.md`: in the explicit-only rituals sentence, `` `gate` (pre-commit gate) `` becomes `` `gate` (pre-push gate: complexity gate, diff-selected tests, CI watch) ``.
- `docs/claude/skills-tools.md`, Repo tooling paragraph: `` `/gate` is the pre-commit `` / `verification gate.` becomes `` `/gate` is the pre-push `` / ``gate: complexity gate, `testrun.py changed`, frontend specs, scoped commits, then a CI watch.`` (rewrap the paragraph's lines as needed; change no other words).
- `docs/claude/document-lifecycle.md`, Repo tooling line: `` `/gate` is the `` / `pre-commit gate,` becomes `` `/gate` is the `` / `pre-push gate,`.
- `docs/claude/testing-cost.md`, the paragraph opening `**It is an inner-loop tool and not a gate.**`: replace its second sentence, `` `/gate` and a plan's final verification task still run everything. ``, with ``The CI pipeline still runs everything on every push, and `/gate` ends by watching that run.`` Keep the rest of the paragraph ("That boundary is the safety argument: …").

Leave `docs/claude/document-lifecycle.md`'s Step 5b history line ("`gate` still running the full suite locally") alone: it records the audit that found the drift.

- [ ] **Step 5: Verify**

```bash
python scripts/dev/testrun.py file tests/hooks/test_gate_skill.py
python scripts/dev/skill_citations.py | grep "skills/gate/"
python scripts/dev/sync_codex.py
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/hooks/test_skill_shape.py
python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py
git status --porcelain
```

Expected: every `testrun.py` call `VERDICT: PASS`; the lint `grep` prints nothing (the dead `tests/test_edge_gates.py` citation is gone); `git status` lists the skill, the new test, the four docs and the regenerated files under `.agents/skills/gate/`.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/gate/SKILL.md tests/hooks/test_gate_skill.py AGENTS.md docs/claude/skills-tools.md docs/claude/document-lifecycle.md docs/claude/testing-cost.md .agents/skills/gate/
git commit -m "docs(v213): /gate becomes the pre-push gate

V213-4. Seven steps: CPU, syntax, complexity gate, testrun.py changed,
frontend specs, scoped commits, push and CI watch. The local full run, the
August baseline and the xfail history go; disable-model-invocation stays.
Structural test pins step order. Live descriptions in AGENTS.md and three
docs follow.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

