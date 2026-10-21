# v178 Runner give-back levels. Part 2: measurement script, full suite and merge, the runs with their gates (V178-5..V178-10; V178-11 is in part 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task V178-6:" -A 420 docs/superpowers/plans/2026-10-19-v178-runner-giveback-levels-preregistration_2-script-and-runs.md`.

**Spec:** [`docs/superpowers/specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md`](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md) (this part: § The test, stage by stage; § Ruling on the v92 overlap; § Phases; § Code facts)
**Index:** [`2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md`](2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, the row / funnel / blocks / simulator / script contracts, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration` (branch of the same name, created in V178-1). **Never `cd`**: use `git -C <tree>` and absolute paths. V178-5 and V178-6 run in `$WT` (file paths below are relative to it); V178-7 starts in `$WT` and ends on `main` in `$R`; V178-8..V178-11 run in `$R` on `main`. A long run started from a worktree (not planned, but if it happens) needs `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache` and `--earnings-dir E:/Documents/Private/Projects/Discord-Bot/market_data/earnings`.

**Consumed from part 1 (ledger names only):**
- `swingbot/core/planning/exit_sim.py` (V178-1): module constants `GIVEBACK_MODE` (`"pct"` default), `GIVEBACK_K`, `GIVEBACK_F`, `GIVEBACK_FLOOR_ATR` (1.0); `giveback_allowance(mode, extreme, entry, atr, *, k, f) -> float | None` (None when ATR is NaN, zero, negative, infinite or missing); the v1 walk reads `GIVEBACK_MODE/K/F` at call time and labels a carried adaptive level `"giveback"`. Existing `runner_floor`, `_scale_out_exit_walk(..., trace=)`, `_hold_cap_bars`, `HORIZONS`, `GIVEBACK_EXTREME_BASIS`.
- `swingbot/core/backtesting/giveback_levels_funnel.py` (V178-3): `PCT`, `ARMS`, `CONTROLS`, `CANDIDATES`, `FAMILIES`, `pooled_window()`, `fold_train_windows()`, `fold_test_windows()`, `arm_trades`, `changed_count`, `paired_delta`, `week_interval`, `stage0`, `stage2`, `run_funnel`, `cells_looked_at`.
- `swingbot/core/backtesting/giveback_levels_blocks.py` (V178-4): `SHAKEOUT_BARS`, `TR_SHOCK_ATR`, `ADX_TREND_MIN`, `describe_arm`, `seven_blocks`, `per_horizon`, `concentration`, `regime_split`, `flips`.

**Stop gates in this part (frozen now, before any window is read):**
- After V178-8: every candidate refused at stage −1 (zero changed outcomes on the pilot) ends the test: skip to V178-11, verdict `UNMEASURABLE`.
- After V178-9: every candidate refused at stage 0 ends the test as a **finished result** (the spec's base case): no sensitivity run, no VALIDATION, skip to V178-11, verdict `NO-LIFT`. Stage 1 or stage 2 closing everything ends it the same way.
- V178-10 runs **only if exactly one arm** (`summary.stage3_arm`) survived stages 0–2, and only after the partner says go through `AskUserQuestion`. VALIDATION is read once, never for the high/low sensitivity.

---

# Phase 3: Measurement script (in the worktree)

### Task V178-5: Measurement script: arms, entries, rows

**Model:** opus — the paired instrument itself (one entry set, eight arms, frictions, frame cut before VALIDATION, row fields the funnel gates on); a silent pairing or lookahead slip here fakes every later reading.

**Files:**
- Create: `scripts/backtest/measure_giveback_levels.py`
- Create: `tests/backtest_scripts/test_measure_giveback_levels.py` (suite `backtest-scripts` = `tests/backtest_scripts/`; no manifest edit)

**Interfaces:**
- Consumes: V178-1 `exit_sim.GIVEBACK_MODE/GIVEBACK_K/GIVEBACK_F/GIVEBACK_FLOOR_ATR`, `exit_sim.giveback_allowance(mode, extreme, entry, atr, *, k, f)`; V178-3 `funnel.ARMS`, `funnel.PCT`, `funnel.CANDIDATES`; V178-4 `blocks.SHAKEOUT_BARS`, `blocks.TR_SHOCK_ATR`, `blocks.ADX_TREND_MIN`; existing `simulate_exit`, `exit_sim._scale_out_exit_walk(..., trace=)`, `exit_sim._hold_cap_bars`, `exit_sim.HORIZONS`, `exit_sim.runner_floor`, `net_r`, `acceptance.CLOSED`, `acceptance.planned_rr`, `arms.windows.STAGES`, `indicators.atr`, `indicators.adx`, `earnings_calendar.CsvSource/reaction_session/EARNINGS_CSV_DIR`, `SessionCalendar.from_bar_index`, `training_data`, `instrument_cli`.
- Produces (V178-6 and the runs consume):
  - `arm_settings(arm: str)` — context manager: sets `config.RUNNER_GIVEBACK_ENABLED`, `config.RUNNER_GIVEBACK_PCT = PCT`, `exit_sim.GIVEBACK_MODE/K/F` from `ARMS[arm]`; restores every value after. Unknown arm → `KeyError`.
  - `stage_window(stage: str) -> tuple[str, str]` — `pilot` and `validation` from `STAGES`; `train` = (`STAGES["selection"]` start, `STAGES["walkforward"]` end). `frame_end(stage: str) -> str` — walkforward end for `pilot`/`train`, validation end for `validation`.
  - `entry_row(ticker, df, entry, *, arms, series) -> dict | None` — one row of the index's row contract (None unless control A and every arm closed the trade).
  - `rows_for(ticker, df, *, stage, basis, arms=ARM_IDS, earnings_dir=EARNINGS_CSV_DIR) -> list[dict]`; `build_rows(stage, basis, *, arms=ARM_IDS, tickers=None, workers=None, earnings_dir=EARNINGS_CSV_DIR) -> list[dict]` (ticker order).
  - `write_rows(path, rows) -> Path` (gzipped JSON, atomic), `read_rows(path) -> list[dict]`.
  - `build_parser()`, `parse_args(argv)` (instrument arg + `require_v1`), constants `DATA_SOURCE`, `BASES`, `STAGE_NAMES`, `ROW_STAGES`, `ARM_IDS`, `RESULTS`, `ROWS_DIR`; module aliases `funnel`, `blocks` (tests monkeypatch through them).

**Design (frozen; spec § The test, § Code facts):**
- The entry set comes from **one control-A pass** per ticker (`_entries`, under `arm_settings("A")`), and every entry is re-simulated under every arm through the same `simulate_exit(scale_out=True)` call, so the pairing is exact and the pre-TP1 path identical across arms.
- Frames are cut at `frame_end(stage)` before anything runs: pilot and train never touch a bar on or after `windows.VALIDATION_START`.
- `r_net` is net of frictions (`net_r`), so ΔExpR is a net figure. Rows are kept only when control A's outcome is in `acceptance.CLOSED` and every arm closed.
- Runner extras are measured on each arm's own exit: `tp1_index` (first bar after entry touching TP1), `best`/`best_index` (best close over `[tp1_index, exit_index − 1]`), `allowance_pct` at bar `exit_index − 1` (A: 0.05; B: None; R/S: `giveback_allowance(...) / best`, with ATR(14) at that bar; on the `high_low` basis `best` stays the best close, a descriptive simplification), `floor_bound` (S arms only), `stop_moves` from the v1 walk's `trace` (None if the traced walk does not reproduce the result), `gap_r` and `new_best_within_10` on runner stop exits, `shock` (an earnings reaction bar, or a bar whose true range exceeds `TR_SHOCK_ATR` × the previous bar's ATR(14), inside `[tp1_index, exit_index]`). `regime` reads ADX(14) at the signal bar.
- Duplicate pairing keys inside one ticker get `#2`, `#3`, ... on `strategy`, so `ArmTrade` keys stay unique (`arms.pairing.index_by_key` raises otherwise).
- No date or year literal anywhere in the script (`tests/backtesting/instrument/test_date_literal_guard.py`); the parser is built here so the guard's `add_instrument_arg` + `require_v1` requirement holds from this task on.

- [ ] **Step 1: Write the failing test**

Create `tests/backtest_scripts/test_measure_giveback_levels.py`:

```python
"""v178 measurement script: arms, entries, rows (V178-5) and stages (V178-6).

Frame: v176's run-up-and-reversal (tests/planning/test_exit_sim_giveback.py),
entry 100 at bar 0's close, stop 95, TP1 110 touched on bar 1, bar 2 closes
at the best 120, bar 3 trades down to 113, bar 4 to 106. The chandelier is
parked (trail_atr_mult 50). ATR(14) is pinned flat by monkeypatching
indicators.atr (exit_sim imports it at call time), so every level is
hand-derived: R k -> 120 - 2k, S f -> 120 - max(20 f, 2).
"""
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.arms.windows import STAGES, VALIDATION_START
from swingbot.core.market import indicators
from swingbot.core.planning import exit_sim
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import measure_giveback_levels as mgl  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
        (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
ROW_KEYS = {"ticker", "source", "strategy", "horizon_key", "direction", "signal_date",
            "planned_rr", "risk", "runner_fraction", "regime", "arms"}
ARM_KEYS = {"outcome", "r_net", "runner_r", "entry_index", "exit_index", "exit_date",
            "exit_price", "reason", "stop_source", "tp1_index", "best", "best_index",
            "allowance_pct", "floor_bound", "stop_moves", "gap_r", "new_best_within_10", "shock"}


def _flat(value):
    return lambda df, period=14: pd.Series(value, index=df.index, dtype=float)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)
    monkeypatch.setattr(indicators, "adx", _flat(float("nan")))


@pytest.fixture
def flat_atr(monkeypatch):
    monkeypatch.setattr(indicators, "atr", _flat(2.0))


def _one_entry(monkeypatch, plan=None, *, copies=1, seen=None):
    plan = plan or _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None,
                         trail_atr_mult=50.0)

    def fake_entries(ticker, df, window):
        if seen is not None:
            seen.append((df, window))
        return [("strategy", "2w", 0, plan)] * copies
    monkeypatch.setattr(mgl, "_entries", fake_entries)


def _rows(tmp_path, **kw):
    return mgl.rows_for("AAA", make_ohlcv(BARS, start="2021-01-04"), stage="train",
                        basis="close", earnings_dir=tmp_path, **kw)


def test_arm_settings_sets_each_arm_and_restores():
    with mgl.arm_settings("R0.75"):
        assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_K) == ("range", 0.75)
        assert config.RUNNER_GIVEBACK_ENABLED is True
    with mgl.arm_settings("S0.50"):
        assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_F) == ("profit_share", 0.50)
    with mgl.arm_settings("B"):
        assert config.RUNNER_GIVEBACK_ENABLED is False
    assert (exit_sim.GIVEBACK_MODE, exit_sim.GIVEBACK_K, exit_sim.GIVEBACK_F) == ("pct", 1.0, 0.33)
    assert config.RUNNER_GIVEBACK_ENABLED is True and config.RUNNER_GIVEBACK_PCT == 5.0
    with pytest.raises(KeyError):
        with mgl.arm_settings("R0.50"):
            pass


def test_windows_come_from_the_arms_stage_table():
    assert mgl.stage_window("pilot") == tuple(STAGES["pilot"].signal_window)
    assert mgl.stage_window("train") == (STAGES["selection"].signal_window[0],
                                         STAGES["walkforward"].signal_window[1])
    assert mgl.stage_window("validation") == tuple(STAGES["validation"].signal_window)
    assert mgl.frame_end("pilot") == mgl.frame_end("train") == STAGES["walkforward"].signal_window[1]
    assert mgl.frame_end("train") < VALIDATION_START
    assert mgl.frame_end("validation") == STAGES["validation"].signal_window[1]
    with pytest.raises(ValueError):
        mgl.stage_window("report")


@pytest.mark.parametrize("arm, exit_index, exit_price, source", [
    ("A", 3, 114.0, "giveback"),        # 5% of 120
    ("B", 4, FLOOR, "floor"),           # give-back off: the floor
    ("R0.75", 3, 118.5, "giveback"),    # 120 - 0.75 x 2
    ("R1.00", 3, 118.0, "giveback"),
    ("R1.25", 3, 117.5, "giveback"),
    ("S0.25", 3, 115.0, "giveback"),    # 120 - max(5.0, 2)
    ("S0.33", 3, 113.4, "giveback"),    # 120 - max(6.6, 2); bar 3's low 113 reaches it
    ("S0.50", 4, 110.0, "giveback"),    # 120 - max(10, 2); carried to bar 4
])
def test_every_arm_exits_at_its_hand_derived_level(monkeypatch, tmp_path, flat_atr,
                                                   arm, exit_index, exit_price, source):
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    result = row["arms"][arm]
    assert result["exit_index"] == exit_index
    assert result["exit_price"] == pytest.approx(exit_price)
    assert result["stop_source"] == source
    assert result["outcome"] == "win"


def test_rows_carry_the_contract_fields(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    assert set(row) == ROW_KEYS and set(row["arms"]) == set(mgl.ARM_IDS)
    assert all(set(result) == ARM_KEYS for result in row["arms"].values())
    assert (row["source"], row["strategy"], row["horizon_key"]) == ("strategy", "Fibonacci", "2w")
    assert row["signal_date"] == "2021-01-04" and row["regime"] is None
    assert row["risk"] == pytest.approx(5.0) and row["runner_fraction"] == pytest.approx(0.5)
    assert row["planned_rr"] == pytest.approx(2.0)
    a = row["arms"]["A"]
    assert (a["tp1_index"], a["best"], a["best_index"]) == (1, 120.0, 2)
    assert a["allowance_pct"] == pytest.approx(0.05) and a["floor_bound"] is None
    assert a["stop_moves"] == 1 and a["gap_r"] == 0.0           # bar 3 opened at 120 > 114
    assert a["new_best_within_10"] is False                     # 106.5 after the exit
    assert a["shock"] is True                                   # bar 1 TR 11.5 > 2 x ATR 2.0
    assert row["arms"]["B"]["allowance_pct"] is None and row["arms"]["B"]["stop_moves"] == 0
    assert row["arms"]["R1.00"]["allowance_pct"] == pytest.approx(2.0 / 120.0)
    assert row["arms"]["S0.25"]["allowance_pct"] == pytest.approx(5.0 / 120.0)
    assert row["arms"]["S0.25"]["floor_bound"] is False
    # net of 5 bps per fill: the entry fill 100.05 re-bases risk to 5.05; leg 1 cancels
    assert a["r_net"] - row["arms"]["B"]["r_net"] == pytest.approx(
        0.5 * (114.0 - FLOOR) * 0.9995 / 5.05)
    assert config.RUNNER_GIVEBACK_ENABLED is True and exit_sim.GIVEBACK_MODE == "pct"


def test_the_floor_binds_on_a_wide_atr(monkeypatch, tmp_path):
    monkeypatch.setattr(indicators, "atr", _flat(10.0))
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    s = row["arms"]["S0.25"]                                    # max(5, 10) = 10 -> 110
    assert s["exit_price"] == pytest.approx(110.0) and s["floor_bound"] is True


def test_no_atr_means_no_term_so_an_adaptive_arm_rides_like_control_b(monkeypatch, tmp_path):
    _one_entry(monkeypatch)                                     # 5 bars: ATR(14) is NaN
    [row] = _rows(tmp_path)
    for arm in ("R1.00", "S0.33"):
        assert row["arms"][arm]["exit_index"] == row["arms"]["B"]["exit_index"] == 4
        assert row["arms"][arm]["exit_price"] == pytest.approx(FLOOR)
        assert row["arms"][arm]["allowance_pct"] is None


@pytest.mark.parametrize("adx, expected", [(25.0, "trend"), (20.0, "trend"), (15.0, "chop")])
def test_regime_reads_adx_at_the_signal_bar(monkeypatch, tmp_path, flat_atr, adx, expected):
    monkeypatch.setattr(indicators, "adx", _flat(adx))
    _one_entry(monkeypatch)
    [row] = _rows(tmp_path)
    assert row["regime"] == expected


def test_shock_reads_earnings_bars_and_true_range_against_the_previous_atr():
    calm = {"reactions": [], "atr": np.array([2.0] * 6), "tr": np.array([1.0] * 6)}
    assert mgl.shock(calm, 1, 4) is False
    assert mgl.shock(dict(calm, reactions=[3]), 1, 4) is True
    assert mgl.shock(dict(calm, reactions=[5]), 1, 4) is False   # after the exit bar
    spike = dict(calm, tr=np.array([1.0, 1.0, 4.5, 1.0, 1.0, 1.0]))
    assert mgl.shock(spike, 1, 4) is True                         # 4.5 > 2.0 x 2.0


@pytest.mark.parametrize("timing, expected", [("before_open", [1]), ("after_close", [2])])
def test_reaction_indices_map_reports_to_frame_bars(tmp_path, timing, expected):
    (tmp_path / "AAA.csv").write_text(
        f"report_date,timing,report_ts_et\n2021-01-05,{timing},\n", encoding="utf-8")
    df = make_ohlcv(BARS, start="2021-01-04")
    assert mgl.reaction_indices("AAA", df, tmp_path) == expected


def test_an_entry_control_a_never_filled_is_dropped(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch, _plan(entry_type="stop_entry", trigger_price=200.0, stop_loss=95.0,
                                  tp1=110.0, tp2=None, trail_atr_mult=50.0))
    assert _rows(tmp_path) == []


def test_duplicate_pairing_keys_get_a_suffix(monkeypatch, tmp_path, flat_atr):
    _one_entry(monkeypatch, copies=3)
    rows = _rows(tmp_path)
    assert [r["strategy"] for r in rows] == ["Fibonacci", "Fibonacci#2", "Fibonacci#3"]


def test_no_bar_on_or_after_validation_start_reaches_a_train_row(monkeypatch, tmp_path):
    seen = []
    _one_entry(monkeypatch, seen=seen)
    mgl.rows_for("AAA", make_ohlcv(BARS * 3, start="2023-12-20"), stage="train",
                 basis="close", earnings_dir=tmp_path)
    df, window = seen[0]
    assert str(df.index[-1].date()) <= mgl.frame_end("train") < VALIDATION_START
    assert window == mgl.stage_window("train")


def test_rows_refuse_an_unknown_basis_and_arms_without_control_a(tmp_path):
    df = make_ohlcv(BARS, start="2021-01-04")
    with pytest.raises(ValueError, match="basis"):
        mgl.rows_for("AAA", df, stage="train", basis="open", earnings_dir=tmp_path)
    with pytest.raises(ValueError, match="control A"):
        mgl.rows_for("AAA", df, stage="train", basis="close", arms=("B", "R1.00"),
                     earnings_dir=tmp_path)


def test_rows_round_trip_gzipped(tmp_path):
    rows = [{"ticker": "AAA", "arms": {"A": {"r_net": 1.25}}}]
    path = mgl.write_rows(tmp_path / "sub" / "rows-train-close.json.gz", rows)
    assert mgl.read_rows(path) == rows
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == rows
    assert not list(path.parent.glob("*.tmp"))


def test_parse_args_refuses_instrument_v2():
    with pytest.raises(SystemExit, match="not wired"):
        mgl.parse_args(["--stage", "pilot", "--instrument", "v2"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_giveback_levels.py`
Expected: collection error, `ModuleNotFoundError: No module named 'measure_giveback_levels'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/backtest/measure_giveback_levels.py`:

```python
#!/usr/bin/env python3
"""v178: pre-registered paired test of runner give-back levels (range-multiple and profit-share arms).

Frozen before any window is read (spec 2026-10-19-v178, § The test):
  arms       A = live 5% of the best close; B = give-back off;
             R k in {0.75, 1.0, 1.25}: best -/+ k x ATR14;
             S f in {0.25, 0.33, 0.50}: best -/+ max(f x profit, 1.0 x ATR14)
  entries    ONE control-A pass per ticker; each entry re-simulated under every arm
  windows    arms.windows.STAGES: pilot; train = selection start .. walkforward end
             (every frame cut at the walkforward end, so no VALIDATION bar is run);
             validation = the one shot, for the single stage-3 arm
  data       the 75-ticker yfinance cache; StrategyEngine.iter_trades +
             replay_scenarios, all ten horizons; simulate_exit(scale_out=True), v1
  frictions  net_r: SLIPPAGE_BPS on both fills + commission_r(); zero refused

One look: every output is refused if it exists. Read through the funnel in
giveback_levels_funnel; it never changes the live rule.
PROGRESS: a flushed line per ticker plus logs/measure_giveback_levels.<stage>-<basis>.progress.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import gzip
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.analytics.expectancy_attribution import net_r  # noqa: E402
from swingbot.core.backtesting import giveback_levels_blocks as blocks  # noqa: E402
from swingbot.core.backtesting import giveback_levels_funnel as funnel  # noqa: E402
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, CLOSED,  # noqa: E402
                                                  planned_rr)
from swingbot.core.backtesting.arms.windows import STAGES, universe_for  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.market import indicators  # noqa: E402
from swingbot.core.market.earnings_calendar import (EARNINGS_CSV_DIR, CsvSource,  # noqa: E402
                                                    reaction_session)
from swingbot.core.market.session import SessionCalendar  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.planning import exit_sim  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

DATA_SOURCE = "yfinance"
BASES = ("close", "high_low")
STAGE_NAMES = ("pilot", "train", "report", "validation")
ROW_STAGES = ("pilot", "train", "validation")
ARM_IDS = tuple(funnel.ARMS)
RESULTS = ROOT / "docs" / "superpowers" / "results" / "v178"
ROWS_DIR = ROOT / "logs" / "v178"
LOG_DIR = ROOT / "logs"
_MODULE_KNOBS = ("GIVEBACK_MODE", "GIVEBACK_K", "GIVEBACK_F")
_RUNNER_KEYS = ("tp1_index", "best", "best_index", "allowance_pct", "floor_bound",
                "stop_moves", "gap_r", "new_best_within_10", "shock")


@contextlib.contextmanager
def arm_settings(arm: str):
    """One arm's give-back for the simulations inside the block; every value comes back after."""
    spec = funnel.ARMS[arm]
    saved_cfg = (config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT)
    saved_mod = {name: getattr(exit_sim, name) for name in _MODULE_KNOBS}
    config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = spec["enabled"], funnel.PCT
    exit_sim.GIVEBACK_MODE = spec["mode"]
    exit_sim.GIVEBACK_K = spec.get("k", saved_mod["GIVEBACK_K"])
    exit_sim.GIVEBACK_F = spec.get("f", saved_mod["GIVEBACK_F"])
    try:
        yield spec
    finally:
        config.RUNNER_GIVEBACK_ENABLED, config.RUNNER_GIVEBACK_PCT = saved_cfg
        for name, value in saved_mod.items():
            setattr(exit_sim, name, value)


def stage_window(stage: str) -> tuple[str, str]:
    """Signal window of a row stage, from arms.windows.STAGES (never a literal)."""
    if stage == "train":
        return STAGES["selection"].signal_window[0], STAGES["walkforward"].signal_window[1]
    if stage in ("pilot", "validation"):
        return tuple(STAGES[stage].signal_window)
    raise ValueError(f"no signal window for stage {stage!r}; expected one of {ROW_STAGES}")


def frame_end(stage: str) -> str:
    """Last bar any simulation of ``stage`` may read."""
    stage_window(stage)
    return STAGES["validation" if stage == "validation" else "walkforward"].signal_window[1]


def _entries(ticker, df, window) -> list:
    """(source, horizon_key, signal_index, plan) for every entry of the control-A
    pass whose signal date falls inside ``window``."""
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.scan_params import ScanParams
    params, engine, out = ScanParams.from_config(), StrategyEngine(), []
    position = {str(ts.date()): i for i, ts in enumerate(df.index)}
    with arm_settings("A"):
        for hk in ALL_HORIZONS:
            for strategy in engine.strategies:
                for date, plan, _result in engine.iter_trades(ticker, df, strategy, hk, window, params):
                    out.append(("strategy", hk, position[date], plan))
            for index, plan in replay_scenarios(ticker, df, hk, params=params):
                if window[0] <= str(df.index[index].date()) <= window[1]:
                    out.append(("scenario", hk, index, plan))
    return out


# --- per-ticker series -------------------------------------------------------

def reaction_indices(ticker, df, earnings_dir) -> list[int]:
    """Frame positions of earnings reaction sessions (ETFs have none)."""
    from swingbot.core.marketdata.universe import is_etf
    if is_etf(ticker):
        return []
    calendar = SessionCalendar.from_bar_index(df.index)
    out = set()
    for report in CsvSource(earnings_dir).reports(ticker):
        session = reaction_session(report, calendar)
        position = None if session is None else calendar.position_on_or_after(session)
        if position is not None:
            out.add(position)
    return sorted(out)


def ticker_series(ticker, df, earnings_dir) -> dict:
    """ATR(14), ADX(14), true range and earnings reaction bars of one frame."""
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()],
                   axis=1).max(axis=1)
    return {"atr": indicators.atr(df, 14).to_numpy(dtype=float),
            "adx": indicators.adx(df, 14).to_numpy(dtype=float),
            "tr": tr.to_numpy(dtype=float),
            "reactions": reaction_indices(ticker, df, earnings_dir)}


def regime(series, index) -> str | None:
    value = float(series["adx"][index])
    if not np.isfinite(value):
        return None
    return "trend" if value >= blocks.ADX_TREND_MIN else "chop"


def shock(series, lo, hi) -> bool:
    """An earnings reaction bar, or true range above TR_SHOCK_ATR x the previous bar's
    ATR(14), anywhere in [lo, hi]."""
    if any(lo <= p <= hi for p in series["reactions"]):
        return True
    atr, tr = series["atr"], series["tr"]
    return bool(any(j >= 1 and np.isfinite(atr[j - 1]) and tr[j] > blocks.TR_SHOCK_ATR * atr[j - 1]
                    for j in range(lo, hi + 1)))


# --- one entry under every arm ---------------------------------------------

def _is_runner(result) -> bool:
    return result.outcome == "win" and len(result.legs) == 2


def _stop_moves(df, plan, result) -> int | None:
    """Changes of the runner stop, from the v1 walk's trace; None when the traced
    walk does not reproduce the result (an entry form the plain walk does not take)."""
    hold = exit_sim._hold_cap_bars(plan, exit_sim.HORIZONS[plan.horizon_key]["max_holding_days"])
    trace = []
    again = exit_sim._scale_out_exit_walk(df, result.entry_index, result.entry_price,
                                          copy.deepcopy(plan), hold, trace=trace)
    if (again.exit_index, again.legs) != (result.exit_index, result.legs):
        return None
    stops = [exit_sim.runner_floor(result.entry_price, plan.tp1)] + [stop for _, stop in trace]
    return sum(1 for a, b in zip(stops, stops[1:]) if a != b)


def _simulate(df, index, plan, arm):
    with arm_settings(arm):
        result = simulate_exit(df, index, copy.deepcopy(plan), scale_out=True)
        moves = _stop_moves(df, plan, result) if _is_runner(result) else None
    return result, moves


def _base_result(df, plan, result) -> dict:
    return {"outcome": result.outcome,
            "r_net": net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs),
            "runner_r": float(result.legs[1]["r"]) if _is_runner(result) else None,
            "entry_index": int(result.entry_index), "exit_index": int(result.exit_index),
            "exit_date": str(df.index[result.exit_index].date()),
            "exit_price": float(result.legs[-1]["exit_price"]),
            "reason": result.runner_outcome or result.outcome,
            "stop_source": result.runner_stop_source}


def tp1_bar(df, plan, entry_index, exit_index) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(entry_index + 1, exit_index + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return exit_index


def best_close(df, lo, hi, is_bull) -> tuple[float, int]:
    """Best close over [lo, hi - 1] (just bar lo when hi <= lo) and its bar."""
    closes = df["Close"].values[lo:max(hi, lo + 1)]
    k = int(np.argmax(closes) if is_bull else np.argmin(closes))
    return float(closes[k]), lo + k


def allowance_share(arm, best, entry, atr) -> tuple[float | None, bool | None]:
    """(allowance / best, floor binds) at the bar before the exit."""
    spec = funnel.ARMS[arm]
    if not spec["enabled"]:
        return None, None
    if spec["mode"] == "pct":
        return funnel.PCT / 100.0, None
    allowance = exit_sim.giveback_allowance(spec["mode"], best, entry, atr,
                                            k=spec.get("k", exit_sim.GIVEBACK_K),
                                            f=spec.get("f", exit_sim.GIVEBACK_F))
    if allowance is None or best == 0:
        return None, None
    floor = None
    if spec["mode"] == "profit_share":
        floor = bool(spec["f"] * abs(best - entry) < exit_sim.GIVEBACK_FLOOR_ATR * atr)
    return allowance / best, floor


def _gap_r(df, base, sign, risk, fraction) -> float | None:
    if base["stop_source"] is None:
        return None
    gap = (float(df["Open"].values[base["exit_index"]]) - base["exit_price"]) * sign / risk
    return min(0.0, gap) * fraction


def _new_best_after(df, base, best, sign) -> bool | None:
    if base["stop_source"] is None:
        return None
    j = base["exit_index"]
    later = df["Close"].values[j + 1:j + 1 + blocks.SHAKEOUT_BARS]
    return bool(any((float(c) - best) * sign > 0 for c in later))


def runner_fields(df, plan, base, moves, arm, series, risk, entry) -> dict:
    if base["runner_r"] is None:
        return dict.fromkeys(_RUNNER_KEYS)
    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    tp1 = tp1_bar(df, plan, base["entry_index"], base["exit_index"])
    best, best_index = best_close(df, tp1, base["exit_index"], is_bull)
    share, floor = allowance_share(arm, best, entry,
                                   float(series["atr"][max(base["exit_index"] - 1, tp1)]))
    return {"tp1_index": tp1, "best": best, "best_index": best_index,
            "allowance_pct": share, "floor_bound": floor, "stop_moves": moves,
            "gap_r": _gap_r(df, base, sign, risk, 1.0 - plan.tp1_fraction),
            "new_best_within_10": _new_best_after(df, base, best, sign),
            "shock": shock(series, tp1, base["exit_index"])}


def _closed(result) -> bool:
    return result.outcome in CLOSED and bool(result.legs)


def entry_row(ticker, df, entry, *, arms, series) -> dict | None:
    """One entry simulated under every arm; None unless control A (and every arm) closed it."""
    source, hk, index, plan = entry
    results = {arm: _simulate(df, index, plan, arm) for arm in arms}
    if not all(_closed(result) for result, _ in results.values()):
        return None
    control = results["A"][0]
    risk = abs(control.entry_price - plan.stop_loss)
    row = {"ticker": ticker, "source": source, "strategy": plan.strategy, "horizon_key": hk,
           "direction": plan.direction, "signal_date": str(df.index[index].date()),
           "planned_rr": planned_rr(control.entry_price, plan.stop_loss, plan.tp1),
           "risk": risk, "runner_fraction": 1.0 - plan.tp1_fraction,
           "regime": regime(series, index), "arms": {}}
    for arm, (result, moves) in results.items():
        base = _base_result(df, plan, result)
        base.update(runner_fields(df, plan, base, moves, arm, series, risk,
                                  float(result.entry_price)))
        row["arms"][arm] = base
    return row


def _unique_keys(rows) -> list[dict]:
    """Suffix repeated (ticker, strategy, horizon, date, source, direction) keys."""
    seen = Counter()
    for row in rows:
        key = (row["ticker"], row["strategy"], row["horizon_key"], row["signal_date"],
               row["source"], row["direction"])
        seen[key] += 1
        if seen[key] > 1:
            row["strategy"] = f"{row['strategy']}#{seen[key]}"
    return rows


def rows_for(ticker, df, *, stage, basis, arms=ARM_IDS, earnings_dir=EARNINGS_CSV_DIR) -> list[dict]:
    """Every ``stage`` entry of ``ticker`` under ``arms``, on a frame cut at frame_end(stage)."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}, got {basis!r}")
    if "A" not in arms:
        raise ValueError("arms must include control A (the pairing baseline)")
    exit_sim.GIVEBACK_EXTREME_BASIS = basis
    df = df.loc[:frame_end(stage)]
    series = ticker_series(ticker, df, earnings_dir)
    rows = (entry_row(ticker, df, entry, arms=arms, series=series)
            for entry in _entries(ticker, df, stage_window(stage)))
    return _unique_keys([row for row in rows if row is not None])


# --- run ---------------------------------------------------------------------

def _init_worker(basis) -> None:
    training_data.select(DATA_SOURCE)
    exit_sim.GIVEBACK_EXTREME_BASIS = basis


def _ticker_rows(task):
    ticker, stage, basis, arms, earnings_dir = task
    df = training_data.load_daily(ticker)
    return ticker, ([] if df is None else rows_for(ticker, df, stage=stage, basis=basis,
                                                     arms=arms, earnings_dir=Path(earnings_dir)))


def _universe(stage, tickers) -> list[str]:
    if tickers:
        return list(tickers)
    return universe_for("pilot" if stage == "pilot" else "validation",
                        training_data.available_tickers())


def build_rows(stage, basis, *, arms=ARM_IDS, tickers=None, workers=None,
               earnings_dir=EARNINGS_CSV_DIR) -> list[dict]:
    """Every universe ticker's rows, in ticker order whatever order the pool finishes in."""
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    universe = _universe(stage, tickers)
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_giveback_levels.{stage}-{basis}.progress"
    by_ticker = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        done = len(by_ticker)
        print(f"  [{stage}/{basis}] {done}/{len(universe)} {ticker}: {len(rows)} rows", flush=True)
        progress.write_text(f"{done}/{len(universe)} tickers ({done / len(universe) * 100:.0f}%)\n",
                            encoding="utf-8")

    tasks = [(t, stage, basis, tuple(arms), str(earnings_dir)) for t in universe]
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(universe) <= 1:
        _init_worker(basis)
        for task in tasks:
            record(*_ticker_rows(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker,
                                 initargs=(basis,)) as pool:
            for future in as_completed([pool.submit(_ticker_rows, task) for task in tasks]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


def write_rows(path, rows) -> Path:
    """Gzipped JSON, written to a temporary file then renamed (no half-written rows file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(rows, handle)
    temporary.replace(path)
    return path


def read_rows(path) -> list[dict]:
    with gzip.open(Path(path), "rt", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage", required=True, choices=STAGE_NAMES)
    parser.add_argument("--basis", choices=BASES, default="close")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--rows-dir", type=Path, default=ROWS_DIR)
    parser.add_argument("--tickers", nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--earnings-dir", type=Path, default=EARNINGS_CSV_DIR)
    parser.add_argument("--arm", choices=funnel.CANDIDATES, default=None)
    parser.add_argument("--preregistration", type=Path, default=None)
    instrument_cli.add_instrument_arg(parser)
    return parser


def parse_args(argv=None) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_giveback_levels.py",
                              "a later spec (v178 is frozen on instrument v1)")
    return args
```

- [ ] **Step 4: Run the tests to verify they pass, plus the date-literal guard and the complexity gate**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_giveback_levels.py`
Expected: all pass.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`
Expected: pass (no date or year literal; `add_instrument_arg` and `require_v1`/`spec_from_args` are called).
Run: `python $WT/scripts/dev/complexity_gate.py`
Expected: no new offender (every function above is below 15).

If a hand-derived exit level fails, read the part-1 walk (`git -C $WT grep -n "_giveback_term\|_carried_level" -- swingbot/core/planning/exit_sim.py`) before changing anything: the levels in the test follow the spec's arithmetic, so a mismatch is a part-1 defect to report to the controller, not a test to re-pin.

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/backtest/measure_giveback_levels.py tests/backtest_scripts/test_measure_giveback_levels.py
git -C $WT commit -m "feat(v178): measurement script rows -- one control-A entry pass, eight arms, net R

Each entry re-simulated under A, B, R x3, S x3 with frictions; frames cut before
VALIDATION; runner extras (allowance share, stop moves, gap, shake-out, shock)
for the descriptive blocks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V178-6: Measurement script: stages, refusals, report, validation file

**Model:** opus — the one-look and stage-order guards are what keep VALIDATION unread and the sensitivity off after a stage-0 refusal; a wrong guard spends the one shot.

**Files:**
- Modify: `scripts/backtest/measure_giveback_levels.py` (created in V178-5)
- Modify: `tests/backtest_scripts/test_measure_giveback_levels.py` (created in V178-5)

**Interfaces:**
- Consumes: V178-5 `build_rows`, `write_rows`, `read_rows`, `stage_window`, `frame_end`, `parse_args`, `ARM_IDS`, `RESULTS`, `ROWS_DIR`, `ROW_STAGES`, `DATA_SOURCE`; V178-3 `funnel.run_funnel(rows, *, n_resamples)`, `stage0(rows, arm, *, n_resamples)`, `stage2(rows, arm)`, `changed_count`, `paired_delta(rows, arm, *, against, n_resamples)`, `week_interval(rows, arm, *, against, n_resamples)`, `arm_trades`, `cells_looked_at(..., sensitivity=)`, `pooled_window()`, `fold_train_windows()`, `fold_test_windows()`, `FAMILIES`, `CANDIDATES`; V178-4 `blocks.describe_arm`, `seven_blocks`, `per_horizon`, `concentration`, `regime_split`, `flips`; existing `acceptance_harvest.permutation_p_expectancy(baseline, component, *, n_perm=200, seed=42)`, `arms.provenance.code_hash()`, `validate_component.load_arms`.
- Produces (V178-8..V178-10 run it): the index's CLI and output files; `main(argv) -> int`; `_refusal(args, target) -> str | None`; `cmd_pilot`, `cmd_train`, `cmd_report`, `cmd_validation`; `validation_arms_blob(rows, arm) -> dict`; `BESPOKE_REASON: str`; helpers `family_best`, `best_arm`, `regime_arms_for`, `sensitivity_arms`.

**Stage order and refusals (frozen):**
- Every run refuses zero frictions, a `--tickers` smoke run into the committed `--out-dir`/`--rows-dir`, and any output that already exists (`refused:one-look`).
- `pilot`, `train`, `validation` refuse an earnings directory without CSVs (block 7 needs it). `pilot` and `validation` run on the close basis only.
- `train` and `report` need `pilot-close.json` with at least one survivor; `report` needs its rows file.
- `--basis high_low` (train or report) needs `funnel-close.json` with at least one stage-0 `RESOLVABLE` arm: **every arm refused at stage 0 ends the test, and the sensitivity is not run**.
- `validation` needs `--arm` equal to `funnel-close.json`'s `stage3_arm` and an existing `--preregistration` file; it simulates A, B and that arm only, on the VALIDATION window, and writes `logs/v178/validation-arms.json` for `validate_component.py --stage validation --gate harvest --bespoke-instrument`. The partner's go is asked in V178-10 before the command is run.
- `report --basis close` describes all six candidates (blocks never gate), with the trend/chop split only for each family's best arm and the stage-3 arm (`regime_arms_for`); `report --basis high_low` reads only `sensitivity_arms` (R0.75, each family's best, the stage-3 arm), TRAIN side.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_measure_giveback_levels.py`:

```python
# --- V178-6: stages, refusals, report, validation file ----------------------

