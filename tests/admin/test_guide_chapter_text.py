"""v236 V236-8..V236-10: what chapters 1, 3 and 12 must keep saying (spec v215).

The generic checks (placeholders, sources, headings, figures, anchor fixture)
live in test_guide_content.py; this module pins each chapter's own promises.
"""
from __future__ import annotations

import re

import pytest

from swingbot.admin.guide import chapters, live_market, live_risk, placeholders

#: Spec v215 § What the reader gets: the twelve chapter slugs.
SPEC_SLUGS = frozenset({
    "what-it-is", "reading-an-alert", "pipeline", "levels", "strategies", "gates",
    "trade-plan", "sizing-risk", "after-the-alert", "measuring-edge", "admin-tour", "glossary"})
_GUIDE_LINK = re.compile(r"\]\(/insights/guide/([a-z0-9-]+)(?:#([a-z0-9_-]+))?\)")
_SELF_LINK = re.compile(r"\]\(#([a-z0-9_-]+)\)")


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


def _by_slug() -> dict[str, chapters.Chapter]:
    return {chapter.slug: chapter for chapter in chapters.load_chapters()}


def _chapter(slug: str) -> chapters.Chapter:
    found = _by_slug().get(slug)
    assert found is not None, f"docs/guide has no chapter '{slug}'"
    return found


def _anchors(chapter: chapters.Chapter) -> list[str]:
    return [heading.anchor for heading in chapter.headings]


def _section(body: str, heading: str) -> str:
    """The text under one `## heading`, up to the next `## `."""
    return body.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _link_problems(loaded: dict[str, chapters.Chapter]) -> list[str]:
    problems = []
    for chapter in loaded.values():
        name = chapter.path.name
        for slug, anchor in _GUIDE_LINK.findall(chapter.body):
            if slug not in SPEC_SLUGS:
                problems.append(f"{name}: /insights/guide/{slug} is not a guide chapter")
            elif anchor and slug in loaded and anchor not in _anchors(loaded[slug]):
                problems.append(f"{name}: #{anchor} is not a heading of {slug}")
        problems += [f"{name}: #{anchor} is not a heading of this chapter"
                     for anchor in _SELF_LINK.findall(chapter.body)
                     if anchor not in _anchors(chapter)]
    return problems


# --- chapter 1: what-it-is ---------------------------------------------------

def test_chapter_1_header_and_plain_words_callout():
    chapter = _chapter("what-it-is")
    assert (chapter.order, chapter.title) == (1, "What the bot is (and isn't)")
    assert chapter.path.name == "01-what-it-is.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_1_sections_in_order():
    assert _anchors(_chapter("what-it-is")) == [
        "what-it-does", "what-it-does-not-do", "swing-horizons", "what-an-alert-is",
        "where-alerts-appear", "the-notice"]


def test_chapter_1_says_paper_only_and_that_the_demo_is_not_live():
    section = _section(_chapter("what-it-is").body, "What it does not do")
    assert "It never places an order." in section
    assert "A demo account is not a live account" in section
    assert "nothing is sent to eToro today" in section


def test_chapter_1_carries_the_full_notice():
    notice = _section(_chapter("what-it-is").body, "The notice")
    for phrase in ("This guide is education about a paper-trading tool",
                   "Alerts are not recommendations tailored to you",
                   "A suggested size is a default, not advice",
                   "Past results do not predict future ones"):
        assert phrase in notice, phrase


def test_chapter_1_horizons_come_from_the_live_table():
    section = _section(_chapter("what-it-is").body, "Swing horizons")
    assert "{{horizons.table}}" in section
    rendered = placeholders.resolve(section)
    assert "| Horizon | Swing | Longest hold | Status |" in rendered
    assert "{{" not in rendered


# --- every chapter -----------------------------------------------------------

def test_internal_links_name_a_guide_chapter_and_a_real_anchor():
    """Anchors are checked for chapters that exist; V236-10 also requires the chapter."""
    assert _link_problems(_by_slug()) == []


def test_link_checker_reports_a_bad_slug_and_a_missing_anchor(tmp_path):
    (tmp_path / "01-what-it-is.md").write_text(
        "---\ntitle: T\nslug: what-it-is\norder: 1\nreviewed_for: 2.19.2\nsources: []\n---\n"
        "> **In plain words** x.\n\n## Real\n\n[a](/insights/guide/nowhere) [b](#ghost) "
        "[c](/insights/guide/what-it-is#real) [d](/insights/guide/what-it-is#gone)\n",
        encoding="utf-8")
    loaded = {c.slug: c for c in chapters.load_chapters(tmp_path)}
    assert _link_problems(loaded) == [
        "01-what-it-is.md: /insights/guide/nowhere is not a guide chapter",
        "01-what-it-is.md: #gone is not a heading of what-it-is",
        "01-what-it-is.md: #ghost is not a heading of this chapter",
    ]


# --- chapter 3: pipeline -----------------------------------------------------

PIPELINE_ANCHORS = [
    "watchlist", "price-data", "levels-from-every-method", "duplicate-merge",
    "setups-and-strategy-signals", "confluence-scenarios", "strategy-signals", "gates",
    "plan-construction", "sizing-and-caps", "alert", "monitoring", "close"]


