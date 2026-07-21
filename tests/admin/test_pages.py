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


def test_plans_fragment_etag_304(client, auth):
    r1 = client.get("/plans/fragment", headers=auth)
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag
    r2 = client.get("/plans/fragment", headers={**auth, "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.data == b""


def test_plans_fragment_respects_filters(client, auth):
    # No rank_plans monkeypatch (see the note on test_lifecycle_strip_counts_
    # and_click_filters above): mocking rank_plans to return dicts breaks
    # _ranked_plan_rows, which calls plan_to_dict()/follow_score() on
    # rank_plans()'s output expecting TradePlanV2 objects, not dicts.
    # .add(), not .update(): PlanStore().update() raises KeyError for an
    # unseen plan_id -- .add() is the real insert call.
    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.PENDING))
    PlanStore().add(_plan("p2", "MSFT", status=PlanStatus.ACTIVE))
    r = client.get("/plans/fragment?status=PENDING", headers=auth)
    html = r.data.decode("utf-8")
    assert "AAPL" in html and "MSFT" not in html


def test_plans_page_morphdom_guards_input_and_select(client, auth):
    # Regression test for the C18 review finding: without an onBeforeElUpdated
    # guard, morphdom force-syncs the live .value/.selected DOM property on
    # every INPUT/SELECT during each auto-refresh patch, silently wiping an
    # in-progress filter-form edit (ticker text box, status/tier/badge
    # dropdowns) on the next poll. Asserts the guard actually shipped in the
    # served page, not just in a local edit.
    r = client.get("/plans", headers=auth)
    html = r.data.decode("utf-8")
    assert "onBeforeElUpdated" in html
    assert "from.nodeName === 'INPUT'" in html
    assert "from.nodeName === 'SELECT'" in html


def test_close_active_plan_also_closes_linked_trade(client, auth):
    # Covers the gap flagged by the C17 review: plan_close()'s linked-trade
    # branch (tl = TradeLog(); linked = next(... t.get("plan_id") ==
    # plan_id ...); if linked and linked["status"] == "open":
    # tl.close_trade_manual(...)) had zero test coverage -- every existing
    # close test only exercised the no-linked-trade no-op path. This proves
    # the OPEN trade whose plan_id matches the closed plan is actually
    # closed via TradeLog.close_trade_manual, not just that the plan's own
    # status flips.
    from swingbot.core.performance import TradeLog

    PlanStore().add(_plan("p1", "AAPL", status=PlanStatus.ACTIVE))
    trade_id = TradeLog().log_trade(
        ticker="AAPL", strategy="RSI", horizon_key="4w", direction="bullish",
        confidence_level=4, confidence_label="Strong", entry=100.0, stop_loss=95.0,
        take_profit=110.0, plan_id="p1",
    )

    r = client.post("/plans/p1/close", headers=auth)
    assert r.status_code == 302
    assert PlanStore().get("p1").status == PlanStatus.CLOSED

    closed_trade = TradeLog().get_trade_by_id(trade_id)
    assert closed_trade["status"] == "closed"


