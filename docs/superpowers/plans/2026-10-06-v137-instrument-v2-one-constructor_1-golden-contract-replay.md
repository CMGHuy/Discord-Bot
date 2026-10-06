# v137 Instrument v2, phase 1: one plan constructor. Part 1: golden, contract, v2 replay (IC1-IC3)

> Index, Global Constraints, Where to work and Parallelisation: `2026-10-06-v137-instrument-v2-one-constructor_0-index.md`. Every task here implicitly includes the index's Global Constraints. Pull one task with `grep -n "^### Task IC<n>" -A 200 docs/superpowers/plans/2026-10-06-v137-instrument-v2-one-constructor_*.md`.

# Phase A: baselines

### Task IC1: Pin the v1 golden (byte-identical witness)

Captured on **unmodified** code. Every later task, and phases 2–6, re-run it.

**Files:**
- Create: `tests/backtesting/instrument/__init__.py` (empty; create if absent)
- Create: `tests/backtesting/instrument/golden.py`
- Create: `tests/backtesting/instrument/test_v1_golden.py`
- Create: `tests/fixtures/instrument/v1_golden.jsonl` (generated, never hand-edited)

**Interfaces:**
- Consumes: `swingbot.core.backtesting.backtest.run_backtest` (unchanged signature today); `tests.fixtures.ohlcv_parity.PARITY_CASES`, `load_ohlcv`; `tests.backtesting.test_pullback_dryup_witness.pin_code_defaults`.
- Produces (IC3 and later phases rely on these):
  - `tests.backtesting.instrument.golden.GOLDEN: Path`
  - `render_v1_golden(**extra) -> str`. `extra` is forwarded to every `run_backtest` call (IC3 passes `instrument=resolve("v1")`).
  - `golden_text() -> str`: the committed file with CRLF normalised to LF.
  - `CONFIGS: tuple[tuple[str, dict], ...]`

- [ ] **Step 0: Create the worktree.** Invoke the `worktree-lifecycle` skill, then:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v137-instrument-v2-one-constructor -b 2026-10-06-v137-instrument-v2-one-constructor main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v137-instrument-v2-one-constructor log --oneline -1
```

Expected: HEAD is this plan's commit on `main`. Confirm `git -C $WT grep -n "def _trade_plan_at" -- swingbot/core/backtesting/backtest.py` prints one line (the code is still unmodified).

- [ ] **Step 1: Write the golden module.** Create `$WT/tests/backtesting/instrument/__init__.py` (empty) and `$WT/tests/backtesting/instrument/golden.py`:

```python
"""The v1 instrument golden (v136 cross-cutting rule 1).

A pinned 3-ticker v1 run -- every case in tests/fixtures/ohlcv_parity.py
(TSLA, DOCU, DELL; frozen OHLCV) under both v1 exit models -- serialised one
JSON record per line. tests/backtesting/instrument/test_v1_golden.py asserts the
current code renders it byte for byte (line endings normalised), so any change
to v1 output, however small, is a red test.

Regenerating it is a cutover decision, not a fix: the writer below refuses to
overwrite an existing file without --force. Captured by v137 IC1 on unmodified
code, under every config field pinned to its code default.

    python <repo>/tests/backtesting/instrument/golden.py --write
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402

from swingbot.core.backtesting import backtest as bt  # noqa: E402
from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv  # noqa: E402

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "instrument" / "v1_golden.jsonl"

CONFIGS = (
    ("exit_v1_frictions", {"exit_model": "v1", "frictions": True}),
    ("exit_v2_scale_out_tp2_levels",
     {"exit_model": "v2", "scale_out": True, "tp2_mode": "levels", "frictions": True}),
)


def _jsonable(value):
    """numpy scalars inside trade contexts -> plain Python (json's only gap)."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def _line(record) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=_jsonable)


def golden_records(**extra):
    """One summary record, then one record per trade, per (case, config)."""
    for ticker, strategy, horizon in PARITY_CASES:
        frame = load_ohlcv(ticker)
        for name, kwargs in CONFIGS:
            summary = dataclasses.asdict(
                bt.run_backtest(ticker, frame, strategy, horizon, **kwargs, **extra))
            trades = summary.pop("trades")
            case = [ticker, strategy, horizon, name]
            yield {"case": case, "summary": summary}
            for k, trade in enumerate(trades):
                yield {"case": case, "trade": k, "row": trade}


def render_v1_golden(**extra) -> str:
    """The golden text the current code produces; `extra` goes to run_backtest."""
    return "".join(_line(record) + "\n" for record in golden_records(**extra))


def golden_text() -> str:
    return GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _write(force: bool) -> None:
    import pytest

    from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

    if GOLDEN.exists() and not force:
        raise SystemExit(f"{GOLDEN} exists; regenerating the v1 golden is a cutover "
                         "decision -- pass --force only with that decision recorded")
    with pytest.MonkeyPatch.context() as mp:
        pin_code_defaults(mp)
        text = render_v1_golden()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN} ({text.count(chr(10))} records)")