def test_chapter_3_header_and_plain_words_callout():
    chapter = _chapter("pipeline")
    assert (chapter.order, chapter.title) == (3, "The scan pipeline, end to end")
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_3_walks_the_pipeline_in_order():
    assert _anchors(_chapter("pipeline")) == PIPELINE_ANCHORS


def test_chapter_3_places_the_diagram_once_before_the_first_stage():
    body = _chapter("pipeline").body
    assert chapters.FIGURE_RE.findall(body) == ["pipeline"]
    assert body.index("<!-- figure:pipeline -->") < body.index("## Watchlist")


def test_chapter_3_takes_every_rule_number_from_a_placeholder():
    names = set(placeholders.names_in(_chapter("pipeline").body))
    assert {"levels.families", "CLUSTER_TOLERANCE_PCT", "MAX_STOP_LOSS_PCT", "CLAMP_STOP_TO_HARD_CAP",
            "RISK_PER_TRADE_PCT", "MAX_RISK_AMOUNT_ABSOLUTE", "POSITION_SIZING_MODE",
            "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT"} <= names
    rendered = placeholders.resolve(_section(_chapter("pipeline").body, "Sizing and caps"))
    assert "{{" not in rendered and "%" in rendered


def test_chapter_3_names_the_three_sizing_outcomes():
    section = _section(_chapter("pipeline").body, "Sizing and caps")
    for outcome in ("**rejected**", "**clamped**", "**size-0 alert**", "`plan rejected (`"):
        assert outcome in section, outcome


def test_chapter_3_sources_cover_every_stage():
    paths = {entry.partition(":")[0] for entry in _chapter("pipeline").sources}
    assert {
        "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/fetch.py",
        "swingbot/core/market/levels.py", "swingbot/core/scanning/dedup.py",
        "swingbot/core/scanning/strategy_pass.py", "swingbot/core/scanning/analyze.py",
        "swingbot/core/scanning/gating.py", "swingbot/core/planning/builders.py",
        "swingbot/core/planning/account.py", "swingbot/core/edge/heat.py",
        "swingbot/core/edge/correlation.py", "swingbot/core/scanning/alert_embeds.py",
        "swingbot/core/tracking/performance.py", "swingbot/core/planning/plan_engine.py",
        "frontend/src/app/workspaces/guide/pipeline-diagram.ts"} <= paths


# --- chapter 12: glossary ----------------------------------------------------

GLOSSARY_GROUPS = ["the-bot-and-its-alerts", "levels-and-setups", "inside-a-trade-plan",
                   "risk-and-sizing", "measuring-results", "about-this-guide"]
#: Anchors chapters 1 and 3 link to (part 3 header of plan v236).
GLOSSARY_LINKED = {
    "alert", "trade-plan", "paper-trade", "horizon", "long-and-short", "confidence",
    "watchlist-and-universe", "level", "level-family", "confluence", "scenario", "strategy",
    "completed-bar", "gate", "market-regime", "relative-strength", "stop", "tp1-and-tp2", "runner",
    "scale-out", "reward-to-risk-rr", "stop-distance-cap", "risk-per-trade", "dollar-risk-cap",
    "portfolio-heat", "correlated-heat", "size-0-alert", "gap-through-the-stop", "r-multiple", "badge"}


def test_glossary_header_and_plain_words_callout():
    chapter = _chapter("glossary")
    assert (chapter.order, chapter.title, chapter.path.name) == (12, "Glossary", "12-glossary.md")
    assert chapter.body.startswith("> **In plain words**")


def test_glossary_groups_terms_one_heading_each():
    headings = _chapter("glossary").headings
    assert [h.anchor for h in headings if h.level == 2] == GLOSSARY_GROUPS
    terms = [h.text.lower() for h in headings if h.level == 3]
    assert len(terms) >= 45
    assert len(set(terms)) == len(terms), "a term is defined twice"


def test_glossary_defines_every_term_the_guide_links_to():
    assert GLOSSARY_LINKED <= set(_anchors(_chapter("glossary")))
    linked = {anchor for chapter in _by_slug().values()
              for slug, anchor in _GUIDE_LINK.findall(chapter.body) if slug == "glossary" and anchor}
    assert linked <= set(_anchors(_chapter("glossary")))


def test_every_linked_chapter_is_written():
    """From V236-10 on, prose links only to chapters that exist (no dead links)."""
    loaded = _by_slug()
    dead = sorted({f"{c.path.name} -> {slug}" for c in loaded.values()
                   for slug, _anchor in _GUIDE_LINK.findall(c.body) if slug not in loaded})
    assert dead == []
    assert _link_problems(loaded) == []


def test_glossary_risk_numbers_come_from_placeholders():
    body = _chapter("glossary").body
    assert {"MAX_STOP_LOSS_PCT", "RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE",
            "PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT", "correlation.threshold",
            "correlation.window", "CLUSTER_TOLERANCE_PCT"} <= set(placeholders.names_in(body))
    assert "{{" not in placeholders.resolve(body)