DELTAS = (0.001, 0.004, 0.002, -0.001, 0.003, 0.0)          # R0.75 .. S0.50


def _arm(r, *, moved=False):
    return {"outcome": "win", "r_net": r, "runner_r": r, "entry_index": 0,
            "exit_index": 6 if moved else 5, "exit_date": "2019-03-08",
            "exit_price": 1.5 if moved else 1.0, "reason": "runner_trail",
            "stop_source": "giveback", "tp1_index": 1, "best": 2.0, "best_index": 2,
            "allowance_pct": 0.05, "floor_bound": None, "stop_moves": 1, "gap_r": 0.0,
            "new_best_within_10": False, "shock": False}


def _row(ticker, *, moved=(), lift=0.0, arms=None):
    return {"ticker": ticker, "source": "strategy", "strategy": "Fibonacci", "horizon_key": "2w",
            "direction": "bullish", "signal_date": "2019-03-01", "planned_rr": 2.0, "risk": 5.0,
            "runner_fraction": 0.5, "regime": "trend",
            "arms": {a: _arm(1.0 + (lift if a in moved else 0.0), moved=a in moved)
                     for a in (arms or mgl.ARM_IDS)}}


def _funnel(*, resolvable=(), stage3=None):
    stage0 = {a: {"delta_r": d, "p": 0.3, "n": 10, "changed": 3,
                  "verdict": "RESOLVABLE" if a in resolvable else "REFUSED"}
              for a, d in zip(mgl.funnel.CANDIDATES, DELTAS)}
    return {"stage0": stage0, "stage1": {}, "stage2": {}, "stage3_arm": stage3,
            "stopped_at": None if stage3 else "stage0",
            "holm": dict.fromkeys(mgl.funnel.CANDIDATES, 1.0), "week_interval": {}}


