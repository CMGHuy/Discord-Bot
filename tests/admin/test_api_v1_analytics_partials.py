"""v142: GET /api/v1/analytics/partials -- scoped, echoed, plans-only."""
import pytest

from swingbot.core.planning.plan_engine import plan_to_dict
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_partials import _book
from tests.analytics.test_partials import _trade as _partial_plan
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_URL = "/api/v1/analytics/partials"


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("plans", [plan_to_dict(plan) for plan in plans])
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _manual_trade():
    """D's linked trade: the admin close realised the runner at 112.5 (2.5R)."""
    trade = _trade("dddddddddddddddd", plan_id="D", status="closed")
    trade["exit_price"] = 112.5
    return trade


def test_requires_auth(client):
    assert_error(client.get(_URL), "auth", 401)


def test_shape_and_echo(seed, logged_in):
    seed(plans=_book(), trades=[_manual_trade()])
    body = logged_in.get(_URL).get_json()
    assert set(body) == {"kpis", "funnel", "runner_endings", "counterfactuals", "holds",
                         "breakdowns", "thin_n", "population", "scope", "n"}
    assert body["n"] == 8 and body["scope"]["ledger"] == "main"
    assert [row["n"] for row in body["funnel"]] == [8, 6, 5, 1]
    assert body["counterfactuals"]["runner_r_unavailable"] == 0     # D priced from its trade
    assert body["kpis"]["beat_all_out_n"] == 5
    assert set(body["breakdowns"]) == {"strategy", "horizon", "side", "month"}


def test_the_runner_endings_block(seed, logged_in):
    seed(plans=_book(), trades=[_manual_trade()])
    body = logged_in.get(_URL).get_json()
    block = body["runner_endings"]
    assert set(block) == {"n", "decidable", "cards", "rows", "odds", "excluded"}
    assert (block["n"], block["decidable"]) == (4, 3)
    assert block["excluded"]["manual_close"] == 1 and block["excluded"]["no_tp2"] == 1
    assert [row["ending"] for row in block["rows"]] == ["tp2", "trail", "floor", "other", "giveback"]
    assert [bar["level"] for bar in block["odds"]] == [25, 50, 75]
    assert body["counterfactuals"]["giveback_excluded"] == 2


def test_without_the_linked_trade_the_manual_runner_is_counted_unpriced(seed, logged_in):
    seed(plans=_book())
    body = logged_in.get(_URL).get_json()
    assert body["counterfactuals"]["runner_r_unavailable"] == 1


def test_scope_filters_on_fill_date_and_plan_fields(seed, logged_in):
    seed(plans=_book())
    assert logged_in.get(f"{_URL}?from=2026-10-02").get_json()["n"] == 0
    assert logged_in.get(f"{_URL}?strategy=MACD").get_json()["n"] == 2
    assert logged_in.get(f"{_URL}?direction=bearish").get_json()["n"] == 1


def test_an_empty_scope_answers_with_zeros(seed, logged_in):
    seed()
    body = logged_in.get(_URL).get_json()
    assert body["n"] == 0 and [row["n"] for row in body["funnel"]] == [0, 0, 0, 0]
    assert body["kpis"]["tp1_rate"] is None


def test_rejects_non_scope_parameters(logged_in):
    assert_error(logged_in.get(f"{_URL}?dim=strategy"), "invalid", 400)


def test_a_malformed_runner_path_leaves_the_endpoint_answering(seed, logged_in):
    seed(plans=[_partial_plan("A", reason="tp1_runner_tp2", runner_r=4.0,
                              path={"mfe_r": "high", "ladder": []}),
                _partial_plan("B", reason="tp1_runner_trail", runner_r=3.0,
                              path={"mfe_r": None, "ladder": {}})])
    response = logged_in.get(_URL)
    assert response.status_code == 200
    block = response.get_json()["runner_endings"]
    assert (block["n"], block["decidable"], block["excluded"]["unpathed"]) == (2, 0, 2)
