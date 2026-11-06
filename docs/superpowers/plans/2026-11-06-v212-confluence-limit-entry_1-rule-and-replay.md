# v212 — Confluence limit entry, part 1: rule and replay

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Spec:** [v212 — Confluence limit entry partway to the support](../specs/2026-11-06-v212-confluence-limit-entry.md)
**Index:** [`2026-11-06-v212-confluence-limit-entry_0-index.md`](2026-11-06-v212-confluence-limit-entry_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.
**Brief:** `.superpowers/briefs/2026-11-06-v212-confluence-limit-entry.md`

Tasks V212-1 .. V212-5: the knob, the pure limit geometry and the plan field,
the builder wiring with its drop reasons and the knob-0 goldens, the shared
fill rule, and the `exit_sim_v2` arm path. All paths are relative to the
worktree `.claude/worktrees/2026-11-06-v212-confluence-limit-entry` (created in
V212-1 Step 0). Every task's verification is the narrow run; no task runs the
full suite.

# Phase A — rule

### Task V212-1: Knob `CONFLUENCE_LIMIT_ENTRY_F`: config field, ScanParams, `.env.example`, reachability row

**Model:** sonnet — schema plumbing that mirrors the v139/v191 knob shape across five files, with a registry test that fails if one is missed.

**Files:**
- Modify: `swingbot/config.py` (new `Field` directly after `CONFLUENCE_ATR_TARGET_MODE` ~line 229; the `"searchable"` set ~line 1578)
- Modify: `swingbot/scan_params.py` (field after `confluence_atr_target_mode` ~line 97; `from_config()` ~line 170)
- Modify: `.env.example` (after `CONFLUENCE_ATR_TARGET_MODE=rechoose`, line 117)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (`_V212` text beside `_V191` ~line 56; REGISTRY row after `CONFLUENCE_ATR_TARGET_MODE`)
- Modify: `tests/market/test_v115_strategy_work_off.py` (`FLAGS_OFF` row)
- Create: `tests/test_config_v212_limit_entry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.CONFLUENCE_LIMIT_ENTRY_F: float` (default `0.0`); `ScanParams.confluence_limit_entry_f: float = 0.0`, filled in `from_config()`; `reachability.REGISTRY["CONFLUENCE_LIMIT_ENTRY_F"]` (`REACHABLE`, `observed_by == C`, reason names `confluence_limit_replay.py` / `measure_confluence_limit.py` and says it is not `measure_arms.py`).

**Placement note.** The ledger says "after `CONFLUENCE_STOP_DROP_PCT`"; the v191
fields already sit there and `tests/test_config_v191_atr_band.py::test_the_band_fields_follow_the_v139_knobs`
pins `attrs[base + 1:base + 3] == [FLOOR, MODE]`, so the new field goes **after
`CONFLUENCE_ATR_TARGET_MODE`**, which keeps that pin green. Same file, no
cross-task contract changes.

- [ ] **Step 0: Create the worktree** (once, for V212-1..V212-14)

```bash
git worktree add .claude/worktrees/2026-11-06-v212-confluence-limit-entry -b 2026-11-06-v212-confluence-limit-entry main
cd .claude/worktrees/2026-11-06-v212-confluence-limit-entry
```

Every later command in this plan runs from that directory.

- [ ] **Step 1: Write the failing test** `tests/test_config_v212_limit_entry.py`

```python
"""v212: the confluence limit-entry knob -- schema, ScanParams, reachability,
.env.example. Ships inert at 0 (spec § The rule)."""
import pathlib

import pytest
from dotenv import dotenv_values

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

REPO = pathlib.Path(__file__).resolve().parents[1]
KNOB = "CONFLUENCE_LIMIT_ENTRY_F"


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_knob_is_an_inert_searchable_float():
    f = _field(KNOB)
    assert (f.key, f.section, f.type, f.default) == (KNOB, "Trade Filters & Risk", "float", "0")
    assert (f.min, f.max, f.step) == (0, 0.9, 0.01)
    assert f.search_class == "searchable" and KNOB in config.searchable_attrs()
    assert config._cast(f, f.default) == 0.0
    assert config.CONFLUENCE_LIMIT_ENTRY_F == 0.0


def test_knob_follows_the_v191_fields():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs[attrs.index("CONFLUENCE_ATR_TARGET_MODE") + 1] == KNOB


def test_help_states_the_rule_and_the_default():
    text = _field(KNOB).help
    for phrase in ("v212", "0 = off", "0.25%", "TP1", "3 sessions", "2%", "Keep 0"):
        assert phrase in text, phrase


def test_scan_params_default_is_off():
    assert ScanParams.from_config().confluence_limit_entry_f == 0.0


@pytest.mark.parametrize("value", [1 / 3, 0.5, 2 / 3])
def test_scan_params_carries_the_knob(value, monkeypatch):
    monkeypatch.setattr(config, KNOB, value)
    assert ScanParams.from_config().confluence_limit_entry_f == value


def test_reachability_row_is_confluence_only_and_names_its_own_replay():
    assert reach.classify(KNOB) == reach.REACHABLE
    row = reach.REGISTRY[KNOB]
    assert row.observed_by == reach.C
    assert "confluence_limit_replay.py" in row.reason
    assert "measure_arms.py" in row.reason           # names what does NOT measure it
    assert row.fixture_observable is False


def test_measure_arms_parses_the_knob():
    assert parse_knob(f"{KNOB}=0.5") == (KNOB, 0.5)


def test_env_example_ships_it_at_zero():
    assert dotenv_values(REPO / ".env.example").get(KNOB) == "0"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_config_v212_limit_entry.py`
Expected: FAIL — `StopIteration` in `_field` (no such field) and `AttributeError` on `confluence_limit_entry_f`.

- [ ] **Step 3: Add the `Field` in `swingbot/config.py`** directly after the `CONFLUENCE_ATR_TARGET_MODE` field

```python
    Field("CONFLUENCE_LIMIT_ENTRY_F", "CONFLUENCE_LIMIT_ENTRY_F", "Trade Filters & Risk",
          "Confluence limit entry fraction f (v212)",
          type="float", default="0", min=0, max=0.9, step=0.01,
          help="v212 pre-registration. 0 = off: confluence plans enter at market as today. "
               "Above 0, a confluence market plan whose level sits more than 2% from the "
               "price rests a limit at price - f x (price - level) instead, with its stop "
               "0.25% beyond the level, TP1/TP2 unchanged, valid through the close of the "
               "3rd full session (3 sessions) after the alert and cancelled if TP1 trades "
               "first. A plan whose stop would sit more than 2% from the limit is dropped "
               "(limit_stop_beyond_cap). Unmeasured -- see "
               "docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md. Keep 0."),
```

Then add `"CONFLUENCE_LIMIT_ENTRY_F"` to the `"searchable"` set next to
`"CONFLUENCE_ATR_STOP_FLOOR", "CONFLUENCE_ATR_TARGET_MODE"` (~line 1579).

- [ ] **Step 4: ScanParams** — in `swingbot/scan_params.py`, after
`confluence_atr_target_mode: str = "rechoose"` add
`confluence_limit_entry_f: float = 0.0   # v212 f; 0 = market entry (today)`,
and in `from_config()` after `confluence_atr_target_mode=...` add
`confluence_limit_entry_f=config.CONFLUENCE_LIMIT_ENTRY_F,`.

- [ ] **Step 5: `.env.example`** — after line 117 (`CONFLUENCE_ATR_TARGET_MODE=rechoose`):

```
# v212 confluence limit entry (pre-registration; keep 0). Above 0 a clamped
# confluence plan rests a limit partway (fraction f) to its support, stop 0.25%
# under it, valid 3 sessions, cancelled if TP1 trades first.
CONFLUENCE_LIMIT_ENTRY_F=0
```

- [ ] **Step 6: Reachability row** — in `swingbot/core/backtesting/arms/reachability.py`, beside `_V191`:

```python
_V212 = ("v212: builders.apply_confluence_limit inside build_confluence_plan turns a clamped "
         "confluence market plan into a resting limit. Measured by its own paired replay "
         "(swingbot/core/backtesting/confluence_limit_replay.py through "
         "scripts/backtest/measure_confluence_limit.py), which derives every arm from the "
         "knob-0 reference stream -- not measure_arms.py.")
```

and in `REGISTRY`, after the `CONFLUENCE_ATR_TARGET_MODE` row:
`"CONFLUENCE_LIMIT_ENTRY_F": Reach(REACHABLE, _V212, C),` (`fixture_observable`
stays at its default `False`: the arm is observed by its own module, which reads
the knob-0 stream, not by perturbing the shared fixture).

- [ ] **Step 7: Keep-off table** — in `tests/market/test_v115_strategy_work_off.py`, append to `FLAGS_OFF` after the v191 rows:
`("v212", "CONFLUENCE_LIMIT_ENTRY_F", 0.0),`

- [ ] **Step 8: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/test_config_v212_limit_entry.py
python scripts/dev/testrun.py file tests/market/test_v115_strategy_work_off.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py
python scripts/dev/testrun.py file tests/backtesting/test_knob_observability.py
python scripts/dev/testrun.py file tests/test_config_v191_atr_band.py
```

Expected: all PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 9: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py .env.example \
  swingbot/core/backtesting/arms/reachability.py tests/market/test_v115_strategy_work_off.py \
  tests/test_config_v212_limit_entry.py
git commit -m "feat(v212): CONFLUENCE_LIMIT_ENTRY_F knob, inert at 0 (V212-1)"
```

### Task V212-2: Limit geometry helper and `limit_entry_f` plan field

**Model:** opus — the frozen rule's arithmetic (scope, tick rounding in two directions, three drop reasons) is what every later task and the pre-registration rest on.

**Files:**
- Modify: `swingbot/core/planning/builders.py` (new block after `confluence_stop_geometry`, before `TODAY_BAND_FLOOR_PCT` ~line 646; add `import copy` and `from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR` to the imports)
- Modify: `swingbot/core/planning/plan_types.py` (`limit_entry_f` after `issued_at_source` ~line 233; `_OMIT_WHEN_NONE` ~line 253)
- Create: `tests/planning/test_confluence_limit_geometry.py`

**Interfaces:**
- Consumes: `ScanParams.confluence_limit_entry_f` (V212-1) — not read here; callers pass `f`.
- Produces (final names, consumed by V212-3, V212-4, V212-11):
  - `builders.LIMIT_STOP_BUFFER = 0.0025`, `builders.LIMIT_EXPIRY_BARS = 3`, `builders.LIMIT_DROP_REASONS = ("limit_scope", "limit_stop_beyond_cap", "limit_rr_fail")`
  - `class LimitGeometry(NamedTuple): limit: float; stop_loss: float; level_distance_pct: float`
  - `confluence_limit_geometry(entry: float, level: float | None, is_bull: bool, tp1: float | None, f: float, min_rr: float) -> LimitGeometry | str | None` — `None` = out of scope (today's plan), `str` = one of `LIMIT_DROP_REASONS`
  - `to_limit_plan(plan: TradePlanV2, geom: LimitGeometry, f: float) -> TradePlanV2` — a deep copy; never mutates `plan`
  - `apply_confluence_limit(plan: TradePlanV2, level: float | None, f: float, min_rr: float) -> TradePlanV2 | str`
  - `TradePlanV2.limit_entry_f: float | None = None` (in `_OMIT_WHEN_NONE`)

**The rule, as code decides it** (spec § The rule 1–5; index Global Constraints):

| Step | Long (short mirrored) |
|---|---|
| scope | `f > 0` and `clamped_distance(entry, level, is_bull)` is not None (level on the stop side, strictly more than 2% from `entry`); `None` level, NaN, exactly 2%, wrong side → `None` |
| limit | `entry − f·(entry − level)`, rounded to `tick_size(entry)` **toward entry** (long ceil, short floor; nine-decimal pre-round as `atr_band.round_away_from_entry`) |
| stop | `level·(1 − LIMIT_STOP_BUFFER)` long, `level·(1 + LIMIT_STOP_BUFFER)` short, then `atr_band.round_away_from_entry(stop, limit, is_bull)` |
| degenerate | not `stop < limit < entry` (short: `entry < limit < stop`) → `"limit_scope"` (index OPEN: `limit_scope` names a degenerate rounded geometry) |
| cap | `planned_loss_pct(limit, stop) > HARD_MAX_PLANNED_LOSS_PCT + STOP_GEOMETRY_TOL` → `"limit_stop_beyond_cap"` |
| R:R | `tp1` None or reward `|tp1 − limit| / |limit − stop|` on the wrong side or `< min_rr − STOP_GEOMETRY_TOL` → `"limit_rr_fail"` |
| keep | `LimitGeometry(limit, stop, d)` with `d` the `clamped_distance` value |

`MIN_STOP_DISTANCE_PCT` is deliberately not consulted (spec rule 3).

- [ ] **Step 1: Write the failing test** `tests/planning/test_confluence_limit_geometry.py`

```python
"""v212 limit geometry (spec § The rule 1-5): scope by clamped_distance, the
limit partway to the level rounded toward the price, the stop 0.25% beyond
the level rounded away from the limit, and the three drop reasons."""
import pytest

from swingbot.core.planning import builders
from swingbot.core.planning.builders import (LIMIT_DROP_REASONS, LIMIT_EXPIRY_BARS,
                                             LIMIT_STOP_BUFFER, LimitGeometry,
                                             apply_confluence_limit,
                                             confluence_limit_geometry, to_limit_plan)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2, plan_to_dict

THIRD, HALF, TWO_THIRDS = 1 / 3, 0.5, 2 / 3


def _geo(entry, level, is_bull, tp1, f, min_rr=1.5):
    return confluence_limit_geometry(entry, level, is_bull, tp1, f, min_rr)


def test_frozen_constants():
    assert LIMIT_STOP_BUFFER == 0.0025
    assert LIMIT_EXPIRY_BARS == 3
    assert LIMIT_DROP_REASONS == ("limit_scope", "limit_stop_beyond_cap", "limit_rr_fail")


@pytest.mark.parametrize("f,limit", [(HALF, 98.5), (TWO_THIRDS, 98.0)])
def test_long_limit_partway_with_the_stop_under_the_support(f, limit):
    geo = _geo(100.0, 97.0, True, 104.0, f)
    assert isinstance(geo, LimitGeometry)
    assert (geo.limit, geo.stop_loss) == (limit, 96.75)          # 97 * 0.9975 = 96.7575 -> floor
    assert geo.level_distance_pct == pytest.approx(3.0)


@pytest.mark.parametrize("f,limit", [(HALF, 101.5), (TWO_THIRDS, 102.0)])
def test_short_limit_mirrors_with_the_stop_over_the_resistance(f, limit):
    geo = _geo(100.0, 103.0, False, 96.0, f)
    assert (geo.limit, geo.stop_loss) == (limit, 103.26)         # 103 * 1.0025 = 103.2575 -> ceil


@pytest.mark.parametrize("is_bull,level,tp1,limit,stop", [
    (True, 96.9, 104.0, 97.94, 96.65),     # 97.9333 ceil toward 100; 96.65775 floor
    (False, 103.1, 96.0, 102.06, 103.36),  # 102.0667 floor toward 100; 103.35775 ceil
])
def test_tick_rounding_limit_toward_price_stop_away_from_limit(is_bull, level, tp1, limit, stop):
    geo = _geo(100.0, level, is_bull, tp1, TWO_THIRDS)
    assert (geo.limit, geo.stop_loss) == (limit, stop)


@pytest.mark.parametrize("is_bull,level,tp1", [(True, 97.0, 104.0), (False, 103.0, 96.0)])
def test_stop_beyond_two_percent_of_the_limit_is_dropped(is_bull, level, tp1):
    # f = 1/3: long 99.00 vs 96.75 is 2.27%; short 101.00 vs 103.26 is 2.24%
    assert _geo(100.0, level, is_bull, tp1, THIRD) == "limit_stop_beyond_cap"


@pytest.mark.parametrize("is_bull,level,tp1", [(True, 97.0, 101.0), (False, 103.0, 99.0)])
def test_target_failing_min_rr_from_the_limit_is_dropped(is_bull, level, tp1):
    # long: (101 - 98.5) / 1.75 = 1.43R; short: (101.5 - 99) / 1.76 = 1.42R
    assert _geo(100.0, level, is_bull, tp1, HALF) == "limit_rr_fail"


@pytest.mark.parametrize("is_bull,tp1", [(True, None), (True, 97.5), (False, 102.5)])
def test_missing_or_wrong_side_target_is_an_rr_drop(is_bull, tp1):
    level = 97.0 if is_bull else 103.0
    assert _geo(100.0, level, is_bull, tp1, HALF) == "limit_rr_fail"


@pytest.mark.parametrize("is_bull,level", [
    (True, 98.0), (False, 102.0),            # exactly 2%: clamped_distance is None
    (True, 98.5), (False, 101.5),            # inside 2%: stop already on structure
    (True, None), (False, None),             # missing level
    (True, float("nan")), (True, 101.0), (False, 99.0),   # non-finite, wrong side
])
def test_out_of_scope_returns_none(is_bull, level):
    assert _geo(100.0, level, is_bull, 104.0 if is_bull else 96.0, HALF) is None


@pytest.mark.parametrize("f", [0.0, -0.5])
def test_non_positive_f_is_out_of_scope(f):
    assert _geo(100.0, 97.0, True, 104.0, f) is None


def test_degenerate_rounding_is_a_scope_drop():
    # 1.00 - (1/3) * 0.025 = 0.99167 ceils to 1.00 == the price
    assert _geo(1.0, 0.975, True, 1.05, THIRD) == "limit_scope"


def _market(direction="bullish", **kw):
    bull = direction == "bullish"
    base = dict(plan_id="p1", ticker="XYZ", created_at="2026-11-06", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=98.25 if bull else 101.75, tp1=104.0 if bull else 96.0,
                tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5,
                trail_atr_mult=2.5, quality_score=0, quality_breakdown=[], badge="WEAK",
                badge_stats={}, status=PlanStatus.ACTIVE,
                status_history=[{"status": "ACTIVE", "reason": "market_entry", "at": "2026-11-06"}],
                acceptance_level=97.0 if bull else 103.0)
    base.update(kw)
    return TradePlanV2(**base)


def test_to_limit_plan_rewrites_only_the_entry_fields_and_copies():
    plan = _market(reclaim_level=99.0, waits_next_open=True)
    before = plan_to_dict(plan)
    out = to_limit_plan(plan, LimitGeometry(98.5, 96.75, 3.0), HALF)
    assert plan_to_dict(plan) == before                          # never mutates
    assert (out.entry_type, out.trigger_price, out.entry_price) == ("limit", 98.5, None)
    assert (out.stop_loss, out.tp1, out.tp2) == (96.75, 104.0, None)
    assert (out.status, out.status_history) == (PlanStatus.PENDING, [])
    assert (out.expiry_bars, out.limit_cancel_level, out.limit_strict_fill) == (3, 104.0, True)
    assert (out.limit_entry_f, out.stop_ceiling_pct) == (HALF, None)
    assert (out.reclaim_level, out.waits_next_open) == (None, None)
    assert out.acceptance_level == 97.0 and out.plan_id == "p1"


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_apply_converts_an_in_scope_market_plan(direction):
    level = 97.0 if direction == "bullish" else 103.0
    out = apply_confluence_limit(_market(direction), level, HALF, 1.5)
    assert out.entry_type == "limit"
    assert out.trigger_price == (98.5 if direction == "bullish" else 101.5)


def test_apply_returns_the_drop_reason():
    assert apply_confluence_limit(_market(), 97.0, THIRD, 1.5) == "limit_stop_beyond_cap"


@pytest.mark.parametrize("plan,level,f", [
    (_market(), 97.0, 0.0),                                   # knob off
    (_market(entry_type="stop_entry", entry_price=None), 97.0, HALF),   # breakout
    (_market(source="strategy"), 97.0, HALF),                 # strategy-source
    (_market(), 98.5, HALF),                                  # level within 2%
    (_market(), None, HALF),                                  # missing level
])
def test_apply_leaves_out_of_scope_plans_as_the_same_object(plan, level, f):
    assert apply_confluence_limit(plan, level, f, 1.5) is plan


def test_limit_entry_f_is_omitted_while_none():
    assert "limit_entry_f" not in plan_to_dict(_market())
    converted = to_limit_plan(_market(), LimitGeometry(98.5, 96.75, 3.0), HALF)
    assert plan_to_dict(converted)["limit_entry_f"] == HALF


def test_helpers_live_in_builders():
    assert builders.confluence_limit_geometry is confluence_limit_geometry
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_limit_geometry.py`
Expected: FAIL — `ImportError: cannot import name 'LIMIT_DROP_REASONS'`.

- [ ] **Step 3: Add the plan field** in `swingbot/core/planning/plan_types.py`, after `issued_at_source`:

```python
    # v212 (planning/builders.apply_confluence_limit): the fraction f of the way
    # from the market price to the level at which a confluence plan rests its
    # limit. Set once at creation on an arm limit plan; None on every other plan
    # (knob 0, out of scope, v113/v131 limits, every plan persisted before v212).
    # Lives in the plans doc JSON, no promoted column. Omitted while None.
    limit_entry_f: float | None = None
```

and append `"limit_entry_f"` to `_OMIT_WHEN_NONE` (update its leading comment to name v212).

- [ ] **Step 4: Implement the helpers in `swingbot/core/planning/builders.py`**

Constants as in the Interfaces block. Functions, each well under complexity 15:

- `_round_toward_entry(price: float, entry: float, is_bull: bool) -> float` — `Decimal` on `atr_band.tick_size(entry)`, `ROUND_CEILING` for a long and `ROUND_FLOOR` for a short, after `round(float(price), 9)` (the same float-noise guard as `atr_band.round_away_from_entry`).
- `_limit_stop(level: float, limit: float, is_bull: bool) -> float` — buffer then `atr_band.round_away_from_entry`.
- `_limit_reward_ok(limit, stop, tp1, is_bull, min_rr) -> bool` — False for `tp1 is None`, a target not beyond `limit` on the reward side, or a reward:risk under `min_rr - STOP_GEOMETRY_TOL`.
- `confluence_limit_geometry(...)` — table above, in that order: scope (`f <= 0` → None; `d = clamped_distance(...)`; None → None), limit, stop, degenerate, cap, R:R, keep.
- `to_limit_plan(plan, geom, f)` — `copy.deepcopy(plan)`, then set `entry_type="limit"`, `trigger_price=geom.limit`, `entry_price=None`, `stop_loss=geom.stop_loss`, `status=PlanStatus.PENDING`, `status_history=[]`, `working_stop=None`, `expiry_bars=LIMIT_EXPIRY_BARS`, `limit_cancel_level=plan.tp1`, `limit_strict_fill=True`, `limit_entry_f=f`, `stop_ceiling_pct=None`, and the v192 stamps `reclaim_atr`, `reclaim_level`, `reclaim_session`, `waits_next_open` to None. Resetting status and history lets V212-11 derive an arm from an already-settled (ACTIVE) knob-0 reference plan; `acceptance_level` (the pre-clamp level) is kept.
- `apply_confluence_limit(plan, level, f, min_rr)` — return `plan` itself (same object) when `f <= 0`, `plan.source != "confluence"` or `plan.entry_type != "market"`; else `geom = confluence_limit_geometry(plan.trigger_price, level, plan.direction == "bullish", plan.tp1, f, min_rr)`; `None` → `plan`; a `str` → that string; else `to_limit_plan(plan, geom, f)`.

Docstrings cite spec § The rule and say the helper is shared by live (`build_confluence_plan`, V212-3) and the replay module (V212-11).

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/planning/test_confluence_limit_geometry.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/testrun.py file tests/planning/test_confluence_stop_geometry.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS; the v191 golden is untouched (the new field is omitted while None); the complexity gate reports no new violation.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/builders.py swingbot/core/planning/plan_types.py \
  tests/planning/test_confluence_limit_geometry.py
git commit -m "feat(v212): confluence limit geometry and limit_entry_f plan field (V212-2)"
```

### Task V212-3: Wire the rule into `build_confluence_plan`; drop reasons in attach; knob-0 plan and replay goldens

**Model:** opus — changes THE confluence constructor under a byte-identical golden, with a behaviour-preserving extraction to keep complexity from growing.

**Files:**
- Create: `tests/planning/test_v212_plan_golden.py`, `tests/fixtures/v212/plan_golden.json` (captured in Step 2, never regenerated)
- Create: `tests/backtesting/test_v212_flag_off_golden.py`, `tests/fixtures/v212/replay_golden.json` (captured in Step 2, never regenerated)
- Modify: `swingbot/core/planning/builders.py` (`build_confluence_plan` ~line 741 via `_confluence_tp2`; new `confluence_limit_dropped` beside `confluence_stop_dropped` ~line 728)
- Modify: `swingbot/core/scanning/analyze.py` (import line 39; `_no_plan_reason` line 416; its call at line 550)
- Create: `tests/scanning/test_v212_limit_rejects.py`

**Interfaces:**
- Consumes: `apply_confluence_limit`, `confluence_limit_geometry`, `LIMIT_DROP_REASONS` (V212-2); `ScanParams.confluence_limit_entry_f` (V212-1).
- Produces: `builders.confluence_limit_dropped(scenario, df, level_map=None, params=None) -> str | None` — the `LIMIT_DROP_REASONS` token `build_confluence_plan` returned None for, else None; `analyze._no_plan_reason(scenario, level_map, df=None)` returns it first; live limit plans carry `limit_entry_f`. The two goldens are the knob-0 witnesses every later task (V212-5 above all) must keep green.

**Golden rule.** Both goldens are captured in Step 2, **before** any edit to
`builders.py` or `analyze.py` in this task. V212-1 and V212-2 add no behaviour
(a field omitted while None, unused helpers), and the plan golden additionally
asserts that every scenario it shares with the v191 golden equals that
pre-v191 capture, so "captured from the base" is checked, not trusted. A
changed golden is a stop, never an update.

- [ ] **Step 1: Write the golden tests**

`tests/planning/test_v212_plan_golden.py`:

```python
"""v212 knob-0 parity for the builder: with CONFLUENCE_LIMIT_ENTRY_F at 0,
build_confluence_plan returns exactly the plan dicts it did before V212-3
touched it. Captured at V212-3 Step 2 on unmodified builder code; never
regenerate. Above 0, only in-scope (clamped) scenarios change."""
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

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "v212" / "plan_golden.json"
V191_GOLDEN = FIXTURES / "v191" / "plan_golden.json"
INERT = {"CONFLUENCE_LIMIT_ENTRY_F": 0.0, "CONFLUENCE_ATR_STOP_FLOOR": 0.0,
         "CONFLUENCE_ATR_TARGET_MODE": "rechoose", "LONG_GAP_SIZING": False,
         "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0, "CONFLUENCE_STOP_DROP_PCT": 0.0,
         "CLAMP_STOP_TO_HARD_CAP": True}
#: name -> (direction, entry, level stop, own target); the v191 seven plus two far levels
SCENARIOS = {
    "bull_inside": ("bullish", 100.0, 98.2, 104.0),
    "bull_clamped": ("bullish", 100.0, 96.5, 108.0),
    "bull_tight": ("bullish", 100.0, 99.0, 103.0),
    "bear_inside": ("bearish", 100.0, 101.8, 96.0),
    "bear_clamped": ("bearish", 100.0, 103.5, 92.0),
    "bear_tight": ("bearish", 100.0, 101.0, 97.0),
    "penny_bull": ("bullish", 0.85, 0.835, 0.88),
    "bull_far": ("bullish", 100.0, 97.0, 110.0),
    "bear_far": ("bearish", 100.0, 103.0, 90.0),
}
IN_SCOPE = ("bull_clamped", "bear_clamped", "bull_far", "bear_far")
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _params(f=0.0):
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0, confluence_limit_entry_f=f)


def _build(direction, entry, stop, target, f=0.0):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    return build_confluence_plan(scenario, make_ohlcv([entry] * 60, spread=0.02), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence",
                                 level_map=None, params=_params(f))


def _snapshot(*args, f=0.0):
    plan = _build(*args, f=f)
    if plan is None:
        return None
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _capture(f=0.0):
    return json.loads(json.dumps({name: _snapshot(*a, f=f) for name, a in SCENARIOS.items()}))


def _golden(captured):
    if os.environ.get("V212_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knob_zero_confluence_plans_match_the_pre_v212_golden():
    captured = _capture()
    golden = _golden(captured)
    built = [snap for snap in golden.values() if snap is not None]
    assert len(built) >= 7, "the golden must hold real plans, not a row of Nones"
    assert all("limit_entry_f" not in snap["keys"] for snap in built)
    assert captured == golden


def test_golden_agrees_with_the_pre_v191_capture_on_shared_scenarios():
    golden, v191 = (json.loads(p.read_text(encoding="utf-8")) for p in (GOLDEN, V191_GOLDEN))
    shared = set(golden) & set(v191)
    assert len(shared) == 7
    assert all(golden[name] == v191[name] for name in shared)


@pytest.mark.parametrize("f", [1 / 3, 0.5, 2 / 3])
def test_knob_on_leaves_out_of_scope_scenarios_identical(f):
    golden, captured = _golden(_capture()), _capture(f)
    for name in set(SCENARIOS) - set(IN_SCOPE):
        assert captured[name] == golden[name], name


@pytest.mark.parametrize("name", IN_SCOPE)
def test_knob_on_turns_in_scope_scenarios_into_limits_or_drops(name):
    ref = _build(*SCENARIOS[name])
    arm = _build(*SCENARIOS[name], f=2 / 3)
    assert ref.entry_type == "market" and arm is not None
    assert (arm.entry_type, arm.limit_entry_f, arm.expiry_bars) == ("limit", 2 / 3, 3)
    assert (arm.tp1, arm.tp2, arm.limit_cancel_level) == (ref.tp1, ref.tp2, ref.tp1)
    assert arm.acceptance_level == ref.acceptance_level == SCENARIOS[name][2]
    assert arm.status == "PENDING" and arm.entry_price is None
```

`tests/backtesting/test_v212_flag_off_golden.py` — copy the shape of
`tests/backtesting/test_v191_flag_off_golden.py` (same `pytestmark = pytest.mark.slow`,
`_structured_df`, `GATES`, `load_ohlcv("DELL").loc[:"2019-12-31"]`, `_r6`,
`_clamped`), importing `simulate_exit_v2` from `swingbot.core.planning.exit_sim_v2`
and `plan_to_dict` from `swingbot.core.planning.plan_types`, with these differences:

```python
GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v212" / "replay_golden.json"
V2 = resolve("v2")            # from swingbot.core.backtesting.instrument.contract import resolve
INERT = {"CONFLUENCE_LIMIT_ENTRY_F": 0.0, "CONFLUENCE_ATR_STOP_FLOOR": 0.0,
         "CONFLUENCE_ATR_TARGET_MODE": "rechoose", "LONG_GAP_SIZING": False,
         "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0, "CONFLUENCE_STOP_DROP_PCT": 0.0}


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit_v2(df, i, plan, V2, scale_out=True)   # the path V212-5 edits
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total),
                     None if res.exit_index is None else int(res.exit_index),
                     None if res.entry_index is None else int(res.entry_index),
                     sorted(plan_to_dict(plan))])
    return rows
