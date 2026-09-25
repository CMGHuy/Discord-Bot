# v104 Part 1a — Risk model (worktree branch)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Global Constraints, Review Focus and Parallelisation live in `2026-09-25-v104-structural-stops-and-shorts_0-index.md` and bind every task here.

**Spec:** `docs/superpowers/specs/2026-09-25-v104-structural-stops-and-shorts-design.md` §1.1, §1.3, §2

Work in the worktree `.claude/worktrees/2026-09-25-v104-structural-stops-and-shorts`, on the branch of the same name (`worktree-lifecycle` skill). Create it from `main` at or after the commit that adds this plan.

---

### Task V104-1: `stop_scope` — the scope list and the stop ceiling

**Files:**
- Create: `swingbot/core/planning/stop_scope.py`
- Modify: `swingbot/core/market/strategy_types.py` (add `SHORT_STRATEGIES` after `SR_VOLUME_MULTIPLE`)
- Modify: `swingbot/config.py` (new `Field` directly after the `FIB_LEVEL_STOP_DIRECTIONS` Field)
- Modify: `.env.example` (after the `FIB_LEVEL_STOP_DIRECTIONS=` line)
- Test: `tests/planning/test_stop_scope.py`

**Interfaces:**
- Produces:
  - `strategy_types.SHORT_STRATEGIES: tuple[str, str, str] = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")`
  - `stop_scope.CAP = "cap"`, `stop_scope.DROP = "drop"`
  - `stop_scope.scope_pairs(raw: str | None = None) -> frozenset[tuple[str, str]]`: lower-cased `(strategy, direction)` pairs. `raw=None` reads `config.STRUCTURAL_STOP_SCOPE`.
  - `stop_scope.in_scope(strategy: str, direction: str, raw: str | None = None) -> bool`: always `True` for a `SHORT_STRATEGIES` name.
  - `stop_scope.stop_ceiling(strategy: str, direction: str, horizon_key: str, raw: str | None = None) -> tuple[float, str]`: `(max_risk_pct, DROP)` in scope, otherwise `(capped_planned_loss_pct(max_risk_pct), CAP)`.
  - `stop_scope.plan_stop_ceiling(plan) -> float`: `HARD_MAX_PLANNED_LOSS_PCT` for any `plan.source != "strategy"`, otherwise `stop_ceiling(plan.strategy, plan.direction, plan.horizon_key)[0]`.
  - `config.STRUCTURAL_STOP_SCOPE: str`, default `""`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_stop_scope.py
"""v104 §2.1: which strategy x direction keep structural stops, and their ceiling."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.planning import stop_scope as ss
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT


def test_empty_scope_is_the_two_percent_cap_everywhere():
    for horizon in HORIZONS:
        assert ss.stop_ceiling("Fibonacci", "bullish", horizon, raw="") == (2.0, ss.CAP)


def test_scoped_pair_gets_the_horizon_ceiling_and_drop_mode():
    raw = "Fibonacci:bullish"
    assert ss.stop_ceiling("Fibonacci", "bullish", "4w", raw=raw) == (7.0, ss.DROP)
    assert ss.stop_ceiling("Fibonacci", "bearish", "4w", raw=raw) == (2.0, ss.CAP)
    assert ss.stop_ceiling("MACD", "bullish", "4w", raw=raw) == (2.0, ss.CAP)


def test_parsing_is_forgiving_and_ignores_junk():
    raw = " fibonacci : Bullish ,MACD:bullish,, nonsense ,Support/Resistance:bullish"
    assert ss.scope_pairs(raw) == frozenset({
        ("fibonacci", "bullish"), ("macd", "bullish"), ("support/resistance", "bullish")})


def test_short_strategies_are_always_in_scope():
    for name in SHORT_STRATEGIES:
        assert ss.in_scope(name, "bearish", raw="")
        assert ss.stop_ceiling(name, "bearish", "2m", raw="") == (HORIZONS["2m"]["max_risk_pct"], ss.DROP)


def test_raw_none_reads_config(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "MACD:bullish", raising=False)
    assert ss.in_scope("MACD", "bullish")
    assert not ss.in_scope("MACD", "bearish")


def test_plan_ceiling_is_the_hard_cap_for_non_strategy_plans(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    confluence = SimpleNamespace(source="confluence", strategy="Fibonacci", direction="bullish", horizon_key="4w")
    strategy = SimpleNamespace(source="strategy", strategy="Fibonacci", direction="bullish", horizon_key="4w")
    assert ss.plan_stop_ceiling(confluence) == HARD_MAX_PLANNED_LOSS_PCT
    assert ss.plan_stop_ceiling(strategy) == pytest.approx(7.0)


def test_config_default_is_empty():
    assert config.STRUCTURAL_STOP_SCOPE == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`
Expected: FAIL. The import of `SHORT_STRATEGIES` (and of `stop_scope`) errors.

- [ ] **Step 3: Implement**

In `swingbot/core/market/strategy_types.py`, directly below `SR_VOLUME_MULTIPLE = 1.5 ...`:

```python
# v104 Part B: short-only strategies. Named here (market layer) so both
# market/short_entries.py and planning/stop_scope.py can import them without
# market ever importing planning.
SHORT_STRATEGIES = ("Bull Trap", "Vol Expansion Breakdown", "Earnings Gap Drift")
```

Create `swingbot/core/planning/stop_scope.py`:

```python
"""v104: which strategy x direction keep structural stops, and each one's ceiling.

