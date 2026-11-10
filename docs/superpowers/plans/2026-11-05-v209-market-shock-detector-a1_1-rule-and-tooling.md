# v209 Amendment A1 — part 1: the rule, the selector, the builder

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md), § Amendment A1, § Panel review (A1)
**Index:** [`_0-index.md`](2026-11-05-v209-market-shock-detector-a1_0-index.md) — Global Constraints, Review Focus, Parallelisation and the task ledger apply to every task below; the parent v209 index's Global Constraints still bind.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector-a1.md`

All work happens in the worktree `.claude/worktrees/2026-11-05-v209-market-shock-detector`
(`cd` there first; every path below is relative to it). Line numbers are from
HEAD a382234d; re-read before editing.

Tasks: V209-A1-1 (the re-registered entry rule and the config removal),
V209-A1-2 (the validation-day selector) and V209-A1-2b (the builder's
session-date and validation mode).

# Phase A1-A — the rule

### Task V209-A1-1: Weighted-depth and sustained-breadth entry; `SHOCK_SECTORS_FRAC` removed everywhere

**Model:** opus — rewires the detector's entry signal across `core/market` and `core/scanning` and makes a stored-record field required.

**Files:**
- Modify (v209 branch): `swingbot/core/market/shock.py` (`ShockThresholds` :33, `ShockReading` :82, `_sectors` :183, `measure` :238, `_sectors_needed` :302 deleted, `_depth_path` :306, new `_majority_path`, `entry_condition` :317)
- Modify (v209 branch): `swingbot/core/scanning/shock_scan.py` (`THRESHOLD_ATTRS` :35)
- Modify: `swingbot/config.py` (Market Shock section, `SHOCK_BREADTH_ENTER` :1583 through `SHOCK_VIX_RELIEF` :1609)
- Modify: `.env.example` (Market Shock block, ~:845-860)
- Modify (v209 branch): `tests/test_config_v209_keys.py`
- Modify (v209 branch): `tests/market/test_shock_measure.py`, `tests/market/test_shock_step_entry.py`, `tests/market/test_shock_step_exit.py`, `tests/db/test_market_shock_repository.py`, `tests/scanning/test_shock_pass.py`, `tests/scanning/test_shock_scan.py`

**Interfaces:**
- Consumes: the built v209 detector (V209-2..V209-6a).
- Produces: `ShockThresholds` field order `atr_k, breadth_enter, depth_frac=0.50, breadth_majority=0.50, breadth_fast, speed_enter, vix_spike_pct, vix_relief, breadth_reenter, breadth_exit, recovery_vix_off_high_pct, recovery_spy_retrace, min_dwell_min, recovery_min_dwell_min, min_names, vix_max_age_s, open_settle_min, quote_max_age_s` (18 fields, `sectors_frac` gone); `ShockReading.depth_frac: float | None`, right after `sectors_total`, required (no default); `_sectors(contribs, atr_k) -> tuple[int, int, float | None]` = `(down, total, depth_frac)`; `_majority_path(reading, th, relief) -> bool`; config `SHOCK_DEPTH_FRAC`, `SHOCK_BREADTH_MAJORITY`. V209-A1-4 replays with `ShockThresholds()`.

**Rules:**
- Spec A1 § Revised entry rule, verbatim values: `SHOCK_DEPTH_FRAC = 0.50`, `SHOCK_BREADTH_MAJORITY = 0.50`; relief lowers the **breadth** bar of the depth path and the majority bar, never the depth bar.
- `depth_frac` denominator: contributing names in sectors with ≥ 2 contributing members (spec at 50a970cb). `None` when there is no such sector; the depth path then cannot fire (`_meets(None, ...)` is already `False`).
- `sectors_down`/`sectors_total` are still computed and stored (display only). No Alembic revision: `depth_frac` rides in the reading's `doc` JSONB.
- `ShockReading.from_row` stays strict (a row without `depth_frac` raises `TypeError`). That is safe only because no row exists; Step 1 proves it.

- [ ] **Step 1: Prove no stored reading exists (read-only, then a local drop)**

Production (read-only, standing permission):

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -c \"SELECT to_regclass('market_shock_readings') IS NOT NULL\""
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c '^SHOCK_' .env || true"
```

Expected: `f` (v209 was never deployed, so the table does not exist) and `0`. A `t`, or any `SHOCK_` key, means v209 reached production unexpectedly: stop and report to the controller.

Local replica (run `/replicate-prod-db` first if this session has not; the engine reads `.env`, nothing is printed but counts):

```bash
python - <<'PYEOF'
from sqlalchemy import text
from swingbot.core.db.engine import get_engine
with get_engine().begin() as c:
    if c.execute(text("SELECT to_regclass('market_shock_readings')")).scalar() is None:
        print("market_shock_readings: absent")
    else:
        n = c.execute(text("SELECT count(*) FROM market_shock_readings")).scalar()
        c.execute(text("DELETE FROM market_shock_state"))
        c.execute(text("DELETE FROM market_shock_readings"))
        print(f"market_shock_readings: {n} local rows dropped")
PYEOF
```

Record both results in `.superpowers/sdd/progress.md` (V209-13 re-checks production before the deploy).

- [ ] **Step 2: Write the failing tests**

`tests/test_config_v209_keys.py` — in `V209_FIELDS` replace the `"SHOCK_SECTORS_FRAC": ("float", "0.6"),` row with these two rows, in this order; in `CAST_DEFAULTS` replace `"SHOCK_SECTORS_FRAC": 0.6,` with `"SHOCK_DEPTH_FRAC": 0.50, "SHOCK_BREADTH_MAJORITY": 0.50,`:

```python
    "SHOCK_DEPTH_FRAC": ("float", "0.50"),
    "SHOCK_BREADTH_MAJORITY": ("float", "0.50"),
```

Replace `test_nineteen_fields_one_mode_plus_eighteen_thresholds` and add two tests:

```python
def test_twenty_fields_one_mode_plus_nineteen_thresholds():
    # A1: SHOCK_SECTORS_FRAC removed, SHOCK_DEPTH_FRAC and SHOCK_BREADTH_MAJORITY added
    assert len(V209_FIELDS) == 20
    assert set(V209_FIELDS) == set(CAST_DEFAULTS)


def test_sectors_frac_is_gone_from_the_schema_and_the_example():
    assert not any(f.attr == "SHOCK_SECTORS_FRAC" for f in config.FIELDS)
    assert all("SHOCK_SECTORS_FRAC" not in (f.help or "") for f in config.FIELDS)
    assert "SHOCK_SECTORS_FRAC" not in (REPO / ".env.example").read_text(encoding="utf-8")


def test_a_stale_sectors_frac_env_key_is_ignored(monkeypatch):
    monkeypatch.setenv("SHOCK_SECTORS_FRAC", "0.6")
    try:
        config._apply_env()
        assert config.SHOCK_DEPTH_FRAC == 0.50 and config.SHOCK_BREADTH_MAJORITY == 0.50
    finally:
        monkeypatch.undo()
        config._apply_env()
