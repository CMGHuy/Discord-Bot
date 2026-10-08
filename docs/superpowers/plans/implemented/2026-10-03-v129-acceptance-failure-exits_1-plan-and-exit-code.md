# v129 — Part 1: plan fields, level wiring, exit rule

> Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-03-v129-acceptance-failure-exits_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-03-v129-acceptance-failure-exits` on branch `2026-10-03-v129-acceptance-failure-exits`. Every path below is relative to that worktree. Never edit the main tree.

# Phase 1 — Foundations (Group A)

### Task V129-0: Capture the flag-off golden

**Files:**
- Create: `tests/backtesting/test_v129_flag_off_golden.py`
- Create: `tests/fixtures/v129/flag_off_golden.json` (generated, then committed)

**Interfaces:**
- Consumes: `run_backtest` (`swingbot/core/backtesting/backtest.py:283`), `backtest_scenarios.replay_scenarios`, `exit_sim.simulate_exit`, `tests.fixtures.ohlcv_parity.load_ohlcv`, `tests.backtesting.test_backtest_scenarios._structured_df`/`GATES`.
- Produces: `GOLDEN` fixture path and `_capture()`. Every later task must leave `test_flag_off_exits_match_the_pre_v129_golden` green. This is the spec's "flag off → byte-identical" parity for both populations.

This task must be committed **before** any of V129-4/5/6 change behaviour. The golden is the pre-v129 baseline.

- [ ] **Step 1: Write the test module**

```python
"""v129 flag-off parity (spec § Testing, first bullet): with
ACCEPTANCE_EXIT_ENABLED off, the Break & Retest backtest and the confluence
replay produce exactly the exits they produced before v129 touched
builders.py, backtest.py or exit_sim.py. The golden was captured at V129-0,
before any v129 code change -- never regenerate it to make this pass."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.planning.exit_sim import simulate_exit
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v129" / "flag_off_golden.json"
# The only Break & Retest cells the frozen fixtures trade (3 trades total).
BR_CASES = (("DELL", "2m"), ("DELL", "3m"))


def _r6(value):
    return None if value is None else round(float(value), 6)


def _break_retest_rows():
    rows = []
    for ticker, horizon_key in BR_CASES:
        summary = run_backtest(ticker, load_ohlcv(ticker), "Break & Retest", horizon_key,
                               exit_model="v2", scale_out=True, tp2_mode="levels")
        rows += [[ticker, horizon_key, t.entry_date, t.exit_date, t.direction,
                  _r6(t.stop_loss), _r6(t.take_profit), t.outcome, _r6(t.r_multiple),
                  t.runner_outcome] for t in summary.trades]
    return rows


def _confluence_rows():
    df = _structured_df()
    rows = []
    for i, plan in bs.replay_scenarios("AAPL", df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([int(i), plan.direction, plan.entry_type, _r6(plan.stop_loss),
                     _r6(plan.tp1), res.outcome, _r6(res.r_total), exit_index])
    return rows


def _capture():
    return {"break_retest": _break_retest_rows(), "confluence": _confluence_rows()}


def test_flag_off_exits_match_the_pre_v129_golden(monkeypatch):
    # raising=False: the attribute only exists from V129-5 on.
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", False, raising=False)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["break_retest"] and golden["confluence"], "golden must be non-empty"
    assert _capture() == golden
```

- [ ] **Step 2: Run it to verify it fails** (the fixture does not exist yet)

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`
Expected: FAIL, `FileNotFoundError` on `flag_off_golden.json`.

- [ ] **Step 3: Generate the golden from the unchanged code**

```bash
python -c "import json; from tests.backtesting.test_v129_flag_off_golden import _capture, GOLDEN; GOLDEN.parent.mkdir(parents=True, exist_ok=True); GOLDEN.write_text(json.dumps(_capture(), indent=1), encoding='utf-8')"
```

Check `git diff --stat` shows **no** change under `swingbot/` (the golden must come from pre-v129 code). Check the JSON has 3 `break_retest` rows and at least 1 `confluence` row (16 at time of writing).

- [ ] **Step 4: Run it to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add tests/backtesting/test_v129_flag_off_golden.py tests/fixtures/v129/flag_off_golden.json
git commit -m "test(v129): capture the flag-off exit golden before any v129 change

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V129-1: `TradePlanV2` acceptance fields

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (append after `issued_at: str | None = None`, the last field, ~line 129)
- Test: `tests/planning/test_plan_serialization.py`, `tests/db/test_plans_repository.py`

**Interfaces:**
- Produces: `TradePlanV2.acceptance_level: float | None = None` and `TradePlanV2.acceptance_close_below: float | None = None`. They are consumed by V129-4/5 (stamping), V129-6 (`acceptance_exit`) and V129-7 (replay).

Schema path (index, Spec correction 3): **add**. The fields land in `plans.doc` JSONB through `plan_to_dict`. No Alembic revision. No read-time upcasting: `plan_from_dict` already defaults missing fields.

- [ ] **Step 1: Write the failing tests**

Append to `tests/planning/test_plan_serialization.py`:

```python
def test_acceptance_fields_default_to_none_and_round_trip():
    p = _plan()
    assert p.acceptance_level is None
    assert p.acceptance_close_below is None
    stamped = _plan(acceptance_level=97.5, acceptance_close_below=97.0)
    q = plan_from_dict(plan_to_dict(stamped))
    assert (q.acceptance_level, q.acceptance_close_below) == (97.5, 97.0)


def test_pre_v129_record_without_acceptance_fields_loads_as_none():
    d = plan_to_dict(_plan())
    d.pop("acceptance_level")
    d.pop("acceptance_close_below")
    q = plan_from_dict(d)
    assert q.acceptance_level is None
    assert q.acceptance_close_below is None
```

Append to `tests/db/test_plans_repository.py`:

```python
def test_v129_acceptance_fields_ride_in_the_doc(repo, db_conn):
    """v129 used schema-evolution's ADD path: no column, no revision -- the
    two fields live in plans.doc and must survive the repository."""
    from tests.db_diff import diff_records
    record = _plan("P1", acceptance_level=97.5, acceptance_close_below=97.0)
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []
```

- [ ] **Step 2: Run them to verify the serialization tests fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: FAIL. `TypeError: ... unexpected keyword argument 'acceptance_level'` and `AttributeError`/`KeyError`.
(The repository test passes already. It pins the add path rather than driving code.)

- [ ] **Step 3: Add the fields**

In `plan_types.py`, directly after `issued_at: str | None = None`:

```python
    # v129: the price this trade leans on, frozen at the creating bar --
    # confluence: the PRE-clamp stop level (supports[0] / resistances[0]);
    # Break & Retest: the broken resistance / support. Recorded on every such
    # plan whatever ACCEPTANCE_EXIT_ENABLED says, so the live book collects
    # it before any decision. None for other strategies and pre-v129 rows.
    acceptance_level: float | None = None
    # v129: the daily CLOSE that ends the trade -- bullish: a close strictly
    # below it; bearish: strictly above (the name keeps the bullish reading).
    # Set only by an enabled acceptance arm (planning/acceptance_levels.py);
    # None = no close exit. Read by exit_sim.acceptance_exit.
    acceptance_close_below: float | None = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`, then `python scripts/dev/testrun.py file tests/db/test_plans_repository.py`, then `python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_types.py tests/planning/test_plan_serialization.py tests/db/test_plans_repository.py
git commit -m "feat(v129): TradePlanV2 acceptance_level / acceptance_close_below (doc add path)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V129-2: Expose Break & Retest's broken-level series

**Files:**
- Modify: `swingbot/core/market/entry_filters.py:773-809` (`break_retest_entries`)
- Create: `tests/market/test_break_retest_levels.py`

**Interfaces:**
- Produces:
  - `entry_filters._break_retest_levels(df, horizon_key) -> tuple[pd.Series, pd.Series]` returns `(resistance, support)`.
  - `entry_filters.break_retest_level_at(df, index: int, horizon_key: str, direction: str) -> float | None`. It returns resistance for `"bullish"`, support for `"bearish"`, and None when non-finite.
  - V129-4 consumes `break_retest_level_at`.

This is a pure refactor: the boolean signals stay byte-identical, asserted against a frozen copy of the pre-refactor function.

- [ ] **Step 1: Write the failing tests**

```python
"""v129: break_retest_entries exposes its broken-level series. The refactor
must leave the boolean signals byte-identical (spec § Testing), checked
against a frozen copy of the pre-v129 function on the parity fixtures."""
import numpy as np
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import HORIZONS
from tests.fixtures.ohlcv_parity import load_ohlcv

CASES = [(t, h) for t in ("DELL", "TSLA", "DOCU") for h in ("2m", "3m", "4m")]


def _legacy_break_retest_entries(df, horizon_key, params=None):
    """Frozen verbatim copy of entry_filters.break_retest_entries as of
    63d416c8 (pre-v129). Never edit."""
    p = ef._params("Break & Retest", params)
    h = HORIZONS[horizon_key]
    g = ef.compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(lookback)
    support = low.rolling(lookback).min().shift(lookback)
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean()
    recent = ef.BRT_RECENT_BARS.get(horizon_key, 10)

    broke_up = (high.rolling(recent).max().shift(1) > resistance) & \
               (vol_ratio.rolling(recent).max().shift(1) >= ef.SR_VOLUME_MULTIPLE)
    broke_dn = (low.rolling(recent).min().shift(1) < support) & \
               (vol_ratio.rolling(recent).max().shift(1) >= ef.SR_VOLUME_MULTIPLE)

    dist_to_res = (close - resistance) / resistance.replace(0, np.nan) * 100
    dist_to_sup = (close - support) / support.replace(0, np.nan) * 100
    retest_pct = ef.BRT_RETEST_PCT.get(horizon_key, 1.0)

    held_level_bull = low >= resistance * (1 - p["hold_tol_pct"] / 100)
    held_level_bear = high <= support * (1 + p["hold_tol_pct"] / 100)
    turned_bull = close > high.shift(1)
    turned_bear = close < low.shift(1)
    rsi14 = g["rsi14"]

    bullish = (broke_up & dist_to_res.between(0, retest_pct) & held_level_bull & turned_bull
               & rsi14.between(42, 63)
               & g["bull_regime"] & g["trend50_bull"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    bearish = (broke_dn & dist_to_sup.between(-retest_pct, 0) & held_level_bear & turned_bear
               & rsi14.between(37, 58)
               & g["bear_regime"] & g["trend50_bear"]
               & g["atr_floor"] & g["atr_calm"]).fillna(False)
    return bullish, bearish


@pytest.mark.parametrize(("ticker", "horizon_key"), CASES)
def test_signals_byte_identical_to_pre_v129(ticker, horizon_key):
    df = load_ohlcv(ticker)
    new_bull, new_bear = ef.break_retest_entries(df, horizon_key)
    old_bull, old_bear = _legacy_break_retest_entries(df, horizon_key)
    assert new_bull.equals(old_bull)
    assert new_bear.equals(old_bear)


def test_level_at_reads_resistance_for_bulls_and_support_for_bears():
    df = load_ohlcv("DELL")
    resistance, support = ef._break_retest_levels(df, "2m")
    i = 849   # a real DELL 2m Break & Retest entry bar (see V129-4)
    assert ef.break_retest_level_at(df, i, "2m", "bullish") == float(resistance.iloc[i])
    assert ef.break_retest_level_at(df, i, "2m", "bearish") == float(support.iloc[i])


def test_level_at_is_none_during_warm_up():
    df = load_ohlcv("DELL")
    assert ef.break_retest_level_at(df, 5, "2m", "bullish") is None


def test_level_at_never_sees_future_bars():
    df = load_ohlcv("DELL")
    for t in (400, 849, 1246):
        for direction in ("bullish", "bearish"):
            assert (ef.break_retest_level_at(df, t, "3m", direction)
                    == ef.break_retest_level_at(df.iloc[:t + 1], t, "3m", direction))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_break_retest_levels.py`
Expected: parity tests PASS (nothing has changed yet). The three level tests FAIL with `AttributeError: ... '_break_retest_levels'` / `'break_retest_level_at'`.

- [ ] **Step 3: Implement the refactor**

In `entry_filters.py`, insert above `def break_retest_entries`:

```python
def _break_retest_levels(df, horizon_key):
    """The broken levels Break & Retest trades against: the `sr_lookback`-bar
    high / low as it stood `sr_lookback` bars earlier. Every value is built
    from bars at or before its own index (shift(lookback)) -- no lookahead.
    Shared by break_retest_entries and break_retest_level_at (v129)."""
    lookback = HORIZONS[horizon_key]["sr_lookback"]
    resistance = df["High"].rolling(lookback).max().shift(lookback)
    support = df["Low"].rolling(lookback).min().shift(lookback)
    return resistance, support


def break_retest_level_at(df, index, horizon_key, direction):
    """v129: the broken level a Break & Retest entry at `index` leans on --
    resistance for a bullish retest, support for a bearish one. None while
    the series is still warming up."""
    resistance, support = _break_retest_levels(df, horizon_key)
    value = float((resistance if direction == "bullish" else support).iloc[index])
    return value if np.isfinite(value) else None
```

In `break_retest_entries`, replace these four lines:

```python
    h = HORIZONS[horizon_key]
    ...
    lookback = h["sr_lookback"]

    resistance = high.rolling(lookback).max().shift(lookback)
    support = low.rolling(lookback).min().shift(lookback)
```

with the single line (drop `h = HORIZONS[horizon_key]`, since nothing else in the function reads `h`):

```python
    resistance, support = _break_retest_levels(df, horizon_key)
```

Keep `close, high, low = df["Close"], df["High"], df["Low"]`. The rest of the body is unchanged.

- [ ] **Step 4: Run the tests and the existing entry-filter tests**

Run: `python scripts/dev/testrun.py file tests/market/test_break_retest_levels.py`, then `python scripts/dev/testrun.py file tests/market/test_entry_filters.py`
Expected: all pass. Then run `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`. None of the three touched functions may be listed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py tests/market/test_break_retest_levels.py
git commit -m "refactor(v129): expose Break & Retest broken-level series, signals byte-identical

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V129-3: `mde_expectancy_r_paired`

**Files:**
- Modify: `swingbot/core/backtesting/acceptance_harvest.py` (add after `mde_expectancy_r`, update `__all__`)
- Test: `tests/backtesting/test_acceptance_harvest.py`

**Interfaces:**
- Produces:
  - `paired_r_deltas(baseline, component) -> list[tuple[ArmTrade, float]]`. It yields `(baseline_trade, component.r_multiple - baseline.r_multiple)` for every key closed with an R in both arms, in baseline order.
  - `mde_expectancy_r_paired(baseline, component, *, target_n: int, power: float = 0.80, alpha: float = ALPHA) -> float | None`.
  - V129-8 consumes both.
- `mde_expectancy_r` stays byte-identical. Its value on the existing fixture is pinned below.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_acceptance_harvest.py`:

```python
def _pair(ticker, r_base, r_comp, outcome="win"):
    base = _trade(ticker, r_base, outcome)
    comp = _trade(ticker, r_comp, outcome)
    return base, comp


def test_mde_expectancy_r_is_unchanged_by_v129():
    pop = [_trade(f"T{i}", 0.2 if i % 2 else -1.0) for i in range(20)]
    assert ah.mde_expectancy_r(pop, target_n=30) == pytest.approx(0.3952139647010678, abs=1e-12)


def test_paired_mde_matches_hand_computation():
    # dR = [+0.1, -0.1, +0.3, +0.1]; var(ddof=1) = 0.08/3; one trade per
    # ticker -> design effect 1; target_n 4 -> (1.6449+0.8416)*sqrt(var/4).
    pairs = [_pair("A", 0.5, 0.6), _pair("B", -1.0, -1.1),
             _pair("C", 0.2, 0.5), _pair("D", 1.0, 1.1)]
    baseline = [b for b, _ in pairs]
    component = [c for _, c in pairs]
    expected = (1.6449 + 0.8416) * np.sqrt((0.08 / 3) / 4)
    got = ah.mde_expectancy_r_paired(baseline, component, target_n=4)
    assert got == pytest.approx(expected, rel=1e-9)
    assert got == pytest.approx(0.20302187, abs=1e-6)


def test_paired_mde_shrinks_with_target_n_and_ignores_unpaired():
    pairs = [_pair(f"T{i}", 0.3, 0.3 + (0.2 if i % 2 else -0.1)) for i in range(20)]
    baseline = [b for b, _ in pairs]
    component = [c for _, c in pairs] + [_trade("ONLY_COMP", 5.0)]
    small = ah.mde_expectancy_r_paired(baseline, component, target_n=20)
    large = ah.mde_expectancy_r_paired(baseline, component, target_n=200)
    assert large < small
    assert len(ah.paired_r_deltas(baseline, component)) == 20


def test_paired_mde_none_below_two_pairs_or_zero_target():
    b, c = _pair("A", 0.5, 0.6)
    assert ah.mde_expectancy_r_paired([b], [c], target_n=10) is None
    pairs = [_pair("A", 0.5, 0.6), _pair("B", 0.1, 0.0)]
    assert ah.mde_expectancy_r_paired([p[0] for p in pairs], [p[1] for p in pairs],
                                      target_n=0) is None


def test_paired_deltas_skip_untriggered_and_missing_r():
    b1, c1 = _pair("A", 0.5, 0.6)
    b2 = _trade("B", None, "not_triggered")
    c2 = _trade("B", -1.0, "loss")
    deltas = ah.paired_r_deltas([b1, b2], [c1, c2])
    assert [(t.ticker, round(d, 9)) for t, d in deltas] == [("A", 0.1)]
```

Add `import numpy as np` and `import pytest` to that test file's imports if they are absent.

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest.py`
Expected: the new paired tests FAIL with `AttributeError: ... 'mde_expectancy_r_paired'`. `test_mde_expectancy_r_is_unchanged_by_v129` PASSES.

- [ ] **Step 3: Implement**

In `acceptance_harvest.py`, extend `__all__` with `"paired_r_deltas", "mde_expectancy_r_paired"`. Then add after `mde_expectancy_r`:

```python
def paired_r_deltas(baseline, component) -> list:
    """(baseline_trade, component R - baseline R) for every pairing key that
    is CLOSED with an R in both arms, in baseline order. v129: the paired
    exit-only design replays the same entries under two exit rules, so the
    per-trade CHANGE in R is the quantity whose variance matters."""
    comp_by_key = {t.key: t for t in component
                   if t.outcome in CLOSED and t.r_multiple is not None}
    out = []
    for trade in baseline:
        if trade.outcome not in CLOSED or trade.r_multiple is None:
            continue
        other = comp_by_key.get(trade.key)
        if other is not None:
            out.append((trade, other.r_multiple - trade.r_multiple))
    return out


def mde_expectancy_r_paired(baseline, component, *, target_n: int,
                            power: float = 0.80, alpha: float = ALPHA) -> float | None:
    """v129 Stage 0: smallest ΔExpR detectable at `power` (one-sided
    `alpha`) for a PAIRED exit-only design -- (z_a + z_b) * sqrt(var(ΔR) /
    n_eff), var over per-trade ΔR (ddof=1), n_eff = target_n / design effect
    of the paired baseline trades. No factor 2: the variance of a paired
    difference already carries both arms. mde_expectancy_r (unpaired) is
    left byte-identical so v92's closed results stay reproducible."""
    pairs = paired_r_deltas(baseline, component)
    if len(pairs) < 2 or target_n <= 0:
        return None
    z_a = _Z_ALPHA_ONE_SIDED.get(alpha)
    z_b = _Z_POWER.get(power)
    if z_a is None or z_b is None:
        raise ValueError(f"no tabulated z for alpha={alpha}, power={power}")
    variance = float(np.var([delta for _, delta in pairs], ddof=1))
    n_eff = target_n / design_effect([trade for trade, _ in pairs])
    if n_eff <= 0:
        return None
    return float((z_a + z_b) * np.sqrt(variance / n_eff))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_acceptance_harvest.py`
Expected: all pass. Then run `python -m radon cc -s -n C swingbot/core/backtesting/acceptance_harvest.py`. Neither new function may be listed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/acceptance_harvest.py tests/backtesting/test_acceptance_harvest.py
git commit -m "feat(v129): paired-ΔR MDE for exit-only harvest designs; unpaired MDE pinned

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2 — Plans carry the level (Group B) and the exit rule (Group C)

### Task V129-4: Trap test, then wire `acceptance_level` into both plan paths

**Files:**
- Create: `swingbot/core/planning/acceptance_levels.py`
- Modify: `swingbot/core/planning/builders.py` (`build_strategy_plan` ~line 313, `build_confluence_plan` ~lines 403-444)
- Modify: `swingbot/core/backtesting/backtest.py:257-280` (`_bt_plan`)
- Create: `tests/planning/test_v129_acceptance_level_trap.py`

**Interfaces:**
- Consumes: `TradePlanV2.acceptance_level` (V129-1) and `entry_filters.break_retest_level_at` (V129-2).
- Produces (in `acceptance_levels.py`):
  - `BREAK_RETEST = "Break & Retest"`.
  - `stamp_strategy_acceptance(plan, df, index) -> None` sets `acceptance_level` on Break & Retest plans only.
  - `stamp_confluence_acceptance(plan, df, level) -> None` sets `acceptance_level = float(level)` (None stays None).
  - V129-5 extends both with the flag-on arm transforms. The signatures do not change.

This is the spec's "Known trap, designed out". The trap test is written first and **must be seen red** before any wiring.

- [ ] **Step 1: Write the trap test**

```python
"""v129 trap (spec § Code changes, "Known trap, designed out"): v92's stall
exit was unmeasurable because backtest-built plans never set its field. These
assert acceptance_level on BACKTEST-constructed plans for both populations,
and on the live constructors that share the same helper."""
import types

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market.entry_filters import break_retest_level_at
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow


