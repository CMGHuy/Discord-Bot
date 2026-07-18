import datetime as dt

from swingbot.core.analytics.snapshots import build_snapshot, save_snapshot, load_snapshot
from swingbot.core.analytics.aggregate import DIMENSIONS


def _t(i, status="win"):
    return {"id": f"t{i}", "ticker": "AAPL", "target_sources": ["EMA20"], "status": status,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0,
            "realized_pnl_amount": 80.0 if status == "win" else -40.0,
            "opened_at": f"2026-03-0{i}T10:00:00+00:00", "closed_at": f"2026-03-0{i+1}T10:00:00+00:00",
            "horizon_key": "4w", "tier": "A", "badge": "VALIDATED", "source": "confluence",
            "confidence_level": 4, "quality_score": 75}


def test_build_snapshot_has_every_documented_key():
    closed = [_t(1), _t(2), _t(3, "loss"), _t(4), _t(5)]
    snap = build_snapshot(closed, starting_balance=10_000.0, registry_entries=[])
    assert set(snap) == {"built_at", "overall", "equity_curve", "drawdown", "rolling_wr", "by",
                         "calibration", "r_multiples"}
    assert set(snap["overall"]) == {"n", "wins", "losses", "win_rate", "expectancy_r",
                                    "profit_factor", "sharpe", "sortino", "max_drawdown_pct",
                                    "total_pnl", "streaks"}
    assert set(snap["by"]) == set(DIMENSIONS)
    assert set(snap["calibration"]) == {"deciles", "tiers", "drift"}
    assert snap["overall"]["n"] == 5


def test_save_and_load_snapshot_roundtrip(tmp_path):
    path = str(tmp_path / "analytics_snapshot.json")
    snap = build_snapshot([_t(1)], 10_000.0, [])
    save_snapshot(snap, path=path)
    loaded = load_snapshot(path=path, max_age_seconds=3600)
    assert loaded is not None and loaded["overall"]["n"] == 1


def test_load_snapshot_missing_or_stale_returns_none(tmp_path):
    path = str(tmp_path / "analytics_snapshot.json")
    assert load_snapshot(path=path) is None

    stale = build_snapshot([_t(1)], 10_000.0, [])
    stale["built_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    save_snapshot(stale, path=path)
    assert load_snapshot(path=path, max_age_seconds=3600) is None


from unittest.mock import patch

from swingbot.core.analytics.snapshots import refresh_snapshot, DEFAULT_PATH


def test_refresh_snapshot_writes_file(tmp_path, monkeypatch):
    snap_path = str(tmp_path / "analytics_snapshot.json")
    monkeypatch.setattr("swingbot.core.analytics.snapshots.DEFAULT_PATH", snap_path)

    fake_trades = [_t(1)]
    with patch("swingbot.core.performance.TradeLog") as MockLog, \
         patch("swingbot.core.account.load_account_config", return_value={"base_balance": 10_000.0}), \
         patch("swingbot.core.registry.load_registry", return_value=[]):
        MockLog.return_value.get_trades.return_value = fake_trades
        refresh_snapshot()

    import os
    assert os.path.exists(snap_path)


def test_refresh_snapshot_never_raises_on_failure(monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.snapshots.DEFAULT_PATH", "/nonexistent/deeply/nested/x.json")
    with patch("swingbot.core.performance.TradeLog", side_effect=RuntimeError("boom")):
        refresh_snapshot()  # must not raise
