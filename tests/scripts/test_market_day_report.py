"""v141 report script: adapters, rendering, dump loading. No network, no DB."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import market_day_live_dump as dump  # noqa: E402


def _live_trade(**over):
    trade = {"id": "a" * 16, "ticker": "AAPL", "direction": "bullish", "status": "win",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0,
             "opened_at": "2026-09-01T14:35:00+00:00", "closed_at": "2026-09-04T19:00:00+00:00",
             "strategies": ["RSI"]}
    return {**trade, **over}


def test_trade_record_keeps_only_what_the_report_needs():
    record = dump.trade_record(_live_trade())
    assert set(record) == {"opened_at", "closed_at", "direction", "status", "r", "strategy"}
    assert record["r"] == pytest.approx(2.0)          # (110-100)/(100-95)
    assert record["direction"] == "bullish"
    assert "ticker" not in record


def test_scan_record_skips_deploy_markers():
    assert dump.scan_record({"at": "2026-09-01T14:00:00+00:00", "type": "deploy"}) is None
    scan = dump.scan_record({"at": "2026-09-01T14:00:00+00:00", "duration_s": 12.5,
                             "signals": 9, "alerts": 2, "tickers": 80,
                             "short_funnel": {"bullish/base/base/send/ok": 2}})
    assert scan == {"at": "2026-09-01T14:00:00+00:00", "signals": 9, "alerts": 2,
                    "funnel": {"bullish/base/base/send/ok": 2}}


def test_build_dump_drops_open_trades_and_is_json_serialisable():
    out = dump.build_dump(
        [_live_trade(), _live_trade(status="open", exit_price=None, closed_at=None)],
        [{"at": "2026-09-01T14:00:00+00:00", "duration_s": 3.0, "signals": 1, "alerts": 0}])
    assert len(out["trades"]) == 1
    assert out["scans"][0]["funnel"] == {}
    json.dumps(out)


import market_day_report as report  # noqa: E402


def _market(returns, start="2021-03-01"):
    idx = pd.bdate_range(start, periods=len(returns))
    return {str(ts.date()): {"same_day": ret, "prior_day": ret, "trailing_5d": ret, "regime": "bull"}
            for ts, ret in zip(idx, returns)}


def test_et_day_uses_the_us_market_date():
    assert report.et_day("2026-09-02T01:30:00+00:00") == "2026-09-01"     # 21:30 ET the day before
    assert report.et_day("2026-09-01T14:35:00+00:00") == "2026-09-01"
    assert report.et_day(None) is None
    assert report.et_day("not a date") is None


def test_sweep_row_and_live_row_share_one_shape():
    swept = report.sweep_row({"opened_at": "2021-03-01", "closed_at": "2021-03-05",
                              "direction": "bullish", "outcome": "win", "r_multiple": 2.0,
                              "strategy": "RSI", "source": "strategy", "ticker": "AAA", "horizon": "2w"})
    live = report.live_row({"opened_at": "2026-09-01T14:35:00+00:00",
                            "closed_at": "2026-09-04T19:00:00+00:00", "direction": "bullish",
                            "status": "closed", "r": 0.4, "strategy": "RSI"})
    assert set(swept) == set(live) == {"day", "closed_day", "direction", "outcome", "r",
                                       "strategy", "source"}
    assert swept["day"] == "2021-03-01" and swept["closed_day"] == "2021-03-05"
    assert live["day"] == "2026-09-01" and live["closed_day"] == "2026-09-04"
    assert live["outcome"] == "scratch"          # only win/loss are decided
    assert live["source"] == "live"


def test_counts_by_day_filters_direction_and_strategy():
    rows = [{"day": "d1", "direction": "bullish", "strategy": "RSI"},
            {"day": "d1", "direction": "bullish", "strategy": "MACD"},
            {"day": "d1", "direction": "bearish", "strategy": "RSI"},
            {"day": "d2", "direction": "bullish", "strategy": "RSI"}]
    assert report.counts_by_day(rows) == {"d1": 2, "d2": 1}
    assert report.counts_by_day(rows, strategy="RSI") == {"d1": 1, "d2": 1}
    assert report.counts_by_day(rows, direction="bearish") == {"d1": 1}


def test_raw_signal_counts_sums_bullish_entries_in_window(monkeypatch):
    idx = pd.bdate_range("2021-03-01", periods=4)
    frame = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    bullish = pd.Series([True, False, True, True], index=idx)
    monkeypatch.setattr(report.entry_filters, "entries_for",
                        lambda strategy, df, hk: (bullish, ~bullish))
    counts = report.raw_signal_counts({"AAA": frame, "BBB": frame}, ["RSI"], ["2w"],
                                      "2021-03-02", "2021-03-04")
    assert counts == {"2021-03-03": 2, "2021-03-04": 2}        # day 1 is outside the window


def test_raw_signal_counts_survives_one_bad_pair(monkeypatch):
    idx = pd.bdate_range("2021-03-01", periods=2)
    frame = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)

    def _boom(strategy, df, hk):
        raise ValueError("no data")

    monkeypatch.setattr(report.entry_filters, "entries_for", _boom)
    assert report.raw_signal_counts({"AAA": frame}, ["RSI"], ["2w"], "2021-01-01", "2021-12-31") == {}


def test_scan_days_sums_scans_into_et_days():
    scans = [
        {"at": "2026-09-01T14:00:00+00:00", "signals": 5, "alerts": 2,
         "funnel": {"bullish/base/base/send/ok": 2, "bullish/base/base/rs/rs_blocked": 1}},
        {"at": "2026-09-01T18:00:00+00:00", "signals": 3, "alerts": 0, "funnel": {}},
        {"at": "2026-09-02T14:00:00+00:00", "signals": 0, "alerts": 0, "funnel": {}},
        {"at": None, "signals": 9, "alerts": 9, "funnel": {}},
    ]
    alerts, sums = report.scan_days(scans)
    assert alerts == {"2026-09-01": 2, "2026-09-02": 0}
    assert sums["2026-09-01"] == {"signals": 8, "alerts": 2, "send:ok": 2, "rs:rejected": 1}
    assert sums["2026-09-02"] == {"signals": 0, "alerts": 0}


def test_load_live_dump_takes_the_json_line_and_ignores_noise(tmp_path):
    path = tmp_path / "dump.json"
    path.write_text('some docker warning\n{"trades": [], "scans": []}\n', encoding="utf-8")
    assert report.load_live_dump(path) == {"trades": [], "scans": []}
    path.write_text("nothing here\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        report.load_live_dump(path)


def test_backtest_section_renders_every_form_with_intervals():
    days = _market([1.5] * 12 + [-1.5] * 12)
    keys = list(days)
    rows = [{"day": d, "closed_day": d, "direction": "bullish", "outcome": "win", "r": 1.0,
             "strategy": "RSI", "source": "strategy"} for d in keys[:12]]
    rows += [{"day": d, "closed_day": None, "direction": "bullish", "outcome": "loss", "r": -1.0,
              "strategy": "confluence", "source": "confluence"} for d in keys[12:]]
    text = "\n".join(report.backtest_section(rows, days, {keys[0]: 5}))
    for form in ("same_day", "prior_day", "trailing_5d"):
        assert form in text
    assert "95% interval" in text
    assert "Spearman" in text
    assert "| > +1% | 12 | 12 | 100.00% " in text
    assert "named strategies only" in text


def test_live_section_prints_no_interval_and_no_correlation():
    days = _market([1.5] * 12, start="2026-09-01")
    keys = list(days)
    rows = [{"day": d, "closed_day": d, "direction": "bullish", "outcome": "win", "r": 1.0,
             "strategy": "RSI", "source": "live"} for d in keys]
    scans = [{"at": f"{d}T14:00:00+00:00", "signals": 4, "alerts": 1,
              "funnel": {"bullish/base/base/send/ok": 1}} for d in keys]
    text = "\n".join(report.live_section(rows, scans, days))
    assert "interval" not in text
    assert "Spearman" not in text
    assert "holdout" in text
    assert "send" in text
    assert "| > +1% | 12 | 12 | 100.00% " in text
