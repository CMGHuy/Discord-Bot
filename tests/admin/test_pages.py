"""Route-level smoke tests for the admin Flask app. Every test in this file
(and every other tests/admin/*.py file in this plan) uses the `client`/`auth`
fixtures from conftest.py rather than talking to a real running server."""


def test_index_requires_auth(client):
    assert client.get("/").status_code == 401


def test_index_renders(client, auth):
    r = client.get("/", headers=auth)
    assert r.status_code == 200 and b"Dashboard" in r.data


import pytest

NEW_PATHS = ["/plans", "/strategies", "/calibration", "/journal", "/tuning"]


@pytest.mark.parametrize("path", NEW_PATHS)
def test_new_pages_200_authed(client, auth, path):
    r = client.get(path, headers=auth)
    assert r.status_code == 200


@pytest.mark.parametrize("path", NEW_PATHS)
def test_new_pages_401_unauthed(client, path):
    assert client.get(path).status_code == 401


def test_new_nav_items_in_sidebar(client, auth):
    r = client.get("/", headers=auth)
    html = r.data.decode("utf-8")
    for label in ("Plans", "Strategies", "Calibration", "Journal", "Tuning"):
        assert label in html


import dataclasses

from swingbot.core.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.plan_store import PlanStore


def _plan(plan_id, ticker, tier="A", badge="VALIDATED", status=PlanStatus.PENDING):
    return TradePlanV2(
        plan_id=plan_id, ticker=ticker, created_at="2026-07-01", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish", entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
        tp1=104.0, tp1_fraction=0.5, tp2=110.0, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.5, quality_score=70, quality_breakdown=[], tier=tier,
        badge=badge, badge_stats={}, status=status, status_history=[],
    )


def _fake_ranked_plan_rows_by_ticker(plans):
    rows = [dataclasses.asdict(p) for p in plans]
    for r in rows:
        r["follow_score"] = 100.0
    return sorted(rows, key=lambda r: r["ticker"])


def test_plans_page_renders_ranked_rows_with_chips(client, auth, monkeypatch):
    # Real PlanStore.update() raises KeyError for an unseen plan_id --
    # .add() is the real insert call (see the C7 commit's deviation note).
    PlanStore().add(_plan("p1", "MSFT", tier="A", badge="VALIDATED"))
    PlanStore().add(_plan("p2", "AAPL", tier="B", badge="WEAK"))
    monkeypatch.setattr("swingbot.admin.pages._ranked_plan_rows", _fake_ranked_plan_rows_by_ticker)

    r = client.get("/plans", headers=auth)
    html = r.data.decode("utf-8")
    assert "chip-tier-a" in html
    assert "chip-validated" in html
    assert html.index("AAPL") < html.index("MSFT")  # ranked order = alphabetical per the fake


import re
from datetime import datetime, timedelta, timezone


def _lifecycle_card_count(html, status):
    """Extract the lc-count integer for a specific lifecycle-strip card by
    anchoring on that status's href and taking the very next lc-count span
    (the template emits href then lc-count within the same <a> element, in
    a fixed status order) -- avoids a page-wide substring match that could
    coincidentally match any digit anywhere on the page."""
    match = re.search(
        r'href="[^"]*status=' + status + r'[^"]*".*?<span class="lc-count">(\d+)</span>',
        html, re.S,
    )
    assert match, f"no lifecycle card found for status={status}"
    return int(match.group(1))


