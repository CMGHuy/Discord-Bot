"""Side-effect-free parsing of plan and spec markdown (v193).

One parser for plan_lint.py (--ledger) and plan_slice.py: ledger rows keyed
by header cell, ## sections, backticked tokens, Spec § references and the
symbol name a ledger token stands for. Import with scripts/dev on sys.path.
"""
from __future__ import annotations

import re
from pathlib import Path

COL_TASK = "Task"
COL_PART = "Part"
COL_SPEC = "Spec §"
COL_FILES = "Files created / modified"
COL_CREATES = "Creates"
COL_CONSUMES = "Consumes"

BACKTICK_RE = re.compile(r"`([^`]+)`")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
SEPARATOR_RE = re.compile(r"^\|?\s*:?-{3,}")
SPEC_LINE_RE = re.compile(r"^\*\*Spec:\*\*\s*(?:\[[^\]]*\]\(([^)]+)\)|`([^`]+)`)", re.M)
REF_SPLIT_RE = re.compile(r"[;,]")
SYMBOL_SPLIT_RE = re.compile(r"::|\.")
NO_REF = {"", "—", "–", "-"}


def backticked(cell: str) -> list[str]:
    return [t.strip() for t in BACKTICK_RE.findall(cell) if t.strip()]


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, text) of every heading outside fenced code."""
    found, fenced = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        m = None if fenced else HEADING_RE.match(line)
        if m:
            found.append((i, len(m.group(1)), m.group(2)))
    return found


def sections(text: str, level: int = 2) -> dict[str, str]:
    lines = text.splitlines()
    heads = _headings(lines)
    out: dict[str, str] = {}
    for k, (i, lvl, title) in enumerate(heads):
        if lvl != level or title in out:
            continue
        end = next((j for j, other, _ in heads[k + 1:] if other <= level), len(lines))
        out[title] = "\n".join(lines[i:end]).rstrip() + "\n"
    return out


def _cells(line: str) -> list[str]:
    cells = CELL_SPLIT_RE.split(line.strip())
    if cells and not cells[0].strip():
        cells = cells[1:]
    if cells and not cells[-1].strip():
        cells = cells[:-1]
    return [c.replace("\\|", "|").strip() for c in cells]


def ledger_rows(text: str) -> list[dict[str, str]]:
    section = sections(text).get("Task ledger", "")
    table = [line for line in section.splitlines() if line.lstrip().startswith("|")]
    if not table:
        return []
    header = _cells(table[0])
    rows = []
    for line in table[1:]:
        if SEPARATOR_RE.match(line.strip()):
            continue
        cells = _cells(line)
        rows.append({h: cells[k] if k < len(cells) else "" for k, h in enumerate(header)})
    return rows


def spec_refs(cell: str) -> list[str]:
    refs = [part.strip().lstrip("§").strip() for part in REF_SPLIT_RE.split(cell)]
    return [r for r in refs if r not in NO_REF]


def resolve_ref(ref: str, headings: list[str]) -> str | None:
    if ref in headings:
        return ref
    return next((h for h in headings if h.startswith((ref + ".", ref + " "))), None)


def spec_path(index: Path, index_text: str) -> Path | None:
    m = SPEC_LINE_RE.search(index_text)
    if not m:
        return None
    target = (m.group(1) or m.group(2)).split("#", 1)[0].strip()
    for candidate in (index.parent / target, Path(target)):
        if candidate.is_file():
            return candidate.resolve()
    return None


def symbol_name(token: str) -> str:
    """The name a ledger token stands for: a repo path (contains '/') or a
    flag (starts with '-') as its first word; otherwise the last '.'/'::'
    segment of the first word before any '(' with a trailing ':' dropped."""
    words = token.split("(", 1)[0].split()
    if not words:
        return ""
    first = words[0]
    if "/" in first or first.startswith("-"):
        return first
    return SYMBOL_SPLIT_RE.split(first.rstrip(":"))[-1]
