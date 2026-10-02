"""V118-8 part A: the inert per-mode admission guard for the SHORT extra lane.

Broad and isolated are admitted separately behind default-off flags; a mode not
admitted never reaches the analysis/alert stages, and with none admitted the
lane never fetches.
"""
import asyncio
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import short_run
from swingbot.core.scanning.short_candidates import ShortCandidate, admitted_short_modes
from tests.scanning.test_short_lane_scan import CANDIDATE, both_directions, lane  # noqa: F401  (fixture reuse)


def emit_modes(*, enabled, allowed):
    cfg = SimpleNamespace(SHORT_UNIVERSE_ENABLED=enabled,
                          SHORT_UNIVERSE_BROAD_ENABLED="broad" in allowed,
                          SHORT_UNIVERSE_ISOLATED_ENABLED="isolated" in allowed)
    return set(admitted_short_modes(cfg))


def test_guard_default_off_neither_broad_isolated_only():
    assert emit_modes(enabled=False, allowed={"broad", "isolated"}) == set()
    assert emit_modes(enabled=True, allowed={"broad"}) == {"broad"}
    assert emit_modes(enabled=True, allowed={"isolated"}) == {"isolated"}
    assert emit_modes(enabled=True, allowed=set()) == set()
    assert emit_modes(enabled=True, allowed={"broad", "isolated"}) == {"broad", "isolated"}


def test_all_three_flags_default_false():
    assert config.SHORT_UNIVERSE_ENABLED is False
    assert config.SHORT_UNIVERSE_BROAD_ENABLED is False
    assert config.SHORT_UNIVERSE_ISOLATED_ENABLED is False
    assert admitted_short_modes(config) == frozenset()


def _set(monkeypatch, enabled, broad, isolated):
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ENABLED", enabled)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_BROAD_ENABLED", broad)
    monkeypatch.setattr(config, "SHORT_UNIVERSE_ISOLATED_ENABLED", isolated)


def test_no_admitted_mode_means_no_fetch_even_with_the_master_flag_on(lane, monkeypatch):
    _set(monkeypatch, True, False, False)
    assert asyncio.run(short_run.run_short_universe_scan()) == []
    assert lane["bounded"] == [] and lane["built"] == []


def test_selector_firing_for_a_non_admitted_mode_emits_nothing(lane, monkeypatch):
    _set(monkeypatch, True, False, True)          # isolated only; the selector yields a broad candidate
    short_run._sync_run_short_scan(False)
    assert lane["built"][0] == []


def test_admitted_mode_still_reaches_the_alert_stage(lane, monkeypatch):
    _set(monkeypatch, True, True, False)
    short_run._sync_run_short_scan(False)
    assert [i.candidate_context["mode"] for i in lane["built"][0]] == ["broad"]


def test_isolated_candidate_dropped_when_only_broad_is_admitted(lane, monkeypatch):
    iso = ShortCandidate("AAA", "isolated", "short_universe", "2026-09-18", "2026-09-01", "ref-1")
    monkeypatch.setattr(short_run.scan_run, "build_extra_candidates", lambda *a, **k: [iso])
    _set(monkeypatch, True, True, False)
    short_run._sync_run_short_scan(False)
    assert lane["built"][0] == []


@pytest.mark.parametrize("modes,expected", [
    (frozenset(), []), (frozenset({"broad"}), ["broad"]),
    (frozenset({"isolated"}), []), (frozenset({"broad", "isolated"}), ["broad"])])
def test_filter_keeps_only_admitted_modes(modes, expected):
    assert [c.mode for c in short_run._admitted_candidates([CANDIDATE], modes)] == expected
