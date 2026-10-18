"""v171 D4: the proven delta splice over two single-basis daily caches.

Two caches, one basis per file, frames never cross:
  * ``alpaca-all``: ``market_data/daily_alpaca/<SYM>_daily.csv``, Alpaca SIP
    daily bars, ``Adjustment.ALL``, for every symbol the scan routes to Alpaca.
  * ``yfinance-auto_adjust``: the existing ``market_data/daily/<SYM>.csv``
    (yfinance ``auto_adjust=True``), for every other symbol.
Each CSV has a sidecar ``<csv stem>.meta.json`` (``DailyMeta``).

Rules (per file, on its own basis):

  cold     no CSV -> "cold"; no or unreadable sidecar -> "no-meta"; sidecar
           basis != file basis -> "basis"; window longer than
           DELTA_WINDOW_MAX_DAYS -> "window-cap". Each goes straight to a full
           refetch on the same basis.
  window   one fetch_window(warm, min(starts), today, basis) per basis per call;
           a symbol's window starts MIN_OVERLAP_BARS + 2 business days before
           its last_verified bar.
  anchor   symbols whose sidecar anchor_checked != today: one
           fetch_window(due, anchor_date, anchor_date + 7 days, basis) per
           (basis, anchor_date). A failed anchor fetch leaves the symbol due.
  refetch  needs_full_refetch, in order: yfinance basis, a non-zero Dividends /
           Stock Splits row dated after last_full_fetch -> "event"; the fresh
           anchor close off the sidecar's by more than DELTA_OVERLAP_TOLERANCE
           -> "anchor"; fewer than MIN_OVERLAP_BARS common bars dated <=
           last_verified -> "overlap-short"; any common close off by more than
           DELTA_OVERLAP_TOLERANCE -> "overlap-mismatch". A refusal is logged
           and refetched in full from the file's own provider, never through
           history_splice's live-only path.
  write    only bars dated before today; a union (merge_adjusted for a delta,
           _union_full for a full fetch), never shallower than the file.
  misses   a warm window miss serves the cached frame unchanged; a cold
           alpaca-all full miss goes to the yfinance basis for this call
           (tagged yfinance-fallback); a refused symbol's full miss serves its
           cached frame; BudgetDeferred counts as a miss.
  spot     XAUUSD / XAGUSD are dropped before any fetch; write_daily refuses them.

NO-LOOKAHEAD: nothing is ever placed after the provider frame's last bar, and
the forming bar (dated today) is returned in memory only, never persisted.

One writer: ``write_daily``, under the key's lease.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from datetime import date, datetime, timedelta

import pandas as pd

from swingbot import config
from swingbot.core.infra.jsonio import atomic_write_json, read_json
from swingbot.core.marketdata import data_store, spot_metals, yf_safe
from swingbot.core.marketdata.adjustments import (
    _ADJUSTMENT_RATIO_DISPERSION, DELTA_OVERLAP_TOLERANCE, MIN_OVERLAP_BARS, merge_adjusted)
from swingbot.core.marketdata.data_store import OHLCV_COLUMNS
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.providers.base import (
    NY, SOURCE_ALPACA, SOURCE_FALLBACK, SOURCE_YF, is_alpaca_eligible)
from swingbot.core.marketdata.shared import counters, layer
from swingbot.core.marketdata.shared.kinds import PROVIDER_ALPACA, PROVIDER_YF, Asker, DataKind

log = logging.getLogger(__name__)

BASIS_ALPACA = "alpaca-all"
BASIS_YF = "yfinance-auto_adjust"
_SOURCES = {BASIS_ALPACA: {SOURCE_ALPACA}, BASIS_YF: {SOURCE_YF, SOURCE_FALLBACK}}
_WINDOW_BDAYS = MIN_OVERLAP_BARS + 2
_ANCHOR_SPAN_DAYS = 7
_LEASE_DEADLINE_S = 10.0
_RESCALE_BARS = 20
_OHLC = ["Open", "High", "Low", "Close"]
_ACTIONS = ("Dividends", "Stock Splits")


@dataclasses.dataclass(frozen=True)
class DailyMeta:
    basis: str
    last_full_fetch: str | None
    last_verified: str | None
    anchor_date: str | None
    anchor_close: float | None
    anchor_checked: str | None = None


_REQUIRED = ("basis", "last_full_fetch", "last_verified", "anchor_date", "anchor_close")


def _today_ny() -> date:
    return datetime.now(NY).date()


# -- paths and sidecar ------------------------------------------------------------


def basis_for(ticker: str) -> str:
    """The cache this symbol lives in: the one the scan routes it to."""
    if config.ALPACA_ENABLED and is_alpaca_eligible(ticker):
        return BASIS_ALPACA
    return BASIS_YF


def cache_file(ticker: str, basis: str) -> str:
    if basis == BASIS_ALPACA:
        return os.path.join(data_store.ALPACA_DAILY_DIR, f"{data_store.safe_symbol(ticker)}_daily.csv")
    return data_store.cache_path(ticker, "daily")


def meta_path(ticker: str, basis: str) -> str:
    return os.path.splitext(cache_file(ticker, basis))[0] + ".meta.json"


def read_meta(ticker: str, basis: str) -> DailyMeta | None:
    """The sidecar, or None when it is missing, unreadable or incomplete."""
    raw = read_json(meta_path(ticker, basis), None)
    if not isinstance(raw, dict) or any(k not in raw for k in _REQUIRED):
        return None
    try:
        return DailyMeta(**{k: raw[k] for k in _REQUIRED}, anchor_checked=raw.get("anchor_checked"))
    except TypeError:
        return None


def _write_meta(ticker: str, basis: str, meta: DailyMeta) -> None:
    atomic_write_json(meta_path(ticker, basis), dataclasses.asdict(meta))


def read_daily(ticker: str, basis: str | None = None) -> pd.DataFrame | None:
    basis = basis or basis_for(ticker)
    return data_store.load_normalized_file(cache_file(ticker, basis), label=f"{ticker}/{basis}")


# -- the rules --------------------------------------------------------------------


def delta_window(meta: DailyMeta, today: date) -> tuple[date, date] | None:
    """(start, today), or None when the gap is past DELTA_WINDOW_MAX_DAYS."""
    start = (pd.Timestamp(meta.last_verified) - pd.offsets.BDay(_WINDOW_BDAYS)).date()
    if (today - start).days > int(config.DELTA_WINDOW_MAX_DAYS):
        return None
    return start, today


def _action_after(window: pd.DataFrame, last_full_fetch: str | None) -> bool:
    if not last_full_fetch:
        return False
    after = window[window.index > pd.Timestamp(last_full_fetch)]
    for column in _ACTIONS:
        if column in after.columns and (after[column].fillna(0.0) != 0.0).any():
            return True
    return False


def _anchor_moved(anchor_close: float, meta: DailyMeta) -> bool:
    if not meta.anchor_close:
        return False
    return abs(anchor_close / float(meta.anchor_close) - 1.0) > DELTA_OVERLAP_TOLERANCE


def _overlap_reason(cached: pd.DataFrame, window: pd.DataFrame, last_verified: str) -> str | None:
    verified = cached[cached.index <= pd.Timestamp(last_verified)]
    common = verified.index.intersection(window.index)
    if len(common) < MIN_OVERLAP_BARS:
        return "overlap-short"
    rel = (window.loc[common, "Close"].astype(float) / verified.loc[common, "Close"].astype(float) - 1.0).abs()
    if rel.isna().any() or (rel > DELTA_OVERLAP_TOLERANCE).any():
        return "overlap-mismatch"
    return None


def needs_full_refetch(cached: pd.DataFrame, window: pd.DataFrame, meta: DailyMeta,
                       anchor_close: float | None = None) -> str | None:
    """The refusal reason for splicing `window` onto `cached`, or None."""
    if meta.basis == BASIS_YF and _action_after(window, meta.last_full_fetch):
        return "event"
    if anchor_close is not None and _anchor_moved(anchor_close, meta):
        return "anchor"
    return _overlap_reason(cached, window, meta.last_verified)


# -- the one writer -----------------------------------------------------------------


def _naive(df: pd.DataFrame) -> pd.DataFrame:
    """A copy over a tz-naive, de-duplicated, sorted DatetimeIndex (all columns)."""
    out = df.copy()
    index = pd.DatetimeIndex(out.index)
    out.index = index.tz_localize(None) if index.tz is not None else index
    return out[~out.index.duplicated(keep="last")].sort_index()


def _ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = _naive(df[OHLCV_COLUMNS].astype("float64"))
    out.attrs = {}
    return out


def _rescaled(kept: pd.DataFrame, existing: pd.DataFrame, fresh: pd.DataFrame,
              ticker: str) -> pd.DataFrame:
    """`kept` (cached bars older than the fresh span) on the fresh basis, when the
    oldest common closes prove one ratio; unscaled otherwise."""
    common = existing.index.intersection(fresh.index).sort_values()[:_RESCALE_BARS]
    ratios = (fresh.loc[common, "Close"] / existing.loc[common, "Close"]).dropna()
    ratios = ratios[ratios > 0]
    if len(ratios) < MIN_OVERLAP_BARS:
        log.warning("daily %s: %d older cached bar(s) kept unscaled (only %d common bar(s) to prove a ratio)",
                    ticker, len(kept), len(ratios))
        return kept
    ratio = float(ratios.median())
    if abs(ratio - 1.0) <= DELTA_OVERLAP_TOLERANCE:
        return kept
    if float((ratios / ratio - 1.0).abs().max()) > _ADJUSTMENT_RATIO_DISPERSION:
        log.warning("daily %s: %d older cached bar(s) kept unscaled (ratio %.6f not uniform)",
                    ticker, len(kept), ratio)
        return kept
    kept = kept.copy()
    kept[_OHLC] = kept[_OHLC] * ratio
    kept["Volume"] = kept["Volume"] / ratio
    return kept


def _union_full(existing: pd.DataFrame | None, fresh: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """Fresh wins on its span; older cached bars are kept (rescaled when proven)."""
    if existing is None or existing.empty:
        return fresh
    if fresh.empty:
        return existing
    kept = existing[existing.index < fresh.index.min()]
    if kept.empty:
        return fresh
    out = pd.concat([_rescaled(kept, existing, fresh, ticker), fresh])
    return out[~out.index.duplicated(keep="last")].sort_index()


def _anchor_of(frame: pd.DataFrame) -> tuple[str | None, float | None]:
    rows = frame[frame.index >= pd.Timestamp(config.ALPACA_ANCHOR_DATE)]
    if rows.empty:
        return None, None
    return rows.index[0].date().isoformat(), float(rows["Close"].iloc[0])


def _next_meta(prev: DailyMeta | None, merged: pd.DataFrame, basis: str, full: bool,
               today: date, anchor_checked: str | None) -> DailyMeta | None:
    closed = merged[merged.index < pd.Timestamp(today)]
    last_verified = closed.index.max().date().isoformat() if not closed.empty else None
    if full:
        anchor_date, anchor_close = _anchor_of(merged)
        return DailyMeta(basis=basis, last_full_fetch=today.isoformat(), last_verified=last_verified,
                         anchor_date=anchor_date, anchor_close=anchor_close,
                         anchor_checked=today.isoformat())
    if prev is None:
        return None      # no sidecar to carry: the next delta refetches in full ("no-meta")
    return dataclasses.replace(prev, last_verified=last_verified or prev.last_verified,
                               anchor_checked=anchor_checked or prev.anchor_checked)


def _check_source(ticker: str, fresh: pd.DataFrame, basis: str) -> None:
    src = fresh.attrs.get("source")
    if src not in _SOURCES[basis]:
        raise ValueError(f"{ticker}: a {src!r} frame cannot be written to the {basis} cache")


def write_daily(ticker: str, fresh: pd.DataFrame, *, basis: str, full: bool,
                today: date | None = None, anchor_checked: str | None = None) -> pd.DataFrame | None:
    """The one writer of both daily caches. Persists `fresh`'s bars dated before
    `today` as a union with the file, under the key's lease, then the sidecar.
    Returns the persisted frame."""
    data_store.refuse_spot_write(ticker)
    _check_source(ticker, fresh, basis)
    today = today or _today_ny()
    closed = _ohlcv(fresh)
    closed = closed[closed.index < pd.Timestamp(today)]
    if closed.empty and not full:
        return read_daily(ticker, basis)
    with layer.lease(DataKind.DAILY_BARS, ticker, asker=Asker.BACKGROUND,
                     deadline_s=_LEASE_DEADLINE_S) as held:
        if not held:
            counters.warn_fail_open("daily-write", RuntimeError("lease not held"))
        existing = read_daily(ticker, basis)
        if full:
            merged = _union_full(existing, closed, ticker)
        else:
            merged = merge_adjusted(existing, closed, ticker, "daily", data_store._align_tz)
        if merged is None or merged.empty:
            return existing
        data_store.atomic_write_csv(merged, cache_file(ticker, basis))
        meta = _next_meta(read_meta(ticker, basis), merged, basis, full, today, anchor_checked)
        if meta is not None:
            _write_meta(ticker, basis, meta)
    return merged


def _mark_anchor_checked(ticker: str, basis: str, today: date) -> None:
    """Sidecar-only write (no new closed bar): the anchor was checked today."""
    with layer.lease(DataKind.DAILY_BARS, ticker, asker=Asker.BACKGROUND,
                     deadline_s=_LEASE_DEADLINE_S) as held:
        if not held:
            counters.warn_fail_open("daily-write", RuntimeError("lease not held"))
        meta = read_meta(ticker, basis)
        if meta is not None:
            _write_meta(ticker, basis, dataclasses.replace(meta, anchor_checked=today.isoformat()))


# -- default providers (module level: a spawned worker can call them) --------------


def _count(provider: str, asked: int, got: int) -> None:
    asker = router.current_asker()
    if got:
        counters.count(provider, DataKind.DAILY_BARS, asker, "fetched", n=got)
    if asked - got:
        counters.count(provider, DataKind.DAILY_BARS, asker, "failed", n=asked - got)


def _alpaca_only(frames: dict) -> dict:
    return {t: df for t, df in frames.items() if df.attrs.get("source") == SOURCE_ALPACA}


def _yf_frames(tickers: list[str], **kwargs) -> dict:
    """One batched yfinance download (auto_adjust, actions), sliced per ticker."""
    try:
        raw = yf_safe.download(" ".join(tickers), interval="1d", group_by="ticker",
                               auto_adjust=True, actions=True, progress=False, **kwargs)
    except yf_safe.BudgetDeferred:
        raise
    except Exception as exc:  # noqa: BLE001 - DownloadBusy or a network failure: a miss
        log.info("daily delta: yfinance download skipped for %d ticker(s): %s", len(tickers), exc)
        return {}
    if raw is None or raw.empty:
        return {}
    out = {}
    for ticker in tickers:
        try:
            sub = raw[ticker].dropna(how="all", subset=_OHLC)
        except KeyError:
            continue
        if not sub.empty:
            sub.attrs["source"] = SOURCE_YF
            out[ticker] = sub
    return out


def provider_window(tickers: list[str], start: date, end: date, basis: str) -> dict[str, pd.DataFrame]:
    if basis == BASIS_ALPACA:
        got, provider = _alpaca_only(router.daily_bars_between(tickers, start, end)), PROVIDER_ALPACA
    else:
        got = _yf_frames(tickers, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
        provider = PROVIDER_YF
    _count(provider, len(tickers), len(got))
    return got


def provider_full(tickers: list[str], basis: str) -> dict[str, pd.DataFrame]:
    if basis == BASIS_ALPACA:
        frames = router.daily_bars(tickers, config.DEFAULT_HISTORY_PERIOD, lambda ts, p: {})
        got, provider = _alpaca_only(frames), PROVIDER_ALPACA
    else:
        got, provider = _yf_frames(tickers, period="max"), PROVIDER_YF
    _count(provider, len(tickers), len(got))
    return got


# -- delta_update / full_refetch ------------------------------------------------------


def _plain(tickers) -> list[str]:
    out = []
    for ticker in dict.fromkeys(str(t).upper().strip() for t in tickers):
        if spot_metals.is_spot_metal(ticker):
            log.debug("daily delta: %s is spot-scaled and never cached; skipped", ticker)
        elif ticker:
            out.append(ticker)
    return out


def _by_basis(symbols: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for symbol in symbols:
        groups.setdefault(basis_for(symbol), []).append(symbol)
    return groups


def _fetch(fn, *args) -> dict:
    """An injected fetch; BudgetDeferred is a miss."""
    try:
        return fn(*args) or {}
    except yf_safe.BudgetDeferred as exc:
        log.info("daily delta: fetch deferred (%s)", exc)
        return {}


def _with_forming(persisted: pd.DataFrame | None, provider_frame: pd.DataFrame,
                  today: date) -> pd.DataFrame:
    """Persisted bars before `today` plus the provider's own bars on or after
    `today` (the forming bar, in memory only). Never a bar the provider frame
    does not hold."""
    cut = pd.Timestamp(today)
    forming = _ohlcv(provider_frame)
    forming = forming[forming.index >= cut]
    base = persisted[persisted.index < cut] if persisted is not None else forming.iloc[:0]
    out = pd.concat([base, forming]) if not forming.empty else base.copy()
    out.attrs = {}
    return out


def _cold_reason(df, meta: DailyMeta | None, basis: str, today: date) -> str | None:
    if df is None:
        return "cold"
    if meta is None or not meta.last_verified:
        return "no-meta"
    if meta.basis != basis:
        return "basis"
    if delta_window(meta, today) is None:
        return "window-cap"
    return None


def _anchor_closes(basis: str, warm: list[str], metas: dict, today: date, fw) -> dict[str, float]:
    """Fresh anchor-bar closes for the symbols not yet checked today, one
    ranged call per anchor date. A symbol whose fetch failed stays due."""
    due: dict[str, list[str]] = {}
    for t in warm:
        meta = metas[t]
        if meta.anchor_checked != today.isoformat() and meta.anchor_date:
            due.setdefault(meta.anchor_date, []).append(t)
    out = {}
    for anchor_date, symbols in due.items():
        day = date.fromisoformat(anchor_date)
        got = _fetch(fw, symbols, day, day + timedelta(days=_ANCHOR_SPAN_DAYS), basis)
        stamp = pd.Timestamp(day)
        for t in symbols:
            frame = got.get(t)
            if frame is not None and not frame.empty:
                frame = _naive(frame)
                if stamp in frame.index:
                    out[t] = float(frame.loc[stamp, "Close"])
    return out


def _apply_delta(ticker: str, basis: str, cached: pd.DataFrame, fresh: pd.DataFrame,
                 meta: DailyMeta, today: date, anchor_checked: bool) -> pd.DataFrame:
    """Write only when the window holds a closed bar newer than last_verified;
    otherwise only the sidecar, and only when the anchor was checked."""
    idx = fresh.index
    newer = (idx > pd.Timestamp(meta.last_verified)) & (idx < pd.Timestamp(today))
    stamp = today.isoformat() if anchor_checked else None
    if newer.any():
        persisted = write_daily(ticker, fresh, basis=basis, full=False, today=today, anchor_checked=stamp)
    else:
        if anchor_checked:
            _mark_anchor_checked(ticker, basis, today)
        persisted = cached
    return _with_forming(persisted, fresh, today)


def _splice_warm(basis: str, warm: list[str], cached: dict, metas: dict, today: date,
                 fw) -> tuple[dict, dict]:
    """(served frames, {refused symbol: reason}) for the warm symbols."""
    start = min(delta_window(metas[t], today)[0] for t in warm)
    frames = _fetch(fw, warm, start, today, basis)
    anchors = _anchor_closes(basis, warm, metas, today, fw)
    out, refused = {}, {}
    for t in warm:
        fresh = frames.get(t)
        if fresh is None or fresh.empty:
            out[t] = cached[t]
            continue
        fresh = _naive(fresh)
        reason = needs_full_refetch(cached[t], fresh, metas[t], anchor_close=anchors.get(t))
        if reason is not None:
            refused[t] = reason
            continue
        out[t] = _apply_delta(t, basis, cached[t], fresh, metas[t], today, t in anchors)
    return out, refused


def _log_drift(ticker: str, basis: str, before: DailyMeta | None, after: DailyMeta | None) -> None:
    if before is None or after is None or not before.anchor_close or after.anchor_close is None:
        return
    if before.anchor_date != after.anchor_date or before.anchor_close == after.anchor_close:
        return
    drift = (float(after.anchor_close) / float(before.anchor_close) - 1.0) * 100.0
    log.info("daily re-anchor %s (%s): anchor_close %.6f -> %.6f (drift %+.4f%%)",
             ticker, basis, before.anchor_close, after.anchor_close, drift)


def _write_full(ticker: str, basis: str, fresh: pd.DataFrame, today: date) -> pd.DataFrame:
    before = read_meta(ticker, basis)
    persisted = write_daily(ticker, fresh, basis=basis, full=True, today=today)
    _log_drift(ticker, basis, before, read_meta(ticker, basis))
    frame = _with_forming(persisted, fresh, today)
    frame.attrs["source"] = fresh.attrs.get("source")
    return frame


def _full_basis(basis: str, targets: list[str], cached: dict, today: date, fw, ff) -> dict:
    """Full refetch of `targets` from this basis' own provider. A cold
    alpaca-all miss goes to the yfinance basis (tagged yfinance-fallback); a
    miss with a cached file serves that file."""
    got = _fetch(ff, targets, basis)
    out, cold_miss = {}, []
    for t in targets:
        fresh = got.get(t)
        if fresh is not None and not fresh.empty:
            out[t] = _write_full(t, basis, fresh, today)
        elif cached.get(t) is not None:
            out[t] = cached[t]
        else:
            cold_miss.append(t)
    if basis == BASIS_ALPACA and cold_miss:
        for t, frame in _delta_basis(BASIS_YF, cold_miss, today, fw, ff).items():
            frame.attrs["source"] = SOURCE_FALLBACK
            out[t] = frame
    return out


def _log_refusals(basis: str, reasons: dict) -> list[str]:
    """Log each full-refetch reason; the symbols that need one."""
    targets = [t for t, reason in reasons.items() if reason is not None]
    for t in targets:
        level = logging.DEBUG if reasons[t] == "cold" else logging.INFO
        log.log(level, "daily delta %s (%s): full refetch (%s)", t, basis, reasons[t])
    return targets


def _delta_basis(basis: str, group: list[str], today: date, fw, ff) -> dict:
    cached = {t: read_daily(t, basis) for t in group}
    metas = {t: read_meta(t, basis) for t in group}
    reasons = {t: _cold_reason(cached[t], metas[t], basis, today) for t in group}
    warm = [t for t in group if reasons[t] is None]
    out, refused = _splice_warm(basis, warm, cached, metas, today, fw) if warm else ({}, {})
    reasons.update(refused)
    targets = _log_refusals(basis, reasons)
    if targets:
        out.update(_full_basis(basis, targets, cached, today, fw, ff))
    return out


def delta_update(tickers, *, asker: Asker, today: date | None = None,
                 fetch_window=None, fetch_full=None) -> dict[str, pd.DataFrame]:
    """Daily frames for `tickers` (upper-cased keys): each cache brought up to
    date by a proven delta, or a full refetch where the delta is refused."""
    fw = fetch_window or provider_window
    ff = fetch_full or provider_full
    today = today or _today_ny()
    with router.asker_scope(asker):
        try:
            out = {}
            for basis, group in _by_basis(_plain(tickers)).items():
                out.update(_delta_basis(basis, group, today, fw, ff))
            return out
        finally:
            counters.flush()


def full_refetch(tickers, *, asker: Asker, today: date | None = None,
                 fetch_full=None, fetch_window=None) -> dict[str, pd.DataFrame]:
    """A full refetch of every symbol on its own basis (the weekly re-anchor);
    logs each symbol whose anchor_close moved."""
    fw = fetch_window or provider_window
    ff = fetch_full or provider_full
    today = today or _today_ny()
    with router.asker_scope(asker):
        try:
            out = {}
            for basis, group in _by_basis(_plain(tickers)).items():
                cached = {t: read_daily(t, basis) for t in group}
                out.update(_full_basis(basis, group, cached, today, fw, ff))
            return out
        finally:
            counters.flush()
