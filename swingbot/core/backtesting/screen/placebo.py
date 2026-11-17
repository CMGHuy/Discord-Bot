"""v230 A1: the placebo harness -- universes with no edge by construction.

Each universe is a screen cache directory on a given trading calendar:
<T>.csv (Date,Open,High,Low,Close,Volume), membership.csv (one span per
ticker from the first session, open end), a synthetic SPY.csv built as the
equal-weight index after generation, and universe.json (written last: its
presence marks a complete universe).

gbm: driftless (martingale) geometric random walks. Daily sd = level /
ATR_PER_SIGMA, x STRESS_MULT while stressed; stressed = the ticker's own
two-state Markov chain OR one shared market chain, so volatility clusters
and ATR14 lags it. Overnight gap and open-to-close legs split the variance
(GAP_SHARE); wicks widen max/min(open, close). ATR_PER_SIGMA (1.9) was
fitted by simulating this model: median ATR14 % of close / calm sd = 1.89.
One seed per ticker, [seed, crc32(ticker)], so a ticker's path does not
depend on the ticker count.

shuffled: the real cached bars with whole trading days 1..n-1 permuted, one
permutation shared by every ticker. Each day carries its close-to-close
return, open/high/low-to-close ratios and volume, so each day's
cross-section survives and no serial structure does.

No date literal lives here: the calendar is always a parameter.
"""
from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.context import CONTEXT_ONLY_STEMS
from swingbot.core.backtesting.screen.ideas import Idea

PLACEBO_SEED = 42
GBM_TICKERS = 200
INDEX_TICKER = "SPY"
MEMBERSHIP_FILE = "membership.csv"
MANIFEST_FILE = "universe.json"
OHLCV = ("Open", "High", "Low", "Close", "Volume")

STRESS_ENTER = 0.02     # P(calm -> stressed) per session
STRESS_EXIT = 0.10      # P(stressed -> calm) per session
STRESS_MULT = 2.0
GAP_SHARE = 0.4         # overnight gap sd as a share of the daily sd
WICK_SHARE = 0.5        # wick sd as a share of the open-to-close sd
ATR_PER_SIGMA = 1.9     # median ATR14 % of close per unit of calm daily sd (simulated)
QUARTILE_POINTS = (12.5, 37.5, 62.5, 87.5)
GBM_VOLUME = 1_000_000.0
PRICE_FORMAT = "%.6f"
_MARKET_STREAM = zlib.crc32(b"market")
_LEVEL_STREAM = 1


def ticker_seed(ticker: str, base: int = PLACEBO_SEED) -> list:
    return [base, zlib.crc32(ticker.encode("utf-8"))]


def read_frame(path) -> pd.DataFrame:
    """One cache CSV, tz-naive, sorted, duplicates dropped, OHLCV only."""
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    return df.loc[:, list(OHLCV)].dropna()


def trading_calendar(spy_csv, start: str, end: str) -> pd.DatetimeIndex:
    """The index ticker's sessions in [start, end]."""
    idx = read_frame(spy_csv).index
    idx = idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]
    if len(idx) == 0:
        raise ValueError(f"{spy_csv}: no session in {start}..{end}")
    return pd.DatetimeIndex(idx, name="Date")


def _source_files(cache_dir, tickers=None) -> list[Path]:
    """Ticker CSVs only: no index, context-only, ^-prefixed or _-prefixed files."""
    paths = sorted(Path(cache_dir).glob("*.csv"))
    keep = [p for p in paths if p.stem != INDEX_TICKER and p.stem not in CONTEXT_ONLY_STEMS
            and not p.stem.startswith(("^", "_"))]
    return keep if tickers is None else [p for p in keep if p.stem in set(tickers)]


