# v235 — Guide foundation, Part 2: freshness gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V235-7" -A 400 <this file>`).

**Spec:** v215 — [2026-11-06-v215-guide-page.md](../specs/2026-11-06-v215-guide-page.md) § Freshness gate: how the guide stays current.
**Index:** [2026-11-18-v235-guide-foundation_0-index.md](2026-11-18-v235-guide-foundation_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and the Handoff decisions bind every task here.

Tasks: V235-6 (content test and anchor fixture), V235-7 (`guide_sources.py`), V235-8 (`/close-out` rule, `CLAUDE.md`, mirrors).

Two decisions this part makes inside the ledger's contracts:

- **Anchors come from the raw chapter body, and headings may not hold placeholders.** The API builds headings from the *resolved* body (V235-5); resolving every placeholder in a script would read the live book (`alerts.per_week`). The content test forbids `{{…}}` in a `##`/`###` line, so raw and resolved anchors are always equal and `guide_anchors.py` never touches the database.
- **Checks that need Plan B/C content are vacuous until it exists**, and each check is proved to fire by a unit test on a synthetic chapter in the same module: the strategies file set (once `docs/guide/strategies/` holds any `.md`), bare `N%` (orders 7–9), and "some chapter renders `{{horizons.table}}`" (once any chapter exists; V235-14 adds it).

# Phase 1 — Freshness gate

### Task V235-6: Content test and anchor fixture

**Model:** sonnet — new test module and generator script on fixed contracts; no trading code.

**Files:**
- Create: `scripts/dev/guide_anchors.py`
- Create: `frontend/src/app/workspaces/guide/guide-anchors.json` (generated, never hand-edited)
- Create: `tests/scripts/test_guide_anchors.py` (suite `tooling`), `tests/admin/test_guide_content.py` (suite `admin-core`; no `suites.toml` edit)

**Interfaces:**
- Consumes: `chapters.Chapter`, `GuideFormatError`, `extract_headings`, `split_source`, `FIGURE_RE`, `guide_dir` (V235-2), `load_chapters` (V235-2b); `placeholders.resolve`, `names_in`, `UnknownPlaceholder` (`str()` = `unknown guide placeholder: <name>`), `PLACEHOLDER_RE` (V235-3b); `live_market._load_trades`, `registered_strategy_keys()`, `strategy_file_slug()`; `horizons.table` rows render as ``| `<key>` | …`` (V235-4).
- Produces: `guide_anchors.FIXTURE` (repo-relative), `build(root=None) -> dict` (`{"chapters": {slug: [anchor, …]}}`, slugs sorted), `render(data) -> str`, `main(argv=None) -> int` (`--check` exits 1 on drift or a missing fixture; `--guide-dir`, `--out`; malformed chapter exits 2). V235-10 reads the fixture; V235-14..16 regenerate it.
- `figure_names()` reads the keys of the `GUIDE_FIGURES = { … }` literal in `guide-figures.ts` (V235-11); absent file = empty set (no figure before V235-15).

- [ ] **Step 1: Write the failing script tests**

Create `tests/scripts/test_guide_anchors.py`:

```python
"""v235 V235-6: the guide anchor fixture generator (scripts/dev/guide_anchors.py)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import guide_anchors as ga  # noqa: E402


def _chapter(root: Path, order: int, slug: str, body: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{order:02d}-{slug}.md").write_text(
        f"---\ntitle: T {slug}\nslug: {slug}\norder: {order}\n"
        f"reviewed_for: 2.19.2\nsources: []\n---\n{body}", encoding="utf-8")


def _args(guide: Path, out: Path, *extra: str) -> list[str]:
    return ["--guide-dir", str(guide), "--out", str(out), *extra]


def test_build_lists_anchors_per_slug_sorted(tmp_path):
    _chapter(tmp_path, 3, "pipeline", "## Scan run\n### Gates\n## Gates\n")
    _chapter(tmp_path, 1, "what-it-is", "## The notice\n")
    data = ga.build(tmp_path)
    assert list(data["chapters"]) == ["pipeline", "what-it-is"]
    assert data["chapters"]["pipeline"] == ["scan-run", "gates", "gates-2"]
    assert data["chapters"]["what-it-is"] == ["the-notice"]


def test_missing_guide_renders_an_empty_two_space_fixture(tmp_path):
    assert ga.render(ga.build(tmp_path / "missing")) == '{\n  "chapters": {}\n}\n'


def test_main_writes_the_fixture_then_check_passes(tmp_path):
    guide, out = tmp_path / "guide", tmp_path / "web" / "anchors.json"
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    assert ga.main(_args(guide, out)) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"chapters": {"what-it-is": ["the-notice"]}}
    assert ga.main(_args(guide, out, "--check")) == 0


def test_check_fails_on_drift_and_leaves_the_file_alone(tmp_path, capsys):
    guide, out = tmp_path / "guide", tmp_path / "anchors.json"
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    ga.main(_args(guide, out))
    before = out.read_text(encoding="utf-8")
    _chapter(guide, 1, "what-it-is", "## The notice\n## Swing horizons\n")
    assert ga.main(_args(guide, out, "--check")) == 1
    assert "stale" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == before
    assert ga.main(_args(guide, tmp_path / "absent.json", "--check")) == 1
    _chapter(guide, 1, "what-it-is", "## The notice\n")
    out.write_bytes(before.replace("\n", "\r\n").encode("utf-8"))
    assert ga.main(_args(guide, out, "--check")) == 0


def test_malformed_chapter_exits_2(tmp_path, capsys):
    guide = tmp_path / "guide"
    guide.mkdir()
    (guide / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert ga.main(_args(guide, tmp_path / "anchors.json")) == 2
    assert "01-what-it-is.md" in capsys.readouterr().err
    assert ga.FIXTURE.as_posix() == "frontend/src/app/workspaces/guide/guide-anchors.json"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_anchors.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'guide_anchors'`.

- [ ] **Step 3: Write the generator**

Create `scripts/dev/guide_anchors.py`:

```python
"""Write (or --check) the guide anchor fixture, from raw headings (v235)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.admin.guide.chapters import GuideFormatError, load_chapters  # noqa: E402

FIXTURE = Path("frontend/src/app/workspaces/guide/guide-anchors.json")


def build(root: Path | None = None) -> dict:
    chapters = sorted(load_chapters(root), key=lambda chapter: chapter.slug)
    return {"chapters": {c.slug: [h.anchor for h in c.headings] for c in chapters}}


def render(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _parse(argv):
    parser = argparse.ArgumentParser(description="Write or check the guide anchor fixture.")
    parser.add_argument("--check", action="store_true", help="exit 1 when stale")
    parser.add_argument("--guide-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=ROOT / FIXTURE)
    return parser.parse_args(argv)


def _check(out: Path, text: str) -> int:
    current = out.read_text(encoding="utf-8").replace("\r\n", "\n") if out.exists() else None
    if current == text:
        print("guide_anchors: fixture is current")
        return 0
    print(f"guide_anchors: {out} is stale -- run python scripts/dev/guide_anchors.py",
          file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = _parse(argv)
    try:
        data = build(args.guide_dir)
    except GuideFormatError as exc:
        print(f"guide_anchors: {exc}", file=sys.stderr)
        return 2
    text = render(data)
    if args.check:
        return _check(args.out, text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"guide_anchors: wrote {len(data['chapters'])} chapter(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the script tests, then generate the fixture**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_anchors.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/guide_anchors.py`
Expected: `wrote 0 chapter(s)`; the file is `{"chapters": {}}` in 2-space form.

- [ ] **Step 5: Write the content test**

Create `tests/admin/test_guide_content.py`:

```python
"""v235 freshness gate (spec v215 § Freshness gate). Each check returns problems;
the real guide must have none, and a synthetic chapter proves each check fires.
Plan B/C checks (strategies/ file set, bare N% in orders 7-9) start vacuous."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

from swingbot.admin.guide import live_market, placeholders
from swingbot.admin.guide.chapters import (FIGURE_RE, Chapter, extract_headings, guide_dir,
                                           load_chapters, split_source)
from swingbot.core.market import strategy_types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import guide_anchors  # noqa: E402

FIGURES_TS = ROOT / "frontend/src/app/workspaces/guide/guide-figures.ts"
_FENCE = re.compile(r"^[ \t]{0,3}(?:```|~~~)")
_HEADING = re.compile(r"^#{2,3}[ \t]")
_BARE_PCT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?[ \t]?%")
_FIGURE_KEY = re.compile(r"(?:^|,)\s*['\"]?([a-z0-9-]+)['\"]?\s*:")
_PCT_ORDERS = range(7, 10)   # Plan B chapters 7-9


