"""v230 A2: the v2 matched null -- a cross-sectional pool in three stages.

Stage 1 (panel, per ticker): on the ticker's own bars, v1's eligible flag
(member, warm, race completes inside the frame, not a raw event), the trend
state (close > SMA200), ATR14 as a fraction of close, the raw event flag and,
in avoid mode, the control flag. Every value at bar t reads bars <= t, except
race completeness, which reads the frame's end exactly as v1 does.

Stage 2 (draw, per date): for an event on ticker i at date t the pool is
every other ticker j eligible at t, in the same trend state, in the same ATR%
tercile of t's eligible cross-section, with no raw event at t. Market-scope
ideas draw from the same ticker's trailing sessions instead. Market scope:
the same ticker's TRAILING_DAYS sessions before t, embargoed CAP bars around
every raw event, so no null bar postdates its event. Level entry: the event's
depth on the null ticker's own Open and ATR14[t-1], unfilled picks replaced
on the child stream; avoid mode's control arm is the same draw with the
control flag required of j.

Stage 3 (race, per null ticker): null bars raced on their own frame with
their own ATR14 and scattered back to their events. Rows keep the draw table's order; a blank level
slot is never raced and reads "unfilled".

v1's null.py is not edited; v2 imports its constants and masks.
"""
from __future__ import annotations

import json
import os
import pickle
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import forward, null, race as race_mod

if TYPE_CHECKING:
    from swingbot.core.backtesting.screen.ideas import Idea

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


TRAILING_DAYS = 252


def _embargoed(event: np.ndarray, lo: int, hi: int, cap: int) -> np.ndarray:
    """True for positions lo..hi-1 within ``cap`` bars of any raw event in ``event``."""
    hits = np.flatnonzero(event)
    window = np.arange(lo, hi)
    if hits.size == 0:
        return np.zeros(window.size, dtype=bool)
    nxt = np.searchsorted(hits, window)                       # first event at or after p
    after = hits[np.minimum(nxt, hits.size - 1)] - window
    before = window - hits[np.maximum(nxt - 1, 0)]
    return ((nxt < hits.size) & (after <= cap)) | ((nxt > 0) & (before <= cap))


def market_pool(panel: TickerPanel, pos: int, *, cap: int) -> np.ndarray:
    """Market scope: own positions in the TRAILING_DAYS sessions before ``pos``,
    eligible, same trend state, more than ``cap`` bars from every raw event.
    Reads the event flag up to ``pos`` only; ``pos`` is itself a raw event, so
    a later event could only embargo bars ``pos`` already embargoes."""
    lo = max(0, pos - TRAILING_DAYS)
    near = _embargoed(panel.event[: pos + 1], lo, pos, cap)
    keep = (panel.eligible[lo:pos] & (panel.trend[lo:pos] == panel.trend[pos]) & ~near)
    return np.arange(lo, pos)[keep]


def _draw_market_ticker(tally: _Tally, panel: TickerPanel, positions, *,
                        idea: str, cap: int, k: int) -> None:
    rng = np.random.default_rng(null.null_seed(_v2_name(idea), panel.ticker))
    for pos in np.sort(np.asarray(positions, dtype=int)).tolist():
        day = panel.dates[pos]
        pool = market_pool(panel, pos, cap=cap)
        starved = pool.size < null.MIN_CANDIDATES
        tally.mark_date(day, starved)
        if starved:
            tally.dropped[panel.ticker] += 1
            continue
        pick = np.sort(rng.choice(pool, size=min(k, pool.size), replace=False))
        tally.count_slots(pick.size)
        tally.add(_records(panel.ticker, pos, day, [panel.ticker] * pick.size, pick))


