# v67 — Part 2: Live trading state (tasks P2-19…P2-22)

> Continuation of `2026-08-29-v67-json-to-postgres_2c-trading-state-account.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P2-19: The signal-state repository

`state.json` is a dict of `key → {trend, pending_value, pending_count}`, rewritten
whole on every `confirm_or_update` — which runs once per ticker × strategy ×
horizon on every scan. It is the highest-frequency write in the repo.

**Files:**
- Create: `swingbot/core/db/repositories/signal_state.py`
- Test: `tests/db/test_signal_state_repository.py`

**Interfaces:**
- Consumes: `signal_state` (P2-01).
- Produces: `SignalStateRepository` with `entry(key) -> dict`,
  `put(key, entry)`, `all_entries() -> dict[str, dict]`; `signal_state_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_signal_state_repository.py`:

```python
"""Signal state: one row per ticker|strategy|horizon."""
import pytest

from swingbot.core.db.repositories.signal_state import SignalStateRepository


@pytest.fixture
def repo():
    return SignalStateRepository()


def test_entry_for_an_unknown_key_is_an_empty_dict(repo, db_conn):
    # StateStore does self._data.setdefault(key, {}), so absent must read as
    # {} rather than None -- every caller indexes into it immediately.
    assert repo.entry("AAPL|RSI|2w", conn=db_conn) == {}


def test_put_then_entry_round_trips(repo, db_conn):
    repo.put("AAPL|RSI|2w", {"trend": "bullish", "pending_value": None,
                             "pending_count": 0}, conn=db_conn)
    assert repo.entry("AAPL|RSI|2w", conn=db_conn)["trend"] == "bullish"


def test_put_replaces_the_whole_entry(repo, db_conn):
    repo.put("K", {"trend": "bullish", "pending_count": 3}, conn=db_conn)
    repo.put("K", {"trend": "bearish"}, conn=db_conn)
    assert repo.entry("K", conn=db_conn) == {"trend": "bearish"}


def test_two_keys_do_not_interfere(repo, db_conn):
    repo.put("A|RSI|2w", {"trend": "bullish"}, conn=db_conn)
    repo.put("B|RSI|2w", {"trend": "bearish"}, conn=db_conn)
    assert repo.entry("A|RSI|2w", conn=db_conn)["trend"] == "bullish"
    assert repo.entry("B|RSI|2w", conn=db_conn)["trend"] == "bearish"


def test_all_entries_is_keyed_by_key(repo, db_conn):
    repo.put("A|RSI|2w", {"trend": "bullish"}, conn=db_conn)
    repo.put("B|RSI|2w", {"trend": "bearish"}, conn=db_conn)
    out = repo.all_entries(conn=db_conn)
    assert set(out) == {"A|RSI|2w", "B|RSI|2w"}
    assert "key" not in out["A|RSI|2w"]


def test_a_none_valued_field_survives(repo, db_conn):
    # pending_value=None is a meaningful state, not an absent field. It lives
    # in doc, where JSONB stores an explicit null -- which is exactly why key
    # is the only promoted column on this table.
    repo.put("K", {"trend": "bullish", "pending_value": None}, conn=db_conn)
    assert repo.entry("K", conn=db_conn)["pending_value"] is None
```

The last test is the one that matters: `merge_doc` drops NULL *promoted* columns
but preserves an explicit JSON `null` inside `doc`. Promoting `pending_value`
would have broken this store silently, and the test is what records why it is
not promoted.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_signal_state_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/signal_state.py`:

```python
"""Per-ticker/strategy/horizon signal debounce state.

Only `key` is promoted. Everything else -- trend, pending_value, pending_count
-- stays in doc, because pending_value=None is a meaningful state and a
promoted NULL column reads back as an ABSENT key (codec.merge_doc), while an
explicit JSON null inside doc round-trips exactly.
"""
from __future__ import annotations

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import signal_state


class SignalStateRepository(Repository):
    def __init__(self):
        super().__init__(signal_state, key="key")

    def entry(self, key: str, *, conn=None) -> dict:
        row = self.get(key, conn=conn)
        if row is None:
            return {}
        return {k: v for k, v in row.items() if k != "key"}

    def put(self, key: str, entry: dict, *, conn=None) -> None:
        self.upsert({"key": key, **entry}, conn=conn)

    def all_entries(self, *, conn=None) -> dict[str, dict]:
        return {row["key"]: {k: v for k, v in row.items() if k != "key"}
                for row in self.list_all(conn=conn)}


_repo: SignalStateRepository | None = None


def signal_state_repo() -> SignalStateRepository:
    global _repo
    if _repo is None:
        _repo = SignalStateRepository()
    return _repo
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_signal_state_repository.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/signal_state.py \
        tests/db/test_signal_state_repository.py
git commit -m "feat(v67): add the signal-state repository"
```

