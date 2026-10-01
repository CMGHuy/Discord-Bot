"""Maintenance scripts read Postgres through the repositories (v116 Phase 4).

data/watchlist.json, journal.json and trades.json no longer back a store, so a
script that still opened them would silently read a missing or stale file.
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from tests.helpers import make_ohlcv
from tests.store_seed import seed_store
from tests.test_emit_cohort_registry import _raw_win_trade

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load(relpath: str):
    path = ROOT / relpath
    spec = importlib.util.spec_from_file_location(f"_t_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("relpath", [
    "scripts/data/fetch_backtest_data.py",
    "scripts/data/fetch_intraday_cache.py",
    "scripts/data/fmp_crawl.py",
])
def test_watchlist_comes_from_the_repository(relpath):
    seed_store("watchlist", ["AAPL", "MSFT"])
    assert sorted(_load(relpath).load_watchlist()) == ["AAPL", "MSFT"]


def test_dcb_load_frames_takes_the_watchlist_as_a_list(tmp_path):
    from scripts.backtest.measure_dcb_veto import load_frames
    for sym in ("AAPL", "MSFT"):
        make_ohlcv([10.0] * 30).rename_axis("Date").to_csv(tmp_path / f"{sym}.csv")
    frames = load_frames(tmp_path, ["AAPL", "MSFT", "NOCSV"], None, 1)
    assert sorted(frames) == ["AAPL", "MSFT"]


def test_cohort_separation_report_reads_the_journal_table():
    from scripts.reports.cohort_separation_report import load_entries
    seed_store("journal", [{"trade_id": "T1", "ticker": "AAPL", "strategy": "RSI", "outcome": "win",
                            "closed_at": "2026-10-01T15:00:00+00:00",
                            "created_at": "2026-10-01T15:00:01+00:00"}])
    assert [e["trade_id"] for e in load_entries(None)] == ["T1"]


def test_cohort_separation_report_still_accepts_an_exported_file(tmp_path):
    from scripts.reports.cohort_separation_report import load_entries
    path = tmp_path / "journal.json"
    path.write_text('[{"trade_id": "X"}]', encoding="utf-8")
    assert load_entries(str(path)) == [{"trade_id": "X"}]


def test_emit_cohort_registry_reads_the_trades_table():
    from scripts.backtest.emit_cohort_registry import load_live_trades
    seed_store("trades", [_raw_win_trade(ticker="AAPL", strategy="RSI", horizon_key="1m"),
                          _raw_win_trade(id="t2", source="strategy", ticker="AAPL",
                                         strategy="RSI", horizon_key="1m")])
    assert [t["id"] for t in load_live_trades(None)] == ["trade-1"]


def test_no_maintenance_script_opens_a_retired_json_store():
    pattern = re.compile(r"(watchlist|journal|trades|plans|state|account)\.json")
    offenders = []
    for folder in ("data", "backtest", "reports", "ops"):
        for path in (ROOT / "scripts" / folder).glob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert offenders == []
