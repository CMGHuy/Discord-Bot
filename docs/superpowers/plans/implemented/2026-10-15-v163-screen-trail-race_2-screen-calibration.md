# v163 Idea screen: a trailing-exit race shape. Part 2: screen wiring, trail doc, A/A calibration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task V163-6" -A 300 docs/superpowers/plans/2026-10-15-v163-screen-trail-race_2-screen-calibration.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-15-v163-screen-trail-race-design.md`](../../specs/implemented/2026-10-15-v163-screen-trail-race-design.md)
**Bump:** none
**Edge:** none (integrity)
**Index:** [`2026-10-15-v163-screen-trail-race_0-index.md`](2026-10-15-v163-screen-trail-race_0-index.md) — Global Constraints, the controller's binding deviations, `## Parallelisation` and the task ledger live there and bind every task below.

**Where to work:** worktree `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race`, main tree `$R` = `E:/Documents/Private/Projects/Discord-Bot`. Never `cd`; use absolute paths and `git -C $WT`.

**What Part 1 hands this part (from the ledger, created by V163-1..V163-4):**

- `Idea.race_shape: str = "fixed"` (last field); `RACE_SHAPES = ("fixed", "trail")`; `TRAIL_MIN_CAP = 60`; `Idea(..., race_shape="trail", time_cap_bars=59)` raises `ValueError`.
- `race.OUTCOMES = ("gap_stop", "gap_target", "stop", "target", "timeout", "trail", "gap_trail")`; `race.SHAPE_OUTCOMES = {"fixed": OUTCOMES[:5], "trail": ("gap_stop", "stop", "gap_trail", "trail", "timeout")}`.
- `screen_idea._mix(outcomes, names)`, `screen_idea._render_arms(summary, names)`; `render_results` passes `race.SHAPE_OUTCOMES[idea.race_shape]`.
- Test literals in `tests/scripts/test_screen_idea.py`: `_fixed_doc_inputs()`, `FIXED_DOC`, `FIXED_HYPOTHESIS` (a fixed idea's doc and ledger hypothesis, byte-identical to `main @ 316c57e9`). **Those tests are this part's fixed-path guard: they must stay green after every task here.**
- `trail.TRAIL_ATR = 3.0`; `trail.race_trail(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None) -> race.RaceResult`.
- `race.run_book(..., shape: str = "fixed")`; `null.matched_null(..., shape: str = "fixed")`; `race.race_for(shape)`.

Before V163-5, confirm Part 1 landed on the branch:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race grep -n "SHAPE_OUTCOMES\|def race_for\|shape: str = \"fixed\"\|race_shape: str\|TRAIL_ATR = 3.0\|FIXED_DOC = \|FIXED_HYPOTHESIS = "
```

Expected: hits in `race.py`, `null.py`, `ideas/__init__.py`, `trail.py`, `tests/scripts/test_screen_idea.py`. A miss means Part 1 is not done: stop.

# Phase 3: screen script

### Task V163-5: `screen_ticker` races the idea's shape; trail-only timeout and 2 × slippage data; `summarise` aggregates them

**Model:** opus — wires the race shape through the per-ticker pipeline and adds a second costed race whose pairing must match the base book exactly.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (imports :20, `TickerScreen` :80-87, `screen_ticker` :107-131, `summarise` :230-241, `_run_info` :373-377 — line numbers as on `main`; V163-2 has edited `_mix`/`_render_arms`/`render_results` lower down)
- Test: `tests/scripts/test_screen_idea.py` (append only)

**Interfaces:**
- Consumes: `Idea.race_shape` (V163-1); `race.SHAPE_OUTCOMES` (V163-2); `race.run_book(df, events, cap, *, member, warm, atr, slippage_bps=None, commission=None, shape="fixed")` and `null.matched_null(df, event_pos, eligible, k, seed, *, cap, atr, trend, slippage_bps=None, commission=None, shape="fixed")` (V163-4); `trail.race_trail` reached through them (V163-3).
- Produces (consumed by V163-6 and V163-7):
  - `screen_idea.STRESS_SLIPPAGE_FACTOR = 2`
  - `screen_idea.base_slippage(slippage_bps=None)` — the passed value, else `getattr(config, "SLIPPAGE_BPS", 5.0)`; never cast (a config int must keep printing as it does today).
  - `TickerScreen.null_timeout_r: list = field(default_factory=list)` — net R of every null-race `timeout`, trail ideas only (`[]` for fixed).
  - `TickerScreen.stressed: list | None = None` — trail only: one dict per kept event, keys `entry_date`, `r_event`, `r_null`, re-raced at `STRESS_SLIPPAGE_FACTOR × base_slippage(slippage_bps)`; `None` for fixed.
  - `summarise(...)["timeouts"] = {"event": (count, share, mean_r), "null": (count, share, mean_r)}` (share `None` when the book is empty, mean `None` when it has no timeout R).
  - `summarise(...)["stress"]` — a `verdict.Verdict` over the stressed pairs, `None` when every screen's `stressed is None`.
  - `screen_ticker(idea, ticker, df, spans, *, slippage_bps=None, commission=None)` keeps its signature (V163-7 calls it as is).

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_screen_idea.py`:

```python
# --- v163: the idea's shape reaches the race; trail-only timeout and stress data

from swingbot.core.backtesting.screen import race as race_mod  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402


def _trail_probe(cap=60):
    """turn_of_month's trigger raced under the trail shape; never registered."""
    return Idea(name="trail_probe", events=IDEAS["turn_of_month"].events,
                time_cap_bars=cap, race_shape="trail", summary="probe", source="test")


def test_base_slippage_reads_config_only_when_none(monkeypatch):
    monkeypatch.setattr(screen_idea.config, "SLIPPAGE_BPS", 7.0, raising=False)
    assert screen_idea.base_slippage(None) == 7.0
    assert screen_idea.base_slippage(3.0) == 3.0
    assert screen_idea.base_slippage(0.0) == 0.0
    assert screen_idea.STRESS_SLIPPAGE_FACTOR == 2


def test_screen_ticker_passes_the_idea_shape_to_book_and_null(monkeypatch):
    shapes = {"book": [], "null": []}
    real_book, real_null = race_mod.run_book, null.matched_null

    def book_spy(*args, **kwargs):
        shapes["book"].append(kwargs.get("shape"))
        return real_book(*args, **kwargs)

    def null_spy(*args, **kwargs):
        shapes["null"].append(kwargs.get("shape"))
        return real_null(*args, **kwargs)

    monkeypatch.setattr(race_mod, "run_book", book_spy)
    monkeypatch.setattr(null, "matched_null", null_spy)
    df = random_walk(2600)
    screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", df, ALWAYS)
    assert shapes == {"book": ["fixed"], "null": ["fixed"]}
    shapes["book"].clear()
    shapes["null"].clear()
    screen_idea.screen_ticker(_trail_probe(), "AAA", df, ALWAYS)
    # the base book, then the 2 x slippage re-race
    assert shapes == {"book": ["trail", "trail"], "null": ["trail", "trail"]}


def test_a_fixed_idea_carries_no_trail_only_data():
    out = screen_idea.screen_ticker(IDEAS["turn_of_month"], "AAA", random_walk(2600), ALWAYS)
    assert out.null_timeout_r == [] and out.stressed is None


def test_a_trail_idea_races_only_trail_outcomes():
    out = screen_idea.screen_ticker(_trail_probe(), "AAA", random_walk(2600), ALWAYS)
    allowed = set(race_mod.SHAPE_OUTCOMES["trail"])
    assert out.events
    assert {row["outcome"] for row in out.events} <= allowed
    assert set(out.null_outcomes) <= allowed
    assert "target" not in out.null_outcomes and "gap_target" not in out.null_outcomes


def test_trail_null_timeout_r_is_every_null_timeout():
    out = screen_idea.screen_ticker(_trail_probe(), "AAA", random_walk(2600), ALWAYS)
    assert out.null_outcomes["timeout"] > 0
    assert len(out.null_timeout_r) == out.null_outcomes["timeout"]
    assert all(np.isfinite(out.null_timeout_r))


def test_stressed_rows_equal_a_rerun_at_twice_the_slippage():
    df = random_walk(2600)
    idea = _trail_probe()
    base = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, slippage_bps=5.0, commission=0.0)
    double = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS, slippage_bps=10.0, commission=0.0)
    assert base.stressed == [{"entry_date": r["entry_date"], "r_event": r["r_event"],
                              "r_null": r["r_null"]} for r in double.events]
    assert [r["entry_date"] for r in base.stressed] == [r["entry_date"] for r in base.events]
    assert all(s["r_event"] < r["r_event"] for s, r in zip(base.stressed, base.events))


def _screen(events, null_outcomes, *, null_timeout_r=(), stressed=None):
    empty_rank = pd.DataFrame(columns=["year", "event"]
                              + [f"fwd_{h}" for h in forward.HORIZONS])
    return screen_idea.TickerScreen(
        ticker="AAA", counters=Counter(), events=events,
        null_outcomes=Counter(null_outcomes),
        excess={h: [] for h in forward.HORIZONS}, rank=empty_rank,
        null_timeout_r=list(null_timeout_r), stressed=stressed)


def _row(day, r_event, r_null, outcome):
    return {"ticker": "AAA", "entry_date": day, "exit_date": day,
            "r_event": r_event, "r_null": r_null, "outcome": outcome}


def test_summarise_reports_timeouts_per_book():
    rows = [_row("2012-03-01", 2.0, 0.5, "timeout"), _row("2012-04-02", -1.0, 0.0, "stop"),
            _row("2013-05-01", 4.0, 0.5, "timeout"), _row("2013-06-03", 1.5, 0.5, "trail")]
    screen = _screen(rows, {"timeout": 2, "trail": 5, "stop": 3}, null_timeout_r=[0.5, 1.5])
    out = screen_idea.summarise([screen])
    assert out["timeouts"]["event"] == (2, 0.5, pytest.approx(3.0))
    assert out["timeouts"]["null"] == (2, 0.2, pytest.approx(1.0))


def test_summarise_timeouts_and_stress_are_empty_for_an_empty_book():
    out = screen_idea.summarise([_screen([], {})])
    assert out["timeouts"] == {"event": (0, None, None), "null": (0, None, None)}
    assert out["stress"] is None


def test_summarise_stress_verdict_pools_only_stressed_rows():
    rows = [_row("2012-03-01", 2.0, 0.5, "timeout"), _row("2013-04-02", -1.0, 0.0, "stop")]
    stressed = [{"entry_date": "2012-03-01", "r_event": 1.9, "r_null": 0.45},
                {"entry_date": "2013-04-02", "r_event": -1.1, "r_null": -0.05}]
    trail = _screen(rows, {"timeout": 1}, null_timeout_r=[0.3], stressed=stressed)
    fixed = _screen([_row("2014-01-02", 1.0, 0.0, "target")], {"target": 1})
    out = screen_idea.summarise([trail, fixed])
    assert out["stress"].n == 2
    assert out["stress"].delta_exp_r == pytest.approx(((1.9 - 0.45) + (-1.1 + 0.05)) / 2)
    assert screen_idea.summarise([fixed])["stress"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: the nine new tests FAIL (`AttributeError: ... has no attribute 'base_slippage'`, `TypeError: TickerScreen.__init__() got an unexpected keyword argument 'null_timeout_r'`, `KeyError: 'timeouts'`, the shape spies seeing `[None]`); every pre-existing test, including V163-2's `FIXED_DOC` / `FIXED_HYPOTHESIS` pins, still passes.

- [ ] **Step 3: Implement**

In `scripts/backtest/screen_idea.py`:

1. Import `field` beside `dataclass`:

```python
from dataclasses import dataclass, field
```

2. Below `COUNTER_ORDER = (...)` add:

```python
STRESS_SLIPPAGE_FACTOR = 2   # v163: the trail book re-priced at 2 x slippage; printed, never gating


def base_slippage(slippage_bps=None):
    """The slippage a run is priced at: the passed value, else config's.
    Never cast: the results doc prints it as config holds it."""
    return getattr(config, "SLIPPAGE_BPS", 5.0) if slippage_bps is None else slippage_bps
```

3. Replace `TickerScreen` with (two defaulted fields appended, so the hand-built `TickerScreen(...)` in the existing summarise test keeps working):

```python
@dataclass
class TickerScreen:
    ticker: str
    counters: Counter
    events: list
    null_outcomes: Counter
    excess: dict
    rank: pd.DataFrame
    null_timeout_r: list = field(default_factory=list)   # v163: trail only, net R per null timeout
    stressed: list | None = None                          # v163: trail only, 2 x slippage pairs
```

4. Replace `screen_ticker` (:107-131) with these four functions:

```python
def _books(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """The kept event book, its counters and its matched null at one cost
    setting, both raced under the idea's own shape (v163)."""
    cap, shape = idea.time_cap_bars, idea.race_shape
    booked, counts = race.run_book(df, ctx["raw"], cap, member=ctx["member"],
                                   warm=ctx["warm"], atr=ctx["atr"], shape=shape, **costs)
    draw = null.matched_null(df, booked.event_pos,
                             null.eligible_mask(ctx["raw"], ctx["member"], ctx["warm"], cap),
                             null.K, null.null_seed(idea.name, ticker), cap=cap,
                             atr=ctx["atr"], trend=ctx["trend"], shape=shape, **costs)
    counts["dropped_no_match"] = draw.dropped_no_match
    return booked.take(np.isin(booked.event_pos, draw.event_pos)), counts, draw


def _null_timeout_r(idea: Idea, draw) -> list:
    """Trail only: net R of every null race that ran to its cap."""
    if idea.race_shape != "trail":
        return []
    raced = draw.null_race
    return [float(r) for r in raced.r[raced.outcome == "timeout"]]


def _stressed(idea: Idea, ticker: str, df: pd.DataFrame, ctx: dict, costs: dict):
    """Trail only: every kept event and its null mean re-raced at
    STRESS_SLIPPAGE_FACTOR x the base slippage. Slippage never moves an exit
    bar, so the overlap rule and the null draw (same seed) keep the same
    events; only the R changes."""
    if idea.race_shape != "trail":
        return None
    stress = {"slippage_bps": STRESS_SLIPPAGE_FACTOR * base_slippage(costs["slippage_bps"]),
              "commission": costs["commission"]}
    kept, _, draw = _books(idea, ticker, df, ctx, stress)
    return [{"entry_date": row["entry_date"], "r_event": row["r_event"], "r_null": row["r_null"]}
            for row in _event_rows(ticker, df.index, kept, draw.null_mean_r)]


def screen_ticker(idea: Idea, ticker: str, df: pd.DataFrame, spans, *,
                  slippage_bps=None, commission=None) -> TickerScreen:
    costs = {"slippage_bps": slippage_bps, "commission": commission}
    atr = indicators.atr(df)
    sma200 = indicators.sma(df["Close"], 200)
    member = null.member_mask(df.index, spans)
    warm = race.warm_mask(atr, sma200) & (df.index >= pd.Timestamp(EVENT_START))
    ctx = {"raw": np.asarray(idea.events(df).reindex(df.index, fill_value=False), dtype=bool),
           "member": member, "warm": warm, "atr": atr,
           "trend": null.trend_state(df, sma200)}
    kept, counts, draw = _books(idea, ticker, df, ctx, costs)
    fwd = {h: forward.forward_atr(df, atr, h) for h in forward.HORIZONS}
    return TickerScreen(
        ticker=ticker, counters=Counter(counts),
        events=_event_rows(ticker, df.index, kept, draw.null_mean_r),
        null_outcomes=Counter(draw.null_race.outcome.tolist()),
        excess={h: forward.excess_drift(fwd[h], draw.event_pos, draw.groups)
                for h in forward.HORIZONS},
        rank=_rank_frame(df.index, ctx["raw"], member & warm, fwd),
        null_timeout_r=_null_timeout_r(idea, draw),
        stressed=_stressed(idea, ticker, df, ctx, costs))
```

5. Above `summarise`, add the two aggregators, and give `summarise` two new keys (the rest of its body is unchanged):

```python
def _book_timeouts(count: int, total: int, values) -> tuple:
    return (count, count / total if total else None, _mean(values))


def _timeouts(screens, events) -> dict:
    """(count, share of the book, mean net R) of timeouts, event and null
    books. The null mean is trail only: fixed screens keep no null R."""
    event_r = [row["r_event"] for row in events if row["outcome"] == "timeout"]
    null_mix = _sum_counters(screen.null_outcomes for screen in screens)
    null_r = [r for screen in screens for r in screen.null_timeout_r]
    return {"event": _book_timeouts(len(event_r), len(events), event_r),
            "null": _book_timeouts(null_mix["timeout"], sum(null_mix.values()), null_r)}


def _stress(screens):
    """The 2 x slippage verdict over the trail pairs; None for a fixed idea."""
    if all(screen.stressed is None for screen in screens):
        return None
    rows = [row for screen in screens if screen.stressed is not None
            for row in screen.stressed]
    return verdict.decide([verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                           for row in rows])


def summarise(screens, skipped=None) -> dict:
    events = [row for screen in screens for row in screen.events]
    paired = [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
              for row in events]
    return {"verdict": verdict.decide(paired), "events": events,
            "counters": _sum_counters(screen.counters for screen in screens),
            "skipped": Counter(skipped or {}),
            "event_outcomes": Counter(row["outcome"] for row in events),
            "null_outcomes": _sum_counters(screen.null_outcomes for screen in screens),
            "mean_r_event": _mean([row["r_event"] for row in events]),
            "mean_r_null": _mean([row["r_null"] for row in events]),
            "drift": _drift(screens), "rank": _rank(screens),
            "timeouts": _timeouts(screens, events), "stress": _stress(screens)}
```

6. In `_run_info`, read the slippage through the one helper (same value, so the fixed doc is unchanged):

```python
def _run_info(args, q) -> dict:
    return {"ledger_id": ledger_id(args.idea), "q": q, "date": args.date,
            "start": args.start, "end": args.end,
            "slippage_bps": base_slippage(None),
            "commission": commission_r()}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: all PASS, `0 failed`, `0 xfailed` — the pre-existing tests and V163-2's byte-identity pins untouched and green.

Then the null tests (the `shape` kwarg crosses into them):

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/backtesting/screen/test_null.py`
Expected: PASS.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_idea.py`
Expected: no output.

- [ ] **Step 6: Commit**

The guardrails hook tokenises any Bash command naming the screen script; every quote in these lines is closed, so they pass it.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add scripts/backtest/screen_idea.py tests/scripts/test_screen_idea.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): screen_ticker races the idea shape; trail timeout and 2x slippage data" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree shows no change from this task.

### Task V163-6: Trail rendering — per-shape trade line, "Trail race" section, per-shape ledger hypothesis, docstring

**Model:** sonnet — rendering and text inside one script, fully specified, guarded by V163-2's byte-identity pins.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (module docstring :1-14, screen import :32, `_render_head` :252-272, `render_results` :346-351, `ledger_row` :362-370 — line numbers as on `main`)
- Test: `tests/scripts/test_screen_idea.py` (append only)

**Interfaces:**
- Consumes: `Idea.race_shape` (V163-1); `race.SHAPE_OUTCOMES`, `_render_arms(summary, names)` (V163-2); `trail.TRAIL_ATR` (V163-3); `STRESS_SLIPPAGE_FACTOR`, `summarise(...)["timeouts"]`, `summarise(...)["stress"]`, test helpers `_trail_probe()`, `_screen(...)`, `_row(...)` (V163-5).
- Produces:
  - `screen_idea._render_trade(idea, run) -> str` — fixed: today's trade line, byte for byte; trail: the chandelier line.
  - `screen_idea._render_trail(summary: dict, run: dict) -> list` — heading `## Trail race (reported, never gating)`; rendered only for a trail idea, between `## Both arms` and `## Per year`.
  - `screen_idea.hypothesis(idea) -> str` — fixed: today's text, byte for byte; trail: contains `chandelier 3.0 ATR trail race, initial stop 1.5 ATR, cap <cap>`. `ledger_row` calls it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_screen_idea.py`:

```python
# --- v163: trail rendering

from swingbot.core.backtesting.screen import trail as trail_mod  # noqa: E402

RUN_INFO = {"ledger_id": "screen-trail_probe", "q": None, "date": "2026-10-15",
            "start": screen_idea.WINDOW_START, "end": screen_idea.WINDOW_END,
            "slippage_bps": 5.0, "commission": 0.02}


def _trail_render_inputs():
    rows = [_row("2012-03-01", 2.0, 0.5, "timeout"), _row("2013-04-02", -1.0, 0.0, "stop"),
            _row("2014-05-01", 1.2, 0.1, "trail"), _row("2015-06-01", 0.4, -0.2, "gap_trail")]
    stressed = [{"entry_date": r["entry_date"], "r_event": r["r_event"] - 0.05,
                 "r_null": r["r_null"] - 0.04} for r in rows]       # every d falls by 0.01
    screen = _screen(rows, {"timeout": 3, "trail": 9, "stop": 6, "gap_stop": 1, "gap_trail": 1},
                     null_timeout_r=[0.2, 0.4, 0.9], stressed=stressed)
    screen.counters.update(skipped_overlap=7)
    universe = screen_idea.Universe(intervals={}, members=["AAA"], cached=["AAA"], missing=[])
    return screen_idea.summarise([screen]), universe


def test_fixed_trade_line_is_unchanged():
    assert screen_idea._render_trade(IDEAS["turn_of_month"], RUN_INFO) == (
        "**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap "
        "through either level fills at the open; stop first on a bar touching both; "
        "costs 5.0 bps a side + 0.0200R commission.")


def test_trail_trade_line_names_the_trail_and_no_target():
    line = screen_idea._render_trade(_trail_probe(), RUN_INFO)
    assert line.startswith("**Trade:** entry next open; initial stop 1.5 x ATR14")
    assert "no target" in line and "chandelier" in line
    assert f"{trail_mod.TRAIL_ATR} x ATR14[t]" in line
    assert "60 bars" in line and "initial 1R" in line
    assert line.endswith("costs 5.0 bps a side + 0.0200R commission.")
    assert "chandelier" in screen_idea.__doc__


def test_trail_doc_has_the_trail_section_and_only_trail_exits():
    summary, universe = _trail_render_inputs()
    doc = screen_idea.render_results(_trail_probe(), summary, universe, RUN_INFO)
    assert (doc.index("## Both arms") < doc.index("## Trail race (reported, never gating)")
            < doc.index("## Per year"))
    for name in race_mod.SHAPE_OUTCOMES["trail"]:
        assert f"| {name} |" in doc, name
    assert "| target |" not in doc and "| gap_target |" not in doc
    assert "(`skipped_overlap`) = 7" in doc
    assert "| races | 4 | 20 |" in doc
    assert "| timeouts (share) | 1 (25.0%) | 3 (15.0%) |" in doc
    assert "| mean timeout R, after costs | +2.0000R | +0.5000R |" in doc
    assert "At 10.0 bps a side (2 x slippage, both fills)" in doc
    assert "change vs the base book -0.0100R" in doc
    assert "no target" in doc


def test_a_fixed_doc_has_no_trail_section_and_no_trail_rows():
    summary, universe = _trail_render_inputs()
    doc = screen_idea.render_results(IDEAS["turn_of_month"], summary, universe, RUN_INFO)
    assert "## Trail race" not in doc
    assert "| gap_trail |" not in doc and "| trail |" not in doc
    assert "| target |" in doc


def test_the_stress_line_says_so_when_there_are_no_stressed_pairs():
    summary, universe = _trail_render_inputs()
    summary["stress"] = None
    lines = screen_idea._render_trail(summary, RUN_INFO)
    assert lines[0] == "## Trail race (reported, never gating)"
    assert lines[-1] == "At 10.0 bps a side (2 x slippage): no stressed pairs."


def test_trail_hypothesis_names_the_shape_and_cap():
    idea = _trail_probe()
    text = screen_idea.hypothesis(idea)
    assert "chandelier 3.0 ATR trail race, initial stop 1.5 ATR, cap 60" in text
    assert "fixed" not in text
    v = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.2, 6, {}, {})
    row = screen_idea.ledger_row(idea, v, "docs/superpowers/results/x.md", "2026-10-15")
    stats.validate_ledger_row(row)
    assert row["hypothesis"] == text


def test_fixed_hypothesis_is_unchanged():
    idea = IDEAS["gap_volume"]
    assert screen_idea.hypothesis(idea) == (
        f"gap_volume: {idea.summary}; fixed 1.5/3.0 ATR race vs K=20 matched null, "
        "cap 20, PIT S&P 500 2010-2019, after costs (v140 screen)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: the seven new tests FAIL (`AttributeError: ... has no attribute '_render_trade'` / `'hypothesis'` / `'_render_trail'`, the doc lacking `## Trail race`); every earlier test passes.

- [ ] **Step 3: Implement**

In `scripts/backtest/screen_idea.py`:

1. Replace the module docstring's second paragraph (`Every event races a fixed trade ... appends ledger row screen-<idea>.`) with:

```python
"""v140 idea screen: one idea, one shot, PIT S&P 500 daily bars 2010-2019.

    python scripts/backtest/screen_idea.py --idea high52w \
        --cache-dir E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext

Every event races the idea's frozen shape (v163): ``fixed`` (entry next
open, stop 1.5 x ATR14, target 3 x ATR14, idea-specific time cap, costs) or
``trail`` (same entry and initial stop, no target, a chandelier stop
3 x ATR14[t] under the highest high of the bars before, cap >= 60 bars)
against K = 20 matched random bars raced the same way (same ticker, month
and trend state). verdict.decide applies the four-clause pass rule, the
same for both shapes; the script writes
docs/superpowers/results/<date>-screen-<idea>.md and appends ledger row
screen-<idea>. It refuses an idea already in the
ledger (one shot per idea) and a window end after 2019-12-31. --dry-run
prints the results doc and writes nothing; --tickers needs --dry-run.
"""
```

2. Add `trail` to the screen import:

```python
from swingbot.core.backtesting.screen import forward, indicators, null, race, trail, verdict  # noqa: E402,F401
```

3. Replace `_render_head` with `_render_trade` plus a `_render_head` that calls it (every other line unchanged):

```python
def _render_trade(idea, run) -> str:
    """The trade line for the idea's shape; the fixed text is today's, byte for byte."""
    costs = (f"costs {run['slippage_bps']} bps a side + {run['commission']:.4f}R "
             "commission.")
    if idea.race_shape == "trail":
        return (f"**Trade:** entry next open; initial stop {race.STOP_ATR} x ATR14[t] (1R); "
                "no target; chandelier trail: the stop on bar j is the higher of the "
                "initial stop and the highest high of bars t+1..j-1 minus "
                f"{trail.TRAIL_ATR} x ATR14[t], never lowered, ATR frozen at the signal "
                "bar; a gap through the stop fills at the open; no exit after "
                f"{idea.time_cap_bars} bars -> out at that close; R in the initial 1R; "
                + costs)
    return (f"**Trade:** entry next open; stop {race.STOP_ATR} x ATR14; target "
            f"{race.STOP_ATR * race.REWARD_RISK} x ATR14; a gap through either level "
            "fills at the open; stop first on a bar touching both; " + costs)


def _render_head(idea, v, run) -> list:
    params = ", ".join(f"{key}={value}" for key, value in idea.params.items())
    return [
        f"# v140 screen: `{idea.name}` -> {v.verdict}", "",
        f"**Ledger id:** `{run['ledger_id']}` (instrument `{INSTRUMENT}`); BH q = "
        f"{_fmt(run['q'], '.4f')} across the ledger (reported, never gating).", "",
        f"**Run:** {run['date']}; window {run['start']}..{run['end']}; "
        f"events count from {EVENT_START} (earlier bars only prime the indicators); the "
        f"year rule is {verdict.MIN_POSITIVE_YEARS} of {len(verdict.YEARS)} calendar years "
        f"({verdict.YEARS[0]}-{verdict.YEARS[-1]}); "
        f"`python scripts/backtest/screen_idea.py --idea {idea.name}`; null K = {null.K}, "
        f"seed {null.SEED_BASE} per (idea, ticker); bootstrap {stats.WEEK_BOOTSTRAP_RESAMPLES:,} "
        f"week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Trigger:** {idea.summary} ({idea.source}); params {params}; time cap "
        f"{idea.time_cap_bars} bars; {idea.direction} only.", "",
        _render_trade(idea, run), "",
        "**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`",
    ]
