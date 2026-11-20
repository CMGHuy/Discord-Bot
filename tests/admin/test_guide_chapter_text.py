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
#: Anchors chapters 1 and 3 link to (part 3 header of plan v236), plus the terms
#: chapters 4-8 link to (v237 V237-8).
GLOSSARY_LINKED = {
    "alert", "trade-plan", "paper-trade", "horizon", "long-and-short", "confidence",
    "watchlist-and-universe", "level", "level-family", "confluence", "scenario", "strategy",
    "completed-bar", "gate", "market-regime", "relative-strength", "stop", "tp1-and-tp2", "runner",
    "scale-out", "reward-to-risk-rr", "stop-distance-cap", "risk-per-trade", "dollar-risk-cap",
    "portfolio-heat", "correlated-heat", "size-0-alert", "gap-through-the-stop", "r-multiple", "badge",
    # v237 V237-8
    "level-lifecycle", "direction-mask", "drawdown-throttle", "kill-switch", "masked", "clamp",
    "rejected-plan", "suggested-size", "entry", "shadow-mode", "support-and-resistance",
    "provenance-label", "train-and-validation", "plan-states", "expectancy-expr"}


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


# --- v237 V237-8: glossary terms for chapters 4-8 ----------------------------------------

def _term(heading: str) -> str:
    return _chapter("glossary").body.split(f"### {heading}\n", 1)[1].split("\n#", 1)[0]


def test_glossary_holds_the_v237_terms_in_their_groups():
    body = _chapter("glossary").body
    assert len(GLOSSARY_LINKED) == 45
    for group, term in [("Levels and setups", "Level lifecycle"),
                        ("Levels and setups", "Direction mask"),
                        ("Risk and sizing", "Drawdown throttle"),
                        ("Risk and sizing", "Kill switch")]:
        assert f"### {term}\n" in _section(body, group), term


def test_glossary_level_lifecycle_and_throttle_follow_the_code():
    from swingbot.core.market import levels_lifecycle
    lifecycle = _term("Level lifecycle")
    assert all(state in lifecycle for state in levels_lifecycle.STATES)
    assert "retest" not in lifecycle.lower()
    assert "{{DD_THROTTLE_ENABLED}}" in _term("Drawdown throttle")
    assert "size of zero" in _term("Kill switch")
    assert "{{" not in placeholders.resolve(_term("Drawdown throttle"))


# --- chapter 4: levels (v237 V237-9, V237-9b) ------------------------------------------

CH4_ANCHORS = ["the-next-level-idea", "level-families", "confluence-counts-families",
               "bonus-confirmations", "touch-break-and-the-four-states",
               "higher-horizon-alignment", "closed-bars-only", "the-minimum-move",
               "duplicate-merge"]


def test_chapter_4_header_and_plain_words_callout():
    chapter = _chapter("levels")
    assert (chapter.order, chapter.title) == (4, "Finding levels and setups")
    assert chapter.path.name == "04-levels.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_4_sections_in_order():
    assert _anchors(_chapter("levels")) == CH4_ANCHORS


def test_chapter_4_families_come_from_the_live_list():
    from swingbot.core.market.levels import ALL_STRATEGY_FAMILIES
    section = _section(_chapter("levels").body, "Level families")
    assert "{{levels.families}}" in section
    rendered = placeholders.resolve(section)
    assert all(f"- {family}" in rendered for family in ALL_STRATEGY_FAMILIES)
    assert "chapter 5" in section          # families are kept apart from strategies


def test_chapter_4_confluence_counts_families_with_live_numbers():
    section = _section(_chapter("levels").body, "Confluence counts families")
    assert {"CLUSTER_TOLERANCE_PCT", "CONFLUENCE_DEVIATION_PCT", "MIN_TARGET_CONFLUENCE_COUNT",
            "MIN_ALERT_CONFIDENCE_LEVEL"} <= set(placeholders.names_in(section))
    assert "counts once" in section


def test_chapter_4_lifecycle_has_four_states_and_no_retest():
    from swingbot.core.market import levels_lifecycle
    body = _chapter("levels").body
    section = _section(body, "Touch, break and the four states")
    assert all(f"| {state} |" in section for state in levels_lifecycle.STATES)
    assert {"levels.touch_atr", "levels.break_atr",
            "LEVEL_LIFECYCLE_STOPS_ENABLED"} <= set(placeholders.names_in(section))
    assert "retest" not in body.lower()