Out of scope (the default) a stop is CAPPED at the 2% hard cap -- today's
behaviour, byte for byte. In scope the stop keeps its structure up to the
horizon's max_risk_pct and a stop beyond that DROPS the plan; dollar risk is
then bounded by position size, not price distance (spec §2). The builders, the
level lifecycle and the live fill check all read this one module, so backtest
and live cannot disagree about a plan's ceiling.
"""
from __future__ import annotations

from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct

CAP = "cap"
DROP = "drop"
_ALWAYS_IN_SCOPE = frozenset(name.lower() for name in SHORT_STRATEGIES)


def scope_pairs(raw: str | None = None) -> frozenset[tuple[str, str]]:
    """Parse `Strategy:direction` pairs; case/space-insensitive, junk ignored."""
    if raw is None:
        from swingbot import config
        raw = getattr(config, "STRUCTURAL_STOP_SCOPE", "") or ""
    pairs = set()
    for item in str(raw).split(","):
        name, sep, direction = item.rpartition(":")
        if sep and name.strip() and direction.strip():
            pairs.add((name.strip().lower(), direction.strip().lower()))
    return frozenset(pairs)


def in_scope(strategy: str, direction: str, raw: str | None = None) -> bool:
    name = str(strategy).strip().lower()
    if name in _ALWAYS_IN_SCOPE:
        return True
    return (name, str(direction).strip().lower()) in scope_pairs(raw)


def stop_ceiling(strategy: str, direction: str, horizon_key: str,
                 raw: str | None = None) -> tuple[float, str]:
    """(ceiling %, mode): (max_risk_pct, DROP) in scope, else (2% cap, CAP)."""
    max_risk = HORIZONS[horizon_key]["max_risk_pct"]
    if in_scope(strategy, direction, raw):
        return float(max_risk), DROP
    return capped_planned_loss_pct(max_risk), CAP


def plan_stop_ceiling(plan) -> float:
    """The planned-loss ceiling a persisted plan is held to at fill time.

    Confluence plans keep the hard cap: only strategy-source plans can be in
    scope (spec §8 leaves the confluence pipeline out)."""
    if getattr(plan, "source", None) != "strategy":
        return HARD_MAX_PLANNED_LOSS_PCT
    return stop_ceiling(plan.strategy, plan.direction, plan.horizon_key)[0]
```

In `swingbot/config.py`, directly after the `FIB_LEVEL_STOP_DIRECTIONS` Field:

```python
    Field("STRUCTURAL_STOP_SCOPE", "STRUCTURAL_STOP_SCOPE", "Trade Filters & Risk",
          "Structural stops (Strategy:direction list)",
          type="text", default="",
          help="v104. Comma-separated Strategy:direction pairs (e.g. 'Fibonacci:bullish') whose "
               "plans keep their structural stop up to the horizon's max_risk_pct and are sized to "
               "a fixed dollar risk, instead of being capped at the 2% price cap. A stop beyond that "
               "ceiling drops the signal. Empty = every strategy uses the 2% cap. A pair is added "
               "only after its pre-registered 2026 holdout shot passes."),
```

In `.env.example`, directly after `FIB_LEVEL_STOP_DIRECTIONS=`:

```
# v104: Strategy:direction pairs using structural stops + dollar-risk sizing
# (e.g. Fibonacci:bullish). Empty = 2% price cap for every strategy.
STRUCTURAL_STOP_SCOPE=
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`
Expected: PASS (7 passed).
Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: PASS.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/planning/stop_scope.py`. Expected: no output (everything below C).

```bash
git add swingbot/core/planning/stop_scope.py swingbot/core/market/strategy_types.py swingbot/config.py .env.example tests/planning/test_stop_scope.py
git commit -m "feat(v104): stop_scope -- STRUCTURAL_STOP_SCOPE list and stop_ceiling (cap out of scope, drop in scope)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-2: The level lifecycle respects the stop ceiling (Part 0 integrity fix)

**Files:**
- Modify: `swingbot/core/planning/lifecycle.py` (`apply_level_lifecycle`, the `max_risk_amount = ...` line)
- Modify: `swingbot/config.py` (the `LEVEL_LIFECYCLE_STOPS_ENABLED` help text)
- Modify: `docs/claude/known-traps.md` (the "level-lifecycle stop breaches the 2% cap" section, marked fixed)
- Test: `tests/planning/test_lifecycle_ceiling.py`

**Interfaces:**
- Consumes: `stop_scope.stop_ceiling` (V104-1).
- Produces: `apply_level_lifecycle` never widens a stop beyond `stop_ceiling(strategy, direction, horizon_key)[0]` percent of entry.

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_lifecycle_ceiling.py
"""v104 Part 0: lifecycle widening is bounded by the stop ceiling, not max_risk_pct."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.market import levels_lifecycle
from swingbot.core.planning import lifecycle


@pytest.fixture
def tested_anchor(monkeypatch):
    """One tested support at 95.0 behind a 2% stop at 98.0 (entry 100)."""
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(lifecycle, "_lifecycle_levels", lambda *a, **k: ["level"])
    monkeypatch.setattr(levels_lifecycle, "preferred_stop_anchor",
                        lambda levels, direction: SimpleNamespace(price=95.0, state="tested"))


