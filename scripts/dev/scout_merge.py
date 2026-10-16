#!/usr/bin/env python3
"""v161: merge the generator roles' rows into one ranked scout slate.

This part (TS8) parses the role-output file into ScoutRows -- dropping malformed and
duplicate rows -- and reads the two sources of already-decided names: the
pre-registration ledger and the closed-pre-registrations table of
docs/claude/backtest-methodology.md. TS9 adds the drops against the autopsy JSON,
the ranking, the slate and the CLI. Deterministic; no model, no network."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER = ROOT / "docs" / "superpowers" / "results" / "preregistration-ledger.jsonl"
METHODOLOGY = ROOT / "docs" / "claude" / "backtest-methodology.md"
CLOSED_HEADING = "### Closed pre-registrations — do not re-run these"
ROW_FIELDS = ("idea", "claim", "evidence", "exploratory", "edge", "mechanism", "order_form",
              "manual_actions", "pairs_with", "divergence", "route")
EXACT_ONLY = "="   # prefix: a name from a PASS row matches only an identical idea
_EDGES = ("expectancy", "harvest", "volume")
_ROLE_RE = re.compile(r"^## role:\s*(\S+)\s*$")
_START_RE = re.compile(r"^- idea:\s*(.*)$")
_FIELD_RE = re.compile(r"^  ([a-z_]+):\s*(.*)$")
_CELL_RE = re.compile(r"\bcell\s+([^;]+?)\s*(?:;|$)")
_PLAYBOOK_RE = re.compile(r"\bplaybook:?\s+([a-z0-9][a-z0-9-]*)")
_N_RE = re.compile(r"\bN\s+(\d+)")
_TAG_RE = re.compile(r"\((v\d+)")
_TICK_RE = re.compile(r"`([^`]+)`")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{3,}$")
_PASS_RE = re.compile(r"^\*\*(SCREEN-)?PASS\b")
_KNOB_RE = re.compile(r"\b[A-Z][A-Z0-9_]{4,}\b")
_HEAD_MAX_WORDS = 3


@dataclass
class ScoutRow:
    role: str
    idea: str
    claim: str
    evidence: str
    exploratory: str
    edge: str
    mechanism: str
    order_form: str
    manual_actions: str
    pairs_with: str
    divergence: str
    route: str

    @property
    def cell_id(self) -> str | None:
        match = _CELL_RE.search(self.evidence)
        return match.group(1) if match else None

    @property
    def playbook_id(self) -> str | None:
        match = _PLAYBOOK_RE.search(self.evidence)
        return match.group(1) if match else None

    @property
    def quoted_n(self) -> int | None:
        match = _N_RE.search(self.evidence)
        return int(match.group(1)) if match else None


@dataclass(frozen=True)
class Drop:
    idea: str
    role: str
    reason: str


def normalise(name: str) -> str:
    """Case-insensitive kebab form: every run outside a-z0-9 becomes one '-'."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _add_field(fields: dict, key: str, value: str, problems: list[str]) -> None:
    if key not in ROW_FIELDS:
        problems.append(f"unknown field {key}")
    elif key in fields:
        problems.append(f"repeated field {key}")
    else:
        fields[key] = value


def _read_blocks(text: str) -> list[tuple[str, dict, list[str]]]:
    """(role, fields, problems) per '- idea:' block, in file order."""
    blocks: list[tuple[str, dict, list[str]]] = []
    role, current = "", None
    for line in text.replace("\r\n", "\n").split("\n"):
        heading, start, field = _ROLE_RE.match(line), _START_RE.match(line), _FIELD_RE.match(line)
        if heading:
            role, current = heading.group(1), None
        elif start:
            current = {"idea": start.group(1).strip()}
            blocks.append((role, current, []))
        elif field and current is not None:
            _add_field(current, field.group(1), field.group(2).strip(), blocks[-1][2])
    return blocks