def test_plan_detail_page_renders_timeline_and_breakdown(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.generate_trade_chart", lambda *a, **k: "/tmp/does-not-matter.png")
    monkeypatch.setattr("swingbot.admin.pages.get_daily_data", lambda ticker: object())
    plan = _plan("p1", "AAPL", status=PlanStatus.ACTIVE)
    # quality_breakdown rows are (label, points) tuples, not dicts -- see
    # plan_engine.py's plan_to_dict, which round-trips each row via
    # list(row), proving they're sequences. .add(), not .update(): PlanStore
    # .update() raises KeyError for an unseen plan_id (see the C7 commit's
    # deviation note referenced throughout this file).
    plan.quality_breakdown = [("Confluence x3", 30)]
    plan.status_history = [{"status": "ACTIVE", "reason": "market_entry", "at": "2026-07-01T14:00:00+00:00"}]
    plan.badge_stats = {"status": "VALIDATED", "n": 608, "win_rate": 85.2, "expectancy_r": 0.14, "window": "2024-01-01..2025-12-31"}
    PlanStore().add(plan)

    r = client.get("/plans/p1", headers=auth)
    html = r.data.decode("utf-8")
    assert r.status_code == 200
    assert "Confluence x3" in html
    assert "ACTIVE" in html
    assert "85.2" in html
    # Proves swingbot.core.analytics.rank.follow_breakdown actually imported
    # and ran (not silently swallowed by the route's `except (ImportError,
    # AttributeError)`) and that the template's tuple-unpack loop rendered
    # real content. _plan()'s defaults (badge="VALIDATED", quality_score=70)
    # deterministically produce these two lines per rank.py:76-111 --
    # BADGE_WEIGHT contributes "✅ validated source" whenever badge ==
    # "VALIDATED", and QUALITY_WEIGHT (0.4) * 70 == 28 contributes
    # "quality 70 → +28". The regression this guards against: the brief's
    # original (wrong) import path `swingbot.analytics.rank` always raises
    # ImportError, follow_breakdown silently becomes None, and the template's
    # `{% if follow_breakdown %}` block simply never renders -- a bug the
    # prior version of this test would not have caught.
    assert "validated source" in html
    assert "quality 70" in html


def test_plan_detail_page_404_for_unknown_id(client, auth):
    r = client.get("/plans/does-not-exist", headers=auth)
    assert r.status_code == 404


def test_plan_chart_image_200_on_success(client, auth, tmp_path, monkeypatch):
    # Real-file pattern matched to test_views.py's /trades/<id>/chart.png
    # tests (test_closed_trade_chart_is_cacheable et al.): write an actual
    # tiny PNG to disk and point generate_trade_chart at it, so send_file
    # operates on a real path rather than needing its own mock.
    png_path = tmp_path / "AAPL_p1_plan.png"
    png_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
            "de0000000c4944415478da6360606060000000050001d78f7e6e0000000049454e44ae426082"
        )
    )
    monkeypatch.setattr("swingbot.admin.pages.generate_trade_chart", lambda *a, **k: str(png_path))
    monkeypatch.setattr("swingbot.admin.pages.get_daily_data", lambda ticker: object())
    PlanStore().add(_plan("p1", "AAPL"))

    r = client.get("/plans/p1/chart.png", headers=auth)
    assert r.status_code == 200