def draw_market_scope(panels: Mapping[str, TickerPanel], booked: Mapping, *, idea: str,
                      cap: int, k: int = null.K) -> DrawResult:
    """Stage 2, market scope: one generator per ticker, its events ascending."""
    unknown = sorted(set(booked) - set(panels))
    if unknown:
        raise ValueError(f"booked tickers without a panel: {unknown[:5]}")
    tally = _Tally()
    for ticker in sorted(booked):
        _draw_market_ticker(tally, panels[ticker], booked[ticker], idea=idea, cap=cap, k=k)
    return tally.result()


def level_fill(bar_row, depth: float, direction: str) -> float:
    """One null bar's resting-order fill from its ``level_bars`` row (Open,
    High, Low, ATR14[t-1]): Open +/- depth x ATR when the bar reaches it (v1
    ``null._null_fills``); NaN when unreached or the ATR is not finite and > 0."""
    if direction not in ("long", "short"):
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    o, h, l, a = (float(v) for v in bar_row)
    if not (np.isfinite(a) and a > 0):
        return float("nan")
    if direction == "short":
        level = o - depth * a
        return level if l <= level else float("nan")
    level = o + depth * a
    return level if h >= level else float("nan")


def _depth_lookup(booked: Mapping, depths: Mapping) -> dict:
    """{(ticker, own position): depth}; one depth per booked event, in order."""
    out = {}
    for ticker, positions in booked.items():
        positions = np.asarray(positions, dtype=int)
        values = np.asarray(depths.get(ticker, ()), dtype=float)
        if values.shape != positions.shape:
            raise ValueError(f"{ticker}: a level draw needs one depth per booked event "
                             f"({values.size} for {positions.size})")
        out.update(zip(((ticker, p) for p in positions.tolist()), values.tolist()))
    return out


def _fill_at(xs: CrossSection, panels: Mapping, row: int, col: int, d: float,
             direction: str) -> float:
    bars = panels[xs.tickers[col]].level_bars
    if bars is None:
        raise ValueError(f"{xs.tickers[col]}: a level draw needs level_bars (keep_bars=True)")
    return level_fill(bars[xs.pos[row, col]], d, direction)


def _level_slots(xs, panels, row, pool, first, d, child, direction):
    """Filled (columns, fills) sorted by column: the first picks, then
    replacements from the rest of the pool in ``child.permutation`` order
    (v1 ``null._level_group``)."""
    m = len(first)
    cols, fills = [], []

    def take(candidates) -> None:
        for j in candidates:
            if len(cols) == m:
                return
            f = _fill_at(xs, panels, row, j, d, direction)
            if np.isfinite(f):
                cols.append(j)
                fills.append(f)

    take(first.tolist())
    rest = np.setdiff1d(pool, first)
    if len(cols) < m and rest.size:
        take(child.permutation(rest).tolist())
    order = np.argsort(np.asarray(cols, dtype=int), kind="stable")
    return np.asarray(cols, dtype=int)[order], np.asarray(fills, dtype=float)[order]


def _level_event(tally: _Tally, xs, panels, row, col, pos, d, rng, child, *,
                 direction: str, k: int) -> bool:
    """One level event's slots; True when its pool is under the floor."""
    ticker = xs.tickers[col]
    pool = ticker_pool(xs, row, col)
    if pool.size < null.MIN_CANDIDATES:
        tally.dropped[ticker] += 1
        return True
    m = min(k, pool.size)
    tally.count_slots(m)
    first = rng.choice(pool, size=m, replace=False)
    cols, fills = _level_slots(xs, panels, row, pool, first, d, child, direction)
    blank = m - cols.size
    tally.count_unfilled(blank)
    if cols.size == 0:
        tally.dropped[ticker] += 1
    day = xs.dates[row]
    tally.add(_records(ticker, pos, day, [xs.tickers[j] for j in cols], xs.pos[row, cols], fills))
    tally.add(_records(ticker, pos, day, [""] * blank, np.full(blank, -1)))
    return False


