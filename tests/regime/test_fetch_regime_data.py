"""v239 V239-1: the base-rate study's SPY + ^VIX cache is fetched once into
data/backtest_cache_regime/, cut at END, written with LF endings, and pinned
by a SHA-256 manifest. No test touches the network: `_download` is faked."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_regime_data as frd  # noqa: E402
from swingbot.core.marketdata.providers.base import is_alpaca_eligible  # noqa: E402
from swingbot.core.marketdata.ticker_utils import candidate_symbols  # noqa: E402

FIRST = {"SPY": "1993-01-29", "^VIX": "1993-01-04"}


def _frame(start: str, end: str) -> pd.DataFrame:
    index = pd.bdate_range(start, end, name="Date")
    close = np.linspace(40.0, 600.0, len(index))
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.full(len(index), 1e6)}, index=index)


class _Fake:
    def __init__(self, end: str = "2026-11-20", empty: tuple = ()):
        self.end, self.empty, self.calls = end, empty, []

    def __call__(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if symbol in self.empty:
            return None
        return _frame(FIRST[symbol], self.end)


@pytest.fixture
def fake(monkeypatch):
    stub = _Fake()
    monkeypatch.setattr(frd, "_download", stub)
    return stub


def test_constants_are_the_ledger_contract():
    assert frd.START == "1993-01-01" and frd.END == "2026-11-20"
    assert frd.SYMBOLS == ("SPY", "^VIX") and frd.MANIFEST == "manifest.json"
    assert frd.CACHE_DIR == frd.ROOT / "data" / "backtest_cache_regime"
    assert frd.csv_path(Path("x"), "^VIX") == Path("x") / "^VIX.csv"


def test_vix_is_served_by_yfinance_not_the_alpaca_router():
    # spec reconciliation 1: the live pass reads ^VIX through get_daily_data,
    # which only reaches yfinance because the caret fails the Alpaca shape.
    assert is_alpaca_eligible("^VIX") is False
    assert is_alpaca_eligible("SPY") is True
    assert candidate_symbols("^VIX") == ["^VIX"]


def test_main_writes_both_csvs_and_a_manifest_whose_hashes_match(tmp_path, fake):
    assert frd.main(["--cache-dir", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["symbols"]) == {"SPY", "^VIX"}
    for symbol in frd.SYMBOLS:
        path = frd.csv_path(tmp_path, symbol)
        entry = manifest["symbols"][symbol]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        written = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        assert entry["rows"] == len(written)
        assert entry["first"] == FIRST[symbol] and entry["last"] == "2026-11-20"
        assert list(written.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert manifest["command"].startswith("python scripts/data/fetch_regime_data.py")
    assert manifest["fetched_at"].endswith("+00:00")


def test_end_is_requested_exclusive_and_later_rows_are_cut(tmp_path, monkeypatch):
    stub = _Fake(end="2026-11-24")
    monkeypatch.setattr(frd, "_download", stub)
    assert frd.main(["--cache-dir", str(tmp_path)]) == 0
    assert {c[2] for c in stub.calls} == {"2026-11-21"}  # yfinance `end` is exclusive
    assert {c[1] for c in stub.calls} == {"1993-01-01"}
    written = pd.read_csv(frd.csv_path(tmp_path, "SPY"), parse_dates=["Date"], index_col="Date")
    assert written.index[-1] == pd.Timestamp("2026-11-20")


def test_csv_files_are_lf_only(tmp_path, fake):
    frd.main(["--cache-dir", str(tmp_path)])
    for symbol in frd.SYMBOLS:
        assert b"\r\n" not in frd.csv_path(tmp_path, symbol).read_bytes()


def test_refuses_when_the_manifest_exists_and_fetches_nothing(tmp_path, fake, capsys):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert fake.calls == []
    assert "refusing" in capsys.readouterr().out


def test_force_overwrites_an_existing_cache(tmp_path, fake):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert frd.main(["--cache-dir", str(tmp_path), "--force"]) == 0
    assert "symbols" in json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("stub", [_Fake(end="2026-11-19"), _Fake(empty=("^VIX",))])
def test_a_short_or_empty_symbol_writes_nothing_at_all(tmp_path, monkeypatch, stub):
    monkeypatch.setattr(frd, "_download", stub)
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []


def test_a_late_first_bar_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(frd, "_download", lambda s, a, b: _frame("1999-01-04", "2026-11-20"))
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert not (tmp_path / "manifest.json").exists()


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes(b"Date,Close\n2026-11-20,1.0\n")
    assert frd.sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_manifest_returns_what_it_wrote(tmp_path):
    frame = _frame("1993-01-29", "1993-03-01")
    frame.to_csv(frd.csv_path(tmp_path, "SPY"), lineterminator="\n")
    out = frd.write_manifest(tmp_path, {"SPY": frame}, "python scripts/data/fetch_regime_data.py")
    assert out == json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert out["symbols"]["SPY"]["rows"] == len(frame)
