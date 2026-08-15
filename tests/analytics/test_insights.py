import datetime as dt

from swingbot.core.analytics.insights import weekly_digest

TODAY = dt.date(2026, 3, 8)  # a Sunday; window is 2026-03-02..2026-03-08


def _closed(status, r_amount, closed_at):
    return {"status": status, "closed_at": closed_at, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0,
            "realized_pnl_amount": r_amount}


def _entry(trade_id, r_realized, closed_at, tags, note="", auto_lesson="Outcome win at +1.00R."):
    return {"trade_id": trade_id, "ticker": trade_id.upper(), "r_realized": r_realized,
            "closed_at": closed_at, "tags": tags, "note": note, "auto_lesson": auto_lesson}


def test_weekly_digest_headline_and_worst_trade_lesson():
    closed = [
        _closed("win", 80.0, "2026-03-03T10:00:00+00:00"),
        _closed("win", 40.0, "2026-03-04T10:00:00+00:00"),
        _closed("win", 20.0, "2026-03-05T10:00:00+00:00"),
        _closed("loss", -40.0, "2026-03-06T10:00:00+00:00"),
    ]
    entries = [
        _entry("aaa", 0.8, "2026-03-03T10:00:00+00:00", ["fast_win"]),
        _entry("bbb", 0.4, "2026-03-04T10:00:00+00:00", ["fast_win"]),
        _entry("ccc", 0.2, "2026-03-05T10:00:00+00:00", []),
        _entry("ddd", -1.2, "2026-03-06T10:00:00+00:00", ["gap_fill"],
              note="Should have waited for confirmation.",
              auto_lesson="Entry was wrong from the first bar — review the trigger, not the exit."),
    ]
    messages = weekly_digest(entries, closed, TODAY)
    joined = "\n".join(messages)
    assert "WR 75" in joined
    assert "Entry was wrong from the first bar" in joined  # worst trade's lesson, verbatim
    assert all(len(m) <= 1900 for m in messages)


def test_weekly_digest_outside_window_excluded():
    closed = [_closed("win", 50.0, "2026-02-01T10:00:00+00:00")]  # 5 weeks before TODAY
    entries = [_entry("old", 1.0, "2026-02-01T10:00:00+00:00", [])]
    messages = weekly_digest(entries, closed, TODAY)
    assert "n=0" in "\n".join(messages).lower() or "0 trade" in "\n".join(messages).lower()


def test_weekly_digest_empty_week_still_returns_a_message():
    messages = weekly_digest([], [], TODAY)
    assert len(messages) >= 1


from unittest.mock import patch

from swingbot.core.analytics.insights import edge_decay_report, top_lessons


def _live_t(status):
    return {"target_sources": ["Fib 61.8%"], "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0}


def test_edge_decay_report_line_on_real_alert():
    registry = [{"source": "strategy", "strategy": "Fibonacci", "horizon": None,
                "status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.105,
                "window": "2024-01-01..2025-12-31"}]
    live = [_live_t("win") for _ in range(14)] + [_live_t("loss") for _ in range(11)]  # 56% of 25
    with patch("swingbot.core.registry.load_registry", return_value=registry):
        lines = edge_decay_report(live)
    assert len(lines) == 1
    assert "Fibonacci" in lines[0] and "81.6" in lines[0] and "56" in lines[0]


def test_edge_decay_report_empty_when_no_alerts():
    with patch("swingbot.core.registry.load_registry", return_value=[]):
        assert edge_decay_report([]) == []


def test_top_lessons_counts_pairings():
    entries = [
        {"auto_lesson": "Clean capture.", "tags": ["fast_win"]},
        {"auto_lesson": "Clean capture.", "tags": ["fast_win"]},
        {"auto_lesson": "Entry was wrong.", "tags": ["gap_fill"]},
    ]
    lines = top_lessons(entries, n=2)
    assert lines[0].startswith("2x")
    assert "Clean capture." in lines[0]


import datetime as _dt
from unittest.mock import patch as _patch

from swingbot.core.retrospective import build_daily_retrospective


def _closed_today(ticker, status, closed_at="2026-03-10T16:00:00+00:00"):
    return {"id": ticker.lower(), "ticker": ticker, "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0 if status == "win" else 96.0,
            "opened_at": "2026-03-09T10:00:00+00:00", "closed_at": closed_at,
            "confidence_level": 4, "horizon_key": "4w", "tier": "C", "target_sources": []}


def test_retrospective_includes_edge_decay_line_when_alert():
    registry = [{"source": "strategy", "strategy": "Fibonacci", "horizon": None,
                "status": "VALIDATED", "n": 206, "win_rate": 81.6, "expectancy_r": 0.105,
                "window": "2024-01-01..2025-12-31"}]
    heavy_losers = [dict(_closed_today("AAA", "loss"), target_sources=["Fib 61.8%"]) for _ in range(30)]
    with _patch("swingbot.core.registry.load_registry", return_value=registry):
        messages = build_daily_retrospective(heavy_losers, today=_dt.date(2026, 3, 10))
    joined = "\n".join(messages)
    assert "Edge decay" in joined or "📉" in joined


def test_retrospective_without_decay_omits_the_line():
    trades = [_closed_today("AAA", "win")]
    with _patch("swingbot.core.registry.load_registry", return_value=[]):
        messages = build_daily_retrospective(trades, today=_dt.date(2026, 3, 10))
    joined = "\n".join(messages)
    assert "Edge decay" not in joined


def test_retrospective_lessons_block_present_when_journaled(tmp_path, monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.config.DATA_DIR", str(tmp_path))
    from swingbot.core.analytics.journal import JournalStore

    JournalStore(path=str(tmp_path / "journal.json")).add({
        "trade_id": "aaa", "ticker": "AAA", "auto_lesson": "Clean capture: banked 100% of the available move.",
        "closed_at": "2026-03-10T16:00:00+00:00", "tags": [], "note": "",
    })
    trades = [_closed_today("AAA", "win")]
    with _patch("swingbot.core.registry.load_registry", return_value=[]):
        messages = build_daily_retrospective(trades, today=_dt.date(2026, 3, 10))
    assert any("Clean capture" in m for m in messages)