if __name__ == "__main__":
    if "--write" not in sys.argv:
        raise SystemExit("usage: golden.py --write [--force]")
    _write("--force" in sys.argv)
```

- [ ] **Step 2: Write the test**, `$WT/tests/backtesting/instrument/test_v1_golden.py`:

```python
"""v136 rule 1: the v1 instrument is byte-identical until cutover.

The golden was captured by v137 IC1 on unmodified code. A failure here means v1
output moved. Find the commit that moved it; do not regenerate the file to make
this pass (see golden.py). A code-default change made elsewhere in config.py
also moves it. Record that decision in the commit that regenerates the file.
"""
import json

import pytest

from tests.backtesting.instrument.golden import CONFIGS, golden_text, render_v1_golden
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults


def _first_difference(expected: str, actual: str) -> str:
    for n, (want, got) in enumerate(zip(expected.splitlines(), actual.splitlines()), 1):
        if want != got:
            return f"line {n}:\n  golden:  {want[:400]}\n  current: {got[:400]}"
    return f"line counts differ: golden {expected.count(chr(10))}, current {actual.count(chr(10))}"


def test_the_golden_pins_real_trades_under_every_config():
    records = [json.loads(line) for line in golden_text().splitlines()]
    with_trades = {tuple(r["case"])[3] for r in records if "trade" in r}
    assert with_trades == {name for name, _ in CONFIGS}


@pytest.mark.slow
def test_v1_instrument_output_is_byte_identical_to_the_pinned_golden(monkeypatch):
    pin_code_defaults(monkeypatch)
    expected, actual = golden_text(), render_v1_golden()
    assert actual == expected, _first_difference(expected, actual)
```

- [ ] **Step 3: Run it before the golden exists.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: FAIL with `FileNotFoundError` on `v1_golden.jsonl`.

- [ ] **Step 4: Generate the golden on unmodified code.**

```bash
git -C $WT status --short swingbot/   # must print nothing: swingbot/ is untouched
python $WT/tests/backtesting/instrument/golden.py --write
```

Expected: `wrote .../tests/fixtures/instrument/v1_golden.jsonl (N records)`. N is about 260 (60 summaries + about 200 trades), and the run takes about 30 s.

- [ ] **Step 5: Run the test.** It should pass, and pass twice: the second run checks determinism in a fresh process.

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py` (twice)
Expected: `2 passed` both times.

- [ ] **Step 6: Commit.**

```bash
git -C $WT add tests/backtesting/instrument/__init__.py tests/backtesting/instrument/golden.py tests/backtesting/instrument/test_v1_golden.py tests/fixtures/instrument/v1_golden.jsonl
git -C $WT commit -m "test(v137): pin the v1 instrument golden on unmodified code (IC1)"
```

---

### Task IC2: `instrument/contract.py` skeleton

**Files:**
- Create: `swingbot/core/backtesting/instrument/__init__.py`
- Create: `swingbot/core/backtesting/instrument/contract.py`
- Create: `tests/backtesting/instrument/__init__.py` (empty; create if absent, because IC1 may already have done it)
- Create: `tests/backtesting/instrument/test_contract.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FillModel(market_entry: str, gap_through: bool, same_bar: str)`, frozen
  - `CostModel(commission_per_share: float, slippage_bps: float, stop_slippage_bps: float)`, frozen
  - `InstrumentSpec(version: str, fill_model: FillModel, cost_model: CostModel)`, frozen, with property `live_constructor -> bool` (False only for `"v1"`)
  - `resolve(version: str) -> InstrumentSpec` (raises `ValueError` for an unknown version)
  - `VERSIONS: tuple[str, ...] == ("v1", "v2")`, `V1_FILLS`, `ZERO_COSTS`

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/instrument/test_contract.py`:

```python
"""v136 phase 1: the instrument contract skeleton (fill/cost fields only)."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import (CostModel, FillModel, InstrumentSpec,
                                                           resolve)


def test_v1_is_todays_behaviour_and_keeps_its_own_plan_path():
    spec = resolve("v1")
    assert spec.version == "v1"
    assert spec.live_constructor is False
    assert spec.fill_model == FillModel(market_entry="signal_close", gap_through=False,
                                        same_bar="stop_first")
    assert spec.cost_model == CostModel(commission_per_share=0.0, slippage_bps=0.0,
                                        stop_slippage_bps=0.0)


def test_v2_builds_through_the_live_constructor():
    assert resolve("v2").version == "v2"
    assert resolve("v2").live_constructor is True


def test_phase_one_v2_stub_carries_v1_fills_and_costs():
    """Phase 2 sets v2's values from spec section 2 and rewrites this test."""
    assert resolve("v2").fill_model == resolve("v1").fill_model
    assert resolve("v2").cost_model == resolve("v1").cost_model