def _captured_break_retest(monkeypatch, horizon_key="2m"):
    """(signal_index, plan) for every plan run_backtest's v2 loop built."""
    seen = []
    real = bt.simulate_exit

    def capture(df, i, plan, **kw):
        seen.append((int(i), plan))
        return real(df, i, plan, **kw)

    monkeypatch.setattr(bt, "simulate_exit", capture)
    df = load_ohlcv("DELL")
    bt.run_backtest("DELL", df, "Break & Retest", horizon_key,
                    exit_model="v2", scale_out=True, tp2_mode="levels")
    return df, seen


def test_backtest_break_retest_plans_carry_acceptance_level(monkeypatch):
    _, seen = _captured_break_retest(monkeypatch)
    assert seen, "DELL 2m must still produce Break & Retest plans"
    assert all(plan.acceptance_level is not None for _, plan in seen)


def test_backtest_break_retest_level_is_the_broken_level(monkeypatch):
    df, seen = _captured_break_retest(monkeypatch)
    for i, plan in seen:
        assert plan.acceptance_level == break_retest_level_at(df, i, "2m", plan.direction)


def test_live_break_retest_plan_carries_the_same_level(monkeypatch):
    df, seen = _captured_break_retest(monkeypatch)
    for i, plan in seen:
        live = build_strategy_plan(df, i, ticker="DELL", strategy="Break & Retest",
                                   horizon_key="2m", direction=plan.direction)
        assert live is not None
        assert live.acceptance_level == plan.acceptance_level


