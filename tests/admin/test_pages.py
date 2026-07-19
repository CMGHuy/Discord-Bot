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
