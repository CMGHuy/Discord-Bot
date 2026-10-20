"""v171 D9: the success-week report and the tape sampler (scripts, loaded by path)."""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rpt = _load("scripts/reports/market_fetch_report.py", "market_fetch_report")
smp = _load("scripts/ops/v171_tape_sampler.py", "v171_tape_sampler")

# Thursday 2026-10-15: 14:00 UTC = 10:00 ET (in session); 03:00 UTC is not.
H_IN = datetime(2026, 10, 15, 14, tzinfo=timezone.utc)
H_OUT = datetime(2026, 10, 15, 3, tzinfo=timezone.utc)
START, END = rpt.window(date(2026, 10, 15), date(2026, 10, 15))


def _count(hour, outcome, n, provider="alpaca", kind="quote", asker="STOP_MONITOR"):
    return {"hour": hour, "provider": provider, "kind": kind, "asker": asker, "outcome": outcome, "n": n}


def test_window_is_inclusive_utc_days():
    assert (START, END) == (datetime(2026, 10, 15, tzinfo=timezone.utc), datetime(2026, 10, 16, tzinfo=timezone.utc))


def test_session_hours_use_the_bucket_midpoint():
    assert rpt.in_session_hour(H_IN) and rpt.in_session_hour(H_IN.replace(hour=13))   # 09:00 ET bucket, midpoint 09:30
    assert not rpt.in_session_hour(H_OUT) and not rpt.in_session_hour(H_IN.replace(hour=20))
    assert not rpt.in_session_hour(datetime(2026, 10, 17, 14, tzinfo=timezone.utc))  # Saturday


def test_calls_count_only_provider_outcomes_in_session_hours():
    rows = [_count(H_IN, "fetched", 10), _count(H_IN, "failed", 2), _count(H_IN, "hit", 50),
            _count(H_IN, "shared-wait", 5), _count(H_IN, "budget-deferred", 3),
            _count(H_IN + timedelta(hours=1), "fetched", 4, provider="yfinance", asker="ADMIN_PAGE"),
            _count(H_OUT, "fetched", 99)]
    got = rpt.calls_per_hour(rows)
    assert (got["hours"], got["calls"], got["mean"]) == (2, 16, 8.0)
    assert got["by_provider"] == {"alpaca": 12, "yfinance": 4}
    assert got["by_outcome"]["hit"] == 50 and got["days"] == {"2026-10-15": 2}


def test_calls_mean_is_none_without_session_rows():
    assert rpt.calls_per_hour([_count(H_OUT, "fetched", 3)])["mean"] is None


def test_scan_quality_skips_rows_without_tickers():
    rows = [{"at": "2026-10-15T14:05:00+00:00", "tickers": 100, "errors": 1, "data_skips": 1},
            {"at": "2026-10-15T14:06:00+00:00", "type": "deploy"},
            {"at": "2026-10-14T14:05:00+00:00", "tickers": 100, "errors": 50, "data_skips": 0}]
    assert rpt.scan_quality(rows, START, END) == {"scans": 1, "tickers": 100, "errors": 1,
                                                  "data_skips": 1, "per_ticker": 0.02}


def test_quote_age_misses_use_the_fixed_five_seconds():
    plans = [{"plan_id": "a", "issued_at": "2026-10-15T14:00:00+00:00", "quote_age_s": 5.0},
             {"plan_id": "b", "issued_at": "2026-10-15T15:00:00+00:00", "quote_age_s": 5.01},
             {"plan_id": "c", "created_at": "2026-10-15T15:00:00+00:00", "quote_age_s": None},
             {"plan_id": "d", "issued_at": "2026-10-14T15:00:00+00:00", "quote_age_s": 9.0}]
    assert rpt.QUOTE_AGE_LIMIT_S == 5.0
    assert rpt.quote_ages(plans, START, END) == {"stamped": 2, "misses": 1, "max_s": 5.01, "miss_ids": ["b"]}


