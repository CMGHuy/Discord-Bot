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

import yaml

from swingbot import config

FIGURE_RE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$", re.M)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_FILE_GLOB = "[0-9][0-9]-*.md"
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


def _is_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_source_list(value) -> bool:
    return isinstance(value, list) and all(_is_text(item) for item in value)


def _is_slug(value) -> bool:
    return isinstance(value, str) and bool(_SLUG_RE.match(value))


def _is_order(value) -> bool:
    return type(value) is int and 1 <= value <= 99   # `type(...) is int` excludes bool


def _is_version(value) -> bool:
    return isinstance(value, str) and bool(_VERSION_RE.match(value))


#: (key, check, what the key must be) -- table-driven, one rule per row.
_FIELD_RULES = (
    ("title", _is_text, "a non-empty string"),
    ("slug", _is_slug, "lowercase words joined by '-'"),
    ("order", _is_order, "an integer from 1 to 99"),
    ("reviewed_for", _is_version, "an X.Y.Z version string"),
    ("sources", _is_source_list, "a list of non-empty strings"),
)


def _fail(path: Path, problem: str) -> GuideFormatError:
    return GuideFormatError(f"{path.name}: {problem}")


def _split_front_matter(text: str, path: Path) -> tuple[str, str]:
    lines = text.split("\n")
    if lines[0].strip() != "---":
        raise _fail(path, "must open with a '---' front-matter line")
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    raise _fail(path, "front matter has no closing '---' line")


def _load_meta(raw: str, path: Path) -> dict:
    try:
        meta = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise _fail(path, f"front matter is not valid YAML ({exc})") from exc
    if not isinstance(meta, dict):
        raise _fail(path, "front matter must be a mapping of keys")
    return meta


def _check_meta(meta: dict, path: Path) -> None:
    for key, check, wanted in _FIELD_RULES:
        if key not in meta:
            raise _fail(path, f"front matter lacks '{key}'")
        if not check(meta[key]):
            raise _fail(path, f"'{key}' must be {wanted}, got {meta[key]!r}")
    expected = f"{meta['order']:02d}-{meta['slug']}.md"
    if path.name != expected:
        raise _fail(path, f"file name must be {expected} for its order and slug")


def parse_chapter(path: Path) -> Chapter:
    """One chapter file -> Chapter; GuideFormatError names the file on any defect."""
    try:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise _fail(path, f"unreadable ({exc})") from exc
    raw, body = _split_front_matter(text, path)
    meta = _load_meta(raw, path)
    _check_meta(meta, path)
    body = body.lstrip("\n")
    return Chapter(slug=meta["slug"], title=meta["title"].strip(), order=meta["order"],
                   reviewed_for=meta["reviewed_for"],
                   sources=tuple(item.strip() for item in meta["sources"]),
                   body=body, headings=extract_headings(body), path=path)


def _check_unique(chapters: list[Chapter], attr: str) -> None:
    seen: dict[object, Chapter] = {}
    for chapter in chapters:
        value = getattr(chapter, attr)
        if value in seen:
            raise _fail(chapter.path, f"{attr} {value!r} already used by {seen[value].path.name}")
        seen[value] = chapter


def load_chapters(root: Path | None = None) -> list[Chapter]:
    """Every top-level NN-*.md chapter under `root` (default guide_dir()), by order."""
    folder = Path(root) if root is not None else guide_dir()
    if not folder.is_dir():
        return []
    chapters = [parse_chapter(p) for p in sorted(folder.glob(_FILE_GLOB)) if p.is_file()]
    _check_unique(chapters, "slug")
    _check_unique(chapters, "order")
    return sorted(chapters, key=lambda chapter: chapter.order)
