# v222 — Market-shock detector: index + VIX entry path — Part 4: the detector path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md) (§ What changes, § Acceptance)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V222-9, V222-10, V222-11: the fourth entry path in the pure detector,
its two hot-reloadable config keys and pins, and the pipeline tests that prove
partial data never fires and the path off changes nothing.

**Start condition.** None of these tasks starts before gate 2 has passed
(V222-8 wrote a frozen cell `FROZEN_K, FROZEN_V` into Results). On a NO-LIFT
at gate 1 or gate 2 this part is never run. The frozen cell is **not** used
here: the dataclass and config defaults stay `0.0` (off) in this part, and
V222-14 sets the config default later. Tests pass cells explicitly.

**Rules every task here keeps (index § Global Constraints, restated because
they decide review):**

- `ShockThresholds()` defaults never change: `index_atr_k = 0.0`,
  `index_vix_chg = 0.0`, floats, appended after `quote_max_age_s`.
- `_index_path` returns False when `th.index_atr_k <= 0` (the guard), when
  `spy_atr_move` is None, or when `vix_chg_pct` misses the bar (`shock._meets`:
  None never meets). VIX relief never applies to it.
- No stored field: `ShockReading` and `ShockState` keep their fields; no
  Alembic revision; `shock.py` gains no import.
- `tests/market/test_shock_acceptance_a1.py` is never edited and prints the same
  report after V222-9 as before it.
- With the path off every long and short plan, every reading row and every
  state row is byte-identical to the A1-only detector.

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths. The tests in this part use
fakes and monkeypatched config only; none reaches Postgres, so no
`/replicate-prod-db` run is needed.

# Phase 4 — The detector path

### Task V222-9: `ShockThresholds` index fields, `_index_path`, `entry_condition`

**Model:** sonnet — a small, fully specified change to a pure function with exact boundary tests; the risk (off path, A1 record) is pinned by tests written here.

**Files:**
- Modify: `swingbot/core/market/shock.py` (`ShockThresholds` l.32-50; new `_index_path` after `_fast_path`, l.~318; `entry_condition` l.323-327; module docstring l.1-13)
- Modify: `tests/market/test_shock_step_entry.py` (append the v222 block; add `from dataclasses import fields`)

**Interfaces:**
- Consumes: `shock._meets(value, bar) -> bool` (None never meets; `value + 1e-9 >= bar`), `shock._settled`, `shock._from_normal` (unchanged: a settled reading on which `entry_condition` holds adds one to the shared streak; the second is `SHOCK`), `shock.step` (an insufficient reading returns the state untouched).
- Produces: `ShockThresholds.index_atr_k: float = 0.0`, `ShockThresholds.index_vix_chg: float = 0.0` (fields 19 and 20, after `quote_max_age_s`); `shock._index_path(reading: ShockReading, th: ShockThresholds) -> bool`; `entry_condition` = depth or majority or fast or index. V222-10 maps the two fields to config; V222-11 and V222-13 drive them through `shock.step`.

**Known red between V222-9 and V222-10.** `tests/scanning/test_shock_scan.py::test_thresholds_map_every_field_and_keep_ints_int`
asserts `set(THRESHOLD_ATTRS) == {f.name for f in fields(ShockThresholds)}`. It
fails after this task (two fields, no rows yet) and is made green by V222-10,
which runs next on the same branch. That one failure is expected here; any other
failure is not. Never push the branch between V222-9 and V222-10.

- [ ] **Step 0: Record the A1 report before any detector change**

The A1 acceptance test must print the same report after this task. Capture it
first (`logs/` is gitignored in the worktree). `testrun.py` runs pytest inside
its own checkout, so the worktree's `swingbot` is imported (a bare `python -m
pytest` from the main tree's working directory would import the main tree's),
and it parks the full output, including the report the test prints under
`capsys.disabled()`, in `$W/.pytest-last-run.log`. The report runs from the line
`v209 A1 acceptance (one shot)` to the `verdict:` line:

```bash
mkdir -p "$W/logs/v222"
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_acceptance_a1.py
python - "$W/.pytest-last-run.log" "$W/logs/v222/a1_report_before.txt" <<'PY'
import sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip() == "v209 A1 acceptance (one shot)")
end = next(i for i in range(start, len(lines)) if lines[i].startswith("verdict:"))
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines[start:end + 1]) + "\n")
print(lines[end])
PY
```

Expected: the printed line starts `verdict: PASS`. If it does not, stop and
report `BLOCKED:` (the A1 record must be green before v222 touches the detector).

- [ ] **Step 1: Write the failing tests**

In `tests/market/test_shock_step_entry.py`, add `from dataclasses import fields`
to the imports (below `import json`), then append:

```python
# --- v222: the index path (spec § What changes) ------------------------------
# The cell here is a test value, not the frozen one: ShockThresholds() stays off.

IDX = ShockThresholds(index_atr_k=1.5, index_vix_chg=20.0)
INDEX = dict(spy_atr_move=-1.5, vix_chg_pct=20.0)      # calm breadth, both halves at the bar


def _run_th(th, state, *readings):
    for reading in readings:
        state = step(state, reading, th)
    return state


def test_index_fields_are_appended_and_default_to_off():
    names = [f.name for f in fields(ShockThresholds)]
    assert len(names) == 20
    assert names[17] == "quote_max_age_s"
    assert names[-2:] == ["index_atr_k", "index_vix_chg"]
    th = ShockThresholds()
    assert (th.index_atr_k, th.index_vix_chg) == (0.0, 0.0)
    assert type(th.index_atr_k) is float and type(th.index_vix_chg) is float