def test_unknown_version_is_refused():
    with pytest.raises(ValueError, match="unknown instrument 'v3'"):
        resolve("v3")


def test_specs_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolve("v1").version = "v2"


def test_phase_one_carries_no_span_fields():
    """Phase 3 adds research/holdout spans, universe and folds and updates this."""
    assert [f.name for f in dataclasses.fields(InstrumentSpec)] == [
        "version", "fill_model", "cost_model"]


def test_versions_lists_every_resolvable_instrument():
    assert contract.VERSIONS == ("v1", "v2")
    assert all(resolve(v).version == v for v in contract.VERSIONS)
```

- [ ] **Step 2: Run it to verify it fails.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.core.backtesting.instrument'`.

- [ ] **Step 3: Implement.** Create `$WT/swingbot/core/backtesting/instrument/__init__.py`:

```python
"""Backtest instrument v2 (v136 spec): the contract and, in later phases, folds,
fills, costs, the causal cache, scan replay and statistics. No re-exports: import
from the defining module."""
```

Create `$WT/swingbot/core/backtesting/instrument/contract.py`:

```python
"""The backtest instrument contract (v136 spec, "Architecture").

``resolve(version)`` is the ONLY place an instrument's rules are defined.
Callers receive an ``InstrumentSpec`` and pass it down
(``run_backtest(..., instrument=spec)``); nothing reads a module-level
"current instrument".

Phase 1 (v137) ships the fill/cost fields only, and v2's values equal v1's:
the one v2 difference phase 1 delivers is the plan constructor
(``InstrumentSpec.live_constructor``). Phase 2 sets v2's fill and cost values
(spec section 2) and owns the final shape of ``FillModel``/``CostModel``;
phase 3 adds the span, universe and fold fields. v1 is frozen: a change to its
values breaks tests/backtesting/instrument/test_v1_golden.py, which is the point.

v1's ``cost_model`` is zero because no v1 path books a contract cost. The legacy
v1 exit loop's own friction (``run_backtest(frictions=True)``,
``edge/frictions.py``) is frozen v1 code that predates this contract and is not
expressed here (spec section 2, "Scope").
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FillModel:
    """How a planned price becomes a fill."""

    market_entry: str   # "signal_close" (v1) | "next_open" (v2, phase 2)
    gap_through: bool   # a bar opening beyond a stop/target fills at the open
    same_bar: str       # a bar containing both stop and target: "stop_first"


@dataclass(frozen=True)
class CostModel:
    """Per-trade costs, converted to R once at booking (phase 2)."""

    commission_per_share: float
    slippage_bps: float        # entries, limit and target exits
    stop_slippage_bps: float   # stop exits (market-on-trigger)


@dataclass(frozen=True)
class InstrumentSpec:
    """One backtest instrument. Phase 1: version, fills, costs."""

    version: str
    fill_model: FillModel
    cost_model: CostModel

    @property
    def live_constructor(self) -> bool:
        """Every plan is built by builders.build_strategy_plan (v136 rule 3).
        False only for the frozen v1 instrument."""
        return self.version != "v1"


V1_FILLS = FillModel(market_entry="signal_close", gap_through=False, same_bar="stop_first")
ZERO_COSTS = CostModel(commission_per_share=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)

_SPECS = {
    "v1": InstrumentSpec("v1", V1_FILLS, ZERO_COSTS),
    # Phase-1 stub: v1's fills and costs until phase 2 sets spec section 2's values.
    "v2": InstrumentSpec("v2", V1_FILLS, ZERO_COSTS),
}
VERSIONS = tuple(_SPECS)


def resolve(version: str) -> InstrumentSpec:
    """The InstrumentSpec for `version`; ValueError for an unknown one."""
    spec = _SPECS.get(version)
    if spec is None:
        raise ValueError(f"unknown instrument {version!r}; known: {', '.join(VERSIONS)}")
    return spec
```

- [ ] **Step 4: Run the tests and check complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py`
Expected: `7 passed`.
Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/contract.py`
Expected: no output (every function is below C).

