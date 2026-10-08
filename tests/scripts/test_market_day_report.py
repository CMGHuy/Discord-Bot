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
