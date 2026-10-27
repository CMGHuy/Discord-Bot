"""v194 B7 -- admin money in the account currency (api_v1/money.py); rates faked at the fx seam."""
from datetime import date

import pytest

from swingbot.admin.api_v1 import money
from swingbot.core.marketdata import fx
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}

#: USD -> EUR closes by day. 2026-09-01 has no rate on purpose.
_RATES = {date(2026, 8, 3): 0.9, date(2026, 8, 4): 0.8}
_QUOTES = {"AAPL": "USD", "ASML.AS": "EUR"}


@pytest.fixture
def rates(monkeypatch):
    """A EUR account; returns the rate lookups made. API tests list it AFTER
    `seed`/`logged_in` so it overrides admin_app's identity pin."""
    asked = []

    def fake_rate(from_code, to_code, on):
        asked.append((from_code, to_code, on))
        return _RATES.get(on)

    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker: _QUOTES.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return asked


def _closed(trade_id="a" * 16, *, ticker="AAPL", closed_at="2026-08-03T20:00:00+00:00",
            pnl=50.0, legs=(), exit_price=105.0):
    return {
        "id": trade_id, "plan_id": None, "ticker": ticker,
        "strategy": "S/R Confluence", "horizon_key": "4w",
        "direction": "bullish", "confidence_level": 4,
        "confidence_label": "High", "confidence_score": 81.0,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 120.0,
        "target2": None, "risk_reward_ratio": 2.0, "badge": "VALIDATED",
        "quality_score": 72, "source": "confluence", "legs": list(legs),
        "opened_at": "2026-08-01T14:00:00+00:00", "status": "win",
        "closed_at": closed_at, "exit_price": exit_price,
        "realized_pnl_amount": pnl, "shares": 10, "position_value": 1000.0,
        "target_sources": [], "stop_sources": [], "target2_sources": [],
        "confirmed_by": [], "explanation": None, "confidence_breakdown": None,
    }


def test_a_usd_close_converts_at_its_exit_dates_rate(rates):
    [row] = money.to_account_currency([_closed()])
    assert row["realized_pnl_amount"] == 45.0
    assert row["fx_missing"] is False
    assert rates == [("USD", "EUR", date(2026, 8, 3))]


def test_a_eur_quoted_close_is_unchanged_and_asks_no_rate(rates):
    [row] = money.to_account_currency([_closed(ticker="ASML.AS")])
    assert row["realized_pnl_amount"] == 50.0
    assert rates == []


def test_a_usd_account_converts_nothing(rates):
    [row] = money.to_account_currency([_closed()], account="USD")
    assert row["realized_pnl_amount"] == 50.0
    assert rates == []


def test_a_missing_rate_is_flagged_and_counted_never_one(rates):
    rows = money.to_account_currency([
        _closed(closed_at="2026-09-01T20:00:00+00:00"),   # no rate that day
        _closed("b" * 16, ticker="ZZZZ"),                  # unknown quote currency
        _closed("c" * 16),
    ])
    assert [r["realized_pnl_amount"] for r in rows] == [None, None, 45.0]
    assert [r["fx_missing"] for r in rows] == [True, True, False]
    assert money.missing_count(rows) == 2


def test_an_unsettled_row_stays_none_and_unflagged(rates):
    [row] = money.to_account_currency([_closed(pnl=None)])
    assert row["realized_pnl_amount"] is None
    assert row["fx_missing"] is False
    assert rates == []


def test_conversion_copies_and_rewrites_only_the_money_fields(rates):
    original = _closed()
    [row] = money.to_account_currency([original])
    assert original["realized_pnl_amount"] == 50.0 and "fx_missing" not in original
    assert set(row) - set(original) == {"fx_missing"}
    assert {k for k in original if row[k] != original[k]} == set(money.MONEY_FIELDS)


