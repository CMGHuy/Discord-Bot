# v190 part 1 — Store and selection: instrument v3, two store roots, integrity trims, PIT selection, span cuts, the instrument picking the store

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-24-v190-pit-alpaca-universe-design.md](../specs/2026-10-24-v190-pit-alpaca-universe-design.md)
**Index:** [2026-10-24-v190-pit-alpaca-universe_0-index.md](2026-10-24-v190-pit-alpaca-universe_0-index.md) — Goal, Global Constraints, Contracts, `## Parallelisation` and the task ledger live there; every task below implicitly includes the index's Global Constraints.

**Scope of this part:** V190-1..V190-6 — the worktree and `_SPECS["v3"]` with its `store="pit"` field; `history_store` serving two roots (`watchlist`, `pit`), both worktree-aware; the `_integrity.json` reader and the frame trim inside `history_store.load`; `training_data` selecting the PIT store with its own admission rule, the `research_end` cut, an intraday loader, signal cuts and the worker hand-off; `pit_membership` subtracting signal cuts from spans; `fetch_backtest_data.apply_data_source` letting the instrument pick the store and refusing a v3 run without its context frames.

**Working directory.** Every command below runs inside the worktree `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` (created in V190-1 Step 1). Agent shells reset their cwd and drop variables between calls, so `cd "$WT"` below means: set `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` in the same command (`WT=...; cd "$WT" && ...`) or substitute the path.

**Database.** No test in this part reaches a store (`get_engine()` is never called: every fixture is a CSV/JSON tree under `tmp_path`), so `/replicate-prod-db` is not needed for Part 1.

**Facts this part relies on (verified at `668fc59f`).**
- No module outside `training_data` calls `history_store.load` (`git grep -n "history_store.load("` → `training_data.py:124` only), so `training_data.load_intraday` (V190-4) is the only intraday seam and nothing else needs rewiring.
- `scripts/data/alpaca_history/store_io.sha256_file(path)` is the sha256 of the file's bytes; V190-4 compares `_integrity.json`'s `manifest_sha256["daily"]` against `hashlib.sha256(<daily _manifest.json bytes>).hexdigest()`, the same value. Part 3 (V190-15) writes it with `store_io.sha256_file`.
- `config.DATA_DIR` is `<project root>/data`; inside a worktree the project root is `.claude/worktrees/<name>`, whose `data/` has no git-ignored store directories.
- Two existing pins name `"v3"` as an unknown instrument (`tests/backtesting/instrument/test_contract.py:54-55`, `tests/backtesting/instrument/test_instrument_cli.py:31-35`); V190-1 moves them to `"v4"`. `tests/backtesting/test_instrument_stats_ledger.py:45` (ledger vocabulary) is V190-10's, not this part's.

# Phase 1 — Instrument v3

### Task V190-1: Worktree, `InstrumentSpec.store`, `_SPECS["v3"]`

**Model:** sonnet — one module's frozen dataclass and its tests, every value given by the spec; no lookahead or cross-package wiring yet.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/contract.py` (`InstrumentSpec` `:63-96`, `_SPECS`/`_V2_WINDOW`/`VERSIONS` `:105-127`)
- Modify: `swingbot/core/backtesting/instrument/cli.py` (module docstring `:1-8`, `add_instrument_arg` help text `:23-28`)
- Test: `tests/backtesting/instrument/test_contract.py`, `tests/backtesting/instrument/test_folds.py`, `tests/backtesting/instrument/test_instrument_cli.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (used by V190-6..V190-11):
  - worktree `.claude/worktrees/2026-10-24-v190-pit-alpaca-universe` on branch `2026-10-24-v190-pit-alpaca-universe`
  - `contract.STORES = (None, "pit")` — defined **above** `InstrumentSpec`
  - `InstrumentSpec.store: str | None = None` — the **last** field (after `liquidity_floor`); `__post_init__` raises `ValueError` for a value not in `STORES`
  - `contract._V3_WINDOW: dict` and `_SPECS["v3"] = replace(_SPECS["v2"], version="v3", **_V3_WINDOW)`
  - `contract.VERSIONS == ("v1", "v2", "v3")`, so every `--instrument` parser (`cli.add_instrument_arg`, `check_cache_coverage.py`) accepts `v3` with no further edit
  - `resolve("v3")`: `store="pit"`, `warmup_start="2016-01-04"`, `research_start="2017-01-01"`, `research_end="2025-12-31"`, `holdout_start="2026-01-01"`, `fold_test_years=(2021, 2022, 2023, 2024, 2025)`; every other field equal to `resolve("v2")`'s (universe `sp500_pit`, `V2_FILLS`, `V2_COSTS`, `V2_LIQUIDITY_FLOOR`, `fold_scheme="anchored_yearly"`, `purge=True`, `embargo_days=270`, both v1 windows `None`)
  - `folds.MIN_TRAIN_YEARS` stays `4` (pinned)

- [ ] **Step 1: Create the worktree**

```bash
cd E:/Documents/Private/Projects/Discord-Bot && git worktree list && git worktree add .claude/worktrees/2026-10-24-v190-pit-alpaca-universe -b 2026-10-24-v190-pit-alpaca-universe main
```

If `git worktree list` already shows this worktree, reuse it and skip the `add` (resume rule, `docs/claude/document-lifecycle.md`). Every later step runs in `$WT`.

- [ ] **Step 2: Update the pins the new field and version break, and write the failing v3 tests**

In `tests/backtesting/instrument/test_contract.py`:

1. Append `"store"` to `SPAN_FIELDS` (`:63-65`), so `test_span_fields_are_appended_after_the_fill_and_cost_fields` pins it as the last, defaulted field:

```python
SPAN_FIELDS = ["universe", "research_start", "research_end", "holdout_start", "fold_scheme",
               "fold_test_years", "purge", "embargo_days", "train_window", "validation_window",
               "warmup_start", "liquidity_floor", "store"]
```

2. `test_versions_lists_every_resolvable_instrument` (`:78-80`): `assert contract.VERSIONS == ("v1", "v2", "v3")`.
3. `test_unknown_version_is_refused` (`:53-55`): use `"v4"` in both the `match=` and the call.
4. Append:

```python
# --- v190: instrument v3, the PIT Alpaca store ------------------------------------------

def test_v3_values_are_the_spec_values():
    spec = resolve("v3")
    assert spec.version == "v3"
    assert spec.store == "pit"
    assert spec.warmup_start == "2016-01-04"
    assert spec.research_span == ("2017-01-01", "2025-12-31")
    assert spec.holdout_start == "2026-01-01"
    assert spec.fold_test_years == (2021, 2022, 2023, 2024, 2025)
    assert spec.live_constructor is True


def test_v3_is_v2_except_store_and_window():
    """Fills, costs, universe, liquidity floor, purge, embargo and the sealed
    holdout are v2's; only the store, the warm-up, the research start and the
    fold years differ (spec section 4)."""
    v2, v3 = resolve("v2"), resolve("v3")
    differing = {f.name for f in dataclasses.fields(InstrumentSpec)
                 if getattr(v2, f.name) != getattr(v3, f.name)}
    assert differing == {"version", "store", "warmup_start", "research_start",
                         "fold_test_years"}
    assert v3.fill_model is v2.fill_model and v3.cost_model is v2.cost_model
    assert v3.liquidity_floor == V2_LIQUIDITY_FLOOR
    assert (v3.universe, v3.purge, v3.embargo_days) == ("sp500_pit", True, 270)
    assert (v3.train_window, v3.validation_window) == (None, None)


def test_v1_and_v2_keep_todays_store_selection():
    assert resolve("v1").store is None
    assert resolve("v2").store is None


def test_store_values_are_a_closed_set():
    assert contract.STORES == (None, "pit")
    with pytest.raises(ValueError, match="unknown store 'watchlist'"):
        dataclasses.replace(resolve("v2"), store="watchlist")


def test_v2_values_are_untouched_by_v3():
    """v3 is built by replace(); v2's own spec object is unchanged."""
    v2 = resolve("v2")
    assert v2.research_span == ("2010-01-01", "2025-12-31")
    assert v2.warmup_start == "2009-06-01"
    assert v2.fold_test_years == tuple(range(2014, 2026))
```

In `tests/backtesting/instrument/test_folds.py`, below `test_v2_has_twelve_anchored_yearly_folds`, add:

```python
V3 = resolve("v3")


def test_v3_has_five_anchored_yearly_folds_from_a_2017_research_start():
    got = folds.anchored_folds(V3)
    assert [f.test_year for f in got] == [2021, 2022, 2023, 2024, 2025]
    assert got[0] == Fold(test_year=2021, train_start="2017-01-01", train_end="2020-12-31",
                          test_start="2021-01-01", test_end="2021-12-31")
    assert got[-1] == Fold(test_year=2025, train_start="2017-01-01", train_end="2024-12-31",
                           test_start="2025-01-01", test_end="2025-12-31")


def test_min_train_years_stays_four_so_2020_is_not_a_legal_v3_test_year():
    """Lowering the constant would loosen a gate v2 shares (quant-engineer finding 2)."""
    assert folds.MIN_TRAIN_YEARS == 4
    with pytest.raises(ValueError, match="fewer than 4 training years"):
        folds.anchored_folds(dataclasses.replace(V3, fold_test_years=(2020, 2021)))
```

In `tests/backtesting/instrument/test_instrument_cli.py`:

1. `test_flag_refuses_an_unknown_version` (`:31-35`): parse `["--instrument", "v4"]` and assert `"invalid choice: 'v4'"`.
2. Append:

```python
# --- v190: v3 inherits v2's windows and refusals ------------------------------------

def test_v3_train_is_its_research_span():
    assert cli.window_for(resolve("v3"), "train") == ("2017-01-01", "2025-12-31")


