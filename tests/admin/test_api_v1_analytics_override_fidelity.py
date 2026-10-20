"""v173 §5: GET /api/v1/analytics/override-fidelity -- computed on request,
the verdict read from preregistration_verdicts and never evaluated."""
import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_io as oio
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.analytics import runner_path as rp
from tests.admin.api_v1_contract import assert_error
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/override-fidelity"
PAYLOAD_KEYS = {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
RECORD = {"ledger_id": "v173-override-fidelity", "verdict": "COST", "recorded_on": "2027-03-01",
          "n": 31, "weeks": 12, "mean_delta_r": -0.25, "mean_delta_r_gross": -0.23,
          "ci": [-0.4, -0.1], "sum_delta_r": -7.75, "sum_delta_usd": -1550.0,
          "bar_close_n": 2, "excluded_share": 0.0,
          "engine_flags": {"stall_exit_enabled": False, "runner_structure_exit": "off"},
          "rows": []}
SHARES = 10          # dollar risk = 10 x |100 - 95| = 50


def _boom(*_args, **_kwargs):
    raise AssertionError("the API never evaluates and never writes the verdict")


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def api(admin_app, monkeypatch):
    """One stamped individual override (a), one bulk-clear close (b), no DB,
    no stored verdict. The analytics module is imported here, after
    admin_app's reloads; each evaluating or writing call raises."""
    import swingbot.admin.api_v1.analytics as analytics_api

    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    plans = [plan(plan_id="a", ticker="AAA"),
             plan(plan_id="b", ticker="BBB", reason="manual_bulk",
                  close_at="2026-10-08T18:00:00+00:00")]
    monkeypatch.setattr(analytics_api, "_override_inputs",
                        lambda: (plans, {"a": {"id": "t-a", "plan_id": "a", "shares": SHARES}}))
    monkeypatch.setattr(analytics_api, "_override_verdict", lambda: None)
    monkeypatch.setattr(rp, "cached_daily_bars", lambda ticker: frame({19: STOP_BAR}))
    monkeypatch.setattr(of, "latest_completed_session", lambda now: LAST_DAY)
    for module, name in ((ov, "evaluate_verdict"), (ov, "verdict_record"),
                         (oio, "run_daily_check")):
        monkeypatch.setattr(module, name, _boom)
    return analytics_api


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def _assert_header_and_rows(body):
    assert set(body) == PAYLOAD_KEYS
    assert (body["asof"], body["currency_symbol"]) == ("2026-10-19", "$")
    assert body["engine_flags"] == {"stall_exit_enabled": False, "runner_structure_exit": "off"}
    assert [r["plan_id"] for r in body["rows"]] == ["b", "a"]        # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS
    assert all(set(r) == ROW_KEYS for r in body["rows"])
    by_id = {r["plan_id"]: r for r in body["rows"]}
    assert (by_id["b"]["bulk"], by_id["a"]["bulk"]) == (True, False)


def _assert_bulk_excluded_summary(summary):
    assert (summary["bulk_n"], summary["bulk_dates"]) == (1, {"2026-10-08": 1})
    assert summary["counted_n"] == 1                                  # bulk shown, never summed
    assert sum(summary["n_by_status"].values()) == 1                  # eligible rows only
    assert "sum_delta_r_gross" in summary


def _assert_waiting_verdict(verdict):
    assert set(verdict) == VERDICT_KEYS
    assert (verdict["state"], verdict["recorded"], verdict["recorded_on"]) == ("WAITING", False, None)
    assert (verdict["mean_delta_r"], verdict["ci"], verdict["sum_delta_r"]) == (None, None, None)
    assert verdict["waiting_on"] == ["count", "weeks"]                # 1 row, 1 week
    assert verdict["bar_close_n"] == 0                                # a's stamp is a quote


def test_shape_and_the_bulk_exclusion(api, logged_in):
    resp = logged_in.get(_URL)
    assert resp.status_code == 200
    body = resp.get_json()
    _assert_header_and_rows(body)
    _assert_bulk_excluded_summary(body["summary"])
    _assert_waiting_verdict(body["verdict"])


def test_dollars_sit_beside_every_r_figure(api, logged_in):
    rows = {r["plan_id"]: r for r in logged_in.get(_URL).get_json()["rows"]}
    a = rows["a"]
    assert a["status"] == "resolved"
    for key in ("actual", "engine", "delta"):
        assert a[f"{key}_usd"] == pytest.approx(a[f"{key}_r"] * 50, abs=0.01)
    b = rows["b"]                                                     # no linked trade
    assert (b["actual_usd"], b["engine_usd"], b["delta_usd"]) == (None, None, None)


def test_the_stored_verdict_is_returned_as_stored(api, logged_in, monkeypatch):
    seen = []
    monkeypatch.setattr(api, "_override_verdict", lambda: seen.append(1) or RECORD)
    verdict = logged_in.get(_URL).get_json()["verdict"]
    assert seen == [1]
    assert (verdict["state"], verdict["recorded"], verdict["recorded_on"]) == (
        "COST", True, "2027-03-01")
    assert (verdict["n"], verdict["weeks"]) == (31, 12)               # the recorded figures
    assert (verdict["mean_delta_r"], verdict["mean_delta_r_gross"], verdict["ci"]) == (
        -0.25, -0.23, [-0.4, -0.1])
    assert (verdict["sum_delta_r"], verdict["sum_delta_usd"], verdict["bar_close_n"]) == (
        -7.75, -1550.0, 2)
    assert (verdict["open_n"], verdict["evaluable"]) == (0, False)    # live fields stay live
    assert verdict["waiting_on"] == ["count", "weeks"]


def test_build_report_gets_the_stored_record_and_nothing_else(api, logged_in, monkeypatch):
    calls = []

    def fake(plans, trades, bars_fn, asof, recorded, currency_symbol):
        calls.append((len(plans), asof, recorded, currency_symbol))
        return {"rows": [], "summary": {}, "verdict": {}, "engine_flags": {}, "asof": "",
                "currency_symbol": currency_symbol}

    monkeypatch.setattr(ov, "build_report", fake)
    monkeypatch.setattr(api, "_override_verdict", lambda: RECORD)
    assert logged_in.get(_URL).status_code == 200
    assert calls == [(2, LAST_DAY, RECORD, "$")]


def test_the_seams_delegate_to_override_io(admin_app, monkeypatch):
    import swingbot.admin.api_v1.analytics as analytics_api

    monkeypatch.setattr(oio, "load_inputs", lambda: (["plan-a"], {"a": {"id": "t1"}}))
    monkeypatch.setattr(oio, "stored_verdict", lambda repo=None: RECORD)
    assert analytics_api._override_inputs() == (["plan-a"], {"a": {"id": "t1"}})
    assert analytics_api._override_verdict() is RECORD
