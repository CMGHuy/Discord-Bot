"""v205 V205-16: amounts convert on their Berlin day. Hand-computed values only.
EU DST 2026 switches: 03-29 and 10-25, 01:00 UTC."""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import pytest

from swingbot.core.marketdata import fx, fx_convert
from tests.admin_perf import golden_book as gb

_QUOTES = {"AAPL": "USD", "SAP.DE": "EUR", "VOD.L": "GBp", "NPN.JO": "ZAc"}
_RATES = {date(2026, 10, 29): 0.9, date(2026, 11, 2): 0.8, date(2026, 11, 3): 0.868,
          date(2026, 8, 4): 0.5}


@pytest.fixture
def asked(monkeypatch):
    """Pins fx as the admin's money tests do; records every rate fx_convert asks for."""
    calls = []

    def fake_rate(from_code, to_code, on, **_):
        calls.append((from_code, to_code, on))
        return _RATES.get(on)

    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "quote_currency_code", lambda ticker, **_: _QUOTES.get(ticker))
    monkeypatch.setattr(fx, "fx_rate", fake_rate)
    return calls


def _row(ticker, amount, closed_at):
    return {"ticker": ticker, "realized_pnl_amount": amount, "closed_at": closed_at}


# --- fx_day ------------------------------------------------------------------

@pytest.mark.parametrize("stamp,day", [
    ("2026-08-03T21:59:00+00:00", date(2026, 8, 3)),    # CEST 23:59
    ("2026-08-03T22:00:00+00:00", date(2026, 8, 4)),    # CEST 00:00
    ("2026-08-03T23:59:00+00:00", date(2026, 8, 4)),    # CEST 01:59
    ("2026-08-03T00:30:00+00:00", date(2026, 8, 3)),    # CEST 02:30
    ("2026-11-02T21:59:00+00:00", date(2026, 11, 2)),   # CET 22:59
    ("2026-11-02T22:00:00+00:00", date(2026, 11, 2)),   # CET 23:00
    ("2026-11-02T23:59:00+00:00", date(2026, 11, 3)),   # CET 00:59
    ("2026-11-02T00:30:00+00:00", date(2026, 11, 2)),   # CET 01:30
])
def test_utc_closes_map_to_their_berlin_day(stamp, day):
    assert fx_convert.fx_day(stamp) == day


@pytest.mark.parametrize("stamp,day", [
    ("2026-03-28T22:59:00+00:00", date(2026, 3, 28)),   # CET 23:59, the night before the switch
    ("2026-03-28T23:00:00+00:00", date(2026, 3, 29)),   # CET 00:00
    ("2026-03-29T22:00:00+00:00", date(2026, 3, 30)),   # CEST 00:00, after the switch
    ("2026-10-24T22:00:00+00:00", date(2026, 10, 25)),  # CEST 00:00
    ("2026-10-25T22:59:00+00:00", date(2026, 10, 25)),  # CET 23:59, after the switch back
    ("2026-10-25T23:00:00+00:00", date(2026, 10, 26)),  # CET 00:00
])
def test_dst_switch_days(stamp, day):
    assert fx_convert.fx_day(stamp) == day


def test_a_naive_stamp_is_utc_and_offsets_and_z_are_honoured():
    assert fx_convert.fx_day("2026-08-03T22:30:00") == date(2026, 8, 4)
    assert fx_convert.fx_day("2026-08-03T22:30:00Z") == date(2026, 8, 4)
    assert fx_convert.fx_day("2026-08-03T21:30:00-02:00") == date(2026, 8, 4)   # 23:30 UTC
    assert fx_convert.fx_day(datetime(2026, 8, 3, 22, 30)) == date(2026, 8, 4)
    assert fx_convert.fx_day(datetime(2026, 8, 3, 21, 30, tzinfo=timezone.utc)) == date(2026, 8, 3)


def test_a_date_or_date_only_string_is_that_date_unshifted():
    assert fx_convert.fx_day("2026-08-03") == date(2026, 8, 3)
    assert fx_convert.fx_day(date(2026, 8, 3)) == date(2026, 8, 3)


@pytest.mark.parametrize("stamp", [None, "", "  ", "not a stamp", 42,
                                   "9999-12-31T23:30:00-02:00"])
def test_absent_or_unreadable_is_berlin_today(stamp, monkeypatch):
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2030, 1, 2))
    assert fx_convert.fx_day(stamp) == date(2030, 1, 2)