def test_rebuild_totals_sum_the_telemetry_key():
    rows = [{"at": "2026-10-15T14:05:00+00:00", "rebuild": {"kept": 2, "dropped": 1, "misses": 0}},
            {"at": "2026-10-15T14:10:00+00:00", "rebuild": {"kept": 1, "dropped": 0, "misses": 1}},
            {"at": "2026-10-15T14:15:00+00:00", "tickers": 3}]
    assert rpt.rebuild_totals(rows, START, END) == {"kept": 3, "dropped": 1, "misses": 1}


def _samples(n, blank=(), error=None, start=datetime(2026, 10, 15, 13, 30, tzinfo=timezone.utc)):
    return [{"at": (start + timedelta(minutes=i)).isoformat(), "in_session": True,
             "blank": None if error else list(blank), "error": error} for i in range(n)]


def test_blank_tape_needs_coverage_to_pass():
    full = rpt.blank_tape(_samples(390), START, END)
    assert (full["session_minutes"], full["blank_minutes"], full["coverage"]) == (390, 0, 1.0)
    assert rpt.blank_tape(_samples(10, blank=["^VIX"]), START, END)["blank_minutes"] == 10


def _week(**over):
    base = {"calls": {"mean": 100.0}, "scan": {"scans": 10, "per_ticker": 0.01},
            "quotes": {"stamped": 3, "misses": 0},
            "tape": {"blank_minutes": 0, "coverage": 0.99, "errors": 0}}
    base.update(over)
    return base


def _verdicts(week, baseline):
    return {c["check"]: c["verdict"] for c in rpt.checks(week, baseline)}


def test_checks_against_the_fixed_thresholds():
    baseline = {"calls": {"mean": 200.0}, "scan": {"scans": 10, "per_ticker": 0.01}}
    assert _verdicts(_week(), baseline) == {
        "quote_age": "PASS", "blank_tape": "PASS", "provider_429s": "UNMEASURED",
        "errors_per_ticker": "PASS", "calls_per_hour": "PASS", "delta_parity": "UNMEASURED"}
    assert _verdicts(_week(calls={"mean": 100.01}), baseline)["calls_per_hour"] == "MISS"
    assert _verdicts(_week(scan={"scans": 10, "per_ticker": 0.011}), baseline)["errors_per_ticker"] == "MISS"
    assert _verdicts(_week(quotes={"stamped": 3, "misses": 1}), baseline)["quote_age"] == "MISS"
    assert _verdicts(_week(quotes={"stamped": 0, "misses": 0}), baseline)["quote_age"] == "UNMEASURED"
    assert _verdicts(_week(tape={"blank_minutes": 0, "coverage": 0.94, "errors": 0}), baseline)["blank_tape"] == "UNMEASURED"
    assert _verdicts(_week(tape={"blank_minutes": 1, "coverage": 0.5, "errors": 0}), baseline)["blank_tape"] == "MISS"
    assert _verdicts(_week(), None)["calls_per_hour"] == "UNMEASURED"


def test_build_report_wires_the_loaders():
    out = rpt.build_report(since=date(2026, 10, 15), until=date(2026, 10, 15), baseline=None,
                           count_rows=lambda s, u: [_count(H_IN, "fetched", 6)],
                           telemetry_rows=[], plans=[], samples=[])
    assert out["week"]["calls"]["calls"] == 6 and out["baseline"] is None
    assert [c["check"] for c in out["checks"]] == ["quote_age", "blank_tape", "provider_429s",
                                                   "errors_per_ticker", "calls_per_hour", "delta_parity"]


def test_sampler_counts_a_symbol_with_neither_price_nor_change_as_blank():
    entry = lambda price, chg: SimpleNamespace(price=price, change_pct=chg)
    entries = {"^GSPC": entry(None, 0.4), "^NDX": entry(20000.0, None), "^DJI": entry(None, None)}
    assert smp.blank_symbols(entries, ("^GSPC", "^NDX", "^DJI", "^VIX")) == ["^DJI", "^VIX"]
