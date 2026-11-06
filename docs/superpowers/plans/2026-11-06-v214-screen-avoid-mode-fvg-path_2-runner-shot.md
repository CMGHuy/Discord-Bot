# v214 — Avoid mode for the idea screen, and the overhead bearish-gap idea — Part 2: runner, call sites, hook, docs, the shot (V214-6..V214-12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md`](../specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md)
**Index:** [`2026-11-06-v214-screen-avoid-mode-fvg-path_0-index.md`](2026-11-06-v214-screen-avoid-mode-fvg-path_0-index.md). Its Goal, Architecture, `## Global Constraints`, `## Review Focus`, `## Parallelisation` and `## Task ledger` apply to every task here. Its signatures are the contract.
**Part 1:** [`2026-11-06-v214-screen-avoid-mode-fvg-path_1-core.md`](2026-11-06-v214-screen-avoid-mode-fvg-path_1-core.md) creates what this part consumes: `verdict.MODES`, `verdict.SCREEN_AVOID_PASS`, `verdict.ControlArm`, `decide(events, *, mode=, control=)`, `Verdict.mode`/`years_negative`/`control`, `ideas.MODES`, `Idea.mode`/`Idea.states`, `screen.errors.IdeaError` and the idea `fvg_overhead_aged` with `states(df)`.

This part covers the runner (control arm, pool exclusion, per-ticker errors, mode-threaded verdicts, the avoid read-outs), the other `decide` call sites (G5), the spec-header hook (G6), the docs (G7) and the one shot (G8).

**Sequencing gate, checked by symbol.** Every task starts with these two commands. If either prints nothing, stop and report `BLOCKED: v211 V211-4/V211-6 not merged on main`.

```bash
git grep -n "context_kind" main -- swingbot/core/backtesting/screen/ideas/__init__.py
git grep -n "checkpoint_dir" main -- scripts/backtest/screen_idea.py
```

**The v211 pins.** Every task touching `scripts/backtest/screen_idea.py` runs these, untouched, and they must stay green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_context_runner.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_idea.py
git grep -ln "hypotheses_pre_v211" -- tests
```

The last command names the test file that loads the hypothesis golden; run it with `testrun.py file` too.

**The screen hook.** A PreToolUse hook tokenises every Bash command that names the screen runner. Edit `screen_idea.py` and its tests with the editor tools, never a heredoc, and keep every such command on one shell-parsable line.

**Line numbers are indicative.** v211 (V211-4..6, and possibly V211-5, 11, 11b, 12) reshapes `screen_idea.py` before these tasks start. Find every function by name (`git grep -n "def <name>" -- scripts/backtest/screen_idea.py`) and build on the shape you find.

# Phase 3 — Runner (waves C, D, E)

### Task V214-6: Runner: avoid books — condition exclusion, control arm, per-ticker errors

**Model:** opus — the pool exclusion and the control-arm draw decide what every avoid verdict compares against; a wrong mask or seed biases d_c silently.

**Files:**
- Modify: `scripts/backtest/screen_idea.py`:
  - the import of `IdeaError`;
  - `TickerScreen.avoid` and `CONTROL_SEED_SUFFIX`;
  - new `_avoid_context`, `_overnight`, `_avoid_arm`, `_guarded_errors` and `_screen_guarded`;
  - `ticker_context`, `_null_pool` and `screen_ticker`;
  - the per-ticker call inside `screen_universe` (V211-6 routes it through `_screen_or_resume`), and `count_universe`.
- Create: `tests/backtest_scripts/test_screen_avoid_mode.py`. `tests/backtest_scripts/` already belongs to a suite.

**Interfaces:**
- Consumes:
  - V214-4: `Idea.mode`, `Idea.states`.
  - V214-5: `screen.errors.IdeaError`, and the `states(df)` contract: columns `event`, `control_condition`, `condition` (bool) and `bottom` (float, NaN off event bars) on `df.index`.
  - V211-6: `screen_universe(..., checkpoint_dir=None)`, `_screen_or_resume`, `_EMPTY`.
  - Existing: `null.matched_null`, `null.null_seed`, `null.K`, `null.MIN_CANDIDATES`, `_event_rows`, `_books`.
- Produces (V214-7 and V214-8 read these):
  - `TickerScreen.avoid: dict | None = None`, the **last** field (after V211-11's `shock` when it exists). For an avoid idea it is `{"control": rows, "below_floor": int, "kept": int, "excluded": int, "population": int, "overnight": int}`. `rows` have the `_event_rows` shape, and each row's `r_null` is the mean R of that event's control bars. Edge ideas get `None`.
  - `CONTROL_SEED_SUFFIX = ":control"`. The control arm's seed is `null.null_seed(idea.name + CONTROL_SEED_SUFFIX, ticker)`.
  - `ticker_context(...)` gains keys `"control_condition"`, `"condition"` (bool arrays) and `"bottom"` (float array) for avoid ideas only. An edge idea's dict is unchanged, key for key.
  - An `IdeaError` raised by an avoid idea aborts that ticker only:
    - `skipped["idea_error"] += 1` and `skipped[f"idea_error:{ticker}"] = 1`;
    - one line, `[<idea>] <ticker>: idea error: <message>`, through `out(..., flush=True)`;
    - the ticker is never checkpointed, and the run continues.
    - An edge idea's errors are never caught.

- [ ] **Step 0: Gate and prerequisites.** Run the two `git grep` commands from this part's header. Then each of these must print a line:

```bash
git grep -n "class IdeaError" -- swingbot/core/backtesting/screen/errors.py
git grep -n "_mode_problem" -- swingbot/core/backtesting/screen/ideas/__init__.py
git grep -n "fvg_overhead_aged" -- swingbot/core/backtesting/screen/ideas/__init__.py
git grep -n "def _screen_or_resume" -- scripts/backtest/screen_idea.py
```

Read the current `TickerScreen`, `ticker_context`, `screen_universe`, `_screen_or_resume` and `count_universe`; v211 shaped them.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_screen_avoid_mode.py`:

```python
"""v214 runner: an avoid idea's condition bars leave the null and the control
pools; the control arm draws from control_condition bars on its own seed; a
per-ticker IdeaError is counted and skipped; edge ideas are untouched."""
import functools
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402

from swingbot.core.backtesting.screen import null, verdict  # noqa: E402
from swingbot.core.backtesting.screen.errors import IdeaError  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea  # noqa: E402
from tests.backtesting.screen.helpers import random_walk  # noqa: E402

ALWAYS = [("2000-01-01", "9999-12-31")]
QUIET = {"out": lambda *a, **k: None}
AVOID_KEYS = {"control", "below_floor", "kept", "excluded", "population", "overnight"}


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    """500 week resamples instead of 10,000: same code path, test-speed."""
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def fake_states(df):
    """Cheap, deterministic avoid states. An event on every 40th bar from 300;
    the condition holds on each event bar and the two after it; control on
    every 7th bar outside the condition; bottom = Close + 1 on event bars."""
    pos = np.arange(len(df))
    event = (pos >= 300) & ((pos - 300) % 40 == 0)
    condition = event | np.roll(event, 1) | np.roll(event, 2)
    control = (pos % 7 == 3) & ~condition
    bottom = np.where(event, df["Close"].to_numpy(dtype=float) + 1.0, np.nan)
    return pd.DataFrame({"event": event, "control_condition": control,
                         "condition": condition, "bottom": bottom}, index=df.index)


def _avoid(name, states):
    return Idea(name=name, events=lambda df: states(df)["event"].rename(name),
                time_cap_bars=20, mode="avoid", states=states)


AVOID = _avoid("fake_avoid", fake_states)


def _no_control(df):
    out = fake_states(df)
    out["control_condition"] = False
    return out


def _fragile(df):
    if len(df) < 2000:
        raise IdeaError("detector failed on a short frame")
    return fake_states(df)


def _write_csv(path, df):
    df.rename_axis("Date").to_csv(path)


def _universe(tmp_path, frames):
    for ticker, df in frames.items():
        _write_csv(tmp_path / f"{ticker}.csv", df)
    names = list(frames)
    return screen_idea.Universe(intervals={t: ALWAYS for t in names}, members=names,
                                cached=names, missing=[])


def _spy_matched_null(monkeypatch):
    seen = []
    real = null.matched_null

    def spy(df, event_pos, eligible, k, seed, **kwargs):
        seen.append((np.asarray(eligible, dtype=bool).copy(), seed))
        return real(df, event_pos, eligible, k, seed, **kwargs)

    monkeypatch.setattr(null, "matched_null", spy)
    return seen


def test_condition_bars_leave_both_pools_and_the_control_has_its_own_seed(monkeypatch):
    seen = _spy_matched_null(monkeypatch)
    df = random_walk(2600)
    states = fake_states(df)
    screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    (pool, seed), (control_pool, control_seed) = seen          # the null, then the control arm
    condition = states["condition"].to_numpy()
    assert condition.any() and not pool[condition].any() and not control_pool[condition].any()
    assert not control_pool[~states["control_condition"].to_numpy()].any()
    assert control_pool.any() and (control_pool <= pool).all()
    assert seed == null.null_seed("fake_avoid", "AAA")
    assert control_seed == null.null_seed("fake_avoid" + screen_idea.CONTROL_SEED_SUFFIX, "AAA")
    assert screen_idea.CONTROL_SEED_SUFFIX == ":control"


def test_the_avoid_block_pairs_kept_events_with_their_control_mean():
    df = random_walk(2600)
    out = screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    block = out.avoid
    assert set(block) == AVOID_KEYS
    assert block["kept"] == len(out.events) > 0
    assert len(block["control"]) + block["below_floor"] == block["kept"]
    by_date = {row["entry_date"]: row for row in out.events}
    assert all(row["r_event"] == by_date[row["entry_date"]]["r_event"]
               for row in block["control"])
    dates = [row["entry_date"] for row in block["control"]]
    assert dates == sorted(dates) and set(dates) <= set(by_date)


def test_the_read_out_counts_match_the_masks():
    df = random_walk(2600)
    ctx = screen_idea.ticker_context(AVOID, df, ALWAYS)
    out = screen_idea.screen_ticker(AVOID, "AAA", df, ALWAYS)
    population = ctx["member"] & ctx["warm"]
    assert out.avoid["population"] == int(population.sum())
    assert out.avoid["excluded"] == int((ctx["condition"] & population).sum())
    signal = [df.index.get_loc(pd.Timestamp(row["entry_date"])) - 1 for row in out.events]
    opens, bottom = df["Open"].to_numpy(), ctx["bottom"]
    assert out.avoid["overnight"] == sum(int(opens[t + 1] >= bottom[t]) for t in signal)


def test_events_below_the_control_floor_still_count_in_n():
    """Review Focus 1: no control bar anywhere -> every event is below the
    floor, yet every event stays in the null-paired book."""
    out = screen_idea.screen_ticker(_avoid("no_control", _no_control), "AAA",
                                    random_walk(2600), ALWAYS)
    assert out.events and out.avoid["control"] == []
    assert out.avoid["below_floor"] == out.avoid["kept"] == len(out.events)


def test_states_is_read_once_per_ticker():
    calls = []

    def counting(df):
        calls.append(len(df))
        return fake_states(df)

    screen_idea.screen_ticker(_avoid("counting", counting), "AAA", random_walk(2600), ALWAYS)
    assert calls == [2600]


def test_an_edge_idea_is_untouched():
    df = random_walk(2600)
    idea = IDEAS["turn_of_month"]
    ctx = screen_idea.ticker_context(idea, df, ALWAYS)
    assert not {"condition", "control_condition", "bottom"} & set(ctx)
    assert screen_idea.screen_ticker(idea, "AAA", df, ALWAYS).avoid is None


def test_an_idea_error_skips_only_that_ticker(tmp_path):
    uni = _universe(tmp_path, {"AAA": random_walk(2600), "BAD": random_walk(1500, seed=3),
                               "CCC": random_walk(2600, seed=5)})
    lines = []
    screens, skipped = screen_idea.screen_universe(
        _avoid("fragile", _fragile), uni, tmp_path,
        out=lambda *a, **k: lines.append(a[0]))
    assert [s.ticker for s in screens] == ["AAA", "CCC"]
    assert skipped == Counter({"idea_error": 1, "idea_error:BAD": 1})
    assert "[fragile] BAD: idea error: detector failed on a short frame" in lines


def test_an_idea_error_is_never_checkpointed(tmp_path):
    uni = _universe(tmp_path, {"AAA": random_walk(2600), "BAD": random_walk(1500, seed=3)})
    directory = tmp_path / "ck"
    screen_idea.screen_universe(_avoid("fragile", _fragile), uni, tmp_path,
                                checkpoint_dir=directory, **QUIET)
    assert (directory / "AAA.pkl").exists() and not (directory / "BAD.pkl").exists()


def test_an_edge_idea_error_is_not_swallowed(tmp_path):
    def boom(df):
        raise IdeaError("edge ideas get no guard")

    uni = _universe(tmp_path, {"AAA": random_walk(2600)})
    edge = Idea(name="edge_boom", events=boom, time_cap_bars=20)
    with pytest.raises(IdeaError, match="no guard"):
        screen_idea.screen_universe(edge, uni, tmp_path, **QUIET)


def test_count_only_shares_the_pool_and_the_guard(tmp_path, monkeypatch):
    seen = []
    real = null.draw_groups

    def spy(df, event_pos, eligible, *args, **kwargs):
        seen.append(np.asarray(eligible, dtype=bool).copy())
        return real(df, event_pos, eligible, *args, **kwargs)

    monkeypatch.setattr(null, "draw_groups", spy)
    df = random_walk(2600)
    screen_idea.count_ticker(AVOID, "AAA", df, ALWAYS)
    assert not seen[0][fake_states(df)["condition"].to_numpy()].any()
    uni = _universe(tmp_path, {"AAA": df, "BAD": random_walk(1500, seed=3)})
    total = screen_idea.count_universe(_avoid("fragile", _fragile), uni, tmp_path, **QUIET)
    assert total["tickers"] == 1
    assert total["skipped"] == Counter({"idea_error": 1, "idea_error:BAD": 1})


@pytest.mark.slow
def test_the_real_idea_screens_one_ticker_deterministically():
    df = random_walk(700)
    idea = IDEAS["fvg_overhead_aged"]
    a = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    b = screen_idea.screen_ticker(idea, "AAA", df, ALWAYS)
    assert set(a.avoid) == AVOID_KEYS
    assert (a.events, a.avoid) == (b.events, b.avoid)
```

If V211-6 named the checkpoint file differently from `<ticker>.pkl`, follow its name in `test_an_idea_error_is_never_checkpointed`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py`
Expected: FAIL. `screen_ticker` books the fake idea through `raw_events` and has no `avoid` field (`AttributeError: 'TickerScreen' object has no attribute 'avoid'`), and `CONTROL_SEED_SUFFIX` is missing. `test_an_edge_idea_is_untouched` and `test_an_edge_idea_error_is_not_swallowed` pass.

- [ ] **Step 3: Implement in `scripts/backtest/screen_idea.py`**

- Import: `from swingbot.core.backtesting.screen.errors import IdeaError`.
- `TickerScreen`: the last field, `avoid: dict | None = None  # v214: avoid only, control-arm rows and read-out counts`.
- `CONTROL_SEED_SUFFIX = ":control"`, beside `_ENTRY_OFFSET`, with the comment `#: v214 G1: the control arm's own seed stream, null_seed(idea + ":control", ticker).`
- `_avoid_context(idea: Idea, df: pd.DataFrame) -> dict`:
  - an edge idea returns `{}`;
  - an avoid idea calls `idea.states(df)` **once**, reindexes it to `df.index`, and returns `{"raw", "control_condition", "condition", "bottom"}`;
  - `raw` is the `event` column. The three bool columns are `fillna(False)` numpy bool arrays, and `bottom` is a float array.
- `ticker_context`: take `avoid = _avoid_context(idea, df)`. `raw` is `avoid.pop("raw")` when `avoid` is non-empty; otherwise it is today's `raw_events(...)` expression. Append `**avoid` after the existing keys. The edge dict keeps its keys and order.
- `_null_pool(idea, ctx, exclude=None)`: drop both `exclude` and `ctx.get("condition")` from the pool. Loop over the two masks and skip `None`. Docstring addition: `v214: an avoid idea's condition bars never enter the pool.` An edge `ctx` has no `condition` key, so its pool is unchanged. `count_ticker` inherits the exclusion with no edit of its own.
- `_overnight(df: pd.DataFrame, event_pos, bottom: np.ndarray) -> int`: the number of event positions `t` with `Open[t + 1] >= bottom[t]`. A booked next-open event always has bar `t + 1`.
- `_avoid_arm(idea, ticker, df, ctx, costs, kept) -> dict | None`:
  - an edge idea returns `None`;
  - otherwise the pool is `_null_pool(idea, ctx) & ctx["control_condition"]`;
  - the draw is `null.matched_null(df, kept.event_pos, pool, null.K, null.null_seed(idea.name + CONTROL_SEED_SUFFIX, ticker), cap=idea.time_cap_bars, atr=ctx["atr"], trend=ctx["trend"], shape=idea.race_shape, direction=idea.direction, **costs)`;
  - `matched = kept.take(np.isin(kept.event_pos, draw.event_pos))`, the same pattern as `_books`;
  - `population = ctx["member"] & ctx["warm"]`.

  It returns:
  - `control`: `_event_rows(ticker, df.index, matched, draw.null_mean_r, entry_offset=_ENTRY_OFFSET[idea.entry])`;
  - `below_floor`: `int(draw.dropped_no_match)`;
  - `kept`: `len(kept.event_pos)`;
  - `excluded`: `int((ctx["condition"] & population).sum())`;
  - `population`: `int(population.sum())`;
  - `overnight`: `_overnight(df, kept.event_pos, ctx["bottom"])`.

  The floor is `null.MIN_CANDIDATES` inside `matched_null`; do not re-implement it.
- `screen_ticker`: add `avoid=_avoid_arm(idea, ticker, df, ctx, costs, kept)` to the `TickerScreen(...)` call.
- `_guarded_errors(idea: Idea) -> tuple`: `(IdeaError,)` for an avoid idea, `()` for an edge idea (`except ()` catches nothing).
- `_screen_guarded(idea: Idea, ticker: str, skipped: Counter, out, call)`:
  - returns `call()`;
  - on `except _guarded_errors(idea) as exc`, it counts both keys, prints `out(f"[{idea.name}] {ticker}: idea error: {exc}", flush=True)` and returns `None`.
- `screen_universe`: the per-ticker call becomes `result = _screen_guarded(idea, ticker, skipped, out, lambda: _screen_or_resume(...same arguments...))`. `None` appends nothing; `_EMPTY` and a screen behave as today. A failing ticker raises before `checkpoint.save`, so it is never pickled, and a restart re-screens it.
- `count_universe`: wrap the `count_ticker(...)` call the same way, with `total["skipped"]` as the counter. `None` adds nothing to the total.

