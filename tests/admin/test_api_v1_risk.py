"""NG14 — /api/v1/risk and /api/v1/risk/killswitch.

The killswitch is a row in the test database (truncated after every test),
so no test here can engage the real bot's killswitch.

The payload is broader than spec v14 Decision 7's three items. See risk.py:
sector heat, clusters, throttle and scan health are on today's page and the
specs never decided to drop them, so they are projected too and pinned here.
"""
import json

import pandas as pd
import pytest

from tests.admin.api_v1_contract import (NULLABLE_NUMBER, NULLABLE_STR,
                                         assert_error, assert_shape)
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


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


@pytest.fixture(autouse=True)
def fresh_risk_cache():
    """`GET /risk` reuses its two expensive halves for a few seconds; every
    test here seeds its own book, so none may read the previous test's."""
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1 import risk
    risk._invalidate_cache()
    yield
    risk._invalidate_cache()


def _open_trade(trade_id, ticker="AAPL", entry=100.0, stop=95.0, shares=10):
    return {
        "id": trade_id, "ticker": ticker, "status": "open", "direction": "bullish",
        "strategy": "VWAP", "horizon_key": "1m",
        "entry": entry, "stop_loss": stop, "take_profit": 120.0,
        "shares": shares, "opened_at": "2026-08-01T12:00:00+00:00",
    }


def _closed_trade(trade_id, ticker="AAPL", win=True):
    """A closed trade with a real, computable r_multiple -- see
    `metrics.r_multiple`. Alternates win/loss so a Sharpe/max-drawdown
    fixture is never a flat line of identical R."""
    return {
        "id": trade_id, "ticker": ticker, "status": "closed",
        "strategy": "VWAP", "horizon_key": "1m", "direction": "bullish",
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
        seed_store("trades", trades)

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


def test_risk_shape(logged_in):
    body = logged_in.get("/api/v1/risk").get_json()
    assert_shape(body, {
        "heat": dict, "positions": (list, type(None)),
        "sector_heat": (list, type(None)), "unmapped_count": int,
        "clusters": (list, type(None)), "throttle": dict, "killswitch": dict,
        "availability": dict,
        "scan_health": dict, "metrics": dict, "correlation": dict,
    })
    assert_shape(body["heat"], {
        "open_pct": NULLABLE_NUMBER, "cap_pct": NULLABLE_NUMBER,
        "utilisation_pct": NULLABLE_NUMBER,
        "gap_risk_amount": NULLABLE_NUMBER, "gap_risk_unknown": int,
    }, where="heat")
    assert_shape(body["throttle"], {
        "multiplier": NULLABLE_NUMBER, "paused": (bool, type(None)),
    }, where="throttle")
    assert_shape(body["killswitch"], {
        "on": (bool, type(None)), "reason": NULLABLE_STR, "at": NULLABLE_STR,
        "availability": dict,
    }, where="killswitch")
    assert_shape(body["scan_health"], {
        "durations_s": list, "latest_s": NULLABLE_NUMBER, "slowdown": bool,
        "data_sources": (dict, type(None)),
    }, where="scan_health")
    # v85 D37: every metric is a {value, n} pair, never a bare number.
    metric_keys = ("var_95", "expected_shortfall_95", "annualised_vol",
                   "beta_spy", "sharpe_r", "max_drawdown_r")
    assert_shape(body["metrics"], {
        **{key: dict for key in metric_keys},
        # v194 B8 -- the money twin of max_drawdown_r; carries its FX gap count.
        "max_drawdown_amount": dict,
        "as_of": NULLABLE_STR,
        # I4: the tile label must name the ACTUAL configured benchmark, not
        # a hardcoded "SPY" -- carried on the payload so the frontend can
        # render it instead of assuming.
        "benchmark_symbol": str,
    }, where="metrics")
    for key in metric_keys:
        counts = {"excluded_count": int, "invalid_date_count": int,
                  "invalid_outcome_count": int} if key in ("sharpe_r", "max_drawdown_r") else {}
        assert_shape(body["metrics"][key], {
            "value": NULLABLE_NUMBER, "n": int, **counts,
        }, where=f"metrics.{key}")
    assert_shape(body["metrics"]["max_drawdown_amount"], {
        "value": NULLABLE_NUMBER, "n": int, "fx_missing_count": int, "invalid_date_count": int,
    }, where="metrics.max_drawdown_amount")
    # v85 D38.
    assert_shape(body["correlation"], {
        "labels": list, "values": list,
    }, where="correlation")


def test_heat_carries_the_cap_it_is_measured_against(logged_in):
    """A heat figure without its cap says nothing about whether you are near
    the limit -- the same reason the Dashboard ships risk_cap_pct."""
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["cap_pct"] > 0


def test_position_rows_sum_to_open_heat(logged_in, tmp_path):
    """The guard against a second definition of risk. These rows come from
    heat.trade_risk_pct, which is exactly what open_heat sums; if either side
    ever recomputes risk from entry and stop, the two drift and this fails."""
    seed_store("trades", [
        _open_trade("a" * 16, "AAPL", entry=100.0, stop=95.0, shares=10),
        _open_trade("b" * 16, "MSFT", entry=200.0, stop=190.0, shares=5),
    ])

    body = logged_in.get("/api/v1/risk").get_json()
    assert len(body["positions"]) == 2
    assert_shape(body["positions"][0], {
        "trade_id": str, "ticker": str, "strategy": NULLABLE_STR,
        "shares": NULLABLE_NUMBER, "entry": NULLABLE_NUMBER,
        "stop_loss": NULLABLE_NUMBER, "risk_pct": NULLABLE_NUMBER,
        # v189 B4 -- beside the enforced figure, never summed into it.
        "risk_of_loss_amount": NULLABLE_NUMBER, "risk_of_loss_pct": NULLABLE_NUMBER,
    }, where="position")

    total = sum(p["risk_pct"] for p in body["positions"])
    assert total == pytest.approx(body["heat"]["open_pct"], abs=0.01)


def test_positions_are_ordered_by_risk(logged_in, tmp_path):
    """Largest exposure first: the row that matters is the one at the top."""
    seed_store("trades", [
        _open_trade("a" * 16, "AAPL", entry=100.0, stop=99.0, shares=1),
        _open_trade("b" * 16, "MSFT", entry=200.0, stop=150.0, shares=20),
    ])

    rows = logged_in.get("/api/v1/risk").get_json()["positions"]
    assert [r["ticker"] for r in rows] == ["MSFT", "AAPL"]


GAP_STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}


