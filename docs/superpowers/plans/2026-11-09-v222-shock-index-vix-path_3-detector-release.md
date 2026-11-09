# v222 — Market-shock detector: index + VIX entry path — Part 3: detector, production check, Stage 3 and release (V222-9..V222-14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Architecture, **Global Constraints** (the `0.0` off sentinel, no stored field, config pins, the three human gates) and the task ledger live there; every task below implicitly includes them.

## Parallelisation

See the index. **No task in this part starts before gate 2 passed** (Stage 1 and Stage 2
results in the spec's `## Results`, frozen cell confirmed by the partner). Inside this part:
V222-9 → V222-10 → V222-11 is sequential (V222-10's `THRESHOLD_ATTRS` set-equality test
needs V222-9's fields; V222-11 drives `run_shock_pass` through `thresholds_from_config`).
V222-12 touches disjoint files and may run beside V222-9..V222-11. V222-13 needs
V222-9..V222-11 merged on the v209 branch and V222-6d's rebuilt 2026-11-05 fixture (real
one-minute VIX bars, Part 2a); V222-14 runs only on a Stage 3 PASS and edits
the files V222-9/V222-10 edited.

Conventions for every task in this part (same as Parts 1 and 2):

- `W` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector`
  (code, tests, commits on branch `2026-11-05-v209-market-shock-detector`).
- `M` = `E:/Documents/Private/Projects/Discord-Bot` (main tree: the spec's `## Results`).
- Never `cd`; run tests by the absolute path of `W`'s runner, e.g.
  `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`.
- Commit messages are one subject line (the partner's rule: no body, no trailer).
- After each task: `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows
  nothing from the task except the spec's `## Results` edits.
- **`tests/market/test_shock_replay_2026_11_05.py` stays untracked until V222-14 and
  unedited apart from V222-6d's one provenance line** (`vix_interpolated is False`,
  `vix_source == "yfinance_1m"`), and nothing before V222-13 opens 2026-11-05's outcome.

# Phase 3 — Detector, production check, Stage 3 and release

### Task V222-9: `ShockThresholds` index fields, `_index_path`, `entry_condition`

**Model:** sonnet — one pure function and two dataclass fields in one module, every value pinned by the spec.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/swingbot/core/market/shock.py` (`ShockThresholds` `:32-49`, `_fast_path`/`entry_condition` `:312-320`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_step_entry.py`

**Interfaces:**
- Consumes (exist on the v209 branch): `ShockReading.spy_atr_move: float | None`, `ShockReading.vix_chg_pct: float | None` (already `None` when the VIX tape is missing, stale or a proxy: `shock_scan.read_vix` and `shock._fresh_vix`), `shock._meets(value, bar)` (`value + _EPS >= bar`, `None` never meets), `shock.step`, `shock._from_normal` (settle + two-consecutive-reading rule, unchanged).
- Produces (for V222-10, V222-11, V222-13, V222-14):
  - `ShockThresholds.index_atr_k: float = 0.0` and `ShockThresholds.index_vix_chg: float = 0.0`, appended **after** `quote_max_age_s` (so every existing construction, `test_shock_measure.py:38`'s explicit 17-argument one included, still equals `ShockThresholds()`).
  - `shock._index_path(reading: ShockReading, th: ShockThresholds) -> bool`.
  - `entry_condition(reading, th)` returns `_depth_path or _fast_path or _index_path`.

Rules (spec § What changes, index Global Constraints): off when `th.index_atr_k <= 0` (an
explicit guard: without it `-0.0 >= 0.0` and `0.0 >= 0.0` would fire on every calm
reading); otherwise true when `-spy_atr_move >= index_atr_k` **and**
`vix_chg_pct >= index_vix_chg`, each with `_meets`' `1e-9` tolerance; a `None` on either side
is false. VIX relief lowers only the breadth bars, never the index bars. No new
`ShockReading`/`ShockState` field, no new import in `shock.py`.

- [ ] **Step 1: Write the failing tests**

In `W/tests/market/test_shock_step_entry.py`: add `from dataclasses import fields` to the
imports; change the last row of `test_entry_condition_paths` (its comment is no longer true
once the path exists) to

```python
    (dict(breadth_frac=0.05, spy_atr_move=-4.0, qqq_atr_move=-4.0), False),  # calm VIX: no index fire
```

(the reading's `vix_chg_pct` is `0.0`, so the row stays False whatever cell is the default),
then append:

```python
TH_OFF = ShockThresholds(index_atr_k=0.0, index_vix_chg=0.0)
INDEX_ON = ShockThresholds(index_atr_k=1.5, index_vix_chg=20.0)
INDEX = dict(spy_atr_move=-1.5, vix_chg_pct=20.0)


def _run_th(th, state, *readings):
    for reading in readings:
        state = step(state, reading, th)
    return state


def test_index_fields_are_appended_after_the_v209_fields():
    names = [f.name for f in fields(ShockThresholds)]
    assert names[-3:] == ["quote_max_age_s", "index_atr_k", "index_vix_chg"]
    assert len(names) == 19


def test_index_fields_default_to_off():
    th = ShockThresholds()
    assert (th.index_atr_k, th.index_vix_chg) == (0.0, 0.0)
    assert type(th.index_atr_k) is float and type(th.index_vix_chg) is float


@pytest.mark.parametrize("over, expected", [
    (INDEX, True),                                                  # exactly at both bars
    (dict(spy_atr_move=-1.5 + 1e-10, vix_chg_pct=20.0 - 1e-10), True),   # inside _EPS
    (dict(spy_atr_move=-1.49, vix_chg_pct=20.0), False),
    (dict(spy_atr_move=-1.5, vix_chg_pct=19.9), False),
    (dict(spy_atr_move=-3.0, vix_chg_pct=50.0), True),
    (dict(spy_atr_move=2.0, vix_chg_pct=50.0), False),              # SPY up
    (dict(spy_atr_move=None, vix_chg_pct=50.0), False),             # no SPY quote or ATR
    (dict(spy_atr_move=-3.0, vix_chg_pct=None), False),             # missing, stale or proxy VIX
    (dict(spy_atr_move=None, vix_chg_pct=None), False),
])
def test_index_path_meets_both_bars_or_nothing(over, expected):
    reading = _reading(**over)                                      # breadth 0.05: other paths off
    assert shock._index_path(reading, INDEX_ON) is expected
    assert entry_condition(reading, INDEX_ON) is expected


@pytest.mark.parametrize("th", [
    TH_OFF,
    ShockThresholds(index_atr_k=0.0, index_vix_chg=20.0),
    ShockThresholds(index_atr_k=-1.0, index_vix_chg=0.0),
], ids=["zero", "zero-k-only", "negative"])
@pytest.mark.parametrize("over", [
    dict(spy_atr_move=0.0, vix_chg_pct=0.0),                         # calm: the -0.0 >= 0.0 trap
    dict(spy_atr_move=-9.0, vix_chg_pct=99.0),                       # a crash still never fires
], ids=["calm", "crash"])
def test_a_zero_or_negative_index_atr_k_is_off(th, over):
    assert shock._index_path(_reading(**over), th) is False
    assert entry_condition(_reading(**over), th) is False


def test_vix_relief_never_lowers_the_index_bars():
    reading = _reading(spy_atr_move=-1.45, vix_chg_pct=40.0)          # VIX spike, SPY short of 1.5
    assert entry_condition(reading, INDEX_ON) is False


@pytest.mark.parametrize("over", [
    DEPTH, FAST, dict(breadth_frac=0.39, sectors_down=5, sectors_total=5),
    dict(breadth_frac=0.25, breadth_speed=0.09)])
def test_the_other_paths_are_unchanged_with_the_index_path_on(over):
    reading = _reading(**over)                                      # spy 0.0, vix 0.0: no index fire
    assert entry_condition(reading, INDEX_ON) is entry_condition(reading, TH_OFF)


def test_the_index_path_needs_two_consecutive_settled_readings():
    first = _run_th(INDEX_ON, ShockState(), _reading(0, **INDEX))
    assert first.label == "NORMAL" and first.entry_streak == 1
    second = _run_th(INDEX_ON, first, _reading(15, **INDEX))
    assert second.label == "SHOCK" and second.since == T0 + timedelta(minutes=15)


def test_an_index_reading_inside_the_open_settle_window_never_counts():
    gap = _reading(0, **dict(INDEX, minutes_since_open=14.9))         # a gap at the open
    state = _run_th(INDEX_ON, ShockState(), gap)
    assert state.label == "NORMAL" and state.entry_streak == 0
    state = _run_th(INDEX_ON, state, _reading(15, **dict(INDEX, minutes_since_open=15.0)))
    assert state.label == "NORMAL" and state.entry_streak == 1
    state = _run_th(INDEX_ON, state, _reading(30, **dict(INDEX, minutes_since_open=30.0)))
    assert state.label == "SHOCK"


def test_a_calm_reading_between_index_readings_resets_the_streak():
    state = _run_th(INDEX_ON, ShockState(), _reading(0, **INDEX), _reading(15),
                    _reading(30, **INDEX))
    assert state.label == "NORMAL" and state.entry_streak == 1


def test_an_index_reading_then_a_depth_reading_are_consecutive():
    state = _run_th(INDEX_ON, ShockState(), _reading(0, **INDEX), _reading(15, **DEPTH))
    assert state.label == "SHOCK"


def test_off_steps_exactly_as_before_over_an_index_sequence():
    seq = [_reading(i * 15, **INDEX) for i in range(4)]
    off = _run_th(TH_OFF, ShockState(), *seq)
    assert off.label == "NORMAL" and off.entry_streak == 0
    assert off == _run_th(ShockThresholds(index_atr_k=0.0, index_vix_chg=99.0), ShockState(), *seq)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`
Expected: FAIL at collection — `TypeError: ... unexpected keyword argument 'index_atr_k'` from the module-level `TH_OFF`.

- [ ] **Step 3: Implement in `W/swingbot/core/market/shock.py`**

Append the two fields to `ShockThresholds`, after `quote_max_age_s: int = 300`:

```python
    index_atr_k: float = 0.0      # v222: off while <= 0 (a float sentinel, never None)
    index_vix_chg: float = 0.0
```

Add `_index_path` after `_fast_path` and widen `entry_condition` (the guard is the
load-bearing line):

```python
def _index_path(reading: ShockReading, th: ShockThresholds) -> bool:
    """v222: SPY down at least index_atr_k ATR from the prior close and VIX up at
    least index_vix_chg % on this reading. Off while index_atr_k <= 0; a missing
    SPY move or VIX change (no quote, no ATR, stale or proxy tape) never meets."""
    if th.index_atr_k <= 0:
        return False
    move = reading.spy_atr_move
    return (move is not None and _meets(-move, th.index_atr_k)
            and _meets(reading.vix_chg_pct, th.index_vix_chg))


def entry_condition(reading: ShockReading, th: ShockThresholds = ShockThresholds()) -> bool:
    """NORMAL -> SHOCK on this one reading (breadth+depth, breadth+speed, or index+VIX)."""
    relief = _relief(reading, th)
    return (_depth_path(reading, th, relief) or _fast_path(reading, th, relief)
            or _index_path(reading, th))
```

- [ ] **Step 4: Run the detector tests**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_step_entry.py`
Expected: PASS, `0 failed`.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_measure.py`
Expected: PASS (the explicit 17-argument `ShockThresholds(...)` still equals the default; the ast walk finds no config/I/O import).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_scan.py`
Expected: exactly one failure, `test_thresholds_map_every_field_and_keep_ints_int` (the new fields have no `THRESHOLD_ATTRS` row yet). V222-10 fixes it next; never push between V222-9 and V222-10.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/complexity_gate.py`
Expected: no new violation.

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add swingbot/core/market/shock.py tests/market/test_shock_step_entry.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): shock index+VIX entry path, off at index_atr_k 0.0 (V222-9)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-10: Config keys, `THRESHOLD_ATTRS` rows, `.env.example`, config pins

**Model:** sonnet — two config `Field`s, two map rows and their pins; fully specified, but three test files assert order and counts.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/swingbot/config.py` (Market Shock block, after `SHOCK_VIX_RELIEF` `:1606-1609`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/swingbot/core/scanning/shock_scan.py` (`THRESHOLD_ATTRS` `:37-49`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/.env.example` (after `SHOCK_VIX_RELIEF=0.05`, `:857`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scanning/test_shock_scan.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/test_config_v209_keys.py`

**Interfaces:**
- Consumes: V222-9's `ShockThresholds.index_atr_k` / `.index_vix_chg` (`float`, default `0.0`); `shock_scan.thresholds_from_config()` (casts each attr with `type(default)(getattr(config, attr, default))`, unchanged); `config.Field`, `config._cast`, `config._apply_env`, `config.searchable_attrs`.
- Produces (for V222-11, V222-14):
  - config `SHOCK_INDEX_ATR_K` — `type="float"`, `default="0.0"`, `min=0`, `max=5.0`, `step=0.25`, section `"Market Shock"`.
  - config `SHOCK_INDEX_VIX_CHG` — `type="float"`, `default="0.0"`, `min=0`, `max=200`, `step=1`, section `"Market Shock"`.
  - Both placed directly after `SHOCK_VIX_RELIEF` and before `SHOCK_BREADTH_REENTER` in `FIELDS` (and in `V209_FIELDS`, whose dict order must equal the FIELDS order); both hot-reloadable, not sensitive, `search_class == "excluded"` through the `Field` dataclass defaults (`config.py:88-92`; copy the `Field(...)` shape of `SHOCK_VIX_SPIKE_PCT`, `:1601-1605`, and never add the keys to `_SEARCH_CLASSES`); help strings contain `v209` **and** `v222`.
  - `THRESHOLD_ATTRS["index_atr_k"] = "SHOCK_INDEX_ATR_K"`, `THRESHOLD_ATTRS["index_vix_chg"] = "SHOCK_INDEX_VIX_CHG"` (17 → 19 rows).

`min=0` (unlike `SHOCK_ATR_K`'s `min=0.25`) so the off value `0.0` is a valid stored value.
`_cast` treats both as plain floats (neither joins `_POSITIVE_FLOATS`).

- [ ] **Step 1: Write the failing tests**

`W/tests/scanning/test_shock_scan.py`: in `test_thresholds_map_every_field_and_keep_ints_int`
change `== 17` to `== 19`, then append after that test:

```python
def test_index_thresholds_come_from_config_as_floats(monkeypatch):
    assert shock_scan.THRESHOLD_ATTRS["index_atr_k"] == "SHOCK_INDEX_ATR_K"
    assert shock_scan.THRESHOLD_ATTRS["index_vix_chg"] == "SHOCK_INDEX_VIX_CHG"
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", 1.5)
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", 20)            # an int still lands a float
    th = shock_scan.thresholds_from_config()
    assert (th.index_atr_k, th.index_vix_chg) == (1.5, 20.0)
    assert type(th.index_atr_k) is float and type(th.index_vix_chg) is float


def test_the_config_default_matches_the_detector_default():
    th = shock_scan.thresholds_from_config()
    default = shock.ShockThresholds()
    assert (th.index_atr_k, th.index_vix_chg) == (default.index_atr_k, default.index_vix_chg)
```

`W/tests/test_config_v209_keys.py`:

1. In `V209_FIELDS`, directly after the `"SHOCK_VIX_RELIEF"` row, insert:

```python
    "SHOCK_INDEX_ATR_K": ("float", "0.0"),
    "SHOCK_INDEX_VIX_CHG": ("float", "0.0"),
```

2. In `CAST_DEFAULTS`, after `"SHOCK_VIX_RELIEF": 0.05,` insert
   `"SHOCK_INDEX_ATR_K": 0.0, "SHOCK_INDEX_VIX_CHG": 0.0,`.

3. Replace `test_nineteen_fields_one_mode_plus_eighteen_thresholds` with:

```python
def test_twenty_one_fields_one_mode_plus_twenty_thresholds():
    assert len(V209_FIELDS) == 21
    assert set(V209_FIELDS) == set(CAST_DEFAULTS)
```

4. Append:

```python
INDEX_KEYS = ("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG")


@pytest.mark.parametrize("attr", INDEX_KEYS)
def test_index_keys_name_v222_and_accept_zero_as_off(attr):
    field = _field(attr)
    assert "v222" in field.help and "v209" in field.help
    assert field.min == 0
    assert config._cast(field, "0.0") == 0.0 and config._cast(field, "0") == 0.0


def test_index_key_bounds_and_steps():
    k, v = _field("SHOCK_INDEX_ATR_K"), _field("SHOCK_INDEX_VIX_CHG")
    assert (k.min, k.max, k.step) == (0, 5.0, 0.25)
    assert (v.min, v.max, v.step) == (0, 200, 1)


def test_index_keys_sit_right_after_the_vix_relief_knob():
    attrs = [f.attr for f in config.FIELDS]
    at = attrs.index("SHOCK_VIX_RELIEF")
    assert attrs[at + 1:at + 4] == ["SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG",
                                    "SHOCK_BREADTH_REENTER"]
```

The existing parametrized tests (`test_field_is_a_hot_reloadable_excluded_market_shock_knob`,
`test_fields_sit_together_between_chart_patterns_and_database`,
`test_default_casts_to_the_documented_value`, `test_numeric_fields_carry_bounds_...`,
`test_module_attrs_hold_the_cast_defaults_on_a_clean_env`,
`test_env_example_lists_the_key_with_its_default`) pick the two keys up through the dict.

- [ ] **Step 2: Run them to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/test_config_v209_keys.py`
Expected: FAIL — `StopIteration` in `_field("SHOCK_INDEX_ATR_K")`, and the block-order test.

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_scan.py`
Expected: FAIL — `KeyError: 'index_atr_k'` and the set-equality/count assertion.

- [ ] **Step 3: Implement**

`W/swingbot/config.py`, directly after the `SHOCK_VIX_RELIEF` `Field(...)`:

```python
    Field("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_ATR_K", "Market Shock",
          "SPY down-move for the index path, in ATR14 (0 = off)",
          type="float", default="0.0", min=0, max=5.0, step=0.25,
          help="v209 detector, v222 index path. NORMAL -> SHOCK also when SPY is down at "
               "least this many ATR14 from the prior close and ^VIX is up at least "
               "SHOCK_INDEX_VIX_CHG on the same reading (settle and two-reading rules "
               "still apply). 0 turns the path off."),
    Field("SHOCK_INDEX_VIX_CHG", "SHOCK_INDEX_VIX_CHG", "Market Shock",
          "VIX day change for the index path (%)",
          type="float", default="0.0", min=0, max=200, step=1,
          help="v209 detector, v222 index path. The ^VIX day change the index path needs "
               "beside SHOCK_INDEX_ATR_K. A missing, stale or proxy ^VIX never meets it."),
```

`W/swingbot/core/scanning/shock_scan.py`, last two rows of `THRESHOLD_ATTRS`:

```python
    "quote_max_age_s": "SHOCK_QUOTE_MAX_AGE_S",
    "index_atr_k": "SHOCK_INDEX_ATR_K", "index_vix_chg": "SHOCK_INDEX_VIX_CHG",
}
```

`W/.env.example`, after the `SHOCK_VIX_RELIEF=0.05` line (keep the blank line before the
`# RECOVERY -> SHOCK` comment):

```
# v222 index path: SPY down SHOCK_INDEX_ATR_K ATR14 and ^VIX up SHOCK_INDEX_VIX_CHG %
# on the same reading. 0.0 turns the path off.
SHOCK_INDEX_ATR_K=0.0
SHOCK_INDEX_VIX_CHG=0.0
```

(a blank line between `SHOCK_VIX_RELIEF=0.05` and the new comment).

- [ ] **Step 4: Run the tests**

Run each, expected PASS with `0 failed`:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/test_config_v209_keys.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_scan.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_pass.py
```

`test_shock_pass.py` confirms the default (`0.0`) leaves every v209 pass test unchanged.

- [ ] **Step 5: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add swingbot/config.py swingbot/core/scanning/shock_scan.py .env.example tests/scanning/test_shock_scan.py tests/test_config_v209_keys.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): SHOCK_INDEX_ATR_K and SHOCK_INDEX_VIX_CHG config keys, off by default (V222-10)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-11: Pipeline tests: partial data, stale/proxy VIX, off is byte-identical

**Model:** sonnet — tests only, through existing seams (`run_shock_pass`, `_shock_state_for_pass`); no production code changes.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scanning/test_shock_index_path.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scanning/test_shock_plans_byte_identical.py`

**Interfaces:**
- Consumes: V222-9 `shock._index_path`, `entry_condition`; V222-10 config `SHOCK_INDEX_ATR_K` / `SHOCK_INDEX_VIX_CHG` and their `THRESHOLD_ATTRS` rows; existing v209 seams `shock_scan.run_shock_pass(*, step_shock, frames, live_prices, sector_of, quotes_at, spy_df=None, now=None, repo=None)`, `shock_scan.read_vix` (empty for missing, stale > `vix_max_age_s`, proxy), `scan_run._shock_state_for_pass(**kwargs)`, `TapeEntry(symbol, price, change_pct, is_proxy, proxy_symbol, as_of)`; in the pins file: `long_env`, `_attach_on_rebuild`, `_confluence(state)`, `_requote(state)`, `_canon`, `FRAME`, `NOW`.
- Produces: none (tests only). Every test here sets the index cell explicitly, so V222-14's default change leaves them valid.

Fixture arithmetic (same as `test_shock_pass.py`): a 30-bar frame with `High − Low = 2`
and a constant close has ATR14 `2.0` (Wilder EWM of a constant); the bar dated today is
dropped as incomplete, so SPY's prior close is `500.0` and a `496.0` quote is `−2.0` ATR.
Names quoted at their prior close (`100.0`) give breadth `0.0`, so depth and fast are off
and only the index path can fire.

- [ ] **Step 1: Write the tests**

`W/tests/scanning/test_shock_index_path.py`:

```python
"""v222: the index + VIX path through run_shock_pass -- fires on SPY and VIX together,
never on partial data, and changes nothing while index_atr_k is 0.0."""
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.marketdata.shared.tape import TapeEntry
from swingbot.core.scanning import fetch, shock_scan

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, settled
SECTORS = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech"}
FLAT = {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0}       # breadth 0.0
INDEX_DAY = {**FLAT, "SPY": 496.0}                      # SPY -2.0 ATR, names flat
CRASH = {"AAA": 94.0, "BBB": 94.0, "CCC": 94.0, "SPY": 490.0}
NO_SPY = dict(FLAT)
OFF, ON = (0.0, 0.0), (1.5, 20.0)


def _frame(close=100.0, n=30):
    idx = pd.bdate_range(end=pd.Timestamp(D0), periods=n)
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": 1e6}, index=idx)


def _frames(spy_bars=30):
    return {t: _frame() for t in SECTORS} | {"SPY": _frame(close=500.0, n=spy_bars)}


class _Repo:
    def __init__(self):
        self.state, self.latest, self.recorded = None, None, []

    def current_state(self, *, conn=None):
        return self.state

    def latest_reading(self, *, conn=None):
        return self.latest

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.recorded.append((reading, state, state_after))
        self.latest = {**reading, "id": len(self.recorded), "state_after": state_after}
        self.state = {"label": state_after, "doc": {"state": state}}
        return len(self.recorded)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 2)
    monkeypatch.setattr(shock_scan.asset_class, "classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))
    _cell(monkeypatch, OFF)


def _cell(monkeypatch, cell):
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", cell[0])
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", cell[1])


def _tape(monkeypatch, now, vix):
    """vix: None = no ^VIX row; else dict(chg=, age_s=, proxy=)."""
    if vix is None:
        monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})
        return
    proxy = vix.get("proxy", False)
    entry = TapeEntry("^VIX", None if proxy else 21.0, vix.get("chg", 25.0), proxy,
                      "VIXY" if proxy else None, now - timedelta(seconds=vix.get("age_s", 60)))
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {"^VIX": entry})


def _passes(monkeypatch, quotes, *, vix=None, frames=None, n=2):
    repo, labels = _Repo(), []
    for i in range(n):
        now = NOW + timedelta(minutes=15 * i)
        _tape(monkeypatch, now, vix)
        labels.append(shock_scan.run_shock_pass(
            step_shock=True, frames=frames or _frames(), live_prices=quotes,
            sector_of=SECTORS, quotes_at=now, now=now, repo=repo))
    return labels, repo


def test_spy_and_vix_on_two_settled_readings_enter_shock(monkeypatch):
    _cell(monkeypatch, ON)
    labels, repo = _passes(monkeypatch, INDEX_DAY, vix={"chg": 25.0})
    assert labels == ["NORMAL", "SHOCK"]
    reading = repo.recorded[0][0]
    assert reading["breadth_frac"] == pytest.approx(0.0)
    assert reading["spy_atr_move"] == pytest.approx(-2.0) and reading["vix_chg_pct"] == 25.0


def test_the_same_day_stays_normal_while_the_path_is_off(monkeypatch):
    labels, _ = _passes(monkeypatch, INDEX_DAY, vix={"chg": 25.0}, n=3)
    assert labels == ["NORMAL", "NORMAL", "NORMAL"]


@pytest.mark.parametrize("quotes, vix, frames, missing", [
    (NO_SPY, {"chg": 25.0}, None, "spy_atr_move"),              # no SPY quote
    (INDEX_DAY, {"chg": 25.0}, _frames(spy_bars=10), "spy_atr_move"),   # < 15 bars: no ATR14
    (INDEX_DAY, None, None, "vix_chg_pct"),                     # no ^VIX row
    (INDEX_DAY, {"chg": 25.0, "age_s": 601}, None, "vix_chg_pct"),   # stale past 600 s
    (INDEX_DAY, {"chg": 25.0, "proxy": True}, None, "vix_chg_pct"),  # VIXY proxy row
], ids=["no-spy-quote", "no-spy-atr", "no-vix", "stale-vix", "proxy-vix"])
def test_partial_data_never_fires_the_index_path(monkeypatch, quotes, vix, frames, missing):
    _cell(monkeypatch, ON)
    labels, repo = _passes(monkeypatch, quotes, vix=vix, frames=frames, n=3)
    assert labels == ["NORMAL", "NORMAL", "NORMAL"]
    assert all(r[0][missing] is None for r in repo.recorded)
    assert all(r[0]["insufficient"] is False for r in repo.recorded)


@pytest.mark.parametrize("chg, labels", [(19.9, ["NORMAL", "NORMAL"]),
                                          (20.0, ["NORMAL", "SHOCK"])])
def test_the_vix_bar_is_inclusive(monkeypatch, chg, labels):
    _cell(monkeypatch, ON)
    assert _passes(monkeypatch, INDEX_DAY, vix={"chg": chg})[0] == labels


def _pre_v222_entry(reading, th=shock.ShockThresholds()):
    relief = shock._relief(reading, th)
    return shock._depth_path(reading, th, relief) or shock._fast_path(reading, th, relief)


SCENARIOS = {"flat": (FLAT, {"chg": 25.0}), "index_day": (INDEX_DAY, {"chg": 25.0}),
             "crash": (CRASH, {"chg": 30.0}), "crash_no_vix": (CRASH, None),
             "no_spy": (NO_SPY, {"chg": 25.0})}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_off_records_exactly_what_pre_v222_recorded(monkeypatch, name):
    quotes, vix = SCENARIOS[name]
    labels_off, off = _passes(monkeypatch, quotes, vix=vix, n=3)
    with monkeypatch.context() as m:
        m.setattr(shock, "entry_condition", _pre_v222_entry)
        labels_old, old = _passes(m, quotes, vix=vix, n=3)
    assert labels_off == labels_old
    assert off.recorded == old.recorded


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_turning_the_path_on_changes_no_reading(monkeypatch, name):
    quotes, vix = SCENARIOS[name]
    labels_off, off = _passes(monkeypatch, quotes, vix=vix, n=3)
    _cell(monkeypatch, ON)
    labels_on, on = _passes(monkeypatch, quotes, vix=vix, n=3)
    assert [r[0] for r in on.recorded] == [r[0] for r in off.recorded]
    if name != "index_day":                                     # only the index day moves a label
        assert labels_on == labels_off
```

`W/tests/scanning/test_shock_plans_byte_identical.py`: add `from datetime import timedelta`
(extend the existing `from datetime import datetime, timezone`), `import pandas as pd` and
`from swingbot.core.marketdata.shared.tape import TapeEntry`; extend the module docstring with
one sentence: "v222: the index path changes a long plan only through its shock_state
label."; then append:

```python
class _MemStore:
    def __init__(self):
        self.state, self.latest = None, None

    def current_state(self, *, conn=None):
        return self.state

    def latest_reading(self, *, conn=None):
        return self.latest

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.latest = {**reading, "id": 1, "state_after": state_after}
        self.state = {"label": state_after, "doc": {"state": state}}
        return 1


def _spy_frame():
    idx = pd.bdate_range(end=pd.Timestamp(NOW.date()), periods=30)
    return pd.DataFrame({"Open": 500.0, "High": 501.0, "Low": 499.0, "Close": 500.0,
                         "Volume": 1e6}, index=idx)


def _index_label(monkeypatch, cell):
    """Two stepped passes on an index-only day (AAPL flat, SPY -2 ATR, VIX +25 %)."""
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 1)
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", cell[0])
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", cell[1])
    monkeypatch.setattr(shock_scan.asset_class, "classify",
                        lambda t: "etf" if t == "SPY" else "equity")
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))
    store, label = _MemStore(), None
    flat = float(FRAME["Close"].iloc[-1])
    for i in (0, 1):
        now = NOW + timedelta(minutes=15 * i)
        entry = TapeEntry("^VIX", 21.0, 25.0, False, None, now)
        monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols, e=entry: {"^VIX": e})
        label = scan_run._shock_state_for_pass(
            step_shock=True, frames={"AAPL": FRAME, "SPY": _spy_frame()},
            live_prices={"AAPL": flat, "SPY": 496.0},
            sector_of={"AAPL": "Information Technology"}, quotes_at=now, spy_df=None,
            now=now, repo=store)
    return label


@pytest.mark.parametrize("cell,label", [((0.0, 0.0), "NORMAL"), ((1.5, 20.0), "SHOCK")],
                         ids=["off", "on"])
@pytest.mark.parametrize("lane", ["confluence", "requote"])
def test_the_index_path_changes_a_long_plan_only_through_its_label(long_env, monkeypatch,
                                                                   cell, label, lane):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")
    build = {"confluence": _confluence, "requote": _requote}[lane]
    with monkeypatch.context() as m:
        got = _index_label(m, cell)
    assert got == label
    plan, unlabelled = build(got), build(None)
    assert plan.entry_context.pop("shock_state") == label
    assert _canon(plan) == _canon(unlabelled)
```

- [ ] **Step 2: Run them**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_index_path.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_plans_byte_identical.py
```

Expected: PASS, `0 failed`. These pin behaviour V222-9/V222-10 already implement, so they pass
first time. Prove they bite: temporarily delete the `if th.index_atr_k <= 0: return False`
guard in `shock._index_path`, rerun `test_shock_index_path.py`, see
`test_off_records_exactly_what_pre_v222_recorded[index_day]` fail, restore the guard
(`git -C W diff --stat swingbot/core/market/shock.py` shows nothing afterwards).

If `test_partial_data_never_fires_the_index_path[no-spy-atr]` fails because the reading is
`insufficient` (SPY is not a name, so it should not be): stop and report; never loosen the
assertion.

- [ ] **Step 3: Commit (v209 branch)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add tests/scanning/test_shock_index_path.py tests/scanning/test_shock_plans_byte_identical.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "test(v222): index path pipeline pins -- partial data, stale/proxy VIX, off byte-identical (V222-11)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task.

### Task V222-12: Production `^VIX` tape check and VIX-coverage query (read-only)

**Model:** sonnet — one standalone read-only script with pure helpers and a fake connection; the production run is read-only through the standing permission.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/reports/shock_vix_check.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/scripts/test_shock_vix_check.py`
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (main tree, `## Results`: new `### Production VIX`)

**Interfaces:**
- Consumes (exist on `main` and so in production): `swingbot.core.marketdata.shared.tape.read_tape(symbols) -> dict[str, TapeEntry]` (latest stored row, any age, never fetches; a proxy row has `is_proxy=True`, `price=None`); `swingbot.core.market.session.is_nyse_regular_session(now)`; `swingbot.core.db.engine.get_engine()`; v209's table `market_shock_readings` (columns `session_date`, `vix_chg_pct`, `insufficient`) — **absent in production until V209-13 deploys**, so the query is guarded by `to_regclass`.
- Produces: `shock_vix_check.tape_status(entry, now: datetime, max_age_s: int = 600) -> dict` (keys `present, is_proxy, proxy_symbol, price, change_pct, as_of, age_s, fresh, usable`); `COVERAGE_SQL` (per `session_date`: `readings`, `vix_missing`, `insufficient`); `coverage(conn) -> list[dict] | None` (`None` when the table does not exist); Results § Production VIX.

`usable` restates `shock_scan.read_vix`'s rule exactly (present, not a proxy, finite price,
an `as_of`, age `<= max_age_s`), because production runs `main` and has no `shock_scan.py`;
the script imports only modules production already runs, and only inside functions
(`shock_longbook_dump.py` precedent, V222-4). The spec's acceptance line: "a non-proxy `^VIX`
tape row exists during market hours … if production only has the proxy, the path can never
fire and the spec says so."

- [ ] **Step 1: Write the failing tests**

`W/tests/scripts/test_shock_vix_check.py`:

```python
"""v222 V222-12: the read-only production ^VIX tape check."""
import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reports" / "shock_vix_check.py"
sys.path.insert(0, str(SCRIPT.parent))
import shock_vix_check as chk  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)


def _entry(price=21.13, chg=27.21, proxy=False, age_s=60, as_of=...):
    stamp = NOW - timedelta(seconds=age_s) if as_of is ... else as_of
    return SimpleNamespace(symbol="^VIX", price=price, change_pct=chg, is_proxy=proxy,
                           proxy_symbol="VIXY" if proxy else None, as_of=stamp)


def test_no_row_is_absent_and_unusable():
    status = chk.tape_status(None, NOW)
    assert status["present"] is False and status["usable"] is False
    assert status["age_s"] is None and status["as_of"] is None


def test_a_fresh_real_row_is_usable():
    status = chk.tape_status(_entry(), NOW)
    assert (status["present"], status["is_proxy"], status["fresh"], status["usable"]) == (
        True, False, True, True)
    assert status["age_s"] == 60.0 and status["price"] == 21.13 and status["change_pct"] == 27.21
    assert status["as_of"] == (NOW - timedelta(seconds=60)).isoformat()


@pytest.mark.parametrize("age_s, fresh", [(600, True), (601, False)])
def test_the_age_gate_is_inclusive_at_six_hundred_seconds(age_s, fresh):
    status = chk.tape_status(_entry(age_s=age_s), NOW)
    assert status["fresh"] is fresh and status["usable"] is fresh


def test_a_proxy_row_is_present_but_never_usable():
    status = chk.tape_status(_entry(price=None, chg=4.2, proxy=True, age_s=30), NOW)
    assert status["present"] is True and status["is_proxy"] is True
    assert status["proxy_symbol"] == "VIXY" and status["fresh"] is True
    assert status["usable"] is False


@pytest.mark.parametrize("entry", [_entry(as_of=None), _entry(price=float("nan")),
                                   _entry(price=None)], ids=["no-time", "nan", "no-price"])
def test_a_row_without_time_or_finite_price_is_unusable(entry):
    assert chk.tape_status(entry, NOW)["usable"] is False


def test_a_naive_stamp_is_read_as_utc():
    naive = (NOW - timedelta(seconds=90)).replace(tzinfo=None)
    assert chk.tape_status(_entry(as_of=naive), NOW)["age_s"] == 90.0


def test_the_coverage_sql_counts_missing_vix_per_session():
    sql = " ".join(chk.COVERAGE_SQL.split())
    assert "FROM market_shock_readings" in sql and "vix_chg_pct IS NULL" in sql
    assert "GROUP BY session_date" in sql and "insufficient" in sql


class _Conn:
    def __init__(self, exists, rows=()):
        self.exists, self.rows, self.sql = exists, list(rows), []

    def execute(self, statement):
        text = str(statement)
        self.sql.append(text)
        if "to_regclass" in text:
            return SimpleNamespace(scalar=lambda: self.exists)
        return iter(self.rows)


def test_coverage_is_none_while_the_table_does_not_exist():
    conn = _Conn(False)
    assert chk.coverage(conn) is None
    assert len(conn.sql) == 1                       # never queries a missing table


def test_coverage_maps_each_session_row():
    row = SimpleNamespace(session_date="2026-11-10", readings=26, vix_missing=3, insufficient=1)
    assert chk.coverage(_Conn(True, [row])) == [
        {"session_date": "2026-11-10", "readings": 26, "vix_missing": 3, "insufficient": 1}]


def test_the_script_imports_nothing_from_swingbot_at_module_level():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = [a.name for n in top for a in n.names] + [n.module or "" for n in top
                                                     if isinstance(n, ast.ImportFrom)]
    assert not any(name.startswith(("swingbot", "sqlalchemy")) for name in names)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_shock_vix_check.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_vix_check'`.

- [ ] **Step 3: Implement `W/scripts/reports/shock_vix_check.py`**

Module docstring: what it checks, that it is read-only, and the exact pipe command from
Step 5. Module level: `from __future__ import annotations`, `json`, `math`,
`datetime`/`timezone` only; constants `VIX_SYMBOL = "^VIX"`, `MAX_AGE_S = 600` (comment:
restates `ShockThresholds.vix_max_age_s`; production has no `shock.py`),

```python
TABLE_SQL = "SELECT to_regclass('public.market_shock_readings') IS NOT NULL"
COVERAGE_SQL = """
SELECT session_date,
       count(*) AS readings,
       count(*) FILTER (WHERE vix_chg_pct IS NULL) AS vix_missing,
       count(*) FILTER (WHERE insufficient) AS insufficient
FROM market_shock_readings
GROUP BY session_date
ORDER BY session_date
"""
```

- `tape_status(entry, now, max_age_s=MAX_AGE_S) -> dict`: `None` → every key `None` except
  `present=False, fresh=False, usable=False`. Otherwise a naive `as_of` is read as UTC;
  `age_s = (now - as_of).total_seconds()` (or `None`); `fresh = age_s is not None and
  age_s <= max_age_s`; `price` is the finite float or `None`; `usable = fresh and not
  is_proxy and price is not None`; `as_of` reported as ISO text. Split into `_finite(v)` and
  `_aware(stamp)` helpers to stay well under complexity 15.
- `coverage(conn) -> list[dict] | None`: `import sqlalchemy as sa` inside; run `TABLE_SQL`
  via `conn.execute(sa.text(...)).scalar()`; falsy → `None` (no second query); else map each
  row of `COVERAGE_SQL` to `{"session_date": str(...), "readings": int, "vix_missing": int,
  "insufficient": int}`.
- `main() -> int`: imports `get_engine`, `is_nyse_regular_session`, `tape` inside; `now =
  datetime.now(timezone.utc)`; prints one JSON line
  `{"checked_at", "in_session", "vix": tape_status(...), "coverage": coverage(conn)}` (the
  connection from `get_engine().connect()` in a `with`); writes nothing; returns 0.
  `if __name__ == "__main__": raise SystemExit(main())` (true under `python -`).

- [ ] **Step 4: Run the tests**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scripts/test_shock_vix_check.py`
Expected: PASS, `0 failed`.

Commit (v209 branch):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/reports/shock_vix_check.py tests/scripts/test_shock_vix_check.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): read-only production ^VIX tape and coverage check (V222-12)"
```

- [ ] **Step 5: Run it on production, twice, inside the NYSE session (read-only)**

Check the clock first (`date -u`; Git Bash has no timezone data, so judge from UTC): the
regular session is Mon–Fri 14:30–21:00 UTC in EST (13:30–20:00 UTC in EDT). Run once early
(before 16:00 UTC in EST) and once at least two hours later, on the same session day:

```bash
bash E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/reports/shock_vix_check.py > E:/Documents/Private/Projects/Discord-Bot/data/v222/vix_check_1.json
```

(second run: `vix_check_2.json`). Expected: one JSON line each, `"in_session": true`;
`"coverage": null` while v209 is not deployed. A run with `in_session` false does not
count: repeat it in session. Never read or print `.env` on the VM; nothing is changed there.

- [ ] **Step 6: Write the Results (main tree spec)**

Add `### Production VIX` under `## Results`: a table, one row per run (`checked_at`,
`in_session`, `present`, `is_proxy`, `proxy_symbol`, `age_s`, `usable`), then exactly one
verdict line:

- both runs `usable: true` → "A non-proxy `^VIX` tape row exists in market hours (age ≤ 600 s); the index path can read VIX."
- any in-session run with `is_proxy: true` or no row → "Production served only the proxy (or no `^VIX` row) at <time>: the index path cannot fire while that holds." Then ask the partner (`AskUserQuestion`, recommended first: "record it and carry on to Stage 3; V209-13's release decides"; alternative: "stop before Stage 3").
- a real row but stale (`fresh: false`) → record the age; same question.

Add: "Coverage of missing or stale VIX on shadow rows: no `market_shock_readings` table in production yet (v209 not deployed); rerun this script after V209-13 for per-session `vix_missing` counts." (or the coverage table, if it exists).

Commit on `main` (controller):

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v222): production ^VIX tape check results"
```

### Task V222-13: Stage 3: replay 2026-11-05 once with the frozen cell, gate 3

**Model:** sonnet — a small replay script that mirrors the existing replay test's helpers, tested on a synthetic fixture, then one recorded run.

**Files:**
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_replay_once.py`
- Create: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/backtest_scripts/test_shock_index_replay_once.py` (the script's own tests, synthetic fixture only; not in the index ledger's file list, no other task depends on it)
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (main tree, `## Results`: new `### Stage 3 — replay of 2026-11-05`)

**Interfaces:**
- Consumes: V222-9 `ShockThresholds(index_atr_k=, index_vix_chg=)`, `shock._depth_path`, `_fast_path`, `_index_path`, `_relief`, `_settled`, `entry_condition`; v209 `shock.measure(snapshot, prev, th)`, `shock.step(state, reading, th)`, `ShockState`, `NameRow`, `VixTape`, `ShockSnapshot`; V222-6d's rebuilt `tests/fixtures/shock_replay_2026_11_05.json` (VIX from real one-minute `^VIX` bars: `vix_interpolated: false`, `vix_source: "yfinance_1m"`); the fixture JSON shape (`source`, `vix_interpolated`, `vix_source`, `note`, `steps[]` with `as_of`, `minutes_since_open`, `vix{level,chg_pct}`, `spy`, `qqq`, `names[]` of `NameRow` dicts); the frozen cell `(FROZEN_K, FROZEN_V)` from the spec's Results § Stage 2 (V222-8).
- Produces (for V222-14): `replay_table(fx: dict, th: ShockThresholds) -> list[dict]` (one row per step: `as_of, minutes_since_open, breadth_frac, breadth_speed, sectors_down, sectors_total, spy_atr_move, vix_chg_pct, insufficient, settled, depth, fast, index, entry, streak, label`); `first_shock(rows) -> str | None`; `verdict(rows, deadline: datetime = DEADLINE) -> str` (`"PASS"` / `"FAIL"`); `DEADLINE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)`; CLI `--fixture --k --v --out-json --out-md` (an interpolated fixture exits `2`); Results § Stage 3 PASS or FAIL.

Rules (spec § Stage 3): the cell is the one frozen at gate 2 and is passed on the command
line, never chosen here; the run happens **once** — the CLI refuses to overwrite an
existing `--out-json` (exit 3), and refuses `--k <= 0` or a fixture whose
`vix_interpolated` is not `false` (exit 2). PASS means the first
`SHOCK` is at or before 15:00 UTC (the earliest the settle and two-reading rules allow on
15-minute steps). A FAIL is a measured answer: no grid, rule or cell is moved, no test is
weakened. The snapshot is built exactly as the untracked
`tests/market/test_shock_replay_2026_11_05.py::_snapshot` does (VIX `as_of` = the step's
`as_of`; `session_date` = the first step's UTC date), so V222-14's unchanged test sees the
same readings. The fixture's VIX comes from real one-minute `^VIX` bars, point-in-time (the
close of the last bar finished by each step; spec § VIX provenance, amended 2026-11-09,
rebuilt by V222-6d), and the Results say so beside the verdict. An interpolated fixture
(the pre-amendment one) is refused, because its 14:45 VIX could never meet any grid value.

- [ ] **Step 1: Write the failing tests**

`W/tests/backtest_scripts/test_shock_index_replay_once.py`:

```python
"""v222 V222-13: the run-once Stage 3 replay script, on a synthetic session only."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import shock_index_replay_once as once  # noqa: E402

from swingbot.core.market.shock import ShockThresholds  # noqa: E402

UTC = timezone.utc
T0 = datetime(2025, 1, 6, 14, 45, tzinfo=UTC)          # a Monday in EST, 15 min after the open
ON = ShockThresholds(min_names=2, index_atr_k=1.5, index_vix_chg=20.0)
OFF = ShockThresholds(min_names=2)


def _name(t, last=100.0):
    return {"ticker": t, "sector": "Tech", "last": last, "prev_close": 100.0, "atr14": 2.0,
            "is_equity": True}


def _step(i, spy_last=496.0, vix_chg=25.0):
    return {"as_of": (T0 + timedelta(minutes=15 * i)).isoformat(),
            "minutes_since_open": 15.0 + 15 * i,
            "vix": {"level": 20.0, "chg_pct": vix_chg},
            "spy": {"ticker": "SPY", "sector": None, "last": spy_last, "prev_close": 500.0,
                    "atr14": 2.0, "is_equity": False},
            "qqq": None, "names": [_name("AAA"), _name("BBB"), _name("CCC")]}


def _fx(*steps):
    return {"source": "synthetic", "vix_interpolated": False, "vix_source": "yfinance_1m",
            "note": "test", "steps": list(steps)}


def test_the_deadline_is_fifteen_hundred_utc_on_the_replay_day():
    assert once.DEADLINE == datetime(2026, 11, 5, 15, 0, tzinfo=UTC)


def test_two_index_readings_enter_shock_at_the_second():
    rows = once.replay_table(_fx(_step(0), _step(1), _step(2)), ON)
    assert [r["label"] for r in rows] == ["NORMAL", "SHOCK", "SHOCK"]
    first = rows[0]
    assert (first["index"], first["depth"], first["fast"], first["entry"]) == (
        True, False, False, True)
    assert first["settled"] is True and first["streak"] == 1
    assert first["spy_atr_move"] == pytest.approx(-2.0) and first["vix_chg_pct"] == 25.0
    assert once.first_shock(rows) == (T0 + timedelta(minutes=15)).isoformat()


@pytest.mark.parametrize("deadline, expected", [
    (T0 + timedelta(minutes=15), "PASS"), (T0 + timedelta(minutes=14), "FAIL")])
def test_the_verdict_is_inclusive_at_the_deadline(deadline, expected):
    rows = once.replay_table(_fx(_step(0), _step(1)), ON)
    assert once.verdict(rows, deadline) == expected


def test_never_shock_is_a_fail():
    rows = once.replay_table(_fx(_step(0), _step(1)), OFF)
    assert [r["label"] for r in rows] == ["NORMAL", "NORMAL"]
    assert once.first_shock(rows) is None and once.verdict(rows, T0 + timedelta(hours=9)) == "FAIL"


def test_a_vix_short_of_the_bar_at_the_first_step_delays_shock():
    rows = once.replay_table(_fx(_step(0, vix_chg=8.0), _step(1), _step(2)), ON)
    assert [r["label"] for r in rows] == ["NORMAL", "NORMAL", "SHOCK"]
    assert rows[0]["index"] is False and rows[0]["streak"] == 0


def _cli(tmp_path, *extra):
    fixture = tmp_path / "fx.json"
    fixture.write_text(json.dumps(_fx(_step(0), _step(1))))
    return fixture, ["--fixture", str(fixture), "--out-json", str(tmp_path / "s3.json"),
                     "--out-md", str(tmp_path / "s3.md"), *extra]


def test_the_cli_writes_the_table_once(tmp_path, capsys):
    _fixture, argv = _cli(tmp_path, "--k", "1.5", "--v", "20")
    assert once.main(argv) == 0
    out = json.loads((tmp_path / "s3.json").read_text())
    assert set(out) == {"cell", "fixture", "source", "vix_interpolated", "vix_source", "rows",
                        "first_shock", "deadline", "verdict"}
    assert (out["vix_interpolated"], out["vix_source"]) == (False, "yfinance_1m")
    assert out["cell"] == [1.5, 20.0] and len(out["rows"]) == 2
    assert "| as_of |" in (tmp_path / "s3.md").read_text()
    assert once.main(argv) == 3                       # run once: never overwrite


def test_the_cli_refuses_an_off_cell(tmp_path):
    _fixture, argv = _cli(tmp_path, "--k", "0", "--v", "20")
    assert once.main(argv) == 2
    assert not (tmp_path / "s3.json").exists()


def test_the_cli_refuses_an_interpolated_fixture(tmp_path):
    fixture, argv = _cli(tmp_path, "--k", "1.5", "--v", "20")
    fixture.write_text(json.dumps({**_fx(_step(0), _step(1)), "vix_interpolated": True}))
    assert once.main(argv) == 2
    assert not (tmp_path / "s3.json").exists()
```

`replay_table` must use `OFF`/`ON`'s `min_names=2` from the passed thresholds (the synthetic
session has 3 names); the real run uses the defaults plus the frozen cell.

- [ ] **Step 2: Run them to see them fail**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_replay_once.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'shock_index_replay_once'`.

- [ ] **Step 3: Implement `W/scripts/backtest/shock_index_replay_once.py`**

Put the repo root on `sys.path` (as the other `scripts/backtest/` CLIs do), then
`from swingbot.core.market import shock`. Constants: `UTC`, `DEADLINE`,
`DEFAULT_FIXTURE = ROOT / "tests/fixtures/shock_replay_2026_11_05.json"`.

- `_snapshot(step: dict, session: date) -> shock.ShockSnapshot` — the replay test's `_snapshot`, with `session` passed in.
- `_paths(reading, th) -> dict` — `relief = shock._relief(reading, th)`; returns `depth`, `fast`, `index`, `settled`, `entry` (`shock.entry_condition(reading, th)`).
- `replay_table(fx, th) -> list[dict]` — `session = datetime.fromisoformat(fx["steps"][0]["as_of"]).date()`; loop as the test's `_replay` (`measure`, then `step`), one row per step with the keys in Interfaces (`as_of` ISO text, `streak` = the new state's `entry_streak`, `label` = the new state's label).
- `first_shock(rows) -> str | None`; `verdict(rows, deadline=DEADLINE) -> str` — `"PASS"` iff a first `SHOCK` exists and `datetime.fromisoformat(first) <= deadline`.
- `_markdown(out: dict) -> str` — a header line with the cell, source, `vix_interpolated`, `vix_source`, first SHOCK and verdict; the line "Fixture VIX: one-minute ^VIX bars (`<vix_source>`), the close of the last bar finished by each step (point-in-time)."; then a pipe table `| as_of | min | breadth | speed | sectors | spy ATR | VIX % | settled | depth | fast | index | streak | label |` (values rounded to 3 places, `—` for `None`).
- `main(argv=None) -> int` — argparse `--fixture` (default `DEFAULT_FIXTURE`), `--k` and `--v` (`float`, required), `--out-json`, `--out-md` (required); `--k <= 0` → print an error, return 2; a fixture whose `vix_interpolated` is not `False` → print "interpolated VIX fixture: rebuild it (V222-6d)", return 2, write nothing; existing `--out-json` → print "Stage 3 already ran: <path>", return 3; else `th = shock.ShockThresholds(index_atr_k=k, index_vix_chg=v)`, write `{"cell": [k, v], "fixture": str(path), "source", "vix_interpolated", "vix_source", "rows", "first_shock", "deadline": DEADLINE.isoformat(), "verdict"}` as JSON (indent 2) and the markdown, print `verdict: PASS|FAIL first SHOCK: <time|never>`, return 0. Keep every function under complexity 15.

- [ ] **Step 4: Run the tests and commit the script**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/backtest_scripts/test_shock_index_replay_once.py`
Expected: PASS, `0 failed`.

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add scripts/backtest/shock_index_replay_once.py tests/backtest_scripts/test_shock_index_replay_once.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): run-once Stage 3 replay script for the frozen index cell (V222-13)"
```

- [ ] **Step 5: Run Stage 3 once**

Preconditions: V222-9..V222-11 and V222-6d (the rebuilt fixture) committed on the v209
branch; the spec's Results § Stage 2
names the frozen cell and gate 2 passed. Read `FROZEN_K` and `FROZEN_V` from that section
(copy them; never recompute). Then, exactly once:

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/backtest/shock_index_replay_once.py --k FROZEN_K --v FROZEN_V --out-json E:/Documents/Private/Projects/Discord-Bot/data/v222/stage3.json --out-md E:/Documents/Private/Projects/Discord-Bot/data/v222/stage3.md
```

