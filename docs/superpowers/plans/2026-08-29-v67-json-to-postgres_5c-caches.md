# v67 — Part 5: Caches and verification (tasks P5-08…P5-14)

> Continuation of `2026-08-29-v67-json-to-postgres_5b-snapshots.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_5a`/`_5b` files before starting any task here** — the
> Parallelisation map, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P5-08: The ticker metadata cache

`data.py:153-186` holds two dicts (`currency_symbols`, `company_names`) in one
file, rewritten whole on every new lookup, and **loaded at import time**
(`data.py:186`). It is regenerable from Yahoo, so reads may fall back — this is
the second of the spec's two named read-fallback stores.

**Files:**
- Create: `swingbot/core/db/repositories/meta_cache.py`
- Modify: `swingbot/core/marketdata/data.py` (`_load_ticker_meta_cache` `:161`,
  `_save_ticker_meta_cache` `:174`, and the import-time call at `:186`)
- Test: `tests/marketdata/test_ticker_meta_cache_db.py`

**Interfaces:**
- Consumes: `ticker_meta_cache` (P5-01), `stages`.
- Produces: `MetaCacheRepository` with `load_all() -> tuple[dict, dict]`,
  `put(symbol, currency=None, name=None)`; `meta_cache_repo()`.

**The import-time call is the hazard here**, and it is a real one: `data.py`
calls `_load_ticker_meta_cache()` at module scope, so at the db stage importing
`data.py` would open a database connection during import — in every process,
including `scripts/` that never touch a ticker. The fix is to make the load
**lazy**, triggered by the first lookup rather than by the import.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_ticker_meta_cache_db.py`:

```python
"""The metadata cache, and the import-time load that must become lazy."""
import os

import pytest

from swingbot import config
from swingbot.core.marketdata import data as mkt


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "meta_cache:db")
    monkeypatch.setattr(mkt, "_TICKER_META_CACHE_PATH",
                        os.path.join(tmp_path, "ticker_meta_cache.json"))
    monkeypatch.setattr(mkt, "_currency_cache", {})
    monkeypatch.setattr(mkt, "_company_name_cache", {})
    monkeypatch.setattr(mkt, "_meta_cache_loaded", False)


def test_save_then_load(db_stage):
    mkt._currency_cache["AAPL"] = "$"
    mkt._company_name_cache["AAPL"] = "Apple Inc."
    mkt._save_ticker_meta_cache()

    mkt._currency_cache.clear()
    mkt._company_name_cache.clear()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()

    assert mkt._currency_cache["AAPL"] == "$"
    assert mkt._company_name_cache["AAPL"] == "Apple Inc."


def test_a_symbol_with_only_one_half_round_trips(db_stage):
    mkt._currency_cache["MSFT"] = "$"
    mkt._save_ticker_meta_cache()
    mkt._currency_cache.clear()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()
    assert mkt._currency_cache["MSFT"] == "$"
    assert "MSFT" not in mkt._company_name_cache


def test_saving_twice_keeps_one_row_per_symbol(db_stage):
    from swingbot.core.db.repositories.meta_cache import MetaCacheRepository
    mkt._currency_cache["AAPL"] = "$"
    mkt._save_ticker_meta_cache()
    mkt._company_name_cache["AAPL"] = "Apple Inc."
    mkt._save_ticker_meta_cache()
    assert MetaCacheRepository().count() == 1


def test_an_unreachable_database_degrades_to_an_empty_cache(db_stage,
                                                             monkeypatch):
    """Regenerable from Yahoo: an empty cache costs a network call, not
    correctness."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    mkt._meta_cache_loaded = False
    mkt._load_ticker_meta_cache()            # must not raise
    assert mkt._currency_cache == {}
    dbengine.reset_engine()


def test_importing_data_py_opens_no_connection(monkeypatch):
    """The import-time load must be lazy. Every script that imports data.py
    would otherwise connect to Postgres just to be imported."""
    import importlib
    import sys

    monkeypatch.setattr(config, "DB_STORES", "meta_cache:db")
    opened = []
    from swingbot.core.db import engine as dbengine
    monkeypatch.setattr(dbengine, "get_engine",
                        lambda: opened.append(1) or (_ for _ in ()).throw(
                            AssertionError("connected during import")))
    sys.modules.pop("swingbot.core.marketdata.data", None)
    importlib.import_module("swingbot.core.marketdata.data")
    assert opened == []


def test_no_meta_cache_json_at_the_db_stage(db_stage, tmp_path):
    mkt._currency_cache["AAPL"] = "$"
    mkt._save_ticker_meta_cache()
    assert not os.path.exists(os.path.join(tmp_path, "ticker_meta_cache.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/marketdata/test_ticker_meta_cache_db.py -q
```

Expected: `ModuleNotFoundError`, and — after the module exists —
`test_importing_data_py_opens_no_connection` failing on the import-time call.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/meta_cache.py`:

```python
"""Ticker currency symbols and company names.