- [ ] **Step 5: Commit.**

```bash
git -C $WT add swingbot/core/backtesting/instrument/__init__.py swingbot/core/backtesting/instrument/contract.py tests/backtesting/instrument/__init__.py tests/backtesting/instrument/test_contract.py
git -C $WT commit -m "feat(v137): instrument contract skeleton -- InstrumentSpec, resolve(v1|v2) (IC2)"
```

---

# Phase B: one constructor

### Task IC3: Thread the instrument through `run_backtest`; v2 builds through `build_strategy_plan`

**Files:**
- Modify: `swingbot/core/backtesting/backtest.py`: imports (top), new helpers placed after `_bt_plan` (currently ends at line 290), `run_backtest` (lines 293–549), `run_backtest_daterange` (lines 568–594)
- Create: `tests/backtesting/instrument/test_live_constructor_replay.py`

**Interfaces:**
- Consumes: `resolve`, `InstrumentSpec.live_constructor` (IC2); `render_v1_golden(**extra)`, `golden_text()` (IC1); `builders.build_strategy_plan(df, index, *, ticker, strategy, horizon_key, direction, ...)`; `backtest.simulate_exit` (module-level import from `planning/exit_sim.py`); `entry_context`, `asof_row` (already imported in `backtest.py`).
- Produces (IC4, IC6 and later phases rely on these):
  - `run_backtest(..., asof=None, instrument=None)` and `run_backtest_daterange(..., asof=None, instrument=None)`
  - `_live_plan_at(df, i, *, ticker, strategy, horizon_key, direction) -> TradePlanV2 | None`: the v2 replay's only constructor call
  - `_signal_masks(df, strategy, horizon_key) -> (bullish: pd.Series, bearish: pd.Series)`: `_vectorized_entries` plus the `ENTRY_SHIFT` roll
  - `_replay_live_constructor(ticker, df, strategy, horizon_key, *, one_at_a_time, scale_out, asof) -> (total_signals: int, trades: list[BacktestTrade], runner_counts: dict)`
  - `_summarize(ticker, strategy, horizon_key, total_signals, trades, runner_counts) -> BacktestSummary`
  - `_uses_live_constructor(instrument, exit_model, tp2_mode) -> bool`. Under v2 it raises `ValueError` when `exit_model != "v2"` (message contains `exit_model='v2'`) or `tp2_mode != "none"` (message contains `tp2_mode`). Through `_refuse_live_state_flags`, it also raises when any of `config.DATA_DRIVEN_STOPS_ENABLED`, `config.STALL_EXIT_ENABLED` or `config.OPEX_CAUTION_ENABLED` is on; that message contains `lookahead` and names each flag that is on.
  - `_LIVE_STATE_FLAGS = ("DATA_DRIVEN_STOPS_ENABLED", "STALL_EXIT_ENABLED", "OPEX_CAUTION_ENABLED")` and `_refuse_live_state_flags(instrument) -> None`. Phase 5 lifts this guard once the replay has its own simulated journal and session calendar.

- [ ] **Step 1: Write the failing tests**, `$WT/tests/backtesting/instrument/test_live_constructor_replay.py`:

```python
"""v137 IC3: under the v2 instrument run_backtest builds every plan through
builders.build_strategy_plan on the frame truncated at the signal bar; v1 is
unchanged (the golden)."""
import dataclasses

import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.planning import builders
from tests.backtesting.instrument.golden import golden_text, render_v1_golden
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import load_ohlcv

TICKER, STRATEGY, HORIZON = "DOCU", "RSI", "4w"
V2_EXIT = {"exit_model": "v2", "scale_out": True}


@pytest.fixture
def frame():
    return load_ohlcv(TICKER)


def _run(frame, **kwargs):
    return bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **kwargs)


def _forbidden(*_args, **_kwargs):
    raise AssertionError("the v2 instrument must never reach the v1 plan path")


def test_v2_refuses_the_frozen_v1_exit_loop(frame):
    with pytest.raises(ValueError, match="exit_model='v2'"):
        _run(frame, exit_model="v1", instrument=resolve("v2"))


def test_v2_refuses_the_v1_tp2_knob(frame):
    with pytest.raises(ValueError, match="tp2_mode"):
        _run(frame, exit_model="v2", tp2_mode="levels", instrument=resolve("v2"))


@pytest.mark.parametrize("flag", bt._LIVE_STATE_FLAGS)
def test_v2_refuses_a_flag_that_reads_live_state(monkeypatch, frame, flag):
    """DATA_DRIVEN_STOPS_ENABLED and STALL_EXIT_ENABLED make the builder read the
    live journal. OPEX_CAUTION_ENABLED makes it read today's opex tier from the
    wall clock. Either is lookahead inside a historical replay."""
    from swingbot import config
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, flag, True)
    with pytest.raises(ValueError, match=rf"lookahead.*{flag}"):
        _run(frame, **V2_EXIT, instrument=resolve("v2"))


def test_the_live_state_guard_names_the_real_config_flags():
    from swingbot import config
    names = {field.attr for field in config.FIELDS}
    assert set(bt._LIVE_STATE_FLAGS) <= names
    assert bt._LIVE_STATE_FLAGS == ("DATA_DRIVEN_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                                    "OPEX_CAUTION_ENABLED")


def test_v1_ignores_the_live_state_flags(monkeypatch, frame):
    """The guard applies only to v2. v1 never calls the builder, so the flags cannot reach it."""
    from swingbot import config
    pin_code_defaults(monkeypatch)
    for flag in bt._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, flag, True)
    _run(frame, **V2_EXIT, instrument=resolve("v1"))


def test_v2_builds_every_plan_on_the_frame_truncated_at_its_signal_bar(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    calls = []
    real = builders.build_strategy_plan

    def spy(df, index, **kwargs):
        calls.append((len(df), int(index)))
        return real(df, index, **kwargs)

    monkeypatch.setattr(builders, "build_strategy_plan", spy)
    monkeypatch.setattr(bt, "_trade_plan_at", _forbidden)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    assert summary.trades, "fixture case must trade under v2 or this proves nothing"
    assert calls and all(length == index + 1 for length, index in calls)
    assert len(calls) >= len(summary.trades)


def test_v2_trade_rows_carry_the_live_plans_levels(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    index_of = {str(day.date()): k for k, day in enumerate(frame.index)}
    assert summary.trades
    for trade in summary.trades:
        plan = bt._live_plan_at(frame, index_of[trade.entry_date], ticker=TICKER,
                                strategy=STRATEGY, horizon_key=HORIZON,
                                direction=trade.direction)
        assert (trade.entry, trade.stop_loss, trade.take_profit) == (
            round(plan.trigger_price, 4), round(plan.stop_loss, 4), round(plan.tp1, 4))


def test_v2_summary_is_built_by_the_shared_summariser(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    again = bt._summarize(TICKER, STRATEGY, HORIZON, summary.total_signals,
                          summary.trades, {"runner_tp2": summary.runner_tp2,
                                           "runner_trail": summary.runner_trail,
                                           "runner_be": summary.runner_be,
                                           "runner_timeout": summary.runner_timeout})
    # trades compared by identity: their context dicts can hold NaN, and NaN != NaN.
    assert again.trades is summary.trades
    assert dataclasses.replace(again, trades=[]) == dataclasses.replace(summary, trades=[])


def test_daterange_threads_the_instrument(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    seen = {}
    real = bt.run_backtest

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(bt, "run_backtest", spy)
    spec = resolve("v2")
    bt.run_backtest_daterange(TICKER, frame, STRATEGY, HORIZON, "2020-01-01", "2023-12-31",
                              **V2_EXIT, instrument=spec)
    assert seen["instrument"] is spec


@pytest.mark.slow
def test_explicit_v1_instrument_reproduces_the_golden(monkeypatch):
    pin_code_defaults(monkeypatch)
    assert render_v1_golden(instrument=resolve("v1")) == golden_text()
```

- [ ] **Step 2: Run them to verify they fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_live_constructor_replay.py`
Expected: FAIL at collection with `AttributeError: module 'swingbot.core.backtesting.backtest' has no attribute '_LIVE_STATE_FLAGS'` (the parametrize reads it).

- [ ] **Step 3: Add the type-only import.** In `$WT/swingbot/core/backtesting/backtest.py`, replace

```python
from dataclasses import dataclass, field