def test_no_index_field_is_stored():
    for cls in (ShockReading, ShockState):
        assert not [f.name for f in fields(cls) if "index" in f.name], cls


@pytest.mark.parametrize("spy, vix, expected", [
    (-1.5, 20.0, True),                      # both halves exactly at the bar
    (-1.5 + 5e-10, 20.0 - 5e-10, True),      # inside the 1e-9 tolerance
    (-1.49, 20.0, False),                    # SPY short of the bar
    (-1.5, 19.99, False),                    # VIX short of the bar
    (-4.0, 80.0, True),
    (1.5, 20.0, False),                      # SPY up, not down
    (0.0, 50.0, False),                      # VIX alone never fires
    (None, 20.0, False),                     # no SPY quote or no ATR
    (-1.5, None, False),                     # stale, proxy or missing VIX
    (None, None, False),
])
def test_index_path_boundaries(spy, vix, expected):
    reading = _reading(spy_atr_move=spy, vix_chg_pct=vix)
    assert shock._index_path(reading, IDX) is expected
    assert entry_condition(reading, IDX) is expected       # calm breadth: the index decides


@pytest.mark.parametrize("k", [0.0, -1.0])
def test_a_non_positive_k_is_off_even_on_a_calm_reading(k):
    th = ShockThresholds(index_atr_k=k, index_vix_chg=0.0)
    for over in (dict(spy_atr_move=0.0, vix_chg_pct=0.0), dict(spy_atr_move=-6.0, vix_chg_pct=90.0)):
        reading = _reading(**over)
        assert shock._index_path(reading, th) is False
        assert entry_condition(reading, th) is False


def test_default_thresholds_never_take_the_index_path():
    reading = _reading(spy_atr_move=-6.0, vix_chg_pct=90.0)
    assert shock._index_path(reading, TH) is False
    assert entry_condition(reading, TH) is False


@pytest.mark.parametrize("vix, expected", [(0.0, True), (-0.5, False), (None, False)])
def test_a_zero_vix_bar_still_needs_a_fresh_vix_change(vix, expected):
    th = ShockThresholds(index_atr_k=1.0, index_vix_chg=0.0)
    assert shock._index_path(_reading(spy_atr_move=-1.0, vix_chg_pct=vix), th) is expected


def test_vix_relief_never_lowers_the_index_bars():
    # vix_chg_pct >= vix_spike_pct (15) turns relief on; the index bars stay where they are
    assert entry_condition(_reading(spy_atr_move=-1.45, vix_chg_pct=30.0), IDX) is False
    assert entry_condition(_reading(spy_atr_move=-1.5, vix_chg_pct=19.95), IDX) is False


@pytest.mark.parametrize("over", [DEPTH, MAJORITY, FAST], ids=["depth", "majority", "fast"])
@pytest.mark.parametrize("vix", [0.0, None])
def test_a1_paths_are_unchanged_with_the_index_path_on(over, vix):
    reading = _reading(**dict(over, vix_chg_pct=vix))
    assert entry_condition(reading, IDX) is True
    assert entry_condition(reading, TH) is True


def test_two_index_readings_enter_shock():
    first = step(ShockState(), _reading(0, **INDEX), IDX)
    assert first.label == "NORMAL" and first.entry_streak == 1
    second = step(first, _reading(15, **INDEX), IDX)
    assert second.label == "SHOCK" and second.since == T0 + timedelta(minutes=15)
    assert second.entry_streak == 0 and second.hold_since is None


@pytest.mark.parametrize("first, second", [
    (INDEX, MAJORITY), (MAJORITY, INDEX), (FAST, INDEX), (INDEX, DEPTH)],
    ids=["index-majority", "majority-index", "fast-index", "index-depth"])
def test_a_streak_mixes_an_a1_path_and_the_index_path(first, second):
    state = _run_th(IDX, ShockState(), _reading(0, **first), _reading(15, **second))
    assert state.label == "SHOCK"


def test_with_the_path_off_the_same_readings_never_enter_shock():
    state = _run_th(TH, ShockState(), _reading(0, **INDEX), _reading(15, **INDEX))
    assert state.label == "NORMAL" and state.entry_streak == 0


def test_index_readings_inside_the_open_settle_window_never_count():
    early = dict(INDEX, minutes_since_open=14.0)
    state = _run_th(IDX, ShockState(), _reading(0, **early),
                    _reading(1, **dict(early, minutes_since_open=14.9)))
    assert state.label == "NORMAL" and state.entry_streak == 0
    state = _run_th(IDX, state, _reading(2, **dict(INDEX, minutes_since_open=15.0)))
    assert state.entry_streak == 1


def test_a_partial_reading_between_index_readings_resets_the_streak():
    state = _run_th(IDX, ShockState(), _reading(0, **INDEX),
                    _reading(15, **dict(INDEX, vix_chg_pct=None)), _reading(30, **INDEX))
    assert state.label == "NORMAL" and state.entry_streak == 1
    state = _run_th(IDX, ShockState(), _reading(0, **INDEX),
                    _reading(15, **dict(INDEX, spy_atr_move=None)), _reading(30, **INDEX))
    assert state.label == "NORMAL" and state.entry_streak == 1


