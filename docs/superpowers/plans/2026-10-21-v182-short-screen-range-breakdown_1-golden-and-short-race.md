# v182 Part 1 — Golden long capture and the short fixed race

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. Global constraints, Review Focus, parallelisation and the task ledger live in the index: [`_0-index.md`](2026-10-21-v182-short-screen-range-breakdown_0-index.md). Every task's requirements include the index's `## Global Constraints`.

**Bump:** none
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-10-21-v182-short-screen-range-breakdown-design.md](../specs/2026-10-21-v182-short-screen-range-breakdown-design.md)

Tasks V182-1..V182-4. All work happens in the worktree
`.claude/worktrees/2026-10-21-v182-short-screen-range-breakdown` (created in
V182-1 Step 1); every path below is relative to that worktree's root and every
command runs from it. V182-1 is the worktree's first commit and is taken on
engine code identical to `main` — no file under `swingbot/` or `scripts/` may
change before its golden files are committed.

**Long byte-identity, every task:** after each task's own tests, run both
golden regressions and expect them green:

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

A red golden is never "fixed" by regenerating it: `long_golden.py --write`
runs in V182-1 only. A red golden means the task changed a long result;
find the operand-order or call-path change and revert it.

# Phase 1 — Golden capture and the short fixed race

### Task V182-1: Golden long outputs and the byte-identity regression tests

**Model:** sonnet — test-only scaffolding over existing entry points, but the platform-exact fixture design must be followed exactly.

**Files:**
- Create: `tests/backtesting/screen/long_golden.py`
- Create: `tests/backtesting/screen/golden/long_v182.json`
- Create: `tests/backtesting/screen/test_long_byte_identical.py`
- Create: `tests/backtest_scripts/golden/trail_calibration_v182.txt`
- Create: `tests/backtest_scripts/test_calibration_long_golden.py`

