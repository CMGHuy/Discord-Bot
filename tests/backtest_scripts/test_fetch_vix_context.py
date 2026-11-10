"""v211 V211-2: ^VIX context is fetched once, stored as ^VIX.csv (never
_VIX.csv), and refused unless its dates equal SPY's sessions exactly."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_backtest_data as fbd  # noqa: E402
from swingbot.core.backtesting.screen.context import ContextError  # noqa: E402

START, END = "2009-05-01", "2009-07-31"
HEADER = "Date,Open,High,Low,Close,Volume"


def _ohlcv(index) -> pd.DataFrame:
    index = pd.DatetimeIndex(index, name="Date")
    close = np.linspace(20.0, 30.0, len(index))
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.zeros(len(index))}, index=index)


def _sessions() -> pd.DatetimeIndex:
    return pd.bdate_range(START, END)


def _with_spy(tmp_path: Path) -> Path:
    _ohlcv(_sessions()).to_csv(tmp_path / "SPY.csv")
    return tmp_path


def _fetcher(index, calls=None):
    def fake(ticker, start, end):
        if calls is not None:
            calls.append((ticker, start, end))
        return _ohlcv(index)
    return fake


def test_the_path_keeps_the_caret(tmp_path):
    assert fbd.VIX_CONTEXT == "^VIX"
    assert fbd.vix_context_path(tmp_path) == tmp_path / "^VIX.csv"


def test_fetch_writes_caret_vix_aligned_to_spy(tmp_path):
    calls = []
    path = fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END,
                                 fetcher=_fetcher(_sessions(), calls))
    assert path == tmp_path / "^VIX.csv"
    assert not (tmp_path / "_VIX.csv").exists()
    assert calls == [("^VIX", START, "2009-08-01")]        # yfinance end is exclusive
    assert path.read_text(encoding="utf-8").splitlines()[0] == HEADER
    written = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    assert written.index.equals(_sessions())


def test_a_missing_session_refuses_and_writes_nothing(tmp_path):
    index = _sessions().drop(pd.Timestamp("2009-06-15"))
    with pytest.raises(ContextError, match="missing"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))
    assert not (tmp_path / "^VIX.csv").exists()


def test_an_extra_bar_refuses(tmp_path):
    index = _sessions().append(pd.DatetimeIndex(["2009-06-13"])).sort_values()  # a Saturday
    with pytest.raises(ContextError, match="extra"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))


def test_dates_before_the_context_start_are_not_checked(tmp_path):
    index = _sessions().drop(pd.Timestamp("2009-05-04"))   # before CONTEXT_START 2009-06-01
    path = fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=_fetcher(index))
    assert path.exists()


def test_a_nan_row_counts_as_missing(tmp_path):
    def fake(ticker, start, end):
        frame = _ohlcv(_sessions())
        frame.loc[pd.Timestamp("2009-06-15"), "Close"] = np.nan
        return frame
    with pytest.raises(ContextError, match="missing"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END, fetcher=fake)


def test_no_spy_file_refuses(tmp_path):
    with pytest.raises(ContextError, match="SPY"):
        fbd.fetch_vix_context(tmp_path, start=START, end=END, fetcher=_fetcher(_sessions()))


def test_an_empty_fetch_refuses(tmp_path):
    with pytest.raises(ContextError, match="no data"):
        fbd.fetch_vix_context(_with_spy(tmp_path), start=START, end=END,
                              fetcher=lambda ticker, start, end: None)


def test_check_rejects_a_repeated_date():
    index = _sessions().append(pd.DatetimeIndex(["2009-06-15"])).sort_values()
    with pytest.raises(ContextError, match="not unique"):
        fbd.check_vix_sessions(index, _sessions(), end=END)


def _argv(tmp_path, *extra):
    return ["--vix-context", "--cache-dir", str(tmp_path), "--start", START, "--end", END, *extra]


def test_cli_refuses_an_existing_file_without_force(tmp_path, monkeypatch, capsys):
    _with_spy(tmp_path)
    (tmp_path / "^VIX.csv").write_text("old", encoding="utf-8")
    calls = []
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions(), calls))
    assert fbd.vix_context_main(_argv(tmp_path)) == 2
    assert (tmp_path / "^VIX.csv").read_text(encoding="utf-8") == "old"
    assert calls == []
    assert "--force" in capsys.readouterr().out


def test_cli_force_overwrites_and_a_failed_check_keeps_the_file(tmp_path, monkeypatch):
    _with_spy(tmp_path)
    (tmp_path / "^VIX.csv").write_text("old", encoding="utf-8")
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions()))
    assert fbd.vix_context_main(_argv(tmp_path, "--force")) == 0
    good = (tmp_path / "^VIX.csv").read_text(encoding="utf-8")
    assert good.splitlines()[0] == HEADER
    monkeypatch.setattr(fbd, "fetch", _fetcher(_sessions().drop(pd.Timestamp("2009-06-15"))))
    assert fbd.vix_context_main(_argv(tmp_path, "--force")) == 2
    assert (tmp_path / "^VIX.csv").read_text(encoding="utf-8") == good


def test_entry_dispatches_the_vix_mode_and_leaves_main_alone(monkeypatch):
    seen = []
    monkeypatch.setattr(fbd, "vix_context_main", lambda argv: seen.append(("vix", argv)) or 0)
    monkeypatch.setattr(fbd, "main", lambda: seen.append(("main", None)))
    assert fbd._entry(["--vix-context", "--cache-dir", "x"]) == 0
    fbd._entry(["--tickers", "SPY"])
    assert seen == [("vix", ["--vix-context", "--cache-dir", "x"]), ("main", None)]