```

Its test, `test_knob_zero_replay_matches_the_pre_v212_golden`, asserts
`len(_clamped(golden["dell"])) >= 5` (clamped plans exercised), that no row's
key list contains `"limit_entry_f"` and no row's `entry_type` is `"limit"`, then
`captured == golden`. The capture switch is `V212_CAPTURE_GOLDEN=1`.

- [ ] **Step 2: Capture both goldens on the unmodified builder**

```bash
git status --short swingbot/        # must print nothing: no builder/analyze edit yet
V212_CAPTURE_GOLDEN=1 python -m pytest tests/planning/test_v212_plan_golden.py tests/backtesting/test_v212_flag_off_golden.py -k "golden" -v
```

Expected: the three selected tests (the two `knob_zero` goldens and the
v191-agreement check) PASS and the two JSON files now exist. The
`knob_on_turns...` tests are not selected by `-k golden`; they fail until
Step 4 wires the rule. Commit the goldens alone so their capture point is in
history:

```bash
git add tests/fixtures/v212/plan_golden.json tests/fixtures/v212/replay_golden.json
git commit -m "test(v212): capture knob-0 plan and replay goldens before wiring (V212-3)"
```

- [ ] **Step 3: Write the failing attach test** `tests/scanning/test_v212_limit_rejects.py`

```python
"""v212 on the live attach path (spec rule 9): a drop is recorded with its
bare-token reason and logged by the existing 'plan rejected (' line; a kept
limit reaches item.plan_v2 as a PENDING limit; knob 0 changes nothing."""
import logging
import re
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.builders import LIMIT_DROP_REASONS
from swingbot.core.scanning import engine, scan_run
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def v2_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