```

4. Below `_render_arms` add the trail section:

```python
def _share(share) -> str:
    return "n/a" if share is None else f"{100.0 * share:.1f}%"


def _render_stress(summary, run) -> str:
    """The trail book re-priced at STRESS_SLIPPAGE_FACTOR x slippage (spec
    § Costs): printed beside the verdict, never a clause of it."""
    stressed, base = summary["stress"], summary["verdict"]
    bps = STRESS_SLIPPAGE_FACTOR * run["slippage_bps"]
    if stressed is None or stressed.delta_exp_r is None:
        return f"At {bps} bps a side ({STRESS_SLIPPAGE_FACTOR} x slippage): no stressed pairs."
    change = None if base.delta_exp_r is None else stressed.delta_exp_r - base.delta_exp_r
    return (f"At {bps} bps a side ({STRESS_SLIPPAGE_FACTOR} x slippage, both fills): "
            f"ΔExpR {_fmt(stressed.delta_exp_r)}R, 95% week-clustered interval "
            f"{_fmt(stressed.ci_low)}R to {_fmt(stressed.ci_high)}R; change vs the base "
            f"book {_fmt(change)}R. Printed, never gating.")


def _render_trail(summary, run) -> list:
    """Trail ideas only: N beside the overlap skips, timeouts per book (the cap
    is the trail's main free parameter), and the 2 x slippage line."""
    v, t = summary["verdict"], summary["timeouts"]
    null_n = sum(summary["null_outcomes"].values())
    return ["## Trail race (reported, never gating)", "",
            f"Kept events N = {v.n}; skipped as overlapping an open race "
            f"(`skipped_overlap`) = {summary['counters']['skipped_overlap']}.", "",
            "| | event book | null book |", "|---|---|---|",
            f"| races | {v.n} | {null_n} |",
            f"| timeouts (share) | {t['event'][0]} ({_share(t['event'][1])}) | "
            f"{t['null'][0]} ({_share(t['null'][1])}) |",
            f"| mean timeout R, after costs | {_fmt(t['event'][2])}R | {_fmt(t['null'][2])}R |",
            "", _render_stress(summary, run)]
