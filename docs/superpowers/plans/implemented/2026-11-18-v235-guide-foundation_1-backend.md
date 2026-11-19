# v235 — Guide foundation, Part 1: backend (V235-1..V235-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V235-3" -A 400 <this file>`); never read the file whole.

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) (Plan A only)
**Index:** [2026-11-18-v235-guide-foundation_0-index.md](2026-11-18-v235-guide-foundation_0-index.md) — Goal, Global Constraints, `## Parallelisation`, the task ledger (cross-task names and signatures) and `## Handoff` live there and bind every task below.

Scope of this part: the correlation-window constant, the chapter loader (with PyYAML promoted to a runtime dependency), the risk placeholders and the whitelist resolver with its provenance label. Ledger part 1 spans two files so neither passes the 1500-line cap: this file holds V235-1, V235-2, V235-2b, V235-3 and V235-3b; [`_1b-market-api.md`](2026-11-18-v235-guide-foundation_1b-market-api.md) holds V235-4 (market placeholders, alerts per week) and V235-5 (API routes and access rows). V235-2b and V235-3b are the `b` halves of tasks that passed the 20 KB cap.

Shared facts every task below relies on (verified 2026-11-18):

- Config values are module globals read at call time: `getattr(config, "MAX_STOP_LOSS_PCT")`. Field metadata (`max`, select `options`) lives in `config.FIELDS: list[Field]`, matched on `Field.attr` (`swingbot/config.py:75`, `:100`).
- `swingbot/core/infra/swallowed.py:62` `swallowed(log, tag, exc, msg="", *args, level=logging.WARNING, exc_info=False)`. Every new `except Exception` that does not re-raise calls it (`tests/infra/test_swallowed_ratchet.py` lets the repo-wide untagged count only fall).
- `tests/admin/conftest.py` gives `client` (Flask test client; logs in with `{"username": "admin", "password": "admin"}`) and never reloads `swingbot.admin.api_v1.*`; resolve paths per call so tests can monkeypatch.
- Suites: `tests/admin/test_api*.py` → `admin`; other `tests/admin/test_*.py` → `admin-core`; `tests/edge/` → `edge`. No new directory, no `tests/suites.toml` edit.

# Phase 1 — Backend: constant, loader, whitelist, API

### Task V235-1: Correlation window constant

**Model:** haiku — a mechanical, behaviour-preserving constant extraction in one 58-line module with an existing test file.