One row per symbol, not two dicts in one blob: the file was rewritten whole on
every new lookup, and lookups happen one ticker at a time.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ticker_meta_cache


class MetaCacheRepository(Repository):
    def __init__(self):
        super().__init__(ticker_meta_cache, key="symbol")

    def load_all(self, *, conn=None) -> tuple[dict, dict]:
        """(currency_symbols, company_names), each keyed by symbol."""
        currencies, names = {}, {}
        for row in self.list_all(conn=conn):
            symbol = row["symbol"]
            if row.get("currency") is not None:
                currencies[symbol] = row["currency"]
            if row.get("name") is not None:
                names[symbol] = row["name"]
        return currencies, names

    def put(self, symbol: str, *, currency: str | None = None,
            name: str | None = None, conn=None) -> None:
        """Patch, not upsert: the two halves are learned at different times,
        and a currency lookup must not erase a name already cached."""
        changes = {}
        if currency is not None:
            changes["currency"] = currency
        if name is not None:
            changes["name"] = name
        if not changes:
            return
        if self.get(symbol, conn=conn) is None:
            self.insert({"symbol": symbol, **changes}, conn=conn)
        else:
            self.patch(symbol, changes, conn=conn)


_repo: MetaCacheRepository | None = None


def meta_cache_repo() -> MetaCacheRepository:
    global _repo
    if _repo is None:
        _repo = MetaCacheRepository()
    return _repo
```

- [ ] **Step 4: Make the load lazy and branch both functions**

In `swingbot/core/marketdata/data.py`, replace the import-time call at `:186`:

```python
_meta_cache_loaded = False


def _ensure_meta_cache_loaded() -> None:
    """Load the metadata cache on first use, not at import.

    This used to be a bare `_load_ticker_meta_cache()` at module scope. At the
    db stage that would open a Postgres connection just to IMPORT this module
    -- in every process, including the scripts that never look up a ticker.
    """
    global _meta_cache_loaded
    if _meta_cache_loaded:
        return
    _meta_cache_loaded = True
    _load_ticker_meta_cache()
```

Call `_ensure_meta_cache_loaded()` at the top of `get_company_name` and
`get_currency_symbol` (and any other reader of the two dicts — find them with
`grep -n "_currency_cache\|_company_name_cache" swingbot/core/marketdata/data.py`).

`_load_ticker_meta_cache` gains a `reads_db("meta_cache")` branch calling
`meta_cache_repo().load_all()` inside the existing `try/except Exception` —
which already degrades to an empty cache and logs at debug, exactly the
behaviour the fallback needs. `_save_ticker_meta_cache` writes per stage, using
`put()` per symbol on the db side.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/marketdata/test_ticker_meta_cache_db.py
python scripts/dev/testrun.py file tests/marketdata/test_data.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier because making the load lazy changes
`data.py`'s import behaviour, and `data.py` is imported nearly everywhere.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/meta_cache.py \
        swingbot/core/marketdata/data.py \
        tests/marketdata/test_ticker_meta_cache_db.py
git commit -m "feat(v67): move the ticker metadata cache to postgres, load it lazily"
```

---

### Task P5-09: The relative-strength cache

`factors.py:17,41-50` — `{as_of, rels: {symbol: float}}`, refreshed once per
scan over the whole universe and read by `rs_percentile`. It lives under
`data/universe/`, which is the one migrated store not directly in `data/`.

**Files:**
- Create: `swingbot/core/db/repositories/rs_cache.py`
- Modify: `swingbot/core/edge/factors.py` (`refresh_rs_cache` `:41`,
  `load_rs_cache` `:49`)
- Test: `tests/edge/test_rs_cache_db.py`

**Interfaces:**
- Consumes: `rs_cache` (P5-01), `stages`.
- Produces: `RsCacheRepository` with `load() -> dict`, `replace(as_of, rels)`;
  `rs_cache_repo()`.

**The return shape is the contract.** `load_rs_cache()` returns
`{"as_of": ..., "rels": {...}}` and `rs_percentile` reads `rels` out of it. The
table stores one row per symbol, and the repository reassembles that shape — so
no caller changes.

- [ ] **Step 1: Write the failing tests**

Create `tests/edge/test_rs_cache_db.py`:

