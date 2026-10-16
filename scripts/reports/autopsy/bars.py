"""v161 TS5: autopsy cuts that read daily bars -- fill reality, open gaps,
liquidity and near-stop reversals.

Bars come only from ``bars_dir`` (files named like
``backtest_cache.cache_path``: ``<TICKER with = ^ / -> _>.csv``, columns
``Date,Open,High,Low,Close,Volume``); this module does no network I/O. A row
is bar-covered when its file exists, it has an anchor bar and the anchor close
lies within SPLIT_GUARD of the planned entry: the cache is split- and
dividend-adjusted, so a row past the guard would compare prices on two scales.

No lookahead: dollar volume ends at the plan day; the fill-day open is known
at the fill; the reversal walk reads only bars strictly after the exit day."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from pathlib import Path
from io import StringIO

import pandas as pd

from .cells import Tally
from .rows import BookRow, read_input

SPLIT_GUARD = 0.25            # fraction: anchor close vs planned entry
REVERSAL_BARS = 10            # bars after the exit day the reversal walk reads
WIDER_STOP_ATR = 0.5          # how much wider the counterfactual stop is, in ATR
DOLLAR_VOLUME_BARS = 20
GAP_FLAT_PCT = 0.25           # |open gap| at or under this is "flat"
GAP_LARGE_PCT = 1.0           # an adverse gap above this is "adverse_large"
DOLLAR_VOLUME_EDGES = ((20e6, "lt_20m"), (50e6, "20m_50m"), (200e6, "50m_200m"))
DOLLAR_VOLUME_TOP = "ge_200m"
FILLED_PLAN_STATUSES = frozenset({"ACTIVE", "PARTIAL", "CLOSED"})
FILL_STATUS_ORDER = ("filled", "expired_unfilled", "never_touched", "risk_cap",
                     "invalidated", "open", "unknown")
STOP_REASONS = frozenset({"loss", "stop"})
_CANCEL_REASONS = {"risk_cap": "risk_cap", "invalidated": "invalidated"}
# (entry_type, direction sign) -> (bar column, True when the price must reach at-or-above)
_TOUCH = {("stop_entry", 1): ("High", True), ("stop_entry", -1): ("Low", False),
          ("limit", 1): ("Low", False), ("limit", -1): ("High", True)}
_EMPTY = {"covered": False, "fill_day_open": None, "open_gap_pct": None,
          "gapped_through": None, "dollar_volume": None, "fill_status": "unknown",
          "reversal": None, "wider_stop_lost": None}


def _cache_name(ticker: str) -> str:
    """``backtest_cache.cache_path``'s file stem (not imported: its CACHE_DIR is not ours)."""
    return ticker.replace("=", "_").replace("^", "_").replace("/", "_")


def load_bars(bars_dir: Path | None, ticker: str, *,
              input_fingerprints: dict | None = None) -> pd.DataFrame | None:
    """The ticker's daily bars sorted by day, with an ISO ``day`` column; None when absent."""
    if bars_dir is None or not ticker:
        return None
    path = Path(bars_dir) / f"{_cache_name(ticker)}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(StringIO(read_input(path, input_fingerprints)))
    if df.empty or "Date" not in df.columns:
        return None
    df["day"] = df["Date"].astype(str).str[:10]
    return df.sort_values("day").reset_index(drop=True)


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def _sign(row) -> int:
    return 1 if row.direction == "bullish" else -1


def _is_closed_trade(row) -> bool:
    return row.row_kind == "trade" and row.gross_r is not None


def _index_of(days: list[str], day: str | None) -> int | None:
    if day is None:
        return None
    i = bisect_left(days, day)
    return i if i < len(days) and days[i] == day else None


def _anchor_index(days: list[str], row) -> int | None:
    """The plan-day bar; a row without a plan day anchors on the last bar before its fill."""
    if row.plan_date:
        i = bisect_right(days, _day(row.plan_date)) - 1
    elif row.entry_date:
        i = bisect_left(days, _day(row.entry_date)) - 1
    else:
        return None
    return i if i >= 0 else None


