"""NG14 — /api/v1/risk and /api/v1/risk/killswitch.

**Every test that touches the killswitch must patch
`throttle.KILLSWITCH_PATH`.** That constant is computed at import time from
`config.DATA_DIR` and `swingbot.core.edge.throttle` is deliberately absent
from conftest's reload list, so it keeps pointing at the real project's
data/killswitch.json whatever `admin_app` does. Writing through it from a
test would ENGAGE THE REAL BOT'S KILLSWITCH -- it never releases itself, so
the next live session would take no new entries and nothing would say why.
tests/admin/test_risk_panel.py patches the same constant for the Jinja
route; `killswitch_file` below is that precedent as a fixture.

The payload is broader than spec v14 Decision 7's three items. See risk.py:
sector heat, clusters, throttle and scan health are on today's page and the
specs never decided to drop them, so they are projected too and pinned here.
"""
import json

import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR,
                                         assert_error, assert_shape)

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def killswitch_file(admin_app, tmp_path, monkeypatch):
    """Redirect the killswitch away from the real data/ directory.

    See this module's docstring -- without it these tests pause the actual
    bot.
    """
    from swingbot.core.edge import throttle

    path = tmp_path / "killswitch.json"
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(path))
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Cluster detection fetches daily history per open ticker. That is
    parity with the Jinja page, not something these tests are about, and a
    suite that needs yfinance reachable fails for unrelated reasons."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data",
                        lambda *a, **k: None, raising=False)


def _open_trade(trade_id, ticker="AAPL", entry=100.0, stop=95.0, shares=10):
    return {
        "id": trade_id, "ticker": ticker, "status": "open",
        "strategy": "VWAP", "horizon": "1m",
        "entry": entry, "stop_loss": stop, "take_profit": 120.0,
        "shares": shares, "opened_at": "2026-08-01T12:00:00+00:00",
    }


def test_requires_auth(client):
    assert_error(client.get("/api/v1/risk"), "auth", 401)


def test_risk_shape(logged_in, killswitch_file):
    body = logged_in.get("/api/v1/risk").get_json()
    assert_shape(body, {
        "heat": dict, "positions": list, "sector_heat": list,
        "clusters": list, "throttle": dict, "killswitch": dict,
        "scan_health": dict,
    })
    assert_shape(body["heat"], {
        "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER,
    }, where="heat")
    assert_shape(body["throttle"], {
        "multiplier": NULLABLE_NUMBER, "paused": bool,
    }, where="throttle")
    assert_shape(body["killswitch"], {
        "on": bool, "reason": NULLABLE_STR, "at": NULLABLE_STR,
    }, where="killswitch")
    assert_shape(body["scan_health"], {
        "durations_s": list, "latest_s": NULLABLE_NUMBER, "slowdown": bool,
    }, where="scan_health")


def test_heat_carries_the_cap_it_is_measured_against(logged_in, killswitch_file):
    """A heat figure without its cap says nothing about whether you are near
    the limit -- the same reason the Dashboard ships risk_cap_pct."""
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["cap_pct"] > 0


def test_position_rows_sum_to_open_heat(logged_in, killswitch_file, tmp_path):
    """The guard against a second definition of risk. These rows come from
    heat.trade_risk_pct, which is exactly what open_heat sums; if either side
    ever recomputes risk from entry and stop, the two drift and this fails."""
    (tmp_path / "trades.json").write_text(json.dumps([
        _open_trade("a" * 16, "AAPL", entry=100.0, stop=95.0, shares=10),
        _open_trade("b" * 16, "MSFT", entry=200.0, stop=190.0, shares=5),
    ]), encoding="utf-8")

    body = logged_in.get("/api/v1/risk").get_json()
    assert len(body["positions"]) == 2
    assert_shape(body["positions"][0], {
        "trade_id": str, "ticker": str, "strategy": NULLABLE_STR,
        "shares": NULLABLE_NUMBER, "entry": NULLABLE_NUMBER,
        "stop_loss": NULLABLE_NUMBER, "risk_pct": NULLABLE_NUMBER,
    }, where="position")

    total = sum(p["risk_pct"] for p in body["positions"])
    assert total == pytest.approx(body["heat"]["open_pct"], abs=0.01)


def test_positions_are_ordered_by_risk(logged_in, killswitch_file, tmp_path):
    """Largest exposure first: the row that matters is the one at the top."""
    (tmp_path / "trades.json").write_text(json.dumps([
        _open_trade("a" * 16, "AAPL", entry=100.0, stop=99.0, shares=1),
        _open_trade("b" * 16, "MSFT", entry=200.0, stop=150.0, shares=20),
    ]), encoding="utf-8")

    rows = logged_in.get("/api/v1/risk").get_json()["positions"]
    assert [r["ticker"] for r in rows] == ["MSFT", "AAPL"]