def _short_trade(trade_id, ticker, *, shares=25, gap_sizing=None):
    trade = dict(_open_trade(trade_id, ticker, entry=100.0, stop=102.0, shares=shares),
                 direction="bearish", take_profit=96.0)
    if gap_sizing is not None:
        trade["gap_sizing"] = gap_sizing
    return trade


def test_heat_carries_the_summed_gap_risk_of_open_shorts(logged_in):
    """v183: 25 sh x max(2, 100 x 4%) = 100.0 for the stamped short; the unstamped
    and the switch-off short are counted, not guessed; the long is not a short."""
    seed_store("trades", [
        _short_trade("a" * 16, "TSLA", gap_sizing=GAP_STAMP),
        _short_trade("b" * 16, "NIO"),
        _short_trade("c" * 16, "RIVN", gap_sizing=dict(GAP_STAMP, rule="stop")),
        _open_trade("d" * 16, "AAPL"),
    ])
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["heat"]["gap_risk_amount"] == pytest.approx(100.0)
    assert body["heat"]["gap_risk_unknown"] == 2
    total = sum(p["risk_pct"] for p in body["positions"])
    assert total == pytest.approx(body["heat"]["open_pct"], abs=0.01)    # heat stays on stop risk


def test_no_open_short_means_no_gap_figure(logged_in):
    seed_store("trades", [_open_trade("a" * 16, "AAPL")])
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["gap_risk_amount"] is None
    assert heat["gap_risk_unknown"] == 0


def test_only_unknown_shorts_give_null_not_zero(logged_in):
    seed_store("trades", [_short_trade("a" * 16, "NIO"), _short_trade("b" * 16, "RIVN", shares=0)])
    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["gap_risk_amount"] is None
    assert heat["gap_risk_unknown"] == 2


def test_a_failing_trade_read_degrades_the_gap_figure_not_the_page(logged_in, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("swingbot.core.tracking.performance.TradeLog.get_trades", boom)
    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    assert response.get_json()["heat"]["gap_risk_amount"] is None


def test_utilisation_is_not_clamped_at_100(logged_in, tmp_path):
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
    seed_store("trades", [
        # 20% of the account at risk against the 6% default cap -> 333%.
        {**_open_trade("a" * 16, "AAPL"), "risk_pct": 20.0},
    ])

    heat = logged_in.get("/api/v1/risk").get_json()["heat"]
    assert heat["open_pct"] == pytest.approx(20.0)
    assert heat["utilisation_pct"] > 100


# -- v85 D37/D38 -- the institutional risk metric set and the correlation
# matrix, both served from GET /risk (R8-03). --

def test_every_metric_carries_its_own_sample_size(client, open_book):
    open_book(["AAPL", "MSFT"])
    metrics = client.get("/api/v1/risk").get_json()["metrics"]
    for key in ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy"):
        assert set(metrics[key]) == {"value", "n"}
    # The closed-trade R metrics also report how many records were excluded
    # and why (chronology coverage, 60975f95); value and n stay mandatory.
    chronology = {"value", "n", "excluded_count", "invalid_date_count", "invalid_outcome_count"}
    for key in ("sharpe_r", "max_drawdown_r"):
        assert set(metrics[key]) == chronology


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
        logged_in, tmp_path, monkeypatch):
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
    seed_store("trades", [
        _open_trade("a" * 16, "FLAT"), _open_trade("b" * 16, "AAPL"),
    ])

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


def test_a_malformed_closed_trade_preserves_valid_trade_derived_metrics(
        client, open_book, monkeypatch):
    """A malformed outcome is excluded and counted beside valid closed trades."""
    open_book(["AAPL"], closed_trades=5)

    # A numeric column cannot hold a string `entry`, so the malformed record is
    # simulated: r_multiple() raises the same TypeError for one trade.
    seed_store("trades", [_closed_trade("m" * 16)])
    from swingbot.core.analytics import metrics as trade_metrics
    real_r_multiple = trade_metrics.r_multiple

    def flaky_r_multiple(trade):
        if trade["id"].startswith("m"):
            raise TypeError("unsupported operand type(s) for -: 'str' and 'float'")
        return real_r_multiple(trade)

    monkeypatch.setattr(trade_metrics, "r_multiple", flaky_r_multiple)

    response = client.get("/api/v1/risk")
    assert response.status_code == 200
    body = response.get_json()
    metrics = body["metrics"]

    sharpe = metrics["sharpe_r"]
    drawdown = metrics["max_drawdown_r"]
    assert (sharpe["value"] is not None, sharpe["n"], sharpe["invalid_outcome_count"]) == (True, 5, 1)
    assert (drawdown["value"] is not None, drawdown["n"], drawdown["excluded_count"]) == (True, 5, 1)

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


def test_killswitch_roundtrip(logged_in):
    from swingbot.core.edge import throttle

    body = logged_in.post("/api/v1/risk/killswitch", json={"on": True}).get_json()
    assert body["killswitch"]["on"] is True
    assert throttle.kill_state()["on"] is True
    assert logged_in.get("/api/v1/risk").get_json()["killswitch"]["on"] is True

    body = logged_in.post("/api/v1/risk/killswitch", json={"on": False}).get_json()
    assert body["killswitch"]["on"] is False
    assert throttle.kill_state()["on"] is False


def test_engaging_records_a_reason(logged_in):
    """The Risk page shows the reason beside the state. An engaged killswitch
    with no explanation is the thing whoever finds it has to reconstruct."""
    body = logged_in.post("/api/v1/risk/killswitch",
                          json={"on": True, "reason": "SPY -6%"}).get_json()
    assert body["killswitch"]["reason"] == "SPY -6%"


def test_engaging_without_a_reason_still_records_where_it_came_from(
        logged_in):
    assert logged_in.post("/api/v1/risk/killswitch",
                          json={"on": True}).get_json()["killswitch"]["reason"]