def test_chapter_4_types_no_rule_number_before_a_percent_sign():
    body = re.sub(r"\{\{[^}]*\}\}", "", _chapter("levels").body)
    assert not re.search(r"(?<![\w.])\d+(?:\.\d+)?[ \t]?%", body)


def test_chapter_4_resolves_and_links_only_written_chapters():
    chapter = _chapter("levels")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE


def test_chapter_4_alignment_reads_the_switch_not_a_hard_coded_state():
    section = _section(_chapter("levels").body, "Higher-horizon alignment")
    assert "{{HTF_CONFLUENCE_ENABLED}}" in section
    assert "chapter 6" in section
    assert not re.search(r"\b(is|are|switched) (off|on)\b", section)


def test_chapter_4_minimum_move_and_confirmation_use_live_settings():
    body = _chapter("levels").body
    assert {"MIN_REWARD_PCT", "MIN_STOP_DISTANCE_PCT", "MIN_RISK_REWARD_RATIO"} <= set(
        placeholders.names_in(_section(body, "The minimum move")))
    assert "{{SIGNAL_CONFIRMATION_SCANS}}" in _section(body, "Closed bars only")
    assert "{{DEDUP_TOLERANCE_PCT}}" in _section(body, "Duplicate merge")


# --- chapter 5: strategies (v237 V237-10) ----------------------------------------------

CH5_ANCHORS = ["strategies-are-not-level-families", "how-a-strategy-alert-is-sent",
               "reading-a-card", "masked-strategies", "the-cards"]
CH5_LINKABLE = {"glossary", "pipeline", "what-it-is", "levels", "strategies"}
_NO_PCT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?[ \t]?%")


@pytest.fixture
def _unmeasured_badges(monkeypatch):
    """Every key reads as having no registry row, so no test depends on the committed registry."""
    from swingbot.admin.guide import live_strategies
    from swingbot.core.backtesting.registry import Badge
    monkeypatch.setattr(live_strategies, "_badge", lambda key: Badge("WEAK", 0, 0.0, 0.0))


def test_chapter_5_header_and_plain_words_callout():
    chapter = _chapter("strategies")
    assert (chapter.order, chapter.title) == (5, "Strategies")
    assert chapter.path.name == "05-strategies.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_5_sections_in_order():
    assert _anchors(_chapter("strategies")) == CH5_ANCHORS


def test_chapter_5_cards_placeholder_closes_the_chapter():
    body = _chapter("strategies").body
    assert body.rstrip().endswith("{{strategies.cards}}")
    assert placeholders.names_in(body).count("strategies.cards") == 1


def test_chapter_5_renders_one_card_per_registered_key(_unmeasured_badges):
    from swingbot.admin.guide import live_strategies
    rendered = placeholders.resolve(_section(_chapter("strategies").body, "The cards"))
    for key in live_market.registered_strategy_keys():
        assert f"### {key}\n" in rendered
    assert live_strategies.NO_ROW_MASKED in rendered
    assert "**Badge:** WEAK" not in rendered   # a key with no row never shows a tier


def test_chapter_5_badge_carries_its_provenance(monkeypatch):
    from swingbot.admin.guide import live_strategies
    from swingbot.core.backtesting.registry import Badge
    row = Badge("VALIDATED", 112, 50.0, 0.219, window="2024-01-01..2025-12-31",
                run_date="2026-08-17")
    monkeypatch.setattr(live_strategies, "_badge", lambda key: row)
    rendered = placeholders.resolve(_section(_chapter("strategies").body, "The cards"))
    assert "N = 112; as of 2026-08-17; costs not recorded; before tax" in rendered


def test_chapter_5_alert_path_reads_the_live_switches():
    section = _section(_chapter("strategies").body, "How a strategy alert is sent")
    assert {"STRATEGY_ALERTS_MODE", "STRATEGY_ALERTS_LIVE_STRATEGIES"} <= set(
        placeholders.names_in(section))
    assert all(f"| {mode} |" in section for mode in ("off", "shadow", "live"))


