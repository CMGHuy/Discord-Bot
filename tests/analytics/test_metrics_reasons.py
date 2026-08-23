"""Exit-reason vocabulary shared by journal and metrics."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import metrics


def test_win_and_loss_come_from_status():
    assert metrics.resolve_outcome({"status": "win"}) == "win"
    assert metrics.resolve_outcome({"status": "loss"}) == "loss"


def test_scratch_and_timeout_come_from_close_reason_under_generic_closed():
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "scratch"}) == "scratch"
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "Timeout"}) == "timeout"


def test_leg_reason_wins_over_close_reason():
    trade = {"status": "closed", "close_reason": "timeout",
             "legs": [{"reason": "scratch exit"}]}
    assert metrics.resolve_outcome(trade) == "scratch"


def test_unknown_reason_falls_back_to_status():
    assert metrics.resolve_outcome({"status": "closed", "close_reason": "???"}) == "closed"


def test_close_reason_text_prefers_last_leg():
    trade = {"close_reason": "stop", "legs": [{"reason": "runner_trail"}]}
    assert metrics.close_reason_text(trade) == "runner_trail"


def test_close_reason_text_is_lowercased_and_never_none():
    assert metrics.close_reason_text({"close_reason": None}) == ""
    assert metrics.close_reason_text({"close_reason": "STOP"}) == "stop"


def test_journal_still_resolves_identically():
    # The move must not change journal's behaviour.
    from swingbot.core.analytics import journal
    trade = {"status": "closed", "close_reason": "scratch"}
    assert journal._resolve_outcome(trade) == metrics.resolve_outcome(trade)


def test_exit_reasons_includes_other():
    assert "other" in metrics.EXIT_REASONS
