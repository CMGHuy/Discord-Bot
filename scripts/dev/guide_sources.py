"""Name the guide chapters a diff touches (v235; /close-out Step 5b).

    python scripts/dev/guide_sources.py <base>..<head>

A chapter (docs/guide/NN-<slug>.md) or strategy card (docs/guide/strategies/
*.md) is touched when a changed path equals one of its `sources:` paths or
lies under a source directory. A touched chapter gets its text updated where
behaviour changed and `reviewed_for` bumped, or the close-out commit records
"guide: no reader-visible change". Exit 0 either way; 2 on a bad range, a git
failure or a malformed chapter or card.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.admin.guide.chapters import (Chapter, GuideFormatError,  # noqa: E402
                                           guide_dir, load_chapters, split_source)

NONE_TOUCHED = "guide: no chapter sources touched"


@dataclass(frozen=True)
class Card:
    """A Plan B strategy card: only the two fields touched() reads."""
    path: Path
    sources: tuple[str, ...]


def _norm(path: str) -> str:
    return path.strip().replace("\\", "/").removeprefix("./")


def _covered(source: str, changed: list[str]) -> list[str]:
    target = _norm(split_source(source)[0]).rstrip("/")
    return [path for path in changed if path == target or path.startswith(target + "/")]


def touched(paths: Iterable[str], chapters) -> list[tuple[Chapter, list[str]]]:
    """(document, the changed paths its sources cover) for every document hit, in order."""
    changed = sorted({_norm(path) for path in paths if path.strip()})
    result = []
    for chapter in chapters:
        hits = sorted({hit for source in chapter.sources for hit in _covered(source, changed)})
        if hits:
            result.append((chapter, hits))
    return result


def _card_sources(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---" not in text[3:]:
        raise GuideFormatError(f"{path.name}: front matter must sit between two '---' lines")
    meta = yaml.safe_load(text[4:].split("\n---", 1)[0]) or {}
    sources = meta.get("sources", []) if isinstance(meta, dict) else None
    if not isinstance(sources, list):
        raise GuideFormatError(f"{path.name}: 'sources' must be a list")
    return tuple(str(item).strip() for item in sources)


def load_cards(root: Path | None = None) -> list[Card]:
    """docs/guide/strategies/*.md by file name; [] until Plan B adds the folder."""
    folder = (Path(root) if root is not None else guide_dir()) / "strategies"
    if not folder.is_dir():
        return []
    return [Card(path, _card_sources(path)) for path in sorted(folder.glob("*.md"))]


def changed_paths(rev_range: str) -> list[str]:
    """`git diff --name-only <base>..<head>` at the repo root."""
    if ".." not in rev_range or rev_range.startswith("-"):
        raise ValueError(f"expected <base>..<head>, got {rev_range!r}")
    out = subprocess.run(["git", "diff", "--name-only", rev_range], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise ValueError(out.stderr.strip() or f"git diff failed for {rev_range}")
    return [line for line in out.stdout.splitlines() if line.strip()]


def _label(document) -> str:
    return f"strategies/{document.path.name}" if isinstance(document, Card) else document.path.name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Which guide chapters does a diff touch?")
    parser.add_argument("range", help="<base>..<head>")
    parser.add_argument("--guide-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        paths = changed_paths(args.range)
        documents = [*load_chapters(args.guide_dir), *load_cards(args.guide_dir)]
    except (ValueError, yaml.YAMLError) as exc:   # GuideFormatError is a ValueError
        print(f"guide_sources: {exc}", file=sys.stderr)
        return 2
    hits = touched(paths, documents)
    for document, covered in hits:
        print(f"{_label(document)}: {', '.join(covered)}")
    if not hits:
        print(NONE_TOUCHED)
    return 0


if __name__ == "__main__":
    sys.exit(main())
