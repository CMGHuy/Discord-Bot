# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 1: foundations and replay

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V192-4:" -A 300 <this file>`.

**Scope of this part (V192-1..V192-7):** the worktree and the flag-off goldens captured on unmodified code; the two knobs with their `ScanParams` slots, reachability rows, the load/reload coupling and the `apply_knobs` guard; the three plan fields; the pure `gap_reclaim` rule module; builders building waiting market plans; the replay next-open market fill with its fill-bar check, hold cap and observer; the veto branch.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (created in V192-1, Step 1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`. Never edit the main tree's files from a task.

**Dirty main tree:** the main checkout may carry unrelated uncommitted edits (`tests/conftest.py`, `CLAUDE.md`, skills, `version_history.json`). The worktree is branched from `main`'s HEAD and never sees them; leave them alone.

**Complexity:** after every code task run `python scripts/dev/complexity_gate.py`; it must pass (index § Global Constraints).

---

# Phase 1 — Worktree and the flag-off goldens

### Task V192-1: Worktree; flag-off golden (replay results, arm rows, plan dicts)
**Model:** sonnet — two new test modules following the v139/v191 golden pattern; the only judgement is capturing before any code change.

**Files:**
- Create: `tests/backtesting/arms/test_v192_flag_off_golden.py`
- Create: `tests/fixtures/v192/replay_golden.json` (written by the test's capture path, never by hand)
- Create: `tests/planning/test_v192_plan_golden.py`
- Create: `tests/fixtures/v192/plan_golden.json` (same)

**Interfaces:**
- Consumes (all exist today): `simulate_exit(df, i, plan, *, scale_out=)` (`swingbot/core/planning/exit_sim.py:848`), `run_arm(ticker, df, engine_ids, horizons, signal_window, delta)` (`swingbot/core/backtesting/arms/engine.py:31`), `load_v74_fixture()` (`tests/backtesting/test_v74_fixture.py:10`), `_plan(**kw)` (`tests/planning/test_plan_engine_model.py:6`), `make_ohlcv(rows, *, start=, spread=)` (`tests/helpers.py:10`), `PLAN_SHAPES` (`swingbot/core/planning/params.py`), `TURTLE_SOUP` (`swingbot/core/market/strategy_types.py`), `build_confluence_plan` / `build_strategy_plan` (`swingbot/core/planning/builders.py:645`, `:411`), `ALL_STRATEGIES` (`swingbot/core/backtesting/backtest.py:788`), `plan_to_dict` (`swingbot/core/planning/plan_types.py`), `config.FIELDS`, `config._cast`.
- Produces: the branch and worktree `2026-10-24-v192-gap-toward-stop-reclaim`; two golden fixtures every later task keeps green. **Never regenerate either fixture to make a test pass** — a diff against them is a behaviour change with both knobs off, which this plan forbids.

Why this comes first: every later code task edits code these goldens pin (`exit_sim.py`, `builders.py`, `plan_types.py`, `knobs.py`). The fixtures must be written by unmodified `main` code, so this task changes no file under `swingbot/`.

Both modules pin **every searchable knob to its shipped default** (autouse fixture), so a `.env` found by the upward dotenv search can never move the capture; from V192-2 on, `MARKET_ENTRY_NEXT_OPEN` and `GAP_RECLAIM_ATR` are searchable and get pinned to `False` / `0.0` here automatically.

- [ ] **Step 1: Create the worktree** (skill `worktree-lifecycle`; run from the main tree)

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git worktree add .claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim -b 2026-10-24-v192-gap-toward-stop-reclaim main
git -C .claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim log --oneline -1
```

Expected: the new branch at `main`'s HEAD (the v192 part commits or later). Every command from here on runs inside that worktree.

- [ ] **Step 2: Write the replay golden test** — `tests/backtesting/arms/test_v192_flag_off_golden.py`

Two captures. `exits`: `dataclasses.asdict(ExitResult)` for hand-built plans of every entry family the spec names — market strategy (bull and bear, scale-out and single-leg), market confluence (scale-out, both directions), a market plan with a hold cap, stop-entry, limit and the v180 Turtle Soup next-open plan — on a deterministic wave whose opens differ from the prior close (so a next-open fill would show). Market plans are built **ACTIVE with `entry_price = trigger_price`**, exactly what the builders produce today. `arms`: the `ArmTrade` rows of `run_arm` for both engines on the v74 AAPL fixture. The capture path writes the fixture only when it is **missing** and `V192_CAPTURE_GOLDEN=1` is set, so it can never overwrite a committed golden.

```python
"""v192 flag-off parity (spec § Testing, first bullet): with
MARKET_ENTRY_NEXT_OPEN off and GAP_RECLAIM_ATR at 0 the replay fills and exits
market, stop-entry, limit and v180 Turtle Soup plans exactly as it did before
v192 touched exit_sim.py, builders.py or knobs.py, and run_arm returns the same
ArmTrade rows for both engines. Captured at V192-1, before any v192 code change
-- never regenerate it to make this pass."""
import dataclasses
import json
import math
import os
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "v192" / "replay_golden.json"
WINDOW = ("1900-01-01", "2100-12-31")
SIGNALS = range(20, 141, 15)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    """Every searchable knob at its shipped default (the v192 knobs included once they exist)."""
    for f in config.FIELDS:
        if f.search_class == "searchable":
            monkeypatch.setattr(config, f.attr, config._cast(f, f.default), raising=False)


def _wave(n=170):
    rows, prev = [], 100.0
    for i in range(n):
        close = 100.0 + 6.0 * math.sin(i / 5.0) + 0.03 * i
        open_ = prev + 0.4 * math.sin(i * 1.7)
        rows.append((round(open_, 4), round(max(open_, close) + 0.8, 4),
                     round(min(open_, close) - 0.8, 4), round(close, 4)))
        prev = close
    return make_ohlcv(rows, start="2024-01-02")


def _market(c, direction, **kw):
    sign = 1 if direction == "bullish" else -1
    base = dict(direction=direction, entry_type="market", trigger_price=c, entry_price=c,
                status=PlanStatus.ACTIVE, stop_loss=c * (1 - sign * 0.03),
                tp1=c * (1 + sign * 0.04), tp2=c * (1 + sign * 0.08), tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _turtle(c):
    shape = PLAN_SHAPES[TURTLE_SOUP]
    return _plan(strategy=TURTLE_SOUP, horizon_key="2w", direction="bullish",
                 entry_type=shape["entry_type"], expiry_bars=shape["expiry_bars"],
                 tp1_fraction=shape["tp1_fraction"],
                 breakeven_trigger_fraction=shape["breakeven_trigger_fraction"],
                 hold_cap_bars=shape["hold_cap_bars"], trigger_price=c,
                 stop_loss=c * 0.98, tp1=c * 1.04, tp2=None)


def _plans(c):
    """name -> (plan, scale_out) for one signal close c."""
    return {
        "mkt_strategy_bull_so": (_market(c, "bullish"), True),
        "mkt_strategy_bull_single": (_market(c, "bullish"), False),
        "mkt_strategy_bear_so": (_market(c, "bearish"), True),
        "mkt_confluence_bull_so": (_market(c, "bullish", source="confluence",
                                           strategy="S/R Confluence"), True),
        "mkt_confluence_bear_so": (_market(c, "bearish", source="confluence",
                                           strategy="S/R Confluence"), True),
        "mkt_hold_cap_bull": (_market(c, "bullish", hold_cap_bars=5), True),
        "stop_entry_bull": (_plan(entry_type="stop_entry", trigger_price=c * 1.01,
                                  stop_loss=c * 0.97, tp1=c * 1.05, tp2=c * 1.09,
                                  expiry_bars=3), True),
        "limit_bull": (_plan(entry_type="limit", trigger_price=c * 0.99, stop_loss=c * 0.96,
                             tp1=c * 1.03, tp2=None, tp1_fraction=1.0, expiry_bars=1), True),
        "turtle_soup": (_turtle(c), True),
    }


def _exits():
    df = _wave()
    out = []
    for i in SIGNALS:
        for name, (plan, scale_out) in _plans(float(df["Close"].values[i])).items():
            res = simulate_exit(df, i, plan, scale_out=scale_out)
            out.append({"name": name, "signal": i, "result": dataclasses.asdict(res)})
    return out


def _arms():
    frame = load_v74_fixture()["AAPL"]
    trades = run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, {})
    return [dataclasses.asdict(t) for t in trades]


def _golden(captured):
    if os.environ.get("V192_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_replay_matches_the_pre_v192_golden():
    captured = json.loads(json.dumps({"exits": _exits(), "arms": _arms()}))
    golden = _golden(captured)
    names = {row["name"] for row in golden["exits"]}
    assert names == set(_plans(100.0)), "every entry family is pinned"
    outcomes = {row["result"]["outcome"] for row in golden["exits"]}
    assert {"win", "loss"} <= outcomes, "the wave must exercise wins and losses"
    assert len(golden["arms"]) >= 5, "the arm capture must hold real trades"
    assert captured == golden
```

- [ ] **Step 3: Capture the replay golden on unmodified code**

```bash
V192_CAPTURE_GOLDEN=1 python -m pytest tests/backtesting/arms/test_v192_flag_off_golden.py -v
```

Expected: `1 passed`; `tests/fixtures/v192/replay_golden.json` now exists. Confirm `git status --short swingbot/` prints nothing (no code was touched before the capture). If the `{"win", "loss"}` or `>= 5` guard fails, the capture is void: delete the fixture, widen `SIGNALS` or the wave amplitude, capture again — this is the only moment a re-capture is allowed.

- [ ] **Step 4: Write the plan-dict golden test** — `tests/planning/test_v192_plan_golden.py`

Market plans exactly as the builders persist them today: confluence plans through `build_confluence_plan` on a flat frame (a non-breakout scenario, so `entry_type == "market"`), both directions plus a sub-$1 entry; strategy plans through `build_strategy_plan` over the v74 AAPL fixture, the first eight market plans the sweep finds. The snapshot keeps the persisted key list (pins that no `reclaim_*` key appears) and every value except `plan_id` (a uuid) and the registry-derived stamps (`badge`, `badge_stats`, `cohort_label`, `cohort_stats`, `ledger`), which move with the strategy registry rather than with this plan's code.

```python
"""v192 flag-off parity for the builders: with MARKET_ENTRY_NEXT_OPEN off and
GAP_RECLAIM_ATR at 0, market plans are built ACTIVE with entry_price = the
entry, a market_entry transition, and no reclaim_atr / reclaim_level / waits_next_open /
reclaim_session key. Captured at V192-1 on unmodified code; never regenerate."""
import json
import os
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from swingbot.core.planning.plan_types import plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v192" / "plan_golden.json"
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")
RECLAIM_KEYS = ("reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open")
#: name -> (direction, entry, level stop, own target)
CONFLUENCE = {
    "conf_bull": ("bullish", 100.0, 98.4, 104.0),
    "conf_bear": ("bearish", 100.0, 101.6, 96.0),
    "conf_penny_bull": ("bullish", 0.85, 0.838, 0.88),
}
STRATEGY_PLANS = 8


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    for f in config.FIELDS:
        if f.search_class == "searchable":
            monkeypatch.setattr(config, f.attr, config._cast(f, f.default), raising=False)


def _snap(plan):
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _confluence(direction, entry, stop, target):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([entry] * 60, spread=0.02), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")
    return None if plan is None else _snap(plan)


def _strategy_sweep():
    df = load_v74_fixture()["AAPL"]
    found = []
    for index in range(120, len(df), 7):
        for strategy in ALL_STRATEGIES:
            for direction in ("bullish", "bearish"):
                plan = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                           horizon_key="4w", direction=direction)
                if plan is not None and plan.entry_type == "market":
                    found.append({"index": index, **_snap(plan)})
                if len(found) == STRATEGY_PLANS:
                    return found
    return found


def _capture():
    return {"confluence": {name: _confluence(*args) for name, args in CONFLUENCE.items()},
            "strategy": _strategy_sweep()}


def _golden(captured):
    if os.environ.get("V192_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_market_plans_match_the_pre_v192_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    built = [s for s in golden["confluence"].values() if s is not None] + golden["strategy"]
    assert len(golden["strategy"]) == STRATEGY_PLANS, "the sweep must find real strategy plans"
    assert len(built) >= STRATEGY_PLANS + 2
    for snap in built:
        assert snap["plan"]["entry_type"] == "market"
        assert snap["plan"]["status"] == "ACTIVE"
        assert snap["plan"]["entry_price"] == snap["plan"]["trigger_price"]
        assert not set(RECLAIM_KEYS) & set(snap["keys"])
    assert captured == golden
```

- [ ] **Step 5: Capture the plan golden on unmodified code**

```bash
V192_CAPTURE_GOLDEN=1 python -m pytest tests/planning/test_v192_plan_golden.py -v
```

Expected: `1 passed`; `tests/fixtures/v192/plan_golden.json` exists. Open it and check that `conf_bull` and `conf_bear` are non-null market plans with a `market_entry` row in `status_history`. If a confluence scenario is `null` or a `stop_entry`, or the sweep finds fewer than eight plans, the capture is void: delete the fixture, adjust the scenario stops (inside 2%) or widen the sweep range, capture again — the only moment a re-capture is allowed.

- [ ] **Step 6: Re-run both goldens without the capture variable**

```bash
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
```

Expected: `1 passed` each, `0 failed`. `git status --short tests/fixtures/v192/` shows both fixtures as new and unchanged since Steps 3 and 5.

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add tests/backtesting/arms/test_v192_flag_off_golden.py tests/fixtures/v192/replay_golden.json tests/planning/test_v192_plan_golden.py tests/fixtures/v192/plan_golden.json
git commit -m "test(v192): flag-off goldens -- replay exits, arm rows and market plan dicts captured before any change"
```

# Phase 2 — Config, coupling and the plan fields

### Task V192-2: Config knobs, ScanParams slots, reachability rows, load coupling, `apply_knobs` guard
**Model:** sonnet — schema additions on the v135/v139 field pattern plus two small guards on existing load and knob paths; no behaviour reads the knobs yet.

**Files:**
- Modify: `swingbot/config.py` (two `Field`s after `HEADROOM_MIN_R` ~`:302`; `_SEARCH_CLASSES["searchable"]` ~`:1480`; `enforce_gap_reclaim_coupling` and `_settle_change` above `_apply_env` ~`:1582`; two lines inside `_apply_env`)
- Modify: `swingbot/scan_params.py` (two slots after `headroom_min_r` ~`:96`; two `from_config` lines after `headroom_min_r=` ~`:166`)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (`_V192` reason and two `REGISTRY` rows)
- Modify: `swingbot/core/backtesting/arms/knobs.py` (`GAP_RECLAIM_NEEDS_NEXT_OPEN`, `_check_coupling`, the call inside `apply_knobs`)
- Modify: `.env.example` (two keys after `HEADROOM_MIN_R=0`; `tests/infra/test_env_example_sync.py` fails without them)
- Modify: `tests/infra/test_config_flags.py`, `tests/backtesting/arms/test_knobs.py`
- Create: `tests/planning/test_v192_config.py`

**Interfaces:**
- Consumes: `Field(key, attr, section, label, type=, default=, min=, max=, step=, help=)` (`config.py:75`), `_SEARCH_CLASSES`, `_apply_env()` (`config.py:1582`), `log` (`config.py:56`), `Reach(cls, reason, observed_by, fixture_observable)` and `REACHABLE`, `CS` (`reachability.py:20`, `:12`), `apply_knobs(delta)` (`knobs.py:31`).
- Produces (index § Contracts, exact):
  - `config.MARKET_ENTRY_NEXT_OPEN: bool` (default `False`), `config.GAP_RECLAIM_ATR: float` (default `0.0`), both `search_class == "searchable"`.
  - `config.enforce_gap_reclaim_coupling() -> bool` — True when it zeroed `GAP_RECLAIM_ATR`; called last in `_apply_env` (import and every `reload()`), logs at ERROR.
  - `ScanParams.market_entry_next_open: bool = False`, `ScanParams.gap_reclaim_atr: float = 0.0`.
  - `reachability.REGISTRY["MARKET_ENTRY_NEXT_OPEN"]`, `REGISTRY["GAP_RECLAIM_ATR"]`, both `Reach(REACHABLE, _V192, CS)`.
  - `knobs.GAP_RECLAIM_NEEDS_NEXT_OPEN = "GAP_RECLAIM_ATR > 0 needs MARKET_ENTRY_NEXT_OPEN on"`; `apply_knobs(delta)` raises `ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)` after setting the delta when the merged config has `GAP_RECLAIM_ATR > 0` and `MARKET_ENTRY_NEXT_OPEN` off; the `finally` restores config first.

- [ ] **Step 1: Write the failing config tests** — `tests/planning/test_v192_config.py`

```python
"""V192-2: MARKET_ENTRY_NEXT_OPEN and GAP_RECLAIM_ATR ship inert, are searchable,
reach ScanParams and the reachability registry, and GAP_RECLAIM_ATR > 0 is
zeroed with an ERROR log at load and reload while MARKET_ENTRY_NEXT_OPEN is off."""
import logging

