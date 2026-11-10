"""v210: market_shock notice payload, open longs, rate limit, and the stepped-pass hook."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.scanning import shock_notices

UTC = timezone.utc
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)            # 10:00 ET, a regular session
READING = shock.ShockReading(
    as_of=NOW, session_date=date(2026, 11, 5), minutes_since_open=30.0, breadth_frac=0.45,
    depth_frac=0.3,
    sectors_down=6, sectors_total=9, breadth_speed=0.15, spy_atr_move=-1.6, qqq_atr_move=-2.1,
    spy_last=490.0, spy_prev_close=500.0, spy_session_low=489.0, spy_new_low=True,
    spy_retrace=0.0, vix_level=21.1, vix_chg_pct=27.0, vix_session_high=21.1,
    vix_off_high_pct=0.0, n_names=60, insufficient=False)
QUOTES = {"SPY": 490.0, "STX": 94.0}


def trade(ticker, *, direction="bullish", entry=100.0, stop=95.0,
          opened="2026-11-05T12:55:00+00:00"):
    return {"ticker": ticker, "direction": direction, "entry": entry, "stop_loss": stop,
            "opened_at": opened, "status": "open"}


TRADES = [trade("STX"), trade("MU", entry=50.0, stop=48.0), trade("NVDA", direction="bearish")]


def test_open_long_rows_keep_open_longs_sorted_with_r_age_and_marker():
    rows = shock_notices.open_long_rows(TRADES, {"STX": 94.0, "MU": 51.0}, NOW)
    assert [r["ticker"] for r in rows] == ["MU", "STX"]
    mu, stx = rows
    assert mu == {"ticker": "MU", "entry": 50.0, "stop": 48.0, "last": 51.0,
                  "open_r": pytest.approx(0.5), "age_min": 125, "through_stop": False}
    assert stx["open_r"] == pytest.approx(-1.2) and stx["through_stop"] is True


def test_an_unquoted_long_has_no_last_no_r_and_is_not_through():
    (row,) = shock_notices.open_long_rows([trade("MU")], {}, NOW)
    assert (row["last"], row["open_r"], row["through_stop"]) == (None, None, False)


def test_last_exactly_at_the_stop_is_through_it():
    (row,) = shock_notices.open_long_rows([trade("MU")], {"MU": 95.0}, NOW)
    assert row["through_stop"] is True and row["open_r"] == pytest.approx(-1.0)


def test_a_stop_at_or_above_entry_has_no_r():
    (row,) = shock_notices.open_long_rows([trade("MU", stop=100.0)], {"MU": 101.0}, NOW)
    assert row["open_r"] is None and row["through_stop"] is False


@pytest.mark.parametrize("bad", [{"entry": None}, {"stop_loss": 0}, {"ticker": ""}])
def test_a_trade_without_entry_stop_or_ticker_is_skipped(bad):
    assert shock_notices.open_long_rows([trade("MU") | bad], {"MU": 99.0}, NOW) == []


@pytest.mark.parametrize("opened,age", [("2026-11-05T12:55:00", 125), ("garbage", 0), (None, 0)])
def test_age_treats_naive_as_utc_and_unreadable_as_zero(opened, age):
    (row,) = shock_notices.open_long_rows([trade("MU", opened=opened)], {}, NOW)
    assert row["age_min"] == age


def test_no_open_trades_gives_no_rows():
    assert shock_notices.open_long_rows([], QUOTES, NOW) == []


@pytest.mark.parametrize("prior,new,minutes_ago,sent", [
    ("SHOCK", "SHOCK", None, False),
    ("NORMAL", "SHOCK", 5, True),            # entry: always sent
    ("RECOVERY", "SHOCK", 5, True),          # second leg inside the window: still sent
    ("SHOCK", "RECOVERY", 44, False),
    ("SHOCK", "RECOVERY", 45, True),
    ("RECOVERY", "NORMAL", None, True),
])
def test_should_notify(prior, new, minutes_ago, sent):
    last = None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago)
    assert shock_notices.should_notify(prior, new, last, NOW, 45) is sent


def test_notice_payload_and_event(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "222")
    longs = shock_notices.open_long_rows(TRADES, QUOTES, NOW)
    payload = shock_notices.notice_payload(shock.ShockState(label="RECOVERY"),
                                           shock.ShockState(label="SHOCK", since=NOW),
                                           READING, longs, NOW)
    assert payload == {"label": "SHOCK", "prior_label": "RECOVERY",
                       "occurred_at": "2026-11-05T15:00:00+00:00", "reading": READING.as_row(),
                       "open_longs": longs, "entry_into_shock": True}
    event = shock_notices.notice_event(payload, as_of=NOW)
    assert event["kind"] == "market_shock" and event["target_channel_id"] == "111"
    assert event["transition_id"] == "market_shock:2026-11-05T15:00:00+00:00"
    assert event["queued_at"] == payload["occurred_at"] and event["blocked"] is False


@pytest.mark.parametrize("ops,trades_id,target", [("", "222", "222"), ("", "", None)])
def test_notice_routes_to_trades_then_blocks(monkeypatch, ops, trades_id, target):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", ops)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", trades_id)
    payload = shock_notices.notice_payload(shock.ShockState(), shock.ShockState(label="SHOCK"),
                                           READING, [], NOW)
    event = shock_notices.notice_event(payload, as_of=NOW)
    assert event["target_channel_id"] == target and event["blocked"] is (target is None)
