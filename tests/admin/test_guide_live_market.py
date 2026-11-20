"""v235 V235-4: market placeholders, alerts per week and registered keys."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.admin.guide import live_market as lm, live_risk, live_rules, placeholders as ph
from swingbot.core.market import levels, strategy_types

MARKET_NAMES = {"levels.families", "CLUSTER_TOLERANCE_PCT", "horizons.table", "gates.list",
                "alerts.per_week"}
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)   # a Wednesday


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(lm, "_load_trades", lambda: [])
    monkeypatch.setattr(lm, "_now", lambda: NOW)


def _render(name: str) -> str:
    return ph.resolve("{{" + name + "}}")


def _row(table: str, first_cell: str) -> str:
    rows = [line for line in table.splitlines() if line.startswith(f"| {first_cell} |")]
    assert len(rows) == 1, (first_cell, table)
    return rows[0]


# --- registry ------------------------------------------------------------------

def test_market_table_has_exactly_the_planned_names():
    assert set(lm.MARKET_PLACEHOLDERS) == MARKET_NAMES


def test_registry_merges_both_tables_and_nothing_else():
    assert set(ph.PLACEHOLDERS) == (set(live_risk.RISK_PLACEHOLDERS) | MARKET_NAMES
                                    | set(live_rules.RULE_PLACEHOLDERS))


@pytest.mark.parametrize("name", sorted(MARKET_NAMES))
def test_every_market_placeholder_renders_plain_text(name):
    out = _render(name)
    assert out.strip() and "{{" not in out


def test_no_sensitive_field_value_reaches_a_market_placeholder(monkeypatch):
    for f in (f for f in config.FIELDS if f.sensitive):
        monkeypatch.setattr(config, f.attr, f"SENTINEL-{f.attr}", raising=False)
    rendered = "\n".join(_render(name) for name in sorted(MARKET_NAMES))
    assert "SENTINEL-" not in rendered


# --- levels ----------------------------------------------------------------------

@pytest.mark.parametrize("enabled, state", [(True, "on"), (False, "off")])
def test_families_list_every_family_and_mark_avwap(monkeypatch, enabled, state):
    monkeypatch.setattr(config, "AVWAP_LEVELS_ENABLED", enabled)
    lines = _render("levels.families").splitlines()
    assert len(lines) == len(levels.ALL_STRATEGY_FAMILIES)
    for line, family in zip(lines, levels.ALL_STRATEGY_FAMILIES):
        assert line.startswith(f"- {family}")
    assert f"- AVWAP (only when `AVWAP_LEVELS_ENABLED`; currently {state})" in lines


def test_cluster_tolerance_reads_the_module_constant(monkeypatch):
    assert _render("CLUSTER_TOLERANCE_PCT") == f"{levels.CLUSTER_TOLERANCE_PCT:g}%"
    monkeypatch.setattr(levels, "CLUSTER_TOLERANCE_PCT", 2.0)
    assert _render("CLUSTER_TOLERANCE_PCT") == "2%"


# --- horizons --------------------------------------------------------------------

def test_horizons_table_has_every_key_and_marks_masked_ones():
    table = _render("horizons.table")
    assert table.splitlines()[0] == "| Horizon | Swing | Longest hold | Status |"
    assert len(table.splitlines()) == len(strategy_types.HORIZONS) + 2
    for key, spec in strategy_types.HORIZONS.items():
        row = _row(table, f"`{key}`")
        assert spec["label"] in row and f"{spec['max_holding_days']} days" in row
    assert _row(table, "`1w`").endswith("| masked — research only |")
    assert _row(table, "`2w`").endswith("| live |")


def test_a_cell_that_admits_a_masked_horizon_shows_it_live(monkeypatch):
    monkeypatch.setitem(strategy_types.STRATEGY_GATES, strategy_types.TURTLE_SOUP,
                        {"directions": (), "cells": {("bullish", "1w")}})
    assert _row(_render("horizons.table"), "`1w`").endswith("| live |")


# --- gates -----------------------------------------------------------------------

def test_gates_list_has_one_row_per_registered_key():
    table = _render("gates.list")
    assert table.splitlines()[0] == "| Strategy | Long | Short | Status |"
    for key in lm.registered_strategy_keys():
        _row(table, key)


def test_gates_list_reads_admits():
    table = _render("gates.list")
    assert _row(table, "VWAP") == "| VWAP | 4w | — | live |"
    assert _row(table, "Break & Retest") == "| Break & Retest | 2m, 3m, 4m | 2m, 3m, 4m | live |"
    assert _row(table, "EMA Crossover") == ("| EMA Crossover | every live horizon | "
                                             "every live horizon | live |")
    assert _row(table, "Fibonacci") == "| Fibonacci | every live horizon | — | live |"
    assert _row(table, "Turtle Soup") == "| Turtle Soup | — | — | masked — research only |"


def test_gates_list_follows_a_cell_at_call_time(monkeypatch):
    monkeypatch.setitem(strategy_types.STRATEGY_GATES, strategy_types.TURTLE_SOUP,
                        {"directions": (), "cells": {("bullish", "2w")}})
    assert _row(_render("gates.list"), "Turtle Soup") == "| Turtle Soup | 2w | — | live |"


# --- registered keys ---------------------------------------------------------------

def test_registered_keys_are_the_sorted_union():
    from swingbot.core.market.strategy import STRATEGY_FUNCS
    keys = lm.registered_strategy_keys()
    assert keys == tuple(sorted(set(STRATEGY_FUNCS) | set(strategy_types.STRATEGY_GATES)))
    assert "EMA Crossover" in keys and "Turtle Soup" in keys


@pytest.mark.parametrize("key, slug", [
    ("Break & Retest", "break-retest"),
    ("Support/Resistance", "supportresistance"),
    ("Fibonacci Limit", "fibonacci-limit"),
    ("RSI", "rsi"),
])
def test_strategy_file_slug(key, slug):
    assert lm.strategy_file_slug(key) == slug


def test_strategy_file_slugs_are_unique():
    slugs = [lm.strategy_file_slug(k) for k in lm.registered_strategy_keys()]
    assert len(slugs) == len(set(slugs))


# --- alerts per week -----------------------------------------------------------------

def test_alerts_per_week_counts_the_last_eight_full_weeks(monkeypatch):
    trades = [
        {"opened_at": "2026-11-17T10:00:00+00:00"},   # this week: excluded
        {"opened_at": "2026-11-15T23:59:00+00:00"},   # last full week: in
        {"opened_at": "2026-09-21T00:00:00+00:00"},   # window start, inclusive: in
        {"opened_at": "2026-09-20T23:59:59+00:00"},   # before the window: out
        {"opened_at": "2026-10-01T10:00:00Z"},        # Z suffix: in
        {"opened_at": "2026-10-02T10:00:00"},         # naive, read as UTC: in
        {"opened_at": None},
        {"opened_at": "garbage"},
        {},
    ]
    monkeypatch.setattr(lm, "_load_trades", lambda: trades)
    assert _render("alerts.per_week") == (
        "0.5 alerts a week, mean of the last 8 full weeks (Source: live paper book; "
        "N = 4; as of 2026-11-18; costs not included; before tax)")


def test_alerts_per_week_empty_book():
    assert _render("alerts.per_week") == (
        "no live alerts in the last 8 weeks (Source: live paper book; N = 0; "
        "as of 2026-11-18; costs not included; before tax)")


def test_alerts_per_week_survives_an_unreadable_book(monkeypatch, caplog):
    def boom():
        raise RuntimeError("database down")
    monkeypatch.setattr(lm, "_load_trades", boom)
    assert _render("alerts.per_week") == (
        "not available right now (the live paper book could not be read)")
    assert "database down" in caplog.text