```

`tests/scanning/test_shock_scan.py` — in `test_thresholds_map_every_field_and_keep_ints_int`, `== 17` becomes `== 18`, and append:

```python
    assert "SHOCK_SECTORS_FRAC" not in shock_scan.THRESHOLD_ATTRS.values()
    monkeypatch.setattr(config, "SHOCK_DEPTH_FRAC", 0.55)
    monkeypatch.setattr(config, "SHOCK_BREADTH_MAJORITY", 0.6)
    th = shock_scan.thresholds_from_config()
    assert (th.depth_frac, th.breadth_majority) == (0.55, 0.6)
```

`tests/market/test_shock_measure.py`:
- `_full_reading` base: add `depth_frac=0.6,` right after `sectors_total=6,`.
- `test_threshold_defaults_equal_the_config_defaults`: `sectors_frac=0.6` becomes `depth_frac=0.50, breadth_majority=0.50`.
- `test_reading_field_order_is_the_ledger_contract`: insert `"depth_frac"` between `"sectors_total"` and `"breadth_speed"` (21 names).
- `test_sectors_need_two_contributing_members_and_use_the_median`: append `assert reading.depth_frac == pytest.approx(3 / 5)` (Semis' 3 names are down, Banks' 2 are not; B1 and N1 sit outside the denominator).
- `test_empty_watchlist_is_insufficient_with_no_breadth`: append `assert reading.depth_frac is None`.
- Add (the file's `_row(ticker, ratio, sector)` and `_snap(names)` helpers are used as the sectors test uses them):

```python
def test_depth_frac_weights_sectors_by_their_names():
    # one heavy sector down, two light ones flat: 1 of 3 sectors, but 6 of 10 names
    names = ([_row(f"T{i}", -1.5, "Tech") for i in range(6)]
             + [_row("B1", 0.0, "Banks"), _row("B2", 0.1, "Banks"),
                _row("E1", 0.0, "Energy"), _row("E2", -0.2, "Energy")])
    reading = measure(_snap(names), None, TH)
    assert (reading.sectors_down, reading.sectors_total) == (1, 3)
    assert reading.depth_frac == pytest.approx(0.6)


def test_depth_frac_is_none_without_a_two_member_sector():
    names = [_row("A", -2.0, "Semis"), _row("B", -2.0, "Energy"), _row("C", -2.0, None)]
    assert measure(_snap(names), None, TH).depth_frac is None


def test_a_row_without_depth_frac_is_refused():
    row = _full_reading().as_row()
    del row["depth_frac"]
    with pytest.raises(TypeError):
        ShockReading.from_row(row)
```

`tests/market/test_shock_step_entry.py`:
- `_reading` base: add `depth_frac=0.0,` right after `sectors_total=5,`.
- `DEPTH = dict(breadth_frac=0.40, sectors_down=3, sectors_total=5, depth_frac=0.6)`; add `MAJORITY = dict(breadth_frac=0.50, depth_frac=0.0)` beside it.
- `test_two_consecutive_qualifying_readings_enter_shock`: parameters `[DEPTH, MAJORITY, FAST]`, ids `["depth", "majority", "fast"]`.
- Replace the `test_entry_condition_paths` parameter list:

```python
@pytest.mark.parametrize("over, expected", [
    (dict(breadth_frac=0.40, depth_frac=0.50), True),                     # weighted depth at both bars
    (dict(breadth_frac=0.40, depth_frac=0.49), False),
    (dict(breadth_frac=0.39, depth_frac=1.0), False),
    (dict(breadth_frac=0.45, depth_frac=None), False),                    # no sector to judge depth
    (dict(breadth_frac=0.45, sectors_down=5, sectors_total=5, depth_frac=0.40), False),  # the count no longer counts
    (dict(breadth_frac=0.50, depth_frac=None), True),                     # sustained breadth alone
    (dict(breadth_frac=0.49, depth_frac=0.0, breadth_speed=None), False),
    (dict(breadth_frac=0.25, breadth_speed=0.10), True),                  # fast path unchanged
    (dict(breadth_frac=0.25, breadth_speed=0.09), False),
    (dict(breadth_frac=0.24, breadth_speed=0.20), False),
    (dict(breadth_frac=0.30, breadth_speed=None), False),
    (dict(breadth_frac=None, depth_frac=1.0), False),
    (dict(breadth_frac=0.05, spy_atr_move=-4.0, qqq_atr_move=-4.0), False),  # index moves never trigger
])
def test_entry_condition_paths(over, expected):
    assert entry_condition(_reading(**over), TH) is expected
```

- Replace `test_vix_spike_lowers_both_breadth_bars`:

```python
@pytest.mark.parametrize("chg, expected", [(15.0, True), (14.9, False), (None, False)])
def test_vix_spike_lowers_every_breadth_bar_but_not_the_depth_bar(chg, expected):
    depth = _reading(breadth_frac=7 / 20, depth_frac=0.6, vix_chg_pct=chg)
    majority = _reading(breadth_frac=0.45, depth_frac=0.0, vix_chg_pct=chg)
    fast = _reading(breadth_frac=0.20, breadth_speed=0.10, vix_chg_pct=chg)
    assert entry_condition(depth, TH) is expected
    assert entry_condition(majority, TH) is expected
    assert entry_condition(fast, TH) is expected
    shallow = _reading(breadth_frac=0.40, depth_frac=0.46, vix_chg_pct=chg)
    assert entry_condition(shallow, TH) is False
```

- Replace `test_hysteresis_band_holds_normal`:

```python
@pytest.mark.parametrize("between", [
    dict(breadth_frac=0.30, depth_frac=0.6),       # deep, but under the depth path's breadth bar
    dict(breadth_frac=0.45, depth_frac=0.40),      # under the majority bar and shallow
], ids=["deep-narrow", "wide-shallow"])
def test_hysteresis_band_holds_normal(between):
    state = _run(ShockState(), *[_reading(15 * i, **between) for i in range(4)])
    assert state.label == "NORMAL" and state.entry_streak == 0
```

`tests/market/test_shock_step_exit.py`:
- `_reading` base: add `depth_frac=0.0,` after `sectors_total=5,`.
- `test_overnight_second_leg_down_stays_shock`: the `_day1(...)` call gains `depth_frac=0.6`.
- `depth = dict(breadth_frac=0.45, sectors_down=4, sectors_total=5)` (~:180) gains `depth_frac=0.6`.

`tests/db/test_market_shock_repository.py` — `_reading` base gains `depth_frac=0.6,` after `sectors_total=5,`; the test that reads `latest_reading()` back gains `assert got["depth_frac"] == 0.6` (use that test's own variable name).

`tests/scanning/test_shock_pass.py` — after `assert (reading["sectors_down"], reading["sectors_total"]) == (1, 1)` (~:96): `assert reading["depth_frac"] == pytest.approx(1.0)`.

- [ ] **Step 3: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/market/test_shock_measure.py
python scripts/dev/testrun.py file tests/market/test_shock_step_entry.py
python scripts/dev/testrun.py file tests/test_config_v209_keys.py
```

