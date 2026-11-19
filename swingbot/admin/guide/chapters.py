"""v235: load the guide's Markdown chapters (docs/guide/NN-<slug>.md).

Each chapter file opens with YAML front matter (title, slug, order,
reviewed_for, sources) parsed by yaml.safe_load, then Markdown. Headings
(## and ### outside code fences) get stable anchors by one algorithm that
scripts/dev/guide_anchors.py and the frontend fixture share: lowercase, drop
everything outside [a-z0-9 _-], whitespace runs to '-', collapse '-', strip
'-', empty -> 'section', repeats -> '-2', '-3', ...

Placeholders ({{name}}) are left untouched here; placeholders.resolve fills
them per request. docs/guide/strategies/ (Plan B cards) is not read here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from swingbot import config

FIGURE_RE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$", re.M)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_HEADING_RE = re.compile(r"^(#{2,3})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(?:```|~~~)")


class GuideFormatError(ValueError):
    """A chapter file the loader refuses; the message names the file."""


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class Chapter:
    slug: str
    title: str
    order: int
    reviewed_for: str
    sources: tuple[str, ...]
    body: str
    headings: tuple[Heading, ...]
    path: Path


def guide_dir() -> Path:
    """docs/guide under the project root, read at call time (tests patch it)."""
    return Path(config._PROJECT_ROOT) / "docs" / "guide"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9 _-]", "", text.lower())
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "section"


def anchor_for(text: str, seen: dict[str, int]) -> str:
    """The anchor for `text`, numbered when `seen` already holds its base."""
    base = _slugify(text)
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}-{count}"


def extract_headings(markdown: str) -> tuple[Heading, ...]:
    """Every ## / ### heading outside a code fence, in document order."""
    seen: dict[str, int] = {}
    headings: list[Heading] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            text = match.group(2).strip()
            headings.append(Heading(len(match.group(1)), text, anchor_for(text, seen)))
    return tuple(headings)


def split_source(entry: str) -> tuple[str, str | None]:
    """'path:symbol' -> (path, symbol); a bare path -> (path, None)."""
    path, sep, symbol = entry.partition(":")
    if not sep:
        return entry.strip(), None
    return path.strip(), symbol.strip() or None
