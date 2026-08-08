"""NG10 — GET /api/v1/cockpit.

Spec 3 fixed the Cockpit header at nine metrics in two tiers, replacing
fourteen equal-weight cards. This endpoint returns exactly those nine and
nothing else -- the six that moved to Analytics (wins, losses, avg realised
P&L, best trade, worst trade, avg holding period) are NOT here, and
`test_relocated_metrics_are_absent` is what stops them drifting back.

  primary   account_balance · open_pnl_pct · risk_used_pct
  chips     open_trades · avg_confidence · win_rate · expectancy ·
            equity_30d (sparkline series) · position_premium

Everything is projected from `dashboard`'s existing builders and
`_collect_portfolio_state`. No metric is computed here: spec 3's constraint
is "UI renders, analytics computes", and a second definition of win rate
would drift from the one the Jinja UI shows.

The equity sparkline ships as NUMBERS, not the `<svg>` string
`build_equity_curve` hands Jinja. Sub-project 3 owns how a sparkline looks,
and a server that ships markup has taken that decision away from it.
"""
import json

import pytest

from tests.admin.api_v1_contract import NULLABLE_NUMBER, assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}

COCKPIT = {
    "account_balance": NULLABLE_NUMBER,
    "open_pnl_pct": NULLABLE_NUMBER,
    "risk_used_pct": NULLABLE_NUMBER,
    "risk_cap_pct": NULLABLE_NUMBER,
    "open_trades": int,
    "avg_confidence": NULLABLE_NUMBER,
    "win_rate": NULLABLE_NUMBER,
    "expectancy_r": NULLABLE_NUMBER,
    "equity_30d": dict,
    "position_premium": dict,
}

RELOCATED = [
    "wins", "losses", "avg_realized_pct", "best_trade_pct",
    "worst_trade_pct", "avg_holding_days",
]


@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        (tmp_path / "plans.json").write_text("[]", encoding="utf-8")
        (tmp_path / "trades.json").write_text(json.dumps(list(trades)), encoding="utf-8")
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def test_requires_auth(client):
    assert_error(client.get("/api/v1/cockpit"), "auth", 401)


def test_returns_exactly_the_nine_metrics(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/cockpit").get_json(), COCKPIT)


def test_relocated_metrics_are_absent(seed, logged_in):
    """Spec 3 moved these six to Analytics. assert_shape already rejects
    undeclared keys, but this names them so a future re-add fails loudly
    rather than as an anonymous 'undeclared key'."""
    seed()
    body = logged_in.get("/api/v1/cockpit").get_json()
    assert not [k for k in RELOCATED if k in body]


def test_works_on_an_empty_store(seed, logged_in):
    """A fresh install has no trades. The Cockpit must render zeros and
    nulls rather than 500 -- it is the landing page."""
    seed()
    body = logged_in.get("/api/v1/cockpit").get_json()
    assert body["open_trades"] == 0
    assert body["win_rate"] is None or isinstance(body["win_rate"], (int, float))


def test_equity_sparkline_is_numbers_not_svg(seed, logged_in):
    """Sub-project 3 owns how a sparkline looks; markup from the server
    would take that decision away from it."""
    seed()
    equity = logged_in.get("/api/v1/cockpit").get_json()["equity_30d"]
    assert_shape(equity, {"points": list, "change_pct": NULLABLE_NUMBER}, where="equity_30d")
    assert all(isinstance(p, (int, float)) for p in equity["points"])
    assert "svg" not in equity


def test_risk_used_is_reported_with_its_cap(seed, logged_in):
    """A heat percentage is meaningless without the cap it is measured
    against -- spec 3 defines this card as heat AS A FRACTION of the cap."""
    seed()
    body = logged_in.get("/api/v1/cockpit").get_json()
    assert body["risk_cap_pct"] is not None


def test_open_trades_counts_open_positions(seed, logged_in):
    from tests.admin.test_api_v1_trades import _trade
    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="open"),
        _trade("bbbbbbbbbbbbbbbb", plan_id=None, status="open"),
        _trade("cccccccccccccccc", plan_id=None, status="win"),
    ])
    assert logged_in.get("/api/v1/cockpit").get_json()["open_trades"] == 2
