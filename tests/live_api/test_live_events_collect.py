"""v202 V202-3: merge, sort, limit, and per-source failure of the activity feed."""
from datetime import datetime, timezone

import pytest

from swingbot.admin.api_v1 import live_events as ev
from tests.store_seed import seed_store

NOW = datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc)
PLAN = {"plan_id": "p1", "ticker": "MSFT", "direction": "bullish", "strategy": "VWAP",
        "horizon_key": "1m", "status": "ACTIVE", "created_at": "2026-10-29T08:00:00+00:00",
        "entry_price": 418.5,
        "status_history": [{"status": "ACTIVE", "reason": "limit_fill",
                            "at": "2026-10-29T13:40:00+00:00"}], "legs_realized": []}
TRADE = {"id": "812", "ticker": "NVDA", "direction": "bullish", "status": "win",
         "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
         "closed_at": "2026-10-29T15:20:00+00:00", "realized_pnl_amount": 200.0}
KILL = {"on": True, "reason": "daily loss", "at": "2026-10-29T07:31:00+00:00"}


def _loaders(**over):
    base = {"plans": lambda: [PLAN], "trades": lambda: [TRADE],
            "killswitch": lambda: KILL, "shares": lambda: {}}
    return {**base, **over}


def _boom():
    raise RuntimeError("source down")


def test_rows_merge_newest_first():
    rows, meta = ev.collect_events(8, loaders=_loaders(), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "paper_filled", "plan_alerted",
                                         "killswitch"]
    assert meta == {"availability": "ok", "as_of": "2026-10-29T16:00:00+00:00", "missing": []}


def test_limit_truncates_after_sorting():
    rows, _ = ev.collect_events(2, loaders=_loaders(), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "paper_filled"]


def test_a_failed_plans_source_is_partial_and_named():
    rows, meta = ev.collect_events(8, loaders=_loaders(plans=_boom), now=NOW)
    assert [r["kind"] for r in rows] == ["trade_closed", "killswitch"]
    assert meta["availability"] == "partial"
    assert meta["missing"] == ["plan_alerted", "paper_filled", "tp1_hit"]


def test_every_source_failing_is_unavailable_not_empty():
    loaders = {name: _boom for name in ("plans", "trades", "killswitch", "shares")}
    rows, meta = ev.collect_events(8, loaders=loaders, now=NOW)
    assert rows == []
    assert meta["availability"] == "unavailable"
    assert meta["missing"] == [kind.kind for kind in ev.EVENT_KINDS]


def test_a_builder_failing_on_bad_data_drops_only_its_kinds():
    rows, meta = ev.collect_events(8, loaders=_loaders(trades=lambda: None), now=NOW)
    assert meta["missing"] == ["trade_closed"]
    assert "trade_closed" not in {r["kind"] for r in rows}


def test_a_failed_shares_source_drops_no_kind():
    _, meta = ev.collect_events(8, loaders=_loaders(shares=_boom), now=NOW)
    assert meta["availability"] == "ok"


def test_the_quiet_day_is_ok_and_empty():
    rows, meta = ev.collect_events(8, loaders=_loaders(
        plans=lambda: [], trades=lambda: [], killswitch=lambda: {"on": False, "at": None}),
        now=NOW)
    assert (rows, meta["availability"]) == ([], "ok")


def test_the_trade_window_covers_the_largest_limit(admin_app):
    from swingbot.admin.api_v1 import live
    assert ev.TRADE_WINDOW >= live.MAX_LIMIT


def test_live_serves_the_feed(logged_in):
    seed_store("plans", [PLAN])
    seed_store("killswitch", KILL)
    body = logged_in.get("/api/v1/live?limit=2").get_json()

    assert [r["kind"] for r in body["events"]] == ["paper_filled", "plan_alerted"]
    assert set(body["events_meta"]) == {"availability", "as_of", "missing"}
    assert body["events_meta"]["availability"] == "ok"


def test_live_answers_200_when_a_source_fails(logged_in, monkeypatch):
    monkeypatch.setitem(ev.SOURCE_LOADERS, "plans", _boom)
    response = logged_in.get("/api/v1/live")
    assert response.status_code == 200
    meta = response.get_json()["events_meta"]
    assert meta["availability"] == "partial"
    assert meta["missing"] == ["plan_alerted", "paper_filled", "tp1_hit"]


@pytest.mark.parametrize("limit", ["1", "50"])
def test_live_limit_bounds_the_feed(logged_in, limit):
    seed_store("plans", [PLAN])
    body = logged_in.get(f"/api/v1/live?limit={limit}").get_json()
    assert len(body["events"]) <= int(limit)
