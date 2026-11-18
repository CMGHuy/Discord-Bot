"""v230 A2: one idea's v2 screen -- stage 1 (panel and event book per ticker),
stage 2 (one draw, which refuses a starved pool), stage 3 (race per null
ticker) -- each stage checkpointed under ``<checkpoint_dir>/<stage>/``.

Frame loading, the per-ticker context and the event-side blocks that read no
null (rank, overlap) come from the caller through V2Inputs, so this module
never imports scripts/backtest/screen_idea.py.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import forward, indicators, null_v2, race

#: bars from the event bar to the entry bar (screen_idea._ENTRY_OFFSET).
_ENTRY_OFFSET = {"next_open": 1, "level": 0}


@dataclass(frozen=True)
class V2Inputs:
    load: Callable[[str], pd.DataFrame | None]
    context: Callable[[str, pd.DataFrame], dict]
    extras: Callable[[str, pd.DataFrame, dict], dict]


@dataclass
class V2Ticker:
    ticker: str
    counters: Counter
    events: list
    null_outcomes: Counter
    excess: dict
    extras: dict
    null_timeout_r: list
    null_slots: int
    null_unfilled: int
    depths: dict | None
    avoid_control: list | None


@dataclass(frozen=True, eq=False)
class _Book:
    """Stage 1's event side for one event ticker."""
    raced: race.RaceResult
    counts: dict
    depths: np.ndarray | None
    fwd: dict
    extras: dict


def _book(idea, df: pd.DataFrame, ctx: Mapping, costs: Mapping):
    """The event book exactly as v1 ``_books`` races it, and its level depths."""
    level = idea.entry == "level"
    kw = {"levels": ctx["levels"]} if level else {}
    booked, counts = race.run_book(df, ctx["raw"], idea.time_cap_bars, member=ctx["member"],
                                   warm=ctx["warm"], atr=ctx["atr"], shape=idea.race_shape,
                                   direction=idea.direction, **costs, **kw)
    depths = None
    if level:
        depths = (race.level_fills(df, booked.event_pos, ctx["levels"], ctx["atr"],
                                   idea.direction)[1]
                  if len(booked) else np.array([], dtype=float))
    return booked, counts, depths


def _stage1(idea, name: str, inputs: V2Inputs, costs: Mapping, is_event: bool) -> dict | None:
    df = inputs.load(name)
    if df is None:
        return None
    ctx = inputs.context(name, df)
    control = ctx.get("control_condition") if idea.mode == "avoid" else None
    panel = null_v2.ticker_panel(name, df, ctx, cap=idea.time_cap_bars, control=control,
                                 keep_bars=idea.entry == "level")
    if not is_event:
        return {"panel": panel, "book": None}
    booked, counts, depths = _book(idea, df, ctx, costs)
    fwd = {h: forward.forward_atr(df, ctx["atr"], h, direction=idea.direction)[booked.event_pos]
           for h in forward.HORIZONS}
    extras = inputs.extras(name, df, {**ctx, "book": booked})
    return {"panel": panel, "book": _Book(booked, dict(counts), depths, fwd, extras)}


def _kept(table: pd.DataFrame) -> dict:
    filled = table[table["null_pos"] >= 0]
    return {t: np.unique(g["event_pos"].to_numpy(dtype=int))
            for t, g in filled.groupby("event_ticker")}


def _draw_stage(idea, units: Mapping, checkpoint) -> tuple:
    saved = checkpoint.load("draw")
    if saved is not None:
        return saved
    panels = {t: u["panel"] for t, u in units.items()}
    books = {t: u["book"] for t, u in units.items() if u["book"] is not None}
    depths = {t: b.depths for t, b in books.items()} if idea.entry == "level" else None
    xs = None if idea.scope == "market" else null_v2.cross_section(panels)
    result = null_v2.draw(xs, panels, {t: b.raced.event_pos for t, b in books.items()},
                          idea=idea, depths=depths)
    control = (null_v2.draw_control(xs, _kept(result.table), idea=idea.name)
               if idea.mode == "avoid" else None)
    checkpoint.save("draw", (result, control))
    return result, control


def _race_stage(idea, result, control, inputs: V2Inputs, costs: Mapping, checkpoint, out):
    def load(ticker):
        df = inputs.load(ticker)
        return None if df is None else (df, indicators.atr(df))

    tables = [result.table.assign(arm="null")]
    if control is not None:
        tables.append(control.table.assign(arm="control"))
    raced = null_v2.race_pass(pd.concat(tables, ignore_index=True), load,
                              shape=idea.race_shape, cap=idea.time_cap_bars,
                              direction=idea.direction, costs=costs,
                              checkpoint=checkpoint, out=out)
    nulls = null_v2.scatter(raced[raced["arm"] == "null"])
    controls = None if control is None else null_v2.scatter(raced[raced["arm"] == "control"])
    return nulls, controls