import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as r
from swingbot.scan_params import ScanParams

KNOBS = ("MARKET_ENTRY_NEXT_OPEN", "GAP_RECLAIM_ATR")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.fixture
def restore_config():
    """_apply_env() rewrites every FIELDS global; put them all back afterwards."""
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def test_fields_ship_inert_and_searchable():
    nxt, gap = _field("MARKET_ENTRY_NEXT_OPEN"), _field("GAP_RECLAIM_ATR")
    assert (nxt.key, nxt.type, nxt.default, nxt.section) == (
        "MARKET_ENTRY_NEXT_OPEN", "checkbox", "false", "Trade Filters & Risk")
    assert (gap.key, gap.type, gap.default, gap.section) == (
        "GAP_RECLAIM_ATR", "float", "0", "Trade Filters & Risk")
    assert (gap.min, gap.max, gap.step) == (0, 1.0, 0.05)
    assert config._cast(nxt, nxt.default) is False
    assert config._cast(gap, gap.default) == 0.0
    for attr in KNOBS:
        assert attr in config.searchable_attrs()
        assert _field(attr).hot_reloadable is True


def test_knobs_reach_scan_params(monkeypatch):
    assert ScanParams.from_config().market_entry_next_open is False
    assert ScanParams.from_config().gap_reclaim_atr == 0.0
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.25)
    params = ScanParams.from_config()
    assert params.market_entry_next_open is True and params.gap_reclaim_atr == 0.25