@pytest.fixture(autouse=True)
def _no_live_book(monkeypatch):
    """alerts.per_week would read the database."""
    monkeypatch.setattr(live_market, "_load_trades", lambda: [])


@pytest.fixture(scope="module")
def guide() -> list[Chapter]:
    return load_chapters()


def unresolved(chapters) -> list[str]:
    problems = []
    for chapter in chapters:
        try:
            placeholders.resolve(chapter.body)
        except placeholders.UnknownPlaceholder as exc:
            problems.append(f"{chapter.path.name}: {exc}")
    return problems


def _lines_outside_fences(body: str):
    in_fence = False
    for number, line in enumerate(body.splitlines(), start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            yield number, line


def heading_problems(chapters) -> list[str]:
    problems = []
    for chapter in chapters:
        depth = 0
        for number, line in _lines_outside_fences(chapter.body):
            if _HEADING.match(line) and "{{" in line:
                problems.append(f"{chapter.path.name}:{number}: placeholder in a heading")
            if _HEADING.match(line) and depth > 0:
                problems.append(f"{chapter.path.name}:{number}: heading inside <details>")
            depth += line.count("<details") - line.count("</details>")
    return problems


def _py_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, ast.ClassDef):
            names.update(f"{node.name}.{item.name}" for item in node.body
                         if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)))
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _config_fields(tree: ast.Module) -> set[str]:
    """Field("NAME", ...) entries: config settings are not module-level names."""
    return {node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Field"
            and node.args and isinstance(node.args[0], ast.Constant)}