def _scenario(stop, target, direction="bullish", entry=100.0):
    return SimpleNamespace(direction=direction, entry=entry, stop_loss=stop, take_profit=target,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


def _attach(scenario):
    item = SimpleNamespace(plan_v2=None)
    engine.attach_plan_v2(item, scenario, make_ohlcv([scenario.entry] * 60),
                          "AAPL", "4w", level_map=None)
    return item


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.6, 92.0)])
def test_stop_beyond_two_percent_of_the_limit_is_rejected_with_its_reason(
        monkeypatch, direction, stop, target):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)   # 98.25/96.25 = 2.04%
    item = _attach(_scenario(stop, target, direction=direction))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "limit_stop_beyond_cap"


def test_kept_limit_is_attached_pending(monkeypatch):
    ref = _attach(_scenario(96.5, 108.0)).plan_v2
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 2 / 3)
    plan = _attach(_scenario(96.5, 108.0)).plan_v2
    assert (plan.entry_type, plan.trigger_price, plan.stop_loss) == ("limit", 97.67, 96.25)
    assert (plan.status, plan.expiry_bars, plan.limit_entry_f) == ("PENDING", 3, 2 / 3)
    assert plan.tp1 == ref.tp1 == plan.limit_cancel_level


def test_knob_zero_keeps_the_clamped_market_plan():
    plan = _attach(_scenario(96.5, 108.0)).plan_v2
    assert (plan.entry_type, plan.stop_loss, plan.limit_entry_f) == ("market", pytest.approx(98.25), None)