```python
"""Universe relative strength. Regenerable, so reads may fall back."""
import os

import pytest

from swingbot import config
from swingbot.core.edge import factors


@pytest.fixture(params=["", "rs_cache:dual", "rs_cache:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(factors, "RS_CACHE_PATH",
                        os.path.join(tmp_path, "universe", "rs_cache.json"))
    os.makedirs(os.path.join(tmp_path, "universe"), exist_ok=True)
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def _write(as_of="2026-01-02", rels=None):
    from swingbot.core.db import stages
    rels = rels if rels is not None else {"AAPL": 0.05, "MSFT": -0.02}
    if stages.writes_json("rs_cache"):
        from swingbot.core.infra.jsonio import atomic_write_json
        atomic_write_json(factors.RS_CACHE_PATH, {"as_of": as_of, "rels": rels})
    if stages.writes_db("rs_cache"):
        from swingbot.core.db.repositories.rs_cache import rs_cache_repo
        rs_cache_repo().replace(as_of, rels)


def test_an_empty_store_loads_the_documented_empty_shape(any_stage):
    assert factors.load_rs_cache() == {"as_of": None, "rels": {}}


def test_write_then_load(any_stage):
    _write()
    cache = factors.load_rs_cache()
    assert cache["as_of"] == "2026-01-02"
    assert cache["rels"]["AAPL"] == pytest.approx(0.05)


def test_a_none_rel_survives(any_stage):
    """relative_return returns None when a symbol has too little history, and
    refresh_rs_cache stores that. rs_percentile filters them out itself."""
    _write(rels={"AAPL": 0.05, "NEWCO": None})
    assert factors.load_rs_cache()["rels"]["NEWCO"] is None


def test_a_refresh_replaces_the_previous_universe(any_stage):
    _write(rels={"AAPL": 0.05, "GONE": 0.01})
    _write(as_of="2026-01-03", rels={"AAPL": 0.06})
    cache = factors.load_rs_cache()
    assert set(cache["rels"]) == {"AAPL"}
    assert cache["as_of"] == "2026-01-03"


def test_rs_percentile_still_works_off_the_cache(any_stage):
    import numpy as np
    import pandas as pd
    _write(rels={"A": -0.10, "B": 0.00, "C": 0.10})
    rels = list(factors.load_rs_cache()["rels"].values())
    n = factors.RS_WINDOW + 2
    idx = pd.bdate_range("2026-01-01", periods=n)
    up = pd.DataFrame({"Close": np.linspace(100, 130, n)}, index=idx)
    flat = pd.DataFrame({"Close": np.full(n, 100.0)}, index=idx)
    pct = factors.rs_percentile(up, flat, universe_rels=rels)
    assert 0.0 <= pct <= 100.0


def test_an_unreachable_database_degrades_to_the_empty_shape(any_stage,
                                                              monkeypatch):
    if any_stage != "rs_cache:db":
        pytest.skip("the fallback is a db-stage property")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    assert factors.load_rs_cache() == {"as_of": None, "rels": {}}
    dbengine.reset_engine()


def test_no_rs_cache_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "rs_cache:db":
        pytest.skip("file absence is only asserted at the db stage")
    _write()
    assert not os.path.exists(os.path.join(tmp_path, "universe", "rs_cache.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/edge/test_rs_cache_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository and branch**

Create `swingbot/core/db/repositories/rs_cache.py`:

```python
"""Universe relative strength, one row per symbol.

load() reassembles the {"as_of": ..., "rels": {...}} shape load_rs_cache() has
always returned, so rs_percentile and every other caller are untouched.
"""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import rs_cache


class RsCacheRepository(Repository):
    def __init__(self):
        super().__init__(rs_cache, key="symbol")

    def load(self, *, conn=None) -> dict:
        rows = self.list_all(conn=conn)
        if not rows:
            return {"as_of": None, "rels": {}}
        # `rel` is promoted, so merge_doc omits it when NULL -- which is the
        # None that relative_return returns for a symbol with too little
        # history. Re-materialise it explicitly; rs_percentile filters Nones.
        rels = {r["symbol"]: (float(r["rel"]) if r.get("rel") is not None else None)
                for r in rows}
        return {"as_of": rows[0].get("as_of"), "rels": rels}

    def replace(self, as_of: str, rels: dict, *, conn=None) -> None:
        """One transaction. A refresh drops symbols that left the universe, and
        a concurrent rs_percentile must never see a half-empty universe."""
        with transaction(conn) as c:
            c.execute(sa.delete(rs_cache))
            for symbol, rel in rels.items():
                self.insert({"symbol": symbol, "as_of": as_of, "rel": rel},
                            conn=c)


_repo: RsCacheRepository | None = None


def rs_cache_repo() -> RsCacheRepository:
    global _repo
    if _repo is None:
        _repo = RsCacheRepository()
    return _repo
```

Branch the two functions in `factors.py`:

```python
def refresh_rs_cache(universe_dfs: dict, spy_df: pd.DataFrame) -> dict:
    from swingbot.core.db import stages
    cache = {"as_of": dt.date.today().isoformat(),
             "rels": {sym: relative_return(df, spy_df)
                      for sym, df in universe_dfs.items()}}
    if stages.writes_json("rs_cache"):
        atomic_write_json(RS_CACHE_PATH, cache)
    if stages.writes_db("rs_cache"):
        from swingbot.core.db.repositories.rs_cache import rs_cache_repo
        rs_cache_repo().replace(cache["as_of"], cache["rels"])
    return cache