def defines(path: Path, symbol: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return re.search(rf"(?<![\w$]){re.escape(symbol)}(?![\w$])", text) is not None
    tree = ast.parse(text)
    return symbol in _py_names(tree) | _config_fields(tree)


def source_problems(chapters, root: Path = ROOT) -> list[str]:
    problems = []
    for chapter in chapters:
        for entry in chapter.sources:
            rel, symbol = split_source(entry)
            target = root / rel
            if not target.exists():
                problems.append(f"{chapter.path.name}: source {rel} does not exist")
            elif symbol and (target.is_dir() or not defines(target, symbol)):
                problems.append(f"{chapter.path.name}: {symbol} is no longer defined in {rel}")
    return problems


def horizon_problems(chapters) -> list[str]:
    if not chapters:
        return []
    if not any("horizons.table" in placeholders.names_in(c.body) for c in chapters):
        return ["no chapter renders {{horizons.table}}"]
    table = placeholders.resolve("{{horizons.table}}")
    return [f"horizons.table lacks `{key}`" for key in strategy_types.HORIZONS
            if f"| `{key}` |" not in table]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def version_problems(chapters, bot: str) -> list[str]:
    return [f"{c.path.name}: reviewed_for {c.reviewed_for} is newer than bot {bot}"
            for c in chapters if _version(c.reviewed_for) > _version(bot)]


def _bot_version() -> str:
    return json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))["bot"]


def figure_names(path: Path = FIGURES_TS) -> set[str]:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    start = text.find("= {", max(text.find("GUIDE_FIGURES"), 0))
    if "GUIDE_FIGURES" not in text or start < 0:
        return set()
    return set(_FIGURE_KEY.findall(text[start + 3:text.find("}", start)]))


def figure_problems(chapters, known: set[str]) -> list[str]:
    return [f"{c.path.name}: figure '{name}' is not in GUIDE_FIGURES"
            for c in chapters for name in FIGURE_RE.findall(c.body) if name not in known]


def strategy_file_problems(folder: Path) -> list[str]:
    files = {p.stem for p in folder.glob("*.md")} if folder.is_dir() else set()
    if not files:
        return []
    wanted = {live_market.strategy_file_slug(k) for k in live_market.registered_strategy_keys()}
    return ([f"strategies/: no card for {slug}.md" for slug in sorted(wanted - files)]
            + [f"strategies/{slug}.md: not a registered strategy" for slug in sorted(files - wanted)])


def bare_percent_problems(chapters) -> list[str]:
    problems = []
    for chapter in (c for c in chapters if c.order in _PCT_ORDERS):
        for number, line in _lines_outside_fences(chapter.body):
            if _BARE_PCT.search(placeholders.PLACEHOLDER_RE.sub("", line)):
                problems.append(f"{chapter.path.name}:{number}: bare number before % -- "
                                "use a placeholder")
    return problems


REAL_CHECKS = {
    "placeholders": unresolved,
    "headings": heading_problems,
    "sources": lambda g: source_problems(g),
    "horizons": horizon_problems,
    "reviewed_for": lambda g: version_problems(g, _bot_version()),
    "figures": lambda g: figure_problems(g, figure_names()),
    "strategy cards": lambda g: strategy_file_problems(guide_dir() / "strategies"),
    "bare percent": bare_percent_problems,
}


@pytest.mark.parametrize("check", list(REAL_CHECKS))
def test_the_real_guide_passes(guide, check):
    assert REAL_CHECKS[check](guide) == []


def test_anchor_fixture_is_current():
    fixture = json.loads((ROOT / guide_anchors.FIXTURE).read_text(encoding="utf-8"))
    assert fixture == guide_anchors.build(), "run python scripts/dev/guide_anchors.py"


def _ch(body: str, *, order: int = 1, slug: str = "sample", reviewed_for: str = "2.19.2",
        sources=()) -> Chapter:
    return Chapter(slug=slug, title="Sample", order=order, reviewed_for=reviewed_for,
                   sources=tuple(sources), body=body, headings=extract_headings(body),
                   path=Path(f"{order:02d}-{slug}.md"))


