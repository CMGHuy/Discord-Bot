"""Shared protection against mixed yfinance adjustment bases in cached OHLCV."""
import logging

import pandas as pd

log = logging.getLogger("swing-bot.data_refresh")

_ADJUSTMENT_MISMATCH_TOLERANCE = 0.01
_MIN_OVERLAP_BARS = 3
_ADJUSTMENT_RATIO_DISPERSION = 0.005
_PRICE_COLUMNS = ("Open", "High", "Low", "Close")


def adjustment_ratio(existing, fresh, symbol: str, timeframe: str):
    """Return the uniform fresh/cached price ratio, if one proves an adjustment."""
    common = existing.index.intersection(fresh.index)
    if len(common) < _MIN_OVERLAP_BARS:
        return None
    ratios = (fresh.loc[common, "Close"] / existing.loc[common, "Close"]).dropna()
    ratios = ratios[ratios > 0]
    if ratios.empty:
        return None
    ratio = float(ratios.median())
    if abs(ratio - 1.0) <= _ADJUSTMENT_MISMATCH_TOLERANCE + 1e-9:
        return None
    spread = float((ratios / ratio - 1.0).abs().max())
    if spread > _ADJUSTMENT_RATIO_DISPERSION:
        log.warning(
            "%s/%s: prices disagree on %d overlapping bar(s) but not uniformly "
            "(median ratio %.4f, worst bar %.2f%% away from it); leaving cached bars untouched",
            symbol, timeframe, len(common), ratio, spread * 100,
        )
        return None
    log.warning(
        "%s/%s: adjustment-basis mismatch detected on %d overlapping bar(s) "
        "(fresh/cached price ratio %.4f); re-scaling %d cached bar(s)",
        symbol, timeframe, len(common), ratio, len(existing),
    )
    return ratio


def merge_adjusted(existing, fresh, symbol: str, timeframe: str, align_tz):
    """Union cached and fresh bars after aligning a proven adjustment change."""
    if existing is None or existing.empty:
        return fresh.copy()
    existing, fresh = align_tz(existing, fresh)
    ratio = adjustment_ratio(existing, fresh, symbol, timeframe)
    if ratio is not None:
        existing = existing.copy()
        columns = [column for column in _PRICE_COLUMNS if column in existing.columns]
        existing[columns] = existing[columns] * ratio
        if "Volume" in existing.columns:
            existing["Volume"] = existing["Volume"] / ratio
    return pd.concat([existing, fresh])[lambda frame: ~frame.index.duplicated(keep="last")].sort_index()


def adjustment_seam_issue(frame, symbol: str, timeframe: str, threshold: float = 0.20):
    """Report a likely persistent two-basis seam; never alters cached history."""
    if frame is None or frame.empty or "Close" not in frame:
        return None
    close = frame["Close"].astype(float)
    ratios = (close / close.shift(1)).replace([float("inf"), float("-inf")], pd.NA)
    candidates = ratios[(ratios - 1.0).abs() >= threshold]
    for stamp, ratio in candidates.items():
        before = close.loc[:stamp].iloc[-6:-1]
        after = close.loc[stamp:].iloc[1:6]
        if len(before) < 3 or len(after) < 3:
            continue
        before_cv = before.std() / before.mean() if before.mean() else float("inf")
        after_cv = after.std() / after.mean() if after.mean() else float("inf")
        if before_cv < 0.03 and after_cv < 0.03:
            return (f"{symbol}/{timeframe}: likely adjustment-basis seam at {stamp:%Y-%m-%d} "
                    f"({ratio:.3f}x close ratio); delete this cache file and cold-refetch")
    return None