def draw_ticker_level(xs: CrossSection, panels: Mapping[str, TickerPanel], booked: Mapping,
                      depths: Mapping, *, idea: str, direction: str,
                      k: int = null.K) -> DrawResult:
    """Stage 2, level entry: the event's depth on each null ticker's own Open
    and ATR14[t-1]; an unfilled pick is replaced from the rest of the date's
    pool; a slot still unfilled is a blank row (null_ticker "", null_pos -1)."""
    lookup = _depth_lookup(booked, depths)
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        seed = date_seed(idea, xs.dates[row])
        rng, child = np.random.default_rng(seed), np.random.default_rng(null.child_seed(seed))
        starved = False
        for col, pos in events:
            d = lookup[(xs.tickers[col], pos)]
            starved |= _level_event(tally, xs, panels, row, col, pos, d, rng, child,
                                    direction=direction, k=k)
        tally.mark_date(xs.dates[row], starved)
    return tally.result()


def _control_seed(idea: str, day) -> list:
    return null.null_seed(f"{_v2_name(idea)}:control", pd.Timestamp(day).strftime("%Y-%m-%d"))


def draw_control(xs: CrossSection, booked: Mapping, *, idea: str,
                 k: int = null.K) -> DrawResult:
    """Avoid mode's control arm: the ticker-scope draw with the control flag
    required of every null ticker, on its own stream ``idea:v2:control``. Never
    refused; an event under the floor is counted in ``dropped`` (v1 below_floor)."""
    tally = _Tally()
    for row, events in sorted(_events_by_row(xs, booked).items()):
        day = xs.dates[row]
        rng = np.random.default_rng(_control_seed(idea, day))
        starved = False
        for col, pos in events:
            pool = ticker_pool(xs, row, col, require_control=True)
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


def draw(xs: CrossSection | None, panels: Mapping[str, TickerPanel], booked: Mapping, *,
         idea: Idea, depths: Mapping | None = None) -> DrawResult:
    """Stage 2 for one idea -- market scope, level entry or the ticker-scope
    next-open draw -- then the SCOPE_MISMATCH / NULL_STARVED refusal, so a
    starved pool stops the run before any race."""
    if idea.scope == "market":
        result = draw_market_scope(panels, booked, idea=idea.name, cap=idea.time_cap_bars)
    elif idea.entry == "level":
        if depths is None:
            raise ValueError(f"{idea.name}: a level draw needs one depth per booked event")
        result = draw_ticker_level(xs, panels, booked, depths, idea=idea.name,
                                   direction=idea.direction)
    else:
        result = draw_ticker_scope(xs, booked, idea=idea.name)
    check_starvation(result, idea.scope)
    return result


#: Stage 3's outcome for a level slot that never filled; it is never raced.
UNFILLED = "unfilled"
_KEYS = ["event_ticker", "event_pos"]


def _fwd_name(h: int) -> str:
    return f"fwd_{h}"


def _race_rows(part: pd.DataFrame, df: pd.DataFrame, atr, *, shape: str, cap: int,
               direction: str, costs: Mapping, level_factor: float, horizons) -> pd.DataFrame:
    """One null ticker's slots raced on its own frame and ATR14 (v1 matched_null tail)."""
    pos = part["null_pos"].to_numpy(dtype=int)
    fill = part["fill"].to_numpy(dtype=float)
    level = np.isfinite(fill)
    if level.any() and not level.all():
        raise ValueError(f"{part['null_ticker'].iloc[0]}: level and next-open slots "
                         "on one null ticker")
    extra = {} if direction == "long" else {"direction": direction}
    if level.all():
        extra.update(fill=fill, level_factor=level_factor)
    raced = race_mod.race_for(shape)(df, pos, cap, atr=atr, **costs, **extra)
    out = part.assign(r=raced.r, gross_r=raced.gross_r, outcome=raced.outcome.astype(object))
    for h in horizons:
        out[_fwd_name(h)] = forward.forward_atr(df, atr, h, direction=direction)[pos]
    return out


