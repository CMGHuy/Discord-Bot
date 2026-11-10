"""v210: the stepped pass enqueues a market_shock notice with its reading."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.scanning import fetch, shock_scan, singletons

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


def trade(ticker, *, direction="bullish", entry=100.0, stop=95.0):
    return {"ticker": ticker, "direction": direction, "entry": entry, "stop_loss": stop,
            "opened_at": "2026-11-05T12:55:00+00:00", "status": "open"}


TRADES = [trade("STX"), trade("MU", entry=50.0, stop=48.0), trade("NVDA", direction="bearish")]


class _Repo:
    def __init__(self, label, last_notice_at=None):
        self.state = {"label": label, "last_notice_at": last_notice_at,
                      "doc": {"state": shock.ShockState(label=label).as_row()}}
        self.records = []

    def current_state(self, *, conn=None):
        return self.state

    def latest_reading(self, *, conn=None):
        return None

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.records.append({"after": state_after, "event": notice_event})
        return len(self.records)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "111")
    monkeypatch.setattr(shock_scan, "build_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(shock_scan, "read_vix", lambda *a, **k: None)
    monkeypatch.setattr(shock_scan.shock, "measure", lambda snapshot, prev, th: READING)
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("unexpected quote fetch"))
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: TRADES)


def _step(monkeypatch, prior, new, *, minutes_ago=None):
    monkeypatch.setattr(shock_scan.shock, "step",
                        lambda state, reading, th: shock.ShockState(label=new, since=NOW))
    last = None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago)
    repo = _Repo(prior, last)
    label = shock_scan.run_shock_pass(step_shock=True, frames={}, live_prices=QUOTES,
                                      sector_of={}, quotes_at=NOW, now=NOW, repo=repo)
    (record,) = repo.records
    assert label == new == record["after"]
    return record["event"]


def test_entry_into_shock_enqueues_with_the_open_longs(monkeypatch):
    event = _step(monkeypatch, "NORMAL", "SHOCK")
    payload = event["payload"]
    assert (payload["prior_label"], payload["label"], payload["entry_into_shock"]) == (
        "NORMAL", "SHOCK", True)
    assert [r["ticker"] for r in payload["open_longs"]] == ["MU", "STX"]
    assert payload["open_longs"][0]["last"] is None                  # MU unquoted this pass
    assert event["target_channel_id"] == "111"


def test_a_second_leg_inside_the_rate_limit_still_enqueues(monkeypatch):
    event = _step(monkeypatch, "RECOVERY", "SHOCK", minutes_ago=5)
    assert event is not None and event["payload"]["entry_into_shock"] is True


def test_a_rate_limited_exit_records_the_reading_without_a_notice(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: pytest.fail("longs read"))
    assert _step(monkeypatch, "SHOCK", "RECOVERY", minutes_ago=10) is None


def test_an_exit_after_the_dwell_is_announced_without_longs(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: pytest.fail("longs read"))
    payload = _step(monkeypatch, "SHOCK", "RECOVERY", minutes_ago=45)["payload"]
    assert payload["open_longs"] == [] and payload["entry_into_shock"] is False


def test_no_transition_no_notice(monkeypatch):
    assert _step(monkeypatch, "SHOCK", "SHOCK", minutes_ago=500) is None


def test_an_unreadable_trade_log_is_flagged_not_hidden(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: None)
    payload = _step(monkeypatch, "NORMAL", "SHOCK")["payload"]
    assert payload["open_longs"] == [] and payload["open_longs_unavailable"] is True


def test_a_notice_that_cannot_be_built_still_records_the_reading(monkeypatch, caplog):
    def boom(payload, *, as_of):
        raise ValueError("invalid_shock_reading")
    monkeypatch.setattr(shock_scan.shock_notices, "notice_event", boom)
    assert _step(monkeypatch, "NORMAL", "SHOCK") is None
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.notice" for r in caplog.records)


def test_open_trades_reads_the_trade_log_and_swallows_a_failure(monkeypatch):
    monkeypatch.undo()                                   # the real _open_trades
    calls = []

    def get_trades(status=None, limit=20, **kwargs):
        calls.append((status, limit))
        return TRADES
    monkeypatch.setattr(singletons.trade_log, "get_trades", get_trades)
    assert shock_scan._open_trades() == TRADES and calls == [("open", None)]

    def boom(**kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(singletons.trade_log, "get_trades", boom)
    assert shock_scan._open_trades() is None
