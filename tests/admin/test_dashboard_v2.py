"""Dashboard v2 fragment behaviors: bounded history, pedigree chips, leg
rows, lifecycle strip, equity sparkline."""
import json
import os


def _seed_many_closed_trades(data_dir, n):
    trades = []
    for i in range(n):
        trades.append({
            "id": f"t{i}", "ticker": "AAA", "status": "win", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
            "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00+00:00",
            "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        })
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def test_dashboard_fragment_bounds_closed_history_at_500(client, auth, admin_app):
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 510)
    r = client.get("/dashboard/fragment?mode=all", headers=auth)
    html = r.data.decode("utf-8")
    assert "Showing latest 500 of 510" in html
    assert html.count('id="ct-row-') <= 500


def test_dashboard_fragment_no_banner_under_limit(client, auth, admin_app):
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 40)
    r = client.get("/dashboard/fragment?mode=all", headers=auth)
    assert "Showing latest" not in r.data.decode("utf-8")


def test_dashboard_open_trade_renders_pedigree_chip_and_runner_row(client, auth, admin_app):
    from swingbot import config
    trades = [{
        "id": "t1", "ticker": "AAPL", "status": "open", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00",
        "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        "tier": "A", "badge": "VALIDATED",
        "legs": [{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                {"fraction": 0.5, "exit_price": None, "r": None}],
    }]
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    r = client.get("/dashboard/fragment", headers=auth)
    html = r.data.decode("utf-8")
    assert "chip-tier-a" in html
    assert "runner" in html
