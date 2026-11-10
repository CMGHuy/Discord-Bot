"""v211 V211-3: build_breadth_context.py writes <cache-dir>/BREADTH_ATR1.csv on
SPY's sessions from CONTEXT_START, point in time, and never overwrites it."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import build_breadth_context as bbc  # noqa: E402
from swingbot.core.backtesting.screen import context as screen_context  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

HEADER = "Date,Open,High,Low,Close,Volume"
END = "2009-12-31"


def _cache(tmp_path: Path) -> tuple[Path, Path]:
    cache = tmp_path / "cache"
    cache.mkdir()
    random_walk(300, seed=1, start="2009-01-02").to_csv(cache / "SPY.csv", index_label="Date")
    random_walk(300, seed=2, start="2009-01-02").to_csv(cache / "AAA.csv", index_label="Date")
    random_walk(300, seed=3, start="2009-01-02").to_csv(cache / "BRK-B.csv", index_label="Date")
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n"
                          "AAA,2000-01-03,\n"
                          "BRK.B,2000-01-03,2009-09-01\n"          # normalised to BRK-B, leaves 09-01
                          "CCC,2000-01-03,\n", encoding="utf-8")   # a PIT member without a cache file
    return cache, membership


def _spy_sessions(cache: Path) -> pd.DatetimeIndex:
    spy = pd.read_csv(cache / "SPY.csv", parse_dates=["Date"], index_col="Date").index
    return spy[(spy >= pd.Timestamp(screen_context.CONTEXT_START)) & (spy <= pd.Timestamp(END))]


def test_builds_breadth_on_spy_sessions(tmp_path, capsys):
    cache, membership = _cache(tmp_path)
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 0
    out = cache / "BREADTH_ATR1.csv"
    assert out.read_text(encoding="utf-8").splitlines()[0] == HEADER
    raw = pd.read_csv(out, parse_dates=["Date"], index_col="Date")
    screen_context.check_raw_index(raw.index, "BREADTH_ATR1")
    sessions = _spy_sessions(cache)
    screen_context.check_contiguous(raw.index, sessions, "BREADTH_ATR1")
    assert raw["Close"].between(0.0, 1.0).all()
    assert raw.loc[: "2009-08-31", "Volume"].max() == 2
    assert raw.loc["2009-09-01":, "Volume"].max() == 1         # BRK-B left the index
    printed = capsys.readouterr().out
    assert "2009:" in printed
    assert "1 PIT member(s) without a cache file" in printed


def test_refuses_an_existing_output(tmp_path, capsys):
    cache, membership = _cache(tmp_path)
    (cache / "BREADTH_ATR1.csv").write_text("old", encoding="utf-8")
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 2
    assert (cache / "BREADTH_ATR1.csv").read_text(encoding="utf-8") == "old"
    assert "exists" in capsys.readouterr().out


def test_out_path_is_honoured(tmp_path):
    cache, membership = _cache(tmp_path)
    target = tmp_path / "elsewhere.csv"
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership),
                     "--end", END, "--out", str(target)]) == 0
    assert target.exists() and not (cache / "BREADTH_ATR1.csv").exists()


def test_refuses_without_spy_or_membership(tmp_path):
    cache, membership = _cache(tmp_path)
    empty = tmp_path / "empty.csv"
    empty.write_text("ticker,start_date,end_date\n", encoding="utf-8")
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(empty), "--end", END]) == 2
    (cache / "SPY.csv").unlink()
    assert bbc.main(["--cache-dir", str(cache), "--membership", str(membership), "--end", END]) == 2