def test_unknown_placeholder_is_reported():
    assert unresolved([_ch("Cap {{NOT_A_NAME}}.")]) == [
        "01-sample.md: unknown guide placeholder: NOT_A_NAME"]
    assert unresolved([_ch("Cap {{MAX_STOP_LOSS_PCT}}.")]) == []


def test_placeholder_in_heading_and_heading_in_details_are_reported():
    body = ("## Cap {{MAX_STOP_LOSS_PCT}}\n<details><summary>Under the hood</summary>\n\n"
            "### Inner\n</details>\n## After\n```\n<details>\n## in a fence\n```\n")
    assert heading_problems([_ch(body)]) == ["01-sample.md:1: placeholder in a heading",
                                             "01-sample.md:4: heading inside <details>"]


def test_source_check_covers_paths_symbols_methods_and_config_fields(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        'X = 1\nY: int = 2\nclass Plan:\n    def poll(self): ...\ndef run(): ...\n'
        'FIELDS = [Field("RISK_PCT", "RISK_PCT")]\n', encoding="utf-8")
    (tmp_path / "pkg" / "page.ts").write_text("export const guideRoutes = [];\n", encoding="utf-8")
    good = _ch("x", sources=["pkg/mod.py", "pkg/mod.py:X", "pkg/mod.py:Y", "pkg/mod.py:Plan.poll",
                             "pkg/mod.py:run", "pkg/mod.py:RISK_PCT", "pkg/page.ts:guideRoutes", "pkg"])
    assert source_problems([good], root=tmp_path) == []
    bad = _ch("x", sources=["pkg/gone.py", "pkg/mod.py:missing", "pkg/page.ts:guide", "pkg:X"])
    assert source_problems([bad], root=tmp_path) == [
        "01-sample.md: source pkg/gone.py does not exist",
        "01-sample.md: missing is no longer defined in pkg/mod.py",
        "01-sample.md: guide is no longer defined in pkg/page.ts",
        "01-sample.md: X is no longer defined in pkg"]


def test_horizons_check_wants_the_table_once_chapters_exist(monkeypatch):
    assert horizon_problems([]) == []
    assert horizon_problems([_ch("No table.")]) == ["no chapter renders {{horizons.table}}"]
    assert horizon_problems([_ch("{{horizons.table}}")]) == []
    monkeypatch.setattr(placeholders, "resolve", lambda markdown: "| `nope` |")
    assert horizon_problems([_ch("{{horizons.table}}")]) == [
        f"horizons.table lacks `{key}`" for key in strategy_types.HORIZONS]


@pytest.mark.parametrize("reviewed, flagged", [
    ("2.19.2", False), ("2.9.10", False), ("2.19.3", True), ("3.0.0", True)])
def test_reviewed_for_compares_as_numbers(reviewed, flagged):
    assert bool(version_problems([_ch("x", reviewed_for=reviewed)], "2.19.2")) is flagged


def test_figure_names_read_the_registry_literal(tmp_path):
    ts = tmp_path / "guide-figures.ts"
    ts.write_text("import { Type } from '@angular/core';\n"
                  "export const GUIDE_FIGURES: Record<string, Type<unknown>> = {\n"
                  "  pipeline: GuidePipelineDiagram,\n  'risk-ladder': RiskLadder,\n};\n",
                  encoding="utf-8")
    assert figure_names(ts) == {"pipeline", "risk-ladder"}
    ts.write_text("export const GUIDE_FIGURES: Record<string, Type<unknown>> = {};\n", encoding="utf-8")
    assert figure_names(ts) == set()
    assert figure_names(tmp_path / "absent.ts") == set()
    chapter = _ch("Intro.\n<!-- figure:pipeline -->\n<!-- figure:ghost -->\n")
    assert figure_problems([chapter], {"pipeline"}) == [
        "01-sample.md: figure 'ghost' is not in GUIDE_FIGURES"]


def test_strategy_cards_are_vacuous_until_any_exist_then_must_match(tmp_path, monkeypatch):
    monkeypatch.setattr(live_market, "registered_strategy_keys", lambda: ("Break & Retest", "RSI"))
    folder = tmp_path / "strategies"
    assert strategy_file_problems(folder) == []
    folder.mkdir()
    assert strategy_file_problems(folder) == []
    (folder / "break-retest.md").write_text("x", encoding="utf-8")
    (folder / "old-one.md").write_text("x", encoding="utf-8")
    assert strategy_file_problems(folder) == ["strategies/: no card for rsi.md",
                                              "strategies/old-one.md: not a registered strategy"]


