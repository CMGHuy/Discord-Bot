"""The two attribution sections of the weekly digest.

insights.py formats, it never computes: every assertion here is about wording,
completeness and Discord's cap, and the arithmetic is checked in
test_metrics_exit_reasons.py / test_metrics_hold_by_outcome.py.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.analytics import insights, metrics

TODAY = dt.date(2026, 1, 10)


def _t(reason, r, opened="2026-01-01", closed="2026-01-05", status="closed"):
    """A closed trade inside the digest's trailing-7-day window.

    entry 100 / stop 99 -> risk 1.0, so exit = 100 + r gives exactly r R.
    """
    return {"status": status, "close_reason": reason,
            "entry": 100.0, "stop_loss": 99.0, "direction": "bullish",
            "exit_price": 100.0 + r,
            "opened_at": f"{opened}T00:00:00", "closed_at": f"{closed}T00:00:00",
            "ticker": "AAPL", "realized_pnl_amount": r * 10.0}


def _winners(k):
    return [_t("tp1", 1.0, status="win") for _ in range(k)]


def _losers(k):
    return [_t("stop", -1.0, closed="2026-01-09", status="loss") for _ in range(k)]


def _digest(closed):
    return "\n".join(insights.weekly_digest([], closed, TODAY))


def test_every_exit_reason_gets_a_row_including_the_empty_ones():
    text = _digest(_winners(5) + _losers(5))
    for reason in metrics.EXIT_REASONS:
        assert reason in text, f"{reason} row missing from the digest"
    # A reason that never fired is a finding, not a row to drop.
    assert "reversed" in text


def test_r_attribution_reports_total_and_average_together():
    text = _digest(_winners(5) + _losers(5))
    assert "+5.00R" in text   # tp1 total
    assert "-5.00R" in text   # stop total
    assert "n=5" in text


def test_hold_ratio_line_states_measurement_and_severity():
    text = _digest(_winners(5) + _losers(5))
    assert "2.00x" in text
    assert "high" in text


def test_undefined_ratio_renders_na_not_zero():
    text = _digest(_winners(2) + _losers(2))
    assert "n/a" in text
    assert "0.00x" not in text
    assert "0.0x" not in text


def test_digest_with_no_computable_hold_times_does_not_crash():
    bare = [{"status": "win", "close_reason": "tp1", "closed_at": "2026-01-05T00:00:00",
             "ticker": "AAPL", "entry": 100.0, "stop_loss": 99.0,
             "direction": "bullish", "exit_price": 101.0}]
    text = _digest(bare)
    assert "n/a" in text


def test_every_chunk_stays_under_the_discord_limit():
    chunks = insights.weekly_digest([], _winners(40) + _losers(40), TODAY)
    assert chunks
    for chunk in chunks:
        assert len(chunk) <= insights.DISCORD_MESSAGE_LIMIT
