"""v230 A2: the v2 matched null -- a cross-sectional pool in three stages.

Stage 1 (panel, per ticker): on the ticker's own bars, v1's eligible flag
(member, warm, race completes inside the frame, not a raw event), the trend
state (close > SMA200), ATR14 as a fraction of close, the raw event flag and,
in avoid mode, the control flag. Every value at bar t reads bars <= t, except
race completeness, which reads the frame's end exactly as v1 does.

Stage 2 (draw, per date): for an event on ticker i at date t the pool is
every other ticker j eligible at t, in the same trend state, in the same ATR%
tercile of t's eligible cross-section, with no raw event at t. Market-scope
ideas draw from the same ticker's trailing sessions instead.

Stage 3 (race, per null ticker): null bars raced on their own frame with
their own ATR14 and scattered back to their events.

v1's null.py is not edited; v2 imports its constants and masks.
"""
from __future__ import annotations

import json
import os
import pickle
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import null

NULL_VERSION = "v2"
STAGES = ("panel", "draw", "race")
STAGE_MANIFEST = "manifest.json"
_PROGRESS_EVERY = 50


def _bool(values) -> np.ndarray:
    return np.asarray(values, dtype=bool)


@dataclass(frozen=True, eq=False)
class TickerPanel:
    """Stage 1 for one ticker: one value per bar of its own frame."""
    ticker: str
    dates: np.ndarray
    eligible: np.ndarray
    trend: np.ndarray
    atr_pct: np.ndarray
    event: np.ndarray
    control: np.ndarray | None = None
    level_bars: np.ndarray | None = None


def _level_bars(df: pd.DataFrame, atr: np.ndarray) -> np.ndarray:
    """(n, 4): Open, High, Low and ATR14 of the previous bar (NaN on row 0),
    what a level fill at bar p reads (v1 ``null._null_fills``)."""
    prev_atr = np.r_[np.nan, atr[:-1]]
    return np.column_stack([df["Open"].to_numpy(dtype=float),
                            df["High"].to_numpy(dtype=float),
                            df["Low"].to_numpy(dtype=float), prev_atr])


