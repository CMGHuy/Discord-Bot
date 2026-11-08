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