def test_chapter_5_reading_a_card_defines_the_shared_gates():
    import pandas as pd
    from swingbot.core.market.entry_filters import compute_shared_gates
    section = _section(_chapter("strategies").body, "Reading a card")
    assert "the shared gates" in section
    for label in ("Uptrend", "Medium-term trend", "Not dead flat", "Not panicking", "Real volume"):
        assert f"**{label}**" in section
    frame = pd.DataFrame({"Open": [10.0] * 30, "High": [11.0] * 30, "Low": [9.0] * 30,
                          "Close": [10.0] * 30, "Volume": [1000.0] * 30})
    gates = compute_shared_gates(frame)
    for name in ("bull_regime", "trend50_bull", "atr_floor", "atr_calm", "vol_ok"):
        assert name in gates and f"`{name}`" in section
    assert "not a forecast" in section
    assert "costs not recorded" in section and "before tax" in section


def test_chapter_5_masked_strategies_never_show_an_empty_badge():
    from swingbot.admin.guide import live_strategies
    section = _section(_chapter("strategies").body, "Masked strategies")
    assert live_strategies.NO_ROW_MASKED in section
    assert "masked — research only" in section
    assert "](/insights/guide/what-it-is#swing-horizons)" in section


def test_chapter_5_resolves_and_links_only_written_chapters(_unmeasured_badges):
    chapter = _chapter("strategies")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))


# --- chapter 6: gates (v237 V237-11, V237-11b) ------------------------------------------

CH6_ANCHORS = ["what-a-gate-does", "gates-in-the-live-scan", "direction-and-horizon-masks",
               "shared-entry-gates", "market-regime", "relative-strength",
               "higher-horizon-alignment", "post-signal-fill-vetoes", "measured-not-used"]
CH6_LINKABLE = CH5_LINKABLE | {"gates"}


def test_chapter_6_header_and_plain_words_callout():
    chapter = _chapter("gates")
    assert (chapter.order, chapter.title) == (6, "Filters and gates")
    assert chapter.path.name == "06-gates.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_6_sections_in_order():
    assert _anchors(_chapter("gates")) == CH6_ANCHORS


def test_chapter_6_masks_come_from_the_live_table():
    section = _section(_chapter("gates").body, "Direction and horizon masks")
    assert "{{gates.list}}" in section
    assert "| Strategy | Long | Short | Status |" in placeholders.resolve(section)


def test_chapter_6_live_scan_numbers_are_placeholders():
    section = _section(_chapter("gates").body, "Gates in the live scan")
    assert {"SIGNAL_CONFIRMATION_SCANS", "MIN_ALERT_CONFIDENCE_LEVEL"} <= set(
        placeholders.names_in(section))


def test_chapter_6_regime_is_a_score_and_its_gate_reads_the_switch_table():
    section = _section(_chapter("gates").body, "Market regime")
    assert "a score, not a gate" in section
    assert "first row of the switch table" in section


def test_chapter_6_never_types_a_switch_state():
    assert not re.search(r"\b(?:is|are) (?:on|off)\b", _chapter("gates").body)


def test_chapter_6_resolves_and_links_only_written_chapters():
    chapter = _chapter("gates")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))


def test_chapter_6_switch_table_lists_every_row():
    from swingbot.admin.guide import live_switches
    section = _section(_chapter("gates").body, "Measured, not used")
    assert "{{gates.switches}}" in section
    rendered = placeholders.resolve(section)
    assert "| Gate | Setting | Now | In the live scan |" in rendered
    assert all(f"| {row.label} |" in rendered for row in live_switches.SWITCH_ROWS)


@pytest.mark.parametrize("value, verdict", [(False, "measured, not used"), (True, "applied")])
def test_chapter_6_switch_state_follows_the_setting(monkeypatch, value, verdict):
    from swingbot import config
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", value)
    rendered = placeholders.resolve(_section(_chapter("gates").body, "Measured, not used"))
    row = next(line for line in rendered.splitlines()
               if line.startswith("| Dead-cat bounce veto |"))
    assert row.endswith(f"| {verdict} |")


@pytest.mark.parametrize("heading, names", [
    ("Relative strength", {"RS_GATE", "RS_LEADER_PERCENTILE", "RS_LAGGARD_PERCENTILE"}),
    ("Higher-horizon alignment", {"HTF_CONFLUENCE_ENABLED"}),
])
def test_chapter_6_switch_values_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("gates").body, heading)))


def test_chapter_6_names_the_built_but_unused_vetoes():
    section = _section(_chapter("gates").body, "Measured, not used")
    assert "dead-cat bounce veto" in section and "headroom veto" in section
    assert "built but off by default" in section
    assert "whatever this list says" in section   # the table, not the prose, decides

# --- chapter 7: trade plan (v237 V237-12, V237-12b) -------------------------------------