Expected: FAIL (`TypeError: ... unexpected keyword argument 'depth_frac'`, the 20-field count, missing config attrs).

- [ ] **Step 4: Implement the rule in `swingbot/core/market/shock.py`**

- `ShockThresholds`: delete `sectors_frac: float = 0.6`; insert `depth_frac: float = 0.50` and `breadth_majority: float = 0.50` in its place.
- `ShockReading`: add `depth_frac: float | None` directly after `sectors_total: int`.
- `_sectors(contribs, atr_k) -> tuple[int, int, float | None]`: same grouping; `names = sum(len(m) for m in groups)`; `in_down = sum(len(m) for m in groups if _is_down(statistics.median(m), atr_k))`; return `(down, len(groups), in_down / names if names else None)`.
- `measure`: `down, total, depth = _sectors(contribs, th.atr_k)` and `depth_frac=depth,` after `sectors_total=total,`.
- Delete `_sectors_needed`. The entry block becomes:

```python
def _depth_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    """A1 weighted depth: enough names sit in down sectors, and breadth is wide."""
    return (_meets(reading.depth_frac, th.depth_frac)
            and _meets(reading.breadth_frac, th.breadth_enter - relief))


def _majority_path(reading: ShockReading, th: ShockThresholds, relief: float) -> bool:
    """A1 sustained breadth: a majority of names down, no depth or speed needed."""
    return _meets(reading.breadth_frac, th.breadth_majority - relief)


def entry_condition(reading: ShockReading, th: ShockThresholds = ShockThresholds()) -> bool:
    """NORMAL -> SHOCK on this one reading (A1: weighted depth, sustained breadth or speed)."""
    relief = _relief(reading, th)
    return (_depth_path(reading, th, relief) or _majority_path(reading, th, relief)
            or _fast_path(reading, th, relief))
```

- `math` stays imported only while used (`git grep -n "math\." swingbot/core/market/shock.py`).

- [ ] **Step 5: Config, key map and example**

`swingbot/core/scanning/shock_scan.py` `THRESHOLD_ATTRS`: replace `"sectors_frac": "SHOCK_SECTORS_FRAC",` with `"depth_frac": "SHOCK_DEPTH_FRAC", "breadth_majority": "SHOCK_BREADTH_MAJORITY",`.

`swingbot/config.py`: delete the `SHOCK_SECTORS_FRAC` Field and add the two below in its place, copying every other keyword argument (hot-reload, search class, sensitivity) from the neighbouring `SHOCK_BREADTH_FAST` Field. `SHOCK_BREADTH_ENTER` gets the new title and help shown:

```python
    Field("SHOCK_BREADTH_ENTER", "SHOCK_BREADTH_ENTER", "Market Shock",
          "Breadth to enter SHOCK (with weighted depth)",
          type="float", default="0.40", min=0.05, max=1.0, step=0.05,
          help="v209 A1. NORMAL -> SHOCK when this share of watchlist equities is down and at "
               "least SHOCK_DEPTH_FRAC of the sectored names sit in down sectors, on two "
               "consecutive readings."),
    Field("SHOCK_DEPTH_FRAC", "SHOCK_DEPTH_FRAC", "Market Shock",
          "Share of sectored names in down sectors",
          type="float", default="0.50", min=0.05, max=1.0, step=0.05,
          help="v209 A1. Names in sectors with >= 2 contributing members whose median move is "
               "down, over all names in such sectors. Frozen at 0.50 by the A1 pre-registration."),
    Field("SHOCK_BREADTH_MAJORITY", "SHOCK_BREADTH_MAJORITY", "Market Shock",
          "Breadth to enter SHOCK on its own",
          type="float", default="0.50", min=0.05, max=1.0, step=0.05,
          help="v209 A1. NORMAL -> SHOCK when this share of watchlist equities is down on two "
               "consecutive readings, with no depth or speed needed. Frozen at 0.50 by A1."),
```

`SHOCK_VIX_SPIKE_PCT` help: "lowers both entry breadth bars" becomes "lowers every entry breadth bar". `SHOCK_VIX_RELIEF` help becomes `"v209. Subtracted from SHOCK_BREADTH_ENTER, SHOCK_BREADTH_MAJORITY and SHOCK_BREADTH_FAST on a VIX spike (never from SHOCK_DEPTH_FRAC)."`

`.env.example`: delete `SHOCK_SECTORS_FRAC=0.6`; the block becomes

```
# NORMAL -> SHOCK (v209 A1): breadth with weighted sector depth, breadth
# alone at a majority, or breadth with speed, on two consecutive readings at
# least SHOCK_OPEN_SETTLE_MIN after the open.
SHOCK_BREADTH_ENTER=0.40
SHOCK_DEPTH_FRAC=0.50
SHOCK_BREADTH_MAJORITY=0.50
SHOCK_BREADTH_FAST=0.25
SHOCK_SPEED_ENTER=0.10

# A VIX day change at or above SHOCK_VIX_SPIKE_PCT lowers every breadth bar
# by SHOCK_VIX_RELIEF.
```

Last check, expected to print nothing:

```bash
git grep -n "SHOCK_SECTORS_FRAC\|sectors_frac\|_sectors_needed" -- swingbot tests .env.example scripts
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/market/test_shock_measure.py
python scripts/dev/testrun.py file tests/market/test_shock_step_entry.py
python scripts/dev/testrun.py file tests/market/test_shock_step_exit.py
python scripts/dev/testrun.py file tests/scanning/test_shock_scan.py
python scripts/dev/testrun.py file tests/scanning/test_shock_pass.py
python scripts/dev/testrun.py file tests/test_config_v209_keys.py
python scripts/dev/testrun.py file tests/db/test_market_shock_repository.py
python scripts/dev/complexity_gate.py
```

Expected: each file `0 failed`, `0 xfailed`; the gate reports no new or grown function. Do **not** run `tests/market/test_shock_replay_2026_11_05.py` here: replaying the new rule over any recorded day is the acceptance run, which only V209-A1-4 performs, after the validation list is frozen.

- [ ] **Step 7: Commit (two scoped commits, one task)**

```bash
git add swingbot/core/market/shock.py tests/market/test_shock_measure.py tests/market/test_shock_step_entry.py tests/market/test_shock_step_exit.py tests/db/test_market_shock_repository.py tests/scanning/test_shock_pass.py
git commit -m "feat(shock): A1 entry rule -- weighted depth_frac and sustained-breadth paths replace the sector count"
git add swingbot/core/scanning/shock_scan.py swingbot/config.py .env.example tests/test_config_v209_keys.py tests/scanning/test_shock_scan.py
git commit -m "feat(config): A1 -- SHOCK_DEPTH_FRAC and SHOCK_BREADTH_MAJORITY replace SHOCK_SECTORS_FRAC"
```

# Phase A1-B — the validation tooling

### Task V209-A1-2: Validation-day selector and the frozen day-list shape

**Model:** opus — statistical selection code that fixes the sample a one-shot gate is scored on.