---

### Task P2-20: StateStore uses Postgres

**Files:**
- Modify: `swingbot/core/infra/state.py` (`StateStore`, `:22-79`)
- Create: `scripts/db/import_state.py`
- Modify: `scripts/db/parity_report.py`
- Test: `tests/infra/test_state_db.py`

**Interfaces:**
- Consumes: `signal_state_repo` (P2-19), `stages`.
- Produces: no new public symbols. `confirm_or_update(key, new_value,
  required_confirmations=2) -> bool` keeps its exact contract.

**The behaviour under test is the debounce, not the storage.** This store's
whole job is "fire True exactly once, on the scan where a new value becomes
confirmed". Every test below asserts that sequence rather than the rows.

- [ ] **Step 1: Write the failing tests**

Create `tests/infra/test_state_db.py`:

```python
"""The debounce contract, unchanged across backends."""
import os

import pytest

from swingbot import config
from swingbot.core.infra.state import StateStore


@pytest.fixture(params=["", "state:dual", "state:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    """Every test here runs at all three stages. The debounce contract is
    what must not change, so it is asserted three times rather than once."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    return request.param


def test_first_sighting_does_not_fire(any_stage):
    assert StateStore().confirm_or_update("K", "bullish") is False


def test_second_consecutive_sighting_fires(any_stage):
    s = StateStore()
    assert s.confirm_or_update("K", "bullish") is False
    assert s.confirm_or_update("K", "bullish") is True


def test_it_fires_exactly_once(any_stage):
    s = StateStore()
    s.confirm_or_update("K", "bullish")
    s.confirm_or_update("K", "bullish")
    assert s.confirm_or_update("K", "bullish") is False


def test_a_flip_back_before_confirmation_clears_the_pending(any_stage):
    s = StateStore()
    s.confirm_or_update("K", "bullish")
    s.confirm_or_update("K", "bullish")     # confirmed bullish
    s.confirm_or_update("K", "bearish")     # pending, 1 of 2
    assert s.confirm_or_update("K", "bullish") is False   # back to confirmed
    assert s.confirm_or_update("K", "bearish") is False   # pending restarts


def test_required_confirmations_is_honoured(any_stage):
    s = StateStore()
    for _ in range(2):
        assert s.confirm_or_update("K", "bullish", required_confirmations=3) is False
    assert s.confirm_or_update("K", "bullish", required_confirmations=3) is True


def test_keys_are_independent(any_stage):
    s = StateStore()
    s.confirm_or_update("A", "bullish")
    s.confirm_or_update("A", "bullish")
    assert s.confirm_or_update("B", "bullish") is False


def test_a_second_instance_sees_confirmed_state_at_the_db_stage(any_stage):
    if any_stage != "state:db":
        pytest.skip("cross-instance visibility is the db stage's property")
    StateStore().confirm_or_update("K", "bullish")
    # A fresh StateStore is a fresh process, as far as this store is concerned.
    assert StateStore().confirm_or_update("K", "bullish") is True


def test_no_state_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "state:db":
        pytest.skip("file absence is only asserted at the db stage")
    StateStore().confirm_or_update("K", "bullish")
    assert not os.path.exists(os.path.join(tmp_path, "state.json"))
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/infra/test_state_db.py -q
```

Expected: the `state:db` parametrisations fail —
`test_a_second_instance_sees_confirmed_state_at_the_db_stage` most clearly.

- [ ] **Step 3: Rewrite `confirm_or_update` around a per-key read**

The file version holds `self._data` for the whole store. The database version
reads and writes one key, which is what makes two scan processes safe:

```python
    def _read(self, key: str) -> dict:
        from swingbot.core.db import stages
        if stages.reads_db("state"):
            from swingbot.core.db.repositories.signal_state import signal_state_repo
            return signal_state_repo().entry(key)
        return self._data.setdefault(key, {})

    def _write(self, key: str, entry: dict) -> None:
        from swingbot.core.db import stages
        if stages.writes_json("state"):
            self._data[key] = entry
            self._save()
        if stages.writes_db("state"):
            from swingbot.core.db.repositories.signal_state import signal_state_repo
            signal_state_repo().put(key, entry)
```