def _problems(role: str, fields: dict, problems: list[str]) -> list[str]:
    out = list(problems)
    missing = [f for f in ROW_FIELDS if not fields.get(f)]
    if missing:
        out.append("missing " + ", ".join(missing))
    if not role:
        out.append("no '## role:' heading above it")
    checks = (("exploratory", ("yes",), "exploratory must be yes (spec boundary 5)"),
              ("edge", _EDGES, "edge must be expectancy, harvest or volume"),
              ("divergence", ("yes", "no"), "divergence must be yes or no"))
    out += [message for key, allowed, message in checks
            if fields.get(key) and fields[key] not in allowed]
    return out


def parse_rows(text: str) -> tuple[list[ScoutRow], list[Drop]]:
    """Rows in the Row format under '## role:' headings; malformed and duplicates dropped."""
    rows: list[ScoutRow] = []
    drops: list[Drop] = []
    seen: dict[str, str] = {}
    for role, fields, problems in _read_blocks(text):
        idea = fields.get("idea") or "(no idea)"
        bad = _problems(role, fields, problems)
        if bad:
            drops.append(Drop(idea, role, "malformed: " + "; ".join(bad)))
            continue
        key = normalise(idea)
        if key in seen:
            drops.append(Drop(idea, role, f"duplicate of {seen[key]}"))
            continue
        seen[key] = f"{role}/{idea}"
        rows.append(ScoutRow(role=role, **{f: fields[f] for f in ROW_FIELDS}))
    return rows, drops


def _table_rows(lines: list[str]) -> list[str]:
    """The closed table: from the heading to the first non-blank, non-table line.
    ``list.index`` raises ValueError when the heading is gone -- loudly, on purpose."""
    start = lines.index(CLOSED_HEADING)
    out = []
    for line in lines[start + 1:]:
        if line.startswith("|"):
            out.append(line)
        elif line.strip():
            break
    return out


def _names_in_row(line: str) -> set[str]:
    cols = [c.strip() for c in line.strip().strip("|").split("|")]
    raw = set(_TAG_RE.findall(cols[0]))
    raw.update(t for t in _TICK_RE.findall(cols[0]) if _NAME_RE.match(t))
    for token in _TICK_RE.findall(line):
        if token.startswith("screen-"):
            raw.update({token, token.removeprefix("screen-")})
    names = {normalise(n) for n in raw}
    passed = len(cols) > 1 and _PASS_RE.match(cols[1])
    return {EXACT_ONLY + n for n in names} if passed else names


def closed_names(methodology: Path = METHODOLOGY) -> set[str]:
    """Every name the closed-pre-registrations table records (PASS rows prefixed EXACT_ONLY)."""
    lines = Path(methodology).read_text(encoding="utf-8").splitlines()
    names: set[str] = set()
    for line in _table_rows(lines):
        names |= _names_in_row(line)
    return names


def _ledger_row_names(row: dict) -> list[str]:
    rid = row["id"]
    raw = [rid, rid.removeprefix("screen-"), re.sub(r"^v\d+-", "", rid)]
    hypothesis = row.get("hypothesis") or ""
    head = hypothesis.split(":", 1)[0]
    if ":" in hypothesis and len(head.split()) <= _HEAD_MAX_WORDS:
        raw.append(head)
    raw += _KNOB_RE.findall(hypothesis)
    return [n for n in (normalise(r) for r in raw) if n]


def ledger_names(ledger: Path = LEDGER) -> dict[str, str]:
    """Normalised name -> ledger id, for EXACT matching only (never closed_match)."""
    out: dict[str, str] = {}
    for line in Path(ledger).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            for name in _ledger_row_names(row):
                out.setdefault(name, row["id"])
    return out


def _contains(tokens: list[str], needle: list[str]) -> bool:
    size = len(needle)
    return any(tokens[i:i + size] == needle for i in range(len(tokens) - size + 1))


def closed_match(idea: str, names: Iterable[str]) -> str | None:
    """The closed name an idea re-runs: equal, or a contiguous token run inside it."""
    norm = normalise(idea)
    tokens = norm.split("-")
    for name in sorted(names):
        bare = name.removeprefix(EXACT_ONLY)
        if bare == norm or (not name.startswith(EXACT_ONLY) and _contains(tokens, bare.split("-"))):
            return bare
    return None