def ticker_panel(ticker: str, df: pd.DataFrame, ctx: Mapping, *, cap: int,
                 control=None, keep_bars: bool = False) -> TickerPanel:
    """Stage 1 from one ticker's ``ticker_context``. In avoid mode
    ``ctx["condition"]`` leaves the pool and ``control`` is the control flag."""
    raw = _bool(ctx["raw"])
    eligible = null.eligible_mask(raw, ctx["member"], ctx["warm"], cap)
    if ctx.get("condition") is not None:
        eligible = eligible & ~_bool(ctx["condition"])
    atr = np.asarray(ctx["atr"], dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        atr_pct = atr / df["Close"].to_numpy(dtype=float)
    return TickerPanel(ticker, df.index.to_numpy(), eligible, _bool(ctx["trend"]), atr_pct,
                       raw, None if control is None else _bool(control),
                       _level_bars(df, atr) if keep_bars else None)


@dataclass(frozen=True, eq=False)
class CrossSection:
    """Every panel on the union calendar, shape (dates, tickers), tickers sorted."""
    dates: pd.DatetimeIndex
    tickers: tuple
    eligible: np.ndarray
    trend: np.ndarray
    tercile: np.ndarray
    event: np.ndarray
    control: np.ndarray | None
    pos: np.ndarray


def atr_terciles(atr_pct_row, eligible_row) -> np.ndarray:
    """0/1/2 by the date's eligible ATR% terciles for every finite value; -1 off."""
    values = np.asarray(atr_pct_row, dtype=float)
    out = np.full(values.shape, -1, dtype=np.int8)
    finite = np.isfinite(values)
    pool = values[_bool(eligible_row) & finite]
    if pool.size == 0:
        return out
    low, high = np.quantile(pool, [1 / 3, 2 / 3])
    out[finite] = (values[finite] > low).astype(np.int8) + (values[finite] > high)
    return out


def _union_dates(panels: Mapping[str, TickerPanel], tickers) -> pd.DatetimeIndex:
    if not tickers:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(np.unique(np.concatenate([panels[t].dates for t in tickers])))


def cross_section(panels: Mapping[str, TickerPanel]) -> CrossSection:
    tickers = tuple(sorted(panels))
    dates = _union_dates(panels, tickers)
    shape = (len(dates), len(tickers))
    eligible, trend, event = (np.zeros(shape, dtype=bool) for _ in range(3))
    atr_pct = np.full(shape, np.nan)
    pos = np.full(shape, -1, dtype=np.int32)
    with_control = any(panels[t].control is not None for t in tickers)
    control = np.zeros(shape, dtype=bool) if with_control else None
    for col, ticker in enumerate(tickers):
        p = panels[ticker]
        rows = dates.get_indexer(pd.DatetimeIndex(p.dates))
        eligible[rows, col], trend[rows, col], event[rows, col] = p.eligible, p.trend, p.event
        atr_pct[rows, col] = p.atr_pct
        pos[rows, col] = np.arange(len(rows), dtype=np.int32)
        if control is not None and p.control is not None:
            control[rows, col] = p.control
    tercile = np.zeros(shape, dtype=np.int8)
    for row in range(len(dates)):
        tercile[row] = atr_terciles(atr_pct[row], eligible[row])
    return CrossSection(dates, tickers, eligible, trend, tercile, event, control, pos)


class StageCheckpoint:
    """One pickle per finished key under a stage directory; a no-op without one."""

    def __init__(self, directory: Path | None):
        self.directory = None if directory is None else Path(directory)

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.pkl"

    def load(self, key: str):
        if self.directory is None:
            return None
        path = self._path(key)
        # pickle is safe here: local scratch files this same run wrote, never shared input
        return pickle.loads(path.read_bytes()) if path.exists() else None

    def save(self, key: str, obj) -> None:
        if self.directory is None:
            return
        final = self._path(key)
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(tmp, final)

    def done(self) -> set[str]:
        if self.directory is None:
            return set()
        return {p.name[: -len(".pkl")] for p in self.directory.glob("*.pkl")}


def _normalised(manifest: Mapping) -> dict:
    return json.loads(json.dumps(dict(manifest), sort_keys=True, default=str))


def _refuse_v1_root(root: Path) -> None:
    """A v1 screen checkpoint keeps manifest.json and <ticker>.pkl in its root."""
    path = root / STAGE_MANIFEST
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if any(root.glob("*.pkl")) or (saved is not None
                                   and saved.get("null_version") != NULL_VERSION):
        raise ValueError(f"checkpoint {root} is a v1 screen checkpoint; "
                         "a v1 checkpoint never resumes under v2")


def open_stage(root, stage: str, manifest: Mapping, out=print) -> StageCheckpoint:
    """``<root>/<stage>/`` with a manifest adding ``null_version`` and ``stage``."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGES}")
    if root is None:
        return StageCheckpoint(None)
    root = Path(root)
    if root.exists():
        _refuse_v1_root(root)
    directory = root / stage
    directory.mkdir(parents=True, exist_ok=True)
    full = _normalised({**manifest, "null_version": NULL_VERSION, "stage": stage})
    path = directory / STAGE_MANIFEST
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved != full:
            raise ValueError(f"checkpoint {directory} belongs to another run: "
                             f"{saved} != {full}")
    else:
        path.write_text(json.dumps(full, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    checkpoint = StageCheckpoint(directory)
    out(f"[{manifest.get('idea', '?')}] {stage} checkpoint {directory}: "
        f"{len(checkpoint.done())} unit(s) already done", flush=True)
    return checkpoint


def resumable_map(keys: Iterable[str], fn: Callable[[str], object], *,
                  checkpoint: StageCheckpoint, out=print, label: str = "") -> dict:
    """``{key: fn(key)}``, resuming finished keys; a None result is never saved."""
    keys = list(keys)
    done = checkpoint.done()
    out(f"{label}: {len(done & set(keys))} of {len(keys)} already done", flush=True)
    results = {}
    for i, key in enumerate(keys, 1):
        obj = checkpoint.load(key) if key in done else None
        if obj is None:
            obj = fn(key)
            if obj is not None:
                checkpoint.save(key, obj)
        if obj is not None:
            results[key] = obj
        if i % _PROGRESS_EVERY == 0 or i == len(keys):
            out(f"{label}: {i}/{len(keys)} ({100 * i // len(keys)}%)", flush=True)
    return results


DRAW_COLUMNS = ("event_ticker", "event_pos", "event_date", "null_ticker", "null_pos", "fill")
SCOPE_MISMATCH = "SCOPE_MISMATCH"
NULL_STARVED = "NULL_STARVED"
STARVED_SHARE = 0.5
_REFUSAL_CODES = {"ticker": SCOPE_MISMATCH, "market": NULL_STARVED}
_TABLE_TYPES = {"event_ticker": object, "event_pos": "int64", "event_date": "datetime64[ns]",
                "null_ticker": object, "null_pos": "int64", "fill": "float64"}


class NullRefusal(ValueError):
    """A v2 pool too thin to judge: raised after the draw, before any race."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


def _v2_name(idea: str) -> str:
    return f"{idea}:v2"


def date_seed(idea: str, day) -> list:
    """Ticker scope: one generator per date, ``null_seed(idea + ":v2", ISO day)``."""
    return null.null_seed(_v2_name(idea), pd.Timestamp(day).strftime("%Y-%m-%d"))


def ticker_pool(xs: CrossSection, row: int, col: int, *,
                require_control: bool = False) -> np.ndarray:
    """Columns j != col eligible at row, same trend state and ATR% tercile, no event."""
    mask = (xs.eligible[row] & ~xs.event[row]
            & (xs.trend[row] == xs.trend[row, col])
            & (xs.tercile[row] == xs.tercile[row, col]))
    if require_control:
        if xs.control is None:
            raise ValueError("the cross-section carries no control flag")
        mask &= xs.control[row]
    mask[col] = False
    return np.flatnonzero(mask)


@dataclass(frozen=True)
class DrawResult:
    """Stage 2's artefact: the draw table and the counts the refusal reads."""
    table: pd.DataFrame
    dropped: Counter
    event_dates: int
    starved_dates: int
    slots: int
    unfilled: int


def _records(event_ticker, event_pos, day, null_tickers, null_pos, fills=None) -> list[tuple]:
    fills = np.full(len(null_pos), np.nan) if fills is None else np.asarray(fills, dtype=float)
    return [(event_ticker, int(event_pos), pd.Timestamp(day), str(t), int(p), float(f))
            for t, p, f in zip(null_tickers, null_pos, fills)]


def _table(records) -> pd.DataFrame:
    return pd.DataFrame.from_records(records, columns=list(DRAW_COLUMNS)).astype(_TABLE_TYPES)


class _Tally:
    """The draw passes' accumulator; event dates are sets, so a date seen on
    several tickers (market scope) counts once."""

    def __init__(self):
        self.records: list[tuple] = []
        self.dropped: Counter = Counter()
        self.days: set = set()
        self.starved_days: set = set()
        self.slots = 0
        self.unfilled = 0

    def add(self, rows) -> None:
        self.records.extend(rows)

    def count_slots(self, m) -> None:
        self.slots += int(m)

    def count_unfilled(self, m) -> None:
        self.unfilled += int(m)

    def mark_date(self, day, starved: bool) -> None:
        self.days.add(pd.Timestamp(day))
        if starved:
            self.starved_days.add(pd.Timestamp(day))

    def result(self) -> DrawResult:
        return DrawResult(_table(self.records), self.dropped, len(self.days),
                          len(self.starved_days), self.slots, self.unfilled)


def _events_by_row(xs: CrossSection, booked: Mapping) -> dict[int, list[tuple[int, int]]]:
    """{row: [(col, own position), ...]} with columns ascending (sorted tickers)."""
    unknown = sorted(set(booked) - set(xs.tickers))
    if unknown:
        raise ValueError(f"booked tickers missing from the cross-section: {unknown[:5]}")
    by_row: dict[int, list[tuple[int, int]]] = {}
    for col, ticker in enumerate(xs.tickers):
        positions = np.sort(np.asarray(booked.get(ticker, ()), dtype=int))
        rows = np.flatnonzero(xs.pos[:, col] >= 0)[positions]
        for row, pos in zip(rows.tolist(), positions.tolist()):
            by_row.setdefault(row, []).append((col, pos))
    return by_row


def draw_ticker_scope(xs: CrossSection, booked: Mapping, *, idea: str,
                      k: int = null.K) -> DrawResult:
    """Stage 2, ticker scope: up to k null bars per event from its date's pool."""
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        day = xs.dates[row]
        rng = np.random.default_rng(date_seed(idea, day))
        starved = False
        for col, pos in events:
            pool = ticker_pool(xs, row, col)
            if pool.size < null.MIN_CANDIDATES:
                tally.dropped[xs.tickers[col]] += 1
                starved = True
                continue
            pick = np.sort(rng.choice(pool, size=min(k, pool.size), replace=False))
            tally.count_slots(pick.size)
            tally.add(_records(xs.tickers[col], pos, day, [xs.tickers[j] for j in pick],
                               xs.pos[row, pick]))
        tally.mark_date(day, starved)
    return tally.result()


def check_starvation(result: DrawResult, scope: str) -> None:
    """SCOPE_MISMATCH / NULL_STARVED when starved dates exceed half the event dates."""
    if scope not in _REFUSAL_CODES:
        raise ValueError(f"unknown scope {scope!r}")
    if result.starved_dates > STARVED_SHARE * result.event_dates:
        raise NullRefusal(_REFUSAL_CODES[scope],
                          f"{result.starved_dates} of {result.event_dates} event dates "
                          f"left an event under {null.MIN_CANDIDATES} candidates")