def _blank_rows(part: pd.DataFrame, horizons) -> pd.DataFrame:
    out = part.assign(r=np.nan, gross_r=np.nan, outcome=UNFILLED)
    for h in horizons:
        out[_fwd_name(h)] = np.nan
    return out.astype({"outcome": object})


def race_pass(table: pd.DataFrame, load: Callable, *, shape: str, cap: int, direction: str,
              costs: Mapping, level_factor: float = race_mod.LEVEL_SLIPPAGE_FACTOR,
              horizons=forward.HORIZONS, checkpoint: StageCheckpoint | None = None,
              out=print) -> pd.DataFrame:
    """Stage 3: every filled slot raced on its null ticker's own frame and
    ATR14, one ticker's frame resident at a time, each finished ticker saved to
    ``checkpoint``; blank level slots read UNFILLED. Rows keep their order."""
    checkpoint = StageCheckpoint(None) if checkpoint is None else checkpoint
    filled = table["null_pos"].to_numpy() >= 0
    sub = table[filled]
    groups = sub.groupby("null_ticker", sort=True).indices
    kw = {"shape": shape, "cap": cap, "direction": direction, "costs": costs,
          "level_factor": level_factor, "horizons": horizons}

    def one(ticker: str) -> pd.DataFrame:
        loaded = load(ticker)
        if loaded is None:
            raise ValueError(f"null ticker {ticker} has no frame to race on")
        df, atr = loaded
        return _race_rows(sub.iloc[groups[ticker]], df, atr, **kw)

    raced = resumable_map(sorted(groups), one, checkpoint=checkpoint, out=out, label="race")
    parts = [raced[t] for t in sorted(raced)]
    if not filled.all():
        parts.append(_blank_rows(table[~filled], horizons))
    if not parts:
        return _blank_rows(table, horizons)
    return pd.concat(parts).loc[table.index]


@dataclass(frozen=True)
class EventNull:
    """One event's null after stage 3: means over its filled slots."""
    mean_r: float
    mean_gross_r: float
    outcomes: Counter
    fwd: dict
    timeout_r: tuple
    slots: int
    unfilled: int


def _outcome_counters(filled: pd.DataFrame) -> dict:
    counters: dict = defaultdict(Counter)
    if not filled.empty:
        for (t, p, outcome), n in filled.groupby(_KEYS)["outcome"].value_counts().items():
            counters[(t, p)][outcome] = int(n)
    return counters


def _timeouts(filled: pd.DataFrame) -> dict:
    out: dict = defaultdict(list)
    hit = filled.loc[filled["outcome"] == "timeout", [*_KEYS, "r"]]
    for t, p, r in hit.itertuples(index=False):
        out[(t, p)].append(float(r))
    return out


def scatter(raced: pd.DataFrame) -> dict[tuple[str, int], EventNull]:
    """Stage 3 back to events: one EventNull per (event ticker, event position)."""
    if raced.empty:
        return {}
    fwd_cols = sorted((c for c in raced.columns if c.startswith("fwd_")),
                      key=lambda c: int(c[4:]))
    filled = raced[raced["null_pos"].to_numpy() >= 0].copy()
    filled[fwd_cols] = filled[fwd_cols].where(np.isfinite(filled[fwd_cols]))
    slots = raced.groupby(_KEYS).size()
    means = filled.groupby(_KEYS)[["r", "gross_r", *fwd_cols]].mean().reindex(slots.index)
    n_filled = filled.groupby(_KEYS).size().reindex(slots.index, fill_value=0)
    outcomes, timeouts = _outcome_counters(filled), _timeouts(filled)
    return {(str(t), int(p)): EventNull(
                float(m["r"]), float(m["gross_r"]), outcomes[(t, p)],
                {int(c[4:]): float(m[c]) for c in fwd_cols}, tuple(timeouts[(t, p)]),
                int(slots[(t, p)]), int(slots[(t, p)] - n_filled[(t, p)]))
            for (t, p), m in means.iterrows()}
