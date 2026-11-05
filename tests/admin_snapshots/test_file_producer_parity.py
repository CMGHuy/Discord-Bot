"""v204: analytics_snapshot.json (Discord) and the admin routes agree on the same trades."""
import pytest

from swingbot import config
from swingbot.core.analytics import snapshots
from swingbot.core.marketdata import fx
from tests.admin_snapshots.golden_book import (  # noqa: F401
    _clear_login_limiter, admin_app, client, golden_book)


@pytest.fixture
def same_currency(golden_book, monkeypatch):
    """The file sums stored amounts and the routes convert; an identity rate makes both one sum."""
    account = fx.account_currency_code()
    monkeypatch.setattr(fx, "quote_currency_code", lambda t, **k: account)
    assert config.ADMIN_REFRESHER == "off"                     # golden_book: today's routes
    return golden_book.client


def get(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return response.get_json()


def test_main_ledger_totals_and_equity_agree(same_currency):
    src = snapshots.gather_sources()
    file_doc = snapshots.compute_snapshot(src)
    perf = get(same_currency, "/api/v1/analytics/performance?ledger=main")
    curve = get(same_currency, "/api/v1/analytics/equity-curve?ledger=main")
    overall = file_doc["overall"]
    assert perf["totals"]["closed"] == overall["n"] == curve["points_n"]
    assert perf["win_rate"] == overall["win_rate"]
    assert perf["expectancy_r"] == overall["expectancy_r"]
    file_points = file_doc["equity_curve"]["points"]
    assert file_points, "the golden book must close at least one main-ledger trade"
    assert curve["points"][-1]["cum_pnl"] == pytest.approx(
        file_points[-1]["balance"] - src.starting_balance, abs=0.01)


def test_weak_ledger_totals_agree(same_currency):
    weak = snapshots.compute_snapshot()["weak"]
    perf = get(same_currency, "/api/v1/analytics/performance?ledger=weak")
    curve = get(same_currency, "/api/v1/analytics/equity-curve?ledger=weak")
    assert perf["totals"]["closed"] == weak["n"] == curve["points_n"]
    assert perf["win_rate"] == weak["win_rate"]
    final = curve["points"][-1]["cum_pnl"] if curve["points"] else 0.0
    assert final == pytest.approx(weak["total_pnl"], abs=0.01)
