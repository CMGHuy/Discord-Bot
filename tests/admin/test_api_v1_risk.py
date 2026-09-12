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

import pandas as pd
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
    """Cluster detection fetches daily history per open ticker, and (v85
    D37/D38) so does the risk-metric/correlation block, via the batched
    sibling. That is parity with the Jinja page, not something these tests
    are about, and a suite that needs yfinance reachable fails for
    unrelated reasons. `open_book` below overrides the batch call with its
    own synthetic bars where a test needs real numbers out of it."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data",
                        lambda *a, **k: None, raising=False)
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch",
                        lambda *a, **k: {}, raising=False)


def _open_trade(trade_id, ticker="AAPL", entry=100.0, stop=95.0, shares=10):
    return {
        "id": trade_id, "ticker": ticker, "status": "open",
        "strategy": "VWAP", "horizon": "1m",
        "entry": entry, "stop_loss": stop, "take_profit": 120.0,
        "shares": shares, "opened_at": "2026-08-01T12:00:00+00:00",
    }


def _closed_trade(trade_id, ticker="AAPL", win=True):
    """A closed trade with a real, computable r_multiple -- see
    `metrics.r_multiple`. Alternates win/loss so a Sharpe/max-drawdown
    fixture is never a flat line of identical R."""
    return {
        "id": trade_id, "ticker": ticker, "status": "closed",
        "strategy": "VWAP", "horizon": "1m", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0,
        "exit_price": 110.0 if win else 90.0,
        "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "2026-01-02T00:00:00+00:00",
    }


@pytest.fixture
def open_book(client, tmp_path, monkeypatch):
    """Seeds `trades.json` with open positions (v85 D37/D38's book) and,
    optionally, a run of closed trades for the trade-sample metrics --
    then hands `get_daily_data_batch` synthetic daily bars for every open
    ticker plus the configured benchmark, so `/api/v1/risk`'s metric and
    correlation blocks compute real numbers instead of the `no_network`
    default of "nothing came back".

    Logs in through the same `client` a test also requests -- fixtures are
    cached per test, so the two names resolve to one already-authenticated
    session.
    """
    client.post("/api/v1/session", json=_LOGIN)

    def _make(tickers: list[str], bars: int = 120, closed_trades: int = 0) -> None:
        trades = [
            _open_trade(f"o{i:015d}", ticker) for i, ticker in enumerate(tickers)
        ]
        trades += [
            _closed_trade(f"c{i:015d}", tickers[0] if tickers else "AAPL", win=(i % 2 == 0))
            for i in range(closed_trades)
        ]
        (tmp_path / "trades.json").write_text(json.dumps(trades), encoding="utf-8")

        # A gently oscillating close series -- flat would make every
        # variance-based metric (vol, VaR, beta, correlation) None by
        # construction, which would prove nothing about the "has real data"
        # path these tests exist to cover.
        closes = [100.0 + (i % 7) - 3 for i in range(bars)]
        frame = pd.DataFrame(
            {"Close": closes}, index=pd.bdate_range("2026-01-01", periods=bars)
        )
        fake_bars = {ticker: frame.copy() for ticker in tickers}
        fake_bars["SPY"] = frame.copy()
        monkeypatch.setattr(
            "swingbot.core.marketdata.data.get_daily_data_batch",
            lambda symbols, *a, fake_bars=fake_bars, **k: {
                s: fake_bars[s] for s in symbols if s in fake_bars
            },
            raising=False,
        )

    return _make


def test_requires_auth(client):
    assert_error(client.get("/api/v1/risk"), "auth", 401)


def test_risk_shape(logged_in, killswitch_file):
    body = logged_in.get("/api/v1/risk").get_json()
    assert_shape(body, {
        "heat": dict, "positions": list, "sector_heat": list,
        "clusters": list, "throttle": dict, "killswitch": dict,
        "scan_health": dict, "metrics": dict, "correlation": dict,
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
    # v85 D37: every metric is a {value, n} pair, never a bare number.
    metric_keys = ("var_95", "expected_shortfall_95", "annualised_vol",
                   "beta_spy", "sharpe_r", "max_drawdown_r")
    assert_shape(body["metrics"], {
        **{key: dict for key in metric_keys},
        "as_of": NULLABLE_STR,
        # I4: the tile label must name the ACTUAL configured benchmark, not
        # a hardcoded "SPY" -- carried on the payload so the frontend can
        # render it instead of assuming.
        "benchmark_symbol": str,
    }, where="metrics")
    for key in metric_keys:
        assert_shape(body["metrics"][key], {
            "value": NULLABLE_NUMBER, "n": int,
        }, where=f"metrics.{key}")
    # v85 D38.
    assert_shape(body["correlation"], {
        "labels": list, "values": list,
    }, where="correlation")


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


# -- v85 D37/D38 -- the institutional risk metric set and the correlation
# matrix, both served from GET /risk (R8-03). --

def test_every_metric_carries_its_own_sample_size(client, open_book):
    open_book(["AAPL", "MSFT"])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    for key in ("var_95", "expected_shortfall_95", "annualised_vol",
                "beta_spy", "sharpe_r", "max_drawdown_r"):
        assert set(metrics[key]) == {"value", "n"}


def test_a_metric_that_cannot_be_computed_is_null_not_zero(client, open_book):
    open_book(["AAPL"], bars=3)
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["value"] is None
    assert metrics["var_95"]["n"] is not None


def test_distributional_and_trade_metrics_report_different_samples(client, open_book):
    open_book(["AAPL", "MSFT"], bars=120, closed_trades=40)
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["n"] != metrics["sharpe_r"]["n"]


def test_an_empty_book_returns_metrics_of_nulls_rather_than_omitting_them(client, open_book):
    open_book([])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["var_95"]["value"] is None
    assert metrics["beta_spy"]["value"] is None


def test_the_correlation_labels_match_the_open_positions(client, open_book):
    open_book(["AAPL", "MSFT"])
    corr = client.get("/api/v1/risk").get_json()["correlation"]
    assert corr["labels"] == ["AAPL", "MSFT"]
    assert len(corr["values"]) == 2


def test_json_is_parseable_with_a_flat_price_position_in_the_book(
        logged_in, killswitch_file, tmp_path, monkeypatch):
    """C1: a zero-variance leg (a halted ticker, a stale cache entry) makes
    the correlation step's `.corr()` return NaN. Flask has no custom JSON
    provider registered anywhere in this repo, so its `DefaultJSONProvider`
    would emit the literal token `NaN` for an unguarded NaN float -- not
    valid JSON per spec, and a strict browser JSON.parse() rejects the whole
    response, blanking the page (killswitch included). The response must
    stay free of that literal token even with a flat-price ticker in the
    open book.

    NOTE: `json.loads()` does NOT catch this -- Python's json module accepts
    bare `NaN`/`Infinity`/`-Infinity` tokens by design (`parse_constant`
    defaults to `float`), so `json.loads(response.data)` would pass whether
    or not the NaN-in-correlation-matrix bug is present. The raw bytes must
    be checked directly instead.
    """
    (tmp_path / "trades.json").write_text(json.dumps([
        _open_trade("a" * 16, "FLAT"), _open_trade("b" * 16, "AAPL"),
    ]), encoding="utf-8")

    bars = 40
    flat = pd.DataFrame(
        {"Close": [100.0] * bars}, index=pd.bdate_range("2026-01-01", periods=bars),
    )
    moving = pd.DataFrame(
        {"Close": [100.0 + (i % 7) - 3 for i in range(bars)]},
        index=pd.bdate_range("2026-01-01", periods=bars),
    )
    fake_bars = {"FLAT": flat, "AAPL": moving, "SPY": moving}
    monkeypatch.setattr(
        "swingbot.core.marketdata.data.get_daily_data_batch",
        lambda symbols, *a, **k: {s: fake_bars[s] for s in symbols if s in fake_bars},
        raising=False,
    )

    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    assert b"NaN" not in response.data, (
        "a literal NaN token in the raw response is invalid JSON -- "
        "json.loads() would NOT catch this, it accepts bare NaN by design"
    )
    body = json.loads(response.data)
    assert body["correlation"]["labels"] == ["AAPL", "FLAT"]
    assert isinstance(body["killswitch"]["on"], bool)


def test_a_market_data_failure_degrades_the_metrics_not_the_page(
        client, open_book, monkeypatch):
    """I2: the market-data section (bars fetch through the correlation
    matrix) is wrapped in its own try/except so a hiccup anywhere in it
    degrades to null market-data metrics rather than 500ing the page the
    killswitch lives on. The patch target is `swingbot.core.marketdata.data`,
    the ORIGIN module `get_daily_data_batch` is imported from -- `risk.py`
    imports it with a function-local `from ... import`, which binds a local
    name, not a module attribute, so patching
    `swingbot.admin.api_v1.risk.get_daily_data_batch` does not exist to
    patch. Same target the `no_network` fixture above already uses.

    `sharpe_r`/`max_drawdown_r` are trade-log-derived with NO dependency on
    price data (they come from `TradeLog`, fetched safely before this
    section), so a market-data failure must NOT blank them -- only the
    metrics that actually need bars (VaR, ES, annualised vol, beta) go
    null. The correlation matrix's `labels` are just the open-position
    ticker list -- also trade-log-derived, no price data needed -- so those
    survive too; only the `values` matrix (which needs bars) empties out.
    """
    open_book(["AAPL"], closed_trades=10)

    def _boom(*a, **k):
        raise RuntimeError("no network")

    monkeypatch.setattr(
        "swingbot.core.marketdata.data.get_daily_data_batch", _boom, raising=False,
    )

    response = client.get("/api/v1/risk")
    assert response.status_code == 200
    body = response.get_json()
    metrics = body["metrics"]

    # Market-data-dependent metrics: null.
    assert metrics["var_95"]["value"] is None
    assert metrics["expected_shortfall_95"]["value"] is None
    assert metrics["annualised_vol"]["value"] is None
    assert metrics["beta_spy"]["value"] is None

    # Trade-log-derived metrics: real numbers, unaffected by the outage.
    assert metrics["sharpe_r"]["value"] is not None
    assert metrics["sharpe_r"]["n"] > 0
    assert metrics["max_drawdown_r"]["value"] is not None
    assert metrics["max_drawdown_r"]["n"] > 0

    # Correlation labels are trade-log-derived (the open ticker list); only
    # the price-derived values matrix is empty.
    assert body["correlation"]["labels"] == ["AAPL"]
    assert body["correlation"]["values"] == []

    assert body["heat"] is not None


def test_a_malformed_closed_trade_degrades_only_the_trade_derived_metrics(
        client, open_book, tmp_path):
    """Round 3: `r_series = trade_metrics.r_multiples(closed)` and the
    `sharpe_r`/`max_drawdown_r` computation run entirely OUTSIDE the
    market-data try/except (that separation was round 2's fix, for the
    opposite failure domain) -- and were therefore, until this fix,
    completely unguarded. A malformed closed-trade record (here, a
    string-typed `entry`) raises a `TypeError` deep inside
    `metrics.r_multiple()`'s `abs(entry - stop)`, which must degrade only
    `sharpe_r`/`max_drawdown_r` to null, not 500 the whole endpoint --
    including the killswitch control block, which has nothing to do with
    the trade log. This is the structural mirror of
    `test_a_market_data_failure_degrades_the_metrics_not_the_page` above,
    for the trade-log failure domain instead of the market-data one.
    """
    open_book(["AAPL"], closed_trades=5)

    trades = json.loads((tmp_path / "trades.json").read_text(encoding="utf-8"))
    trades.append({
        "id": "m" * 16, "ticker": "AAPL", "status": "closed",
        "strategy": "VWAP", "horizon": "1m", "direction": "bullish",
        "entry": "not-a-number", "stop_loss": 95.0, "exit_price": 110.0,
        "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "2026-01-02T00:00:00+00:00",
    })
    (tmp_path / "trades.json").write_text(json.dumps(trades), encoding="utf-8")

    response = client.get("/api/v1/risk")
    assert response.status_code == 200
    body = response.get_json()
    metrics = body["metrics"]

    # Trade-log-derived metrics: degraded to null by the malformed record.
    assert metrics["sharpe_r"]["value"] is None
    assert metrics["sharpe_r"]["n"] == 0
    assert metrics["max_drawdown_r"]["value"] is None
    assert metrics["max_drawdown_r"]["n"] == 0

    # Market-data-derived metrics: unaffected -- this is a trade-log
    # failure, not a market-data one, and the two guards are independent.
    assert metrics["var_95"]["value"] is not None
    assert metrics["beta_spy"]["value"] is not None

    # Everything else on the payload still renders, unblanked -- including
    # the killswitch block this whole endpoint exists to keep alive.
    assert "on" in body["killswitch"]
    assert body["heat"] is not None
    assert body["correlation"]["labels"] == ["AAPL"]


def test_beta_tile_carries_the_actual_configured_benchmark(client, open_book):
    """I4: the payload must name the real benchmark so the frontend can
    label the tile correctly instead of assuming "SPY"."""
    open_book(["AAPL"])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    assert metrics["benchmark_symbol"] == "SPY"


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
    from swingbot.core.scanning import telemetry

    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    for _ in range(20):
        engine.log_scan_telemetry({"duration_s": 60, "tickers": 150})
    engine.log_scan_telemetry({"duration_s": 150, "tickers": 150})

    health = logged_in.get("/api/v1/risk").get_json()["scan_health"]
    assert health["latest_s"] == 150
    assert health["slowdown"] is True
    assert all(isinstance(d, (int, float)) for d in health["durations_s"])