def test_unclamped_plan_is_untouched_with_the_knob_on(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)
    assert _attach(_scenario(98.5, 104.0)).plan_v2.entry_type == "market"


def test_no_target_is_still_no_qualifying_target(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)
    assert _attach(_scenario(98.5, 100.5)).plan_v2_rejected == "no_qualifying_target"


@pytest.mark.parametrize("reason", LIMIT_DROP_REASONS)
def test_reason_survives_the_export_grep(caplog, reason):
    item = SimpleNamespace(plan=SimpleNamespace(stop_distance_pct=3.5), plan_v2_rejected=reason,
                           result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="up"))
    with caplog.at_level(logging.INFO):
        scan_run._skip_rejected_plan(item, require_confirmation=False)
    # scripts/ops/export_book_rows.sh reads "(<reason>[,)]" after "plan rejected ("
    assert re.search(r"plan rejected \(([a-z_]+)[,)]", caplog.text).group(1) == reason
```

Run: `python scripts/dev/testrun.py file tests/scanning/test_v212_limit_rejects.py`
Expected: FAIL — the reject tests see a `market` plan (rule not wired).

- [ ] **Step 4: Wire the rule into `build_confluence_plan`** without growing its complexity (C12 today)

1. Extract the TP2 block (the `if level_map is not None: ... else: ...` with its two nested `if`s) verbatim into
   `_confluence_tp2(scenario, level_map, entry: float, tp1: float, is_bull: bool) -> float | None` and call it — a behaviour-preserving extraction (−3 branches).
2. After the `TradePlanV2(...)` construction and **before** `_settle_market_entry`, add the one new branch:

```python
    plan = apply_confluence_limit(plan, level, getattr(params, "confluence_limit_entry_f", 0.0),
                                  params.min_risk_reward_ratio)
    if isinstance(plan, str):
        return None          # v212 drop; confluence_limit_dropped names the reason
