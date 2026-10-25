"""Print one plan part writer's whole context (v193, spec section C).

    python scripts/dev/plan_slice.py <index> <part> [--brief <path>]

Prints the index preamble, ## Global Constraints, ## Handoff (if any) and
## Task ledger; the spec sections the part's ledger rows cite; the brief
sections (## <repo path>) for the files those rows modify, plus ## Traps.
Whatever it cannot find is a trailing `MISSING:` line. Exit 2 on bad usage
or a part with no ledger rows.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_doc  # noqa: E402  (scripts/dev has no __init__.py)

ROOT = Path(__file__).resolve().parents[2]
PART_SUFFIX_RE = re.compile(r"_\d+[a-z]?(-[^.]*)?\.md$")
FILE_ITEM_RE = re.compile(r"(?:\b([CM])\s+)?`([^`]+)`")
INDEX_SECTIONS = ("Global Constraints", "Handoff", "Task ledger")
OPTIONAL_INDEX = ("Handoff",)
EMPTY_REFS = ("", "—", "-")
USAGE = "usage: python scripts/dev/plan_slice.py <index> <part> [--brief <path>]"


def default_brief(index: Path) -> Path:
    base = PART_SUFFIX_RE.sub("", index.name).removesuffix(".md")
    return ROOT / ".superpowers" / "briefs" / f"{base}.md"


def ordered_unique(items) -> list[str]:
    return list(dict.fromkeys(items))


def all_sections(text: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for level in (1, 2, 3, 4):
        merged.update(plan_doc.sections(text, level))
    return merged


def index_blocks(text: str, missing: list[str]) -> list[str]:
    secs = plan_doc.sections(text, 2)
    blocks = [text.split("\n## ", 1)[0]]
    for name in INDEX_SECTIONS:
        if name in secs:
            blocks.append(secs[name])
        elif name not in OPTIONAL_INDEX:
            missing.append(f"MISSING: index section '{name}'")
    return blocks


def spec_blocks(index: Path, text: str, rows: list[dict[str, str]],
                missing: list[str]) -> list[str]:
    spec = plan_doc.spec_path(index, text)
    if spec is None or not spec.is_file():
        missing.append(f"MISSING: spec file {spec}")
        return []
    secs = all_sections(spec.read_text(encoding="utf-8"))
    refs = ordered_unique(r.strip() for row in rows
                          for r in plan_doc.spec_refs(row.get(plan_doc.COL_SPEC, ""))
                          if r.strip() not in EMPTY_REFS)
    headings: list[str] = []
    for ref in refs:
        heading = plan_doc.resolve_ref(ref, list(secs))
        if heading is None:
            missing.append(f"MISSING: spec section '{ref}'")
        else:
            headings.append(heading)
    return [f"===== spec: {spec.name} ====="] + [secs[h] for h in ordered_unique(headings)]


def modified_paths(rows: list[dict[str, str]]) -> list[str]:
    paths = []
    for row in rows:
        kind = "M"
        for m in FILE_ITEM_RE.finditer(row.get(plan_doc.COL_FILES, "")):
            kind = m.group(1) or kind
            path = m.group(2).split(":")[0].strip()
            if kind == "M" and "/" in path:
                paths.append(path)
    return ordered_unique(paths)


def brief_blocks(brief: Path, rows: list[dict[str, str]], missing: list[str]) -> list[str]:
    if not brief.is_file():
        missing.append(f"MISSING: brief file {brief}")
        return []
    secs = plan_doc.sections(brief.read_text(encoding="utf-8"), 2)
    blocks = [f"===== brief: {brief.name} ====="]
    for ref in modified_paths(rows) + ["Traps"]:
        heading = plan_doc.resolve_ref(ref, list(secs))
        if heading is None:
            missing.append(f"MISSING: brief section '{ref}'")
        else:
            blocks.append(secs[heading])
    return blocks


def slice_part(index: Path, part: str, brief: Path | None = None) -> tuple[str, list[str]]:
    text = index.read_text(encoding="utf-8")
    rows = [r for r in plan_doc.ledger_rows(text)
            if r.get(plan_doc.COL_PART, "").strip() == part]
    if not rows:
        raise ValueError(f"plan_slice: no ledger rows for part '{part}' in {index.name}")
    missing: list[str] = []
    ids = ", ".join(r.get(plan_doc.COL_TASK, "?") for r in rows)
    blocks = [f"===== slice: {index.name}, part {part}: {ids} ====="]
    blocks += index_blocks(text, missing)
    blocks += spec_blocks(index, text, rows, missing)
    blocks += brief_blocks(brief or default_brief(index), rows, missing)
    return "".join(b.rstrip("\n") + "\n\n" for b in blocks), missing


def parse_args(argv: list[str]) -> tuple[Path, str, Path | None] | None:
    args, brief = list(argv[1:]), None
    if "--brief" in args:
        k = args.index("--brief")
        if k + 1 >= len(args):
            return None
        brief = Path(args[k + 1])
        del args[k:k + 2]
    if len(args) != 2 or not Path(args[0]).is_file():
        return None
    return Path(args[0]), args[1], brief


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parsed = parse_args(argv)
    if parsed is None:
        print(USAGE)
        return 2
    try:
        text, missing = slice_part(*parsed)
    except ValueError as exc:
        print(exc)
        return 2
    print(text, end="")
    for line in missing:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