(substitute the two numbers). Expected: exit 0 and one `verdict:` line. Exit 3 means it
already ran: use the existing `stage3.json`, never rerun with another cell.

- [ ] **Step 6: Write the Results (main tree spec)**

Add `### Stage 3 — replay of 2026-11-05` under `## Results`: the cell, the fixture
(`tests/fixtures/shock_replay_2026_11_05.json`, source, V222-6d's rebuild commit, its
sha256), the VIX provenance line (real one-minute `^VIX` bars, point-in-time), the full step table from `stage3.md`, the first `SHOCK` time and
**PASS** or **FAIL** against 15:00 UTC, and: "Run once with the cell frozen at gate 2; not
re-run."

```bash
git -C E:/Documents/Private/Projects/Discord-Bot add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C E:/Documents/Private/Projects/Discord-Bot commit -m "docs(v222): Stage 3 replay of 2026-11-05 with the frozen cell"
```

- [ ] **Step 7: Gate 3**

- **PASS** → go on to V222-14 (tell the partner the verdict in one line; no question).
- **FAIL** → stop. Nothing that weakens the replay test is committed; the test stays
  untracked; the path stays off (`0.0`); V222-14 does not run. Ask the partner
  (`AskUserQuestion`, recommended first): "Record Stage 3 FAIL as the measured answer;
  keep the index path shipped off and decide v209's release (V209-13) separately"
  (recommended) / "Close v222 as NO-LIFT now (plan to `no-lift/`)". Never offer moving the
  grid, the rule or the cell.