def test_utilisation_is_not_clamped_at_100(logged_in, killswitch_file, tmp_path):
    """An over-cap portfolio must report the true figure. The Jinja page
    clamps the WIDTH of its bar so it cannot paint past its track; clamping
    the number would hide exactly the situation the reader needs to see.

    Risk is stated on the trade rather than derived from entry/stop/balance
    ON PURPOSE. `trade_risk_pct` honours a stored `risk_pct` and only falls
    back to the balance calculation without one -- and the balance is not
    reliably isolated: `account.load_account_config` takes its path as an
    import-time default argument (`account.py`'s CONFIG_PATH), and
    `swingbot.core.planning.account` is not in conftest's reload list, so whether it
    sees the test's account.json or the real one depends on which test
    imported it first. An earlier version of this test asserted against the
    seeded 10,000 balance and passed alone while failing in a full run.
    """
    (tmp_path / "trades.json").write_text(json.dumps([
        # 20% of the account at risk against the 6% default cap -> 333%.
        {**_open_trade("a" * 16, "AAPL"), "risk_pct": 20.0},
    ]), encoding="utf-8")

    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["open_pct"] == pytest.approx(20.0)
    assert heat["utilisation_pct"] > 100


def test_killswitch_roundtrip(logged_in, killswitch_file):
    from swingbot.core.edge import throttle

    body = logged_in.post("/api/v1/risk/killswitch", json={"on": True}).get_json()
    assert body["killswitch"]["on"] is True
    assert throttle.kill_state()["on"] is True
    assert logged_in.get("/api/v1/risk").get_json()["killswitch"]["on"] is True

    body = logged_in.post("/api/v1/risk/killswitch", json={"on": False}).get_json()
    assert body["killswitch"]["on"] is False
    assert throttle.kill_state()["on"] is False


def test_engaging_records_a_reason(logged_in, killswitch_file):
    """The Risk page shows the reason beside the state. An engaged killswitch
    with no explanation is the thing whoever finds it has to reconstruct."""
    body = logged_in.post("/api/v1/risk/killswitch",
                          json={"on": True, "reason": "SPY -6%"}).get_json()
    assert body["killswitch"]["reason"] == "SPY -6%"


def test_engaging_without_a_reason_still_records_where_it_came_from(
        logged_in, killswitch_file):
    assert logged_in.post("/api/v1/risk/killswitch",
                          json={"on": True}).get_json()["killswitch"]["reason"]


@pytest.mark.parametrize("payload", [{}, {"on": "false"}, {"on": 0},
                                     {"on": None}, {"action": "off"}])
def test_an_unclear_toggle_is_rejected(logged_in, killswitch_file, payload):
    """`on` is required and required to BE a bool.

    The Jinja form treats anything that is not the string "on" as off, which
    is safe for two buttons and dangerous for JSON: `{"on": "false"}` is
    truthy, `{"action": "off"}` misses the key entirely, and either silently
    RELEASING the killswitch while reporting success is the failure that
    matters here.
    """
    assert_error(logged_in.post("/api/v1/risk/killswitch", json=payload),
                 "invalid", 400)


def test_a_rejected_toggle_does_not_change_state(logged_in, killswitch_file):
    from swingbot.core.edge import throttle

    logged_in.post("/api/v1/risk/killswitch", json={"on": True})
    logged_in.post("/api/v1/risk/killswitch", json={"on": "false"})
    assert throttle.kill_state()["on"] is True, (
        "a 400 must leave the killswitch exactly as it was"
    )


def test_killswitch_requires_auth(client, killswitch_file):
    assert_error(client.post("/api/v1/risk/killswitch", json={"on": True}),
                 "auth", 401)


def test_sector_heat_is_a_sorted_list_not_a_map(logged_in, killswitch_file):
    """A JSON object has no guaranteed order, and the page ranks sectors by
    heat. Ordering that in the client means re-deriving a decision the server
    already made."""
    body = logged_in.get("/api/v1/risk").get_json()
    pcts = [row["heat_pct"] or 0.0 for row in body["sector_heat"]]
    assert pcts == sorted(pcts, reverse=True)
    for row in body["sector_heat"]:
        assert_shape(row, {"sector": str, "heat_pct": NULLABLE_NUMBER},
                     where="sector_heat row")


def test_scan_health_ships_numbers_not_svg(logged_in, killswitch_file, tmp_path, monkeypatch):
    """The Jinja page renders a sparkline server-side because Jinja needs
    one. Sub-project 3 owns how a sparkline looks in the SPA, and markup from
    the server takes that decision away from it."""
    from swingbot.core.scanning import engine

    monkeypatch.setattr(engine, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    for _ in range(20):
        engine.log_scan_telemetry({"duration_s": 60, "tickers": 150})
    engine.log_scan_telemetry({"duration_s": 150, "tickers": 150})

    health = logged_in.get("/api/v1/risk").get_json()["scan_health"]
    assert health["latest_s"] == 150
    assert health["slowdown"] is True
    assert all(isinstance(d, (int, float)) for d in health["durations_s"])
