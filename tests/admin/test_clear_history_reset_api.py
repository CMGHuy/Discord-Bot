"""v189 A6: POST /api/v1/trades/clear-history is the archived full reset.

200 names the archive, the throttle and the kill switch; 409 while the kill
switch is tripped unless forced; 500 when the archive cannot be written.
"""
import pytest

from swingbot.core.db.repositories.killswitch import killswitch_repo
from swingbot.core.tracking import account_reset
from tests.admin.api_v1_contract import assert_error
from tests.admin.test_api_v1_trade_commands import _no_live_quote, logged_in, seed  # noqa: F401  fixtures
from tests.admin.test_api_v1_trades import _trade
from tests.store_seed import seed_store

URL = "/api/v1/trades/clear-history"
KEYS = {"removed", "removed_plans", "archive", "throttle", "kill_switch", "notice"}


@pytest.fixture(autouse=True)
def _switch_off_by_default(admin_app, monkeypatch):
    """After admin_app's module reloads: a .env KILLSWITCH_DEFAULT_ON must not leak in."""
    monkeypatch.setattr("swingbot.config.KILLSWITCH_DEFAULT_ON", False)


def _book(seed):
    seed_store("account", {"base_balance": 10_000.0})
    seed(trades=[_trade("aaaaaaaaaaaaaaaa", status="open"),
                 _trade("cccccccccccccccc", status="win")])


def _statuses(client):
    return sorted(t["status"] for t in client.get("/api/v1/trades").get_json()["items"])


def test_the_reset_answers_with_its_archive_throttle_and_notice(seed, logged_in):
    _book(seed)
    r = logged_in.post(URL)
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == KEYS
    assert (body["removed"], body["removed_plans"]) == (1, 0)
    assert body["archive"].startswith("account-reset-") and body["archive"].endswith("Z.json")
    assert "/" not in body["archive"] and "\\" not in body["archive"]      # a name, never a path
    assert (account_reset.archive_dir() / body["archive"]).exists()
    assert body["throttle"] == {"multiplier": 1.0, "paused": False}
    assert body["kill_switch"] is False
    assert body["notice"].startswith("Account reset: removed 1 closed trade(s) and 0 finished plan(s).")
    assert f"\nArchive: {body['archive']}\n" in body["notice"]
    assert _statuses(logged_in) == ["ACTIVE"]


def test_refused_while_the_kill_switch_is_tripped(seed, logged_in):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    r = logged_in.post(URL)
    assert_error(r, "kill_switch_tripped", 409)
    assert r.get_json()["error"]["message"] == account_reset.REFUSED_TEXT
    assert _statuses(logged_in) == ["ACTIVE", "CLOSED"]


@pytest.mark.parametrize("send", [
    lambda c: c.post(f"{URL}?force=true"),
    lambda c: c.post(f"{URL}?force=1"),
    lambda c: c.post(URL, json={"force": True}),
], ids=["query-true", "query-1", "json-true"])
def test_force_resets_past_the_kill_switch_and_leaves_it_on(seed, logged_in, send):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    r = send(logged_in)
    assert r.status_code == 200
    assert r.get_json()["kill_switch"] is True
    assert killswitch_repo().state()["on"] is True
    assert _statuses(logged_in) == ["ACTIVE"]


@pytest.mark.parametrize("send", [
    lambda c: c.post(f"{URL}?force=false"),
    lambda c: c.post(URL, json={"force": "yes"}),
    lambda c: c.post(URL, json=["force"]),
    lambda c: c.post(URL, data="force", content_type="text/plain"),
], ids=["query-false", "json-string", "json-list", "plain-text"])
def test_anything_but_an_explicit_true_is_not_force(seed, logged_in, send):
    _book(seed)
    killswitch_repo().engage("drawdown >20%")
    assert_error(send(logged_in), "kill_switch_tripped", 409)


def test_a_failed_archive_is_a_500_that_says_nothing_was_deleted(seed, logged_in, monkeypatch):
    _book(seed)
    text = ("Reset aborted: the archive account-reset-x.json could not be written "
            "(disk full). Nothing was deleted.")

    def failing(*, force=False, now=None):
        raise account_reset.ArchiveFailed(text)

    monkeypatch.setattr(account_reset, "reset_closed_history", failing)
    r = logged_in.post(URL)
    assert_error(r, "archive_failed", 500)
    assert r.get_json()["error"]["message"] == text
    assert _statuses(logged_in) == ["ACTIVE", "CLOSED"]