def test_bare_percent_is_caught_only_in_chapters_7_to_9():
    body = "Risk is 2% of the account.\nCap {{MAX_STOP_LOSS_PCT}}%.\n```\n50%\n```\nRatio 1.5 %.\n"
    assert bare_percent_problems([_ch(body, order=8, slug="sizing-risk")]) == [
        "08-sizing-risk.md:1: bare number before % -- use a placeholder",
        "08-sizing-risk.md:6: bare number before % -- use a placeholder"]
    assert bare_percent_problems([_ch(body, order=6, slug="gates")]) == []
```

- [ ] **Step 6: Run the content test**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: PASS (`0 failed`); real-guide cases are vacuous until V235-14. A database connection means `_no_live_book` misses its patch target: fix it, never skip.

Run: `python scripts/dev/guide_anchors.py --check`
Expected: `guide_anchors: fixture is current`, exit 0.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/guide_anchors.py frontend/src/app/workspaces/guide/guide-anchors.json tests/scripts/test_guide_anchors.py tests/admin/test_guide_content.py
git commit -m "test(guide): content freshness gate and generated anchor fixture (v235 V235-6)"
```

### Task V235-7: `guide_sources.py` diff helper

**Model:** sonnet — a small stdlib-plus-YAML CLI with a git call; contracts fixed in the ledger.

**Files:**
- Create: `scripts/dev/guide_sources.py`
- Create: `tests/scripts/test_guide_sources.py` (suite `tooling`; no `suites.toml` edit)