```

5. Replace `render_results` (as V163-2 left it) with:

```python
def render_results(idea, summary, universe, run) -> str:
    v = summary["verdict"]
    sections = [_render_head(idea, v, run), _render_universe(universe, summary),
                _render_verdict(v),
                _render_arms(summary, race.SHAPE_OUTCOMES[idea.race_shape])]
    if idea.race_shape == "trail":
        sections.append(_render_trail(summary, run))
    sections += [_render_years(v), _render_drift(summary)]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"
```

6. Replace `ledger_row` with `hypothesis` plus a `ledger_row` that calls it:

```python
def hypothesis(idea) -> str:
    """The ledger hypothesis, naming the shape and cap; the fixed text is
    today's, byte for byte."""
    if idea.race_shape == "trail":
        return (f"{idea.name}: {idea.summary}; chandelier {trail.TRAIL_ATR} ATR trail race, "
                f"initial stop {race.STOP_ATR} ATR, cap {idea.time_cap_bars} vs K={null.K} "
                "matched null, PIT S&P 500 2010-2019, after costs (v163 trail screen)")
    return (f"{idea.name}: {idea.summary}; fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race vs K={null.K} "
            f"matched null, cap {idea.time_cap_bars}, PIT S&P 500 "
            "2010-2019, after costs (v140 screen)")