def test_confluence_replay_plans_carry_acceptance_level():
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one confluence plan"
    assert all(plan.acceptance_level is not None for _, plan in out)


def test_confluence_acceptance_level_is_the_pre_clamp_stop(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    scenario = types.SimpleNamespace(
        direction="bullish", entry=100.0, stop_loss=96.0, take_profit=104.0,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([100.0] * 60), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")
    assert plan is not None
    assert plan.stop_loss == pytest.approx(98.25)       # clamped, unchanged by v129
    assert plan.acceptance_level == pytest.approx(96.0)  # the level, pre-clamp
```

- [ ] **Step 2: Run it to verify it is red**

Run: `python scripts/dev/testrun.py file tests/planning/test_v129_acceptance_level_trap.py`
Expected: FAIL. Every test fails on `acceptance_level is None` (the field exists from V129-1 but nothing sets it). **Do not continue until you have seen this red run.**

- [ ] **Step 3: Create `acceptance_levels.py`**

```python
"""v129 acceptance-failure exits: the level a plan leans on.

Shared by BOTH plan paths -- the live builders (builders.py) and the
backtest (backtest._bt_plan) -- for the reason builders.py's level-lifecycle
comment records: a stop/exit feature reaching only one path is unmeasurable
by construction (edge-engine v4, v92 STALL_EXIT_ENABLED). V129-5 adds the
flag-on arm transforms here; with ACCEPTANCE_EXIT_ENABLED off this module
only records acceptance_level and never touches a stop.
"""
from __future__ import annotations

BREAK_RETEST = "Break & Retest"


def stamp_strategy_acceptance(plan, df, index) -> None:
    """Record the broken level on a Break & Retest plan. Every other
    strategy keeps acceptance_level None -- only Break & Retest has a
    well-defined broken level (spec § Out of scope)."""
    if plan.strategy != BREAK_RETEST:
        return
    from swingbot.core.market.entry_filters import break_retest_level_at
    plan.acceptance_level = break_retest_level_at(df, index, plan.horizon_key,
                                                  plan.direction)


def stamp_confluence_acceptance(plan, df, level) -> None:
    """Record a confluence plan's level: the scenario's stop BEFORE
    _clamp_stop_to_hard_cap ran (supports[0] / resistances[0])."""
    plan.acceptance_level = None if level is None else float(level)
```

- [ ] **Step 4: Wire the three call sites**

`builders.py`: add the import beside the other relative imports:

```python
from .acceptance_levels import stamp_confluence_acceptance, stamp_strategy_acceptance
```

In `build_strategy_plan`, after `plan.stall_exit_day = plan_params._resolve_stall_exit_day(strategy)` and before `return plan`:

```python
    stamp_strategy_acceptance(plan, df, index)
```

In `build_confluence_plan`, capture the level before the clamp. Replace

```python
    stop_loss = _clamp_stop_to_hard_cap(entry, scenario.stop_loss, is_bull)
```

with

```python
    level = scenario.stop_loss   # v129: the pre-clamp level the trade leans on
    stop_loss = _clamp_stop_to_hard_cap(entry, level, is_bull)
```

and after `plan_params._apply_quality(plan, quality_inputs)`, before `return plan`:

```python
    # Last, after targets, badge, cohort and quality were set from today's
    # stop: v129 never changes entries or targets (spec § Out of scope).
    stamp_confluence_acceptance(plan, df, level)
```

`backtest.py` `_bt_plan`: replace `return TradePlanV2(` … `)` with `plan = TradePlanV2(` … `)` (same arguments). Then add:

```python
    from swingbot.core.planning.acceptance_levels import stamp_strategy_acceptance
    stamp_strategy_acceptance(plan, df, i)
    return plan
```

- [ ] **Step 5: Run the trap test green, then the neighbours**

Run, in order:
- `python scripts/dev/testrun.py file tests/planning/test_v129_acceptance_level_trap.py` (expected all pass)
- `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py` (still pass: no stop moved)
- `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py`
- `python scripts/dev/testrun.py file tests/planning/test_build_strategy_plan.py`
- `python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py`

Then `python -m radon cc -s -n C swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py swingbot/core/planning/acceptance_levels.py`. `build_confluence_plan` (14) and `build_strategy_plan` (13) must not rise (plain calls add no branch). `run_backtest` is untouched.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/acceptance_levels.py swingbot/core/planning/builders.py swingbot/core/backtesting/backtest.py tests/planning/test_v129_acceptance_level_trap.py
git commit -m "feat(v129): stamp acceptance_level on live and backtest plans (trap test red->green)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V129-5: Config flags and the arm transforms

**Files:**
- Modify: `swingbot/config.py` (four `Field`s after the `STALL_EXIT_ENABLED` Field, ~line 1077, section `"Exit quality"`)
- Modify: `.env.example` (after `STALL_EXIT_ENABLED=false`, ~line 634)
- Modify: `tests/test_v115_strategy_work_off.py` (`FLAGS_OFF`)
- Modify: `swingbot/core/planning/acceptance_levels.py`
- Create: `tests/planning/test_acceptance_levels.py`

**Interfaces:**
- Consumes: V129-4's stamp functions and `risk_limits.HARD_MAX_PLANNED_LOSS_PCT`/`planned_loss_pct`.
- Produces (all in `acceptance_levels.py`; V129-7 consumes `apply_arm_z`, `apply_arm_b`, `atr_at`):
  - `ARM_Z = "Z"`, `ARM_B = "B"`, `ARMS = ("Z", "B")`.
  - `enabled_arms() -> frozenset[str]`.
  - `close_threshold(level: float, atr_val: float, b: float, direction: str) -> float`.
  - `disaster_stop(entry: float, level: float, atr_val: float, m: float, direction: str) -> float`.
  - `confluence_eligible(entry, level, direction) -> bool`.
  - `apply_arm_z(plan, atr_val: float, m: float, b: float) -> bool` mutates `stop_loss` and `acceptance_close_below` and returns eligibility.
  - `apply_arm_b(plan, atr_val: float, b: float) -> bool` mutates only `acceptance_close_below`.
  - `atr_at(df, index: int, entry: float) -> float` is ATR14 at `index` through `_safe_atr_value`.
- Config attrs: `ACCEPTANCE_EXIT_ENABLED` (bool, `false`), `ACCEPTANCE_EXIT_ARMS` (text, `"Z,B"`), `ACCEPTANCE_DISASTER_ATR_M` (float, interim `1.0`), `ACCEPTANCE_CLOSE_BUFFER_ATR` (float, interim `0.0`). All four keep `search_class="excluded"` (the default), so no `ScanParams` or `reachability.py` row is needed.

- [ ] **Step 1: Write the failing tests**

```python
"""v129 arm transforms (spec § Definitions): disaster stop, close threshold,
eligibility, flag parsing -- and that the flag-off build is untouched."""
import types

import pytest

from swingbot import config
from swingbot.core.planning import acceptance_levels as al
from swingbot.core.planning.builders import build_confluence_plan
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv


def _flags(monkeypatch, enabled=True, arms="Z,B", m=1.0, b=0.25):
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", enabled)
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ARMS", arms)
    monkeypatch.setattr(config, "ACCEPTANCE_DISASTER_ATR_M", m)
    monkeypatch.setattr(config, "ACCEPTANCE_CLOSE_BUFFER_ATR", b)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _confluence(direction, entry, stop, target, df=None):
    scenario = types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop, take_profit=target,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])
    return build_confluence_plan(scenario, df if df is not None else make_ohlcv([entry] * 60),
                                 ticker="XYZ", horizon_key="4w",
                                 primary_strategy="S/R Confluence")