**Interfaces:**
- Consumes: `swingbot.admin.guide.chapters` — `Chapter`, `GuideFormatError` (a `ValueError`), `guide_dir()`, `split_source()` (V235-2), `load_chapters(root=None)` (V235-2b); PyYAML (runtime pin from V235-2b).
- Produces (V235-8's `/close-out` rule runs the CLI):
  - `python scripts/dev/guide_sources.py <base>..<head> [--guide-dir DIR]` prints one line per touched document, `NN-<slug>.md: <path>, <path>` for a chapter and `strategies/<file>.md: <path>, …` for a Plan B strategy card, chapters first by `order`, then cards by file name; prints `guide: no chapter sources touched` when none is touched. Exit 0 in both cases; exit 2 on a bad range, a git failure or a malformed chapter/card.
  - `touched(paths: Iterable[str], chapters) -> list[tuple[Chapter, list[str]]]` — `chapters` is any sequence of objects with `.path` and `.sources` (a `Chapter` or a `Card`); the paths list per document is sorted and de-duplicated.
  - `changed_paths(rev_range: str) -> list[str]` (`git diff --name-only <base>..<head>`, run at the repo root; `ValueError` on a range without `..`, one starting with `-`, or a non-zero git exit).
  - `load_cards(root: Path | None = None) -> list[Card]` (`docs/guide/strategies/*.md`; `[]` while the folder is absent); `Card(path: Path, sources: tuple[str, ...])` frozen dataclass; `NONE_TOUCHED = "guide: no chapter sources touched"`; `main(argv=None) -> int`.
- Matching rule: a changed path touches a document when it equals a source's path part (`split_source`) or lies under it as a directory (`<source>/…`); a `path:symbol` source matches on its path. Backslashes and a leading `./` are normalised away, blank lines ignored.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_guide_sources.py`:

```python
"""v235 V235-7: guide_sources.py names the guide chapters a diff touches."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

import guide_sources as gs  # noqa: E402
from swingbot.admin.guide.chapters import GuideFormatError, load_chapters  # noqa: E402


def _front(slug: str, order: int | None, sources: list[str]) -> str:
    listed = "".join(f"\n  - {s}" for s in sources) if sources else " []"
    order_line = f"order: {order}\n" if order is not None else ""
    return (f"---\ntitle: T {slug}\nslug: {slug}\n{order_line}"
            f"reviewed_for: 2.19.2\nsources:{listed}\n---\nBody.\n")


def _chapter(root: Path, order: int, slug: str, sources: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{order:02d}-{slug}.md").write_text(_front(slug, order, sources), encoding="utf-8")


def _card(root: Path, name: str, sources: list[str]) -> None:
    folder = root / "strategies"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(_front(name, None, sources), encoding="utf-8")


def test_touched_matches_exact_paths_and_directories(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/core/market/strategy_types.py:HORIZONS",
                                         "VERSION.json"])
    _chapter(tmp_path, 3, "pipeline", ["swingbot/core/scanning/", "swingbot/core/planning"])
    changed = ["swingbot/core/scanning/scan_run.py", "swingbot/core/planning/builders.py",
               "swingbot/core/market/strategy_types.py", "README.md",
               "swingbot/core/planning_extra.py"]
    result = gs.touched(changed, load_chapters(tmp_path))
    assert [(c.slug, paths) for c, paths in result] == [
        ("what-it-is", ["swingbot/core/market/strategy_types.py"]),
        ("pipeline", ["swingbot/core/planning/builders.py", "swingbot/core/scanning/scan_run.py"])]


def test_touched_normalises_paths_and_ignores_blanks(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py:MAX_STOP_LOSS_PCT",
                                         "swingbot/config.py:RISK_PER_TRADE_PCT", "VERSION.json"])
    result = gs.touched(["swingbot\\config.py", "", "  ", "./VERSION.json"], load_chapters(tmp_path))
    assert [paths for _, paths in result] == [["VERSION.json", "swingbot/config.py"]]


def test_touched_is_empty_when_no_source_changes(tmp_path):
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py"])
    assert gs.touched(["frontend/src/app/app.ts"], load_chapters(tmp_path)) == []
    assert gs.touched([], load_chapters(tmp_path)) == []


def test_strategy_cards_are_scanned(tmp_path):
    assert gs.load_cards(tmp_path) == []
    _card(tmp_path, "rsi", ["swingbot/core/market/strategy.py:STRATEGY_FUNCS"])
    _card(tmp_path, "break-retest", [])
    cards = gs.load_cards(tmp_path)
    assert [c.path.name for c in cards] == ["break-retest.md", "rsi.md"]
    assert cards[1].sources == ("swingbot/core/market/strategy.py:STRATEGY_FUNCS",)
    result = gs.touched(["swingbot/core/market/strategy.py"], cards)
    assert [(c.path.name, paths) for c, paths in result] == [
        ("rsi.md", ["swingbot/core/market/strategy.py"])]


@pytest.mark.parametrize("text", ["no front matter\n", "---\nsources: nope\n---\nBody.\n",
                                  "---\ntitle: open front matter\n"])
def test_malformed_card_is_a_format_error(tmp_path, text):
    (tmp_path / "strategies").mkdir()
    (tmp_path / "strategies" / "rsi.md").write_text(text, encoding="utf-8")
    with pytest.raises(GuideFormatError, match="rsi.md"):
        gs.load_cards(tmp_path)


def test_main_prints_chapters_then_cards(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: [
        "swingbot/config.py", "swingbot/core/market/strategy.py", "docs/notes.md"])
    _chapter(tmp_path, 3, "pipeline", ["swingbot/core/market/"])
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py:MAX_STOP_LOSS_PCT"])
    _card(tmp_path, "rsi", ["swingbot/core/market/strategy.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "01-what-it-is.md: swingbot/config.py",
        "03-pipeline.md: swingbot/core/market/strategy.py",
        "strategies/rsi.md: swingbot/core/market/strategy.py"]


def test_main_says_when_nothing_is_touched(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: ["README.md"])
    _chapter(tmp_path, 1, "what-it-is", ["swingbot/config.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == gs.NONE_TOUCHED == "guide: no chapter sources touched"


def test_main_with_an_absent_guide_touches_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: ["swingbot/config.py"])
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path / "missing")]) == 0
    assert capsys.readouterr().out.strip() == gs.NONE_TOUCHED


def test_main_reports_a_malformed_chapter(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gs, "changed_paths", lambda rev_range: [])
    (tmp_path / "01-what-it-is.md").write_text("no front matter\n", encoding="utf-8")
    assert gs.main(["main..HEAD", "--guide-dir", str(tmp_path)]) == 2
    assert "01-what-it-is.md" in capsys.readouterr().err


@pytest.mark.parametrize("rev_range", ["HEAD", "main", "-x..HEAD"])
def test_a_range_without_two_dots_is_rejected(rev_range):
    with pytest.raises(ValueError, match="<base>..<head>"):
        gs.changed_paths(rev_range)


def test_bad_range_exits_2(capsys):
    assert gs.main(["not-a-range"]) == 2
    assert "<base>..<head>" in capsys.readouterr().err


def test_unknown_revision_exits_2(capsys):
    assert gs.main(["no-such-rev-v235..HEAD"]) == 2
    assert capsys.readouterr().err.startswith("guide_sources: ")


def test_an_empty_range_has_no_changed_paths():
    assert gs.changed_paths("HEAD..HEAD") == []
```

`HEAD..HEAD` is used instead of `HEAD~1..HEAD` because CI may check out a single commit.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_sources.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'guide_sources'`.

- [ ] **Step 3: Write the helper**

Create `scripts/dev/guide_sources.py`:

```python
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
```

The open-front-matter case (`"---\ntitle: …\n"`) fails the `"\n---" not in text[3:]` test: `text[3:]` starts at the newline after the opening marker, so only a second marker line satisfies it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_guide_sources.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/guide_sources.py HEAD..HEAD`
Expected: `guide: no chapter sources touched`, exit 0.

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`main` and `_card_sources` are the largest, about 4 each).

- [ ] **Step 5: Commit**