def test_an_insufficient_index_reading_holds_the_state():
    state = step(ShockState(), _reading(0, **INDEX), IDX)
    thin = _reading(15, **dict(INDEX, n_names=3, insufficient=True))
    assert step(state, thin, IDX) is state
    assert step(state, _reading(30, **INDEX), IDX).label == "SHOCK"
```

The existing row `(dict(breadth_frac=0.05, spy_atr_move=-4.0, qqq_atr_move=-4.0), False)`
in `test_entry_condition_paths` stays as it is: under `TH = ShockThresholds()`
the path is off, so index moves still never trigger there.

Why these readings stay calm on A1's paths: `_reading` has `breadth_frac=0.05`,
`depth_frac=0.0`, `breadth_speed=None`; a VIX change at or above 15 % lowers the
majority bar to 0.45 and the fast bar to 0.20, both still far above 0.05.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_step_entry.py
```

Expected: FAIL at collection — `TypeError: ShockThresholds.__init__() got an unexpected keyword argument 'index_atr_k'` (the module-level `IDX`).

- [ ] **Step 3: Implement**

In `swingbot/core/market/shock.py`, append the two fields to `ShockThresholds`
after `quote_max_age_s`:

```python
    quote_max_age_s: int = 300
    # v222 index path. 0.0 is off; these dataclass defaults stay 0.0 for good:
    # test_shock_acceptance_a1.py replays ShockThresholds() as a closed record.
    # A release sets the config Field defaults (SHOCK_INDEX_*), never these.
    index_atr_k: float = 0.0
    index_vix_chg: float = 0.0
```

Add `_index_path` directly after `_fast_path`:

```python
def _index_path(reading: ShockReading, th: ShockThresholds) -> bool:
    """v222: SPY at least ``index_atr_k`` ATR14 below its prior close and ^VIX up at
    least ``index_vix_chg`` percent on the day. Off when ``index_atr_k <= 0`` (without
    the guard a calm 0.0 / 0.0 reading would meet 0.0 bars). A missing SPY move (no
    quote, no ATR) or VIX change (missing, stale or proxy tape) never meets. VIX
    relief does not apply: it lowers breadth bars only."""
    if th.index_atr_k <= 0 or reading.spy_atr_move is None:
        return False
    return (_meets(-reading.spy_atr_move, th.index_atr_k)
            and _meets(reading.vix_chg_pct, th.index_vix_chg))
```

Replace `entry_condition`:

```python
def entry_condition(reading: ShockReading, th: ShockThresholds = ShockThresholds()) -> bool:
    """NORMAL -> SHOCK on this one reading: A1's weighted depth, sustained breadth or
    speed, or v222's index path (SPY down and VIX up; off at index_atr_k = 0)."""
    relief = _relief(reading, th)
    return (_depth_path(reading, th, relief) or _majority_path(reading, th, relief)
            or _fast_path(reading, th, relief) or _index_path(reading, th))
```

In the module docstring, after the `Spec:` line, add:

```text
v222 adds a fourth entry path (``_index_path``: SPY down in ATR and ^VIX up),
off by default; spec docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
```