def _br_plan(**kw):
    base = dict(plan_id="p", ticker="DELL", created_at="2024-01-02", source="strategy",
                strategy="Break & Retest", horizon_key="2m", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=96.0, tp1=106.0, tp1_fraction=0.5, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.ACTIVE)
    base.update(kw)
    return TradePlanV2(**base)


# --- flag parsing ------------------------------------------------------------

def test_flag_off_means_no_arm_even_if_arms_listed(monkeypatch):
    _flags(monkeypatch, enabled=False, arms="Z,B")
    assert al.enabled_arms() == frozenset()


def test_enabled_arms_parses_case_and_drops_unknown(monkeypatch):
    _flags(monkeypatch, arms="x, z ,")
    assert al.enabled_arms() == frozenset({"Z"})
    _flags(monkeypatch, arms="b,Z")
    assert al.enabled_arms() == frozenset({"Z", "B"})
    _flags(monkeypatch, arms="")
    assert al.enabled_arms() == frozenset()


# --- pure geometry -----------------------------------------------------------

def test_disaster_stop_bullish_is_level_minus_m_atr():
    assert al.disaster_stop(100.0, 99.0, 1.0, 0.5, "bullish") == pytest.approx(98.5)


def test_disaster_stop_pulled_in_to_the_2pct_cap():
    assert al.disaster_stop(100.0, 98.5, 1.0, 1.5, "bullish") == pytest.approx(98.0)


def test_disaster_stop_bearish_mirror_and_cap():
    assert al.disaster_stop(100.0, 101.0, 1.0, 0.5, "bearish") == pytest.approx(101.5)
    assert al.disaster_stop(100.0, 101.5, 1.0, 1.5, "bearish") == pytest.approx(102.0)