```bash
git add scripts/dev/guide_sources.py tests/scripts/test_guide_sources.py
git commit -m "feat(dev): guide_sources.py names the guide chapters a diff touches (v235 V235-7)"
```

### Task V235-8: `/close-out` guide rule, CLAUDE.md and mirrors

**Model:** sonnet — process text across five files plus the Codex mirror, all in one commit; the 200-line `CLAUDE.md` cap needs care, no code logic.

**Files:**
- Modify: `.claude/skills/close-out/SKILL.md` (§ Step 5b, line ~48)
- Modify: `.agents/skills/close-out/SKILL.md` — generated, never hand-edited: `python scripts/dev/sync_codex.py`
- Modify: `docs/claude/document-lifecycle.md` (§ Implemented plans keep the skills aligned, line ~149)
- Modify: `CLAUDE.md` (199 lines today; ends at 199)
- Modify: `AGENTS.md` (the close-out paragraph at lines ~501-506)
- Modify: `docs/claude/working-conventions.md` — the section owner for the lines moved out of `CLAUDE.md` (its opening bullet list already holds the `.superpowers/sdd/progress.md` rule)
- Create: `tests/hooks/test_guide_closeout_rule.py` (suite `dev-setup`, `tests/hooks/`; no `suites.toml` edit)

**Interfaces:**
- Consumes: `scripts/dev/guide_sources.py <base>..<head>` and its two outputs, `NN-<slug>.md: <path>, …` / `guide: no chapter sources touched` (V235-7); `python scripts/dev/guide_anchors.py` (V235-6).
- Produces: the Step 5b guide check; the commit phrase `guide: no reader-visible change` (spec v215 § Freshness gate, layer 3), which later close-outs grep for.
- **Why something leaves `CLAUDE.md`:** it is at 199 lines and must stay under 200 (its own header rule; Handoff 4). The two-line Token-discipline bullet `**README.md is only an index** — read the one topic file it points at. / \`tail\` \`.superpowers/sdd/progress.md\`, never \`cat\` it.` becomes one line with a pointer, and its full text moves to `working-conventions.md`. Net: −1 +1 = 199 lines.

- [ ] **Step 1: Write the failing test**

Create `tests/hooks/test_guide_closeout_rule.py`:

```python
"""v235 V235-8: the guide freshness rule (spec v215 § Freshness gate, layer 3)
is wired into /close-out, its Codex mirror, document-lifecycle.md, CLAUDE.md
and AGENTS.md, and CLAUDE.md stays under its 200-line cap."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NO_CHANGE = "guide: no reader-visible change"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + len(heading))
    return text[start:end if end >= 0 else len(text)]


def test_close_out_step_5b_runs_guide_sources():
    step = _section(_read(".claude/skills/close-out/SKILL.md"), "## Step 5b")
    assert "python scripts/dev/guide_sources.py" in step
    assert "reviewed_for" in step
    assert NO_CHANGE in step


def test_codex_close_out_skill_carries_the_rule():
    assert "python scripts/dev/guide_sources.py" in _read(".agents/skills/close-out/SKILL.md")


def test_document_lifecycle_explains_the_rule():
    section = _section(_read("docs/claude/document-lifecycle.md"),
                       "## Implemented plans keep the skills aligned")
    assert "guide_sources.py" in section and NO_CHANGE in section


@pytest.mark.parametrize("rel", ["CLAUDE.md", "AGENTS.md"])
def test_operator_files_state_the_rule(rel):
    text = _read(rel)
    assert "guide_sources.py" in text and NO_CHANGE in text


def test_claude_md_stays_under_200_lines():
    assert len(_read("CLAUDE.md").splitlines()) < 200


def test_the_moved_readme_rule_keeps_its_detail():
    assert "read the one topic file it points at" in _read("docs/claude/working-conventions.md")
    assert "**README.md is only an index" in _read("CLAUDE.md")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guide_closeout_rule.py`
Expected: FAIL — six of the seven cases (only `test_claude_md_stays_under_200_lines` passes today).

- [ ] **Step 3: Add the guide check to `/close-out` Step 5b**

In `.claude/skills/close-out/SKILL.md`, § `## Step 5b — Align every skill the plan affected`, append this paragraph after the existing one (before `## Step 6`):

```markdown
**Guide check (v235).** Run `python scripts/dev/guide_sources.py <merge>^1..<merge>`
over the plan's merge commit (or `<base>..<head>` of its commits). For each
chapter or strategy card it names, update the text where reader-visible
behaviour changed and set its `reviewed_for` to the bot version `VERSION.json`
now carries (re-run `python scripts/dev/guide_anchors.py` if a heading
changed), in a `docs(guide): align <chapter> with vN` commit; or, when nothing
a reader sees changed, write `guide: no reader-visible change` in the move
commit. `guide: no chapter sources touched` needs neither
(`document-lifecycle.md` § Implemented plans keep the skills aligned).
```