### Task V222-14: Frozen cell becomes the default; commit the replay test unchanged

**Model:** sonnet — mechanical default change across four files plus their pins, gated on a recorded PASS.

**Runs only when the spec's Results § Stage 3 says PASS (gate 3).** On FAIL this task is
skipped and nothing here is committed.

**Files:**
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/swingbot/core/market/shock.py` (`ShockThresholds.index_atr_k` / `index_vix_chg` defaults)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/swingbot/config.py` (`SHOCK_INDEX_ATR_K` / `SHOCK_INDEX_VIX_CHG` `default=`)
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/.env.example`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/test_config_v209_keys.py`
- Modify: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_step_entry.py`
- Add to git, unchanged since V222-6d: `.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_replay_2026_11_05.py` (untracked since V209-12b; V222-6d changed only its provenance line)

**Interfaces:**
- Consumes: the frozen cell `(FROZEN_K, FROZEN_V)` from the spec's Results § Stage 2 and the Stage 3 PASS in § Stage 3; V222-9's fields; V222-10's `Field`s, `V209_FIELDS`, `CAST_DEFAULTS`, `.env.example` lines.
- Produces: defaults `index_atr_k = FROZEN_K`, `index_vix_chg = FROZEN_V` everywhere a default lives (spec § Stage 3: "the `ShockThresholds` default, the config `Field` default and `CAST_DEFAULTS`"), so the V209-12b replay test, which reads `ShockThresholds()`, passes unchanged.

Substitution rule: read the two numbers from Results § Stage 2 (they must equal the
`cell` in `M/data/v222/stage3.json`; if not, stop and report). Write the Python defaults as
float literals (`1.5`, `20.0`); write every config/`.env.example` default string as
`repr(float(x))` (`"1.5"`, `"20.0"`, `"1.25"`). The settle rule, the two-reading rule, the
off guard and the `0.0` meaning of "off" are unchanged; the mode stays `shadow`, so the
label still blocks nothing.

- [ ] **Step 0: Record the replay test's hash**

Run `sha256sum E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_replay_2026_11_05.py` and keep the hash (the file is untracked, so git cannot show an edit to it). It must equal the hash V222-6d reported; if not, stop and report (something edited the test after V222-6d).

- [ ] **Step 1: Update the pins first (they fail against the `0.0` defaults)**

`W/tests/market/test_shock_step_entry.py`: replace `test_index_fields_default_to_off` with
(literal numbers substituted):

```python
FROZEN = (FROZEN_K, FROZEN_V)          # spec Results § Stage 2; Stage 3 PASS