def ledger_row(idea, v, record: str, day: str) -> dict:
    return {"id": ledger_id(idea.name), "date": day, "hypothesis": hypothesis(idea),
            "instrument": INSTRUMENT, "n": v.n,
            "exp_r": None if v.delta_exp_r is None else round(v.delta_exp_r, 4),
            "p": None if v.p is None else round(v.p, 4),
            "verdict": v.verdict, "record": record}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_idea.py`
Expected: all PASS, `0 failed`, `0 xfailed`. V163-2's `FIXED_DOC` and `FIXED_HYPOTHESIS` pins passing here is the proof that the fixed doc and ledger row are byte-identical; if either fails, the fixed branch of `_render_trade` or `hypothesis` drifted from today's text — fix the code, never the literal.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_idea.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add scripts/backtest/screen_idea.py tests/scripts/test_screen_idea.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): trail results doc -- trade line, Trail race section, shape in the ledger hypothesis" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree shows no change from this task.

# Phase 4: A/A calibration

### Task V163-7: A/A calibration script and its smoke test

**Model:** opus — a statistical harness: a fat-tailed regime generator and a false-pass/coverage measurement that must drive the real screen and verdict, not a re-implementation.

**Files:**
- Create: `scripts/backtest/screen_trail_calibration.py`
- Test: `tests/scripts/test_screen_trail_calibration.py` (create; `tests/scripts/` is already in a suite, no `tests/suites.toml` edit)

**Interfaces:**
- Consumes: `screen_idea.screen_ticker(idea, ticker, df, spans)` racing a trail idea (V163-5; `spans=None` means a member on every bar, `null.member_mask`); `screen_idea._iso_day`, `screen_idea._utf8_stdout` (exist on `main`); `Idea(..., race_shape="trail", time_cap_bars=60)` (V163-1); `trail.TRAIL_ATR` (V163-3); `verdict.decide(events, *, n_resamples, seed)`, `verdict.SCREEN_PASS/SCREEN_FAIL/SCREEN_UNDERPOWERED`, `verdict.Verdict` (exist).
- Produces (V163-8 runs it):
  - Constants `REPLICATES = 200`, `SEED = 20261015`, `TICKERS = 24`, `BARS = 2600`, `EVENT_RATE = 0.02`, `T_DF = 3`, `VOL_STATES = (0.010, 0.025)`, `SWITCH_PROB = (0.02, 0.05)`, `CAP = 60`, `FALSE_PASS_MAX = 0.05`.
  - `synthetic_frame(rng, bars=BARS, start="2010-01-04") -> pd.DataFrame`; `random_events(index, rng, rate=EVENT_RATE) -> pd.Series`.
  - `replicate(seed: int, *, tickers=TICKERS, bars=BARS, rate=EVENT_RATE, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES) -> verdict.Verdict`.
  - `calibrate(replicates=REPLICATES, seed=SEED, *, tickers=TICKERS, n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES, out=print) -> dict` with keys `replicates, verdicts, false_pass, false_pass_rate, covered, coverage, mean_n`; replicate r uses seed `seed + r`.
  - `render(result: dict, params: dict, day: str) -> str` (`params` keys `replicates, seed, tickers, resamples`).
  - CLI `python scripts/backtest/screen_trail_calibration.py [--replicates N] [--seed N] [--tickers N] [--resamples N] [--date YYYY-MM-DD] [--out-dir DIR] [--dry-run]`, writing `<out-dir>/<date>-trail-race-calibration.md`; exit 0 iff `false_pass_rate <= FALSE_PASS_MAX`, else 1.

Design notes the implementer must keep:
- The script **never reads a cached price file**: no `load_frame`, no cache path, no `data/` read. A test pins the source text.
- The results doc name `<date>-trail-race-calibration.md` deliberately does not match `*-screen-<idea>.md` (the guardrails hook and `scripts/dev/select_tests.py` glob that pattern for registered ideas).
- The calibration idea is built in memory (`Idea(name="aa_trail_calibration", ...)`), never registered in `IDEA_MODULES`, never written to the ledger.
- `screen_ticker` also computes the trail-only 2 × slippage re-race and forward drift that the calibration does not read; that costs run time, not correctness, and keeps the calibration on the exact production path.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_screen_trail_calibration.py`:

