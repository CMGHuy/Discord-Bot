"""Cut the committed v74 fixture from the local backtest cache."""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "backtest_cache"
OUT = ROOT / "tests" / "fixtures" / "v74"
TICKERS = ("AAPL", "XOM")
BARS = 500


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for symbol in TICKERS:
        source = CACHE / f"{symbol}.csv"
        if not source.exists():
            print(f"MISSING {source}")
            return 1
        frame = pd.read_csv(source, index_col=0, parse_dates=True)
        frame = frame[["Open", "High", "Low", "Close", "Volume"]].dropna().tail(BARS).round(4)
        frame.to_csv(OUT / f"{symbol}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