`confirm_or_update` keeps its exact decision logic — the four branches are
unchanged — and only swaps where `entry` comes from and where it goes:

```python
    def confirm_or_update(self, key: str, new_value: str,
                          required_confirmations: int = 2) -> bool:
        with _LOCK:
            entry = dict(self._read(key))
            confirmed = entry.get("trend")

            if new_value == confirmed:
                if entry.get("pending_value") is not None:
                    entry["pending_value"] = None
                    entry["pending_count"] = 0
                    self._write(key, entry)
                return False

            if entry.get("pending_value") == new_value:
                entry["pending_count"] = entry.get("pending_count", 0) + 1
            else:
                entry["pending_value"] = new_value
                entry["pending_count"] = 1

            if entry["pending_count"] >= required_confirmations:
                entry["trend"] = new_value
                entry["pending_value"] = None
                entry["pending_count"] = 0
                self._write(key, entry)
                return True

            self._write(key, entry)
            return False
```

Note `entry = dict(self._read(key))` copies. At the json stage `_read` returns
the live dict out of `self._data`, and mutating it in place before `_write`
would make the "flip back clears the pending" branch write a value it had
already applied.

- [ ] **Step 4: Importer and parity**

Create `scripts/db/import_state.py`. `state.json` is a dict keyed by the state
key, so `load_source` flattens it: `[{"key": k, **v} for k, v in
read_json(path, {}).items()]`, `key="key"`, `name="state"`. Register `state` in
`parity_report.py` with the matching `loader`.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/infra/test_state_db.py
python scripts/dev/testrun.py file tests/infra/test_state.py
python scripts/db/import_state.py --dry-run
```

Expected: `0 failed` for both test files, across all three parametrisations.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/infra/state.py scripts/db/import_state.py \
        scripts/db/parity_report.py tests/infra/test_state_db.py
git commit -m "feat(v67): migrate signal state to postgres"
```

---

### Task P2-21: The watchlist repository and module

`watchlist.py`'s five functions all take `path: str = DEFAULT_PATH` — a
module-level default evaluated at import time, which
`admin/api_v1/watchlist.py:38` already documents as a hazard and works around by
passing an explicit path everywhere.

**Files:**
- Create: `swingbot/core/db/repositories/watchlist.py`
- Modify: `swingbot/core/marketdata/watchlist.py` (all five functions)
- Create: `scripts/db/import_watchlist.py`
- Modify: `scripts/db/parity_report.py`
- Test: `tests/marketdata/test_watchlist_db.py`

**Interfaces:**
- Consumes: `watchlist` table (P2-01), `stages`.
- Produces:
  - `WatchlistRepository` with `tickers() -> list[str]`, `add(ticker)`,
    `remove(ticker)`, `replace(tickers)`, `clear()`; `watchlist_repo()`
  - `load_watchlist(path=None)`, `save_watchlist(tickers, path=None)`,
    `add_ticker(ticker, path=None)`, `remove_ticker(ticker, path=None)`,
    `clear_watchlist(path=None)` — **note the default changes from
    `DEFAULT_PATH` to `None`**

**The signature change is the point.** `path=None` means "use the configured
backend"; an explicit path still means that file, exactly as in P2-14. Leaving
`DEFAULT_PATH` as the default would make every caller that omits `path` pin
itself to a file forever, which is the same import-time-capture bug the admin
module already works around.

- [ ] **Step 1: Write the failing tests**

Create `tests/marketdata/test_watchlist_db.py`:

```python
"""Watchlist at each stage, and the explicit-path escape hatch."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.watchlist import WatchlistRepository
from swingbot.core.marketdata import watchlist as wl


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    wl.add_ticker("AAPL")
    assert wl.load_watchlist() == ["AAPL"]
    assert WatchlistRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual")
    wl.add_ticker("AAPL")
    assert os.path.exists(os.path.join(data_dir, "watchlist.json"))
    assert WatchlistRepository().tickers(conn=db_committed) == ["AAPL"]


def test_db_stage_reads_rows(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.add_ticker("MSFT")
    wl.add_ticker("AAPL")
    assert wl.load_watchlist() == ["AAPL", "MSFT"]      # sorted, as today
    assert not os.path.exists(os.path.join(data_dir, "watchlist.json"))


def test_adding_a_duplicate_is_a_no_op(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.add_ticker("AAPL")
    wl.add_ticker("AAPL")
    assert wl.load_watchlist() == ["AAPL"]


def test_remove(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.add_ticker("AAPL")
    wl.add_ticker("MSFT")
    assert wl.remove_ticker("AAPL") == ["MSFT"]


def test_removing_something_absent_is_not_an_error(data_dir, monkeypatch,
                                                   db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    assert wl.remove_ticker("NOPE") == []


def test_save_watchlist_replaces_the_whole_set(data_dir, monkeypatch,
                                               db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.save_watchlist(["AAPL", "MSFT"])
    wl.save_watchlist(["NVDA"])
    assert wl.load_watchlist() == ["NVDA"]


def test_clear(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.add_ticker("AAPL")
    assert wl.clear_watchlist() == []
    assert wl.load_watchlist() == []


def test_an_explicit_path_always_uses_the_file(data_dir, monkeypatch,
                                               db_committed):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    path = os.path.join(data_dir, "other.json")
    wl.save_watchlist(["ONLYFILE"], path=path)
    assert wl.load_watchlist(path=path) == ["ONLYFILE"]
    assert WatchlistRepository().tickers(conn=db_committed) == []
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/marketdata/test_watchlist_db.py -q
```