Each touched function stays below complexity 15.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py
python -m pytest tests/backtest_scripts/test_screen_avoid_mode.py -m slow -v
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS, the slow test included. The complexity gate reports no regression. Then run the v211 pins from this part's header; all green, untouched.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_avoid_mode.py
git commit -m "feat(screen): avoid books -- condition bars leave both pools, control arm on its own seed, per-ticker idea errors (v214 V214-6)"
```

### Task V214-7: Runner: mode-threaded verdicts and the avoid verdict table (G5)

**Model:** opus — every runner verdict must carry the idea's mode while every edge output stays byte-identical; a missed call site prints an edge label for an avoid idea.

**Files:**
- Modify: `scripts/backtest/screen_idea.py`:
  - `summarise`, `_stress`, `_decide`, and the `_decide` calls inside `with_short_blocks`;
  - `_run_screens` (V211-6), which hands `idea.mode` to `summarise`;
  - new `_avoid_pairs`, `_decide_kwargs` and `_years_text`;
  - `_render_verdict`, which becomes a dispatcher over the new `_render_edge_verdict` and `_render_avoid_verdict`;
  - the `publish` print line.
- Modify: `tests/backtest_scripts/test_screen_avoid_mode.py` (append).

**Interfaces:**
- Consumes:
  - V214-2: `verdict.MODES`, `verdict.SCREEN_AVOID_PASS`, `decide(events, *, mode=, control=)`, `Verdict.mode`/`years_negative`/`control`, and `ControlArm(n, delta_exp_r, ci_low, ci_high, per_year)`. An avoid `Verdict` always carries a `ControlArm`, with `n == 0` when no control rows exist.
  - V214-3: `stats.VERDICTS` ending in `"SCREEN-AVOID-PASS"`.
  - V214-4: `ideas.MODES`, `Idea.mode`.
  - V214-6: `TickerScreen.avoid["control"]` rows.
- Produces (V214-8 reads these):
  - `summarise(screens, skipped=None, *, mode: str = "edge") -> dict`. Its keys are unchanged. In avoid mode `"verdict"` is `verdict.decide(paired, mode="avoid", control=_avoid_pairs(screens))`.
  - `_avoid_pairs(screens) -> list[verdict.PairedEvent]`: every screen's `avoid["control"]` rows, in screen order, with `d = r_event − r_null`.
  - `_stress(screens, mode: str = "edge")` and `_decide(rows, mode: str = "edge")`.
  - `_render_verdict(v) -> list[str]`, which dispatches on `v.mode`. The edge text is today's, byte for byte.
  - `_years_text(v) -> str`: `"4/9 years"` (edge, today's text) or `"9/9 years negative"` (avoid).

- [ ] **Step 0: Gate and prerequisites.** Run the two `git grep` commands from this part's header. `git grep -n "CONTROL_SEED_SUFFIX" -- scripts/backtest/screen_idea.py` must print a line (V214-6). Read the current `summarise`, `_stress`, `_decide`, `with_short_blocks`, `_run_screens` and `publish`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_screen_avoid_mode.py`:

```python
# --- V214-7: mode-threaded verdicts ---------------------------------------

import re  # noqa: E402
from datetime import date, timedelta  # noqa: E402

from swingbot.core.backtesting.instrument import stats  # noqa: E402
from swingbot.core.backtesting.screen import forward  # noqa: E402
from swingbot.core.backtesting.screen import ideas as ideas_module  # noqa: E402

CLAUSES_AVOID = {"exp_r", "ci", "years", "n", "control_exp_r", "control_ci", "control_n"}


def _rows(n, r_event, r_null=0.0):
    """n rows, one per ISO week, cycling through 2011-2019."""
    out = []
    for i in range(n):
        day = date(verdict.YEARS[i % len(verdict.YEARS)], 1, 4) + timedelta(weeks=i // 9)
        out.append({"ticker": "AAA", "entry_date": day.isoformat(),
                    "exit_date": day.isoformat(), "r_event": r_event, "r_null": r_null,
                    "outcome": "stop"})
    return out


def _screen(events, arm=None, **fields):
    rank = pd.DataFrame(columns=["year", "event"] + [f"fwd_{h}" for h in forward.HORIZONS])
    avoid = None if arm is None else {"control": arm, "below_floor": 0, "kept": len(events),
                                      "excluded": 0, "population": 0, "overnight": 0}
    return screen_idea.TickerScreen(ticker="AAA", counters=Counter(), events=events,
                                    null_outcomes=Counter(),
                                    excess={h: [] for h in forward.HORIZONS}, rank=rank,
                                    avoid=avoid, **fields)


def _avoid_summary():
    """N = 400 at d = -0.5; N_c = 350 at d_c = -0.4: every avoid clause holds."""
    return screen_idea.summarise([_screen(_rows(400, -0.5), _rows(350, -0.5, -0.1))],
                                 mode="avoid")


def test_the_mode_vocabularies_agree():
    assert verdict.MODES == ideas_module.MODES == ("edge", "avoid")
    assert verdict.SCREEN_AVOID_PASS == stats.VERDICTS[-1] == "SCREEN-AVOID-PASS"


def test_an_avoid_summary_pairs_the_null_and_the_control_arm():
    v = _avoid_summary()["verdict"]
    assert (v.mode, v.verdict, v.n) == ("avoid", "SCREEN-AVOID-PASS", 400)
    assert set(v.clauses) == CLAUSES_AVOID and all(v.clauses.values())
    assert v.delta_exp_r == pytest.approx(-0.5)
    assert v.control.n == 350 and v.control.delta_exp_r == pytest.approx(-0.4)


def test_avoid_pairs_pool_every_screens_control_rows_in_order():
    first, last = _rows(3, -0.2, 0.1), _rows(2, 0.4, 0.5)
    pairs = screen_idea._avoid_pairs([_screen(_rows(3, 0.0), first),
                                      _screen(_rows(1, 0.0)), _screen(_rows(2, 0.0), last)])
    assert [p.d for p in pairs] == pytest.approx([-0.3, -0.3, -0.3, -0.1, -0.1])
    assert [p.entry_date for p in pairs] == [r["entry_date"] for r in first + last]


def test_an_edge_summary_is_unchanged():
    screens = [_screen(_rows(320, 0.3))]
    default, edge = screen_idea.summarise(screens), screen_idea.summarise(screens, mode="edge")
    assert default["verdict"] == edge["verdict"]
    v = default["verdict"]
    assert (v.mode, v.control, v.years_negative) == ("edge", None, None)
    assert set(v.clauses) == {"exp_r", "ci", "years", "n"}


def test_stress_and_decide_carry_the_mode():
    rows = _rows(50, -0.3)
    screens = [_screen(rows, stressed=rows)]
    assert screen_idea._stress(screens).mode == "edge"
    assert screen_idea._stress(screens, mode="avoid").mode == "avoid"
    assert screen_idea._decide(rows, "avoid").mode == "avoid"
    assert screen_idea._decide(None, "avoid") is None


def test_short_blocks_carry_the_mode():
    idea = Idea(name="short_avoid", events=lambda df: fake_states(df)["event"],
                time_cap_bars=20, direction="short", mode="avoid", states=fake_states)
    rows = _rows(40, -0.2)
    block = screen_idea.with_short_blocks({"events": rows}, [_screen(rows, control=rows)],
                                          idea, None)["short"]
    assert block["control"].mode == "avoid"


def test_the_avoid_verdict_table_states_the_avoid_rules():
    text = "\n".join(screen_idea._render_verdict(_avoid_summary()["verdict"]))
    assert text.startswith("## Verdict: SCREEN-AVOID-PASS")
    for row in ("| ΔExpR = mean(R_event − mean R_null) | -0.5000R | ≤ -0.10R | yes |",
                "| years with mean(d) < 0 | 9 of 9 | ≥ 7 | yes |",
                "| kept events N | 400 | ≥ 300 | yes |",
                "| control arm ΔExpR = mean(R_event − mean R_control) | -0.4000R | ≤ -0.10R | yes |",
                "| control arm events N_c | 350 | ≥ 300 | yes |",
                "One-sided bootstrap p (share of resamples ≥ 0): "):
        assert row in text
    assert "| upper 95% bound, week-clustered bootstrap | -0.5000R (lower -0.5000R) | < 0 | yes |" in text
    assert "| control arm upper 95% bound | -0.4000R (lower -0.4000R) | < 0 | yes |" in text
    assert "mean(d) > 0" not in text and "share of resamples ≤ 0" not in text


def test_years_text_per_mode():
    assert screen_idea._years_text(_avoid_summary()["verdict"]) == "9/9 years negative"
    edge = verdict.Verdict("SCREEN-FAIL", 412, 0.03, -0.01, 0.07, 0.23, 4, {}, {})
    assert screen_idea._years_text(edge) == "4/9 years"


def test_an_avoid_run_never_prints_an_edge_label(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(screen_idea.IDEAS, "fake_avoid", AVOID)
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\nAAA,2000-01-01,\nBBB,2000-01-01,\n",
                          encoding="utf-8")
    argv = ["--idea", "fake_avoid", "--cache-dir", str(cache), "--membership", str(membership),
            "--ledger", str(tmp_path / "ledger.jsonl"), "--results-dir", str(tmp_path / "r"),
            "--date", "2026-11-06", "--dry-run"]
    assert screen_idea.main(argv) == 0
    text = capsys.readouterr().out
    assert "## Verdict: SCREEN-" in text and "years with mean(d) < 0" in text
    assert re.search(r"(?<!AVOID-)SCREEN-PASS", text) is None
    assert "years with mean(d) > 0" not in text
```

