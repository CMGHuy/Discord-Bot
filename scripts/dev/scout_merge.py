#!/usr/bin/env python3
"""v161: merge the generator roles' rows into one ranked scout slate.

This part (TS8) parses the role-output file into ScoutRows -- dropping malformed and
duplicate rows -- and reads the two sources of already-decided names: the
pre-registration ledger and the closed-pre-registrations table of
docs/claude/backtest-methodology.md. TS9 adds the drops against the autopsy JSON,
the ranking, the slate and the CLI. Deterministic; no model, no network."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
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
_FIELD_RE = re.compile(r"^  ([^:]+):\s*(.*)$")
_CELL_RE = re.compile(r"\bcell\s+([^;]+?)\s*(?:;|$)")
_PLAYBOOK_RE = re.compile(r"\bplaybook:?\s+([a-z0-9][a-z0-9-]*)")
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_EVIDENCE_RE = re.compile(
    rf"cell\s+[^;]+;\s*N\s+(?P<n>\d+);\s*weeks\s+(?P<weeks>\d+);\s*"
    rf"Δ net ExpR\s+(?P<delta>{_NUMBER})\s*"
    rf"\[\s*(?P<lo>{_NUMBER})\s*,\s*(?P<hi>{_NUMBER})\s*\];\s*q\s+(?P<q>{_NUMBER})"
    r"(?:\s*\|\s*playbook:?\s+[a-z0-9][a-z0-9-]*)?"
)
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


# ---- v161 TS9: drops, pinning, ranking, slate, CLI ------------------------

# ROOT, LEDGER and METHODOLOGY are TS8's; the slate goes beside the ledger.
DEFAULT_OUT_DIR = ROOT / "docs" / "superpowers" / "results"

EDGE_ORDER = ("expectancy", "harvest", "volume")

# Spec boundary 5, repeated on every slate.
HOLDOUT_REMINDER = (
    "Every autopsy-derived row is exploratory, and the holdout is protected: the "
    "live-book window above overlaps the frozen holdout (HOLDOUT_START 2026-01-01, "
    "scripts/backtest/measure_v104.py). A row picked from this slate and sent to "
    "/prereg must freeze its thresholds and score them on TRAIN/VALIDATION windows "
    "that end before the autopsy window starts, and its pre-registration records "
    "that the holdout is contaminated for that idea (never spent as confirmation). "
    "A /screen route is unaffected (PIT S&P 500 2010-2019 does not overlap)."
)

# Spec boundaries 1 and 2.
BOUNDARY_NOTE = (
    "A slate row is a hypothesis. No gate moves: it never edits code, config, "
    "thresholds or live alerts, and never licenses a re-run of a closed "
    "pre-registration. Every entry or filter idea still needs a `SCREEN-PASS` "
    "row before its spec."
)


def _is_yes(text: str) -> bool:
    return text.strip().lower() == "yes"


def _is_playbook_screen(row: ScoutRow) -> bool:
    return row.playbook_id is not None and row.route.strip().startswith("/screen")


def _lower_bound(cell: dict | None) -> float | None:
    if not cell or not cell.get("ci"):
        return None
    return float(cell["ci"][0])


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _identity_reason(row: ScoutRow, seen: dict[str, str], closed: set[str],
                     ledger: dict[str, str]) -> str | None:
    """Duplicate, ledger, closed-table and edge checks: they need no cell."""
    key = normalise(row.idea)
    if key in seen:
        return f"duplicate of the {seen[key]} row with the same idea"
    if key in ledger:
        return f"matches ledger id {ledger[key]}"
    hit = closed_match(row.idea, closed)
    if hit is not None:
        return f"matches closed pre-registration {hit}"
    if row.edge.strip() not in EDGE_ORDER:
        return f"edge {row.edge.strip()!r} is not one of {', '.join(EDGE_ORDER)}"
    return None


def _finite_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _statistical_reason(cell: dict) -> str | None:
    """Apply evidence thresholds to unrounded JSON, including the q boundary."""
    lower = _lower_bound(cell)
    if _finite_number(lower) is None or lower <= 0:
        return f"cell {cell['id']} Δ lower bound {_signed(lower)} is at or below zero or unavailable"
    q = _finite_number(cell.get("q"))
    if q is None or not 0 <= q <= 0.10:
        return f"cell {cell['id']} q must be finite and between 0 and 0.10 in the autopsy JSON"
    return None


def _quoted_figures_reason(row: ScoutRow, cell: dict) -> str | None:
    """Require the complete Row format and the autopsy Markdown's three decimals."""
    match = _EVIDENCE_RE.fullmatch(row.evidence.strip())
    if match is None:
        return "evidence format must quote cell, N, weeks, Δ net ExpR [CI] and q exactly once"
    values = match.groupdict()
    expected = (("n", "N", cell["n"]), ("weeks", "weeks", cell["weeks"]),
                ("delta", "Δ", cell.get("delta")), ("lo", "CI lower", cell["ci"][0]),
                ("hi", "CI upper", cell["ci"][1]), ("q", "q", cell.get("q")))
    for key, label, raw in expected:
        number = _finite_number(raw)
        if number is None:
            return f"autopsy {label} is unavailable for {cell['id']}"
        printed = number if key in ("n", "weeks") else float(f"{number:.3f}")
        if float(values[key]) != printed:
            return (f"quoted {label} {values[key]} differs from the autopsy {label} "
                    f"{printed:g} for {cell['id']} (invented figure)")
    return None