**Files:**
- Create: `scripts/data/shock_validation_days.py`
- Create: `tests/scripts/test_shock_validation_days.py` (suite of `tests/scripts/`; no `suites.toml` change)

**Interfaces:**
- Consumes: nothing from other A1 tasks. Reads `data/market_data_pit/daily/SPY.csv`, `data/market_data_pit/daily/QQQ.csv` (`Date,Open,High,Low,Close,Volume`) and `market_data/vix/VIX_daily.csv` (`Date,Open,High,Low,Close`) under a data root that defaults to the **main repo** (the worktree has no data dirs).
- Produces (V209-A1-2b, V209-A1-3, V209-A1-4 rely on it):
  - constants `WINDOW = (date(2023, 1, 2), date(2025, 12, 31))`, `SEED = 209`, `SPACING = 5`, `YEAR_CAP = 4`, `CLASS_ORDER = ("shock", "hard", "rotation", "calm")`, `CLASS_SIZES = {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}`, `DEFAULT_OUT = ROOT / "tests/fixtures/shock_replay/validation_days.json"`
  - `main_repo_root() -> Path`; `load_daily(path: Path) -> pd.DataFrame` (index `datetime.date`, float columns `Open`, `Close`, sorted, duplicate dates dropped keeping the last)
  - `day_table(spy, qqq, vix) -> pd.DataFrame` indexed by `date`, window only, columns `session_no, spy_prev_close, spy_open, spy_close, spy_ret, qqq_ret, vix_prev_close, vix_open, vix_close, vix_chg` (returns in %)
  - `pick_shock(table, n=6, spacing=5) -> list[date]`, `pick_hard(table, taken: set, n=4) -> list[date]`, `pick_rotation(table, taken: set, n=4) -> list[date]`, `calm_pool(table, taken: set) -> list[date]`, `pick_calm(table, taken: set, n=12, seed=209, year_cap=4) -> list[date]`
  - `select_days(table) -> dict`, the day-list JSON:
    `{"window": ["2023-01-02", "2025-12-31"], "seed": 209, "rules": str, "classes": {"shock": [iso, ...], "hard": [...], "rotation": [...], "calm": [...]}, "days": {iso: {"class": str, "spy_prev_close", "spy_open", "spy_close", "spy_ret", "qqq_ret", "vix_prev_close", "vix_open", "vix_close", "vix_chg": float}}}` (floats rounded to 4 dp; class lists in pick order)
  - `main(argv=None) -> int`: `--data-root` (default `main_repo_root()`), `--out` (default `DEFAULT_OUT`); exit 2 without writing when `--out` exists.

**Rules (spec A1 § Validation set, verbatim; precedence fixed by this plan):**
- Close-to-close moves: each series' prior close is its own previous row, taken **before** restricting to the window (2023-01-03's prior close is 2022-12-30's). Only dates present in all three series are selectable. `session_no` is the row position in the full SPY calendar.
- Shock (6): largest SPY drops (`spy_ret < 0` only) in order (ties by date), skipping a day whose `|session_no − chosen|` ≤ 5 for any chosen day.
- Hard (4): `−2.5 ≤ spy_ret ≤ −1.5` and `vix_chg < 15`, largest drops first.
- Rotation (4): `spy_ret ≥ −1.5` and `vix_chg < 15`, most negative `qqq_ret − spy_ret` first.
- Calm (12): `|spy_ret| < 0.5` and `vix_chg < 3`; pool sorted by date, `random.Random(209).shuffle(pool)`, taken in order skipping a day whose year already holds 4.
- Classes are disjoint, picked in `CLASS_ORDER`; each later class skips days an earlier class took. A class that cannot be filled raises `ValueError` naming it (never a short list).
- The selector reads daily rows only, never a detector output or a fixture.

- [ ] **Step 1: Write the failing tests**

`tests/scripts/test_shock_validation_days.py`:

```python
"""v209 A1: the outcome-blind validation-day selector (spec § Amendment A1)."""
import json
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import shock_validation_days as sv  # noqa: E402

PRICE_COLS = ("spy_prev_close", "spy_open", "spy_close", "vix_prev_close", "vix_open", "vix_close")


def _table(rows):
    """rows: (date, spy_ret, qqq_ret, vix_chg); session_no is the row order."""
    df = pd.DataFrame({"session_no": range(len(rows)),
                       "spy_ret": [r[1] for r in rows], "qqq_ret": [r[2] for r in rows],
                       "vix_chg": [r[3] for r in rows]},
                      index=[r[0] for r in rows])
    for col in PRICE_COLS:
        df[col] = 100.0
    return df


def _bdays(start, n):
    return [d.date() for d in pd.bdate_range(start, periods=n)]


def _csv(path, rows, volume=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "Date,Open,High,Low,Close" + (",Volume" if volume else "")
    lines = [head] + [f"{d},{o},{max(o, c)},{min(o, c)},{c}" + (",1" if volume else "")
                      for d, o, c in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_constants_are_the_pre_registered_values():
    assert sv.WINDOW == (date(2023, 1, 2), date(2025, 12, 31))
    assert (sv.SEED, sv.SPACING, sv.YEAR_CAP) == (209, 5, 4)
    assert sv.CLASS_ORDER == ("shock", "hard", "rotation", "calm")
    assert sv.CLASS_SIZES == {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}


def test_load_daily_reads_both_csv_shapes(tmp_path):
    _csv(tmp_path / "s.csv", [("2023-01-04", 99.0, 101.0), ("2023-01-03", 100.0, 98.0)])
    _csv(tmp_path / "v.csv", [("2023-01-03", 20.0, 21.0)], volume=False)
    spy = sv.load_daily(tmp_path / "s.csv")
    assert list(spy.index) == [date(2023, 1, 3), date(2023, 1, 4)]
    assert spy.loc[date(2023, 1, 4), "Close"] == 101.0
    assert sv.load_daily(tmp_path / "v.csv").loc[date(2023, 1, 3), "Open"] == 20.0


def test_day_table_takes_prior_closes_from_before_the_window_and_needs_all_three(tmp_path):
    spy = [("2022-12-30", 100.0, 100.0), ("2023-01-03", 99.0, 98.0), ("2023-01-04", 98.0, 99.0)]
    qqq = [("2022-12-30", 200.0, 200.0), ("2023-01-03", 199.0, 194.0), ("2023-01-04", 194.0, 196.0)]
    vix = [("2022-12-30", 20.0, 20.0), ("2023-01-03", 21.0, 22.0)]           # 01-04 missing
    for name, rows in (("spy", spy), ("qqq", qqq), ("vix", vix)):
        _csv(tmp_path / f"{name}.csv", rows)
    table = sv.day_table(*(sv.load_daily(tmp_path / f"{n}.csv") for n in ("spy", "qqq", "vix")))
    assert list(table.index) == [date(2023, 1, 3)]
    row = table.loc[date(2023, 1, 3)]
    assert row["spy_ret"] == pytest.approx(-2.0) and row["qqq_ret"] == pytest.approx(-3.0)
    assert row["vix_chg"] == pytest.approx(10.0) and row["session_no"] == 1
    assert (row["spy_prev_close"], row["spy_open"], row["vix_open"]) == (100.0, 99.0, 21.0)


def test_shock_days_skip_anything_within_five_sessions():
    days = _bdays("2024-01-02", 40)
    rets = {0: -5.0, 5: -4.5, 6: -4.0, 12: -3.0, 20: -2.9, 25: -2.6, 30: -2.8, 39: -2.7}
    table = _table([(d, rets.get(i, 0.1), 0.1, 0.0) for i, d in enumerate(days)])
    assert sv.pick_shock(table, n=6, spacing=5) == [days[i] for i in (0, 6, 12, 20, 30, 39)]


def test_hard_negatives_are_the_largest_band_drops_with_calm_vix():
    days = _bdays("2024-03-01", 9)
    spy = [-2.6, -2.5, -2.0, -1.9, -1.8, -1.7, -1.6, -1.5, -1.4]
    vix = [5.0, 5.0, 20.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    table = _table([(d, s, 0.0, v) for d, s, v in zip(days, spy, vix)])
    assert sv.pick_hard(table, set(), n=4) == [days[1], days[3], days[4], days[5]]
    assert sv.pick_hard(table, {days[1]}, n=4) == [days[3], days[4], days[5], days[6]]


def test_rotation_is_the_most_negative_qqq_shortfall_under_the_filters():
    days = _bdays("2024-05-01", 8)
    rows = [(days[0], 0.2, -1.5, 5.0),    # -1.7
            (days[1], -1.6, -4.0, 5.0),   # SPY below -1.5: out
            (days[2], -1.0, -2.5, 16.0),  # VIX +16 %: out
            (days[3], 0.0, -1.0, 0.0),    # -1.0
            (days[4], -1.5, -2.0, 0.0),   # -0.5, SPY exactly -1.5 is in
            (days[5], 0.5, 0.1, 0.0),     # -0.4
            (days[6], 0.3, -0.9, 0.0),    # -1.2
            (days[7], 0.1, 0.5, 0.0)]     # +0.4
    table = _table(rows)
    assert sv.pick_rotation(table, set(), n=4) == [days[0], days[6], days[3], days[4]]
    assert sv.pick_rotation(table, {days[0]}, n=4) == [days[6], days[3], days[4], days[5]]


def test_calm_pool_filters_and_the_draw_is_seeded_with_a_year_cap():
    days = _bdays("2023-01-03", 780)
    rows = [(d, 0.1, 0.1, 0.0) for d in days]
    rows[1] = (days[1], 0.5, 0.1, 0.0)      # |SPY| not < 0.5
    rows[2] = (days[2], -0.2, 0.1, 3.0)     # VIX change not < +3
    table = _table(rows)
    pool = sv.calm_pool(table, {days[3]})
    assert days[1] not in pool and days[2] not in pool and days[3] not in pool
    assert pool == sorted(pool)
    order, expected, per_year = list(pool), [], {}
    random.Random(209).shuffle(order)
    for d in order:
        if per_year.get(d.year, 0) < 4:
            expected.append(d)
            per_year[d.year] = per_year.get(d.year, 0) + 1
        if len(expected) == 12:
            break
    picked = sv.pick_calm(table, {days[3]})
    assert picked == expected and len(picked) == 12
    assert max(sum(d.year == y for d in picked) for y in {d.year for d in picked}) <= 4


def _three_years():
    days = _bdays("2023-01-03", 760)
    rows = {i: (d, 0.1, 0.1, 0.0) for i, d in enumerate(days)}
    for i in (10, 20, 30, 40, 50):
        rows[i] = (days[i], -4.0, -4.0, 30.0)
    rows[60] = (days[60], -2.0, -2.0, 5.0)              # a band drop that is also a top-6 drop
    for i in (70, 80, 90, 100, 110):
        rows[i] = (days[i], -1.6, -1.6, 5.0)
    for i in range(120, 125):
        rows[i] = (days[i], 0.0, -2.0, 0.0)              # rotation and calm-eligible
    return days, _table([rows[i] for i in range(len(days))])


def test_classes_are_disjoint_and_taken_in_order():
    days, table = _three_years()
    out = sv.select_days(table)
    cls = out["classes"]
    assert days[60].isoformat() in cls["shock"] and days[60].isoformat() not in cls["hard"]
    assert cls["hard"] == [days[i].isoformat() for i in (70, 80, 90, 100)]
    assert cls["rotation"] == [days[i].isoformat() for i in (120, 121, 122, 123)]
    assert {k: len(v) for k, v in cls.items()} == sv.CLASS_SIZES
    every = [d for v in cls.values() for d in v]
    assert len(every) == len(set(every)) == 26
    assert set(out["days"]) == set(every)
    assert all(out["days"][d]["class"] == k for k, v in cls.items() for d in v)
    assert out["window"] == ["2023-01-02", "2025-12-31"] and out["seed"] == 209


def test_a_class_that_cannot_be_filled_raises():
    table = _table([(d, 0.1, 0.1, 0.0) for d in _bdays("2023-01-03", 700)])
    with pytest.raises(ValueError, match="shock"):
        sv.select_days(table)


def test_main_writes_the_list_once_and_refuses_to_overwrite(tmp_path, monkeypatch):
    rows = [("2022-12-30", 1.0, 1.0), ("2023-01-03", 1.0, 1.0)]
    _csv(tmp_path / "data/market_data_pit/daily/SPY.csv", rows)
    _csv(tmp_path / "data/market_data_pit/daily/QQQ.csv", rows)
    _csv(tmp_path / "market_data/vix/VIX_daily.csv", rows, volume=False)
    frozen = {"window": ["2023-01-02", "2025-12-31"], "seed": 209, "rules": "x",
              "classes": {}, "days": {}}
    monkeypatch.setattr(sv, "select_days", lambda table: frozen)
    out = tmp_path / "list.json"
    assert sv.main(["--data-root", str(tmp_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == frozen
    out.write_text("{}", encoding="utf-8")
    assert sv.main(["--data-root", str(tmp_path), "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "{}"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_shock_validation_days.py`
Expected: FAIL (`ModuleNotFoundError: shock_validation_days`).

- [ ] **Step 3: Implement `scripts/data/shock_validation_days.py`**

Module docstring: what it picks, from which three CSVs, that the output is frozen once committed (spec A1), and the usage line `python scripts/data/shock_validation_days.py [--data-root <main repo>] [--out <path>]`. Same `ROOT`/`sys.path` preamble as `build_shock_replay_fixture.py` (no swingbot import is needed). Paths as module constants: `SPY_CSV = "data/market_data_pit/daily/SPY.csv"`, `QQQ_CSV = "data/market_data_pit/daily/QQQ.csv"`, `VIX_CSV = "market_data/vix/VIX_daily.csv"`.