`main` builds `--idea` choices from `IDEAS` when it is called, so `monkeypatch.setitem` registers the fake idea for that call only. If v211 made `with_short_blocks` read more summary keys, add them to the `{"events": rows}` literal; keep the assertion.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py`
Expected: FAIL. `summarise()` has no `mode` keyword (`TypeError: summarise() got an unexpected keyword argument 'mode'`), and `_avoid_pairs` and `_years_text` are missing. The V214-6 tests, `test_the_mode_vocabularies_agree` and `test_an_edge_summary_is_unchanged`'s first assertion still pass.

- [ ] **Step 3: Implement in `scripts/backtest/screen_idea.py`**

- `_avoid_pairs(screens) -> list`: `[verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"]) for s in screens if s.avoid for r in s.avoid["control"]]`.
- `_decide_kwargs(mode: str, screens=()) -> dict`:
  - edge returns `{}`, so every edge call stays the literal `verdict.decide(paired)` it is today. The runner tests' `functools.partial(..., n_resamples=500)` patch keeps working.
  - avoid returns `{"mode": "avoid", "control": _avoid_pairs(screens)}`.
- `summarise(screens, skipped=None, *, mode="edge")`: `"verdict": verdict.decide(paired, **_decide_kwargs(mode, screens))`. Nothing else changes.
- `_stress(screens, mode="edge")` and `_decide(rows, mode="edge")` pass `**_decide_kwargs(mode)`. These books have no control arm, so an avoid verdict there has `N_c = 0` and is `SCREEN-UNDERPOWERED`. That is never an edge label.
- `with_short_blocks`: both `_decide(...)` calls pass `idea.mode`.
- `_run_screens`: `summarise(screens, skipped, mode=idea.mode)`.
- Rename today's `_render_verdict` body, unchanged, to `_render_edge_verdict(v)`. `_render_verdict(v)` becomes `_VERDICT_RENDERERS[v.mode](v)`, with `_VERDICT_RENDERERS = {"edge": _render_edge_verdict, "avoid": _render_avoid_verdict}` defined below both functions.
- `_render_avoid_verdict(v) -> list` returns exactly these lines (`c = v.control`; `_fmt` and `_yes` as today; rule numbers from `verdict.PASS_EXP_R`, `verdict.MIN_POSITIVE_YEARS`, `verdict.YEARS` and `verdict.MIN_N`, never literals):

```text
## Verdict: {v.verdict}

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | {_fmt(v.delta_exp_r)}R | ≤ {-verdict.PASS_EXP_R:+.2f}R | {_yes(v.clauses['exp_r'])} |
| upper 95% bound, week-clustered bootstrap | {_fmt(v.ci_high)}R (lower {_fmt(v.ci_low)}R) | < 0 | {_yes(v.clauses['ci'])} |
| years with mean(d) < 0 | {v.years_negative} of {len(verdict.YEARS)} | ≥ {verdict.MIN_POSITIVE_YEARS} | {_yes(v.clauses['years'])} |
| kept events N | {v.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['n'])} |
| control arm ΔExpR = mean(R_event − mean R_control) | {_fmt(c.delta_exp_r)}R | ≤ {-verdict.PASS_EXP_R:+.2f}R | {_yes(v.clauses['control_exp_r'])} |
| control arm upper 95% bound | {_fmt(c.ci_high)}R (lower {_fmt(c.ci_low)}R) | < 0 | {_yes(v.clauses['control_ci'])} |
| control arm events N_c | {c.n} | ≥ {verdict.MIN_N} | {_yes(v.clauses['control_n'])} |

One-sided bootstrap p (share of resamples ≥ 0): {_fmt(v.p, '.4f')}. N < {verdict.MIN_N} or N_c < {verdict.MIN_N} is `SCREEN-UNDERPOWERED` whatever the other clauses say; the control arm is drawn from bars where the idea's control condition holds (G1), so a sign flip alone never passes.
```

- `_years_text(v) -> str`: avoid gives `f"{v.years_negative}/{len(verdict.YEARS)} years negative"`; edge gives `f"{v.years_positive}/{len(verdict.YEARS)} years"`. The `publish` print line uses it in place of its inline `{v.years_positive}/{len(verdict.YEARS)} years`, so the edge line is byte-identical.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_checkpoint.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS, no complexity regression. Then run the v211 pins from this part's header. `test_screen_idea.py::test_a_fixed_idea_renders_its_results_doc_byte_identical_to_v140` proves `_render_edge_verdict` is today's text.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_avoid_mode.py
git commit -m "feat(screen): every runner verdict carries the idea's mode; avoid verdict table (v214 V214-7)"
```

### Task V214-8: Runner: avoid read-outs, calibration printout, avoid hypothesis, ledger order

**Model:** sonnet — pooling and rendering of counts V214-6 already computes, in the runner's established `with_*` / `_render_*` pattern.

**Files:**
- Modify: `scripts/backtest/screen_idea.py`:
  - new constants `CALIBRATION_IDS`, `CALIBRATION_P`, `V211_SHOT_IDS` and `AVOID_COUNTS`;
  - new functions `with_avoid_blocks`, `_calibration`, `_avoid_run`, `_render_avoid`, `_render_calibration` and `_avoid_hypothesis`;
  - `hypothesis`, `render_results`, `publish` and `_run_screens`.
- Modify: `tests/backtest_scripts/test_screen_avoid_mode.py` (append).

**Interfaces:**
- Consumes:
  - V214-6: `TickerScreen.avoid` counts, and `skipped["idea_error:<TICKER>"]`.
  - V214-7: `summarise(..., mode=)`, `Verdict.control.per_year` (year → `(n, mean | None)`) and `_years_text`.
  - Existing: `stats.load_ledger` rows, `IDEAS`, `_share`, `_ratio`, `_fmt`, `_yes`.
- Produces (V214-12 reads the rendered doc):
  - `CALIBRATION_IDS = ("screen-high52w", "screen-gap_volume", "screen-sweep_reclaim_bos", "screen-range_breakdown_close")`.
  - `CALIBRATION_P = 0.975`.
  - `V211_SHOT_IDS = ("screen-shock_support_break_short", "screen-shock_failed_bounce_short")`.
  - `AVOID_COUNTS = ("below_floor", "kept", "excluded", "population", "overnight")`.
  - `with_avoid_blocks(summary, screens, idea) -> dict`. An avoid idea gets `"avoid"` = the five `AVOID_COUNTS` summed over the screens, plus `"errors"`: `{ticker: 1}` sorted by ticker. Any other idea gets the same dict object back, untouched.
  - `_calibration(rows) -> list[dict]`: one dict per `CALIBRATION_IDS` entry, in that order, with keys `"id"`, `"direction"`, `"exp_r"`, `"p"`, `"clause_1"`, `"clause_2"`.
  - `_avoid_run(run, idea, rows, row) -> dict`. An avoid idea gets `run` plus `"calibration"` and `"ledger_order"`; `"ledger_order"` is `{"position": len(rows) + 1, "preceding_v211": [ids of V211_SHOT_IDS already in rows, in ledger order]}`. Any other idea gets `run` back unchanged.
  - `render_results` appends `## Avoid mode (read-outs, never gating)` for `idea.mode == "avoid"` only.

- [ ] **Step 0: Gate and prerequisites.** Run the two `git grep` commands from this part's header. `git grep -n "def _render_avoid_verdict" -- scripts/backtest/screen_idea.py` must print a line (V214-7).

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_screen_avoid_mode.py`:

```python
# --- V214-8: avoid read-outs, calibration, hypothesis, ledger order --------

def _block(**counts):
    return {"control": [], **{key: counts.get(key, 0) for key in screen_idea.AVOID_COUNTS}}


def _ledger_row(row_id, exp_r=None, p=None):
    return {"id": row_id, "exp_r": exp_r, "p": p, "verdict": "SCREEN-FAIL"}


def test_with_avoid_blocks_sums_the_counts_and_lists_the_errors():
    a, b = _screen([]), _screen([])
    a.avoid = _block(below_floor=2, kept=10, excluded=30, population=900, overnight=1)
    b.avoid = _block(below_floor=1, kept=5, excluded=20, population=600, overnight=4)
    skipped = Counter({"idea_error": 2, "idea_error:ZZZ": 1, "idea_error:BAD": 1,
                       "empty_frame": 1})
    out = screen_idea.with_avoid_blocks({"skipped": skipped}, [a, b], AVOID)["avoid"]
    assert out == {"below_floor": 3, "kept": 15, "excluded": 50, "population": 1500,
                   "overnight": 5, "errors": {"BAD": 1, "ZZZ": 1}}
    assert list(out["errors"]) == ["BAD", "ZZZ"]


def test_with_avoid_blocks_leaves_an_edge_summary_alone():
    summary = {"skipped": Counter()}
    assert screen_idea.with_avoid_blocks(summary, [], IDEAS["gap_volume"]) is summary


def test_the_calibration_reads_the_four_closed_rows():
    rows = [_ledger_row("screen-high52w", -0.366, 1.0),
            _ledger_row("screen-gap_volume", -0.4639, 1.0),
            _ledger_row("screen-sweep_reclaim_bos", -0.05, 0.99),
            _ledger_row("other", -0.9, 1.0)]
    out = screen_idea._calibration(rows)
    assert [c["id"] for c in out] == list(screen_idea.CALIBRATION_IDS)
    assert (out[0]["direction"], out[0]["clause_1"], out[0]["clause_2"]) == ("long", True, True)
    assert (out[2]["clause_1"], out[2]["clause_2"]) == (False, True)
    assert out[3] == {"id": "screen-range_breakdown_close", "direction": "short",
                      "exp_r": None, "p": None, "clause_1": False, "clause_2": False}


def test_the_ledger_order_names_the_v211_shots_already_in():
    rows = [{"id": "screen-a"}, {"id": "screen-shock_failed_bounce_short"}]
    run = screen_idea._avoid_run({"q": 0.5}, AVOID, rows, {"id": "screen-fake_avoid"})
    assert run["ledger_order"] == {"position": 3,
                                   "preceding_v211": ["screen-shock_failed_bounce_short"]}
    assert len(run["calibration"]) == 4 and run["q"] == 0.5
    edge_run = {"q": 0.5}
    assert screen_idea._avoid_run(edge_run, IDEAS["gap_volume"], rows, {}) is edge_run


def test_the_avoid_hypothesis_names_the_mode_and_both_baselines():
    text = screen_idea.hypothesis(AVOID)
    assert text.startswith("fake_avoid: ")
    for part in ("AVOID mode (v214)", "K=20 matched null", "K=20 control arm",
                 ">= 0.10R", "cap 20", "condition bars excluded from both pools",
                 "(v214 avoid screen)"):
        assert part in text
    assert "SCREEN-PASS" not in text


def test_a_real_avoid_run_writes_the_avoid_section_and_one_row(tmp_path, monkeypatch):
    monkeypatch.setitem(screen_idea.IDEAS, "fake_avoid", AVOID)
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB"), start=1):
        _write_csv(cache / f"{ticker}.csv", random_walk(2700, seed=seed))
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\nAAA,2000-01-01,\nBBB,2000-01-01,\n",
                          encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    argv = ["--idea", "fake_avoid", "--cache-dir", str(cache), "--membership", str(membership),
            "--ledger", str(ledger), "--results-dir", str(tmp_path / "r"),
            "--date", "2026-11-06"]
    assert screen_idea.main(argv) == 0
    doc = (tmp_path / "r" / "2026-11-06-screen-fake_avoid.md").read_text(encoding="utf-8")
    for heading in ("## Avoid mode (read-outs, never gating)", "### Control arm per year",
                    "### Calibration: four closed screens (never re-run)", "### Ledger order"):
        assert heading in doc
    assert 'null_seed(idea + ":control", ticker)' in doc
    assert "This row is ledger row 1; v211 shots already in the ledger: none." in doc
    (row,) = stats.load_ledger(ledger)
    assert row["id"] == "screen-fake_avoid" and row["verdict"] in stats.VERDICTS
    assert row["hypothesis"] == screen_idea.hypothesis(AVOID)
```

`_screen` and `AVOID` come from the V214-6 and V214-7 blocks above.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py`
Expected: FAIL with `AttributeError: module 'screen_idea' has no attribute 'AVOID_COUNTS'` (then `with_avoid_blocks`, `_calibration`, `_avoid_run`). The V214-6/7 tests still pass.

- [ ] **Step 3: Implement in `scripts/backtest/screen_idea.py`**

- **Constants.** Put the four constants from Interfaces near `INSTRUMENT`, each with a `#:` comment:
  - `CALIBRATION_IDS`: *"v214 G1: the closed screens a sign flip alone would clear (calibration only, never re-run)"*.
  - `CALIBRATION_P`: *"the ledger keeps the edge p (share of resamples <= 0), not the interval; p >= 0.975 means the upper 95% bound sits at or below 0"*.
  - `V211_SHOT_IDS`: *"the v211 shots that share the ledger's BH family (spec § Constraints, ledger order)"*.
  - `AVOID_COUNTS`.
- **`with_avoid_blocks(summary, screens, idea)`**, as in Interfaces. Error tickers are the keys of `summary["skipped"]` that start with `"idea_error:"`, minus that prefix.
- **`_calibration(rows)`.** Build `{row["id"]: row for row in rows}`. For each id, `name = id.removeprefix("screen-")`, `direction = IDEAS[name].direction if name in IDEAS else "n/a"`. A missing row gives `exp_r`/`p` `None` and both clauses `False`. Otherwise:
  - `clause_1 = verdict.avoid_mean_clause(exp_r)`;
  - `clause_2 = p is not None and p >= CALIBRATION_P`.
- **`_avoid_run(run, idea, rows, row)`**, as in Interfaces. `row` is unused beyond the signature; it keeps the call parallel to `_context_run`.
- **`_render_avoid(summary, run) -> list`.** `a = summary["avoid"]`, `c = summary["verdict"].control`. It returns these lines in order:

```text
## Avoid mode (read-outs, never gating)

**Seeds:** the matched null draws with `null_seed(idea, ticker)` = [42, crc32(idea), crc32(ticker)]; the control arm with `null_seed(idea + ":control", ticker)`, from bars where the idea's control condition holds, at least {null.MIN_CANDIDATES} candidates per event. Every bar where the idea's condition holds is excluded from both pools.

| Read-out | Count | Share |
|---|---|---|
| member and warm bars | {a['population']} | |
| condition bars excluded from both pools | {a['excluded']} | {_share(_ratio(a['excluded'], a['population']))} of member and warm bars |
| kept events below the control floor | {a['below_floor']} | {_share(_ratio(a['below_floor'], a['kept']))} of kept events |
| kept events whose next open reached the gap bottom (overnight) | {a['overnight']} | {_share(_ratio(a['overnight'], a['kept']))} of kept events |
| tickers aborted by an idea error | {len(a['errors'])} | |

Idea errors per ticker: {", ".join(f"{t} 1" for t in a['errors']) or "none"}.

### Control arm per year

| Year | N_c | mean(d_c) |
|---|---|---|
| {year} | {n} | {_fmt(mean)}R |      <- one row per year of c.per_year

<_render_calibration(run["calibration"])>

### Ledger order

This row is ledger row {position}; v211 shots already in the ledger: {", ".join(ids) or "none"}. The BH q in the header is computed across the whole ledger in this order (spec § Constraints).
```

- **`_render_calibration(rows) -> list`.** It returns:

```text
### Calibration: four closed screens (never re-run)

Clause 1 is ΔExpR ≤ {-verdict.PASS_EXP_R:+.2f}R. Clause 2 (upper 95% bound < 0) is read from the ledger's edge p as p ≥ {CALIBRATION_P}, because the ledger stores no interval. A screen passing both shows what a sign flip alone would clear; the control arm is what it never faced.

| Ledger id | Direction | ΔExpR | edge p | Clause 1 | Clause 2 |
|---|---|---|---|---|---|
| `{id}` | {direction} | {_fmt(exp_r)}R | {_fmt(p, '.4f')} | {_yes(clause_1)} | {_yes(clause_2)} |      <- one row per entry
```

- **`_avoid_hypothesis(idea) -> str`.** `f"{idea.name}: {idea.summary}; AVOID mode (v214): fixed {race.STOP_ATR}/{race.STOP_ATR * race.REWARD_RISK} ATR race, {idea.direction}, entry next open, cap {idea.time_cap_bars}, must trail both a K={null.K} matched null and a K={null.K} control arm by >= {verdict.PASS_EXP_R:.2f}R, condition bars excluded from both pools, PIT S&P 500 2010-2019, after costs (v214 avoid screen)"`.
- **`hypothesis(idea)`.** The first line is `if idea.mode == "avoid": return _avoid_hypothesis(idea)`. Every edge branch is unchanged; the hypothesis golden proves it.
- **`render_results`.** After the existing optional sections, `if idea.mode == "avoid": sections.append(_render_avoid(summary, run))`.
- **`publish`.** `run = _avoid_run(_context_run(...), idea, rows, row)`; nothing else moves.
- **`_run_screens`.** After `with_short_blocks(...)` (and V211-11's `with_shock_blocks`, if present), add `summary = with_avoid_blocks(summary, screens, idea)`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_avoid_mode.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS, no complexity regression. Then run the v211 pins from this part's header; the hypothesis golden and `FIXED_DOC` must be untouched and green.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_avoid_mode.py
git commit -m "feat(screen): avoid read-outs, calibration printout, avoid hypothesis and ledger order (v214 V214-8)"
```

# Phase 4 — Call sites, hook, docs (waves A and B)

### Task V214-9: `decide` call sites in diagnostics and trail calibration take `mode` (G5)

**Model:** sonnet — threads one keyword through two modules with spy tests; the shapes are fixed by V214-2.

**Files:**
- Modify: `swingbot/core/backtesting/screen/diagnostics.py` (`_decide`, `_overlap`, `_selloff`, `compute`)
- Modify: `scripts/backtest/screen_trail_calibration.py` (`replicate`, new `_false_passes`, `calibrate`)
- Modify: `tests/backtesting/screen/test_diagnostics.py` (append)
- Modify: `tests/backtest_scripts/test_screen_trail_calibration.py` (append)

**Interfaces:**
- Consumes: V214-2's `decide(events, *, mode=, control=)`, `Verdict.mode` and `verdict.SCREEN_AVOID_PASS`; V214-4's `Idea.mode`/`Idea.states`.
- Produces:
  - `diagnostics._decide(rows, mode: str = "edge")`;
  - `diagnostics._overlap(events, restricted, cap: int, mode: str = "edge")`;
  - `diagnostics._selloff(events, signals, days, spy_r5, mode: str = "edge")`;
  - `compute(...)` passes `idea.mode` to both;
  - `screen_trail_calibration._false_passes(verdicts) -> int`, which counts `verdict.SCREEN_PASS` only;
  - `replicate` hands the replicate idea's `mode` to `decide`.

  Nothing else reads these.

- [ ] **Step 0: Gate and prerequisites.** Run the two `git grep` commands from this part's header. Then `git grep -n "SCREEN_AVOID_PASS" -- swingbot/core/backtesting/screen/verdict.py` and `git grep -n "_mode_problem" -- swingbot/core/backtesting/screen/ideas/__init__.py` must both print a line (V214-2, V214-4). This task does not touch `screen_idea.py`, so it may run beside V214-6..8.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/screen/test_diagnostics.py`:

```python
# --- v214 G5: the idea's mode reaches every decide ---------------------------

import dataclasses  # noqa: E402


def _mode_spy(monkeypatch):
    modes = []
    real = verdict.decide

    def spy(events, **kw):
        modes.append(kw.get("mode", "edge"))
        return real(events, n_resamples=200, **kw)

    monkeypatch.setattr(verdict, "decide", spy)
    return modes


def _restricted():
    return [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3}]


def test_an_avoid_idea_gets_avoid_verdicts_in_every_diagnostic(monkeypatch):
    modes = _mode_spy(monkeypatch)
    idea = dataclasses.replace(_idea(), mode="avoid", states=lambda df: df)
    out = diagnostics.compute(idea, _events(), _restricted(), _data(), **_window())
    assert modes == ["avoid", "avoid", "avoid"]           # restricted, selloff down, selloff up
    verdicts = [out["overlap"]["restricted"], out["selloff"]["down"], out["selloff"]["up"]]
    assert {v.mode for v in verdicts} == {"avoid"}
    assert all(v.verdict != verdict.SCREEN_PASS for v in verdicts)


def test_an_edge_idea_keeps_edge_verdicts(monkeypatch):
    modes = _mode_spy(monkeypatch)
    out = diagnostics.compute(_idea(), _events(), _restricted(), _data(), **_window())
    assert modes == ["edge", "edge", "edge"]
    assert out["overlap"]["restricted"].mode == "edge"


def test_the_private_decide_defaults_to_edge():
    assert diagnostics._decide([]) is None
    assert diagnostics._decide(_events()).mode == "edge"
    assert diagnostics._decide(_events(), "avoid").mode == "avoid"
```

Append to `tests/backtest_scripts/test_screen_trail_calibration.py`:

```python
# --- v214 G5: only an edge pass is a false pass ------------------------------

import dataclasses  # noqa: E402

AVOID_PASS = _v(verdict.SCREEN_AVOID_PASS, 400, -0.2, -0.3, -0.1)


def test_false_passes_count_only_edge_passes():
    assert cal._false_passes(FAKE + [AVOID_PASS]) == 1
    assert cal._false_passes([]) == 0


def test_calibrate_never_counts_an_avoid_pass(monkeypatch):
    _fake_replicates(monkeypatch, [AVOID_PASS, AVOID_PASS])
    out = cal.calibrate(2, seed=0, **QUIET)
    assert (out["false_pass"], out["false_pass_rate"]) == (0, 0.0)


def _as_avoid(make):
    def avoid_idea(df, rng, rate, direction, entry):
        idea = make(df, rng, rate, direction, entry)

        def states(frame):
            event = idea.events(frame).reindex(frame.index, fill_value=False)
            return pd.DataFrame({"event": event.to_numpy(dtype=bool),
                                 "control_condition": False, "condition": False,
                                 "bottom": np.nan}, index=frame.index)

        return dataclasses.replace(idea, mode="avoid", states=states)

    return avoid_idea


def test_a_replicate_hands_the_ideas_mode_to_decide(monkeypatch):
    modes = []
    real = verdict.decide

    def spy(events, **kw):
        modes.append(kw.get("mode"))
        return real(events, **kw)

    monkeypatch.setattr(cal.verdict, "decide", spy)
    edge = cal.replicate(5, tickers=1, n_resamples=100, direction="short")
    monkeypatch.setattr(cal, "_replicate_idea", _as_avoid(cal._replicate_idea))
    avoid = cal.replicate(5, tickers=1, n_resamples=100, direction="short")
    assert modes == ["edge", "avoid"]
    assert (edge.mode, avoid.mode) == ("edge", "avoid")
    assert avoid.verdict != verdict.SCREEN_PASS
```

The short replicate idea is the fixed, cap-20, next-open one (`test_the_short_idea_is_fixed_cap_20_short`), so V214-4 accepts it in avoid mode. The long replicate idea is a trail idea and would be refused.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
```

Expected: FAIL.
- In diagnostics, the avoid test records `["edge", "edge", "edge"]`, and `_decide()` takes 1 positional argument but 2 were given.
- In calibration, `AttributeError: module 'screen_trail_calibration' has no attribute '_false_passes'`, and the replicate spy records `[None, None]`.

- [ ] **Step 3: Implement**

`swingbot/core/backtesting/screen/diagnostics.py`:
- `_decide(rows, mode="edge")`: `verdict.decide(_paired(rows), mode=mode) if rows else None`. `decide` is still looked up on the module at call time, as the module docstring promises.
- `_overlap(events, restricted, cap, mode="edge")`: `"restricted": None if restricted is None else verdict.decide(_paired(restricted), mode=mode)`.
- `_selloff(events, signals, days, spy_r5, mode="edge")`: `_decide(groups["down"], mode)` and `_decide(groups["up"], mode)`.
- `compute`: pass `idea.mode` to `_overlap(...)` and `_selloff(...)`. An avoid idea has no control arm here, so these verdicts are `SCREEN-UNDERPOWERED` or `SCREEN-FAIL` and never an edge label. Add one docstring line: `v214: every verdict carries idea.mode.`

`scripts/backtest/screen_trail_calibration.py`:
- `replicate`: set `mode = "edge"` before the ticker loop and `mode = idea.mode` inside it (every replicate idea of one call shares one mode). The final call is `verdict.decide(paired, mode=mode, n_resamples=n_resamples)`.
- `_false_passes(verdicts) -> int`: `sum(v.verdict == verdict.SCREEN_PASS for v in verdicts)`. Docstring: *"v214 G5: only an edge pass is a false pass; SCREEN-AVOID-PASS answers a different question."*
- `calibrate`: `false_pass = _false_passes(verdicts)`. The `_render_result` tally of the three edge labels is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_trail_calibration.py
python scripts/dev/complexity_gate.py
```

Expected: both files `0 failed`, including the existing `test_every_decide_goes_through_the_module_attribute` (its spy takes `**kw`). No complexity regression.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/diagnostics.py scripts/backtest/screen_trail_calibration.py tests/backtesting/screen/test_diagnostics.py tests/backtest_scripts/test_screen_trail_calibration.py
git commit -m "feat(screen): diagnostics and trail calibration verdicts take the idea's mode; only edge passes are false passes (v214 V214-9)"
```

### Task V214-10: Spec-header hook accepts `SCREEN-AVOID-PASS (veto)` for `Edge: expectancy` only (G6)

**Model:** sonnet — regex classification in one self-contained file, with accept/reject tests listed in the spec.

**Files:**
- Modify: `tests/hooks/test_spec_screen_header.py`, which holds the hook logic and its tests in one file. Change the module docstring table, the constants, `_ledger_problem` and `_classify`; add a new `_cited`; append tests. The file is in suite `hooks` (`tests/hooks/`).

**Interfaces:**
- Consumes: nothing from other tasks at runtime. The repository gate reads the real ledger through `stats.load_ledger()`. Once V214-3 has landed, a committed row with verdict `SCREEN-AVOID-PASS` validates; this test needs only the label string.
- Produces:
  - hook kind `"avoid_veto"`, with `_EDGES_FOR["avoid_veto"] = {"expectancy"}`;
  - `SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"`;
  - regexes `_AVOID_VETO`, `_AVOID_BARE` and `_PASS_VETO`;
  - `_ledger_problem(row_id, ledger, wanted=SCREEN_PASS)`.

  V214-11's docs describe exactly these rules.

- [ ] **Step 0: Gate.** Run the two `git grep` commands from this part's header. This file is untouched by v211, so no other prerequisite applies.

- [ ] **Step 1: Write the failing tests**

Add `import pytest` to the file's imports (beside `import re`). Then append below `test_grandfathered_and_split_specs_are_skipped`, before the `# -- the repository gate` banner:

```python
# -- v214 G6: an avoid pass licenses a veto only ------------------------------

AVOID_LEDGER = LEDGER + [{"id": "screen-avoid", "verdict": "SCREEN-AVOID-PASS"}]


def test_an_avoid_pass_cited_as_a_veto_fits_an_expectancy_spec():
    for screen in ("screen-avoid SCREEN-AVOID-PASS (veto)",
                   "`screen-avoid` SCREEN-AVOID-PASS (veto)"):
        assert screen_problems(_spec("expectancy", screen), ledger=AVOID_LEDGER) == []


@pytest.mark.parametrize("edge", ["volume", "harvest", "none (integrity)"])
def test_an_avoid_veto_fits_only_an_expectancy_edge(edge):
    problems = screen_problems(_spec(edge, "screen-avoid SCREEN-AVOID-PASS (veto)"),
                               ledger=AVOID_LEDGER)
    assert problems and "does not fit" in problems[0]


def test_an_avoid_pass_without_the_veto_suffix_fails():
    problems = screen_problems(_spec("expectancy", "screen-avoid SCREEN-AVOID-PASS"),
                               ledger=AVOID_LEDGER)
    assert problems and "SCREEN-AVOID-PASS (veto)" in problems[0]


def test_a_veto_suffix_beside_a_screen_pass_fails():
    problems = screen_problems(_spec("expectancy", "screen-good SCREEN-PASS (veto)"),
                               ledger=AVOID_LEDGER)
    assert problems and "only beside SCREEN-AVOID-PASS" in problems[0]


def test_an_avoid_veto_must_cite_an_avoid_pass_row():
    wrong = screen_problems(_spec("expectancy", "screen-good SCREEN-AVOID-PASS (veto)"),
                            ledger=AVOID_LEDGER)
    assert wrong == ["ledger id screen-good is SCREEN-PASS, not SCREEN-AVOID-PASS"]
    absent = screen_problems(_spec("expectancy", "screen-nope SCREEN-AVOID-PASS (veto)"),
                             ledger=AVOID_LEDGER)
    assert absent and "not in the ledger" in absent[0]


def test_a_screen_pass_cite_of_an_avoid_row_fails():
    problems = screen_problems(_spec("expectancy", "screen-avoid SCREEN-PASS"),
                               ledger=AVOID_LEDGER)
    assert problems == ["ledger id screen-avoid is SCREEN-AVOID-PASS, not SCREEN-PASS"]


def test_every_other_case_still_needs_a_screen_pass():
    assert screen_problems(_spec(screen="screen-good SCREEN-PASS"), ledger=AVOID_LEDGER) == []
    problems = screen_problems(_spec(screen="screen-bad SCREEN-PASS"), ledger=AVOID_LEDGER)
    assert problems == ["ledger id screen-bad is SCREEN-FAIL, not SCREEN-PASS"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/hooks/test_spec_screen_header.py`
Expected: FAIL. The avoid veto is "unrecognised"; `screen-good SCREEN-PASS (veto)` is accepted by today's `_LEDGER`; the bare avoid message lacks `SCREEN-AVOID-PASS (veto)`. `test_a_screen_pass_cite_of_an_avoid_row_fails` and `test_every_other_case_still_needs_a_screen_pass` already pass.

- [ ] **Step 3: Implement in `tests/hooks/test_spec_screen_header.py`**

- **Docstring table.** Add one row after the ledger row:
  `| expectancy, a veto filter licensed by an avoid screen  | `<ledger-id> SCREEN-AVOID-PASS (veto)` (v214) |`
- **Constants:**

```python
SCREEN_AVOID_PASS = "SCREEN-AVOID-PASS"
_AVOID_VETO = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-AVOID-PASS\s+\(veto\)")
_AVOID_BARE = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-AVOID-PASS\b")
_PASS_VETO = re.compile(r"^`?([^`\s]+)`?\s+SCREEN-PASS\s+\(veto\)")
```

  `_EDGES_FOR` gains `"avoid_veto": {"expectancy"}`.
- **`_FORMS`**, an ordered table of `(pattern, kind, verdict or reason)`. The order matters: the veto forms come before `_LEDGER`, which would otherwise accept `SCREEN-PASS (veto)`.

```python
#: v214 G6: the cited Screen forms, first match wins. A kind of None refuses
#: the value with the reason in the third slot.
_FORMS = (
    (_AVOID_VETO, "avoid_veto", SCREEN_AVOID_PASS),
    (_AVOID_BARE, None, "SCREEN-AVOID-PASS licenses a veto only: write "
                        "`<ledger-id> SCREEN-AVOID-PASS (veto)` under Edge: expectancy"),
    (_PASS_VETO, None, "`(veto)` goes only beside SCREEN-AVOID-PASS; cite a "
                       "SCREEN-PASS as `<ledger-id> SCREEN-PASS`"),
    (_LEDGER, "ledger", SCREEN_PASS),
)
```

- **`_ledger_problem(row_id, ledger, wanted=SCREEN_PASS)`.** The verdict check compares against `wanted`, with the message `f"ledger id {row_id} is {verdicts[row_id]}, not {wanted}"`.
- **`_cited(screen, ledger)`.** It walks `_FORMS`. On the first match it returns `(kind, _ledger_problem(match.group(1), ledger, wanted))` for a kind, or `(None, reason)` for a refusal. With no match it returns `(None, f"unrecognised Screen value `{screen}`")`.
- **`_classify`.** It keeps the post-signal, exempt and headroom branches, then `return _cited(screen, ledger)`. `screen_problems` is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/hooks/test_spec_screen_header.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`, including the repository gate `test_every_spec_above_v140_carries_a_valid_screen_line` over every committed spec. No complexity regression.

- [ ] **Step 5: Commit**

```bash
git add tests/hooks/test_spec_screen_header.py
git commit -m "feat(hooks): Screen header accepts <id> SCREEN-AVOID-PASS (veto) for Edge: expectancy only (v214 V214-10)"
```

### Task V214-11: Docs: Stage −2 avoid mode, `Screen:` avoid row, `AGENTS.md` mirror (G7)

**Model:** sonnet — fixed prose into three docs under a 32 KB byte cap on `AGENTS.md`; the text is given below.

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (§ Funnel stages, the Stage −2 bullet)
- Modify: `docs/claude/document-conventions.md` (the `Screen:` table and the hook sentence below it)
- Modify: `AGENTS.md` (the `Specs from v141 carry **Screen:**` paragraph)

**Interfaces:**
- Consumes: V214-10's hook rules (`<id> SCREEN-AVOID-PASS (veto)`, `Edge: expectancy` only, bare avoid label and `SCREEN-PASS (veto)` rejected) and V214-2's six clauses. These docs describe them; nothing imports them.
- Produces: nothing a later task reads.

- [ ] **Step 0: Gate and byte budget.** Run the two `git grep` commands from this part's header. Then measure the Codex byte budget:

```bash
python -c "import pathlib; b = pathlib.Path('AGENTS.md').read_bytes().replace(b'\r\n', b'\n'); print(len(b), 32 * 1024 - len(b))"
```

`tests/scout/test_generator_roles.py` requires `AGENTS.md` to stay under `32 * 1024` bytes. At plan time the file had 17 bytes of headroom. The replacement below is 2 bytes shorter than the paragraph it replaces. If v211 has since grown `AGENTS.md`, the replacement must still net ≤ 0 bytes: shorten inside this paragraph, never elsewhere.

- [ ] **Step 1: Write the failing checks**

The docs have no unit test of their own, so these checks are the red state. Each must print `0` now:

```bash
git grep -c "SCREEN-AVOID-PASS" -- docs/claude/backtest-methodology.md
git grep -c "SCREEN-AVOID-PASS (veto)" -- docs/claude/document-conventions.md
git grep -c "SCREEN-AVOID-PASS (veto)" -- AGENTS.md
```

(`git grep -c` prints nothing and exits 1 for no match; that counts as `0`.)

- [ ] **Step 2: Edit `docs/claude/backtest-methodology.md`**

In § Funnel stages, the Stage −2 bullet ends with *"...must clear Stage −1 reachability on the bot's own replay before any shot; the funnel's clauses are otherwise unchanged."* Append this paragraph to the same bullet, indented two spaces, before `- **The acceptance funnel.**`:

```markdown
  **Avoid mode (v214, partner 2026-11-06).** An idea module may declare
  `MODE = "avoid"` (default `"edge"`, part of the frozen definition like
  `RACE`, pinned in `test_ideas_registry.py`). It asks whether the event's
  bars do **worse** than chance: the evidence a veto filter needs. A sign
  flip is not enough. Four closed screens (`high52w`, `gap_volume`,
  `sweep_reclaim_bos`, short `range_breakdown_close`) sit at ΔExpR ≤ −0.10
  with p near 1, partly because 2010–2019 lifts the long null and sinks
  shorts. So an avoid idea also faces a **control arm**: up to K = 20 bars
  per event from the same ticker, month and trend state where the idea's
  `control_condition` holds (the state exists, but differs in the one
  tested way), floor `null.MIN_CANDIDATES` = 5, seed
  `null_seed(idea + ":control", ticker)`. Every bar where the idea's
  condition holds leaves both the null and the control pool.
  `SCREEN-AVOID-PASS` needs all six: mean d ≤ −0.10R (the tolerance
  mirrored, so exactly −0.10 passes); upper 95% bound < 0; mean d < 0 in
  ≥ 7 of 2011–2019 (an empty year counts against); N ≥ 300; against the
  control arm, mean d_c ≤ −0.10R, and upper bound < 0 with N_c ≥ 300.
  N or N_c < 300 is `SCREEN-UNDERPOWERED`; any other failing clause is
  `SCREEN-FAIL`. The avoid p (the share of resamples ≥ 0) joins the
  ledger's one BH family. One shot per idea, as above; a fail is closed,
  and no closed idea is re-run under the other mode. **An avoid pass buys
  a veto spec, not a veto**: that spec says
  `<ledger-id> SCREEN-AVOID-PASS (veto)` under `Edge: expectancy` and runs
  the unchanged funnel on the bot's own replay.
```

- [ ] **Step 3: Edit `docs/claude/document-conventions.md`**

In the `Screen:` table, insert this row directly after the `<ledger-id> SCREEN-PASS` row:

```markdown
| `expectancy`, a **veto filter** licensed by an avoid screen (v214) | `<ledger-id> SCREEN-AVOID-PASS (veto)` — the row must carry `SCREEN-AVOID-PASS`; the literal `(veto)` marks a spec that adds a veto. The avoid label without `(veto)`, or `(veto)` beside a `SCREEN-PASS`, is rejected (`backtest-methodology.md` § Stage −2, avoid mode) |
```

In the sentence below the table, replace `cites an absent or non-\`SCREEN-PASS\` ledger id,` with:

```markdown
cites an absent ledger id or one whose verdict is not the cited label,
cites `SCREEN-AVOID-PASS` without `(veto)` or under an `Edge:` other than
`expectancy`, puts `(veto)` beside a `SCREEN-PASS`,
```

The rest of the sentence is unchanged.

- [ ] **Step 4: Edit `AGENTS.md`**

Replace the paragraph's opening, from `Specs from v141 carry` up to (not including) `and from v146`, with exactly:

```markdown
Specs from v141 carry `**Screen:**` under `Edge:` (an entry strategy or filter
cites a `SCREEN-PASS` row of `scripts/backtest/screen_idea.py`; an `Edge: expectancy`
veto may cite `<id> SCREEN-AVOID-PASS (veto)` (v214: >= 0.10R worse than the null
and a control arm); a fill-timing veto says `exempt (post-signal)` and clears
Stage -1 reachability (v192); a fail is closed, never re-screened; each idea
freezes one race (`fixed`/`trail` cap >= 60) and one `MODE`) and from v146
```

The text from `and from v146` onward stays as it is.

- [ ] **Step 5: Verify**

```bash
git grep -c "SCREEN-AVOID-PASS" -- docs/claude/backtest-methodology.md
git grep -c "SCREEN-AVOID-PASS (veto)" -- docs/claude/document-conventions.md
git grep -c "SCREEN-AVOID-PASS (veto)" -- AGENTS.md
python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py
python scripts/dev/testrun.py file tests/scout/test_generator_roles.py
python scripts/dev/doc_section.py docs/claude/backtest-methodology.md "Funnel stages"
```

Expected:
- each of the three counts is at least 1;
- both test files report `0 failed`, so the mirror is current and `AGENTS.md` is under 32 KB;
- the section print shows the avoid paragraph inside the Stage −2 bullet, before the acceptance-funnel bullet.

- [ ] **Step 6: Commit** (the docs and their Codex mirror together)

```bash
git add docs/claude/backtest-methodology.md docs/claude/document-conventions.md AGENTS.md
git commit -m "docs(v214): Stage -2 avoid mode, the Screen: avoid-veto row, AGENTS.md mirror (V214-11)"
```

# Phase 5 — The one shot (wave F)

### Task V214-12: The one shot via `backtest-runner`; results doc, ledger row; `/panel`; `/close-out` (G8)

**Model:** sonnet — an operational run of finished code with fixed commands; the judgment calls (panel findings, the veto brainstorm on a pass) go to the partner.

**Files:**
- Create (by the runner): `docs/superpowers/results/<run-date>-screen-fvg_overhead_aged.md`
- Modify (by the runner): `docs/superpowers/results/preregistration-ledger.jsonl`. The runner appends one row; it is never hand-edited.
- Modify: `docs/claude/backtest-methodology.md` (§ Closed pre-registrations), on `SCREEN-FAIL` / `SCREEN-UNDERPOWERED` only
- Modify: `docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md` (a `## Result` section)

**Interfaces:**
- Consumes: everything from V214-1..11, merged on `main` with CI green. V211-6's `--checkpoint-dir`.
- Produces: ledger row `screen-fvg_overhead_aged`. A later veto spec cites it only if it reads `SCREEN-AVOID-PASS`.

This task runs **on `main`**, after the implementation branch is merged and CI is green. It spends the idea's one shot. A failure after the ledger row is written is never fixed by re-running: the refusal in `screen_idea.refusal` blocks it, and the anti-goals forbid it.

- [ ] **Step 0: Preconditions.** Run the two `git grep` commands from this part's header. Then:

```bash
git branch --show-current
git grep -n "def with_avoid_blocks" main -- scripts/backtest/screen_idea.py
git grep -n "fvg_overhead_aged" main -- swingbot/core/backtesting/screen/ideas/__init__.py
gh run list --branch main --limit 3
python -c "from swingbot.core.backtesting.instrument import stats; rows = stats.load_ledger(); ids = [r['id'] for r in rows]; print(len(rows), 'screen-fvg_overhead_aged' in ids, [i for i in ids if i.startswith('screen-shock_')])"
```

Expected:
- the branch is `main`;
- both greps print a line;
- the newest CI run on `main` is `completed success`;
- the Python line prints `<rows> False [...]`. `False` means the shot is unspent. The list shows which v211 shots are already in, and the results doc records that order.

If the shot is already in the ledger, stop: the shot is spent.

- [ ] **Step 1: Gate the run.** Invoke the `backtest-gate` skill (Skill tool), naming this command and the frozen rule it serves: the spec's G1 six clauses, window 2010-01-01..2019-12-31, one shot. Follow its checks before any command below.

- [ ] **Step 2: Smoke run on three tickers (writes nothing)**

```bash
python scripts/backtest/screen_idea.py --idea fvg_overhead_aged --tickers AAPL,MSFT,JPM --dry-run
```

Expected:
- exit code 0, no traceback;
- the printed doc contains `## Verdict: SCREEN-` (N is tiny, so `SCREEN-UNDERPOWERED` is the likely label), `years with mean(d) < 0`, `## Avoid mode (read-outs, never gating)`, `### Calibration: four closed screens (never re-run)` and `Idea errors per ticker: none`.

Note the wall time. It sets the expectation for the full run: the detector runs once per bar per ticker, so expect tens of minutes to hours over the PIT universe. If any ticker prints `idea error`, stop and report it; do not spend the shot on a broken detector.

- [ ] **Step 3: The shot, through `backtest-runner`**

Dispatch the `backtest-runner` agent (background) with exactly this command, from the repo root on `main`:

```bash
python scripts/backtest/screen_idea.py --idea fvg_overhead_aged --checkpoint-dir data/screen_checkpoints/fvg_overhead_aged
```

Tell the agent four things:
- `data/screen_checkpoints/` is git-ignored. A restart is the **same command**: V211-6's manifest check resumes from the pickled tickers, and the flushed `[fvg_overhead_aged] i/n tickers (p%)` line shows progress.
- Report back only three things: the final publish line (`screen-fvg_overhead_aged: <VERDICT>, N=..., dExpR=...R, lower95=...R, <k>/9 years negative -> <record>`), the number of `idea error` lines with their tickers, and the wall time.
- Never re-run the command once the publish line has printed.
- Never pass `--tickers`, `--start`, `--end` or `--dry-run`.

- [ ] **Step 4: Verify the results doc carries what G8 and G4 require**

With `D` set to the doc path from the publish line:

```bash
for s in "window 2010-01-01..2019-12-31" "## Universe and counters" "null_seed(idea, ticker)" ":control" "## Per year" "Idea errors per ticker" "below the control floor" "excluded from both pools" "overnight" "### Control arm per year" "### Calibration" "### Ledger order"; do printf '%s: ' "$s"; grep -cF -- "$s" "$D"; done
```

Expected: every count ≥ 1. These items cover the window, the universe, the seed derivation, events per year, errors per ticker, the control-floor, exclusion and overnight shares, per-year d_c, the calibration printout and the ledger order relative to v211's shots. If any count is 0, report it as a defect in the runner. Do **not** re-run the shot; the fix goes into a follow-up spec.

- [ ] **Step 5: Commit the measurement on `main`**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl "$D"
git commit -m "results(v214): screen-fvg_overhead_aged -> <VERDICT> (N=<n>, dExpR <d>R; control N_c=<nc>, dExpR_c <dc>R)"
```

- [ ] **Step 6: Record the verdict**

Append to the spec, `docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md`:

```markdown
## Result

<run-date>: `screen-fvg_overhead_aged` -> **<VERDICT>**. N = <n>, ΔExpR <d>R (upper 95% <hi>R), <k> of 9 years negative; control arm N_c = <nc>, ΔExpR_c <dc>R (upper 95% <hic>R); avoid p <p>, BH q <q> across the ledger (row <position>; v211 shots before it: <ids or none>). Results: `docs/superpowers/results/<run-date>-screen-fvg_overhead_aged.md`.
```

Then act on the verdict:
- **`SCREEN-FAIL` or `SCREEN-UNDERPOWERED`.** Add one row to `docs/claude/backtest-methodology.md` § Closed pre-registrations, in the screen rows' format:

```markdown
| Idea screen `fvg_overhead_aged` (avoid mode) — an unfilled bearish FVG from the live detector run per bar, aged >= 5 bars, bottom within Close + 3 x ATR14, one event per gap; long fixed 1.5/3 ATR race vs a K=20 matched null and a K=20 control arm (aged gap beyond reach), cap 20, PIT S&P 500 2010-2019, after costs (v214 Stage −2 avoid) | **<VERDICT>.** N=<n>, ΔExpR <d>R (upper 95% <hi>R), <k> of 9 years negative; control arm N_c=<nc>, ΔExpR_c <dc>R. Closed: no veto spec, never re-screened; another age, the gap mid or top, a k x ATR reach, the displacement mode or a dropped control clause is a new idea, never a retry. | `results/<run-date>-screen-fvg_overhead_aged.md`, ledger `screen-fvg_overhead_aged` |
```

  `AGENTS.md` does not mirror this table, so no mirror edit is needed.
- **`SCREEN-AVOID-PASS`.** No closed row. Following the spec's *What follows*, ask the partner (`AskUserQuestion`) whether to brainstorm the confluence veto spec now. That spec will carry `**Screen:** screen-fvg_overhead_aged SCREEN-AVOID-PASS (veto)` under `Edge: expectancy`.

```bash
git add docs/superpowers/specs/2026-11-06-v214-screen-avoid-mode-fvg-path.md docs/claude/backtest-methodology.md
git commit -m "docs(v214): record the screen-fvg_overhead_aged verdict in the spec and the closed table"
```

(On a pass, only the spec is staged.)

- [ ] **Step 7: Panel, push, close-out**

- Run `/panel quant-researcher,quant-engineer,technical-analyst` on the results doc (the spec's `Panel:` line) through the Skill tool.
  - Any `BLOCKING` finding is resolved before close-out by a doc correction or a follow-up spec, **never** by re-running the shot.
  - Record the panel outcome in the spec under `## Result` and commit it.
- `git push`, then watch the CI run until green (`working-conventions.md` § Pipeline watch). Fix any failing test alone, never by re-running the suite locally.
- Run `/close-out` through the Skill tool. `Bump: none`. The plan's code is on `main`, so `/close-out` files the plan and spec under `implemented/` whatever the verdict (`document-lifecycle.md`), and removes the `2026-11-06-v214-screen-avoid-mode-fvg-path` worktree.

