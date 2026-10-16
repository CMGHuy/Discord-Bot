"""Identity check and skip classification (v162 spec §2).

One bad fetch can hand a ticker another instrument's history
(known-traps.md, "The market_data cache never self-heals"), and Alpaca serves
reused tickers' old histories (SNDK). So a fresh daily frame is compared with
data/backtest_cache/<SAFE>.csv (fallback: the root market_data/daily cache):
the median fresh/reference close ratio over at least MIN_IDENTITY_OVERLAP
finite bars must lie within ALPACA_TOLERANCE of 1. A disagreeing ticker is
still written, but flagged; training leaves flagged tickers out.
"""
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from swingbot.core.marketdata.data_store import safe_symbol
from swingbot.core.marketdata.providers.base import NY, is_alpaca_eligible
from swingbot.core.marketdata.spot_metals import is_spot_metal

_OPS = Path(__file__).resolve().parents[2] / "ops"
if str(_OPS) not in sys.path:
    sys.path.append(str(_OPS))
from market_cache_repair import ALPACA_TOLERANCE, close_ratios  # noqa: E402

MIN_IDENTITY_OVERLAP = 250
OK = "ok"
NO_REFERENCE = "flagged: no-reference"
SHORT_OVERLAP = "flagged: short-overlap"
PRICE_MISMATCH = "flagged: price-mismatch"


def skip_reason(ticker: str) -> str | None:
    """The manifest status for a symbol Alpaca cannot serve, else None."""
    symbol = (ticker or "").upper().strip()
    if is_spot_metal(symbol):
        return "skipped: spot metal (built from futures)"
    if symbol.endswith("=F"):
        return "skipped: futures"
    if symbol.startswith("^"):
        return "skipped: index"
    if not is_alpaca_eligible(symbol):
        return "skipped: not Alpaca-eligible"
    return None


def _naive_dates(values) -> pd.DatetimeIndex:
    """Naive midnight dates from a CSV index that may carry a UTC offset."""
    try:
        index = pd.DatetimeIndex(pd.to_datetime(values))
    except (ValueError, TypeError):
        index = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    if index.tz is not None:
        index = index.tz_convert(NY).tz_localize(None)
    return index.normalize()


def _read_reference(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    raw = pd.read_csv(path, index_col=0)
    if raw.empty or "Close" not in raw.columns:
        return None
    frame = pd.DataFrame({"Close": pd.to_numeric(raw["Close"], errors="coerce").to_numpy()},
                         index=_naive_dates(raw.index))
    frame.index.name = "Date"
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index()


def reference_frame(ticker: str, *, backtest_dir: Path, market_dir: Path) -> pd.DataFrame | None:
    name = f"{safe_symbol(ticker)}.csv"
    for folder in (backtest_dir, market_dir):
        frame = _read_reference(Path(folder) / name)
        if frame is not None:
            return frame
    return None


@dataclass(frozen=True)
class IdentityResult:
    status: str
    median_ratio: float | None
    overlap: int
    dropped_before: str | None

    def to_json(self) -> dict:
        out = asdict(self)
        if out["median_ratio"] is not None:
            out["median_ratio"] = round(out["median_ratio"], 6)
        return out


def _unique(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[~frame.index.duplicated(keep="last")]


def _finite_ratios(fresh: pd.DataFrame, reference: pd.DataFrame) -> list[float]:
    """fresh/reference close per overlapping bar, NaN-safe: close_ratios
    already skips a NaN or non-positive reference close; a NaN or
    non-positive fresh close is dropped here."""
    _, _, ratios = close_ratios(_unique(reference), _unique(fresh))
    return [r for r in ratios if math.isfinite(r) and r > 0]


def _trim(fresh: pd.DataFrame, first_reference_bar) -> tuple[pd.DataFrame, str | None]:
    if fresh.empty or fresh.index.min() >= first_reference_bar:
        return fresh, None
    return fresh[fresh.index >= first_reference_bar], first_reference_bar.strftime("%Y-%m-%d")


def _verdict(ratios: list[float]) -> tuple[str, float | None]:
    median = statistics.median(ratios) if ratios else None
    if len(ratios) < MIN_IDENTITY_OVERLAP:
        return SHORT_OVERLAP, median
    return (OK if abs(median - 1) <= ALPACA_TOLERANCE else PRICE_MISMATCH), median


def identity_check(fresh: pd.DataFrame, reference: pd.DataFrame | None
                   ) -> tuple[IdentityResult, pd.DataFrame]:
    """(result, fresh without the bars before the reference's first bar)."""
    if reference is None or reference.empty:
        return IdentityResult(NO_REFERENCE, None, 0, None), fresh
    kept, dropped_before = _trim(fresh, reference.index.min())
    ratios = _finite_ratios(kept, reference)
    status, median = _verdict(ratios)
    return IdentityResult(status, median, len(ratios), dropped_before), kept