```python
"""v163 A/A calibration script: generator, replicate smoke test, CLI."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_trail_calibration as cal  # noqa: E402

from swingbot.core.backtesting.screen import verdict  # noqa: E402

SMALL = {"tickers": 2, "n_resamples": 200}
QUIET = {"out": lambda *a, **k: None}


def _v(label, n, delta, low, high):
    return verdict.Verdict(label, n, delta, low, high, None, 0, {}, {})


FAKE = [_v(verdict.SCREEN_PASS, 400, 0.2, 0.05, 0.3),
        _v(verdict.SCREEN_FAIL, 380, 0.01, -0.05, 0.07),
        _v(verdict.SCREEN_UNDERPOWERED, 0, None, None, None),
        _v(verdict.SCREEN_FAIL, 350, -0.02, -0.08, 0.04)]


def _fake_replicates(monkeypatch, verdicts):
    seeds = []
    feed = iter(verdicts)

    def fake(seed, **kwargs):
        seeds.append(seed)
        return next(feed)

    monkeypatch.setattr(cal, "replicate", fake)
    return seeds


def test_synthetic_frame_is_valid_ohlcv_inside_the_window():
    df = cal.synthetic_frame(np.random.default_rng(1))
    assert len(df) == cal.BARS
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    prices = df[["Open", "High", "Low", "Close"]]
    assert not df.isna().any().any() and (prices > 0).all().all()
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert df.index[0] == pd.Timestamp("2010-01-04")
    assert df.index[-1] <= pd.Timestamp("2019-12-31") and df.index.year.max() == 2019


def test_synthetic_returns_are_fat_tailed_and_volatility_clustered():
    df = cal.synthetic_frame(np.random.default_rng(2), bars=20_000)
    r = np.diff(np.log(df["Close"].to_numpy()))
    z = (r - r.mean()) / r.std()
    assert np.mean(z ** 4) > 4.0                       # a Gaussian's kurtosis is 3
    ranks = np.argsort(np.argsort(np.abs(r)))          # rank autocorrelation of |r|
    assert np.corrcoef(ranks[:-1], ranks[1:])[0, 1] > 0.03


def test_random_events_carry_the_rate_and_the_index():
    idx = pd.bdate_range("2010-01-04", periods=10_000)
    events = cal.random_events(idx, np.random.default_rng(3))
    assert events.index.equals(idx) and events.dtype == bool
    assert abs(events.mean() - cal.EVENT_RATE) < 0.005


def test_a_replicate_runs_the_real_screen_and_verdict_deterministically():
    a = cal.replicate(11, **SMALL)
    assert isinstance(a, verdict.Verdict) and a.n > 0
    assert cal.replicate(11, **SMALL) == a
    assert cal.replicate(12, **SMALL).delta_exp_r != a.delta_exp_r


def test_a_replicate_races_the_trail_shape(monkeypatch):
    shapes = []
    real = cal.screen_idea.race.run_book

    def spy(*args, **kwargs):
        shapes.append(kwargs.get("shape"))
        return real(*args, **kwargs)

    monkeypatch.setattr(cal.screen_idea.race, "run_book", spy)
    cal.replicate(5, tickers=1, n_resamples=100)
    assert shapes and set(shapes) == {"trail"}


def test_calibrate_counts_false_passes_and_coverage(monkeypatch):
    seeds = _fake_replicates(monkeypatch, FAKE)
    out = cal.calibrate(4, seed=100, **QUIET)
    assert seeds == [100, 101, 102, 103]
    assert out["replicates"] == 4 and len(out["verdicts"]) == 4
    assert out["false_pass"] == 1 and out["false_pass_rate"] == 0.25
    assert out["covered"] == 2 and out["coverage"] == 0.5     # no interval never covers
    assert out["mean_n"] == pytest.approx((400 + 380 + 0 + 350) / 4)


def test_calibrate_refuses_zero_replicates():
    with pytest.raises(ValueError):
        cal.calibrate(0, **QUIET)


def test_render_states_the_rate_the_rule_the_generator_and_every_seed(monkeypatch):
    _fake_replicates(monkeypatch, FAKE)
    result = cal.calibrate(4, seed=100, **QUIET)
    params = {"replicates": 4, "seed": 100, "tickers": 2, "resamples": 200}
    text = cal.render(result, params, "2026-10-15")
    assert text.startswith("# v163 trail race A/A calibration -> **over** the 5% false-pass limit")
    for needle in ("1 of 4 = 25.0%", "≤ 5% (gating)", "2 of 4 = 50.0%", "reported, not gated",
                   "df = 3", "0.01 / 0.025", "seed 100", "--replicates 4 --seed 100",
                   "SCREEN-PASS 1, SCREEN-FAIL 2, SCREEN-UNDERPOWERED 1", "| 103 |",
                   "no cached price file"):
        assert needle in text, needle


def test_dry_run_prints_the_doc_and_writes_nothing(tmp_path, capsys):
    code = cal.main(["--replicates", "1", "--tickers", "1", "--resamples", "100",
                     "--date", "2026-10-15", "--out-dir", str(tmp_path / "out"), "--dry-run"])
    assert code in (0, 1)
    assert "# v163 trail race A/A calibration" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_a_run_writes_the_dated_doc_and_the_exit_code_follows_the_rate(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    argv = ["--replicates", "2", "--date", "2026-10-15", "--out-dir", str(out_dir)]
    _fake_replicates(monkeypatch, [FAKE[1], FAKE[3]])
    assert cal.main(argv) == 0
    doc = out_dir / "2026-10-15-trail-race-calibration.md"
    assert "within the 5% false-pass limit" in doc.read_text(encoding="utf-8")
    _fake_replicates(monkeypatch, [FAKE[0], FAKE[1]])
    assert cal.main(argv) == 1
    assert "**over**" in doc.read_text(encoding="utf-8")


def test_the_script_never_names_a_price_cache():
    source = (ROOT / "scripts" / "backtest" / "screen_trail_calibration.py").read_text(
        encoding="utf-8")
    for forbidden in ("backtest_cache", "load_frame", "DEFAULT_CACHE", "read_csv"):
        assert forbidden not in source, forbidden
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_trail_calibration.py`
Expected: collection error, `ModuleNotFoundError: No module named 'screen_trail_calibration'`.