```

`_settle_market_entry` then passes a limit plan through unchanged (it only
settles `market`); badge, cohort, quality and `stamp_confluence_acceptance`
(the pre-clamp level) run on the limit plan as on any other. Extend the
docstring with one v212 sentence. (`getattr` keeps duck-typed params in older
tests working.)

3. Add beside `confluence_stop_dropped`:

`confluence_limit_dropped(scenario, df, level_map=None, params=None) -> str | None` — params default `ScanParams.from_config()`; returns None when `f <= 0`, when `scenario_is_breakout(scenario, df)`, or when `_plan_geometry(...)` is None or has no `tp1`; otherwise the `str` result of `confluence_limit_geometry(scenario.entry, scenario.stop_loss, scenario.direction == "bullish", geometry.tp1, f, params.min_risk_reward_ratio)`, else None. Same inputs as the builder, so attach names the reason without a second rule.

- [ ] **Step 5: Name the reason in `swingbot/core/scanning/analyze.py`**

Import `confluence_limit_dropped` on line 39. `_no_plan_reason(scenario, level_map, df=None) -> str`: when `df` is not None and `confluence_limit_dropped(scenario, df, level_map)` returns a reason, return it first; the existing band / v139 / `no_qualifying_target` order is unchanged. At line 550 pass `df`: `_no_plan_reason(scenario, level_map, df)` (an argument, no new branch in `attach_plan_v2`). Docstring names the v212 reasons.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/planning/test_v212_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v212_flag_off_golden.py
python scripts/dev/testrun.py file tests/scanning/test_v212_limit_rejects.py
python scripts/dev/testrun.py file tests/planning/test_v191_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v191_flag_off_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py
python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS with the goldens byte-unchanged (`git diff --stat tests/fixtures` prints nothing); `build_confluence_plan` scores below its baseline 12.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/builders.py swingbot/core/scanning/analyze.py \
  tests/planning/test_v212_plan_golden.py tests/backtesting/test_v212_flag_off_golden.py \
  tests/scanning/test_v212_limit_rejects.py
git commit -m "feat(v212): confluence limit entry in build_confluence_plan, drop reasons at attach (V212-3)"
```

If the complexity gate reports `improved build_confluence_plan`, run
`python scripts/dev/complexity_gate.py --update` and add `complexity_baseline.json` to this commit.

# Phase B — fill rule and replay

### Task V212-4: Shared fill rule `bar_outcome`

**Model:** opus — one pure function decides fill, cancel or nothing for replay, live and the measurement; its precedence order (gap-stop, TP1 cancel, gap fill, trade-through) is the pre-registered rule.

**Files:**
- Create: `swingbot/core/planning/limit_entry_rule.py`
- Create: `tests/planning/test_limit_entry_rule.py`

**Interfaces:**
- Consumes: `TradePlanV2.limit_entry_f` (V212-2); `swingbot.core.market.atr_band.tick_size` (exists, `atr_band.py:57`).
- Produces (consumed by V212-5 `exit_sim_v2`, v216 V216-1 `plan_manager`, V212-11 replay module):
  - `class BarOutcome(NamedTuple): kind: str; fill: float | None; gap_stopped: bool` — `kind` is `"fill"`, `"cancel"` or `"none"`; `fill` is set only for `"fill"`; `gap_stopped` is True only for a fill at an open at or through the stop
  - `is_arm_limit(plan) -> bool` — `plan.entry_type == "limit" and plan.limit_entry_f is not None`
  - `tp1_reached(plan, high: float, low: float) -> bool` — inclusive: long `high >= level`, short `low <= level`, `level = plan.limit_cancel_level` if set else `plan.tp1`
  - `bar_outcome(plan, *, open_: float | None, high: float, low: float, touch: bool = False) -> BarOutcome` — `ValueError` for a plan that is not an arm limit