def _within_guard(df: pd.DataFrame, index: int, row) -> bool:
    ref = row.planned_entry if row.planned_entry is not None else row.entry
    if ref is None or ref <= 0:
        return False
    return abs(float(df["Close"].iloc[index]) - ref) / ref <= SPLIT_GUARD


def _dollar_volume(df: pd.DataFrame, index: int) -> float | None:
    if index + 1 < DOLLAR_VOLUME_BARS:
        return None
    window = df.iloc[index + 1 - DOLLAR_VOLUME_BARS: index + 1]
    return float((window["Close"] * window["Volume"]).mean())


def _gap(row, open_: float) -> tuple[float | None, bool | None]:
    """Open gap in percent, positive = adverse to the trade, and the gapped-through flag."""
    if row.planned_entry is None or row.planned_entry <= 0:
        return None, None
    pct = (open_ - row.planned_entry) / row.planned_entry * 100.0 * _sign(row)
    if row.entry_type == "stop_entry":
        return pct, pct > 0
    if row.entry_type == "limit":
        return pct, pct < 0
    return pct, None


def _fill_day_fields(df: pd.DataFrame, days: list[str], row) -> dict:
    if row.row_kind != "trade":
        return {}
    i = _index_of(days, _day(row.entry_date))
    if i is None:
        return {}
    open_ = float(df["Open"].iloc[i])
    pct, through = _gap(row, open_)
    return {"fill_day_open": open_, "open_gap_pct": pct, "gapped_through": through}


def _window(days: list[str], row) -> list[int]:
    """The plan's validity bars: its valid_session alone, else the expiry_bars bars after
    the plan day. Empty when the bars end before the window does."""
    if row.valid_session:
        i = _index_of(days, _day(row.valid_session))
        return [] if i is None else [i]
    if not row.plan_date:
        return []
    start = bisect_right(days, _day(row.plan_date))
    end = start + (row.expiry_bars or 1)
    return list(range(start, end)) if end <= len(days) else []


def _touched(df: pd.DataFrame, window: list[int], row) -> bool | None:
    if not window or row.planned_entry is None:
        return None
    if row.entry_type == "market":
        return True
    rule = _TOUCH.get((row.entry_type, _sign(row)))
    if rule is None:
        return None
    column, at_or_above = rule
    prices = df[column].iloc[window]
    hits = prices >= row.planned_entry if at_or_above else prices <= row.planned_entry
    return bool(hits.any())


def _plan_fill_status(row) -> str | None:
    """The status the plan record alone decides; None for an expired plan (bars decide)."""
    status = (row.plan_status or "").upper()
    if status == "PENDING":
        return "open"
    if status in FILLED_PLAN_STATUSES:
        return "filled"
    if status != "CANCELLED":
        return "unknown"
    reason = (row.plan_status_reason or "").lower()
    return None if reason == "expired" else _CANCEL_REASONS.get(reason, "unknown")


def _fill_status(row, df: pd.DataFrame | None, days: list[str], covered: bool) -> str:
    if row.row_kind == "trade":
        return "filled"
    decided = _plan_fill_status(row)
    if decided is not None:
        return decided
    touched = _touched(df, _window(days, row), row) if covered else None
    if touched is None:
        return "unknown"
    return "expired_unfilled" if touched else "never_touched"


def _stopped_out(row) -> bool:
    """A stop exit -- the same rule as ``exits.is_stop_exit`` (TS7 pins that they agree):
    the v2 leg reason ``loss`` (bucket ``stop``), or a legacy price-monitor close that lost."""
    reason = (row.close_reason or "").lower()
    if reason in STOP_REASONS:
        return True
    return reason.startswith("auto (price monitor)") and row.outcome == "loss"


def _wider_stop(row) -> float | None:
    if None in (row.entry, row.stop, row.take_profit) or not row.stop_width_atr:
        return None
    atr = abs(row.entry - row.stop) / row.stop_width_atr
    return row.stop - _sign(row) * WIDER_STOP_ATR * atr