def load_rs_cache() -> dict:
    """Regenerable: one of the two stores whose read may fall back (the other
    is the ticker directory). An empty cache costs one scan's RS percentiles
    defaulting to 50.0, which the function already handles."""
    from swingbot.core.db import stages
    if stages.reads_db("rs_cache"):
        try:
            from swingbot.core.db.repositories.rs_cache import rs_cache_repo
            return rs_cache_repo().load()
        except Exception:
            log.warning("rs_cache unreadable from the database; "
                        "percentiles will default until the next refresh",
                        exc_info=True)
            return {"as_of": None, "rels": {}}
    return read_json(RS_CACHE_PATH, {"as_of": None, "rels": {}})
```

`factors.py` has no module logger today — add
`log = logging.getLogger("swing-bot.factors")` beside the imports.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/edge/test_rs_cache_db.py
python scripts/dev/testrun.py file tests/edge/test_factors.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/rs_cache.py swingbot/core/edge/factors.py \
        tests/edge/test_rs_cache_db.py
git commit -m "feat(v67): move the RS cache to postgres"
```

---

### Task P5-10: Fold trades

`analyze.py:141` reads `data/fold_trades/<strategy>.json` for E39's fold
outcomes. The code comment says plainly that **no producer exists yet** — the
read is a documented no-op until E39 lands.

**Files:**
- Create: `swingbot/core/db/repositories/fold_trades.py`
- Modify: `swingbot/core/scanning/analyze.py:141`
- Test: `tests/scanning/test_fold_trades_db.py`

**Interfaces:**
- Consumes: `fold_trades` (P5-01), `stages`.
- Produces: `FoldTradesRepository` with `outcomes(strategy) -> list | None`,
  `put(strategy, payload)`; `fold_trades_repo()`.

**This store is an empty table that is a measured answer, not a stub** —
`docs/claude/known-traps.md` names that exact pattern. Do not "fix" the absence
by writing a producer; E39 owns that. The deliverable here is that when E39
lands, it writes rows instead of files.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_fold_trades_db.py`:

```python
"""E39's fold-outcome cache. Deliberately empty until E39 produces it."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.fold_trades import FoldTradesRepository


@pytest.fixture(params=["", "fold_trades:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def test_an_absent_strategy_reads_as_none(any_stage):
    assert FoldTradesRepository().outcomes("RSI") is None


def test_put_then_outcomes(any_stage):
    repo = FoldTradesRepository()
    repo.put("RSI", {"outcomes": [{"r": 1.5}, {"r": -1.0}]})
    assert len(repo.outcomes("RSI")) == 2


def test_strategies_are_independent(any_stage):
    repo = FoldTradesRepository()
    repo.put("RSI", {"outcomes": [{"r": 1.0}]})
    assert repo.outcomes("MACD") is None


def test_put_twice_replaces(any_stage):
    repo = FoldTradesRepository()
    repo.put("RSI", {"outcomes": [{"r": 1.0}]})
    repo.put("RSI", {"outcomes": [{"r": 2.0}, {"r": 3.0}]})
    assert repo.count() == 1
    assert len(repo.outcomes("RSI")) == 2


def test_a_payload_with_no_outcomes_key_reads_as_none(any_stage):
    repo = FoldTradesRepository()
    repo.put("RSI", {"note": "computed, but empty"})
    assert repo.outcomes("RSI") is None


def test_the_analyze_hook_stays_a_documented_no_op(any_stage, tmp_path):
    """The read in analyze.py is a no-op until E39 ships a producer. That is a
    measured answer, not a stub -- see docs/claude/known-traps.md. This test
    exists so nobody 'fixes' the emptiness by inventing a producer."""
    from swingbot.core.scanning import analyze
    assert hasattr(analyze, "_fold_outcomes")
    assert analyze._fold_outcomes("RSI") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scanning/test_fold_trades_db.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository and extract the read**

Create `swingbot/core/db/repositories/fold_trades.py`:

```python
"""E39's per-strategy fold outcomes.

No producer exists in this codebase yet -- the read in analyze.py is a
documented no-op, not a stub. This table is where E39 will write when it lands.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import fold_trades


class FoldTradesRepository(Repository):
    def __init__(self):
        super().__init__(fold_trades, key="strategy")

    def outcomes(self, strategy: str, *, conn=None) -> list | None:
        row = self.get(strategy, conn=conn)
        if row is None:
            return None
        return row.get("outcomes") or None

    def put(self, strategy: str, payload: dict, *, conn=None) -> dict:
        return self.upsert({"strategy": strategy, **payload}, conn=conn)


_repo: FoldTradesRepository | None = None


def fold_trades_repo() -> FoldTradesRepository:
    global _repo
    if _repo is None:
        _repo = FoldTradesRepository()
    return _repo
```

In `analyze.py`, extract the inline read at `:141` into a named function so
there is one seam:

```python
def _fold_outcomes(strategy: str) -> list | None:
    """E39's fold-trade cache. Returns None until E39 ships a producer -- a
    documented no-op, not a fabricated reading."""
    from swingbot.core.db import stages
    if stages.reads_db("fold_trades"):
        try:
            from swingbot.core.db.repositories.fold_trades import fold_trades_repo
            return fold_trades_repo().outcomes(strategy)
        except Exception:
            return None
    fold_path = os.path.join(config.DATA_DIR, "fold_trades", f"{strategy}.json")
    return read_json(fold_path, {}).get("outcomes")