def _on_calendar(path, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    df = read_frame(path)
    return df.loc[(df.index >= calendar[0]) & (df.index <= calendar[-1])]


def atr_pct_quartiles(cache_dir, calendar, tickers=None) -> tuple[float, float, float, float]:
    """Quartile midpoints (QUARTILE_POINTS) of the per-ticker median ATR14 % of close."""
    medians = []
    for path in _source_files(cache_dir, tickers):
        df = _on_calendar(path, calendar)
        if len(df) < 15:
            continue
        value = float(np.nanmedian((indicators.atr(df) / df["Close"]).to_numpy(dtype=float)))
        if np.isfinite(value):
            medians.append(value)
    if not medians:
        raise ValueError(f"no ATR% could be measured in {cache_dir}")
    return tuple(float(v) for v in np.percentile(medians, QUARTILE_POINTS))


def _markov(rng, n: int) -> np.ndarray:
    """A two-state chain starting calm; True = stressed."""
    draws = rng.random(n)
    out = np.zeros(n, dtype=bool)
    for t in range(1, n):
        out[t] = draws[t] >= STRESS_EXIT if out[t - 1] else draws[t] < STRESS_ENTER
    return out


def market_states(calendar, seed) -> np.ndarray:
    """The shared market chain (True = stressed), one per universe seed."""
    return _markov(np.random.default_rng([seed, _MARKET_STREAM]), len(calendar))


def _lognormal(rng, sd: np.ndarray) -> np.ndarray:
    """Log-returns with mean -sd^2/2: exp() of them has expectation one."""
    return rng.normal(-sd ** 2 / 2.0, sd)


def gbm_frame(ticker: str, calendar, *, level: float, stressed,
              seed: int = PLACEBO_SEED) -> pd.DataFrame:
    """One driftless OHLCV path whose median ATR14 % of close sits near ``level``."""
    rng = np.random.default_rng(ticker_seed(ticker, seed))
    n = len(calendar)
    regime = _markov(rng, n) | np.asarray(stressed, dtype=bool)
    sd = level / ATR_PER_SIGMA * np.where(regime, STRESS_MULT, 1.0)
    day_sd = np.sqrt(1.0 - GAP_SHARE ** 2) * sd
    gap, day = _lognormal(rng, GAP_SHARE * sd), _lognormal(rng, day_sd)
    close = rng.uniform(20.0, 200.0) * np.exp(np.cumsum(gap + day))
    open_ = close * np.exp(-day)
    up = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    down = np.abs(rng.normal(0.0, WICK_SHARE * day_sd))
    return pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * np.exp(up),
                         "Low": np.minimum(open_, close) * np.exp(-down), "Close": close,
                         "Volume": np.full(n, GBM_VOLUME)},
                        index=pd.DatetimeIndex(calendar, name="Date"))


