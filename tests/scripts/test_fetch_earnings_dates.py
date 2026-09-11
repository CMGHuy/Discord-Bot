import sys
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts" / "data"))
import fetch_earnings_dates as fed
from swingbot.core.market.earnings_calendar import CsvSource
ET=ZoneInfo("America/New_York")
def frame(*stamps): return pd.DataFrame({"EPS Estimate": [1.] * len(stamps)}, index=pd.DatetimeIndex(stamps))
def test_rows_sort_dedup_and_roundtrip(tmp_path):
    rows=fed.rows_from_frame(frame(pd.Timestamp("2026-10-29 16:00", tz=ET), pd.Timestamp("2026-07-30 06:00", tz=ET), pd.Timestamp("2026-07-30 07:00", tz=ET)))
    assert [(row["report_date"], row["timing"]) for row in rows] == [("2026-07-30", "before_open"), ("2026-10-29", "after_close")]
    fed.write_csv(tmp_path / "NVDA.csv", rows); assert len(CsvSource(tmp_path).reports("NVDA")) == 2
def test_main_skips_etfs_existing_and_reports_missing(tmp_path, monkeypatch):
    cache, out=tmp_path / "cache", tmp_path / "out"; cache.mkdir(); out.mkdir()
    for symbol in ("SPY", "AAA", "BBB", "CCC"): (cache / f"{symbol}.csv").write_text("Date\n")
    (out / "BBB.csv").write_text("report_date,timing,report_ts_et\n")
    monkeypatch.setattr("swingbot.core.marketdata.universe.is_etf", lambda symbol: symbol == "SPY")
    monkeypatch.setattr(fed, "fetch_frame", lambda symbol, limit: frame(pd.Timestamp("2026-10-29 16:00", tz=ET)) if symbol == "AAA" else None)
    assert fed.main(["--cache-dir", str(cache), "--out-dir", str(out)]) == 1 and (out / "AAA.csv").exists()
