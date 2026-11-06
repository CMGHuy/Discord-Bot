"""v204: analytics, sparkline and calendar builders; the file producer keeps its behaviour."""
import functools
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot.core.analytics import admin_snapshots as snaps
from swingbot.core.analytics import snapshots
from swingbot.core.marketdata.shared import admin_refresh as ar
from tests.admin_snapshots.golden_book import (  # noqa: F401
    GOLDEN_MONTH, _clear_login_limiter, admin_app, assert_matches_golden, client, golden_book,
    golden_payload)

ROUTES = ("analytics.performance", "analytics.equity_curve", "calendar.pnl")
RESULTS = Path(__file__).resolve().parents[2] / "docs/superpowers/results/2026-10-29-v204-measure-first.md"
NOW = datetime(2026, 10, 2, 15, 0, tzinfo=timezone.utc)


def test_snapshot_routes_follow_the_measured_verdicts():
    text = RESULTS.read_text(encoding="utf-8")
    verdicts = {}
    for route in ROUTES:
        found = re.findall(rf"{re.escape(route)}\W+(request|snapshot)\b", text)
        assert found, f"no verdict line for {route}"
        verdicts[route] = found[0]
    assert snaps.SNAPSHOT_ROUTES == frozenset(r for r, v in verdicts.items() if v == "snapshot")


def test_builders_order_with_every_route_snapshotted(monkeypatch):
    monkeypatch.setattr(snaps, "SNAPSHOT_ROUTES", frozenset(ROUTES))
    for name in ("build_performance", "build_equity_curve", "build_calendar"):
        monkeypatch.setattr(snaps, name, lambda *a: None, raising=False)
    keys = list(snaps.builders(NOW))
    assert keys == ["risk", "analytics.snapshot",
                    "analytics.performance:main", "analytics.equity_curve:main",
                    "analytics.performance:weak", "analytics.equity_curve:weak",
                    "analytics.performance:both", "analytics.equity_curve:both",
                    *[ar.calendar_key(m) for m in ar.calendar_months(NOW)]]


def test_builders_hold_only_the_routes_marked_snapshot():
    keys = set(snaps.builders(NOW))
    assert {"risk", "analytics.snapshot"} <= keys
    prefixes = {"analytics.performance": "analytics.performance:",
                "analytics.equity_curve": "analytics.equity_curve:", "calendar.pnl": "calendar.pnl:"}
    for route, prefix in prefixes.items():
        has = any(k.startswith(prefix) for k in keys)
        assert has is (route in snaps.SNAPSHOT_ROUTES)
    assert all(ar.is_snapshot_key(k) for k in keys)


def test_compute_snapshot_raises_and_refresh_snapshot_still_swallows(monkeypatch):
    def broken():
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(snapshots, "gather_sources", broken)
    with pytest.raises(RuntimeError, match="registry unreadable"):
        snapshots.compute_snapshot()
    assert snapshots.refresh_snapshot() is None


def test_refresh_snapshot_still_saves_the_computed_doc(monkeypatch):
    saved = []
    monkeypatch.setattr(snapshots, "compute_snapshot", lambda sources=None: {"a": 1})
    monkeypatch.setattr(snapshots, "save_snapshot", saved.append)
    snapshots.refresh_snapshot()
    assert saved == [{"a": 1}]


def test_analytics_builder_never_writes_the_file_and_records_trade_ids(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("analytics_snapshot.json written by the refresher")
    src = snapshots.SnapshotSources(closed=[{"id": 1}], weak_closed=[{"id": 2}],
                                    starting_balance=10_000.0, registry_entries=[])
    monkeypatch.setattr(snapshots, "save_snapshot", boom)
    monkeypatch.setattr(snapshots, "gather_sources", lambda: src)
    monkeypatch.setattr(snapshots, "build_snapshot",
                        lambda closed, bal, reg, *, weak_closed=(): {"n": len(closed)})
    res = snaps.build_analytics_snapshot()
    assert res.doc == {"n": 1} and res.stale_inputs is False
    assert res.inputs["trade_ids"] == [1, 2]


def test_analytics_snapshot_and_sparkline_match_golden(golden_book):
    doc = snaps.build_analytics_snapshot().doc
    assert_matches_golden("analytics_snapshot", doc)
    spark = [p["balance"] for p in doc["equity_curve"]["points"][-30:]]
    assert spark == golden_payload("sparkline")["points"]


@pytest.mark.parametrize("route, name, golden", [
    ("analytics.performance", "build_performance", "performance_main"),
    ("analytics.equity_curve", "build_equity_curve", "equity_curve_main"),
])
def test_ledger_builders_match_the_golden_route_body(golden_book, route, name, golden):
    if route not in snaps.SNAPSHOT_ROUTES:
        assert not hasattr(snaps, name)
        return
    res = getattr(snaps, name)("main")
    assert_matches_golden(golden, res.doc)
    assert res.inputs["ledger"] == "main" and res.stale_inputs is False


def test_calendar_builder_matches_the_golden_month(golden_book):
    if "calendar.pnl" not in snaps.SNAPSHOT_ROUTES:
        assert not hasattr(snaps, "build_calendar")
        return
    res = snaps.build_calendar(GOLDEN_MONTH)
    assert_matches_golden("calendar_pnl", res.doc)
    assert res.inputs["fx"] == {"EUR": {"rate": 1.1, "as_of": None}}
    assert res.inputs["trade_ids"] == list(dict.fromkeys(res.inputs["trade_ids"]))


def test_partial_builders_are_bound_to_their_scope(monkeypatch):
    monkeypatch.setattr(snaps, "SNAPSHOT_ROUTES", frozenset({"analytics.performance"}))
    monkeypatch.setattr(snaps, "build_performance", lambda ledger: ledger, raising=False)
    fn = snaps.builders(NOW)["analytics.performance:weak"]
    assert isinstance(fn, functools.partial) and fn() == "weak"