CH7_ANCHORS = ["entry", "the-stop", "the-stop-distance-cap-and-the-clamp",
               "the-stop-never-widens", "targets-that-pay-for-the-risk",
               "scale-out-and-the-runner", "how-a-plan-closes",
               "backtest-and-live-use-the-same-plan"]
CH7_LINKABLE = CH6_LINKABLE | {"trade-plan"}


def test_chapter_7_header_and_plain_words_callout():
    chapter = _chapter("trade-plan")
    assert (chapter.order, chapter.title) == (7, "Building the trade plan")
    assert chapter.path.name == "07-trade-plan.md"
    assert chapter.body.startswith("> **In plain words**")


def test_chapter_7_sections_in_order():
    assert _anchors(_chapter("trade-plan")) == CH7_ANCHORS


@pytest.mark.parametrize("heading, names", [
    ("Entry", {"plan.expiry_bars"}),
    ("The stop", {"MIN_STOP_DISTANCE_PCT", "LEVEL_LIFECYCLE_STOPS_ENABLED"}),
    ("The stop-distance cap and the clamp",
     {"stop.hard_cap", "stop.clamp_level", "CLAMP_STOP_TO_HARD_CAP"}),
])
def test_chapter_7_rule_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("trade-plan").body, heading)))


def test_chapter_7_clamp_renders_the_live_numbers():
    from swingbot.core.planning.builders import CLAMP_HEADROOM_PCT
    from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT
    section = _section(_chapter("trade-plan").body, "The stop-distance cap and the clamp")
    rendered = placeholders.resolve(section)
    assert f"{HARD_MAX_PLANNED_LOSS_PCT:g}%" in rendered
    assert f"{HARD_MAX_PLANNED_LOSS_PCT - CLAMP_HEADROOM_PCT:g}%" in rendered
    assert "`risk_cap`" in section


def test_chapter_7_hard_cap_binds_whatever_the_setting_reads():
    section = _section(_chapter("trade-plan").body, "The stop-distance cap and the clamp")
    assert "settings page" in section
    assert "still binds" in section
    assert "MAX_STOP_LOSS_PCT" in placeholders.names_in(section)


def test_chapter_7_names_edge_stops_only_as_not_adopted():
    body = _chapter("trade-plan").body
    assert "`edge/stops.py`" in body and "DATA_DRIVEN_STOPS_ENABLED" in body
    assert "](/insights/guide/gates#measured-not-used)" in body
    # The live plan manager scales out whenever tp1_fraction < 1; SCALE_OUT_ENABLED has no
    # live reader (scan_params.scale_out_enabled is never read), so the chapter does not cite it.
    assert "SCALE_OUT_ENABLED" not in body


def test_chapter_7_pending_plan_is_cancelled_when_price_trades_through_the_stop():
    section = _section(_chapter("trade-plan").body, "Entry")
    assert "trades through its stop" in section
    assert "closes through its stop" not in section


def test_chapter_7_resolves_and_links_only_written_chapters():
    chapter = _chapter("trade-plan")
    assert "{{" not in placeholders.resolve(chapter.body)
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))


def test_chapter_7_stop_never_widens_and_gaps_can_pass_it():
    section = _section(_chapter("trade-plan").body, "The stop never widens")
    assert "tighter" in section and "loosen" in section
    assert "glossary#gap-through-the-stop" in section


@pytest.mark.parametrize("heading, names", [
    ("Targets that pay for the risk",
     {"MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO", "MIN_REWARD_PCT"}),
    ("Scale-out and the runner",
     {"plan.breakeven_trigger", "plan.tp1_share", "plan.runner_floor", "plan.trail_atr"}),
    ("Backtest and live use the same plan", {"PLAN_ENGINE_V2"}),
])
def test_chapter_7_exit_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("trade-plan").body, heading)))


def test_chapter_7_targets_have_no_fallback_and_tp2_is_optional():
    section = _section(_chapter("trade-plan").body, "Targets that pay for the risk")
    assert "no fallback" in section
    assert "has a TP2 only when" in section


def test_chapter_7_close_table_lists_every_outcome():
    section = _section(_chapter("trade-plan").body, "How a plan closes")
    for outcome in ("expired", "invalidated", "cancelled at the cap", "gap through the stop",
                    "loss", "scratch", "TP1, runner at the floor", "TP1, runner trailed",
                    "TP1, then TP2"):
        assert f"| {outcome} |" in section
    for reason in ("tp1_runner_be", "tp1_runner_trail", "tp1_runner_tp2"):
        assert f"`{reason}`" in section