def test_v3_validation_is_the_sealed_holdout():
    with pytest.raises(SystemExit) as exc:
        cli.window_for(resolve("v3"), "validation")
    assert cli.HOLDOUT_SEALED in str(exc.value)
    assert "2026-01-01" in str(exc.value)


@pytest.mark.parametrize("date_from, date_to", [
    ("2016-01-04", "2018-12-31"),     # warm-up is not research
    ("2025-06-01", "2026-01-02"),     # reaches the sealed holdout
])
def test_v3_window_outside_the_research_span_is_refused(date_from, date_to):
    with pytest.raises(SystemExit) as exc:
        cli.check_inside_research(resolve("v3"), date_from, date_to)
    assert "research span 2017-01-01..2025-12-31" in str(exc.value)


def test_require_v1_refuses_v3_like_v2():
    with pytest.raises(SystemExit) as exc:
        cli.require_v1(resolve("v3"), "measure_arms.py", "phase 5")
    assert "--instrument v3 is not wired yet" in str(exc.value)


def test_help_names_v3_and_its_store():
    assert "market_data_pit" in _parser().format_help()
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/backtesting/instrument/test_contract.py tests/backtesting/instrument/test_folds.py tests/backtesting/instrument/test_instrument_cli.py
```

Expected: FAIL — `unknown instrument 'v3'`, `VERSIONS == ("v1", "v2")`, no `store` field, no `contract.STORES`.

- [ ] **Step 4: Implement in `contract.py` and `cli.py`**

`contract.py`:
- Above `InstrumentSpec`: `STORES = (None, "pit")`, commented: `None` = today's selection (`TRAINING_DATA_SOURCE`/`HISTORY_STORE_DIR`), `"pit"` = `data/market_data_pit/` (v190).
- After `liquidity_floor`, under a `# --- v190; the default keeps v1 and v2 on today's store ---` comment: `store: str | None = None`.
- `def __post_init__(self) -> None:` raising `ValueError(f"unknown store {self.store!r}; known: {STORES}")` when `self.store not in STORES`.
- After `_SPECS["v2"] = replace(...)` and **before** `VERSIONS = tuple(_SPECS)`:

```python
# v190 instrument v3: v2's contract on the point-in-time Alpaca store. Alpaca
# serves bars from 2016-01-04, so research starts 2017-01-01 and, with
# folds.MIN_TRAIN_YEARS = 4 unchanged, the first legal test year is 2021.
_V3_WINDOW = {
    "store": "pit",
    "warmup_start": "2016-01-04",
    "research_start": "2017-01-01",
    "research_end": "2025-12-31",
    "holdout_start": "2026-01-01",
    "fold_test_years": tuple(range(2021, 2026)),
}
_SPECS["v3"] = replace(_SPECS["v2"], version="v3", **_V3_WINDOW)
```

- Extend the module docstring by one sentence: v190 appends `store` as the last keyword field and adds `v3`, built from v2 by `replace`, so neither positional `_SPECS` line changes.

`cli.py`: the docstring's first line names ``--instrument v1|v2|v3``; the `--instrument` help text appends `"; v3 = v2's contract on the point-in-time Alpaca store (data/market_data_pit/), research 2017-2025"`. No logic change in `cli.py`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/backtesting/instrument/
```

Expected: `0 failed`, `0 xfailed` — including the untouched `test_v1_golden.py` and `test_v1_windows_pinned.py`.

- [ ] **Step 6: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
cd "$WT" && git add swingbot/core/backtesting/instrument/contract.py swingbot/core/backtesting/instrument/cli.py tests/backtesting/instrument/test_contract.py tests/backtesting/instrument/test_folds.py tests/backtesting/instrument/test_instrument_cli.py && git commit -m "feat(instrument): v3 -- v2's contract on the PIT Alpaca store, research 2017-2025, five folds (v190)"
```

# Phase 2 — The store and its integrity seam

### Task V190-2: Two store roots, worktree fallback for both

**Model:** sonnet — path resolution inside one module plus a routing-table row; behaviour fully given by the index contract.

**Files:**
- Modify: `swingbot/core/marketdata/history_store.py` (`store_root` `:38-45`; `timeframe_dir`, `file_path`, `manifest_path`, `manifest`, `require_manifest`, `load` `:48-100`; module docstring)
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS`, after the `data/market_data/` row at `:327-331`)
- Test: `tests/history_store/test_history_store.py`, `tests/dev/test_select_tests.py`

**Interfaces:**
- Consumes: the worktree from V190-1.
- Produces (used by V190-3, V190-4, V190-9, V190-15, V190-17):
  - constants `WATCHLIST = "watchlist"`, `PIT = "pit"`, `PIT_DIRNAME = "market_data_pit"`, `WATCHLIST_DIRNAME = "market_data"`
  - `store_key(store: str | None) -> str` — `None`/`"watchlist"` → `"watchlist"`, `"pit"` → `"pit"`, anything else `ValueError` (a Part-1 helper; `training_data` uses it)
  - `resolve_data_root(name: str) -> Path` — `<config.DATA_DIR>/<name>` when that directory exists; else, when `config.DATA_DIR` lies inside `<main>/.claude/worktrees/<x>/`, `<main>/data/<name>` if that exists; else `<config.DATA_DIR>/<name>`
  - `store_root(store: str | None = None) -> Path` — watchlist: `HISTORY_STORE_DIR` when set (unchanged rule, no worktree fallback for an explicit override), else `resolve_data_root("market_data")`; pit: `resolve_data_root("market_data_pit")`, **never** `HISTORY_STORE_DIR`
  - keyword-only `store: str | None = None` on `timeframe_dir`, `file_path`, `manifest_path`, `manifest`, `require_manifest`, `load` (each passes it down; `ticker_status` unchanged)
  - `require_manifest(..., store="pit")` names the PIT backfill command, not `TRAINING_DATA_SOURCE=yfinance`
  - `DATA_READERS` rows `("data/market_data_pit/", ("tests/history_store/",))` and `("data/universe/symbol_aliases.json", ("tests/history_store/",))`

- [ ] **Step 1: Write the failing tests**

In `tests/history_store/test_history_store.py`, make the default-root test hermetic (in a worktree, `data/market_data` is absent and would resolve to the main checkout's) and add the store tests:

```python
def test_default_root_is_data_market_data(monkeypatch, tmp_path):
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    assert hs.store_root() == tmp_path / "data" / "market_data"
    assert hs.store_root("watchlist") == tmp_path / "data" / "market_data"


# --- v190: the PIT store root, worktree resolution ------------------------------------

def _worktree(tmp_path, monkeypatch):
    """A fake main checkout with a worktree under .claude/worktrees/wt1; DATA_DIR
    points at the worktree's data/, as config computes it there."""
    main = tmp_path / "repo"
    wt_data = main / ".claude" / "worktrees" / "wt1" / "data"
    wt_data.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", str(wt_data))
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)
    return main, wt_data