def _apply(scope, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", scope, raising=False)
    return lifecycle.apply_level_lifecycle(
        None, 0, entry=100.0, stop=98.0, tp1=104.0, atr_val=1.0, direction="bullish",
        strategy="Fibonacci", horizon_key="4w", candidate_levels=[112.0])


def test_out_of_scope_never_widens_past_two_percent(tested_anchor, monkeypatch):
    stop, tp1, _ = _apply("", monkeypatch)
    assert (stop, tp1) == (98.0, 104.0)          # 94.75 would be 5.25% > 2%


def test_in_scope_widens_to_the_tested_level(tested_anchor, monkeypatch):
    stop, tp1, meta = _apply("Fibonacci:bullish", monkeypatch)
    assert stop == pytest.approx(94.75)          # 95.0 - 0.25 * ATR
    assert tp1 == 112.0                          # re-selected at 2.29R against the wider risk
    assert meta["lifecycle_stop"]["state"] == "tested"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_lifecycle_ceiling.py`
Expected: `test_out_of_scope_never_widens_past_two_percent` FAILS (the stop widens to 94.75, because the 4w `max_risk_pct` is 7%). The in-scope test passes already.

- [ ] **Step 3: Implement**

In `swingbot/core/planning/lifecycle.py`, add the import next to the other package-relative imports:

```python
from .stop_scope import stop_ceiling
```

In `apply_level_lifecycle`, replace

```python
    max_risk_amount = entry * (h["max_risk_pct"] / 100)
```

with

```python
    # v104 Part 0: bounded by the plan's own stop ceiling. Out of scope that is
    # the 2% hard cap the builders already applied -- widening past it built
    # backtest trades the live fill check cancels (known-traps.md).
    ceiling_pct, _mode = stop_ceiling(strategy, direction, horizon_key)
    max_risk_amount = entry * (ceiling_pct / 100)
```

Then run `grep -n "\bh\[" swingbot/core/planning/lifecycle.py`. If the only remaining use of `h` was the replaced line, delete `h = HORIZONS[horizon_key]` from the function. If the module no longer uses `HORIZONS` at all (`grep -n HORIZONS swingbot/core/planning/lifecycle.py`), remove that import too.

In `swingbot/config.py`, `LEVEL_LIFECYCLE_STOPS_ENABLED` help: replace `"capped by the horizon's max_risk_pct, and re-selects"` with `"capped by the plan's stop ceiling (the 2% hard cap, or the horizon's max_risk_pct for STRUCTURAL_STOP_SCOPE pairs), and re-selects"`.

In `docs/claude/known-traps.md`, under `## The level-lifecycle stop breaches the 2% cap in the backtest`, append:

```markdown

**Fixed by v104 Part 0 (V104-2):** the widening ceiling is now
`stop_scope.stop_ceiling(...)` -- 2% out of scope. Numbers measured before
this fix are not comparable to numbers after it.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_lifecycle_ceiling.py`, then `tests/market/test_levels_lifecycle_wiring.py`, then `tests/backtesting/test_sizing_parity.py`.
Expected: PASS for all three. `test_sizing_parity.py` pins lifecycle off, so it cannot see this change. If `test_levels_lifecycle_wiring.py` fails because it asserted a widening past 2% on an out-of-scope strategy, that assertion encoded the bug: set `STRUCTURAL_STOP_SCOPE` to that test's `strategy:direction` in the test (with `monkeypatch`) so it still exercises widening, and never loosen the assertion. If the right fix is unclear, stop and ask.

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/planning/lifecycle.py`. Expected: `apply_level_lifecycle` at or below its current 12.

```bash
git add swingbot/core/planning/lifecycle.py swingbot/config.py docs/claude/known-traps.md tests/planning/test_lifecycle_ceiling.py
git commit -m "fix(v104): level lifecycle widens only up to the stop ceiling -- closes the backtest-vs-live 2% gap

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-3: Builders cap out of scope and drop in scope

**Files:**
- Modify: `swingbot/core/planning/builders.py` (`_atr_plan`, `_fibonacci_plan`, `_sr_plan`, `_elliott_plan`, plus a new `_bounded_stop`)
- Test: `tests/planning/test_structural_stop_builders.py`

**Interfaces:**
- Consumes: `stop_scope.stop_ceiling`, `stop_scope.DROP` (V104-1).
- Produces: `builders._bounded_stop(entry: float, stop_loss: float, is_bull: bool, strategy: str, direction: str, horizon_key: str) -> float | None`. It returns the stop unchanged within the ceiling, the capped stop when out of scope, or `None` when in scope and beyond the ceiling. Every builder keeps its signature.

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_structural_stop_builders.py
"""v104 §2.2: out of scope the builders cap at 2% (unchanged); in scope they keep
the structural stop up to max_risk_pct and drop beyond it."""
import pytest

from swingbot import config
from swingbot.core.planning import builders as b
from swingbot.core.planning.targets import atr_target_candidates


@pytest.fixture
def rr(monkeypatch):
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)


def _scope(monkeypatch, raw):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", raw, raising=False)


