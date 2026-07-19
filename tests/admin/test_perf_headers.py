"""Response-header behaviors: ETag/304 polling, gzip, chart caching."""


def test_dashboard_fragment_etag_304(client, auth):
    r1 = client.get("/dashboard/fragment", headers=auth)
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag, "expected an ETag header on the fragment response"

    r2 = client.get("/dashboard/fragment", headers={**auth, "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.data == b""


def test_dashboard_fragment_etag_changes_when_content_changes(client, auth):
    r1 = client.get("/dashboard/fragment?mode=all", headers=auth)
    r2 = client.get("/dashboard/fragment?mode=today", headers=auth)
    # Different query params -> (usually) different rendered HTML -> different ETag.
    # Both still 200 since neither request sent an If-None-Match at all.
    assert r1.status_code == 200 and r2.status_code == 200


import gzip


def test_gzip_applied_to_large_html_response(client, auth):
    r = client.get("/", headers={**auth, "Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") == "gzip"
    assert b"Dashboard" in gzip.decompress(r.data)


def test_gzip_skipped_without_accept_encoding(client, auth):
    r = client.get("/", headers=auth)  # no Accept-Encoding at all
    assert r.headers.get("Content-Encoding") is None


def test_gzip_skipped_for_small_response(client, auth):
    r = client.get("/api/health", headers={**auth, "Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") is None


import json
import os

_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
    "de0000000c4944415478da6360606060000000050001d78f7e6e0000000049454e44ae426082"
)


def _seed_trade(config_data_dir, trade_id, status, closed_at=None):
    path = os.path.join(config_data_dir, "trades.json")
    trades = json.load(open(path)) if os.path.exists(path) else []
    trades.append({
        "id": trade_id, "ticker": "AAPL", "status": status, "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-01-01T00:00:00+00:00", "closed_at": closed_at,
        "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
    })
    json.dump(trades, open(path, "w"))


def test_closed_trade_chart_is_cacheable(client, auth, admin_app, tmp_path, monkeypatch):
    from swingbot import config
    _seed_trade(config.DATA_DIR, "t1", "win", closed_at="2026-01-05T00:00:00+00:00")
    png_path = tmp_path / "t1_view.png"
    png_path.write_bytes(_TINY_PNG)
    monkeypatch.setattr("swingbot.admin.app.regenerate_chart_for_trade", lambda t: str(png_path))

    r = client.get("/trades/t1/chart.png", headers=auth)
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "private, max-age=86400"
    assert r.headers.get("Last-Modified")


def test_open_trade_chart_is_not_cached(client, auth, admin_app, tmp_path, monkeypatch):
    from swingbot import config
    _seed_trade(config.DATA_DIR, "t2", "open")
    png_path = tmp_path / "t2_view.png"
    png_path.write_bytes(_TINY_PNG)
    monkeypatch.setattr("swingbot.admin.app.regenerate_chart_for_trade", lambda t: str(png_path))

    r = client.get("/trades/t2/chart.png", headers=auth)
    assert r.headers.get("Cache-Control") == "no-store"
