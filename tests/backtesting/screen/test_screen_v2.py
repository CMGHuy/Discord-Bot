"""v230 A2: run_v2 runs panel -> draw -> race with staged checkpoints and
returns one V2Ticker per event ticker; a starved pool refuses before stage 3."""
import json

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward, indicators, null, null_v2, race, screen_v2
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import frame, random_walk

FRAMES = {f"T{i:02d}": random_walk(500, seed=100 + i) for i in range(90)}
COSTS = {"slippage_bps": 5.0, "commission": 0.01}
QUIET = {"out": lambda *a, **k: None}
ROW_KEYS = {"ticker", "entry_date", "exit_date", "r_event", "r_null", "outcome",
            "cost_event", "cost_null"}


def _breakout(df):
    return df["Close"] > df["Close"].rolling(20).max().shift(1)


def _month_end(df):
    months = df.index.to_series().dt.month
    return months != months.shift(-1)


IDEA = Idea(name="x", events=_breakout, time_cap_bars=10)


def _context(idea):
    def context(name, df):
        atr, sma200 = indicators.atr(df), indicators.sma(df["Close"], 200)
        levels = None if idea.levels is None else idea.levels(df).to_numpy(dtype=float)
        return {"raw": idea.events(df).fillna(False).to_numpy(dtype=bool),
                "member": null.member_mask(df.index, None),
                "warm": race.warm_mask(atr, sma200), "atr": atr,
                "trend": null.trend_state(df, sma200), "levels": levels}
    return context


def _inputs(idea=IDEA, frames=FRAMES, loads=None):
    def load(name):
        if loads is not None:
            loads.append(name)
        return frames.get(name)
    return screen_v2.V2Inputs(load, _context(idea),
                              lambda name, df, ctx: {"booked": len(ctx["book"])})


def _run(idea=IDEA, names=FRAMES, inputs=None, **kw):
    return screen_v2.run_v2(idea, sorted(names), inputs or _inputs(idea), costs=COSTS,
                            **QUIET, **kw)


def _independent_draw():
    ctxs = {t: _context(IDEA)(t, df) for t, df in FRAMES.items()}
    panels = {t: null_v2.ticker_panel(t, FRAMES[t], c, cap=10) for t, c in ctxs.items()}
    booked = {t: race.run_book(FRAMES[t], c["raw"], 10, member=c["member"], warm=c["warm"],
                               atr=c["atr"], **COSTS)[0].event_pos for t, c in ctxs.items()}
    return null_v2.draw_ticker_scope(null_v2.cross_section(panels), booked, idea="x").table


def _pos(row):
    return FRAMES[row["ticker"]].index.get_loc(pd.Timestamp(row["entry_date"])) - 1


def test_each_event_pairs_its_book_race_with_its_raced_null_slots():
    screens = _run(names=[*FRAMES, "ZZZ"])                  # ZZZ has no frame: skipped
    assert [s.ticker for s in screens] == sorted(FRAMES)
    s = next(s for s in screens if s.events)
    row, table = s.events[0], _independent_draw()
    pos, df = _pos(row), FRAMES[s.ticker]
    slots = table[(table.event_ticker == s.ticker) & (table.event_pos == pos)]
    rs = [race.race(FRAMES[t], [p], 10, atr=indicators.atr(FRAMES[t]), **COSTS).r[0]
          for t, p in zip(slots.null_ticker, slots.null_pos)]
    want = race.race(df, [pos], 10, atr=indicators.atr(df), **COSTS)
    assert set(row) == ROW_KEYS
    assert row["r_null"] == pytest.approx(np.mean(rs))
    assert row["r_event"] == pytest.approx(want.r[0])
    assert row["cost_event"] == pytest.approx(want.gross_r[0] - want.r[0])
    assert s.extras == {"booked": len(s.events) + s.counters["dropped_no_match"]}


def test_null_counts_and_drift_come_from_the_null_tickers_frames():
    s = next(s for s in _run() if s.events)
    assert sum(s.null_outcomes.values()) == s.null_slots and s.null_unfilled == 0
    assert set(s.excess) == set(forward.HORIZONS) and len(s.excess[5]) == len(s.events)
    assert (s.depths, s.avoid_control, s.null_timeout_r) == (None, None, [])