No other line of `shock.py` changes; no import is added.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_step_entry.py
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_acceptance_a1.py
python - "$W/.pytest-last-run.log" "$W/logs/v222/a1_report_after.txt" <<'PY'
import sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip() == "v209 A1 acceptance (one shot)")
end = next(i for i in range(start, len(lines)) if lines[i].startswith("verdict:"))
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines[start:end + 1]) + "\n")
print(lines[end])
PY
diff "$W/logs/v222/a1_report_before.txt" "$W/logs/v222/a1_report_after.txt" && echo SAME-REPORT
git -C "$W" diff --quiet main -- tests/market/test_shock_acceptance_a1.py tests/fixtures/shock_replay tests/fixtures/shock_replay_2026_11_05.json && echo A1-UNTOUCHED
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_scan.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: `test_shock_step_entry.py` all pass; the A1 test passes unedited,
`SAME-REPORT` and `A1-UNTOUCHED` print (a diff line is a stop: the off path
changed A1's readings; fix `shock.py`, never the test); `test_shock_scan.py`
shows exactly one failure, `test_thresholds_map_every_field_and_keep_ints_int`
(the known red above, fixed by V222-10); the complexity gate passes.

- [ ] **Step 5: Commit**

```bash
git -C "$W" add swingbot/core/market/shock.py tests/market/test_shock_step_entry.py
git -C "$W" commit -m "feat(v222): shock index entry path -- SPY ATR move and VIX change, off at 0.0"
git -C "$M" status --short
```

The main-tree status shows nothing but the spec's `## Results` edits.

### Task V222-10: Config keys, `THRESHOLD_ATTRS` rows, `.env.example`, config pins

**Model:** sonnet — config wiring along an existing pattern with exact pins; the one trap (a key without a `THRESHOLD_ATTRS` row is a silent no-op) is tested end to end here.

**Files:**
- Modify: `swingbot/config.py` (two `Field`s after `SHOCK_VIX_RELIEF`, l.~1633)
- Modify: `swingbot/core/scanning/shock_scan.py` (`THRESHOLD_ATTRS`, l.38-50)
- Modify: `.env.example` (Market Shock block, after `SHOCK_VIX_RELIEF=0.05`, l.865)
- Modify: `tests/scanning/test_shock_scan.py` (`test_thresholds_map_every_field_and_keep_ints_int`, l.43-54)
- Modify: `tests/test_config_v209_keys.py` (`V209_FIELDS`, `CAST_DEFAULTS`, the count test, three new tests)

**Interfaces:**
- Consumes: `ShockThresholds.index_atr_k`, `.index_vix_chg` (V222-9, float, default 0.0); `shock_scan.thresholds_from_config()` (casts each config value with `type(default)(...)`, so the 0.0 float defaults make both keys floats); `config._apply_env()`, `config._cast(field, raw)`, `config.FIELDS`.
- Produces: config attrs `SHOCK_INDEX_ATR_K` (float, default `"0.0"`, `min=0`, `max=5.0`, `step=0.25`) and `SHOCK_INDEX_VIX_CHG` (float, default `"0.0"`, `min=0`, `max=200`, `step=1`), both hot-reloadable, `search_class` `"excluded"` (the `Field` default), placed directly after `SHOCK_VIX_RELIEF`; `THRESHOLD_ATTRS["index_atr_k"] = "SHOCK_INDEX_ATR_K"`, `THRESHOLD_ATTRS["index_vix_chg"] = "SHOCK_INDEX_VIX_CHG"`; `.env.example` lines `SHOCK_INDEX_ATR_K=0.0` and `SHOCK_INDEX_VIX_CHG=0.0`. V222-11 monkeypatches the two config attrs; V222-14 changes the two defaults (Field, `V209_FIELDS`, `CAST_DEFAULTS`, `.env.example`) to the frozen cell.

Pins this task keeps (spec § Acceptance, index § Global Constraints): the
Market Shock block stays contiguous after `DCB_VOLUME_RATIO` and directly
before `DATABASE_URL`; `len(V209_FIELDS)` 20 → 22;
`len(set(THRESHOLD_ATTRS.values()))` 18 → 20; each new `help` contains `v209`
and `v222`; `min <= default <= max` with `min = 0` for both.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config_v209_keys.py`, insert the two keys into `V209_FIELDS`
directly after `SHOCK_VIX_RELIEF` (dict order is the `FIELDS` order):

```python
    "SHOCK_VIX_RELIEF": ("float", "0.05"),
    "SHOCK_INDEX_ATR_K": ("float", "0.0"),
    "SHOCK_INDEX_VIX_CHG": ("float", "0.0"),
    "SHOCK_BREADTH_REENTER": ("float", "0.30"),
```

and into `CAST_DEFAULTS` (after the `"SHOCK_VIX_RELIEF": 0.05,` entry on its line):

```python
    "SHOCK_VIX_RELIEF": 0.05, "SHOCK_BREADTH_REENTER": 0.30, "SHOCK_BREADTH_EXIT": 0.20,
    "SHOCK_INDEX_ATR_K": 0.0, "SHOCK_INDEX_VIX_CHG": 0.0,
```

Replace the count test:

```python
def test_twenty_two_fields_one_mode_plus_twenty_one_thresholds():
    # A1: SHOCK_SECTORS_FRAC removed, SHOCK_DEPTH_FRAC and SHOCK_BREADTH_MAJORITY added.
    # v222: SHOCK_INDEX_ATR_K and SHOCK_INDEX_VIX_CHG added (20 detector thresholds,
    # SHOCK_READINGS_KEEP_DAYS retention, MARKET_SHOCK_MODE).
    assert len(V209_FIELDS) == 22
    assert set(V209_FIELDS) == set(CAST_DEFAULTS)
```

Append:

```python
# --- v222: the index path keys (spec § What changes, Config) ----------------

V222_KEYS = ("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG")


@pytest.mark.parametrize("attr", V222_KEYS)
def test_index_keys_are_off_at_zero_with_a_zero_floor(attr):
    field = _field(attr)
    assert "v222" in field.help and "v209" in field.help
    assert field.min == 0
    value = config._cast(field, field.default)
    assert value == 0.0 and type(value) is float
    assert config._cast(field, "1.25") == 1.25


def test_index_keys_sit_right_after_vix_relief():
    attrs = [f.attr for f in config.FIELDS]
    at = attrs.index("SHOCK_VIX_RELIEF")
    assert attrs[at + 1:at + 3] == list(V222_KEYS)


def test_an_env_index_key_reaches_the_detector_thresholds(monkeypatch):
    from swingbot.core.scanning import shock_scan
    monkeypatch.setenv("SHOCK_INDEX_ATR_K", "1.5")
    monkeypatch.setenv("SHOCK_INDEX_VIX_CHG", "20")
    try:
        config._apply_env()
        th = shock_scan.thresholds_from_config()
        assert (th.index_atr_k, th.index_vix_chg) == (1.5, 20.0)
        assert type(th.index_vix_chg) is float
    finally:
        monkeypatch.undo()
        config._apply_env()
    assert shock_scan.thresholds_from_config().index_atr_k == 0.0
```

The last assert holds on any checkout whose local `.env` carries no
`SHOCK_INDEX_*` key (none does before V222-14; the keys are new). If a local
`.env` ever sets one, the test is wrong for that machine, not the code: delete
the key from the local `.env`, never the assert.

In `tests/scanning/test_shock_scan.py`, replace
`test_thresholds_map_every_field_and_keep_ints_int` with:

```python
def test_thresholds_map_every_field_and_keep_ints_int(monkeypatch):
    assert set(shock_scan.THRESHOLD_ATTRS) == {f.name for f in fields(shock.ShockThresholds)}
    assert len(set(shock_scan.THRESHOLD_ATTRS.values())) == 20
    monkeypatch.setattr(config, "SHOCK_ATR_K", 1.5)
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 7.0)
    th = shock_scan.thresholds_from_config()
    assert th.atr_k == 1.5 and th.min_names == 7 and isinstance(th.min_names, int)
    assert "SHOCK_SECTORS_FRAC" not in shock_scan.THRESHOLD_ATTRS.values()
    monkeypatch.setattr(config, "SHOCK_DEPTH_FRAC", 0.55)
    monkeypatch.setattr(config, "SHOCK_BREADTH_MAJORITY", 0.6)
    th = shock_scan.thresholds_from_config()
    assert (th.depth_frac, th.breadth_majority) == (0.55, 0.6)