def equal_weight_index(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Level 100 x cumprod(1 + mean daily return); O/H/L from the mean ratios to close."""
    if not frames or any(df.empty for df in frames.values()):
        raise ValueError("cannot build an index from empty frames")
    names = sorted(frames)
    close = pd.DataFrame({t: frames[t]["Close"] for t in names})
    level = 100.0 * (1.0 + close.pct_change(fill_method=None).mean(axis=1).fillna(0.0)).cumprod()

    def ratio(col):
        return pd.DataFrame({t: frames[t][col] / frames[t]["Close"] for t in names}).mean(axis=1)

    volume = pd.DataFrame({t: frames[t]["Volume"] for t in names}).sum(axis=1)
    return pd.DataFrame({"Open": level * ratio("Open"), "High": level * ratio("High"),
                         "Low": level * ratio("Low"), "Close": level, "Volume": volume},
                        index=pd.DatetimeIndex(close.index, name="Date"))


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.loc[:, list(OHLCV)].to_csv(path, index_label="Date", date_format="%Y-%m-%d",
                                  float_format=PRICE_FORMAT, lineterminator="\n")


def _publish_manifest(path: Path, manifest: Mapping) -> None:
    """Publish the completion marker only after its full JSON is closed."""
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(manifest, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_universe(out_dir, frames: Mapping[str, pd.DataFrame], *, kind: str,
                   meta: Mapping) -> Path:
    """One screen cache directory; universe.json is written last."""
    if INDEX_TICKER in frames:
        raise ValueError(f"{INDEX_TICKER} is the synthetic index; no ticker may use the name")
    index = equal_weight_index(frames)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / MANIFEST_FILE).unlink(missing_ok=True)
    names = sorted(frames)
    for ticker in names:
        _write_csv(out / f"{ticker}.csv", frames[ticker])
    _write_csv(out / f"{INDEX_TICKER}.csv", index)
    first, last = (d.strftime("%Y-%m-%d") for d in (index.index[0], index.index[-1]))
    (out / MEMBERSHIP_FILE).write_text(
        "ticker,start_date,end_date\n" + "".join(f"{t},{first},\n" for t in names),
        encoding="utf-8", newline="\n")
    manifest = {"kind": kind, "seed": PLACEBO_SEED, "tickers": names,
                "calendar_start": first, "calendar_end": last, **meta}
    _publish_manifest(out / MANIFEST_FILE, manifest)
    return out


def _level_for(ticker: str, quartiles, seed: int) -> float:
    rng = np.random.default_rng(ticker_seed(ticker, seed) + [_LEVEL_STREAM])
    return float(quartiles[int(rng.integers(len(quartiles)))])


def gbm_universe(out_dir, calendar, quartiles, *, n_tickers: int = GBM_TICKERS,
                 seed: int = PLACEBO_SEED) -> Path:
    """G000.. tickers; each path depends on its name and ``seed`` only."""
    market = market_states(calendar, seed)
    frames = {}
    for i in range(n_tickers):
        ticker = f"G{i:03d}"
        frames[ticker] = gbm_frame(ticker, calendar, level=_level_for(ticker, quartiles, seed),
                                   stressed=market, seed=seed)
    return write_universe(out_dir, frames, kind="gbm",
                          meta={"seed": seed, "n_tickers": n_tickers,
                                "quartiles": [float(q) for q in quartiles]})


def day_permutation(n: int, seed) -> np.ndarray:
    """Day 0 fixed; days 1..n-1 permuted."""
    return np.r_[0, 1 + np.random.default_rng(seed).permutation(n - 1)]


def shuffle_frame(df: pd.DataFrame, perm: np.ndarray) -> pd.DataFrame:
    """Rebuild ``df`` on its own index from the permuted days."""
    close = df["Close"].to_numpy(dtype=float)
    ret = np.r_[1.0, close[1:] / close[:-1]]
    rebuilt = close[0] * np.cumprod(ret[perm])
    cols = {c: rebuilt * (df[c].to_numpy(dtype=float) / close)[perm]
            for c in ("Open", "High", "Low")}
    return pd.DataFrame({**cols, "Close": rebuilt,
                         "Volume": df["Volume"].to_numpy(dtype=float)[perm]},
                        index=df.index)


def _full_sources(source_dir, calendar) -> tuple[dict, dict]:
    """Tickers with a bar on every calendar session, and their files' sha256."""
    frames, hashes = {}, {}
    for path in _source_files(source_dir):
        df = _on_calendar(path, calendar)
        if len(df) == len(calendar) and np.array_equal(df.index.values, calendar.values):
            frames[path.stem] = df
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not frames:
        raise ValueError(f"no ticker in {source_dir} has a bar on every calendar session")
    return frames, hashes


def shuffled_universe(out_dir, source_dir, calendar, *, seed: int = PLACEBO_SEED,
                      copies: int = 1) -> Path:
    """The real bars, whole days permuted alike across tickers; copy c >= 1 is <T>_C<c>."""
    sources, hashes = _full_sources(source_dir, calendar)
    frames = {}
    for c in range(copies):
        perm = day_permutation(len(calendar), seed if c == 0 else [seed, c])
        suffix = "" if c == 0 else f"_C{c}"
        for ticker, df in sources.items():
            frames[ticker + suffix] = shuffle_frame(df, perm)
    return write_universe(out_dir, frames, kind="shuffled",
                          meta={"seed": seed, "copies": copies, "source_sha256": hashes})


PLACEBO_CAP = 10
PLANT_ATR = 0.5
PLANT_SPACING = 12 * PLACEBO_CAP     # bars between planted events on one ticker
PLANTED_FILE = "planted_events.json"
TOLERANCE_R = 0.02
FINGERPRINT_BARS = 5
_PLACES = 10


@dataclass(frozen=True)
class PlaceboTrigger:
    name: str
    scope: str
    events: Callable[[pd.DataFrame, pd.DataFrame], pd.Series]   # (ticker frame, index frame)


def _high20(df, index):
    return df["Close"] > indicators.rolling_max(df["High"], 20).shift(1)


def _rsi2_dip(df, index):
    close = df["Close"]
    return (close > indicators.sma(close, 200)) & (indicators.rsi(close, 2) < 10)


def _gap_up(df, index):
    return df["Open"] >= df["Close"].shift(1) + 0.5 * indicators.atr(df).shift(1)


def _sweep20(df, index):
    low20 = indicators.rolling_min(df["Low"], 20).shift(1)
    return (df["Low"] < low20) & (df["Close"] > low20)


def _market_down(df, index):
    ret = index["Close"].pct_change(fill_method=None)
    flag = ret < -1.5 * ret.rolling(20, min_periods=20).std().shift(1)
    return flag.reindex(df.index, fill_value=False)


def _month_turn(df, index):
    if df.empty:
        return pd.Series(False, index=df.index, dtype=bool)
    month = df.index.year * 12 + df.index.month
    return pd.Series(np.r_[month[1:] != month[:-1], True], index=df.index)


TRIGGERS: dict[str, PlaceboTrigger] = {t.name: t for t in (
    PlaceboTrigger("p_high20", "ticker", _high20),
    PlaceboTrigger("p_rsi2_dip", "ticker", _rsi2_dip),
    PlaceboTrigger("p_gap_up", "ticker", _gap_up),
    PlaceboTrigger("p_sweep20", "ticker", _sweep20),
    PlaceboTrigger("p_market_down", "market", _market_down),
    PlaceboTrigger("p_month_turn", "market", _month_turn))}


def placebo_idea(trigger: PlaceboTrigger, index_frame: pd.DataFrame) -> Idea:
    """The trigger as an unregistered Idea: long, fixed race, next open, cap 10."""
    def events(df):
        flags = trigger.events(df, index_frame).reindex(df.index, fill_value=False)
        return flags.fillna(False).astype(bool)

    return Idea(name=trigger.name, events=events, time_cap_bars=PLACEBO_CAP,
                params={"placebo": trigger.name, "cap": PLACEBO_CAP},
                summary=f"v230 placebo trigger {trigger.name}", source="spec v230 A1",
                scope=trigger.scope)


def plant_drift(df, events, atr, *, cap: int = PLACEBO_CAP,
                atr_mult: float = PLANT_ATR) -> pd.DataFrame:
    """+atr_mult x ATR14[t] spread over bars t+1..t+cap, persisting after."""
    n = len(df)
    add_close, add_open = np.zeros(n), np.zeros(n)
    atr_v = np.asarray(atr, dtype=float)
    for t in np.flatnonzero(np.asarray(events, dtype=bool)):
        if t + 1 >= n or not np.isfinite(atr_v[t]):
            continue
        steps = np.arange(1, n - t)
        add_close[t + 1:] += atr_mult * atr_v[t] * np.minimum(steps, cap) / cap
        add_open[t + 1:] += atr_mult * atr_v[t] * np.minimum(steps - 1, cap) / cap
    out = df.copy()
    for col, add in (("Open", add_open), ("High", add_close), ("Low", add_open),
                     ("Close", add_close)):
        out[col] = df[col].to_numpy(dtype=float) + add
    return out


def _spaced(pos: np.ndarray, spacing: int) -> list[int]:
    kept: list[int] = []
    for p in pos:
        if not kept or p - kept[-1] >= spacing:
            kept.append(int(p))
    return kept


def plant_universe(base_dir, out_dir) -> Path:
    """The base universe with drift planted after spaced p_high20 events."""
    base = Path(base_dir)
    manifest = json.loads((base / MANIFEST_FILE).read_text(encoding="utf-8"))
    index = read_frame(base / f"{INDEX_TICKER}.csv")
    frames, planted = {}, {}
    for ticker in manifest["tickers"]:
        df = read_frame(base / f"{ticker}.csv")
        atr = indicators.atr(df)
        fired = TRIGGERS["p_high20"].events(df, index).to_numpy(dtype=bool)
        ok = fired & np.isfinite(atr.to_numpy()) & (np.arange(len(df)) + 1 < len(df))
        pos = _spaced(np.flatnonzero(ok), PLANT_SPACING)
        flags = np.zeros(len(df), dtype=bool)
        flags[pos] = True
        frames[ticker] = plant_drift(df, flags, atr)
        planted[ticker] = [d.strftime("%Y-%m-%d") for d in df.index[pos]]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / MANIFEST_FILE).unlink(missing_ok=True)
    _publish_manifest(out / PLANTED_FILE, planted)
    return write_universe(out, frames, kind="planted",
                         meta={"seed": manifest["seed"], "base": manifest["kind"],
                               "plant_atr": PLANT_ATR, "cap": PLACEBO_CAP,
                               "spacing": PLANT_SPACING})


