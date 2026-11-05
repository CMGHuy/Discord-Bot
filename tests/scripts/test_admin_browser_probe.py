"""scripts/ops/admin_browser_probe.py: the browser probe (v206 P1-a).

Only the Playwright loop goes without a unit test (spec P1-a); every metric
the Goal reads -- settle time, nearest-rank percentiles with the thin rule,
the heavy-call rule, requests per minute, the run label -- is pinned here.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import admin_browser_probe as probe  # noqa: E402


def test_importing_the_probe_does_not_import_playwright():
    """Playwright is not a declared dependency: only the browser loop imports it."""
    assert "playwright" not in sys.modules


# --- settle_time -------------------------------------------------------------

def test_overlapping_calls_merge_and_the_page_settles_when_the_last_one_ends():
    intervals = [(2.9, 4.0), (0.0, 1.0), (0.5, 3.0)]  # unsorted on purpose
    assert probe.settle_time(intervals, 2.0, 90.0) == 4.0


def test_a_gap_just_under_the_quiet_window_does_not_settle_the_page():
    assert probe.settle_time([(0.0, 1.0), (2.99, 3.5)], 2.0, 90.0) == 3.5


def test_a_gap_just_over_the_quiet_window_settles_the_page_where_the_gap_began():
    assert probe.settle_time([(0.0, 1.0), (3.01, 3.5)], 2.0, 90.0) == 1.0


def test_a_call_still_in_flight_at_the_cap_means_the_page_never_settled():
    assert probe.settle_time([(0.0, 1.0), (1.5, None)], 2.0, 90.0) is None


def test_a_quiet_gap_that_completes_after_the_cap_is_still_cap():
    assert probe.settle_time([(0.0, 89.0)], 2.0, 90.0) is None


def test_a_page_with_no_calls_settles_at_once():
    assert probe.settle_time([], 2.0, 90.0) == 0.0


# --- percentiles and the thin rule -------------------------------------------

@pytest.mark.parametrize("pct, expected", [(0, 15), (50, 35), (90, 50), (100, 50)])
def test_nearest_rank_picks_an_observed_value(pct, expected):
    assert probe.nearest_rank([50, 15, 40, 20, 35], pct) == expected


def test_nearest_rank_of_nothing_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        probe.nearest_rank([], 90)


def test_four_values_are_thin_and_carry_no_p90():
    calls = [{"url": "/api/v1/trades", "ttfb_ms": v} for v in (100, 200, 300, 400)]
    (row,) = probe.endpoint_stats(calls)
    assert row == {"endpoint": "/trades", "n": 4, "median": 200, "p90": None, "max": 400, "thin": True}
    assert probe.goal_value(row) == 400


def test_five_values_get_a_p90():
    calls = [{"url": "/api/v1/trades", "ttfb_ms": v} for v in (100, 200, 300, 400, 500)]
    (row,) = probe.endpoint_stats(calls)
    assert row["thin"] is False and row["p90"] == 500
    assert probe.goal_value(row) == 500


def test_calls_without_a_ttfb_are_not_timed():
    assert probe.endpoint_stats([{"url": "/api/v1/live", "ttfb_ms": None}]) == []


def test_rows_are_worst_first_and_a_thin_row_ranks_on_its_max():
    calls = ([{"url": "/api/v1/system/scan", "ttfb_ms": v} for v in (200, 240, 250, 260, 300, 6000)]
             + [{"url": "/api/v1/trades?page=1", "ttfb_ms": v} for v in (700, 4000)]
             + [{"url": "/api/v1/health", "ttfb_ms": 90}])
    rows = probe.endpoint_stats(calls)
    assert [r["endpoint"] for r in rows] == ["/system/scan", "/trades", "/health"]
    assert rows[0] == {"endpoint": "/system/scan", "n": 6, "median": 250, "p90": 6000, "max": 6000, "thin": False}


# --- endpoints ---------------------------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("https://bomeo-capital.com/api/v1/dashboard?mode=today", "/dashboard"),
    ("/api/v1/trades/42", "/trades/{id}"),
    ("/api/v1/calendar/pnl/day/2026-11-03", "/calendar/pnl/day/{date}"),
    ("/api/v1/calendar/pnl/day/sparklines?date=2026-11-03", "/calendar/pnl/day/sparklines"),
])
def test_endpoints_drop_host_prefix_query_ids_and_dates(url, expected):
    assert probe.normalise_endpoint(url) == expected


@pytest.mark.parametrize("endpoint", ["/session", "/health", "/system/scan", "/system/preferences",
                                      "/risk/killswitch", "/market/updates", "/events"])
def test_shell_and_polling_endpoints_are_light(endpoint):
    assert probe.is_heavy(endpoint) is False


@pytest.mark.parametrize("endpoint", ["/dashboard", "/market/tape", "/trades", "/live"])
def test_every_other_endpoint_is_heavy(endpoint):
    assert probe.is_heavy(endpoint) is True


# --- rates and labels --------------------------------------------------------

def test_requests_per_minute():
    assert probe.requests_per_minute(6, 120.0) == 3.0
    assert probe.requests_per_minute(4, 5.5) == 43.6


def test_requests_per_minute_needs_a_window():
    with pytest.raises(ValueError):
        probe.requests_per_minute(3, 0.0)


@pytest.mark.parametrize("samples, label", [
    ([True, True, True], "scan"),
    ([False, False], "quiet"),
    ([True, False], "mixed"),
    ([True, None], "mixed"),
    ([], "mixed"),
])
def test_only_a_scan_on_every_page_labels_the_run_scan(samples, label):
    assert probe.run_label(samples) == label