**Interfaces:**
- Consumes (all existing on `main` @ 9536ce09): `screen_idea.screen_ticker(idea, ticker, df, spans, *, slippage_bps=None, commission=None, context=None) -> TickerScreen` (`scripts/backtest/screen_idea.py:203`), `screen_idea.summarise(screens, skipped=None) -> dict` (:475), `screen_idea.hypothesis(idea) -> str` (:698), `screen_idea.render_results(idea, summary, universe, run) -> str` (:667), `screen_idea.Universe` (:80, built positionally `(intervals, members, cached, missing)`), `screen_idea.ledger_id` (:376), `screen_idea.base_slippage` (:61), `race.race` (`race.py:98`), `race.race_for` (:155), `trail.race_trail` (`trail.py:64`), `race.warm_mask` (:64), `indicators.atr`, `indicators.sma`, `IDEAS`, `verdict.decide` (`verdict.py:117`), `commission_r` (`frictions.py:22`), the `scripts/backtest/screen_trail_calibration.py` CLI.
- Produces: `long_golden.LONG_IDEAS: tuple[str, ...]` (the nine names registered today, frozen — never `list(IDEAS)`, which grows in V182-14/15); `long_golden.TRAIL_VARIANT = "high52w_trail"`; `long_golden.GOLDEN_PATH: Path`; `long_golden.fixture_frame(seed: int, n: int = BARS, start: str = START) -> pd.DataFrame`; `long_golden.capture() -> dict` (keys `"<idea>/<seed>/<field>"`, `"<idea>/summary/<key>"`, `"<idea>/hypothesis"`, `"<idea>/results_doc"`, `"race_all/<seed>/<shape>"`; values JSON-safe, every float as its `repr` string); `long_golden.digests(payload: dict) -> dict[str, str]` (sha256 per key); `long_golden.counts(payload: dict) -> dict[str, int]` (kept events per idea, summed over the frames); `python tests/backtesting/screen/long_golden.py --write` regenerates the golden (run in this task only). `test_calibration_long_golden.run_default() -> str` (the calibration CLI's stdout, LF newlines).

**Why the fixture avoids `np.exp`:** `tests/backtest_scripts/test_screen_context_runner.py:28-31` rounds its parity digests to 8 digits because `random_walk` uses `np.exp`, and Windows and Linux libm differ in the last bits. This golden compares floats **exactly**, so its input frames use only `rng.integers` (PCG64, platform-identical), `+ - * /` and `np.cumprod` (sequential, correctly rounded IEEE operations). Everything downstream (Wilder ATR via `ewm`, SMA, the races, the null, `np.mean`, `np.percentile`, Spearman on half-integer ranks) is then the same bits on every platform.

- [ ] **Step 1: Create the worktree**

```bash
git worktree add .claude/worktrees/2026-10-21-v182-short-screen-range-breakdown -b 2026-10-21-v182-short-screen-range-breakdown main
cd .claude/worktrees/2026-10-21-v182-short-screen-range-breakdown
git diff --quiet main -- swingbot scripts && echo "engine identical to main"
```

Expected: `engine identical to main`. Every later command in this plan runs from the worktree root.

- [ ] **Step 2: Write `tests/backtesting/screen/long_golden.py`**

The module is a test helper (no `test_` prefix, so pytest does not collect it) and a script. Its header and constants:

```python
"""v182 golden long outputs (partner rule 2026-10-21: the long side stays
byte-identical). Captured once, on engine code identical to main @ 9536ce09,
before any v182 engine edit; compared exactly by test_long_byte_identical.py.

    python tests/backtesting/screen/long_golden.py --write   # V182-1 only

Frames use integer draws and + - * / only, so every float is the same bits
on Windows and Linux (no np.exp: see test_screen_context_runner.py:28-31).
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections import Counter
from functools import partial
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
for _path in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import screen_idea  # noqa: E402
from swingbot.core.backtesting.screen import indicators, race, verdict  # noqa: E402
from swingbot.core.backtesting.screen.ideas import IDEAS  # noqa: E402
from swingbot.core.edge.frictions import commission_r  # noqa: E402

GOLDEN_PATH = Path(__file__).with_name("golden") / "long_v182.json"
#: The nine ideas registered on main @ 9536ce09, frozen. Never list(IDEAS):
#: V182-14/15 register two short ideas that must not enter this capture.
LONG_IDEAS = ("high52w", "uptrend_pullback", "gap_volume", "turn_of_month",
              "turtle_soup", "quiet_pullback", "bond_spike_rebound", "dollar_drop",
              "sweep_reclaim_bos")
TRAIL_VARIANT = "high52w_trail"        # covers trail race, trail null, stressed book
SEEDS = (7, 11, 13)
BARS = 2600
START = "2010-01-04"
CONTEXT_SEEDS = {"TLT": 101, "UUP": 102}
CONTEXT_BARS, CONTEXT_START = 2800, "2009-06-01"
TAIL_ODDS = 40                         # one bar in 40 moves 4x / gaps 8x
ALWAYS = [("2000-01-01", "9999-12-31")]
RACE_ALL_EVERY = 5                     # race_all: every 5th warm bar
RACE_ALL_CAPS = {"fixed": 20, "trail": 60}
GOLDEN_RESAMPLES = 500
GOLDEN_DATE = "2026-10-21"
```

Functions (bodies are the implementer's, except where one is given):

- `fixture_frame(seed: int, n: int = BARS, start: str = START) -> pd.DataFrame` — exactly this algorithm (it fixes the golden's inputs):

```python
def fixture_frame(seed: int, n: int = BARS, start: str = START) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = rng.integers(-40, 43, n)                       # close move in 1/2048ths, slight up-drift
    step = np.where(rng.integers(0, TAIL_ODDS, n) == 0, 4 * step, step)
    close = 100.0 * np.cumprod(1.0 + step / 2048.0)
    gap = rng.integers(-24, 25, n)
    gap = np.where(rng.integers(0, TAIL_ODDS, n) == 0, 8 * gap, gap)
    open_ = np.r_[100.0, close[:-1]] * (1.0 + gap / 4096.0)
    high = np.maximum(open_, close) * (1.0 + rng.integers(0, 40, n) / 4096.0)
    low = np.minimum(open_, close) * (1.0 - rng.integers(0, 40, n) / 4096.0)
    spike = np.where(rng.integers(0, 50, n) == 0, 3.0, 1.0)
    volume = rng.integers(500_000, 3_000_000, n).astype(float) * spike
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": volume}, index=pd.bdate_range(start, periods=n))
```

- `_exact(value)` — recursive JSON-safe conversion: NumPy scalars via `.item()` first; floats → `repr(float(v))` (NaN becomes `"nan"`); ints, bools, str, None unchanged; `np.ndarray` → `_exact(v.tolist())`; `Counter` / `dict` → dict with `str` keys, sorted; list/tuple → list; `pd.DataFrame` → `{"columns": [...], "index": [str(i) ...], "values": _exact(df.to_numpy().tolist())}`; a dataclass instance (`verdict.Verdict`, `race.RaceResult`) → `{f.name: _exact(getattr(v, f.name)) for f in dataclasses.fields(v)}`. Anything else raises `TypeError` (a silent `str()` would hide a type change).
- `_ideas() -> dict` — `{name: IDEAS[name] for name in LONG_IDEAS}` plus `TRAIL_VARIANT: dataclasses.replace(IDEAS["high52w"], name=TRAIL_VARIANT, race_shape="trail")`.
- `_context() -> dict[str, pd.DataFrame]` — `{name: fixture_frame(seed, CONTEXT_BARS, CONTEXT_START) for name, seed in CONTEXT_SEEDS.items()}`.
- `_screen_fields(screen) -> dict` — the nine `TickerScreen` fields in declaration order (`ticker`, `counters`, `events`, `null_outcomes`, `excess`, `rank`, `null_timeout_r`, `stressed`, `restricted`).
- `_race_all(df) -> dict` — `atr = indicators.atr(df)`, `sma200 = indicators.sma(df["Close"], 200)`; for each `shape, cap in RACE_ALL_CAPS.items()`: positions `p` with `race.warm_mask(atr, sma200)[p]` and `p + cap <= len(df) - 1`, every `RACE_ALL_EVERY`-th of them; `race.race_for(shape)(df, positions, cap, atr=atr)` with default costs (config slippage, `commission_r()`); returns `{shape: RaceResult}`.
- `_results_doc(idea, summary) -> str` — `screen_idea.render_results(idea, summary, screen_idea.Universe({}, ["S7", "S11", "S13"], ["S7", "S11", "S13"], []), run)` with `run = {"ledger_id": screen_idea.ledger_id(idea.name), "q": 0.5, "date": GOLDEN_DATE, "start": screen_idea.WINDOW_START, "end": screen_idea.WINDOW_END, "slippage_bps": screen_idea.base_slippage(None), "commission": commission_r()}`. Non-context ideas only (a context idea's doc needs diagnostics data; `diagnostics.py` is untouched by v182).
- `capture() -> dict` — inside `mock.patch.object(screen_idea.verdict, "decide", partial(verdict.decide, n_resamples=GOLDEN_RESAMPLES))`: build `_context()` once; for every seed build `fixture_frame(seed)`; for every idea in `_ideas()` screen each frame with `screen_idea.screen_ticker(idea, f"S{seed}", df, ALWAYS, context=context)`; store `payload[f"{name}/{seed}/{field}"]` for every screen field, `payload[f"{name}/summary/{key}"]` for every key of `screen_idea.summarise(screens)`, `payload[f"{name}/hypothesis"] = screen_idea.hypothesis(idea)`, `payload[f"{name}/results_doc"]` when `not idea.context`, and `payload[f"race_all/{seed}/{shape}"]` from `_race_all(df)`. Every value goes through `_exact`.
- `digests(payload) -> dict[str, str]` — `{key: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}`.
- `counts(payload) -> dict[str, int]` — for each name in `_ideas()`: `sum(len(payload[f"{name}/{seed}/events"]) for seed in SEEDS)`.
- `write() -> Path` — writes `{"captured_on": "main @ 9536ce09 (engine unchanged)", "counts": counts(p), "digests": digests(p)}` to `GOLDEN_PATH` (`json.dumps(..., indent=1, sort_keys=True)`, `newline="\n"`, parent created).
- `main(argv=None) -> int` — `--write` calls `write()` and prints the path; without it, prints `counts(capture())` and writes nothing. `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 3: Write `tests/backtesting/screen/test_long_byte_identical.py`**

```python
"""v182 partner rule: every long result stays byte-identical. The golden was
captured in V182-1 on engine code identical to main; never regenerate it to
make this pass."""
import json

import pytest

from tests.backtesting.screen import long_golden


@pytest.fixture(scope="module")
def payload():
    return long_golden.capture()


@pytest.fixture(scope="module")
def golden():
    return json.loads(long_golden.GOLDEN_PATH.read_text(encoding="utf-8"))


def test_every_long_output_is_byte_identical_to_the_golden(payload, golden):
    now = long_golden.digests(payload)
    assert set(now) == set(golden["digests"])
    changed = sorted(key for key in now if now[key] != golden["digests"][key])
    assert changed == []


def test_the_golden_is_not_vacuous(payload, golden):
    assert long_golden.counts(payload) == golden["counts"]
    assert all(n > 0 for n in golden["counts"].values())
    assert set(golden["counts"]) == set(long_golden.LONG_IDEAS) | {long_golden.TRAIL_VARIANT}


def test_the_fixture_frame_is_well_formed_and_deterministic():
    df = long_golden.fixture_frame(7, n=300)
    assert df.equals(long_golden.fixture_frame(7, n=300))
    assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
    assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
    assert (df["Low"] > 0).all()


def test_the_capture_never_reads_the_growing_registry():
    assert long_golden.LONG_IDEAS == (
        "high52w", "uptrend_pullback", "gap_volume", "turn_of_month", "turtle_soup",
        "quiet_pullback", "bond_spike_rebound", "dollar_drop", "sweep_reclaim_bos")
```

The comparison is over sha256 digests of exact `repr` strings, so it is exact (never `approx`) and the golden stays a few kilobytes. A failure names the changed keys, e.g. `["turtle_soup/11/events", "turtle_soup/summary/verdict"]`.

- [ ] **Step 4: Capture the long golden on unchanged engine code**

```bash
git diff --quiet main -- swingbot scripts && python tests/backtesting/screen/long_golden.py
```

Expected: a counts dict, every value > 0. If an idea shows 0 (most likely `bond_spike_rebound` or `dollar_drop` on too-quiet context frames), lower `TAIL_ODDS` (e.g. 40 → 25) and re-run until every count is > 0 — this changes test inputs only, never engine code. Then:

```bash
python tests/backtesting/screen/long_golden.py --write
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
```

Expected: `tests/backtesting/screen/golden/long_v182.json` written (a few KB); 4 passed, twice (determinism).

- [ ] **Step 5: Write `tests/backtest_scripts/test_calibration_long_golden.py`**

```python
"""v182 partner rule: the calibration script's default (long, trail) run
prints the same text, byte for byte, after every v182 task. Golden captured
in V182-1 on the unchanged script."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backtest" / "screen_trail_calibration.py"
GOLDEN = Path(__file__).with_name("golden") / "trail_calibration_v182.txt"
ARGS = ("--replicates", "3", "--tickers", "2", "--resamples", "500",
        "--date", "2026-10-21", "--dry-run")


def run_default() -> str:
    """The script's stdout for ARGS, decoded UTF-8, CRLF folded to LF."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, str(SCRIPT), *ARGS], cwd=ROOT, env=env,
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8").replace("\r\n", "\n")


def test_default_calibration_output_is_byte_identical_to_the_golden():
    assert run_default() == GOLDEN.read_text(encoding="utf-8")


def test_the_golden_is_the_long_trail_calibration():
    text = GOLDEN.read_text(encoding="utf-8")
    assert text.startswith("# v163 trail race A/A calibration")
    assert "| 20261015 |" in text and "| 20261017 |" in text
```

- [ ] **Step 6: Capture the calibration golden on the unchanged script**

```bash
mkdir -p tests/backtest_scripts/golden
python -c "import sys; sys.path.insert(0, '.'); from tests.backtest_scripts import test_calibration_long_golden as t; t.GOLDEN.write_text(t.run_default(), encoding='utf-8', newline='\n')"
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: the golden starts `# v163 trail race A/A calibration ->` and holds three per-replicate rows (seeds 20261015..20261017); 2 passed.

- [ ] **Step 7: Prove the engine is still main's, then commit (the worktree's first commit)**

```bash
git diff --quiet main -- swingbot scripts && echo "engine identical to main"
git add tests/backtesting/screen/long_golden.py tests/backtesting/screen/golden/long_v182.json tests/backtesting/screen/test_long_byte_identical.py tests/backtest_scripts/golden/trail_calibration_v182.txt tests/backtest_scripts/test_calibration_long_golden.py
git commit -m "test(v182): golden long outputs before any engine edit -- screen and calibration byte-identity

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `engine identical to main`, then one commit with five new files.

### Task V182-2: Borrow fee in frictions

**Model:** haiku — one pure arithmetic function with its formula fixed by the spec.

**Files:**
- Modify: `swingbot/core/edge/frictions.py` (append after `commission_r`, line 28)
- Test: `tests/edge/test_edge_frictions.py` (extend the import at line 6; append tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `BORROW_RATE_ANNUAL = 0.005`; `borrow_r(entry, risk, days)` → `entry * BORROW_RATE_ANNUAL / 365.0 * days / risk`, same shape as its inputs (Python floats in, float out; NumPy arrays in, array out — no `float()` cast, no branching). `days` is calendar days from the entry date to the exit date (`sides.holding_days`, V182-4); `entry` is the real fill price (also in level mode). Consumed by `sides.net_r` (V182-4) for short trades only; nothing existing calls it, so adding it cannot touch a long result.

- [ ] **Step 1: Write the failing tests**

Change line 6 of `tests/edge/test_edge_frictions.py` to

```python
from swingbot.core.edge.frictions import (BORROW_RATE_ANNUAL, apply_frictions, borrow_r,
                                          commission_r)
```

and append:

```python
def test_borrow_rate_is_half_a_percent_a_year():
    assert BORROW_RATE_ANNUAL == 0.005


def test_borrow_r_golden_value():
    # $100 short for 73 calendar days at 0.5%/yr = $0.10; over $2 risk = 0.05R
    assert borrow_r(100.0, 2.0, 73) == pytest.approx(0.05, rel=1e-12)


def test_borrow_r_is_the_spec_expression_bit_for_bit():
    entry, risk, days = 87.375, 3.125, 11
    assert borrow_r(entry, risk, days) == entry * 0.005 / 365.0 * days / risk


def test_borrow_is_zero_for_a_same_day_exit():
    assert borrow_r(100.0, 2.0, 0) == 0.0


def test_borrow_counts_calendar_days_over_a_weekend():
    # Friday entry, Monday exit: three calendar days, not one session
    friday, monday = pd.Timestamp("2015-03-06"), pd.Timestamp("2015-03-09")
    days = (monday - friday).days
    assert days == 3
    assert borrow_r(100.0, 2.0, days) == pytest.approx(3 * borrow_r(100.0, 2.0, 1), rel=1e-12)


def test_borrow_r_is_vectorised_elementwise():
    entry = np.array([100.0, 50.0, 80.0])
    risk = np.array([2.0, 1.0, 4.0])
    days = np.array([0.0, 7.0, 30.0])
    out = borrow_r(entry, risk, days)
    assert isinstance(out, np.ndarray) and out.shape == (3,)
    assert out.tolist() == [borrow_r(e, r, d) for e, r, d in zip(entry, risk, days)]


def test_borrow_r_grows_with_price_and_time_and_shrinks_with_risk():
    base = borrow_r(100.0, 2.0, 10)
    assert borrow_r(200.0, 2.0, 10) == pytest.approx(2 * base)
    assert borrow_r(100.0, 2.0, 20) == pytest.approx(2 * base)
    assert borrow_r(100.0, 4.0, 10) == pytest.approx(base / 2)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_frictions.py`
Expected: collection error, `ImportError: cannot import name 'BORROW_RATE_ANNUAL'`.

- [ ] **Step 3: Implement**

Append to `swingbot/core/edge/frictions.py`:

```python
#: v182: the stock-borrow fee a short pays, a year. S&P 500 names are
#: general-collateral borrows (about 0.25-0.5%); 0.5% is the conservative end.
BORROW_RATE_ANNUAL = 0.005


def borrow_r(entry, risk, days):
    """The borrow fee of a short held ``days`` calendar days, in R:
    entry x BORROW_RATE_ANNUAL / 365 x days / risk. Elementwise on arrays.
    Never charged on a long trade (v182)."""
    return entry * BORROW_RATE_ANNUAL / 365.0 * days / risk
```

Also extend the module docstring's first line to `"""Execution frictions: slippage, commission and (v182) the short borrow fee.`.

- [ ] **Step 4: Run the tests and the goldens**

```bash
python scripts/dev/testrun.py file tests/edge/test_edge_frictions.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: all pass, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/edge/frictions.py tests/edge/test_edge_frictions.py
git commit -m "feat(v182): borrow_r -- 0.5%/yr short borrow fee in R over calendar days

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-3: `Idea` accepts short, an entry mode, levels, a control and a family

**Model:** sonnet — a dataclass extension with validation and registry pins; two existing tests change meaning and must be rewritten, not deleted.

**Files:**
- Modify: `swingbot/core/backtesting/screen/ideas/__init__.py` (docstring :1-15, `Idea` :38-62, `_load` :65-71)
- Test: `tests/backtesting/screen/test_ideas_registry.py` (rewrite :51-55 and :66-72; append)

**Interfaces:**
- Consumes: nothing new.
- Produces (fields appended after `context`, all keyword-defaulted, so every existing constructor call is unchanged):
  - `DIRECTIONS = ("long", "short")`, `ENTRY_MODES = ("next_open", "level")`
  - `Idea.entry: str = "next_open"`
  - `Idea.levels: Callable[[pd.DataFrame], pd.Series] | None = None` — level-mode ideas only: the level per bar, known from bars ≤ t−1
  - `Idea.control: Callable[[pd.DataFrame], pd.Series] | None = None` — the trend-only control events (V182-17), never gating
  - `Idea.family: tuple[str, ...] = ()` — names screened as one family (V182-13: the two breakdown ideas)
  - `_load(name)` reads `DIRECTION` (default `"long"`), `ENTRY` (default `"next_open"`), `levels` (default `None`), `control_events` (default `None`), `FAMILY` (default `()`) with `getattr`, beside `RACE` and `CONTEXT`.
  - Validation (all `ValueError`, message starts with the idea name): direction not in `DIRECTIONS`; entry not in `ENTRY_MODES`; `entry == "level"` without `levels`; `entry == "next_open"` with `levels`; `entry == "level"` with `race_shape == "trail"` (spec: level mode is fixed shape only).
- Consumed by: V182-6 (`_books` reads `idea.direction`), V182-7 (`Idea(direction="short", entry=...)`), V182-11 (`idea.entry`, `idea.levels`), V182-14/15 (module constants), V182-17 (`idea.control`, `idea.family`).

No registered idea changes: all nine keep `long`, `next_open`, no levels, no control, no family. Allowing `"short"` here does not race anything short yet — the race learns direction in V182-4/5 and no short idea is registered before V182-14.

- [ ] **Step 1: Write the failing tests**

In `tests/backtesting/screen/test_ideas_registry.py`, replace `test_every_idea_is_long_and_cites_its_source` (:51-55) with:

```python
def test_every_idea_cites_its_source():
    for idea in IDEAS.values():
        assert idea.summary.strip() and idea.source.strip()
        assert callable(idea.events)


def test_every_registered_idea_pins_its_direction_and_entry():
    """Direction and entry are frozen with the idea, like RACE (v182 Part A/B).
    Flipping either means a new idea with a new name, and editing this pin in
    the same diff."""
    assert ideas.DIRECTIONS == ("long", "short")
    assert ideas.ENTRY_MODES == ("next_open", "level")
    assert {n: i.direction for n, i in IDEAS.items()} == {
        "high52w": "long", "uptrend_pullback": "long", "gap_volume": "long",
        "turn_of_month": "long", "turtle_soup": "long", "quiet_pullback": "long",
        "bond_spike_rebound": "long", "dollar_drop": "long", "sweep_reclaim_bos": "long"}
    assert {n: i.entry for n, i in IDEAS.items()} == {
        "high52w": "next_open", "uptrend_pullback": "next_open", "gap_volume": "next_open",
        "turn_of_month": "next_open", "turtle_soup": "next_open",
        "quiet_pullback": "next_open", "bond_spike_rebound": "next_open",
        "dollar_drop": "next_open", "sweep_reclaim_bos": "next_open"}
    assert {n: (i.levels, i.control, i.family) for n, i in IDEAS.items()} == {
        n: (None, None, ()) for n in IDEAS}
```

Replace `test_an_idea_refuses_a_short_direction_and_a_zero_cap` (:66-72) with:

```python
def test_an_idea_refuses_an_unknown_direction_and_a_zero_cap():
    with pytest.raises(ValueError, match="direction"):
        Idea(name="x", events=_events, time_cap_bars=5, direction="sideways")
    with pytest.raises(ValueError):
        Idea(name="x", events=_events, time_cap_bars=0)


def test_an_idea_accepts_a_short_direction_and_defaults_to_long_next_open():
    short = Idea(name="x", events=_events, time_cap_bars=20, direction="short")
    assert short.direction == "short" and short.entry == "next_open"
    plain = Idea(name="x", events=_events, time_cap_bars=5)
    assert (plain.direction, plain.entry, plain.levels, plain.control, plain.family) == (
        "long", "next_open", None, None, ())
```

(`_events` at :102 is a module global, looked up at call time, so these tests may stay where they are.) Append:

```python
def _levels(df):
    return df["Low"].shift(1)


def test_an_unknown_entry_mode_is_refused():
    with pytest.raises(ValueError, match="entry"):
        Idea(name="x", events=_events, time_cap_bars=20, entry="limit")


def test_a_level_idea_needs_levels_and_a_next_open_idea_refuses_them():
    with pytest.raises(ValueError, match="levels"):
        Idea(name="x", events=_events, time_cap_bars=20, entry="level")
    with pytest.raises(ValueError, match="levels"):
        Idea(name="x", events=_events, time_cap_bars=20, levels=_levels)
    idea = Idea(name="x", events=_events, time_cap_bars=20, direction="short",
                entry="level", levels=_levels)
    assert idea.entry == "level" and idea.levels is _levels


def test_level_entry_is_fixed_shape_only():
    with pytest.raises(ValueError, match="fixed"):
        Idea(name="x", events=_events, time_cap_bars=60, entry="level",
             levels=_levels, race_shape="trail")


def test_family_is_stored_as_a_tuple():
    idea = Idea(name="x", events=_events, time_cap_bars=5, family=["x", "y"])
    assert idea.family == ("x", "y")


def test_load_reads_direction_entry_levels_control_and_family(monkeypatch):
    plain = _fake_module(monkeypatch, "fake_long_default", CAP=10)
    short = _fake_module(monkeypatch, "fake_short_level", CAP=20, DIRECTION="short",
                         ENTRY="level", levels=_levels, control_events=_events,
                         FAMILY=["fake_short_level", "fake_other"])
    loaded = ideas._load(plain)
    assert (loaded.direction, loaded.entry, loaded.levels, loaded.control, loaded.family) == (
        "long", "next_open", None, None, ())
    loaded = ideas._load(short)
    assert loaded.direction == "short" and loaded.entry == "level"
    assert loaded.levels is _levels and loaded.control is _events
    assert loaded.family == ("fake_short_level", "fake_other")


def test_load_refuses_a_module_with_an_unknown_direction(monkeypatch):
    bad = _fake_module(monkeypatch, "fake_bad_direction", CAP=10, DIRECTION="both")
    with pytest.raises(ValueError, match="direction"):
        ideas._load(bad)
```

Also change the module docstring's first line to `"""Idea registry (v140; v163 race shape; v174 context; v182 direction and entry)."""`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'DIRECTIONS'`, `TypeError: ... unexpected keyword argument 'entry'`, and the short-direction test raising `v140 screens long ideas only`.

- [ ] **Step 3: Implement in `swingbot/core/backtesting/screen/ideas/__init__.py`**

- Add after `TRAIL_MIN_CAP`:

```python
#: v182: a short idea races the exact mirror of the long race.
DIRECTIONS = ("long", "short")
#: v182: "next_open" (every idea before v182) or "level" (a resting stop order
#: that fills on the event bar at levels(df), fixed shape only).
ENTRY_MODES = ("next_open", "level")
```

- Append four fields to `Idea` after `context` (order fixed by the ledger): `entry: str = "next_open"`, `levels: Callable[[pd.DataFrame], pd.Series] | None = None`, `control: Callable[[pd.DataFrame], pd.Series] | None = None`, `family: tuple[str, ...] = ()`.
- Replace the long-only check in `__post_init__` with the validation listed under **Interfaces**, and store `family` as a tuple (`object.__setattr__(self, "family", tuple(self.family))`). Keep `__post_init__` under complexity 15 by moving the checks into two module-level helpers that return a message or `None`: `_shape_problem(idea) -> str | None` (cap, race shape, trail cap — the existing three checks, same messages) and `_side_problem(idea) -> str | None` (direction, entry, levels, level-with-trail); `__post_init__` raises `ValueError(problem)` for the first non-`None`. Messages: `f"{name}: direction {d!r} is not one of {DIRECTIONS}"`, `f"{name}: entry {e!r} is not one of {ENTRY_MODES}"`, `f"{name}: a level idea needs levels(df)"`, `f"{name}: a next_open idea takes no levels"`, `f"{name}: level entry races the fixed shape only"`. The three existing messages stay word for word (`test_a_trail_idea_needs_a_cap_of_at_least_sixty_bars` matches `at least 60`).
- `_load`: add `direction=getattr(module, "DIRECTION", "long")`, `entry=getattr(module, "ENTRY", "next_open")`, `levels=getattr(module, "levels", None)`, `control=getattr(module, "control_events", None)`, `family=tuple(getattr(module, "FAMILY", ()))`.
- Docstring: add a paragraph — `v182: a module may also export DIRECTION ("long" default, or "short"), ENTRY ("next_open" default, or "level" with a levels(df) function giving the order level per bar from bars <= t-1), control_events(df) (the trend-only control, printed, never gating) and FAMILY (names screened as one family). A changed DIRECTION or ENTRY is a new idea with a new name.`

- [ ] **Step 4: Run the tests, the complexity gate and the goldens**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_ideas_registry.py
python scripts/dev/complexity_gate.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
```

Expected: all pass; the complexity gate reports no regression.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/screen/ideas/__init__.py tests/backtesting/screen/test_ideas_registry.py
git commit -m "feat(v182): Idea accepts short, an entry mode, levels, a control and a family

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V182-4: `sides.py` and the short fixed race (mirror identity)

**Model:** opus — shared race code under a byte-identity rule: operand order, negation exactness and float ties decide whether the long golden survives and the mirror identity holds.

**Files:**
- Create: `swingbot/core/backtesting/screen/sides.py`
- Modify: `swingbot/core/backtesting/screen/race.py` (docstring :1-16, imports :25-26, `race` :98-116, `run_book` :168-178)
- Test: `tests/backtesting/screen/test_sides.py` (create)
- Test: `tests/backtesting/screen/test_race_short.py` (create)

**Interfaces:**
- Consumes: `borrow_r(entry, risk, days)` (V182-2); `apply_frictions`, `commission_r` (`frictions.py:15`, `:22`); `_first_exit` (`race.py:79`, unchanged).
- Produces:
  - `sides.oriented(o, h, l, c, direction) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]` — long: the **same objects** `(o, h, l, c)`; short: `(-o, -l, -h, -c)` (the long race reads a short as a long on negated prices: High' = −Low, Low' = −High); anything else: `ValueError` naming the direction.
  - `sides.holding_days(index: pd.DatetimeIndex, entry_pos, exit_pos) -> np.ndarray` — calendar days `index[exit_pos] − index[entry_pos]` as float.
  - `sides.net_r(entry, price, risk, *, direction, days, slippage_bps=None, entry_bps=None, commission=None) -> np.ndarray` — `entry` and `price` are **real (un-negated) prices**; `entry_bps=None` means the entry fill uses `slippage_bps` (V182-9 passes `entry_bps` = 2 × base for level entries); `commission=None` means `commission_r()`. Long: `(apply_frictions(price, "sell", slippage_bps) - apply_frictions(entry, "buy", entry_bps_or_slippage)) / risk - cost` — today's expression, operand order kept, `days` ignored, `borrow_r` never called. Short: `(apply_frictions(entry, "sell", eb) - apply_frictions(price, "buy", slippage_bps)) / risk - cost - borrow_r(entry, risk, days)`.
  - `race.race(df, event_pos, cap, *, atr=None, slippage_bps=None, commission=None, direction="long") -> RaceResult` — `RaceResult.entry` holds the real entry price in both directions; `gross_r` is `(exit − entry) / risk` long, `(entry − exit) / risk` short.
  - `race.run_book(df, events, cap, *, member, warm, atr, slippage_bps=None, commission=None, shape="fixed", direction="long")` — passes `direction=` to the race function **only when it is not `"long"`**, so the long call is literally today's and `trail.race_trail` (direction-aware only from V182-5) is never handed an unknown keyword on a long run.
- Consumed by: V182-5 (`trail.py` calls `sides.oriented`, `sides.holding_days`, `sides.net_r` with real prices), V182-6 (null races through `race_for(shape)(…, direction=)`), V182-9 (`net_r(entry_bps=)`).

**How the short race works:** `race()` reads `o, h, l, c = sides.oriented(...)` and runs the unchanged long machinery on them: entry `o[t+1]`, stop `entry − risk`, target `entry + 2 × risk`, `_first_exit` untouched. On negated prices that is exactly the short table of the spec (stop above, target below, gap stop `Open ≥ stop`, high checked first). Gross R is computed in that oriented space. Only then are entry and exit negated back (exact in IEEE) for `RaceResult.entry` and for `net_r`. For a long, `oriented` returns the original arrays and no negation runs, so every long float is computed by the same operations as today.

- [ ] **Step 1: Write the failing `tests/backtesting/screen/test_sides.py`**

```python
"""v182 sides: orientation, holding days and per-fill net R by direction."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import sides
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r


def _ohlc():
    return (np.array([100.0, 101.0]), np.array([102.0, 103.0]),
            np.array([99.0, 98.5]), np.array([101.0, 100.0]))


def test_long_orientation_returns_the_same_arrays():
    o, h, l, c = _ohlc()
    out = sides.oriented(o, h, l, c, "long")
    assert all(a is b for a, b in zip(out, (o, h, l, c)))


def test_short_orientation_negates_and_swaps_high_and_low():
    o, h, l, c = _ohlc()
    so, sh, sl, sc = sides.oriented(o, h, l, c, "short")
    assert so.tolist() == (-o).tolist() and sc.tolist() == (-c).tolist()
    assert sh.tolist() == (-l).tolist() and sl.tolist() == (-h).tolist()
    assert (sh >= sl).all()


def test_an_unknown_direction_is_refused():
    with pytest.raises(ValueError, match="direction"):
        sides.oriented(*_ohlc(), "sideways")
    with pytest.raises(ValueError, match="direction"):
        sides.net_r(np.array([1.0]), np.array([1.0]), np.array([1.0]),
                    direction="both", days=np.array([1.0]))


def test_holding_days_are_calendar_days():
    index = pd.bdate_range("2015-03-04", periods=6)    # Wed .. next Wed
    days = sides.holding_days(index, np.array([0, 2, 1]), np.array([0, 3, 5]))
    assert days.tolist() == [0.0, 3.0, 6.0]            # same day; Fri->Mon; Thu->Wed


def test_long_net_r_is_todays_expression_bit_for_bit():
    rng = np.random.default_rng(3)
    entry = rng.uniform(20, 200, 50)
    price = entry * rng.uniform(0.9, 1.1, 50)
    risk = rng.uniform(0.5, 5.0, 50)
    for bps, comm in ((None, None), (5.0, 0.02), (0.0, 0.0)):
        cost = commission_r() if comm is None else comm
        old = (apply_frictions(price, "sell", bps)
               - apply_frictions(entry, "buy", bps)) / risk - cost
        new = sides.net_r(entry, price, risk, direction="long", days=None,
                          slippage_bps=bps, commission=comm)
        assert new.tolist() == old.tolist()


def test_long_net_r_never_charges_borrow(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("borrow_r called on a long trade")
    monkeypatch.setattr(sides, "borrow_r", boom)
    sides.net_r(np.array([100.0]), np.array([103.0]), np.array([2.0]),
                direction="long", days=np.array([5.0]))


def test_short_net_r_sells_the_entry_and_buys_the_exit():
    entry, price, risk, days = np.array([100.0]), np.array([94.0]), np.array([3.0]), np.array([7.0])
    out = sides.net_r(entry, price, risk, direction="short", days=days,
                      slippage_bps=5.0, commission=0.02)
    expected = (99.95 - 94.047) / 3.0 - 0.02 - borrow_r(100.0, 3.0, 7.0)
    assert out[0] == pytest.approx(expected, rel=1e-12)
    exact = ((apply_frictions(entry, "sell", 5.0) - apply_frictions(price, "buy", 5.0)) / risk
             - 0.02 - borrow_r(entry, risk, days))
    assert out.tolist() == exact.tolist()


def test_short_net_r_charges_borrow_on_calendar_days():
    args = (np.array([100.0, 100.0, 100.0]), np.array([97.0, 97.0, 97.0]),
            np.array([2.0, 2.0, 2.0]))
    out = sides.net_r(*args, direction="short", days=np.array([0.0, 1.0, 3.0]),
                      slippage_bps=0.0, commission=0.0)
    assert out[0] == pytest.approx(1.5, rel=1e-12)              # same day: no borrow
    assert out[0] - out[2] == pytest.approx(3 * (out[0] - out[1]), rel=1e-9)
    assert out[0] - out[2] == pytest.approx(borrow_r(100.0, 2.0, 3.0), rel=1e-9)


def test_entry_bps_moves_only_the_entry_fill():
    e, p, r, d = np.array([100.0]), np.array([95.0]), np.array([2.0]), np.array([0.0])
    short = sides.net_r(e, p, r, direction="short", days=d, slippage_bps=5.0,
                        entry_bps=10.0, commission=0.0)
    assert short[0] == pytest.approx(((100.0 - 0.10) - (95.0 + 0.0475)) / 2.0, rel=1e-12)
    long = sides.net_r(p, e, r, direction="long", days=d, slippage_bps=5.0,
                       entry_bps=10.0, commission=0.0)
    assert long[0] == pytest.approx(((100.0 - 0.05) - (95.0 + 0.095)) / 2.0, rel=1e-12)
```

- [ ] **Step 2: Write the failing `tests/backtesting/screen/test_race_short.py`**

```python
"""v182 short fixed race: the exact mirror of the long race (spec Part A 1)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators, race as race_mod, sides
from tests.backtesting.screen.helpers import frame, random_walk

QUIET = (100.0, 101.0, 99.0, 100.0)    # short entry 100: never reaches stop 103 or target 94
C_HAND = 256.0                          # a power of two: reflection is exact on 1/8 prices
C_RANDOM = 1024.0


def _frame(bars):
    rows = [QUIET] + list(bars)
    o, h, l, c = (np.array(col, dtype=float) for col in zip(*rows))
    return frame(c, opens=o, highs=h, lows=l)


def _mirror(df, c):
    """P' = c - P for Open/Close; High' = c - Low; Low' = c - High."""
    out = df.copy()
    out["Open"], out["Close"] = c - df["Open"], c - df["Close"]
    out["High"], out["Low"] = c - df["Low"], c - df["High"]
    return out


def _atr(df, value=2.0):
    return pd.Series(value, index=df.index)          # risk 3.0


def _short(df, positions, cap, **kw):
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    return race_mod.race(df, positions, cap, direction="short", **kw)


def _long(df, positions, cap, **kw):
    kw.setdefault("slippage_bps", 0.0)
    kw.setdefault("commission", 0.0)
    return race_mod.race(df, positions, cap, **kw)


HAND = {   # name: (bars after the signal bar, cap, outcome, gross R, exit bar)
    "gap_stop": ([QUIET, (105.0, 106.0, 104.0, 105.0), QUIET], 3, "gap_stop", -5.0 / 3.0, 2),
    "gap_target": ([QUIET, (93.0, 94.0, 92.0, 93.0), QUIET], 3, "gap_target", 7.0 / 3.0, 2),
    "stop_first": ([(100.0, 104.0, 93.0, 100.0), QUIET], 2, "stop", -1.0, 1),
    "target": ([QUIET, (99.0, 100.0, 93.5, 94.0), QUIET], 3, "target", 2.0, 2),
    "stop": ([QUIET, (101.0, 103.125, 99.0, 102.0), QUIET], 3, "stop", -1.0, 2),
    "timeout": ([QUIET, QUIET, (100.0, 101.0, 99.0, 98.5)], 3, "timeout", 0.5, 3),
}


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_race_on_hand_built_frames(name):
    bars, cap, outcome, gross, exit_bar = HAND[name]
    df = _frame(bars)
    out = _short(df, [0], cap, atr=_atr(df))
    assert out.outcome.tolist() == [outcome]
    assert out.gross_r.tolist() == [pytest.approx(gross, rel=1e-12)]
    assert out.exit_pos.tolist() == [exit_bar]
    assert out.entry.tolist() == [100.0]                # the real entry price
    assert out.risk.tolist() == [3.0]


@pytest.mark.parametrize("name", sorted(HAND))
def test_short_on_p_is_long_on_the_reflected_frame_exactly(name):
    bars, cap, *_ = HAND[name]
    df = _frame(bars)
    mirror = _mirror(df, C_HAND)
    short, long = _short(df, [0], cap, atr=_atr(df)), _long(mirror, [0], cap, atr=_atr(mirror))
    assert short.outcome.tolist() == long.outcome.tolist()
    assert short.exit_pos.tolist() == long.exit_pos.tolist()
    assert short.gross_r.tolist() == long.gross_r.tolist()       # dyadic: exact


def _tie_free(df, positions, cap, atr, tol=1e-9):
    """True where no Open/High/Low of the raced bars lies within tol of the
    short stop or target (a near-tie may flip under reflection rounding)."""
    o, h, l = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low"))
    a = atr.to_numpy(dtype=float)
    ok = []
    for p in positions:
        entry, risk = o[p + 1], race_mod.STOP_ATR * a[p]
        levels = np.array([entry + risk, entry - race_mod.REWARD_RISK * risk])
        prices = np.concatenate([o[p + 1:p + 1 + cap], h[p + 1:p + 1 + cap], l[p + 1:p + 1 + cap]])
        ok.append(np.abs(prices[:, None] - levels[None, :]).min() > tol)
    return np.asarray(ok)


@pytest.mark.parametrize("seed", [7, 11, 23])
def test_mirror_identity_on_random_frames(seed):
    df = random_walk(800, seed=seed)
    atr = indicators.atr(df)
    cap = 20
    positions = np.arange(20, len(df) - 1 - cap)
    short = _short(df, positions, cap, atr=atr)
    long = _long(_mirror(df, C_RANDOM), positions, cap, atr=atr)       # ATR unchanged
    np.testing.assert_allclose(short.gross_r, long.gross_r, rtol=0.0, atol=1e-9)
    ok = _tie_free(df, positions, cap, atr)
    assert ok.mean() > 0.99                                           # non-vacuous
    assert short.outcome[ok].tolist() == long.outcome[ok].tolist()
    assert short.exit_pos[ok].tolist() == long.exit_pos[ok].tolist()
    assert set(short.outcome) >= {"stop", "target", "timeout"}


def test_short_net_r_uses_sides_with_the_real_prices():
    df = _frame([QUIET, (99.0, 100.0, 93.5, 94.0), QUIET])
    out = race_mod.race(df, [0], 3, atr=_atr(df), slippage_bps=5.0, commission=0.02,
                        direction="short")
    days = sides.holding_days(df.index, np.array([1]), out.exit_pos)
    expected = sides.net_r(np.array([100.0]), np.array([94.0]), np.array([3.0]),
                           direction="short", days=days, slippage_bps=5.0, commission=0.02)
    assert out.r.tolist() == expected.tolist()
    assert out.r[0] < out.gross_r[0]


def test_borrow_is_charged_once_per_short_trade_and_never_on_a_long(monkeypatch):
    charged = []
    real = sides.borrow_r

    def counting(entry, risk, days):
        charged.append(int(np.size(days)))
        return real(entry, risk, days)

    monkeypatch.setattr(sides, "borrow_r", counting)
    df = random_walk(400, seed=5)
    positions = np.arange(20, 300, 7)
    race_mod.race(df, positions, 20)
    assert charged == []
    race_mod.race(df, positions, 20, direction="short")
    assert sum(charged) == len(positions)


def test_run_book_threads_the_direction():
    df = random_walk(500, seed=9)
    atr = indicators.atr(df)
    events = np.zeros(len(df), dtype=bool)
    events[30:400:9] = True
    member = np.ones(len(df), dtype=bool)
    warm = np.isfinite(atr.to_numpy())
    booked, counts = race_mod.run_book(df, events, 20, member=member, warm=warm, atr=atr,
                                       direction="short")
    cand, _ = race_mod.candidate_events(events, member, warm, 20)
    raced = race_mod.race(df, cand, 20, atr=atr, direction="short")
    keep = race_mod.non_overlapping(raced.event_pos, raced.exit_pos)
    assert booked.event_pos.tolist() == raced.event_pos[keep].tolist()
    assert booked.r.tolist() == raced.r[keep].tolist()
    assert counts["skipped_overlap"] == int((~keep).sum())


def test_run_book_long_never_passes_a_direction(monkeypatch):
    seen = []

    def fake_race(df, cand, cap, **kwargs):
        seen.append(kwargs)
        return race_mod.RaceResult.empty()

    monkeypatch.setattr(race_mod, "race_for", lambda shape: fake_race)
    df = random_walk(100, seed=1)
    race_mod.run_book(df, np.zeros(100, dtype=bool), 5, member=np.ones(100, bool),
                      warm=np.ones(100, bool), atr=indicators.atr(df))
    assert seen and "direction" not in seen[0]


def test_an_unknown_direction_is_refused_by_the_race():
    df = _frame([QUIET, QUIET])
    with pytest.raises(ValueError, match="direction"):
        race_mod.race(df, [0], 2, atr=_atr(df), direction="sideways")
```

Check the `HAND` values by hand before running (risk 3, entry 100, stop 103, target 94): `gap_stop` bar 2 opens 105 ≥ 103 → exit 105, gross (100 − 105)/3; `gap_target` opens 93 ≤ 94 → exit 93, gross 7/3; `stop_first` bar 1 high 104 ≥ 103 and low 93 ≤ 94 → stop first, −1; `target` low 93.5 ≤ 94 → 94, +2; `stop` high 103.125 ≥ 103 → 103, −1; `timeout` closes 98.5 at bar 3 → (100 − 98.5)/3 = 0.5. Every price is a multiple of 1/8 and `C_HAND = 256`, so the reflected frame is exact.

- [ ] **Step 3: Run both to verify they fail**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_sides.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_short.py
```

Expected: `ModuleNotFoundError: ... sides` and `TypeError: race() got an unexpected keyword argument 'direction'`.

- [ ] **Step 4: Create `swingbot/core/backtesting/screen/sides.py`**

```python
"""v182: trade direction for the screen races.

A short race is the long race on negated prices (O, H, L, C -> -O, -L, -H,
-C): stop above, target below, gap stop on Open >= stop, the high checked
first. So the mirror identity is a property of the code. ``oriented`` hands
a long its own arrays back, untouched, and ``net_r`` keeps the long net-R
expression with its operand order, so every long float is computed exactly
as before v182 (partner rule 2026-10-21).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r

DIRECTIONS = ("long", "short")
```

Then `_check(direction)` (raises `ValueError(f"unknown direction {direction!r}; expected one of {DIRECTIONS}")`), and the three public functions with the signatures and semantics under **Interfaces**. `net_r` dispatches on `direction` with the long expression first; the short expression is

```python
    return ((apply_frictions(entry, "sell", eb) - apply_frictions(price, "buy", slippage_bps))
            / risk - cost - borrow_r(entry, risk, days))
```

`borrow_r` is looked up as a module global (so the counting test can patch `sides.borrow_r`). `holding_days` is `(index[np.asarray(exit_pos)] - index[np.asarray(entry_pos)]).days.to_numpy(dtype=float)`.

- [ ] **Step 5: Make `race.py` direction-aware**

- Imports: replace line 26 with `from swingbot.core.backtesting.screen import indicators, sides` (drop the now-unused `apply_frictions, commission_r` import — `sides` applies both).
- `race(..., direction: str = "long")`: read the four columns through `sides.oriented(*(df[col].to_numpy(dtype=float) for col in ("Open", "High", "Low", "Close")), direction)`; keep `bars`, `entry = o[event_pos + 1]`, `risk = STOP_ATR * atr_v[event_pos]` and the `_first_exit(...)` call exactly as they are; then

```python
    exit_pos = event_pos + 1 + offset
    gross = (price - entry) / risk
    if direction == "short":
        entry, price = -entry, -price            # back to real prices; negation is exact
    net = sides.net_r(entry, price, risk, direction=direction,
                      days=sides.holding_days(df.index, event_pos + 1, exit_pos),
                      slippage_bps=slippage_bps, commission=commission)
    return RaceResult(event_pos, exit_pos, entry, risk, gross, net,
                      np.asarray(OUTCOMES)[code])
```

- `run_book(..., shape: str = "fixed", direction: str = "long")`: build `extra = {} if direction == "long" else {"direction": direction}` and call `race_fn(df, cand, cap, atr=atr, slippage_bps=slippage_bps, commission=commission, **extra)`. Nothing else changes.
- Docstring: replace `Long only.` in line 1 with `Long, and (v182) short as its exact mirror.`, and add a paragraph: `v182: direction="short" races the long machinery on negated prices (sides.oriented): stop = entry + risk, target = entry - 2 x risk, gap stop when the open is at/above the stop, high checked first; gross R = (entry - exit) / risk; frictions sell the entry and buy the exit, plus borrow_r. RaceResult.entry is the real entry price either way.`

- [ ] **Step 6: Run the new tests, the old race tests, the goldens and the gate**

```bash
python scripts/dev/testrun.py file tests/backtesting/screen/test_sides.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race_short.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_race.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_trail.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_null.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_calibration_long_golden.py
python scripts/dev/complexity_gate.py
```

Expected: all pass, `0 failed`, no complexity regression. If the long golden goes red, the long path is no longer computing the same operations: check that `oriented` returns the original arrays (not copies or `1.0 * o`), that `net_r`'s long expression is `(sell(price) - buy(entry)) / risk - cost` in that order, and that `entry_bps=None` resolves to `slippage_bps` itself (including `None`).

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/screen/sides.py swingbot/core/backtesting/screen/race.py tests/backtesting/screen/test_sides.py tests/backtesting/screen/test_race_short.py
git commit -m "feat(v182): sides.py and the short fixed race -- exact mirror of the long race, borrow on shorts only

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