- `main_repo_root()`: `git rev-parse --path-format=absolute --git-common-dir` (run with `cwd=ROOT`), return its parent (`<main>/.git` → `<main>`).
- `load_daily`: `pd.read_csv`, `Date` parsed to `date`, keep `Open`, `Close` as float.
- `day_table`: per series `ret = (Close / Close.shift(1) - 1) * 100`, computed on the full series; SPY gives `session_no = range(len(spy))`; inner-join the three on date, drop rows with any NaN, keep `WINDOW[0] <= d <= WINDOW[1]`.
- Pickers: one small function each, sorting with an explicit `(key, date)` tuple so ties fall to the earlier date; `pick_hard`/`pick_rotation`/`pick_calm` skip `taken`.
- `select_days`: walk `CLASS_ORDER` with a dispatch dict `{"shock": lambda t, taken: pick_shock(t), ...}`, accumulating `taken`; `ValueError(f"{cls}: {len(got)} of {n} days")` on a short class; `rules` is a one-paragraph restatement of the Rules bullets above; `days[iso]` holds the table row's ten columns minus `session_no`, rounded to 4 dp, plus `class`.
- `main`: refuse an existing `--out` (print `frozen: <path> exists; the A1 day list is never regenerated` to stderr, return 2); else write `json.dumps(out, indent=1) + "\n"` (create the parent dir), print each class with its dates, return 0.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scripts/test_shock_validation_days.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`, `0 xfailed`; no function at complexity ≥ 15. Do **not** run the CLI against the real CSVs here: freezing the list is V209-A1-3's first step.

- [ ] **Step 5: Commit**

```bash
git add scripts/data/shock_validation_days.py tests/scripts/test_shock_validation_days.py
git commit -m "feat(scripts): A1 validation-day selector from daily SPY, QQQ and VIX"
```

### Task V209-A1-2b: Fixture builder: session date, DST bounds, daily-VIX path, validation mode, gz, no synthetic

**Model:** opus — no-lookahead territory (which bar a fixture step may see) and the data a one-shot gate is scored on.

**Files:**
- Modify (v209 branch): `scripts/data/build_shock_replay_fixture.py` (constants :45-61, `step_times` :72, `fixture_step` :103, `load_or_fetch` :170, `_fetch_all`, `_parse` :233, `main` :261)
- Modify (v209 branch): `tests/scripts/test_build_shock_replay_fixture.py`
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`, beside the hooks-fixture row ~:303)
- Modify: `tests/dev/test_select_tests.py`

