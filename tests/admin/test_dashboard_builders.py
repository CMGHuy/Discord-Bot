"""swingbot/admin/dashboard.py -- the Dashboard's view-model builders.

NG19 TRIAGE — **builder-level · KEEP UNCHANGED.** Spec v15 Decision 4 names
this file explicitly. These target dashboard.py, which /api/v1/cockpit and
/api/v1/trades project from rather than replace; they were extracted out of
the templates precisely so they would survive this migration. Nothing here
touches a template or a route.


These are plain functions of their arguments (the dashboard mode arrives as a
parameter, not off `flask.request`), so most of this file needs no client and
no request context at all.
"""
import json
import os

import pytest

from swingbot.admin import dashboard as dash


# ---------------------------------------------------------------------------
# Mode handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("active", "active"), ("today", "today"), ("all", "all"),
    ("", "active"), (None, "active"), ("garbage", "active"), ("ALL", "active"),
])
def test_normalize_mode_clamps_to_a_known_mode(value, expected):
    assert dash.normalize_mode(value) == expected


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("seconds,label", [
    (0, "0m"),
    (59, "0m"),
    (12 * 60, "12m"),
    (4 * 3600 + 20 * 60, "4h 20m"),
    (86400 + 5 * 3600 + 32 * 60, "1d 5h 32m"),
    (-500, "0m"),                       # negatives clamp rather than go weird
])
def test_format_duration_hms(seconds, label):
    assert dash.format_duration_hms(seconds) == label


def test_format_duration_keeps_hours_and_minutes_past_a_day():
    """Whole-days-only granularity reported 10 minutes and 23 hours both as
    '0', which is the reason this helper exists."""
    assert dash.format_duration_hms(86400 + 60) == "1d 0h 1m"


# ---------------------------------------------------------------------------
# Position sizing note
# ---------------------------------------------------------------------------
def test_sizing_note_account_pct_mode_is_a_single_fixed_premium():
    note = dash.build_sizing_note({
        "sizing_mode": "account_pct", "balance": 10000,
        "position_pct": 5, "max_position_pct": 20,
    })
    assert note["mode"] == "account_pct"
    assert note["premium"] == 500.0


def test_sizing_note_applies_the_absolute_position_cap():
    """The %-based cap alone let this card advertise an 'up to' figure no real
    trade could reach, because compute_position_size() also honours the
    absolute caps."""
    note = dash.build_sizing_note({
        "sizing_mode": "risk_pct", "balance": 100000,
        "risk_pct": 1, "max_position_pct": 50,
        "max_position_value_absolute": 1000,
    })
    assert note["max_position"] == 1000.0        # not 50000 (50% of balance)


def test_sizing_note_applies_the_absolute_risk_cap():
    note = dash.build_sizing_note({
        "sizing_mode": "risk_pct", "balance": 100000,
        "risk_pct": 5, "max_position_pct": 50,
        "max_risk_amount_absolute": 250,
    })
    assert note["risk_amount"] == 250.0          # not 5000 (5% of balance)


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------
def _closed(tid, closed_at, status="win"):
    return {"id": tid, "status": status, "ticker": "AAA", "closed_at": closed_at,
            "opened_at": closed_at, "direction": "bullish"}


def test_scoped_closed_trades_excludes_open_positions():
    rows = dash.scoped_closed_trades(
        [_closed("a", "2026-01-01T00:00:00+00:00"),
         {"id": "b", "status": "open", "ticker": "AAA"}], "all")
    assert [r["id"] for r in rows] == ["a"]


def test_scoped_trades_returns_none_for_all_mode():
    """None is the signal TradeLog.get_stats() reads as 'use every trade', so
    'all' mode never materialises a redundant copy of the list."""
    assert dash.scoped_trades([_closed("a", "2026-01-01T00:00:00+00:00")], "all") is None


# ---------------------------------------------------------------------------
# Realized stat cards -- the scoping defect this refactor fixed
# ---------------------------------------------------------------------------
def _seed_history_with_extremes_off_the_first_page(data_dir):
    """30 closed trades. Every one is +10% EXCEPT the two oldest, which are
    +100% and -50%.

    Trade History sorts newest-close-first and shows 25 per page, so those two
    extremes land on page 2 -- outside the slice the stat cards used to be
    computed from.
    """
    trades = []
    for i in range(30):
        exit_price = 110.0
        if i == 0:
            exit_price = 200.0      # +100%, the real best
        elif i == 1:
            exit_price = 50.0       # -50%, the real worst
        trades.append({
            "id": f"t{i}", "ticker": "AAA", "status": "win", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
            "exit_price": exit_price,
            "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": f"2026-02-{i + 1:02d}T00:00:00+00:00",
            "confidence_level": 3, "confidence_score": 60,
            "strategy": "RSI", "horizon_key": "4w",
        })
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def _stat_card_value(html, label):
    """The stat-value text of the card carrying `label`."""
    after_label = html.split(">%s<" % label, 1)[1]
    value_block = after_label.split('class="stat-value"', 1)[1]
    return value_block.split(">", 1)[1].split("<", 1)[0].strip()


def test_best_and_worst_trade_see_the_whole_scoped_history(client, auth, admin_app):
    """These cards were computed from Trade History's FIRST PAGE, which quietly
    made 'Best trade' mean 'best of the 25 most recently closed'. Seeding the
    real extremes onto page 2 pins the fix."""
    from swingbot import config
    _seed_history_with_extremes_off_the_first_page(config.DATA_DIR)
    html = client.get("/jinja/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")

    assert _stat_card_value(html, "Best trade") == "+100.0%"
    assert _stat_card_value(html, "Worst trade") == "-50.0%"


def test_avg_realized_pnl_counts_every_closed_trade_in_scope(client, auth, admin_app):
    """28 trades at +10%, one at +100%, one at -50% -> (280+100-50)/30 = 11.0%.

    Page 1 holds the 25 newest, every one of them +10%, so the old first-page
    average was exactly 10.0% -- the two figures differ, which is what makes
    this a real check rather than a coincidence.
    """
    from swingbot import config
    _seed_history_with_extremes_off_the_first_page(config.DATA_DIR)
    html = client.get("/jinja/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")

    assert "over 30 closed" in html
    assert _stat_card_value(html, "Avg realized P&amp;L") == "+11.0%"


def test_equity_card_shows_period_change_not_the_balance_again(client, auth, admin_app, monkeypatch):
    """The Equity (30d) card used to repeat the account balance -- the exact
    number already headlining the card beside it."""
    curve = {"points": [{"date": f"2026-06-{i + 1:02d}", "balance": 10000 + i * 100, "pnl": 1.0}
                        for i in range(30)], "skipped_n": 0}
    monkeypatch.setattr("swingbot.admin.dashboard.load_snapshot",
                        lambda max_age_seconds=3600: {"built_at": "x", "equity_curve": curve})
    monkeypatch.setattr("swingbot.admin.pages.rank_plans", lambda plans: [])

    html = client.get("/jinja/dashboard/fragment", headers=auth).data.decode("utf-8")
    # 10000 -> 12900 across the window
    assert _stat_card_value(html, "Equity (30d)") == "+29.00%"