# --- chapter 8: sizing and risk (v237 V237-13, V237-13b) --------------------------------

CH8_ANCHORS = ["three-limits-not-one", "how-the-share-count-is-found", "sizing-modes",
               "gap-aware-sizing", "portfolio-and-correlated-heat",
               "drawdown-throttle-and-kill-switch", "reject-clamp-or-size-0",
               "caps-that-are-not-applied", "costs-turnover-and-tax"]
CH8_LINKABLE = CH7_LINKABLE | {"sizing-risk"}
CH8_NOTICE = ("Education about a paper-trading tool, not advice: alerts are not tailored to you, "
              "a suggested size is a default, and past results do not predict future ones.")


def test_chapter_8_header_callout_and_notice():
    chapter = _chapter("sizing-risk")
    assert (chapter.order, chapter.title) == (8, "Sizing and risk")
    assert chapter.path.name == "08-sizing-risk.md"
    blocks = chapter.body.split("\n\n")
    assert blocks[0].startswith("> **In plain words**")
    assert blocks[1] == CH8_NOTICE


def test_chapter_8_sections_in_order():
    assert _anchors(_chapter("sizing-risk")) == CH8_ANCHORS


@pytest.mark.parametrize("heading, names", [
    ("Three limits, not one", {"stop.hard_cap", "MAX_STOP_LOSS_PCT", "RISK_PER_TRADE_PCT",
                               "RISK_PER_TRADE_PCT.max", "MAX_RISK_AMOUNT_ABSOLUTE"}),
    ("How the share count is found", {"MAX_POSITION_SIZE_PCT", "MAX_POSITION_VALUE_ABSOLUTE",
                                      "sizing.risk_ceiling"}),
    ("Sizing modes", {"POSITION_SIZING_MODE", "sizing.kelly_cap", "sizing.risk_floor"}),
    ("Gap-aware sizing", {"sizing.gap"}),
])
def test_chapter_8_sizing_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("sizing-risk").body, heading)))


def test_chapter_8_limits_come_from_the_stored_account(monkeypatch):
    monkeypatch.setattr(live_risk, "_load_account",
                        lambda: {**_ACCOUNT_ROW, "risk_pct": 0.5, "max_risk_amount_absolute": 250.0})
    rendered = placeholders.resolve(_section(_chapter("sizing-risk").body, "Three limits, not one"))
    assert "0.5%" in rendered and "$250" in rendered


def test_chapter_8_says_the_edge_modes_get_no_estimate_live():
    section = _section(_chapter("sizing-risk").body, "Sizing modes")
    assert "The alert path passes them no strategy record and no volatility reading" in section


def test_chapter_8_says_the_risk_floor_can_raise_a_low_risk():
    section = _section(_chapter("sizing-risk").body, "Sizing modes")
    assert "even when the risk per trade is set lower" in section
    assert "never raise it" not in section


def test_chapter_8_resolves_and_links_only_written_chapters():
    chapter = _chapter("sizing-risk")
    rendered = placeholders.resolve(chapter.body)
    assert "{{" not in rendered and "not available right now" not in rendered
    links = _GUIDE_LINK.findall(chapter.body)
    glossary = {anchor for slug, anchor in links if slug == "glossary"}
    assert glossary and glossary <= GLOSSARY_LINKED
    assert {slug for slug, _anchor in links} <= CH8_LINKABLE
    assert not _NO_PCT.search(re.sub(r"\{\{[^}]*\}\}", "", chapter.body))