```

and replace the body of the existing `try:` block with
`outcomes = _fold_outcomes(plan.strategy)`, keeping the surrounding
`if outcomes: ctx["outcomes"] = outcomes` and the `except Exception: pass`
exactly as they are.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_fold_trades_db.py
python scripts/dev/testrun.py file tests/scanning/test_analyze.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/fold_trades.py \
        swingbot/core/scanning/analyze.py tests/scanning/test_fold_trades_db.py
git commit -m "feat(v67): move the fold-trade cache seam to postgres"
```

---

### Task P5-11: Part 5 importers

Three of these stores hold history worth keeping; the rest regenerate
themselves within one scan.

**Files:**
- Create: `scripts/db/import_telemetry.py`, `import_shadow.py`,
  `import_retrospective.py`
- Test: `tests/scripts/test_part5_importers.py`

**Interfaces:**
- Consumes: `run_import` (P2-02 — **if Part 2 has not landed, this task creates
  `scripts/db/import_common.py`**).
- Produces: the three scripts, each with `--dry-run`.

**What is deliberately not imported, and why.** `analytics_snapshot` is rebuilt
from closed trades by `refresh_snapshot()`; `scan_snapshots` is rewritten by the
next scan; `ticker_meta_cache` and `rs_cache` regenerate from the network;
`fold_trades` has no producer. Importing any of them would move a stale copy of
something the system reproduces in minutes. That decision is a table in
P5-12's coverage test, not a comment nobody reads.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_part5_importers.py`:

```python
"""Three importers, and an explicit list of what is deliberately not imported."""
import importlib
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

IMPORTED = ["telemetry", "shadow", "retrospective"]

NOT_IMPORTED = {
    "analytics_snapshot": "rebuilt from closed trades by refresh_snapshot()",
    "scan_snapshots": "rewritten by the next scan",
    "ticker_meta_cache": "regenerates from the network on demand",
    "rs_cache": "regenerates on the next universe refresh",
    "fold_trades": "no producer exists yet (E39)",
}


@pytest.mark.parametrize("name", IMPORTED)
def test_the_importer_exists(name):
    assert (REPO / "scripts" / "db" / f"import_{name}.py").exists()
    importlib.import_module(f"scripts.db.import_{name}")


@pytest.mark.parametrize("name", IMPORTED)
def test_dry_run_writes_nothing(name, tmp_path, monkeypatch, db_committed):
    from swingbot import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    mod = importlib.import_module(f"scripts.db.import_{name}")
    if not hasattr(mod, "main"):
        pytest.skip(f"{name} uses run_import's CLI")
    assert mod.main(["--dry-run"]) == 0


def test_every_skipped_store_carries_a_reason():
    assert all(reason.strip() for reason in NOT_IMPORTED.values())


def test_the_two_lists_together_cover_every_part5_store():
    from swingbot.core.db import schema
    part5 = {"scan_telemetry", "shadow_plans", "retrospective_history",
             "analytics_snapshot", "scan_snapshots", "ticker_meta_cache",
             "rs_cache", "fold_trades"}
    assert part5 <= set(schema.METADATA.tables)
    covered = {"scan_telemetry", "shadow_plans", "retrospective_history"} \
        | set(NOT_IMPORTED)
    assert part5 == covered, f"unaccounted stores: {sorted(part5 ^ covered)}"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_part5_importers.py -q
```

Expected: every `test_the_importer_exists` parametrisation fails.

- [ ] **Step 3: Write them**

All three take `run_import`'s shape:

| Script | Source | Key | Loader |
|---|---|---|---|
| `import_telemetry.py` | `scan_telemetry.jsonl` | `at` | one JSON object per line; **skip a torn trailing line** |
| `import_shadow.py` | `shadow_plans.jsonl` **and `shadow_plans.jsonl.1`** | `id` | both files, `.1` first — it is the older half, and importing it second would put the archive after the live log |
| `import_retrospective.py` | `retrospective_history.json` | `day` | a plain list |

`import_shadow.py` needs a note about the rotation slot:

```python
# The file store rotated at 50 MB into a SINGLE slot, so at most one archive
# survives and any earlier one was already destroyed. Import `.1` first, then
# the live file, so what remains is in chronological order. This is the last
# moment that archive is readable -- P5-13 replaces rotation with retention.
```

`import_shadow.py`'s key is the surrogate `id`, which the source lines do not
carry — so it cannot use `compare()`'s keyed comparison. Give it a `main()`
that verifies by **count plus a checksum of the whole set**, and say in a
comment why a per-record key is unavailable here.

- [ ] **Step 4: Run the tests and dry runs**

```bash
python scripts/dev/testrun.py file tests/scripts/test_part5_importers.py
for s in telemetry shadow retrospective; do
  python scripts/db/import_$s.py --dry-run || echo "FAILED: $s"
done
```

