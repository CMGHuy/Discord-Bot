"""Citation lint for skills, agents and eval prompts (v213 spec § A).

A skill that cites a moved file sends every brief and review built on it to
the wrong place, and no other test reads what a skill cites. ``scan`` reads
the prose of each file (never fenced blocks) and reports every backticked
citation that no longer resolves. It is a pure function of its arguments, so
tests/hooks/test_skill_citations.py runs it on tmp_path fixtures.

What it cannot see (facades that still exist, bare file names, function
names, drifted file:line numbers, fenced commands) stays with /close-out
Step 5b.

CLI: python scripts/dev/skill_citations.py [--root <repo>] prints every
finding the allowlist does not cover, then every dead allowlist line, then a
summary; exit 1 when anything is listed.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

REASON_MISSING = "missing"
REASON_AMBIGUOUS = "ambiguous"
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
    names: dict[str, bool] = field(default_factory=dict)       # word -> found in code
    headings: dict[str, list[str]] = field(default_factory=dict)  # doc rel -> headings


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


def _line_findings(rel: str, number: int, line: str, ctx: _Context) -> list[Finding]:
    found = []
    for word in span_words(line):
        reason = _word_reason(word, ctx)
        if reason:
            found.append(Finding(rel, number, word, reason))
    return found


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


def _file_findings(path: Path, ctx: _Context) -> list[Finding]:
    rel = path.relative_to(ctx.root).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    found: list[Finding] = []
    for number, line in prose_lines(lines):
        found.extend(_line_findings(rel, number, line, ctx))
    found.extend(_section_findings(rel, lines, ctx))
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
