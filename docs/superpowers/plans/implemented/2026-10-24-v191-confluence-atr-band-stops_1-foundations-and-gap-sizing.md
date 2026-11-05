# v191 — Confluence ATR-band stops, Part 1: foundations and long gap sizing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v191-confluence-atr-band-stops-design.md](../specs/2026-10-24-v191-confluence-atr-band-stops-design.md)
**Index:** [2026-10-24-v191-confluence-atr-band-stops_0-index.md](2026-10-24-v191-confluence-atr-band-stops_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V191-5:" -A 300 <this file>`.

**Scope of this part (V191-1..V191-6):** the worktree and the flag-off golden captured on unmodified code; the three config fields with their `ScanParams` slots and reachability rows; the coupling guard at config load/reload and in the admin validator; `TradePlanV2.stop_moved_by`; Part B — the p99 down-gap, the long gap-sizing stamp and sizing behind `LONG_GAP_SIZING`, and the readers that assumed every stamp was a short's.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops` (created in V191-1, Step 1). Subagent shells reset their cwd between calls: prefix each command with `cd <main tree>/.claude/worktrees/2026-10-24-v191-confluence-atr-band-stops &&`. Never edit the main tree's files from a task (CLAUDE.md, `subagents-edit-main-tree-by-mistake`).

**Dirty main tree:** the main checkout carries unrelated uncommitted edits (`tests/conftest.py`, `CLAUDE.md`, skills, `version_history.json`). The worktree is branched from `main`'s HEAD and never sees them; leave them alone.

---

# Phase 1 — Worktree and the flag-off golden

### Task V191-1: Worktree; flag-off golden (replay rows and plan dicts)
**Model:** sonnet — two new test modules copying an existing golden pattern; the only judgement is capturing before any code change.

**Files:**
- Create: `tests/backtesting/test_v191_flag_off_golden.py`
- Create: `tests/fixtures/v191/flag_off_golden.json` (written by the test's capture path, never by hand)
- Create: `tests/planning/test_v191_plan_golden.py`
- Create: `tests/fixtures/v191/plan_golden.json` (same)

**Interfaces:**
- Consumes: `bs.replay_scenarios(ticker, df, "4w", gates=GATES)`, `simulate_exit(df, i, plan, scale_out=True)`, `GATES` and `_structured_df` from `tests/backtesting/test_backtest_scenarios.py`, `load_ohlcv` from `tests/fixtures/ohlcv_parity.py`, `build_confluence_plan` from `swingbot.core.planning.plan_engine`, `plan_to_dict`, `make_ohlcv(closes, *, spread=)` from `tests/helpers.py`. All exist today.
- Produces: the branch and worktree `2026-10-24-v191-confluence-atr-band-stops`; two golden fixtures that every later task keeps green. **Never regenerate either fixture to make a test pass** — a diff against them is a behaviour change with every knob off, which this plan forbids.

Why this comes first: every later task edits code these goldens pin (`builders.py`, `levels.py`, `backtest_scenarios.py`, `gap_sizing.py`, `plan_types.py`). The fixtures must be written by unmodified `main` code, so this task changes no file under `swingbot/`.

- [ ] **Step 1: Create the worktree** (skill `worktree-lifecycle`; run from the main tree)

```bash
cd E:/Documents/Private/Projects/Discord-Bot
git worktree add .claude/worktrees/2026-10-24-v191-confluence-atr-band-stops -b 2026-10-24-v191-confluence-atr-band-stops main
git -C .claude/worktrees/2026-10-24-v191-confluence-atr-band-stops log --oneline -1
```

Expected: the new branch at `main`'s HEAD (the v191 index commit or later). Every command from here on runs inside that worktree.

- [ ] **Step 2: Write the replay golden test** — `tests/backtesting/test_v191_flag_off_golden.py`

The v139 golden's row shape plus the plan's `stop_ceiling_pct` (column 12), so a later change that stores a ceiling with the floor off shows up here. The capture path writes the fixture only when it is **missing** and `V191_CAPTURE_GOLDEN=1` is set, so it can never overwrite a committed golden.

```python
"""v191 flag-off parity (spec § Testing, first bullet): with
CONFLUENCE_ATR_STOP_FLOOR at 0 (and the v139 knobs at 0, LONG_GAP_SIZING off)
the confluence replay builds and exits exactly the plans it did before v191
touched builders.py, levels.py, backtest_scenarios.py or gap_sizing.py. The
golden was captured at V191-1, before any v191 code change -- never
regenerate it to make this pass."""
import json
import os
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v191" / "flag_off_golden.json"
DELL_END = "2019-12-31"
TRIGGER, LEVEL, CEILING = 4, 8, 12      # row positions of trigger_price, acceptance_level, stop_ceiling_pct
#: Every knob at its inert value. raising=False: the v191 attributes exist from V191-2 on.
INERT = {"CONFLUENCE_ATR_STOP_FLOOR": 0.0, "CONFLUENCE_ATR_TARGET_MODE": "rechoose",
         "LONG_GAP_SIZING": False, "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0,
         "CONFLUENCE_STOP_DROP_PCT": 0.0}


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _r6(value):
    return None if value is None else round(float(value), 6)


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total), exit_index,
                     _r6(plan.stop_ceiling_pct)])
    return rows


def _capture():
    return {"structured": _rows("AAPL", _structured_df()),
            "dell": _rows("DELL", load_ohlcv("DELL").loc[:DELL_END])}


def _golden(captured):
    if os.environ.get("V191_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _clamped(rows):
    return [r for r in rows if r[LEVEL] is not None
            and planned_loss_pct(r[TRIGGER], r[LEVEL]) > HARD_MAX_PLANNED_LOSS_PCT]


def test_knobs_off_replay_matches_the_pre_v191_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    assert len(_clamped(golden["dell"])) >= 5, "the golden must exercise clamped plans"
    assert all(row[CEILING] is None for rows in golden.values() for row in rows), (
        "with every knob off no confluence plan stores a ceiling")
    assert captured == golden
```

- [ ] **Step 3: Capture the replay golden on unmodified code**

```bash
V191_CAPTURE_GOLDEN=1 python -m pytest tests/backtesting/test_v191_flag_off_golden.py -v
```

Expected: `1 passed`; `tests/fixtures/v191/flag_off_golden.json` now exists. Confirm `git status --short swingbot/` prints nothing (no code was touched before the capture).

- [ ] **Step 4: Write the plan-dict golden test** — `tests/planning/test_v191_plan_golden.py`

Fixed scenarios through `build_confluence_plan` on a frame with a real ATR (`spread=0.02`, so V191-8's band would see one), both directions, inside / clamped / tight stops and a sub-$1 entry. The snapshot stores the persisted key order (pins that no `stop_moved_by` key appears) and every value except `plan_id` (a uuid) and the registry-derived stamps (`badge`, `badge_stats`, `cohort_label`, `cohort_stats`, `ledger`), which move with the strategy registry rather than with this plan's code.

```python
"""v191 flag-off parity for the builder: with every v191 knob at its default,
build_confluence_plan returns exactly the plan dicts it did before V191-8
touched it -- same stop, ceiling, targets and the same persisted key list (no
stop_moved_by). Captured at V191-1 on unmodified code; never regenerate."""
import dataclasses
import json
import os
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v191" / "plan_golden.json"
INERT = {"CONFLUENCE_ATR_STOP_FLOOR": 0.0, "CONFLUENCE_ATR_TARGET_MODE": "rechoose",
         "LONG_GAP_SIZING": False, "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0,
         "CONFLUENCE_STOP_DROP_PCT": 0.0, "CLAMP_STOP_TO_HARD_CAP": True}
#: name -> (direction, entry, level stop, own target)
SCENARIOS = {
    "bull_inside": ("bullish", 100.0, 98.2, 104.0),
    "bull_clamped": ("bullish", 100.0, 96.5, 108.0),
    "bull_tight": ("bullish", 100.0, 99.0, 103.0),
    "bear_inside": ("bearish", 100.0, 101.8, 96.0),
    "bear_clamped": ("bearish", 100.0, 103.5, 92.0),
    "bear_tight": ("bearish", 100.0, 101.0, 97.0),
    "penny_bull": ("bullish", 0.85, 0.835, 0.88),
}
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _params():
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0)


def _snapshot(direction, entry, stop, target):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([entry] * 60, spread=0.02), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence",
                                 level_map=None, params=_params())
    if plan is None:
        return None
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _capture():
    return {name: _snapshot(*args) for name, args in SCENARIOS.items()}


def _golden(captured):
    if os.environ.get("V191_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_confluence_plans_match_the_pre_v191_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    built = [snap for snap in golden.values() if snap is not None]
    assert len(built) >= 5, "the golden must hold real plans, not a row of Nones"
    assert all("stop_moved_by" not in snap["keys"] for snap in built)
    assert captured == golden
```

- [ ] **Step 5: Capture the plan golden on unmodified code**

```bash
V191_CAPTURE_GOLDEN=1 python -m pytest tests/planning/test_v191_plan_golden.py -v
```

Expected: `1 passed`; `tests/fixtures/v191/plan_golden.json` exists. Open it and check that `bull_clamped` stores `stop_loss: 98.25` (the v115 1.75% clamp) and `stop_ceiling_pct: null`. If it does not, `CLAMP_STOP_TO_HARD_CAP` did not reach the builder and the capture is void: delete the fixture, fix the patch, capture again — this is the only moment a re-capture is allowed.

- [ ] **Step 6: Re-run both goldens without the capture variable**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
```

Expected: `1 passed` each, `0 failed`. Neither file was rewritten: `git status --short tests/fixtures/v191/` shows both as new and their content is unchanged since Steps 3 and 5.

- [ ] **Step 7: Commit (in the worktree)**

```bash
git add tests/backtesting/test_v191_flag_off_golden.py tests/fixtures/v191/flag_off_golden.json tests/planning/test_v191_plan_golden.py tests/fixtures/v191/plan_golden.json
git commit -m "test(v191): flag-off goldens -- confluence replay rows and plan dicts captured before any change"
```

# Phase 2 — Config, coupling and the plan field

### Task V191-2: Config fields, ScanParams slots, reachability rows
**Model:** sonnet — schema additions following the v139/v183 field pattern; no behaviour reads the knobs yet.

**Files:**
- Modify: `swingbot/config.py` (two `Field`s after `CONFLUENCE_STOP_DROP_PCT` ~:211; one after `SHORT_GAP_SIZING` ~:581 and that field's help; `_SEARCH_CLASSES` ~:1457; `_MODE_VALUES` / `_MODE_FALLBACK` ~:1527-1543)
- Modify: `swingbot/scan_params.py` (slots after `confluence_stop_drop_pct` ~:97; `from_config` ~:164)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (`_V191` text and two `REGISTRY` rows after the v139 rows ~:131)
- Modify: `.env.example` (three lines; `tests/market/test_v115_strategy_work_off.py` reads it)
- Modify: `tests/market/test_v115_strategy_work_off.py` (`FLAGS_OFF`)
- Modify: `tests/planning/test_v183_config_switches.py` (`EXPECTED` gains `LONG_GAP_SIZING`; field order)
- Create: `tests/test_config_v191_atr_band.py`

**Interfaces:**
- Consumes: `Field` (config.py:73), `_cast`, `searchable_attrs()`, `reach.Reach`, `reach.REACHABLE`, `reach.C`, `arms.knobs.parse_knob`. All exist.
- Produces (final, § Contracts): `config.CONFLUENCE_ATR_STOP_FLOOR: float` (default `0.0`), `config.CONFLUENCE_ATR_TARGET_MODE: str` (`"rechoose"` | `"keep"`, default `"rechoose"`), `config.LONG_GAP_SIZING: bool` (default `False`); `ScanParams.confluence_atr_stop_floor: float = 0.0`, `ScanParams.confluence_atr_target_mode: str = "rechoose"`; `REGISTRY["CONFLUENCE_ATR_STOP_FLOOR"]`, `REGISTRY["CONFLUENCE_ATR_TARGET_MODE"]` (both `REACHABLE`, `observed_by == C`). Nothing reads any of them in this task.

- [ ] **Step 1: Write the failing tests** — `tests/test_config_v191_atr_band.py`

```python
"""v191: the ATR-band knobs and the long gap-sizing switch -- schema,
ScanParams, reachability, .env.example. Every one ships inert."""
import pathlib

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

REPO = pathlib.Path(__file__).resolve().parents[1]
FLOOR, MODE, LONG = "CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE", "LONG_GAP_SIZING"


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_floor_is_an_inert_searchable_float_capped_below_the_ceiling():
    f = _field(FLOOR)
    assert (f.key, f.section, f.type, f.default) == (FLOOR, "Trade Filters & Risk", "float", "0")
    assert (f.min, f.max, f.step) == (0, 1.5, 0.25)
    assert f.max < 2.0                                  # k < BAND_CEILING_ATR, so lo < hi always
    assert f.search_class == "searchable" and FLOOR in config.searchable_attrs()
    assert config._cast(f, f.default) == 0.0
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0


def test_target_mode_is_a_searchable_select_defaulting_to_rechoose():
    f = _field(MODE)
    assert (f.key, f.section, f.type, f.default) == (MODE, "Trade Filters & Risk", "select", "rechoose")
    assert [value for value, _label in f.options] == ["rechoose", "keep"]
    assert f.search_class == "searchable" and MODE in config.searchable_attrs()
    assert config._cast(f, "KEEP") == "keep"
    assert config._cast(f, "typo") == "rechoose"        # an unknown value lands on today's arm
    assert config.CONFLUENCE_ATR_TARGET_MODE == "rechoose"


def test_the_band_fields_follow_the_v139_knobs():
    attrs = [f.attr for f in config.FIELDS]
    base = attrs.index("CONFLUENCE_STOP_DROP_PCT")
    assert attrs[base + 1:base + 3] == [FLOOR, MODE]


def test_floor_help_names_the_coupling_and_the_default():
    text = _field(FLOOR).help
    assert "LONG_GAP_SIZING" in text and "SHORT_GAP_SIZING" in text
    assert "Keep 0" in text


def test_short_gap_sizing_help_no_longer_claims_longs_are_never_affected():
    assert "Longs are never affected" not in _field("SHORT_GAP_SIZING").help
    assert "LONG_GAP_SIZING" in _field("SHORT_GAP_SIZING").help


def test_scan_params_defaults_are_off():
    params = ScanParams.from_config()
    assert params.confluence_atr_stop_floor == 0.0
    assert params.confluence_atr_target_mode == "rechoose"


@pytest.mark.parametrize("attr,value", [(FLOOR, 1.0), (MODE, "keep")])
def test_scan_params_carries_the_knob(attr, value, monkeypatch):
    monkeypatch.setattr(config, attr, value)
    assert getattr(ScanParams.from_config(), attr.lower()) == value


@pytest.mark.parametrize("attr", [FLOOR, MODE])
def test_reachability_row_is_confluence_only(attr):
    assert reach.classify(attr) == reach.REACHABLE
    assert reach.REGISTRY[attr].observed_by == reach.C
    assert "measure_arms.py" in reach.REGISTRY[attr].reason        # names what does NOT measure it


def test_measure_arms_parses_the_knobs():
    assert parse_knob(f"{FLOOR}=1.0") == (FLOOR, 1.0)
    assert parse_knob(f"{MODE}=keep") == (MODE, "keep")


def test_long_gap_sizing_is_not_searchable():
    assert LONG not in config.searchable_attrs()


def test_env_example_ships_all_three_inert():
    env = dotenv_values(REPO / ".env.example")
    assert (env.get(FLOOR), env.get(MODE), env.get(LONG)) == ("0", "rechoose", "false")
```

Add to `tests/planning/test_v183_config_switches.py`:

```python
# in EXPECTED:
    "LONG_GAP_SIZING": ("Account Defaults", "checkbox", "false", False, None, None, None),


def test_long_gap_switch_follows_the_short_one():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("LONG_GAP_SIZING") == attrs.index("SHORT_GAP_SIZING") + 1
```

(`test_field_schema` then also asserts `LONG_GAP_SIZING` is `live_only`, hot-reloadable and not searchable.)

Add three rows to `FLAGS_OFF` in `tests/market/test_v115_strategy_work_off.py`, after the v139 rows:

```python
    ("v191", "CONFLUENCE_ATR_STOP_FLOOR", 0.0),
    ("v191", "CONFLUENCE_ATR_TARGET_MODE", "rechoose"),
    ("v191", "LONG_GAP_SIZING", False),
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/test_config_v191_atr_band.py
```

Expected: FAIL — `StopIteration` in `_field` (no such field) and `AttributeError` on `ScanParams`.

- [ ] **Step 3: Add the three `Field`s in `swingbot/config.py`**

After `CONFLUENCE_STOP_DROP_PCT`:

```python
    Field("CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_STOP_FLOOR", "Trade Filters & Risk",
          "Confluence ATR stop floor k (v191)",
          type="float", default="0", min=0, max=1.5, step=0.25,
          help="v191 pre-registration. 0 = off: today's 1.75-2% stop band. Above 0, a confluence "
               "plan's stop sits no closer than k x ATR14 and no further than 2 x ATR14 (rounded to "
               "the tick away from entry), the percent stop gates and the 2% clamp step aside for "
               "that plan, and shares are sized so the worst accepted fill to the stop, plus the "
               "p99 gap allowance, never loses more than the per-trade risk. Honoured live only "
               "with LONG_GAP_SIZING and SHORT_GAP_SIZING both on -- otherwise treated as 0 and "
               "logged as an error. Unmeasured; Keep 0 until the partner decides."),
    Field("CONFLUENCE_ATR_TARGET_MODE", "CONFLUENCE_ATR_TARGET_MODE", "Trade Filters & Risk",
          "Confluence ATR-band target mode (v191)",
          type="select", default="rechoose", options=["rechoose", "keep"],
          help="v191. Read only when CONFLUENCE_ATR_STOP_FLOOR is above 0. rechoose (arm R): TP1 "
               "is picked again against the band stop's risk. keep (arm K): TP1 stays where "
               "today's 1.75-2% stop put it and the plan is dropped when its reward:risk against "
               "the band stop falls under the minimum."),
```

After `SHORT_GAP_SIZING` (and in `SHORT_GAP_SIZING`'s help replace the closing `"Longs are never affected."` with `"Longs follow LONG_GAP_SIZING."`; keep the `byte-for-byte` sentence):

```python
    Field("LONG_GAP_SIZING", "LONG_GAP_SIZING", "Account Defaults",
          "LONG gap-aware sizing (v191)", type="checkbox", default="false",
          help="v191 Part B. On: a LONG plan is sized on max(stop distance, entry x the ticker's "
               "p99 down-gap over 250 completed bars), the mirror of SHORT_GAP_SIZING, so a "
               "routine bad gap through the stop stays inside the per-trade dollar risk. A gap "
               "beyond the ticker's own p99 still can exceed it. The stop never moves and R stays "
               "measured on the stop; only the share count can shrink. Stamped on each plan at "
               "creation, so flipping this never resizes an alerted plan. Off (default): every "
               "long is sized on the stop, byte-for-byte as before v191."),
```

In `_SEARCH_CLASSES["searchable"]` add `"CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE"`; in `"live_only"` add `"LONG_GAP_SIZING"`. In `_MODE_VALUES` add `"CONFLUENCE_ATR_TARGET_MODE": ("rechoose", "keep")` and in `_MODE_FALLBACK` add `"CONFLUENCE_ATR_TARGET_MODE": "rechoose"` (a typo must land on today's default, not on `"off"`, which is not a value of this select).

- [ ] **Step 4: Add the `ScanParams` slots** — `swingbot/scan_params.py`

```python
    confluence_atr_stop_floor: float = 0.0        # v191 k; 0 = today's percent band
    confluence_atr_target_mode: str = "rechoose"  # v191: rechoose (arm R) | keep (arm K)
```

directly after `confluence_stop_drop_pct`, and in `from_config` after the v139 pair:

```python
            confluence_atr_stop_floor=config.CONFLUENCE_ATR_STOP_FLOOR,
            confluence_atr_target_mode=config.CONFLUENCE_ATR_TARGET_MODE,
```

- [ ] **Step 5: Add the reachability rows** — `swingbot/core/backtesting/arms/reachability.py`

Next to `_V139`:

```python
_V191 = ("v191: atr_band.band_stop inside builders.build_confluence_plan, and the band admission "
         "in levels.build_scenarios that backtest_scenarios.scenarios_at reaches, so "
         "replay_scenarios (ConfluenceEngine) observes it. Confluence plans only; strategy plans "
         "never. Gated by the v92 harvest gate through a v139-style staged driver, not "
         "measure_arms.py.")
```

and after the v139 rows in `REGISTRY`:

```python
    "CONFLUENCE_ATR_STOP_FLOOR": Reach(REACHABLE, _V191, C),
    "CONFLUENCE_ATR_TARGET_MODE": Reach(REACHABLE, _V191 + " Read only when "
                                        "CONFLUENCE_ATR_STOP_FLOOR > 0; a lone perturbation at "
                                        "floor 0 is inert by design.", C),
```

(V191-17 names the driver script in `_V191` once it exists.)

- [ ] **Step 6: Add the three keys to `.env.example`**

After `CONFLUENCE_STOP_DROP_PCT=0`:

```
# v191 confluence ATR-band stops (pre-registration; keep 0). Live only with LONG_GAP_SIZING and SHORT_GAP_SIZING on.
CONFLUENCE_ATR_STOP_FLOOR=0
CONFLUENCE_ATR_TARGET_MODE=rechoose
```

After `SHORT_GAP_SIZING=true`:

```
# v191 Part B: size longs on max(stop distance, p99 down-gap). Off by default.
LONG_GAP_SIZING=false
```

- [ ] **Step 7: Run the tests to see them pass**

```bash
python scripts/dev/testrun.py file tests/test_config_v191_atr_band.py
python scripts/dev/testrun.py file tests/planning/test_v183_config_switches.py
python scripts/dev/testrun.py file tests/market/test_v115_strategy_work_off.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py
python scripts/dev/testrun.py file tests/test_config_v139_confluence_stop.py
python -m pytest tests/backtesting/test_knob_observability.py::test_every_searchable_knob_is_classified -q
```

Expected: all pass, `0 failed`. `test_every_searchable_knob_is_classified` proves the two searchable fields each have a `REGISTRY` row.

- [ ] **Step 8: Goldens and complexity**

```bash
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/complexity_gate.py
```

Expected: both goldens `1 passed`; the gate passes (no function grew).

- [ ] **Step 9: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py .env.example tests/test_config_v191_atr_band.py tests/planning/test_v183_config_switches.py tests/market/test_v115_strategy_work_off.py
git commit -m "feat(v191): CONFLUENCE_ATR_STOP_FLOOR, CONFLUENCE_ATR_TARGET_MODE and LONG_GAP_SIZING -- inert fields, ScanParams slots, reachability rows"
```

### Task V191-3: Coupling guard: config load/reload and admin validator
**Model:** sonnet — two small guards on existing load and validation paths, with tests modelled on the settings suite.

**Files:**
- Modify: `swingbot/config.py` (new `enforce_atr_band_coupling` and `_note_floor_change` above `_apply_env` ~:1582; `_apply_env` calls them before `return changed`)
- Modify: `swingbot/admin/api_v1/system.py` (new `_coupling_problem` beside `_validate` ~:127; `_validate`'s final `return None` becomes `return _coupling_problem(values)`)
- Modify: `tests/admin/test_api_v1_system_settings.py` (coupling tests in the validation block)
- Create: `tests/test_config_v191_coupling.py`

**Interfaces:**
- Consumes: `config.CONFLUENCE_ATR_STOP_FLOOR`, `config.LONG_GAP_SIZING`, `config.SHORT_GAP_SIZING` (V191-2); `system._effective_form(values)` (exists, system.py:164).
- Produces: `config.enforce_atr_band_coupling() -> bool` — True when it zeroed the floor; run at the end of every `_apply_env` (module import and every `reload()`/SIGHUP). `system._coupling_problem(values: Mapping) -> tuple[str, str] | None` — `("invalid", COUPLING_MESSAGE)` when the effective form has a floor above 0 without both gap-sizing boxes on. Replay and measurement are uncoupled by construction: `arms.knobs.apply_knobs` sets globals without `_apply_env`.

Spec § Part B, Coupling: a live `CONFLUENCE_ATR_STOP_FLOOR > 0` is honoured only with `LONG_GAP_SIZING` and `SHORT_GAP_SIZING` both on; a hand-edited `.env` must not bypass it, and the admin save refuses the combination. `SHORT_GAP_SIZING` already defaults to `true`, so in practice the partner turns `LONG_GAP_SIZING` on alongside a floor.

- [ ] **Step 1: Write the failing config tests** — `tests/test_config_v191_coupling.py`

`_apply_env` rewrites every `FIELDS` global from `os.environ`, so a fixture snapshots and restores all of them; `reload()` is never called here (it re-reads the developer's real `.env` with `override=True`). `reload()` and the module import both go through `_apply_env`, which is what these tests drive.

```python
"""v191 coupling: a live CONFLUENCE_ATR_STOP_FLOOR > 0 needs LONG_GAP_SIZING
and SHORT_GAP_SIZING both on. Config load and every reload treat a broken
combination as floor 0 and log an ERROR, so a hand-edited .env cannot
bypass the admin validator."""
import logging

import pytest

from swingbot import config

FLOOR = "CONFLUENCE_ATR_STOP_FLOOR"


@pytest.fixture(autouse=True)
def _restore_config():
    saved = {f.attr: getattr(config, f.attr) for f in config.FIELDS if hasattr(config, f.attr)}
    yield
    for attr, value in saved.items():
        setattr(config, attr, value)


def _set(monkeypatch, floor, long_on, short_on):
    monkeypatch.setattr(config, FLOOR, floor)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", long_on)
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", short_on)


@pytest.mark.parametrize("long_on,short_on", [(False, True), (True, False), (False, False)])
def test_a_floor_without_both_gap_flags_is_zeroed_and_logged(monkeypatch, caplog, long_on, short_on):
    _set(monkeypatch, 1.0, long_on, short_on)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is True
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "CONFLUENCE_ATR_STOP_FLOOR=1.0" in errors[0].getMessage()
    assert "treated as 0" in errors[0].getMessage()


def test_a_floor_with_both_flags_on_is_honoured(monkeypatch, caplog):
    _set(monkeypatch, 1.5, True, True)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is False
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 1.5
    assert not caplog.records


def test_floor_zero_never_logs(monkeypatch, caplog):
    _set(monkeypatch, 0.0, False, False)
    with caplog.at_level(logging.ERROR, logger="swingbot.config"):
        assert config.enforce_atr_band_coupling() is False
    assert not caplog.records


def test_apply_env_enforces_the_coupling(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "false")
    monkeypatch.setenv("SHORT_GAP_SIZING", "true")
    monkeypatch.setattr(config, FLOOR, 0.0)
    changed = config._apply_env()
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 0.0
    assert FLOOR not in changed                       # 0 -> 0: nothing changed for reload() to log


def test_apply_env_reports_a_live_floor_switched_off(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "false")
    monkeypatch.setattr(config, FLOOR, 1.5)            # was live before this reload
    assert config._apply_env()[FLOOR] == (1.5, 0.0)


def test_apply_env_keeps_a_coupled_floor(monkeypatch):
    monkeypatch.setenv(FLOOR, "1.0")
    monkeypatch.setenv("LONG_GAP_SIZING", "true")
    monkeypatch.setenv("SHORT_GAP_SIZING", "true")
    config._apply_env()
    assert config.CONFLUENCE_ATR_STOP_FLOOR == 1.0


def test_reload_goes_through_apply_env():
    import inspect
    assert "_apply_env()" in inspect.getsource(config.reload)
```

`config.log` is `logging.getLogger(__name__)` (config.py:56), hence the logger name `"swingbot.config"`.

- [ ] **Step 2: Write the failing admin tests** — append to the `# --- validation` block of `tests/admin/test_api_v1_system_settings.py`

```python
# v191: a live ATR stop floor needs both gap-sizing switches (spec § Part B, Coupling).

def test_a_floor_without_long_gap_sizing_is_rejected(logged_in, env_file):
    env_file({"SHORT_GAP_SIZING": "true", "LONG_GAP_SIZING": "false"})
    response = logged_in.put("/api/v1/system/settings",
                             json={"settings": {"CONFLUENCE_ATR_STOP_FLOOR": "1.0"}})
    assert_error(response, "invalid", 400)
    assert "LONG_GAP_SIZING" in response.get_json()["error"]["message"]
    assert env_file.read().get("CONFLUENCE_ATR_STOP_FLOOR") in (None, "0"), "nothing written"


def test_a_floor_with_both_switches_in_the_same_body_is_saved(logged_in, env_file):
    env_file({"SHORT_GAP_SIZING": "true"})
    response = logged_in.put("/api/v1/system/settings", json={"settings": {
        "CONFLUENCE_ATR_STOP_FLOOR": "1.0", "LONG_GAP_SIZING": True}})
    assert response.status_code == 200
    saved = env_file.read()
    assert (saved["CONFLUENCE_ATR_STOP_FLOOR"], saved["LONG_GAP_SIZING"]) == ("1.0", "true")


def test_turning_short_gap_sizing_off_under_a_live_floor_is_rejected(logged_in, env_file):
    env_file({"CONFLUENCE_ATR_STOP_FLOOR": "1.0", "LONG_GAP_SIZING": "true", "SHORT_GAP_SIZING": "true"})
    assert_error(logged_in.put("/api/v1/system/settings",
                               json={"settings": {"SHORT_GAP_SIZING": False}}), "invalid", 400)
    assert env_file.read()["SHORT_GAP_SIZING"] == "true"


def test_the_preview_refuses_the_same_combination(logged_in, env_file):
    env_file({"LONG_GAP_SIZING": "false"})
    assert_error(logged_in.post("/api/v1/system/settings/preview",
                                json={"settings": {"CONFLUENCE_ATR_STOP_FLOOR": "0.75"}}),
                 "invalid", 400)


def test_a_zero_floor_never_needs_the_switches(logged_in, env_file):
    env_file({"LONG_GAP_SIZING": "false", "SHORT_GAP_SIZING": "false"})
    response = logged_in.put("/api/v1/system/settings",
                             json={"settings": {"CONFLUENCE_ATR_STOP_FLOOR": "0"}})
    assert response.status_code == 200
```

The error body is `{"error": {"code", "message"}}` (`tests/admin/api_v1_contract.py:assert_error`).

- [ ] **Step 3: Run both to see them fail**

```bash
python scripts/dev/testrun.py file tests/test_config_v191_coupling.py
python -m pytest tests/admin/test_api_v1_system_settings.py -k "floor or short_gap_sizing_off or preview_refuses" -q
```

Expected: FAIL — `AttributeError: module 'swingbot.config' has no attribute 'enforce_atr_band_coupling'`; the admin tests get 200 where 400 is expected.

- [ ] **Step 4: Implement the bot-side guard** — `swingbot/config.py`, above `_apply_env`

```python
def enforce_atr_band_coupling() -> bool:
    """v191: a live CONFLUENCE_ATR_STOP_FLOOR > 0 needs LONG_GAP_SIZING and
    SHORT_GAP_SIZING both on (partner, 2026-10-24). Otherwise the floor is
    treated as 0 and the refusal logged at ERROR. Runs at the end of every
    _apply_env (import and reload), so a hand-edited .env cannot bypass the
    admin validator. Replay sets knobs through arms.knobs.apply_knobs, which
    never calls this, so measurement is uncoupled. True when it zeroed the floor."""
```

Body: read the three globals with `globals().get(..., default)`; return False when the floor is `<= 0` or both flags are truthy; otherwise `log.error("CONFLUENCE_ATR_STOP_FLOOR=%s needs LONG_GAP_SIZING and SHORT_GAP_SIZING both on (LONG_GAP_SIZING=%s, SHORT_GAP_SIZING=%s) -- treated as 0 (v191 coupling)", floor, long_on, short_on)`, set the global to `0.0`, return True.

```python
def _note_floor_change(changed: dict, before) -> None:
    """Re-state the floor's entry in _apply_env's change map after the coupling zeroed it."""
    changed.pop("CONFLUENCE_ATR_STOP_FLOOR", None)
    if before != 0.0:
        changed["CONFLUENCE_ATR_STOP_FLOOR"] = (before, 0.0)
```

In `_apply_env`: capture `floor_before = g.get("CONFLUENCE_ATR_STOP_FLOOR")` right after `g = globals()`, and before `return changed` add

```python
    if enforce_atr_band_coupling():
        _note_floor_change(changed, floor_before)
```

`_apply_env` gains one branch (it stays far below 15).

- [ ] **Step 5: Implement the admin guard** — `swingbot/admin/api_v1/system.py`

```python
COUPLING_MESSAGE = ("Confluence ATR stop floor above 0 needs LONG_GAP_SIZING and "
                    "SHORT_GAP_SIZING both on (v191: the planned loss must stay inside the "
                    "per-trade risk on a gap)")


def _coupling_problem(values: Mapping) -> tuple[str, str] | None:
    """v191: refuse an effective form (submitted keys over what is on disk) that
    sets a live ATR stop floor without both gap-sizing checkboxes on. Runs after
    the per-field checks, so the floor is already a valid number or blank."""
```

Body: `form = _effective_form(values)`; `floor = float(form.get("CONFLUENCE_ATR_STOP_FLOOR") or 0)`; return None when `floor <= 0`; a checkbox is on exactly when its key is present in the form (`_effective_form` drops unchecked boxes), so return None when both `"LONG_GAP_SIZING"` and `"SHORT_GAP_SIZING"` are in `form`; else `("invalid", COUPLING_MESSAGE)`. Replace `_validate`'s final `return None` with `return _coupling_problem(values)` (no new branch in `_validate`).

- [ ] **Step 6: Run the tests to see them pass**

```bash
python scripts/dev/testrun.py file tests/test_config_v191_coupling.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_system_settings.py
python scripts/dev/testrun.py file tests/test_config_v191_atr_band.py
python scripts/dev/complexity_gate.py
```

Expected: all pass, `0 failed`; every pre-existing settings test still passes (a body without the floor never trips the guard because the on-disk floor defaults to `0`); the complexity gate passes.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py swingbot/admin/api_v1/system.py tests/test_config_v191_coupling.py tests/admin/test_api_v1_system_settings.py
git commit -m "feat(v191): couple a live ATR stop floor to both gap-sizing switches -- config load/reload and the admin validator"
```

### Task V191-4: `TradePlanV2.stop_moved_by` with serialization and DB round trip
**Model:** sonnet — one optional dataclass field on the `schema-evolution.md` ADD path, with a DB round trip that must actually run.

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (field after `risk_notice` ~:204; `_OMIT_WHEN_NONE` ~:231)
- Modify: `tests/planning/test_plan_serialization.py`
- Modify: `tests/db/test_plans_repository.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TradePlanV2.stop_moved_by: str | None = None` — `"floor"` | `"ceiling"` | `"untouched"` on a band plan (set by V191-8 from `atr_band.MOVED_*`), `None` everywhere else. In `_OMIT_WHEN_NONE`, so `plan_to_dict` drops it while `None` and every existing plan doc — including the long key pin `PRE_V183_PLAN_KEYS` in `tests/planning/test_gap_sizing.py` and the V191-1 plan golden — stays byte-identical. Rides in `plans.doc` JSONB: no column, no Alembic revision, no read-time upcasting (`plan_from_dict` defaults a missing key to `None`).

The field goes **after `risk_notice`**, the last field, so `dataclasses.asdict` order is unchanged for every existing key; a band plan's doc gains the key at the end.

- [ ] **Step 1: Write the failing serialization tests** — append to `tests/planning/test_plan_serialization.py`

```python
def test_stop_moved_by_defaults_to_none_and_is_omitted_while_none():
    """v191: only a band plan carries the key; every other plan doc is unchanged."""
    assert _plan().stop_moved_by is None
    assert "stop_moved_by" not in plan_to_dict(_plan())


@pytest.mark.parametrize("moved_by", ["floor", "ceiling", "untouched"])
def test_stop_moved_by_round_trips(moved_by):
    d = plan_to_dict(_plan(stop_moved_by=moved_by, stop_ceiling_pct=7.25))
    assert d["stop_moved_by"] == moved_by
    assert list(d)[-1] == "stop_moved_by"                # appended, no existing key moves
    q = plan_from_dict(json.loads(json.dumps(d)))
    assert (q.stop_moved_by, q.stop_ceiling_pct) == (moved_by, 7.25)


def test_pre_v191_record_without_stop_moved_by_loads_as_none():
    d = plan_to_dict(_plan(stop_ceiling_pct=4.0))
    assert "stop_moved_by" not in d
    assert plan_from_dict(d).stop_moved_by is None


def test_omit_when_none_lists_the_v191_key():
    from swingbot.core.planning.plan_types import _OMIT_WHEN_NONE
    assert _OMIT_WHEN_NONE == ("gap_sizing", "risk_notice", "stop_moved_by")
```

Add `import json` and `import pytest` at the top of the module if they are not imported yet.

- [ ] **Step 2: Write the failing DB round trip** — append to `tests/db/test_plans_repository.py`

```python
def test_v191_stop_moved_by_rides_in_the_doc(repo, db_conn):
    """v191 used schema-evolution's ADD path: no column, no revision -- the band
    plan's stop_moved_by and its stored ceiling live in plans.doc."""
    from tests.db_diff import diff_records
    record = _plan("P1", source="confluence", stop_ceiling_pct=6.1, stop_moved_by="floor")
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []
```

- [ ] **Step 3: Run the serialization tests to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
```

Expected: FAIL — `TypeError: ... unexpected keyword argument 'stop_moved_by'` and the `_OMIT_WHEN_NONE` assertion.

- [ ] **Step 4: Add the field** — `swingbot/core/planning/plan_types.py`

After `risk_notice`:

```python
    # v191 (planning/builders.py, atr_band.py): where the ATR band put the stop
    # of a confluence band plan -- "floor" (moved out to k x ATR14), "ceiling"
    # (moved in to 2 x ATR14) or "untouched" (the level, inside the band). Set
    # once at creation with stop_ceiling_pct; None for every plan built with
    # CONFLUENCE_ATR_STOP_FLOOR at 0 and every plan persisted before v191.
    # Omitted from plan_to_dict while None (_OMIT_WHEN_NONE).
    stop_moved_by: str | None = None
```

and `_OMIT_WHEN_NONE = ("gap_sizing", "risk_notice", "stop_moved_by")`, with its comment saying "v183/v191".

- [ ] **Step 5: Run the serialization, key-pin and golden tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
```

Expected: all pass — `PRE_V183_PLAN_KEYS` and the plan golden still match (the key is omitted while `None`).

- [ ] **Step 6: Run the DB round trip against a live test database**

First `/replicate-prod-db` into the shared `swing-db` container (CLAUDE.md: a task that runs tests against the database). Then:

```bash
docker compose --profile test up -d db-test
python -m pytest tests/db/test_plans_repository.py -v -rs
```

Expected: `test_v191_stop_moved_by_rides_in_the_doc PASSED` and the v129/v139 doc tests still PASS. **A `SKIPPED` line is a failure of this step** (`docs/claude/known-traps.md` / test-infra pitfalls: the default DB port skips silently) — fix the connection and re-run; never commit with it skipped.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/plan_types.py tests/planning/test_plan_serialization.py tests/db/test_plans_repository.py
git commit -m "feat(v191): TradePlanV2.stop_moved_by -- omitted while None, rides in plans.doc"
```

# Phase 3 — Part B: gap-aware sizing for longs

### Task V191-5: Part B core: down-gap p99, long stamp and sizing behind `LONG_GAP_SIZING`
**Model:** opus — the one sizing path every alert, engine and paper trade shares; a wrong branch silently resizes longs or breaks v183's byte-for-byte long pin.

**Files:**
- Modify: `swingbot/core/edge/gates.py` (`gap_stats` :16-30 and a new `_down_gap_stats` beside `_up_gap_stats` :33)
- Modify: `swingbot/core/planning/gap_sizing.py` (module docstring, stamp, floor, `size_for`, `gap_risk_amount_for`)
- Modify: `tests/edge/test_edge_gates.py` (`test_existing_keys_are_unchanged_by_the_new_ones` key set; a down-gap test)
- Modify: `tests/planning/test_gap_sizing.py` (autouse `_env` pins `LONG_GAP_SIZING` off)
- Create: `tests/planning/test_gap_sizing_long.py`

**Interfaces:**
- Consumes: `config.LONG_GAP_SIZING` (V191-2); `account.compute_position_size(entry, stop_loss, account_cfg, *, gap_floor_pct=)` and `account._sizing_distance` (exist, direction-agnostic: `max(stop distance, entry × floor / 100)`).
- Produces (§ Contracts):
  - `gap_stats(df, lookback=250)` gains `"p99_down_gap_pct": float | None` (p99 of the absolute size of the strictly negative gaps, a positive percent; `None` when there are none) and `"n_down": int`; the empty-frame return carries both (`None`, `0`).
  - `gap_sizing.MIN_DOWN_GAPS = 60`.
  - The long stamp `{"rule": RULE_GAP | RULE_STOP, "down_gap_p99_pct": float | None, "n_down_gaps": int}`. In this task it exists only when `LONG_GAP_SIZING` is on, with `rule == RULE_GAP`. A long is on the gap path **only when its stamp carries `n_down_gaps`** — a long handed a short-shaped stamp (`up_gap_p99_pct`) still sizes exactly as today, which keeps `tests/planning/test_long_sizing_regression.py` green.
  - `gap_floor_for(direction, gap_sizing)`: bullish reads `down_gap_p99_pct`, bearish `up_gap_p99_pct`; `None` for any other direction, no stamp, rule `stop`, or a missing / non-positive p99.
  - `gap_risk_amount_for(shares, entry, stop_loss, gap_sizing, direction: str = "bearish") -> float | None` — the default keeps every current caller's result.
  - Private helpers V191-11 reuses in the same file: `_short_stamp(df) -> dict`, `_long_stamp(df, rule: str) -> dict`, `_on_gap_path(direction, gap_sizing) -> bool`.

The rule mirrors v183 exactly (spec § Part B): shares sized on `max(stop distance, entry × p99 / 100)`, at least 60 down-gaps over the 250-bar lookback or "sized on the stop", stamped once at live creation from completed bars (both stamp sites — `analyze._stamp_gap_sizing_live` and `strategy_pass.build_strategy_plan_at` — already pass a completed frame and call `stamp_gap_sizing`, so they need no edit). Sizing and display only: R stays on the stop.

- [ ] **Step 1: Write the failing gate test** — in `tests/edge/test_edge_gates.py`

Change the key set in `test_existing_keys_are_unchanged_by_the_new_ones` to

```python
    assert set(stats) == {"p90_gap_pct", "p99_gap_pct", "n", "p99_up_gap_pct", "n_up",
                          "p99_down_gap_pct", "n_down"}
```

and add

```python
def test_down_gap_p99_measures_only_the_adverse_side_for_a_long():
    stats = gap_stats(_signed_gaps())                         # up 2%, down 6%, alternating
    assert stats["p99_down_gap_pct"] == pytest.approx(6.0)    # a positive percent
    assert stats["n_down"] == 125
    assert stats["p99_up_gap_pct"] == pytest.approx(2.0)      # v183 keys unchanged
    assert stats["n_up"] == 125


def test_no_down_gaps_gives_none_and_an_empty_frame_carries_both_keys():
    only_up = _signed_gaps(down_pct=-2.0)                     # every gap opens above the prior close
    assert gap_stats(only_up)["p99_down_gap_pct"] is None and gap_stats(only_up)["n_down"] == 0
    empty = gap_stats(_signed_gaps().iloc[:1])
    assert (empty["p99_down_gap_pct"], empty["n_down"]) == (None, 0)
```

- [ ] **Step 2: Write the failing long sizing tests** — `tests/planning/test_gap_sizing_long.py`

```python
"""v191 Part B: LONG_GAP_SIZING sizes a long on max(stop distance, entry x the
p99 down-gap) -- v183's short rule, mirrored. Off by default; a long without a
long stamp sizes exactly as before v191."""
import json
import logging

import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import strategy_pass as sp
from tests.planning.test_gap_sizing import CFG, NO_GAP, PRE_V183_PLAN_KEYS, _attach, _plan, _signed_gaps

LONG_STAMP = {"rule": "gap_p99", "down_gap_p99_pct": 3.0, "n_down_gaps": 125}
BUDGET = CFG["balance"] * CFG["risk_pct"] / 100          # $100


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(config, "SHORT_RISK_NOTICE", False)


# --- the stamp ---------------------------------------------------------------

def test_switch_off_leaves_a_long_unstamped(monkeypatch):
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    assert gs.gap_sizing_stamp(_signed_gaps(), "bullish") is None


def test_stamp_for_a_long_reads_the_down_gap_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(), "bullish")       # up 2%, down 6%
    assert stamp == {"rule": "gap_p99", "down_gap_p99_pct": pytest.approx(6.0), "n_down_gaps": 125}


def test_the_short_stamp_is_unchanged_by_the_long_switch():
    assert gs.gap_sizing_stamp(_signed_gaps(), "bearish") == {
        "rule": "gap_p99", "up_gap_p99_pct": pytest.approx(2.0), "n_up_gaps": 125}


def test_too_few_down_gaps_records_no_p99():
    stamp = gs.gap_sizing_stamp(_signed_gaps(n=100), "bullish")   # 99 gaps, 50 down < 60
    assert stamp == {"rule": "gap_p99", "down_gap_p99_pct": None, "n_down_gaps": 50}
    assert gs.MIN_DOWN_GAPS == 60


def test_stamp_never_raises_for_a_long_and_logs_once(caplog):
    plan = _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, None)
    assert plan.gap_sizing == {"rule": "gap_p99", "down_gap_p99_pct": None, "n_down_gaps": 0}
    assert len([r for r in caplog.records if "ZZZ: gap sizing" in r.getMessage()]) == 1


def test_missing_down_p99_is_logged_at_stamp_time(caplog):
    plan = _plan("bullish")
    with caplog.at_level(logging.INFO, logger="swingbot.core.planning.gap_sizing"):
        gs.stamp_gap_sizing(plan, _signed_gaps(n=100))
    assert "ZZZ: gap sizing p99 n/a (50 down-gaps, need 60) -- sized on the stop" in caplog.text


# --- the one sizing path --------------------------------------------------------

def test_gap_floor_for_reads_the_side_that_hurts():
    assert gs.gap_floor_for("bullish", LONG_STAMP) == 3.0
    assert gs.gap_floor_for("bearish", LONG_STAMP) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "rule": "stop"}) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "down_gap_p99_pct": None}) is None
    assert gs.gap_floor_for("bullish", {**LONG_STAMP, "down_gap_p99_pct": 0.0}) is None
    assert gs.gap_floor_for(None, LONG_STAMP) is None


def test_long_with_the_gap_rule_is_cut():
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=LONG_STAMP)
    assert (out["shares"], out["risk_amount"], out["gap_risk_amount"], out["gap_sized"]) == \
        (33.33, 66.67, 100.0, True)


def test_long_whose_p99_is_inside_the_stop_is_not_cut():
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing={**LONG_STAMP, "down_gap_p99_pct": 1.0})
    assert (out["shares"], out["gap_sized"]) == (50.0, False)


def test_long_without_a_usable_p99_sizes_on_the_stop_and_says_n_a():
    plain = account.compute_position_size(100.0, 98.0)
    stamp = {**LONG_STAMP, "down_gap_p99_pct": None, "n_down_gaps": 40}
    assert gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=stamp) == {**plain, **NO_GAP}


@pytest.mark.parametrize("stamp", [None, {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120},
                                   {**LONG_STAMP, "rule": "stop"}])
def test_a_long_without_a_long_gap_stamp_is_todays_sizing_byte_for_byte(stamp):
    plain = account.compute_position_size(100.0, 98.0)
    out = gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=stamp)
    assert out == plain and json.dumps(out) == json.dumps(plain)


@pytest.mark.parametrize("entry,stop,p99", [(100.0, 98.0, 0.5), (100.0, 98.0, 3.0), (100.0, 98.5, 9.0),
                                            (37.13, 36.02, 4.4), (412.7, 401.9, 2.6)])
def test_dollar_loss_on_a_p99_gap_stays_inside_the_budget(entry, stop, p99):
    out = gs.size_for(entry, stop, direction="bullish",
                      gap_sizing={**LONG_STAMP, "down_gap_p99_pct": p99})
    distance = max(entry - stop, entry * p99 / 100)
    # v183's rule rounds shares to the cent-share, so one rounding step (0.005 shares)
    # is the only slack; V191-11's band branch floors instead and has none.
    assert out["shares"] * distance <= BUDGET + 0.005 * distance + 1e-9


def test_a_later_switch_flip_never_resizes_a_stamped_long(monkeypatch):
    plan = _plan("bullish", gap_sizing=LONG_STAMP)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    assert gs.size_for_plan(plan, entry=100.0)["shares"] == 33.33


def test_gap_risk_amount_for_a_long():
    assert gs.gap_risk_amount_for(33.33, 100.0, 98.0, LONG_STAMP, direction="bullish") == 99.99
    assert gs.gap_risk_amount_for(33.33, 100.0, 98.0, LONG_STAMP) is None    # default stays bearish


def test_size_for_trade_reads_a_long_trade_stamp():
    trade = {"ticker": "ZZZ", "direction": "bullish", "entry": 100.0, "stop_loss": 98.0,
             "gap_sizing": LONG_STAMP}
    assert gs.size_for_trade(trade)["shares"] == 33.33


# --- the two live stamp sites and the plan doc ------------------------------------

def test_attach_plan_v2_stamps_a_long_when_the_switch_is_on(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.gap_sizing == {"rule": "gap_p99", "down_gap_p99_pct": pytest.approx(6.0), "n_down_gaps": 125}


def test_strategy_long_is_stamped_from_its_completed_frame(monkeypatch):
    monkeypatch.setattr(sp, "build_strategy_plan", lambda *a, **k: _plan("bullish", source="strategy"))
    monkeypatch.setattr(sp, "stamp_badge", lambda plan: None)
    monkeypatch.setattr(sp, "stamp_cohort", lambda plan, state: None)
    monkeypatch.setattr(sp, "stamp_entry_context", lambda plan, df, asof: None)
    plan = sp.build_strategy_plan_at(_signed_gaps(), ticker="ZZZ", strategy="MACD", horizon_key="3m",
                                     direction="bullish", regime2_state="bull_quiet")
    assert plan.gap_sizing["n_down_gaps"] == 125


def test_a_stamped_long_round_trips_and_appends_one_key():
    d = plan_to_dict(_plan("bullish", gap_sizing=LONG_STAMP))
    assert list(d) == PRE_V183_PLAN_KEYS + ["gap_sizing"]
    assert plan_from_dict(json.loads(json.dumps(d))).gap_sizing == LONG_STAMP
```

Values: `size_for(100, 98, LONG_STAMP)` sizes on `max(2.0, 3.0) = 3.0` → `1000 / 30 = 33.33` shares, `risk_amount = 33.33 × 2 = 66.67`, `gap_risk_amount = 100.0` — the same numbers v183's short test pins at `(100, 102, up 3%)`. `gap_risk_amount_for(33.33, 100, 98, …)` is `round(33.33 × 3.0, 2) = 99.99`.

In `tests/planning/test_gap_sizing.py`'s autouse `_env`, add `monkeypatch.setattr(config, "LONG_GAP_SIZING", False)` so its "a long stays unstamped" pins hold whatever a developer's `.env` says.

- [ ] **Step 3: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/edge/test_edge_gates.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing_long.py
```

Expected: FAIL — `KeyError: 'p99_down_gap_pct'`; the long stamp is `None`; `gap_risk_amount_for() got an unexpected keyword argument 'direction'`.

- [ ] **Step 4: Add the down-gap side** — `swingbot/core/edge/gates.py`

```python
def _down_gap_stats(signed: pd.Series) -> dict:
    """v191: p99 and count of the strictly negative gaps, as positive percents."""
```

Body mirrors `_up_gap_stats` on `-signed[signed < 0]`, returning `{"p99_down_gap_pct": … | None, "n_down": int}`. `gap_stats` returns `**_up_gap_stats(signed), **_down_gap_stats(signed)`; its empty-frame dict gains `"p99_down_gap_pct": None, "n_down": 0`. Extend the docstring with one v191 sentence. The three original keys and the two v183 keys do not change.

- [ ] **Step 5: Extend the sizing module** — `swingbot/core/planning/gap_sizing.py`

Constants: `MIN_DOWN_GAPS = 60`; `_P99_KEY = {"bearish": "up_gap_p99_pct", "bullish": "down_gap_p99_pct"}`; `_COUNT_KEY = {"bearish": "n_up_gaps", "bullish": "n_down_gaps"}`; `_GAP_WORD = {"bearish": "up-gaps", "bullish": "down-gaps"}`.

Functions (all `< 15`; signatures fixed, bodies the implementer's):

- `_short_stamp(df) -> dict` — today's bearish body of `gap_sizing_stamp`, unchanged (`{"rule": _rule(), "up_gap_p99_pct": …, "n_up_gaps": …}`).
- `_long_stamp(df, rule: str) -> dict` — `gap_stats(df, lookback=LOOKBACK)`; `{"rule": rule, "down_gap_p99_pct": p99 if n_down >= MIN_DOWN_GAPS else None, "n_down_gaps": n_down}`.
- `gap_sizing_stamp(df, direction)` — bearish → `_short_stamp(df)`; bullish with `config.LONG_GAP_SIZING` → `_long_stamp(df, RULE_GAP)`; else `None`.
- `_fallback_stamp(direction) -> dict | None` — the stamp a failed read leaves: bearish `{"rule": _rule(), "up_gap_p99_pct": None, "n_up_gaps": 0}` (today's), bullish with the switch on `{"rule": RULE_GAP, "down_gap_p99_pct": None, "n_down_gaps": 0}`, else `None`.
- `stamp_gap_sizing(plan, df)` — same shape as today, using `_fallback_stamp` in the `except` and a helper `_log_missing_p99(plan)` that reads `_P99_KEY` / `_COUNT_KEY` / `_GAP_WORD` by `plan.direction`, so the short line stays byte-identical (`"%s: gap sizing p99 n/a (%d up-gaps, need %d) -- sized on the stop"`) and the long one reads `down-gaps` with `MIN_DOWN_GAPS`.
- `gap_floor_for(direction, gap_sizing)` — `key = _P99_KEY.get(direction)`; `None` when no key, no stamp or rule ≠ `RULE_GAP`; else the positive p99 or `None`.
- `_on_gap_path(direction, gap_sizing) -> bool` — False for rule `RULE_STOP`; True for bearish (today: a short without a stamp still reports "gap risk n/a"); True for bullish only when `"n_down_gaps" in (gap_sizing or {})`; False otherwise.
- `size_for(...)` — first line becomes `if not _on_gap_path(direction, gap_sizing): return _stop_only(entry, stop_loss, account_cfg)`; the rest is unchanged.
- `gap_risk_amount_for(shares, entry, stop_loss, gap_sizing, direction: str = "bearish")` — `gap_floor_for(direction, gap_sizing)`; docstring "an open position" instead of "an open short".

Rewrite the module docstring's "A long never reaches the gap branch" as: "A long reaches it only with a long stamp (`n_down_gaps`), written while LONG_GAP_SIZING is on (v191 Part B)."

- [ ] **Step 6: Run the tests to see them pass**

```bash
python scripts/dev/testrun.py file tests/edge/test_edge_gates.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing_long.py
python scripts/dev/testrun.py file tests/planning/test_gap_sizing.py
python scripts/dev/testrun.py file tests/planning/test_long_sizing_regression.py
python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_cap_invariants.py
python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_resize_sites.py
python scripts/dev/testrun.py file tests/tracking/test_gap_fill_real_r.py
```

Expected: all pass, `0 failed`. `test_long_sizing_regression.py` is the v183 byte-for-byte long pin; it must pass unchanged (a short-shaped stamp on a long never enters the gap path).

- [ ] **Step 7: Goldens and complexity**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/complexity_gate.py
```

Expected: both goldens `1 passed` (replay never stamps); the gate passes.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/edge/gates.py swingbot/core/planning/gap_sizing.py tests/edge/test_edge_gates.py tests/planning/test_gap_sizing.py tests/planning/test_gap_sizing_long.py
git commit -m "feat(v191): Part B -- p99 down-gap and gap-aware sizing for longs behind LONG_GAP_SIZING"
```

### Task V191-6: Part B readers: admin trades/risk/dashboard and the alert gap line for longs; long sizing parity
**Model:** sonnet — mechanical direction-awareness at four readers plus a parity test over the existing sizing sites.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (`_recorded_sizing_view` ~:820, `_gap_sizing_detail` ~:829)
- Modify: `swingbot/admin/api_v1/risk.py` (`_open_short_gap_risk` ~:88 passes `direction="bearish"` explicitly)
- Modify: `swingbot/core/tracking/performance.py` (`_paper_sizing` ~:575, the fallback log line)
- Modify: `tests/scanning/test_gap_sizing_resize_sites.py` (autouse `_env` pins `LONG_GAP_SIZING` off)
- Modify: `tests/presentation/test_gap_risk_line.py` (a cut long on every channel)
- Create: `tests/scanning/test_long_gap_sizing_parity.py`
- `swingbot/admin/dashboard.py`: **no code change** — `build_open_trade_views` (~:448) already hands each trade's own `direction` and `gap_sizing` to `size_for`; the parity test pins that it cuts a stamped long. Edit it only if that test fails.

**Interfaces:**
- Consumes (V191-5): the long stamp `{"rule", "down_gap_p99_pct", "n_down_gaps"}`; `gap_sizing.size_for` / `size_for_plan` / `size_for_trade` on the long path; `gap_risk_amount_for(shares, entry, stop_loss, gap_sizing, direction=)`.
- Produces: nothing new for later tasks. Response changes are additive: `_gap_sizing_detail` returns `None` for an unstamped long exactly as today, keeps a short's dict **byte-identical**, and for a stamped long returns the same keys plus `"down_gap_p99_pct"` (with `"up_gap_p99_pct": None`, so the SPA's `GapSizingDetail` type still holds). The risk page's `heat.gap_risk_amount` / `gap_risk_unknown` stay **shorts only** (the SPA labels them "Short gap risk"); a stamped long is never counted into them.

Spec § Part B: "One sizing function serves the alert's shown shares, the engine and the replay's dollar view (`gap_sizing.size_for*`), pinned by a parity test for the long gap path", and "Part B adds a gap line for longs mirroring v183's short line" (§ Code changes, Alert text). The line wording is direction-neutral already (`gap_risk_line`: "on a p99 gap"), and every channel renders it from `size_for_plan`, so a stamped long gets it with no presentation change.

- [ ] **Step 1: Write the failing parity tests** — `tests/scanning/test_long_gap_sizing_parity.py`

```python
"""v191 Part B: every site that sizes a plan or a paper trade sizes a stamped
LONG through the one path (gap_sizing.size_for), so the alert's shares, the
paper book, the dashboard, the decision chart and the admin order block agree."""
import pytest

from swingbot import config
from swingbot.admin import dashboard
from swingbot.admin.api_v1 import risk as risk_api
from swingbot.admin.api_v1 import trades as trades_api
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import analyze, execution_embeds, plan_table
from swingbot.core.scanning import outlook_run as orun
from tests.scanning.test_gap_sizing_resize_sites import CFG, STAMP, _decision_ctx, _plan, _trade

LONG_STAMP = {"rule": "gap_p99", "down_gap_p99_pct": 3.0, "n_down_gaps": 125}
LINE = "Risk $67 at stop · $100 on a p99 gap (3.0%) · size cut for gap risk"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    monkeypatch.setattr(account, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(analyze, "load_account_config", lambda: dict(CFG))
    monkeypatch.setattr(config, "SHORT_GAP_SIZING", True)
    monkeypatch.setattr(config, "LONG_GAP_SIZING", True)
    monkeypatch.setattr(config, "CURRENCY_SYMBOL", "$")


def _long(**kw):
    return _plan("bullish", gap_sizing=LONG_STAMP, **kw)


def _one_path():
    return gs.size_for(100.0, 98.0, direction="bullish", gap_sizing=LONG_STAMP)


def test_the_one_path_cuts_a_stamped_long():
    out = _one_path()
    assert (out["shares"], out["gap_sized"], out["gap_floor_pct"]) == (33.33, True, 3.0)


def test_alert_snapshot_and_ticket_line_match_the_one_path():
    assert plan_table._sizing_snapshot(100.0, _long()) == _one_path()
    assert execution_embeds.ticket_gap_line(_long()) == LINE


def test_outlook_card_risk_uses_the_cut_shares():
    assert orun._risk_dollars(_long()) == 66.66                       # 33.33 x 2.00


def test_dashboard_sizing_map_cuts_a_stamped_long(monkeypatch):
    monkeypatch.setattr(dashboard, "_open_trade_prices", lambda trades: {})
    trades = [_trade("l1", "bullish", 98.0, LONG_STAMP), _trade("l0", "bullish", 98.0)]
    sizing = dashboard.build_open_trade_views(trades, dict(CFG))["sizing"]
    assert sizing["l1"]["shares"] == 33.33 and sizing["l1"]["gap_sized"] is True
    assert sizing["l0"] == account.compute_position_size(entry=100.0, stop_loss=98.0, account_cfg=dict(CFG))


def test_decision_context_shows_the_cut_shares_and_keeps_heat_on_config_risk(monkeypatch):
    ctx = _decision_ctx(monkeypatch, _long())
    assert ctx["sizing"]["shares"] == 33.33
    assert ctx["sizing"]["heat_after"] == ctx["sizing"]["heat_before"] + 1.0


def test_paper_sizing_matches_the_one_path():
    from swingbot.core.tracking import performance
    out = performance._paper_sizing(100.0, 98.0, "bullish", LONG_STAMP, "ZZZ")
    assert out == _one_path()


def test_admin_order_block_of_a_stamped_long():
    detail = trades_api._gap_sizing_detail(plan_to_dict(_long()), None)
    assert detail["rule"] == "gap_p99"
    assert (detail["up_gap_p99_pct"], detail["down_gap_p99_pct"]) == (None, 3.0)
    assert (detail["shares"], detail["gap_sized"], detail["line"]) == (33.33, True, LINE)


def test_admin_order_block_uses_the_recorded_shares_of_a_long_trade():
    trade = {**_trade("l1", "bullish", 98.0, LONG_STAMP), "shares": 20.0}
    detail = trades_api._gap_sizing_detail(None, trade)
    assert detail["shares"] == 20.0
    assert detail["risk_amount"] == 40.0 and detail["gap_risk_amount"] == 60.0      # 20 x 2, 20 x 3


def test_admin_order_block_of_an_unstamped_long_is_none_and_a_short_is_unchanged():
    assert trades_api._gap_sizing_detail(plan_to_dict(_plan("bullish")), None) is None
    short = trades_api._gap_sizing_detail(plan_to_dict(_plan(gap_sizing=STAMP)), None)
    assert list(short) == ["rule", "up_gap_p99_pct", "shares", "risk_amount", "gap_risk_amount",
                           "gap_sized", "line"]


def test_risk_page_short_gap_figure_never_counts_a_long():
    long_trade = {**_trade("l1", "bullish", 98.0, LONG_STAMP), "shares": 33.33}
    assert risk_api._open_short_gap_risk([long_trade]) == {"gap_risk_amount": None, "gap_risk_unknown": 0}


def test_switch_off_long_is_todays_sizing_at_every_site(monkeypatch):
    monkeypatch.setattr(config, "LONG_GAP_SIZING", False)
    plain = account.compute_position_size(100.0, 98.0)
    plan = _plan("bullish")                                          # unstamped: the switch was off
    assert plan_table._sizing_snapshot(100.0, plan) == plain
    assert execution_embeds.ticket_gap_line(plan) is None
    assert trades_api._gap_sizing_detail(plan_to_dict(plan), None) is None
```

`_paper_sizing`'s positional order is `(entry, stop_loss, direction, gap_sizing, label)` (performance.py:575). `_trade(tid, direction, stop, gap_sizing)` builds an open trade at entry 100 (test_gap_sizing_resize_sites.py:41).

- [ ] **Step 2: Write the failing alert-channel test** — append to `tests/presentation/test_gap_risk_line.py`

```python
def test_every_alert_channel_shows_the_line_for_a_cut_long(monkeypatch):
    """v191 Part B: a stamped long prints the same order-block line as a short."""
    for name, text in _renderings(_item(monkeypatch, CUT, "bullish")).items():
        assert CUT_LINE in text, name
```

In `tests/scanning/test_gap_sizing_resize_sites.py`'s autouse `_env`, add `monkeypatch.setattr(config, "LONG_GAP_SIZING", False)` so its "a long is today's dict" pins hold regardless of `.env`.

- [ ] **Step 3: Run them to see which fail**

```bash
python scripts/dev/testrun.py file tests/scanning/test_long_gap_sizing_parity.py
python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py
```

Expected: the admin order-block tests FAIL (`_gap_sizing_detail` returns `None` for any long); the snapshot, ticket, outlook, dashboard, decision-context, paper-sizing, risk-page and alert-channel tests already PASS on V191-5's `size_for` — they are the parity pins, not new behaviour.

- [ ] **Step 4: Make the admin order block direction-aware** — `swingbot/admin/api_v1/trades.py`

- `_recorded_sizing_view(sizing, shares, entry, stop, stamp, direction: str)` — passes `direction=direction` to `gap_risk_amount_for`; otherwise unchanged.
- New `_gap_stamp_for(p: dict, t: dict) -> tuple[str, dict] | None` — the stamp (plan doc first, then the trade, as today) and its direction; `None` without a stamp, for a direction other than bullish/bearish, and for a long whose stamp has no `"n_down_gaps"` (a long's stamp written while `LONG_GAP_SIZING` was on).
- New `_p99_keys(direction: str, stamp: dict) -> dict` — bearish `{"up_gap_p99_pct": stamp.get("up_gap_p99_pct")}`; bullish `{"up_gap_p99_pct": None, "down_gap_p99_pct": stamp.get("down_gap_p99_pct")}`.
- `_gap_sizing_detail(plan, trade)` — `found = _gap_stamp_for(p, t)`; `None` when not found; sizes with `size_for(entry, stop, direction=direction, gap_sizing=stamp)`; returns `{"rule": stamp.get("rule"), **_p99_keys(direction, stamp), "shares": …, "risk_amount": …, "gap_risk_amount": …, "gap_sized": …, "line": …}` — the short's dict keeps today's key order and values. Docstring: "a stamped short's or long's".

- [ ] **Step 5: Make the two remaining short-only readers explicit** —

`swingbot/admin/api_v1/risk.py`, `_open_short_gap_risk`: call `gap_risk_amount_for(..., t.get("gap_sizing"), direction="bearish")`; add to the docstring: "Shorts only, as the risk page labels it; a stamped long's gap figure is on its order block (v191)." No change to the heat keys or `test_risk_shape`.

`swingbot/core/tracking/performance.py`, `_paper_sizing`: the fallback log fires for any stamped trade — `if gap_sizing:` instead of `if direction == "bearish" and gap_sizing:` — and its docstring says "an unstamped long never logs".

- [ ] **Step 6: Run the tests to see them pass**

```bash
python scripts/dev/testrun.py file tests/scanning/test_long_gap_sizing_parity.py
python scripts/dev/testrun.py file tests/presentation/test_gap_risk_line.py
python scripts/dev/testrun.py file tests/scanning/test_gap_sizing_resize_sites.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_trade_risk_notice.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py
python scripts/dev/testrun.py file tests/planning/test_long_sizing_regression.py
python scripts/dev/complexity_gate.py
```

Expected: all pass, `0 failed` — `test_api_v1_trade_risk_notice.py` pins the short order block byte for byte, `test_api_v1_risk.py` the heat shape and short sums. The gate passes.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/api_v1/trades.py swingbot/admin/api_v1/risk.py swingbot/core/tracking/performance.py tests/scanning/test_long_gap_sizing_parity.py tests/scanning/test_gap_sizing_resize_sites.py tests/presentation/test_gap_risk_line.py
git commit -m "feat(v191): Part B readers -- long gap stamp in the admin order block and paper log; one sizing path pinned for longs"
```