def test_index_fields_default_to_the_frozen_cell():
    th = ShockThresholds()
    assert (th.index_atr_k, th.index_vix_chg) == FROZEN
    assert type(th.index_atr_k) is float and type(th.index_vix_chg) is float


def test_the_default_still_needs_both_halves():
    k, v = FROZEN
    assert entry_condition(_reading(spy_atr_move=-k, vix_chg_pct=v), ShockThresholds()) is True
    assert entry_condition(_reading(spy_atr_move=-k, vix_chg_pct=v - 0.1), ShockThresholds()) is False
    assert entry_condition(_reading(spy_atr_move=-k + 0.01, vix_chg_pct=v), ShockThresholds()) is False
```

`W/tests/test_config_v209_keys.py`: set `V209_FIELDS["SHOCK_INDEX_ATR_K"] = ("float",
"<repr(float(FROZEN_K))>")`, `V209_FIELDS["SHOCK_INDEX_VIX_CHG"] = ("float",
"<repr(float(FROZEN_V))>")`, and `CAST_DEFAULTS` to `FROZEN_K` / `FROZEN_V` as floats.
`test_index_keys_name_v222_and_accept_zero_as_off` stays (0.0 is still a valid "off").

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/test_config_v209_keys.py`
Expected: FAIL on the two keys' default, cast and `.env.example` tests.

