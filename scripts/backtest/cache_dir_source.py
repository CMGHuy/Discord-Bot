"""v162: the --cache-dir rule shared by the measure_* scripts that take one.

`--cache-dir DIR` names a yfinance-shaped CSV directory (a Date index, one
<SYMBOL>.csv per ticker). It pins the yfinance source and every frame is read
from DIR exactly as before v162, so a closed pre-registration's recorded run
reproduces. Without it, frames come from the training-data switch: the
script's --data-source, else yfinance when BACKTEST_CACHE_DIR is set, else
TRAINING_DATA_SOURCE (training_data.select). The switch changes where bars come
from, never what may be re-run: a closed component re-measured on Alpaca bars
is the same hypothesis (backtest-methodology.md § Closed pre-registrations).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
for _path in (ROOT, ROOT / "scripts" / "data"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fetch_backtest_data import add_data_source_arg, apply_data_source  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.backtest_cache import cache_path  # noqa: E402

CACHE_DIR_HELP = ("a yfinance-shaped OHLCV CSV directory; pins the yfinance source. "
                  "Default: the training-data switch (--data-source, else "
                  "TRAINING_DATA_SOURCE).")


def add_args(ap) -> None:
    """--data-source; each script keeps its own --cache-dir (default None)."""
    add_data_source_arg(ap)


def as_dir(value) -> Path | None:
    return Path(value) if value else None


def resolve(args) -> Path | None:
    """Apply the rule and return the explicit directory, or None for the switch."""
    cache_dir = as_dir(getattr(args, "cache_dir", None))
    if cache_dir is None:
        apply_data_source(args)
        return None
    if getattr(args, "data_source", None) == "alpaca":
        raise SystemExit("error: --cache-dir reads a yfinance-shaped CSV directory; "
                         "drop it to read the Alpaca store")
    training_data.select("yfinance")
    print(f"training data: yfinance (--cache-dir {cache_dir})", flush=True)
    return cache_dir


def load_frame(cache_dir, symbol: str) -> pd.DataFrame | None:
    if cache_dir is None:
        return training_data.load_daily(symbol)
    path = Path(cache_dir) / cache_path(symbol).name
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col="Date", parse_dates=True)
    return frame if len(frame) else None


def listing(cache_dir) -> list[str]:
    if cache_dir is None:
        return training_data.available_tickers()
    return sorted(p.stem for p in Path(cache_dir).glob("*.csv"))


def load_all(cache_dir, limit: int | None = None) -> dict:
    """{ticker: frame}. A directory is globbed and read exactly as the scripts
    did before v162 (first `limit` paths, empty files kept); the switch gives
    the first `limit` training tickers that load."""
    if cache_dir is not None:
        paths = sorted(Path(cache_dir).glob("*.csv"))[:limit]
        return {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True) for p in paths}
    tickers = training_data.available_tickers()[:limit]
    return {t: f for t in tickers if (f := training_data.load_daily(t)) is not None}


def cache_files(cache_dir) -> list[str]:
    """What a run.json records under cache_files: a resume on other data is refused."""
    if cache_dir is None:
        return [f"{ticker}.csv" for ticker in training_data.available_tickers()]
    return sorted(p.name for p in Path(cache_dir).glob("*.csv"))


def describe(cache_dir) -> str:
    return str(cache_dir) if cache_dir is not None else f"the {training_data.active()} training data"


def pool_kwargs() -> dict:
    """Hand a spawned pool worker the parent's selection (spawn re-imports)."""
    return {"initializer": training_data.select, "initargs": (training_data.active(),)}
