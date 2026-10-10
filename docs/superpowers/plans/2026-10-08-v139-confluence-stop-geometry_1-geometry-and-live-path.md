# v139 — Part 1: foundations, stop geometry, live path

> Index, Spec corrections, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-08-v139-confluence-stop-geometry_0-index.md`. Work in the worktree `.claude/worktrees/2026-10-08-v139-confluence-stop-geometry` on branch `2026-10-08-v139-confluence-stop-geometry`. Every path below is relative to that worktree's root, which is the session root. Never edit the main tree. Never `cd` in Bash.

# Phase 1 — Foundations (Group A)

## Parallelisation (Phase 1)

V139-0 Step 1 (the worktree) comes first. Then V139-0, V139-1, V139-2 and V139-3 run in parallel. Their files are disjoint and none consumes another's symbol. V139-0 must be **committed** before V139-5 starts.

### Task V139-0: Worktree, then capture the knobs-off golden

**Files:**
- Create: `tests/backtesting/test_v139_flag_off_golden.py`
- Create: `tests/fixtures/v139/flag_off_golden.json` (generated, then committed)

**Interfaces:**
- Consumes: `backtest_scenarios.replay_scenarios` (`swingbot/core/backtesting/backtest_scenarios.py:81`), `exit_sim.simulate_exit`, `tests.backtesting.test_backtest_scenarios.GATES` / `_structured_df`, `tests.fixtures.ohlcv_parity.load_ohlcv`.
- Produces: `GOLDEN`, `_capture()`. Every later task must leave `test_knobs_off_replay_matches_the_pre_v139_golden` green. This is the spec's "both knobs at 0 → byte-identical" parity.

The fixture choice was measured while writing this plan, on `main` at `e965b6f3`. DELL `4w` through 2019-12-31 under the test `GATES` replays 40 confluence plans. 9 of them are clamped, with `d` = 2.04, 2.12, 2.84, 3.04, 3.05, 3.53, 4.30, 4.43, 5.55. So every arm and every cell has a plan to move. The structured `AAPL` fixture adds 16 plans, 1 of them clamped.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill. Create the worktree named `2026-10-08-v139-confluence-stop-geometry` on a new branch of the same name from `main` (`EnterWorktree`, or `git worktree add .claude/worktrees/2026-10-08-v139-confluence-stop-geometry -b 2026-10-08-v139-confluence-stop-geometry main` from the main tree's root). Work from it as the session root from here on.

- [ ] **Step 2: Write the test module**

```python
"""v139 flag-off parity (spec § Testing, first bullet): with
CONFLUENCE_STRUCTURAL_STOP_PCT and CONFLUENCE_STOP_DROP_PCT at 0, the
confluence replay builds and exits exactly the plans it did before v139
touched builders.py, stop_scope.py or analyze.py. The golden was captured at
V139-0, before any v139 code change -- never regenerate it to make this pass."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v139" / "flag_off_golden.json"
#: DELL 4w through 2019 under GATES: 40 plans, 9 clamped (d 2.04 .. 5.55).
DELL_END = "2019-12-31"
TRIGGER, LEVEL = 4, 8      # row positions of trigger_price and acceptance_level


def _r6(value):
    return None if value is None else round(float(value), 6)


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total), exit_index])
    return rows


def _capture():
    return {"structured": _rows("AAPL", _structured_df()),
            "dell": _rows("DELL", load_ohlcv("DELL").loc[:DELL_END])}


def _clamped(rows):
    return [r for r in rows if r[LEVEL] is not None
            and planned_loss_pct(r[TRIGGER], r[LEVEL]) > HARD_MAX_PLANNED_LOSS_PCT]


def test_knobs_off_replay_matches_the_pre_v139_golden(monkeypatch):
    # raising=False: the attributes only exist from V139-2 on.
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 0.0, raising=False)
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 0.0, raising=False)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(_clamped(golden["dell"])) >= 5, "the golden must exercise clamped plans"
    assert _capture() == golden
```

- [ ] **Step 3: Run it to verify it fails** (the fixture does not exist yet)

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`
Expected: FAIL, `FileNotFoundError` on `flag_off_golden.json`.

- [ ] **Step 4: Generate the golden from the unchanged code**

```bash
python -c "import json; from tests.backtesting.test_v139_flag_off_golden import _capture, GOLDEN; GOLDEN.parent.mkdir(parents=True, exist_ok=True); GOLDEN.write_text(json.dumps(_capture(), indent=1), encoding='utf-8')"
```

Check that `git diff --stat` shows **no** change under `swingbot/`: the golden must come from pre-v139 code. Check the JSON: `structured` has 16 rows and `dell` has 40. If the counts differ, the fixture data or `GATES` moved since `e965b6f3`. Record the actual counts in the commit body; the `>= 5 clamped` assertion is the one that must hold.

- [ ] **Step 5: Run it to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/backtesting/test_v139_flag_off_golden.py tests/fixtures/v139/flag_off_golden.json
git commit -m "test(v139): capture the knobs-off confluence golden before any v139 change

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-1: `TradePlanV2.stop_ceiling_pct`

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (directly after `acceptance_close_below: float | None = None`, ~line 131)
- Test: `tests/planning/test_plan_serialization.py`, `tests/db/test_plans_repository.py`

**Interfaces:**
- Produces: `TradePlanV2.stop_ceiling_pct: float | None = None`. Consumed by V139-5 (set by the builder), V139-6 (`plan_stop_ceiling`, `risk_sizing_ok`), V139-7 (`attach_plan_v2`) and V139-8 (`changed` = the field is set).

Schema path: **add** (`docs/claude/schema-evolution.md` § The four operations). The field is not a key, an index or NOT NULL, so it lands in `plans.doc` JSONB through `plan_to_dict`. No Alembic revision. No read-time upcasting: `plan_from_dict` already defaults missing fields.

- [ ] **Step 1: Write the failing tests**

Append to `tests/planning/test_plan_serialization.py`:

```python
def test_stop_ceiling_pct_defaults_to_none_and_round_trips():
    assert _plan().stop_ceiling_pct is None
    q = plan_from_dict(plan_to_dict(_plan(stop_ceiling_pct=4.0)))
    assert q.stop_ceiling_pct == 4.0


def test_pre_v139_record_without_stop_ceiling_pct_loads_as_none():
    d = plan_to_dict(_plan())
    d.pop("stop_ceiling_pct")
    assert plan_from_dict(d).stop_ceiling_pct is None
```

Append to `tests/db/test_plans_repository.py`:

```python
def test_v139_stop_ceiling_pct_rides_in_the_doc(repo, db_conn):
    """v139 used schema-evolution's ADD path: no column, no revision -- the
    arm S ceiling lives in plans.doc and must survive the repository."""
    from tests.db_diff import diff_records
    record = _plan("P1", source="confluence", stop_ceiling_pct=4.0)
    repo.insert(record, conn=db_conn)
    assert diff_records(record, repo.get("P1", conn=db_conn)) == []
```

- [ ] **Step 2: Run the serialization tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: FAIL: `TypeError: ... unexpected keyword argument 'stop_ceiling_pct'`, and `AttributeError` / `KeyError` on the second test.

- [ ] **Step 3: Add the field**

In `plan_types.py`, directly after `acceptance_close_below: float | None = None`:

```python
    # v139 arm S: the planned-loss ceiling (percent) this plan is held to --
    # the c of CONFLUENCE_STRUCTURAL_STOP_PCT it was built under, when it kept
    # a structural stop past the 2% cap. None = today's ceiling
    # (stop_scope.plan_stop_ceiling: 2% for confluence, the v104 scope
    # ceiling for strategy plans). Set only by
    # builders.confluence_stop_geometry; read by plan_stop_ceiling,
    # risk_sizing_ok and analyze.attach_plan_v2.
    stop_ceiling_pct: float | None = None
```

- [ ] **Step 4: Run the tests, the repository test against the test database**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_serialization.py`
Expected: pass.

Start the test database and run the repository test with skip reasons shown:

```bash
docker compose --profile test up -d db-test
python -m pytest tests/db/test_plans_repository.py tests/db/test_unknown_field_round_trip.py -rs -v
```

Expected: `test_v139_stop_ceiling_pct_rides_in_the_doc PASSED`, and **no** `SKIPPED` line. A skip means `db-test` is not reachable. Fix that (the skip message names the start command); never commit with the round trip skipped (spec § Testing).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_types.py tests/planning/test_plan_serialization.py tests/db/test_plans_repository.py
git commit -m "feat(v139): TradePlanV2.stop_ceiling_pct (doc add path, no revision)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-2: The two inert knobs, `ScanParams` and the reachability rows

**Files:**
- Modify: `swingbot/config.py` (two `Field`s after `CLAMP_STOP_TO_HARD_CAP`, ~line 186; `_SEARCH_CLASSES["searchable"]`, ~lines 1237-1262)
- Modify: `swingbot/scan_params.py` (two fields after `fvg_displacement_atr_k`, ~line 91; two `from_config` lines)
- Modify: `swingbot/core/backtesting/arms/reachability.py` (two `REGISTRY` rows)
- Modify: `.env.example` (after `CLAMP_STOP_TO_HARD_CAP=true`, ~line 102)
- Modify: `tests/market/test_v115_strategy_work_off.py` (`FLAGS_OFF`)
- Create: `tests/test_config_v139_confluence_stop.py`

**Interfaces:**
- Produces: `config.CONFLUENCE_STRUCTURAL_STOP_PCT: float = 0.0`, `config.CONFLUENCE_STOP_DROP_PCT: float = 0.0`, `ScanParams.confluence_structural_stop_pct: float = 0.0`, `ScanParams.confluence_stop_drop_pct: float = 0.0`. Both are reachable through `measure_arms.parse_knob`. Consumed by V139-4 (the helper reads `params`), V139-8 (`apply_knobs`) and V139-14 (`--knob CONFLUENCE_STOP_DROP_PCT=c`).

`tests/backtesting/test_knob_observability.py::test_every_searchable_knob_is_classified` requires the `searchable` class and the `REGISTRY` row to land together. `tests/infra/test_scan_params_coverage.py` requires the `ScanParams` fields. `tests/infra/test_env_example_sync.py` requires the `.env.example` keys. That is why all of them are one task.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_v139_confluence_stop.py`:

```python
"""v139: the confluence stop-geometry knobs -- schema, ScanParams, reachability."""
import pytest

from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.scan_params import ScanParams

KNOBS = ("CONFLUENCE_STRUCTURAL_STOP_PCT", "CONFLUENCE_STOP_DROP_PCT")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


@pytest.mark.parametrize("attr", KNOBS)
def test_field_is_an_inert_searchable_float(attr):
    field = _field(attr)
    assert (field.type, field.default, field.search_class) == ("float", "0", "searchable")
    assert config._cast(field, field.default) == 0.0
    assert attr in config.searchable_attrs()


def test_scan_params_defaults_are_off():
    params = ScanParams.from_config()
    assert params.confluence_structural_stop_pct == 0.0
    assert params.confluence_stop_drop_pct == 0.0


@pytest.mark.parametrize("attr", KNOBS)
def test_scan_params_carries_the_knob(attr, monkeypatch):
    monkeypatch.setattr(config, attr, 4.0)
    assert getattr(ScanParams.from_config(), attr.lower()) == 4.0


@pytest.mark.parametrize("attr", KNOBS)
def test_reachability_row_is_confluence_only(attr):
    assert reach.classify(attr) == reach.REACHABLE
    assert reach.REGISTRY[attr].observed_by == reach.C


@pytest.mark.parametrize("attr", KNOBS)
def test_measure_arms_parses_the_knob(attr):
    assert parse_knob(f"{attr}=3.0") == (attr, 3.0)
```

In `tests/market/test_v115_strategy_work_off.py`, append to `FLAGS_OFF`:

```python
    ("v139", "CONFLUENCE_STRUCTURAL_STOP_PCT", 0.0),
    ("v139", "CONFLUENCE_STOP_DROP_PCT", 0.0),
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/test_config_v139_confluence_stop.py`
Expected: FAIL: `StopIteration` in `_field`, and `AttributeError` on the `ScanParams` fields.

- [ ] **Step 3: Add the two Fields**

In `swingbot/config.py`, directly after the `CLAMP_STOP_TO_HARD_CAP` `Field(...)`:

```python
    Field("CONFLUENCE_STRUCTURAL_STOP_PCT", "CONFLUENCE_STRUCTURAL_STOP_PCT", "Trade Filters & Risk",
          "Confluence structural-stop ceiling % (v139 arm S)",
          type="float", default="0", min=0, max=11, step=0.5,
          help="v139 arm S. 0 = off: today's 1.75% clamp. Above 0, a confluence stop the clamp "
               "would move stays at its level when that level is within this ceiling less 0.25% "
               "headroom; the target is re-chosen against the wider risk, the plan stores this "
               "ceiling, and the position must be sized to fixed dollar risk (risk_pct). No target "
               "inside the reward:risk band rolls the plan back to the clamp. Unmeasured: "
               "pre-registered grid {3, 4, 5}; keep 0 until its VALIDATION shot passes and the "
               "partner decides."),
    Field("CONFLUENCE_STOP_DROP_PCT", "CONFLUENCE_STOP_DROP_PCT", "Trade Filters & Risk",
          "Confluence stop drop ceiling % (v139 arm D)",
          type="float", default="0", min=0, max=11, step=0.5,
          help="v139 arm D. 0 = off. Above 0, a confluence setup whose structural stop sits "
               "further than this from the entry gets no plan (stop_beyond_confluence_ceiling) "
               "instead of the 1.75% clamp. Unmeasured: pre-registered grid {3, 4, 5}; keep 0 "
               "until its VALIDATION shot passes and the partner decides."),
```

In `_SEARCH_CLASSES["searchable"]`, after `"FVG_LEVELS_MODE", "FVG_DISPLACEMENT_ATR_K",` add:

```python
        "CONFLUENCE_STRUCTURAL_STOP_PCT", "CONFLUENCE_STOP_DROP_PCT",
```

- [ ] **Step 4: Carry them in `ScanParams`**

In `swingbot/scan_params.py`, after `fvg_displacement_atr_k: float = 1.5     # v128: read only in displacement mode`:

```python
    confluence_structural_stop_pct: float = 0.0   # v139 arm S ceiling c; 0 = today's clamp
    confluence_stop_drop_pct: float = 0.0         # v139 arm D ceiling c; 0 = no drop
```

In `from_config`, after `fvg_displacement_atr_k=config.FVG_DISPLACEMENT_ATR_K,`:

```python
            confluence_structural_stop_pct=config.CONFLUENCE_STRUCTURAL_STOP_PCT,
            confluence_stop_drop_pct=config.CONFLUENCE_STOP_DROP_PCT,
```

- [ ] **Step 5: The reachability rows**

In `swingbot/core/backtesting/arms/reachability.py`, add a reason constant after `_DRYUP = (...)`:

```python
_V139 = ("v139: builders.confluence_stop_geometry inside build_confluence_plan, which "
         "replay_scenarios (ConfluenceEngine) reaches. Only clamped confluence plans "
         "(structural stop beyond the 2% cap) move; strategy plans never. Not verified on "
         "the v74 fixture; covered by tests/planning/test_confluence_stop_geometry.py and "
         "tests/backtesting/test_confluence_stop_replay.py.")
```

and two rows at the end of `REGISTRY`, after `"RUNNER_STALL_RANGE_MAX": ...`:

```python
    "CONFLUENCE_STRUCTURAL_STOP_PCT": Reach(REACHABLE, _V139 + " Arm S is gated by the v92 harvest "
                                            "gate through scripts/backtest/measure_confluence_stop.py, "
                                            "not measure_arms.py.", C),
    "CONFLUENCE_STOP_DROP_PCT": Reach(REACHABLE, _V139 + " Arm D runs the standard v72 funnel "
                                      "through measure_arms.py.", C),
```

- [ ] **Step 6: `.env.example`**

Directly after `CLAMP_STOP_TO_HARD_CAP=true`:

```bash

# v139 (unmeasured, keep both at 0): confluence stops the 2% clamp would move.
# Arm S: keep the structural stop up to this ceiling (less 0.25% headroom) and
# size to fixed dollar risk. 0 = today's 1.75% clamp.
CONFLUENCE_STRUCTURAL_STOP_PCT=0
# Arm D: issue no plan when the structural stop is beyond this ceiling. 0 = no drop.
CONFLUENCE_STOP_DROP_PCT=0
```

- [ ] **Step 7: Run the tests**

Run each:
- `python scripts/dev/testrun.py file tests/test_config_v139_confluence_stop.py`
- `python scripts/dev/testrun.py file tests/market/test_v115_strategy_work_off.py`
- `python scripts/dev/testrun.py file tests/infra/test_scan_params_coverage.py`
- `python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_knob_observability.py`
- `python scripts/dev/testrun.py file tests/backtesting/arms/test_reachability.py`

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/backtesting/arms/reachability.py .env.example tests/test_config_v139_confluence_stop.py tests/market/test_v115_strategy_work_off.py
git commit -m "feat(v139): inert CONFLUENCE_STRUCTURAL_STOP_PCT / CONFLUENCE_STOP_DROP_PCT knobs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-3: `MEASURE_ARMS_UNIVERSE` — the arm universe from the cache listing

**Files:**
- Modify: `scripts/backtest/measure_arms.py` (`cached_universe`, ~line 27; a new `cache_listing`; `import os`)
- Test: `tests/scripts/test_measure_arms.py`

**Interfaces:**
- Produces: `measure_arms.UNIVERSE_ENV = "MEASURE_ARMS_UNIVERSE"`, `measure_arms.UNIVERSE_SOURCES = ("watchlist", "cache")`, `measure_arms.cache_listing() -> list[str]`, and `measure_arms.cached_universe() -> list[str]`, which now honours the variable. With it unset, behaviour is unchanged.
- Consumed by V139-10 (the arm S driver lists its universe through `cached_universe`) and by every arm D command (V139-11, V139-14, V139-15). The arm D commands reach it through `measure_arms`, `validate_component._full_universe` and `permutation_test._full_universe`.

Why an environment variable and not a flag (index, Spec correction 9): three scripts stamp-check the universe, and `permutation_test` imports `scripts.backtest.measure_arms`, a second module object. Only the environment reaches all three the same way.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_arms.py`:

```python
def _cache(tmp_path, monkeypatch, names):
    from swingbot.core.marketdata import backtest_cache
    for name in names:
        (tmp_path / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)


def test_universe_defaults_to_the_cached_watchlist(tmp_path, monkeypatch):
    import run_backtest_range
    _cache(tmp_path, monkeypatch, ["AAPL.csv", "MSFT.csv"])
    monkeypatch.delenv(ma.UNIVERSE_ENV, raising=False)
    monkeypatch.setattr(run_backtest_range, "_tickers_for_run",
                        lambda universe: ["MSFT", "AAPL", "NOPE"])
    assert ma.cached_universe() == ["AAPL", "MSFT"]


def test_cache_source_lists_every_cached_csv_without_the_watchlist(tmp_path, monkeypatch):
    import run_backtest_range
    _cache(tmp_path, monkeypatch, ["MSFT.csv", "AAPL.csv", "SPY.csv", "notes.txt"])
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    monkeypatch.setattr(run_backtest_range, "_tickers_for_run",
                        lambda universe: pytest.fail("the watchlist was read"))
    assert ma.cached_universe() == ["AAPL", "MSFT", "SPY"]


def test_unknown_source_raises_never_falls_back(monkeypatch):
    monkeypatch.setenv(ma.UNIVERSE_ENV, "postgres")
    with pytest.raises(ValueError, match=ma.UNIVERSE_ENV):
        ma.cached_universe()


def test_the_judges_read_the_same_universe(tmp_path, monkeypatch):
    import validate_component as vc
    from scripts.backtest import permutation_test as pt
    _cache(tmp_path, monkeypatch, ["AAPL.csv", "DELL.csv"])
    monkeypatch.setenv(ma.UNIVERSE_ENV, "cache")
    assert vc._full_universe() == ["AAPL", "DELL"]
    assert pt._full_universe() == ["AAPL", "DELL"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_arms.py`
Expected: FAIL: `AttributeError: module 'measure_arms' has no attribute 'UNIVERSE_ENV'`.

- [ ] **Step 3: Implement**

In `scripts/backtest/measure_arms.py`, add `import os` beside `import json`. Replace `cached_universe` with:

```python
#: v139: where the arm universe comes from. "watchlist" (the default, unchanged)
#: is the Postgres watchlist filtered to cached frames. "cache" is every cached
#: CSV in backtest_cache.CACHE_DIR, for a worktree where Postgres is unreachable
#: (the v129 precedent, partner-approved 2026-10-08). The stamp records the list
#: either way, and validate_component / permutation_test call this same function,
#: so a producer run and its judge agree.
UNIVERSE_ENV = "MEASURE_ARMS_UNIVERSE"
UNIVERSE_SOURCES = ("watchlist", "cache")


def cache_listing() -> list[str]:
    """Every ticker with a cached CSV, sorted."""
    from swingbot.core.marketdata import backtest_cache
    return sorted(path.stem for path in Path(backtest_cache.CACHE_DIR).glob("*.csv"))


def cached_universe() -> list[str]:
    source = (os.environ.get(UNIVERSE_ENV) or "watchlist").strip().lower()
    if source not in UNIVERSE_SOURCES:
        raise ValueError(f"{UNIVERSE_ENV} must be one of {UNIVERSE_SOURCES}, got {source!r}")
    if source == "cache":
        return cache_listing()
    from swingbot.core.marketdata.backtest_cache import cache_path
    from run_backtest_range import _tickers_for_run
    return sorted(ticker for ticker in _tickers_for_run(None) if cache_path(ticker).exists())
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_arms.py`, then `python scripts/dev/testrun.py file tests/backtesting/test_permutation_test_arms.py`
Expected: both pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_arms.py tests/scripts/test_measure_arms.py
git commit -m "feat(v139): MEASURE_ARMS_UNIVERSE=cache -- arm universe from the cache listing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

# Phase 2 — Stop geometry and the live path (Group B)

## Parallelisation (Phase 2)

Sequential throughout: V139-4 → V139-5 → V139-6 → V139-7, after all of Group A.
- V139-4 reads the V139-2 `ScanParams` fields.
- V139-5 edits `builders.py` again and consumes V139-4's helper and the V139-1 field.
- V139-6 consumes the V139-1 field.
- V139-7 consumes V139-5's `confluence_stop_dropped` and V139-6's `plan_stop_ceiling`.

### Task V139-4: `confluence_stop_geometry` (the helper, not yet called)

**Files:**
- Modify: `swingbot/core/planning/builders.py` (new code directly after `_clamp_stop_to_hard_cap`, which ends at ~line 433)
- Create: `tests/planning/test_confluence_stop_geometry.py`

**Interfaces:**
- Consumes: `_clamp_stop_to_hard_cap` (`builders.py:418`), `CLAMP_HEADROOM_PCT` (`:415`), `select_structural_target` (`targets.py:10`), `planned_loss_pct` / `HARD_MAX_PLANNED_LOSS_PCT` (`risk_limits.py`), `ScanParams.confluence_structural_stop_pct` / `confluence_stop_drop_pct` / `min_risk_reward_ratio` / `max_risk_reward_ratio`.
- Produces:
  - `STOP_GEOMETRY_TOL = 1e-9`
  - `clamped_distance(entry, level, is_bull) -> float | None`
  - `confluence_stop_geometry(entry, level, is_bull, candidates, params) -> tuple[float | None, float | None] | None`. It returns `(stop_loss, stop_ceiling_pct)`, or `None` to drop the plan.

  V139-5 calls the geometry function. V139-8 imports `clamped_distance`, `STOP_GEOMETRY_TOL` and `CLAMP_HEADROOM_PCT`.

Nothing calls the new function in this task, so behaviour is unchanged and the golden stays green.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_confluence_stop_geometry.py`:

```python
"""v139 confluence_stop_geometry: arm S (structural stop up to c - 0.25,
target re-selected, rollback to the clamp) and arm D (no plan beyond c), both
directions. Spec: docs/superpowers/specs/2026-10-08-v139-confluence-stop-geometry-design.md"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.builders import clamped_distance, confluence_stop_geometry
from swingbot.scan_params import ScanParams