def _arm_rows(ticker: str, dates: pd.DatetimeIndex, book: _Book, nulls: Mapping,
              offset: int) -> tuple[list, list]:
    """Rows for the booked events whose null has a filled slot, and (i, EventNull)."""
    rows, kept, rr = [], [], book.raced
    for i, pos in enumerate(rr.event_pos.tolist()):
        en = nulls.get((ticker, pos))
        if en is None or en.slots == en.unfilled:
            continue
        r, gross = float(rr.r[i]), float(rr.gross_r[i])
        rows.append({"ticker": ticker,
                     "entry_date": dates[pos + offset].strftime("%Y-%m-%d"),
                     "exit_date": dates[rr.exit_pos[i]].strftime("%Y-%m-%d"),
                     "r_event": r, "r_null": en.mean_r, "outcome": str(rr.outcome[i]),
                     "cost_event": gross - r, "cost_null": en.mean_gross_r - en.mean_r})
        kept.append((i, en))
    return rows, kept


def _excess(book: _Book, kept: list) -> dict:
    """Event minus null forward drift per horizon, finite pairs only (v1 excess_drift)."""
    out = {h: [] for h in forward.HORIZONS}
    for i, en in kept:
        for h in forward.HORIZONS:
            ev, nl = float(book.fwd[h][i]), en.fwd.get(h, np.nan)
            if np.isfinite(ev) and np.isfinite(nl):
                out[h].append(ev - nl)
    return out


def _depths(idea, book: _Book, kept: list) -> dict | None:
    """Level only: a filled null slot's realised depth is its event's depth."""
    if idea.entry != "level":
        return None
    return {"event": [float(book.depths[i]) for i, _ in kept],
            "null": [float(book.depths[i]) for i, en in kept
                     for _ in range(en.slots - en.unfilled)]}


def _ticker(idea, name: str, unit: Mapping, result, control, nulls, controls) -> V2Ticker:
    book, dates = unit["book"], pd.DatetimeIndex(unit["panel"].dates)
    offset = _ENTRY_OFFSET[idea.entry]
    events, kept = _arm_rows(name, dates, book, nulls, offset)
    counters = Counter(book.counts)
    counters["dropped_no_match"] = int(result.dropped.get(name, 0))
    avoid_rows = None
    if controls is not None:
        avoid_rows = _arm_rows(name, dates, book, controls, offset)[0]
        counters["control_below_floor"] = int(control.dropped.get(name, 0))
    mine = [nulls[(name, p)] for p in book.raced.event_pos.tolist() if (name, p) in nulls]
    timeouts = [r for _, en in kept for r in en.timeout_r] if idea.race_shape == "trail" else []
    return V2Ticker(ticker=name, counters=counters, events=events,
                    null_outcomes=sum((en.outcomes for _, en in kept), Counter()),
                    excess=_excess(book, kept), extras=book.extras, null_timeout_r=timeouts,
                    null_slots=sum(en.slots for en in mine),
                    null_unfilled=sum(en.unfilled for en in mine),
                    depths=_depths(idea, book, kept), avoid_control=avoid_rows)


def _manifest(idea, manifest: Mapping | None, costs: Mapping, event_tickers) -> dict:
    digest = None
    if event_tickers is not None:
        digest = hashlib.sha256("\n".join(sorted(event_tickers)).encode("utf-8")).hexdigest()
    return {"idea": idea.name, **(manifest or {}), "scope": idea.scope,
            "event_tickers_sha256": digest, "costs": dict(costs)}


def run_v2(idea, names, inputs: V2Inputs, *, costs: Mapping, checkpoint_dir=None,
           manifest: Mapping | None = None, out=print, event_tickers=None) -> list[V2Ticker]:
    """The v2 screen of ``idea`` over ``names`` (the pool's whole universe).
    ``event_tickers`` restricts the event book, never the pool. Raises
    ``null_v2.NullRefusal`` after stage 2, before any race."""
    full = _manifest(idea, manifest, costs, event_tickers)
    events = set(names) if event_tickers is None else set(event_tickers)
    units = null_v2.resumable_map(
        sorted(names), lambda n: _stage1(idea, n, inputs, costs, n in events),
        checkpoint=null_v2.open_stage(checkpoint_dir, "panel", full, out),
        out=out, label=f"[{idea.name}] panel")
    result, control = _draw_stage(idea, units,
                                  null_v2.open_stage(checkpoint_dir, "draw", full, out))
    nulls, controls = _race_stage(idea, result, control, inputs, costs,
                                  null_v2.open_stage(checkpoint_dir, "race", full, out), out)
    return [_ticker(idea, t, units[t], result, control, nulls, controls)
            for t in sorted(units) if units[t]["book"] is not None]