def test_fibonacci_out_of_scope_is_capped_at_two_percent(rr, monkeypatch):
    _scope(monkeypatch, "")
    stop, _ = b._fibonacci_plan(100.0, 1.0, 120.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(98.0)


def test_fibonacci_in_scope_keeps_the_swing_stop(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bullish")
    stop, tp1 = b._fibonacci_plan(100.0, 1.0, 120.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(94.75)          # 95 - 0.25 ATR = 5.25% <= 7%
    assert tp1 == 110.0                          # 10 / 5.25 = 1.90R


def test_fibonacci_in_scope_beyond_the_ceiling_drops(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bullish")
    assert b._fibonacci_plan(100.0, 1.0, 120.0, 90.0, "bullish", "4w", candidate_levels=[130.0]) is None


def test_atr_plan_in_scope_keeps_two_atr(rr, monkeypatch):
    cands = atr_target_candidates(100.0, 3.0, "bullish")
    _scope(monkeypatch, "")
    assert b._atr_plan(100.0, 3.0, "bullish", "4w", "MACD", candidate_levels=cands)[0] == pytest.approx(98.0)
    _scope(monkeypatch, "MACD:bullish")
    assert b._atr_plan(100.0, 3.0, "bullish", "4w", "MACD", candidate_levels=cands)[0] == pytest.approx(94.0)


def test_sr_plan_in_scope_uses_sr_stop_pct(rr, monkeypatch):
    _scope(monkeypatch, "")
    assert b._sr_plan(100.0, 2.0, "bullish", "2m", candidate_levels=[115.0])[0] == pytest.approx(98.0)
    _scope(monkeypatch, "Support/Resistance:bullish")
    stop, tp1 = b._sr_plan(100.0, 2.0, "bullish", "2m", candidate_levels=[115.0])
    assert stop == pytest.approx(92.0) and tp1 == 115.0


def test_elliott_in_scope_keeps_the_wave_two_stop(rr, monkeypatch):
    _scope(monkeypatch, "Elliott Wave:bullish")
    stop, _ = b._elliott_plan(100.0, 1.0, 95.0, "bullish", "4w", candidate_levels=[110.0])
    assert stop == pytest.approx(94.75)


def test_bearish_mirror_in_scope(rr, monkeypatch):
    _scope(monkeypatch, "Fibonacci:bearish")
    stop, _ = b._fibonacci_plan(100.0, 1.0, 105.0, 80.0, "bearish", "4w", candidate_levels=[90.0])
    assert stop == pytest.approx(105.25)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_structural_stop_builders.py`
Expected: the in-scope tests FAIL (still capped at 98.0 / 102.0); the out-of-scope ones pass.

- [ ] **Step 3: Implement**

In `swingbot/core/planning/builders.py`, add the import beside the `risk_limits` import:

```python
from .stop_scope import DROP, stop_ceiling
```

Add this helper directly above `_atr_plan`:

```python
def _bounded_stop(entry, stop_loss, is_bull, strategy, direction, horizon_key):
    """v104 §2.2: the stop within its ceiling, capped (out of scope) or None
    (in scope, drop-don't-cap). The capped arithmetic is exactly the old
    `entry -/+ entry * (capped_pct / 100)` so out-of-scope floats are identical."""
    ceiling_pct, mode = stop_ceiling(strategy, direction, horizon_key)
    max_risk_amount = entry * (ceiling_pct / 100)
    if abs(entry - stop_loss) <= max_risk_amount:
        return stop_loss
    if mode == DROP:
        return None
    return entry - max_risk_amount if is_bull else entry + max_risk_amount
```

`_atr_plan`: replace

```python
    max_risk_amount = entry * (capped_planned_loss_pct(h["max_risk_pct"]) / 100)
    if risk_distance > max_risk_amount:
        risk_distance = max_risk_amount
    stop_loss = entry - risk_distance if is_bull else entry + risk_distance
```

with

```python
    stop_loss = entry - risk_distance if is_bull else entry + risk_distance
    stop_loss = _bounded_stop(entry, stop_loss, is_bull, strategy, direction, horizon_key)
    if stop_loss is None:
        return None
```

In the docstring, change `` `strategy` is accepted but unused `` to `` `strategy` selects the stop ceiling (v104 stop_scope) ``.

`_fibonacci_plan`: in the `else:` branch, replace

```python
        buffer = STRUCTURE_BUFFER_ATR * atr_val
        stop_loss = swing_low - buffer if is_bull else swing_high + buffer
        max_risk_amount = entry * (capped_planned_loss_pct(h["max_risk_pct"]) / 100)
        if abs(entry - stop_loss) > max_risk_amount:
            stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount
```

with

```python
        buffer = STRUCTURE_BUFFER_ATR * atr_val
        stop_loss = _bounded_stop(entry, swing_low - buffer if is_bull else swing_high + buffer,
                                  is_bull, "Fibonacci", direction, horizon_key)
        if stop_loss is None:
            return None
```

`_sr_plan`: replace

```python
    stop_pct = capped_planned_loss_pct(h["sr_stop_pct"])
```

with

```python
    # min(sr_stop_pct, ceiling) is exactly capped_planned_loss_pct out of scope
    # (ceiling 2.0), and sr_stop_pct itself in scope (sr_stop_pct == max_risk_pct
    # in every horizon, so it never needs dropping).
    stop_pct = min(float(h["sr_stop_pct"]), stop_ceiling("Support/Resistance", direction, horizon_key)[0])
```

`_elliott_plan`: replace

```python
    stop_loss = wave2 - buffer if is_bull else wave2 + buffer

    max_risk_amount = entry * (capped_planned_loss_pct(h["max_risk_pct"]) / 100)
    if abs(entry - stop_loss) > max_risk_amount:
        stop_loss = entry - max_risk_amount if is_bull else entry + max_risk_amount
```

with

```python
    stop_loss = _bounded_stop(entry, wave2 - buffer if is_bull else wave2 + buffer,
                              is_bull, "Elliott Wave", direction, horizon_key)
    if stop_loss is None:
        return None
```

Then `grep -n "capped_planned_loss_pct" swingbot/core/planning/builders.py`. `_level_stop_or_none` still uses it, so keep the import. Remove any `h = HORIZONS[horizon_key]` line that is left unused in `_elliott_plan` or `_sr_plan` (`_sr_plan` still reads `h["sr_stop_pct"]`, so keep it there).

- [ ] **Step 4: Run the tests to verify they pass**

Run each with `python scripts/dev/testrun.py file <path>`:
- `tests/planning/test_structural_stop_builders.py`: PASS (7 passed).
- `tests/backtesting/test_sizing_parity.py`, `tests/planning/test_plan_engine_sizing.py`, `tests/planning/test_build_strategy_plan.py`, `tests/planning/test_fib_level_stop_builder.py`, `tests/planning/test_fib_continuation_builder.py`, `tests/planning/test_opex_stop_size.py`: PASS unchanged. These pin the out-of-scope arithmetic; any failure there means float identity broke (Review Focus 1).

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py`. Expected: nothing at or above 15, and `build_strategy_plan` still 13.

```bash
git add swingbot/core/planning/builders.py tests/planning/test_structural_stop_builders.py
git commit -m "feat(v104): builders read stop_ceiling -- cap at 2% out of scope, structural stop or drop in scope

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-4: The live fill check uses the plan's ceiling

**Files:**
- Modify: `swingbot/core/planning/plan_manager.py` (`_step_pending` risk check; `_warn_legacy_open_risk`)
- Test: `tests/planning/test_plan_manager_stop_ceiling.py`

**Interfaces:**
- Consumes: `stop_scope.plan_stop_ceiling` (V104-1).
- Produces: `cancelled_risk_cap` fires when a fill's planned loss exceeds `plan_stop_ceiling(plan)`. Its `detail["max_planned_loss_pct"]` carries that ceiling.

- [ ] **Step 1: Write the failing tests**

```python
# tests/planning/test_plan_manager_stop_ceiling.py
"""v104 §2.3: pending fills are checked against the plan's own stop ceiling."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending


def _poll(tmp_path, monkeypatch, scope, **plan_kw):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", scope, raising=False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", 106.0)]))
    store.add(_pending(**plan_kw))
    return store, mgr.poll()


def test_in_scope_fill_within_max_risk_pct_fills(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=99.0)   # 6.6%, 4w ceiling 7%
    assert [e.transition for e in events] == ["filled"]
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_in_scope_fill_beyond_max_risk_pct_cancels_at_that_ceiling(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=95.0)       # 10.4%
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(7.0)


def test_out_of_scope_keeps_the_two_percent_cap(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, "", stop_loss=99.0)
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(2.0)


def test_confluence_plans_are_never_in_scope(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, "Fibonacci:bullish", stop_loss=99.0, source="confluence")
    assert [e.transition for e in events] == ["cancelled_risk_cap"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_stop_ceiling.py`
Expected: `test_in_scope_fill_within_max_risk_pct_fills` and the 7.0 assertion FAIL.

- [ ] **Step 3: Implement**

In `swingbot/core/planning/plan_manager.py`, add the import:

```python
from swingbot.core.planning.stop_scope import plan_stop_ceiling
```

In `_step_pending`, replace

```python
            risk_pct = planned_loss_pct(fill, plan.stop_loss)
            if risk_pct > HARD_MAX_PLANNED_LOSS_PCT:
```

with

```python
            risk_pct = planned_loss_pct(fill, plan.stop_loss)
            ceiling_pct = plan_stop_ceiling(plan)
            if risk_pct > ceiling_pct:
```

and in the same event detail replace `"max_planned_loss_pct": HARD_MAX_PLANNED_LOSS_PCT,` with `"max_planned_loss_pct": ceiling_pct,`.

In `_warn_legacy_open_risk`, replace

```python
        if risk_pct <= HARD_MAX_PLANNED_LOSS_PCT or plan.plan_id in self._risk_cap_warned:
```

with

```python
        ceiling_pct = plan_stop_ceiling(plan)
        if risk_pct <= ceiling_pct or plan.plan_id in self._risk_cap_warned:
```

and in its `log.warning(...)` argument list replace `HARD_MAX_PLANNED_LOSS_PCT` with `ceiling_pct`.

Then `grep -n HARD_MAX_PLANNED_LOSS_PCT swingbot/core/planning/plan_manager.py`. If nothing is left, drop it from the `risk_limits` import (keep `planned_loss_pct`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_stop_ceiling.py`, then `tests/planning/test_plan_manager_pending.py`, then `tests/planning/test_plan_manager_fills.py`.
Expected: PASS for all three (the existing `planned_loss_pct == 10.3774` test is out of scope and unchanged).

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/planning/plan_manager.py | grep -E "_step_pending|_warn_legacy"`. Expected: no output (both below C).

```bash
git add swingbot/core/planning/plan_manager.py tests/planning/test_plan_manager_stop_ceiling.py
git commit -m "feat(v104): pending-fill risk check uses the plan's stop ceiling (confluence keeps the hard cap)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-5: Fail-closed dollar-risk sizing, and `run_strategy_pass` split below CC 15

**Files:**
- Modify: `swingbot/core/planning/stop_scope.py` (append `risk_sizing_ok`)
- Modify: `swingbot/core/scanning/strategy_pass.py` (extract `_PassDeps`, `_regime_for`, `_rs_blocked`, `_open_trade`, `_emit_signal`; add `PassResult.sizing_blocked`)
- Test: `tests/planning/test_stop_scope.py` (append), `tests/scanning/test_strategy_pass_emit.py` (new)

**Interfaces:**
- Consumes: `stop_scope.in_scope` (V104-1); `account.compute_position_size(entry, stop_loss) -> dict | None`. Its dict keys used here are `mode`, `risk_amount`, `balance` and `risk_pct`; all modes except `account_pct` resolve to `mode == "risk_pct"`.
- Produces:
  - `stop_scope.risk_sizing_ok(plan, sizing_fn=None) -> bool`: `True` for an out-of-scope plan. For an in-scope plan, `True` only when sizing is risk-based and within budget.
  - `strategy_pass._emit_signal(result, frame, *, ticker, strategy, direction, horizon, bar_date, regime, deps) -> None`
  - `strategy_pass.PassResult.sizing_blocked: int`
  - `run_strategy_pass`'s signature is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/planning/test_stop_scope.py`:

```python
# --- v104 §2.4 real-money invariant ------------------------------------------

def _plan(strategy="Fibonacci", direction="bullish", entry=100.0, stop=91.0):
    return SimpleNamespace(strategy=strategy, direction=direction, trigger_price=entry, stop_loss=stop)


def _sizing(mode="risk_pct", balance=10_000.0, risk_pct=1.0, risk_amount=None, entry=100.0, stop=91.0):
    if risk_amount is None:
        risk_amount = balance * risk_pct / 100
    return {"mode": mode, "balance": balance, "risk_pct": risk_pct, "risk_amount": risk_amount,
            "shares": risk_amount / abs(entry - stop)}


def test_out_of_scope_plans_are_never_blocked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    assert ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: None)


def test_in_scope_risk_pct_sizing_passes(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: _sizing())


def test_risk_sizing_fails_closed_on_account_pct(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: _sizing(mode="account_pct"))


def test_risk_sizing_fails_closed_when_sizing_is_unavailable(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    def boom(entry, stop):
        raise OSError("account file unreadable")
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: None)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=boom)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: _sizing(risk_amount=0.0))


def test_risk_sizing_fails_closed_over_budget(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "Fibonacci:bullish", raising=False)
    assert not ss.risk_sizing_ok(_plan(), sizing_fn=lambda e, s: _sizing(risk_amount=450.0))


def test_shorts_are_always_checked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    short = _plan(strategy=SHORT_STRATEGIES[0], direction="bearish", stop=109.0)
    assert not ss.risk_sizing_ok(short, sizing_fn=lambda e, s: _sizing(mode="account_pct"))
```

Create `tests/scanning/test_strategy_pass_emit.py`:

```python
"""v104 §2.4: an in-scope plan without risk-based sizing is neither stored nor posted."""
from types import SimpleNamespace

import pytest

from swingbot.core.scanning import strategy_pass as sp


class _Store:
    def __init__(self):
        self.plans = []

    def all(self):
        return list(self.plans)

    def add(self, plan):
        self.plans.append(plan)


class _Log:
    def __init__(self):
        self.logged = []

    def open_trade_for_ticker(self, ticker):
        return None

    def log_trade(self, **kw):
        self.logged.append(kw)


def _plan():
    return SimpleNamespace(plan_id="p1", source="strategy", strategy="Fibonacci", direction="bullish",
                           horizon_key="4w", trigger_price=100.0, stop_loss=94.0, tp1=110.0, tp2=None,
                           badge="WEAK", quality_score=0, cohort_label="COHORT_UNKNOWN", cohort_stats={},
                           risk_features={}, ledger="weak", entry_context={}, ticker="AAPL")


@pytest.fixture
def deps():
    return sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="live", live_allow=set(),
                        rs_combined_of=lambda t: None, asof_of=None)


def _emit(deps, monkeypatch, sizing_ok):
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *a, **k: _plan())
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: sizing_ok)
    monkeypatch.setattr(sp, "build_strategy_alert_embed", lambda plan: "embed")
    result = sp.PassResult()
    sp._emit_signal(result, None, ticker="AAPL", strategy="Fibonacci", direction="bullish",
                    horizon="4w", bar_date="2026-09-25", regime=None, deps=deps)
    return result


def test_sizing_failure_blocks_store_trade_and_alert(deps, monkeypatch):
    result = _emit(deps, monkeypatch, sizing_ok=False)
    assert result.sizing_blocked == 1
    assert deps.plan_store.plans == [] and deps.trade_log.logged == [] and result.alerts == []


def test_sizing_ok_opens_the_trade_and_alerts(deps, monkeypatch):
    result = _emit(deps, monkeypatch, sizing_ok=True)
    assert result.opened == 1 and len(result.alerts) == 1 and len(deps.plan_store.plans) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py` (FAIL: `risk_sizing_ok` is missing), then `tests/scanning/test_strategy_pass_emit.py` (FAIL: `_PassDeps` is missing).

- [ ] **Step 3: Implement**

Append to `swingbot/core/planning/stop_scope.py`:

```python
def risk_sizing_ok(plan, sizing_fn=None) -> bool:
    """v104 §2.4 real-money invariant, fail-closed.

    An in-scope plan may carry a stop up to max_risk_pct (11% on 9m). The
    partner places real orders at the ticket's share count, so that count must
    come from risk-based sizing: shares x |entry - stop| <= the risk budget.
    Anything else -- account_pct sizing, no sizing, an exception, zero risk,
    over budget -- returns False and the plan must not be stored or posted.
    Out-of-scope plans return True: their path is unchanged."""
    if not in_scope(plan.strategy, plan.direction):
        return True
    if sizing_fn is None:
        from swingbot.core.planning.account import compute_position_size as sizing_fn
    try:
        sizing = sizing_fn(plan.trigger_price, plan.stop_loss)
    except Exception:
        return False
    if not sizing or sizing.get("mode") != "risk_pct":
        return False
    risk_amount = float(sizing.get("risk_amount") or 0.0)
    budget = float(sizing.get("balance") or 0.0) * float(sizing.get("risk_pct") or 0.0) / 100.0
    return 0.0 < risk_amount <= budget + 0.01
```

In `swingbot/core/scanning/strategy_pass.py`:

1. Add the import: `from swingbot.core.planning.stop_scope import risk_sizing_ok`.
2. Add `sizing_blocked: int = 0` as the last field of `PassResult`.
3. Replace everything from `def run_strategy_pass(` to the end of the file with:

```python
@dataclass
class _PassDeps:
    """The collaborators one strategy pass threads through every signal."""
    plan_store: object
    trade_log: object
    mode: str
    live_allow: set
    rs_combined_of: object
    asof_of: object = None


def _regime_for(regimes, frame):
    if regimes is None:
        return None
    # Lazy import avoids scan engine's analyze <-> engine import cycle.
    from swingbot.core.scanning import analyze
    return analyze._regime_at(regimes, frame.index[-1])


def _rs_blocked(ticker: str, direction: str, rs_combined_of) -> bool:
    """The live v93 laggard rule for bearish signals (unchanged behaviour)."""
    if direction != "bearish":
        return False
    rs_value = rs_combined_of(ticker)
    verdict = rs_verdict(ticker, direction, rs_value if rs_value is not None else 50.0,
                         rs_available=rs_value is not None)
    return verdict["status"] == "block"


def _open_trade(deps: _PassDeps, plan, *, ticker, strategy, horizon, direction) -> None:
    deps.trade_log.log_trade(ticker=ticker, strategy=strategy, horizon_key=horizon, direction=direction,
                             confidence_level=None, confidence_label="strategy signal", entry=plan.trigger_price,
                             stop_loss=plan.stop_loss, take_profit=plan.tp1, target2=plan.tp2,
                             plan_id=plan.plan_id, badge=plan.badge, quality_score=plan.quality_score,
                             source=plan.source, cohort_label=plan.cohort_label,
                             cohort_stats=plan.cohort_stats, risk_features=plan.risk_features,
                             ledger=plan.ledger, entry_context=plan.entry_context)


def _emit_signal(result: PassResult, frame, *, ticker, strategy, direction, horizon,
                 bar_date, regime, deps: _PassDeps) -> None:
    """One fired signal -> a stored plan, plus a live trade and alert when eligible."""
    if already_emitted(deps.plan_store, ticker, strategy, horizon, bar_date):
        result.skipped_dup += 1
        return
    if _rs_blocked(ticker, direction, deps.rs_combined_of):
        result.rs_blocked += 1
        return
    plan = build_strategy_plan_at(frame, ticker=ticker, strategy=strategy, horizon_key=horizon,
                                  direction=direction, regime2_state=regime,
                                  asof=deps.asof_of(ticker) if deps.asof_of else None)
    if plan is None:
        return
    if not risk_sizing_ok(plan):
        log.error("strategy pass: %s %s %s %s uses structural stops but has no risk-based sizing "
                  "-- not stored, not posted (v104 fail-closed)", ticker, strategy, horizon, direction)
        result.sizing_blocked += 1
        return
    deps.plan_store.add(plan)
    result.plans.append(plan)
    goes_live = deps.mode == "live" and (not deps.live_allow or strategy in deps.live_allow)
    if not goes_live or deps.trade_log.open_trade_for_ticker(ticker) is not None:
        result.stored_only += 1
        return
    _open_trade(deps, plan, ticker=ticker, strategy=strategy, horizon=horizon, direction=direction)
    result.opened += 1
    result.alerts.append((build_strategy_alert_embed(plan), None, plan, simple_line(plan)))


def run_strategy_pass(tickers, fresh_data, *, now, horizons, spy_df, regimes,
                      rs_combined_of, mode: str, live_allow: set, trade_log, plan_store, asof_of=None) -> PassResult:
    """Build strategy plans after confluence; only eligible live plans open trades."""
    result = PassResult()
    deps = _PassDeps(plan_store, trade_log, mode, live_allow, rs_combined_of, asof_of)
    for ticker in tickers:
        raw = fresh_data.get(ticker)
        if raw is None or len(raw) == 0:
            continue
        try:
            frame = completed_frame(raw, now)
            if frame is None or len(frame) == 0:
                continue
            bar_date = frame.index[-1].date().isoformat()
            regime = _regime_for(regimes, frame)
            for horizon in horizons:
                for strategy, direction in strategy_signals(frame, horizon, spy_df=spy_df):
                    _emit_signal(result, frame, ticker=ticker, strategy=strategy, direction=direction,
                                 horizon=horizon, bar_date=bar_date, regime=regime, deps=deps)
        except Exception:
            log.warning("strategy pass: %s failed -- continuing", ticker, exc_info=True)
    return result
```

4. Check that `scan_run.py` does not read a `PassResult` field this changes: `grep -n "PassResult\|result\.\(opened\|stored_only\|rs_blocked\|skipped_dup\)" swingbot/core/scanning/scan_run.py`. Adding a field is backwards compatible; nothing else changes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py` (PASS, 13), `tests/scanning/test_strategy_pass_emit.py` (PASS, 2), then `tests/scanning/test_strategy_pass_frame.py` and `tests/scanning/test_strategy_pass_signals.py` (PASS, unchanged).

- [ ] **Step 5: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/scanning/strategy_pass.py swingbot/core/planning/stop_scope.py`.
Expected: no function at or above 15. `run_strategy_pass` was 20 and must now be below 15. Paste the radon line for it into the commit body.

```bash
git add swingbot/core/planning/stop_scope.py swingbot/core/scanning/strategy_pass.py tests/planning/test_stop_scope.py tests/scanning/test_strategy_pass_emit.py
git commit -m "feat(v104): fail-closed dollar-risk sizing for in-scope plans; run_strategy_pass split below CC 15

<radon line for run_strategy_pass here>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V104-6: `fib_funnel.py` → `funnel.py`, with fold years and a date guard

**Files:**
- Rename: `scripts/backtest/fib_funnel.py` → `scripts/backtest/funnel.py`
- Rename: `tests/scripts/test_fib_funnel.py` → `tests/scripts/test_funnel.py`
- Modify: `scripts/backtest/measure_fib_confluence.py` (imports lines 44–48), `scripts/backtest/measure_fib_v103.py` (lines 18–19 and every `fib_funnel.`)
- Test: `tests/scripts/test_funnel.py` (append)

**Interfaces:**
- Produces, in addition to every existing name unchanged:
  - `funnel.stage2(rows_by_cell, direction, grid, fold_years=FOLD_YEARS)`
  - `funnel.fixed_folds(rows, fold_years) -> list[dict]`: one `{"test_year", "tol": "fixed", "stats"}` per year, for a single arm with no grid (Part A).
  - `funnel.assert_rows_before(rows, last_date: str) -> None`: raises `SystemExit` when any `row["entry_date"] > last_date`.

- [ ] **Step 1: Rename and write the failing tests**

```bash
git mv scripts/backtest/fib_funnel.py scripts/backtest/funnel.py
git mv tests/scripts/test_fib_funnel.py tests/scripts/test_funnel.py
```

In `tests/scripts/test_funnel.py`, change `import fib_funnel as funnel  # noqa: E402` to `import funnel  # noqa: E402`. Then append:

```python
def test_stage2_accepts_custom_fold_years():
    rows = [_row(f"T{i}", "win", 1.0, year=str(year)) for year in range(2010, 2026) for i in range(40)]
    by_cell = {funnel.cell_key(0.5): rows}
    result = funnel.stage2(by_cell, "bullish", (0.5,), fold_years=tuple(range(2013, 2026)))
    assert [fold["test_year"] for fold in result["folds"]] == list(range(2013, 2026))


def test_fixed_folds_score_one_arm_per_year():
    rows = [_row("A", "win", 1.0, year="2014")] * 16 + [_row("B", "loss", -1.0, year="2015")] * 16
    folds = funnel.fixed_folds(rows, (2014, 2015, 2016))
    assert [f["tol"] for f in folds] == ["fixed"] * 3
    assert folds[0]["stats"]["n"] == 16 and folds[2]["stats"]["n"] == 0
    verdict = funnel.fold_verdict(folds)
    assert verdict["qualifying"] == 2 and verdict["positive"] == 1


def test_assert_rows_before_refuses_a_future_row():
    funnel.assert_rows_before([_row("A", "win", 1.0, year="2025")], "2025-12-31")
    import pytest
    with pytest.raises(SystemExit):
        funnel.assert_rows_before([_row("A", "win", 1.0, year="2026")], "2025-12-31")
```

The existing `_row(ticker, outcome, value, year="2015", direction="bullish")` helper at the top of the file must produce an `entry_date` of `f"{year}-06-01"`. Check it with `grep -n "entry_date" tests/scripts/test_funnel.py`. If it uses another day, keep that day: only the year matters above.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_funnel.py`
Expected: the three new tests FAIL (`stage2` has no `fold_years`; `fixed_folds` and `assert_rows_before` are missing). The old ones pass.

- [ ] **Step 3: Implement**

In `scripts/backtest/funnel.py`:
- Docstring line 1 becomes `"""Grid-agnostic measurement funnel shared by v102, v103 and v104."""`.
- Replace `stage2` with:

```python
def stage2(rows_by_cell, direction, grid, fold_years=FOLD_YEARS):
    folds = []
    for year in fold_years:
        value = fold_pick(rows_by_cell, direction, year, grid)
        stats = pooled(dir_rows(year_rows(rows_by_cell[cell_key(value)], year, year), direction)) if value is not None else None
        folds.append({"test_year": year, "tol": value, "stats": stats})
    return {"folds": folds, "verdict": fold_verdict(folds)}
```

- Append:

```python
def fixed_folds(rows, fold_years):
    """Per-year stats for one fixed arm (no grid, so nothing to re-select)."""
    return [{"test_year": year, "tol": "fixed", "stats": pooled(year_rows(rows, year, year))}
            for year in fold_years]


def assert_rows_before(rows, last_date):
    """Refuse any row entered after `last_date` -- the holdout is read by Stage 3 only."""
    late = [row["entry_date"] for row in rows if row["entry_date"] > last_date]
    if late:
        raise SystemExit(f"{len(late)} row(s) after {last_date} (first {min(late)}): holdout leak refused")
```

`pooled([])` must return `n == 0` for an empty year. Confirm with `grep -n "def pooled_stats" -A 12 swingbot/core/backtesting/arm_rule.py`. If it returns `n: 0` for an empty list (expected), nothing else is needed.

In `scripts/backtest/measure_fib_confluence.py`, replace every `from fib_funnel import` with `from funnel import` (lines 44–48). In `scripts/backtest/measure_fib_v103.py`, replace `import fib_funnel` with `import funnel as fib_funnel`, and `from fib_funnel import` with `from funnel import`. The alias keeps every call site in that closed script untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_funnel.py` (PASS), then `git grep -ln "measure_fib_v103\|measure_fib_confluence" -- tests` and run each file listed (PASS, unchanged).
Run: `git grep -n "fib_funnel" -- scripts tests swingbot`. Expected: only the alias line in `measure_fib_v103.py`.

- [ ] **Step 5: Commit, then run the fast tier (end of Part 1a)**

```bash
git add scripts/backtest/funnel.py scripts/backtest/measure_fib_confluence.py scripts/backtest/measure_fib_v103.py tests/scripts/test_funnel.py
git commit -m "refactor(v104): fib_funnel -> funnel (v102/v103 unchanged), with fold_years, fixed_folds and a holdout date guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Run: `python scripts/dev/testrun.py fast`. Expected: `0 failed`, `0 xfailed`. A failure in code this part touched is fixed before Part 1b starts. For a failure elsewhere, check it in isolation (`testrun.py file <path>`) and report it with both outputs.