def test_close_threshold_both_directions():
    assert al.close_threshold(99.0, 2.0, 0.25, "bullish") == pytest.approx(98.5)
    assert al.close_threshold(101.0, 2.0, 0.25, "bearish") == pytest.approx(101.5)
    assert al.close_threshold(99.0, 2.0, 0.0, "bullish") == pytest.approx(99.0)


def test_confluence_eligible_boundary_and_wrong_side():
    assert al.confluence_eligible(100.0, 98.0, "bullish")        # exactly 2%: eligible
    assert not al.confluence_eligible(100.0, 97.9, "bullish")    # beyond the cap
    assert not al.confluence_eligible(100.0, 100.5, "bullish")   # profit side
    assert al.confluence_eligible(100.0, 102.0, "bearish")
    assert not al.confluence_eligible(100.0, 99.5, "bearish")
    assert not al.confluence_eligible(100.0, None, "bullish")


def test_atr_at_falls_back_on_short_history():
    df = make_ohlcv([100.0] * 5)                 # < 14 bars: ATR14 is NaN
    assert al.atr_at(df, 4, 100.0) == pytest.approx(2.0)   # 2% of entry


# --- builder, flag on / off --------------------------------------------------

def test_flag_off_confluence_build_is_unchanged(monkeypatch):
    _flags(monkeypatch, enabled=False)
    plan = _confluence("bullish", 100.0, 99.0, 102.0)
    assert plan.stop_loss == pytest.approx(99.0)
    assert plan.acceptance_level == pytest.approx(99.0)
    assert plan.acceptance_close_below is None


def test_eligible_confluence_plan_gets_disaster_stop_and_threshold(monkeypatch):
    _flags(monkeypatch, enabled=False)
    off = _confluence("bullish", 100.0, 99.0, 102.0)
    _flags(monkeypatch, m=1.0, b=0.25)
    df = make_ohlcv([100.0] * 60)
    on = _confluence("bullish", 100.0, 99.0, 102.0, df)
    atr = al.atr_at(df, len(df) - 1, 100.0)
    assert on.stop_loss == pytest.approx(max(99.0 - atr, 98.0))
    assert on.acceptance_close_below == pytest.approx(99.0 - 0.25 * atr)
    assert on.tp1 == off.tp1 and on.tp2 == off.tp2          # targets unchanged
    assert on.entry_type == off.entry_type                  # entries unchanged


def test_bearish_confluence_mirror(monkeypatch):
    _flags(monkeypatch, m=0.5, b=0.25)
    df = make_ohlcv([100.0] * 60)
    plan = _confluence("bearish", 100.0, 101.0, 98.0, df)
    atr = al.atr_at(df, len(df) - 1, 100.0)
    assert plan.stop_loss == pytest.approx(min(101.0 + 0.5 * atr, 102.0))
    assert plan.acceptance_close_below == pytest.approx(101.0 + 0.25 * atr)


def test_not_eligible_clamped_plan_keeps_todays_stop_and_no_exit(monkeypatch):
    _flags(monkeypatch)
    plan = _confluence("bullish", 100.0, 96.0, 104.0)        # 4% level -> clamped
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.acceptance_level == pytest.approx(96.0)
    assert plan.acceptance_close_below is None


def test_arm_b_only_leaves_confluence_plans_alone(monkeypatch):
    _flags(monkeypatch, arms="B")
    plan = _confluence("bullish", 100.0, 99.0, 102.0)
    assert plan.stop_loss == pytest.approx(99.0)
    assert plan.acceptance_close_below is None


def test_arm_b_sets_threshold_and_keeps_the_stop(monkeypatch):
    _flags(monkeypatch, arms="B", b=0.25)
    monkeypatch.setattr("swingbot.core.market.entry_filters.break_retest_level_at",
                        lambda df, index, horizon_key, direction: 99.0)
    df = make_ohlcv([100.0] * 60)
    plan = _br_plan()
    al.stamp_strategy_acceptance(plan, df, 59)
    atr = al.atr_at(df, 59, 100.0)
    assert plan.acceptance_level == 99.0
    assert plan.acceptance_close_below == pytest.approx(99.0 - 0.25 * atr)
    assert plan.stop_loss == 96.0


def test_arm_b_not_eligible_without_a_level():
    plan = _br_plan(acceptance_level=None)
    assert al.apply_arm_b(plan, 2.0, 0.25) is False
    assert plan.acceptance_close_below is None


def test_other_strategies_get_no_level(monkeypatch):
    _flags(monkeypatch)
    plan = _br_plan(strategy="RSI")
    al.stamp_strategy_acceptance(plan, make_ohlcv([100.0] * 60), 59)
    assert plan.acceptance_level is None and plan.acceptance_close_below is None


def test_no_lookahead_stop_and_threshold(monkeypatch):
    """Spec § Testing: values for a plan created at bar t are identical when
    computed on df.iloc[:t+1]."""
    _flags(monkeypatch, m=1.0, b=0.25)
    df = load_ohlcv("DELL")
    t = 849
    entry = float(df["Close"].iloc[t])
    assert al.atr_at(df, t, entry) == al.atr_at(df.iloc[:t + 1], t, entry)
    level = entry * 0.99
    scenario_full = _confluence("bullish", entry, level, entry * 1.02, df.iloc[:t + 1])
    atr = al.atr_at(df, t, entry)
    assert scenario_full.stop_loss == pytest.approx(
        al.disaster_stop(entry, level, atr, 1.0, "bullish"))
    assert scenario_full.acceptance_close_below == pytest.approx(
        al.close_threshold(level, atr, 0.25, "bullish"))
```

Append to `FLAGS_OFF` in `tests/test_v115_strategy_work_off.py`:

```python
    ("v129", "ACCEPTANCE_EXIT_ENABLED", False),
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_acceptance_levels.py`
Expected: FAIL. `AttributeError: module 'swingbot.config' has no attribute 'ACCEPTANCE_EXIT_ENABLED'` (raised by `monkeypatch.setattr`) and `AttributeError: ... 'disaster_stop'`.

- [ ] **Step 3: Add the config Fields and `.env.example` lines**

In `swingbot/config.py`, directly after the `STALL_EXIT_ENABLED` `Field(...)`:

```python
    Field("ACCEPTANCE_EXIT_ENABLED", "ACCEPTANCE_EXIT_ENABLED", "Exit quality",
          "Exit level trades on a daily close beyond the level (v129)",
          type="checkbox", default="false",
          help="Judges a confluence / Break & Retest trade by acceptance -- a "
               "daily CLOSE beyond its level -- instead of an intrabar touch. "
               "Off until its one VALIDATION shot per arm passes. NOTE: live "
               "position management (plan_manager) does not read the close "
               "exit yet; do not flip without wiring it (v129 plan, V129-16)."),
    Field("ACCEPTANCE_EXIT_ARMS", "ACCEPTANCE_EXIT_ARMS", "Exit quality",
          "Acceptance-exit arms in force",
          type="text", default="Z,B",
          help="Comma list of Z (confluence: disaster stop + close exit) and B "
               "(Break & Retest: close exit only). Read only when "
               "ACCEPTANCE_EXIT_ENABLED is on; unknown letters are ignored."),
    Field("ACCEPTANCE_DISASTER_ATR_M", "ACCEPTANCE_DISASTER_ATR_M", "Exit quality",
          "Arm Z disaster stop (ATR beyond the level)",
          type="float", default="1.0", min=0.25, max=3.0, step=0.25,
          help="Interim value; replaced by the Stage 3-selected cell. Never "
               "read while ACCEPTANCE_EXIT_ENABLED is off."),
    Field("ACCEPTANCE_CLOSE_BUFFER_ATR", "ACCEPTANCE_CLOSE_BUFFER_ATR", "Exit quality",
          "Close-exit buffer (ATR beyond the level)",
          type="float", default="0.0", min=0.0, max=1.0, step=0.05,
          help="A close beyond level -/+ this many ATR14 ends the trade. "
               "Interim value; replaced by the Stage 3-selected cell. Never "
               "read while ACCEPTANCE_EXIT_ENABLED is off."),