def test_plan_chart_image_404_when_data_fetch_fails(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.get_daily_data", lambda ticker: None)
    PlanStore().add(_plan("p1", "AAPL"))

    r = client.get("/plans/p1/chart.png", headers=auth)
    assert r.status_code == 404


_FAKE_SNAPSHOT_EMPTY = {"built_at": "x", "by": {"strategy": {}}, "calibration": {}}


def test_strategies_page_shows_registry_rows(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    # 11 registry rows (swingbot.core.backtest.ALL_STRATEGIES) -> 11 badge chips
    assert html.count("chip-validated") + html.count("chip-weak") == 11
    assert "82.3" in html          # Fibonacci's committed OOS win_rate (validation_registry.json, pooled/horizon=None record)
    assert "bullish only" in html  # Fibonacci's real current STRATEGY_GATES entry


import json
import os


def test_strategy_heatmap_colors_and_na_cells(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    monkeypatch.setattr("swingbot.admin.pages.primary_strategy_label", lambda t: t["strategy"])
    from swingbot import config
    trades = [{
        "id": f"w{i}", "ticker": "AAA", "status": "win", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
        "opened_at": "2026-01-01T00:00:00+00:00", "closed_at": "2026-01-02T00:00:00+00:00",
        "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
    } for i in range(6)]  # 6 RSI/4w wins -> WR 100%, n=6
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    assert "hm-na" in html          # e.g. RSI/2w has n=0 < 5 -- greyed n/a
    assert "100% (6)" in html


_FAKE_SNAPSHOT_WITH_DRIFT = {
    "built_at": "x",
    "by": {"strategy": [{"key": "RSI", "n": 40, "win_rate": 68.0}]},
    "calibration": {"drift": [{"strategy": "RSI", "oos_n": 608, "oos_wr": 68.4,
                                "live_n": 40, "live_wr": 68.0, "delta_wr": -0.4,
                                "drift_alert": True}]},
}


def test_drift_chip_and_banner_present_when_flagged(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_WITH_DRIFT)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    assert "chip-decay" in html
    assert "DECAY" in html
    assert "Edge decay flagged" in html


def test_no_drift_chip_or_banner_when_clean(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    assert "chip-decay" not in html
    assert "Edge decay flagged" not in html


def test_strategy_heatmap_all_closed_bucket_renders_na_not_500(client, auth, monkeypatch):
    # 6 manually-"closed" trades (not "win"/"loss") sharing MACD/8m: n=6 (>=5)
    # but metrics.win_rate() returns None since there are zero win/loss
    # trades in the bucket -- must render as n/a, not crash _heatmap_color.
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    monkeypatch.setattr("swingbot.admin.pages.primary_strategy_label", lambda t: t["strategy"])
    from swingbot import config
    trades = [{
        "id": f"c{i}", "ticker": "AAA", "status": "closed", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 102.0,
        "opened_at": "2026-01-01T00:00:00+00:00", "closed_at": "2026-01-02T00:00:00+00:00",
        "confidence_level": 3, "confidence_score": 60, "strategy": "MACD", "horizon_key": "8m",
    } for i in range(6)]
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    r = client.get("/strategies", headers=auth)
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert 'title="MACD / 8m: n=6 (too few trades)"' in html
    assert "hm-na" in html


def test_sparkline_svg_point_count_and_color():
    from swingbot.admin.pages import _sparkline_svg
    svg = _sparkline_svg([50.0, 60.0, 70.0, 80.0], width=100, height=20)
    assert svg.startswith("<svg")

    # Pull the actual rendered polyline out of the SVG (not just check
    # "polyline" appears somewhere -- the ref line at y=80 is also a
    # polyline, so match on the spark-line class specifically).
    m = re.search(r'class="spark-line" stroke="(#[0-9a-f]{6})" points="([^"]+)"', svg)
    assert m is not None, svg
    color, points_attr = m.group(1), m.group(2)

    # last point is 80.0 -- lands in _sparkline_svg's own ">= 80 -> green"
    # bracket (the other two brackets are >=60 amber, else red), chosen
    # deterministically so this assertion pins one specific hex value.
    assert color == "#6dda9e"

    coords = points_attr.split(" ")
    assert len(coords) == 4  # one "x,y" pair per input point, same order

    # Hand-derived from _sparkline_svg's own mapping (n=4, width=100,
    # height=20): x = i/(n-1)*width, y = height - v/100*height.
    #   i=0 v=50.0 -> x=0/3*100=0.0,   y=20-50/100*20=10.0
    #   i=1 v=60.0 -> x=1/3*100=33.3,  y=20-60/100*20=8.0
    #   i=2 v=70.0 -> x=2/3*100=66.7,  y=20-70/100*20=6.0
    #   i=3 v=80.0 -> x=3/3*100=100.0, y=20-80/100*20=4.0
    assert coords == ["0.0,10.0", "33.3,8.0", "66.7,6.0", "100.0,4.0"]


def test_sparkline_svg_empty_data_is_emdash():
    from swingbot.admin.pages import _sparkline_svg
    assert _sparkline_svg([]) == "&mdash;"


def test_rolling_win_rate_series_window_rolls_and_excludes_scratch():
    from swingbot.admin.pages import _rolling_win_rate_series

    def t(day, status):
        return {"status": status, "closed_at": f"2026-01-{day:02d}T00:00:00+00:00"}

    # Chronological order (by closed_at, day 1..14) is:
    #   win win loss closed(scratch) win loss win win closed(scratch)
    #   loss win win loss win
    # Built out of chronological order below to prove the function sorts
    # by closed_at itself rather than trusting input order.
    trades = [
        t(14, "win"), t(1, "win"), t(9, "closed"), t(2, "win"), t(3, "loss"),
        t(13, "loss"), t(4, "closed"), t(5, "win"), t(12, "win"), t(6, "loss"),
        t(11, "win"), t(7, "win"), t(10, "loss"), t(8, "win"),
    ]
    series = _rolling_win_rate_series(trades, window=10)

    # The two "closed" (scratch) trades (day 4, day 9) are dropped
    # entirely -- 14 input trades but only 12 win/loss outcomes feed the
    # series, proving scratches are excluded from both numerator and
    # denominator rather than diluting the window or counting as losses.
    assert len(series) == 12

    # Win/loss-only outcomes in closed_at order (day 1,2,3,5,6,7,8,10,11,
    # 12,13,14): win win loss win loss win win loss win win loss win
    # -> as 1/0:      1   1   0   1   0   1   1   0   1   1   0    1
    assert series[0] == 100.0                    # [1] -> 1/1
    assert series[1] == 100.0                    # [1,1] -> 2/2
    assert series[2] == pytest.approx(200 / 3)    # [1,1,0] -> 2/3
    # 10th outcome (day 12): window is exactly the first 10 outcomes
    # (day1..day8,day10,day11) = 7 wins / 10 -> 70.0
    assert series[9] == 70.0
    # 11th outcome (day 13, a loss): window=10 rolls forward, dropping
    # the oldest outcome (day1, a win) and adding day13 (a loss) ->
    # 6/10 = 60.0. This differs from both series[9] (70.0) and the
    # all-12 global average (8/12 = 66.67), which is only possible if
    # the computation is a genuine trailing window, not a running/global
    # average.
    assert series[10] == 60.0
    # 12th outcome (day 14, a win): window drops day2 (win) and adds
    # day14 (win) -- net unchanged from the previous window's ratio.
    assert series[11] == 60.0


def test_strategies_page_embeds_sparkline_for_strategy_with_data(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    monkeypatch.setattr("swingbot.admin.pages.primary_strategy_label", lambda t: t["strategy"])
    from swingbot import config

    def rsi_trade(id_, day, status, exit_price):
        return {
            "id": id_, "ticker": "AAA", "status": status, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": exit_price,
            "opened_at": "2026-01-01T00:00:00+00:00", "closed_at": f"2026-01-{day:02d}T00:00:00+00:00",
            "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        }

    # Mixed win/loss/scratch by closed_at day, not all-wins: win, loss,
    # closed(scratch, day 3, must be excluded), win, win.
    trades = [
        rsi_trade("w0", 1, "win", 110.0),
        rsi_trade("l1", 2, "loss", 95.0),
        rsi_trade("c2", 3, "closed", 100.0),
        rsi_trade("w3", 4, "win", 110.0),
        rsi_trade("w4", 5, "win", 110.0),
    ]
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    assert 'class="sparkline"' in html

    m = re.search(r'class="spark-line" stroke="(#[0-9a-f]{6})" points="([^"]+)"', html)
    assert m is not None, html
    color, points_attr = m.group(1), m.group(2)
    coords = points_attr.split(" ")

    # The scratch trade (day 3, "closed") must be excluded: only 4
    # win/loss trades feed _rolling_win_rate_series, giving 4 rolling
    # points, not 5 -- proving the route actually threads real trade
    # data through the win/loss-only filter end to end, not just
    # counting rows.
    assert len(coords) == 4

    # Rolling win-rate (window=10, so no truncation) over win, loss, win,
    # win: [1/1, 1/2, 2/3, 3/4] * 100 = [100.0, 50.0, 66.667, 75.0].
    # _sparkline_svg maps these onto default width=120, height=28:
    #   x_i = i/3*120 -> 0.0, 40.0, 80.0, 120.0
    #   y_i = 28 - v/100*28:
    #     v=100.0    -> 28-28.0     = 0.0
    #     v=50.0     -> 28-14.0     = 14.0
    #     v=66.6667  -> 28-18.6667  = 9.3
    #     v=75.0     -> 28-21.0     = 7.0
    assert coords == ["0.0,0.0", "40.0,14.0", "80.0,9.3", "120.0,7.0"]

    # Last rolling value is 75.0 -- lands in the ">=60 amber" bracket
    # (not >=80 green, not <60 red), so the route's real trade data
    # drives a specific, non-default color.
    assert color == "#e2b25a"


def test_strategy_row_links_to_tuning_and_journal(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT_EMPTY)
    r = client.get("/strategies", headers=auth)
    html = r.data.decode("utf-8")
    assert "/tuning?strategy=RSI" in html
    assert "/journal?strategy=RSI" in html


def test_plans_board_strategy_cell_links_to_strategies_anchor(client, auth):
    # No rank_plans monkeypatch (see the note on test_lifecycle_strip_counts_
    # and_click_filters above): mocking rank_plans to return dicts breaks
    # _ranked_plan_rows, which calls plan_to_dict()/follow_score() on
    # rank_plans()'s output expecting TradePlanV2 objects, not dicts.
    # Real PlanStore.update() raises KeyError for an unseen plan_id --
    # .add() is the real insert call (see the C7 commit's deviation note).
    PlanStore().add(_plan("p1", "AAPL"))  # strategy="RSI" per the _plan() test factory's default
    r = client.get("/plans", headers=auth)
    html = r.data.decode("utf-8")
    assert "/strategies#strategy-rsi" in html


def test_calibration_page_renders_chart_data_and_tier_table(client, auth, monkeypatch):
    fake_snapshot = {
        "built_at": "x",
        "calibration": {
            "deciles": [{"decile": 10, "n": 30, "win_rate": 88.0}, {"decile": 1, "n": 25, "win_rate": 55.0}],
            "tiers": [
                {"tier": "A", "n": 200, "win_rate": 84.0, "expected_band": "80-100", "ok": True},
                {"tier": "C", "n": 40, "win_rate": 55.0, "expected_band": "0-60", "ok": False},
            ],
            "drift": [],
        },
    }
    monkeypatch.setattr("swingbot.admin.pages.load_snapshot", lambda max_age_seconds=3600: fake_snapshot)
    r = client.get("/calibration", headers=auth)
    html = r.data.decode("utf-8")
    assert r.status_code == 200
    assert '"deciles"' in html
    assert "❌" in html  # the failing tier C row


class _FakeJournalStoreForPages:
    _ENTRIES = [
        {"trade_id": "t1", "ticker": "AAPL", "strategy": "RSI", "tags": ["clean_breakout"], "outcome": "win",
         "r_realized": 1.4, "mfe_r": 1.6, "mae_r": -0.2, "exit_efficiency": 0.87,
         "auto_lesson": "Waited for full confirmation before entering -- textbook execution.", "note": None},
        {"trade_id": "t2", "ticker": "MSFT", "strategy": "MACD", "tags": ["chased"], "outcome": "loss",
         "r_realized": -1.0, "mfe_r": 0.1, "mae_r": -1.0, "exit_efficiency": 0.0,
         "auto_lesson": "Entered after the move was already extended.", "note": "entered late"},
    ]

    def entries(self, *, strategy=None, tag=None, outcome=None, has_note=None):
        rows = list(self._ENTRIES)
        if strategy:
            rows = [r for r in rows if r["strategy"] == strategy]
        if tag:
            rows = [r for r in rows if tag in r["tags"]]
        if outcome:
            rows = [r for r in rows if r["outcome"] == outcome]
        if has_note is not None:
            rows = [r for r in rows if (r["note"] is not None) == has_note]
        return rows


def test_journal_page_filters_and_shows_lesson(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.pages.JournalStore", _FakeJournalStoreForPages)
    r = client.get("/journal?tag=clean_breakout", headers=auth)
    html = r.data.decode("utf-8")
    assert "AAPL" in html
    assert "MSFT" not in html
    assert "textbook execution" in html