@pytest.mark.parametrize("payload", [{}, {"on": "false"}, {"on": 0},
                                     {"on": None}, {"action": "off"}, [], [True], "off"])
def test_an_unclear_toggle_is_rejected(logged_in, payload):
    """`on` is required and required to BE a bool.

    The Jinja form treats anything that is not the string "on" as off, which
    is safe for two buttons and dangerous for JSON: `{"on": "false"}` is
    truthy, `{"action": "off"}` misses the key entirely, and either silently
    RELEASING the killswitch while reporting success is the failure that
    matters here.
    """
    assert_error(logged_in.post("/api/v1/risk/killswitch", json=payload),
                 "invalid", 400)


def test_a_rejected_toggle_does_not_change_state(logged_in):
    from swingbot.core.edge import throttle

    logged_in.post("/api/v1/risk/killswitch", json={"on": True})
    logged_in.post("/api/v1/risk/killswitch", json={"on": "false"})
    assert throttle.kill_state()["on"] is True, (
        "a 400 must leave the killswitch exactly as it was"
    )


def test_killswitch_can_be_read_without_the_whole_risk_resource(logged_in):
    logged_in.post("/api/v1/risk/killswitch", json={"on": True, "reason": "test"})
    resp = logged_in.get("/api/v1/risk/killswitch")
    assert resp.status_code == 200
    assert resp.get_json()["killswitch"]["on"] is True


def test_killswitch_read_requires_auth(client):
    assert client.get("/api/v1/risk/killswitch").status_code == 401


def test_concurrent_risk_reads_share_one_portfolio_build(logged_in, monkeypatch):
    calls = []

    def counting_state():
        calls.append(1)
        return {}

    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state", counting_state)
    logged_in.get("/api/v1/risk")
    logged_in.get("/api/v1/risk")
    assert len(calls) == 1


def test_a_cached_risk_read_still_shows_a_fresh_killswitch(logged_in):
    assert logged_in.get("/api/v1/risk").get_json()["killswitch"]["on"] is False
    logged_in.post("/api/v1/risk/killswitch", json={"on": True, "reason": "test"})
    assert logged_in.get("/api/v1/risk").get_json()["killswitch"]["on"] is True


def test_killswitch_requires_auth(client):
    assert_error(client.post("/api/v1/risk/killswitch", json={"on": True}),
                 "auth", 401)


def test_sector_heat_is_a_sorted_list_not_a_map(logged_in):
    """A JSON object has no guaranteed order, and the page ranks sectors by
    heat. Ordering that in the client means re-deriving a decision the server
    already made."""
    body = logged_in.get("/api/v1/risk").get_json()
    pcts = [row["heat_pct"] or 0.0 for row in body["sector_heat"]]
    assert pcts == sorted(pcts, reverse=True)
    for row in body["sector_heat"]:
        assert_shape(row, {"sector": str, "heat_pct": NULLABLE_NUMBER},
                     where="sector_heat row")


def test_unmapped_count_carries_the_collectors_count(logged_in, monkeypatch):
    """v194 B6: `sector_heat: []` over open positions is "no sector data for
    N positions", and the response says N."""
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state",
                        lambda: {"sector_heat": {}, "unmapped_count": 8})
    body = logged_in.get("/api/v1/risk").get_json()
    assert body["sector_heat"] == []
    assert body["unmapped_count"] == 8


def test_unmapped_count_is_zero_when_the_collector_has_none(logged_in, monkeypatch):
    monkeypatch.setattr("swingbot.core.edge.portfolio_state.collect_portfolio_state", lambda: {})
    assert logged_in.get("/api/v1/risk").get_json()["unmapped_count"] == 0


def test_unmapped_count_from_a_real_book_with_a_partial_sector_map(open_book, client, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.universe.sector_map",
                        lambda name: {"AAPL": "Technology"})
    open_book(["AAPL", "ZZZZ"])
    body = client.get("/api/v1/risk").get_json()
    assert body["unmapped_count"] == 1
    assert [row["sector"] for row in body["sector_heat"]] == ["Technology"]


def test_scan_health_ships_numbers_not_svg(logged_in, tmp_path, monkeypatch):
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


def test_scan_health_summarises_data_sources(logged_in, tmp_path, monkeypatch):
    """v106: the fallback rate is yfinance-fallback over everything Alpaca was
    asked for (hits + misses), across the recent rows that carry the key."""
    from swingbot import config
    from swingbot.core.scanning import engine
    from swingbot.core.scanning import telemetry

    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    monkeypatch.setattr(config, "ALPACA_DATA_FEED_LIVE", "iex")
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150})   # pre-v106 row, no key
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150, "data_sources": {
        "alpaca": 9, "yfinance": 3, "yfinance-fallback": 1, "cache": 0}})
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150, "data_sources": {
        "alpaca": 10, "yfinance": 3, "yfinance-fallback": 0, "cache": 0}})

    ds = logged_in.get("/api/v1/risk").get_json()["scan_health"]["data_sources"]
    assert ds["enabled"] is True and ds["feed"] == "iex"
    assert ds["breaker_open"] is False
    assert ds["fallback_rate"] == pytest.approx(0.05)
    assert ds["scans"] == 2


def test_fallback_rate_pools_daily_frames_and_live_prices(
        logged_in, tmp_path, monkeypatch):
    from swingbot.core.scanning import engine
    from swingbot.core.scanning import telemetry

    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150,
        "data_sources": {"alpaca": 2, "yfinance": 0, "yfinance-fallback": 0, "cache": 70},
        "price_sources": {"alpaca": 72, "yfinance": 2, "yfinance-fallback": 6, "none": 0}})
    ds = logged_in.get("/api/v1/risk").get_json()["scan_health"]["data_sources"]
    assert ds["fallback_rate"] == pytest.approx(6 / 80)


def test_data_sources_fallback_rate_is_null_without_alpaca_traffic(
        logged_in, tmp_path, monkeypatch):
    from swingbot.core.scanning import engine
    from swingbot.core.scanning import telemetry

    monkeypatch.setattr(telemetry, "TELEMETRY_PATH", str(tmp_path / "scan_telemetry.jsonl"))
    engine.log_scan_telemetry({"duration_s": 60, "tickers": 150, "data_sources": {
        "alpaca": 0, "yfinance": 12, "yfinance-fallback": 0, "cache": 3}})
    ds = logged_in.get("/api/v1/risk").get_json()["scan_health"]["data_sources"]
    assert ds["fallback_rate"] is None and ds["scans"] == 1