def _walk_after(after: pd.DataFrame, row, wider: float) -> tuple[bool, bool]:
    """(reversed_to_target, wider_stop_lost): the wider stop is checked first on each bar."""
    bull = _sign(row) == 1
    for high, low in zip(after["High"], after["Low"]):
        if (low <= wider) if bull else (high >= wider):
            return False, True
        if (high >= row.take_profit) if bull else (low <= row.take_profit):
            return True, False
    return False, False


def _reversal(df: pd.DataFrame, days: list[str], row) -> tuple[bool | None, bool | None]:
    if not _is_closed_trade(row) or not _stopped_out(row) or not row.exit_date:
        return None, None
    wider = _wider_stop(row)
    if wider is None:
        return None, None
    start = bisect_right(days, _day(row.exit_date))   # strictly after the exit day
    after = df.iloc[start:start + REVERSAL_BARS]
    if len(after) < REVERSAL_BARS:
        return None, None
    return _walk_after(after, row, wider)


def _row_bars(row, df: pd.DataFrame | None) -> dict:
    out = dict(_EMPTY)
    days = df["day"].tolist() if df is not None else []
    anchor = _anchor_index(days, row) if days else None
    out["covered"] = anchor is not None and _within_guard(df, anchor, row)
    out["fill_status"] = _fill_status(row, df, days, out["covered"])
    if not out["covered"]:
        return out
    out["dollar_volume"] = _dollar_volume(df, anchor)
    out.update(_fill_day_fields(df, days, row))
    out["reversal"], out["wider_stop_lost"] = _reversal(df, days, row)
    return out


def enrich_with_bars(rows: list[BookRow], bars_dir: Path | None, *,
                     input_fingerprints: dict | None = None) -> int:
    """Fill every row's ``bars`` dict; return how many closed trades are bar-covered."""
    cache: dict[str, pd.DataFrame | None] = {}
    covered = 0
    for row in rows:
        if row.ticker not in cache:
            cache[row.ticker] = load_bars(bars_dir, row.ticker, input_fingerprints=input_fingerprints)
        row.bars = _row_bars(row, cache[row.ticker])
        covered += int(row.bars["covered"] and _is_closed_trade(row))
    return covered


def _open_gap_bucket(row) -> str | None:
    pct = row.bars.get("open_gap_pct")
    if pct is None:
        return None
    if pct < -GAP_FLAT_PCT:
        return "favourable"
    if pct <= GAP_FLAT_PCT:
        return "flat"
    return "adverse_small" if pct <= GAP_LARGE_PCT else "adverse_large"


def _gapped_through_entry(row) -> str | None:
    flag = row.bars.get("gapped_through")
    if flag is None:
        return None
    return "gapped" if flag else "not_gapped"


def _dollar_volume_bucket(row) -> str | None:
    value = row.bars.get("dollar_volume")
    if value is None:
        return None
    for edge, label in DOLLAR_VOLUME_EDGES:
        if value < edge:
            return label
    return DOLLAR_VOLUME_TOP


def _near_stop_reversal(row) -> str | None:
    reversal = row.bars.get("reversal")
    if reversal is None:
        return None
    if reversal:
        return "reversed_to_target"
    return "wider_stop_lost" if row.bars.get("wider_stop_lost") else "no_resolution"


def bar_cuts() -> tuple:
    """The four bar cuts, in ledger order: (name, key) pairs for ``cells.cut_cells``."""
    return (("open_gap_bucket", _open_gap_bucket),
            ("gapped_through_entry", _gapped_through_entry),
            ("dollar_volume_bucket", _dollar_volume_bucket),
            ("near_stop_reversal", _near_stop_reversal))


def fill_tallies(rows: list[BookRow]) -> list[Tally]:
    """Fill reality over every exported row (one row = one plan or one closed trade)."""
    counts: Counter = Counter()
    covered: Counter = Counter()
    for row in rows:
        status = row.bars.get("fill_status", "unknown")
        counts[status] += 1
        covered[status] += int(bool(row.bars.get("covered")))
    total = sum(counts.values())
    return [Tally(id=f"fill_status={s}", cut="fill_status", value=s, count=counts[s],
                  extra={"bar_covered": covered[s], "of_plans": total})
            for s in FILL_STATUS_ORDER]