- [ ] **Step 2: Set the defaults**

- `shock.py`: `index_atr_k: float = FROZEN_K` and `index_vix_chg: float = FROZEN_V` (comment: "v222 frozen cell, spec Results § Stage 2; 0.0 turns the path off").
- `config.py`: `default="<repr(float(FROZEN_K))>"` on `SHOCK_INDEX_ATR_K`, `default="<repr(float(FROZEN_V))>"` on `SHOCK_INDEX_VIX_CHG`; append to each help string: " Default: the v222 frozen cell (spec Results)."
- `.env.example`: `SHOCK_INDEX_ATR_K=<repr(float(FROZEN_K))>`, `SHOCK_INDEX_VIX_CHG=<repr(float(FROZEN_V))>`; the comment above keeps "0.0 turns the path off".

`SHOCK_INDEX_ATR_K`'s `min=0`/`max=5.0` and `SHOCK_INDEX_VIX_CHG`'s `min=0`/`max=200` already
contain every grid value.

- [ ] **Step 3: Run every shock test file, the replay test included, unchanged**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/test_config_v209_keys.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_step_entry.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_step_exit.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_measure.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/market/test_shock_replay_2026_11_05.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_scan.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_pass.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_index_path.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_plans_byte_identical.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_short_lane.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/scripts/dev/testrun.py file tests/scanning/test_shock_state_stamp.py
```

Expected: every file PASS, `0 failed`; the replay file's five tests pass with its first
`SHOCK` at exactly 15:00 UTC (the Stage 3 table's first SHOCK). If the replay test fails
while Stage 3 said PASS, stop and report the mismatch: never edit the replay test, the
fixture or the cell to make it pass. If an older v209 test fails because a calm reading now
crosses the default cell, report it (with the reading) rather than changing the cell; the
fix is that test's reading, reviewed by the controller.

Then `sha256sum E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector/tests/market/test_shock_replay_2026_11_05.py` must print the hash recorded in Step 0.

- [ ] **Step 4: Commit (v209 branch), two scoped commits**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add swingbot/core/market/shock.py swingbot/config.py .env.example tests/test_config_v209_keys.py tests/market/test_shock_step_entry.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "feat(v222): the Stage 3 frozen cell becomes the index path default (V222-14)"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector add tests/market/test_shock_replay_2026_11_05.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector commit -m "test(v209): commit the 2026-11-05 replay acceptance test unchanged (V209-12b, V222-14)"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the main-tree status shows nothing from this task. Nothing is merged, pushed to
production or released here: V209-13 owns the release, and the spec's Results already hold
Stages 1–3 and the production VIX check.