def test_berlin_today_is_the_berlin_date_not_the_utc_date(monkeypatch):
    class _At(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 2, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(fx_convert, "datetime", _At)
    assert fx_convert.berlin_today() == date(2026, 11, 3)


def test_the_utc_day_helper_and_its_slice_are_gone():
    assert not hasattr(fx_convert, "_day")
    assert "[:10]" not in inspect.getsource(fx_convert)


# --- conversion --------------------------------------------------------------

def test_a_close_after_berlin_midnight_converts_at_the_next_days_rate(asked):
    [row] = fx_convert.to_account_currency([_row("AAPL", -30.0, "2026-11-02T23:30:00+00:00")])
    assert row["realized_pnl_amount"] == -26.04          # -30.00 x 0.868
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_scale_out_legs_convert_on_their_own_berlin_days(asked):
    trade = next(t for t in gb.trades() if t["id"] == "golden-t4-usd-scaleout")
    [row] = fx_convert.to_account_currency([trade])
    assert row["realized_pnl_amount"] == 61.0            # round(50 x 0.9, 2) + round(20 x 0.8, 2)
    assert asked == [("USD", "EUR", date(2026, 10, 29)), ("USD", "EUR", date(2026, 11, 2))]


def test_the_exact_same_code_stays_untouched_and_asks_nothing(asked):
    [row] = fx_convert.to_account_currency([_row("SAP.DE", 12.345, "2026-11-02T23:30:00+00:00")])
    assert row["realized_pnl_amount"] == 12.345 and row["fx_missing"] is False
    assert asked == []


def test_pence_into_pounds_is_the_scale_with_no_lookup(asked):
    [row] = fx_convert.to_account_currency([_row("VOD.L", 1234.0, "2026-08-03T22:30:00+00:00")],
                                           account="GBP")
    assert row["realized_pnl_amount"] == 12.34           # 1234 x 0.01
    assert asked == []


def test_pence_into_euros_asks_for_the_minor_pair_on_the_berlin_day(asked):
    [row] = fx_convert.to_account_currency([_row("VOD.L", 1234.0, "2026-08-03T22:30:00+00:00")])
    assert row["realized_pnl_amount"] == 617.0           # 1234 x 0.5 (fx_rate owns the 0.01)
    assert asked == [("GBp", "EUR", date(2026, 8, 4))]


@pytest.mark.parametrize("account,value,calls", [
    ("ZAR", 50.0, []),                                    # 5000 x 0.01, no lookup
    ("EUR", 2500.0, [("ZAc", "EUR", date(2026, 8, 4))]),  # 5000 x 0.5
    ("USD", 2500.0, [("ZAc", "USD", date(2026, 8, 4))]),
    ("GBP", 2500.0, [("ZAc", "GBP", date(2026, 8, 4))]),
])
def test_rand_cents_into_each_account_currency(asked, account, value, calls):
    [row] = fx_convert.to_account_currency([_row("NPN.JO", 5000.0, "2026-08-04T12:00:00+00:00")],
                                           account=account)
    assert row["realized_pnl_amount"] == value
    assert asked == calls


def test_convert_amount_keeps_the_given_date(asked):
    assert fx_convert.convert_amount(30.0, "AAPL", date(2026, 8, 4)) == (15.0, False)
    assert asked == [("USD", "EUR", date(2026, 8, 4))]


# --- the callers -------------------------------------------------------------
# Each imports the admin app first: a cold `api_v1.<view>` import hits the
# auth -> app -> register circle that the app's own import order avoids.

def test_dashboard_open_amounts_use_berlin_today(asked, monkeypatch):
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1 import dashboard
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2026, 11, 3))
    trade = {"id": "t5", "ticker": "AAPL", "entry": 100.0, "direction": "bullish", "shares": 10}
    assert dashboard._open_amounts([trade], {"t5": 104.0}) == ([34.72], 0)   # 40 x 0.868
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_trades_unrealized_amounts_use_berlin_today(asked, monkeypatch):
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1 import trades
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: date(2026, 11, 3))
    row = {"status": "open", "ticker": "AAPL", "entry": 100.0, "direction": "bullish",
           "open_shares": 10, "current_price": 104.0, "risk_stop": 95.0}
    trades._attach_unrealized_pnl([row])
    assert (row["realized_pnl_amount"], row["fx_missing"]) == (34.72, False)
    assert asked == [("USD", "EUR", date(2026, 11, 3))]


def test_risk_weights_take_the_berlin_day_of_the_check(monkeypatch):
    import swingbot.admin.app  # noqa: F401
    from swingbot.admin.api_v1 import risk
    from swingbot.core.analytics import risk_read_model  # v204: the payload reads core's
    seen = []

    def weights(open_trades, *, on, account=None):
        seen.append(on)
        return {}, "missing_fx"

    def no_bars(symbols):
        raise RuntimeError("no bars in this test")

    monkeypatch.setattr(risk_read_model, "signed_weights", weights)
    monkeypatch.setattr(risk, "_risk_bars", no_bars)
    risk._distribution_metrics([{"ticker": "AAPL"}], "QQQ", "2026-11-02T23:30:00+00:00")
    assert seen == [date(2026, 11, 3)]
