"""v140 § Enforcement: every spec numbered above v140 carries a valid
**Screen:** header line under **Edge:**.

| Edge:                                                  | Screen:                                     |
| expectancy / volume adding an entry strategy or filter | `<ledger-id> SCREEN-PASS` (row must exist)  |
| expectancy moving stops/targets, or harvest            | `harvest-headroom <path>` (path must exist) |
| none (integrity)                                       | `exempt (integrity)`                        |

v140 and earlier are grandfathered by number. A split spec carries the line
in its _0-index part. See
docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md.
"""
from __future__ import annotations

import re
from pathlib import Path

from swingbot.core.backtesting.instrument import stats

ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "docs" / "superpowers" / "specs"
LAST_GRANDFATHERED = 140
SCREEN_PASS = "SCREEN-PASS"

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_PART = re.compile(r"_(\d+)[a-z]?(?:-[^.]*)?\.md$")
_EXEMPT = re.compile(r"^exempt\b")
_HEADROOM = re.compile(r"^harvest-headroom\s+`?([^`\s]+)`?")
_LEDGER = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-PASS\b")
_EDGES_FOR = {"exempt": {"none"}, "headroom": {"expectancy", "harvest"},
              "ledger": {"expectancy", "volume"}}


def spec_number(path: Path) -> int | None:
    match = _NUMBER.match(path.name)
    return int(match.group(1)) if match else None


def carries_header(path: Path) -> bool:
    part = _PART.search(path.name)
    return part is None or part.group(1) == "0"


def checked_specs(specs_dir: Path = SPECS_DIR) -> list:
    return sorted(p for p in Path(specs_dir).rglob("*.md")
                  if (spec_number(p) or 0) > LAST_GRANDFATHERED and carries_header(p))


def header(text: str, key: str) -> str | None:
    match = re.search(rf"^\*\*{re.escape(key)}:\*\*[ \t]*(.*?)[ \t]*$", text,
                      re.MULTILINE)
    return match.group(1) if match else None


def edge_kind(value: str | None) -> str:
    value = (value or "").replace("`", "").strip().lower()
    if value.startswith("none"):
        return "none"
    return re.split(r"[\s(,;]", value, maxsplit=1)[0] if value else ""


def _ledger_problem(row_id: str, ledger) -> str | None:
    verdicts = {row["id"]: row["verdict"] for row in ledger}
    if row_id not in verdicts:
        return f"ledger id {row_id} is not in the ledger"
    if verdicts[row_id] != SCREEN_PASS:
        return f"ledger id {row_id} is {verdicts[row_id]}, not {SCREEN_PASS}"
    return None


def _classify(screen: str, ledger, root: Path):
    """(kind, problem) for one Screen: value."""
    if _EXEMPT.match(screen):
        return "exempt", None
    match = _HEADROOM.match(screen)
    if match:
        missing = not (root / match.group(1)).exists()
        return "headroom", f"headroom path {match.group(1)} does not exist" if missing else None
    match = _LEDGER.match(screen)
    if match:
        return "ledger", _ledger_problem(match.group(1), ledger)
    return None, f"unrecognised Screen value `{screen}`"


def screen_problems(text: str, *, ledger, root: Path = ROOT) -> list:
    screen = header(text, "Screen")
    if screen is None:
        return ["missing **Screen:** line"]
    kind, problem = _classify(screen, ledger, root)
    if problem:
        return [problem]
    edge = edge_kind(header(text, "Edge"))
    if edge not in _EDGES_FOR[kind]:
        return [f"Screen `{screen}` does not fit Edge `{edge or '(missing)'}`"]
    return []


# -- unit tests -------------------------------------------------------------

LEDGER = [{"id": "screen-good", "verdict": "SCREEN-PASS"},
          {"id": "screen-bad", "verdict": "SCREEN-FAIL"}]


def _spec(edge="expectancy", screen=None):
    lines = ["# v999 demo", "", "**Bump:** none", f"**Edge:** {edge}"]
    if screen is not None:
        lines.append(f"**Screen:** {screen}")
    return "\n".join(lines + ["", "## Why", "text"]) + "\n"


def test_a_cited_screen_pass_is_accepted():
    assert screen_problems(_spec(screen="screen-good SCREEN-PASS"), ledger=LEDGER) == []


def test_a_volume_spec_may_cite_a_screen_pass():
    assert screen_problems(_spec("volume", "`screen-good` SCREEN-PASS"), ledger=LEDGER) == []


def test_a_missing_screen_line_fails():
    assert screen_problems(_spec(), ledger=LEDGER) == ["missing **Screen:** line"]


def test_an_unknown_ledger_id_fails():
    problems = screen_problems(_spec(screen="screen-nope SCREEN-PASS"), ledger=LEDGER)
    assert problems and "not in the ledger" in problems[0]


def test_a_non_pass_ledger_id_fails():
    problems = screen_problems(_spec(screen="screen-bad SCREEN-PASS"), ledger=LEDGER)
    assert problems and "SCREEN-FAIL" in problems[0]


def test_a_missing_headroom_path_fails(tmp_path):
    text = _spec("harvest", "harvest-headroom docs/superpowers/results/none.md")
    problems = screen_problems(text, ledger=LEDGER, root=tmp_path)
    assert problems and "does not exist" in problems[0]


def test_an_existing_headroom_path_passes_for_harvest_and_expectancy(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "headroom.md").write_text("x", encoding="utf-8")
    for edge in ("harvest", "expectancy"):
        text = _spec(edge, "harvest-headroom `docs/headroom.md`")
        assert screen_problems(text, ledger=LEDGER, root=tmp_path) == []


def test_exempt_needs_an_integrity_edge():
    assert screen_problems(_spec("none (integrity)", "exempt (integrity)"), ledger=LEDGER) == []
    problems = screen_problems(_spec("expectancy", "exempt (integrity)"), ledger=LEDGER)
    assert problems and "does not fit" in problems[0]


def test_a_ledger_pass_does_not_fit_a_harvest_edge():
    problems = screen_problems(_spec("harvest", "screen-good SCREEN-PASS"), ledger=LEDGER)
    assert problems and "does not fit" in problems[0]


def test_an_unrecognised_value_fails():
    problems = screen_problems(_spec(screen="pending"), ledger=LEDGER)
    assert problems and "unrecognised" in problems[0]


def test_edge_kind_reads_the_first_word():
    assert edge_kind("expectancy — the screen is a tightening") == "expectancy"
    assert edge_kind("`harvest`") == "harvest"
    assert edge_kind("none (integrity)") == "none"
    assert edge_kind(None) == ""


def test_grandfathered_and_split_specs_are_skipped(tmp_path):
    names = ["2026-10-08-v139-old-design.md", "2026-10-08-v140-idea-screen-design.md",
             "implemented/2026-10-09-v141-a-design.md",
             "no-lift/2026-10-10-v142-b-design.md",
             "2026-10-11-v143-c_0-index.md", "2026-10-11-v143-c_1-detail.md"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert {p.name for p in checked_specs(tmp_path)} == {
        "2026-10-09-v141-a-design.md", "2026-10-10-v142-b-design.md",
        "2026-10-11-v143-c_0-index.md"}


# -- the repository gate ----------------------------------------------------

def test_every_spec_above_v140_carries_a_valid_screen_line():
    ledger = stats.load_ledger()
    problems = {p.relative_to(ROOT).as_posix():
                screen_problems(p.read_text(encoding="utf-8"), ledger=ledger)
                for p in checked_specs()}
    assert {path: found for path, found in problems.items() if found} == {}