def test_index_keys_reach_the_thresholds_as_floats(monkeypatch):
    assert shock_scan.THRESHOLD_ATTRS["index_atr_k"] == "SHOCK_INDEX_ATR_K"
    assert shock_scan.THRESHOLD_ATTRS["index_vix_chg"] == "SHOCK_INDEX_VIX_CHG"
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", 1.25)
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", 15)    # an int from a hand edit still casts
    th = shock_scan.thresholds_from_config()
    assert (th.index_atr_k, th.index_vix_chg) == (1.25, 15.0)
    assert type(th.index_atr_k) is float and type(th.index_vix_chg) is float


def test_a_missing_index_attr_falls_back_to_off(monkeypatch):
    monkeypatch.delattr(config, "SHOCK_INDEX_ATR_K")
    monkeypatch.delattr(config, "SHOCK_INDEX_VIX_CHG")
    th = shock_scan.thresholds_from_config()
    assert (th.index_atr_k, th.index_vix_chg) == (0.0, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python "$W/scripts/dev/testrun.py" file tests/test_config_v209_keys.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_scan.py
```

Expected: FAIL — `StopIteration` from `_field("SHOCK_INDEX_ATR_K")`, the count
test (`22`), the contiguity test, the `.env.example` tests for both keys;
`test_shock_scan.py` fails the set-equality and `== 20` asserts, `KeyError:
'index_atr_k'`, and `AttributeError` from `monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", ...)`.

- [ ] **Step 3: Implement**

In `swingbot/config.py`, directly after the `SHOCK_VIX_RELIEF` `Field` (and
before `SHOCK_BREADTH_REENTER`), add:

```python
    Field("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_ATR_K", "Market Shock",
          "Index path: SPY down-move, in ATR14 (0 = off)",
          type="float", default="0.0", min=0, max=5.0, step=0.25,
          help="v209 detector, v222 index path. An entry reading when SPY is at least this "
               "many ATR14 below its prior close AND ^VIX is up at least SHOCK_INDEX_VIX_CHG % "
               "on the day; it counts toward the same two-reading streak as the breadth paths. "
               "0 turns the path off. A missing SPY quote or ATR, or a stale or proxy VIX, "
               "never fires it. VIX relief does not apply to it."),
    Field("SHOCK_INDEX_VIX_CHG", "SHOCK_INDEX_VIX_CHG", "Market Shock",
          "Index path: VIX day change (%)",
          type="float", default="0.0", min=0, max=200, step=1,
          help="v209 detector, v222 index path. The ^VIX day change the index path needs "
               "beside SHOCK_INDEX_ATR_K. Inert while SHOCK_INDEX_ATR_K is 0."),
```

In `swingbot/core/scanning/shock_scan.py`, extend the comment above
`THRESHOLD_ATTRS` and append two rows after `quote_max_age_s` (same order as
the dataclass):

```python
#: ShockThresholds field -> config attribute (V209-1; v222 adds the index path).
#: SHOCK_READINGS_KEEP_DAYS is retention, read by loops._prune_shock_readings, not
#: a threshold. A key without a row here never reaches ShockThresholds.
THRESHOLD_ATTRS = {
    "atr_k": "SHOCK_ATR_K", "breadth_enter": "SHOCK_BREADTH_ENTER",
    "depth_frac": "SHOCK_DEPTH_FRAC", "breadth_majority": "SHOCK_BREADTH_MAJORITY",
    "breadth_fast": "SHOCK_BREADTH_FAST",
    "speed_enter": "SHOCK_SPEED_ENTER", "vix_spike_pct": "SHOCK_VIX_SPIKE_PCT",
    "vix_relief": "SHOCK_VIX_RELIEF", "breadth_reenter": "SHOCK_BREADTH_REENTER",
    "breadth_exit": "SHOCK_BREADTH_EXIT",
    "recovery_vix_off_high_pct": "RECOVERY_VIX_OFF_HIGH_PCT",
    "recovery_spy_retrace": "RECOVERY_SPY_RETRACE", "min_dwell_min": "SHOCK_MIN_DWELL_MIN",
    "recovery_min_dwell_min": "RECOVERY_MIN_DWELL_MIN", "min_names": "SHOCK_MIN_NAMES",
    "vix_max_age_s": "SHOCK_VIX_MAX_AGE_S", "open_settle_min": "SHOCK_OPEN_SETTLE_MIN",
    "quote_max_age_s": "SHOCK_QUOTE_MAX_AGE_S",
    "index_atr_k": "SHOCK_INDEX_ATR_K", "index_vix_chg": "SHOCK_INDEX_VIX_CHG",
}
```

In `.env.example`, after `SHOCK_VIX_RELIEF=0.05` (keep the blank line that
follows it before the `RECOVERY -> SHOCK` comment):

```text
SHOCK_VIX_RELIEF=0.05

# v222 index path: an entry reading when SPY is SHOCK_INDEX_ATR_K ATR14 below
# its prior close and ^VIX is up SHOCK_INDEX_VIX_CHG % on the day. 0.0 = off.
SHOCK_INDEX_ATR_K=0.0
SHOCK_INDEX_VIX_CHG=0.0
```

`SHOCK_VIX_SPIKE_PCT`'s help ("VIX never triggers SHOCK on its own") stays: the
index path needs SPY down as well, so VIX alone still never triggers.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/test_config_v209_keys.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_scan.py
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_step_entry.py
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_acceptance_a1.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass, the V222-9 known red included; the A1 test passes unedited.
If another config test fails on the two new fields (a test that enumerates every
`FIELDS` key, a settings-page section count), update its expectation for the
two keys in this task and name it in the commit body; never remove a field to
make it pass.

- [ ] **Step 5: Commit**

```bash
git -C "$W" add swingbot/config.py swingbot/core/scanning/shock_scan.py .env.example
git -C "$W" commit -m "feat(v222): SHOCK_INDEX_ATR_K and SHOCK_INDEX_VIX_CHG keys reach the detector, off at 0.0"
git -C "$W" add tests/test_config_v209_keys.py tests/scanning/test_shock_scan.py
git -C "$W" commit -m "test(v222): config pins 20 -> 22 fields, 18 -> 20 threshold rows, env to thresholds"
git -C "$M" status --short
```

### Task V222-11: Pipeline tests: partial data, stale/proxy VIX, SPY chunk room, off is byte-identical

**Model:** sonnet — tests only, through existing seams (`run_shock_pass`, `quote_tickers`, the V209-8b plan pins); no production code changes.

**Files:**
- Create: `tests/scanning/test_shock_index_path.py` (suite `scanning`, an existing directory)
- Modify: `tests/scanning/test_shock_plans_byte_identical.py` (append the v222 block)

**Interfaces:**
- Consumes: `config.SHOCK_INDEX_ATR_K`, `config.SHOCK_INDEX_VIX_CHG` (V222-10); `THRESHOLD_ATTRS` rows (V222-10); `shock._index_path`, `entry_condition` (V222-9); `shock_scan.run_shock_pass(*, step_shock, frames, live_prices, sector_of, quotes_at, spy_df=None, now=None, repo=None) -> str | None`, `shock_scan.quote_tickers(tickers, step_shock) -> list`, `shock_scan.read_vix` (proxy, stale or missing tape -> no VIX); `TapeEntry(symbol, price, change_pct, is_proxy, proxy_symbol, as_of)` (`swingbot.core.marketdata.shared.tape`); `tests.scanning.test_shock_pass._Repo` and `_frame(close=100.0, partial=None, n=30)` (an in-memory store; `repo.recorded` holds `(reading_row, state_row, state_after)`, `repo.state["doc"]["state"]` the last state row); in `test_shock_plans_byte_identical.py`: `_assert_pinned`, `_long_item`, `_canon`, `_confluence`, `_requote`, `_attach_on_rebuild`, fixtures `long_env`, `sealed`, and `CANDIDATE`, `GOLDEN_KEPT`, `_items`, `_context`, `qualify`.
- Produces: test helper `tests.scanning.test_shock_index_path.run_passes(m, *, quotes=INDEX_QUOTES, frames=None, vix=fresh_vix, k=1.5, v=20.0, steps=2, mode="shadow") -> tuple[list[str | None], _Repo]`, used by the byte-identical file in this same task. No later task consumes anything here.

What the scenario measures. `_frame` bars have `High - Low = 2`, so ATR14 is
2.0 and the prior close is the last completed bar (today's bar is dropped).
`INDEX_QUOTES` holds the three names flat at 100 (breadth 0, so no A1 path can
fire) and SPY at 496 against a 500 prior close: −2.0 ATR, past the test cell's
1.5. `fresh_vix` is a `^VIX` tape row 60 s old, up 25 % (past 20). NOW is
10:00 ET, 30 minutes after the open, so every reading is settled.

- [ ] **Step 1: Write the tests**

Create `tests/scanning/test_shock_index_path.py`:

```python
"""v222: the index path through the real shock pass (spec § What changes, § Acceptance).

Partial data never fires it, a stale or proxy VIX silences it, SPY's quote
depends on the last fetch chunk's room, A1's paths record exactly as before,
and with the path off every reading and state row is byte-identical to the
A1-only detector. The cell (1.5 ATR, 20 %) is a test value, not the frozen one."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.marketdata.shared.tape import TapeEntry
from swingbot.core.scanning import fetch, shock_scan
from tests.scanning.test_shock_pass import _frame, _Repo

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST (UTC-5)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, 30 min after the open
SECTORS = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech"}
NAMES_FLAT = {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0}
INDEX_QUOTES = {**NAMES_FLAT, "SPY": 496.0}                     # SPY -2.0 ATR, breadth 0
CRASH_QUOTES = {"AAA": 94.0, "BBB": 94.0, "CCC": 94.0, "SPY": 500.0}  # names -3 ATR, SPY flat
CALM_QUOTES = {**NAMES_FLAT, "SPY": 500.0}


def fresh_vix(t):
    return TapeEntry("^VIX", 25.0, 25.0, False, None, t - timedelta(seconds=60))


def stale_vix(t):
    return TapeEntry("^VIX", 25.0, 25.0, False, None, t - timedelta(seconds=601))


def proxy_vix(t):
    return TapeEntry("^VIX", 25.0, 25.0, True, "VIXY", t - timedelta(seconds=60))


def no_vix(t):
    return None


def _frames(spy_n=30):
    return {t: _frame() for t in SECTORS} | {"SPY": _frame(close=500.0, n=spy_n)}


def _setup(m, *, k=1.5, v=20.0, mode="shadow"):
    m.setattr(config, "MARKET_SHOCK_MODE", mode)
    m.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    m.setattr(config, "SHOCK_MIN_NAMES", 2)
    m.setattr(config, "SHOCK_INDEX_ATR_K", k)
    m.setattr(config, "SHOCK_INDEX_VIX_CHG", v)
    m.setattr(shock_scan, "_open_trades", lambda: [])
    m.setattr(shock_scan.asset_class, "classify",
              lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    m.setattr(shock_scan.tape, "read_tape", lambda symbols: {})
    m.setattr(fetch, "_fetch_live_prices",
              lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))


def run_passes(m, *, quotes=INDEX_QUOTES, frames=None, vix=fresh_vix, k=1.5, v=20.0,
               steps=2, mode="shadow"):
    """`steps` stepped passes 15 minutes apart; `quotes` is one dict or one per step."""
    _setup(m, k=k, v=v, mode=mode)
    repo, labels = _Repo(), []
    for i in range(steps):
        t = NOW + timedelta(minutes=15 * i)
        entry = vix(t)
        m.setattr(shock_scan.tape, "read_tape",
                  lambda symbols, e=entry: {} if e is None else {"^VIX": e})
        live = quotes[i] if isinstance(quotes, list) else quotes
        labels.append(shock_scan.run_shock_pass(
            step_shock=True, frames=frames or _frames(), live_prices=live,
            sector_of=SECTORS, quotes_at=t, now=t, repo=repo))
    if mode != "off":
        # run_shock_pass swallows failures: a pass that did not record proves nothing
        assert len(repo.recorded) == steps
    return labels, repo


def _rows(repo) -> str:
    return json.dumps(repo.recorded, sort_keys=True, default=str)


def test_the_index_path_alone_enters_shock_through_the_real_pass(monkeypatch):
    with monkeypatch.context() as m:
        labels, repo = run_passes(m)
    assert labels == ["NORMAL", "SHOCK"]
    first = repo.recorded[0][0]
    assert first["breadth_frac"] == pytest.approx(0.0)
    assert first["spy_atr_move"] == pytest.approx(-2.0)
    assert first["vix_chg_pct"] == pytest.approx(25.0)
    assert not [key for key in first if "index" in key]        # no stored field


def test_the_same_passes_with_the_path_off_stay_normal(monkeypatch):
    with monkeypatch.context() as m:
        labels, repo = run_passes(m, k=0.0, v=0.0)
    assert labels == ["NORMAL", "NORMAL"]
    assert repo.state["doc"]["state"]["entry_streak"] == 0


def test_a_vix_change_below_the_bar_stays_normal(monkeypatch):
    with monkeypatch.context() as m:
        labels, _repo = run_passes(m, v=30.0)
    assert labels == ["NORMAL", "NORMAL"]


PARTIAL = {
    "no_spy_quote": dict(quotes=NAMES_FLAT),
    "no_spy_atr": dict(frames=_frames(spy_n=15)),      # 14 completed bars: no ATR14
    "stale_vix": dict(vix=stale_vix),
    "proxy_vix": dict(vix=proxy_vix),
    "no_vix": dict(vix=no_vix),
}


@pytest.mark.parametrize("case", sorted(PARTIAL))
def test_partial_data_never_fires_the_index_path(monkeypatch, case):
    with monkeypatch.context() as m:
        labels, repo = run_passes(m, **PARTIAL[case])
    assert labels == ["NORMAL", "NORMAL"]
    assert repo.state["doc"]["state"]["entry_streak"] == 0
    for reading, _state, _after in repo.recorded:
        assert reading["insufficient"] is False
        assert reading["spy_atr_move"] is None or reading["vix_chg_pct"] is None


@pytest.mark.parametrize("vix", [fresh_vix, no_vix, stale_vix], ids=["vix", "no-vix", "stale"])
def test_with_the_path_on_the_a1_paths_record_exactly_as_with_it_off(monkeypatch, vix):
    with monkeypatch.context() as m:
        on, repo_on = run_passes(m, quotes=CRASH_QUOTES, vix=vix, k=1.5)
    with monkeypatch.context() as m:
        off, repo_off = run_passes(m, quotes=CRASH_QUOTES, vix=vix, k=0.0, v=0.0)
    assert on == off == ["NORMAL", "SHOCK"]
    assert _rows(repo_on) == _rows(repo_off)


def test_spy_quote_depends_on_the_last_chunk_room(monkeypatch):
    watchlist = sorted(SECTORS)
    with monkeypatch.context() as m:
        _setup(m)
        m.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 3)          # watchlist fills the chunk
        assert shock_scan.quote_tickers(watchlist, True) == watchlist
        m.setattr(config, "BATCH_FETCH_CHUNK_SIZE", 4)          # room for one benchmark
        assert shock_scan.quote_tickers(watchlist, True) == [*watchlist, "SPY"]
    with monkeypatch.context() as m:
        labels, repo = run_passes(m, quotes=NAMES_FLAT)        # what a full chunk delivers
    assert labels == ["NORMAL", "NORMAL"]
    assert all(r[0]["spy_atr_move"] is None for r in repo.recorded)


SEQUENCE = [INDEX_QUOTES, CRASH_QUOTES, INDEX_QUOTES, CRASH_QUOTES, CRASH_QUOTES, CALM_QUOTES]


def test_the_path_off_records_byte_identical_rows_to_the_a1_only_detector(monkeypatch):
    with monkeypatch.context() as m:
        off_labels, off = run_passes(m, quotes=SEQUENCE, steps=len(SEQUENCE), k=0.0, v=0.0)
    with monkeypatch.context() as m:
        m.setattr(shock, "_index_path", lambda reading, th: False)   # the pre-v222 entry rule
        ref_labels, ref = run_passes(m, quotes=SEQUENCE, steps=len(SEQUENCE), k=1.5)
    with monkeypatch.context() as m:
        on_labels, _on = run_passes(m, quotes=SEQUENCE, steps=len(SEQUENCE), k=1.5)
    assert off_labels == ref_labels
    assert _rows(off) == _rows(ref)
    assert on_labels != off_labels            # the scenario does exercise the path


def test_mode_off_ignores_the_index_keys(monkeypatch):
    with monkeypatch.context() as m:
        labels, repo = run_passes(m, mode="off")
    assert labels == [None, None] and repo.recorded == []
```

Append to `tests/scanning/test_shock_plans_byte_identical.py`:

```python
# --- v222: the index path changes the label, never a plan ---------------------
from tests.scanning.test_shock_index_path import run_passes  # noqa: E402


@pytest.fixture
def index_keys_on(monkeypatch):
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", 1.5)
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", 20.0)


def test_the_index_keys_leave_the_long_plan_pinned(long_env, index_keys_on):
    def build(kwargs):
        item = _long_item()
        scan_run._attach_item_plan(item, "scenario", FRAME, None, None, **kwargs)
        return item.plan_v2

    _assert_pinned(build)


def test_the_index_keys_leave_the_short_plan_pinned(sealed, index_keys_on):  # noqa: F811
    def build(kwargs):
        verdict = qualify.qualify_short_item(CANDIDATE, _items()[0], _context(**kwargs))
        assert isinstance(verdict, qualify.Accepted), verdict
        return verdict.item.plan_v2

    off = _assert_pinned(build, features=False)["off"]
    assert (round(off.trigger_price, 6), round(off.stop_loss, 6), round(off.tp1, 6)) == GOLDEN_KEPT[0][2]


@pytest.mark.parametrize("lane", ["confluence", "requote"])
def test_an_index_path_shock_changes_only_the_shock_state_key(long_env, monkeypatch, lane):
    _attach_on_rebuild(monkeypatch, scan_run, lambda item: "rebuilt")
    with monkeypatch.context() as m:
        on, _repo = run_passes(m, k=1.5)
    with monkeypatch.context() as m:
        off, _repo = run_passes(m, k=0.0, v=0.0)
    assert (on[-1], off[-1]) == ("SHOCK", "NORMAL")
    build = {"confluence": _confluence, "requote": _requote}[lane]
    plans = {label: build(label) for label in ("SHOCK", "NORMAL")}
    assert {label: plan.entry_context.pop("shock_state") for label, plan in plans.items()} == {
        "SHOCK": "SHOCK", "NORMAL": "NORMAL"}
    assert _canon(plans["SHOCK"]) == _canon(plans["NORMAL"])
```

`_confluence`, `_requote` and `_attach_on_rebuild` are defined earlier in the
same file; appending at the end keeps every name resolved. If the linter
objects to the mid-file import, move the `run_passes` import into the import
block at the top of the file (same line, without the `noqa`).

- [ ] **Step 2: Run the tests**

```bash
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_index_path.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_plans_byte_identical.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_pass.py
```

Expected: all pass. These are tests over code V222-9 and V222-10 already
shipped, so there is no red step; prove each test can fail instead:

- [ ] **Step 3: Prove the tests bite (then revert)**

Temporarily delete the `th.index_atr_k <= 0 or` part of the guard in
`swingbot/core/market/shock.py` and run
`python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_index_path.py`:
`test_the_same_passes_with_the_path_off_stay_normal` and the byte-identical-rows
test must fail. Restore the guard, then temporarily remove the
`"index_atr_k": "SHOCK_INDEX_ATR_K"` row from `THRESHOLD_ATTRS`:
`test_the_index_path_alone_enters_shock_through_the_real_pass` must fail.
Restore it and confirm `git -C "$W" diff --quiet -- swingbot/` prints nothing
(exit 0) before committing.

A failure in Step 2 that is not a test typo is a finding about V222-9/V222-10
(for example, the pass swallowing an exception, caught by the
`len(repo.recorded) == steps` assert): fix the production code in a separate
commit named for that task, never loosen the test.

- [ ] **Step 4: Commit**

```bash
python "$W/scripts/dev/complexity_gate.py"
git -C "$W" add tests/scanning/test_shock_index_path.py
git -C "$W" commit -m "test(v222): index path through the shock pass -- partial data, stale/proxy VIX, chunk room, off rows"
git -C "$W" add tests/scanning/test_shock_plans_byte_identical.py
git -C "$W" commit -m "test(v222): V209-8b plan pins extend to the index path -- label only"
git -C "$M" status --short
```

