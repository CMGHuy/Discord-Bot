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

from swingbot.admin.guide import live_market, live_risk, placeholders
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


#: The stored account row the sizer reads; live_risk._load_account would open the database.
_ACCOUNT_ROW = {
    "risk_pct": 1.0, "max_risk_amount_absolute": 100.0, "sizing_mode": "risk_pct",
    "max_position_pct": 10.0, "max_position_value_absolute": 1000.0, "max_open_positions": 30,
}


@pytest.fixture(autouse=True)
def _stored_account(monkeypatch):
    monkeypatch.setattr(live_risk, "_load_account", lambda: dict(_ACCOUNT_ROW))


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


_PCT_AFTER_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}%")


def double_percent_problems(chapters) -> list[str]:
    """A `%` right after a {{name}} whose value already ends in `%` renders `2%%`."""
    problems = []
    for chapter in chapters:
        for number, line in enumerate(chapter.body.split("\n"), start=1):
            for match in _PCT_AFTER_PLACEHOLDER.finditer(line):
                provider = placeholders.PLACEHOLDERS.get(match.group(1))
                if provider is not None and provider().endswith("%"):
                    problems.append(f"{chapter.path.name}:{number}: {{{{{match.group(1)}}}}} "
                                    "already ends in % -- drop the extra %")
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
    "double percent": double_percent_problems,
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
    body = "Risk is 2% of the account.\nCap {{MAX_STOP_LOSS_PCT}}.\n```\n50%\n```\nRatio 1.5 %.\n"
    assert bare_percent_problems([_ch(body, order=8, slug="sizing-risk")]) == [
        "08-sizing-risk.md:1: bare number before % -- use a placeholder",
        "08-sizing-risk.md:6: bare number before % -- use a placeholder"]
    assert bare_percent_problems([_ch(body, order=6, slug="gates")]) == []


def test_double_percent_flags_a_percent_after_a_percent_placeholder():
    assert double_percent_problems([_ch("Cap {{MAX_STOP_LOSS_PCT}}%.")]) == [
        "01-sample.md:1: {{MAX_STOP_LOSS_PCT}} already ends in % -- drop the extra %"]
    assert double_percent_problems([_ch("Cap {{MAX_STOP_LOSS_PCT}}.")]) == []
    assert double_percent_problems([_ch("Mode {{POSITION_SIZING_MODE}}%.")]) == []
