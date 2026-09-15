"""v86 Task C8 -- the cohort verdict on the trade detail API payload.

`sample_trade`/`client` in the brief's own test skeleton do not exist
anywhere in this codebase (grep confirms zero hits) -- the established
pattern for this exact endpoint is `tests/admin/test_api_v1_trade_detail.py`:
a `seed(plans=[...], trades=[...])` fixture that writes plans.json/
trades.json, and a `logged_in` client authenticated through POST
/api/v1/session. `_plan`/`_trade` are the fixed-dict builders from
`tests.admin.test_api_v1_trades`, imported the same way
test_api_v1_trade_detail.py does; neither takes a `cohort_label`/
`cohort_stats` kwarg (same as `badge`), so a specific value is assigned onto
the built dict afterward.

Both cases route through the plan-id path (`_row_from_plan` /
`GET /api/v1/trades/<plan_id>`), since `cohort_label`/`cohort_stats` are v2
plan fields stamped by C3/C4 -- there is no cohort-bearing legacy fixture
builder to test the `_row_from_trade` path against, and that path's default
is covered by the shared TRADE_ROW contract test in test_api_v1_trades.py
(every seeded fixture there omits cohort_label/cohort_stats entirely and
still gets a typed `str`/`dict` back).
"""
import json

import pytest

from tests.admin.test_api_v1_trades import _plan

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "55555555-5555-4555-8555-555555555555"


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(plans=(), trades=()):
        (tmp_path / "plans.json").write_text(json.dumps(list(plans)), encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_trade_detail_exposes_the_cohort_verdict(seed, logged_in):
    plan = _plan(_PLAN_ID)
    plan["cohort_label"] = "COHORT_POOR"
    plan["cohort_stats"] = {
        "regime2_state": "bear_volatile", "win_rate": 41.2, "expectancy_r": -0.38,
        "n_live": 100, "n_backtest": 500, "run_date": "2026-09-14",
    }
    seed(plans=[plan])

    body = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert body["cohort_label"] == "COHORT_POOR"
    assert body["cohort_stats"]["run_date"] == "2026-09-14"
    assert body["cohort_stats"]["win_rate"] == 41.2


def test_a_trade_predating_v86_reports_unknown_not_null(seed, logged_in):
    plan = _plan(_PLAN_ID)
    # Neither key present -- exactly what a plan written before v86 looks
    # like on disk; _plan()'s own fixture never sets them.
    assert "cohort_label" not in plan and "cohort_stats" not in plan
    seed(plans=[plan])

    body = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert body["cohort_label"] == "COHORT_UNKNOWN"
    assert body["cohort_stats"] == {}


def test_an_explicitly_null_cohort_label_also_reports_unknown(seed, logged_in):
    """scan_run.py stamps `cohort_label=None` (not an absent key) when the v2
    plan lookup itself came back None -- `plan.get(...) or default` must
    catch that path too, not just a missing key."""
    plan = _plan(_PLAN_ID)
    plan["cohort_label"] = None
    plan["cohort_stats"] = None
    seed(plans=[plan])

    body = logged_in.get(f"/api/v1/trades/{_PLAN_ID}").get_json()
    assert body["cohort_label"] == "COHORT_UNKNOWN"
    assert body["cohort_stats"] == {}
