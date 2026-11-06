# v209 — Market-shock detector, part 1: config and the pure detector core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md)
**Index:** [`2026-11-05-v209-market-shock-detector_0-index.md`](2026-11-05-v209-market-shock-detector_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly carries the index's Global Constraints.

This part builds V209-1..V209-4: the "Market Shock" config section and the
pure `swingbot/core/market/shock.py` (types, `measure`, and the table-driven
`step` with entry, exit, second-leg and overnight-carry rules). Nothing here
does I/O, touches the scan, the database or Discord; parts 2 and 3 wire it.

Shared decisions for this part (from the index ledger and Notes, restated so
a task read alone is complete):

- `shock.py` imports nothing from `swingbot.config`; thresholds arrive as a
  frozen `ShockThresholds` whose defaults equal the V209-1 config defaults.
- Float comparisons against a threshold use a `1e-9` tolerance (`_EPS`), so
  `7/20 = 0.35` meets a `0.40 − 0.05` bar.
- Every function stays below cyclomatic complexity 15
  (`python scripts/dev/complexity_gate.py`).
- Tests live in `tests/market/` (suite `market-signals`; no `suites.toml`
  edit) and `tests/` root (config pins, like `tests/test_config_v171_keys.py`).
- Do not commit on `main`: each task's commit step runs on the plan's
  worktree branch.

# Phase 1 — config

### Task V209-1: "Market Shock" config section: `MARKET_SHOCK_MODE` + 18 thresholds

**Model:** haiku — mechanical config declarations and a pin test that mirror an existing pattern (`tests/test_config_v171_keys.py`).

**Files:**
- Modify: `swingbot/config.py` (new `# --- Market Shock (v209) ---` block of `Field`s between the `DCB_VOLUME_RATIO` field and the `# --- Database ---` comment, ~line 1535; one `_MODE_VALUES` entry, ~line 1640)
- Modify: `.env.example` (new `# --- Market Shock ---` section between `DCB_VOLUME_RATIO=0` and `# --- Database ---`)
- Create: `tests/test_config_v209_keys.py`

**Interfaces:**
- Consumes: `config.Field` (`swingbot/config.py:74`), `config._MODE_VALUES`, `config._MODE_FALLBACK`, `config._cast`, `config._apply_env` (reads `os.environ`), `config.searchable_attrs()`.
- Produces: `config.MARKET_SHOCK_MODE` (str in `off|shadow|live`, default `"shadow"`, unknown → `"off"`); floats `SHOCK_ATR_K` 1.0, `SHOCK_BREADTH_ENTER` 0.40, `SHOCK_SECTORS_FRAC` 0.6, `SHOCK_BREADTH_FAST` 0.25, `SHOCK_SPEED_ENTER` 0.10, `SHOCK_VIX_SPIKE_PCT` 15.0, `SHOCK_VIX_RELIEF` 0.05, `SHOCK_BREADTH_REENTER` 0.30, `SHOCK_BREADTH_EXIT` 0.20, `RECOVERY_VIX_OFF_HIGH_PCT` 5.0, `RECOVERY_SPY_RETRACE` 0.5; ints `SHOCK_MIN_DWELL_MIN` 45, `RECOVERY_MIN_DWELL_MIN` 30, `SHOCK_MIN_NAMES` 20, `SHOCK_VIX_MAX_AGE_S` 600, `SHOCK_OPEN_SETTLE_MIN` 15, `SHOCK_QUOTE_MAX_AGE_S` 300, `SHOCK_READINGS_KEEP_DAYS` 180. Section `"Market Shock"`, all `hot_reloadable=True`, `search_class="excluded"`, help text names `v209`. V209-6's `shock_scan.thresholds_from_config()` / `shock_mode()` and V209-5's prune read these attrs.

Background: `_cast` dispatches on `f.attr in _MODE_VALUES` before the type
casters, so a `select` field listed there is lower-cased and an unknown value
falls back to `_MODE_FALLBACK.get(attr, "off")` — exactly the Global
Constraint "unknown mode values fall back to `off`". No `_MODE_FALLBACK`
entry is added. `number` casts to `int`, `float` to `float` (`_CASTERS`).
Hot reload needs no per-field code: every `hot_reloadable=True` field is
re-read by `reload()` on SIGHUP.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_v209_keys.py`:

```python
"""v209: the "Market Shock" config section (spec § Starting thresholds)."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]

#: attr -> (type, default). Key == attr for every v209 field. Dict order is the FIELDS order.
V209_FIELDS = {
    "MARKET_SHOCK_MODE": ("select", "shadow"),
    "SHOCK_ATR_K": ("float", "1.0"),
    "SHOCK_BREADTH_ENTER": ("float", "0.40"),
    "SHOCK_SECTORS_FRAC": ("float", "0.6"),
    "SHOCK_BREADTH_FAST": ("float", "0.25"),
    "SHOCK_SPEED_ENTER": ("float", "0.10"),
    "SHOCK_VIX_SPIKE_PCT": ("float", "15.0"),
    "SHOCK_VIX_RELIEF": ("float", "0.05"),
    "SHOCK_BREADTH_REENTER": ("float", "0.30"),
    "SHOCK_BREADTH_EXIT": ("float", "0.20"),
    "RECOVERY_VIX_OFF_HIGH_PCT": ("float", "5.0"),
    "RECOVERY_SPY_RETRACE": ("float", "0.5"),
    "SHOCK_MIN_DWELL_MIN": ("number", "45"),
    "RECOVERY_MIN_DWELL_MIN": ("number", "30"),
    "SHOCK_MIN_NAMES": ("number", "20"),
    "SHOCK_VIX_MAX_AGE_S": ("number", "600"),
    "SHOCK_OPEN_SETTLE_MIN": ("number", "15"),
    "SHOCK_QUOTE_MAX_AGE_S": ("number", "300"),
    "SHOCK_READINGS_KEEP_DAYS": ("number", "180"),
}

#: The value each default casts to (spec § Starting thresholds, verbatim).
CAST_DEFAULTS = {
    "MARKET_SHOCK_MODE": "shadow",
    "SHOCK_ATR_K": 1.0, "SHOCK_BREADTH_ENTER": 0.40, "SHOCK_SECTORS_FRAC": 0.6,
    "SHOCK_BREADTH_FAST": 0.25, "SHOCK_SPEED_ENTER": 0.10, "SHOCK_VIX_SPIKE_PCT": 15.0,
    "SHOCK_VIX_RELIEF": 0.05, "SHOCK_BREADTH_REENTER": 0.30, "SHOCK_BREADTH_EXIT": 0.20,
    "RECOVERY_VIX_OFF_HIGH_PCT": 5.0, "RECOVERY_SPY_RETRACE": 0.5,
    "SHOCK_MIN_DWELL_MIN": 45, "RECOVERY_MIN_DWELL_MIN": 30, "SHOCK_MIN_NAMES": 20,
    "SHOCK_VIX_MAX_AGE_S": 600, "SHOCK_OPEN_SETTLE_MIN": 15, "SHOCK_QUOTE_MAX_AGE_S": 300,
    "SHOCK_READINGS_KEEP_DAYS": 180,
}


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_nineteen_fields_one_mode_plus_eighteen_thresholds():
    assert len(V209_FIELDS) == 19
    assert set(V209_FIELDS) == set(CAST_DEFAULTS)


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_field_is_a_hot_reloadable_excluded_market_shock_knob(attr):
    field = _field(attr)
    kind, default = V209_FIELDS[attr]
    assert (field.key, field.section, field.type, field.default) == (
        attr, "Market Shock", kind, default)
    assert field.hot_reloadable is True
    assert field.sensitive is False
    assert field.search_class == "excluded"
    assert attr not in config.searchable_attrs()
    assert "v209" in field.help


def test_fields_sit_together_between_chart_patterns_and_database():
    attrs = [f.attr for f in config.FIELDS]
    start = attrs.index("DCB_VOLUME_RATIO") + 1
    assert attrs[start:start + len(V209_FIELDS)] == list(V209_FIELDS)
    assert attrs[start + len(V209_FIELDS)] == "DATABASE_URL"


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_default_casts_to_the_documented_value(attr):
    field = _field(attr)
    value = config._cast(field, field.default)
    assert value == CAST_DEFAULTS[attr]
    assert type(value) is type(CAST_DEFAULTS[attr])


def test_mode_is_off_shadow_live_and_a_typo_falls_back_to_off():
    field = _field("MARKET_SHOCK_MODE")
    assert [value for value, _label in field.options] == ["off", "shadow", "live"]
    assert config._MODE_VALUES["MARKET_SHOCK_MODE"] == ("off", "shadow", "live")
    assert "MARKET_SHOCK_MODE" not in config._MODE_FALLBACK
    assert config._cast(field, "SHADOW") == "shadow"
    assert config._cast(field, "live") == "live"
    assert config._cast(field, "off") == "off"
    assert config._cast(field, "on") == "off"
    assert config._cast(field, "") == "off"


def test_numeric_fields_carry_bounds_around_their_default_and_a_step():
    for attr, (kind, _default) in V209_FIELDS.items():
        if kind not in ("float", "number"):
            continue
        field = _field(attr)
        assert field.min is not None and field.max is not None, attr
        assert field.step is not None, attr
        assert field.min <= CAST_DEFAULTS[attr] <= field.max, attr


def test_module_attrs_hold_the_cast_defaults_on_a_clean_env(monkeypatch):
    for attr in V209_FIELDS:
        monkeypatch.delenv(attr, raising=False)
    try:
        config._apply_env()
        for attr, expected in CAST_DEFAULTS.items():
            assert getattr(config, attr) == expected, attr
    finally:
        monkeypatch.undo()
        config._apply_env()


@pytest.mark.parametrize("attr", sorted(V209_FIELDS))
def test_env_example_lists_the_key_with_its_default(attr):
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert f"\n{attr}={V209_FIELDS[attr][1]}\n" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_config_v209_keys.py`
Expected: FAIL — `StopIteration` from `_field("MARKET_SHOCK_MODE")` (no such field yet) and `KeyError` on `_MODE_VALUES["MARKET_SHOCK_MODE"]`.

- [ ] **Step 3: Add the fields and the mode entry**

In `swingbot/config.py`, directly after the `DCB_VOLUME_RATIO` `Field(...)`
and before the `# --- Database ---` comment, insert:

```python
    # --- Market Shock (v209) ---
    Field("MARKET_SHOCK_MODE", "MARKET_SHOCK_MODE", "Market Shock",
          "Market-shock detector (v209)",
          type="select", default="shadow",
          options=[("off", "Off -- no reading, no state, no notice, no shock_state stamp"),
                   ("shadow", "Shadow -- measure, record, notify; change no trade"),
                   ("live", "Live -- identical to shadow until a screened follow-on spec")],
          help="v209. Each scheduled scan pass in US regular hours takes one reading of the "
               "watchlist (share of names down >= SHOCK_ATR_K ATR from the prior close, sectors "
               "down, the speed of that drop, SPY/QQQ ATR moves, VIX) and steps a NORMAL -> "
               "SHOCK -> RECOVERY -> NORMAL state machine. shadow: readings and state are "
               "stored, every new plan's entry_context gains shock_state, and a notice goes to "
               "the ops channel on each transition -- no long is blocked, no short issued, no "
               "stop moved. live: in v209 exactly the same as shadow. off: a byte-identical "
               "kill switch. An unknown value falls back to off."),
    Field("SHOCK_ATR_K", "SHOCK_ATR_K", "Market Shock", "Down-move size, in ATR14",
          type="float", default="1.0", min=0.25, max=5.0, step=0.25,
          help="v209. A name counts as 'down' when (last - prior close) / ATR14 <= -this."),
    Field("SHOCK_BREADTH_ENTER", "SHOCK_BREADTH_ENTER", "Market Shock",
          "Breadth to enter SHOCK (with sector depth)",
          type="float", default="0.40", min=0.05, max=1.0, step=0.05,
          help="v209. NORMAL -> SHOCK when this share of watchlist equities is down and at "
               "least SHOCK_SECTORS_FRAC of the sectors are down, on two consecutive readings."),
    Field("SHOCK_SECTORS_FRAC", "SHOCK_SECTORS_FRAC", "Market Shock",
          "Share of sectors that must be down",
          type="float", default="0.6", min=0.1, max=1.0, step=0.05,
          help="v209. Sectors down needed = ceil(this x sectors with >= 2 contributing names)."),
    Field("SHOCK_BREADTH_FAST", "SHOCK_BREADTH_FAST", "Market Shock",
          "Breadth to enter SHOCK (fast path)",
          type="float", default="0.25", min=0.05, max=1.0, step=0.05,
          help="v209. NORMAL -> SHOCK when this share is down and breadth rose by at least "
               "SHOCK_SPEED_ENTER since the previous reading of the same session."),
    Field("SHOCK_SPEED_ENTER", "SHOCK_SPEED_ENTER", "Market Shock",
          "Breadth speed for the fast path, per reading",
          type="float", default="0.10", min=0.01, max=1.0, step=0.01,
          help="v209. Rise in breadth since the previous same-session reading."),
    Field("SHOCK_VIX_SPIKE_PCT", "SHOCK_VIX_SPIKE_PCT", "Market Shock",
          "VIX day change that eases entry (%)",
          type="float", default="15.0", min=0, max=200, step=1,
          help="v209. A ^VIX day change at or above this lowers both entry breadth bars by "
               "SHOCK_VIX_RELIEF. VIX never triggers SHOCK on its own."),
    Field("SHOCK_VIX_RELIEF", "SHOCK_VIX_RELIEF", "Market Shock",
          "Breadth relief on a VIX spike",
          type="float", default="0.05", min=0, max=0.5, step=0.01,
          help="v209. Subtracted from SHOCK_BREADTH_ENTER and SHOCK_BREADTH_FAST on a VIX spike."),
    Field("SHOCK_BREADTH_REENTER", "SHOCK_BREADTH_REENTER", "Market Shock",
          "Breadth to re-enter SHOCK from RECOVERY",
          type="float", default="0.30", min=0.05, max=1.0, step=0.05,
          help="v209. RECOVERY -> SHOCK (second leg) on one reading at or above this with "
               "breadth rising since the previous reading, or on a new SPY session low."),
    Field("SHOCK_BREADTH_EXIT", "SHOCK_BREADTH_EXIT", "Market Shock",
          "Breadth at or below which SHOCK can end",
          type="float", default="0.20", min=0, max=1.0, step=0.05,
          help="v209. One of the SHOCK -> RECOVERY clauses (with dwell, VIX and SPY retrace)."),
    Field("RECOVERY_VIX_OFF_HIGH_PCT", "RECOVERY_VIX_OFF_HIGH_PCT", "Market Shock",
          "VIX off its session high for RECOVERY (%)",
          type="float", default="5.0", min=0, max=100, step=0.5,
          help="v209. The VIX clause holds when VIX is this far below its session high, or "
               "below its prior close. A missing VIX leaves the clause unmet."),
    Field("RECOVERY_SPY_RETRACE", "RECOVERY_SPY_RETRACE", "Market Shock",
          "Share of SPY's session drop regained",
          type="float", default="0.5", min=0, max=1.0, step=0.05,
          help="v209. SPY must regain this share of its drop from the prior close to the "
               "session low."),
    Field("SHOCK_MIN_DWELL_MIN", "SHOCK_MIN_DWELL_MIN", "Market Shock",
          "Minimum minutes in SHOCK; notice rate limit",
          type="number", default="45", min=0, max=600, step=5,
          help="v209. SHOCK cannot end sooner; also at most one notice per this many minutes, "
               "except a transition into SHOCK, which is always sent."),
    Field("RECOVERY_MIN_DWELL_MIN", "RECOVERY_MIN_DWELL_MIN", "Market Shock",
          "Minutes RECOVERY must hold before NORMAL",
          type="number", default="30", min=0, max=600, step=5,
          help="v209. The RECOVERY conditions must hold on every reading for this long."),
    Field("SHOCK_MIN_NAMES", "SHOCK_MIN_NAMES", "Market Shock",
          "Minimum contributing names per reading",
          type="number", default="20", min=1, max=1000, step=1,
          help="v209. Below this a reading is 'insufficient' and the state holds."),
    Field("SHOCK_VIX_MAX_AGE_S", "SHOCK_VIX_MAX_AGE_S", "Market Shock",
          "Oldest usable ^VIX tape row (seconds)",
          type="number", default="600", min=30, max=86400, step=30,
          help="v209. An older or missing ^VIX row leaves every VIX field empty."),
    Field("SHOCK_OPEN_SETTLE_MIN", "SHOCK_OPEN_SETTLE_MIN", "Market Shock",
          "Minutes after the US open before entry counts",
          type="number", default="15", min=0, max=120, step=1,
          help="v209. Readings earlier than this never count toward entering or re-entering "
               "SHOCK."),
    Field("SHOCK_QUOTE_MAX_AGE_S", "SHOCK_QUOTE_MAX_AGE_S", "Market Shock",
          "Oldest usable live quote (seconds)",
          type="number", default="300", min=10, max=3600, step=10,
          help="v209. When the pass's live quotes are older than this, no name contributes."),
    Field("SHOCK_READINGS_KEEP_DAYS", "SHOCK_READINGS_KEEP_DAYS", "Market Shock",
          "Days of readings to keep",
          type="number", default="180", min=1, max=3650, step=1,
          help="v209. The nightly recap prunes market_shock_readings older than this."),
```

In `_MODE_VALUES`, add one line after `"ADMIN_REFRESHER": ("on", "off"),`:

```python
    "MARKET_SHOCK_MODE": ("off", "shadow", "live"),
```

- [ ] **Step 4: Add the `.env.example` section**

In `.env.example`, after the `DCB_VOLUME_RATIO=0` line and its blank line,
before `# --- Database ---`, insert (keep the trailing blank line):

```
# --- Market Shock (v209; all hot-reloadable) ---
# The market-shock detector. shadow (default) measures, records and notifies
# on each NORMAL/SHOCK/RECOVERY transition and changes no trade; live is the
# same as shadow in v209; off is a byte-identical kill switch.
MARKET_SHOCK_MODE=shadow

# A name is "down" when (last - prior close) / ATR14 <= -SHOCK_ATR_K.
SHOCK_ATR_K=1.0

# NORMAL -> SHOCK: breadth and sector depth, or breadth and speed, on two
# consecutive readings at least SHOCK_OPEN_SETTLE_MIN after the open.
SHOCK_BREADTH_ENTER=0.40
SHOCK_SECTORS_FRAC=0.6
SHOCK_BREADTH_FAST=0.25
SHOCK_SPEED_ENTER=0.10

# A VIX day change at or above SHOCK_VIX_SPIKE_PCT lowers both breadth bars
# by SHOCK_VIX_RELIEF.
SHOCK_VIX_SPIKE_PCT=15.0
SHOCK_VIX_RELIEF=0.05

# RECOVERY -> SHOCK (second leg) at this rising breadth, or a new SPY low.
SHOCK_BREADTH_REENTER=0.30

# SHOCK -> RECOVERY: dwell, breadth at or below this, VIX off its high,
# SPY retrace.
SHOCK_BREADTH_EXIT=0.20
RECOVERY_VIX_OFF_HIGH_PCT=5.0
RECOVERY_SPY_RETRACE=0.5

# Dwell times in minutes; SHOCK_MIN_DWELL_MIN also rate-limits notices.
SHOCK_MIN_DWELL_MIN=45
RECOVERY_MIN_DWELL_MIN=30

# Reading quality: minimum contributing names, VIX and quote freshness, the
# open-settle window, and how long readings are kept.
SHOCK_MIN_NAMES=20
SHOCK_VIX_MAX_AGE_S=600
SHOCK_OPEN_SETTLE_MIN=15
SHOCK_QUOTE_MAX_AGE_S=300
SHOCK_READINGS_KEEP_DAYS=180

```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_config_v209_keys.py`
Expected: PASS (every parametrized case).

Run: `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
Expected: PASS (every new key is in `.env.example`, none extra).

Run: `python scripts/dev/complexity_gate.py`
Expected: no new violation (the change adds data only).

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_config_v209_keys.py
git commit -m "feat(v209): Market Shock config section -- MARKET_SHOCK_MODE and 18 thresholds"
```

# Phase 2 — the pure detector

### Task V209-2: `shock.py`: types, thresholds, JSON rows

**Model:** sonnet — a new pure module of frozen dataclasses and row helpers that every later task imports; small, but its names are the contract for parts 2 and 3.

**Files:**
- Create: `swingbot/core/market/shock.py`
- Create: `tests/market/test_shock_measure.py`

**Interfaces:**
- Consumes: nothing from the repo (stdlib only).
- Produces (later tasks import these names exactly):
  - `LABELS = ("NORMAL", "SHOCK", "RECOVERY")` and the aliases `NORMAL`, `SHOCK`, `RECOVERY`.
  - frozen `ShockThresholds(atr_k=1.0, breadth_enter=0.40, sectors_frac=0.6, breadth_fast=0.25, speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30, breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5, min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600, open_settle_min=15, quote_max_age_s=300)`.
  - frozen `NameRow(ticker: str, sector: str | None, last: float | None, prev_close: float | None, atr14: float | None, is_equity: bool)`.
  - frozen `VixTape(level: float | None, chg_pct: float | None, as_of: datetime | None)`.
  - frozen `ShockSnapshot(as_of: datetime, session_date: date, minutes_since_open: float, names: tuple[NameRow, ...], spy: NameRow | None, qqq: NameRow | None, vix: VixTape)`.
  - frozen `ShockReading(as_of, session_date, minutes_since_open, breadth_frac, sectors_down, sectors_total, breadth_speed, spy_atr_move, qqq_atr_move, spy_last, spy_prev_close, spy_session_low, spy_new_low, spy_retrace, vix_level, vix_chg_pct, vix_session_high, vix_off_high_pct, n_names, insufficient)` with `as_row() -> dict` (JSON-safe; datetimes and dates as ISO strings) and `classmethod from_row(row: dict) -> ShockReading`.
  - Module-private helpers V209-2b/3/4 reuse: `_EPS = 1e-9`; `_meets(value: float | None, bar: float) -> bool` (`value + _EPS >= bar`, `None` never meets); `_to_row(obj) -> dict`; `_from_row(cls, row: dict)`; `_DATETIME_FIELDS = {"as_of", "since", "hold_since"}` (already covers V209-3's `ShockState`), `_DATE_FIELDS = {"session_date"}`.
- `measure` is V209-2b.

Why `_EPS`: breadth fractions are ratios of small integers and the VIX
relief subtracts a float, so `7/20 = 0.35` must meet `0.40 − 0.05 =
0.35000000000000003`. Every threshold comparison in this module goes through
`_meets` (or the `_EPS`-tolerant `≤` V209-2b adds).

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_shock_measure.py` (V209-2b appends the `measure`
tests to this file):

```python
"""v209 shock.py: types, rows and measure (spec § The reading, § Units)."""
import ast
import dataclasses
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (LABELS, NameRow, ShockReading, ShockSnapshot,
                                        ShockThresholds, VixTape)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET
D0 = date(2026, 11, 5)
NO_VIX = VixTape(None, None, None)
TH = ShockThresholds(min_names=3)


def _full_reading(**over):
    base = dict(
        as_of=T0, session_date=D0, minutes_since_open=60.0, breadth_frac=0.45,
        sectors_down=4, sectors_total=6, breadth_speed=0.12, spy_atr_move=-1.8,
        qqq_atr_move=None, spy_last=490.0, spy_prev_close=500.0, spy_session_low=489.5,
        spy_new_low=True, spy_retrace=0.05, vix_level=21.13, vix_chg_pct=27.21,
        vix_session_high=21.5, vix_off_high_pct=1.77, n_names=42, insufficient=False)
    base.update(over)
    return ShockReading(**base)


def test_labels_are_the_three_states_in_order():
    assert LABELS == ("NORMAL", "SHOCK", "RECOVERY")
    assert (shock.NORMAL, shock.SHOCK, shock.RECOVERY) == LABELS


def test_threshold_defaults_equal_the_config_defaults():
    assert ShockThresholds() == ShockThresholds(
        atr_k=1.0, breadth_enter=0.40, sectors_frac=0.6, breadth_fast=0.25,
        speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30,
        breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5,
        min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600,
        open_settle_min=15, quote_max_age_s=300)


def test_reading_field_order_is_the_ledger_contract():
    assert [f.name for f in dataclasses.fields(ShockReading)] == [
        "as_of", "session_date", "minutes_since_open", "breadth_frac", "sectors_down",
        "sectors_total", "breadth_speed", "spy_atr_move", "qqq_atr_move", "spy_last",
        "spy_prev_close", "spy_session_low", "spy_new_low", "spy_retrace", "vix_level",
        "vix_chg_pct", "vix_session_high", "vix_off_high_pct", "n_names", "insufficient"]


@pytest.mark.parametrize("value", [
    ShockThresholds(),
    NameRow("MU", "Information Technology", 98.0, 100.0, 2.0, True),
    VixTape(21.13, 27.21, T0),
    ShockSnapshot(T0, D0, 60.0, (), None, None, NO_VIX),
])
def test_every_type_is_frozen(value):
    first = dataclasses.fields(value)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, first, None)


def test_reading_round_trips_through_json_with_iso_times():
    reading = _full_reading()
    row = json.loads(json.dumps(reading.as_row()))
    assert row["as_of"] == "2026-11-05T15:30:00+00:00"
    assert row["session_date"] == "2026-11-05"
    assert row["qqq_atr_move"] is None and row["spy_new_low"] is True
    assert ShockReading.from_row(row) == reading


def test_round_trip_keeps_none_everywhere_a_field_allows_it():
    reading = _full_reading(breadth_frac=None, breadth_speed=None, spy_atr_move=None,
                            spy_last=None, spy_prev_close=None, spy_session_low=None,
                            spy_new_low=False, spy_retrace=None, vix_level=None,
                            vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None,
                            n_names=0, insufficient=True)
    assert ShockReading.from_row(json.loads(json.dumps(reading.as_row()))) == reading


def test_from_row_accepts_already_decoded_values():
    reading = _full_reading()
    assert ShockReading.from_row(dataclasses.asdict(reading)) == reading


def test_from_row_refuses_a_row_missing_a_field():
    row = _full_reading().as_row()
    del row["n_names"]
    with pytest.raises(TypeError):
        ShockReading.from_row(row)


def test_meets_tolerates_float_noise_and_never_meets_none():
    assert shock._meets(7 / 20, 0.40 - 0.05) is True
    assert shock._meets(0.3499, 0.35) is False
    assert shock._meets(None, 0.0) is False


def test_shock_module_imports_no_config_and_does_no_io():
    source = pathlib.Path(shock.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"__future__", "math", "statistics", "dataclasses", "datetime",
                        "typing", "collections.abc"}
```

`NO_VIX` and `TH` are unused until V209-2b appends the `measure` tests; keep
them (they are module constants, not lint errors).

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.shock'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/market/shock.py`:

```python
"""v209 market-shock detector: one reading per scan pass, and its state machine.

Pure: no I/O and no ``swingbot.config`` import. Thresholds arrive as a frozen
:class:`ShockThresholds` whose defaults equal the "Market Shock" config
defaults; ``swingbot.core.scanning.shock_scan`` builds one from config, builds
the :class:`ShockSnapshot` from the scan's frames and live quotes, and stores
what ``measure`` and ``step`` return.

A reading measures the watchlist at pass time (the live quote against the last
completed session's close); it never looks at a later bar.

Spec: docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime

LABELS = ("NORMAL", "SHOCK", "RECOVERY")
NORMAL, SHOCK, RECOVERY = LABELS

#: Tolerance for threshold comparisons, so 7/20 meets a 0.40 - 0.05 bar.
_EPS = 1e-9

_DATETIME_FIELDS = frozenset({"as_of", "since", "hold_since"})
_DATE_FIELDS = frozenset({"session_date"})


@dataclass(frozen=True)
class ShockThresholds:
    atr_k: float = 1.0
    breadth_enter: float = 0.40
    sectors_frac: float = 0.6
    breadth_fast: float = 0.25
    speed_enter: float = 0.10
    vix_spike_pct: float = 15.0
    vix_relief: float = 0.05
    breadth_reenter: float = 0.30
    breadth_exit: float = 0.20
    recovery_vix_off_high_pct: float = 5.0
    recovery_spy_retrace: float = 0.5
    min_dwell_min: int = 45
    recovery_min_dwell_min: int = 30
    min_names: int = 20
    vix_max_age_s: int = 600
    open_settle_min: int = 15
    quote_max_age_s: int = 300


@dataclass(frozen=True)
class NameRow:
    ticker: str
    sector: str | None
    last: float | None
    prev_close: float | None
    atr14: float | None
    is_equity: bool


@dataclass(frozen=True)
class VixTape:
    level: float | None
    chg_pct: float | None
    as_of: datetime | None


@dataclass(frozen=True)
class ShockSnapshot:
    as_of: datetime
    session_date: date
    minutes_since_open: float
    names: tuple[NameRow, ...]
    spy: NameRow | None
    qqq: NameRow | None
    vix: VixTape


@dataclass(frozen=True)
class ShockReading:
    as_of: datetime
    session_date: date
    minutes_since_open: float
    breadth_frac: float | None
    sectors_down: int
    sectors_total: int
    breadth_speed: float | None
    spy_atr_move: float | None
    qqq_atr_move: float | None
    spy_last: float | None
    spy_prev_close: float | None
    spy_session_low: float | None
    spy_new_low: bool
    spy_retrace: float | None
    vix_level: float | None
    vix_chg_pct: float | None
    vix_session_high: float | None
    vix_off_high_pct: float | None
    n_names: int
    insufficient: bool

    def as_row(self) -> dict:
        return _to_row(self)

    @classmethod
    def from_row(cls, row: dict) -> "ShockReading":
        return _from_row(cls, row)


# --- JSON rows -------------------------------------------------------------

def _encode(value):
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def _decode(name: str, value):
    if not isinstance(value, str):
        return value
    if name in _DATETIME_FIELDS:
        return datetime.fromisoformat(value)
    if name in _DATE_FIELDS:
        return date.fromisoformat(value)
    return value


def _to_row(obj) -> dict:
    return {f.name: _encode(getattr(obj, f.name)) for f in fields(obj)}


def _from_row(cls, row: dict):
    """Rebuild a dataclass from its row. A key the class lacks is ignored; a
    required field missing from the row raises ``TypeError`` (no upcasting)."""
    return cls(**{f.name: _decode(f.name, row[f.name]) for f in fields(cls) if f.name in row})


# --- small numeric helpers -------------------------------------------------

def _meets(value: float | None, bar: float) -> bool:
    """``value >= bar`` with the ``_EPS`` tolerance; a missing value never meets."""
    return value is not None and value + _EPS >= bar
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/shock.py tests/market/test_shock_measure.py
git commit -m "feat(v209): shock.py -- reading types, thresholds and JSON rows"
```

### Task V209-2b: `shock.py`: `measure`

**Model:** sonnet — numeric reading rules with several edge cases (sector minimum and median, same-session carry, stale VIX, missing SPY) in a pure function set, each helper under complexity 15.

**Files:**
- Modify: `swingbot/core/market/shock.py` (two stdlib imports; helpers and `measure` appended after `_meets`)
- Modify: `tests/market/test_shock_measure.py` (import `measure`; append the `measure` tests)

**Interfaces:**
- Consumes (V209-2): `NameRow`, `VixTape`, `ShockSnapshot`, `ShockReading`, `ShockThresholds`, `_EPS`, `_meets`.
- Produces: `measure(snapshot: ShockSnapshot, prev: ShockReading | None, th: ShockThresholds = ShockThresholds()) -> ShockReading` (V209-6 calls it with the latest stored reading as `prev`; V209-12 replays it). Private `_atr_move(row: NameRow | None) -> float | None` (V209-6 may reuse it for SPY/QQQ display; it is not part of the ledger contract).

Reading rules (spec § The reading; index Global Constraints):

- A name **contributes** when `is_equity` is true and `last`, `prev_close`,
  `atr14` are present, `atr14 > 0` and the ratio is finite. V209-6 sets
  `last=None` for a name without a fresh live quote and `atr14=None` for
  fewer than 15 completed bars, so `measure` needs no quote clock or history.
- `breadth_frac` = share of contributors with ratio `≤ −atr_k` (`_EPS`
  tolerance); `None` when nothing contributes.
- `sectors_total` = sectors with ≥ 2 contributors; `sectors_down` = those
  whose **median** ratio is `≤ −atr_k`. `sector=None` counts toward breadth only.
- `breadth_speed` = `breadth_frac − prev.breadth_frac` only when `prev` has
  the same `session_date`, is not `insufficient`, and both values exist.
- SPY: `spy_session_low` is the running min of `spy_last` this session
  (carried from `prev` only when same session); `spy_new_low` needs an
  earlier same-session low and `spy_last` strictly below it; `spy_retrace =
  (last − low) / (prev_close − low)`, `1.0` when `low ≥ prev_close`, `None`
  when SPY or its prior close is missing. `qqq_atr_move` is QQQ's ratio or `None`.
- VIX: no level, no `as_of`, or older than `vix_max_age_s` at
  `snapshot.as_of` ⇒ `vix_level` and `vix_chg_pct` are `None`.
  `vix_session_high` is the running max this session (kept when today's
  level is missing); `vix_off_high_pct = (high − level) / high × 100`.
- `n_names` = contributors; `insufficient = n_names < min_names`.

- [ ] **Step 1: Write the failing tests**

In `tests/market/test_shock_measure.py`, change the shock import to:

```python
from swingbot.core.market.shock import (LABELS, NameRow, ShockReading, ShockSnapshot,
                                        ShockThresholds, VixTape, measure)
```

Append to the end of the file:

```python
# --- measure (V209-2b) -----------------------------------------------------

def _row(ticker, move, sector="Tech", *, equity=True, atr=2.0, prev=100.0):
    """A name whose (last - prev_close) / atr14 is exactly `move`."""
    return NameRow(ticker, sector, prev + move * atr, prev, atr, equity)


def _snap(names, *, as_of=T0, session=D0, minutes=60.0, spy=None, qqq=None, vix=NO_VIX):
    return ShockSnapshot(as_of, session, minutes, tuple(names), spy, qqq, vix)


def _flat(n, sector="Flat"):
    return [_row(f"F{i}", 0.0, sector) for i in range(n)]


def _spy(last, prev=500.0, atr=5.0):
    return NameRow("SPY", None, last, prev, atr, False)


def _later(minutes):
    return T0 + timedelta(minutes=minutes)


def test_breadth_counts_equities_only_and_non_equities_never_contribute():
    names = [_row(f"D{i}", -1.5) for i in range(4)] + _flat(6)
    names += [_row(sym, -3.0, None, equity=False) for sym in ("XAUUSD", "XAGUSD", "GC=F")]
    reading = measure(_snap(names), None, TH)
    assert reading.n_names == 10
    assert reading.breadth_frac == pytest.approx(0.4)


def test_exactly_minus_one_atr_counts_as_down_and_just_above_does_not():
    reading = measure(_snap([_row("A", -1.0), _row("B", -0.99), _row("C", 0.5)]), None, TH)
    assert reading.breadth_frac == pytest.approx(1 / 3)


@pytest.mark.parametrize("bad", [
    NameRow("NOQ", "Tech", None, 100.0, 2.0, True),       # no fresh live quote
    NameRow("NOP", "Tech", 98.0, None, 2.0, True),        # no completed prior bar
    NameRow("NOA", "Tech", 98.0, 100.0, None, True),      # < 15 completed bars
    NameRow("ZER", "Tech", 98.0, 100.0, 0.0, True),       # degenerate ATR
    NameRow("NAN", "Tech", 98.0, 100.0, float("nan"), True),
])
def test_names_without_a_usable_ratio_are_excluded_from_n_names(bad):
    reading = measure(_snap(_flat(3) + [bad]), None, TH)
    assert reading.n_names == 3 and reading.breadth_frac == 0.0


def test_sectors_need_two_contributing_members_and_use_the_median():
    names = [
        _row("A1", -2.0, "Semis"), _row("A2", -1.5, "Semis"), _row("A3", 0.5, "Semis"),  # median -1.5
        _row("B1", -3.0, "Energy"),                                                     # 1 member
        _row("C1", 0.0, "Banks"), _row("C2", -0.2, "Banks"),                            # median -0.1
        _row("N1", -2.0, None),                                                          # no sector
    ]
    reading = measure(_snap(names), None, TH)
    assert (reading.sectors_down, reading.sectors_total) == (1, 2)
    assert reading.n_names == 7 and reading.breadth_frac == pytest.approx(4 / 7)


def test_empty_watchlist_is_insufficient_with_no_breadth():
    reading = measure(_snap([]), None, ShockThresholds())
    assert reading.n_names == 0 and reading.insufficient is True
    assert reading.breadth_frac is None and reading.breadth_speed is None
    assert (reading.sectors_down, reading.sectors_total) == (0, 0)


def test_insufficient_below_min_names_and_sufficient_at_it():
    th = ShockThresholds(min_names=5)
    assert measure(_snap(_flat(4)), None, th).insufficient is True
    assert measure(_snap(_flat(5)), None, th).insufficient is False


def test_measure_defaults_its_thresholds():
    reading = measure(_snap(_flat(20)), None)
    assert reading.insufficient is False and reading.n_names == 20


def test_breadth_speed_only_within_the_same_session():
    first = measure(_snap([_row("A", -2.0)] + _flat(3)), None, TH)                     # 0.25
    two_down = [_row("A", -2.0), _row("B", -2.0)] + _flat(2)                           # 0.50
    assert first.breadth_speed is None
    assert measure(_snap(two_down, as_of=_later(15)), first, TH).breadth_speed == pytest.approx(0.25)
    next_day = _snap(two_down, as_of=T0 + timedelta(days=1), session=D0 + timedelta(days=1))
    assert measure(next_day, first, TH).breadth_speed is None


def test_breadth_speed_ignores_an_insufficient_previous_reading():
    thin = measure(_snap(_flat(2)), None, TH)
    assert thin.insufficient is True
    later = _snap([_row("A", -2.0)] + _flat(3), as_of=_later(15))
    assert measure(later, thin, TH).breadth_speed is None


def test_spy_and_qqq_atr_moves_are_recorded():
    qqq = _row("QQQ", -1.25, None, equity=False)
    reading = measure(_snap(_flat(3), spy=_spy(490.0), qqq=qqq), None, TH)
    assert reading.spy_atr_move == pytest.approx(-2.0)
    assert reading.qqq_atr_move == pytest.approx(-1.25)
    assert (reading.spy_last, reading.spy_prev_close) == (490.0, 500.0)


def test_spy_session_low_runs_and_a_new_low_needs_an_earlier_same_session_reading():
    first = measure(_snap(_flat(3), spy=_spy(490.0)), None, TH)
    assert first.spy_session_low == 490.0 and first.spy_new_low is False
    bounce = measure(_snap(_flat(3), as_of=_later(15), spy=_spy(495.0)), first, TH)
    assert bounce.spy_session_low == 490.0 and bounce.spy_new_low is False
    assert bounce.spy_retrace == pytest.approx(0.5)
    lower = measure(_snap(_flat(3), as_of=_later(30), spy=_spy(489.0)), bounce, TH)
    assert lower.spy_session_low == 489.0 and lower.spy_new_low is True
    equal = measure(_snap(_flat(3), as_of=_later(45), spy=_spy(489.0)), lower, TH)
    assert equal.spy_new_low is False


def test_spy_retrace_is_one_when_the_session_never_traded_below_the_prior_close():
    assert measure(_snap(_flat(3), spy=_spy(503.0)), None, TH).spy_retrace == 1.0


def test_a_new_session_restarts_the_spy_low_and_prior_close():
    yesterday = measure(_snap(_flat(3), spy=_spy(480.0)), None, TH)
    today = measure(_snap(_flat(3), as_of=T0 + timedelta(days=1), session=D0 + timedelta(days=1),
                          spy=_spy(485.0, prev=482.0)), yesterday, TH)
    assert today.spy_session_low == 485.0 and today.spy_new_low is False
    assert today.spy_prev_close == 482.0 and today.spy_retrace == 1.0


def test_missing_spy_leaves_every_spy_field_empty():
    reading = measure(_snap(_flat(3)), None, TH)
    assert (reading.spy_atr_move, reading.spy_last, reading.spy_prev_close,
            reading.spy_session_low, reading.spy_retrace) == (None, None, None, None, None)
    assert reading.spy_new_low is False and reading.qqq_atr_move is None


def test_fresh_vix_fills_level_change_and_session_high():
    reading = measure(_snap(_flat(3), vix=VixTape(21.13, 27.21, T0 - timedelta(seconds=60))), None, TH)
    assert (reading.vix_level, reading.vix_chg_pct) == (21.13, 27.21)
    assert reading.vix_session_high == 21.13 and reading.vix_off_high_pct == 0.0


def test_vix_session_high_is_the_running_max_and_off_high_is_a_percent():
    first = measure(_snap(_flat(3), vix=VixTape(25.0, 30.0, T0)), None, TH)
    later = measure(_snap(_flat(3), as_of=_later(15), vix=VixTape(22.5, 15.0, _later(15))), first, TH)
    assert later.vix_session_high == 25.0
    assert later.vix_off_high_pct == pytest.approx(10.0)


@pytest.mark.parametrize("vix", [
    VixTape(None, None, None),                                   # no ^VIX row
    VixTape(20.0, 5.0, None),                                    # no timestamp
    VixTape(20.0, 5.0, T0 - timedelta(seconds=601)),             # older than SHOCK_VIX_MAX_AGE_S
])
def test_missing_or_stale_vix_is_none(vix):
    reading = measure(_snap(_flat(3), vix=vix), None, TH)
    assert (reading.vix_level, reading.vix_chg_pct, reading.vix_off_high_pct) == (None, None, None)
    assert reading.vix_session_high is None


def test_a_stale_vix_keeps_the_session_high_already_seen():
    first = measure(_snap(_flat(3), vix=VixTape(25.0, 30.0, T0)), None, TH)
    later = measure(_snap(_flat(3), as_of=_later(15), vix=VixTape(24.0, 20.0, T0)), first, TH)  # 900 s old
    assert later.vix_level is None and later.vix_session_high == 25.0
    assert later.vix_off_high_pct is None


def test_a_new_session_restarts_the_vix_high():
    first = measure(_snap(_flat(3), vix=VixTape(30.0, 30.0, T0)), None, TH)
    tomorrow = T0 + timedelta(days=1)
    today = measure(_snap(_flat(3), as_of=tomorrow, session=D0 + timedelta(days=1),
                          vix=VixTape(22.0, -10.0, tomorrow)), first, TH)
    assert today.vix_session_high == 22.0 and today.vix_off_high_pct == 0.0


def test_a_measured_reading_round_trips_through_json():
    names = [_row("A", -2.0, "Semis"), _row("B", -2.0, "Semis")] + _flat(2)
    reading = measure(_snap(names, spy=_spy(490.0), vix=VixTape(21.0, 20.0, T0)), None, TH)
    assert ShockReading.from_row(json.loads(json.dumps(reading.as_row()))) == reading
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: FAIL — `ImportError: cannot import name 'measure' from 'swingbot.core.market.shock'`.

- [ ] **Step 3: Implement `measure`**

In `swingbot/core/market/shock.py`, change the import block to:

```python
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, fields
from datetime import date, datetime
```

Append after `_meets`:

```python
def _is_down(move: float, atr_k: float) -> bool:
    return move <= -atr_k + _EPS


def _atr_move(row: NameRow | None) -> float | None:
    if row is None or row.last is None or row.prev_close is None or row.atr14 is None:
        return None
    if not row.atr14 > 0:                       # also rejects NaN
        return None
    move = (row.last - row.prev_close) / row.atr14
    return move if math.isfinite(move) else None


def _running(pick, prior: float | None, value: float | None) -> float | None:
    if prior is None:
        return value
    if value is None:
        return prior
    return pick(prior, value)


# --- the reading -----------------------------------------------------------

def _contributors(names) -> list[tuple[str | None, float]]:
    out = []
    for row in names:
        move = _atr_move(row) if row.is_equity else None
        if move is not None:
            out.append((row.sector, move))
    return out


def _breadth(contribs, atr_k: float) -> float | None:
    if not contribs:
        return None
    return sum(1 for _sector, move in contribs if _is_down(move, atr_k)) / len(contribs)


def _sectors(contribs, atr_k: float) -> tuple[int, int]:
    by_sector: dict[str, list[float]] = {}
    for sector, move in contribs:
        if sector:
            by_sector.setdefault(sector, []).append(move)
    groups = [moves for moves in by_sector.values() if len(moves) >= 2]
    down = sum(1 for moves in groups if _is_down(statistics.median(moves), atr_k))
    return down, len(groups)


def _speed(breadth: float | None, prev: ShockReading | None, same: bool) -> float | None:
    if not same or breadth is None or prev.insufficient or prev.breadth_frac is None:
        return None
    return breadth - prev.breadth_frac


def _retrace(last, prev_close, low) -> float | None:
    if last is None or prev_close is None or low is None:
        return None
    if low >= prev_close:
        return 1.0
    return (last - low) / (prev_close - low)


def _spy_fields(spy: NameRow | None, prev: ShockReading | None, same: bool) -> dict:
    last = spy.last if spy is not None else None
    prev_close = spy.prev_close if spy is not None else None
    prior_low = prev.spy_session_low if same else None
    low = _running(min, prior_low, last)
    return {
        "spy_last": last,
        "spy_prev_close": prev_close,
        "spy_session_low": low,
        "spy_new_low": prior_low is not None and last is not None and last < prior_low,
        "spy_retrace": _retrace(last, prev_close, low),
    }


def _fresh_vix(vix: VixTape, now: datetime, max_age_s: int) -> tuple[float | None, float | None]:
    if vix.level is None or vix.as_of is None:
        return None, None
    if (now - vix.as_of).total_seconds() > max_age_s:
        return None, None
    return vix.level, vix.chg_pct


def _vix_fields(snapshot: ShockSnapshot, prev: ShockReading | None, same: bool,
                th: ShockThresholds) -> dict:
    level, chg = _fresh_vix(snapshot.vix, snapshot.as_of, th.vix_max_age_s)
    high = _running(max, prev.vix_session_high if same else None, level)
    off = (high - level) / high * 100.0 if level is not None and high else None
    return {"vix_level": level, "vix_chg_pct": chg, "vix_session_high": high,
            "vix_off_high_pct": off}


def measure(snapshot: ShockSnapshot, prev: ShockReading | None,
            th: ShockThresholds = ShockThresholds()) -> ShockReading:
    """Build one reading from a pass's snapshot and the previous stored reading."""
    same = prev is not None and prev.session_date == snapshot.session_date
    contribs = _contributors(snapshot.names)
    breadth = _breadth(contribs, th.atr_k)
    down, total = _sectors(contribs, th.atr_k)
    return ShockReading(
        as_of=snapshot.as_of,
        session_date=snapshot.session_date,
        minutes_since_open=snapshot.minutes_since_open,
        breadth_frac=breadth,
        sectors_down=down,
        sectors_total=total,
        breadth_speed=_speed(breadth, prev, same),
        spy_atr_move=_atr_move(snapshot.spy),
        qqq_atr_move=_atr_move(snapshot.qqq),
        **_spy_fields(snapshot.spy, prev, same),
        **_vix_fields(snapshot, prev, same, th),
        n_names=len(contribs),
        insufficient=len(contribs) < th.min_names,
    )
```

Notes: `_atr_move` serves SPY and QQQ without the `is_equity` filter (V209-6
passes them as `is_equity=False`; only `_contributors` checks the flag).
`_fresh_vix` returns `(None, None)` together, so `vix_chg_pct` is never set
without a usable level. `_atr_move` only returns finite floats, so `as_row()`
stays JSON-safe with no NaN guard.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (largest new function `_atr_move`, about 6).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/shock.py tests/market/test_shock_measure.py
git commit -m "feat(v209): shock.measure -- breadth, sectors, speed, SPY and VIX fields"
```

### Task V209-3: `shock.py`: `ShockState` + `step` entry rules

**Model:** sonnet — a table-driven state machine with a two-consecutive-readings streak and an open-settle rule; pure code, but the rule order matters.

**Files:**
- Modify: `swingbot/core/market/shock.py` (import `replace`, `Callable`; append `ShockState`, entry rules, `RULES`, `step`)
- Create: `tests/market/test_shock_step_entry.py`

**Interfaces:**
- Consumes (V209-2/2b): `LABELS`, `NORMAL`, `SHOCK`, `RECOVERY`, `ShockReading`, `ShockThresholds`, `_EPS`, `_meets`, `_to_row`, `_from_row`.
- Produces: frozen `ShockState(label="NORMAL", since: datetime | None = None, session_date: date | None = None, vix_session_high: float | None = None, spy_prev_close: float | None = None, entry_streak: int = 0, hold_since: datetime | None = None, prev_breadth: float | None = None)` (an unknown label raises `ValueError`) with `as_row() -> dict` and `classmethod from_row(row: dict | None) -> ShockState` (`None`/`{}` ⇒ `ShockState()`); `entry_condition(reading, th=ShockThresholds()) -> bool`; `RULES: dict[str, Callable[[ShockState, ShockReading, ShockThresholds], ShockState]]` keyed by every label; `step(state, reading, th=ShockThresholds()) -> ShockState`. Private `_settled(reading, th)`, `_enter_shock(state, reading)`, `_carry(state, reading)` that V209-4 reuses.

Rules (spec § State machine; index Global Constraints):

- `step` returns the **same object** for an `insufficient` reading (it neither
  counts toward nor resets the entry streak).
- Otherwise `_carry` copies `session_date`, `vix_session_high` and
  `spy_prev_close` from the reading (a missing SPY prior close keeps the
  state's value within the same session, `None` on a new one) and, on a new
  session, clears `prev_breadth` and `hold_since`; then `RULES[label]` runs;
  then `prev_breadth` is set to the reading's `breadth_frac`.
- **Entry condition**: depth path (`sectors_total ≥ 1`,
  `sectors_down ≥ ceil(sectors_frac × sectors_total)`, breadth ≥
  `breadth_enter − relief`) or fast path (breadth ≥ `breadth_fast − relief`
  and `breadth_speed ≥ speed_enter`); `relief = vix_relief` when
  `vix_chg_pct ≥ vix_spike_pct`, else 0. SPY/QQQ moves never trigger.
- **NORMAL**: a reading that is not settled (`minutes_since_open <
  open_settle_min`) or fails the entry condition resets `entry_streak` to 0;
  a qualifying settled reading increments it; the second consecutive one
  enters SHOCK (`since = reading.as_of`, streak 0, `hold_since` `None`).
- **SHOCK** and **RECOVERY** hold their state in this task (`_hold`);
  V209-4 replaces both entries.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_shock_step_entry.py`:

```python
"""v209 shock.step: NORMAL -> SHOCK entry rules (spec § State machine)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (LABELS, ShockReading, ShockState, ShockThresholds,
                                        entry_condition, step)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET, 60 min after the open
D0 = date(2026, 11, 5)
TH = ShockThresholds()


def _reading(at=0, **over):
    """A calm, sufficient reading `at` minutes after T0; override any field."""
    base = dict(
        as_of=T0 + timedelta(minutes=at), session_date=D0, minutes_since_open=60.0 + at,
        breadth_frac=0.05, sectors_down=0, sectors_total=5, breadth_speed=None,
        spy_atr_move=0.0, qqq_atr_move=None, spy_last=500.0, spy_prev_close=500.0,
        spy_session_low=500.0, spy_new_low=False, spy_retrace=1.0, vix_level=16.0,
        vix_chg_pct=0.0, vix_session_high=16.0, vix_off_high_pct=0.0, n_names=30,
        insufficient=False)
    base.update(over)
    return ShockReading(**base)


DEPTH = dict(breadth_frac=0.40, sectors_down=3, sectors_total=5)
FAST = dict(breadth_frac=0.25, breadth_speed=0.10)


def _run(state, *readings):
    for reading in readings:
        state = step(state, reading, TH)
    return state


def test_default_state_and_label_validation():
    assert ShockState() == ShockState(label="NORMAL", since=None, session_date=None,
                                      vix_session_high=None, spy_prev_close=None,
                                      entry_streak=0, hold_since=None, prev_breadth=None)
    with pytest.raises(ValueError):
        ShockState(label="PANIC")


def test_state_round_trips_through_json_and_empty_rows_mean_default():
    state = ShockState("SHOCK", T0, D0, 25.0, 500.0, 0, T0, 0.42)
    assert ShockState.from_row(json.loads(json.dumps(state.as_row()))) == state
    assert ShockState.from_row(None) == ShockState() == ShockState.from_row({})


def test_rules_cover_every_label():
    assert set(shock.RULES) == set(LABELS)


@pytest.mark.parametrize("over", [DEPTH, FAST], ids=["depth", "fast"])
def test_two_consecutive_qualifying_readings_enter_shock(over):
    first = step(ShockState(), _reading(0, **over), TH)
    assert first.label == "NORMAL" and first.entry_streak == 1
    second = step(first, _reading(15, **over), TH)
    assert second.label == "SHOCK" and second.since == T0 + timedelta(minutes=15)
    assert second.entry_streak == 0 and second.hold_since is None


def test_a_non_qualifying_reading_between_resets_the_streak():
    state = _run(ShockState(), _reading(0, **DEPTH), _reading(15), _reading(30, **DEPTH))
    assert state.label == "NORMAL" and state.entry_streak == 1


@pytest.mark.parametrize("over, expected", [
    (dict(breadth_frac=0.50, sectors_down=2, sectors_total=5), False),   # needs ceil(3.0) = 3
    (dict(breadth_frac=0.50, sectors_down=3, sectors_total=5), True),
    (dict(breadth_frac=0.50, sectors_down=2, sectors_total=3), True),    # ceil(1.8) = 2
    (dict(breadth_frac=0.50, sectors_down=0, sectors_total=0), False),   # no sector to judge depth
    (dict(breadth_frac=0.39, sectors_down=5, sectors_total=5), False),
    (dict(breadth_frac=0.25, breadth_speed=0.09), False),
    (dict(breadth_frac=0.24, breadth_speed=0.20), False),
    (dict(breadth_frac=0.30, breadth_speed=None), False),
    (dict(breadth_frac=None, sectors_down=5, sectors_total=5), False),
    (dict(breadth_frac=0.05, spy_atr_move=-4.0, qqq_atr_move=-4.0), False),  # index moves never trigger
])
def test_entry_condition_paths(over, expected):
    assert entry_condition(_reading(**over), TH) is expected


@pytest.mark.parametrize("chg, expected", [(15.0, True), (14.9, False), (None, False)])
def test_vix_spike_lowers_both_breadth_bars(chg, expected):
    depth = _reading(breadth_frac=7 / 20, sectors_down=3, sectors_total=5, vix_chg_pct=chg)
    fast = _reading(breadth_frac=0.20, breadth_speed=0.10, vix_chg_pct=chg)
    assert entry_condition(depth, TH) is expected
    assert entry_condition(fast, TH) is expected


def test_readings_inside_the_open_settle_window_never_count():
    early = dict(DEPTH, minutes_since_open=14.0)
    state = _run(ShockState(), _reading(0, **early), _reading(1, **dict(early, minutes_since_open=14.9)))
    assert state.label == "NORMAL" and state.entry_streak == 0
    state = _run(state, _reading(2, **dict(DEPTH, minutes_since_open=15.0)))
    assert state.entry_streak == 1
    state = _run(state, _reading(3, **dict(DEPTH, minutes_since_open=10.0)))   # resets
    assert state.entry_streak == 0


def test_an_insufficient_reading_returns_the_state_untouched():
    state = step(ShockState(), _reading(0, **DEPTH), TH)
    thin = _reading(15, **dict(DEPTH, n_names=3, insufficient=True))
    assert step(state, thin, TH) is state
    assert step(state, _reading(30, **DEPTH), TH).label == "SHOCK"


def test_hysteresis_band_holds_normal():
    between = dict(breadth_frac=0.30, sectors_down=3, sectors_total=5)
    state = _run(ShockState(), *[_reading(15 * i, **between) for i in range(4)])
    assert state.label == "NORMAL" and state.entry_streak == 0


def test_carry_copies_session_fields_and_records_breadth():
    state = step(ShockState(), _reading(0, vix_session_high=22.0, spy_prev_close=501.0,
                                        breadth_frac=0.12), TH)
    assert (state.session_date, state.vix_session_high, state.spy_prev_close) == (D0, 22.0, 501.0)
    assert state.prev_breadth == 0.12


def test_a_missing_spy_prior_close_keeps_it_within_the_session_only():
    state = step(ShockState(), _reading(0), TH)
    same = step(state, _reading(15, spy_prev_close=None), TH)
    assert same.spy_prev_close == 500.0
    next_day = _reading(0, as_of=T0 + timedelta(days=1), session_date=D0 + timedelta(days=1),
                        spy_prev_close=None)
    assert step(same, next_day, TH).spy_prev_close is None


def test_a_shock_state_with_breadth_still_high_stays_shock():
    state = ShockState("SHOCK", T0, D0, 20.0, 500.0)
    after = step(state, _reading(120, breadth_frac=0.50, sectors_down=4), TH)
    assert after.label == "SHOCK" and after.since == T0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`
Expected: FAIL — `ImportError: cannot import name 'ShockState'`.

- [ ] **Step 3: Implement**

In `swingbot/core/market/shock.py` change two imports:

```python
from dataclasses import dataclass, fields, replace
from typing import Callable
```

(keep `math`, `statistics`, `date`, `datetime`; `typing` is on the purity
test's allow-list). Append at the end of the module:

```python
# --- the state machine -----------------------------------------------------

@dataclass(frozen=True)
class ShockState:
    """The stored state. ``entry_streak``, ``hold_since`` and ``prev_breadth``
    are the bookkeeping for the two-consecutive rule, the RECOVERY hold and the
    rising-breadth re-entry; they live in ``market_shock_state.doc["state"]``."""
    label: str = NORMAL
    since: datetime | None = None
    session_date: date | None = None
    vix_session_high: float | None = None
    spy_prev_close: float | None = None
    entry_streak: int = 0
    hold_since: datetime | None = None
    prev_breadth: float | None = None

    def __post_init__(self):
        if self.label not in LABELS:
            raise ValueError(f"unknown shock label {self.label!r}")

    def as_row(self) -> dict:
        return _to_row(self)

    @classmethod
    def from_row(cls, row: dict | None) -> "ShockState":
        return cls() if not row else _from_row(cls, row)


Rule = Callable[[ShockState, ShockReading, ShockThresholds], ShockState]


def _settled(reading: ShockReading, th: ShockThresholds) -> bool:
    """False for readings inside the open-settle window (the opening gap)."""
    return reading.minutes_since_open + _EPS >= th.open_settle_min


def _relief(reading: ShockReading, th: ShockThresholds) -> float:
    return th.vix_relief if _meets(reading.vix_chg_pct, th.vix_spike_pct) else 0.0


def _sectors_needed(reading: ShockReading, th: ShockThresholds) -> int:
    return math.ceil(round(th.sectors_frac * reading.sectors_total, 9))


def _depth_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    return (reading.sectors_total >= 1
            and reading.sectors_down >= _sectors_needed(reading, th)
            and _meets(reading.breadth_frac, th.breadth_enter - relief))


def _fast_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    return (_meets(reading.breadth_frac, th.breadth_fast - relief)
            and _meets(reading.breadth_speed, th.speed_enter))


def entry_condition(reading: ShockReading, th: ShockThresholds = ShockThresholds()) -> bool:
    """NORMAL -> SHOCK on this one reading (breadth+depth or breadth+speed)."""
    relief = _relief(reading, th)
    return _depth_path(reading, th, relief) or _fast_path(reading, th, relief)


def _enter_shock(state: ShockState, reading: ShockReading) -> ShockState:
    return replace(state, label=SHOCK, since=reading.as_of, entry_streak=0, hold_since=None)


def _from_normal(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    if not (_settled(reading, th) and entry_condition(reading, th)):
        return replace(state, entry_streak=0)
    if state.entry_streak + 1 >= 2:
        return _enter_shock(state, reading)
    return replace(state, entry_streak=state.entry_streak + 1)


def _hold(state: ShockState, reading: ShockReading, th: ShockThresholds) -> ShockState:
    return state


RULES: dict[str, Rule] = {NORMAL: _from_normal, SHOCK: _hold, RECOVERY: _hold}


def _carried_prev_close(state: ShockState, reading: ShockReading, new_session: bool):
    if reading.spy_prev_close is not None:
        return reading.spy_prev_close
    return None if new_session else state.spy_prev_close


def _carry(state: ShockState, reading: ShockReading) -> ShockState:
    """Overnight carry: the reading's session fields; per-session clocks restart."""
    new_session = state.session_date != reading.session_date
    return replace(
        state,
        session_date=reading.session_date,
        vix_session_high=reading.vix_session_high,
        spy_prev_close=_carried_prev_close(state, reading, new_session),
        prev_breadth=None if new_session else state.prev_breadth,
        hold_since=None if new_session else state.hold_since,
    )


def step(state: ShockState, reading: ShockReading,
         th: ShockThresholds = ShockThresholds()) -> ShockState:
    """Advance the state by one reading; an insufficient reading holds it."""
    if reading.insufficient:
        return state
    stepped = RULES[state.label](_carry(state, reading), reading, th)
    return replace(stepped, prev_breadth=reading.breadth_frac)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: PASS (the purity test still allows `typing`).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/shock.py tests/market/test_shock_step_entry.py
git commit -m "feat(v209): shock.step -- ShockState and NORMAL -> SHOCK entry rules"
```