def _put(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    out, rows, earnings = tmp_path / "out", tmp_path / "rows", tmp_path / "earnings"
    earnings.mkdir()
    (earnings / "AAA.csv").write_text("report_date,timing,report_ts_et\n", encoding="utf-8")
    monkeypatch.setattr(mgl.training_data, "select", lambda name=None: name)
    monkeypatch.setattr(mgl.training_data, "write_provenance", lambda path: path)
    return out, rows, earnings


def _main(dirs, *argv):
    out, rows, earnings = dirs
    return mgl.main([*argv, "--out-dir", str(out), "--rows-dir", str(rows),
                     "--earnings-dir", str(earnings)])


def _pilot(dirs, survivors=mgl.funnel.CANDIDATES):
    _put(dirs[0] / "pilot-close.json", {"survivors": list(survivors)})


def test_main_refuses_zero_frictions(dirs, monkeypatch, capsys):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 0.0)
    assert _main(dirs, "--stage", "pilot") == 1
    assert "refused:zero-frictions" in capsys.readouterr().err


def test_main_refuses_a_smoke_run_into_the_committed_directories(capsys):
    assert mgl.main(["--stage", "pilot", "--tickers", "AAA"]) == 1
    assert "refused:smoke-run" in capsys.readouterr().err


def test_main_refuses_an_empty_earnings_directory(tmp_path, capsys):
    assert mgl.main(["--stage", "pilot", "--out-dir", str(tmp_path / "o"), "--rows-dir",
                     str(tmp_path / "r"), "--earnings-dir", str(tmp_path)]) == 1
    assert "refused:no-earnings" in capsys.readouterr().err