def test_each_leg_of_a_scaled_out_trade_converts_at_its_own_exit_date(rates):
    legs = [
        {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
         "closed_at": "2026-08-03T15:00:00+00:00"},
        {"fraction": 0.5, "exit_price": 104.0, "r": 0.8, "reason": "runner_trail",
         "closed_at": "2026-08-04T15:00:00+00:00"},
    ]
    trade = _closed(legs=legs, pnl=70.0, exit_price=104.0,
                    closed_at="2026-08-04T15:00:00+00:00")
    [row] = money.to_account_currency([trade])
    # 5 sh x +10 = 50 at 0.9, then 5 sh x +4 = 20 at 0.8.
    assert row["realized_pnl_amount"] == 61.0
    assert row["legs"] == legs


def test_convert_amount_prices_a_live_amount_on_the_given_day(rates):
    assert money.convert_amount(30.0, "AAPL", date(2026, 8, 4)) == (24.0, False)
    assert money.convert_amount(30.0, "AAPL", date(2026, 9, 1)) == (None, True)
    assert money.convert_amount(None, "AAPL", date(2026, 8, 4)) == (None, False)


@pytest.fixture
def seed(admin_app):
    return lambda trades: seed_store("trades", list(trades))


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _book():
    """One USD close with a rate (+50 -> 45.00) and one without (2026-08-05)."""
    return [_closed(), _closed("b" * 16, pnl=30.0, closed_at="2026-08-05T20:00:00+00:00")]


def test_trade_rows_are_in_the_account_currency(seed, logged_in, rates):
    seed(_book())
    rows = {r["id"]: r for r in logged_in.get("/api/v1/trades?per_page=200").get_json()["items"]}
    assert rows["a" * 16]["realized_pnl_amount"] == 45.0
    assert rows["a" * 16]["pnl_pct"] == 5.0           # percent reads the stored row
    assert rows["b" * 16]["realized_pnl_amount"] is None
    assert rows["b" * 16]["fx_missing"] is True


def test_dashboard_realized_converts_and_counts_the_left_out(seed, logged_in, rates):
    seed(_book())
    body = logged_in.get("/api/v1/dashboard?mode=all").get_json()
    assert body["realized"]["amount"] == 45.0
    assert body["realized"]["pct"] == 5.0
    assert body["realized"]["fx_missing_count"] == 1
    assert body["fx_missing_count"] == 1


def test_analytics_money_converts_and_counts(seed, logged_in, rates):
    seed(_book())
    dim = logged_in.get("/api/v1/analytics/by-dimension?dim=strategy").get_json()
    assert dim["rows"][0]["total_pnl"] == 45.0
    assert dim["fx_missing_count"] == 1
    curve = logged_in.get("/api/v1/analytics/equity-curve").get_json()
    assert [p["cum_pnl"] for p in curve["points"]] == [45.0, 45.0]
    assert curve["fx_missing_count"] == 1
    assert logged_in.get("/api/v1/analytics/performance").get_json()["fx_missing_count"] == 1


def test_calendar_converts_and_counts_the_month_and_the_day(seed, logged_in, rates):
    seed(_book())
    month = logged_in.get("/api/v1/calendar/pnl?month=2026-08").get_json()
    assert month["totals"]["net_pnl_amount"] == 45.0
    assert month["fx_missing_count"] == 1
    day = logged_in.get("/api/v1/calendar/pnl/day?date=2026-08-05").get_json()
    assert day["fx_missing_count"] == 1
    assert day["total_ccy"] is None
    assert day["trades"][0]["fx_missing"] is True


def test_weak_ledger_pnl_is_converted_and_counted(seed, logged_in, rates):
    weak = [{**_closed("d" * 16), "ledger": "weak"},
            {**_closed("e" * 16, pnl=30.0, closed_at="2026-08-05T20:00:00+00:00"), "ledger": "weak"}]
    seed(weak)
    body = logged_in.get("/api/v1/analytics/performance").get_json()
    assert body["weak"]["total_pnl"] == 45.0       # 50 USD at 0.9, not the stored 80
    assert body["weak"]["n"] == 2
    assert body["fx_missing_count"] == 1