- [ ] **Step 3: Implement**

Create `scripts/backtest/screen_trail_calibration.py`:

```python
#!/usr/bin/env python3
"""v163 A/A calibration of the trail race shape (spec § Testing).

    python scripts/backtest/screen_trail_calibration.py
    python scripts/backtest/screen_trail_calibration.py --replicates 3 --tickers 2 --resamples 500 --dry-run

Each replicate builds a synthetic universe of TICKERS fat-tailed,
volatility-clustered daily frames (Student-t innovations, df = 3, under a
two-state volatility regime), marks random "events" with no planted effect,
runs every ticker through the real screen_ticker with a trail idea (cap 60)
and the pooled pairs through the real verdict.decide. Reported: the
full-verdict false-pass rate and the coverage of the 95% interval for
dExpR = 0. Exit 0 iff the false-pass rate is at most FALSE_PASS_MAX (5%);
coverage is reported, not gated. Synthetic data only: no cached price file
is ever read, and nothing is written to the pre-registration ledger.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import null, race, trail, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import Idea  # noqa: E402

REPLICATES = 200
SEED = 20261015
TICKERS = 24
BARS = 2600                       # 2010-01-04 .. December 2019, business days
EVENT_RATE = 0.02
T_DF = 3
VOL_STATES = (0.010, 0.025)       # daily log-return sigma: calm, stressed
SWITCH_PROB = (0.02, 0.05)        # per-bar chance of leaving calm, leaving stressed
CAP = 60
FALSE_PASS_MAX = 0.05
IDEA_NAME = "aa_trail_calibration"
START = "2010-01-04"
RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"
PROGRESS_EVERY = 10


def _regimes(rng, bars: int) -> np.ndarray:
    """A two-state Markov volatility path: 0 calm, 1 stressed."""
    flips = rng.random(bars)
    state = np.empty(bars, dtype=int)
    current = 0
    for i in range(bars):
        state[i] = current
        if flips[i] < SWITCH_PROB[current]:
            current = 1 - current
    return state


def synthetic_frame(rng, bars: int = BARS, start: str = START) -> pd.DataFrame:
    """One driftless OHLCV frame: unit-variance Student-t log returns scaled
    by the regime's sigma; the open gaps off the prior close; wicks beyond
    the open/close body. High >= max(Open, Close), Low <= min(Open, Close)."""
    sigma = np.asarray(VOL_STATES)[_regimes(rng, bars)]
    unit_t = rng.standard_t(T_DF, bars) / np.sqrt(T_DF / (T_DF - 2))
    close = 100.0 * np.exp(np.cumsum(sigma * unit_t))
    open_ = np.r_[100.0, close[:-1]] * np.exp(0.3 * sigma * rng.standard_normal(bars))
    high = np.maximum(open_, close) * np.exp(np.abs(0.5 * sigma * rng.standard_normal(bars)))
    low = np.minimum(open_, close) * np.exp(-np.abs(0.5 * sigma * rng.standard_normal(bars)))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": np.full(bars, 1e6)},
                        index=pd.bdate_range(start, periods=bars, name="Date"))


def random_events(index, rng, rate: float = EVENT_RATE) -> pd.Series:
    """Each bar an "event" independently with probability ``rate``."""
    return pd.Series(rng.random(len(index)) < rate, index=index)


def _idea(events: pd.Series) -> Idea:
    return Idea(name=IDEA_NAME, events=lambda df: events, time_cap_bars=CAP,
                race_shape="trail", summary="random events, no planted effect",
                source="v163 A/A calibration")


def replicate(seed: int, *, tickers: int = TICKERS, bars: int = BARS,
              rate: float = EVENT_RATE,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES) -> verdict.Verdict:
    """One synthetic universe through the real screen and the real verdict."""
    rng = np.random.default_rng(seed)
    paired = []
    for i in range(tickers):
        df = synthetic_frame(rng, bars)
        screen = screen_idea.screen_ticker(_idea(random_events(df.index, rng, rate)),
                                           f"R{seed}T{i:03d}", df, None)
        paired += [verdict.PairedEvent(row["entry_date"], row["r_event"] - row["r_null"])
                   for row in screen.events]
    return verdict.decide(paired, n_resamples=n_resamples)


def _covers_zero(v) -> bool:
    """An undefined interval (no events) does not cover."""
    return v.ci_low is not None and v.ci_low <= 0.0 <= v.ci_high


def calibrate(replicates: int = REPLICATES, seed: int = SEED, *, tickers: int = TICKERS,
              n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES, out=print) -> dict:
    if replicates < 1:
        raise ValueError("the calibration needs at least one replicate")
    verdicts = []
    for r in range(replicates):
        verdicts.append(replicate(seed + r, tickers=tickers, n_resamples=n_resamples))
        if (r + 1) % PROGRESS_EVERY == 0 or r + 1 == replicates:
            out(f"[calibration] {r + 1}/{replicates} replicates "
                f"({100.0 * (r + 1) / replicates:.0f}%)", flush=True)
    false_pass = sum(v.verdict == verdict.SCREEN_PASS for v in verdicts)
    covered = sum(_covers_zero(v) for v in verdicts)
    return {"replicates": replicates, "verdicts": verdicts, "false_pass": false_pass,
            "false_pass_rate": false_pass / replicates, "covered": covered,
            "coverage": covered / replicates,
            "mean_n": float(np.mean([v.n for v in verdicts]))}


def _render_head(result: dict, params: dict, day: str) -> list:
    holds = result["false_pass_rate"] <= FALSE_PASS_MAX
    command = (f"python scripts/backtest/screen_trail_calibration.py --replicates "
               f"{params['replicates']} --seed {params['seed']} --tickers {params['tickers']} "
               f"--resamples {params['resamples']}")
    return [
        f"# v163 trail race A/A calibration -> {'within' if holds else '**over**'} "
        f"the {FALSE_PASS_MAX:.0%} false-pass limit", "",
        "**Spec:** `docs/superpowers/specs/2026-10-15-v163-screen-trail-race-design.md` "
        "§ Testing (A/A calibration).", "",
        f"**Run:** {day}; `{command}`; replicate r uses seed {params['seed']} + r; "
        f"{params['tickers']} tickers x {BARS} business days from {START}; bootstrap "
        f"{params['resamples']:,} week resamples, seed {stats.WEEK_BOOTSTRAP_SEED}.", "",
        f"**Generator:** Student-t innovations, df = {T_DF}, scaled to unit variance; "
        f"two-state volatility regime, daily sigma {VOL_STATES[0]} / {VOL_STATES[1]}, "
        f"per-bar switch probability {SWITCH_PROB[0]} (calm -> stressed) / "
        f"{SWITCH_PROB[1]} (stressed -> calm); no drift. Events: every bar independently "
        f"with probability {EVENT_RATE}, no planted effect. Synthetic data only; no cached "
        "price file is read and no ledger row is written.", "",
        f"**Race:** the real `screen_ticker` with a trail idea (cap {CAP} bars, chandelier "
        f"{trail.TRAIL_ATR} x ATR14[t], initial stop {race.STOP_ATR} x ATR14[t]) against a "
        f"trail matched null (K = {null.K}), pooled through the real `verdict.decide` "
        "(pass rule unchanged).",
    ]


def _render_result(result: dict) -> list:
    n = result["replicates"]
    labels = Counter(v.verdict for v in result["verdicts"])
    tally = ", ".join(f"{name} {labels.get(name, 0)}" for name in
                      (verdict.SCREEN_PASS, verdict.SCREEN_FAIL, verdict.SCREEN_UNDERPOWERED))
    return [
        "## Result", "", "| | value | rule |", "|---|---|---|",
        f"| full-verdict false-pass rate | {result['false_pass']} of {n} = "
        f"{result['false_pass_rate']:.1%} | ≤ {FALSE_PASS_MAX:.0%} (gating) |",
        f"| coverage of the 95% interval for ΔExpR = 0 | {result['covered']} of {n} = "
        f"{result['coverage']:.1%} | reported, not gated |",
        f"| mean kept events N per replicate | {result['mean_n']:.1f} | — |", "",
        f"Verdicts: {tally}. A replicate with no interval (no events) counts as not covering.",
    ]


def _render_replicates(result: dict, seed: int) -> list:
    lines = ["## Per replicate", "",
             "| seed | verdict | N | ΔExpR | lower 95% | upper 95% |",
             "|---|---|---|---|---|---|"]
    fmt = screen_idea._fmt
    lines += [f"| {seed + r} | {v.verdict} | {v.n} | {fmt(v.delta_exp_r)} | "
              f"{fmt(v.ci_low)} | {fmt(v.ci_high)} |"
              for r, v in enumerate(result["verdicts"])]
    return lines


def render(result: dict, params: dict, day: str) -> str:
    sections = [_render_head(result, params, day), _render_result(result),
                _render_replicates(result, params["seed"])]
    return "\n\n".join("\n".join(lines) for lines in sections) + "\n"


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--replicates", type=_positive, default=REPLICATES)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--tickers", type=_positive, default=TICKERS)
    p.add_argument("--resamples", type=_positive, default=stats.WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--date", type=screen_idea._iso_day, default=date.today().isoformat(),
                   help="results-doc date; default today")
    p.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--dry-run", action="store_true", help="print the doc, write nothing")
    return p


def _progress(message: str, flush: bool = False) -> None:
    print(message, file=sys.stderr, flush=flush)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    screen_idea._utf8_stdout()
    result = calibrate(args.replicates, args.seed, tickers=args.tickers,
                       n_resamples=args.resamples, out=_progress)
    params = {"replicates": args.replicates, "seed": args.seed,
              "tickers": args.tickers, "resamples": args.resamples}
    text = render(result, params, args.date)
    if args.dry_run:
        print(text)
    else:
        path = Path(args.out_dir) / f"{args.date}-trail-race-calibration.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"false-pass {result['false_pass']}/{result['replicates']} = "
              f"{result['false_pass_rate']:.1%}, coverage {result['coverage']:.1%} -> {path}")
    return 0 if result["false_pass_rate"] <= FALSE_PASS_MAX else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/scripts/test_screen_trail_calibration.py`