def test_pilot_reports_reachability_per_candidate_and_is_one_look(dirs, monkeypatch, capsys):
    rows = [_row(t, moved=("R0.75",), lift=0.1) for t in "ABC"]
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: rows)
    assert _main(dirs, "--stage", "pilot") == 0
    blob = json.loads((dirs[0] / "pilot-close.json").read_text(encoding="utf-8"))
    assert blob["arms"]["R0.75"] == {"changed": 3, "verdict": "REACHABLE"}
    assert blob["arms"]["S0.50"] == {"changed": 0, "verdict": "refused:zero-diff"}
    assert blob["survivors"] == ["R0.75"] and blob["frozen"]["window"] == list(mgl.stage_window("pilot"))
    assert mgl.read_rows(dirs[1] / "rows-pilot-close.json.gz") == rows
    assert _main(dirs, "--stage", "pilot") == 1
    assert "refused:one-look" in capsys.readouterr().err


def test_a_pilot_without_changed_outcomes_closes_every_candidate(dirs, monkeypatch):
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: [_row("A")])
    assert _main(dirs, "--stage", "pilot") == 1
    assert json.loads((dirs[0] / "pilot-close.json").read_text(encoding="utf-8"))["survivors"] == []


def test_train_needs_a_pilot_survivor(dirs, capsys):
    assert _main(dirs, "--stage", "train") == 1
    assert "refused:no-pilot" in capsys.readouterr().err
    _pilot(dirs, survivors=())
    assert _main(dirs, "--stage", "train") == 1
    assert "refused:pilot-closed-everything" in capsys.readouterr().err


