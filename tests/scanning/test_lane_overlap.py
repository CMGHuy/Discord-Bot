"""v144: each lane's alert shows the other lane's open plan on the ticker -- display only."""
import inspect

import discord

from swingbot.core.scanning import lane_overlap, scan_run, short_run
from swingbot.core.tracking.performance import TradeLog


def _open(log, ticker="AAPL", **kw):
    trade_id = log.log_trade(ticker=ticker, strategy="MACD", horizon_key="3m", direction="bullish",
                             confidence_level=3, confidence_label="Medium", entry=100.0,
                             stop_loss=98.0, take_profit=105.0, **kw)
    trade = log.get_trade_by_id(trade_id)
    trade["shares"] = 50
    log._db_upsert(trade)
    return trade_id


def test_no_other_lane_means_no_line():
    _open(TradeLog())
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None) is None


def test_the_outlook_card_names_the_regular_plan_and_its_dollar_risk():
    _open(TradeLog())
    assert lane_overlap.overlap_line("AAPL", viewer_origin="next_session") == \
        "⚠ regular plan also open on AAPL (bullish, risk $100)"


def test_the_regular_alert_names_the_outlook_plan():
    _open(TradeLog(), origin="next_session")
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None) == \
        "⚠ outlook plan also open on AAPL (bullish, risk $100)"


def test_unknown_shares_read_as_risk_na():
    log = TradeLog()
    trade = log.get_trade_by_id(_open(log, origin="next_session"))
    trade["shares"] = None
    log._db_upsert(trade)
    assert lane_overlap.overlap_line("AAPL", viewer_origin=None).endswith("(bullish, risk n/a)")


def test_append_adds_one_field_and_never_raises(monkeypatch):
    _open(TradeLog(), origin="next_session")
    embed = discord.Embed()
    lane_overlap.append_overlap_field(embed, "AAPL")
    assert [(f.name, f.value) for f in embed.fields] == [
        ("⚠ Overlap", "⚠ outlook plan also open on AAPL (bullish, risk $100)")]
    monkeypatch.setattr(lane_overlap, "_other_lane_trades", lambda *a: 1 / 0)
    quiet = discord.Embed()
    lane_overlap.append_overlap_field(quiet, "AAPL")
    assert quiet.fields == []


def test_both_regular_alert_builders_call_it():
    call = "lane_overlap.append_overlap_field(embed, result.ticker)"
    assert call in inspect.getsource(scan_run._sync_run_scan)
    assert call in inspect.getsource(short_run._alert_for)