**Interfaces:**
- Consumes: V209-A1-2's day-list JSON (`days[iso]` keys `class`, `spy_prev_close`, `spy_open`, `spy_close`, `vix_prev_close`, `vix_open`, `vix_close`); `swingbot.core.market.session.US_MARKET_TZ`, `RTH_OPEN`, `session_close(d)`; `shock_scan.build_snapshot` (its `minutes_since_open` is already DST-aware); `alpaca_history.fetch.fetch_raw(provider, ticker, timeframe, start: date, end: datetime, *, limiter)`.
- Produces (V209-A1-3 runs it, V209-A1-4 reads its output):
  - `DAILY_LOOKBACK = timedelta(days=127)` (2026-11-05 − 127 d = 2026-07-01, V209-12's window, so the 11-05 path is unchanged); `VALIDATION_OUT = ROOT / "tests/fixtures/shock_replay"`; `VALIDATION_CACHE = ROOT / "market_data/shock_replay"` (gitignored, one sub-dir per day)
  - `session_bounds(day: date) -> tuple[datetime, datetime]` (UTC open and close; `OPEN_UTC, CLOSE_UTC = session_bounds(SESSION)`)
  - `step_times(day: date = SESSION) -> list[datetime]`
  - `daily_vix_path(t, open_utc, close_utc, info: dict) -> dict` (`{"level", "chg_pct"}`, 4 dp)
  - `fixture_step(t, daily, bars15, sector_of, vix: dict | None = None) -> dict` (`None` keeps the 11-05 tape path `vix_path(t)`)
  - `load_or_fetch(ticker, provider, limiter, cache_dir, day: date = SESSION)`
  - `fixture_tickers(path: Path) -> list[str]` (sorted tickers of every step's `names` in the 11-05 fixture: the frozen 87-name watchlist)
  - `build_day_fixture(day, info, tickers, *, provider, limiter, cache_root) -> dict`; `unbuildable_fixture(day, info, note) -> dict`
  - `write_gz(path, payload)` (atomic, byte-deterministic: `mtime=0`, compact JSON); `read_gz(path) -> dict`
  - `run_validation(days_file, tickers, *, provider, limiter, cache_root, out_dir) -> list[str]` (ISO days written this run)
  - CLI: `--validation-days PATH [--out-dir DIR] [--cache-dir DIR] [--tickers A,B]`, and `--validation-days PATH --unbuildable YYYY-MM-DD --reason TEXT`
  - Day fixture: `{"source": "alpaca" | "unbuildable", "session_date": iso, "class": str, "open_utc": iso, "close_utc": iso, "vix_interpolated": true, "spy_daily": {"prev_close", "open", "close"}, "note": str, "steps": [<V209-12 step shape>]}`, at `tests/fixtures/shock_replay/<iso>.json.gz`

**Rules:**
- **No lookahead:** daily bars end at `datetime(day, 00:00, UTC)` (strictly before the session); 15-minute bars run `day` .. session close; `last_at` (unchanged) only sees bars finished by the step.
- **Never synthetic in validation mode.** Fewer than `ShockThresholds().min_names` equities with both bar sets ⇒ `unbuildable_fixture` (a data answer, written). A raised fetch error propagates and aborts the run with no fixture for that day (a restart resumes from the cache). Missing Alpaca keys ⇒ exit 2, nothing written. A day that keeps raising is recorded by the operator with `--unbuildable` (V209-A1-3), never dropped.
- **Checkpoints:** raw bars per (day, ticker) at `<cache>/<iso>/<TICKER>.json`; a day's gz is written only after every ticker was attempted; a day whose gz exists is skipped.
- VIX per step (spec A1): `chg` linear from `(vix_open / vix_prev_close − 1) × 100` at the open to `(vix_close / vix_prev_close − 1) × 100` at the close, clamped outside; `level = vix_prev_close × (1 + chg / 100)`.
- The 11-05 path (no `--validation-days`) keeps its behaviour and output byte for byte; its committed fixture is not rebuilt.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_build_shock_replay_fixture.py` (add `import gzip` and `from datetime import date` to the imports):

```python
D_EDT = date(2025, 7, 15)
D_HALF = date(2024, 11, 29)                      # day after Thanksgiving: 13:00 ET close
INFO = {"class": "shock", "spy_prev_close": 600.0, "spy_open": 590.0, "spy_close": 580.0,
        "vix_prev_close": 20.0, "vix_open": 22.0, "vix_close": 25.0}


def U(d, h, m):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


def test_session_bounds_follow_dst_and_half_days():
    assert bsr.session_bounds(date(2026, 11, 5)) == (T(14, 30), T(21, 0))
    assert bsr.session_bounds(D_EDT) == (U(D_EDT, 13, 30), U(D_EDT, 20, 0))
    assert bsr.session_bounds(D_HALF) == (U(D_HALF, 14, 30), U(D_HALF, 18, 0))
    assert (bsr.OPEN_UTC, bsr.CLOSE_UTC) == (T(14, 30), T(21, 0))


def test_step_times_take_a_session_date():
    steps = bsr.step_times(D_EDT)
    assert (steps[0], steps[-1], len(steps)) == (U(D_EDT, 13, 45), U(D_EDT, 20, 0), 26)
    half = bsr.step_times(D_HALF)
    assert (half[0], half[-1], len(half)) == (U(D_HALF, 14, 45), U(D_HALF, 18, 0), 14)


def test_daily_vix_path_ramps_from_the_open_change_to_the_close_change():
    o, c = bsr.session_bounds(D_EDT)
    assert bsr.daily_vix_path(o, o, c, INFO) == {"level": 22.0, "chg_pct": 10.0}
    assert bsr.daily_vix_path(U(D_EDT, 16, 45), o, c, INFO) == {"level": 23.5, "chg_pct": 17.5}
    assert bsr.daily_vix_path(c, o, c, INFO) == {"level": 25.0, "chg_pct": 25.0}
    assert bsr.daily_vix_path(c + timedelta(hours=1), o, c, INFO)["chg_pct"] == 25.0


def test_a_step_takes_an_explicit_vix(monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    daily = {"AAA": bsr.to_daily(_daily(100.0)), "SPY": bsr.to_daily(_daily(500.0))}
    bars = {"AAA": _m15([99.0, 97.0]), "SPY": _m15([498.0, 495.0])}
    vix = {"level": 30.0, "chg_pct": 40.0}
    assert bsr.fixture_step(T(15, 0), daily, bars, {"AAA": "Tech"}, vix=vix)["vix"] == vix


def _daily_before(day, close=100.0, n=30):
    idx = pd.date_range(end=pd.Timestamp(day) - pd.Timedelta(days=1), periods=n, freq="B", tz=UTC)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1000}, index=idx)


class RecordingFetch:
    """Stands in for bsr.fetch_raw; records every call."""

    def __init__(self, day):
        self.day, self.calls = day, []

    def __call__(self, provider, ticker, timeframe, start, end, *, limiter):
        self.calls.append((ticker, timeframe, start, end))
        if timeframe == "daily":
            return _daily_before(self.day)
        return _m15([99.0, 97.0, 95.0, 94.0], start=bsr.session_bounds(self.day)[0])


def test_validation_fetch_is_per_day_and_ticker_and_daily_bars_end_before_the_session(
        tmp_path, monkeypatch):
    rec = RecordingFetch(D_EDT)
    monkeypatch.setattr(bsr, "fetch_raw", rec)
    bsr.load_or_fetch("AAA", None, None, tmp_path / D_EDT.isoformat(), day=D_EDT)
    assert rec.calls == [
        ("AAA", "daily", D_EDT - timedelta(days=127), U(D_EDT, 0, 0)),
        ("AAA", "15min", D_EDT, U(D_EDT, 20, 0))]
    assert (tmp_path / "2025-07-15" / "AAA.json").exists()
    bsr.load_or_fetch("AAA", None, None, tmp_path / D_EDT.isoformat(), day=D_EDT)
    assert len(rec.calls) == 2


def _equities(monkeypatch, n):
    monkeypatch.setattr("swingbot.core.marketdata.asset_class.classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    monkeypatch.setattr("swingbot.core.scanning.fetch._sector_etfs_for_tickers",
                        lambda tickers: ({t: "Tech" for t in tickers},))
    return [f"E{i:02d}" for i in range(n)]


def test_a_validation_day_carries_its_header_and_the_daily_vix_path(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "fetch_raw", RecordingFetch(D_EDT))
    fx = bsr.build_day_fixture(D_EDT, INFO, _equities(monkeypatch, 20), provider=None,
                               limiter=None, cache_root=tmp_path)
    o, c = bsr.session_bounds(D_EDT)
    assert fx["source"] == "alpaca" and fx["class"] == "shock" and fx["vix_interpolated"] is True
    assert (fx["session_date"], fx["open_utc"], fx["close_utc"]) == (
        "2025-07-15", o.isoformat(), c.isoformat())
    assert fx["spy_daily"] == {"prev_close": 600.0, "open": 590.0, "close": 580.0}
    assert len(fx["steps"]) == 26 and fx["steps"][0]["minutes_since_open"] == 15.0
    assert fx["steps"][0]["vix"] == bsr.daily_vix_path(U(D_EDT, 13, 45), o, c, INFO)
    assert sum(n["is_equity"] for n in fx["steps"][0]["names"]) == 20


def test_too_few_equities_is_unbuildable_and_never_synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(bsr, "fetch_raw", RecordingFetch(D_EDT))
    fx = bsr.build_day_fixture(D_EDT, INFO, _equities(monkeypatch, 3), provider=None,
                               limiter=None, cache_root=tmp_path)
    assert fx["source"] == "unbuildable" and fx["steps"] == []
    assert "fewer than 20 equities" in fx["note"] and fx["class"] == "shock"


def _days_file(tmp_path, days=("2025-07-15", "2024-11-29")):
    path = tmp_path / "validation_days.json"
    path.write_text(json.dumps({"days": {d: dict(INFO) for d in days}}), encoding="utf-8")
    return path


def test_run_validation_writes_one_gz_per_day_and_skips_finished_days(tmp_path, monkeypatch):
    built = []

    def fake(day, info, tickers, **kw):
        built.append(day)
        return bsr.unbuildable_fixture(day, info, "fake")
    monkeypatch.setattr(bsr, "build_day_fixture", fake)
    out = tmp_path / "out"
    kw = dict(provider=None, limiter=None, cache_root=tmp_path / "cache", out_dir=out)
    assert bsr.run_validation(_days_file(tmp_path), ["AAA"], **kw) == ["2024-11-29", "2025-07-15"]
    fx = bsr.read_gz(out / "2025-07-15.json.gz")
    assert fx["source"] == "unbuildable" and fx["session_date"] == "2025-07-15"
    assert bsr.run_validation(_days_file(tmp_path), ["AAA"], **kw) == [] and len(built) == 2


def test_gz_bytes_are_deterministic(tmp_path):
    payload = {"b": [1, 2.5], "a": "x"}
    bsr.write_gz(tmp_path / "1.json.gz", payload)
    bsr.write_gz(tmp_path / "2.json.gz", payload)
    assert (tmp_path / "1.json.gz").read_bytes() == (tmp_path / "2.json.gz").read_bytes()
    assert bsr.read_gz(tmp_path / "1.json.gz") == payload
    with gzip.open(tmp_path / "1.json.gz", "rt", encoding="utf-8") as fh:
        assert json.load(fh) == payload


def test_validation_mode_without_keys_writes_nothing(tmp_path, monkeypatch):
    def no_keys():
        raise bsr.AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    monkeypatch.setattr(bsr, "make_provider", no_keys)
    out = tmp_path / "out"
    rc = bsr.main(["--validation-days", str(_days_file(tmp_path)), "--out-dir", str(out),
                   "--tickers", "AAA"])
    assert rc == 2 and not out.exists()


def test_an_operator_records_an_unbuildable_day_with_its_reason(tmp_path):
    out, days = tmp_path / "out", _days_file(tmp_path)
    args = ["--validation-days", str(days), "--out-dir", str(out), "--reason", "HTTP 500 x3"]
    assert bsr.main([*args, "--unbuildable", "2025-07-15"]) == 0
    fx = bsr.read_gz(out / "2025-07-15.json.gz")
    assert fx["source"] == "unbuildable" and "HTTP 500 x3" in fx["note"]
    assert bsr.main([*args, "--unbuildable", "2025-07-16"]) == 2      # not on the frozen list


def test_fixture_tickers_are_the_frozen_watchlist(tmp_path):
    fx = {"steps": [{"names": [{"ticker": "MU"}, {"ticker": "AMD"}]},
                    {"names": [{"ticker": "MU"}, {"ticker": "XAUUSD"}]}]}
    path = tmp_path / "fx.json"
    path.write_text(json.dumps(fx), encoding="utf-8")
    assert bsr.fixture_tickers(path) == ["AMD", "MU", "XAUUSD"]
```

`tests/dev/test_select_tests.py`, beside the other real-repo routing tests:

```python
def test_shock_replay_fixtures_route_to_the_replay_test(sel):
    target = "tests/market/test_shock_replay_2026_11_05.py"
    for rel in ("tests/fixtures/shock_replay/validation_days.json",
                "tests/fixtures/shock_replay/2025-04-04.json.gz",
                "tests/fixtures/shock_replay_2026_11_05.json"):
        result = sel.select([rel], REPO)
        assert result.full is False and target in result.targets, rel
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
```

Expected: FAIL (`AttributeError: ... 'session_bounds'`, unrouted fixture paths).

- [ ] **Step 3: Implement the builder changes**

In `scripts/data/build_shock_replay_fixture.py` (import `gzip` and `from swingbot.core.market import session`):
- `session_bounds(day)`: `datetime.combine(day, session.RTH_OPEN, tzinfo=session.US_MARKET_TZ).astimezone(UTC)` and the same with `session.session_close(day)`. Define it above the constants and set `OPEN_UTC, CLOSE_UTC = session_bounds(SESSION)`; `TURN_UTC`, `VIX_TAPE_AT` keep `_at`.
- `step_times(day=SESSION)`: the existing loop over `session_bounds(day)`.
- `daily_vix_path`: the Rules formula; `frac = min(1.0, max(0.0, (t - open_utc) / (close_utc - open_utc)))`; round both outputs to 4 dp.
- `fixture_step(..., vix=None)`: `"vix": vix if vix is not None else vix_path(t)`.
- `load_or_fetch(..., day=SESSION)`: `fetch_raw(provider, ticker, "daily", day - DAILY_LOOKBACK, datetime(day.year, day.month, day.day, tzinfo=UTC), limiter=limiter)` and `fetch_raw(provider, ticker, "15min", day, session_bounds(day)[1], limiter=limiter)`. `_fetch_all(..., day=SESSION)` passes it on. `DAILY_START` goes (the 127-day lookback reproduces it for 11-05).
- `fixture_tickers(path)`: `sorted({n["ticker"] for s in json.loads(...)["steps"] for n in s["names"]})`.
- `_day_header(day, info) -> dict` (private): `session_date`, `class`, `open_utc`, `close_utc` (ISO), `vix_interpolated: True`, `spy_daily` from `info["spy_prev_close"/"spy_open"/"spy_close"]`.
- `unbuildable_fixture(day, info, note)`: `{"source": "unbuildable", **_day_header(day, info), "note": note, "steps": []}`.
- `build_day_fixture`: `_fetch_all(tickers, provider, limiter, cache_root / day.isoformat(), day)`; the equity count as `build_fixture` does it; short ⇒ `unbuildable_fixture(day, info, f"alpaca: fewer than {n} equities with daily + 15-minute bars ({k})")`; else `sector_of` exactly as `build_fixture`, steps with `vix=daily_vix_path(t, o, c, info)`, `source: "alpaca"`, a note naming the ticker count and "VIX ramps linearly from the daily ^VIX open change to the close change vs the prior close".
- `write_gz`: `json.dumps(payload, separators=(",", ":")).encode()` into `gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="")` on `<path>.tmp`, then `os.replace`; create the parent dir. `read_gz`: `json.loads(gzip.decompress(path.read_bytes()))`.
- `run_validation`: load the days file, iterate `sorted(days)`, skip an existing `<out_dir>/<iso>.json.gz`, else build, `write_gz`, print `[i/N pct%] <iso> <class> <source> <n> steps` (`flush=True`); return the written ISO days.
- CLI: add `--validation-days`, `--out-dir` (default `VALIDATION_OUT`), `--unbuildable`, `--reason` (default `"recorded unbuildable by the operator"`); `--cache-dir` default becomes `None` (resolved to `DEFAULT_CACHE` or `VALIDATION_CACHE` by mode). `main` dispatches to a new `_main_validation(args, provider, limiter) -> int` when `--validation-days` is given, before the legacy path (which stays as is):
  - `--unbuildable D`: `D` not in the list ⇒ stderr message, return 2; else `write_gz(out_dir / f"{D}.json.gz", unbuildable_fixture(date.fromisoformat(D), info, f"operator: {reason}"))`, return 0. Needs no provider.
  - else `provider = provider or make_provider()`; `AlpacaAuthError` ⇒ stderr message, return 2 (nothing written). Tickers: `--tickers` or `fixture_tickers(DEFAULT_OUT)`. `run_validation(...)`, return 0.

In `scripts/dev/select_tests.py` `DATA_READERS`, beside the hooks-fixture row:

```python
    # v209 A1: the shock replay fixtures (11-05 and the frozen validation days).
    ("tests/fixtures/shock_replay/", ("tests/market/test_shock_replay_2026_11_05.py",)),
    ("tests/fixtures/shock_replay_2026_11_05.json",
     ("tests/market/test_shock_replay_2026_11_05.py",)),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/scripts/test_build_shock_replay_fixture.py
python scripts/dev/testrun.py file tests/dev/test_select_tests.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed`, `0 xfailed` (the old V209-12 builder tests, including the 11-05 synthetic-fallback ones, still pass: the legacy path is unchanged); no function at complexity ≥ 15.

- [ ] **Step 5: Commit (two scoped commits)**

```bash
git add scripts/data/build_shock_replay_fixture.py tests/scripts/test_build_shock_replay_fixture.py
git commit -m "feat(scripts): A1 replay builder -- session date, DST bounds, daily VIX path, gz validation fixtures"
git add scripts/dev/select_tests.py tests/dev/test_select_tests.py
git commit -m "test(select): route the shock replay fixtures to the replay test"
```

