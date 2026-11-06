"""scripts/ops/admin_browser_probe.py: the browser probe (v206 P1-a).

Only the Playwright loop goes without a unit test (spec P1-a); every metric
the Goal reads -- settle time, nearest-rank percentiles with the thin rule,
the heavy-call rule, requests per minute, the run label -- is pinned here.
"""
import json
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


# --- summarise and render (V206-1b) ------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "admin_browser_probe_raw.json"


@pytest.fixture
def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_summary_carries_provenance_and_the_run_label(raw):
    report = probe.summarise(raw)
    assert report["label"] == "scan"
    assert report["meta"] == raw["meta"]


def test_summary_goal_figures(raw):
    goal = probe.summarise(raw)["goal"]
    # First heavy TTFB per page: 1200, 4000, 800, 1100 -> n=4, thin, median rank 2 = 1100.
    assert goal["first_heavy_ms"] == {"n": 4, "median": 1100, "p90": None, "max": 4000, "thin": True}
    assert goal["endpoints_over_5s"] == ["/system/scan"]
    assert goal["idle_rpm"] == 3.0


def test_summary_rounds_are_apart_and_settle_stats_skip_capped_pages(raw):
    first, second = probe.summarise(raw)["rounds"]
    assert (first["round"], first["pages"], first["capped"], first["capped_share"]) == (1, 2, 1, 0.5)
    assert first["settle_s"] == {"n": 1, "median": 3.5, "p90": None, "max": 3.5, "thin": True}
    assert (second["capped"], second["settle_s"]["median"], second["settle_s"]["max"]) == (0, 1.2, 2.1)
    assert [r["endpoint"] for r in second["endpoints"]] == ["/trades", "/dashboard", "/system/scan", "/health"]


def test_summary_endpoints_pool_every_round(raw):
    rows = probe.summarise(raw)["endpoints"]
    assert [r["endpoint"] for r in rows] == ["/system/scan", "/trades", "/dashboard", "/health"]
    assert rows[1] == {"endpoint": "/trades", "n": 4, "median": 900, "p90": None, "max": 4000, "thin": True}


def test_page_rows_carry_cap_and_the_first_heavy_call(raw):
    pages = probe.summarise(raw)["pages"]
    capped = pages[1]
    assert capped["capped"] is True and capped["settle_s"] is None
    assert (capped["first_heavy"], capped["first_heavy_ttfb_ms"]) == ("/trades", 4000)
    # /health starts first on the dashboard but is light; the heavy call is /dashboard.
    assert (pages[0]["first_heavy"], pages[0]["first_heavy_ttfb_ms"]) == ("/dashboard", 1200)
    assert (pages[0]["requests"], pages[0]["rpm"]) == (4, 43.6)


def test_a_page_with_only_light_calls_has_no_first_heavy_call(raw):
    raw["pages"] = [{**raw["pages"][0], "calls": raw["pages"][0]["calls"][:1]}]
    page = probe.summarise(raw)["pages"][0]
    assert (page["first_heavy"], page["first_heavy_ttfb_ms"]) == (None, None)
    assert probe.summarise(raw)["goal"]["first_heavy_ms"]["n"] == 0


def test_summary_idle(raw):
    assert probe.summarise(raw)["idle"] == {"requests": 6, "window_s": 120.0, "rpm": 3.0, "settle_s": 2.4}


def test_markdown_shows_the_label_thin_rows_cap_and_the_idle_rate(raw):
    text = probe.render_markdown(probe.summarise(raw))
    assert "Label: **scan**" in text
    assert "Open SSE streams at start: 3" in text
    assert "| `/system/scan` | 6 | 250 | 6,000 | 6,000 |" in text
    assert "| `/trades` | 4 | 900 | thin | 4,000 |" in text
    assert "| 1 | trades | cap |" in text
    assert "## Round 2" in text
    assert "6 requests in 120 s = 3.0 per minute" in text
    assert "Endpoints over 5 s (p90, or max when thin): /system/scan" in text


def test_markdown_shows_a_dash_for_an_unknown_stream_count(raw):
    raw["meta"]["sse_streams"] = None
    assert "Open SSE streams at start: -" in probe.render_markdown(probe.summarise(raw))


# --- CLI, outputs and credential hygiene (V206-2) ----------------------------

SENTINEL_USER = "sentinel-user-7f3a"
SENTINEL_PASS = "sentinel-pass-91c2"
ARGV = ["--date", "2026-11-03", "--out"]


def _env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(f"# admin\nADMIN_USERNAME={SENTINEL_USER}\nADMIN_PASSWORD=\"{SENTINEL_PASS}\"\n",
                    encoding="utf-8")
    return path


def _runner_from(raw, seen=None):
    def runner(args, credentials):
        if seen is not None:
            seen.append(credentials)
        return {"meta": {"login_status": 200, "sse_streams": 2}, "pages": raw["pages"], "idle": raw["idle"]}
    return runner


def test_routes_are_the_spec_list_in_order_with_the_pinned_date():
    assert probe.routes("2026-11-03") == [
        "dashboard", "trades", "trades/calendar", "trades/calendar/2026-11-03", "trades/cancels",
        "watchlist", "risk", "insights/analytics", "insights/research", "insights/reports",
        "system", "system/versions"]


def test_defaults_match_the_spec():
    args = probe.parse_args(["--date", "2026-11-03", "--out", "x"])
    assert (args.base, args.rounds, args.cap, args.image_tag) == ("https://bomeo-capital.com", 3, 90.0, "")


@pytest.mark.parametrize("argv", [["--out", "x"], ["--date", "2026-13-40", "--out", "x"], ["--date", "2026-11-03"]])
def test_date_and_out_are_required_and_the_date_must_be_real(argv):
    with pytest.raises(SystemExit):
        probe.parse_args(argv)