def test_pit_root_is_data_market_data_pit(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    assert hs.store_root("pit") == tmp_path / "data" / "market_data_pit"
    assert hs.PIT_DIRNAME == "market_data_pit"


def test_pit_root_ignores_history_store_dir(monkeypatch, tmp_path):
    """HISTORY_STORE_DIR is set on the VM and in tests; it must never redirect
    the PIT store, and it still redirects the watchlist store."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "elsewhere"))
    assert hs.store_root("pit") == tmp_path / "data" / "market_data_pit"
    assert hs.store_root() == tmp_path / "elsewhere"


def test_unknown_store_is_rejected():
    with pytest.raises(ValueError, match="unknown history store 'sp500_pit'"):
        hs.store_root("sp500_pit")
    assert hs.store_key(None) == hs.store_key("watchlist") == "watchlist"
    assert hs.store_key("pit") == "pit"


@pytest.mark.parametrize("store, dirname", [(None, "market_data"), ("pit", "market_data_pit")])
def test_a_worktree_without_the_store_reads_the_main_checkouts(monkeypatch, tmp_path,
                                                                store, dirname):
    main, _ = _worktree(tmp_path, monkeypatch)
    (main / "data" / dirname).mkdir(parents=True)
    assert hs.store_root(store) == main / "data" / dirname


@pytest.mark.parametrize("store, dirname", [(None, "market_data"), ("pit", "market_data_pit")])
def test_a_worktrees_own_store_wins(monkeypatch, tmp_path, store, dirname):
    main, wt_data = _worktree(tmp_path, monkeypatch)
    (main / "data" / dirname).mkdir(parents=True)
    (wt_data / dirname).mkdir()
    assert hs.store_root(store) == wt_data / dirname


def test_missing_everywhere_names_the_local_path(monkeypatch, tmp_path):
    """No store in the worktree or the main checkout: the local path, so the
    MissingStoreError message names where this checkout looked."""
    _, wt_data = _worktree(tmp_path, monkeypatch)
    assert hs.store_root("pit") == wt_data / "market_data_pit"


def test_outside_a_worktree_nothing_falls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "plain" / "data"))
    (tmp_path / "data" / "market_data_pit").mkdir(parents=True)   # a sibling, not a main checkout
    assert hs.resolve_data_root("market_data_pit") == tmp_path / "plain" / "data" / "market_data_pit"


def test_store_keyword_reaches_paths_manifest_and_load(monkeypatch, tmp_path, store_root):
    """store_root fixture sets HISTORY_STORE_DIR (the watchlist store); the PIT
    store is a different tree under DATA_DIR, read only with store='pit'."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    pit = tmp_path / "data" / "market_data_pit"
    assert hs.file_path("AAPL", "daily", store="pit") == pit / "daily" / "AAPL.csv"
    assert hs.manifest_path("hourly", store="pit") == pit / "hourly" / hs.MANIFEST_NAME
    assert hs.file_path("AAPL", "daily") == store_root / "daily" / "AAPL.csv"
    _manifest(pit, "daily", {"AAPL": {"status": "ok"}})
    assert hs.manifest("daily", store="pit")["tickers"] == {"AAPL": {"status": "ok"}}
    assert hs.manifest("daily") is None
    with pytest.raises(hs.MissingStoreError, match="market_data_pit"):
        hs.require_manifest("hourly", store="pit")


def test_pit_missing_manifest_message_names_the_pit_backfill(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    with pytest.raises(hs.MissingStoreError) as exc:
        hs.require_manifest("daily", store="pit")
    message = str(exc.value)
    assert "--universe sp500_pit" in message
    assert "TRAINING_DATA_SOURCE=yfinance" not in message
```

(`load(..., store="pit")` reading a frame is pinned in V190-3, where it also applies the trim.)

In `tests/dev/test_select_tests.py`, after `test_data_read_path_routes_to_its_readers`, add:

```python
@pytest.mark.parametrize("path", [
    "data/market_data_pit/_integrity.json",
    "data/market_data_pit/daily/_manifest.json",
    "data/universe/symbol_aliases.json",
])
def test_pit_store_and_alias_table_route_to_the_history_store_suite(sel, tmp_path, path):
    """v190: the PIT store and the rename alias table are read by tests under
    tests/history_store/ (fixture copies, never the real files)."""
    repo = _with_readers(_repo(tmp_path))
    reader = repo / "tests/history_store/test_history_store.py"
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_text("X = 1\n", encoding="utf-8")
    result = sel.select([path], repo)
    assert (result.full, result.targets) == (False, ["tests/history_store/"])


def test_the_watchlist_store_row_is_unchanged(sel, tmp_path):
    """data/market_data_pit/ must not shadow, or be shadowed by, data/market_data/."""
    repo = _with_readers(_repo(tmp_path))
    for rel in ("tests/history_store/test_history_store.py",
                "tests/history_store/test_training_data.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("X = 1\n", encoding="utf-8")
    result = sel.select(["data/market_data/daily/AAPL.csv"], repo)
    assert (result.full, result.targets) == (False, [
        "tests/history_store/test_history_store.py", "tests/history_store/test_training_data.py"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_history_store.py tests/dev/test_select_tests.py
```

Expected: FAIL — `store_root()` takes no argument, no `store_key`/`resolve_data_root`/`PIT_DIRNAME`, the PIT paths widen in `select_tests`.

- [ ] **Step 3: Implement in `history_store.py`**

- Constants beside `ENV_VAR`: `WATCHLIST = "watchlist"`, `PIT = "pit"`, `WATCHLIST_DIRNAME = "market_data"`, `PIT_DIRNAME = "market_data_pit"`, `STORES = (WATCHLIST, PIT)`.
- `store_key(store)`: the normaliser in Interfaces; the `ValueError` reads `f"unknown history store {store!r}; expected one of {STORES}"`.
- `_main_checkout(data_dir: Path) -> Path | None`: the path before the first consecutive `(".claude", "worktrees")` pair in `data_dir.parts`, else `None` (plain parts scan, no `resolve()`, no filesystem access).
- `resolve_data_root(name)` as in Interfaces (two `is_dir()` checks).
- `store_root(store=None)`: `PIT` → `resolve_data_root(PIT_DIRNAME)`; watchlist → the existing override rule, with the no-override default now `resolve_data_root(WATCHLIST_DIRNAME)`. Docstring states that `HISTORY_STORE_DIR` names the watchlist store only and the PIT store is chosen by instrument v3 (no environment variable).
- Thread `*, store=None` through `timeframe_dir` → `file_path` / `manifest_path` → `manifest` → `require_manifest`, and `load` (which calls `file_path(..., store=store)`; the trim lands in V190-3).
- `require_manifest`: a `_missing_store_hint(store)` helper returns the existing text for the watchlist store and, for PIT, `"backfill it with scripts/data/fetch_alpaca_history.py --universe sp500_pit --root data/market_data_pit (one fetcher per root)"`.
- Module docstring: add that `data/market_data_pit/` is the fourth OHLCV directory with the same layout (v190), read with `store="pit"`, and that both default roots fall back to the main checkout's from a worktree.

In `scripts/dev/select_tests.py`, after the `data/market_data/` row add:

```python
    # v190: the point-in-time Alpaca store (data/market_data_pit/, its
    # _integrity.json included) and the rename alias table. Gitignored /
    # data-only: every reader is a tests/history_store/ fixture test, and the
    # whole directory is the target because V190-3/4/12..16 add files there.
    ("data/market_data_pit/", ("tests/history_store/",)),
    ("data/universe/symbol_aliases.json", ("tests/history_store/",)),
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/ tests/dev/test_select_tests.py
```

Expected: `0 failed`, `0 xfailed` — every existing `tests/history_store/` test (they select through `HISTORY_STORE_DIR`) unchanged.

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add swingbot/core/marketdata/history_store.py scripts/dev/select_tests.py tests/history_store/test_history_store.py tests/dev/test_select_tests.py && git commit -m "feat(history-store): a PIT store root beside the watchlist store, worktree fallback for both (v190)"
```

### Task V190-3: Integrity reader; frame trims in `history_store.load`

**Model:** opus — no-lookahead territory: the trim removes a reused symbol's foreign bars before any indicator or exit walk reads them, for every timeframe.

**Files:**
- Create: `swingbot/core/marketdata/pit_integrity.py`
- Modify: `swingbot/core/marketdata/history_store.py` (`load`, from V190-2)
- Create: `tests/history_store/test_pit_integrity.py`

**Interfaces:**
- Consumes: `history_store.store_root("pit")`, `history_store.PIT`, `history_store.store_key`, `history_store.MissingStoreError` (V190-2).
- Produces (used by V190-4, V190-15):
  - `INTEGRITY_NAME = "_integrity.json"`, `SCHEMA_VERSION = 1`
  - `NOT_IN_REPORT = "not in integrity report"`, `NO_BARS_REASON = "no bars"`, `NOT_ADMITTED = "not admitted"` (fallback when an entry has `admitted: false` and no `reason`)
  - `@dataclass(frozen=True) class Integrity: sha256: str; doc: dict`
    - `trim_window(ticker) -> tuple[str | None, str | None]` — `(trim.keep_from, trim.keep_before)`; `(None, None)` when the entry has no `trim` or the ticker is absent
    - `signal_cuts(ticker) -> list[tuple[str, str]]` — `[(start, end_excl), ...]` from the entry's `signal_cuts` triples (the reason dropped), sorted; `[]` when absent
    - `exclusion(ticker) -> str | None` — `NO_BARS_REASON` when the ticker is in `doc["no_bars"]`; `NOT_IN_REPORT` when it has no entry in `doc["tickers"]`; the entry's `reason` (else `NOT_ADMITTED`) when `admitted` is false; `None` when admitted
    - `manifest_sha256(timeframe) -> str | None` — `doc["manifest_sha256"].get(timeframe)`
    - every lookup normalises the ticker with `.upper().strip()`
  - `integrity_path(root: Path) -> Path` — `root / INTEGRITY_NAME`
  - `load_integrity(root: Path) -> Integrity | None` — `None` when the file is absent; `ValueError` naming the path when `doc["schema"] != SCHEMA_VERSION`; `sha256` = `hashlib.sha256(<file bytes>).hexdigest()`
  - `cached_integrity(root: Path) -> Integrity | None` — `load_integrity` memoised on `(path, st_mtime_ns, st_size)` (Part-1 helper for `history_store.load`; a rewritten file is re-read)
  - `apply_trim(frame, window) -> pd.DataFrame | None` — keeps `keep_from <= bar date < keep_before` (date-level for every timeframe: an intraday bar on `keep_before`'s date is dropped, one on `keep_from`'s date kept); `None` in, `None` out; an empty result is `None`; `(None, None)` returns the frame unchanged
  - `history_store.load(ticker, timeframe, session="rth", *, store=None)`: for `store="pit"` reads `cached_integrity(store_root("pit"))`; `None` → `MissingStoreError` naming `_integrity.json` and `check_history_store.py --pit`; otherwise applies `apply_trim(frame, integrity.trim_window(ticker))` after the session filter and before the empty check. The watchlist store's path is byte-identical (no integrity read).

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_pit_integrity.py`:

```python
"""v190 section 2.3 / 3: the _integrity.json reader and the frame trim that
removes a reused symbol's foreign bars inside history_store.load, before any
indicator or exit walk reads them. Fixture stores under tmp_path only."""
import hashlib
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store as hs
from swingbot.core.marketdata import pit_integrity as pi

#: MON's shape: a member until mid-2018, then the symbol reused by another issuer.
DOC = {
    "schema": 1, "generated_at": "2026-10-25T10:00:00Z",
    "store_start": "2016-01-04", "store_end": "2025-12-31",
    "thresholds": {}, "detector_sha": {},
    "manifest_sha256": {"daily": "d" * 64, "hourly": "h" * 64, "15min": None},
    "no_bars": ["FB"],
    "tickers": {
        "MON": {"admitted": True, "reason": None,
                "signal_cuts": [["2017-03-01", "2017-03-20", "missing run of 9 sessions"]],
                "trim": {"keep_from": None, "keep_before": "2018-06-08",
                         "reason": "break after last membership end"}},
        "ABC": {"admitted": True, "reason": None, "signal_cuts": [],
                "trim": {"keep_from": "2016-03-01", "keep_before": None,
                         "reason": "break before first membership start"}},
        "OK1": {"admitted": True, "reason": None, "signal_cuts": [], "trim": None},
        "BAD": {"admitted": False, "reason": "unresolved break 2019-05-02",
                "signal_cuts": [], "trim": None},
        "MUTE": {"admitted": False, "reason": None, "signal_cuts": [], "trim": None},
    },
}


def _write_doc(root, doc=DOC):
    root.mkdir(parents=True, exist_ok=True)
    path = root / pi.INTEGRITY_NAME
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


@pytest.fixture
def pit_root(tmp_path, monkeypatch):
    """A PIT store under DATA_DIR; HISTORY_STORE_DIR points elsewhere on purpose."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HISTORY_STORE_DIR", str(tmp_path / "watchlist_store"))
    return tmp_path / "data" / "market_data_pit"


def _csv(root, ticker, timeframe, frame):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f"{ticker}.csv", index_label=hs.INDEX_NAMES[timeframe])


# --- the reader -----------------------------------------------------------------------

def test_absent_report_is_none(tmp_path):
    assert pi.load_integrity(tmp_path) is None
    assert pi.integrity_path(tmp_path) == tmp_path / "_integrity.json"


def test_report_carries_the_sha256_of_its_bytes(tmp_path):
    path = _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert got.doc == DOC


def test_unknown_schema_is_refused(tmp_path):
    _write_doc(tmp_path, {**DOC, "schema": 2})
    with pytest.raises(ValueError, match="_integrity.json"):
        pi.load_integrity(tmp_path)


def test_trim_window_signal_cuts_and_manifest_hashes(tmp_path):
    _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.trim_window("MON") == (None, "2018-06-08")
    assert got.trim_window(" abc ") == ("2016-03-01", None)
    assert got.trim_window("OK1") == (None, None)
    assert got.trim_window("ZZZ") == (None, None)
    assert got.signal_cuts("MON") == [("2017-03-01", "2017-03-20")]
    assert got.signal_cuts("OK1") == [] and got.signal_cuts("ZZZ") == []
    assert got.manifest_sha256("daily") == "d" * 64
    assert got.manifest_sha256("15min") is None


def test_exclusion_states_a_reason_for_every_refusal(tmp_path):
    _write_doc(tmp_path)
    got = pi.load_integrity(tmp_path)
    assert got.exclusion("MON") is None and got.exclusion("OK1") is None
    assert got.exclusion("BAD") == "unresolved break 2019-05-02"
    assert got.exclusion("MUTE") == pi.NOT_ADMITTED
    assert got.exclusion("FB") == pi.NO_BARS_REASON
    assert got.exclusion("ZZZ") == pi.NOT_IN_REPORT


def test_cached_integrity_rereads_a_rewritten_file(tmp_path):
    _write_doc(tmp_path)
    first = pi.cached_integrity(tmp_path)
    assert pi.cached_integrity(tmp_path) is first
    _write_doc(tmp_path, {**DOC, "no_bars": ["FB", "XYZW"]})
    assert pi.cached_integrity(tmp_path).exclusion("XYZW") == pi.NO_BARS_REASON


# --- apply_trim -------------------------------------------------------------------------

def test_trim_keeps_the_bars_before_a_break_after_the_last_membership_end():
    frame = _bars("2018-06-01", "2018-06-15")
    got = pi.apply_trim(frame, (None, "2018-06-08"))
    assert got.index.max() == pd.Timestamp("2018-06-07")
    assert got.index.min() == pd.Timestamp("2018-06-01")


def test_trim_keeps_the_bars_after_a_break_before_the_first_membership_start():
    frame = _bars("2016-02-22", "2016-03-04")
    got = pi.apply_trim(frame, ("2016-03-01", None))
    assert got.index.min() == pd.Timestamp("2016-03-01")
    assert got.index.max() == pd.Timestamp("2016-03-04")


def test_trim_is_date_level_on_intraday_bars():
    frame = _bars("2018-06-07 09:30", "2018-06-08 15:30", freq="h")
    got = pi.apply_trim(frame, (None, "2018-06-08"))
    assert got.index.max() < pd.Timestamp("2018-06-08")
    assert (got.index.date == pd.Timestamp("2018-06-07").date()).all()


def test_trim_edge_cases():
    frame = _bars("2018-06-01", "2018-06-15")
    assert pi.apply_trim(frame, (None, None)) is frame
    assert pi.apply_trim(None, ("2016-01-04", None)) is None
    assert pi.apply_trim(frame, (None, "2018-06-01")) is None          # trimmed to nothing
    assert pi.apply_trim(frame, ("2018-06-10", "2018-06-10")) is None


# --- history_store.load(store="pit") --------------------------------------------------

def test_pit_load_applies_the_trim_on_every_timeframe(pit_root):
    _write_doc(pit_root)
    _csv(pit_root, "MON", "daily", _bars("2018-05-01", "2022-12-30"))
    _csv(pit_root, "MON", "hourly", _bars("2018-06-06 09:30", "2018-06-12 15:30", freq="h"))
    _csv(pit_root, "MON", "15min", _bars("2018-06-07 09:30", "2018-06-08 15:45", freq="15min"))
    for timeframe in hs.TIMEFRAMES:
        got = hs.load("MON", timeframe, store="pit")
        assert got.index.max() < pd.Timestamp("2018-06-08"), timeframe


def test_pit_load_trimmed_to_nothing_is_none(pit_root):
    _write_doc(pit_root)
    _csv(pit_root, "MON", "daily", _bars("2019-01-02", "2019-03-29"))   # only reused-issuer bars
    assert hs.load("MON", "daily", store="pit") is None


def test_pit_load_without_a_report_refuses(pit_root):
    _csv(pit_root, "OK1", "daily", _bars("2016-01-04", "2016-03-31"))
    with pytest.raises(hs.MissingStoreError, match="_integrity.json"):
        hs.load("OK1", "daily", store="pit")


def test_untrimmed_pit_ticker_loads_whole(pit_root):
    _write_doc(pit_root)
    frame = _bars("2016-01-04", "2016-03-31")
    _csv(pit_root, "OK1", "daily", frame)
    assert len(hs.load("OK1", "daily", store="pit")) == len(frame)


def test_watchlist_load_never_reads_a_report(tmp_path, monkeypatch, store_root):
    """The watchlist store's load is today's: a stray _integrity.json in it is ignored."""
    _write_doc(store_root)
    _csv(store_root, "MON", "daily", _bars("2018-05-01", "2018-12-31"))
    got = hs.load("MON", "daily")
    assert got.index.max() == pd.Timestamp("2018-12-31")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_pit_integrity.py
```

Expected: FAIL — `ModuleNotFoundError: swingbot.core.marketdata.pit_integrity`.

- [ ] **Step 3: Implement `swingbot/core/marketdata/pit_integrity.py`**

The module docstring states: the file is written only by `scripts/data/check_history_store.py --pit` (V190-15) and frozen before a re-baseline; this module reads it and never writes; `marketdata` never imports `scripts/`; the trim is causal (its window comes from membership spans and a break test frozen before any strategy result is read, spec section 2.3); and the full `_integrity.json` shape in the index's § Contracts. Public names and behaviour exactly as in Interfaces. Notes the signatures leave open:

- `apply_trim` compares on the normalised day: `days = frame.index.normalize()`; mask `days >= Timestamp(keep_from)` and `days < Timestamp(keep_before)` for each bound that is not `None`; return `None` when the masked frame is empty.
- `cached_integrity` keeps a module-level `dict[Path, tuple[tuple[int, int], Integrity | None]]`; an absent file returns `None` without caching, so a report written later is found.
- `Integrity._entry(ticker) -> dict` (private) returns `{}` for a missing entry; each accessor treats a `None` sub-field (`"trim": null`) like a missing one.

- [ ] **Step 4: Apply the trim in `history_store.load`**

`load` gains the PIT branch through a helper so `load` stays flat:

```python
def _pit_trim(frame: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """The integrity report's trim window for one PIT ticker (spec section 2.3)."""
    from swingbot.core.marketdata import pit_integrity
    root = store_root(PIT)
    integrity = pit_integrity.cached_integrity(root)
    if integrity is None:
        raise MissingStoreError(
            f"PIT store has no integrity report: {pit_integrity.integrity_path(root)} -- "
            f"build it with scripts/data/check_history_store.py --pit before any run reads it")
    return pit_integrity.apply_trim(frame, integrity.trim_window(ticker))
```

(local import: `pit_integrity` imports nothing from `history_store`, but keeping the import local leaves the watchlist path's import graph unchanged.) In `load`, after the session filter: `if store_key(store) == PIT: frame = _pit_trim(frame, ticker)`, then `return frame if frame is not None and len(frame) else None`. Docstring: a PIT frame is returned already trimmed; an empty trim result is `None` like an empty file.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/
```

Expected: `0 failed`, `0 xfailed`.

- [ ] **Step 6: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
cd "$WT" && git add swingbot/core/marketdata/pit_integrity.py swingbot/core/marketdata/history_store.py tests/history_store/test_pit_integrity.py && git commit -m "feat(history-store): read the PIT integrity report and trim reused-symbol bars on load (v190)"
```

# Phase 3 — Selection and signal cuts

### Task V190-4: PIT selection in `training_data`; worker store hand-off

**Model:** opus — the anti-goal seam: the PIT store must never become the default selection, the admission rule must not undo the survivorship fix, and every frame (daily, intraday, context) must stop at `research_end`; crosses `marketdata` and three backtest scripts.

**Files:**
- Modify: `swingbot/core/marketdata/training_data.py` (`_Selection` `:42-46`, `select` `:76-90`, `_load_alpaca` `:119-128`, `provenance` `:157-165`; new helpers)
- Modify: `scripts/backtest/cache_dir_source.py` (`pool_kwargs` `:101-103`)
- Modify: `scripts/backtest/measure_arms.py:130-131`, `scripts/backtest/measure_acceptance_exits.py:121-122`, `scripts/backtest/measure_fvg_bullish_diagnostic.py:187-188` (`initargs=` only)
- Modify: `tests/history_store/test_training_data.py` (`test_alpaca_provenance` `:155-161`)
- Create: `tests/history_store/test_training_data_pit.py`

**Interfaces:**
- Consumes: `history_store.PIT`, `WATCHLIST`, `store_key`, `store_root(store)`, `manifest_path(..., store=)`, `require_manifest(..., store=)`, `file_path(..., store=)`, `load(..., store=)` (V190-2, V190-3); `pit_integrity.load_integrity`, `integrity_path`, `Integrity.exclusion`, `.trim_window`, `.signal_cuts`, `.manifest_sha256`, `.sha256` (V190-3).
- Produces (used by V190-6, V190-7, V190-15, V190-16):
  - `class StaleIntegrityError(history_store.MissingStoreError)` — callers that already turn `MissingStoreError` into `SystemExit` (`run_backtest_range._resolve_data_source`, `tune_strategy._select_source`) cover it unchanged
  - `PIT_ADMITTED = ("ok", "flagged: no-reference")` (literal strings, pinned equal to `identity.OK` / `identity.NO_REFERENCE`)
  - reason constants `TRIMMED_EMPTY = "empty after integrity trim"`, `NO_BARS_BY_UNTIL = "no bars on or before the cut"`; `_pit_exclusions` prefixes integrity refusals with `"integrity: "`
  - `select(name: str | None = None, store: str | None = None, until: str | None = None) -> str` — positional, so a pool initializer passes all three; `store="pit"` needs source `alpaca` (else `ValueError`); `until` without the PIT store is a `ValueError`; with no arguments the result is today's selection
  - `active_store() -> str` — `"watchlist"` | `"pit"` (`"watchlist"` for a yfinance selection too)
  - `selection_args() -> tuple` — `(source,)` unless the PIT store, then `("alpaca", "pit", until)`
  - `signal_cuts() -> dict[str, list[tuple[str, str]]] | None` — `None` unless the PIT store; else `{ticker: integrity.signal_cuts(ticker)}` for every admitted manifest ticker
  - `load_intraday(ticker: str, timeframe: str, session: str = "rth") -> pd.DataFrame | None` — not the PIT store: exactly `history_store.load(ticker, timeframe, session)` (today's direct read); PIT: `None` for an excluded or unlisted ticker (the daily manifest is the admission authority), else the trimmed frame cut at `until`
  - `load_daily(ticker)` on the PIT store: trimmed frame cut at `until` (bars dated after `until` removed; `None` and a stated exclusion when nothing is left)
  - `_pit_exclusions(manifest: dict, integrity: Integrity, *, store: str) -> dict[str, str]`
  - `provenance()`: alpaca branch gains `"store"` (`"watchlist"` | `"pit"`); PIT also `"integrity_sha256"`; `store_dir` is the selected store's root; the yfinance branch is unchanged
  - `cache_dir_source.pool_kwargs() == {"initializer": training_data.select, "initargs": training_data.selection_args()}`; the three `measure_*` pools pass `initargs=training_data.selection_args()`

- [ ] **Step 1: Pin the watchlist provenance's new key**

In `tests/history_store/test_training_data.py::test_alpaca_provenance`, the expected dict gains `"store": "watchlist"` (additive; `docs/claude/schema-evolution.md`: an old sidecar without it reads as the watchlist store, no upcasting). Nothing else in that file changes — every existing pin there is the byte-identity pin for the watchlist store.

- [ ] **Step 2: Write the failing PIT tests**

Create `tests/history_store/test_training_data_pit.py`:

```python
"""v190 section 2.2 / 3: training_data on the point-in-time Alpaca store --
admission (no-reference in, short-overlap/price-mismatch/integrity out), the
frozen-report refusals, frame trims, the research_end cut on daily, intraday
and context frames, signal cuts, provenance, and the store choice reaching
pool workers. The watchlist store keeps every rule it has today."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import history_store, pit_integrity, training_data

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

UNTIL = "2025-12-31"

#: Daily manifest statuses on the PIT store.
PIT_ENTRIES = {"AAA": "ok", "DEL": "flagged: no-reference", "SHO": "flagged: short-overlap",
               "MIS": "flagged: price-mismatch", "MON": "ok", "BAD": "ok", "GONE": "ok",
               "ZOMB": "ok", "LATE": "ok", "SPY": "ok", "FB": "skipped: no bars"}
#: Daily files on disk: GONE has none; ZOMB's bars all fall in its trimmed side;
#: LATE lists after the cut; AAA and SPY run into the sealed 2026.
PIT_FILES = {"AAA": ("2016-01-04", "2026-03-31"), "DEL": ("2016-01-04", "2019-06-28"),
             "SHO": ("2016-01-04", "2016-06-30"), "MIS": ("2016-01-04", "2016-06-30"),
             "MON": ("2016-01-04", "2022-12-30"), "BAD": ("2016-01-04", "2020-12-31"),
             "ZOMB": ("2019-01-02", "2019-06-28"), "LATE": ("2026-02-02", "2026-03-31"),
             "SPY": ("2016-01-04", "2026-03-31")}
ADMIT = {"admitted": True, "reason": None, "signal_cuts": [], "trim": None}
REPORT_TICKERS = {
    "AAA": {**ADMIT, "signal_cuts": [["2017-03-01", "2017-03-20", "missing run of 9 sessions"]]},
    "DEL": ADMIT, "SHO": ADMIT, "MIS": ADMIT, "GONE": ADMIT, "LATE": ADMIT, "SPY": ADMIT,
    "MON": {**ADMIT, "trim": {"keep_from": None, "keep_before": "2018-06-08",
                              "reason": "break after last membership end"}},
    "ZOMB": {**ADMIT, "trim": {"keep_from": None, "keep_before": "2018-01-01",
                               "reason": "break after last membership end"}},
    "BAD": {**ADMIT, "admitted": False, "reason": "unresolved break 2019-05-02"},
}
EXPECTED_EXCLUDED = {"BAD": "integrity: unresolved break 2019-05-02",
                     "FB": "skipped: no bars", "GONE": "no file",
                     "MIS": "flagged: price-mismatch", "SHO": "flagged: short-overlap"}


def _bars(start, end, freq="B"):
    idx = pd.date_range(start, end, freq=freq)
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


def _csv(root, ticker, timeframe, frame):
    folder = root / timeframe
    folder.mkdir(parents=True, exist_ok=True)
    frame.to_csv(folder / f"{ticker}.csv", index_label=history_store.INDEX_NAMES[timeframe])


def _write_manifest(root, entries) -> bytes:
    path = root / "daily" / "_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timeframe": "daily", "feed": "sip", "adjustment": "all",
                                "hash": "pit-h",
                                "tickers": {t: {"status": s} for t, s in entries.items()}}))
    return path.read_bytes()


def _write_report(root, manifest_bytes) -> Path:
    path = root / pit_integrity.INTEGRITY_NAME
    path.write_text(json.dumps({
        "schema": 1, "generated_at": "2026-10-25T10:00:00Z", "store_start": "2016-01-04",
        "store_end": UNTIL, "thresholds": {}, "detector_sha": {},
        "manifest_sha256": {"daily": hashlib.sha256(manifest_bytes).hexdigest(),
                            "hourly": None, "15min": None},
        "no_bars": ["FB"], "tickers": REPORT_TICKERS}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Both stores on disk: the watchlist store through HISTORY_STORE_DIR (as on
    the VM and in every other test), the PIT store under DATA_DIR."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    watch = tmp_path / "market_data"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watch))
    _csv(watch, "AAPL", "daily", _bars("2016-01-04", "2016-03-31"))
    _csv(watch, "DEL", "daily", _bars("2016-01-04", "2016-03-31"))
    (watch / "daily" / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": "w-h",
         "tickers": {"AAPL": {"status": "ok"}, "DEL": {"status": "flagged: no-reference"}}}))
    pit = tmp_path / "data" / "market_data_pit"
    for ticker, (start, end) in PIT_FILES.items():
        _csv(pit, ticker, "daily", _bars(start, end))
    _csv(pit, "AAA", "hourly", _bars("2025-12-30 09:30", "2026-01-02 15:30", freq="h"))
    _csv(pit, "MON", "hourly", _bars("2018-06-06 09:30", "2018-06-12 15:30", freq="h"))
    _write_report(pit, _write_manifest(pit, PIT_ENTRIES))
    return watch, pit


def _select_pit():
    return training_data.select("alpaca", "pit", UNTIL)


# --- the default never moves ----------------------------------------------------------

def test_default_selection_never_picks_the_pit_store(stores):
    assert training_data.select() == "alpaca"
    assert training_data.active_store() == "watchlist"
    assert training_data.available_tickers() == ["AAPL"]
    assert training_data.signal_cuts() is None
    assert training_data.selection_args() == ("alpaca",)


def test_watchlist_exclusions_still_reject_no_reference(stores):
    """Both stores share the status strings; only the PIT store admits no-reference."""
    training_data.select("alpaca")
    assert training_data.excluded() == {"DEL": "flagged: no-reference"}
    manifest = {"tickers": {"X": {"status": "flagged: no-reference"}}}
    assert training_data._manifest_exclusions(manifest) == {"X": "flagged: no-reference"}


def test_yfinance_selection_args_are_unchanged(stores):
    training_data.select("yfinance")
    assert training_data.selection_args() == ("yfinance",)
    assert training_data.active_store() == "watchlist"


# --- admission ------------------------------------------------------------------------

def test_pit_admission_follows_section_2_2(stores):
    assert _select_pit() == "alpaca"
    assert training_data.active_store() == "pit"
    assert training_data.excluded() == EXPECTED_EXCLUDED
    assert training_data.available_tickers() == ["AAA", "DEL", "LATE", "MON", "SPY", "ZOMB"]


def test_pit_admitted_strings_are_the_fetchers_identity_statuses():
    from alpaca_history import identity
    assert training_data.PIT_ADMITTED == (identity.OK, identity.NO_REFERENCE)


def test_pit_exclusions_function_directly(stores):
    _, pit = stores
    manifest = history_store.require_manifest("daily", store="pit")
    integrity = pit_integrity.load_integrity(pit)
    assert training_data._pit_exclusions(manifest, integrity, store="pit") == EXPECTED_EXCLUDED


def test_pit_requires_the_integrity_report(stores):
    _, pit = stores
    (pit / pit_integrity.INTEGRITY_NAME).unlink()
    with pytest.raises(history_store.MissingStoreError, match="_integrity.json"):
        _select_pit()
    assert training_data._SELECTION is None


def test_a_store_refreshed_after_the_freeze_is_refused(stores):
    _, pit = stores
    _write_manifest(pit, {**PIT_ENTRIES, "NEW": "ok"})          # a --mode update ran
    with pytest.raises(training_data.StaleIntegrityError, match="check_history_store.py --pit"):
        _select_pit()
    assert issubclass(training_data.StaleIntegrityError, history_store.MissingStoreError)
    assert training_data._SELECTION is None


@pytest.mark.parametrize("args, match", [
    (("yfinance", "pit", UNTIL), "PIT store"),
    (("alpaca", None, UNTIL), "until"),
    (("alpaca", "sp500_pit", None), "unknown history store"),
])
def test_store_argument_errors(stores, args, match):
    with pytest.raises(ValueError, match=match):
        training_data.select(*args)


# --- frames: trims and the research_end cut ---------------------------------------------

def test_pit_daily_and_context_frames_stop_at_until(stores):
    _select_pit()
    for ticker in ("AAA", "SPY"):
        frame = training_data.load_daily(ticker)
        assert frame.index.max() == pd.Timestamp(UNTIL), ticker


def test_pit_daily_applies_the_trim(stores):
    _select_pit()
    assert training_data.load_daily("MON").index.max() < pd.Timestamp("2018-06-08")


def test_no_reference_member_loads_whole(stores):
    _select_pit()
    assert training_data.load_daily("DEL").index.max() == pd.Timestamp("2019-06-28")


def test_trimmed_to_nothing_is_excluded_with_a_reason(stores):
    _select_pit()
    assert training_data.load_daily("ZOMB") is None
    assert training_data.excluded()["ZOMB"] == training_data.TRIMMED_EMPTY


def test_no_bar_by_until_is_excluded_with_a_reason(stores):
    _select_pit()
    assert training_data.load_daily("LATE") is None
    assert training_data.excluded()["LATE"] == training_data.NO_BARS_BY_UNTIL


def test_no_intraday_bar_on_or_after_the_holdout_is_reachable(stores):
    _select_pit()
    aaa = training_data.load_intraday("AAA", "hourly")
    assert aaa.index.max() < pd.Timestamp("2026-01-01")
    assert aaa.index.max() >= pd.Timestamp("2025-12-31 09:30")
    assert training_data.load_intraday("MON", "hourly").index.max() < pd.Timestamp("2018-06-08")
    assert training_data.load_intraday("BAD", "hourly") is None      # excluded
    assert training_data.load_intraday("QQQQ", "hourly") is None     # not in the store


def test_watchlist_intraday_is_todays_direct_read(stores):
    watch, _ = stores
    _csv(watch, "AAPL", "hourly", _bars("2025-12-30 09:30", "2026-01-02 15:30", freq="h"))
    training_data.select("alpaca")
    pd.testing.assert_frame_equal(training_data.load_intraday("AAPL", "hourly"),
                                  history_store.load("AAPL", "hourly"))


# --- signal cuts, provenance ---------------------------------------------------------------

def test_signal_cuts_cover_every_admitted_ticker(stores):
    _select_pit()
    cuts = training_data.signal_cuts()
    assert cuts["AAA"] == [("2017-03-01", "2017-03-20")]
    assert cuts["DEL"] == [] and "BAD" not in cuts and "SHO" not in cuts


def test_pit_provenance_names_the_store_and_the_report(stores):
    _, pit = stores
    _select_pit()
    report = pit / pit_integrity.INTEGRITY_NAME
    assert training_data.provenance() == {
        "data_source": "alpaca", "feed": "sip", "adjustment": "all", "manifest_hash": "pit-h",
        "store": "pit", "integrity_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "store_dir": str(pit), "excluded": EXPECTED_EXCLUDED}


# --- workers ---------------------------------------------------------------------------------

def test_a_worker_reselecting_from_selection_args_lands_on_the_same_store_and_cut(stores):
    _select_pit()
    args = training_data.selection_args()
    assert args == ("alpaca", "pit", UNTIL)
    training_data.reset()                         # what a spawned worker starts from
    training_data.select(*args)
    assert training_data.active_store() == "pit"
    assert training_data.load_daily("AAA").index.max() == pd.Timestamp(UNTIL)


def test_pool_kwargs_hand_workers_the_pit_store(stores):
    import cache_dir_source as cds
    _select_pit()
    assert cds.pool_kwargs() == {"initializer": training_data.select,
                                 "initargs": ("alpaca", "pit", UNTIL)}


@pytest.mark.parametrize("script", ["measure_arms.py", "measure_acceptance_exits.py",
                                    "measure_fvg_bullish_diagnostic.py"])
def test_measure_pools_pass_the_whole_selection(script):
    source = (ROOT / "scripts" / "backtest" / script).read_text(encoding="utf-8")
    assert "initargs=training_data.selection_args()" in source
    assert "initargs=(training_data.active(),)" not in source
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_training_data_pit.py tests/history_store/test_training_data.py
```

Expected: FAIL — `select()` takes at most 1 argument; no `active_store`, `selection_args`, `signal_cuts`, `load_intraday`, `StaleIntegrityError`; provenance lacks `store`.

- [ ] **Step 4: Implement in `training_data.py`**

- Import `pit_integrity` beside `history_store`; add the constants and `StaleIntegrityError` from Interfaces. Module docstring: add a v190 paragraph — the PIT store (`data/market_data_pit/`) is selected only by `select(..., store="pit")`, which instrument v3 calls through `fetch_backtest_data.apply_data_source`; it is never the default; it admits `flagged: no-reference`; it refuses without, or with a stale, `_integrity.json`; every frame it returns is trimmed and cut at `until`.
- `_Selection` gains `store: str = history_store.WATCHLIST`, `until: str | None = None`, `integrity: pit_integrity.Integrity | None = None` (defaults keep every existing construction valid).
- `select(name=None, store=None, until=None)` keeps today's first lines (`_SELECTION = None`, source normalise/validate, yfinance short-cut), validates the store arguments in a helper (`_check_store_args(source, key, until)`: PIT with yfinance → `ValueError("the PIT store holds Alpaca bars; source 'yfinance' cannot read it")`; `until` off the PIT store → `ValueError("until cuts the PIT store only")`) **before** the yfinance short-cut, then assigns `_select_pit(until)` or `_select_watchlist()` and logs the root. `_select_watchlist()` is today's two lines (`require_manifest("daily")`, `_manifest_exclusions`), unchanged.
- `_select_pit(until)`:

```python
def _select_pit(until: str | None) -> _Selection:
    manifest = history_store.require_manifest("daily", store=history_store.PIT)
    root = history_store.store_root(history_store.PIT)
    integrity = pit_integrity.load_integrity(root)
    if integrity is None:
        raise history_store.MissingStoreError(
            f"PIT store has no integrity report: {pit_integrity.integrity_path(root)} -- "
            f"build it with scripts/data/check_history_store.py --pit")
    _require_fresh(integrity)
    return _Selection("alpaca", manifest, _pit_exclusions(manifest, integrity, store=history_store.PIT),
                      history_store.PIT, until, integrity)
```

- `_require_fresh(integrity)`: `actual = hashlib.sha256(history_store.manifest_path("daily", store=PIT).read_bytes()).hexdigest()`; when `integrity.manifest_sha256("daily") != actual` raise `StaleIntegrityError` with both short hashes and the text `"the PIT store's daily manifest changed after its integrity report was frozen -- re-run scripts/data/check_history_store.py --pit (never --mode update between the freeze and a run)"`.
- `_pit_exclusions(manifest, integrity, *, store)`: per manifest ticker, in this order — status not in `PIT_ADMITTED` → the status; `integrity.exclusion(ticker)` not `None` → `f"integrity: {reason}"`; daily file absent (`history_store.file_path(ticker, "daily", store=store)`) → `NO_FILE`. `_manifest_exclusions` is **not edited**.
- `_cut(frame, until) -> pd.DataFrame | None`: `None` in → `None`; `until is None` → the frame itself; else `frame[frame.index < pd.Timestamp(until) + pd.Timedelta(days=1)]`, `None` when empty. One helper for daily and intraday.
- `_load_alpaca(sel, ticker)`: reads `history_store.load(ticker, "daily", store=sel.store)`; a `None` frame records `_missing_reason(sel, ticker)` (`NO_FILE` when the file is absent; `TRIMMED_EMPTY` when the PIT trim window is not `(None, None)`; else `EMPTY_FILE`); otherwise `cut = _cut(frame, sel.until)` and a `None` cut records `NO_BARS_BY_UNTIL`. On the watchlist store `until` is `None`, so the returned frame is the loaded object unchanged.
- `load_intraday`, `active_store`, `selection_args`, `signal_cuts` as in Interfaces (`signal_cuts` iterates `sel.manifest["tickers"]` in sorted order, skipping `sel.excluded`).
- `provenance()`: the alpaca dict gains `"store": sel.store`, `store_dir` becomes `str(history_store.store_root(sel.store))`, and on the PIT store `"integrity_sha256": sel.integrity.sha256` — built in a `_alpaca_provenance(sel)` helper so `provenance` stays flat.

- [ ] **Step 5: Hand workers the whole selection**

- `cache_dir_source.pool_kwargs`: `"initargs": training_data.selection_args()`; docstring adds "the PIT store and its cut travel too (v190)".
- The three `ProcessPoolExecutor(...)` calls: `initargs=(training_data.active(),)` → `initargs=training_data.selection_args()`. No other line in those scripts changes.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/ tests/backtest_scripts/test_run_backtest_range_instrument.py
```

Expected: `0 failed`, `0 xfailed` — including the untouched pins `test_cache_dir_scripts.py::test_pool_kwargs_carry_the_selection` (`("alpaca",)`) and `test_script_data_source.py` (`("yfinance",)`).

- [ ] **Step 7: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0 (`select` and `_load_alpaca` stay below 15 because the store logic lives in the helpers above).

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add swingbot/core/marketdata/training_data.py scripts/backtest/cache_dir_source.py scripts/backtest/measure_arms.py scripts/backtest/measure_acceptance_exits.py scripts/backtest/measure_fvg_bullish_diagnostic.py tests/history_store/test_training_data.py tests/history_store/test_training_data_pit.py && git commit -m "feat(training-data): select the PIT store with its own admission, research_end cut and worker hand-off (v190)"
```

### Task V190-5: Signal-span subtraction in `pit_membership`

**Model:** sonnet — a pure interval function and one optional parameter in one module; `cuts=None` must stay byte-identical.

**Files:**
- Modify: `swingbot/core/marketdata/pit_membership.py` (`membership_map` `:97-105`; new `subtract_spans` beside it)
- Create: `tests/history_store/test_pit_membership_cuts.py`

**Interfaces:**
- Consumes: the worktree from V190-1. No contract dependency on V190-2..V190-4 (the cuts arrive as a plain dict; V190-7 passes `training_data.signal_cuts()`).
- Produces (used by V190-7):
  - `subtract_spans(spans: list[tuple[str, str]], cuts: list[tuple[str, str]]) -> list[tuple[str, str]]` — half-open ISO intervals `[start, end)` on both sides; returns the parts of `spans` outside every cut, sorted, with no empty interval; neither input is mutated; overlapping or unsorted cuts are fine
  - `membership_map(universe: str | None, symbols, cuts: dict[str, list[tuple[str, str]]] | None = None) -> dict | None` — `cuts=None` (and `{}`) is exactly today's result; otherwise each symbol's spans are `subtract_spans(intervals.get(sym, []), cuts.get(sym, []))`; a non-`_pit` universe still returns `None` whatever `cuts` holds

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_pit_membership_cuts.py`:

```python
"""v190 section 3: signal-date cuts (missing-session runs, trailing-coverage
failures) are subtracted from the membership spans the signal mask applies.
With no cuts, membership_map is byte-identical to before."""
import pytest

from swingbot import config
from swingbot.core.marketdata import pit_membership as pm

MEMBERSHIP = ("ticker,start_date,end_date\n"
              "AAA,2015-01-02,\n"
              "BBB,2016-03-01,2018-06-08\n"
              "BBB,2020-01-02,2022-01-03\n"
              "BRK.B,2010-01-04,\n")


@pytest.fixture
def universe_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "universe").mkdir(parents=True)
    (data / "universe" / "sp500_membership.csv").write_text(MEMBERSHIP, encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    return data


# --- subtract_spans -------------------------------------------------------------------

@pytest.mark.parametrize("spans, cuts, expected", [
    # no cuts: the spans as they are
    ([("2016-01-04", "2018-01-02")], [], [("2016-01-04", "2018-01-02")]),
    # a cut inside a span splits it; the cut's end is the first admitted day again
    ([("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")],
     [("2016-01-04", "2017-03-01"), ("2017-03-20", "2018-01-02")]),
    # a cut over the span's start / end trims it
    ([("2016-01-04", "2018-01-02")], [("2015-06-01", "2016-02-01")],
     [("2016-02-01", "2018-01-02")]),
    ([("2016-01-04", "2018-01-02")], [("2017-12-01", "2019-01-01")],
     [("2016-01-04", "2017-12-01")]),
    # a cut covering the whole span removes it (a zero-coverage span)
    ([("2016-01-04", "2018-01-02")], [("2016-01-04", "2018-01-02")], []),
    ([("2016-01-04", "2018-01-02")], [("2010-01-01", "9999-12-31")], []),
    # cuts touching a span's edge only (half-open) remove nothing
    ([("2016-01-04", "2018-01-02")], [("2018-01-02", "2018-03-01"), ("2015-01-01", "2016-01-04")],
     [("2016-01-04", "2018-01-02")]),
    # unsorted, overlapping cuts across two spans
    ([("2016-03-01", "2018-06-08"), ("2020-01-02", "2022-01-03")],
     [("2021-01-04", "2021-02-01"), ("2016-05-02", "2016-06-01"), ("2016-05-20", "2016-07-01")],
     [("2016-03-01", "2016-05-02"), ("2016-07-01", "2018-06-08"),
      ("2020-01-02", "2021-01-04"), ("2021-02-01", "2022-01-03")]),
    # an open-ended membership
    ([("2015-01-02", pm.OPEN_END)], [("2017-03-01", "2017-03-20")],
     [("2015-01-02", "2017-03-01"), ("2017-03-20", pm.OPEN_END)]),
    # no spans at all (a symbol with no membership row)
    ([], [("2017-03-01", "2017-03-20")], []),
])
def test_subtract_spans(spans, cuts, expected):
    assert pm.subtract_spans(spans, cuts) == expected


def test_subtract_spans_mutates_nothing():
    spans, cuts = [("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")]
    pm.subtract_spans(spans, cuts)
    assert spans == [("2016-01-04", "2018-01-02")]
    assert cuts == [("2017-03-01", "2017-03-20")]


def test_a_cut_date_is_no_longer_a_member_but_its_end_is():
    spans = pm.subtract_spans([("2016-01-04", "2018-01-02")], [("2017-03-01", "2017-03-20")])
    assert pm.is_member("2017-02-28", spans)
    assert not pm.is_member("2017-03-01", spans)
    assert not pm.is_member("2017-03-19", spans)
    assert pm.is_member("2017-03-20", spans)


# --- membership_map(cuts=) --------------------------------------------------------------

def test_no_cuts_is_byte_identical(universe_dir):
    symbols = ["AAA", "BBB", "BRK-B", "SPY"]
    before = pm.membership_map("sp500_pit", symbols)
    assert pm.membership_map("sp500_pit", symbols, None) == before
    assert pm.membership_map("sp500_pit", symbols, cuts={}) == before
    assert before["SPY"] == []


def test_cuts_are_subtracted_per_symbol(universe_dir):
    got = pm.membership_map("sp500_pit", ["AAA", "BBB", "SPY"],
                            cuts={"BBB": [("2017-01-03", "2017-02-01")],
                                  "SPY": [("2017-01-03", "2017-02-01")],
                                  "ZZZ": [("2017-01-03", "2017-02-01")]})
    assert got["AAA"] == [("2015-01-02", pm.OPEN_END)]
    assert got["BBB"] == [("2016-03-01", "2017-01-03"), ("2017-02-01", "2018-06-08"),
                          ("2020-01-02", "2022-01-03")]
    assert got["SPY"] == []
    assert set(got) == {"AAA", "BBB", "SPY"}


def test_a_non_pit_universe_ignores_cuts(universe_dir):
    assert pm.membership_map("sp500", ["AAA"], cuts={"AAA": [("2017-01-03", "2017-02-01")]}) is None
    assert pm.membership_map(None, ["AAA"], cuts={"AAA": [("2017-01-03", "2017-02-01")]}) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_pit_membership_cuts.py
```

Expected: FAIL — `AttributeError: module ... has no attribute 'subtract_spans'`.

- [ ] **Step 3: Implement in `pit_membership.py`**

`subtract_spans` walks the cuts in sorted order and, for each, replaces every span it overlaps (`cut_start < end and cut_end > start`) with the left remainder `(start, cut_start)` when `start < cut_start` and the right remainder `(cut_end, end)` when `cut_end < end`; spans the cut does not overlap pass through; return `sorted(...)` of the result. Plain ISO-string comparisons (the module's convention: intervals compare lexicographically and pickle cheaply). If the nested loop pushes it toward the complexity limit, split the one-span step into `_minus(span, cut) -> list[tuple[str, str]]`.

`membership_map(universe, symbols, cuts=None)`: unchanged up to `intervals = load_intervals(path)`; then `if not cuts: return {sym: intervals.get(sym, []) for sym in symbols}` (today's line) else the subtracted comprehension. Docstring adds: `cuts` is `training_data.signal_cuts()` under instrument v3 (spec section 3); every cut is decided from bars on or before its dates, so subtracting it is causal.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_pit_membership_cuts.py tests/marketdata/test_pit_membership.py tests/backtesting/instrument/test_universe_gate.py
```

Expected: `0 failed`, `0 xfailed` (the two existing membership test files untouched and green).

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add swingbot/core/marketdata/pit_membership.py tests/history_store/test_pit_membership_cuts.py && git commit -m "feat(pit-membership): subtract signal-date cuts from membership spans (v190)"
```

# Phase 4 — The instrument picks the store

### Task V190-6: The instrument selects the store; context refusal

**Model:** opus — the one call every backtest script makes before reading a bar; it crosses `instrument` and `marketdata`, and a slip either moves a v1/v2 run onto the PIT store or lets a v3 run go without context.

**Files:**
- Modify: `scripts/data/fetch_backtest_data.py` (`add_data_source_arg` help `:85-88`, `apply_data_source` `:91-95`; new helpers beside them)
- Create: `tests/history_store/test_apply_data_source_instrument.py`

**Interfaces:**
- Consumes: `contract.resolve`, `InstrumentSpec.store`, `.research_end`, `.version` (V190-1); `training_data.select(name, store, until)`, `excluded()`, `load_daily`, `selection_args` (V190-4).
- Produces (used by V190-7, V190-9, V190-22):
  - `instrument_store_spec(args) -> InstrumentSpec | None` — `contract.resolve(args.instrument)` when `args` has a truthy `instrument` **and** the spec's `store` is set; `None` otherwise (no attribute, `None`, `v1`, `v2`)
  - `require_context_frames() -> None` — loads `config.MARKET_REGIME_TICKER` and every `universe.sector_map("etfs")` symbol through `training_data.load_daily` (so each is trimmed and cut at `until`); `SystemExit` naming every missing symbol, each with its exclusion reason when `training_data.excluded()` has one
  - `apply_data_source(args) -> str` — same signature; no store spec → today's body byte for byte (`training_data.select(getattr(args, "data_source", None))` and the same print); a store spec → `--data-source` other than `None`/`alpaca` is a `SystemExit`, then `training_data.select("alpaca", spec.store, spec.research_end)`, then `require_context_frames()`, then prints `training data: alpaca, PIT store cut at <research_end> (<n> excluded)`
  - `MissingStoreError` / `StaleIntegrityError` propagate unchanged, so `run_backtest_range._resolve_data_source` and `tune_strategy._select_source` turn them into `SystemExit` as today

- [ ] **Step 1: Write the failing tests**

Create `tests/history_store/test_apply_data_source_instrument.py`:

```python
"""v190 section 3 / 4: the instrument, not a universe name or an environment
variable, picks the store. v1, v2 and scripts without --instrument select
exactly as before; v3 selects the PIT store cut at research_end and refuses
to run without its context frames (regime ticker, etfs.json)."""
from __future__ import annotations

import argparse
import hashlib
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.marketdata import history_store, pit_integrity, training_data, universe

import fetch_backtest_data as fbd

ETFS = {"SPY": "Broad Market", "XLK": "Information Technology"}


def _bars(start, end):
    idx = pd.date_range(start, end, freq="B")
    n = len(idx)
    return pd.DataFrame({"Open": [10.0] * n, "High": [11.0] * n, "Low": [9.0] * n,
                         "Close": [10.0] * n, "Volume": [1000.0] * n}, index=idx)


def _store(root, files, statuses=None):
    """A daily store: CSVs plus a manifest; returns the manifest bytes."""
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for ticker in files:
        _bars("2016-01-04", "2026-03-31").to_csv(folder / f"{ticker}.csv", index_label="Date")
    statuses = statuses or {t: "ok" for t in files}
    path = folder / "_manifest.json"
    path.write_text(json.dumps({"timeframe": "daily", "feed": "sip", "adjustment": "all",
                                "hash": "h", "tickers": {t: {"status": s}
                                                         for t, s in statuses.items()}}))
    return path.read_bytes()


def _report(root, manifest_bytes, tickers):
    (root / pit_integrity.INTEGRITY_NAME).write_text(json.dumps({
        "schema": 1, "generated_at": "2026-10-25T10:00:00Z", "store_start": "2016-01-04",
        "store_end": "2025-12-31", "thresholds": {}, "detector_sha": {},
        "manifest_sha256": {"daily": hashlib.sha256(manifest_bytes).hexdigest()},
        "no_bars": [],
        "tickers": {t: {"admitted": ok, "reason": None if ok else "unresolved break 2019-05-02",
                        "signal_cuts": [], "trim": None} for t, ok in tickers.items()}}))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(universe, "sector_map", lambda name: dict(ETFS) if name == "etfs" else {})
    watch = tmp_path / "market_data"
    monkeypatch.setenv("HISTORY_STORE_DIR", str(watch))
    _store(watch, ("AAPL", "SPY"))
    training_data.reset()
    yield
    training_data.reset()


@pytest.fixture
def pit(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY", "XLK")), {"AAA": True, "SPY": True, "XLK": True})
    return root


def _args(**over):
    base = {"data_source": None, "instrument": "v1"}
    base.update(over)
    return argparse.Namespace(**base)


# --- v1, v2 and scripts without --instrument: unchanged ---------------------------------

@pytest.mark.parametrize("args", [argparse.Namespace(data_source=None), _args(),
                                  _args(instrument="v2"), _args(instrument=None)])
def test_without_a_store_instrument_the_selection_is_todays(pit, capsys, args):
    assert fbd.instrument_store_spec(args) is None
    assert fbd.apply_data_source(args) == "alpaca"
    assert capsys.readouterr().out.strip() == "training data: alpaca (0 excluded)"
    assert training_data.active_store() == "watchlist"
    assert training_data.available_tickers() == ["AAPL", "SPY"]


def test_v2_with_yfinance_is_todays_yfinance(pit):
    assert fbd.apply_data_source(_args(instrument="v2", data_source="yfinance")) == "yfinance"
    assert training_data.selection_args() == ("yfinance",)


# --- v3 ---------------------------------------------------------------------------------

def test_v3_selects_the_pit_store_cut_at_research_end(pit, capsys):
    assert fbd.instrument_store_spec(_args(instrument="v3")) is resolve("v3")
    assert fbd.apply_data_source(_args(instrument="v3")) == "alpaca"
    assert training_data.selection_args() == ("alpaca", "pit", "2025-12-31")
    assert training_data.available_tickers() == ["AAA", "SPY", "XLK"]
    out = capsys.readouterr().out
    assert "training data: alpaca, PIT store cut at 2025-12-31 (0 excluded)" in out


def test_v3_context_frames_stop_at_research_end(pit):
    """SPY and the sector ETFs load through training_data, so the same cut
    holds for the as-of build and the regime gate (spec section 4)."""
    fbd.apply_data_source(_args(instrument="v3"))
    for symbol in ("SPY", "XLK"):
        assert fbd.load_cached(symbol).index.max() == pd.Timestamp("2025-12-31"), symbol


@pytest.mark.parametrize("source", [None, "alpaca"])
def test_v3_accepts_alpaca_or_no_data_source(pit, source):
    assert fbd.apply_data_source(_args(instrument="v3", data_source=source)) == "alpaca"


def test_v3_refuses_yfinance(pit):
    with pytest.raises(SystemExit, match="--data-source yfinance"):
        fbd.apply_data_source(_args(instrument="v3", data_source="yfinance"))


def test_v3_refuses_a_missing_context_frame_naming_it(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY")), {"AAA": True, "SPY": True})
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    message = str(exc.value)
    assert "XLK" in message and "SPY" not in message.split(":", 1)[1]


def test_v3_refuses_a_context_frame_the_integrity_report_excluded(tmp_path):
    root = tmp_path / "data" / "market_data_pit"
    _report(root, _store(root, ("AAA", "SPY", "XLK")), {"AAA": True, "SPY": False, "XLK": True})
    with pytest.raises(SystemExit) as exc:
        fbd.apply_data_source(_args(instrument="v3"))
    assert "SPY (integrity: unresolved break 2019-05-02)" in str(exc.value)


def test_v3_without_a_pit_store_raises_the_store_error(tmp_path):
    """Callers already turn MissingStoreError into SystemExit; it is not swallowed here."""
    with pytest.raises(history_store.MissingStoreError, match="market_data_pit"):
        fbd.apply_data_source(_args(instrument="v3"))


def test_a_universe_name_never_selects_the_pit_store(pit):
    args = _args(instrument="v2")
    args.universe = "sp500_pit"
    fbd.apply_data_source(args)
    assert training_data.active_store() == "watchlist"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/test_apply_data_source_instrument.py
```

Expected: FAIL — `AttributeError: module 'fetch_backtest_data' has no attribute 'instrument_store_spec'`.

- [ ] **Step 3: Implement in `fetch_backtest_data.py`**

- Import `from swingbot.core.backtesting.instrument import contract` and `from swingbot import config` beside the existing `training_data` import (check `config` is not already imported).
- `instrument_store_spec(args)` and `require_context_frames()` as in Interfaces. `require_context_frames` imports `sector_map` locally (`from swingbot.core.marketdata.universe import sector_map`, the pattern `run_backtest_range._build_asof_map` uses) and dedupes `[config.MARKET_REGIME_TICKER, *sector_map("etfs")]` with `dict.fromkeys`. Its message:

```python
raise SystemExit(
    "error: --instrument v3 needs every context frame in the PIT store, missing: "
    + ", ".join(_described(symbol) for symbol in missing)
    + " -- run the context pass (scripts/data/fetch_alpaca_history.py --root "
      "data/market_data_pit --tickers ...) and rebuild the integrity report")
```

where `_described(symbol)` is `f"{symbol} ({reason})"` when `training_data.excluded()` holds a reason for it, else the bare symbol.
- `apply_data_source(args)`:

```python
def apply_data_source(args: argparse.Namespace) -> str:
    """Select the run's training source and say which one, before any bar is read.
    An instrument with a store (v3) selects it here -- one call, every script
    (spec section 3); no universe name and no environment variable does."""
    spec = instrument_store_spec(args)
    if spec is not None:
        return _select_instrument_store(args, spec)
    source = training_data.select(getattr(args, "data_source", None))
    print(f"training data: {source} ({len(training_data.excluded())} excluded)")
    return source
```

  `_select_instrument_store(args, spec)` refuses `--data-source` values other than `None`/`"alpaca"` with `SystemExit(f"error: --instrument {spec.version} reads the {spec.store} Alpaca store; --data-source {args.data_source} cannot be combined with it")`, calls `training_data.select("alpaca", spec.store, spec.research_end)`, then `require_context_frames()`, then prints the PIT line from Interfaces and returns `"alpaca"`.
- `add_data_source_arg` help text appends `"; --instrument v3 always reads the PIT store (data/market_data_pit/)"`.
- No date literal enters `scripts/backtest/` (the cut date comes from `spec.research_end`).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/history_store/ tests/backtest_scripts/test_run_backtest_range_instrument.py tests/backtest_scripts/test_tune_strategy_instrument.py tests/backtesting/instrument/test_date_literal_guard.py
```

Expected: `0 failed`, `0 xfailed` — `test_training_data.py::test_apply_data_source_selects_and_prints` (the no-instrument path) and both `*_instrument.py` v1/v2 files unchanged.

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add scripts/data/fetch_backtest_data.py tests/history_store/test_apply_data_source_instrument.py && git commit -m "feat(backtest-data): instrument v3 selects the PIT store, cut at research_end, refusing missing context frames (v190)"
```