def test_train_writes_the_rows_file_and_nothing_else(dirs, monkeypatch):
    seen, rows = [], [_row("A")]
    monkeypatch.setattr(mgl, "build_rows", lambda stage, basis, **kw: seen.append((stage, basis)) or rows)
    _pilot(dirs)
    assert _main(dirs, "--stage", "train") == 0
    assert seen == [("train", "close")]
    assert mgl.read_rows(dirs[1] / "rows-train-close.json.gz") == rows
    assert not (dirs[0] / "funnel-close.json").exists()


@pytest.mark.parametrize("stage", ["train", "report"])
def test_high_low_is_refused_when_every_arm_was_refused_at_stage_0(dirs, capsys, stage):
    _pilot(dirs)
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel()})
    mgl.write_rows(dirs[1] / "rows-train-high_low.json.gz", [_row("A")])
    assert _main(dirs, "--stage", stage, "--basis", "high_low") == 1
    assert "refused:no-sensitivity" in capsys.readouterr().err


def test_report_close_runs_the_funnel_and_describes_every_candidate(dirs, monkeypatch):
    _pilot(dirs)
    mgl.write_rows(dirs[1] / "rows-train-close.json.gz", [_row("A")])
    monkeypatch.setattr(mgl.funnel, "run_funnel", lambda rows, n_resamples: _funnel())
    monkeypatch.setattr(mgl.blocks, "describe_arm",
                        lambda rows, arm, risk_dollars: {"1_book": arm, "regime": "dropped"})
    monkeypatch.setattr(mgl.blocks, "regime_split", lambda rows, arm: f"regime-{arm}")
    assert _main(dirs, "--stage", "report", "--resamples", "50") == 0
    blob = json.loads((dirs[0] / "funnel-close.json").read_text(encoding="utf-8"))
    assert list(blob["blocks"]) == list(mgl.funnel.CANDIDATES)
    assert blob["regime_arms"] == ["R1.00", "S0.33"]              # each family's best stage-0 delta
    assert "regime" not in blob["blocks"]["R0.75"]
    assert blob["blocks"]["R1.00"]["regime"] == "regime-R1.00"
    summary = blob["summary"]
    assert (summary["best_arm"], summary["ledger_p"], summary["stopped_at"]) == ("R1.00", 0.3, "stage0")
    assert summary["cells_looked_at"] == mgl.funnel.cells_looked_at()


def test_report_drops_a_stage3_arm_the_pilot_refused(dirs, monkeypatch):
    _pilot(dirs, survivors=("R0.75", "S0.33"))
    mgl.write_rows(dirs[1] / "rows-train-close.json.gz", [_row("A")])
    monkeypatch.setattr(mgl.funnel, "run_funnel", lambda rows, n_resamples: _funnel(stage3="R1.00"))
    monkeypatch.setattr(mgl.blocks, "describe_arm", lambda rows, arm, risk_dollars: {})
    monkeypatch.setattr(mgl.blocks, "regime_split", lambda rows, arm: {})
    assert _main(dirs, "--stage", "report") == 0
    blob = json.loads((dirs[0] / "funnel-close.json").read_text(encoding="utf-8"))
    assert blob["funnel"]["stage3_arm"] is None and "R1.00" in blob["funnel"]["pilot_refused"]


def test_report_high_low_reads_only_the_sensitivity_arms(dirs, monkeypatch):
    _pilot(dirs)
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(resolvable=("R1.00",))})
    mgl.write_rows(dirs[1] / "rows-train-high_low.json.gz", [_row("A")])
    seen = []
    monkeypatch.setattr(mgl.funnel, "stage0", lambda rows, arm, n_resamples: seen.append(arm) or {})
    monkeypatch.setattr(mgl.funnel, "stage2", lambda rows, arm: {})
    assert _main(dirs, "--stage", "report", "--basis", "high_low") == 0
    blob = json.loads((dirs[0] / "sensitivity-high_low.json").read_text(encoding="utf-8"))
    assert seen == blob["summary"]["arms"] == ["R0.75", "R1.00", "S0.33"]
    assert blob["summary"]["cells_looked_at"] == mgl.funnel.cells_looked_at(sensitivity=18)


def test_validation_refuses_anything_but_the_stage3_arm_with_a_preregistration(dirs, tmp_path, capsys):
    assert _main(dirs, "--stage", "validation") == 1
    assert "refused:no-arm" in capsys.readouterr().err
    assert _main(dirs, "--stage", "validation", "--arm", "R1.00") == 1
    assert "refused:no-preregistration" in capsys.readouterr().err
    spec = tmp_path / "spec.md"
    spec.write_text("frozen", encoding="utf-8")
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(stage3="R1.00")})
    assert _main(dirs, "--stage", "validation", "--arm", "S0.33", "--preregistration", str(spec)) == 1
    assert "refused:not-the-stage3-arm" in capsys.readouterr().err


def test_validation_writes_the_component_file_and_the_fixed_readings(dirs, tmp_path, monkeypatch, capsys):
    import validate_component
    spec = tmp_path / "spec.md"
    spec.write_text("frozen", encoding="utf-8")
    _put(dirs[0] / "funnel-close.json", {"funnel": _funnel(stage3="R1.00")})
    rows = [_row(t, moved=("R1.00",), lift=0.1, arms=("A", "B", "R1.00")) for t in "ABCDEF"]
    seen = []
    monkeypatch.setattr(mgl, "build_rows",
                        lambda stage, basis, arms, **kw: seen.append((stage, arms)) or rows)
    for name in ("seven_blocks", "per_horizon", "concentration", "regime_split", "flips"):
        monkeypatch.setattr(mgl.blocks, name, lambda *a, **k: {})
    argv = ("--stage", "validation", "--arm", "R1.00", "--preregistration", str(spec),
            "--resamples", "50")
    assert _main(dirs, *argv) == 0
    assert seen == [("validation", ("A", "B", "R1.00"))]
    baseline, component = validate_component.load_arms(dirs[1] / "validation-arms.json")
    assert len(baseline) == len(component) == 6
    assert component[0].r_multiple == pytest.approx(1.1)
    blob = json.loads((dirs[1] / "validation-arms.json").read_text(encoding="utf-8"))
    assert blob["provenance"]["bespoke"] == mgl.BESPOKE_REASON
    readings = json.loads((dirs[0] / "validation-readings.json").read_text(encoding="utf-8"))
    assert {"arm_vs_a", "a_vs_b", "arm_vs_b", "week_interval", "permutation_p"} <= set(readings)
    assert readings["changed"] == 6 and readings["frozen"]["window"] == list(mgl.stage_window("validation"))
    assert _main(dirs, *argv) == 1
    assert "refused:one-look" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_giveback_levels.py`
Expected: the V178-5 tests pass; the new ones fail with `AttributeError: module 'measure_giveback_levels' has no attribute 'main'` (and `BESPOKE_REASON`).

- [ ] **Step 3: Write the implementation**

In `scripts/backtest/measure_giveback_levels.py`, add `import dataclasses` to the standard-library imports and, after the `acceptance` import, `from swingbot.core.backtesting.acceptance_harvest import permutation_p_expectancy  # noqa: E402`. Then append below `parse_args`:

```python
# --- stages ------------------------------------------------------------------

BESPOKE_REASON = ("v178 bespoke producer (measure_giveback_levels.py): the give-back modes are "
                  "simulator-only module constants, not searchable knobs, so measure_arms.py "
                  "cannot produce them; one control-A entry pass re-simulated per arm, R net "
                  "of frictions")
V92_OVERLAP = ("family R is adjacent to the closed v92 adaptive trail (nearest cell trigger_r 2.50, "
               "mult 1.50; dExpR -0.0045R to +0.0091R across its grid, best-cell lower bound "
               "-0.0131R): context, never a threshold; the partner ruled this a new test")
UNIVERSE_LIMIT = "75 liquid cached names: the result says nothing about thin names, where ATR is noisy"


def _frozen(stage, basis) -> dict:
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    return {"stage": stage, "window": list(stage_window(stage)), "frame_end": frame_end(stage),
            "basis": basis, "data_source": DATA_SOURCE, "arms": funnel.ARMS,
            "pooled_fold_train": list(funnel.pooled_window()),
            "fold_train": [[label, list(w)] for label, w in funnel.fold_train_windows()],
            "fold_test": [[label, list(w)] for label, w in funnel.fold_test_windows()],
            "entries": "one control-A pass per ticker; every entry re-simulated under each arm",
            "scale_out": True, "instrument": "v1",
            "engines": ["StrategyEngine.iter_trades", "replay_scenarios"],
            "horizons": list(ALL_HORIZONS), "slippage_bps": float(config.SLIPPAGE_BPS),
            "commission_per_side": float(config.COMMISSION_PER_TRADE),
            "commission_risk_basis": float(config.COMMISSION_RISK_BASIS),
            "v92_overlap": V92_OVERLAP, "universe_limit": UNIVERSE_LIMIT}


def _rows_path(args, stage) -> Path:
    return args.rows_dir / f"rows-{stage}-{args.basis if stage == 'train' else 'close'}.json.gz"


def _primary_target(args) -> Path:
    names = {"pilot": "pilot-close.json", "validation": "validation-readings.json",
             "report": "funnel-close.json" if args.basis == "close" else "sensitivity-high_low.json"}
    return _rows_path(args, "train") if args.stage == "train" else args.out_dir / names[args.stage]


def _secondary_targets(args) -> list[Path]:
    return {"pilot": [_rows_path(args, "pilot")],
            "validation": [_rows_path(args, "validation"), args.rows_dir / "validation-arms.json"],
            }.get(args.stage, [])


def _read_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_json(path, blob) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    training_data.write_provenance(path)
    return path


# --- refusals -----------------------------------------------------------------

def _refusal(args, target) -> str | None:
    if float(config.SLIPPAGE_BPS) <= 0 or float(config.COMMISSION_PER_TRADE) <= 0:
        return "refused:zero-frictions -- the spec needs non-zero frictions in every arm"
    if args.tickers and (args.out_dir.resolve() == RESULTS.resolve()
                         or args.rows_dir.resolve() == ROWS_DIR.resolve()):
        return "refused:smoke-run -- --tickers needs a scratch --out-dir and --rows-dir"
    for path in [target, *_secondary_targets(args)]:
        if path.exists():
            return f"refused:one-look -- {path} exists; every output of this measurement is one look"
    return _stage_refusal(args)


def _any_resolvable(out_dir) -> bool:
    blob = _read_json(Path(out_dir) / "funnel-close.json") or {}
    stage0 = blob.get("funnel", {}).get("stage0", {})
    return any(reading.get("verdict") == "RESOLVABLE" for reading in stage0.values())


def _stage_refusal(args) -> str | None:
    if args.stage in ROW_STAGES and not any(Path(args.earnings_dir).glob("*.csv")):
        return (f"refused:no-earnings -- no earnings CSVs in {args.earnings_dir}; "
                "pass --earnings-dir <main tree>/market_data/earnings")
    if args.stage in ("pilot", "validation") and args.basis != "close":
        return f"refused:basis -- --stage {args.stage} runs on the close basis only"
    if args.basis == "high_low" and not _any_resolvable(args.out_dir):
        return ("refused:no-sensitivity -- every arm was refused at stage 0 (or funnel-close.json "
                "is missing): the test ended there and the sensitivity is not run")
    checks = {"train": _train_refusal, "report": _report_refusal, "validation": _validation_refusal}
    return checks[args.stage](args) if args.stage in checks else None


def _train_refusal(args) -> str | None:
    pilot = _read_json(args.out_dir / "pilot-close.json")
    if pilot is None:
        return "refused:no-pilot -- run --stage pilot first (stage -1)"
    if not pilot["survivors"]:
        return "refused:pilot-closed-everything -- every candidate was refused at stage -1"
    return None


def _report_refusal(args) -> str | None:
    if not _rows_path(args, "train").exists():
        return f"refused:no-rows -- {_rows_path(args, 'train')} is missing; run --stage train first"
    return _train_refusal(args)


def _validation_refusal(args) -> str | None:
    if args.arm is None:
        return "refused:no-arm -- --stage validation needs --arm <the stage-3 arm>"
    if args.preregistration is None or not Path(args.preregistration).exists():
        return "refused:no-preregistration -- the one shot needs --preregistration <committed spec>"
    stage3 = (_read_json(args.out_dir / "funnel-close.json") or {}).get("funnel", {}).get("stage3_arm")
    if stage3 != args.arm:
        return f"refused:not-the-stage3-arm -- funnel-close.json names {stage3!r}, not {args.arm!r}"
    return None


# --- pilot and train ------------------------------------------------------------

def _pilot_verdict(rows, arm) -> dict:
    changed = funnel.changed_count(rows, arm)
    return {"changed": changed, "verdict": "REACHABLE" if changed > 0 else "refused:zero-diff"}


def cmd_pilot(args) -> int:
    """Stage -1: each candidate's knob is read (arm_settings sets it) and changes outcomes."""
    rows = build_rows("pilot", "close", tickers=args.tickers, workers=args.workers,
                      earnings_dir=args.earnings_dir)
    arms = {arm: _pilot_verdict(rows, arm) for arm in funnel.CANDIDATES}
    survivors = [arm for arm, reading in arms.items() if reading["verdict"] == "REACHABLE"]
    write_rows(_rows_path(args, "pilot"), rows)
    blob = {"frozen": _frozen("pilot", "close"), "n": len(rows), "arms": arms,
            "control_b_changed": funnel.changed_count(rows, "B"), "survivors": survivors}
    path = _write_json(_primary_target(args), blob)
    print(json.dumps(arms, indent=1), f"\n-> {path}", flush=True)
    return 0 if survivors else 1


def cmd_train(args) -> int:
    """Rows only: no ΔExpR is computed or printed until --stage report."""
    rows = build_rows("train", args.basis, tickers=args.tickers, workers=args.workers,
                      earnings_dir=args.earnings_dir)
    path = write_rows(_rows_path(args, "train"), rows)
    training_data.write_provenance(path)
    print(f"{len(rows)} rows -> {path}", flush=True)
    return 0


# --- report -----------------------------------------------------------------------

def family_best(result, family) -> str | None:
    """The family's stage-1 adopted arm, else its best pooled fold-train ΔExpR."""
    adopted = ((result.get("stage1") or {}).get(family) or {}).get("adopted")
    if adopted:
        return adopted
    scored = [(result["stage0"][arm]["delta_r"], arm) for arm in funnel.FAMILIES[family]
              if (result["stage0"].get(arm) or {}).get("delta_r") is not None]
    return max(scored)[1] if scored else None


def best_arm(result) -> str | None:
    scored = [(reading["delta_r"], arm) for arm, reading in result["stage0"].items()
              if reading.get("delta_r") is not None]
    return max(scored)[1] if scored else None


def regime_arms_for(result) -> list[str]:
    picks = (family_best(result, "R"), family_best(result, "S"), result.get("stage3_arm"))
    return list(dict.fromkeys(arm for arm in picks if arm))


def sensitivity_arms(result) -> list[str]:
    return list(dict.fromkeys(("R0.75", *regime_arms_for(result))))


def _apply_pilot(result, pilot) -> dict:
    refused = [arm for arm in funnel.CANDIDATES if arm not in pilot["survivors"]]
    stage3 = None if result.get("stage3_arm") in refused else result.get("stage3_arm")
    return {**result, "stage3_arm": stage3, "pilot_refused": refused}


def _described(rows, arm, risk, with_regime) -> dict:
    out = {key: value for key, value in blocks.describe_arm(rows, arm, risk_dollars=risk).items()
           if key != "regime"}
    if with_regime:
        out["regime"] = blocks.regime_split(rows, arm)
    return out


def _report_close(rows, args) -> dict:
    result = _apply_pilot(funnel.run_funnel(rows, n_resamples=args.resamples),
                          _read_json(args.out_dir / "pilot-close.json"))
    regime_arms = regime_arms_for(result)
    risk = float(config.COMMISSION_RISK_BASIS)
    best = best_arm(result)
    return {"frozen": _frozen("train", "close"), "funnel": result, "regime_arms": regime_arms,
            "blocks": {arm: _described(rows, arm, risk, arm in regime_arms)
                       for arm in funnel.CANDIDATES},
            "summary": {"n": len(rows), "stopped_at": result["stopped_at"],
                        "stage3_arm": result["stage3_arm"], "best_arm": best,
                        "ledger_p": result["stage0"][best]["p"] if best else None,
                        "holm": result["holm"], "cells_looked_at": funnel.cells_looked_at()}}


def _report_high_low(rows, args) -> dict:
    close = _read_json(args.out_dir / "funnel-close.json")["funnel"]
    arms = sensitivity_arms(close)
    readings = {arm: {"stage0": funnel.stage0(rows, arm, n_resamples=args.resamples),
                      "stage2": funnel.stage2(rows, arm),
                      "close_stage0_delta_r": close["stage0"][arm]["delta_r"]} for arm in arms}
    return {"frozen": _frozen("train", "high_low"), "readings": readings,
            "summary": {"n": len(rows), "arms": arms,
                        "cells_looked_at": funnel.cells_looked_at(sensitivity=6 * len(arms))}}


def cmd_report(args) -> int:
    rows = read_rows(_rows_path(args, "train"))
    blob = (_report_close if args.basis == "close" else _report_high_low)(rows, args)
    path = _write_json(_primary_target(args), blob)
    print(json.dumps(blob["summary"], indent=1, default=str), f"\n-> {path}", flush=True)
    return 0


# --- validation (the one shot) ----------------------------------------------------

def validation_arms_blob(rows, arm) -> dict:
    """validate_component.py arms file: baseline = control A, component = the stage-3 arm."""
    from swingbot.core.backtesting.arms.provenance import code_hash
    return {"provenance": {"producer": "measure_giveback_levels.py", "stage": "validation",
                           "signal_window": list(stage_window("validation")), "arm": arm,
                           "arm_spec": funnel.ARMS[arm], "baseline_arm": "A",
                           "data_source": DATA_SOURCE, "instrument": "v1",
                           "code_hash": code_hash(), "bespoke": BESPOKE_REASON},
            "baseline": [dataclasses.asdict(t) for t in funnel.arm_trades(rows, "A")],
            "component": [dataclasses.asdict(t) for t in funnel.arm_trades(rows, arm)]}


def validation_readings(rows, arm, *, n_resamples) -> dict:
    """The spec's fixed stage-3 readings beside the gate: arm-vs-A, A-vs-B, arm-vs-B."""
    risk = float(config.COMMISSION_RISK_BASIS)
    return {"arm": arm, "n": len(rows), "changed": funnel.changed_count(rows, arm),
            "arm_vs_a": funnel.paired_delta(rows, arm, n_resamples=n_resamples),
            "a_vs_b": funnel.paired_delta(rows, "A", against="B", n_resamples=n_resamples),
            "arm_vs_b": funnel.paired_delta(rows, arm, against="B", n_resamples=n_resamples),
            "week_interval": funnel.week_interval(rows, arm, n_resamples=n_resamples),
            "permutation_p": permutation_p_expectancy(funnel.arm_trades(rows, "A"),
                                                      funnel.arm_trades(rows, arm),
                                                      n_perm=200, seed=42),
            "blocks": blocks.seven_blocks(rows, arm, risk_dollars=risk),
            "per_horizon": blocks.per_horizon(rows, arm),
            "concentration": blocks.concentration(rows, arm),
            "regime": blocks.regime_split(rows, arm), "flips": blocks.flips(rows, arm)}


def cmd_validation(args) -> int:
    rows = build_rows("validation", "close", arms=("A", "B", args.arm), tickers=args.tickers,
                      workers=args.workers, earnings_dir=args.earnings_dir)
    write_rows(_rows_path(args, "validation"), rows)
    arms_file = _write_json(args.rows_dir / "validation-arms.json",
                            validation_arms_blob(rows, args.arm))
    readings = {"frozen": _frozen("validation", "close"),
                "preregistration": str(args.preregistration),
                **validation_readings(rows, args.arm, n_resamples=args.resamples)}
    path = _write_json(_primary_target(args), readings)
    print(f"permutation_p={readings['permutation_p']}\n-> {path}\n-> {arms_file}", flush=True)
    return 0


COMMANDS = {"pilot": cmd_pilot, "train": cmd_train, "report": cmd_report,
            "validation": cmd_validation}


def main(argv=None) -> int:
    args = parse_args(argv)
    refusal = _refusal(args, _primary_target(args))
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    training_data.select(DATA_SOURCE)
    return COMMANDS[args.stage](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass, plus the guards**

Run: `python $WT/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_giveback_levels.py`
Expected: all pass.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py`
Expected: pass (the new strings carry no bare date or year literal).
Run: `python $WT/scripts/dev/complexity_gate.py`
Expected: no new offender.
Smoke (scratch dirs, two tickers, close basis; proves the pool path end to end, reads only the pilot window):
`BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache python $WT/scripts/backtest/measure_giveback_levels.py --stage pilot --tickers AAPL MSFT --workers 1 --out-dir $SCRATCH/v178-smoke --rows-dir $SCRATCH/v178-smoke-rows --earnings-dir E:/Documents/Private/Projects/Discord-Bot/market_data/earnings`
Expected: per-ticker progress lines, a JSON of six `arms` readings, `-> .../pilot-close.json`; exit 0 or 1. Delete `$SCRATCH/v178-smoke*` afterwards; nothing is committed from it.

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/backtest/measure_giveback_levels.py tests/backtest_scripts/test_measure_giveback_levels.py
git -C $WT commit -m "feat(v178): measurement script stages -- pilot, train, report, the one-shot validation file