Expected: `test_dual_stage_writes_both` fails.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/watchlist.py`:

```python
"""The scanned ticker universe."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import watchlist


class WatchlistRepository(Repository):
    def __init__(self):
        super().__init__(watchlist, key="ticker")

    def tickers(self, *, conn=None) -> list[str]:
        # Sorted, matching what load_watchlist() has always returned. Callers
        # render this list directly, so its order is part of the contract.
        return sorted(row["ticker"] for row in self.list_all(conn=conn))

    def add(self, ticker: str, *, conn=None) -> list[str]:
        self.upsert({"ticker": ticker,
                     "added_at": dt.datetime.now(dt.timezone.utc).isoformat()},
                    conn=conn)
        return self.tickers(conn=conn)

    def remove(self, ticker: str, *, conn=None) -> list[str]:
        self.delete(ticker, conn=conn)
        return self.tickers(conn=conn)

    def replace(self, tickers: list[str], *, conn=None) -> list[str]:
        """One transaction: the old set is never visible as gone-and-not-yet-
        replaced to a scan running concurrently."""
        from swingbot.core.db.engine import transaction
        with transaction(conn) as c:
            self.clear(conn=c)
            for ticker in tickers:
                self.add(ticker, conn=c)
            return self.tickers(conn=c)

    def clear(self, *, conn=None) -> list[str]:
        import sqlalchemy as sa
        with self._tx(conn) as c:
            c.execute(sa.delete(watchlist))
        return []


_repo: WatchlistRepository | None = None


def watchlist_repo() -> WatchlistRepository:
    global _repo
    if _repo is None:
        _repo = WatchlistRepository()
    return _repo
```

- [ ] **Step 4: Rewrite the five module functions**

In `swingbot/core/marketdata/watchlist.py`, change every default from
`path: str = DEFAULT_PATH` to `path: str | None = None` and add the branch. Keep
`DEFAULT_PATH` defined — `admin/api_v1/watchlist.py` names it in a docstring and
other modules may import it — but stop using it as a default:

```python
def _resolve(path: str | None) -> tuple[bool, str]:
    """(use_db, file_path). An explicit path always means the file."""
    from swingbot.core.db import stages
    if path is not None:
        return False, path
    return stages.reads_db("watchlist"), os.path.join(config.DATA_DIR,
                                                      "watchlist.json")


def load_watchlist(path: str | None = None) -> list[str]:
    use_db, file_path = _resolve(path)
    if use_db:
        from swingbot.core.db.repositories.watchlist import watchlist_repo
        return watchlist_repo().tickers()
    return sorted(read_json(file_path, []))
```

`save_watchlist` writes both sides per stage (`writes_json` / `writes_db`, with
`replace()` on the db side); `add_ticker`, `remove_ticker` and `clear_watchlist`
follow the same shape and return the resulting list, as they do today.

**Note `DEFAULT_PATH` is still evaluated at import time and still wrong for
tests.** This task does not fix that — it stops the five functions depending on
it, which is the part that matters here. Part 6 deletes the constant.

- [ ] **Step 5: Importer and parity**

Create `scripts/db/import_watchlist.py` with `load_source` mapping the flat list:
`[{"ticker": t, "added_at": <now>} for t in read_json(path, [])]`. `added_at` has
no source in the file — the original never recorded when a ticker was added — so
stamp import time and say so in a comment rather than inventing a date.

Register `watchlist` in `parity_report.py` with the matching loader. Its
comparison will report `added_at` as a mismatch on every row, which is correct
and expected — add a `ignore_fields` parameter to `compare()` and pass
`{"added_at"}` for this store, rather than making the checksum lie.

- [ ] **Step 6: Run the tests**

```bash
python scripts/dev/testrun.py file tests/marketdata/test_watchlist_db.py
python scripts/dev/testrun.py file tests/marketdata/test_watchlist.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_watchlist.py
python scripts/dev/testrun.py file tests/scripts/test_import_common.py
```

Expected: `0 failed` for all four. The third is the regression check on the
admin endpoints that pass explicit paths.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/db/repositories/watchlist.py \
        swingbot/core/marketdata/watchlist.py scripts/db/import_watchlist.py \
        scripts/db/import_common.py scripts/db/parity_report.py \
        tests/marketdata/test_watchlist_db.py
git commit -m "feat(v67): migrate the watchlist to postgres"
```

---

### Task P2-22: Part 2 verification

Not a full-suite run — that is P6-12. This is the fast tier over everything
Part 2 touched, plus the two checks that only make sense once all seven stores
exist.

**Files:**
- Create: `tests/db/test_part2_coverage.py`

**Interfaces:**
- Consumes: everything in Part 2.
- Produces: nothing.

- [ ] **Step 1: Write the coverage test**

Create `tests/db/test_part2_coverage.py`:

```python
"""Two things that can only be checked once all seven stores exist."""
import pathlib

from scripts.db.parity_report import STORES

PART2_STORES = {"trades", "plans", "starred_plans", "account", "journal",
                "state", "watchlist"}
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_every_part2_store_has_a_parity_entry():
    """A store missing here is a store nobody checks before flipping it."""
    missing = PART2_STORES - set(STORES)
    assert not missing, f"no parity registration for: {sorted(missing)}"


def test_every_part2_store_has_an_importer():
    scripts = {p.stem for p in (REPO_ROOT / "scripts" / "db").glob("import_*.py")}
    expected = {f"import_{name}" for name in PART2_STORES}
    # starred_plans' importer is import_starred.py, not import_starred_plans.py
    expected = {n.replace("import_starred_plans", "import_starred") for n in expected}
    assert expected <= scripts, f"missing importers: {sorted(expected - scripts)}"


def test_no_part2_store_defaults_to_a_stage_other_than_json():
    """Merging Part 2 must not change production behaviour. Every store stays
    on json until someone edits DB_STORES on the VM."""
    from swingbot.core.db import stages
    from swingbot import config
    assert stages.parse(config.DB_STORES) == {} or all(
        s not in stages.parse(config.DB_STORES) for s in PART2_STORES
    ), ".env in this checkout has already promoted a store; that is a local "\
       "setting, not something to commit"
```

- [ ] **Step 2: Run everything Part 2 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part2_coverage.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`, `0 xfailed` on both. **Not** `full`.

- [ ] **Step 3: Run the db tier, including slow**

```bash
python -m pytest tests/db/ tests/tracking/ tests/planning/ -q
```

Expected: `0 failed`. This covers the `slow`-marked notification and
two-connection tests the fast tier skips.

- [ ] **Step 4: Commit**

```bash
git add tests/db/test_part2_coverage.py
git commit -m "test(v67): pin Part 2 store coverage"
```

---

## Part 2 exit criteria

1. All seven stores have a repository, an importer, and a `parity_report` entry.
2. `alembic heads` returns exactly one head: `p2_006`.
3. Each store passes its own tests at all three stages.
4. `tests/analytics/test_analytics_backend_parity.py` is green — success
   criterion 3 for these stores.
5. `python scripts/dev/testrun.py fast` is green.
6. **`DB_STORES` is empty in every committed file.** Stage promotion is a
   production `.env` edit, made in Part 6, not something a merge does.