Expected: `0 failed`, every dry run exiting 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/import_telemetry.py scripts/db/import_shadow.py \
        scripts/db/import_retrospective.py tests/scripts/test_part5_importers.py
git commit -m "feat(v67): add Part 5 importers"
```

---

### Task P5-12: Part 5 parity and channel coverage

**Files:**
- Modify: `scripts/db/parity_report.py`
- Test: `tests/db/test_part5_coverage.py`

**Interfaces:**
- Consumes: `STORES`, `StoreSpec` (P2-06), `TABLE_CHANNELS` (P3-18).
- Produces: `STORES` entries for the three imported stores.

- [ ] **Step 1: Write the failing test**

Create `tests/db/test_part5_coverage.py`:

```python
"""Parity registration, and the analytics channel Part 3 left unraised."""
import pytest

from scripts.db.parity_report import STORES
from swingbot.core.db import events, notify

REGISTERED = {"telemetry", "shadow", "retrospective"}


def test_every_imported_part5_store_is_registered():
    missing = REGISTERED - set(STORES)
    assert not missing, f"no parity registration for: {sorted(missing)}"


def test_the_analytics_channel_now_has_a_table():
    """After Part 3 this was the one SSE concern nothing could raise."""
    assert "analytics" in set(events.TABLE_CHANNELS.values())


def test_every_notify_channel_has_at_least_one_table():
    unraised = set(notify.CHANNELS) - set(events.TABLE_CHANNELS.values())
    assert not unraised, f"channels nothing raises: {sorted(unraised)}"


@pytest.mark.parametrize("table", ["shadow_plans", "retrospective_history",
                                   "ticker_meta_cache", "rs_cache",
                                   "fold_trades"])
def test_a_store_with_no_live_ui_raises_no_event(table):
    """A NOTIFY per shadow line would be one per scan item. These are absent
    from the map on purpose, and this test is where that purpose is written
    down rather than left as a gap."""
    assert table not in events.TABLE_CHANNELS
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_part5_coverage.py -q
```

Expected: `test_every_imported_part5_store_is_registered` fails, naming all
three.

- [ ] **Step 3: Register them**

Append three `StoreSpec` entries to `scripts/db/parity_report.py`.
`telemetry` and `retrospective` are straightforward (`at` and `day` keys);
`shadow` needs `ignore_fields={"id"}` and a JSONL loader, and its comparison is
count-based for the reason P5-11 records.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_part5_coverage.py
python scripts/dev/testrun.py file tests/scripts/test_parity_report.py
python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
```

Expected: `0 failed` for all three.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/parity_report.py tests/db/test_part5_coverage.py
git commit -m "feat(v67): register Part 5 stores, close the analytics channel gap"
```

---

### Task P5-13: Retention for the append-only tables

`shadow_log`'s 50 MB single rotation slot destroys the previous archive on every
second rotation. Rows need a bound too — but a bound that deletes on a schedule
someone can see, not one that silently overwrites.

**Files:**
- Create: `scripts/db/prune_logs.py`
- Modify: `swingbot/config.py` (two retention fields)
- Test: `tests/scripts/test_prune_logs.py`

**Interfaces:**
- Consumes: `telemetry_repo` (P5-02), `shadow_repo` (P5-03), `jobs_repo`
  (P3-08, optional — skip if Part 3 has not landed).
- Produces:
  - `config.LOG_RETENTION_DAYS` (default `"365"`) and
    `config.SHADOW_RETENTION_DAYS` (default `"180"`)
  - `prune(now=None, dry_run=False) -> dict[str, int]` — rows deleted per table

**Why these defaults.** A year of scan telemetry is ~250 rows (one per scan day)
and answers "was the scanner slower last quarter". Six months of shadow lines
covers the forward-gate windows E40 measures over, with room for a cohort that
took longer to mature than expected. Both are one `.env` edit away from
different, and neither silently discards anything: the prune script prints what
it deleted, and `--dry-run` prints what it would.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_prune_logs.py`:

```python
"""Bounded logs, without a rotation slot that destroys an archive."""
import datetime as dt

import pytest

from swingbot import config
from scripts.db.prune_logs import prune


@pytest.fixture
def db_stage(monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES",
                        "telemetry:db,shadow:db")
    monkeypatch.setattr(config, "LOG_RETENTION_DAYS", 365)
    monkeypatch.setattr(config, "SHADOW_RETENTION_DAYS", 180)


NOW = dt.datetime(2026, 8, 30, tzinfo=dt.timezone.utc)


def _telemetry(days_ago):
    from swingbot.core.db.repositories.telemetry import telemetry_repo
    telemetry_repo().append({
        "at": (NOW - dt.timedelta(days=days_ago)).isoformat(),
        "duration_s": 10.0})


def _shadow(days_ago):
    from swingbot.core.db.repositories.shadow import shadow_repo
    shadow_repo().append({
        "ts_scan": (NOW - dt.timedelta(days=days_ago)).isoformat(),
        "ticker": "AAPL", "horizon": "2w"})


def test_nothing_is_deleted_when_everything_is_fresh(db_stage):
    _telemetry(10)
    _shadow(10)
    assert prune(now=NOW) == {"scan_telemetry": 0, "shadow_plans": 0}


def test_old_telemetry_is_deleted(db_stage):
    _telemetry(400)
    _telemetry(10)
    assert prune(now=NOW)["scan_telemetry"] == 1
    from swingbot.core.db.repositories.telemetry import telemetry_repo
    assert len(telemetry_repo().recent(100)) == 1


def test_old_shadow_lines_are_deleted(db_stage):
    _shadow(200)
    _shadow(10)
    assert prune(now=NOW)["shadow_plans"] == 1


def test_the_two_retentions_are_independent(db_stage):
    _telemetry(200)      # inside 365
    _shadow(200)         # outside 180
    result = prune(now=NOW)
    assert result["scan_telemetry"] == 0
    assert result["shadow_plans"] == 1


def test_dry_run_reports_without_deleting(db_stage):
    _telemetry(400)
    assert prune(now=NOW, dry_run=True)["scan_telemetry"] == 1
    from swingbot.core.db.repositories.telemetry import telemetry_repo
    assert len(telemetry_repo().recent(100)) == 1


def test_a_retention_of_zero_deletes_nothing(db_stage, monkeypatch):
    """0 means 'keep everything', not 'delete everything'. The opposite
    reading would make a mistyped .env destroy every log the repo has."""
    monkeypatch.setattr(config, "LOG_RETENTION_DAYS", 0)
    _telemetry(4000)
    assert prune(now=NOW)["scan_telemetry"] == 0


def test_the_retention_fields_are_registered():
    keys = {f.key for f in config.FIELDS}
    assert "LOG_RETENTION_DAYS" in keys
    assert "SHADOW_RETENTION_DAYS" in keys
```

`test_a_retention_of_zero_deletes_nothing` is the important one. `0` is the
value someone types when they mean "off", and the destructive reading of it is
unrecoverable.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_prune_logs.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.db.prune_logs'`.

- [ ] **Step 3: Add the fields and the script**

Append to `FIELDS` in `swingbot/config.py`, in the Database section P4-02 added
(or a new one if Part 4 has not landed):

```python
    Field("LOG_RETENTION_DAYS", "LOG_RETENTION_DAYS", "Database",
          "Scan-telemetry retention (days)",
          type="number", default="365", min=0, step=1,
          help="How long scan_telemetry rows are kept by scripts/db/prune_logs.py. "
               "0 means keep everything -- NOT delete everything. A year is "
               "~250 rows and answers 'was the scanner slower last quarter'."),
    Field("SHADOW_RETENTION_DAYS", "SHADOW_RETENTION_DAYS", "Database",
          "Shadow-log retention (days)",
          type="number", default="180", min=0, step=1,
          help="How long shadow_plans rows are kept. 0 means keep everything. "
               "Six months covers E40's forward-gate windows with room for a "
               "cohort that matured late."),
```

Create `scripts/db/prune_logs.py`:

```python
#!/usr/bin/env python3
"""Bounded retention for the append-only tables.

Replaces shadow_log's 50 MB single rotation slot, which destroyed the previous
archive on every second rotation. This deletes on a schedule someone can see:
--dry-run prints what would go, and a real run prints what did.

    python scripts/db/prune_logs.py --dry-run
    python scripts/db/prune_logs.py
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from swingbot import config                       # noqa: E402


def _cutoff(now: dt.datetime, days: int) -> str | None:
    """None when retention is 0 -- which means KEEP EVERYTHING.

    The opposite reading would make a mistyped .env destroy every log this
    repo has, and there is no undo for that.
    """
    if not days or days <= 0:
        return None
    return (now - dt.timedelta(days=int(days))).isoformat()


def prune(now: dt.datetime | None = None, dry_run: bool = False) -> dict:
    from swingbot.core.db import stages
    now = now or dt.datetime.now(dt.timezone.utc)
    deleted: dict[str, int] = {}

    if stages.reads_db("telemetry"):
        from swingbot.core.db.repositories.telemetry import telemetry_repo
        cutoff = _cutoff(now, config.LOG_RETENTION_DAYS)
        repo = telemetry_repo()
        if cutoff is None:
            deleted["scan_telemetry"] = 0
        elif dry_run:
            import sqlalchemy as sa
            from swingbot.core.db.schema import scan_telemetry
            deleted["scan_telemetry"] = repo.count(
                where=scan_telemetry.c.at < cutoff)
        else:
            deleted["scan_telemetry"] = repo.prune(cutoff)

    if stages.reads_db("shadow"):
        import sqlalchemy as sa
        from swingbot.core.db.engine import get_engine
        from swingbot.core.db.schema import shadow_plans
        cutoff = _cutoff(now, config.SHADOW_RETENTION_DAYS)
        if cutoff is None:
            deleted["shadow_plans"] = 0
        else:
            with get_engine().begin() as conn:
                where = shadow_plans.c.ts_scan < cutoff
                if dry_run:
                    deleted["shadow_plans"] = int(conn.execute(
                        sa.select(sa.func.count())
                        .select_from(shadow_plans).where(where)).scalar_one())
                else:
                    deleted["shadow_plans"] = conn.execute(
                        sa.delete(shadow_plans).where(where)).rowcount

    return deleted


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    result = prune(dry_run=args.dry_run)
    verb = "would delete" if args.dry_run else "deleted"
    for table in sorted(result):
        print(f"[prune] {table}: {verb} {result[table]} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Remove the `MAX_BYTES` rotation from `shadow_log.append`'s **db branch only** —
the file branch keeps it while any deployment is still at the `json` stage, and
Part 6 deletes the file branch entirely.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_prune_logs.py
python scripts/dev/testrun.py file tests/backtesting/test_shadow_log_db.py
python scripts/db/prune_logs.py --dry-run
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add scripts/db/prune_logs.py swingbot/config.py \
        swingbot/core/backtesting/shadow_log.py tests/scripts/test_prune_logs.py
git commit -m "feat(v67): replace shadow-log rotation with visible retention"
```