Then regenerate the Codex copy:

Run: `python scripts/dev/sync_codex.py`
Expected: `.agents/skills/close-out/SKILL.md` rewritten; no other file changes (`git status --short .agents .codex` lists only that file).

- [ ] **Step 4: Explain the rule in `document-lifecycle.md`**

In `docs/claude/document-lifecycle.md`, § `## Implemented plans keep the skills aligned`, append after its last paragraph (the one ending `so a skipped check is visible.`):

```markdown
**The guide is held to the same rule (v235, spec v215).** Every chapter under
`docs/guide/` (and every strategy card under `docs/guide/strategies/`) lists
the code it describes in `sources:`. `/close-out` Step 5b runs
`python scripts/dev/guide_sources.py <base>..<head>`; each chapter it names is
updated where reader-visible behaviour changed, with `reviewed_for` set to the
new bot version and `python scripts/dev/guide_anchors.py` re-run when a
heading moved, or the move commit records `guide: no reader-visible change`.
The content test (`tests/admin/test_guide_content.py`) already fails CI on a
removed symbol, strategy or horizon; this rule is the backstop for prose that
still compiles but is now wrong.
```

- [ ] **Step 5: Free a `CLAUDE.md` line, then add the rule**

In `CLAUDE.md` § Token discipline, replace the two lines

```markdown
- **README.md is only an index** — read the one topic file it points at.
  `tail` `.superpowers/sdd/progress.md`, never `cat` it.
```

with the one line

```markdown
- **README.md is only an index; `tail` `.superpowers/sdd/progress.md`, never `cat` it** — `working-conventions.md`.
```

In `CLAUDE.md` § Naming specs and plans, insert one new line directly after the paragraph line that ends `(`/close-out` Step 5b; `document-lifecycle.md` § Implemented plans keep the skills aligned).` (line ~161), before the blank line:

```markdown
**A plan whose diff touches a guide chapter's `sources:` updates that chapter and its `reviewed_for`, or its close-out commit records `guide: no reader-visible change`** (`/close-out` Step 5b runs `scripts/dev/guide_sources.py`).
```

In `docs/claude/working-conventions.md`, in the opening bullet list (before `## Versioning: when to bump \`VERSION.json\``), add after the bullet that starts `- Active plans live in \`docs/superpowers/plans/*.md\``:

```markdown
- **README.md is only an index** — read the one topic file it points at
  rather than the README itself. `tail` `.superpowers/sdd/progress.md`, never
  `cat` it: it grows with every plan run (moved here from `CLAUDE.md`, v235).
```

Run: `wc -l CLAUDE.md`
Expected: `199 CLAUDE.md`.

- [ ] **Step 6: Mirror the rule into `AGENTS.md`**

In `AGENTS.md`, after the paragraph ending `(\`close-out\` Step 5b; \`document-lifecycle.md\` § Implemented plans keep the / skills aligned).` (line ~506), insert a blank line and:

```markdown
A plan whose diff touches a path in a guide chapter's `sources:`
(`docs/guide/`) updates that chapter where behaviour changed and sets its
`reviewed_for` to the new bot version, or records
`guide: no reader-visible change` in the close-out commit; `close-out` Step 5b
lists the chapters with `python scripts/dev/guide_sources.py <base>..<head>`.
```

The `AGENTS.md` README sentence (line ~300) already carries the moved rule and stays as it is.

- [ ] **Step 7: Run the tests**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guide_closeout_rule.py`
Expected: PASS (`0 failed`).

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS — the `.agents` copy matches and `AGENTS.md` still names every skill, agent and `docs/claude/*.md` file (no new doc was added).

Run: `python scripts/dev/testrun.py file tests/hooks/test_skill_citations.py`
Expected: PASS — the new Step 5b text cites `scripts/dev/guide_sources.py` and `scripts/dev/guide_anchors.py`, both present after V235-6 and V235-7. If the citation lint flags `<merge>^1..<merge>` or `<base>..<head>` as a path, rewrite that placeholder the way the lint's allowlist expects (`tests/hooks/skill_citation_allowlist.txt` shows the accepted forms) rather than adding an allowlist entry.

- [ ] **Step 8: Commit (one commit: rule, mirrors and the moved line together)**

```bash
git add .claude/skills/close-out/SKILL.md .agents/skills/close-out/SKILL.md \
  docs/claude/document-lifecycle.md docs/claude/working-conventions.md \
  CLAUDE.md AGENTS.md tests/hooks/test_guide_closeout_rule.py
git commit -m "docs(close-out): guide freshness check in Step 5b; CLAUDE.md line moved to working-conventions (v235 V235-8)"
```