# -- v194 B8 -- max drawdown in money, beside the R figure. --

def _settled(trade_id, *, ticker="AAPL", pnl, closed_at, status="closed"):
    """A closed main-ledger trade with a settled amount in its quote currency."""
    return {
        "id": trade_id, "ticker": ticker, "status": status,
        "strategy": "VWAP", "horizon_key": "1m", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "exit_price": 105.0, "shares": 10,
        "opened_at": "2026-07-01T00:00:00+00:00", "closed_at": closed_at,
        "realized_pnl_amount": pnl,
    }


@pytest.fixture
def eur_account(logged_in, monkeypatch):
    """A EUR account: USD quotes convert at 0.5 on every day; `NOFX` has no
    quote currency, so its rate is missing. Depends on `logged_in` so it is
    applied after the admin app's own FX pin. Returns the lookups made."""
    from swingbot.core.marketdata import fx
    asked = []

    def fake_rate(from_code, to_code, on):
        asked.append((from_code, to_code, on))
        return 0.5 if from_code == "USD" else None

    quotes = {"AAPL": "USD", "MSFT": "USD", "ASML.AS": "EUR"}
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: quotes.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return asked


def test_money_drawdown_walks_converted_pnl_in_close_order(logged_in, eur_account):
    # Seeded out of order on purpose: the walk sorts by closed_at.
    # In close order: +100, -300, +50, -200 USD -> x0.5 -> +50, -150, +25, -100 EUR.
    # Cumulative 50, -100, -75, -175; peak 50 -> largest fall 225.
    seed_store("trades", [
        _settled("c3", pnl=50.0, closed_at="2026-08-05T20:00:00+00:00"),
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c4", pnl=-200.0, closed_at="2026-08-06T20:00:00+00:00", status="loss"),
        _settled("c2", pnl=-300.0, closed_at="2026-08-04T20:00:00+00:00", status="loss"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 225.0, "n": 4, "fx_missing_count": 0, "invalid_date_count": 0}


def test_a_trade_without_a_rate_is_left_out_and_counted(logged_in, eur_account):
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", ticker="NOFX", pnl=-900.0, closed_at="2026-08-04T20:00:00+00:00"),
        _settled("c3", pnl=-300.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    # +50, -150 in EUR (cumulative 50, -100): the -900 with no rate is never read as 1.0.
    assert metric == {"value": 150.0, "n": 2, "fx_missing_count": 1, "invalid_date_count": 0}


def test_an_unsettled_close_is_left_out_but_not_counted_as_missing(logged_in, eur_account):
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", pnl=None, closed_at="2026-08-04T20:00:00+00:00"),
        _settled("c3", pnl=-100.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 50.0, "n": 2, "fx_missing_count": 0, "invalid_date_count": 0}   # +50, -50 EUR


def test_an_account_in_the_quote_currency_converts_nothing(logged_in, eur_account, monkeypatch):
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    seed_store("trades", [
        _settled("c1", pnl=100.0, closed_at="2026-08-03T20:00:00+00:00"),
        _settled("c2", pnl=-300.0, closed_at="2026-08-04T20:00:00+00:00"),
    ])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": 300.0, "n": 2, "fx_missing_count": 0, "invalid_date_count": 0}
    assert eur_account == []          # identity: no rate was asked for


def test_no_closed_trade_gives_a_null_money_drawdown_not_zero(logged_in, eur_account):
    seed_store("trades", [_open_trade("o1")])
    metric = logged_in.get("/api/v1/risk").get_json()["metrics"]["max_drawdown_amount"]
    assert metric == {"value": None, "n": 0, "fx_missing_count": 0, "invalid_date_count": 0}


def test_a_conversion_failure_degrades_only_the_money_drawdown(logged_in, eur_account, monkeypatch):
    def boom(rows, **kwargs):
        raise RuntimeError("rate store down")

    monkeypatch.setattr("swingbot.admin.api_v1.money.to_account_currency", boom)
    seed_store("trades", [
        _closed_trade("c1", win=True), _closed_trade("c2", win=False),
        _settled("c3", pnl=-100.0, closed_at="2026-08-05T20:00:00+00:00"),
    ])
    response = logged_in.get("/api/v1/risk")
    assert response.status_code == 200
    metrics = response.get_json()["metrics"]
    assert metrics["max_drawdown_amount"] == {"value": None, "n": 0, "fx_missing_count": 0, "invalid_date_count": 0}
    assert metrics["max_drawdown_r"]["value"] is not None


def test_pnl_amounts_sorts_by_close_and_skips_unpriced_rows():
    import swingbot.admin.app  # noqa: F401 -- api_v1 imports resolve through the app
    from swingbot.admin.api_v1.risk import _pnl_amounts
    rows = [
        {"closed_at": "2026-08-05T00:00:00+00:00", "realized_pnl_amount": 3.0},
        {"closed_at": "2026-08-03T00:00:00+00:00", "realized_pnl_amount": 1.0},
        {"closed_at": "2026-08-04T00:00:00+00:00", "realized_pnl_amount": None},
        {"closed_at": None, "realized_pnl_amount": 9.0},
    ]
    assert _pnl_amounts(rows) == [1.0, 3.0]   # undated amounts are excluded before the walk
    assert _pnl_amounts([]) == []


@pytest.fixture
def projection_client(monkeypatch):
    """Exercise the decorated API routes without the store-backed app fixture."""
    from flask import Flask
    from swingbot.admin import app as app_module
    from swingbot.admin.api_v1 import risk

    from swingbot.core.tracking.performance import TradeLog

    monkeypatch.setattr(TradeLog, "get_trades", lambda *a, **kw: [])
    app = Flask(__name__)
    monkeypatch.setattr(app_module, "_session_authenticated", lambda: True)
    app.add_url_rule("/api/v1/risk", view_func=risk.get_risk)
    app.add_url_rule("/api/v1/risk/killswitch", view_func=risk.get_killswitch)
    app.add_url_rule("/api/v1/risk/killswitch", view_func=risk.set_killswitch,
                     methods=["POST"])
    return app.test_client()


@pytest.fixture
def projection_state(monkeypatch):
    from swingbot.admin.api_v1 import risk
    from swingbot.core.edge import portfolio_state, throttle
    stamp = "2026-10-28T00:00:00+00:00"
    ok = {"state": "ok", "checked_at": stamp, "reason": None}
    state = {"open_trades": [], "balance": 1000.0, "open_heat": 0.0,
             "heat_cap": 6.0, "sector_heat": {}, "unmapped_count": 0,
             "clusters": [], "throttle_mult": 1.0, "paused": False,
             "kill": {"on": False}, "growth": {},
             "availability": {key: dict(ok) for key in
                              ("positions", "heat", "sector_heat", "clusters", "throttle", "killswitch")}}
    monkeypatch.setattr(portfolio_state, "collect_portfolio_state", lambda: state)
    monkeypatch.setattr(risk, "_risk_metrics_and_correlation", lambda: ({}, {"labels": [], "values": []}, {}))
    monkeypatch.setattr(risk, "_scan_health", lambda: {})
    monkeypatch.setattr(throttle, "kill_state", lambda: {"on": False, "reason": None, "at": None})
    return state


def unavailable_read(*args, **kwargs):
    raise OSError("private diagnostic must not reach JSON")


def test_unknown_book_remains_null_in_api(projection_client, projection_state):
    state = projection_state
    state.update(open_trades=None, open_heat=None, sector_heat=None, clusters=None)
    for key in ("positions", "heat", "sector_heat", "clusters"):
        state["availability"][key].update(state="unavailable", reason="positions_unavailable")
    body = projection_client.get("/api/v1/risk").get_json()
    assert body["positions"] is None
    assert body["heat"]["open_pct"] is None
    assert body["sector_heat"] is None
    assert body["clusters"] is None
    assert body["availability"]["positions"]["state"] == "unavailable"
    assert body["killswitch"]["on"] is False


def test_invalid_balance_keeps_positions_without_percentage(projection_client, projection_state):
    projection_state.update(balance=None, open_heat=None,
                            open_trades=[_open_trade("visible")])
    projection_state["availability"]["heat"].update(state="unavailable", reason="invalid_balance")
    body = projection_client.get("/api/v1/risk").get_json()
    assert body["positions"][0]["trade_id"] == "visible"
    assert body["positions"][0]["risk_pct"] is None
    assert body["heat"]["utilisation_pct"] is None


def test_positions_do_not_read_trade_log_again(projection_client, projection_state, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    projection_state["open_trades"] = [_open_trade("snapshot")]
    monkeypatch.setattr(TradeLog, "get_trades", unavailable_read)
    body = projection_client.get("/api/v1/risk").get_json()
    assert body["positions"][0]["trade_id"] == "snapshot"


@pytest.mark.parametrize("path", ["/api/v1/risk", "/api/v1/risk/killswitch"])
def test_fresh_kill_failure_never_reuses_current_state(projection_client, projection_state, monkeypatch, path):
    from swingbot.core.edge import throttle
    first = projection_client.get(path).get_json()["killswitch"]
    monkeypatch.setattr(throttle, "kill_state", unavailable_read)
    body = projection_client.get(path).get_json()
    current = body["killswitch"]
    assert current["on"] is None
    assert current["availability"]["state"] == "unavailable"
    assert current["last_known"]["on"] is False
    assert current["last_known"]["checked_at"] == first["availability"]["checked_at"]
    assert "private diagnostic" not in str(body)
    if path == "/api/v1/risk":
        assert body["availability"]["killswitch"] == current["availability"]
        assert body["availability"]["positions"]["checked_at"] == projection_state["availability"]["positions"]["checked_at"]


def test_unknown_read_allows_explicit_engage_without_implicit_release(projection_client, projection_state, monkeypatch):
    from swingbot.core.edge import throttle
    calls = []
    monkeypatch.setattr(throttle, "kill_state", unavailable_read)
    monkeypatch.setattr(throttle, "set_kill", lambda on, **kw: calls.append(on))
    assert projection_client.get("/api/v1/risk/killswitch").get_json()["killswitch"]["on"] is None
    assert calls == []
    response = projection_client.post("/api/v1/risk/killswitch", json={"on": True})
    assert response.status_code == 200
    assert calls == [True]
    assert response.get_json()["killswitch"]["on"] is None
    assert response.get_json()["killswitch"]["availability"]["state"] == "unavailable"
    assert projection_client.post("/api/v1/risk/killswitch", json={"on": None}).status_code == 400
    assert calls == [True]


@pytest.mark.parametrize("payload", [[], [True], "off", {"on": None}, {"on": 0}])
def test_projection_rejects_non_boolean_commands(projection_client, projection_state,
                                                monkeypatch, payload):
    from swingbot.core.edge import throttle
    calls = []
    monkeypatch.setattr(throttle, "set_kill", lambda *a, **kw: calls.append(a))
    response = projection_client.post("/api/v1/risk/killswitch", json=payload)
    assert response.status_code == 400
    assert calls == []


def test_projection_write_failure_reports_unavailable(projection_client, projection_state, monkeypatch):
    from swingbot.core.edge import throttle
    monkeypatch.setattr(throttle, "set_kill", unavailable_read)
    response = projection_client.post("/api/v1/risk/killswitch", json={"on": True})
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "unavailable"
    assert "private diagnostic" not in response.get_data(as_text=True)


def test_projection_failed_readback_retains_original_observation(projection_client, projection_state,
                                                               monkeypatch):
    from swingbot.core.edge import throttle
    first = projection_client.get("/api/v1/risk/killswitch").get_json()["killswitch"]
    calls = []
    monkeypatch.setattr(throttle, "set_kill", lambda on, **kw: calls.append(on))
    monkeypatch.setattr(throttle, "kill_state", unavailable_read)
    current = projection_client.post("/api/v1/risk/killswitch", json={"on": True}).get_json()["killswitch"]
    assert calls == [True]
    assert current["on"] is None
    assert current["last_known"]["on"] is False
    assert current["last_known"]["checked_at"] == first["availability"]["checked_at"]


def test_projection_empty_book_and_controls_keep_observed_values(projection_client, projection_state):
    body = projection_client.get("/api/v1/risk").get_json()
    assert body["positions"] == []
    assert body["sector_heat"] == []
    assert body["clusters"] == []
    assert body["heat"]["open_pct"] == 0.0
    assert body["throttle"] == {"multiplier": 1.0, "paused": False}
    assert body["killswitch"]["availability"]["state"] == "ok"
    assert "last_known" not in body["killswitch"]


@pytest.fixture
def distribution_inputs(monkeypatch):
    import numpy as np
    from swingbot.admin.api_v1 import risk
    from swingbot.core.marketdata import fx

    closes = 100 * np.cumprod(1 + 0.01 * np.sin(np.arange(100)))
    frame = pd.DataFrame({"Close": closes}, index=pd.date_range("2026-01-01", periods=100))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: "EUR")
    monkeypatch.setattr(fx, "fx_rate", lambda *args: 1.0)
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {symbol: frame for symbol in symbols})
    return risk, frame


_DISTRIBUTION_CHECKED = "2026-10-28T00:00:00+00:00"


@pytest.mark.parametrize("direction,beta", [("bullish", 1.0), ("bearish", -1.0)])
def test_distribution_beta_preserves_position_direction(distribution_inputs, direction, beta):
    risk, _ = distribution_inputs
    trade = {**_open_trade("direction"), "direction": direction}
    metrics, corr, availability = risk._distribution_metrics([trade], "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["beta_spy"]["value"] == pytest.approx(beta)
    assert availability["distribution_metrics"]["state"] == "ok"
    assert corr["labels"] == ["AAPL"]


def test_distribution_offset_book_does_not_renormalize_risk(distribution_inputs):
    risk, _ = distribution_inputs
    long = _open_trade("long")
    short = {**long, "id": "short", "direction": "bearish"}
    metrics, corr, availability = risk._distribution_metrics([long, short], "SPY", _DISTRIBUTION_CHECKED)
    for name in ("var_95", "expected_shortfall_95", "annualised_vol", "beta_spy"):
        assert metrics[name]["value"] is None
    assert corr["labels"] == ["AAPL"]
    assert availability["distribution_metrics"]["state"] == "ok"


def test_distribution_missing_bars_are_unavailable(distribution_inputs, monkeypatch):
    risk, frame = distribution_inputs
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {"SPY": frame})
    metrics, _, availability = risk._distribution_metrics([_open_trade("missing")], "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["var_95"]["value"] is None
    assert availability["distribution_metrics"]["reason"] == "incomplete_bars"


def test_distribution_signed_exposures_keep_asset_correlation(distribution_inputs):
    risk, _ = distribution_inputs
    rows = [_open_trade("long", ticker="AAA"),
            {**_open_trade("short", ticker="BBB"), "direction": "bearish"}]
    _, corr, _ = risk._distribution_metrics(rows, "SPY", _DISTRIBUTION_CHECKED)
    assert corr["values"][0][1] == pytest.approx(1.0)


def test_distribution_market_failure_preserves_trade_metrics(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, **kw:
                        [_open_trade("open")] if status == "open" else [_closed_trade("closed")])
    monkeypatch.setattr(risk, "_money_metric", lambda closed: ({"value": 0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 0}, None))
    monkeypatch.setattr(risk, "_risk_bars", unavailable_read)
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["max_drawdown_r"]["n"] == 1
    assert metrics["max_drawdown_amount"]["n"] == 1
    assert availability["distribution_metrics"]["reason"] == "market_data_unavailable"


def test_distribution_missing_fx_is_explicit(distribution_inputs, monkeypatch):
    from swingbot.core.marketdata import fx
    risk, _ = distribution_inputs
    monkeypatch.setattr(fx, "fx_rate", lambda *args: None)
    metrics, _, availability = risk._distribution_metrics([_open_trade("missing-fx")], "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["var_95"]["value"] is None
    assert availability["distribution_metrics"]["reason"] == "missing_fx"


@pytest.mark.parametrize("rows,state,reason", [
    ([], "ok", None), (None, "unavailable", "positions_unavailable"),
])
def test_distribution_empty_and_unknown_positions(distribution_inputs, rows, state, reason):
    risk, _ = distribution_inputs
    metrics, corr, availability = risk._distribution_metrics(rows, "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["as_of"] is None
    assert metrics["var_95"] == {"value": None, "n": 0}
    assert corr == {"labels": [], "values": []}
    assert availability["distribution_metrics"] == {
        "state": state, "reason": reason, "checked_at": _DISTRIBUTION_CHECKED}


def test_distribution_unavailable_open_read_and_configured_benchmark(distribution_inputs, monkeypatch):
    from swingbot import config
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "QQQ")
    monkeypatch.setattr(TradeLog, "get_trades", lambda *args, **kwargs: None)
    monkeypatch.setattr(risk, "_money_metric", lambda closed: ({"value": None, "n": 0, "fx_missing_count": 0, "invalid_date_count": 0}, None))
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["benchmark_symbol"] == "QQQ"
    assert availability["distribution_metrics"]["reason"] == "positions_unavailable"


def test_distribution_availability_merges_without_mutating_cache(projection_client, projection_state, monkeypatch):
    from swingbot.admin.api_v1 import risk
    availability = {"distribution_metrics": {"state": "unavailable", "reason": "missing_fx",
                                             "checked_at": _DISTRIBUTION_CHECKED}}
    monkeypatch.setattr(risk, "_risk_metrics_and_correlation", lambda: ({}, {"labels": [], "values": []}, availability))
    body = projection_client.get("/api/v1/risk").get_json()
    assert body["availability"]["distribution_metrics"] == availability["distribution_metrics"]
    assert body["availability"]["positions"] == projection_state["availability"]["positions"]
    assert set(availability) == {"distribution_metrics"}
    assert "distribution_metrics" not in projection_state["availability"]


def test_distribution_uses_one_valuation_date(distribution_inputs, monkeypatch):
    from datetime import date
    from swingbot.core.marketdata import fx
    risk, _ = distribution_inputs
    calls = []

    def rate(quote, account, on):
        calls.append((quote, account, on))
        return 1.0

    monkeypatch.setattr(fx, "fx_rate", rate)
    rows = [_open_trade("a", ticker="AAA"), _open_trade("b", ticker="BBB")]
    metrics, _, availability = risk._distribution_metrics(rows, "QQQ", _DISTRIBUTION_CHECKED)
    assert calls == [("EUR", "EUR", date(2026, 10, 28))] * 2
    assert metrics["beta_spy"]["value"] == pytest.approx(1.0)
    assert metrics["beta_spy"]["n"] == 99
    assert availability["distribution_metrics"]["state"] == "ok"


def test_distribution_failed_open_read_preserves_closed_metrics(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs

    def trades(self, status=None, **kwargs):
        if status == "open":
            raise OSError("private positions diagnostic")
        return [_closed_trade("closed")]

    monkeypatch.setattr(TradeLog, "get_trades", trades)
    monkeypatch.setattr(risk, "_money_metric", lambda closed: ({"value": 0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 0}, None))
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["max_drawdown_r"]["n"] == 1
    assert metrics["max_drawdown_amount"]["n"] == 1
    assert availability["distribution_metrics"]["reason"] == "positions_unavailable"


@pytest.mark.parametrize("bad_frame", [
    pd.DataFrame(), pd.DataFrame({"Close": [100.0, float("nan")]}),
    pd.DataFrame({"Close": [100.0, 0.0]}), pd.DataFrame({"Open": [100.0]}),
])
def test_distribution_invalid_frames_are_unavailable(distribution_inputs, monkeypatch, bad_frame):
    risk, frame = distribution_inputs
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {"AAPL": bad_frame, "SPY": frame})
    metrics, _, availability = risk._distribution_metrics([_open_trade("bad")], "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["var_95"]["value"] is None
    assert availability["distribution_metrics"]["reason"] == "incomplete_bars"


def test_distribution_computation_failure_is_sanitized(distribution_inputs, monkeypatch):
    risk, _ = distribution_inputs
    monkeypatch.setattr(risk, "_market_values", unavailable_read)
    metrics, corr, availability = risk._distribution_metrics([_open_trade("bad")], "SPY", _DISTRIBUTION_CHECKED)
    assert metrics["var_95"]["value"] is None
    assert corr["labels"] == ["AAPL"]
    assert availability["distribution_metrics"]["reason"] == "market_data_unavailable"


def test_distribution_overflow_is_unavailable_and_json_safe(distribution_inputs, monkeypatch):
    import json

    risk, frame = distribution_inputs
    extreme = pd.DataFrame({"Close": [1.0, 1e200] * 50}, index=frame.index)
    monkeypatch.setattr(risk, "_risk_bars", lambda symbols: {"AAPL": extreme, "SPY": frame})
    metrics, corr, availability = risk._distribution_metrics(
        [_open_trade("overflow")], "SPY", _DISTRIBUTION_CHECKED)

    assert availability["distribution_metrics"]["state"] == "unavailable"
    assert availability["distribution_metrics"]["reason"] == "market_data_unavailable"
    assert all(metrics[name]["value"] is None for name in risk._DISTRIBUTION_KEYS)
    assert corr["labels"] == ["AAPL"]
    json.dumps({"metrics": metrics, "correlation": corr, "availability": availability}, allow_nan=False)


def _r_trade(trade_id, stamp, outcome):
    return {"id": trade_id, "ticker": "AAPL", "status": "closed", "direction": "bullish",
            "entry": 100.0, "stop_loss": 90.0, "exit_price": 100.0 + outcome * 10,
            "shares": 10, "opened_at": "2026-01-01T00:00:00Z", "closed_at": stamp}


@pytest.fixture
def isolated_eur_account(monkeypatch):
    from swingbot.core.marketdata import fx
    asked = []

    def rate(quote, account, on):
        asked.append((quote, account, on))
        return 0.5

    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: None if ticker == "NOFX" else "USD")
    monkeypatch.setattr(fx, "fx_rate", rate)
    return asked


def test_closed_projection_r_order_and_reconciled_exclusions(isolated_eur_account):
    from swingbot.admin.api_v1 import risk
    rows = [_r_trade("late", "2026-03-03T10:00:00Z", 1),
            _r_trade("first", "2026-03-01T10:00:00Z", -1),
            _r_trade("middle", "2026-03-02T10:00:00Z", -1),
            _r_trade("both_bad", None, float("nan")),
            _r_trade("bad_outcome", "2026-03-04", float("nan")),
            {**_r_trade("zero_risk", "2026-03-05", 1), "stop_loss": 100.0}]
    metrics, availability = risk._closed_metrics(rows, _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_r"] == {
        "value": 2.0, "n": 3, "excluded_count": 3,
        "invalid_date_count": 1, "invalid_outcome_count": 2}
    assert metrics["sharpe_r"]["n"] == 3
    assert metrics["sharpe_r"]["excluded_count"] == 3
    assert availability["drawdown_r"]["state"] == "partial"
    assert json.dumps(metrics, allow_nan=False)


@pytest.mark.parametrize("invalid", [{"exit_price": None}, {"legs": ["malformed"]}, {"direction": None}])
def test_closed_projection_missing_r_is_excluded(invalid, isolated_eur_account):
    from swingbot.admin.api_v1 import risk
    metrics, availability = risk._closed_metrics(
        [{**_r_trade("bad", "2026-03-01", 1), **invalid}], _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_r"] == {
        "value": None, "n": 0, "excluded_count": 1,
        "invalid_date_count": 0, "invalid_outcome_count": 1}
    assert availability["drawdown_r"]["state"] == "unavailable"


def test_closed_projection_money_date_filter_precedes_fx(isolated_eur_account):
    from datetime import date
    from swingbot.admin.api_v1 import risk
    rows = [_settled("bad_date", ticker="NOFX", pnl=-900, closed_at=None),
            _settled("loss", pnl=-100, closed_at="2026-08-04T20:00:00Z")]
    metrics, availability = risk._closed_metrics(rows, _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_amount"] == {
        "value": 50.0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 1}
    assert availability["drawdown_amount"]["state"] == "partial"
    assert isolated_eur_account == [("USD", "EUR", date(2026, 8, 4))]


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
def test_closed_projection_nonfinite_money_blanks_only_money(isolated_eur_account, amount):
    from swingbot.admin.api_v1 import risk
    rows = [_settled("nonfinite", pnl=amount, closed_at="2026-08-04T20:00:00Z")]
    metrics, availability = risk._closed_metrics(rows, _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_amount"]["value"] is None
    assert availability["drawdown_amount"]["reason"] == "money_conversion_unavailable"
    assert metrics["max_drawdown_r"]["n"] == 1
    assert availability["drawdown_r"]["state"] == "ok"
    assert json.dumps(metrics, allow_nan=False)


def test_closed_projection_empty_and_failed_read_differ(isolated_eur_account):
    from swingbot.admin.api_v1 import risk
    empty, empty_status = risk._closed_metrics([], _DISTRIBUTION_CHECKED)
    failed, failed_status = risk._closed_metrics(None, _DISTRIBUTION_CHECKED)
    assert empty["max_drawdown_r"]["value"] is None
    assert failed["max_drawdown_r"]["value"] is None
    assert empty_status["drawdown_r"]["state"] == "ok"
    assert empty_status["drawdown_amount"]["state"] == "ok"
    assert failed_status["drawdown_r"]["reason"] == "closed_trades_unavailable"
    assert failed_status["drawdown_amount"]["state"] == "unavailable"


def test_closed_projection_failed_closed_read_preserves_market(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs

    def trades(self, status=None, **kwargs):
        if status == "open":
            return [_open_trade("open")]
        raise OSError("private closed ledger diagnostic")

    monkeypatch.setattr(TradeLog, "get_trades", trades)
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["beta_spy"]["value"] == pytest.approx(1.0)
    assert availability["distribution_metrics"]["state"] == "ok"
    assert availability["drawdown_r"]["reason"] == "closed_trades_unavailable"


@pytest.mark.parametrize("missing,reason,fx_count", [
    ({"ticker": "NOFX", "realized_pnl_amount": -900.0}, "missing_fx", 1),
    ({"realized_pnl_amount": None}, "incomplete_money_outcomes", 0),
])
def test_closed_projection_money_partial_reasons(isolated_eur_account, missing, reason, fx_count):
    from swingbot.admin.api_v1 import risk
    rows = [_settled("known", pnl=-100, closed_at="2026-08-01"),
            {**_settled("missing", pnl=-100, closed_at="2026-08-02"), **missing}]
    metrics, availability = risk._closed_metrics(rows, _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_amount"] == {
        "value": 50.0, "n": 1, "fx_missing_count": fx_count, "invalid_date_count": 0}
    assert availability["drawdown_amount"]["state"] == "partial"
    assert availability["drawdown_amount"]["reason"] == reason
    assert availability["drawdown_r"]["state"] == "ok"


def test_closed_projection_conversion_failure_preserves_r_and_market(distribution_inputs, monkeypatch):
    from swingbot.admin.api_v1 import money
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, **kw:
                        [_open_trade("open")] if status == "open" else [_closed_trade("closed")])
    monkeypatch.setattr(money, "to_account_currency", unavailable_read)
    metrics, _, availability = risk._risk_metrics_and_correlation()
    assert metrics["max_drawdown_r"]["n"] == 1
    assert availability["drawdown_r"]["state"] == "ok"
    assert availability["drawdown_amount"]["reason"] == "money_conversion_unavailable"
    assert availability["distribution_metrics"]["state"] == "ok"
    assert metrics["beta_spy"]["value"] == pytest.approx(1.0)


@pytest.mark.parametrize("closed", [None, {}, "malformed"])
def test_closed_projection_invalid_history_is_unavailable(distribution_inputs, monkeypatch, closed):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    monkeypatch.setattr(TradeLog, "get_trades", lambda self, status=None, **kw:
                        [_open_trade("open")] if status == "open" else closed)
    _, _, availability = risk._risk_metrics_and_correlation()
    assert availability["drawdown_r"]["reason"] == "closed_trades_unavailable"
    assert availability["distribution_metrics"]["state"] == "ok"


def test_closed_projection_wrapper_preserves_same_currency_amounts(isolated_eur_account, monkeypatch):
    from swingbot.admin.api_v1 import risk
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    rows = [_settled("loss", pnl=-100, closed_at="2026-08-01")]
    assert risk._max_drawdown_amount(rows) == {
        "value": 100.0, "n": 1, "fx_missing_count": 0, "invalid_date_count": 0}
    assert isolated_eur_account == []


def test_closed_projection_nonfinite_cumulative_money_is_unavailable(isolated_eur_account, monkeypatch):
    from swingbot.admin.api_v1 import risk
    from swingbot.core.marketdata import fx
    monkeypatch.setattr(fx, "account_currency_code", lambda: "USD")
    rows = [_settled("a", pnl=-1e308, closed_at="2026-08-01"),
            _settled("b", pnl=-1e308, closed_at="2026-08-02")]
    metrics, availability = risk._closed_metrics(rows, _DISTRIBUTION_CHECKED)
    assert metrics["max_drawdown_amount"]["value"] is None
    assert availability["drawdown_amount"]["reason"] == "money_conversion_unavailable"
    assert availability["drawdown_r"]["state"] == "ok"
    assert json.dumps(metrics, allow_nan=False)


def test_closed_projection_history_retains_invalid_records_for_counting(distribution_inputs, monkeypatch):
    from swingbot.core.tracking.performance import TradeLog
    risk, _ = distribution_inputs
    rows = [_closed_trade("valid"), _open_trade("open"), "malformed"]
    monkeypatch.setattr(TradeLog, "get_trades", lambda *args, **kwargs: rows)
    selected = risk._closed_history()
    metrics, availability = risk._closed_metrics(selected, _DISTRIBUTION_CHECKED)
    assert selected == [rows[0], "malformed"]
    assert metrics["max_drawdown_r"]["invalid_date_count"] == 1
    assert availability["drawdown_r"]["state"] == "partial"
    assert "private diagnostic" not in str(availability)