One look on every output; high/low sensitivity refused after an all-stage-0
refusal; validation only for the funnel's stage-3 arm with a preregistration,
written in validate_component's arms format (--bespoke-instrument).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


# Phase 4: Full suite, merge, bump

### Task V178-7: Full suite, merge, bot patch bump

**Model:** sonnet — mechanical gate and merge, but a concurrent session on `main` or a missed regeneration turns it into a red `main`.

**Files:**
- Modify: `VERSION.json` (the `bot` line and `bot_updated` only)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: the branch `2026-10-19-v178-runner-giveback-levels-preregistration` with V178-1..V178-6 committed.
- Produces: the merged script `scripts/backtest/measure_giveback_levels.py` and both modules on `main`, which V178-8..V178-10 run from `$R`.

- [ ] **Step 1: Sync the local database replica**

Run `/replicate-prod-db` (the full suite touches the database). Expected: row counts verified.

- [ ] **Step 2: Run the plan's single full suite in the worktree**

Dispatch `test-runner` with: `python $WT/scripts/dev/testrun.py full` (cwd `$WT`).
Expected: `0 failed`, `0 xfailed`; the complexity gate prints no new offender. A failure is fixed on the branch and re-run alone (`testrun.py file <test>`), never by a second full run. A changed pass count is not a failure (`docs/claude/testing-cost.md`).

- [ ] **Step 3: Check for concurrent work, then merge to `main`**

Follow the `worktree-lifecycle` skill. `git -C $R status --short` must show no tracked change that touches a file in the ledger; `git -C $R log --oneline -5` names who moved `main` since V178-1. Anything unexpected: stop and ask the partner via `AskUserQuestion` (recommended option first: "wait for the other session").

```bash
git -C $R merge --no-ff 2026-10-19-v178-runner-giveback-levels-preregistration -m "merge(v178): adaptive give-back simulator modes, funnel, blocks, measurement script

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python $R/scripts/dev/testrun.py file tests/backtest_scripts/test_measure_giveback_levels.py
```
Expected: merge clean; the narrow run passes on `main`. No full suite after the merge (it ran in Step 2).

- [ ] **Step 4: Bump, then regenerate (two commits, in that order)**

Read `$R/VERSION.json` from disk; increment the **patch** part of `bot` only (e.g. `2.12.0` → `2.12.1` if that is what is on disk), set `bot_updated` to the current UTC time in `YYYY-MM-DD HH-MM-SS`; leave `ui` and `ui_updated` untouched.

```bash
git -C $R add VERSION.json
git -C $R commit -m "release(bot): <new version> -- simulator-only adaptive runner give-back modes (v178, inert by default)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
python $R/scripts/dev/build_version_matrix.py
python $R/scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C $R add swingbot/admin/version_history.json
git -C $R commit -m "chore(bot): <new version> -- simulator-only adaptive runner give-back modes (v178, inert by default)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Expected: the matrix test passes after the regeneration. The worktree stays until `/close-out` (V178-11). Nothing is deployed: the live bot does not read the new constants.

# Phase 5: The runs (on `main`, in `$R`)

`$DOC` = `docs/superpowers/results/2026-10-19-v178-giveback-levels.md` (the record, created in V178-8, appended in V178-9..V178-11). Every run goes to `backtest-runner`: log to `logs/v178/<stage>-<basis>.log`, background it, first check no other heavy python run is live, report the progress file `logs/measure_giveback_levels.<stage>-<basis>.progress`, never re-run a refused or failed stage (the script refuses an existing output anyway).

### Task V178-8: Frozen block and stage −1 pilot (gate)

**Model:** sonnet — runs a fixed command and copies fields; the judgement (the stop gate) is frozen above.

**Files:**
- Create: `$DOC` (header + frozen block + stage −1 section)
- Create: `docs/superpowers/results/v178/pilot-close.json` (+ `.provenance.json` if written), by the script

**Interfaces:**
- Consumes: V178-6 `--stage pilot`; `pilot-close.json` keys `frozen`, `n`, `arms` (`{arm: {"changed", "verdict"}}`), `control_b_changed`, `survivors`.
- Produces: `survivors`, read by `cmd_report` (V178-9) through `_apply_pilot`.

- [ ] **Step 1: Write and commit the frozen block before any window is read**

Create `$DOC` with: title `# v178 measurement: runner give-back levels (range-multiple and profit-share arms)`; `**Plan:**` link to the index; `**Spec:**` link; `**Raw results:** v178/*.json`; `**Looks:** one per output (the script refuses an existing file).` Then `## Frozen block (stated before any window is read)` as a two-column table with these rows, values from the spec and `measure_giveback_levels._frozen`: pilot window (`windows.STAGES["pilot"]`), pooled fold-train window and the three fold-train windows, the three fold-test years, VALIDATION (one shot, stage-3 arm only, partner's go); arms (A 5% of the best close; B off; R k ∈ {0.75, 1.0, 1.25}; S f ∈ {0.25, 0.33, 0.50} with a 1.0 × ATR floor); entries (one control-A pass per ticker); data source `yfinance`, 75-ticker cache; both engines; all ten horizons, `scale_out=True`, instrument v1; frictions (`SLIPPAGE_BPS`, `COMMISSION_PER_TRADE`, `COMMISSION_RISK_BASIS` read from `config` now and written as numbers); gating basis close, high/low TRAIN-side only; `cells_looked_at` 150 + sensitivity; the stop gates of this part (copied from the header above). Then the v92 overlap disclosure and the liquid-universe limit, verbatim from the Global Constraints.