**Precedence, one bar, long (short mirrored)** — spec rule 6 and G2's tie rules:

| # | Condition | Result |
|---|---|---|
| 1 | `open_` given and `open_ <= stop` | `fill` at `open_`, `gap_stopped=True` (realised loss; never a scratch; the open comes before anything else on the bar) |
| 2 | `tp1_reached(plan, high, low)` | `cancel` (inclusive; a bar that also reaches L is cancelled — the conservative same-bar rule) |
| 3 | `open_` given and `open_ <= L` | `fill` at `open_` (gap through L) |
| 4 | trade-through `low <= L − tick_size(L)` (with `1e-9` float tolerance); with `touch=True`, `low <= L` | `fill` at `L` |
| 5 | otherwise | `none` |

`open_=None` (a live poll with no session open in hand) skips rules 1 and 3;
the caller owns that case. Expiry is not this function's business: the caller
counts bars (replay) or sessions (live). Out-of-scope limit plans (v113 fade,
v131 Fibonacci Limit, `limit_entry_f is None`) never reach this function.

- [ ] **Step 1: Write the failing test** `tests/planning/test_limit_entry_rule.py`

```python
"""v212 shared fill rule (spec § The rule 6, G2 tie rules): trade-through
primary, touch as the sensitivity, gap fills at the open, a gap through the
stop fills and is stopped, TP1 cancel inclusive, a bar reaching both L and
TP1 is cancelled."""
import pytest

from swingbot.core.planning.limit_entry_rule import (BarOutcome, bar_outcome, is_arm_limit,
                                                     tp1_reached)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2

LONG = dict(direction="bullish", trigger_price=98.5, stop_loss=96.75, tp1=104.0)
SHORT = dict(direction="bearish", trigger_price=101.5, stop_loss=103.26, tp1=96.0)


def _plan(levels, **kw):
    base = dict(plan_id="p1", ticker="XYZ", created_at="2026-11-06", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", entry_type="limit",
                entry_price=None, expiry_bars=3, tp1_fraction=0.5, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
                status_history=[], limit_cancel_level=levels["tp1"], limit_strict_fill=True,
                limit_entry_f=0.5, **levels)
    base.update(kw)
    return TradePlanV2(**base)


def _out(levels, o, h, l, **kw):
    return bar_outcome(_plan(levels), open_=o, high=h, low=l, **kw)


# mirrored bars: (open, high, low) for the long, then the short
CASES = {
    "trade_through": ((99.5, 100.0, 98.49), (100.5, 101.51, 100.0)),
    "touch_only": ((99.5, 100.0, 98.5), (100.5, 101.5, 100.0)),
    "gap_through_limit": ((98.0, 98.4, 97.5), (102.0, 102.5, 101.6)),
    "open_at_limit": ((98.5, 99.0, 98.2), (101.5, 101.8, 101.0)),
    "gap_through_stop": ((96.0, 97.0, 95.5), (104.0, 104.5, 103.0)),
    "open_at_stop": ((96.75, 97.5, 96.0), (103.26, 104.0, 103.0)),
    "tp1_exact": ((100.0, 104.0, 99.0), (100.0, 101.0, 96.0)),
    "both_l_and_tp1": ((100.0, 105.0, 98.0), (100.0, 102.0, 95.0)),
    "nothing": ((99.5, 100.5, 99.0), (100.5, 101.0, 100.0)),
}
SIDES = pytest.mark.parametrize("side,levels", [(0, LONG), (1, SHORT)])


@SIDES
def test_trade_through_fills_at_the_limit(side, levels):
    assert _out(levels, *CASES["trade_through"][side]) == BarOutcome("fill", levels["trigger_price"], False)


@SIDES
def test_a_bare_touch_fills_only_in_the_touch_sensitivity(side, levels):
    bar = CASES["touch_only"][side]
    assert _out(levels, *bar) == BarOutcome("none", None, False)
    assert _out(levels, *bar, touch=True) == BarOutcome("fill", levels["trigger_price"], False)


@SIDES
@pytest.mark.parametrize("case", ["gap_through_limit", "open_at_limit"])
def test_an_open_at_or_through_the_limit_fills_at_the_open(side, levels, case):
    bar = CASES[case][side]
    assert _out(levels, *bar) == BarOutcome("fill", bar[0], False)


@SIDES
@pytest.mark.parametrize("case", ["gap_through_stop", "open_at_stop"])
def test_an_open_at_or_through_the_stop_fills_and_is_gap_stopped(side, levels, case):
    bar = CASES[case][side]
    assert _out(levels, *bar) == BarOutcome("fill", bar[0], True)


@SIDES
def test_tp1_cancel_is_inclusive(side, levels):
    assert _out(levels, *CASES["tp1_exact"][side]) == BarOutcome("cancel", None, False)


@SIDES
def test_a_bar_reaching_both_the_limit_and_tp1_is_cancelled(side, levels):
    assert _out(levels, *CASES["both_l_and_tp1"][side]).kind == "cancel"


@SIDES
def test_a_quiet_bar_is_nothing(side, levels):
    assert _out(levels, *CASES["nothing"][side]).kind == "none"


@SIDES
def test_gap_through_the_stop_wins_over_a_tp1_print_on_the_same_bar(side, levels):
    o = 96.0 if side == 0 else 104.0
    assert _out(levels, o, 105.0, 95.0) == BarOutcome("fill", o, True)   # bar spans TP1 too


def test_no_open_skips_the_open_rules():
    # a live poll below the stop with no session open: trade-through at L, not a gap
    assert bar_outcome(_plan(LONG), open_=None, high=96.0, low=96.0) == BarOutcome("fill", 98.5, False)
    assert bar_outcome(_plan(LONG), open_=None, high=99.0, low=99.0).kind == "none"


def test_trade_through_needs_a_full_tick():
    assert _out(LONG, 99.5, 100.0, 98.495).kind == "none"       # half a tick under
    assert _out(LONG, 99.5, 100.0, 98.49).kind == "fill"


def test_tp1_reached_falls_back_to_tp1_without_a_cancel_level():
    plan = _plan(LONG, limit_cancel_level=None)
    assert tp1_reached(plan, 104.0, 99.0) and not tp1_reached(plan, 103.99, 99.0)


@pytest.mark.parametrize("kw,expected", [
    ({}, True),
    ({"limit_entry_f": None}, False),                       # v113 / v131 limits
    ({"entry_type": "market", "entry_price": 100.0}, False),
])
def test_is_arm_limit(kw, expected):
    assert is_arm_limit(_plan(LONG, **kw)) is expected


def test_non_arm_plans_are_refused():
    with pytest.raises(ValueError, match="arm limit"):
        bar_outcome(_plan(LONG, limit_entry_f=None), open_=99.0, high=99.5, low=98.0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_limit_entry_rule.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.planning.limit_entry_rule'`.

- [ ] **Step 3: Implement `swingbot/core/planning/limit_entry_rule.py`**

Module docstring: the v212 resting-order rule, shared by `exit_sim_v2` (replay),
`plan_manager` (live) and the measurement; cites spec § The rule 6 and the G2
tie rules; says out-of-scope limits keep `lifecycle.limit_hit` /
`limit_cancelled`. Imports only `NamedTuple`, `atr_band.tick_size` and (for
typing) `TradePlanV2` — no pandas, no config. Small helpers keep each function
far under complexity 15: `_beyond(price, level, bull) -> bool` (long
`price <= level`, short `price >= level`), `_traded(plan, high, low, touch) -> bool`
(rule 4), then `bar_outcome` walks the table top to bottom. A module constant
`NONE = BarOutcome("none", None, False)`; the ValueError message contains
`"arm limit"`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
python scripts/dev/testrun.py file tests/planning/test_limit_entry_rule.py
python scripts/dev/complexity_gate.py
```

Expected: PASS; no complexity violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/limit_entry_rule.py tests/planning/test_limit_entry_rule.py
git commit -m "feat(v212): shared resting-limit fill rule bar_outcome (V212-4)"
```

