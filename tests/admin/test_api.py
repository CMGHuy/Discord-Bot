"""Tests for the /api/* JSON blueprint."""
import json

from swingbot.core.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.plan_store import PlanStore


def test_health_requires_auth_json(client):
    r = client.get("/api/health")
    assert r.status_code == 401
    assert r.get_json() == {"error": "auth"}


def test_health_ok(client, auth):
    r = client.get("/api/health", headers=auth)
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert "versions" in body and "ui" in body["versions"]


def test_api_stats_returns_snapshot_verbatim(client, auth, monkeypatch):
    fake_snapshot = {"built_at": "2026-07-11T00:00:00+00:00", "by": {}, "calibration": {}}
    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: fake_snapshot)
    r = client.get("/api/stats", headers=auth)
    assert r.status_code == 200
    assert r.get_json() == fake_snapshot


def test_api_stats_self_heals_when_missing(client, auth, monkeypatch):
    calls = {"refresh": 0}

    def fake_refresh():
        calls["refresh"] += 1
        return {"built_at": "just-built", "by": {}, "calibration": {}}

    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: None)
    monkeypatch.setattr("swingbot.admin.api.refresh_snapshot", fake_refresh)
    r = client.get("/api/stats", headers=auth)
    assert r.get_json()["built_at"] == "just-built"
    assert calls["refresh"] == 1


def test_api_stats_fresh_query_forces_refresh(client, auth, monkeypatch):
    calls = {"refresh": 0}

    def fake_refresh():
        calls["refresh"] += 1
        return {"built_at": "forced", "by": {}, "calibration": {}}

    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: {"built_at": "stale"})
    monkeypatch.setattr("swingbot.admin.api.refresh_snapshot", fake_refresh)
    r = client.get("/api/stats?fresh=1", headers=auth)
    assert r.get_json()["built_at"] == "forced"
    assert calls["refresh"] == 1


def _seed_plan(plan_id, ticker, status, tier="A", badge="VALIDATED"):
    plan = TradePlanV2(
        plan_id=plan_id, ticker=ticker, created_at="2026-07-01", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish", entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=5, stop_loss=95.0,
        tp1=104.0, tp1_fraction=0.5, tp2=110.0, breakeven_trigger_fraction=0.5,
        trail_atr_mult=2.5, quality_score=70, quality_breakdown=[], tier=tier,
        badge=badge, badge_stats={}, status=status, status_history=[],
    )
    # Real PlanStore.update() raises KeyError for an unseen plan_id (it's an
    # upsert-on-existing-only method) -- .add() is the real insert call.
    PlanStore().add(plan)
    return plan


def _fake_ranked_plan_rows(plans):
    """Deterministic stand-in for api.py's own _ranked_plan_rows (which
    wraps analytics.rank.rank_plans + follow_score) -- this test suite
    verifies API wiring/filtering/counts, not Plan A's real scoring
    formula (that's analytics' own test suite's job)."""
    import dataclasses
    rows = [dataclasses.asdict(p) for p in plans]
    for i, r in enumerate(sorted(rows, key=lambda r: r["plan_id"])):
        r["follow_score"] = 100 - i
    return sorted(rows, key=lambda r: -r["follow_score"])