def test_a_resumed_run_loads_nothing_and_returns_the_same_screens(tmp_path):
    first = _run(checkpoint_dir=tmp_path, manifest={"idea": "x", "start": "s"})
    loads = []
    again = _run(inputs=_inputs(loads=loads), checkpoint_dir=tmp_path,
                 manifest={"idea": "x", "start": "s"})
    assert loads == [] and [s.events for s in again] == [s.events for s in first]
    for stage in null_v2.STAGES:
        saved = json.loads((tmp_path / stage / null_v2.STAGE_MANIFEST).read_text(encoding="utf-8"))
        assert (saved["null_version"], saved["stage"], saved["scope"], saved["start"]) == (
            "v2", stage, "ticker", "s")


def test_a_v1_checkpoint_never_resumes_under_v2(tmp_path):
    (tmp_path / "T00.pkl").write_bytes(b"v1")
    with pytest.raises(ValueError, match="v1"):
        _run(checkpoint_dir=tmp_path)


def test_event_tickers_restrict_the_book_but_not_the_pool(tmp_path):
    screens = _run(event_tickers=["T03"], checkpoint_dir=tmp_path)
    assert [s.ticker for s in screens] == ["T03"]
    full = next(s for s in _run() if s.ticker == "T03")
    assert ([(r["entry_date"], r["r_event"]) for r in screens[0].events]
            == [(r["entry_date"], r["r_event"]) for r in full.events])
    with pytest.raises(ValueError, match="another run"):
        _run(event_tickers=["T04"], checkpoint_dir=tmp_path)


def test_a_starved_pool_refuses_after_the_draw_and_before_any_race(tmp_path):
    few = {t: FRAMES[t] for t in ("T00", "T01", "T02")}
    with pytest.raises(null_v2.NullRefusal) as exc:
        _run(names=few, inputs=_inputs(frames=few), checkpoint_dir=tmp_path)
    assert exc.value.code == null_v2.SCOPE_MISMATCH
    assert (tmp_path / "draw").is_dir() and not (tmp_path / "race").exists()


def test_a_level_idea_reports_event_and_null_depths():
    idea = Idea(name="lvl", events=lambda df: df["High"] > df["Open"] * 1.012,
                time_cap_bars=10, entry="level", levels=lambda df: df["Open"] * 1.012)
    screens = _run(idea=idea, inputs=_inputs(idea))
    s = next(s for s in screens if s.events)
    df = FRAMES[s.ticker]
    pos = df.index.get_loc(pd.Timestamp(s.events[0]["entry_date"]))   # level: entry on the event bar
    assert df["High"].iloc[pos] > df["Open"].iloc[pos] * 1.012
    assert len(s.depths["event"]) == len(s.events)
    assert len(s.depths["null"]) == s.null_slots - s.null_unfilled
    assert all(d > 0 for d in s.depths["event"])


def _avoid_context(name, df):
    ctx = _context(IDEA)(name, df)
    bars = np.arange(len(df))
    return {**ctx, "condition": bars % 7 == 3, "control_condition": bars % 2 == 0}


def test_an_avoid_idea_carries_its_control_arm():
    idea = Idea(name="av", events=_breakout, time_cap_bars=10, mode="avoid",
                states=lambda df: None)
    inputs = screen_v2.V2Inputs(FRAMES.get, _avoid_context, lambda *a: {})
    screens = screen_v2.run_v2(idea, sorted(FRAMES), inputs, costs=COSTS, **QUIET)
    rows = [r for s in screens for r in s.avoid_control]
    below = sum(s.counters["control_below_floor"] for s in screens)
    assert rows and below
    assert len(rows) + below == sum(len(s.events) for s in screens)
    assert all(_pos(r) % 2 == 0 for r in rows) and set(rows[0]) == ROW_KEYS


def test_a_market_idea_runs_without_a_cross_section(monkeypatch):
    idea = Idea(name="mkt", events=_month_end, time_cap_bars=4, scope="market")
    # A steady trend supplies same-state history after warm-up and the embargo.
    # One ticker also proves the market null needs no cross-ticker peers.
    frames = {"MKT": frame(100.0 + np.arange(500) * 0.1)}

    def no_cross_section(*args, **kwargs):
        pytest.fail("market scope must not build a cross-section")

    monkeypatch.setattr(null_v2, "cross_section", no_cross_section)
    screens = _run(idea=idea, names=frames, inputs=_inputs(idea, frames=frames))
    rows = [r for s in screens for r in s.events]
    assert rows and all(np.isfinite(r["r_null"]) for r in rows)
    assert screens[0].counters["dropped_no_match"] == 0
    assert screens[0].extras["booked"] == len(rows)