def _code_calls(pattern: str, *, skip: tuple[str, ...]) -> list[str]:
    """Files under swingbot/ (outside the `skip` prefixes) whose text matches `pattern`."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    found = []
    for path in sorted((root / "swingbot").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if not rel.startswith(skip) and re.search(pattern, path.read_text(encoding="utf-8")):
            found.append(rel)
    return found


@pytest.mark.parametrize("heading, names", [
    ("Portfolio and correlated heat", {"PORTFOLIO_HEAT_CAP_PCT", "CORRELATED_HEAT_CAP_PCT",
                                       "correlation.threshold", "correlation.window"}),
    ("Drawdown throttle and kill switch", {"throttle.ladder", "throttle.resume", "throttle.streak",
                                           "DD_THROTTLE_ENABLED", "KILLSWITCH_DEFAULT_ON"}),
    ("Reject, clamp or size 0", {"stop.clamp_level", "CLAMP_STOP_TO_HARD_CAP"}),
    ("Caps that are not applied", {"SECTOR_HEAT_CAP_PCT", "MAX_OPEN_POSITIONS",
                                   "correlation.sector_fallback"}),
    ("Costs, turnover and tax", {"alerts.per_week"}),
])
def test_chapter_8_portfolio_numbers_are_placeholders(heading, names):
    assert names <= set(placeholders.names_in(_section(_chapter("sizing-risk").body, heading)))


def test_chapter_8_size_0_headlines_match_the_alert_embed():
    from pathlib import Path
    embeds = (Path(__file__).resolve().parents[2]
              / "swingbot" / "core" / "scanning" / "alert_embeds.py").read_text(encoding="utf-8")
    section = _section(_chapter("sizing-risk").body, "Reject, clamp or size 0")
    for headline in ("⛔ ENTRY BLOCKED — portfolio heat cap",
                     "⛔ ENTRY BLOCKED — correlated cluster",
                     "⛔ ENTRIES PAUSED (kill switch"):
        assert headline in section and headline in embeds
    assert "`plan rejected (" in section


def test_chapter_8_says_which_brake_acts_on_alerts():
    section = _section(_chapter("sizing-risk").body, "Drawdown throttle and kill switch")
    assert "does not apply it" in section and "`!killswitch off`" in section
    assert "`!killswitch on`" in section


def test_chapter_8_unapplied_caps_are_still_unwired():
    """If one of these gains a live caller, chapter 8 must change with it."""
    section = _section(_chapter("sizing-risk").body, "Caps that are not applied")
    assert "MAX_OPEN_PER_HORIZON" in section and "not applied to the live scan" in section
    assert _code_calls(r"(sector_check|horizon_check|streak_multiplier)\(",
                       skip=("swingbot/core/edge/heat.py", "swingbot/core/edge/throttle.py")) == []
    assert _code_calls(r"DD_THROTTLE_ENABLED",
                       skip=("swingbot/config.py", "swingbot/admin/guide/")) == []


def test_chapter_8_costs_section_gives_no_tax_advice():
    section = _section(_chapter("sizing-risk").body, "Costs, turnover and tax")
    assert "before tax" in section and "ask a tax adviser" in section


def test_glossary_drawdown_throttle_agrees_with_chapter_8():
    term = _term("Drawdown throttle")
    assert "does not apply it" in term and "{{DD_THROTTLE_ENABLED}}" in term
    assert "When switched on" not in term


def test_glossary_size_0_alert_names_the_kill_switch():
    assert "kill switch" in _term("Size-0 alert")


# --- v237 V237-14: chapters 4-8 link every chapter they name ---------------------------

TRADING_CHAPTERS = ("levels", "strategies", "gates", "trade-plan", "sizing-risk")
_PLAIN_CHAPTER = re.compile(r"(?<!\[)\bchapters? [4-8]\b", re.I)


@pytest.mark.parametrize("slug", TRADING_CHAPTERS)
def test_trading_chapters_link_every_chapter_they_name(slug):
    assert _PLAIN_CHAPTER.findall(_chapter(slug).body) == []


@pytest.mark.parametrize("slug", TRADING_CHAPTERS)
def test_trading_chapter_links_land_on_real_headings(slug):
    for target, anchor in _GUIDE_LINK.findall(_chapter(slug).body):
        if anchor and target != "glossary":
            assert anchor in _anchors(_chapter(target)), f"{slug} -> {target}#{anchor}"


def test_chapter_links_point_where_the_text_says():
    expected = {
        "levels": {("strategies", "strategies-are-not-level-families"), ("trade-plan", "the-stop"),
                   ("gates", "higher-horizon-alignment"), ("trade-plan", "the-stop-distance-cap-and-the-clamp")},
        "strategies": {("levels", ""), ("gates", "market-regime"), ("gates", "relative-strength"),
                       ("gates", "measured-not-used"), ("trade-plan", "targets-that-pay-for-the-risk"),
                       ("gates", "")},
        "gates": {("levels", "the-minimum-move"), ("trade-plan", "the-stop-distance-cap-and-the-clamp"),
                  ("sizing-risk", "portfolio-and-correlated-heat")},
        "trade-plan": {("sizing-risk", "how-the-share-count-is-found")},
    }
    for slug, links in expected.items():
        assert links <= set(_GUIDE_LINK.findall(_chapter(slug).body)), slug
