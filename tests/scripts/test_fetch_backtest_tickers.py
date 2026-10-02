"""v113 §5: --tickers fetches exactly the named tickers, no watchlist, no benchmark."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import fetch_backtest_data as fbd  # noqa: E402

from tests.helpers import make_ohlcv  # noqa: E402


def test_tickers_flag_fetches_only_the_named_tickers(tmp_path, monkeypatch):
    fetched = []

    def fake_fetch(ticker, start, end):
        fetched.append((ticker, start, end))
        return make_ohlcv([10.0] * 300)

    monkeypatch.setattr(fbd, "fetch", fake_fetch)
    monkeypatch.setattr(fbd, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(fbd, "cache_path", lambda t: tmp_path / f"{t}.csv")
    monkeypatch.setattr(fbd, "load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(sys, "argv", ["fetch_backtest_data.py", "--tickers", "sh, PSQ,RWM,DOG",
                                      "--start", "2010-01-01", "--end", "2026-09-26"])
    fbd.main()
    assert sorted(t for t, _, _ in fetched) == ["DOG", "PSQ", "RWM", "SH"]
    assert {(s, e) for _, s, e in fetched} == {("2010-01-01", "2026-09-26")}
    assert sorted(p.stem for p in tmp_path.glob("*.csv")) == ["DOG", "PSQ", "RWM", "SH"]


def test_without_the_flag_the_watchlist_and_benchmark_are_used(monkeypatch):
    from swingbot import config
    monkeypatch.setattr(fbd, "load_watchlist", lambda: ["AAPL"])
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY", raising=False)
    args = fbd.argparse.Namespace(tickers=None)
    assert fbd._tickers(args) == ["AAPL", "SPY"]