**Files:**
- Modify: `swingbot/core/edge/correlation.py:14-30` (add `DEFAULT_WINDOW`, use it in two signatures, reword the docstring's "90-day")
- Test: `tests/edge/test_edge_correlation.py` (append tests; existing tests stay unchanged)

**Interfaces:**
- Consumes: nothing.
- Produces: `correlation.DEFAULT_WINDOW = 90` (module constant beside `DEFAULT_THRESHOLD`); `returns_corr(df_a, df_b, window: int = DEFAULT_WINDOW)`; `cluster_exposure(open_trades, candidate_ticker, dfs, balance, *, window: int = DEFAULT_WINDOW, threshold: float = DEFAULT_THRESHOLD, sectors: dict | None = None)`. V235-3 renders `correlation.window` from `DEFAULT_WINDOW` and `correlation.sector_fallback` from `MIN_OVERLAP_BARS`.

Why: spec v215 § Live values says a value hard-coded inside a function is first extracted into a named module constant so a placeholder can read it. `DEFAULT_THRESHOLD = 0.75` and `MIN_OVERLAP_BARS = 30` already exist; the 90-day window is the two literal defaults at `correlation.py:18` and `:28`. Behaviour must not change: `tests/edge/test_edge_correlation.py`'s four existing tests pass untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/edge/test_edge_correlation.py`:

```python
import inspect

from swingbot.core.edge import correlation


def test_default_window_is_a_named_constant_of_ninety():
    assert correlation.DEFAULT_WINDOW == 90


def test_both_signatures_default_to_the_constant():
    rc = inspect.signature(correlation.returns_corr).parameters["window"].default
    ce = inspect.signature(correlation.cluster_exposure).parameters["window"].default
    assert rc == correlation.DEFAULT_WINDOW
    assert ce == correlation.DEFAULT_WINDOW


def test_default_window_matches_the_explicit_ninety():
    a, b = _walk(1, n=300), _walk(2, n=300)
    assert correlation.returns_corr(a, b) == correlation.returns_corr(a, b, window=90)


def test_window_change_through_the_constant_is_read_at_definition_only(monkeypatch):
    # The default is bound when the function is defined: patching the constant
    # later does not change a call that omits `window` (same as a literal 90).
    a, b = _walk(1, n=300), _walk(2, n=300)
    before = correlation.returns_corr(a, b)
    monkeypatch.setattr(correlation, "DEFAULT_WINDOW", 40)
    assert correlation.returns_corr(a, b) == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_correlation.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.edge.correlation' has no attribute 'DEFAULT_WINDOW'` in three of the new tests; the four existing tests and `test_default_window_matches_the_explicit_ninety` pass.

- [ ] **Step 3: Implement**

In `swingbot/core/edge/correlation.py`, replace the module docstring's first sentence block and lines 14-30 as follows (everything else unchanged):

```python
"""Correlation-aware exposure: three 'different' trades that are 0.9-
correlated are one trade at 3x size. Positions whose daily-returns
correlation over the last DEFAULT_WINDOW bars with a candidate exceeds
DEFAULT_THRESHOLD count their heat against the candidate's cluster budget
(CORRELATED_HEAT_CAP_PCT). When price history is too thin to correlate
(fewer than MIN_OVERLAP_BARS overlapping returns), same-sector membership
(universe file tags, E13) is the conservative fallback."""
from __future__ import annotations

import pandas as pd

from swingbot import config
from swingbot.core.edge.heat import trade_risk_pct

MIN_OVERLAP_BARS = 30
DEFAULT_THRESHOLD = 0.75
DEFAULT_WINDOW = 90   # daily returns per side; the guide quotes it (v235)


def returns_corr(df_a: pd.DataFrame, df_b: pd.DataFrame,
                 window: int = DEFAULT_WINDOW) -> float | None:
    ra = df_a["Close"].pct_change().dropna().tail(window)
    rb = df_b["Close"].pct_change().dropna().tail(window)
    joined = pd.concat([ra, rb], axis=1, join="inner").dropna()
    if len(joined) < MIN_OVERLAP_BARS:
        return None
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def cluster_exposure(open_trades: list, candidate_ticker: str,
                     dfs: dict, balance: float, *, window: int = DEFAULT_WINDOW,
                     threshold: float = DEFAULT_THRESHOLD,
                     sectors: dict | None = None) -> dict:
```

The bodies of `cluster_exposure` and `cluster_check` stay byte-identical. Confirm no other caller relies on a positional literal: `git grep -n "returns_corr\|cluster_exposure(" -- swingbot` must show only call sites that pass `window` explicitly or omit it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_correlation.py`
Expected: PASS (8 tests, `0 failed`).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`cluster_exposure` stays at B(10)).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/correlation.py tests/edge/test_edge_correlation.py
git commit -m "refactor(edge): name the 90-bar correlation window DEFAULT_WINDOW (v235 V235-1)"
```

### Task V235-2: Guide package, anchors and headings

**Model:** sonnet — the anchor algorithm here is the contract the frontend fixture and every deep link depend on; it must match the index's rule exactly.

**Files:**
- Create: `swingbot/admin/guide/__init__.py`
- Create: `swingbot/admin/guide/chapters.py` (data types, anchors, headings, sources, figure marker; V235-2b adds parsing and loading to the same file)
- Test: `tests/admin/test_guide_chapters.py` (suite `admin-core`)

**Interfaces:**
- Consumes: `swingbot.config._PROJECT_ROOT` (`swingbot/config.py:53`).
- Produces (final names; V235-2b..V235-7 consume them):
  - `class GuideFormatError(ValueError)`
  - `@dataclass(frozen=True) Heading(level: int, text: str, anchor: str)`
  - `@dataclass(frozen=True) Chapter(slug: str, title: str, order: int, reviewed_for: str, sources: tuple[str, ...], body: str, headings: tuple[Heading, ...], path: Path)`. `body` is the Markdown after the front matter with placeholders unresolved; `headings` come from that raw body (V235-2b fills both).
  - `guide_dir() -> Path` = `Path(config._PROJECT_ROOT) / "docs" / "guide"`, read at call time.
  - `anchor_for(text: str, seen: dict[str, int]) -> str`: the index's anchor algorithm; mutates `seen`.
  - `extract_headings(markdown: str) -> tuple[Heading, ...]`: `##`/`###` lines outside code fences, anchors unique per call.
  - `split_source(entry: str) -> tuple[str, str | None]`: `"path:symbol"` → `(path, symbol)`; no colon → `(path, None)`.
  - `FIGURE_RE = re.compile(r"^<!-- figure:([a-z0-9-]+) -->$", re.M)`
  - Module-private, used by V235-2b: `_SLUG_RE`, `_VERSION_RE`.

Anchor algorithm (index Global Constraints, final): lowercase; drop every character outside `[a-z0-9 _-]`; runs of whitespace become `-`; collapse repeated `-`; strip leading/trailing `-`; empty becomes `section`; a repeat within one chapter gets `-2`, `-3`, …. Headings are `##` and `###` only (the page anchors rendered `h2`/`h3` in this order, V236-3); a `#` heading or `####` is not a section; a closing `##` sequence needs a space before it (CommonMark), so `C#` keeps its `#`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_guide_chapters.py`:

```python
"""v235 V235-2/V235-2b: the guide chapter loader (docs/guide/NN-<slug>.md)."""
from pathlib import Path

import pytest

from swingbot import config
from swingbot.admin.guide import chapters as ch


# --- anchors -----------------------------------------------------------------

@pytest.mark.parametrize("text, anchor", [
    ("What the bot is (and isn't)", "what-the-bot-is-and-isnt"),
    ("Sizing & risk", "sizing-risk"),
    ("Break & Retest", "break-retest"),
    ("Support/Resistance", "supportresistance"),
    ("  --Hello__World--  ", "hello__world"),
    ("The 2% rule — three limits", "the-2-rule-three-limits"),
    ("`MAX_STOP_LOSS_PCT`", "max_stop_loss_pct"),
    ("!!!", "section"),
    ("", "section"),
])
def test_anchor_algorithm(text, anchor):
    assert ch.anchor_for(text, {}) == anchor


def test_repeated_anchor_gets_numbered_suffixes():
    seen: dict[str, int] = {}
    assert [ch.anchor_for("Notes", seen) for _ in range(3)] == ["notes", "notes-2", "notes-3"]
    assert ch.anchor_for("Other", seen) == "other"


# --- headings ----------------------------------------------------------------

def test_extract_headings_takes_h2_and_h3_outside_fences_only():
    md = (
        "# Title is not a section\n"
        "## First\n"
        "Text ## not a heading\n"
        "### Sub one ###\n"
        "#### Too deep\n"
        "```\n## inside a fence\n```\n"
        "~~~md\n### also fenced\n~~~\n"
        "## First\n"
        "##No space is not a heading\n"
    )
    assert ch.extract_headings(md) == (
        ch.Heading(2, "First", "first"),
        ch.Heading(3, "Sub one", "sub-one"),
        ch.Heading(2, "First", "first-2"),
    )


def test_extract_headings_keeps_a_hash_inside_the_text():
    assert ch.extract_headings("## Notes on C#\n") == (ch.Heading(2, "Notes on C#", "notes-on-c"),)


def test_extract_headings_empty_body():
    assert ch.extract_headings("") == ()


# --- sources, figures, location ----------------------------------------------

def test_split_source():
    assert ch.split_source("swingbot/config.py:RISK_PER_TRADE_PCT") == (
        "swingbot/config.py", "RISK_PER_TRADE_PCT")
    assert ch.split_source("swingbot/core/edge/sizing.py") == ("swingbot/core/edge/sizing.py", None)
    assert ch.split_source(" swingbot/config.py : X ") == ("swingbot/config.py", "X")


def test_figure_marker_regex():
    md = "Intro\n<!-- figure:pipeline -->\nMore\n  <!-- figure:indented -->\n"
    assert ch.FIGURE_RE.findall(md) == ["pipeline"]


def test_guide_dir_reads_the_project_root_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    assert ch.guide_dir() == Path(tmp_path) / "docs" / "guide"


def test_chapter_is_frozen():
    chapter = ch.Chapter(slug="a", title="A", order=1, reviewed_for="2.19.2", sources=(),
                         body="", headings=(), path=Path("01-a.md"))
    with pytest.raises(AttributeError):
        chapter.slug = "b"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapters.py`
Expected: FAIL at collection: `ModuleNotFoundError: No module named 'swingbot.admin.guide'`.

- [ ] **Step 3: Create the package and the first half of the loader**

Create `swingbot/admin/guide/__init__.py`:

```python
"""v235: the Insights -> Guide content layer.

chapters.py loads docs/guide/NN-<slug>.md; placeholders.py resolves the fixed
{{name}} whitelist (live_risk.py, live_market.py). Nothing here writes, and
nothing here imports swingbot.admin.app: api_v1/guide.py is the only caller.
"""
```

Create `swingbot/admin/guide/chapters.py`:

```python
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
```

`_SLUG_RE` and `_VERSION_RE` are defined now and first used by V235-2b; `python -m pyflakes` does not flag unused module-level names.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapters.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`extract_headings` is the largest new function, about 5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/__init__.py swingbot/admin/guide/chapters.py tests/admin/test_guide_chapters.py
git commit -m "feat(guide): guide package, heading anchors and source entries (v235 V235-2)"
```

### Task V235-2b: Chapter parsing, loading and runtime PyYAML

**Model:** sonnet — front-matter validation rules and duplicate checks that every later chapter, the content test and the API rely on.

**Files:**
- Modify: `requirements.txt:94-103` (move `PyYAML==6.0.3` out of "Test-only dependencies" into the runtime block)
- Modify: `swingbot/admin/guide/chapters.py` (created by V235-2: add `import yaml`, the field rules, `parse_chapter`, `load_chapters`)
- Test: `tests/admin/test_guide_chapters.py` (created by V235-2: append)

**Interfaces:**
- Consumes (V235-2): `GuideFormatError`, `Chapter`, `extract_headings`, `guide_dir`, `_SLUG_RE`, `_VERSION_RE`.
- Produces (final; V235-5..V235-7 consume them):
  - `parse_chapter(path: Path) -> Chapter`: raises `GuideFormatError` whose message starts with the file name.
  - `load_chapters(root: Path | None = None) -> list[Chapter]`: top-level `NN-*.md` only (`docs/guide/strategies/` is never read here), sorted by `order`; a missing directory returns `[]`; a duplicate slug or order raises `GuideFormatError`.

Rules the loader enforces (spec v215 § Content; index Global Constraints, Handoff 1):
- The file opens with a `---` line and the front matter closes with a second `---` line; it parses with `yaml.safe_load` (never `yaml.load`) into a mapping.
- Required keys: `title` (non-empty string), `slug` (`^[a-z0-9]+(-[a-z0-9]+)*$`), `order` (int 1–99, not a bool), `reviewed_for` (string `X.Y.Z`; an unquoted `2.19` loads as a float and is rejected), `sources` (list of non-empty strings; may be empty).
- The file name equals `f"{order:02d}-{slug}.md"`, so `docs/guide/NN-<slug>.md` cannot drift from its front matter.
- CRLF files read the same as LF files.

- [ ] **Step 1: Write the failing tests**

Append to `tests/admin/test_guide_chapters.py`:

```python
def _write(root: Path, name: str, *, front: str | None = None, body: str = "Text.\n",
           title="Title", slug="what-it-is", order=1, reviewed_for="2.19.2",
           sources=("swingbot/config.py",)) -> Path:
    if front is None:
        src = "".join(f"  - {s}\n" for s in sources)
        front = (f"title: {title}\nslug: {slug}\norder: {order}\n"
                 f"reviewed_for: {reviewed_for}\nsources:\n{src}")
    path = root / name
    path.write_text(f"---\n{front}---\n{body}", encoding="utf-8")
    return path


# --- parse_chapter -----------------------------------------------------------

def test_parse_chapter_reads_front_matter_body_and_headings(tmp_path):
    path = _write(tmp_path, "01-what-it-is.md", title="What the bot is",
                  sources=("swingbot/config.py:MAX_STOP_LOSS_PCT", "swingbot/core/edge/sizing.py"),
                  body="\n> **In plain words** paper only.\n\n## The notice\n\nText.\n")
    chapter = ch.parse_chapter(path)
    assert chapter.slug == "what-it-is"
    assert chapter.title == "What the bot is"
    assert chapter.order == 1
    assert chapter.reviewed_for == "2.19.2"
    assert chapter.sources == ("swingbot/config.py:MAX_STOP_LOSS_PCT", "swingbot/core/edge/sizing.py")
    assert chapter.body.startswith("> **In plain words**")
    assert chapter.headings == (ch.Heading(2, "The notice", "the-notice"),)
    assert chapter.path == path


def test_parse_chapter_accepts_crlf_and_empty_sources(tmp_path):
    path = tmp_path / "03-pipeline.md"
    path.write_bytes(b"---\r\ntitle: Pipeline\r\nslug: pipeline\r\norder: 3\r\n"
                     b"reviewed_for: 2.19.2\r\nsources: []\r\n---\r\n## Boxes\r\n")
    chapter = ch.parse_chapter(path)
    assert chapter.sources == ()
    assert chapter.headings == (ch.Heading(2, "Boxes", "boxes"),)


@pytest.mark.parametrize("front, message", [
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\n", "sources"),
    ("title: ''\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n", "title"),
    ("title: T\nslug: What It Is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n", "slug"),
    ("title: T\nslug: what-it-is\norder: true\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: '1'\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: 0\nreviewed_for: 2.19.2\nsources: []\n", "order"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19\nsources: []\n", "reviewed_for"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: a.py\n", "sources"),
    ("title: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: ['']\n", "sources"),
    ("- just\n- a list\n", "mapping"),
    ("title: [unclosed\n", "YAML"),
])
def test_parse_chapter_rejects_bad_front_matter(tmp_path, front, message):
    path = _write(tmp_path, "01-what-it-is.md", front=front)
    with pytest.raises(ch.GuideFormatError, match=message) as info:
        ch.parse_chapter(path)
    assert str(info.value).startswith("01-what-it-is.md: ")


def test_parse_chapter_requires_opening_and_closing_markers(tmp_path):
    no_open = tmp_path / "01-what-it-is.md"
    no_open.write_text("title: T\n", encoding="utf-8")
    with pytest.raises(ch.GuideFormatError, match="must open"):
        ch.parse_chapter(no_open)
    unclosed = tmp_path / "02-reading-an-alert.md"
    unclosed.write_text("---\ntitle: T\n", encoding="utf-8")
    with pytest.raises(ch.GuideFormatError, match="closing"):
        ch.parse_chapter(unclosed)


def test_parse_chapter_requires_the_file_name_to_match(tmp_path):
    path = _write(tmp_path, "02-what-it-is.md", order=1)
    with pytest.raises(ch.GuideFormatError, match="01-what-it-is.md"):
        ch.parse_chapter(path)


# --- load_chapters -----------------------------------------------------------

def test_load_chapters_sorts_by_order_and_skips_non_chapters(tmp_path):
    _write(tmp_path, "12-glossary.md", slug="glossary", order=12)
    _write(tmp_path, "03-pipeline.md", slug="pipeline", order=3)
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    (tmp_path / "README.md").write_text("not a chapter", encoding="utf-8")
    (tmp_path / "strategies").mkdir()
    _write(tmp_path / "strategies", "01-rsi.md", slug="rsi", order=1)
    assert [c.slug for c in ch.load_chapters(tmp_path)] == ["what-it-is", "pipeline", "glossary"]


def test_load_chapters_missing_directory_is_empty(tmp_path):
    assert ch.load_chapters(tmp_path / "absent") == []


def test_load_chapters_rejects_duplicate_slug(tmp_path):
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    _write(tmp_path, "02-what-it-is.md", slug="what-it-is", order=2)
    with pytest.raises(ch.GuideFormatError, match="slug 'what-it-is'"):
        ch.load_chapters(tmp_path)


def test_load_chapters_rejects_duplicate_order(tmp_path):
    _write(tmp_path, "01-what-it-is.md", slug="what-it-is", order=1)
    _write(tmp_path, "01-pipeline.md", slug="pipeline", order=1)
    with pytest.raises(ch.GuideFormatError, match="order 1 already used"):
        ch.load_chapters(tmp_path)


def test_load_chapters_defaults_to_guide_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_PROJECT_ROOT", str(tmp_path))
    folder = tmp_path / "docs" / "guide"
    folder.mkdir(parents=True)
    _write(folder, "01-what-it-is.md")
    assert [c.slug for c in ch.load_chapters()] == ["what-it-is"]


# --- runtime dependency ------------------------------------------------------

def test_pyyaml_is_a_pinned_runtime_dependency():
    text = (Path(config._PROJECT_ROOT) / "requirements.txt").read_text(encoding="utf-8")
    runtime, _, test_only = text.partition("# Test-only dependencies")
    assert "PyYAML==6.0.3" in runtime.splitlines()
    assert "PyYAML" not in test_only
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapters.py`
Expected: FAIL: `AttributeError: module 'swingbot.admin.guide.chapters' has no attribute 'parse_chapter'` (and `load_chapters`); `test_pyyaml_is_a_pinned_runtime_dependency` fails on `"PyYAML" not in test_only`. V235-2's tests still pass.

- [ ] **Step 3: Move PyYAML into the runtime block of `requirements.txt`**

Replace the block from `alembic==1.16.5` through `PyYAML==6.0.3` (currently lines 94-103) with:

```text
alembic==1.16.5

# Guide chapter front matter (swingbot/admin/guide/chapters.py, v235): parsed
# with yaml.safe_load only. tests/dev/test_suites.py also reads
# .github/workflows/deploy.yml with it; CI installs only this file.
PyYAML==6.0.3

# Test-only dependencies (not needed at bot runtime)
pytest>=8.0
# Parallel test execution. Opt-in via `pytest -n auto` (12 cores -> ~3min suite
# drops well under a minute); deliberately NOT in pytest.ini addopts, see that file.
pytest-xdist>=3.8
```

Everything from `# Static crash-class gate` down stays as it is. Check: `python -c "import yaml; print(yaml.__version__)"` prints `6.0.3`.

- [ ] **Step 4: Add parsing and loading to `chapters.py`**

Add `import yaml` to the imports (after `from pathlib import Path`, separated as a third-party import):

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from swingbot import config
```

Add `_FILE_GLOB` beside the other module constants:

```python
_FILE_GLOB = "[0-9][0-9]-*.md"
```

Append to the end of the module:

```python
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
```

Messages the tests match: a duplicate slug reads `02-what-it-is.md: slug 'what-it-is' already used by 01-what-it-is.md`; a duplicate order reads `01-what-it-is.md: order 1 already used by 01-pipeline.md` (`repr` of an int has no quotes).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapters.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: PASS (it still imports `yaml`; only the requirements block moved).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`_check_meta` is the largest new function, about 5).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt swingbot/admin/guide/chapters.py tests/admin/test_guide_chapters.py
git commit -m "feat(guide): parse chapter front matter with yaml.safe_load; PyYAML runtime pin (v235 V235-2b)"
```

### Task V235-3: Risk and sizing placeholders

**Model:** sonnet — eighteen live values read from config, `Field` metadata and module constants, with wording that must stay accurate to `gap_sizing.py` and `correlation.py`.

**Files:**
- Create: `swingbot/admin/guide/live_risk.py`
- Test: `tests/admin/test_guide_placeholders.py` (suite `admin-core`; V235-3b appends the resolver tests)

**Interfaces:**
- Consumes: `correlation.DEFAULT_WINDOW` (V235-1), `correlation.DEFAULT_THRESHOLD`, `correlation.MIN_OVERLAP_BARS` (`swingbot/core/edge/correlation.py`); `sizing.KELLY_FRACTION_CAP`, `RISK_FLOOR_PCT`, `RISK_CEILING_PCT` (`swingbot/core/edge/sizing.py:157-159`); `gap_sizing.LOOKBACK = 250`, `MIN_UP_GAPS = 60`, `MIN_DOWN_GAPS = 60`, `RULE_GAP = "gap_p99"` (`swingbot/core/planning/gap_sizing.py:26-31`); `config.FIELDS` / `Field.attr`, `.max`, `.options`, `.sensitive`; `swingbot.admin.helpers.get_versions() -> dict` (`helpers.py:364`).
- Produces (final; V235-3b merges it into `PLACEHOLDERS`): `live_risk.RISK_PLACEHOLDERS: dict[str, Callable[[], str]]` with exactly these 18 names: `MAX_STOP_LOSS_PCT`, `MIN_STOP_DISTANCE_PCT`, `CLAMP_STOP_TO_HARD_CAP`, `RISK_PER_TRADE_PCT`, `RISK_PER_TRADE_PCT.max`, `MAX_RISK_AMOUNT_ABSOLUTE`, `PORTFOLIO_HEAT_CAP_PCT`, `CORRELATED_HEAT_CAP_PCT`, `SECTOR_HEAT_CAP_PCT`, `POSITION_SIZING_MODE`, `correlation.threshold`, `correlation.window`, `correlation.sector_fallback`, `sizing.kelly_cap`, `sizing.risk_floor`, `sizing.risk_ceiling`, `sizing.gap`, `version.bot`.

Rendered forms (each value read at call time from config or the module constant, never cached; config globals follow the SIGHUP hot reload):

| Name | Renders (defaults today) |
|---|---|
| `MAX_STOP_LOSS_PCT`, `MIN_STOP_DISTANCE_PCT`, `RISK_PER_TRADE_PCT`, the three `*_HEAT_CAP_PCT` | `2%`, `1.75%`, `1%`, `6%`, `3%`, `3%` (`f"{v:g}%"`) |
| `RISK_PER_TRADE_PCT.max` | `2%` (the `Field.max` of `RISK_PER_TRADE_PCT`) |
| `CLAMP_STOP_TO_HARD_CAP` | `on` / `off` |
| `MAX_RISK_AMOUNT_ABSOLUTE` | `$100` (`$62.50` when not whole; `$1,500` with a thousands separator) |
| `POSITION_SIZING_MODE` | ``Fixed risk % per trade (`risk_pct`)``: the option label from `Field.options`, the raw value in backticks; an unknown value renders as itself |
| `correlation.threshold` / `.window` / `.sector_fallback` | `0.75` / `90 trading days` / a sentence naming `MIN_OVERLAP_BARS` (30) and the same-sector rule (`correlation.py:39-42`) |
| `sizing.kelly_cap` / `.risk_floor` / `.risk_ceiling` | `0.25 of full Kelly` / `0.25%` / `2%` |
| `sizing.gap` | a Markdown table, one row per side, from `SHORT_GAP_SIZING`, `LONG_GAP_SIZING`, `RULE_GAP`, `LOOKBACK`, `MIN_UP_GAPS`, `MIN_DOWN_GAPS`, then one sentence on the too-few-gaps fallback |
| `version.bot` | `2.19.2` (`helpers.get_versions()["bot"]`) |

What `sizing.gap` describes (from `gap_sizing.py:1-75` and the `SHORT_GAP_SIZING`/`LONG_GAP_SIZING` Field help): a side with gap-aware sizing on is sized on the larger of the stop distance and entry × the ticker's p99 adverse gap over the last `LOOKBACK` completed bars; the p99 counts only with at least `MIN_UP_GAPS` up-gaps (short) or `MIN_DOWN_GAPS` down-gaps (long), otherwise the plan is sized on the stop; the stop never moves and R stays measured on the stop. A side with it off is sized on the stop distance only.

No function in this module takes a name or reads a config attribute that is not spelled out in it, so no secret is reachable (V235-3b adds the resolver-level checks).

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_guide_placeholders.py`:

```python
"""v235 V235-3/V235-3b: the guide's risk placeholders, whitelist and resolver."""
import pytest

from swingbot import config
from swingbot.admin.guide import live_risk

RISK_NAMES = {
    "MAX_STOP_LOSS_PCT", "MIN_STOP_DISTANCE_PCT", "CLAMP_STOP_TO_HARD_CAP",
    "RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE",
    "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT", "SECTOR_HEAT_CAP_PCT",
    "POSITION_SIZING_MODE", "correlation.threshold", "correlation.window",
    "correlation.sector_fallback", "sizing.kelly_cap", "sizing.risk_floor",
    "sizing.risk_ceiling", "sizing.gap", "version.bot",
}


def _risk(name: str) -> str:
    return live_risk.RISK_PLACEHOLDERS[name]()


# --- the table ---------------------------------------------------------------

def test_risk_table_has_exactly_the_planned_names():
    assert set(live_risk.RISK_PLACEHOLDERS) == RISK_NAMES


@pytest.mark.parametrize("name", sorted(RISK_NAMES))
def test_every_risk_placeholder_renders_plain_text(name):
    out = _risk(name)
    assert isinstance(out, str) and out.strip()
    assert "{{" not in out and "}}" not in out


# --- values ------------------------------------------------------------------

@pytest.mark.parametrize("attr, value, text", [
    ("MAX_STOP_LOSS_PCT", 2.0, "2%"),
    ("MAX_STOP_LOSS_PCT", 1.5, "1.5%"),
    ("MIN_STOP_DISTANCE_PCT", 1.75, "1.75%"),
    ("RISK_PER_TRADE_PCT", 1.0, "1%"),
    ("PORTFOLIO_HEAT_CAP_PCT", 6.0, "6%"),
    ("CORRELATED_HEAT_CAP_PCT", 3.0, "3%"),
    ("SECTOR_HEAT_CAP_PCT", 2.5, "2.5%"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 100.0, "$100"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 62.5, "$62.50"),
    ("MAX_RISK_AMOUNT_ABSOLUTE", 1500.0, "$1,500"),
    ("CLAMP_STOP_TO_HARD_CAP", True, "on"),
    ("CLAMP_STOP_TO_HARD_CAP", False, "off"),
])
def test_config_values_are_read_at_call_time(monkeypatch, attr, value, text):
    monkeypatch.setattr(config, attr, value)
    assert _risk(attr) == text


def test_risk_per_trade_max_comes_from_the_field():
    field = next(f for f in config.FIELDS if f.attr == "RISK_PER_TRADE_PCT")
    assert _risk("RISK_PER_TRADE_PCT.max") == f"{float(field.max):g}%"


@pytest.mark.parametrize("mode, text", [
    ("risk_pct", "Fixed risk % per trade (`risk_pct`)"),
    ("vol_target", "Volatility-targeted (portfolio vol budget) (`vol_target`)"),
    ("unheard_of", "unheard_of (`unheard_of`)"),
])
def test_sizing_mode_uses_the_option_label(monkeypatch, mode, text):
    monkeypatch.setattr(config, "POSITION_SIZING_MODE", mode)
    assert _risk("POSITION_SIZING_MODE") == text


def test_correlation_values_come_from_the_module():
    from swingbot.core.edge import correlation
    assert _risk("correlation.threshold") == "0.75"
    assert _risk("correlation.window") == f"{correlation.DEFAULT_WINDOW} trading days"
    fallback = _risk("correlation.sector_fallback")
    assert str(correlation.MIN_OVERLAP_BARS) in fallback and "sector" in fallback


def test_correlation_window_follows_the_constant(monkeypatch):
    from swingbot.core.edge import correlation
    monkeypatch.setattr(correlation, "DEFAULT_WINDOW", 60)
    assert _risk("correlation.window") == "60 trading days"


def test_kelly_and_risk_bounds():
    assert _risk("sizing.kelly_cap") == "0.25 of full Kelly"
    assert _risk("sizing.risk_floor") == "0.25%"
    assert _risk("sizing.risk_ceiling") == "2%"


def test_gap_table_short_on_long_off(monkeypatch):
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    table = _risk("sizing.gap")
    assert table.splitlines()[0] == "| Side | Gap-aware sizing | Sized on |"
    assert "| Short | on | the larger of the stop distance and entry × the ticker's p99 up-gap" in table
    assert "over the last 250 completed bars (needs at least 60 up-gaps) |" in table
    assert "| Long | off | the stop distance only |" in table
    assert "sized on the stop" in table


def test_gap_table_follows_the_switches_and_constants(monkeypatch):
    from swingbot.core.planning import gap_sizing
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", False)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(gap_sizing, "LOOKBACK", 120)
    table = _risk("sizing.gap")
    assert "| Short | off | the stop distance only |" in table
    assert "p99 down-gap over the last 120 completed bars (needs at least 60 down-gaps) |" in table


def test_version_bot(monkeypatch):
    from swingbot.admin import helpers
    monkeypatch.setattr(helpers, "get_versions", lambda: {"ui": "1.0.0", "bot": "9.8.7"})
    assert _risk("version.bot") == "9.8.7"


# --- secrets -----------------------------------------------------------------

def test_no_sensitive_field_value_reaches_a_risk_placeholder(monkeypatch):
    sensitive = [f for f in config.FIELDS if f.sensitive]
    assert sensitive, "config.FIELDS should mark at least one secret"
    for f in sensitive:
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
        assert f.attr not in live_risk.RISK_PLACEHOLDERS
    rendered = "\n".join(_risk(name) for name in sorted(RISK_NAMES))
    assert "SENTINEL-" not in rendered
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: FAIL at collection: `ImportError: cannot import name 'live_risk' from 'swingbot.admin.guide'`.

- [ ] **Step 3: Implement the risk table**

Before writing, confirm the constants: `git grep -n "^KELLY_FRACTION_CAP\|^RISK_FLOOR_PCT\|^RISK_CEILING_PCT" swingbot/core/edge/sizing.py` and `git grep -n "^LOOKBACK\|^MIN_UP_GAPS\|^MIN_DOWN_GAPS\|^RULE_GAP" swingbot/core/planning/gap_sizing.py` each print their lines.

Create `swingbot/admin/guide/live_risk.py`:

```python
"""v235: risk and sizing placeholders for the guide.

Every value is read when the placeholder renders (config globals follow the
SIGHUP hot reload; module constants are read by attribute), so a changed
default can never leave stale prose. Only names in RISK_PLACEHOLDERS exist:
no function here takes a name, and nothing reads a config attribute that is
not spelled out below.
"""
from __future__ import annotations

from typing import Callable

from swingbot import config
from swingbot.core.edge import correlation, sizing
from swingbot.core.planning import gap_sizing


def _num(value) -> str:
    return f"{float(value):g}"


def _pct(value) -> str:
    return f"{_num(value)}%"


def _flag(value) -> str:
    return "on" if value else "off"


def _money(value) -> str:
    amount = float(value)
    return f"${amount:,.0f}" if amount.is_integer() else f"${amount:,.2f}"


def _field(attr: str) -> config.Field:
    return next(f for f in config.FIELDS if f.attr == attr)


def _cfg_pct(attr: str) -> Callable[[], str]:
    return lambda: _pct(getattr(config, attr))


def _risk_max() -> str:
    return _pct(_field("RISK_PER_TRADE_PCT").max)


def _sizing_mode() -> str:
    value = config.POSITION_SIZING_MODE
    label = dict(_field("POSITION_SIZING_MODE").options).get(value, value)
    return f"{label} (`{value}`)"


def _sector_fallback() -> str:
    return (f"when two tickers have fewer than {correlation.MIN_OVERLAP_BARS} overlapping "
            "daily returns, sharing a sector counts as correlated")


def _gap_basis(on: bool, gap_word: str, minimum: int) -> str:
    if not on:
        return "the stop distance only"
    p_rule = gap_sizing.RULE_GAP.removeprefix("gap_")
    return (f"the larger of the stop distance and entry × the ticker's {p_rule} {gap_word} "
            f"over the last {gap_sizing.LOOKBACK} completed bars "
            f"(needs at least {minimum} {gap_word}s)")


def _gap_table() -> str:
    short_on, long_on = bool(config.SHORT_GAP_SIZING), bool(config.LONG_GAP_SIZING)
    rows = [
        "| Side | Gap-aware sizing | Sized on |",
        "|---|---|---|",
        f"| Short | {_flag(short_on)} | {_gap_basis(short_on, 'up-gap', gap_sizing.MIN_UP_GAPS)} |",
        f"| Long | {_flag(long_on)} | {_gap_basis(long_on, 'down-gap', gap_sizing.MIN_DOWN_GAPS)} |",
    ]
    note = ("With fewer gaps on record the plan is sized on the stop. The stop itself never "
            "moves and R is always measured on the stop; only the share count can shrink.")
    return "\n".join(rows) + "\n\n" + note


def _bot_version() -> str:
    from swingbot.admin import helpers   # call time: tests/admin/conftest.py reloads helpers
    return str(helpers.get_versions()["bot"])


RISK_PLACEHOLDERS: dict[str, Callable[[], str]] = {
    "MAX_STOP_LOSS_PCT": _cfg_pct("MAX_STOP_LOSS_PCT"),
    "MIN_STOP_DISTANCE_PCT": _cfg_pct("MIN_STOP_DISTANCE_PCT"),
    "CLAMP_STOP_TO_HARD_CAP": lambda: _flag(config.CLAMP_STOP_TO_HARD_CAP),
    "RISK_PER_TRADE_PCT": _cfg_pct("RISK_PER_TRADE_PCT"),
    "RISK_PER_TRADE_PCT.max": _risk_max,
    "MAX_RISK_AMOUNT_ABSOLUTE": lambda: _money(config.MAX_RISK_AMOUNT_ABSOLUTE),
    "PORTFOLIO_HEAT_CAP_PCT": _cfg_pct("PORTFOLIO_HEAT_CAP_PCT"),
    "CORRELATED_HEAT_CAP_PCT": _cfg_pct("CORRELATED_HEAT_CAP_PCT"),
    "SECTOR_HEAT_CAP_PCT": _cfg_pct("SECTOR_HEAT_CAP_PCT"),
    "POSITION_SIZING_MODE": _sizing_mode,
    "correlation.threshold": lambda: _num(correlation.DEFAULT_THRESHOLD),
    "correlation.window": lambda: f"{correlation.DEFAULT_WINDOW} trading days",
    "correlation.sector_fallback": _sector_fallback,
    "sizing.kelly_cap": lambda: f"{_num(sizing.KELLY_FRACTION_CAP)} of full Kelly",
    "sizing.risk_floor": lambda: _pct(sizing.RISK_FLOOR_PCT),
    "sizing.risk_ceiling": lambda: _pct(sizing.RISK_CEILING_PCT),
    "sizing.gap": _gap_table,
    "version.bot": _bot_version,
}
```

If `python -c "import swingbot.admin.guide.live_risk"` reports a circular import through `gap_sizing → account`, move `from swingbot.core.planning import gap_sizing` inside `_gap_basis` and `_gap_table` (a call-time import); the tests stay the same, because they patch the module object `swingbot.core.planning.gap_sizing` either way.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/live_risk.py tests/admin/test_guide_placeholders.py
git commit -m "feat(guide): risk and sizing placeholder values read live from config (v235 V235-3)"
```

### Task V235-3b: Placeholder registry, resolver and provenance label

**Model:** sonnet — the guide's security boundary: only listed names resolve, malformed or unknown `{{…}}` fail before any substitution, and no secret is reachable.

**Files:**
- Create: `swingbot/admin/guide/placeholders.py`
- Test: `tests/admin/test_guide_placeholders.py` (created by V235-3: append, and extend its import line)

**Interfaces:**
- Consumes: `live_risk.RISK_PLACEHOLDERS` (V235-3).
- Produces (final; consumed by V235-4..V235-7 and Plans B/C):
  - `PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")`
  - `class UnknownPlaceholder(KeyError)` with `.name: str`; `str(exc)` = `"unknown guide placeholder: <name>"`.
  - `_merge(*tables) -> Mapping[str, Callable[[], str]]`: a `MappingProxyType`; a name in two tables raises `ValueError("guide placeholder defined twice: [...]")`. V235-4 calls it with both tables.
  - `PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(RISK_PLACEHOLDERS)` (read-only); V235-4 changes it to `_merge(RISK_PLACEHOLDERS, MARKET_PLACEHOLDERS)`.
  - `names_in(markdown: str) -> list[str]`: well-formed placeholder names in document order, repeats kept.
  - `resolve(markdown: str) -> str`: every `{{…}}` (any content, across lines) must strip to a registered name, or `UnknownPlaceholder(<stripped content>)` is raised before anything is substituted; values are computed per call and never re-scanned.
  - `provenance_label(*, source: str, n: int, run_date: str, costs_included: bool) -> str` = `"Source: <source>; N = <n>; as of <run_date>; costs included|costs not included; before tax"` (index Global Constraints: every performance figure carries it).

Why a whole-text pre-check: a regex substitution alone would leave an unmatched form such as `{{ MAX_STOP_LOSS_PCT + 1 }}` or `{{bad name}}` in the output as raw text; the spec forbids serving raw `{{…}}`. `resolve` therefore scans every `{{…}}` first and refuses the chapter. `resolve` reads the module global `PLACEHOLDERS` at call time, so V235-5's tests could swap it, and V235-4's merge is picked up with no other change.

- [ ] **Step 1: Write the failing tests**

In `tests/admin/test_guide_placeholders.py`, change the import line to:

```python
from swingbot.admin.guide import live_risk, placeholders as ph
```

and append:

```python
def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


# --- the registry ------------------------------------------------------------

def test_every_risk_name_is_registered():
    assert RISK_NAMES <= set(ph.PLACEHOLDERS)


@pytest.mark.parametrize("name", sorted(RISK_NAMES))
def test_resolve_renders_each_risk_name_like_the_table(name):
    assert _render(name) == _risk(name)


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        ph.PLACEHOLDERS["DISCORD_TOKEN"] = lambda: "x"


def test_merge_refuses_a_name_defined_twice():
    with pytest.raises(ValueError, match="defined twice"):
        ph._merge({"a": lambda: "1"}, {"a": lambda: "2"})


# --- resolve -----------------------------------------------------------------

def test_resolve_substitutes_every_occurrence(monkeypatch):
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    monkeypatch.setattr(config, "RISK_PER_TRADE_PCT", 1.0)
    text = "Stop {{MAX_STOP_LOSS_PCT}}, risk {{ RISK_PER_TRADE_PCT }}, again {{MAX_STOP_LOSS_PCT}}."
    assert ph.resolve(text) == "Stop 2%, risk 1%, again 2%."


def test_resolve_reads_live_values_on_each_call(monkeypatch):
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 2.0)
    assert ph.resolve("{{MAX_STOP_LOSS_PCT}}") == "2%"
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 1.5)
    assert ph.resolve("{{MAX_STOP_LOSS_PCT}}") == "1.5%"


def test_resolve_leaves_text_without_placeholders_alone():
    assert ph.resolve("Plain {braces} and } stay.") == "Plain {braces} and } stay."
    assert ph.resolve("") == ""


def test_names_in_lists_well_formed_names_in_order():
    assert ph.names_in("{{a.b}} x {{ C_D }} {{a.b}} {{bad name}}") == ["a.b", "C_D", "a.b"]


@pytest.mark.parametrize("text, name", [
    ("{{NOPE}}", "NOPE"),
    ("ok {{MAX_STOP_LOSS_PCT}} then {{ nope.too }}", "nope.too"),
    ("{{ MAX_STOP_LOSS_PCT + 1 }}", "MAX_STOP_LOSS_PCT + 1"),
    ("{{config.MAX_STOP_LOSS_PCT}}", "config.MAX_STOP_LOSS_PCT"),
    ("{{\nNOPE\n}}", "NOPE"),
])
def test_unknown_or_malformed_placeholder_raises(text, name):
    with pytest.raises(ph.UnknownPlaceholder) as info:
        ph.resolve(text)
    assert info.value.name == name
    assert str(info.value) == f"unknown guide placeholder: {name}"
    assert isinstance(info.value, KeyError)


def test_nothing_is_substituted_when_any_name_is_unknown(monkeypatch):
    calls = []
    monkeypatch.setitem(live_risk.RISK_PLACEHOLDERS, "MAX_STOP_LOSS_PCT",
                        lambda: calls.append(1) or "2%")
    monkeypatch.setattr(ph, "PLACEHOLDERS", ph._merge(live_risk.RISK_PLACEHOLDERS))
    with pytest.raises(ph.UnknownPlaceholder):
        ph.resolve("{{MAX_STOP_LOSS_PCT}} {{NOPE}}")
    assert calls == []


# --- secrets can never be reached --------------------------------------------

@pytest.mark.parametrize("name", [
    "DISCORD_TOKEN", "config.DISCORD_TOKEN", "ETORO_API_KEY", "ETORO_USER_KEY",
    "ADMIN_PASSWORD", "DATABASE_URL", "config.ETORO_API_KEY", "__class__",
])
def test_secret_names_are_not_placeholders(name):
    with pytest.raises(ph.UnknownPlaceholder):
        ph.resolve("{{" + name + "}}")


def test_no_sensitive_field_is_a_registered_name():
    sensitive = {f.attr for f in config.FIELDS if f.sensitive} | {
        f.key for f in config.FIELDS if f.sensitive}
    assert sensitive
    assert not sensitive & set(ph.PLACEHOLDERS)


# --- provenance --------------------------------------------------------------

def test_provenance_label_names_every_part_and_ends_before_tax():
    label = ph.provenance_label(source="live paper book", n=12, run_date="2026-11-18",
                                costs_included=False)
    assert label == ("Source: live paper book; N = 12; as of 2026-11-18; "
                     "costs not included; before tax")
    with_costs = ph.provenance_label(source="backtest TRAIN 2015-2022", n=300,
                                     run_date="2026-09-10", costs_included=True)
    assert "costs included" in with_costs and with_costs.endswith("before tax")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: FAIL at collection: `ImportError: cannot import name 'placeholders' from 'swingbot.admin.guide'`.

- [ ] **Step 3: Implement the registry and resolver**

Create `swingbot/admin/guide/placeholders.py`:

```python
"""v235: the guide's {{name}} whitelist.

A chapter may write {{name}} only for a name in PLACEHOLDERS, a read-only
mapping merged from the live tables. There are no expressions and no generic
config access: a name is looked up in the mapping and nowhere else, so a
secret (a Discord token, an eToro key) can never be rendered. resolve() checks
every {{...}} first and raises UnknownPlaceholder before substituting
anything, so a chapter is either fully resolved or not served at all.

Values are computed per call (live), never cached here. Any figure about
performance carries provenance_label(...) with it.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Callable, Mapping

from swingbot.admin.guide.live_risk import RISK_PLACEHOLDERS

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
_ANY_BRACES_RE = re.compile(r"\{\{(.*?)\}\}", re.S)


class UnknownPlaceholder(KeyError):
    """A {{name}} that is not in the whitelist (or not a plain name at all)."""

    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"unknown guide placeholder: {self.name}"


def _merge(*tables: Mapping[str, Callable[[], str]]) -> Mapping[str, Callable[[], str]]:
    merged: dict[str, Callable[[], str]] = {}
    for table in tables:
        clash = merged.keys() & table.keys()
        if clash:
            raise ValueError(f"guide placeholder defined twice: {sorted(clash)}")
        merged.update(table)
    return MappingProxyType(merged)


PLACEHOLDERS: Mapping[str, Callable[[], str]] = _merge(RISK_PLACEHOLDERS)


def names_in(markdown: str) -> list[str]:
    """Well-formed placeholder names in document order, repeats kept."""
    return [match.group(1) for match in PLACEHOLDER_RE.finditer(markdown)]


def resolve(markdown: str) -> str:
    """Fill every {{name}}; UnknownPlaceholder on the first name not whitelisted."""
    for match in _ANY_BRACES_RE.finditer(markdown):
        name = match.group(1).strip()
        if name not in PLACEHOLDERS:
            raise UnknownPlaceholder(name)
    return PLACEHOLDER_RE.sub(lambda match: PLACEHOLDERS[match.group(1)](), markdown)


def provenance_label(*, source: str, n: int, run_date: str, costs_included: bool) -> str:
    """Where a performance figure comes from; always ends with 'before tax'."""
    costs = "costs included" if costs_included else "costs not included"
    return f"Source: {source}; N = {n}; as of {run_date}; {costs}; before tax"
```

Every `{{…}}` has passed the `_ANY_BRACES_RE` check before `PLACEHOLDER_RE.sub` runs, so the callback's lookup cannot miss. `_merge` copies the tables, so `test_nothing_is_substituted_when_any_name_is_unknown` rebuilds `PLACEHOLDERS` after patching the risk table.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_placeholders.py`
Expected: PASS (`0 failed`), V235-3's tests included.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

Run: `python -m pyflakes swingbot/admin/guide/`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/guide/placeholders.py tests/admin/test_guide_placeholders.py
git commit -m "feat(guide): placeholder whitelist, resolver and provenance label (v235 V235-3b)"
```