---

### Task P5-14: Part 5 verification

**Files:**
- Create: `tests/db/test_part5_exit.py`

**Interfaces:**
- Consumes: everything in Part 5.
- Produces: nothing.

- [ ] **Step 1: Write the exit test**

Create `tests/db/test_part5_exit.py`:

```python
"""Checks that only make sense once every Part 5 task has landed."""
import pathlib

import pytest

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[2]

CACHE_STORES = ["ticker_meta_cache", "rs_cache", "scan_snapshots",
                "analytics_snapshot"]
LOG_STORES = ["scan_telemetry", "shadow_plans", "retrospective_history"]


@pytest.mark.parametrize("store", ["meta_cache", "rs_cache", "scan_snapshots",
                                   "analytics", "fold_trades"])
def test_every_cache_store_degrades_on_an_unreachable_database(
        store, monkeypatch, tmp_path, db_committed):
    """The spec's read-fallback exemption, asserted per store rather than
    trusted. A cache that raises is a cache that can take the bot down."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", f"{store}:db")
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()

    readers = {
        "meta_cache": lambda: __import__(
            "swingbot.core.marketdata.data", fromlist=["x"]
        )._load_ticker_meta_cache(),
        "rs_cache": lambda: __import__(
            "swingbot.core.edge.factors", fromlist=["x"]).load_rs_cache(),
        "scan_snapshots": lambda: __import__(
            "swingbot.core.scanning.snapshots", fromlist=["x"]
        )._load_scan_snapshots(),
        "analytics": lambda: __import__(
            "swingbot.core.analytics.snapshots", fromlist=["x"]).load_snapshot(),
        "fold_trades": lambda: __import__(
            "swingbot.core.scanning.analyze", fromlist=["x"]
        )._fold_outcomes("RSI"),
    }
    readers[store]()          # must not raise
    dbengine.reset_engine()


@pytest.mark.parametrize("table", LOG_STORES)
def test_every_log_store_has_a_table(table):
    from swingbot.core.db import schema
    assert table in schema.METADATA.tables


def test_no_part5_store_writes_a_file_at_the_db_stage(tmp_path, monkeypatch,
                                                      db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", ",".join(
        f"{s}:db" for s in ("telemetry", "shadow", "retrospective",
                            "analytics", "scan_snapshots", "meta_cache",
                            "rs_cache", "fold_trades")))
    from swingbot.core.analytics import snapshots as analytics_snaps
    from swingbot.core.scanning import telemetry
    telemetry.log_scan_telemetry({"duration_s": 1.0})
    analytics_snaps.save_snapshot({"overall": {"n": 0}})
    written = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert written == [], f"files written at the db stage: {written}"


def test_db_stores_is_not_promoted_in_this_checkout():
    from swingbot.core.db import stages
    promoted = stages.parse(config.DB_STORES)
    part5 = {"telemetry", "shadow", "retrospective", "analytics",
             "scan_snapshots", "meta_cache", "rs_cache", "fold_trades"}
    assert not (set(promoted) & part5), (
        "DB_STORES promotes a Part 5 store in this checkout; that is a local "
        "setting, not something to commit")
```

- [ ] **Step 2: Run everything Part 5 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part5_exit.py
python scripts/dev/testrun.py fast
python -m pytest tests/db/ tests/scanning/ tests/analytics/ tests/edge/ \
                 tests/backtesting/ tests/marketdata/ tests/tracking/ -q
```

Expected: `0 failed`, `0 xfailed` on all three. **Not** `full` — that is P6-12.

- [ ] **Step 3: Commit**

```bash
git add tests/db/test_part5_exit.py
git commit -m "test(v67): pin Part 5 exit criteria"
```

---

**Part 5 exit criteria are in `2026-08-29-v67-json-to-postgres_5b-snapshots.md`.**
Confirm all six before treating this part as done.