Expected: all 11 PASS, `0 failed`, `0 xfailed`. If the fat-tail or clustering test fails, the generator is wrong (sigma not regime-indexed, or the t draw not scaled) — fix the generator, never loosen the threshold.

Then a three-replicate smoke run of the CLI, printed only:

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_trail_calibration.py --replicates 3 --tickers 4 --resamples 500 --dry-run`
Expected: three `[calibration]` progress lines on stderr, then the doc on stdout with a `## Result` table and three `## Per replicate` rows; exit code 0 or 1 (three replicates say nothing about the rate — this only proves the path runs). Note the wall time per replicate; V163-8 uses it to size the real run.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_trail_calibration.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add scripts/backtest/screen_trail_calibration.py tests/scripts/test_screen_trail_calibration.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "feat(v163): A/A calibration of the trail race on fat-tailed synthetic universes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree shows no change from this task.

### Task V163-8: Run the 200-replicate calibration and commit its results doc

**Model:** sonnet — runs one pre-registered command and records its output; the judgement is only "over or under 5%", and an over is a stop, never a fix.

**Files:**
- Create: `docs/superpowers/results/2026-10-15-trail-race-calibration.md` (written by the script; the date is the run day, so a later run day gives a later file name — use whatever `--date` defaults to)

**Interfaces:**
- Consumes: `scripts/backtest/screen_trail_calibration.py` with its defaults (V163-7): `REPLICATES = 200`, `SEED = 20261015`, `TICKERS = 24`, `BARS = 2600`, 10,000 week resamples, exit 0 iff the false-pass rate ≤ 5%.
- Produces: the recorded false-pass rate and coverage. Nothing in code consumes it; V163-9 cites the doc by glob.

**Pre-registered, before the run:** the parameters are the V163-7 constants, frozen in a commit before this task. The run is done **once**. Whatever it prints is the answer: no second seed, no more replicates, no change to the generator, the trail multiple, the cap or the pass rule after seeing the rate (`backtest-methodology.md` § Closed pre-registrations applies in spirit: a calibration re-run until it passes calibrates nothing).

- [ ] **Step 1: Check the frozen state**

Run: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race status --short`
Expected: empty (V163-7 committed, nothing uncommitted that could change the run).

Run: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race grep -n "^REPLICATES = 200\|^SEED = 20261015\|^TICKERS = 24\|^FALSE_PASS_MAX = 0.05" -- scripts/backtest/screen_trail_calibration.py`
Expected: four hits.

- [ ] **Step 2: Run it once, in the background**

