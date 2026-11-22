"""v238 additive gate disclosures (v230 spec Part C): reported, never gating."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting import acceptance_additive as aa
from swingbot.core.backtesting.acceptance import ArmTrade


def _row(ticker, r, *, day=0, strategy="Turtle Soup"):
    entry = date(2021, 1, 4) + timedelta(days=day)          # a Monday
    outcome = "win" if r > 0 else ("loss" if r < 0 else "scratch")
    return ArmTrade(ticker=ticker, strategy=strategy, horizon_key="4w",
                    entry_date=entry.isoformat(), outcome=outcome, r_multiple=r,
                    planned_rr=2.0, source="strategy", direction="bullish")


def _sequence():
    # in (date, ticker) order: +2 -1 -1 -1 +3 -1 -> equity 2 1 0 -1 2 1
    return [_row("T1", 2.0, day=0), _row("T2", -1.0, day=0), _row("T3", -1.0, day=1),
            _row("T4", -1.0, day=7), _row("T5", 3.0, day=7), _row("T6", -1.0, day=7)]


def test_disclosure_keys_are_pinned():
    assert set(aa.disclosures(_sequence(), [])) == {
        "max_drawdown_r", "longest_losing_streak", "top5_week_share",
        "signals_per_day_p95", "signals_per_day_max", "same_week_corr"}


def test_drawdown_streak_and_signals_per_day():
    d = aa.disclosures(list(reversed(_sequence())), [])   # input order does not matter
    assert d["max_drawdown_r"] == pytest.approx(3.0)
    assert d["longest_losing_streak"] == 3
    assert d["signals_per_day_max"] == 3                   # day 7
    assert d["signals_per_day_p95"] == pytest.approx(2.9)  # counts 2, 1, 3
    assert d["top5_week_share"] == pytest.approx(1.0)      # weeks sum 0 and +1


def test_unclosed_rows_count_as_signals_but_not_in_r():
    rows = _sequence() + [ArmTrade(ticker="T9", strategy="Turtle Soup", horizon_key="4w",
                                   entry_date="2021-01-11", outcome="not_triggered",
                                   r_multiple=None, planned_rr=2.0)]
    d = aa.disclosures(rows, [])
    assert d["signals_per_day_max"] == 4
    assert d["max_drawdown_r"] == pytest.approx(3.0)


def test_top5_week_share_can_exceed_one_and_is_undefined_without_profit():
    weekly = [5.0, 4.0, 3.0, 2.0, 1.0, -1.0, -4.0]
    rows = [_row(f"T{w}", r, day=7 * w) for w, r in enumerate(weekly)]
    assert aa.disclosures(rows, [])["top5_week_share"] == pytest.approx(15.0 / 10.0)
    losing = [_row(f"T{w}", -1.0, day=7 * w) for w in range(4)]
    assert aa.disclosures(losing, [])["top5_week_share"] is None


def test_same_week_correlation_uses_shared_weeks_only():
    added = [_row(f"T{w}", float(w + 1), day=7 * w) for w in range(5)]
    base = [_row(f"B{w}", 2.0 * (w + 1), day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures(added, base)["same_week_corr"] == pytest.approx(1.0)
    assert aa.disclosures(added, base[:2])["same_week_corr"] is None      # 2 shared weeks
    flat = [_row(f"B{w}", 1.0, day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures(added, flat)["same_week_corr"] is None          # constant


def test_empty_added_rows_disclose_zeros_and_none():
    base = [_row(f"B{w}", 1.0, day=7 * w, strategy="RSI") for w in range(4)]
    assert aa.disclosures([], base) == {
        "max_drawdown_r": 0.0, "longest_losing_streak": 0, "top5_week_share": None,
        "signals_per_day_p95": None, "signals_per_day_max": 0, "same_week_corr": None}


def test_render_disclosures_says_never_gating_and_prints_na():
    lines = aa.render_disclosures(aa.disclosures([], []))
    assert len(lines) == 6
    assert "never gating" in lines[0]
    assert all(line.startswith("- ") for line in lines[1:])
    assert "n/a" in lines[3] and "n/a" in lines[4] and "n/a" in lines[5]
    full = aa.render_disclosures(aa.disclosures(_sequence(), []))
    assert "3.00R" in full[1]
    assert "100.0%" in full[3]
    assert "p95 2.9, max 3" in full[4]