def _fingerprint(df: pd.DataFrame) -> tuple:
    return tuple(np.round(df["Close"].to_numpy(dtype=float)[:FINGERPRINT_BARS], 6))


def planted_trigger(universe_dir) -> PlaceboTrigger:
    """Fires on the planted dates, on the planted universe and its base alike."""
    root = Path(universe_dir)
    planted = json.loads((root / PLANTED_FILE).read_text(encoding="utf-8"))
    lookup: dict[tuple, pd.DatetimeIndex] = {}
    for ticker, days in planted.items():
        key = _fingerprint(read_frame(root / f"{ticker}.csv"))
        if key in lookup:
            raise ValueError(f"{ticker}: first closes collide with another ticker")
        lookup[key] = pd.DatetimeIndex(days)

    def events(df, index):
        days = lookup.get(_fingerprint(df))
        flags = np.zeros(len(df), bool) if days is None else df.index.isin(days)
        return pd.Series(flags, index=df.index)

    return PlaceboTrigger("p_high20_planted", "ticker", events)


def planted_value(base_rows, planted_rows) -> float | None:
    """Mean event-arm R gain on events booked in both universes."""
    base = {(r["ticker"], str(r["entry_date"])[:10]): r["r_event"] for r in base_rows}
    gains = [r["r_event"] - base[key] for r in planted_rows
             if (key := (r["ticker"], str(r["entry_date"])[:10])) in base]
    return float(np.mean(gains)) if gains else None