def test_knobs_have_reachability_rows():
    for attr in KNOBS:
        assert r.classify(attr) == r.REACHABLE
        assert r.REGISTRY[attr].observed_by == r.CS
        assert r.REGISTRY[attr].fixture_observable is False
        assert "Stage -1" in r.reason(attr)


def test_gap_without_next_open_is_zeroed_at_load_with_an_error(monkeypatch, caplog, restore_config):
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "false")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    with caplog.at_level(logging.ERROR, logger=config.log.name):
        changed = config._apply_env()
    assert config.GAP_RECLAIM_ATR == 0.0
    assert "GAP_RECLAIM_ATR" not in changed or changed["GAP_RECLAIM_ATR"][1] == 0.0
    assert any("MARKET_ENTRY_NEXT_OPEN" in rec.getMessage() for rec in caplog.records
               if rec.levelno == logging.ERROR)


def test_gap_with_next_open_is_honoured(monkeypatch, caplog, restore_config):
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "true")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    with caplog.at_level(logging.ERROR, logger=config.log.name):
        config._apply_env()
    assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.25
    assert not [rec for rec in caplog.records if rec.levelno == logging.ERROR
                and "GAP_RECLAIM_ATR" in rec.getMessage()]


def test_reload_turning_next_open_off_zeroes_a_live_gap(monkeypatch, restore_config):
    """A SIGHUP that switches MARKET_ENTRY_NEXT_OPEN off while GAP_RECLAIM_ATR stays
    0.25 in .env: the change log reports the zeroing, not a silent stale 0.25."""
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "true")
    monkeypatch.setenv("GAP_RECLAIM_ATR", "0.25")
    config._apply_env()
    monkeypatch.setenv("MARKET_ENTRY_NEXT_OPEN", "false")
    changed = config._apply_env()
    assert config.GAP_RECLAIM_ATR == 0.0
    assert changed["GAP_RECLAIM_ATR"] == (0.25, 0.0)
    assert changed["MARKET_ENTRY_NEXT_OPEN"] == (True, False)


def test_enforce_is_a_no_op_when_coupled(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    assert config.enforce_gap_reclaim_coupling() is False
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.5)
    assert config.enforce_gap_reclaim_coupling() is False
    assert config.GAP_RECLAIM_ATR == 0.5
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    assert config.enforce_gap_reclaim_coupling() is True
    assert config.GAP_RECLAIM_ATR == 0.0
```

- [ ] **Step 2: Add the `apply_knobs` guard tests** — append to `tests/backtesting/arms/test_knobs.py`

```python
from swingbot.core.backtesting.arms.knobs import GAP_RECLAIM_NEEDS_NEXT_OPEN


def test_parse_casts_the_v192_knobs():
    assert parse_knob("MARKET_ENTRY_NEXT_OPEN=true") == ("MARKET_ENTRY_NEXT_OPEN", True)
    assert parse_knob("GAP_RECLAIM_ATR=0.25") == ("GAP_RECLAIM_ATR", 0.25)