BOTH = pytest.mark.parametrize("is_bull", [True, False])


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(s=0.0, d=0.0):
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5,
                               confluence_structural_stop_pct=s, confluence_stop_drop_pct=d)


def _m(is_bull, price):
    """Mirror a bullish price around the 100.0 entry for the bearish case."""
    return price if is_bull else 200.0 - price


def _geo(is_bull, level, candidate, **knobs):
    return confluence_stop_geometry(100.0, _m(is_bull, level), is_bull,
                                    [_m(is_bull, candidate)], _params(**knobs))


@BOTH
def test_unclamped_plan_is_unchanged_by_both_arms(is_bull):
    assert _geo(is_bull, 98.5, 104.0, s=5.0, d=3.0) == (_m(is_bull, 98.5), None)


@BOTH
def test_arm_s_applies_at_exactly_c_minus_headroom(is_bull):
    # d = 2.75 = 3.0 - 0.25; 105 is 1.82R at the 2.75 structural risk.
    assert _geo(is_bull, 97.25, 105.0, s=3.0) == (_m(is_bull, 97.25), 3.0)


@BOTH
def test_arm_s_just_past_the_headroom_keeps_the_clamp(is_bull):
    stop, ceiling = _geo(is_bull, 97.24, 105.0, s=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_s_without_an_rr_band_target_rolls_back_to_the_clamp(is_bull):
    # 103 is 1.09R at the 2.75 structural risk, under the 1.5R floor.
    stop, ceiling = _geo(is_bull, 97.25, 103.0, s=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_d_keeps_a_plan_exactly_at_c(is_bull):
    stop, ceiling = _geo(is_bull, 97.0, 104.0, d=3.0)
    assert stop == pytest.approx(_m(is_bull, 98.25))
    assert ceiling is None


@BOTH
def test_arm_d_drops_just_past_c(is_bull):
    assert _geo(is_bull, 96.99, 104.0, d=3.0) is None


@BOTH
def test_both_set_arm_s_first_then_arm_d(is_bull):
    # d = 3.5 <= 4.0 - 0.25: arm S keeps it, although arm D's 3.0 would drop it.
    assert _geo(is_bull, 96.5, 108.0, s=4.0, d=3.0) == (_m(is_bull, 96.5), 4.0)
    # d = 4.0 is past arm S's 3.75: arm D drops it.
    assert _geo(is_bull, 96.0, 108.0, s=4.0, d=3.0) is None


@BOTH
def test_arm_s_rollback_past_arm_d_is_dropped(is_bull):
    # d = 3.5: arm S applies by geometry but 103 has no RR-band slot -> rollback;
    # the rolled-back plan is then beyond arm D's 3.0 -> dropped.
    assert _geo(is_bull, 96.5, 103.0, s=4.0, d=3.0) is None


@BOTH
def test_both_off_is_exactly_todays_clamp(is_bull):
    for level in (98.5, 98.0, 97.0, 90.0):
        lv = _m(is_bull, level)
        expected = (builders._clamp_stop_to_hard_cap(100.0, lv, is_bull), None)
        assert confluence_stop_geometry(100.0, lv, is_bull, [_m(is_bull, 120.0)],
                                        _params()) == expected


def test_clamped_distance_is_the_set_the_clamp_moves():
    assert clamped_distance(100.0, 98.0, True) is None          # exactly the cap
    assert clamped_distance(100.0, 97.0, True) == pytest.approx(3.0)
    assert clamped_distance(100.0, 103.0, False) == pytest.approx(3.0)
    assert clamped_distance(100.0, 103.0, True) is None          # profit side
    assert clamped_distance(100.0, None, True) is None
    assert clamped_distance(0.0, 97.0, True) is None
    assert clamped_distance(None, 97.0, True) is None


def test_clamped_distance_ignores_the_clamp_flag(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    assert clamped_distance(100.0, 97.0, True) == pytest.approx(3.0)


def test_invalid_inputs_pass_through_like_the_clamp():
    assert confluence_stop_geometry(100.0, None, True, [], _params(s=4.0, d=3.0)) == (None, None)
    assert confluence_stop_geometry(0.0, 5.0, True, [], _params(s=4.0, d=3.0)) == (5.0, None)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_geometry.py`
Expected: FAIL: `ImportError: cannot import name 'clamped_distance'`.

- [ ] **Step 3: Implement**

In `builders.py`, directly after `_clamp_stop_to_hard_cap` (after its `return entry - offset if is_bull else entry + offset`):

```python
# v139: float tolerance on the two ceiling boundaries (entry_filters' 1e-9), so
# d exactly at c - CLAMP_HEADROOM_PCT is arm S and d exactly at c is kept by arm D.
STOP_GEOMETRY_TOL = 1e-9


def clamped_distance(entry, level, is_bull) -> float | None:
    """v139: the structural distance d (planned-loss %) of a stop that
    _clamp_stop_to_hard_cap moves -- on the stop side of a valid entry and
    beyond HARD_MAX_PLANNED_LOSS_PCT -- else None. It ignores
    CLAMP_STOP_TO_HARD_CAP: the arms key on geometry, and only their
    fallback (today's plan) reads the flag."""
    if level is None or entry is None or entry <= 0:
        return None
    if (level >= entry) if is_bull else (level <= entry):
        return None
    d = planned_loss_pct(entry, level)
    return d if d > HARD_MAX_PLANNED_LOSS_PCT else None


def _arm_s_stop(entry, level, is_bull, d, candidates, params):
    """(level, c) when arm S keeps the structural stop, else None: the knob is
    off, d is past c - CLAMP_HEADROOM_PCT, or no candidate clears the
    reward:risk band at the structural risk (the rollback)."""
    c = params.confluence_structural_stop_pct
    if c <= 0 or d > c - CLAMP_HEADROOM_PCT + STOP_GEOMETRY_TOL:
        return None
    tp1 = select_structural_target(entry, level, is_bull, candidates,
                                   params.min_risk_reward_ratio, params.max_risk_reward_ratio)
    return None if tp1 is None else (float(level), float(c))


def confluence_stop_geometry(entry, level, is_bull, candidates, params):
    """v139: (stop_loss, stop_ceiling_pct) for a confluence plan, or None to
    issue no plan (arm D).

    With both knobs at 0 this is exactly (_clamp_stop_to_hard_cap(...), None).
    Only a clamped plan (clamped_distance is not None) is ever changed:
    arm S (CONFLUENCE_STRUCTURAL_STOP_PCT = c > 0) keeps the level when
    d <= c - CLAMP_HEADROOM_PCT and a candidate clears the reward:risk band at
    that risk, storing c as the plan's ceiling; otherwise the plan is today's.
    Arm D (CONFLUENCE_STOP_DROP_PCT = c > 0) then drops what is beyond c.
    Arm S applies first when both are set."""
    today = _clamp_stop_to_hard_cap(entry, level, is_bull)
    d = clamped_distance(entry, level, is_bull)
    if d is None:
        return today, None
    structural = _arm_s_stop(entry, level, is_bull, d, candidates, params)
    if structural is not None:
        return structural
    drop = params.confluence_stop_drop_pct
    if drop > 0 and d > drop + STOP_GEOMETRY_TOL:
        return None
    return today, None
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_geometry.py`, then `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py`
Expected: both pass.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py`
Expected: only `build_confluence_plan - C (14)` and `build_strategy_plan - C (13)` (both pre-existing and unchanged). None of the three new functions is listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/builders.py tests/planning/test_confluence_stop_geometry.py
git commit -m "feat(v139): confluence_stop_geometry -- arm S structural stop / arm D drop helper (not yet called)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-5: Route `build_confluence_plan` through the helper

**Files:**
- Modify: `swingbot/core/planning/builders.py` (`build_confluence_plan`, ~lines 436–504; two new functions directly above it)
- Create: `tests/planning/test_confluence_stop_build.py`

**Interfaces:**
- Consumes: `confluence_stop_geometry` (V139-4), `TradePlanV2.stop_ceiling_pct` (V139-1), `levels.target_candidates`.
- Produces:
  - `_confluence_candidates(scenario, level_map) -> list`
  - `confluence_stop_dropped(scenario, level_map=None, params=None) -> bool`, consumed by V139-7.
  - Confluence plans carrying `stop_ceiling_pct` (V139-6, V139-8).

**Cross-plan (audit 2026-10-10):** complexity gate (owner v149). If `scripts/dev/complexity_gate.py` exists (v149 merged), this task's extraction of `_confluence_candidates` finishes with `python scripts/dev/complexity_gate.py` after Step 6, then `--update`, and Step 7 commits `scripts/dev/complexity_baseline.json` with it (`gone`/`improved` expected; `new`/`risen` never).

`build_confluence_plan` is at C(14). The drop branch adds one. Extracting `_confluence_candidates` removes two (the `if level_map` and the conditional expression), so the function ends at 13 (index, Spec correction 2).

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_confluence_stop_build.py`:

```python
"""v139: build_confluence_plan takes its stop from confluence_stop_geometry --
today's clamp with both knobs at 0, arm S's structural stop with a re-chosen
target and a stored ceiling, arm D's drop."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(s=0.0, d=0.0):
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5,
                               confluence_structural_stop_pct=s, confluence_stop_drop_pct=d)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])


def _build(scenario, params):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=None, params=params)


def test_knobs_off_build_todays_clamped_plan():
    plan = _build(_scenario("bullish", 100.0, 96.5, 108.0), _params())
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(100.0 + 1.75 * 2.5)   # 108 is past the cap: synthetic
    assert plan.tp2 == pytest.approx(108.0)
    assert plan.stop_ceiling_pct is None
    assert plan.acceptance_level == 96.5


def test_arm_s_keeps_the_level_and_reselects_the_target():
    plan = _build(_scenario("bullish", 100.0, 96.5, 108.0), _params(s=4.0))
    assert plan.stop_loss == 96.5
    assert plan.stop_ceiling_pct == 4.0
    assert plan.tp1 == pytest.approx(108.0)   # 2.29R against the 3.5 structural risk
    assert plan.tp2 is None
    assert plan.acceptance_level == 96.5


def test_arm_s_bearish_mirror():
    plan = _build(_scenario("bearish", 100.0, 103.5, 92.0), _params(s=4.0))
    assert (plan.stop_loss, plan.stop_ceiling_pct) == (103.5, 4.0)
    assert plan.tp1 == pytest.approx(92.0)


def test_arm_s_rollback_builds_exactly_todays_plan():
    # 104 is 1.14R at the 3.5 structural risk (rollback) and 2.29R at 1.75.
    scenario = _scenario("bullish", 100.0, 96.5, 104.0)
    today, rolled = _build(scenario, _params()), _build(scenario, _params(s=4.0))
    assert rolled.stop_ceiling_pct is None
    assert (rolled.stop_loss, rolled.tp1, rolled.tp2) == (today.stop_loss, today.tp1, today.tp2)


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.5, 92.0)])
def test_arm_d_drops_beyond_its_ceiling_and_keeps_within(direction, stop, target):
    assert _build(_scenario(direction, 100.0, stop, target), _params(d=3.0)) is None
    kept = _build(_scenario(direction, 100.0, stop, target), _params(d=4.0))
    assert kept.stop_loss == pytest.approx(98.25 if direction == "bullish" else 101.75)
    assert kept.stop_ceiling_pct is None


def test_unclamped_plan_is_untouched_by_both_arms():
    plan = _build(_scenario("bullish", 100.0, 98.5, 104.0), _params(s=3.0, d=3.0))
    assert plan.stop_loss == 98.5
    assert plan.stop_ceiling_pct is None


def test_confluence_stop_dropped_agrees_with_the_builder():
    scenario = _scenario("bullish", 100.0, 96.5, 108.0)
    assert builders.confluence_stop_dropped(scenario, None, _params(d=3.0)) is True
    assert builders.confluence_stop_dropped(scenario, None, _params(d=4.0)) is False
    assert builders.confluence_stop_dropped(scenario, None, _params()) is False
    assert builders.confluence_stop_dropped(scenario, None, _params(s=4.0, d=3.0)) is False
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_build.py`
Expected: FAIL: `AttributeError: ... has no attribute 'confluence_stop_dropped'`, and `test_arm_s_keeps_the_level_and_reselects_the_target` asserting `98.25 == 96.5`.

- [ ] **Step 3: Add the two helpers directly above `build_confluence_plan`**

```python
def _confluence_candidates(scenario, level_map) -> list:
    """TP candidates for a confluence plan: the unified level map's when one is
    supplied, else the scenario's own real target (or nothing)."""
    if level_map is not None:
        return levels.target_candidates(*level_map, scenario.direction)
    return [scenario.take_profit] if scenario.take_profit is not None else []


def confluence_stop_dropped(scenario, level_map=None, params=None) -> bool:
    """v139: True when build_confluence_plan returns None because arm D drops
    the scenario (its structural stop is beyond CONFLUENCE_STOP_DROP_PCT and
    arm S did not keep it). Same inputs, same geometry call as the builder, so
    analyze.attach_plan_v2 can name the reason without a second rule."""
    if params is None:
        from swingbot.scan_params import ScanParams
        params = ScanParams.from_config()
    candidates = _confluence_candidates(scenario, level_map)
    return confluence_stop_geometry(scenario.entry, scenario.stop_loss,
                                    scenario.direction == "bullish", candidates, params) is None
```

- [ ] **Step 4: Rewire `build_confluence_plan`**

Replace the lines from `entry = scenario.entry` through the `tp1 = select_structural_target(...)` call (today `builders.py:455-466`) with:

```python
    entry = scenario.entry
    is_bull = scenario.direction == "bullish"
    level = scenario.stop_loss   # v129: the pre-clamp level the trade leans on
    candidates = _confluence_candidates(scenario, level_map)
    geometry = confluence_stop_geometry(entry, level, is_bull, candidates, params)
    if geometry is None:
        return None              # v139 arm D: structural stop beyond its ceiling
    stop_loss, stop_ceiling_pct = geometry

    tp1 = select_structural_target(entry, stop_loss, is_bull, candidates,
                                   params.min_risk_reward_ratio, params.max_risk_reward_ratio)
```

In the `TradePlanV2(...)` constructor call, change the last line from `badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,` to:

```python
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
        stop_ceiling_pct=stop_ceiling_pct,
```

Append to the docstring's last sentence (after `use the clamped risk.`):

```
    v139: the stop comes from confluence_stop_geometry -- the clamp with both
    knobs at 0; arm S keeps a structural stop up to
    CONFLUENCE_STRUCTURAL_STOP_PCT (tp1/tp2 against that risk, the ceiling
    stored as stop_ceiling_pct); arm D returns None beyond
    CONFLUENCE_STOP_DROP_PCT.
```

Leave everything from `if tp1 is None:` onwards unchanged, including `stamp_confluence_acceptance(plan, df, level)`.

- [ ] **Step 5: Run the tests**

Run each:
- `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_build.py`
- `python scripts/dev/testrun.py file tests/planning/test_confluence_stop_clamp.py`
- `python scripts/dev/testrun.py file tests/planning/test_build_confluence_plan.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py`
- `python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`

Expected: all pass. The goldens prove the refactor and the knobs-off path changed nothing.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/planning/builders.py`
Expected: `build_confluence_plan` is **not** listed (it is now B(13)); confirm with `python -m radon cc -s swingbot/core/planning/builders.py | grep build_confluence_plan`. `build_strategy_plan - C (13)` is pre-existing.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/planning/builders.py tests/planning/test_confluence_stop_build.py
git commit -m "feat(v139): build_confluence_plan takes its stop from confluence_stop_geometry

Knobs at 0: byte-identical (v139 and v129 goldens). _confluence_candidates
extracted so the function ends at complexity 13 with the drop branch.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-6: `plan_stop_ceiling` returns the stored ceiling; `risk_sizing_ok` covers it

**Files:**
- Modify: `swingbot/core/planning/stop_scope.py` (`plan_stop_ceiling` ~line 49, `risk_sizing_ok` ~line 56)
- Test: `tests/planning/test_stop_scope.py` (append)
- Create: `tests/planning/test_plan_manager_confluence_ceiling.py`

**Interfaces:**
- Consumes: `TradePlanV2.stop_ceiling_pct` (V139-1), `account.compute_position_size`.
- Produces:
  - `plan_stop_ceiling(plan) -> float`: the stored `stop_ceiling_pct` when set, for any source.
  - `risk_sizing_ok(plan, sizing_fn=None) -> bool`: also checks plans with a stored ceiling.

  Read unchanged by `plan_manager._step_pending` (`plan_manager.py:731`), `plan_manager._warn_legacy_open_risk` (`:551`), `exit_sim._compression_fill` (`:567`), and by V139-7 and V139-8.

- [ ] **Step 1: Write the failing tests**

Append to `tests/planning/test_stop_scope.py`:

```python
def test_a_stored_ceiling_wins_for_any_source():
    confluence = SimpleNamespace(source="confluence", strategy="S/R Confluence",
                                 direction="bullish", horizon_key="4w", stop_ceiling_pct=4.0)
    assert ss.plan_stop_ceiling(confluence) == 4.0


def test_no_stored_ceiling_keeps_todays_answer(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    confluence = SimpleNamespace(source="confluence", strategy="S/R Confluence",
                                 direction="bullish", horizon_key="4w", stop_ceiling_pct=None)
    assert ss.plan_stop_ceiling(confluence) == HARD_MAX_PLANNED_LOSS_PCT


def test_a_plan_with_a_stored_ceiling_is_always_sizing_checked(monkeypatch):
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)
    plan = SimpleNamespace(strategy="S/R Confluence", direction="bullish",
                           trigger_price=100.0, stop_loss=96.0, stop_ceiling_pct=4.25)
    assert not ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: _sizing(mode="account_pct", stop=96.0))
    assert ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: _sizing(stop=96.0))


@pytest.mark.parametrize("d", [2.5, 4.0, 4.75])
def test_risk_pct_sizing_holds_the_dollar_loss_at_risk_per_trade(d, monkeypatch):
    from swingbot.core.market import opex
    from swingbot.core.planning import account
    monkeypatch.setattr(opex, "size_mult", lambda: 1.0)
    cfg = {"balance": 1_000_000.0, "risk_pct": config.RISK_PER_TRADE_PCT, "sizing_mode": "risk_pct",
           "max_position_pct": 100.0, "max_position_value_absolute": 0,
           "max_risk_amount_absolute": 0}
    entry = 100.0
    plan = SimpleNamespace(strategy="S/R Confluence", direction="bullish", trigger_price=entry,
                           stop_loss=entry * (1 - d / 100), stop_ceiling_pct=5.0)
    sizing = account.compute_position_size(entry, plan.stop_loss, cfg)
    budget = cfg["balance"] * config.RISK_PER_TRADE_PCT / 100
    distance = entry - plan.stop_loss
    assert sizing["mode"] == "risk_pct"
    assert sizing["shares"] * distance == pytest.approx(budget, abs=0.01 * distance)
    assert ss.risk_sizing_ok(plan, sizing_fn=lambda e, s: account.compute_position_size(e, s, cfg))
```

Create `tests/planning/test_plan_manager_confluence_ceiling.py`:

```python
"""v139 arm S: a confluence plan's stored ceiling is the ceiling
plan_manager._step_pending checks a stop-entry fill against."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_manager_pending import _mgr, _pending

# 3.75% under the 105.0 trigger: arm S at c = 4.0, exactly at c - headroom.
STOP = 105.0 * (1 - 0.0375)


def _poll(tmp_path, monkeypatch, price, **plan_kw):
    # poll() reads the wall clock; without this the quiet window returns [].
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)
    store, mgr = _mgr(tmp_path, FakePriceFeed([("AAPL", price)]))
    store.add(_pending(source="confluence", strategy="S/R Confluence", stop_loss=STOP, **plan_kw))
    return store, mgr.poll()


def test_a_fill_inside_the_headroom_fills(tmp_path, monkeypatch):
    store, events = _poll(tmp_path, monkeypatch, 105.2, stop_ceiling_pct=4.0)   # 3.93% at the fill
    assert [event.transition for event in events] == ["filled"]
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_a_fill_past_the_stored_ceiling_cancels_at_that_ceiling(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 106.0, stop_ceiling_pct=4.0)       # 4.66% at the fill
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(4.0)


def test_without_a_stored_ceiling_the_two_percent_cap_still_applies(tmp_path, monkeypatch):
    _, events = _poll(tmp_path, monkeypatch, 105.2)
    assert [event.transition for event in events] == ["cancelled_risk_cap"]
    assert events[0].detail["max_planned_loss_pct"] == pytest.approx(2.0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`, then `python scripts/dev/testrun.py file tests/planning/test_plan_manager_confluence_ceiling.py`
Expected: FAIL. `plan_stop_ceiling` returns 2.0 instead of 4.0. `risk_sizing_ok` returns `True` for the `account_pct` sizing. `test_a_fill_inside_the_headroom_fills` gets `cancelled_risk_cap`. The `d` parametrisation and the two-percent test already pass.

- [ ] **Step 3: Implement**

Replace `plan_stop_ceiling` and the first two lines of `risk_sizing_ok` in `stop_scope.py`:

```python
def plan_stop_ceiling(plan) -> float:
    """Return the persisted plan's allowed planned-loss percentage. v139: a
    stored stop_ceiling_pct (arm S) wins for any source; otherwise 2% for
    non-strategy plans and the v104 scope ceiling for strategy plans."""
    stored = getattr(plan, "stop_ceiling_pct", None)
    if stored is not None:
        return float(stored)
    if getattr(plan, "source", None) != "strategy":
        return HARD_MAX_PLANNED_LOSS_PCT
    return stop_ceiling(plan.strategy, plan.direction, plan.horizon_key)[0]


def _needs_risk_sizing(plan) -> bool:
    """v104 scope pairs, and (v139) any plan holding a stored structural-stop ceiling."""
    if getattr(plan, "stop_ceiling_pct", None) is not None:
        return True
    return in_scope(plan.strategy, plan.direction)


def risk_sizing_ok(plan, sizing_fn=None) -> bool:
    """Return whether a plan that needs it has safe risk-based dollar sizing."""
    if not _needs_risk_sizing(plan):
        return True
```

The rest of `risk_sizing_ok` (from `if sizing_fn is None:` on) is unchanged.

- [ ] **Step 4: Run the tests**

Run each:
- `python scripts/dev/testrun.py file tests/planning/test_stop_scope.py`
- `python scripts/dev/testrun.py file tests/planning/test_plan_manager_confluence_ceiling.py`
- `python scripts/dev/testrun.py file tests/planning/test_plan_manager_stop_ceiling.py`
- `python scripts/dev/testrun.py file tests/planning/test_plan_manager_pending.py`
- `python scripts/dev/testrun.py file tests/planning/test_compression_short_fill.py`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/stop_scope.py tests/planning/test_stop_scope.py tests/planning/test_plan_manager_confluence_ceiling.py
git commit -m "feat(v139): plan_stop_ceiling returns a stored stop_ceiling_pct; risk_sizing_ok covers it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V139-7: `attach_plan_v2` — ceiling, sizing and the drop reason on the live path

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (imports ~lines 33–36; a new `_no_plan_reason`; `attach_plan_v2` ~lines 371–388)
- Create: `tests/scanning/test_attach_confluence_stop_geometry.py`

**Interfaces:**
- Consumes: `builders.confluence_stop_dropped` (V139-5), `stop_scope.plan_stop_ceiling` / `risk_sizing_ok` (V139-6).
- Produces: new `item.plan_v2_rejected` values `"stop_beyond_confluence_ceiling"` and `"risk_sizing"`. `"risk_cap"` and `"no_qualifying_target"` keep their meaning.

**Cross-plan (audit 2026-10-10):** v147 may have rewritten the risk-cap block in `attach_plan_v2` (`swingbot/core/scanning/analyze.py`) to compute `loss_pct = planned_loss_pct(...)` and call `_reject_plan(..., plan=plan, margin=...)`. Check `git grep -n "loss_pct =\|_reject_plan(.*plan=plan" -- swingbot/core/scanning/analyze.py`. **If both exist (v147 merged),** keep v147's `loss_pct` assignment and its `_reject_plan(..., plan=plan, margin=…)` call; in Step 3 replace only the comparison and the margin base with the ceiling: `ceiling = plan_stop_ceiling(plan)`, `if loss_pct > ceiling + 1e-9:`, `margin=loss_pct - ceiling` (keeping v147's other arguments), and pass v147's extra keywords to the new `"risk_sizing"` rejection only if its `_reject_plan` requires them. The import step's "only use of `HARD_MAX_PLANNED_LOSS_PCT`" grep may then find a v147 use: remove the import only if no use remains after the edit. **Otherwise** as written.

Index Spec corrections 4 and 5. With both knobs at 0, `plan_stop_ceiling` returns 2.0 for every confluence plan and `risk_sizing_ok` is never called, so the live scan is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_attach_confluence_stop_geometry.py`:

```python
"""v139 on the live attach path: an arm S plan passes the risk check at its own
stored ceiling and must have dollar-risk sizing; an arm D drop is recorded as
stop_beyond_confluence_ceiling. Knobs at 0 change nothing."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import analyze, engine
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


def test_knobs_off_issue_todays_clamped_plan():
    item = _attach(_scenario(96.5, 108.0))
    assert item.plan_v2.stop_loss == pytest.approx(98.25)
    assert item.plan_v2.stop_ceiling_pct is None


def test_sizing_is_not_consulted_for_a_plan_without_a_stored_ceiling(monkeypatch):
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: pytest.fail("consulted"))
    assert _attach(_scenario(96.5, 108.0)).plan_v2 is not None


def test_arm_s_plan_passes_the_risk_check_at_its_own_ceiling(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 4.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: True)
    item = _attach(_scenario(96.5, 108.0))
    assert getattr(item, "plan_v2_rejected", None) is None
    assert item.plan_v2.stop_loss == 96.5
    assert item.plan_v2.stop_ceiling_pct == 4.0


def test_arm_s_plan_without_risk_based_sizing_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 4.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: False)
    item = _attach(_scenario(96.5, 108.0))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "risk_sizing"


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.5, 92.0)])
def test_arm_d_drop_is_recorded_with_its_own_reason(monkeypatch, direction, stop, target):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 3.0)
    item = _attach(_scenario(stop, target, direction=direction))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "stop_beyond_confluence_ceiling"


def test_arm_d_within_its_ceiling_keeps_todays_plan(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 4.0)
    assert _attach(_scenario(96.5, 108.0)).plan_v2.stop_loss == pytest.approx(98.25)


def test_no_target_is_still_no_qualifying_target(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 3.0)
    item = _attach(_scenario(98.5, 100.5))      # unclamped; 0.33R
    assert item.plan_v2_rejected == "no_qualifying_target"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py`
Expected: FAIL.
- `test_arm_s_plan_passes_...` gets `plan_v2_rejected == "risk_cap"`: the attach check still uses 2%.
- `test_arm_d_drop_...` gets `"no_qualifying_target"`.
- The `risk_sizing_ok` monkeypatches fail with `AttributeError: ... has no attribute 'risk_sizing_ok'` (`raising` defaults to `True`).

- [ ] **Step 3: Implement**

Imports in `analyze.py`: replace `from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct` with `from swingbot.core.risk_limits import planned_loss_pct`. `analyze.py:381` is the only use of the constant; confirm with `git grep -n "HARD_MAX_PLANNED_LOSS_PCT" -- swingbot/core/scanning/analyze.py`, and check that `git grep -n "analyze.HARD_MAX" -- tests` prints nothing. Then add:

```python
from swingbot.core.planning.builders import confluence_stop_dropped
from swingbot.core.planning.stop_scope import plan_stop_ceiling, risk_sizing_ok
```

Add this module function directly above `attach_plan_v2`:

```python
def _no_plan_reason(scenario, level_map) -> str:
    """Why build_confluence_plan returned None: v139 arm D's ceiling, or no
    level paying MIN_RISK_REWARD_RATIO."""
    if confluence_stop_dropped(scenario, level_map):
        return "stop_beyond_confluence_ceiling"
    return "no_qualifying_target"
```

In `attach_plan_v2`, change `_reject_plan(item, "no_qualifying_target", ticker, horizon_key)` to:

```python
            _reject_plan(item, _no_plan_reason(scenario, level_map), ticker, horizon_key)
```

Replace the risk-cap block (`if planned_loss_pct(plan.trigger_price, plan.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT + 1e-9:` through its `return`) with:

```python
        if planned_loss_pct(plan.trigger_price, plan.stop_loss) > plan_stop_ceiling(plan) + 1e-9:
            # Scenario building keeps the horizon's wider stop ceiling so
            # historical replay evaluates the same candidates (90e3ddef), but
            # PlanManager refuses to open any plan beyond its ceiling -- a
            # stop_entry plan is cancelled_risk_cap on fill and a market plan
            # would open in breach of the 2% rule. Posting it only issues an
            # alert the bot then cancels seconds later (GC=F, 2026-09-28).
            # v139: the ceiling is plan_stop_ceiling -- 2% unless arm S stored one.
            _reject_plan(item, "risk_cap", ticker, horizon_key)
            return
        if plan.stop_ceiling_pct is not None and not risk_sizing_ok(plan):
            # v139 arm S: a structural stop past 2% is honest only when the
            # position is sized to fixed dollar risk (spec § Arm S). Checked
            # only for such plans: a confluence plan's strategy is its primary
            # attribution, which in_scope() could otherwise match.
            _reject_plan(item, "risk_sizing", ticker, horizon_key)
            return
```

- [ ] **Step 4: Run the tests**

Run each:
- `python scripts/dev/testrun.py file tests/scanning/test_attach_confluence_stop_geometry.py`
- `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
- `python scripts/dev/testrun.py file tests/scanning/test_decision_debug_logs.py`

Expected: all pass.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/analyze.py swingbot/core/planning/stop_scope.py`
Expected: `_scan_one - E (36)` and `build_decision_context - D (24)` only. Both are pre-existing and untouched. `attach_plan_v2` and `_no_plan_reason` are not listed.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/analyze.py tests/scanning/test_attach_confluence_stop_geometry.py
git commit -m "feat(v139): attach_plan_v2 checks plan_stop_ceiling, sizes arm S plans, names the arm D drop

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