Size it first from V163-7 Step 4's wall time per replicate (that smoke run used 4 tickers; scale by 24/4 for the screen part). A run longer than about 15 minutes goes to the `backtest-runner` agent (root `CLAUDE.md` § Long backtest/grid runs) with exactly this command; shorter, run it with `run_in_background: true`. The script prints a percent every 10 replicates on stderr either way.

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_trail_calibration.py > C:/Users/HuyCao/AppData/Local/Temp/v163-calibration.log 2>&1; echo "exit=$?" >> C:/Users/HuyCao/AppData/Local/Temp/v163-calibration.log
```

The script's default `--out-dir` resolves from its own path, so the doc lands in the worktree's `docs/superpowers/results/`, never the main tree's. Do not poll the log while it runs; wait for the completion notification.

- [ ] **Step 3: Read the outcome**

Run: `tail -3 C:/Users/HuyCao/AppData/Local/Temp/v163-calibration.log`
Expected: the last progress line `[calibration] 200/200 replicates (100%)`, a summary line `false-pass k/200 = x%, coverage y% -> .../docs/superpowers/results/<date>-trail-race-calibration.md`, and `exit=0` or `exit=1`.

Then read the doc's head and result table only (the per-replicate table is 200 rows):

Run: `grep -n -B 2 -A 12 "^## Result" E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/docs/superpowers/results/*-trail-race-calibration.md`
Expected: the false-pass row, the coverage row, the mean-N row and the verdict tally. Check that the mean N sits well above `verdict.MIN_N` = 300: if most replicates are `SCREEN-UNDERPOWERED`, the false-pass rate measures nothing — report that as the finding (same stop as Step 5), do not enlarge the universe and re-run.

- [ ] **Step 4: Commit the doc — either outcome**

The doc is a measured answer whether it is within or over the limit; it is committed as generated, never hand-edited.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add docs/superpowers/results/
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "docs(v163): trail race A/A calibration, 200 seeded replicates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: one new file committed on the branch; the main tree shows no change from this task.

- [ ] **Step 5: Gate**

- `exit=0` (false-pass rate ≤ 5%) and mean N ≥ 300: the instrument is calibrated; carry on with V163-9 / V163-10. Report the rate and the coverage to the controller in one line each.
- `exit=1` (rate over 5%), or mean N below 300: **stop the plan here.** Do not start V163-10. Report to the controller: the false-pass rate, the coverage, the mean N and the doc path, as a partner question ("the unchanged pass rule passes trail noise at x%; how to proceed?"). Do not tune anything; the spec forbids a different threshold for this shape, so the answer is the partner's.

### Task V163-9: Methodology doc — Stage −2 names both shapes; `AGENTS.md` mirror

**Model:** haiku — two exact text replacements given verbatim below, checked by the mirror test.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (§ Funnel stages, Stage −2 bullet, lines 62-70 on `main`)
- Modify: `AGENTS.md` (lines 161-163 on `main`)

**Interfaces:**
- Consumes: nothing in code. The text names `RACE`, `fixed` / `trail`, the cap floor 60 and `tests/backtesting/screen/test_ideas_registry.py` (V163-1), the trail rule (V163-3), the trail doc's printed lines (V163-6) and the calibration doc (V163-7/V163-8, cited by glob so this task may run before V163-8).
- Produces: nothing consumed later.

Both edits go in **one commit** (root `CLAUDE.md` § Claude is the operator; Codex follows). Use the Edit tool with the exact old text below; never `sed` a doc.

- [ ] **Step 1: Amend the Stage −2 bullet**

In `docs/claude/backtest-methodology.md`, replace exactly:

```markdown
  point-in-time S&P 500 (2010-01-01..2019-12-31, `data/backtest_cache_ext`)
  races one fixed trade — entry next open, stop 1.5 × ATR14, target
  3 × ATR14, gaps through either level filled at the open, an idea-specific
  time cap, 5 bps slippage a side plus commission — against K = 20 random
  non-event bars from the same ticker, month and trend state
  (`close > SMA200`). Pass rule, all four: paired ΔExpR ≥ +0.10R; lower 95%
```

with:

```markdown
  point-in-time S&P 500 (2010-01-01..2019-12-31, `data/backtest_cache_ext`)
  races the idea's one frozen **race shape** — `fixed` (v140: entry next
  open, stop 1.5 × ATR14, target 3 × ATR14, gaps through either level
  filled at the open, an idea-specific time cap) or `trail` (v163: same
  entry and 1.5 × ATR14 initial stop, no target, a chandelier stop
  3 × ATR14[t] under the highest high of the bars before the one tested,
  never lowered, ATR frozen at the event bar, a gap through the stop filled
  at the open, cap ≥ 60 bars; R always in the initial 1R) — with 5 bps
  slippage a side plus commission, against K = 20 random non-event bars
  from the same ticker, month and trend state (`close > SMA200`), raced
  the same shape. **One shape per idea**: an idea module's `RACE` constant
  (default `fixed`) is part of its frozen definition, pinned in
  `tests/backtesting/screen/test_ideas_registry.py`; a changed shape is a
  new idea with a new name, and the trigger of any closed idea never
  returns under the other shape. The pass rule below is the same for both
  shapes. A trail results doc also prints timeouts per book and the book
  re-priced at 2 × slippage, never gating; the trail's A/A calibration is
  `docs/superpowers/results/*-trail-race-calibration.md`. A trail fail is
  "no edge under this exit", and closed; a trail pass is not tradeable
  until a nightly stop-update path exists. Pass rule, all four: paired
  ΔExpR ≥ +0.10R; lower 95%
```

The line after (`  bound > 0 (week-clustered bootstrap, 10,000 resamples); same sign in ≥ 7`) stays as it is.

- [ ] **Step 2: Mirror it in `AGENTS.md`**

In `AGENTS.md`, replace exactly:

```markdown
Specs from v141 carry `**Screen:**` under `Edge:` (an entry strategy or filter
cites a `SCREEN-PASS` ledger row from `scripts/backtest/screen_idea.py`; a screen
fail is closed, never re-screened) and from v146 `**Panel:**` (1-3 role skills run
```

with:

```markdown
Specs from v141 carry `**Screen:**` under `Edge:` (an entry strategy or filter
cites a `SCREEN-PASS` ledger row from `scripts/backtest/screen_idea.py`; a screen
fail is closed, never re-screened under either race shape; each idea freezes one,
`fixed` or v163 `trail` with cap >= 60, under the same pass rule) and from v146
`**Panel:**` (1-3 role skills run
```

- [ ] **Step 3: Verify**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/doc_section.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/docs/claude/backtest-methodology.md "Funnel stages"`
Expected: the section prints with the new Stage −2 text and the funnel table unchanged below it.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS, `0 failed`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py changed`
Expected: `0 failed`, `0 xfailed` (any doc-shape test that reads these two files runs here).

- [ ] **Step 4: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race add docs/claude/backtest-methodology.md AGENTS.md
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race commit -m "docs(v163): Stage -2 names both race shapes, one per idea; AGENTS.md mirror" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main tree shows no change from this task.

# Phase 5: gate

### Task V163-10: Full suite, once

**Model:** haiku — one command dispatched to the `test-runner` agent and a read of its verdict.

**Files:** none changed (a failure is fixed in the task that owns the file, re-run alone).

**Interfaces:**
- Consumes: every earlier task committed on the branch; V163-8 reported a false-pass rate ≤ 5% with mean N ≥ 300 (if it did not, this task does not run).
- Produces: the green full-suite result the close-out needs.

- [ ] **Step 1: Preconditions**

Run: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race status --short`
Expected: empty.

Run: `git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race log --oneline main..HEAD`
Expected: one commit per task V163-1..V163-9 (V163-8's results doc among them).

- [ ] **Step 2: Complexity over every changed Python file**

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/swingbot/core/backtesting/screen/ E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_idea.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/backtest/screen_trail_calibration.py`
Expected: no output.

- [ ] **Step 3: The full suite, through the `test-runner` agent**

Dispatch `test-runner` (so the output stays out of this context) with:

`python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py full`

Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 4: On a failure**

Fix it in the owning file, re-run that test alone (`python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v163-screen-trail-race/scripts/dev/testrun.py file <test>`), commit the fix on the branch with a `fix(v163): ...` message ending in the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line, and do **not** re-run the whole suite. A failure in a test this plan never touched that also fails on `main` is reported to the controller, not fixed here.

- [ ] **Step 5: Report**

Report to the controller: the suite verdict (passed / failed / xfailed counts), the V163-8 false-pass rate and coverage, and the branch head. Do not edit the plan files (they live on `main`; the controller updates the index's `## Progress` and runs `/panel` on the diff and `/close-out`). No full suite after the merge back to `main`.

