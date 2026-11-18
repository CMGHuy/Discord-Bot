"""v232: raw and split-adjusted daily bars in two scratch history stores."""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import raw_bars  # noqa: E402

START, END = date(2026, 9, 1), date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)


def _frame(closes, start="2026-09-01"):
    idx = pd.bdate_range(start=start, periods=len(closes), name="Date")
    rows = [(c, c * 1.01, c * 0.99, c, 1_000_000.0) for c in closes]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


class FakeProvider:
    """daily_bars_between keyed by (ticker, adjustment value)."""

    def __init__(self, frames):
        self.frames, self.calls = frames, []

    def daily_bars_between(self, tickers, start, end, *, adjustment):
        self.calls.append((tuple(tickers), start, end, adjustment.value))
        return {t: self.frames[(t, adjustment.value)] for t in tickers
                if (t, adjustment.value) in self.frames}


def _both(ticker, closes, factor=1.0):
    return {(ticker, "raw"): _frame(closes), (ticker, "split"): _frame([c * factor for c in closes])}


def test_store_dir_names_each_kind_and_refuses_others(tmp_path):
    assert raw_bars.store_dir(tmp_path, "raw") == tmp_path / "raw"
    assert raw_bars.store_dir(tmp_path, "split") == tmp_path / "split"
    with pytest.raises(ValueError, match="unknown bar kind"):
        raw_bars.store_dir(tmp_path, "all")


def test_use_store_sets_then_restores_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_STORE_DIR", "elsewhere")
    with raw_bars.use_store(tmp_path / "raw"):
        assert os.environ["HISTORY_STORE_DIR"] == str((tmp_path / "raw").resolve())
    assert os.environ["HISTORY_STORE_DIR"] == "elsewhere"
    monkeypatch.delenv("HISTORY_STORE_DIR")
    with raw_bars.use_store(tmp_path / "raw"):
        pass
    assert "HISTORY_STORE_DIR" not in os.environ


def test_write_frame_round_trips_through_the_store_reader(tmp_path):
    frame = _frame([100.0, 101.0, 102.0])
    sha = raw_bars.write_frame(tmp_path / "raw", "AAA", frame)
    path = tmp_path / "raw" / "daily" / "AAA.csv"
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert b"\r\n" not in path.read_bytes()
    back = raw_bars.load_bars("AAA", tmp_path, "raw")
    pd.testing.assert_frame_equal(back, frame, check_freq=False)


def test_write_frame_refuses_a_tz_aware_index(tmp_path):
    frame = _frame([100.0])
    frame.index = frame.index.tz_localize("UTC")
    with pytest.raises(ValueError, match="tz-aware"):
        raw_bars.write_frame(tmp_path / "raw", "AAA", frame)


def test_fetch_bars_writes_both_kinds_with_a_manifest_each(tmp_path):
    provider = FakeProvider(_both("AAA", [100.0, 101.0], factor=0.5))
    seen = []
    got = raw_bars.fetch_bars(["aaa"], START, END, tmp_path, provider=provider, out=seen.append)
    assert sorted(got) == ["raw", "split"]
    assert [c[3] for c in provider.calls] == ["raw", "split"]
    entry = got["raw"]["tickers"]["AAA"]
    assert (entry["status"], entry["rows"], entry["first"], entry["last"]) == (
        "ok", 2, "2026-09-01", "2026-09-02")
    assert (got["raw"]["start"], got["raw"]["end"]) == ("2026-09-01", "2026-09-30")
    assert (tmp_path / "split" / "daily" / "_manifest.json").is_file()
    assert raw_bars.load_bars("AAA", tmp_path, "split")["Close"].tolist() == [50.0, 50.5]
    assert any("(100%)" in line for line in seen)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw", "split"]


def test_fetch_bars_resumes_per_ticker(tmp_path):
    frames = {**_both("AAA", [100.0]), **_both("BBB", [50.0])}
    raw_bars.fetch_bars(["AAA"], START, END, tmp_path, provider=FakeProvider(frames),
                        out=lambda _: None)
    again = FakeProvider(frames)
    raw_bars.fetch_bars(["AAA", "BBB"], START, END, tmp_path, provider=again,
                        out=lambda _: None)
    assert [c[0] for c in again.calls] == [("BBB",), ("BBB",)]


def test_a_ticker_without_bars_is_recorded_empty_and_loads_as_none(tmp_path):
    got = raw_bars.fetch_bars(["ZZZ"], START, END, tmp_path, provider=FakeProvider({}),
                              out=lambda _: None)
    assert got["raw"]["tickers"]["ZZZ"] == {"status": "empty"}
    assert raw_bars.load_bars("ZZZ", tmp_path) is None


def test_a_store_fetched_for_another_window_is_refused(tmp_path):
    provider = FakeProvider(_both("AAA", [100.0]))
    raw_bars.fetch_bars(["AAA"], START, END, tmp_path, provider=provider, out=lambda _: None)
    with pytest.raises(ValueError, match="new --bars-root"):
        raw_bars.fetch_bars(["AAA"], START, date(2026, 10, 30), tmp_path, provider=provider,
                            out=lambda _: None)


# --- v232-4b: refusals and the bars manifest --------------------------------------