def test_lifecycle_strip_counts_and_click_filters(client, auth, monkeypatch):
    # No rank_plans/_ranked_plan_rows mock here (unlike
    # test_plans_page_renders_ranked_rows_with_chips above): rank_plans is a
    # pure function with no network/IO dependency (see
    # swingbot/core/analytics/rank.py) and works fine on real TradePlanV2
    # instances -- mocking it to return dicts is actually incompatible with
    # _ranked_plan_rows, which calls plan_to_dict()/follow_score() on
    # rank_plans()'s output expecting TradePlanV2 objects, not dicts.
    # .add() not .update(): PlanStore().update() raises KeyError for an
    # unseen plan_id -- .add() is the real insert call (see the C7 commit's
    # deviation note, and test_plans_page_renders_ranked_rows_with_chips
    # above).
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.PENDING))
    PlanStore().add(_plan("p2", "MSFT", status=PlanStatus.ACTIVE))
    today_closed = _plan("p3", "TSLA", status=PlanStatus.CLOSED)
    today_closed.status_history = [{"status": "CLOSED", "reason": "manual",
                                    "at": datetime.now(timezone.utc).isoformat()}]
    PlanStore().add(today_closed)
    # A second CLOSED plan, but closed several days ago -- proves the
    # _is_today_berlin scoping in _plan_rows (pages.py) actually excludes
    # stale closes rather than passing vacuously (the count would be 2, not
    # 1, if the "today" filter weren't applied).
    old_closed = _plan("p4", "NVDA", status=PlanStatus.CLOSED)
    old_closed.status_history = [{"status": "CLOSED", "reason": "manual",
                                  "at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}]
    PlanStore().add(old_closed)

    r = client.get("/plans", headers=auth)
    html = r.data.decode("utf-8")
    assert 'href="/plans?status=PENDING' in html
    assert _lifecycle_card_count(html, "PENDING") == 1
    # The plan-mandated assertion: CLOSED-today count is 1 (today_closed),
    # and the prior-day close (old_closed) is excluded, not 2.
    assert _lifecycle_card_count(html, "CLOSED") == 1

    r2 = client.get("/plans?status=PENDING", headers=auth)
    html2 = r2.data.decode("utf-8")
    assert "AAPL" in html2 and "MSFT" not in html2


def test_board_filters_by_tier_and_badge(client, auth):
    # No rank_plans monkeypatch (see the note on test_lifecycle_strip_counts_
    # and_click_filters above): rank_plans is pure and works fine on real
    # TradePlanV2 instances -- mocking it to return dicts breaks
    # _ranked_plan_rows's plan_to_dict()/follow_score() calls, which expect
    # TradePlanV2 objects. .add(), not .update(): PlanStore().update() raises
    # KeyError for an unseen plan_id.
    PlanStore().add(_plan("p1", "AAPL", tier="A", badge="VALIDATED"))
    PlanStore().add(_plan("p2", "MSFT", tier="B", badge="WEAK"))
    r = client.get("/plans?tier=A&badge=VALIDATED", headers=auth)
    html = r.data.decode("utf-8")
    assert "AAPL" in html and "MSFT" not in html


def test_board_filters_by_ticker_substring(client, auth):
    PlanStore().add(_plan("p1", "AAPL"))
    PlanStore().add(_plan("p2", "MSFT"))
    r = client.get("/plans?ticker=aap", headers=auth)
    html = r.data.decode("utf-8")
    assert "AAPL" in html and "MSFT" not in html


def test_ticker_filter_preserved_on_lifecycle_strip_links(client, auth):
    # Regression test for a C16 review finding: the lifecycle-strip status
    # cards (added in C15) build their href from status/tier/badge only,
    # dropping the ticker filter -- so clicking a status card while a ticker
    # filter is active silently clears it. Every lifecycle card's href must
    # carry ticker=aap through unchanged.
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.PENDING))
    PlanStore().add(_plan("p2", "MSFT", status=PlanStatus.ACTIVE))
    r = client.get("/plans?ticker=aap", headers=auth)
    html = r.data.decode("utf-8")
    for status in ("PENDING", "ACTIVE", "PARTIAL", "CLOSED", "CANCELLED"):
        match = re.search(r'href="([^"]*status=' + status + r'[^"]*)"', html)
        assert match, f"no lifecycle card href found for status={status}"
        assert "ticker=aap" in match.group(1), (
            f"status={status} lifecycle card lost the ticker filter: {match.group(1)}"
        )


import os


def test_cancel_pending_plan_transitions_and_notifies(client, auth):
    # .add(), not .update(): PlanStore().update() raises KeyError for an
    # unseen plan_id -- .add() is the real insert call (see the C7 commit's
    # deviation note, and the other tests above in this file).
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.PENDING))
    r = client.post("/plans/p1/cancel", headers=auth)
    assert r.status_code == 302
    assert PlanStore().get("p1").status == PlanStatus.CANCELLED
    from swingbot.admin.app import MANUAL_CLOSE_QUEUE
    assert os.path.exists(MANUAL_CLOSE_QUEUE)


def test_cancel_active_plan_rejected(client, auth):
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.ACTIVE))
    r = client.post("/plans/p1/cancel", headers=auth)
    assert r.status_code == 400
    assert PlanStore().get("p1").status == PlanStatus.ACTIVE  # unchanged


def test_close_active_plan_transitions(client, auth):
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.ACTIVE))
    r = client.post("/plans/p1/close", headers=auth)
    assert r.status_code == 302
    assert PlanStore().get("p1").status == PlanStatus.CLOSED


def test_close_pending_plan_rejected(client, auth):
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.PENDING))
    r = client.post("/plans/p1/close", headers=auth)
    assert r.status_code == 400