def test_api_plans_ranked_and_counted(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api._ranked_plan_rows", _fake_ranked_plan_rows)
    _seed_plan("p1", "AAPL", PlanStatus.PENDING)
    _seed_plan("p2", "MSFT", PlanStatus.ACTIVE)
    _seed_plan("p3", "TSLA", PlanStatus.ACTIVE, tier="B", badge="WEAK")

    r = client.get("/api/plans", headers=auth)
    body = r.get_json()
    assert [p["plan_id"] for p in body["plans"]] == ["p1", "p2", "p3"]  # follow_score descending
    assert body["counts"] == {"PENDING": 1, "ACTIVE": 2, "PARTIAL": 0, "CLOSED": 0, "CANCELLED": 0}


def test_api_plans_status_filter(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api._ranked_plan_rows", _fake_ranked_plan_rows)
    _seed_plan("p1", "AAPL", PlanStatus.PENDING)
    _seed_plan("p2", "MSFT", PlanStatus.ACTIVE)
    r = client.get("/api/plans?status=ACTIVE", headers=auth)
    body = r.get_json()
    assert [p["plan_id"] for p in body["plans"]] == ["p2"]
    # Counts stay computed from the FULL set regardless of the row filter.
    assert body["counts"]["PENDING"] == 1


class _FakeJournalStore:
    _ENTRIES = [
        {"trade_id": "t1", "ticker": "AAPL", "strategy": "RSI", "tags": ["clean_breakout"], "outcome": "win", "note": None},
        {"trade_id": "t2", "ticker": "MSFT", "strategy": "MACD", "tags": ["chased"], "outcome": "loss", "note": "entered late"},
    ]

    def entries(self, strategy=None, tag=None, outcome=None, has_note=None, limit=100):
        rows = list(self._ENTRIES)
        if strategy:
            rows = [r for r in rows if r["strategy"] == strategy]
        if tag:
            rows = [r for r in rows if tag in r["tags"]]
        if outcome:
            rows = [r for r in rows if r["outcome"] == outcome]
        if has_note is not None:
            rows = [r for r in rows if (r["note"] is not None) == has_note]
        return rows[:limit]

    def set_note(self, trade_id, note):
        for r in self._ENTRIES:
            if r["trade_id"] == trade_id:
                r["note"] = note
                return True
        return False


def test_api_journal_filters_by_tag(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.JournalStore", _FakeJournalStore)
    r = client.get("/api/journal?tag=chased", headers=auth)
    body = r.get_json()
    assert [e["trade_id"] for e in body["entries"]] == ["t2"]


def test_api_journal_note_roundtrips(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.JournalStore", _FakeJournalStore)
    r = client.post("/api/journal/t1/note", data={"note": "good clean entry"}, headers=auth)
    assert r.get_json() == {"ok": True}


def test_api_journal_note_unknown_id_404(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.JournalStore", _FakeJournalStore)
    r = client.post("/api/journal/does-not-exist/note", data={"note": "x"}, headers=auth)
    assert r.status_code == 404
    assert r.get_json() == {"ok": False}


# NOTE: by.strategy is a LIST of StatRow dicts (each carrying its dimension
# value in "key"), not a strategy-name-keyed dict as an earlier draft of
# this plan assumed -- see swingbot/core/analytics/aggregate.py's StatRow
# and snapshots.py's build_snapshot(). The fake snapshot below uses the
# real shape.
_FAKE_SNAPSHOT = {
    "built_at": "2026-07-11T00:00:00+00:00",
    "by": {"strategy": [
        {"key": "RSI", "n": 40, "win_rate": 77.5},
        {"key": "Fibonacci", "n": 12, "win_rate": 90.0},
    ]},
    "calibration": {
        "deciles": [{"decile": 10, "n": 30, "win_rate": 88.0}],
        "tiers": [{"tier": "A", "n": 200, "win_rate": 84.0, "expected_band": "80-100", "pass": True}],
        "drift": [{"strategy": "RSI", "decayed": True, "live_wr": 68.0, "oos_wr": 82.1, "delta": -14.1}],
    },
}


def test_api_calibration_returns_snapshot_block(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT)
    r = client.get("/api/calibration", headers=auth)
    body = r.get_json()
    assert body["deciles"] == _FAKE_SNAPSHOT["calibration"]["deciles"]
    assert body["tiers"] == _FAKE_SNAPSHOT["calibration"]["tiers"]
    assert body["drift"] == _FAKE_SNAPSHOT["calibration"]["drift"]


def test_api_registry_joins_live_stats(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.load_snapshot", lambda max_age_seconds=3600: _FAKE_SNAPSHOT)
    r = client.get("/api/registry", headers=auth)
    rows = {row["strategy"]: row for row in r.get_json()["registry"]}
    assert rows["RSI"]["live_n"] == 40
    assert rows["RSI"]["live_wr"] == 77.5
    assert rows["RSI"]["status"] in ("VALIDATED", "WEAK")  # from the real committed registry
    # A strategy the fake snapshot has no live data for still appears, with nulls.
    assert rows["Elliott Wave"]["live_n"] is None
