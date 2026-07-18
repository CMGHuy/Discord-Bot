from swingbot.core.plan_engine import WEAK_CAUTION_TEXT, stamp_badge
from swingbot.core.scanning.embeds import (badge_field_for, entry_line,
                                           leg_rows, quality_lines)
from tests.test_plan_engine_model import _plan


def test_validated_badge_line_carries_registry_numbers():
    # Numbers from the exit-v2 validation single run (Task 32, 2026-07-18).
    p = _plan(strategy="Fibonacci")
    stamp_badge(p)
    name, value = badge_field_for(p)
    assert name.startswith("✅ VALIDATED")
    assert "N=203" in value and "82.3%" in value and "+0.268" in value


def test_weak_plan_renders_caution_text_verbatim():
    # EMA Crossover: still WEAK after the rescue round (RSI, the previous
    # exemplar here, was rescued to VALIDATED in Tasks 95-97).
    p = _plan(strategy="EMA Crossover")
    stamp_badge(p)
    name, value = badge_field_for(p)
    assert name.startswith("⚠️ WEAK")
    expected = WEAK_CAUTION_TEXT.format(win_rate=p.badge_stats["win_rate"],
                                        n=p.badge_stats["n"])
    assert expected in value


def test_no_plan_returns_none():
    assert badge_field_for(None) is None


def test_quality_lines_exact_rendering():
    p = _plan(quality_score=82, tier="A",
              quality_breakdown=[("regime", 15), ("htf", 8), ("confluence", 20),
                                 ("volume", 8), ("atr_percentile", 10),
                                 ("trigger_distance", 6), ("badge", 20)])
    header, detail = quality_lines(p)
    assert header == "Quality: 82/100 (Tier A)"
    assert detail == ("regime +15 · htf +8 · confluence +20 · volume +8 · "
                      "atr_percentile +10 · trigger_distance +6 · badge +20")


def test_quality_lines_empty_breakdown():
    assert quality_lines(_plan()) is None    # unscored plan -> no field


def test_entry_line_stop_entry_bullish():
    p = _plan(entry_type="stop_entry", direction="bullish",
              trigger_price=102.5, expiry_bars=5)
    assert entry_line(p) == "Entry: BUY STOP above 102.50 (expires in 5 bars)"


def test_entry_line_stop_entry_bearish():
    p = _plan(entry_type="stop_entry", direction="bearish",
              trigger_price=98.5, expiry_bars=3)
    assert entry_line(p) == "Entry: SELL STOP below 98.50 (expires in 3 bars)"


def test_entry_line_market():
    p = _plan(entry_type="market", trigger_price=101.2)
    assert entry_line(p) == "Entry: market ~101.20"


def test_leg_rows_show_both_legs(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    p = _plan(entry_type="market", trigger_price=100.0, entry_price=100.0,
              stop_loss=99.0, tp1=100.35, tp2=105.0)
    tp1_row, runner_row = leg_rows(p, currency="$")
    assert tp1_row == "50% @ 100.35 → +$17.50"
    assert runner_row == "50% → TP2 105.00 / trail"


def test_leg_rows_no_tp2(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: {"shares": 100.0,
                                             "position_value": 10_000.0,
                                             "mode": "risk_pct"})
    p = _plan(trigger_price=100.0, stop_loss=99.0, tp1=100.35, tp2=None)
    _, runner_row = leg_rows(p, currency="$")
    assert runner_row == "50% → trail"


def test_leg_rows_unsized(monkeypatch):
    import swingbot.core.scanning.embeds as embeds
    monkeypatch.setattr(embeds.account, "compute_position_size",
                        lambda entry, stop: None)
    tp1_row, _ = leg_rows(_plan(trigger_price=100.0, stop_loss=99.0,
                                tp1=100.35), currency="$")
    assert "@ 100.35" in tp1_row and "$" not in tp1_row   # price shown, no P&L
