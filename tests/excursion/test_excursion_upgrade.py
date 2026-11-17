"""v228 V228-5: the upgrade pass -- finer only, note kept, every skip counted."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from swingbot.core.analytics import excursion_upgrade as eu
from swingbot.core.analytics.excursion_upgrade import (
    UpgradeReport, pending_by_ticker, upgrade_excursions, upgrade_ticker,
)
from swingbot.core.analytics.journal import JournalStore

DAY = "2026-11-12"
RULE3 = "Entry was wrong from the first bar — review the trigger, not the exit."


def _trade(tid="u1", ticker="AAPL", **kw):
    t = {"id": tid, "ticker": ticker, "strategy": "RSI", "direction": "bullish", "status": "loss",
         "entry": 100.0, "stop_loss": 96.0, "take_profit": 108.0, "exit_price": 96.0,
         "opened_at": f"{DAY}T15:02:00+00:00", "closed_at": f"{DAY}T15:31:00+00:00"}
    t.update(kw)
    return t


def _entry(tid="u1", ticker="AAPL", **kw):
    e = {"trade_id": tid, "ticker": ticker, "strategy": "RSI", "outcome": "loss",
         "r_realized": -1.0, "mfe_r": 1.24, "mae_r": 1.1, "exit_efficiency": -0.8065,
         "excursion_source": "daily", "tags": ["near_miss_tp"],
         "auto_lesson": "Trade went 1.2R in favor before stopping out — exit management, not entry, cost this one.",
         "note": "partner note", "holding_days": 0.02,
         "opened_at": f"{DAY}T15:02:00+00:00", "closed_at": f"{DAY}T15:31:00+00:00"}
    e.update(kw)
    return e


def _archive(base, folder, stem="AAPL", start=f"{DAY} 14:30", end=f"{DAY} 20:55",
             freq="5min", drop=()):
    idx = pd.date_range(start, end, freq=freq, tz="UTC", name="Datetime")
    df = pd.DataFrame({"Close": 100.0, "High": 100.5, "Low": 99.5, "Open": 100.0,
                       "Volume": 1000.0}, index=idx)
    if len(drop):
        df = df.drop(pd.DatetimeIndex(drop).tz_localize("UTC"))
    (base / folder).mkdir(parents=True, exist_ok=True)
    df.to_csv(base / folder / f"{stem}.csv")


@pytest.fixture
def book(monkeypatch):
    trades: dict[str, dict] = {}
    monkeypatch.setattr(eu, "_trades_by_id", lambda: dict(trades))
    return trades


def test_a_daily_entry_is_upgraded_to_5min_and_keeps_the_note(tmp_path, book):
    JournalStore().add(_entry())
    book["u1"] = _trade()
    _archive(tmp_path, "5min")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"], stored["mae_r"]) == ("5min", 0.125, 1.0)
    assert stored["exit_efficiency"] == -5.0
    assert stored["note"] == "partner note"
    assert "near_miss_tp" not in stored["tags"]
    assert stored["auto_lesson"] == RULE3
    assert (stored["r_realized"], stored["outcome"], stored["holding_days"]) == (-1.0, "loss", 0.02)
    assert report.read == 1 and report.upgraded["5min"] == 1


def test_a_second_run_is_idempotent(tmp_path, book):
    JournalStore().add(_entry())
    book["u1"] = _trade()
    _archive(tmp_path, "5min")
    upgrade_excursions(None, base_dir=str(tmp_path))
    again = upgrade_excursions(None, base_dir=str(tmp_path))
    assert again.read == 0 and sum(again.upgraded.values()) == 0


def test_never_downgrades_and_an_unchanged_entry_is_not_written(tmp_path, book):
    JournalStore().add(_entry(excursion_source="15min", mfe_r=0.4))
    book["u1"] = _trade()
    _archive(tmp_path, "hourly", freq="60min", end=f"{DAY} 20:30")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"]) == ("15min", 0.4)
    assert report.no_file == 1 and sum(report.upgraded.values()) == 0


def test_every_skip_is_counted_apart(tmp_path, book):
    for tid, ticker in (("nf", "AAPL"), ("nt", "AMD"), ("ni", "IBM"), ("ur", "MSFT"),
                        ("dn", "NVDA"), ("nc", "TSLA")):
        JournalStore().add(_entry(tid, ticker))
    book.update({"nf": _trade("nf"), "ni": _trade("ni", "IBM", stop_loss=None),
                 "ur": _trade("ur", "MSFT"), "dn": _trade("dn", "NVDA"), "nc": _trade("nc", "TSLA")})
    (tmp_path / "5min").mkdir()
    (tmp_path / "5min" / "MSFT.csv").write_text("Datetime,Close\nnot-a-date,1\n", encoding="utf-8")
    _archive(tmp_path, "5min", "NVDA", drop=pd.date_range(f"{DAY} 15:05", f"{DAY} 15:20", freq="5min"))
    _archive(tmp_path, "5min", "TSLA", start=f"{DAY} 15:10")
    r = upgrade_excursions(None, base_dir=str(tmp_path))
    assert (r.read, r.no_file, r.no_trade, r.no_inputs, r.unreadable, r.density, r.no_coverage) == (
        6, 1, 1, 1, 1, 1, 1)


def test_a_coarser_write_after_a_finer_one_counts_lost_race(tmp_path, book):
    JournalStore().add(_entry(excursion_source="5min", mfe_r=0.2))
    stale = _entry(excursion_source="daily")          # what the pass read before the backfill wrote
    _archive(tmp_path, "15min", freq="15min", end=f"{DAY} 20:45")
    report = UpgradeReport()
    assert upgrade_ticker("AAPL", [(stale, _trade())], report, base_dir=str(tmp_path)) is True
    assert report.lost_race == 1 and report.upgraded["15min"] == 0
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"]) == ("5min", 0.2)


def test_a_null_source_without_mfe_can_reach_daily(tmp_path, book):
    JournalStore().add(_entry(excursion_source=None, mfe_r=None, mae_r=None, exit_efficiency=None))
    book["u1"] = _trade()
    _archive(tmp_path, "daily", start=DAY, end=DAY, freq="1D")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    assert report.upgraded["daily"] == 1
    assert JournalStore().get("u1")["excursion_source"] == "daily"


def test_the_budget_stops_before_the_next_ticker(tmp_path, book):
    report = UpgradeReport()
    assert upgrade_ticker("AAPL", [(_entry(), _trade())], report, base_dir=str(tmp_path),
                          deadline=time.monotonic() - 1) is False
    assert report.budget_hit is True and report.read == 0
    JournalStore().add(_entry())
    book["u1"] = _trade()
    assert upgrade_excursions(None, budget_seconds=-1, base_dir=str(tmp_path)).budget_hit is True


def test_pending_by_ticker_filters_window_and_rank(book):
    store = JournalStore()
    store.add(_entry("fine", excursion_source="5min"))
    store.add(_entry("in", "MSFT", closed_at="2026-11-12T15:31:00+00:00"))
    store.add(_entry("late", closed_at="2026-11-14T15:31:00+00:00"))
    store.add(_entry("early", closed_at="2026-11-01T15:31:00+00:00"))
    book["in"] = _trade("in", "MSFT")
    pending = pending_by_ticker("2026-11-10T00:00:00+00:00", "2026-11-13T00:00:00+00:00")
    assert list(pending) == ["MSFT"]
    assert [(e["trade_id"], t["id"]) for e, t in pending["MSFT"]] == [("in", "in")]
    assert pending_by_ticker("2026-12-01T00:00:00+00:00") == {}


def test_report_line_dict_and_absorb():
    report = UpgradeReport()
    report.absorb({"read": 3, "no_trade": 1, "upgraded": {"5min": 2}})
    report.absorb({"read": 1, "lost_race": 1, "budget_hit": True})
    assert report.as_dict()["read"] == 4 and report.upgraded["5min"] == 2
    assert report.line() == (
        "excursion upgrade: read 4, upgraded 5min=2 15min=0 hourly=0 daily=0, no_trade 1, "
        "no_file 0, unreadable 0, no_coverage 0, density 0, no_inputs 0, lost_race 1, budget_hit yes")
    assert UpgradeReport().as_dict() == {
        "read": 0, "no_trade": 0, "no_file": 0, "unreadable": 0, "no_coverage": 0, "density": 0,
        "no_inputs": 0, "lost_race": 0,
        "upgraded": {"5min": 0, "15min": 0, "hourly": 0, "daily": 0}, "budget_hit": False}
