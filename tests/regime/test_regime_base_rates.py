"""v244 V244-1/V244-2: the SPY base-rate study (spec v239 § Evidence) on
synthetic series: hash refusal, windowed labels, per-year checkpoint, reports."""
import dataclasses
import datetime as dt
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


def test_without_a_manifest_the_first_run_record_still_guards(tmp_path):
    cache, work = _cache(tmp_path), tmp_path / "work"
    (cache / rbr.frd.MANIFEST).unlink()
    assert rbr.check_hashes(cache, work) is None
    assert (work / rbr.HASHES).exists()
    with open(rbr.frd.csv_path(cache, br.SPY), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("2025-12-31,1,1,1,1,0\n")
    assert "recorded at its first run" in rbr.check_hashes(cache, work)


def test_label_series_without_vix_labels_every_session_with_no_stress():
    spy, _ = _frames(300)
    days = rbr.label_series(spy, None)
    assert [d.session_date for d in days] == [ts.date() for ts in spy.index[br.MIN_BARS:]]
    assert all(d.stress is None and d.vix_close is None for d in days)


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


CODES = {"N": (br.NORMAL, False), "C": (br.CORRECTION, False), "S": (br.CORRECTION, True),
         "c": (br.CORRECTION, None), "B": (br.BEAR, True), "U": (br.UNKNOWN, None)}
# NORMAL x5, one-day CORRECTION flicker, NORMAL x3 -> one NORMAL episode of 9; then
# CORRECTION 4 + CORRECTION_STRESS 3 (one spell of 7) -> BEAR 5; NORMAL 2; CORRECTION 3 -> NORMAL 3.
SEQ = "NNNNN" "C" "NNN" "CCCC" "SSS" "BBBBB" "NN" "CCC" "NNN"


def _days(codes, start="2008-01-02"):
    dates = pd.bdate_range(start, periods=len(codes))
    return [br.RegimeDay(session_date=d.date(), last_bar_date=None, state=CODES[c][0],
                         stress=CODES[c][1]) for d, c in zip(dates, codes)]


def test_episodes_merge_flicker():
    eps = rbr.episodes(_days(SEQ))
    assert [(e.key, e.sessions) for e in eps] == [
        ("NORMAL", 9), ("CORRECTION", 4), ("CORRECTION_STRESS", 3), ("BEAR", 5),
        ("NORMAL", 2), ("CORRECTION", 3), ("NORMAL", 3)]


def test_episode_table():
    table = {row["key"]: row for row in rbr.episode_table(rbr.episodes(_days(SEQ)))}
    assert list(table) == ["BEAR", "CORRECTION_STRESS", "CORRECTION", "NORMAL", "UNKNOWN"]
    assert (table["NORMAL"]["count"], table["NORMAL"]["median"],
            table["NORMAL"]["q1"], table["NORMAL"]["q3"]) == (3, 3.0, 2.5, 6.0)
    assert (table["CORRECTION"]["count"], table["CORRECTION"]["median"]) == (2, 3.5)
    assert table["UNKNOWN"] == {"key": "UNKNOWN", "count": 0, "median": None, "q1": None, "q3": None}


def test_correction_spells_and_conversion():
    spells = rbr.correction_spells(rbr.episodes(_days(SEQ)))
    assert [(s["sessions"], s["stress"], s["outcome"]) for s in spells] == [
        (7, True, "bear"), (3, False, "normal")]
    assert rbr.conversion(spells) == {"spells": 2, "resolved": 2, "converted": 1,
                                      "rate": 0.5, "median_sessions": 7.0}


def test_open_and_unknown_spells_are_not_resolved():
    open_spell = rbr.correction_spells(rbr.episodes(_days("NNN" "CCC")))
    unknown = rbr.correction_spells(rbr.episodes(_days("NNN" "CCC" "UUU")))
    assert [s["outcome"] for s in open_spell + unknown] == ["open", "unknown"]
    assert rbr.conversion(open_spell + unknown) == {"spells": 2, "resolved": 0, "converted": 0,
                                                    "rate": None, "median_sessions": None}
    assert rbr.conversion([]) == {"spells": 0, "resolved": 0, "converted": 0,
                                  "rate": None, "median_sessions": None}


def test_named_rows_cover_every_spec_year():
    rows = rbr.named_rows(rbr.correction_spells(rbr.episodes(_days(SEQ))))
    assert [r["year"] for r in rows if r["start"] is None] == [2000, 2022, 2010, 2011, 2018, 2020]
    assert {r["outcome"] for r in rows if r["start"] is None} == {"no confirmed CORRECTION"}
    assert [(r["outcome"], r["expected"]) for r in rows if r["year"] == 2008] == [
        ("bear", "convert"), ("normal", "convert")]


def test_forward_returns_start_at_the_close_the_label_read():
    idx = pd.bdate_range("2024-01-01", periods=80)
    spy = pd.DataFrame({"Close": np.arange(100.0, 180.0)}, index=idx)
    fwd = rbr.forward_returns(spy, [idx[10].date(), idx[70].date()])
    assert fwd[5] == pytest.approx([100 * (114 / 109 - 1), 100 * (174 / 169 - 1)])
    assert fwd[20] == pytest.approx([100 * (129 / 109 - 1)])      # s+20 past the end for D = idx[70]
    assert fwd[60] == pytest.approx([100 * (169 / 109 - 1)])


def test_forward_returns_skip_a_day_with_no_prior_bar_or_off_the_index():
    idx = pd.bdate_range("2024-01-01", periods=80)
    spy = pd.DataFrame({"Close": np.arange(100.0, 180.0)}, index=idx)
    assert rbr.forward_returns(spy, [idx[0].date(), pd.Timestamp("2023-06-01").date()]) == {
        5: [], 20: [], 60: []}


def test_forward_rows_print_na_for_an_empty_group():
    spy, _ = _frames()
    assert rbr.forward_rows(spy, {"PULLBACK": []}) == [
        ["PULLBACK", str(h), "0", "n/a", "n/a", "n/a"] for h in rbr.HORIZONS]


def test_render_keeps_stress_none_apart():
    days = _days("NNN" "cc" "NNN")
    spy = pd.DataFrame({"Close": np.arange(100.0, 100.0 + len(days) + 70)},
                       index=pd.bdate_range("2008-01-01", periods=len(days) + 70))
    eps = rbr.episodes(days)
    text = rbr.render(days, eps, rbr.correction_spells(eps), spy, {"SPY": "a" * 64}, "cmd")
    assert "CORRECTION / stress None" in text and "CORRECTION / stress False" not in text


def _jump_spy():
    """Close 100 on bars 0..9, 200 from bar 10 on: the only move is the s -> D bar for D = idx[10]."""
    idx = pd.bdate_range("2024-01-01", periods=80)
    return idx, pd.DataFrame({"Close": [100.0] * 10 + [200.0] * 70}, index=idx)


def test_episode_rows_start_at_close_d_and_pullback_rows_at_close_s():
    idx, spy = _jump_spy()
    d = idx[10].date()
    assert rbr.forward_returns(spy, [d], lag=0) == {5: [0.0], 20: [0.0], 60: [0.0]}
    assert rbr.forward_returns(spy, [d]) == {5: [100.0], 20: [100.0], 60: [100.0]}
    rows = rbr.forward_rows(spy, {"BEAR": [d], "BEAR / stress True": [d],
                                  "PULLBACK": [d], "PULLBACK / stress None": [d]})
    by_group = {(r[0], r[1]): r[3] for r in rows}
    assert by_group[("BEAR", "5")] == by_group[("BEAR / stress True", "60")] == "+0.00"
    assert by_group[("PULLBACK", "5")] == by_group[("PULLBACK / stress None", "60")] == "+100.00"


def test_episode_returns_keep_day_zero_and_drop_only_the_horizon_past_the_end():
    idx, spy = _jump_spy()
    assert rbr.forward_returns(spy, [idx[0].date()], lag=0) == {5: [0.0], 20: [100.0], 60: [100.0]}
    assert rbr.forward_returns(spy, [idx[74].date()], lag=0) == {5: [0.0], 20: [], 60: []}
    assert rbr.forward_returns(spy, [idx[75].date()], lag=0) == {5: [], 20: [], 60: []}


def test_named_rows_count_a_cross_year_spell_only_when_it_converts():
    converts = {"start": dt.date(2007, 11, 1), "end": dt.date(2008, 1, 14), "sessions": 50,
                "stress": True, "outcome": "bear", "switch": dt.date(2008, 1, 15)}
    recovers = {"start": dt.date(2007, 12, 3), "end": dt.date(2008, 1, 9), "sessions": 25,
                "stress": False, "outcome": "normal", "switch": dt.date(2008, 1, 10)}
    rows = [r for r in rbr.named_rows([converts, recovers]) if r["year"] == 2008]
    assert [(r["start"], r["outcome"], r["switch"]) for r in rows] == [
        (dt.date(2007, 11, 1), "bear", dt.date(2008, 1, 15))]


def test_forward_rows_format_known_returns():
    closes = [100.0] * 20
    closes[6], closes[7] = 110.0, 150.0          # lag 0: D = bars 0, 1, 2 -> 0%, +10%, +50% at h=5
    spy = pd.DataFrame({"Close": closes}, index=pd.bdate_range("2024-01-01", periods=20))
    dates = [ts.date() for ts in spy.index[:3]]
    assert rbr.forward_rows(spy, {"NORMAL": dates}) == [
        ["NORMAL", "5", "3", "+20.00", "+10.00", "66.7"],
        ["NORMAL", "20", "0", "n/a", "n/a", "n/a"],
        ["NORMAL", "60", "0", "n/a", "n/a", "n/a"]]


def test_render_counts_a_pullback_day():
    days = _days("NNNNN")
    days[2] = dataclasses.replace(days[2], pullback_trigger=True)
    spy = pd.DataFrame({"Close": np.arange(100.0, 100.0 + len(days) + 70)},
                       index=pd.bdate_range("2008-01-01", periods=len(days) + 70))
    eps = rbr.episodes(days)
    text = rbr.render(days, eps, rbr.correction_spells(eps), spy, {"SPY": "a" * 64}, "cmd")
    assert "| PULLBACK | 5 | 1 |" in text and "| PULLBACK | 60 | 1 |" in text
    assert "| PULLBACK / stress False | 20 | 1 |" in text


def _assert_header(text, cache):
    assert "v244" in text and "DESCRIPTION" in text and "moves no gate" in text and rbr.END in text
    assert "never a lift" in text and "only its N and coverage columns" in text
    assert "v244-regime-base-rates" in text
    assert "from the close of D" in text and "from `s`" in text
    for symbol in (br.SPY, br.VIX):
        assert rbr.frd.sha256_file(rbr.frd.csv_path(cache, symbol)) in text


def test_main_writes_the_doc_and_a_rerun_rewrites_the_same_bytes(tmp_path, monkeypatch):
    cache, work, out = _cache(tmp_path), tmp_path / "work", tmp_path / "doc.md"
    argv = ["--cache-dir", str(cache), "--work-dir", str(work), "--out", str(out)]
    assert rbr.main(argv) == 0
    text = out.read_text(encoding="utf-8")
    _assert_header(text, cache)
    assert b"\r\n" not in out.read_bytes()
    calls = []
    monkeypatch.setattr(rbr, "label_year", lambda *a: calls.append(a) or [])
    assert rbr.main(argv) == 0
    assert calls == [] and out.read_text(encoding="utf-8") == text


def test_main_refuses_a_refetched_cache_and_writes_nothing(tmp_path, capsys):
    cache, work, out = _cache(tmp_path), tmp_path / "work", tmp_path / "doc.md"
    assert rbr.check_hashes(cache, work) is None
    with open(rbr.frd.csv_path(cache, br.SPY), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("2025-12-31,1,1,1,1,0\n")
    spy, vix = _frames()
    rbr.frd.write_manifest(cache, {br.SPY: spy, br.VIX: vix}, "refetch")
    assert rbr.main(["--cache-dir", str(cache), "--work-dir", str(work), "--out", str(out)]) == 2
    assert not out.exists() and "refusing" in capsys.readouterr().err


def test_main_refuses_a_cache_too_short_to_label(tmp_path, capsys):
    cache, out = _cache(tmp_path, n=200), tmp_path / "doc.md"
    argv = ["--cache-dir", str(cache), "--work-dir", str(tmp_path / "work"), "--out", str(out)]
    assert rbr.main(argv) == 2
    assert not out.exists() and "no session to label" in capsys.readouterr().err


def test_the_ledger_carries_the_study_as_a_description():
    from swingbot.core.backtesting.instrument import stats
    rows = [r for r in stats.load_ledger(stats.LEDGER_PATH) if r["id"] == "v244-regime-base-rates"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["verdict"], row["instrument"], row["p"], row["exp_r"]) == ("DESCRIPTION", "v1", None, None)
    assert row["record"] == rbr.OUT.relative_to(rbr.ROOT).as_posix()
    assert isinstance(row["n"], int) and row["n"] > 8000
    assert "never a lift" in row["hypothesis"] and "selects nothing" in row["hypothesis"]
    assert "only its N and coverage columns" in row["hypothesis"]
    assert stats.ledger_data_source(row) == "yfinance"