def test_bars_manifest_hashes_each_manifest_and_names_no_ticker(tmp_path):
    assert raw_bars.bars_manifest(tmp_path) == {"raw": None, "split": None}
    provider = FakeProvider(_both("AAA", [100.0]))
    raw_bars.fetch_bars(["AAA", "ZZZ"], START, END, tmp_path, provider=provider,
                        out=lambda _: None)
    got = raw_bars.bars_manifest(tmp_path)
    path = tmp_path / "raw" / "daily" / "_manifest.json"
    assert got["raw"] == {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "start": "2026-09-01", "end": "2026-09-30", "n_ok": 1, "n_empty": 1,
                          "n_unserved": 0}
    assert "AAA" not in repr(got) and "ZZZ" not in repr(got)


def test_the_refusal_vocabulary_is_frozen():
    assert raw_bars.REFUSALS == ("no_bars", "split_in_window", "bars_end_early")
    assert raw_bars.SPLIT_DRIFT == 0.01


CLOSES = [100.0 + i for i in range(10)]          # 2026-09-01 .. 2026-09-14


def test_no_bars_when_either_series_is_missing_or_ends_before_the_window():
    assert raw_bars.refusal(None, _frame(CLOSES), start=START, last_exit=None) == "no_bars"
    assert raw_bars.refusal(_frame(CLOSES), None, start=START, last_exit=None) == "no_bars"
    empty = _frame(CLOSES).iloc[0:0]
    assert raw_bars.refusal(empty, _frame(CLOSES), start=START, last_exit=None) == "no_bars"
    early = _frame(CLOSES, start="2026-08-03")
    assert raw_bars.refusal(early, early, start=START, last_exit=None) == "no_bars"


def test_a_split_after_the_window_is_a_constant_ratio_and_usable():
    raw, split = _frame(CLOSES), _frame([c / 4 for c in CLOSES])
    assert raw_bars.refusal(raw, split, start=START, last_exit=date(2026, 9, 14)) is None


def test_a_split_inside_the_window_is_refused():
    split = _frame([c / 2 if i < 5 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=START,
                            last_exit=None) == "split_in_window"


def test_a_split_before_the_window_start_is_not_in_the_window():
    split = _frame([c / 2 if i < 3 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=date(2026, 9, 4),
                            last_exit=None) is None


def test_drift_at_the_cut_off_is_usable_and_above_it_refused():
    at = _frame([c * (1.01 if i == 9 else 1.0) for i, c in enumerate(CLOSES)])
    above = _frame([c * (1.0101 if i == 9 else 1.0) for i, c in enumerate(CLOSES)])
    raw = _frame(CLOSES)
    assert raw_bars.refusal(raw, at, start=START, last_exit=None) is None
    assert raw_bars.refusal(raw, above, start=START, last_exit=None) == "split_in_window"


def test_a_split_wins_over_short_bars():
    split = _frame([c / 2 if i < 5 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=START,
                            last_exit=date(2026, 12, 1)) == "split_in_window"


def test_bars_that_end_before_the_last_live_exit_are_refused():
    raw = _frame(CLOSES)
    assert raw_bars.refusal(raw, raw, start=START,
                            last_exit=date(2026, 9, 15)) == "bars_end_early"
    assert raw_bars.refusal(raw, raw, start=START, last_exit=date(2026, 9, 14)) is None
    assert raw_bars.refusal(raw, raw, start=START, last_exit=None) is None


# --- a ticker the provider cannot serve (AlpacaMiss) --------------------------------

from swingbot.core.marketdata.providers.alpaca_provider import AlpacaMiss  # noqa: E402


class MissingProvider(FakeProvider):
    """Raises AlpacaMiss for one ticker, serves the rest."""

    def __init__(self, frames, missing="GC=F", error=AlpacaMiss):
        super().__init__(frames)
        self.missing, self.error = missing, error

    def daily_bars_between(self, tickers, start, end, *, adjustment):
        if self.missing in tickers:
            raise self.error(f"invalid symbol: {self.missing}")
        return super().daily_bars_between(tickers, start, end, adjustment=adjustment)


def test_an_alpaca_miss_is_recorded_unserved_and_the_run_continues(tmp_path):
    frames = _both("AAA", [100.0, 101.0])
    got = raw_bars.fetch_bars(["AAA", "GC=F"], START, END, tmp_path,
                              provider=MissingProvider(frames), out=lambda _: None)
    for kind in raw_bars.KINDS:
        assert got[kind]["tickers"]["GC=F"] == {"status": "unserved"}
        assert got[kind]["tickers"]["AAA"]["status"] == "ok"
        assert raw_bars.load_bars("GC=F", tmp_path, kind) is None
    assert raw_bars.load_bars("AAA", tmp_path, "raw") is not None
    assert raw_bars.refusal(raw_bars.load_bars("GC=F", tmp_path, "raw"),
                            raw_bars.load_bars("GC=F", tmp_path, "split"),
                            start=START, last_exit=None) == "no_bars"


def test_another_exception_still_propagates(tmp_path):
    provider = MissingProvider({}, error=lambda message: RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        raw_bars.fetch_bars(["GC=F"], START, END, tmp_path, provider=provider,
                            out=lambda _: None)


def test_a_restart_does_not_retry_an_unserved_ticker_and_the_manifest_works(tmp_path):
    frames = _both("AAA", [100.0])
    raw_bars.fetch_bars(["AAA", "GC=F"], START, END, tmp_path,
                        provider=MissingProvider(frames), out=lambda _: None)
    again = MissingProvider(frames)
    raw_bars.fetch_bars(["AAA", "GC=F"], START, END, tmp_path, provider=again,
                        out=lambda _: None)
    assert again.calls == []
    got = raw_bars.bars_manifest(tmp_path)["raw"]
    assert (got["n_ok"], got["n_empty"], got["n_unserved"]) == (1, 0, 1)
    assert "GC=F" not in repr(got)
