"""v103: a strategy gated to no direction must not render as 'no gate'."""
from swingbot.admin import queries


def test_empty_directions_reads_disabled(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ()})
    assert queries._gate_description("Probe") == "disabled (no direction allowed)"


def test_single_direction_and_missing_gate_are_unchanged(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": ("bullish",)})
    assert queries._gate_description("Probe") == "bullish only"
    monkeypatch.delitem(queries.STRATEGY_GATES, "Probe")
    assert queries._gate_description("Probe") == "no gate (all directions, all horizons)"


def test_cells_are_rendered(monkeypatch):
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert queries._gate_description("Probe") == "only bearish 1w"
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {
        "directions": ("bullish",), "horizons": ("3m",), "cells": {("bearish", "1w")}})
    assert queries._gate_description("Probe") == "bullish only {3m} + bearish 1w"
    monkeypatch.setitem(queries.STRATEGY_GATES, "Probe", {"cells": {("bullish", "1w")}})
    assert queries._gate_description("Probe") == "no gate (all directions, all horizons) + bullish 1w"
