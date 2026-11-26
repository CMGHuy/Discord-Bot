"""v244 V244-1/V244-2: the SPY base-rate study (spec v239 § Evidence) on
synthetic series: hash refusal, windowed labels, per-year checkpoint, reports."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts.research import regime_base_rates as rbr
from swingbot.core.market import bear_regime as br


def _frames(n=300, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n, name="Date")
    close = np.concatenate([np.linspace(100, 160, 240), np.linspace(160, 140, 30),
                            np.linspace(140, 152, max(n - 270, 0))])[:n]
    vix = np.concatenate([np.full(240, 15.0), np.linspace(15, 32, 30),
                          np.linspace(32, 18, max(n - 270, 0))])[:n]
    spy = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0, "Close": close,
                        "Volume": 1e6}, index=idx)
    vix = pd.DataFrame({"Open": vix, "High": vix, "Low": vix, "Close": vix, "Volume": 0.0}, index=idx)
    return spy, vix


def _cache(tmp_path, n=300, start="2024-01-01"):
    spy, vix = _frames(n, start)
    cache = tmp_path / "cache"
    cache.mkdir()
    for symbol, frame in ((br.SPY, spy), (br.VIX, vix)):
        frame.to_csv(rbr.frd.csv_path(cache, symbol), lineterminator="\n")
    rbr.frd.write_manifest(cache, {br.SPY: spy, br.VIX: vix}, "test")
    return cache


def test_constants():
    assert rbr.END == "2026-11-20" == rbr.frd.END
    assert rbr.HORIZONS == (5, 20, 60)
    assert list(rbr.NAMED) == [2000, 2008, 2022, 2010, 2011, 2018, 2020]
    assert {y for y, e in rbr.NAMED.items() if e == "convert"} == {2000, 2008, 2022}
    assert rbr.WINDOW_BARS == br.MIN_BARS + 40
    assert rbr.WORK_DIR.name == "v244_regime_base_rates"
    assert rbr.OUT.name == "2026-11-23-v244-regime-base-rates.md"


def test_windowed_labels_equal_full_frame_classify():
    spy, vix = _frames(320)
    days = rbr.label_series(spy, vix)
    assert days[0].session_date == spy.index[br.MIN_BARS].date()
    assert days[-1].session_date == spy.index[-1].date()
    for i in (br.MIN_BARS, 265, 300, len(spy) - 1):
        got = days[i - br.MIN_BARS]
        full = br.classify(spy, vix, last_session=spy.index[i - 1].date(),
                           session_date=spy.index[i].date(),
                           spy_provider="yfinance", vix_provider="yfinance")
        assert (got.state, got.stress, got.pullback_trigger, got.last_bar_date) == (
            full.state, full.stress, full.pullback_trigger, full.last_bar_date)
        assert (got.sma200, got.sma50_lag5, got.vix_max5) == pytest.approx(
            (full.sma200, full.sma50_lag5, full.vix_max5))


def test_appending_bars_never_changes_earlier_labels():
    spy, vix = _frames(320)
    short = rbr.label_series(spy.iloc[:290], vix.iloc[:290])
    longer = rbr.label_series(spy, vix)[:len(short)]
    assert [d.to_row() for d in short] == [d.to_row() for d in longer]


def test_label_series_on_a_frame_shorter_than_min_bars_is_empty():
    spy, vix = _frames(br.MIN_BARS)
    assert rbr.label_series(spy, vix) == []


def test_label_year_keeps_only_that_year():
    spy, vix = _frames()
    assert {d.session_date.year for d in rbr.label_year(spy, vix, 2025)} == {2025}
    assert rbr.label_year(spy, vix, 2030) == []


def test_load_cache_cuts_at_end(tmp_path):
    cache = _cache(tmp_path, n=300, start="2026-01-01")
    spy, vix = rbr.load_cache(cache)
    assert spy.index[-1] <= pd.Timestamp(rbr.END) and vix.index[-1] <= pd.Timestamp(rbr.END)
    assert spy.index.is_monotonic_increasing


def test_hashes_are_recorded_on_the_first_run_then_enforced(tmp_path):
    cache, work = _cache(tmp_path), tmp_path / "work"
    assert rbr.check_hashes(cache, work) is None
    recorded = json.loads((work / rbr.HASHES).read_text(encoding="utf-8"))
    assert recorded[br.SPY] == rbr.frd.sha256_file(rbr.frd.csv_path(cache, br.SPY))
    assert rbr.check_hashes(cache, work) is None
    (work / rbr.HASHES).write_text(json.dumps({**recorded, br.SPY: "0" * 64}), encoding="utf-8")
    assert "recorded at its first run" in rbr.check_hashes(cache, work)


def test_a_cache_that_differs_from_its_manifest_is_refused(tmp_path):
    cache = _cache(tmp_path)
    with open(rbr.frd.csv_path(cache, br.VIX), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("2025-12-31,1,1,1,1,0\n")
    assert "manifest.json" in rbr.check_hashes(cache, tmp_path / "work")
    assert not (tmp_path / "work" / rbr.HASHES).exists()


def test_a_missing_cache_file_is_refused(tmp_path):
    assert "fetch_regime_data.py" in rbr.check_hashes(tmp_path / "none", tmp_path / "work")


def test_labelled_checkpoints_per_year_and_resumes(tmp_path, monkeypatch):
    spy, vix = _frames()
    work = tmp_path / "work"
    first = rbr.labelled(spy, vix, work)
    assert first == rbr.label_series(spy, vix)
    lines = (work / rbr.CHECKPOINT).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["key"] for line in lines] == ["2024", "2025"]
    calls = []
    monkeypatch.setattr(rbr, "label_year", lambda *a: calls.append(a) or [])
    assert rbr.labelled(spy, vix, work) == first
    assert calls == []


def test_labelled_survives_a_torn_last_line(tmp_path):
    spy, vix = _frames()
    work = tmp_path / "work"
    first = rbr.labelled(spy, vix, work)
    path = work / rbr.CHECKPOINT
    kept = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(kept + "\n" + '{"key": "2025", "row": {"da', encoding="utf-8", newline="\n")
    assert rbr.labelled(spy, vix, work) == first
    assert [json.loads(line)["key"] for line in path.read_text(encoding="utf-8").splitlines()] == [
        "2024", "2025"]