```bash
git -C $R add docs/superpowers/results/2026-10-19-v178-giveback-levels.md
git -C $R commit -m "docs(v178): results -- frozen block, stated before any window is read

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Run the pilot (backtest-runner)**

Run: `python $R/scripts/backtest/measure_giveback_levels.py --stage pilot --basis close > $R/logs/v178/pilot-close.log 2>&1`
Expected: per-ticker progress, six `arms` readings, `-> docs/superpowers/results/v178/pilot-close.json`; exit 0 if any candidate is `REACHABLE`, exit 1 if none. A `refused:*` line means nothing was read: report it, fix nothing silently.

- [ ] **Step 3: Record stage −1 and apply the gate**

Append `## Stage −1 reachability (pilot)` to `$DOC`: `n`, a table arm · changed · verdict for the six candidates, and `control_b_changed`. Check: `frozen` in the JSON matches the committed block (window, arms, frictions, data source); a mismatch is reported to the partner, not edited away.
**Gate:** `survivors` empty → verdict `UNMEASURABLE`, skip V178-9 and V178-10, go to V178-11. Otherwise continue with V178-9 (refused arms stay in the measurement as neighbours; `_apply_pilot` drops them from the stage-3 pick).

- [ ] **Step 4: Commit**

```bash
git -C $R add docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/results/v178/
git -C $R commit -m "docs(v178): results -- stage -1 pilot reachability

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
`logs/v178/` (rows) is not committed.

### Task V178-9: Train simulation, stages 0–2 and the TRAIN-side sensitivity (gates)

**Model:** sonnet — fixed commands and a frozen stop rule; the readings are copied, not interpreted.

**Files:**
- Create (script): `docs/superpowers/results/v178/funnel-close.json`; `docs/superpowers/results/v178/sensitivity-high_low.json` only if an arm is `RESOLVABLE` at stage 0
- Modify: `$DOC` (stage 0–2 sections, descriptive blocks)

**Interfaces:**
- Consumes: V178-6 `--stage train`, `--stage report`; `funnel-close.json` keys `funnel` (`stage0`, `stage1`, `stage2`, `stopped_at`, `stage3_arm`, `holm`, `week_interval`, `pilot_refused`), `regime_arms`, `blocks`, `summary` (`n`, `stopped_at`, `stage3_arm`, `best_arm`, `ledger_p`, `holm`, `cells_looked_at`).
- Produces: `summary.stage3_arm` (V178-10's only permitted `--arm`) and `summary.ledger_p` / `best_arm` (V178-11's ledger row when stage 3 does not run).

- [ ] **Step 1: Simulate the close-basis rows (backtest-runner, hours)**

Run: `python $R/scripts/backtest/measure_giveback_levels.py --stage train --basis close > $R/logs/v178/train-close.log 2>&1`
Expected: `<n> rows -> logs/v178/rows-train-close.json.gz`; no ΔExpR is printed (rows only).

- [ ] **Step 2: Report the funnel (one look)**

Run: `python $R/scripts/backtest/measure_giveback_levels.py --stage report --basis close`
Expected: the `summary` JSON and `-> docs/superpowers/results/v178/funnel-close.json`.

- [ ] **Step 3: Record stages 0–2 and the descriptive blocks in `$DOC`**

Append, copying numbers from `funnel-close.json` (four decimals for R, never re-derived by hand):
- `## Stage 0 (pooled fold-train, paired MDE)`: per candidate n · changed · ΔExpR · ticker-cluster 95% CI · p · `mde_paired` · verdict; the Holm-adjusted p per arm; the week-cluster interval beside each (descriptive). Beside each R arm the v92 context line (nearest cell `trigger_r=2.50, mult=1.50`, never a threshold).
- `## Stage 1 (plateau + family same-sign)` and `## Stage 2 (harvest walk-forward)` only for the stages that ran (`stopped_at` says where it stopped): adopted arm, fold-train deltas, `same_sign`, verdict; per fold test_year · ΔExpR · n · changed · improving.
- `## Descriptive only (<cells_looked_at> cells looked at; none is an effect claim)`: the seven blocks per candidate, per-horizon ΔR, concentration (top-2 horizon share, long/short), arm-vs-B, near-duplicate (S vs R1.00), trend/chop for `regime_arms`, outcome flips. A pooled lift with long horizons clearly negative is written as a trade-off for the partner, not a pass. Close-basis results for R0.75 and R1.00 are stated as an upper bound on the live result until the sensitivity is read.

- [ ] **Step 4: Apply the gate**

- Every candidate `REFUSED` at stage 0 (`stopped_at == "stage0"`): the spec's base case, a finished result. **No sensitivity run, no VALIDATION.** Verdict `NO-LIFT`; skip Step 5 and V178-10, go to V178-11.
- `stopped_at` is `stage1` or `stage2` (nothing survives): run Step 5 (an arm cleared stage 0), then verdict `NO-LIFT`, skip V178-10.
- `stage3_arm` is set: run Step 5, then V178-10.

- [ ] **Step 5: TRAIN-side high/low sensitivity (only if an arm is RESOLVABLE at stage 0)**

Run (backtest-runner, one after the other, never in parallel):
`python $R/scripts/backtest/measure_giveback_levels.py --stage train --basis high_low > $R/logs/v178/train-high_low.log 2>&1`
`python $R/scripts/backtest/measure_giveback_levels.py --stage report --basis high_low`
Expected: `-> docs/superpowers/results/v178/sensitivity-high_low.json` with `summary.arms` = R0.75, each family's best and the stage-3 arm. Append `## High/low sensitivity (TRAIN side, never VALIDATION)` to `$DOC`: per arm close vs high/low stage-0 ΔExpR and stage-2 folds; the updated `cells_looked_at`.

- [ ] **Step 6: Commit**

```bash
git -C $R add docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/results/v178/
git -C $R commit -m "docs(v178): results -- stages 0-2 on TRAIN, descriptive blocks<, high/low sensitivity>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(drop the bracketed clause when Step 5 did not run).

### Task V178-10: Stage 3: the one VALIDATION shot (conditional, partner go)

**Model:** sonnet — two fixed commands; the only judgement is not to run them without the go.

**Runs only if** `funnel-close.json`'s `summary.stage3_arm` is set (V178-9 Step 4). Otherwise skip to V178-11.

**Files:**
- Create (script): `docs/superpowers/results/v178/validation-readings.json`, `logs/v178/validation-arms.json` (not committed)
- Create (`validate_component.py`): `docs/superpowers/results/v178/validation-gate.md`, `docs/superpowers/results/v178/validation-gate.json`
- Modify: `$DOC` (stage-3 section)

**Interfaces:**
- Consumes: V178-6 `--stage validation --arm <id> --preregistration <committed spec>`; `validation-readings.json` keys `arm`, `n`, `changed`, `arm_vs_a`, `a_vs_b`, `arm_vs_b`, `week_interval`, `permutation_p`, `blocks`, `per_horizon`, `concentration`, `regime`, `flips`; `validation-arms.json` `provenance.bespoke` (= `BESPOKE_REASON`), `provenance.signal_window`.
- Produces: the stage-3 verdict (`PASS` / `FAIL`) and the ledger `p` for V178-11.

- [ ] **Step 1: Ask the partner for the go**

`AskUserQuestion`, one question: "v178 stage 3: arm `<stage3_arm>` passed stages 0–2 (stage-2 mean ΔExpR `<x>`R, `<k>` of 3 folds improving). Spend the one VALIDATION shot on it?" Options, recommended first: "Run the shot" / "Stop here, record NO-LIFT at stage 2 unspent". Quote the per-horizon trade-off from `$DOC` in the question if V178-9 recorded one. No go → verdict `NOT-RUN (partner)`, VALIDATION stays unspent, go to V178-11.

- [ ] **Step 2: Run the shot (backtest-runner)**

Run: `python $R/scripts/backtest/measure_giveback_levels.py --stage validation --arm <stage3_arm> --preregistration docs/superpowers/specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md > $R/logs/v178/validation-close.log 2>&1`
Expected: `permutation_p=<p>`, `-> .../validation-readings.json`, `-> logs/v178/validation-arms.json`. Any `refused:*`: stop and report; the shot is not retried with other arguments.

- [ ] **Step 3: Run the harvest gate on the arms file (one look)**

```bash
REASON=$(python -c "import json;print(json.load(open('logs/v178/validation-arms.json',encoding='utf-8'))['provenance']['bespoke'])")
WIN=$(python -c "import json;print('..'.join(json.load(open('logs/v178/validation-arms.json',encoding='utf-8'))['provenance']['signal_window']))")
python $R/scripts/backtest/validate_component.py --stage validation --arms logs/v178/validation-arms.json \
  --gate harvest --permutation-p <permutation_p from Step 2> --bespoke-instrument "$REASON" \
  --title "v178 <stage3_arm> vs control A (fixed 5%)" --window "$WIN" \
  --out-md docs/superpowers/results/v178/validation-gate.md --out-json docs/superpowers/results/v178/validation-gate.json
```
(cwd `$R`.) Expected: every harvest clause printed with `win_rate_floor` `SKIPPED`, the `disclosure: outcome flips=...` line, and an overall verdict. Any clause failing → `FAIL`, the live 5% stays.

- [ ] **Step 4: Record stage 3 in `$DOC`**

Append `## Stage 3 (VALIDATION, one shot): <PASS|FAIL>`: the gate's clause table (from `validation-gate.md`), arm-vs-A, A-vs-B and arm-vs-B (ΔExpR, CI, p), week-cluster interval, permutation p, the flips disclosure, the seven blocks, per-horizon and concentration, regime split. A `PASS` licenses only Phase B's own spec and panel, never a live change.

- [ ] **Step 5: Commit**

```bash
git -C $R add docs/superpowers/results/2026-10-19-v178-giveback-levels.md docs/superpowers/results/v178/
git -C $R commit -m "docs(v178): results -- stage 3, the one VALIDATION shot (<verdict>)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
