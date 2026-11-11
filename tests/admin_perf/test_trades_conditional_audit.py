"""v218 V218-10: /trades audited for the conditional allow-list (v206 P3-c).

Admitted shape: status=closed or outcome=win|loss, no sort that prices rows,
the refresher on, and the ET date equal to the Berlin date. The record is
docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
`### Plan 3 route audits (V218-10..12)`; the allow-list and the ETag behaviour
are tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest
from werkzeug.datastructures import MultiDict

from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR
from tests.admin_perf import golden_book as gb

CLOSED = "/api/v1/trades?status=CLOSED"
UTC = dt.timezone.utc

TOP_LEVEL = {"items": "rows", "market_meta": "rows", "page": "query", "per_page": "query",
             "total": "query", "prices_as_of": "unpriced"}

_STORED = (
    "badge banked_contribution_r banked_exit_price banked_fraction banked_r bar_kind "
    "bars_to_expiry best_pnl_pct closed_at cohort_label cohort_stats confidence_level "
    "confidence_score created_at direction distance_to_trigger_r entry entry_shares exit_price "
    "floor_r headroom_r held_hours horizon id leg_exit_reason leg_index leg_total open_shares "
    "opened_at origin outcome pnl_pct position_value price_r quality_score r_multiple "
    "risk_reward risk_stop runner_best runner_exit_price runner_exit_reason shares status "
    "status_label stop_kind stop_loss stop_pnl_pct strategy target target1 target2 "
    "target_is_banked_tp1 ticker tier tp1 trigger_price").split()
_UNPRICED = ("current_price current_price_stale price_age_s price_as_of progress_pct entry_pct "
             "progress_band blink_seconds").split()
ROW_KEYS = {**{k: "stored" for k in _STORED}, **{k: "unpriced" for k in _UNPRICED},
            "today": "day", "has_note": "journal", "realized_pnl_amount": "fx-daily",
            "fx_missing": "fx-daily", "follow_score": "et-day"}


@pytest.fixture
def refresher_on(admin_app, monkeypatch):
    """The refresher on (closed-row FX from the stored daily rows only); no .env reload."""
    from swingbot import config
    monkeypatch.setattr(config, "auto_reload_if_changed", lambda *a, **k: {})
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


@pytest.fixture
def closed_page(golden_seed, frozen_clock, refresher_on, snapshot_on, logged_in):
    """The golden book behind an admitted /trades shape: snapshot vouched for, refresher on."""
    return logged_in


def _body(client, path=CLOSED):
    response = client.get(path)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


# --- the classification ----------------------------------------------------

def test_every_key_of_a_closed_page_is_classified(closed_page):
    body = _body(closed_page)
    assert set(body) == set(TOP_LEVEL)
    seen = set().union(*(set(row) for row in body["items"]))
    assert seen - set(ROW_KEYS) == set(), f"unclassified keys, re-audit: {seen - set(ROW_KEYS)}"
    assert set(ROW_KEYS) - seen == set(), f"keys gone from the page: {set(ROW_KEYS) - seen}"


def test_a_closed_page_holds_closed_rows_with_nothing_priced(closed_page):
    body = _body(closed_page)
    assert len(body["items"]) == 4
    assert body["prices_as_of"] is None
    assert body["market_meta"]["as_of"] is None and body["market_meta"]["refreshing"] is False
    for row in body["items"]:
        assert row["status"] == "CLOSED" and row["closed_at"], row["id"]
        for key in _UNPRICED:
            assert row[key] in (None, False), (row["id"], key, row[key])


@pytest.mark.parametrize("outcome", ["win", "loss", "WIN"])
def test_an_outcome_filter_returns_closed_rows_only(closed_page, outcome):
    rows = _body(closed_page, f"/api/v1/trades?outcome={outcome}")["items"]
    assert rows and all(row["status"] == "CLOSED" for row in rows)


def test_follow_score_moves_with_the_et_date():
    from swingbot.core.analytics.rank import follow_score
    plan = {"badge": "VALIDATED", "quality_score": 72, "created_at": "2026-11-03"}
    assert follow_score(plan, today=dt.date(2026, 11, 4)) != follow_score(plan, today=dt.date(2026, 11, 5))


# --- the admitted shape (V218-10b) ------------------------------------------

@pytest.mark.parametrize("pairs, admitted", [
    ([("status", "CLOSED")], True),
    ([("status", " closed ")], True),
    ([("outcome", "win")], True),
    ([("outcome", "LOSS")], True),
    ([("status", "closed"), ("sort", "-closed_at")], True),
    ([("status", "closed"), ("ticker", "aapl"), ("page", "2")], True),
    ([], False),
    ([("status", "open")], False),
    ([("status", "cancelled")], False),
    ([("outcome", "open")], False),
    ([("status", "closed"), ("sort", "-pnl_pct")], False),
    ([("status", "closed"), ("sort", "r_multiple")], False),
    ([("status", "closed"), ("sort", "status")], False),
])
def test_closed_only_query_admits_exactly_the_closed_shapes(admin_app, frozen_clock, refresher_on,
                                                            pairs, admitted):
    from swingbot.admin.api_v1 import trades
    assert trades.closed_only_query(MultiDict(pairs)) is admitted


def test_closed_only_query_needs_the_refresher(admin_app, frozen_clock):
    from swingbot.admin.api_v1 import trades
    assert trades.closed_only_query(MultiDict([("status", "closed")])) is False


@pytest.mark.parametrize("now, admitted", [
    (dt.datetime(2026, 11, 4, 4, 30, tzinfo=UTC), False),   # 05:30 Berlin 4 Nov, 23:30 ET 3 Nov
    (dt.datetime(2026, 11, 4, 5, 30, tzinfo=UTC), True),    # 06:30 Berlin 4 Nov, 00:30 ET 4 Nov
    (dt.datetime(2026, 11, 4, 22, 30, tzinfo=UTC), True),   # 23:30 Berlin 4 Nov, 17:30 ET 4 Nov
    (dt.datetime(2026, 11, 4, 23, 30, tzinfo=UTC), False),  # 00:30 Berlin 5 Nov, 18:30 ET 4 Nov
])
def test_closed_only_query_needs_the_et_and_berlin_dates_to_agree(admin_app, frozen_clock, refresher_on,
                                                                  monkeypatch, now, admitted):
    from swingbot.admin.api_v1 import trades
    monkeypatch.setattr(gb, "FROZEN_NOW", now)
    assert trades.closed_only_query(MultiDict([("status", "closed")])) is admitted


# --- the decorator on the real view ------------------------------------------

def test_list_trades_carries_the_trades_route_key_and_its_read_scope(admin_app):
    view = admin_app.view_functions["api_v1.list_trades"]
    assert getattr(view, cond.CONDITIONAL_ATTR) == "trades"
    assert getattr(view, READ_SCOPE_ATTR) is True


def test_a_304_skips_build_rows(closed_page, monkeypatch):
    from swingbot.admin.api_v1 import trades
    calls = []
    real = trades.build_rows

    def spying(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(trades, "build_rows", spying)
    first = closed_page.get(CLOSED)
    assert first.status_code == 200 and first.headers["ETag"].startswith('W/"')
    assert first.headers["Cache-Control"] == cond.CACHE_CONTROL
    second = closed_page.get(CLOSED, headers={"If-None-Match": first.headers["ETag"]})
    assert second.status_code == 304 and second.get_data() == b""
    assert calls == [1]                                     # the 304 built nothing


def test_the_unfiltered_list_keeps_no_store(closed_page):
    response = closed_page.get("/api/v1/trades")
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