```

In `.env.example`, after `STALL_EXIT_ENABLED=false`:

```
# v129: exit a confluence / Break & Retest trade on a daily CLOSE beyond its
# level (acceptance) instead of an intrabar touch. Off until its VALIDATION
# shot passes -- and live plan_manager does not read the close exit yet.
ACCEPTANCE_EXIT_ENABLED=false
# Z = confluence (disaster stop + close exit), B = Break & Retest (close exit).
ACCEPTANCE_EXIT_ARMS=Z,B
# Interim; set from the Stage 3-selected cell. Unread while the flag is off.
ACCEPTANCE_DISASTER_ATR_M=1.0
ACCEPTANCE_CLOSE_BUFFER_ATR=0.0
```

- [ ] **Step 4: Implement the transforms in `acceptance_levels.py`**

Replace the module's imports and the two stamp functions so the file reads (keeping V129-4's docstring):

```python
from __future__ import annotations

from swingbot import config
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct

BREAK_RETEST = "Break & Retest"
ARM_Z, ARM_B = "Z", "B"
ARMS = (ARM_Z, ARM_B)


def enabled_arms() -> frozenset:
    """Arms in force. ACCEPTANCE_EXIT_ARMS is read only when the master flag
    is on; unknown letters and blanks are dropped, never raised on."""
    if not getattr(config, "ACCEPTANCE_EXIT_ENABLED", False):
        return frozenset()
    raw = str(getattr(config, "ACCEPTANCE_EXIT_ARMS", "") or "")
    return frozenset(part.strip().upper() for part in raw.split(",")) & frozenset(ARMS)


def close_threshold(level, atr_val, b, direction) -> float:
    """The close that ends the trade: level - b*ATR (bullish, exit on a close
    strictly below), level + b*ATR (bearish, strictly above)."""
    return level - b * atr_val if direction == "bullish" else level + b * atr_val


def disaster_stop(entry, level, atr_val, m, direction) -> float:
    """Arm Z's intrabar stop: level -/+ m*ATR, pulled in to the 2% hard cap
    when farther -- max(level - m*atr, entry*(1 - 0.02)) for a bullish plan."""
    cap = entry * HARD_MAX_PLANNED_LOSS_PCT / 100.0
    if direction == "bullish":
        return max(level - m * atr_val, entry - cap)
    return min(level + m * atr_val, entry + cap)


def confluence_eligible(entry, level, direction) -> bool:
    """Arm Z applies only when the level sits on the stop side of entry and
    within the 2% cap -- exactly the plans _clamp_stop_to_hard_cap did NOT
    move. The rest keep today's stop and get no acceptance exit."""
    if level is None or entry is None or entry <= 0:
        return False
    on_stop_side = level < entry if direction == "bullish" else level > entry
    return on_stop_side and planned_loss_pct(entry, level) <= HARD_MAX_PLANNED_LOSS_PCT


def apply_arm_z(plan, atr_val, m, b) -> bool:
    """Write arm Z onto an eligible confluence plan: stop_loss becomes the
    disaster stop (so 1R = entry -> disaster stop for every consumer) and the
    close threshold is set. Returns eligibility; an ineligible plan is
    left exactly as built."""
    entry, level = plan.trigger_price, plan.acceptance_level
    if not confluence_eligible(entry, level, plan.direction):
        return False
    plan.stop_loss = disaster_stop(entry, level, atr_val, m, plan.direction)
    plan.acceptance_close_below = close_threshold(level, atr_val, b, plan.direction)
    return True


def apply_arm_b(plan, atr_val, b) -> bool:
    """Arm B: stop unchanged (the 2*ATR fallback); add the close threshold
    at the broken level. False when the plan has no level (warm-up)."""
    if plan.acceptance_level is None:
        return False
    plan.acceptance_close_below = close_threshold(plan.acceptance_level, atr_val, b,
                                                  plan.direction)
    return True


def atr_at(df, index, entry) -> float:
    """ATR14 at `index`, through _safe_atr_value (2% of entry when NaN or
    non-positive) -- causal, so df and df.iloc[:index+1] agree."""
    from swingbot.core.market.indicators import atr as atr_indicator
    from .targets import _safe_atr_value
    return _safe_atr_value(entry, float(atr_indicator(df, 14).iloc[index]))


def stamp_strategy_acceptance(plan, df, index) -> None:
    """Record the broken level on a Break & Retest plan; with arm B enabled,
    also set its close threshold. Every other strategy is left untouched --
    only Break & Retest has a well-defined broken level."""
    if plan.strategy != BREAK_RETEST:
        return
    from swingbot.core.market.entry_filters import break_retest_level_at
    plan.acceptance_level = break_retest_level_at(df, index, plan.horizon_key,
                                                  plan.direction)
    if ARM_B in enabled_arms():
        apply_arm_b(plan, atr_at(df, index, plan.trigger_price),
                    config.ACCEPTANCE_CLOSE_BUFFER_ATR)


def stamp_confluence_acceptance(plan, df, level) -> None:
    """Record a confluence plan's pre-clamp level; with arm Z enabled, apply
    the disaster stop and close threshold at the creating bar's ATR14."""
    plan.acceptance_level = None if level is None else float(level)
    if ARM_Z in enabled_arms():
        apply_arm_z(plan, atr_at(df, len(df) - 1, plan.trigger_price),
                    config.ACCEPTANCE_DISASTER_ATR_M, config.ACCEPTANCE_CLOSE_BUFFER_ATR)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run, in order:
- `python scripts/dev/testrun.py file tests/planning/test_acceptance_levels.py`
- `python scripts/dev/testrun.py file tests/planning/test_v129_acceptance_level_trap.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`
- `python scripts/dev/testrun.py file tests/test_v115_strategy_work_off.py`
- `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
- `python scripts/dev/testrun.py file tests/test_scan_params_coverage.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`

Expected: all pass. Then run `python -m radon cc -s -n C swingbot/core/planning/acceptance_levels.py`; expect empty output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_v115_strategy_work_off.py swingbot/core/planning/acceptance_levels.py tests/planning/test_acceptance_levels.py
git commit -m "feat(v129): inert ACCEPTANCE_EXIT_* flags and arm Z/B plan transforms

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V129-6: `acceptance_exit` and the two exit-walk call sites

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (`_single_leg_exit_walk` :41-134, `_scale_out_exit_walk` :173-310, new helpers)
- Create: `tests/planning/test_exit_sim_acceptance.py`

**Interfaces:**
- Consumes: `TradePlanV2.acceptance_close_below` (V129-1).
- Produces:
  - `exit_sim.acceptance_exit(plan, bar_close: float) -> bool`.
  - An exit leg reason `"acceptance_exit"`. A pre-TP1 exit is a full-fraction leg with outcome `"loss"` (or `"scratch"` if r ≥ 0). An exit on the TP1 bar is the runner leg, with `runner_outcome="acceptance_exit"` and outcome `"win"`.
  - V129-7 reads `legs[-1]["reason"]`.
- New private helpers in `exit_sim.py`: `_close_exit_result`, `_acceptance_result`, `_stall_result`, `_single_leg_r`, `_bar_hits`, `_phase1_stop`, `_runner_walk`, `_runner_leg`.

Both walks are legacy complexity offenders (`_single_leg_exit_walk` 16, `_scale_out_exit_walk` 30). The rule enters each as one helper call. Behaviour-preserving extractions in the same task bring both under 15. V129-0's golden plus the existing exit-sim tests prove nothing else moved.

- [ ] **Step 0: Check for v123's split**

Run `git grep -n "def _stall_exit\|def _runner_phase" swingbot/core/planning/exit_sim.py`. If it prints anything, V123-3 has merged and already split the scale-out walk. In that case keep v123's helpers and make only these changes:
- Put the acceptance check in front of v123's `_stall_exit(ctx, j)` call, as `_acceptance_result(...) or _stall_exit(ctx, j)`.
- Put the TP1-bar check from `_runner_leg` (Step 3) at the top of v123's `_runner_phase`.
- Skip the extractions below that v123 already did.
If it prints nothing, continue as written.

- [ ] **Step 1: Write the failing tests**

```python
"""v129: exit on a daily CLOSE beyond the acceptance threshold (spec § Exit
rule). Order on one bar: stop -> target/TP1 -> acceptance -> stall -> timeout.
entry 100 (market, bar 0), stop 95, tp1 110 -> risk 5, rr 2; threshold 98."""
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import acceptance_exit, simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

