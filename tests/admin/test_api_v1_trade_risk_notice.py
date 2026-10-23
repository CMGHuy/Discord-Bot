"""V183-14: the paper record keeps the alert's notice snapshot, and the plan
page API words it with the same function as Discord full, simple, email and push."""
import ast
import pathlib

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade
from tests.presentation.test_risk_notice_lines import LINES, SNAP
from tests.scanning.test_embeds_v3 import _isolated_scan_snapshots  # noqa: F401
from tests.scanning.test_short_alert_parity import _noticed_item, _renderings, _setup  # noqa: F401
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}
_PLAN_ID = "66666666-6666-4666-8666-666666666666"
_TRADE_ID = "cccccccccccccccc"
STAMP = {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}
REPO = pathlib.Path(__file__).resolve().parents[2]
SHORT_PLAN = {**_plan(_PLAN_ID), "direction": "bearish", "trigger_price": 100.0, "entry_price": None,
              "stop_loss": 102.0, "tp1": 96.0, "tp2": 92.0}
CUT_LINE = "Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk"


@pytest.fixture(autouse=True)
def _account(monkeypatch):
    monkeypatch.setattr(config, "MAX_POSITION_VALUE_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "MAX_RISK_AMOUNT_ABSOLUTE", 0.0)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


@pytest.fixture
def seed(admin_app):
    def _seed(plans=(), trades=()):
        seed_store("account", {"balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 100.0,
                               "sizing_mode": "risk_pct", "balance_history": []})
        seed_store("plans", list(plans))
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _detail(client, row_id):
    return client.get(f"/api/v1/trades/{row_id}").get_json()["detail"]


# --- the paper record ----------------------------------------------------------

def _log(risk_notice, direction="bearish"):
    plan_id = f"p-rn-{direction}"   # one plan id per record: seed() never truncates trades
    log = TradeLog()
    log.log_trade(ticker="TSLA", strategy="Bear Flag", horizon_key="4w", direction=direction,
                  confidence_level=3, confidence_label="Medium", entry=100.0,
                  stop_loss=102.0 if direction == "bearish" else 98.0,
                  take_profit=96.0 if direction == "bearish" else 104.0,
                  plan_id=plan_id, risk_notice=risk_notice)
    return log.trade_for_plan(plan_id)


def test_log_trade_copies_the_snapshot_and_a_long_record_has_no_key(seed):
    seed()
    assert _log(SNAP)["risk_notice"] == SNAP
    seed()
    assert "risk_notice" not in _log(None, direction="bullish")


@pytest.mark.parametrize("path", [
    "swingbot/core/scanning/scan_run.py", "swingbot/core/scanning/short_run.py",
    "swingbot/core/scanning/strategy_pass.py", "swingbot/core/planning/plan_manager.py",
])
def test_every_log_trade_call_site_passes_risk_notice(path):
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "log_trade"]
    assert calls, path
    for call in calls:
        assert "risk_notice" in {kw.arg for kw in call.keywords}, (path, call.lineno)


# --- the plan-page API ---------------------------------------------------------

def test_plan_page_lines_come_from_the_plan_snapshot(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "risk_notice": SNAP}])
    assert _detail(logged_in, _PLAN_ID)["risk_notice_lines"] == LINES


def test_a_trade_record_snapshot_is_used_when_the_plan_doc_has_none(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "status": "ACTIVE"}],
         trades=[{**_trade(_TRADE_ID, plan_id=_PLAN_ID), "direction": "bearish", "risk_notice": SNAP}])
    assert _detail(logged_in, _PLAN_ID)["risk_notice_lines"] == LINES
    seed(trades=[{**_trade(_TRADE_ID), "direction": "bearish", "risk_notice": SNAP}])
    assert _detail(logged_in, _TRADE_ID)["risk_notice_lines"] == LINES


def test_pre_v183_and_long_rows_carry_none(seed, logged_in):
    seed(plans=[_plan(_PLAN_ID)], trades=[_trade(_TRADE_ID)])
    for row_id in (_PLAN_ID, _TRADE_ID):
        detail = _detail(logged_in, row_id)
        assert detail["risk_notice_lines"] is None and detail["gap_sizing"] is None


def test_gap_sizing_block_for_a_pending_gap_cut_short(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "gap_sizing": STAMP}])
    assert _detail(logged_in, _PLAN_ID)["gap_sizing"] == {
        "rule": "gap_p99", "up_gap_p99_pct": 4.0, "shares": 25.0, "risk_amount": 50.0,
        "gap_risk_amount": 100.0, "gap_sized": True, "line": CUT_LINE}


def test_gap_sizing_block_reads_the_paper_books_shares(seed, logged_in):
    trade = {**_trade(_TRADE_ID), "direction": "bearish", "entry": 100.0, "stop_loss": 102.0,
             "shares": 20, "gap_sizing": STAMP}
    seed(trades=[trade])
    block = _detail(logged_in, _TRADE_ID)["gap_sizing"]
    assert (block["shares"], block["risk_amount"], block["gap_risk_amount"]) == (20, 40.0, 80.0)


def test_a_rule_stop_short_shows_no_gap_line(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "gap_sizing": {**STAMP, "rule": "stop"}}])
    block = _detail(logged_in, _PLAN_ID)["gap_sizing"]
    assert (block["rule"], block["line"], block["gap_sized"]) == ("stop", None, False)


# --- five-channel parity (spec "One channel-parity test") ---------------------------

def test_discord_full_simple_email_push_and_the_plan_page_carry_the_same_notice(seed, logged_in):
    seed(plans=[{**SHORT_PLAN, "risk_notice": SNAP}])
    page = _detail(logged_in, _PLAN_ID)["risk_notice_lines"]
    assert page == LINES
    renderings = _renderings(_noticed_item())          # discord, simple, email/push
    for name, text in renderings.items():
        for line in page:
            assert line in text, (name, line)
