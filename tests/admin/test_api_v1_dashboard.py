"""NG10 — GET /api/v1/dashboard.

Spec 3 fixed the Dashboard header at nine metrics in two tiers, replacing
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

DASHBOARD = {
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
    # SR53. The five plan-lifecycle counts the Jinja dashboard's strip showed.
    # Not a tenth metric on the header -- the SPA renders them as filter links
    # into Trades, which is what the Jinja cards were.
    "lifecycle": dict,
    # SR58. The date-scope toggle and the realised figures it scopes.
    "scope": dict,
    "realized": dict,
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
    assert_error(client.get("/api/v1/dashboard"), "auth", 401)


def test_returns_exactly_the_nine_metrics(seed, logged_in):
    seed()
    assert_shape(logged_in.get("/api/v1/dashboard").get_json(), DASHBOARD)


def test_lifecycle_counts_cover_the_five_plan_statuses(seed, logged_in):
    """SR53. The strip's counts, which the SPA had as chips with no numbers.

    PENDING/ACTIVE/PARTIAL are all-time and CLOSED/CANCELLED count only today's
    — a lifetime CLOSED count only ever goes up and says nothing about the
    session. `_plan_rows` already scopes them that way; this projects rather
    than recomputes.
    """
    seed()
    lifecycle = logged_in.get("/api/v1/dashboard").get_json()["lifecycle"]

    assert set(lifecycle) == {"PENDING", "ACTIVE", "PARTIAL", "CLOSED", "CANCELLED"}
    assert all(isinstance(n, int) for n in lifecycle.values())


def test_relocated_metrics_are_absent(seed, logged_in):
    """Spec 3 moved these six to Analytics. assert_shape already rejects
    undeclared keys, but this names them so a future re-add fails loudly
    rather than as an anonymous 'undeclared key'."""
    seed()
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert not [k for k in RELOCATED if k in body]


def test_works_on_an_empty_store(seed, logged_in):
    """A fresh install has no trades. The Dashboard must render zeros and
    nulls rather than 500 -- it is the landing page."""
    seed()
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert body["open_trades"] == 0
    assert body["win_rate"] is None or isinstance(body["win_rate"], (int, float))


def test_equity_sparkline_is_numbers_not_svg(seed, logged_in):
    """Sub-project 3 owns how a sparkline looks; markup from the server
    would take that decision away from it."""
    seed()
    equity = logged_in.get("/api/v1/dashboard").get_json()["equity_30d"]
    assert_shape(equity, {"points": list, "change_pct": NULLABLE_NUMBER}, where="equity_30d")
    assert all(isinstance(p, (int, float)) for p in equity["points"])
    assert "svg" not in equity


def test_risk_used_is_reported_with_its_cap(seed, logged_in):
    """A heat percentage is meaningless without the cap it is measured
    against -- spec 3 defines this card as heat AS A FRACTION of the cap."""
    seed()
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert body["risk_cap_pct"] is not None


def test_open_trades_counts_open_positions(seed, logged_in):
    from tests.admin.test_api_v1_trades import _trade
    seed(trades=[
        _trade("aaaaaaaaaaaaaaaa", plan_id=None, status="open"),
        _trade("bbbbbbbbbbbbbbbb", plan_id=None, status="open"),
        _trade("cccccccccccccccc", plan_id=None, status="win"),
    ])
    assert logged_in.get("/api/v1/dashboard").get_json()["open_trades"] == 2


# ---------------------------------------------------------------------------
# SR4 — the rename itself
# ---------------------------------------------------------------------------

def test_the_old_cockpit_api_path_is_gone_not_aliased(logged_in):
    """/api/v1/cockpit is deleted, with no alias.

    The v1 API has exactly one consumer and it ships from the same build, so
    an alias would only preserve a name nothing can still be asking for. This
    test exists so the absence is deliberate rather than incidental: anything
    that quietly re-adds the old route has to delete this test to do it.
    """
    assert logged_in.get("/api/v1/cockpit").status_code == 404


def test_the_spa_still_serves_the_old_workspace_url():
    """`/cockpit` is NOT deleted the way the API path is.

    A bookmark or an open tab on the old workspace URL must not 404 at the
    server: Angular can only redirect it if index.html is served for it,
    which is why `cockpit` stays in `spa.WORKSPACES`. The assertion is on the
    URL map rather than on a response, because in dev the bundle is unbuilt
    and every SPA route answers 404 by design — that would make a response
    check unable to tell "not routed" from "not built".
    """
    from swingbot.admin import app as _app

    rules = {rule.rule for rule in _app.app.url_map.iter_rules()}
    assert "/cockpit" in rules
    assert "/dashboard" in rules


def test_the_jinja_dashboard_kept_its_own_url_under_jinja(logged_in):
    """SR4 moved it aside rather than letting the flag decide who owns
    `/dashboard`. Both UIs are live until NG57, and NG53 added a dedicated
    URL for this page precisely so enabling the SPA could not strand it.
    """
    assert logged_in.get("/jinja/dashboard").status_code == 200


# --------------------------------------------------------------- SR58

def _closed(trade_id, *, closed_at, amount, pct_entry=100.0, pct_exit=110.0,
            status="win"):
    """A closed trade with a realised amount and a derivable percentage."""
    return {
        "id": trade_id, "plan_id": None, "ticker": "AAPL",
        "strategy": "RSI Divergence", "horizon_key": "1m",
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": pct_entry, "stop_loss": 95.0, "take_profit": 120.0,
        "target2": None, "risk_reward_ratio": 1.8, "tier": "A",
        "badge": "VALIDATED", "quality_score": 72, "source": "strategy",
        "legs": [], "opened_at": "2026-08-01T10:00:00+00:00", "status": status,
        "closed_at": closed_at, "exit_price": pct_exit,
        "realized_pnl_amount": amount, "shares": 10, "position_value": 1000.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def _today_iso():
    """Today in Europe/Berlin, which is what `is_today_berlin` compares to."""
    from swingbot.admin.dashboard import is_today_berlin
    from datetime import datetime, timedelta, timezone as tz
    now = datetime.now(tz.utc)
    for delta in (0, 1, -1):
        candidate = (now + timedelta(hours=delta)).isoformat()
        if is_today_berlin(candidate):
            return candidate
    return now.isoformat()


def test_scope_defaults_to_active_and_is_echoed_back(seed, logged_in):
    seed()
    body = logged_in.get("/api/v1/dashboard").get_json()
    assert_shape(body["scope"], {"mode": str}, where="scope")
    assert body["scope"]["mode"] == "active"


def test_realized_block_is_shaped_even_with_no_trades(seed, logged_in):
    seed()
    realized = logged_in.get("/api/v1/dashboard").get_json()["realized"]
    assert_shape(realized, {
        "amount": NULLABLE_NUMBER, "pct": NULLABLE_NUMBER,
        "n": int, "wins": int, "losses": int,
    }, where="realized")
    # None, not 0.0: "nothing closed" and "closed flat" are different facts.
    assert realized["amount"] is None
    assert realized["n"] == 0


def test_today_scope_counts_only_todays_closes(seed, logged_in):
    seed(trades=[
        _closed("a" * 16, closed_at=_today_iso(), amount=120.0),
        _closed("b" * 16, closed_at="2026-01-05T15:00:00+00:00", amount=999.0),
    ])
    realized = logged_in.get("/api/v1/dashboard?mode=today").get_json()["realized"]
    assert realized["n"] == 1
    assert realized["amount"] == 120.0


def test_all_scope_counts_every_close(seed, logged_in):
    seed(trades=[
        _closed("c" * 16, closed_at=_today_iso(), amount=120.0),
        _closed("d" * 16, closed_at="2026-01-05T15:00:00+00:00", amount=80.0),
    ])
    realized = logged_in.get("/api/v1/dashboard?mode=all").get_json()["realized"]
    assert realized["n"] == 2
    assert realized["amount"] == 200.0


def test_active_and_today_agree_on_realized(seed, logged_in):
    """Open trades have no realised P&L, so the only thing separating the two
    modes cannot show up here. Asserted so a later change does not invent a
    difference -- the same call `2026-08-07-v9` made for Trade History."""
    seed(trades=[
        _closed("e" * 16, closed_at=_today_iso(), amount=50.0),
        _closed("f" * 16, closed_at="2026-01-05T15:00:00+00:00", amount=70.0),
    ])
    active = logged_in.get("/api/v1/dashboard?mode=active").get_json()["realized"]
    today = logged_in.get("/api/v1/dashboard?mode=today").get_json()["realized"]
    assert active == today


def test_realized_splits_wins_and_losses(seed, logged_in):
    seed(trades=[
        _closed("g" * 16, closed_at=_today_iso(), amount=50.0, status="win"),
        _closed("h" * 16, closed_at=_today_iso(), amount=-20.0, status="loss",
                pct_exit=90.0),
    ])
    realized = logged_in.get("/api/v1/dashboard?mode=today").get_json()["realized"]
    assert realized["wins"] == 1
    assert realized["losses"] == 1
    assert realized["amount"] == 30.0


def test_unknown_mode_is_a_400_not_a_silent_fallback(seed, logged_in):
    seed()
    assert_error(logged_in.get("/api/v1/dashboard?mode=last-week"), "invalid", 400)


def test_health_carries_the_versions_and_the_market_session(logged_in):
    """SR58. `/health` is where the shell reads its footer from.

    Auth-guarded like every other v1 route -- `test_api_v1_session.py` pins
    the 401, and this task does not change it.
    """
    body = logged_in.get("/api/v1/health").get_json()
    assert_shape(body, {"ok": bool, "versions": dict, "market_active": bool})
    assert_shape(body["versions"], {
        "ui": str, "bot": str, "last_updated": (str, type(None)),
    }, where="versions")