def _cell_reason(row: ScoutRow, cells: dict[str, dict]) -> str | None:
    """Evidence checks against the autopsy JSON, the only source of figures."""
    cid = row.cell_id
    if cid is None:
        return "cites no autopsy cell and is not a playbook /screen row"
    cell = cells.get(cid)
    if cell is None:
        return f"cell {cid} is not in the autopsy JSON (invented figure)"
    if cell.get("thin"):
        return f"cell {cid} is thin (N {cell['n']}, {cell['weeks']} weeks)"
    if not _is_yes(row.exploratory):
        return "autopsy evidence must be marked exploratory: yes (spec boundary 5)"
    return _statistical_reason(cell) or _quoted_figures_reason(row, cell)


def screen_rows(rows: list[ScoutRow], *, closed: set[str], ledger: dict[str, str],
                cells: dict[str, dict]) -> tuple[list[ScoutRow], list[Drop]]:
    """Drop closed, duplicate and unsupported rows; every drop keeps its reason."""
    kept: list[ScoutRow] = []
    drops: list[Drop] = []
    seen: dict[str, str] = {}
    for row in rows:
        reason = _identity_reason(row, seen, closed, ledger)
        if reason is None and not _is_playbook_screen(row):
            reason = _cell_reason(row, cells)
        if reason is not None:
            drops.append(Drop(idea=row.idea, role=row.role, reason=reason))
            continue
        seen[normalise(row.idea)] = row.role
        kept.append(row)
    return kept, drops


def _rank_key(row: ScoutRow, cells: dict[str, dict]) -> tuple:
    cell = cells.get(row.cell_id) if row.cell_id else None
    lower = _lower_bound(cell)
    edge = row.edge.strip()
    return (
        not _is_yes(row.divergence),                       # divergence pinned first
        EDGE_ORDER.index(edge) if edge in EDGE_ORDER else len(EDGE_ORDER),
        row.manual_actions.strip().lower() != "none",      # manual action ranks down
        -lower if lower is not None else math.inf,         # higher bound first
        -(cell["n"] if cell else 0),                       # then larger N
        normalise(row.idea),                               # deterministic tie-break
    )


def rank(rows: list[ScoutRow], cells: dict[str, dict]) -> list[ScoutRow]:
    return sorted(rows, key=lambda row: _rank_key(row, cells))


def _table_text(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _header_lines(header: dict, autopsy_path: str) -> list[str]:
    window = header.get("window") or ["?", "?"]
    return [
        f"**Autopsy:** `{autopsy_path}`",
        f"**Window:** {window[0]} to {window[1]} · **N:** {header.get('n')} · "
        f"**Cells tested:** {header.get('cells_tested')} · "
        f"**Net of frictions:** {header.get('net_of_frictions')}",
    ]


def _row_block(position: int, row: ScoutRow) -> list[str]:
    pin = " — pinned: live diverges from the plan" if _is_yes(row.divergence) else ""
    lines = [f"### {position}. {row.idea} ({row.role}){pin}", ""]
    lines += [f"- {name}: {getattr(row, name)}" for name in ROW_FIELDS if name != "idea"]
    return lines + [""]


def _drop_lines(drops: list[Drop]) -> list[str]:
    if not drops:
        return ["None."]
    lines = ["| Idea | Role | Reason |", "|---|---|---|"]
    lines += [f"| {_table_text(d.idea)} | {_table_text(d.role)} | {_table_text(d.reason)} |"
              for d in drops]
    return lines


def render_slate(ranked: list[ScoutRow], drops: list[Drop], header: dict, *,
                 date: str, autopsy_path: str) -> str:
    lines = [f"# Scout slate {date}", "", *_header_lines(header, autopsy_path), "",
             f"> {HOLDOUT_REMINDER}", "", BOUNDARY_NOTE, "", "## Ranked", ""]
    if not ranked:
        lines += ["No row survived the merge.", ""]
    for position, row in enumerate(ranked, start=1):
        lines += _row_block(position, row)
    lines += ["## Dropped", "", *_drop_lines(drops)]
    return "\n".join(lines) + "\n"


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Merge scout role outputs into a ranked slate (v161).")
    ap.add_argument("role_output", type=Path, help="role outputs grouped under '## role: <name>' lines")
    ap.add_argument("--autopsy", type=Path, required=True, help="the *-book-autopsy.json of the same run")
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--methodology", type=Path, default=METHODOLOGY)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = json.loads(args.autopsy.read_text(encoding="utf-8"))
    cells = {cell["id"]: cell for cell in report.get("cells", [])}
    rows, parse_drops = parse_rows(args.role_output.read_text(encoding="utf-8"))
    kept, drops = screen_rows(rows, closed=closed_names(args.methodology),
                              ledger=ledger_names(args.ledger), cells=cells)
    ranked = rank(kept, cells)
    all_drops = parse_drops + drops
    slate = render_slate(ranked, all_drops, report.get("header", {}), date=args.date,
                         autopsy_path=_display_path(args.autopsy))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.date}-scout-slate.md"
    out.write_text(slate, encoding="utf-8", newline="\n")
    print(f"scout_merge: {len(ranked)} ranked, {len(all_drops)} dropped -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