def test_gap_reclaim_without_next_open_is_refused_and_config_restored(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with pytest.raises(ValueError, match="needs MARKET_ENTRY_NEXT_OPEN on") as info:
        with apply_knobs({"GAP_RECLAIM_ATR": 0.25}):
            raise AssertionError("the body must not run")
    assert str(info.value) == GAP_RECLAIM_NEEDS_NEXT_OPEN
    assert config.GAP_RECLAIM_ATR == 0.0 and config.MARKET_ENTRY_NEXT_OPEN is False


def test_gap_reclaim_with_next_open_in_the_same_delta_runs(monkeypatch):
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with apply_knobs({"MARKET_ENTRY_NEXT_OPEN": True, "GAP_RECLAIM_ATR": 0.25}):
        assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.25
    assert config.GAP_RECLAIM_ATR == 0.0 and config.MARKET_ENTRY_NEXT_OPEN is False


def test_the_guard_reads_the_merged_config(monkeypatch):
    """The baseline arm runs MARKET_ENTRY_NEXT_OPEN=true alone; the component adds the
    gap. A next-open already on in config satisfies a gap-only delta."""
    monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
    monkeypatch.setattr(config, "GAP_RECLAIM_ATR", 0.0)
    with apply_knobs({"GAP_RECLAIM_ATR": 0.10}):
        assert config.GAP_RECLAIM_ATR == 0.10
    with pytest.raises(ValueError):
        with apply_knobs({"MARKET_ENTRY_NEXT_OPEN": False, "GAP_RECLAIM_ATR": 0.10}):
            pass
    assert config.MARKET_ENTRY_NEXT_OPEN is True and config.GAP_RECLAIM_ATR == 0.0


def test_an_empty_delta_never_trips_the_guard():
    with apply_knobs({}):
        pass
```

And append to `tests/infra/test_config_flags.py`:

```python
def test_v192_knobs_default_off():
    by_key = {f.key: f for f in config.FIELDS}
    assert by_key["MARKET_ENTRY_NEXT_OPEN"].default == "false"
    assert by_key["GAP_RECLAIM_ATR"].default == "0"
    assert isinstance(config.MARKET_ENTRY_NEXT_OPEN, bool)
    assert isinstance(config.GAP_RECLAIM_ATR, float)
```

- [ ] **Step 3: Run the tests to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_v192_config.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_knobs.py
```

Expected: FAIL — `StopIteration` from `_field("MARKET_ENTRY_NEXT_OPEN")`, `ImportError: cannot import name 'GAP_RECLAIM_NEEDS_NEXT_OPEN'`.

- [ ] **Step 4: Add the two fields** — `swingbot/config.py`, directly after the `HEADROOM_MIN_R` `Field(...)` entry

```python
    Field("MARKET_ENTRY_NEXT_OPEN", "MARKET_ENTRY_NEXT_OPEN", "Trade Filters & Risk",
          "Market plans wait for the next open (v192)",
          type="checkbox", default="false",
          help="v192. When on, every market plan is built PENDING and the alert reads "
               "'Enter at the open (market-on-open)': at the next session's open it fills "
               "at the open, or cancels when the open is at or through the stop or the "
               "stop sits past the 2% ceiling from the open. Stop-entry, limit and v180 "
               "Turtle Soup plans are untouched. Ships OFF: it changes every market "
               "plan's fill and needs its own non-inferiority pre-registration before "
               "it can go live."),
    Field("GAP_RECLAIM_ATR", "GAP_RECLAIM_ATR", "Trade Filters & Risk",
          "Gap-toward-stop reclaim threshold g x ATR14 (v192)",
          type="float", default="0", min=0, max=1.0, step=0.05,
          help="v192. With MARKET_ENTRY_NEXT_OPEN on: when the next open sits at or "
               "beyond entry -/+ g x ATR14 toward the stop, the plan does not fill at "
               "the open but rests as a DAY buy-stop (sell-stop for a short) at the "
               "planned entry and cancels at the close without a reclaim. 0 turns it "
               "off. Honoured only with MARKET_ENTRY_NEXT_OPEN on -- otherwise it is "
               "set to 0 at load with an error in the log. Frozen grid 0.10 / 0.25 / 0.50."),
```

Add both names to the `"searchable"` set of `_SEARCH_CLASSES`, on the line after `"HEADROOM_SCOPE", "HEADROOM_MIN_R",`:

```python
        "MARKET_ENTRY_NEXT_OPEN", "GAP_RECLAIM_ATR",
```

- [ ] **Step 5: Add the coupling** — `swingbot/config.py`, directly above `def _apply_env()`

```python
def enforce_gap_reclaim_coupling() -> bool:
    """v192: GAP_RECLAIM_ATR > 0 is honoured only with MARKET_ENTRY_NEXT_OPEN on
    (the veto decides at the next open, which only that knob creates). Otherwise
    set it to 0.0 and log at ERROR. True when it zeroed the value."""
    g = globals()
    if g.get("GAP_RECLAIM_ATR", 0.0) > 0 and not g.get("MARKET_ENTRY_NEXT_OPEN", False):
        log.error("GAP_RECLAIM_ATR=%r needs MARKET_ENTRY_NEXT_OPEN on -- treated as 0",
                  g["GAP_RECLAIM_ATR"])
        g["GAP_RECLAIM_ATR"] = 0.0
        return True
    return False


def _settle_change(changed: dict, attr: str, before) -> None:
    """Rewrite `changed[attr]` after a coupling rule moved the value the loop set."""
    now = globals()[attr]
    if before == now:
        changed.pop(attr, None)
    else:
        changed[attr] = (before, now)
```

Inside `_apply_env`, capture the value before the loop and settle it after:

```python
    changed = {}
    g = globals()
    gap_before = g.get("GAP_RECLAIM_ATR")
    for f in FIELDS:
        ...                                   # the loop body is unchanged
    if enforce_gap_reclaim_coupling():
        _settle_change(changed, "GAP_RECLAIM_ATR", gap_before)
    return changed
```

(`_apply_env` runs at import and from every `reload()`, so both the start-up load and SIGHUP go through the coupling.)

- [ ] **Step 6: Add the `ScanParams` slots** — `swingbot/scan_params.py`

After `headroom_min_r: float = 0.0`:

```python
    market_entry_next_open: bool = False    # v192: market plans wait for the next open
    gap_reclaim_atr: float = 0.0            # v192: g; honoured only with market_entry_next_open
```

In `from_config`, after `headroom_min_r=config.HEADROOM_MIN_R,`:

```python
            market_entry_next_open=config.MARKET_ENTRY_NEXT_OPEN,
            gap_reclaim_atr=config.GAP_RECLAIM_ATR,
```

- [ ] **Step 7: Add the reachability rows** — `swingbot/core/backtesting/arms/reachability.py`

After the `_HEADROOM = (...)` constant:

```python
_V192 = ("v192 next-open market fill (planning/market_next_open.py), reached from "
         "exit_sim._market_exit for a market plan the builders left PENDING under "
         "MARKET_ENTRY_NEXT_OPEN; both engines build market plans. GAP_RECLAIM_ATR is "
         "inert unless MARKET_ENTRY_NEXT_OPEN is on (apply_knobs refuses it alone), so a "
         "lone perturbation at the default is inert by design. Stage -1: measure_arms.py "
         "--stage pilot --baseline-knob MARKET_ENTRY_NEXT_OPEN=true --knob "
         "MARKET_ENTRY_NEXT_OPEN=true --knob GAP_RECLAIM_ATR=<g>, then "
         "validate_component.py --stage reachability --gap-reclaim.")
```

In `REGISTRY`, after the `"HEADROOM_MIN_R"` row:

```python
    "MARKET_ENTRY_NEXT_OPEN": Reach(REACHABLE, _V192, CS),
    "GAP_RECLAIM_ATR": Reach(REACHABLE, _V192, CS),
```

- [ ] **Step 8: Add the guard** — `swingbot/core/backtesting/arms/knobs.py`

```python
#: v192: the veto decides at the next open, which only MARKET_ENTRY_NEXT_OPEN creates.
GAP_RECLAIM_NEEDS_NEXT_OPEN = "GAP_RECLAIM_ATR > 0 needs MARKET_ENTRY_NEXT_OPEN on"


def _check_coupling() -> None:
    """Refuse an arm whose merged config would run the veto without the next-open fill."""
    if getattr(config, "GAP_RECLAIM_ATR", 0.0) > 0 and not getattr(config, "MARKET_ENTRY_NEXT_OPEN", False):
        raise ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)
```

and in `apply_knobs`, after the `setattr` loop, still inside `try` (so `finally` restores before the error leaves):

```python
    try:
        for attr, value in delta.items():
            setattr(config, attr, value)
        _check_coupling()
        yield
    finally:
        ...                                   # unchanged
```

- [ ] **Step 9: Add the `.env.example` keys** — after `HEADROOM_MIN_R=0`

```
# v192 next-open market fill and gap-toward-stop reclaim veto. MARKET_ENTRY_NEXT_OPEN
# makes every market plan wait for the next open; GAP_RECLAIM_ATR (g) then waits for
# a same-session reclaim of the entry when the open gaps toward the stop by
# g x ATR14. GAP_RECLAIM_ATR is honoured only with MARKET_ENTRY_NEXT_OPEN on.
# Both ship OFF.
MARKET_ENTRY_NEXT_OPEN=false
GAP_RECLAIM_ATR=0
```

- [ ] **Step 10: Run the narrow tests and the goldens**

```bash
python scripts/dev/testrun.py file tests/planning/test_v192_config.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_knobs.py
python scripts/dev/testrun.py file tests/infra/test_config_flags.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py
python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py
python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/complexity_gate.py
```

Expected: every file `0 failed`; the gate passes (`_apply_env` gains one `if`).

- [ ] **Step 11: Commit (in the worktree)**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py swingbot/core/backtesting/arms/knobs.py .env.example tests/planning/test_v192_config.py tests/backtesting/arms/test_knobs.py tests/infra/test_config_flags.py
git commit -m "feat(v192): MARKET_ENTRY_NEXT_OPEN and GAP_RECLAIM_ATR knobs, inert -- load coupling and apply_knobs guard"
```

### Task V192-3: `TradePlanV2.reclaim_atr`, `reclaim_level`, `reclaim_session`, `waits_next_open` with serialization and DB round trip
**Model:** sonnet — four optional dataclass fields on the `schema-evolution.md` ADD path (the v183 omit-when-None pattern), with a DB round trip that must actually run.

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (four fields after `risk_notice` ~`:210`; `_OMIT_WHEN_NONE` ~`:231`)
- Modify: `tests/planning/test_plan_serialization.py`
- Modify: `tests/db/test_plans_repository.py`

**Interfaces:**
- Consumes: `TradePlanV2` (`plan_types.py:22`), `_OMIT_WHEN_NONE = ("gap_sizing", "risk_notice")` (`:231`), `plan_to_dict` / `plan_from_dict`, `PlanRepository().insert(record, conn=)` / `.get(plan_id, conn=)`, `tests.db_diff.diff_records`, the `db_conn` fixture.
- Produces (index § Contracts, exact), all four in `_OMIT_WHEN_NONE`:
  - `TradePlanV2.reclaim_atr: float | None = None` — `a_t`, price units
  - `TradePlanV2.reclaim_level: float | None = None` — `X`
  - `TradePlanV2.reclaim_session: str | None = None` — ISO date of the session the plan rests at `E` (live only; V192-9 writes it)
  - `TradePlanV2.waits_next_open: bool | None = None` — `True` only from `gap_reclaim.stamp_next_open` (V192-4); the persisted marker `gap_reclaim.waits_for_open` reads

Why omit-when-None: with both knobs off no plan carries any of the four, so every plan doc stays byte-identical to its pre-v192 shape (the V192-1 plan golden pins the key list). `plan_from_dict` defaults a missing key back to `None`. No column, no Alembic revision (`docs/claude/schema-evolution.md` § add).

- [ ] **Step 1: Write the failing serialization tests** — append to `tests/planning/test_plan_serialization.py`

```python
V192_FIELDS = ("reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open")


def test_v192_fields_default_to_none_and_are_omitted_from_the_doc():
    p = _plan()
    assert all(getattr(p, name) is None for name in V192_FIELDS)
    d = plan_to_dict(p)
    assert not set(V192_FIELDS) & set(d), "a plan without them keeps its pre-v192 key list"


def test_v192_fields_round_trip_when_set():
    p = _plan(reclaim_atr=1.2345, reclaim_level=99.69, reclaim_session="2026-10-26",
              waits_next_open=True)
    d = plan_to_dict(p)
    assert {k: d[k] for k in V192_FIELDS} == {
        "reclaim_atr": 1.2345, "reclaim_level": 99.69, "reclaim_session": "2026-10-26",
        "waits_next_open": True}
    q = plan_from_dict(d)
    assert (q.reclaim_atr, q.reclaim_level, q.reclaim_session, q.waits_next_open) == (
        1.2345, 99.69, "2026-10-26", True)


def test_only_the_set_v192_fields_are_written():
    """A baseline-arm plan (g = 0) carries the marker alone; no reclaim key appears."""
    d = plan_to_dict(_plan(waits_next_open=True))
    assert d["waits_next_open"] is True
    assert not {"reclaim_atr", "reclaim_level", "reclaim_session"} & set(d)


def test_pre_v192_record_loads_with_the_fields_none():
    d = plan_to_dict(_plan())
    for name in V192_FIELDS:
        d.pop(name, None)
    q = plan_from_dict(d)
    assert all(getattr(q, name) is None for name in V192_FIELDS)
```

- [ ] **Step 2: Write the failing DB round trip** — append to `tests/db/test_plans_repository.py`

```python
def test_v192_reclaim_fields_ride_in_the_doc(repo, db_conn):
    """v192 used schema-evolution's ADD path: no column, no revision -- the stored
    a_t, X, the resting session and the next-open marker live in plans.doc and must
    survive the repository, then load back into a TradePlanV2."""
    from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
    from tests.db_diff import diff_records
    from tests.planning.test_plan_engine_model import _plan as model_plan

    record = plan_to_dict(model_plan(plan_id="P192", reclaim_atr=1.2345, reclaim_level=99.69,
                                     reclaim_session="2026-10-26", waits_next_open=True))
    repo.insert(record, conn=db_conn)
    stored = repo.get("P192", conn=db_conn)
    assert diff_records(record, stored) == []
    plan = plan_from_dict(stored)
    assert (plan.reclaim_atr, plan.reclaim_level, plan.reclaim_session, plan.waits_next_open) == (
        1.2345, 99.69, "2026-10-26", True)


def test_v192_plan_without_the_fields_stores_no_key(repo, db_conn):
    from swingbot.core.planning.plan_types import plan_to_dict
    from tests.planning.test_plan_engine_model import _plan as model_plan

    repo.insert(plan_to_dict(model_plan(plan_id="P0")), conn=db_conn)
    stored = repo.get("P0", conn=db_conn)
    assert not {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"} & set(stored)
```

- [ ] **Step 3: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
```

Expected: FAIL — `TypeError: TradePlanV2.__init__() got an unexpected keyword argument 'reclaim_atr'`.

- [ ] **Step 4: Add the fields** — `swingbot/core/planning/plan_types.py`, after `risk_notice: dict | None = None`

```python
    # v192 (planning/gap_reclaim.py): the next-open market fill and its gap veto,
    # stamped once at creation (gap_reclaim.stamp_next_open) and never rewritten --
    # not by a reload, a knob flip or a restart. waits_next_open: True on a market
    # plan built PENDING under MARKET_ENTRY_NEXT_OPEN; gap_reclaim.waits_for_open
    # reads it, so a hand-built PENDING market plan keeps the close fill.
    # reclaim_atr: a_t, Wilder ATR14 through the creating bar (price units);
    # reclaim_level: X = E -/+ g x a_t, rounded to the tick away from E. Both None
    # when GAP_RECLAIM_ATR is 0 or the ATR was unusable. reclaim_session: the ISO
    # session date a live plan rests at E as a DAY stop order (PlanManager).
    # All omitted from plan_to_dict while None (_OMIT_WHEN_NONE).
    reclaim_atr: float | None = None
    reclaim_level: float | None = None
    reclaim_session: str | None = None
    waits_next_open: bool | None = None
```

and widen the omit list:

```python
_OMIT_WHEN_NONE = ("gap_sizing", "risk_notice", "reclaim_atr", "reclaim_level",
                   "reclaim_session", "waits_next_open")
```

Update the comment above `_OMIT_WHEN_NONE` to say "v183, v192".

- [ ] **Step 5: Run the serialization tests and the plan golden**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/testrun.py file tests/planning/test_plan_engine_model.py
```

Expected: `0 failed` each. The golden still matches: no plan built with the knobs off carries a v192 key.

- [ ] **Step 6: Run the DB round trip against the shared `swing-db`**

Run `/replicate-prod-db` first (CLAUDE.md: the project's one shared `swing-db` container, never a per-task database), then:

```bash
python scripts/dev/testrun.py file tests/db/test_plans_repository.py
```

Expected: every test passed, **`0 skipped`** for the two v192 tests. A skip means the database was not reached: fix the connection and re-run. A skipped round trip never counts as done (index § Global Constraints).

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add swingbot/core/planning/plan_types.py tests/planning/test_plan_serialization.py tests/db/test_plans_repository.py
git commit -m "feat(v192): TradePlanV2 reclaim_atr, reclaim_level, reclaim_session, waits_next_open (omit when None)"
```

# Phase 3 — The rule and the builders

### Task V192-4: `gap_reclaim.py`: tick, ATR at t, X, open decision, reclaim touch, builder stamp
**Model:** opus — the one rule module live and replay both call; a wrong sign, rounding direction or lookahead silently moves every measured trade.

**Files:**
- Create: `swingbot/core/planning/gap_reclaim.py`
- Create: `tests/planning/test_gap_reclaim.py`

**Interfaces:**
- Consumes: `config.MARKET_ENTRY_NEXT_OPEN`, `config.GAP_RECLAIM_ATR` (V192-2); `TradePlanV2.reclaim_atr`, `.reclaim_level`, `.waits_next_open` (V192-3); `PlanStatus` (`plan_types.py:5`); `at_or_beyond_stop(plan, price)` (`lifecycle.py:198`); `planned_loss_pct(entry, stop)` (`risk_limits.py:17`); `plan_stop_ceiling(plan)` (`stop_scope.py:51`); `indicators.atr(df, period)` (`swingbot/core/market/indicators.py:62`, Wilder `ewm(alpha=1/14, min_periods=14)`); `next_open_entry.uses_next_open_fill(plan)` (imported lazily: `next_open_entry` imports `exit_sim`, which will import this module in V192-6).
- Produces (index § Contracts, exact):

```python
OPEN_THROUGH_STOP = "open_through_stop"; GAP_NO_RECLAIM = "gap_no_reclaim"; RISK_CAP = "risk_cap"
FILL_OPEN = "open"; RECLAIM_WAIT = "reclaim_wait"; ATR_PERIOD = 14; MIN_ATR_BARS = 15
def tick_for(price: float) -> float
def atr_at(df, index: int) -> float | None
def reclaim_level_for(entry: float, atr: float, g: float, direction: str) -> float
def effective_g() -> float
def next_open_applies(plan) -> bool
def waits_for_open(plan) -> bool          # market and PENDING and plan.waits_next_open is True
def stamp_next_open(plan, df, index: int) -> None
def gap_toward_stop(plan, open_price: float) -> float
def decide_at_open(plan, open_price: float) -> str
def reclaim_touched(plan, high: float, low: float) -> bool
def reclaim_fill_price(plan) -> float
```

The module reads only the plan's own stored values (`trigger_price` = `E`, `stop_loss`, `reclaim_level` = `X`) at decision time, so live (`PlanManager`, part 2) and replay (`market_next_open`, V192-6) cannot drift. Prices on the tick grid are rounded to the grid's decimals (2 for `0.01`, 4 for `0.0001`) so `E + tick` compares exactly against bar data.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_gap_reclaim.py`

```python
"""V192-4: the gap-toward-stop rule, one module for live and replay. Bullish and
bearish twins of every rule; sub-$1 tick; ATR14 through the creating bar only."""
import math

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.plan_types import PlanStatus, plan_to_dict
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan


def _wave(n=40):
    rows, prev = [], 100.0
    for i in range(n):
        close = 100.0 + 3.0 * math.sin(i / 3.0)
        open_ = prev + 0.3 * math.sin(i * 1.3)
        rows.append((open_, max(open_, close) + 0.6, min(open_, close) - 0.6, close))
        prev = close
    return make_ohlcv(rows)


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0)
    base.update(kw)
    return _bull(**base)


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


# --- constants and tick -------------------------------------------------------

def test_names_are_the_frozen_strings():
    assert (gr.OPEN_THROUGH_STOP, gr.GAP_NO_RECLAIM, gr.RISK_CAP) == (
        "open_through_stop", "gap_no_reclaim", "risk_cap")
    assert (gr.FILL_OPEN, gr.RECLAIM_WAIT) == ("open", "reclaim_wait")
    assert (gr.ATR_PERIOD, gr.MIN_ATR_BARS) == (14, 15)


@pytest.mark.parametrize("price, tick", [(1.0, 0.01), (250.0, 0.01), (0.9999, 0.0001),
                                         (0.85, 0.0001)])
def test_tick_for(price, tick):
    assert gr.tick_for(price) == tick


# --- ATR at t -------------------------------------------------------------------

def test_atr_at_is_wilder_atr14_through_the_creating_bar():
    df = _wave()
    expected = float(atr_indicator(df.iloc[:31], 14).iloc[-1])
    assert gr.atr_at(df, 30) == pytest.approx(expected, rel=0, abs=1e-12)
    assert gr.atr_at(df, 30) == pytest.approx(float(atr_indicator(df, 14).iloc[30]), abs=1e-12)


def test_atr_at_ignores_bar_t_plus_1():
    """NO-LOOKAHEAD: mutate bar t+1 and every later bar; a_t and X do not move."""
    df = _wave()
    before = gr.atr_at(df, 30)
    level = gr.reclaim_level_for(100.0, before, 0.25, "bullish")
    moved = df.copy()
    moved.iloc[31:, moved.columns.get_loc("High")] = 500.0
    moved.iloc[31:, moved.columns.get_loc("Low")] = 1.0
    assert gr.atr_at(moved, 30) == before
    assert gr.reclaim_level_for(100.0, gr.atr_at(moved, 30), 0.25, "bullish") == level


@pytest.mark.parametrize("index", [0, 5, 13])
def test_atr_at_needs_fifteen_bars(index):
    assert gr.atr_at(_wave(), index) is None


def test_atr_at_fifteen_bars_is_usable():
    assert gr.atr_at(_wave(), 14) is not None


def test_atr_at_zero_or_nan_is_none():
    flat = make_ohlcv([(100.0, 100.0, 100.0, 100.0)] * 30)
    assert gr.atr_at(flat, 20) is None
    holed = _wave()
    holed.iloc[:, :] = float("nan")
    assert gr.atr_at(holed, 30) is None


def test_atr_at_beyond_the_frame_raises():
    with pytest.raises(IndexError):
        gr.atr_at(_wave(40), 40)


# --- X --------------------------------------------------------------------------

@pytest.mark.parametrize("direction, atr, g, expected", [
    ("bullish", 1.234, 0.25, 99.69),      # 99.6915 floored
    ("bearish", 1.234, 0.25, 100.31),     # 100.3085 ceiled
    ("bullish", 2.0, 0.25, 99.5),         # exactly on the grid stays put
    ("bearish", 2.0, 0.25, 100.5),
    ("bullish", 1.0, 0.10, 99.9),
    ("bearish", 1.0, 0.50, 100.5),
])
def test_reclaim_level_rounds_away_from_entry(direction, atr, g, expected):
    assert gr.reclaim_level_for(100.0, atr, g, direction) == expected


def test_reclaim_level_sub_dollar_uses_the_small_tick():
    assert gr.reclaim_level_for(0.85, 0.0123, 0.25, "bullish") == 0.8469   # 0.846925 floored
    assert gr.reclaim_level_for(0.85, 0.0123, 0.25, "bearish") == 0.8531   # 0.853075 ceiled


# --- knob reads -----------------------------------------------------------------

@pytest.mark.parametrize("next_open, g, expected", [
    (False, 0.0, 0.0), (False, 0.25, 0.0), (True, 0.0, 0.0), (True, 0.25, 0.25)])
def test_effective_g(knobs, next_open, g, expected):
    knobs(next_open, g)
    assert gr.effective_g() == expected


def test_next_open_applies_only_to_market_plans_with_the_knob_on(knobs):
    knobs(False, 0.0)
    assert not gr.next_open_applies(_bull())
    knobs(True, 0.0)
    assert gr.next_open_applies(_bull())
    assert gr.next_open_applies(_bear(source="strategy", strategy="Fibonacci"))
    assert not gr.next_open_applies(_bull(entry_type="stop_entry"))
    assert not gr.next_open_applies(_bull(entry_type="limit"))
    assert not gr.next_open_applies(_bull(source="strategy", strategy=TURTLE_SOUP))


def test_waits_for_open_needs_the_persisted_marker():
    assert gr.waits_for_open(_bull())
    assert not gr.waits_for_open(_bull(waits_next_open=None)), (
        "a hand-built PENDING market plan keeps the close fill")
    assert not gr.waits_for_open(_bull(status=PlanStatus.ACTIVE))
    assert not gr.waits_for_open(_bull(entry_type="stop_entry"))


def test_waits_for_open_ignores_the_knob(knobs):
    """A plan resting since before a knob flip keeps its path (marker, not config)."""
    knobs(False, 0.0)
    assert gr.waits_for_open(_bull())


# --- the builder stamp ------------------------------------------------------------

def test_stamp_with_g_zero_sets_the_marker_only(knobs):
    knobs(True, 0.0)
    plan = _bull(waits_next_open=None, entry_price=100.0)
    gr.stamp_next_open(plan, _wave(), 30)
    assert plan.entry_price is None and plan.waits_next_open is True
    assert plan.reclaim_atr is None and plan.reclaim_level is None
    assert {"reclaim_atr", "reclaim_level", "reclaim_session"}.isdisjoint(plan_to_dict(plan))


@pytest.mark.parametrize("make, sign", [(_bull, -1), (_bear, 1)])
def test_stamp_with_g_stores_atr_and_level(knobs, make, sign):
    knobs(True, 0.25)
    df = _wave()
    plan = make(waits_next_open=None, entry_price=100.0)
    gr.stamp_next_open(plan, df, 30)
    a = gr.atr_at(df, 30)
    assert plan.reclaim_atr == a
    assert plan.reclaim_level == gr.reclaim_level_for(100.0, a, 0.25, plan.direction)
    assert (plan.reclaim_level - 100.0) * sign > 0
    assert plan.entry_price is None and plan.waits_next_open is True


def test_stamp_without_usable_atr_leaves_no_veto(knobs):
    """Fewer than 15 bars: the plan fills at the open like the baseline, never a crash."""
    knobs(True, 0.25)
    plan = _bull(waits_next_open=None)
    gr.stamp_next_open(plan, _wave(), 10)
    assert plan.waits_next_open is True
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_stamp_ignores_a_lone_gap_knob(knobs):
    knobs(False, 0.25)
    plan = _bull(waits_next_open=None)
    gr.stamp_next_open(plan, _wave(), 30)
    assert plan.reclaim_level is None


# --- gap and the open decision ------------------------------------------------------

def test_gap_toward_stop_sign():
    assert gr.gap_toward_stop(_bull(), 99.0) == pytest.approx(1.0)
    assert gr.gap_toward_stop(_bull(), 101.0) == pytest.approx(-1.0)
    assert gr.gap_toward_stop(_bear(), 101.0) == pytest.approx(1.0)
    assert gr.gap_toward_stop(_bear(), 99.0) == pytest.approx(-1.0)


@pytest.mark.parametrize("open_price, expected", [
    (99.51, gr.FILL_OPEN),          # gap 0.49 < g x a_t = 0.50: fills like the baseline
    (99.50, gr.RECLAIM_WAIT),       # exactly at X
    (99.00, gr.RECLAIM_WAIT),       # beyond X
    (98.51, gr.RECLAIM_WAIT),
    (98.50, gr.OPEN_THROUGH_STOP),  # at the stop
    (97.00, gr.OPEN_THROUGH_STOP),  # through it
    (101.0, gr.FILL_OPEN),          # gap away from the stop
    (103.0, gr.RISK_CAP),           # (103 - 98.5) / 103 = 4.4% > the 2% confluence ceiling
])
def test_decide_at_open_bullish(open_price, expected):
    assert gr.decide_at_open(_bull(reclaim_level=99.50), open_price) == expected


@pytest.mark.parametrize("open_price, expected", [
    (100.49, gr.FILL_OPEN),
    (100.50, gr.RECLAIM_WAIT),
    (101.00, gr.RECLAIM_WAIT),
    (101.49, gr.RECLAIM_WAIT),
    (101.50, gr.OPEN_THROUGH_STOP),
    (103.00, gr.OPEN_THROUGH_STOP),
    (99.0, gr.FILL_OPEN),
    (97.0, gr.RISK_CAP),            # (101.5 - 97) / 97 = 4.6%
])
def test_decide_at_open_bearish(open_price, expected):
    assert gr.decide_at_open(_bear(reclaim_level=100.50), open_price) == expected


def test_without_a_level_the_baseline_fills_any_gap_short_of_the_stop():
    assert gr.decide_at_open(_bull(), 98.6) == gr.FILL_OPEN
    assert gr.decide_at_open(_bear(), 101.4) == gr.FILL_OPEN
    assert gr.decide_at_open(_bull(), 98.5) == gr.OPEN_THROUGH_STOP


def test_a_stored_ceiling_drives_the_risk_cap():
    plan = _bull(stop_ceiling_pct=5.0)
    assert gr.decide_at_open(plan, 103.0) == gr.FILL_OPEN


# --- the reclaim -----------------------------------------------------------------

def test_reclaim_needs_one_tick_through_entry_bullish():
    plan = _bull(reclaim_level=99.5)
    assert not gr.reclaim_touched(plan, high=100.0, low=98.9)     # a bare touch of E
    assert gr.reclaim_touched(plan, high=100.01, low=98.9)
    assert gr.reclaim_fill_price(plan) == 100.01


def test_reclaim_needs_one_tick_through_entry_bearish():
    plan = _bear(reclaim_level=100.5)
    assert not gr.reclaim_touched(plan, high=101.2, low=100.0)
    assert gr.reclaim_touched(plan, high=101.2, low=99.99)
    assert gr.reclaim_fill_price(plan) == 99.99


def test_reclaim_sub_dollar_tick():
    bull = _bull(trigger_price=0.85, stop_loss=0.835, tp1=0.88, reclaim_level=0.8469)
    assert not gr.reclaim_touched(bull, high=0.85, low=0.84)
    assert gr.reclaim_touched(bull, high=0.8501, low=0.84)
    assert gr.reclaim_fill_price(bull) == 0.8501
    bear = _bear(trigger_price=0.85, stop_loss=0.865, tp1=0.82, tp2=None, reclaim_level=0.8531)
    assert gr.reclaim_touched(bear, high=0.86, low=0.8499)
    assert gr.reclaim_fill_price(bear) == 0.8499
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_gap_reclaim.py
```

Expected: FAIL — `ImportError: cannot import name 'gap_reclaim'`.

- [ ] **Step 3: Write the module** — `swingbot/core/planning/gap_reclaim.py`

```python
"""v192: the gap-toward-stop reclaim rule, one module for live and replay.

A market plan built under MARKET_ENTRY_NEXT_OPEN waits for the next session's
open (``waits_next_open``). At that open, in this order (``decide_at_open``):

1. the open at or beyond the stop cancels (``OPEN_THROUGH_STOP``);
2. with a stored reclaim level X and the open at or beyond X toward the stop,
   the plan rests as a DAY stop order at the planned entry E for that session
   (``RECLAIM_WAIT``) and fills only on a trade one tick through E;
3. a stop farther than the plan's ceiling from the open cancels (``RISK_CAP``);
4. otherwise the plan fills at the open (``FILL_OPEN``).

E is ``plan.trigger_price``. ``a_t`` is Wilder ATR14 of the completed bars
through the creating bar t -- never t + 1 (NO-LOOKAHEAD) -- and X = E -/+ g x a_t
rounded to the tick away from E. Both are computed once at creation
(``stamp_next_open``) and stored on the plan; every later decision reads the
stored values, so a reload, a knob flip or a restart never moves them.
"""
from __future__ import annotations

import math

from swingbot import config
from swingbot.core.risk_limits import planned_loss_pct
from .lifecycle import at_or_beyond_stop
from .plan_types import PlanStatus
from .stop_scope import plan_stop_ceiling

OPEN_THROUGH_STOP = "open_through_stop"
GAP_NO_RECLAIM = "gap_no_reclaim"
RISK_CAP = "risk_cap"
FILL_OPEN = "open"
RECLAIM_WAIT = "reclaim_wait"
ATR_PERIOD = 14
MIN_ATR_BARS = 15

_GRID_EPS = 1e-9


def tick_for(price: float) -> float:
    """The price grid: a cent from $1 up, a hundredth of a cent below."""
    return 0.01 if price >= 1 else 0.0001


def _places(tick: float) -> int:
    return 2 if tick >= 0.01 else 4


def _on_grid(value: float, tick: float, up: bool) -> float:
    """Round onto the tick grid -- ceil when ``up``, else floor -- tolerant of float noise."""
    steps = value / tick
    steps = math.ceil(steps - _GRID_EPS) if up else math.floor(steps + _GRID_EPS)
    return round(steps * tick, _places(tick))


def atr_at(df, index: int) -> float | None:
    """Wilder ATR14 of ``df.iloc[:index + 1]`` (bars through ``index`` only), or None
    with fewer than MIN_ATR_BARS bars, or when it is NaN or not positive."""
    if index >= len(df):
        raise IndexError(f"bar {index} is beyond a frame of {len(df)} bars")
    if index + 1 < MIN_ATR_BARS:
        return None
    from swingbot.core.market.indicators import atr as atr_indicator
    value = float(atr_indicator(df.iloc[:index + 1], ATR_PERIOD).iloc[-1])
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def reclaim_level_for(entry: float, atr: float, g: float, direction: str) -> float:
    """X = E - g x a_t floored (bullish) / E + g x a_t ceiled (bearish), on E's tick grid."""
    tick = tick_for(entry)
    if direction == "bullish":
        return _on_grid(entry - g * atr, tick, up=False)
    return _on_grid(entry + g * atr, tick, up=True)


def effective_g() -> float:
    """GAP_RECLAIM_ATR as honoured: 0 unless MARKET_ENTRY_NEXT_OPEN is on."""
    if not getattr(config, "MARKET_ENTRY_NEXT_OPEN", False):
        return 0.0
    return float(getattr(config, "GAP_RECLAIM_ATR", 0.0))


def next_open_applies(plan) -> bool:
    """A builder should build this plan waiting for the next open: a market plan,
    MARKET_ENTRY_NEXT_OPEN on, and not a v180 next-open strategy (Turtle Soup keeps
    its own path)."""
    from .next_open_entry import uses_next_open_fill   # next_open_entry imports exit_sim
    return (getattr(plan, "entry_type", None) == "market"
            and bool(getattr(config, "MARKET_ENTRY_NEXT_OPEN", False))
            and not uses_next_open_fill(plan))


def waits_for_open(plan) -> bool:
    """This plan is a market plan still waiting for its next open. Reads the persisted
    marker, never the knob: a plan resting since before a flip keeps its path, and a
    hand-built PENDING market plan without the marker keeps the close fill."""
    return (getattr(plan, "entry_type", None) == "market"
            and getattr(plan, "status", None) == PlanStatus.PENDING
            and getattr(plan, "waits_next_open", None) is True)


def stamp_next_open(plan, df, index: int) -> None:
    """Turn a freshly built market plan into one that waits for the next open.
    ``index`` is the creating bar t in ``df``. Stores a_t and X only when the veto is
    armed (effective_g() > 0) and a_t is usable; otherwise the plan fills at the
    open as the baseline does."""
    plan.entry_price = None
    plan.waits_next_open = True
    g = effective_g()
    if g <= 0:
        return
    a_t = atr_at(df, index)
    if a_t is None:
        return
    plan.reclaim_atr = a_t
    plan.reclaim_level = reclaim_level_for(plan.trigger_price, a_t, g, plan.direction)


def gap_toward_stop(plan, open_price: float) -> float:
    """Price distance the open sits beyond E toward the stop (positive = toward it)."""
    if plan.direction == "bullish":
        return plan.trigger_price - open_price
    return open_price - plan.trigger_price


def _at_or_beyond_level(plan, open_price: float) -> bool:
    level = getattr(plan, "reclaim_level", None)
    if level is None:
        return False
    return open_price <= level if plan.direction == "bullish" else open_price >= level


def decide_at_open(plan, open_price: float) -> str:
    """The open decision, in the frozen order (module docstring)."""
    if at_or_beyond_stop(plan, open_price):
        return OPEN_THROUGH_STOP
    if _at_or_beyond_level(plan, open_price):
        return RECLAIM_WAIT
    if planned_loss_pct(open_price, plan.stop_loss) > plan_stop_ceiling(plan):
        return RISK_CAP
    return FILL_OPEN


def _through_entry(plan) -> float:
    """E plus one tick in the trade's direction (bullish up, bearish down)."""
    tick = tick_for(plan.trigger_price)
    sign = 1 if plan.direction == "bullish" else -1
    return round(plan.trigger_price + sign * tick, _places(tick))


def reclaim_touched(plan, high: float, low: float) -> bool:
    """The bar traded one tick through E: bullish High >= E + tick, bearish Low <= E - tick."""
    level = _through_entry(plan)
    return high >= level if plan.direction == "bullish" else low <= level


def reclaim_fill_price(plan) -> float:
    """Replay's reclaim fill: E + tick (bullish) / E - tick (bearish) -- the one adverse
    tick standing in for the DAY stop order's slippage (the v1 arm replay applies no
    frictions in either arm). Live fills at E."""
    return _through_entry(plan)
```

- [ ] **Step 4: Run the tests and the gate**

```bash
python scripts/dev/testrun.py file tests/planning/test_gap_reclaim.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`; the gate passes (every function here is under cc 6).

- [ ] **Step 5: Commit (in the worktree)**

```bash
git add swingbot/core/planning/gap_reclaim.py tests/planning/test_gap_reclaim.py
git commit -m "feat(v192): gap_reclaim rule module -- tick, ATR at t, X, open decision, reclaim touch, builder stamp"
```