import numpy as np
```

with

```python
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
```

and directly after the `from swingbot.core.market.strategy_types import (  # noqa: F401 ... )` block (before `ENTRY_SHIFT = 0`) add

```python

if TYPE_CHECKING:
    from swingbot.core.backtesting.instrument.contract import InstrumentSpec
```

- [ ] **Step 4: Add the helpers.** Insert this block immediately after `_bt_plan` (after its closing `)` at line 290, before `def run_backtest(`):

```python
_NO_TRADE = ("not_triggered", "no_trade")


def _signal_masks(df, strategy, horizon_key):
    """(bullish, bearish) entry masks, rolled by ENTRY_SHIFT when the permutation
    test sets it -- extracted verbatim from run_backtest (v137)."""
    bullish, bearish = _vectorized_entries(df, strategy, horizon_key)
    if ENTRY_SHIFT:
        bullish = pd.Series(np.roll(bullish.values, ENTRY_SHIFT), index=df.index)
        bearish = pd.Series(np.roll(bearish.values, ENTRY_SHIFT), index=df.index)
    return bullish, bearish


# Builder resolvers that read LIVE state when their flag is on. Under
# DATA_DRIVEN_STOPS_ENABLED, params._resolve_stop_mult, _resolve_tp2_r and
# _resolve_time_stop_days read the journal. Under STALL_EXIT_ENABLED,
# params._resolve_stall_exit_day reads it too. Under OPEX_CAUTION_ENABLED,
# opex.stop_mult reads today's opex tier from the wall clock. Any of these is
# lookahead inside a historical replay. Spec phase 5 gives the replay its own
# simulated journal and session calendar, which lifts this guard.
_LIVE_STATE_FLAGS = ("DATA_DRIVEN_STOPS_ENABLED", "STALL_EXIT_ENABLED", "OPEX_CAUTION_ENABLED")


def _refuse_live_state_flags(instrument) -> None:
    """Fail fast when a v2 replay would read the live journal or the wall clock."""
    from swingbot import config
    on = [name for name in _LIVE_STATE_FLAGS if getattr(config, name, False)]
    if on:
        raise ValueError(f"instrument {instrument.version} replay refuses lookahead: "
                         f"{', '.join(on)} on would read the live journal / wall clock "
                         "inside a historical replay (lifted by v136 phase 5)")


def _uses_live_constructor(instrument, exit_model, tp2_mode) -> bool:
    """True under an instrument whose plans come from the live constructor (v2).
    There it refuses the two v1-only knobs: the frozen v1 exit loop, and
    tp2_mode, which the live path does not have (it builds TP2 with no
    level_map, so tp2_mode="levels" would make the replay plan differ from the
    plan live issues)."""
    if instrument is None or not instrument.live_constructor:
        return False
    if exit_model != "v2":
        raise ValueError(f"instrument {instrument.version} needs exit_model='v2'; "
                         "the v1 exit loop is frozen v1 code")
    if tp2_mode != "none":
        raise ValueError(f"instrument {instrument.version} builds TP2 exactly as live; "
                         f"tp2_mode={tp2_mode!r} is a v1 knob")
    _refuse_live_state_flags(instrument)
    return True


def _live_plan_at(df, i, *, ticker, strategy, horizon_key, direction):
    """The v2 instrument's only plan constructor (v136 rule 3): exactly the call
    scanning/strategy_pass.build_strategy_plan_at makes on a completed frame
    ending at bar i -- no level_map, no injected overrides -- so the backtest
    inherits every builder rule (data-driven stops, the stall-exit day, the
    reward floor, the plan shape). The builder's resolvers that depend on the
    journal or the clock are unreachable here: _refuse_live_state_flags refuses
    the run when any of their flags is on (spec phase 5's simulated journal lifts that)."""
    from swingbot.core.planning.builders import build_strategy_plan
    window = df.iloc[:i + 1]
    return build_strategy_plan(window, len(window) - 1, ticker=ticker, strategy=strategy,
                               horizon_key=horizon_key, direction=direction)


def _live_trade(df, i, plan, res, horizon_key, asof) -> BacktestTrade:
    """One v2-instrument trade row, in exactly the shape the v1 instrument's
    exit_model="v2" branch writes (planned entry; fills arrive in phase 2)."""
    entry, stop_loss, take_profit = plan.trigger_price, plan.stop_loss, plan.tp1
    risk_per_share = abs(entry - stop_loss)
    exit_i = res.exit_index
    return BacktestTrade(
        entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()),
        direction=plan.direction, entry=round(entry, 4), stop_loss=round(stop_loss, 4),
        take_profit=round(take_profit, 4), outcome=res.outcome,
        exit_price=round(res.legs[-1]["exit_price"], 4),
        return_pct=round(res.r_total * (risk_per_share / entry) * 100, 3),
        r_multiple=round(res.r_total, 3), holding_days=exit_i - i,
        runner_outcome=res.runner_outcome,
        context=entry_context(df.iloc[:i + 1], direction=plan.direction, horizon_key=horizon_key,
                              stop=stop_loss, target=take_profit,
                              asof=asof_row(asof, df.index[i]), entry=entry),
    )


def _replay_live_constructor(ticker, df, strategy, horizon_key, *, one_at_a_time, scale_out, asof):
    """The v2 instrument's replay: same signals, warm-up and one-at-a-time rule
    as the v1 loop, but every plan comes from _live_plan_at and every trade is
    walked by simulate_exit. Returns (total_signals, trades, runner_counts)."""
    bullish, bearish = _signal_masks(df, strategy, horizon_key)
    min_bars = MIN_BARS[horizon_key]
    trades, runner_counts, total_signals, open_until = [], {}, 0, -1
    for i in np.where(bullish.values | bearish.values)[0]:
        if i < min_bars:
            continue
        total_signals += 1
        if one_at_a_time and i <= open_until:
            continue
        direction = "bullish" if bullish.values[i] else "bearish"
        plan = _live_plan_at(df, i, ticker=ticker, strategy=strategy,
                             horizon_key=horizon_key, direction=direction)
        if plan is None:
            continue
        res = simulate_exit(df, i, plan, scale_out=scale_out)
        if res.outcome in _NO_TRADE:
            continue
        open_until = res.exit_index
        if res.runner_outcome:
            runner_counts[res.runner_outcome] = runner_counts.get(res.runner_outcome, 0) + 1
        trades.append(_live_trade(df, i, plan, res, horizon_key, asof))
    return total_signals, trades, runner_counts


def _outcome_buckets(trades):
    """(evaluated, wins, losses, scratches, timeouts): the four-outcome taxonomy
    in the module docstring; evaluated is win+loss only."""
    evaluated = [t for t in trades if t.outcome in ("win", "loss")]
    return (evaluated,
            [t for t in evaluated if t.outcome == "win"],
            [t for t in evaluated if t.outcome == "loss"],
            [t for t in trades if t.outcome == "scratch"],
            [t for t in trades if t.outcome == "timeout"])


def _mean_or_none(values):
    return float(np.mean(values)) if values else None


def _max_drawdown_pct(trades):
    """Peak-to-trough % of the sequentially compounded equity curve, or None."""
    if not trades:
        return None
    equity = [1.0]
    for t in trades:
        equity.append(equity[-1] * (1 + t.return_pct / 100))
    equity = np.array(equity)
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / running_max
    return float(drawdowns.min() * 100)


def _summarize(ticker, strategy, horizon_key, total_signals, trades, runner_counts):
    """The BacktestSummary for one run, shared by the v1 loop and the v2 replay
    (extracted verbatim from run_backtest, v137). win_rate is over win+loss;
    expectancy_r is over ALL closed trades -- the number gated on."""
    evaluated, wins, losses, scratches, timeouts = _outcome_buckets(trades)
    return BacktestSummary(
        ticker=ticker, strategy=strategy, horizon_key=horizon_key,
        total_signals=total_signals, evaluated=len(evaluated),
        wins=len(wins), losses=len(losses), timeouts=len(timeouts),
        scratches=len(scratches),
        win_rate=len(wins) / len(evaluated) * 100 if evaluated else None,
        avg_return_pct=_mean_or_none([t.return_pct for t in evaluated]),
        avg_r_multiple=_mean_or_none([t.r_multiple for t in evaluated]),
        expectancy_r=_mean_or_none([t.r_multiple for t in trades]),
        max_drawdown_pct=_max_drawdown_pct(trades),
        avg_holding_days=_mean_or_none([t.holding_days for t in evaluated]),
        trades=trades,
        runner_tp2=runner_counts.get("runner_tp2", 0),
        runner_trail=runner_counts.get("runner_trail", 0),
        runner_be=runner_counts.get("runner_be", 0),
        runner_timeout=runner_counts.get("runner_timeout", 0),
        avg_win_r=_mean_or_none([t.r_multiple for t in wins]),
    )
```

- [ ] **Step 5: Change `run_backtest`.** There are four exact edits; leave the v1 loop body alone otherwise.

(a) Signature: replace

```python
    frictions: bool = True,
    asof=None,
) -> BacktestSummary:
    """
    Run a backtest for one (ticker, strategy, horizon) combination.
```

with

```python
    frictions: bool = True,
    asof=None,
    instrument: "InstrumentSpec | None" = None,
) -> BacktestSummary:
    """
    Run a backtest for one (ticker, strategy, horizon) combination.
```

(b) Docstring: replace

```python
    ``asof`` is this ticker's per-date cross-sectional frame; without it the
    four cross-sectional context features are recorded as ``None``.
    """
    _refuse_compression(strategy)
    min_bars = MIN_BARS[horizon_key]
```

with

```python
    ``asof`` is this ticker's per-date cross-sectional frame; without it the
    four cross-sectional context features are recorded as ``None``.

    ``instrument`` (v136/v137) is the backtest contract from
    ``instrument.contract.resolve``. None is the v1 instrument: today's
    frozen behaviour, pinned byte for byte by
    tests/backtesting/instrument/test_v1_golden.py. Under v2 every plan is
    built by builders.build_strategy_plan on the frame truncated at its signal
    bar (``_live_plan_at``, the live scan's own call). v2 requires
    ``exit_model="v2"`` and ``tp2_mode="none"``. It refuses to run with
    DATA_DRIVEN_STOPS_ENABLED, STALL_EXIT_ENABLED or OPEX_CAUTION_ENABLED on,
    because the live journal or the wall clock is lookahead in a replay (phase 5
    lifts this). It ignores ``frictions``; costs arrive in v136 phase 2.
    """
    _refuse_compression(strategy)
    live = _uses_live_constructor(instrument, exit_model, tp2_mode)
    min_bars = MIN_BARS[horizon_key]
```

(c) Masks plus the v2 hand-off: replace

```python
    bullish_entries, bearish_entries = _vectorized_entries(df, strategy, horizon_key)
    if ENTRY_SHIFT:
        bullish_entries = pd.Series(np.roll(bullish_entries.values, ENTRY_SHIFT), index=df.index)
        bearish_entries = pd.Series(np.roll(bearish_entries.values, ENTRY_SHIFT), index=df.index)
    (atr_series, swing_high_series, swing_low_series,
```

with

```python
    if live:
        total_signals, trades, runner_counts = _replay_live_constructor(
            ticker, df, strategy, horizon_key, one_at_a_time=one_at_a_time,
            scale_out=scale_out, asof=asof)
        return _summarize(ticker, strategy, horizon_key, total_signals, trades, runner_counts)

    bullish_entries, bearish_entries = _signal_masks(df, strategy, horizon_key)
    (atr_series, swing_high_series, swing_low_series,
```

(d) Summary: replace everything from `    evaluated_trades = [t for t in trades if t.outcome in ("win", "loss")]` through the end of `run_backtest`'s final `return BacktestSummary(... avg_win_r=float(np.mean([t.r_multiple for t in wins])) if wins else None,\n    )`, which is currently lines 511–549, with:

```python
    return _summarize(ticker, strategy, horizon_key, total_signals, trades, runner_counts)
```

- [ ] **Step 6: Thread `run_backtest_daterange`.** Replace

```python
    tp2_mode: str = "none",
    asof=None,
) -> BacktestSummary:
    """
    Same as run_backtest() but only evaluates signals whose entry_date falls
```

with

```python
    tp2_mode: str = "none",
    asof=None,
    instrument: "InstrumentSpec | None" = None,
) -> BacktestSummary:
    """
    Same as run_backtest() but only evaluates signals whose entry_date falls
```

then replace

```python
    defaults match run_backtest's, so every existing caller is unaffected.
    """
    summary = run_backtest(ticker, df, strategy, horizon_key, frictions=frictions,
                             exit_model=exit_model, scale_out=scale_out,
                             tp2_mode=tp2_mode, asof=asof)
```

with

```python
    defaults match run_backtest's, so every existing caller is unaffected.
    ``instrument`` passes straight through (run_backtest's docstring).
    """
    summary = run_backtest(ticker, df, strategy, horizon_key, frictions=frictions,
                             exit_model=exit_model, scale_out=scale_out,
                             tp2_mode=tp2_mode, asof=asof, instrument=instrument)
```

- [ ] **Step 7: Run the new tests and the golden.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_live_constructor_replay.py`
Expected: `12 passed`: the original 7, plus 3 parametrised flag cases, the flag-name test and the v1-ignores test.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `2 passed`. A failure here means the extraction changed v1 output. Diff the extracted helper against the deleted lines and fix it; never regenerate the golden.

- [ ] **Step 8: Run the existing backtest neighbours.**

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed, 0 xfailed`. This selects `tests/backtesting/test_backtest_engine.py`, `test_exit_parity.py`, `test_backtest_context.py`, `test_backtest_provenance.py`, `arms/test_strategy_engine.py` and others that reach `backtest.py`.

- [ ] **Step 9: Complexity.**

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/backtest.py`
Expected: only `run_backtest` (it must report **less than 58**; the summary extraction lowers it), `run_backtest_daterange` (unchanged at 25) and `_trade_plan_at` (unchanged at 13). No new function may appear.

- [ ] **Step 10: Commit.**

```bash
git -C $WT add swingbot/core/backtesting/backtest.py tests/backtesting/instrument/test_live_constructor_replay.py
git -C $WT commit -m "feat(v137): run_backtest takes an instrument; v2 builds every plan through build_strategy_plan (IC3)"
```
