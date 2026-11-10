"""v140 § Enforcement: every spec numbered above v140 carries a valid
**Screen:** header line under **Edge:**.

| Edge:                                                  | Screen:                                     |
| expectancy / volume adding an entry strategy or filter | `<ledger-id> SCREEN-PASS` (row must exist)  |
| expectancy moving stops/targets, or harvest            | `harvest-headroom <path>` (path must exist) |
| none (integrity)                                       | `exempt (integrity)`                        |
| expectancy, a fill-timing veto (alert-to-fill price)   | `exempt (post-signal)` (v192, 2026-10-24)   |
| expectancy, a veto filter licensed by an avoid screen  | `<ledger-id> SCREEN-AVOID-PASS (veto)` (v214) |

v140 and earlier are grandfathered by number. A split spec carries the line
in its _0-index part. See
docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from swingbot.core.backtesting.instrument import stats

ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = ROOT / "docs/superpowers/specs"
LAST_GRANDFATHERED = 140
SCREEN_PASS = "SCREEN-PASS"
SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"

_NUMBER = re.compile(r"^\d{4}-\d{2}-\d{2}-v(\d+)-")
_PART = re.compile(r"_(\d+)[a-z]?(?:-[^.]*)?\.md$")
_EXEMPT = re.compile(r"^exempt\b")
_POST_SIGNAL = re.compile(r"^exempt\s*\(post-signal\)")
_HEADROOM = re.compile(r"^harvest-headroom\s+`?([^`\s]+)`?")
_LEDGER = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-PASS\b")
_AVOID_VETO = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-AVOID-PASS\s+\(veto\)")
_AVOID_BARE = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-AVOID-PASS")
_PASS_VETO = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-PASS\s+\(veto\)")
_EDGES_FOR = {"exempt": {"none"}, "post_signal": {"expectancy"},
              "headroom": {"expectancy", "harvest"}, "ledger": {"expectancy", "volume"},
              "avoid_veto": {"expectancy"}}

#: v214 G6: the cited Screen forms, first match wins. A kind of None refuses
#: the value with the reason in the third slot.
_FORMS = (
    (_AVOID_VETO, "avoid_veto", SCREEN_AVOID_PASS),
    (_AVOID_BARE, None, "SCREEN-AVOID-PASS licenses a veto only: write "
                        "`<ledger-id> SCREEN-AVOID-PASS (veto)` under Edge: expectancy"),
    (_PASS_VETO, None, "`(veto)` goes only beside SCREEN-AVOID-PASS; cite a "
                       "SCREEN-PASS as `<ledger-id> SCREEN-PASS`"),
    (_LEDGER, "ledger", SCREEN_PASS),
)


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


def _ledger_problem(row_id: str, ledger, wanted: str = SCREEN_PASS) -> str | None:
    verdicts = {row["id"]: row["verdict"] for row in ledger}
    if row_id not in verdicts:
        return f"ledger id {row_id} is not in the ledger"
    if verdicts[row_id] != wanted:
        return f"ledger id {row_id} is {verdicts[row_id]}, not {wanted}"
    return None


def _cited(screen: str, ledger):
    """(kind, problem) for a ledger-citing Screen value, per ``_FORMS``."""
    for pattern, kind, wanted in _FORMS:
        match = pattern.match(screen)
        if match and kind:
            return kind, _ledger_problem(match.group(1), ledger, wanted)
        if match:
            return None, wanted
    return None, f"unrecognised Screen value `{screen}`"


def _classify(screen: str, ledger, root: Path):
    """(kind, problem) for one Screen: value."""
    if _POST_SIGNAL.match(screen):
        return "post_signal", None
    if _EXEMPT.match(screen):
        return "exempt", None
    match = _HEADROOM.match(screen)
    if match:
        missing = not (root / match.group(1)).exists()
        return "headroom", f"headroom path {match.group(1)} does not exist" if missing else None
    return _cited(screen, ledger)


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
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "headroom.md").write_text("x", encoding="utf-8")
    for edge in ("harvest", "expectancy"):
        text = _spec(edge, "harvest-headroom `notes/headroom.md`")
        assert screen_problems(text, ledger=LEDGER, root=tmp_path) == []


def test_exempt_needs_an_integrity_edge():
    assert screen_problems(_spec("none (integrity)", "exempt (integrity)"), ledger=LEDGER) == []
    problems = screen_problems(_spec("expectancy", "exempt (integrity)"), ledger=LEDGER)
    assert problems and "does not fit" in problems[0]


def test_post_signal_exemption_fits_only_an_expectancy_edge():
    assert screen_problems(_spec("expectancy", "exempt (post-signal)"), ledger=LEDGER) == []
    for edge in ("volume", "harvest", "none (integrity)"):
        problems = screen_problems(_spec(edge, "exempt (post-signal)"), ledger=LEDGER)
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


# -- v214 G6: an avoid pass licenses a veto only ------------------------------

AVOID_LEDGER = LEDGER + [{"id": "screen-avoid", "verdict": "SCREEN-AVOID-PASS"}]


def test_an_avoid_pass_cited_as_a_veto_fits_an_expectancy_spec():
    for screen in ("screen-avoid SCREEN-AVOID-PASS (veto)",
                   "`screen-avoid` SCREEN-AVOID-PASS (veto)"):
        assert screen_problems(_spec("expectancy", screen), ledger=AVOID_LEDGER) == []


@pytest.mark.parametrize("edge", ["volume", "harvest", "none (integrity)"])
def test_an_avoid_veto_fits_only_an_expectancy_edge(edge):
    problems = screen_problems(_spec(edge, "screen-avoid SCREEN-AVOID-PASS (veto)"),
                               ledger=AVOID_LEDGER)
    assert problems and "does not fit" in problems[0]


def test_an_avoid_pass_without_the_veto_suffix_fails():
    problems = screen_problems(_spec("expectancy", "screen-avoid SCREEN-AVOID-PASS"),
                               ledger=AVOID_LEDGER)
    assert problems and "SCREEN-AVOID-PASS (veto)" in problems[0]


def test_a_veto_suffix_beside_a_screen_pass_fails():
    problems = screen_problems(_spec("expectancy", "screen-good SCREEN-PASS (veto)"),
                               ledger=AVOID_LEDGER)
    assert problems and "only beside SCREEN-AVOID-PASS" in problems[0]


def test_an_avoid_veto_must_cite_an_avoid_pass_row():
    wrong = screen_problems(_spec("expectancy", "screen-good SCREEN-AVOID-PASS (veto)"),
                            ledger=AVOID_LEDGER)
    assert wrong == ["ledger id screen-good is SCREEN-PASS, not SCREEN-AVOID-PASS"]
    absent = screen_problems(_spec("expectancy", "screen-nope SCREEN-AVOID-PASS (veto)"),
                             ledger=AVOID_LEDGER)
    assert absent and "not in the ledger" in absent[0]


def test_a_screen_pass_cite_of_an_avoid_row_fails():
    problems = screen_problems(_spec("expectancy", "screen-avoid SCREEN-PASS"),
                               ledger=AVOID_LEDGER)
    assert problems == ["ledger id screen-avoid is SCREEN-AVOID-PASS, not SCREEN-PASS"]


def test_every_other_case_still_needs_a_screen_pass():
    assert screen_problems(_spec(screen="screen-good SCREEN-PASS"), ledger=AVOID_LEDGER) == []
    problems = screen_problems(_spec(screen="screen-bad SCREEN-PASS"), ledger=AVOID_LEDGER)
    assert problems == ["ledger id screen-bad is SCREEN-FAIL, not SCREEN-PASS"]


# -- the repository gate ----------------------------------------------------

def test_every_spec_above_v140_carries_a_valid_screen_line():
    ledger = stats.load_ledger()
    problems = {p.relative_to(ROOT).as_posix():
                screen_problems(p.read_text(encoding="utf-8"), ledger=ledger)
                for p in checked_specs()}
    assert {path: found for path, found in problems.items() if found} == {}