### Task V212-5: Replay: arm limit path in `exit_sim_v2` (gap-through-stop realised, touch sensitivity)

**Model:** opus — edits the v2 replay entry dispatch under two knob-0 goldens; a slip here silently changes every v2 limit replay or mis-scores the gap-through-stop fills.

**Files:**
- Modify: `swingbot/core/planning/exit_sim_v2.py` (imports; new constants beside `GAP_CANCEL` ~line 38; `_arm_unfilled`, `_gap_stopped_exit`, `_arm_limit_entry_v2` after `_limit_entry_v2` ~line 337; `_entry_for` beside `_ENTRIES` ~line 362; `simulate_exit_v2` ~line 365)
- Modify: `swingbot/core/planning/exit_sim.py` (`ExitResult`: one unannotated class attribute beside `tp1_index`, ~line 88)
- Create: `tests/planning/test_exit_sim_v2_arm_limit.py`

**Interfaces:**
- Consumes: `bar_outcome`, `is_arm_limit`, `BarOutcome` (V212-4); `limit_entry_f`, `LIMIT_EXPIRY_BARS` (V212-2).
- Produces (consumed by V212-11):
  - `simulate_exit_v2(df, signal_index, plan, instrument, *, scale_out=False, max_holding_days=None, touch_fill: bool = False)` — `touch_fill` is read only for arm plans (`is_arm_limit`); every other plan ignores it.
  - `ExitResult.exit_reason` — **a plain class attribute** (default `None`, no annotation, so not a dataclass field: `asdict`, `==`, `repr` and the frozen scale-out witness hash stay byte-identical — the `tp1_index` precedent). Set per instance on arm plans only: `"limit_expired"` and `"limit_tp1_cancel"` on `not_triggered` rows (their `cancel_reason` is `"expired"` / `"cancelled"`, as v131's), `"filled_stopped_gap"` on the gap-stop row. A filled arm trade that exits normally keeps `exit_reason = None` (its outcome and legs say how it closed).
  - `ExitResult.gap_stop_r_from_limit` — a second unannotated class attribute (default `None`), set only on a `"filled_stopped_gap"` row: the **pessimistic sensitivity** R as if the fill had been at L (`costs.book` with `entry_price = L`, one `"stop"` leg at the open). Disclosure only (V212-14); never the primary score, never gating.
  - Fill bar index: the existing field **`ExitResult.entry_index`** (confirmed: `exit_sim.py:67`); the fill price: `ExitResult.entry_price`.
  - Module constants `exit_sim_v2.LIMIT_EXPIRED = "limit_expired"`, `LIMIT_TP1_CANCEL = "limit_tp1_cancel"`, `FILLED_STOPPED_GAP = "filled_stopped_gap"`.
- Arm plans must be simulated through `simulate_exit_v2` (or `simulate_exit(..., instrument=<v2/v3>)`); the v1 path keeps `_limit_entry_exit` and knows nothing of the arm.

**Gap-through-stop scoring (controller decision, 2026-11-06).** The spec's
"more than 1R" wording was wrong: a resting buy limit at L whose session opens
at or through the stop fills **at the open**, and the bracket stop sells at
that same open. Primary score: `outcome = "loss"` (the stop fired),
`entry_index = exit_index = j`, `entry_price = open`, one leg
`{"exit_price": open, "reason": "filled_stopped_gap"}`, and
`r = ((exit_px − entry_px)·sign − 2·commission_per_share) / |L − stop|` with
`entry_px = costs.slip(open, buy=bull, bps=slippage_bps)` and
`exit_px = costs.slip(open, buy=not bull, bps=costs.exit_bps(cost_model, "stop"))`
— 0R less the frictions, rounded to 3 dp like `costs.book`. (`costs.book`
cannot score it: it raises when the entry sits at or beyond the stop.) The
from-L reading, `(open − L)·sign / |L − stop|` net of costs, rides on
`gap_stop_r_from_limit` as a disclosed pessimistic sensitivity only.
Out-of-scope limits keep `_entry_gap_scratch` (0R, today's) unchanged.

- [ ] **Step 1: Write the failing test** `tests/planning/test_exit_sim_v2_arm_limit.py`

```python
"""v212 arm limit in the v2 replay (spec rule 6, G2 tie rules): bars t+1..t+3
only, trade-through fills at L, an open through L fills at the open, an open
through the stop fills and stops at the open (0R less frictions on
the planned risk; the from-L loss is a sensitivity field), TP1
cancels inclusively, a bar reaching both cancels; v113/v131 limits unchanged."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.exit_sim_v2 import (ENTRY_GAP_SCRATCH, FILLED_STOPPED_GAP,
                                                LIMIT_EXPIRED, LIMIT_TP1_CANCEL,
                                                simulate_exit_v2)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
SIGNAL = (100.0, 100.5, 99.5, 100.0)
QUIET = (100.0, 100.5, 99.5, 100.0)                 # never reaches 98.49 or 104
THROUGH = (99.5, 100.0, 98.4, 99.0)                 # low trades a tick under 98.5
TO_TP1 = (100.0, 104.5, 99.5, 104.0)
LONG = dict(direction="bullish", trigger_price=98.5, stop_loss=96.75, tp1=104.0)
SHORT = dict(direction="bearish", trigger_price=101.5, stop_loss=103.26, tp1=96.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(levels=LONG, **kw):
    base = dict(plan_id="p1", ticker="XYZ", created_at="2024-01-02", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", entry_type="limit",
                entry_price=None, expiry_bars=3, tp1_fraction=1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
                status_history=[], limit_cancel_level=levels["tp1"], limit_strict_fill=True,
                limit_entry_f=0.5, **levels)
    base.update(kw)
    return TradePlanV2(**base)


def _run(bars, plan=None, instrument=FREE, **kw):
    return simulate_exit_v2(make_ohlcv([SIGNAL, *bars]), 0, plan or _plan(), instrument, **kw)


def test_trade_through_fills_at_the_limit_then_walks():
    res = _run([QUIET, THROUGH, TO_TP1])
    assert (res.entry_index, res.entry_price, res.outcome) == (2, 98.5, "win")
    assert res.r_total == pytest.approx((104.0 - 98.5) / 1.75)
    assert res.exit_reason is None


def test_a_fill_on_the_third_bar_counts_and_the_fourth_does_not():
    assert _run([QUIET, QUIET, THROUGH, TO_TP1]).entry_index == 3
    res = _run([QUIET, QUIET, QUIET, THROUGH, TO_TP1])
    assert (res.outcome, res.cancel_reason, res.exit_reason) == ("not_triggered", "expired", LIMIT_EXPIRED)
    assert (res.entry_index, res.legs) == (None, [])


def test_signal_on_the_last_bar_expires():
    res = simulate_exit_v2(make_ohlcv([SIGNAL]), 0, _plan(), FREE)
    assert res.exit_reason == LIMIT_EXPIRED


@pytest.mark.parametrize("bar", [(100.0, 104.0, 99.5, 103.0),      # TP1 printed exactly
                                 (100.0, 105.0, 98.0, 104.0)])     # L and TP1 on one bar
def test_tp1_before_a_fill_cancels_inclusively(bar):
    res = _run([bar, THROUGH])
    assert (res.outcome, res.cancel_reason, res.exit_reason) == ("not_triggered", "cancelled", LIMIT_TP1_CANCEL)


@pytest.mark.parametrize("levels,open_,from_l", [(LONG, 96.0, (96.0 - 98.5) / 1.75),
                                                 (SHORT, 104.0, (101.5 - 104.0) / 1.76)])
def test_gap_through_the_stop_fills_and_stops_at_the_open(levels, open_, from_l):
    bar = (open_, open_ + 0.5, open_ - 0.5, open_)
    res = _run([bar], _plan(levels))
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.entry_price == open_                       # a resting limit fills at the open
    assert res.legs[0]["exit_price"] == open_ and res.legs[0]["reason"] == FILLED_STOPPED_GAP
    assert res.r_total == 0.0                             # 0R before frictions, never a -1R+ loss
    assert res.exit_reason == FILLED_STOPPED_GAP
    assert res.gap_stop_r_from_limit == pytest.approx(from_l, abs=1e-3)   # sensitivity only


def test_gap_stop_costs_are_scaled_by_the_planned_risk():
    res = _run([(96.0, 96.5, 95.5, 96.0)], instrument=resolve("v2"))
    # 5 bps in, 10 bps out on the stop, over |L - stop| = 1.75 (not |open - stop|)
    assert res.r_total == pytest.approx(-(96.0 * 0.0015) / 1.75, abs=1e-3)
    assert -1.0 < res.r_total < 0.0
    assert res.gap_stop_r_from_limit < -1.0


def test_sensitivity_field_is_unset_on_every_other_row():
    assert _run([QUIET, THROUGH, TO_TP1]).gap_stop_r_from_limit is None
    assert _run([QUIET, QUIET, QUIET]).gap_stop_r_from_limit is None


def test_an_open_through_the_limit_fills_at_the_open():
    res = _run([(98.0, 98.4, 97.5, 98.2), TO_TP1])
    assert (res.entry_index, res.entry_price, res.outcome) == (1, 98.0, "win")


def test_a_fill_bar_that_reaches_the_stop_is_a_one_r_loss_at_the_stop():
    res = _run([(98.0, 98.4, 96.5, 97.0)])
    assert (res.outcome, res.entry_price, res.legs[0]["exit_price"]) == ("loss", 98.0, 96.75)
    assert res.r_total == pytest.approx(-1.0)


def test_a_bare_touch_fills_only_with_touch_fill():
    touch = (99.5, 100.0, 98.5, 99.0)
    assert _run([touch, QUIET, QUIET, TO_TP1]).exit_reason == LIMIT_EXPIRED
    res = _run([touch, TO_TP1], touch_fill=True)
    assert (res.entry_index, res.entry_price) == (1, 98.5)


def _v131(**kw):
    return _plan(limit_entry_f=None, **kw)                     # out of scope: today's path


def test_out_of_scope_limit_keeps_the_0r_gap_scratch():
    res = _run([(96.0, 96.5, 95.5, 96.0)], _v131())
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0, ENTRY_GAP_SCRATCH)
    assert res.exit_reason is None


def test_out_of_scope_limit_fills_on_a_bar_that_also_reaches_tp1():
    res = _run([(100.0, 105.0, 98.0, 104.0), TO_TP1], _v131())
    assert res.outcome != "not_triggered" and res.entry_index == 1


@pytest.mark.parametrize("bars", [[(99.5, 100.0, 98.5, 99.0), TO_TP1], [QUIET, THROUGH, TO_TP1]])
def test_touch_fill_is_ignored_by_out_of_scope_plans(bars):
    assert _run(bars, _v131(), touch_fill=True) == _run(bars, _v131())


def test_exit_reason_is_not_a_dataclass_field():
    res = _run([QUIET, QUIET, QUIET])
    assert {"exit_reason", "gap_stop_r_from_limit"}.isdisjoint(dataclasses.asdict(res))
    assert ExitResult.exit_reason is None and ExitResult.gap_stop_r_from_limit is None
    assert exit_sim_v2._ENTRIES["limit"] is exit_sim_v2._limit_entry_v2   # dispatch table untouched
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_arm_limit.py`
Expected: FAIL — `ImportError: cannot import name 'FILLED_STOPPED_GAP'`.

- [ ] **Step 3: Add `ExitResult.exit_reason`** in `swingbot/core/planning/exit_sim.py`, directly under `tp1_index = None`:

```python
    # v212: why an arm limit (limit_entry_rule.is_arm_limit) ended without a
    # normal walk -- "limit_expired" | "limit_tp1_cancel" | "filled_stopped_gap",
    # set per instance by exit_sim_v2. Unannotated for the same reason as
    # tp1_index: not a dataclass field, so asdict / == / the witness hash hold.
    exit_reason = None
    # v212: on a "filled_stopped_gap" row only, the disclosed pessimistic R as
    # if the fill had been at the limit price. Never the primary score.
    gap_stop_r_from_limit = None
```

- [ ] **Step 4: Implement the arm path in `swingbot/core/planning/exit_sim_v2.py`**

Imports: `import functools`; `from .limit_entry_rule import bar_outcome, is_arm_limit`.
Constants under `GAP_CANCEL`: `LIMIT_EXPIRED`, `LIMIT_TP1_CANCEL`, `FILLED_STOPPED_GAP` (values above).

- `_arm_unfilled(reason: str) -> ExitResult` — `_not_triggered("cancelled" if reason == LIMIT_TP1_CANCEL else "expired")`, then set `exit_reason = reason` on the instance.
- `_gap_stop_r(cost_model, plan, open_: float) -> float` — the primary R from the scoring paragraph above (`costs.slip`, `costs.exit_bps`, denominator `abs(plan.trigger_price - plan.stop_loss)`, `round(..., 3)`).
- `_gap_stopped_exit(df, j: int, plan, instrument) -> ExitResult` — `open_ = float(df["Open"].values[j])`; `r = _gap_stop_r(instrument.cost_model, plan, open_)`; return `ExitResult(outcome="loss", runner_outcome=None, entry_index=j, exit_index=j, entry_price=open_, r_total=r, legs=[{"fraction": 1.0, "exit_price": open_, "r": r, "reason": FILLED_STOPPED_GAP}])` with `exit_reason = FILLED_STOPPED_GAP` and `gap_stop_r_from_limit = costs.book(instrument.cost_model, direction=plan.direction, entry_price=plan.trigger_price, stop_loss=plan.stop_loss, legs=[_leg(1.0, open_, FILLED_STOPPED_GAP, "stop")])[0]` set on the instance. Docstring cites the scoring paragraph and says the sensitivity never gates.
- `_arm_limit_entry_v2(df, signal_index, plan, instrument, scale_out, max_holding_days, *, touch=False) -> ExitResult` — loop `j` over `signal_index + 1 .. min(signal_index + plan.expiry_bars, len(df) - 1)`; `out = bar_outcome(plan, open_=..., high=..., low=..., touch=touch)`; `"cancel"` → `_arm_unfilled(LIMIT_TP1_CANCEL)`; `"fill"` with `gap_stopped` → `_gap_stopped_exit(...)`; `"fill"` otherwise → `_filled(df, j, out.fill, plan, instrument, scale_out, max_holding_days)` (the existing fill-bar stop check, then `walk_v2`); loop exhausted → `_arm_unfilled(LIMIT_EXPIRED)`.
- `_entry_for(plan, touch_fill: bool)` — `functools.partial(_arm_limit_entry_v2, touch=touch_fill)` when `is_arm_limit(plan)`, else `_ENTRIES.get(plan.entry_type, _stop_entry_v2)` (today's lookup, unchanged). `_ENTRIES` itself is not edited.
- `simulate_exit_v2` gains `touch_fill: bool = False` and replaces its `_ENTRIES.get(...)` line with `entry = _entry_for(plan, touch_fill)`; docstring gains one v212 sentence.

No function written here passes complexity 5; `_limit_entry_v2`, `fill_bar_exit` and `_entry_gap_scratch` are not touched.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_arm_limit.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_replay_hooks.py
python scripts/dev/testrun.py file tests/backtesting/test_v212_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_limit_entry_rule.py
python scripts/dev/complexity_gate.py
```

Expected: all PASS; the v212 replay golden is byte-unchanged (`git diff --stat tests/fixtures` prints nothing).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/exit_sim_v2.py swingbot/core/planning/exit_sim.py \
  tests/planning/test_exit_sim_v2_arm_limit.py
git commit -m "feat(v212): arm limit entry in exit_sim_v2 -- shared fill rule, gap stop at the open, touch sensitivity (V212-5)"
```

