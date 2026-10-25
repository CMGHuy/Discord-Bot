"""GET /api/v1/cancel-precision (v188): auth, params, the empty book, a scored
plan, the memo, and the price source."""
import pytest

from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict, record_transition
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_store_records import FakePlansRepo

URL = "/api/v1/cancel-precision"
_LOGIN = {"username": "admin", "password": "admin"}
_PAYLOAD = {"generated_at": str, "data_as_of": NULLABLE_STR, "caption": str,
            "risk_cap_label": str, "tp1_note": str, "small_n_threshold": int,
            "window": dict, "rule_changes": list, "out_of_scope": dict, "headline": dict,
            "baseline": dict, "cards": dict, "splits": dict, "rows": list}
FLAT = (100.0, 100.5, 99.5, 100.0)
STOP_HIT = (100.0, 101.0, 94.0, 95.0)


def _cancelled_dict(plan_id="p1"):
    plan = _plan(plan_id=plan_id, entry_type="stop_entry", trigger_price=105.0,
                 stop_loss=95.0, tp1=120.0, horizon_key="2w", stop_ceiling_pct=2.0)
    record_transition(plan, PlanStatus.CANCELLED, reason="invalidated",
                      at="2026-08-03T15:00:00+00:00")
    return plan_to_dict(plan)


@pytest.fixture
def module(client):
    # `client` first: it loads swingbot.admin.app, which registers the endpoints.
    from swingbot.admin.api_v1 import cancel_precision as mod
    mod.reset_memo()
    yield mod
    mod.reset_memo()


@pytest.fixture
def repo(monkeypatch):
    fake = FakePlansRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: fake)
    return fake


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_an_unknown_parameter_is_a_400(logged_in, module, repo):
    assert_error(logged_in.get(URL + "?reason=risk_cap"), "invalid", 400)


def test_an_empty_book_is_a_200_with_n_zero(logged_in, module, repo, monkeypatch):
    """Review Focus 4."""
    monkeypatch.setattr(module, "_bar_loader", lambda _t: None)
    resp = logged_in.get(URL)
    assert resp.status_code == 200
    body = resp.get_json()
    assert_shape(body, _PAYLOAD)
    head = body["headline"]["all"]
    assert (head["n"], head["precision"], head["precision_ci"], head["small_n"]) == \
        (0, None, None, True)
    assert body["rows"] == [] and body["data_as_of"] is None


def test_a_cancelled_plan_is_scored(logged_in, module, repo, monkeypatch):
    repo.records["p1"] = _cancelled_dict()
    frame = make_ohlcv([FLAT, FLAT, FLAT, (104, 106, 104, 105), STOP_HIT] + [FLAT] * 9,
                       start="2026-07-30")
    monkeypatch.setattr(module, "_bar_loader", lambda _t: frame)
    body = logged_in.get(URL).get_json()
    assert body["headline"]["all"]["counts"]["right"] == 1
    assert [(r["plan_id"], r["outcome"]) for r in body["rows"]] == [("p1", "right")]
    assert body["caption"] == "Hypothetical replay, before commissions, slippage and tax"


def test_the_memo_recomputes_only_on_a_plan_write(logged_in, module, repo, monkeypatch):
    calls = []
    monkeypatch.setattr(module, "_load_plans", lambda: calls.append(1) or [])
    monkeypatch.setattr(module, "_bar_loader", lambda _t: None)
    logged_in.get(URL)
    logged_in.get(URL)
    assert len(calls) == 1
    repo.records["p1"] = _cancelled_dict()          # FakePlansRepo.version() moves
    logged_in.get(URL)
    assert len(calls) == 2


def test_the_memo_key_carries_the_utc_hour(module, repo):
    version, hour = module._memo_key()
    assert version == repo.version()
    assert len(hour) == 13 and hour[10] == "T"      # "YYYY-MM-DDTHH"


def test_spot_metals_have_no_bars(module, monkeypatch):
    from swingbot.core.marketdata import daily_delta
    monkeypatch.setattr(daily_delta, "read_daily",
                        lambda _t: pytest.fail("a spot metal must never be read"))
    assert module._bar_loader("XAUUSD") is None


def test_the_price_source_is_read_daily(module, monkeypatch):
    from swingbot.core.marketdata import daily_delta
    sentinel = make_ohlcv([FLAT])
    monkeypatch.setattr(daily_delta, "read_daily", lambda ticker: sentinel)
    assert module._bar_loader("AAPL") is sentinel


def test_load_plans_reads_the_plan_store(module, repo):
    repo.records["p1"] = _cancelled_dict()
    assert [r["plan_id"] for r in module._load_plans()] == ["p1"]
