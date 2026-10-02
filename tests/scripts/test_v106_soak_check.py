"""scripts/ops/v106_soak_check.py: clause arithmetic only -- no files, no network."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import v106_soak_check as soak  # noqa: E402


def _row(at="2026-10-01T14:00:00+00:00", cold=(1.0,), ds=None, ps=None,
         tickers=77, errors=0, skips=1):
    return {"at": at, "duration_s": 30.0, "tickers": tickers, "errors": errors,
            "data_skips": skips, "cold_fetch_s": list(cold),
            "data_sources": ds or {"alpaca": 70, "yfinance-fallback": 0},
            "price_sources": ps or {"alpaca": 75, "yfinance-fallback": 0, "none": 2}}


def test_scan_rows_keeps_window_and_drops_markers_and_junk():
    lines = [json.dumps(_row(at="2026-09-30T23:59:00+00:00")),
             json.dumps(_row(at="2026-10-01T00:00:01+00:00")),
             json.dumps({"at": "2026-10-02T08:44:00+00:00", "type": "deploy"}),
             "not json",
             json.dumps(_row(at="2026-10-07T21:00:00+00:00")),
             json.dumps(_row(at="2026-10-08T06:00:00+00:00"))]
    rows = soak.scan_rows(lines, "2026-10-01", "2026-10-07")
    assert [r["at"][:10] for r in rows] == ["2026-10-01", "2026-10-07"]


def test_clause_a_under_twenty_timings_is_unmeasured_not_pass():
    assert soak.clause_a([_row(cold=[0.5] * 19)])["verdict"] == "UNMEASURED"


def test_clause_a_p95_threshold():
    assert soak.clause_a([_row(cold=[1.0] * 20)])["verdict"] == "PASS"
    assert soak.clause_a([_row(cold=[1.0] * 18 + [9.0, 9.0])])["verdict"] == "FAIL"


def test_clause_b_pools_daily_and_price_counts():
    rows = [_row(ds={"alpaca": 90, "yfinance-fallback": 2},
                 ps={"alpaca": 4, "yfinance-fallback": 4, "none": 9})]
    b = soak.clause_b(rows)
    assert (b["misses"], b["asked"], b["verdict"]) == (6, 100, "FAIL")


def test_clause_c_equal_to_baseline_passes_and_worse_fails():
    rows = [_row(tickers=77, errors=0, skips=1)]          # 1/77 = 0.012987
    assert soak.clause_c(rows)["verdict"] == "PASS"
    assert soak.clause_c([_row(tickers=77, errors=1, skips=1)])["verdict"] == "FAIL"


def test_overall_interim_until_last_day_closes():
    result = soak.evaluate([_row(cold=[1.0] * 20)])
    before = dt.datetime(2026, 10, 7, 19, 59, tzinfo=dt.timezone.utc)
    after = dt.datetime(2026, 10, 7, 20, 0, tzinfo=dt.timezone.utc)
    assert soak.overall(result, soak.is_final("2026-10-07", before)) == "INTERIM PASS"
    assert soak.overall(result, soak.is_final("2026-10-07", after)) == "FINAL PASS"


def test_overall_fail_beats_unmeasured():
    result = soak.evaluate([_row(cold=[1.0], ds={"alpaca": 1, "yfinance-fallback": 9})])
    assert soak.overall(result, True) == "FINAL FAIL"