def test_meta_records_provenance(monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(probe, "_git_sha", lambda: "abc1234")
    args = probe.parse_args(["--date", "2026-11-03", "--out", "x", "--image-tag", "ghcr.io/x:1"])
    meta = probe.build_meta(args, now=datetime(2026, 11, 5, 16, 20, tzinfo=probe.BERLIN))
    assert meta == {"probe_sha": "abc1234", "image_tag": "ghcr.io/x:1", "berlin_time": "2026-11-05T16:20:00+01:00",
                    "date": "2026-11-03", "base": "https://bomeo-capital.com", "rounds": 3, "cap_s": 90.0,
                    "quiet_s": 2.0}


def test_credentials_reach_the_runner_but_never_the_output(tmp_path, raw, capsys):
    seen, out = [], tmp_path / "run"
    code = probe.main(ARGV + [str(out)], runner=_runner_from(raw, seen), env_path=_env(tmp_path))
    assert code == 0
    assert seen == [(SENTINEL_USER, SENTINEL_PASS)]
    printed = capsys.readouterr()
    texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8"),
             printed.out, printed.err]
    for text in texts:
        assert SENTINEL_USER not in text and SENTINEL_PASS not in text


def test_outputs_merge_runner_meta_over_provenance(tmp_path, raw, monkeypatch):
    monkeypatch.setattr(probe, "_git_sha", lambda: "abc1234")
    out = tmp_path / "run"
    probe.main(ARGV + [str(out), "--image-tag", "ghcr.io/x:1"], runner=_runner_from(raw), env_path=_env(tmp_path))
    written = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    meta = written["report"]["meta"]
    assert (meta["probe_sha"], meta["image_tag"], meta["sse_streams"], meta["login_status"]) == \
        ("abc1234", "ghcr.io/x:1", 2, 200)
    assert written["report"]["label"] == "scan"
    assert "Label: **scan**" in (out / "probe.md").read_text(encoding="utf-8")


def test_a_failed_login_exits_non_zero_and_writes_nothing(tmp_path, capsys):
    def runner(args, credentials):
        raise probe.LoginFailed("HTTP 401")
    out = tmp_path / "run"
    assert probe.main(ARGV + [str(out)], runner=runner, env_path=_env(tmp_path)) == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "HTTP 401" in err and SENTINEL_PASS not in err and SENTINEL_USER not in err


def test_missing_credentials_fail_before_the_browser_starts(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n", encoding="utf-8")

    def runner(*_):
        raise AssertionError("the browser must not start without credentials")
    assert probe.main(ARGV + [str(tmp_path / "run")], runner=runner, env_path=env) == 2


class _ExplodingContext:
    class request:  # noqa: N801 - stands in for context.request
        @staticmethod
        def post(*_, **__):
            raise RuntimeError(f"net::ERR for {SENTINEL_USER} {SENTINEL_PASS}")


def test_a_request_error_during_login_exits_2_with_the_type_only(tmp_path, capsys):
    def runner(args, credentials):
        probe._login(_ExplodingContext(), "https://x", credentials)
    out = tmp_path / "run"
    assert probe.main(ARGV + [str(out)], runner=runner, env_path=_env(tmp_path)) == 2
    assert not out.exists()
    printed = capsys.readouterr()
    assert "RuntimeError" in printed.err
    for text in (printed.out, printed.err):
        assert SENTINEL_USER not in text and SENTINEL_PASS not in text


def test_a_missing_playwright_install_exits_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)  # import raises ImportError
    out = tmp_path / "run"
    assert probe.main(ARGV + [str(out)], env_path=_env(tmp_path)) == 2
    assert not out.exists()
    printed = capsys.readouterr()
    assert "playwright is not installed" in printed.err
    for text in (printed.out, printed.err):
        assert SENTINEL_USER not in text and SENTINEL_PASS not in text


@pytest.mark.parametrize("line", [
    "ADMIN_USERNAME=u1\nexport ADMIN_PASSWORD=p#1",
    "export ADMIN_USERNAME=u1\nexport ADMIN_PASSWORD=\"p#1\"",
    "ADMIN_USERNAME='u1'\nADMIN_PASSWORD='p#1'",
    "  export   ADMIN_USERNAME = u1\nADMIN_PASSWORD=\"p#1\"",
])
def test_load_credentials_accepts_export_prefix_quotes_and_hash(tmp_path, line):
    env = tmp_path / ".env"
    env.write_text(line + "\n", encoding="utf-8")
    assert probe.load_credentials(env) == ("u1", "p#1")


def test_default_env_path_prefers_this_checkout(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    assert probe.default_env_path() == tmp_path / ".env"


class _Request:
    def __init__(self, url, response_start=150.0):
        self.url = url
        self.timing = {"startTime": 0, "requestStart": 50.0, "responseStart": response_start, "responseEnd": 400.0}

    def response(self):
        return None


def test_the_recorder_tracks_api_calls_only_and_knows_what_is_in_flight():
    ticks = iter([0.0, 0.5, 1.0, 1.5])
    recorder = probe._Recorder(clock=lambda: next(ticks))  # t0 = 0.0
    api, events, asset = _Request("https://h/api/v1/trades"), _Request("https://h/api/v1/events"), _Request("https://h/main.js")
    for request in (api, events, asset):
        recorder.on_request(request)                         # api starts at 0.5
    assert recorder.in_flight() == 1
    recorder.on_finished(api)                                # ends at 1.0
    (call,) = recorder.calls.values()
    assert (call["start_s"], call["end_s"], call["ttfb_ms"], call["total_ms"]) == (0.5, 1.0, 100.0, 400.0)
    assert recorder.in_flight() == 0