BOTH = pytest.mark.parametrize("scale_out", [False, True])


def _bull(**kw):
    return _plan(direction="bullish", stop_loss=95.0, tp1=110.0,
                 acceptance_close_below=98.0, **kw)


def _bear(**kw):
    return _plan(direction="bearish", stop_loss=105.0, tp1=90.0,
                 acceptance_close_below=102.0, **kw)


# --- the pure rule -------------------------------------------------------------

def test_acceptance_exit_bullish_strict_below():
    assert acceptance_exit(_bull(), 97.99) is True
    assert acceptance_exit(_bull(), 98.0) is False      # exactly on: no exit
    assert acceptance_exit(_bull(), 98.5) is False


def test_acceptance_exit_bearish_strict_above():
    assert acceptance_exit(_bear(), 102.01) is True
    assert acceptance_exit(_bear(), 102.0) is False
    assert acceptance_exit(_bear(), 101.0) is False


def test_acceptance_exit_none_threshold_never_fires():
    assert acceptance_exit(_plan(acceptance_close_below=None), 1.0) is False


# --- in the walks ------------------------------------------------------------------

@BOTH
def test_close_through_exits_at_the_close(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 97.8), (97.8, 98.0, 96.0, 97.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "loss"
    assert res.exit_index == 1
    assert res.legs == [{"fraction": 1.0, "exit_price": 97.8,
                         "r": pytest.approx(-0.44), "reason": "acceptance_exit"}]
    assert res.r_total == pytest.approx(-0.44)


@BOTH
def test_wick_only_bar_does_not_exit(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.0, 98.5), (98.5, 111.0, 98.4, 110.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "win"          # bar 2 reaches TP1; bar 1 only wicked
    assert res.exit_index == 2
    assert all(leg["reason"] != "acceptance_exit" for leg in res.legs)


@BOTH
def test_close_exactly_on_threshold_does_not_exit(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 98.0), (98.0, 111.0, 97.9, 110.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert all(leg["reason"] != "acceptance_exit" for leg in res.legs)


@BOTH
def test_stop_and_close_through_on_one_bar_stop_wins(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 94.0, 96.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "loss"
    assert res.r_total == -1.0
    assert res.legs[0]["reason"] == "stop"


def test_tp1_and_close_through_on_one_bar_banks_tp1_then_exits_runner():
    df = make_ohlcv([100.0, (100.0, 111.0, 97.0, 97.5), (97.5, 120.0, 97.0, 119.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=True)
    assert res.outcome == "win"
    assert res.runner_outcome == "acceptance_exit"
    assert res.exit_index == 1
    assert res.legs[0] == {"fraction": 0.5, "exit_price": 110.0, "r": pytest.approx(2.0),
                           "reason": "tp1"}
    assert res.legs[1]["exit_price"] == pytest.approx(97.5)
    assert res.legs[1]["r"] == pytest.approx(-0.5)
    assert res.legs[1]["reason"] == "acceptance_exit"
    assert res.r_total == pytest.approx(0.75)


def test_single_leg_tp1_and_close_through_is_a_plain_win():
    df = make_ohlcv([100.0, (100.0, 111.0, 97.0, 97.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=False)
    assert res.outcome == "win" and res.r_total == pytest.approx(2.0)


@BOTH
def test_bearish_mirror_close_through(scale_out):
    df = make_ohlcv([100.0, (101.0, 102.5, 100.5, 102.2)])
    res = simulate_exit(df, 0, _bear(), scale_out=scale_out)
    assert res.legs[0]["reason"] == "acceptance_exit"
    assert res.legs[0]["exit_price"] == pytest.approx(102.2)
    assert res.r_total == pytest.approx(-0.44)


def test_acceptance_beats_stall_on_the_same_bar(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    # Bar 1 is past stall_exit_day 0 AND below +0.5R AND closes through 98:
    # both rules are live on the same bar; acceptance is checked first.
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 97.8)])
    res = simulate_exit(df, 0, _bull(stall_exit_day=0), scale_out=True)
    assert res.exit_index == 1
    assert res.legs[0]["reason"] == "acceptance_exit"


def test_stall_still_fires_without_a_threshold(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    df = make_ohlcv([100.0, 100.0, 101.0, 101.0])
    plan = _plan(direction="bullish", stop_loss=90.0, tp1=120.0, stall_exit_day=1)
    res = simulate_exit(df, 0, plan, scale_out=True)
    assert res.legs[0]["reason"] == "stall_exit"
    assert res.exit_index == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_acceptance.py`
Expected: FAIL with `ImportError: cannot import name 'acceptance_exit'`.

- [ ] **Step 3: Implement the rule and the helpers**

In `exit_sim.py`, add after `_not_triggered`:

```python
def acceptance_exit(plan: TradePlanV2, bar_close: float) -> bool:
    """v129: True when the plan carries an acceptance threshold and this bar
    CLOSED beyond it -- bullish strictly below, bearish strictly above. A
    wick through the threshold that closes back inside is not acceptance."""
    threshold = plan.acceptance_close_below
    if threshold is None:
        return False
    if plan.direction == "bullish":
        return bar_close < threshold
    return bar_close > threshold


def _close_exit_result(entry_index, j, entry_price, exit_price, sign, risk,
                       reason) -> ExitResult:
    """A full-position exit at bar j's close (acceptance or stall)."""
    r = round((exit_price - entry_price) * sign / risk, 3)
    return ExitResult(outcome="loss" if r < 0 else "scratch", runner_outcome=None,
                      entry_index=entry_index, exit_index=j, entry_price=entry_price,
                      r_total=r, legs=[{"fraction": 1.0, "exit_price": exit_price,
                                        "r": r, "reason": reason}])


def _acceptance_result(plan, j, close_j, entry_index, entry_price, sign, risk):
    """The v129 acceptance exit at close[j], or None."""
    if not acceptance_exit(plan, close_j):
        return None
    return _close_exit_result(entry_index, j, entry_price, close_j, sign, risk,
                              "acceptance_exit")


def _stall_result(plan, j, close_j, entry_index, entry_price, sign, risk):
    """v92 Hypothesis 2's stall exit at close[j], or None -- moved verbatim
    out of _scale_out_exit_walk (same condition, same rounding)."""
    if not (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
            and (j - entry_index) > plan.stall_exit_day):
        return None
    if (close_j - entry_price) * sign / risk >= 0.5:
        return None
    return _close_exit_result(entry_index, j, entry_price, close_j, sign, risk,
                              "stall_exit")


def _single_leg_r(outcome, exit_price, entry_price, sign, risk, rr):
    """(unrounded r, reason) for a finished single-leg walk."""
    if outcome == "win":
        return rr, "tp1"
    if outcome == "loss":
        return -1.0, "stop"
    if outcome == "scratch":
        return 0.0, "breakeven_stop"
    return (exit_price - entry_price) * sign / risk, "timeout"


def _bar_hits(is_bull, hi, lo, cur_stop, tp1, be_trigger):
    """(hit_stop, hit_target, reached_trigger) for one pre-TP1 bar."""
    if is_bull:
        return lo <= cur_stop, hi >= tp1, hi >= be_trigger
    return hi >= cur_stop, lo <= tp1, lo <= be_trigger


def _phase1_stop(entry_index, j, entry_price, cur_stop, stop_moved) -> ExitResult:
    """A pre-TP1 stop touch: -1R before the break-even move, a 0R scratch
    after it. Always exactly that R -- a gap through the stop is not
    re-priced (v129 keeps this accounting for the arms' pairing)."""
    r = round(0.0 if stop_moved else -1.0, 3)
    return ExitResult(outcome="scratch" if stop_moved else "loss", runner_outcome=None,
                      entry_index=entry_index, exit_index=j, entry_price=entry_price,
                      r_total=r, legs=[{"fraction": 1.0, "exit_price": cur_stop, "r": r,
                                        "reason": "breakeven_stop" if stop_moved else "stop"}])
```

In `_single_leg_exit_walk`, inside the loop directly after the `if hit_target: ... break` block and before `if reached_trigger and not stop_moved:`, insert:

```python
        # v129: the acceptance exit at this bar's close -- after the stop and
        # the target, so either of those wins a same-bar tie.
        accepted = _acceptance_result(plan, j, float(close[j]), entry_index,
                                      entry_price, sign, risk)
        if accepted is not None:
            return accepted
```

and replace the post-loop `if outcome == "win": ... else: # timeout ...` chain (the four branches) with:

```python
    r, reason = _single_leg_r(outcome, exit_price, entry_price, sign, risk, rr)
```

(keep the following `r = round(r, 3)` and the `return ExitResult(...)` as they are). Add one line to its docstring: `v129: a close beyond plan.acceptance_close_below exits at that close (after the stop and target checks).`

Replace `_scale_out_exit_walk` and add the two runner helpers above it:

```python
def _runner_walk(df, plan, entry_price, risk, tp1_index, end):
    """The runner's bar loop, moved verbatim out of _scale_out_exit_walk:
    returns (runner_exit | None, exit_index | None, runner_reason | None,
    checked_stop). Stop starts at the v39 runner floor and ratchets via the
    chandelier trail on closes only -- no intrabar lookahead."""
    from swingbot.core.market.indicators import atr as atr_indicator

    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    tp1, tp2 = plan.tp1, plan.tp2
    runner_stop = runner_floor(entry_price, tp1)
    extreme_close = float(close[tp1_index])
    atr_series = atr_indicator(df, 14)
    checked_stop = runner_stop
    for j in range(tp1_index + 1, end + 1):
        checked_stop = runner_stop   # snapshot BEFORE this bar's own ratchet
        hi, lo = float(high[j]), float(low[j])
        if (lo <= runner_stop) if is_bull else (hi >= runner_stop):
            # v39: "runner_be" means "closed at its initial post-TP1 floor";
            # the string is deliberately unchanged (~30 files match it).
            reason = ("runner_be" if runner_stop == runner_floor(entry_price, tp1)
                      else "runner_trail")
            return runner_stop, j, reason, checked_stop
        if tp2 is not None and ((hi >= tp2) if is_bull else (lo <= tp2)):
            return tp2, j, "runner_tp2", checked_stop
        extreme_close = (max(extreme_close, float(close[j])) if is_bull
                         else min(extreme_close, float(close[j])))
        atr_val = _safe_atr_value(entry_price, float(atr_series.iloc[j]))
        runner_r = (extreme_close - entry_price) * sign / risk
        mult = _effective_trail_mult(plan.trail_atr_mult, runner_r)
        trail = chandelier_stop(extreme_close, atr_val, mult, plan.direction)
        runner_stop = max(runner_stop, trail) if is_bull else min(runner_stop, trail)
    return None, None, None, checked_stop


def _runner_leg(df, plan, entry_price, risk, tp1_index, end):
    """Phase 2: (runner_exit, exit_index, runner_reason).

    v129: when the TP1 bar itself CLOSED through the acceptance threshold,
    the remainder exits at that close -- TP1 was banked first, per the
    same-bar order stop -> target -> acceptance. Later runner bars need no
    acceptance check: the runner stop sits at or beyond the v39 floor, on the
    profit side of entry, while every acceptance threshold sits on the loss
    side, so a close through the threshold has already traded through the
    runner stop on that bar. On timeout the exit is clamped to checked_stop
    (the level actually tested against the last bar), as before."""
    close = df["Close"].values
    if acceptance_exit(plan, float(close[tp1_index])):
        return float(close[tp1_index]), tp1_index, "acceptance_exit"
    runner_exit, exit_index, runner_reason, checked_stop = _runner_walk(
        df, plan, entry_price, risk, tp1_index, end)
    if runner_exit is None:
        exit_px = float(close[end])
        runner_exit = (max(exit_px, checked_stop) if plan.direction == "bullish"
                       else min(exit_px, checked_stop))
        exit_index, runner_reason = end, "runner_timeout"
    return runner_exit, exit_index, runner_reason


def _scale_out_exit_walk(
    df, entry_index: int, entry_price: float, plan: TradePlanV2, max_holding_days: int,
) -> ExitResult:
    """Hybrid scale-out walk (spec Sec5). Phase 1 (pre-TP1) matches
    _single_leg_exit_walk when the stall-exit flag is off; a stop/scratch/
    timeout before TP1 returns the same single full-fraction leg. With
    STALL_EXIT_ENABLED on and plan.stall_exit_day set, a plan still open
    and below +0.5R past that day closes early (_stall_result). v129: a close
    beyond plan.acceptance_close_below closes it first (_acceptance_result);
    stop and target still win any same-bar tie. TP1 touch banks
    tp1_fraction at tp1 and hands the rest to the runner (_runner_leg)."""
    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    n = len(df)
    is_bull = plan.direction == "bullish"
    sign = 1 if is_bull else -1
    stop_loss, tp1 = plan.stop_loss, plan.tp1
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return ExitResult(outcome="no_trade", runner_outcome=None,
                          entry_index=entry_index, exit_index=None,
                          entry_price=entry_price, r_total=0.0, legs=[])
    target_dist = abs(tp1 - entry_price)
    rr = target_dist / risk
    frac1 = plan.tp1_fraction
    frac2 = 1.0 - frac1
    be_trigger = entry_price + sign * plan.breakeven_trigger_fraction * target_dist
    stop_moved = False
    end = min(entry_index + max_holding_days, n - 1)

    # ---- phase 1: identical to the single-leg walk until TP1 touches ----
    tp1_index = None
    for j in range(entry_index + 1, end + 1):
        cur_stop = entry_price if stop_moved else stop_loss
        hit_stop, hit_target, reached_trigger = _bar_hits(
            is_bull, float(high[j]), float(low[j]), cur_stop, tp1, be_trigger)
        if hit_stop:  # conservative: stop first, exactly as single-leg
            return _phase1_stop(entry_index, j, entry_price, cur_stop, stop_moved)
        if hit_target:
            tp1_index = j
            break
        # stop/target above win any tie; acceptance (v129) before stall.
        early = (_acceptance_result(plan, j, float(close[j]), entry_index,
                                    entry_price, sign, risk)
                 or _stall_result(plan, j, float(close[j]), entry_index,
                                  entry_price, sign, risk))
        if early is not None:
            return early
        if reached_trigger and not stop_moved:
            stop_moved = True

    if tp1_index is None:   # timeout before TP1 -- identical to single-leg
        exit_price = float(close[end])
        r = round((exit_price - entry_price) * sign / risk, 3)
        return ExitResult(outcome="timeout", runner_outcome=None,
                          entry_index=entry_index, exit_index=end,
                          entry_price=entry_price, r_total=r,
                          legs=[{"fraction": 1.0, "exit_price": exit_price,
                                 "r": r, "reason": "timeout"}])

    leg1 = {"fraction": frac1, "exit_price": tp1, "r": round(rr, 3), "reason": "tp1"}
    runner_exit, exit_index, runner_reason = _runner_leg(
        df, plan, entry_price, risk, tp1_index, end)
    r2 = round((runner_exit - entry_price) * sign / risk, 3)
    leg2 = {"fraction": frac2, "exit_price": runner_exit, "r": r2,
            "reason": runner_reason}
    return ExitResult(outcome="win", runner_outcome=runner_reason,
                      entry_index=entry_index, exit_index=exit_index,
                      entry_price=entry_price,
                      r_total=round(frac1 * rr + frac2 * r2, 3),
                      legs=[leg1, leg2])
```

The stall exit's pre-v129 inline form computed `r = round(current_r, 3)` from the same expression `_close_exit_result` rounds. `"loss" if r < 0 else "scratch"` is unchanged. So `_stall_result` is byte-identical.

- [ ] **Step 4: Run the new tests, the exit-sim suite and the golden**

Run, in order:
- `python scripts/dev/testrun.py file tests/planning/test_exit_sim_acceptance.py`
- `python scripts/dev/testrun.py file tests/planning/test_exit_sim_single.py`
- `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py`
- `python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py`
- `python scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`

Expected: all pass. Then run `python -m radon cc -s -n C swingbot/core/planning/exit_sim.py`. **Neither walk may be listed** (both < 15 now: about 14 and 12). No new helper may be listed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_acceptance.py
git commit -m "feat(v129): acceptance_exit at the bar close in both exit walks; walks split under C15

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
