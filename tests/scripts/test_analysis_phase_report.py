"""v245 V245-6: analysis seconds per ticker from scan telemetry."""
import json

import pytest

from scripts.perf import analysis_phase_report as apr


def _scan(at, analysis, tickers=92, **extra):
    return {"at": at, "duration_s": analysis + 90.0, "tickers": tickers,
            "phases_s": {"analysis": analysis, **extra.pop("phases", {})}, **extra}


DEPLOY = {"type": "deploy", "component": "bot", "sha": "abc", "at": "2026-11-25T14:00:00Z"}


def test_per_ticker_seconds():
    assert apr.per_ticker_seconds(_scan("2026-11-25T15:00:00+00:00", 46.0)) == pytest.approx(0.5)
    assert apr.per_ticker_seconds({"tickers": 92}) is None
    assert apr.per_ticker_seconds(_scan("2026-11-25T15:00:00+00:00", 46.0, tickers=0)) is None
    assert apr.per_ticker_seconds(DEPLOY) is None
    row = _scan("2026-11-25T15:00:00+00:00", 46.0, phases={"analysis_prefix": 9.2})
    assert apr.per_ticker_seconds(row, "analysis_prefix") == pytest.approx(0.1)


def test_summarise_percentiles_and_filters():
    rows = [DEPLOY] + [_scan(f"2026-11-25T15:{m:02d}:00+00:00", 9.2 * k) for k, m in enumerate(range(1, 11), 1)]
    s = apr.summarise(rows)
    assert s["scans"] == 10                              # the deploy marker is not a scan
    assert s["p50"] == pytest.approx((0.5 + 0.6) / 2)    # median of 0.1 .. 1.0
    assert s["p90"] == pytest.approx(0.9)                # nearest rank: ceil(0.9 * 10) = 9th
    assert s["prefix_p50"] is None and s["cache_hit_rate"] is None and s["rss_mb_max"] is None


def test_summarise_since_accepts_dates_and_z_suffix():
    rows = [_scan("2026-11-24T20:00:00+00:00", 276.0), _scan("2026-11-25T15:00:00+00:00", 46.0)]
    assert apr.summarise(rows, since="2026-11-25")["scans"] == 1
    assert apr.summarise(rows, since="2026-11-25T14:00:00Z")["p50"] == pytest.approx(0.5)


def test_summarise_cache_fields():
    rows = [_scan("2026-11-25T15:00:00+00:00", 46.0, cache_hits=180, cache_misses=20, rss_mb=410.5,
                  phases={"analysis_prefix": 4.6}),
            _scan("2026-11-25T15:06:00+00:00", 46.0, cache_hits=20, cache_misses=180, rss_mb=None)]
    s = apr.summarise(rows)
    assert s["cache_hit_rate"] == pytest.approx(0.5)
    assert s["rss_mb_max"] == 410.5
    assert s["prefix_p50"] == pytest.approx(0.05)


def test_summarise_empty():
    assert apr.summarise([]) == {"scans": 0, "p50": None, "p90": None, "prefix_p50": None,
                                 "cache_hit_rate": None, "rss_mb_max": None}


def test_verdict():
    assert apr.verdict({"scans": 80, "p50": 0.7}) == "MET"
    assert apr.verdict({"scans": 80, "p50": 0.71}) == "MISSED"
    assert apr.verdict({"scans": 0, "p50": None}) == "NO DATA"


def test_last_deploy_at():
    admin = {**DEPLOY, "component": "admin", "at": "2026-11-26T09:00:00Z"}
    assert apr.last_deploy_at([DEPLOY, _scan("2026-11-25T15:00:00+00:00", 46.0), admin]) == DEPLOY["at"]
    assert apr.last_deploy_at([]) is None


def test_main_prints_summary_and_verdict(tmp_path, capsys):
    path = tmp_path / "scan_telemetry.jsonl"
    lines = [json.dumps(DEPLOY), "{not json", "",
             json.dumps(_scan("2026-11-24T20:00:00+00:00", 276.0)),
             json.dumps(_scan("2026-11-25T15:00:00+00:00", 46.0))]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert apr.main(["--path", str(path), "--since-deploy"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scans"] == 1 and out["verdict"] == "MET"
    assert out["since"] == DEPLOY["at"] and out["bad_lines"] == 1


def test_main_missing_file(tmp_path, capsys):
    assert apr.main(["--path", str(tmp_path / "absent.jsonl")]) == 1
