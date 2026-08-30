# v67 — Part 2: Live trading state (tasks P2-13…P2-18)

> Continuation of `2026-08-29-v67-json-to-postgres_2b-trading-state-plans.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the first file of this part before starting any task here** —
> the Parallelisation map, the Alembic revision-id table and the exit criteria
> live there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---
### Task P2-13: The account repository

`account.json` is a singleton config blob plus an append-only `balance_history`
capped at 5000 entries. The two split: the blob becomes one row, the history
becomes rows.

**Files:**
- Create: `swingbot/core/db/repositories/account.py`
- Test: `tests/db/test_account_repository.py`

**Interfaces:**
- Consumes: `account`, `account_balance_history` (P2-01).
- Produces: `AccountRepository` with `load() -> dict`, `save(cfg: dict)`,
  `append_history(entry: dict)`, `history(limit=None) -> list[dict]`; and
  `account_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_account_repository.py`:

```python
"""Account config as one row; balance history as its own table."""
import pytest

from swingbot.core.db.repositories.account import AccountRepository


@pytest.fixture
def repo():
    return AccountRepository()


def test_load_on_an_empty_table_returns_an_empty_dict(repo, db_conn):
    assert repo.load(conn=db_conn) == {}


def test_save_then_load_round_trips(repo, db_conn):
    cfg = {"balance": 10000.0, "risk_pct": 1.0, "sizing_mode": "fixed_fractional"}
    repo.save(cfg, conn=db_conn)
    assert repo.load(conn=db_conn) == cfg


def test_saving_twice_keeps_one_row(repo, db_conn):
    repo.save({"balance": 1.0}, conn=db_conn)
    repo.save({"balance": 2.0}, conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.load(conn=db_conn)["balance"] == 2.0


def test_save_replaces_rather_than_merges(repo, db_conn):
    # load_account_config() already layers defaults under whatever is stored,
    # so a merge here would resurrect a key the caller deliberately removed.
    repo.save({"balance": 1.0, "gone": True}, conn=db_conn)
    repo.save({"balance": 2.0}, conn=db_conn)
    assert "gone" not in repo.load(conn=db_conn)


def test_balance_history_is_not_stored_on_the_config_row(repo, db_conn):
    repo.save({"balance": 1.0, "balance_history": [{"ts": "x", "balance": 1.0}]},
              conn=db_conn)
    # The array is split out, not persisted twice.
    assert "balance_history" not in repo.load(conn=db_conn)
    assert len(repo.history(conn=db_conn)) == 1


def test_append_history_and_read_it_back(repo, db_conn):
    repo.append_history({"ts": "2026-01-02T00:00:00+00:00", "balance": 100.0,
                         "reason": "settle"}, conn=db_conn)
    rows = repo.history(conn=db_conn)
    assert len(rows) == 1
    assert rows[0]["balance"] == 100.0
    assert rows[0]["reason"] == "settle"


def test_history_is_oldest_first(repo, db_conn):
    repo.append_history({"ts": "2026-01-05T00:00:00+00:00", "balance": 2.0}, conn=db_conn)
    repo.append_history({"ts": "2026-01-02T00:00:00+00:00", "balance": 1.0}, conn=db_conn)
    # equity_curve/drawdown_pct walk this in chronological order.
    assert [r["balance"] for r in repo.history(conn=db_conn)] == [1.0, 2.0]


def test_history_limit_returns_the_most_recent(repo, db_conn):
    for day in range(1, 6):
        repo.append_history({"ts": f"2026-01-0{day}T00:00:00+00:00",
                             "balance": float(day)}, conn=db_conn)
    assert [r["balance"] for r in repo.history(limit=2, conn=db_conn)] == [4.0, 5.0]


def test_history_is_uncapped(repo, db_conn):
    """5000 was a file-size cap, not a domain rule. Rows have no such cost."""
    for i in range(20):
        repo.append_history({"ts": f"2026-01-01T00:00:{i:02d}+00:00",
                             "balance": float(i)}, conn=db_conn)
    assert len(repo.history(conn=db_conn)) == 20
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_account_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/account.py`:

```python
"""Account config (one row) and balance history (its own table).

balance_history was a capped 5000-element array inside account.json, capped
because rewriting a growing array on every settle costs the whole file. Rows
do not have that cost, so the cap is gone: drawdown_pct, growth_path and the
equity chart all read the full series, and truncating it was always a storage
compromise rather than a domain rule.
"""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import account, account_balance_history

CONFIG_KEY = "config"


class AccountRepository(Repository):
    def __init__(self):
        super().__init__(account, key="key")
        self._history = Repository(account_balance_history, key="ts")

    def load(self, *, conn=None) -> dict:
        row = self.get(CONFIG_KEY, conn=conn)
        if row is None:
            return {}
        cfg = {k: v for k, v in row.items() if k != "key"}
        cfg.pop("balance_history", None)
        return cfg

    def save(self, cfg: dict, *, conn=None) -> None:
        """Replace the config row. Splits balance_history out if present.

        Replaces rather than merges: load_account_config() already layers the
        canonical defaults underneath whatever is stored, so merging here would
        resurrect a key the caller deliberately dropped.
        """
        payload = {k: v for k, v in cfg.items() if k != "balance_history"}
        for entry in cfg.get("balance_history") or []:
            self.append_history(entry, conn=conn)
        self.upsert({"key": CONFIG_KEY, **payload}, conn=conn)

    def append_history(self, entry: dict, *, conn=None) -> dict:
        return self._history.upsert(dict(entry), conn=conn)

    def history(self, *, limit: int | None = None, conn=None) -> list[dict]:
        if limit is None:
            return self._history.list_all(
                conn=conn, order_by=account_balance_history.c.ts.asc())
        newest = self._history.list_all(
            conn=conn, order_by=account_balance_history.c.ts.desc(), limit=limit)
        return list(reversed(newest))


_repo: AccountRepository | None = None


def account_repo() -> AccountRepository:
    global _repo
    if _repo is None:
        _repo = AccountRepository()
    return _repo
```

`ts` is the history table's key so a re-run import converges instead of
duplicating. Two settles inside the same microsecond would collide; that has
never happened here (settles are one per closed trade) and a collision would be
a visible unique violation rather than silent duplication, which is the right
failure.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_account_repository.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/repositories/account.py tests/db/test_account_repository.py
git commit -m "feat(v67): add the account repository"
```

---

### Task P2-14: account.py reads and writes Postgres

`account.py` is functions, not a class, and every one takes an optional `path`.
The stage branch goes in the two functions all the others funnel through.

**Files:**
- Modify: `swingbot/core/planning/account.py` (`load_account_config` `:132`,
  `save_account_config` `:192`, `_append_balance_history` `:196`,
  `get_balance_history` `:301`)
- Test: `tests/planning/test_account_db.py`

**Interfaces:**
- Consumes: `account_repo` (P2-13), `stages`.
- Produces: no new public symbols. `load_account_config(path=None)` and
  `save_account_config(cfg, path=None)` keep their signatures; an explicit
  `path` still forces the file backend, which is what keeps every existing test
  isolated.

**The rule that makes this safe:** *an explicit `path` argument always means the
file*. Dozens of tests pass `path=tmp_path/...` precisely to stay off the real
`data/`; if the stage overrode that they would start hitting the database
instead, and the isolation those tests exist for would be gone.

- [ ] **Step 1: Write the failing tests**

Create `tests/planning/test_account_db.py`:

```python
"""Account config at each stage, and the explicit-path escape hatch."""
import os

import pytest

from swingbot import config
from swingbot.core.planning import account as acct


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    acct.set_balance(5000.0)
    assert os.path.exists(os.path.join(data_dir, "account.json"))
    assert acct.load_account_config()["balance"] == 5000.0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "account:dual")
    acct.set_balance(5000.0)
    assert os.path.exists(os.path.join(data_dir, "account.json"))
    from swingbot.core.db.repositories.account import AccountRepository
    assert AccountRepository().load(conn=db_committed)["balance"] == 5000.0


def test_db_stage_writes_no_file(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(5000.0)
    assert not os.path.exists(os.path.join(data_dir, "account.json"))
    assert acct.load_account_config()["balance"] == 5000.0


def test_an_explicit_path_always_uses_the_file(data_dir, monkeypatch, db_committed):
    """Dozens of existing tests pass an explicit path to stay off the real
    data/. The stage must never override that."""
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    path = os.path.join(data_dir, "elsewhere.json")
    acct.set_balance(1234.0, path=path)
    assert os.path.exists(path)
    assert acct.load_account_config(path=path)["balance"] == 1234.0
    # ...and the database was not touched.
    from swingbot.core.db.repositories.account import AccountRepository
    assert AccountRepository().load(conn=db_committed) == {}


def test_defaults_still_layer_under_a_stored_config(data_dir, monkeypatch,
                                                    db_committed):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(5000.0)
    cfg = acct.load_account_config()
    assert cfg["balance"] == 5000.0
    assert "risk_pct" in cfg          # from the canonical defaults


def test_balance_history_accumulates_as_rows(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "account:db")
    acct.set_balance(1000.0)
    acct.apply_realized_pnl(100.0, meta={"reason": "test"})
    points = acct.get_balance_history()
    assert len(points) >= 1
    assert points[-1]["balance"] == pytest.approx(1100.0)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/planning/test_account_db.py -q
```

Expected: `test_dual_stage_writes_both` fails.

- [ ] **Step 3: Branch the two funnels**

In `swingbot/core/planning/account.py`:

```python
def _use_db(path: str | None) -> bool:
    """An explicit path always means the file.

    Dozens of tests pass path=tmp_path/account.json specifically to stay off
    the real data/ directory (see _default_config_path's docstring for how
    that isolation was found the hard way). A stage that overrode an explicit
    path would silently point all of them at the database and take that
    isolation away.
    """
    if path is not None:
        return False
    from swingbot.core.db import stages
    return stages.reads_db("account")
```

`load_account_config` gains, immediately after resolving defaults:

```python
    if _use_db(path):
        stored = account_repo().load()
    else:
        stored = read_json(path or _default_config_path(), {})
```

keeping the existing defaults-layering below it untouched.

`save_account_config` becomes:

```python
def save_account_config(config: dict, path: str = None):
    from swingbot.core.db import stages
    if path is not None or stages.writes_json("account"):
        atomic_write_json(path or _default_config_path(), config)
    if path is None and stages.writes_db("account"):
        from swingbot.core.db.repositories.account import account_repo
        account_repo().save(config)
```

`_append_balance_history` keeps appending to the in-memory `cfg` dict — it is
called before `save_account_config`, and `AccountRepository.save()` splits the
array back out into rows. `get_balance_history(path=None)` gains the same
`_use_db` branch, returning `account_repo().history()` when it applies.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_account_db.py
python scripts/dev/testrun.py file tests/planning/test_account.py
python scripts/dev/testrun.py file tests/tracking/test_one_trade_per_ticker.py
```

Expected: `0 failed` for all three. The third is named specifically: its
docstring records that it was the test that found the `DATA_DIR` isolation
hazard, so it is the one most likely to catch a regression in `_use_db`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/account.py tests/planning/test_account_db.py
git commit -m "feat(v67): read and write account config in postgres"
```

---

### Task P2-15: The account importer, and _sum_realized_pnl

`_sum_realized_pnl` (`account.py:94`) opens `trades.json` directly to avoid a
circular import with `performance.py`. At the db stage that file does not exist,
and the account balance would silently self-heal to zero realized P&L — the
quietest possible data-loss bug in this plan.

**Files:**
- Create: `scripts/db/import_account.py`
- Modify: `swingbot/core/planning/account.py:94` (`_sum_realized_pnl`)
- Modify: `scripts/db/parity_report.py`
- Test: `tests/planning/test_sum_realized_pnl_db.py`

**Interfaces:**
- Consumes: `trades_repo` (P2-01), `stages`, `run_import` (P2-02).
- Produces: no new symbols. `_sum_realized_pnl(trades_path=None)` keeps its
  signature and its explicit-path escape hatch.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_sum_realized_pnl_db.py`:

```python
"""The quietest bug in this plan: realized P&L silently reading zero."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.planning.account import _sum_realized_pnl


def _closed(trade_id, pnl):
    return dict(trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="win",
                opened_at="2026-01-02T15:00:00+00:00",
                closed_at="2026-01-09T15:00:00+00:00",
                realized_pnl_amount=pnl)


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db")


def test_realized_pnl_sums_rows_at_the_db_stage(db_stage):
    TradeRepository().upsert(_closed("T1", 100.0))
    TradeRepository().upsert(_closed("T2", -40.0))
    assert _sum_realized_pnl() == pytest.approx(60.0)


def test_an_open_trade_is_not_counted(db_stage):
    TradeRepository().upsert(_closed("T1", 100.0))
    TradeRepository().upsert(dict(
        trade_id="T2", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="open",
        opened_at="2026-01-02T15:00:00+00:00"))
    assert _sum_realized_pnl() == pytest.approx(100.0)


def test_an_explicit_path_still_reads_that_file(db_stage, tmp_path):
    import os
    from swingbot.core.infra.jsonio import atomic_write_json
    TradeRepository().upsert(_closed("INDB", 999.0))
    path = os.path.join(tmp_path, "other_trades.json")
    atomic_write_json(path, [_closed("INFILE", 5.0)])
    assert _sum_realized_pnl(trades_path=path) == pytest.approx(5.0)


def test_a_missing_realized_amount_is_rederived_from_legs(db_stage):
    TradeRepository().upsert(dict(
        trade_id="T1", ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="win",
        opened_at="2026-01-02T15:00:00+00:00",
        closed_at="2026-01-09T15:00:00+00:00",
        entry=100.0, stop_loss=95.0,
        legs=[{"fraction": 1.0, "exit_price": 110.0, "r": 2.0}]))
    # settle_legs() is the existing fallback; it must still fire on a row.
    assert _sum_realized_pnl() != 0.0
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/planning/test_sum_realized_pnl_db.py -q
```

Expected: `test_realized_pnl_sums_rows_at_the_db_stage` returns `0.0` — the
exact silent failure this task exists to prevent.

- [ ] **Step 3: Branch the reader**

In `_sum_realized_pnl`, replace the file read with:

```python
    if trades_path is None:
        from swingbot.core.db import stages
        if stages.reads_db("trades"):
            from swingbot.core.db.repositories.trades import trades_repo
            # Function-local, like every other db import in this module: the
            # circular-import problem this function was written around is with
            # performance.py, and the repository is a different module.
            trades = trades_repo().list_all()
        else:
            trades = _read_trades_file(trades_path)
    else:
        trades = _read_trades_file(trades_path)
```

with the existing file-reading body extracted verbatim into
`_read_trades_file(path)`. The loop below it — the `realized_pnl_amount` /
`settle_legs` fallback — is untouched, which is what keeps the number identical.

- [ ] **Step 4: Write the importer and register parity**

Create `scripts/db/import_account.py`. Unlike the others its source is a single
dict, not a list, so it does not use `run_import`:

```python
#!/usr/bin/env python3
"""Import data/account.json: the config blob plus its balance history.

    python scripts/db/import_account.py --dry-run
    python scripts/db/import_account.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from swingbot import config                                       # noqa: E402
from swingbot.core.db.repositories.account import AccountRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json                  # noqa: E402
from scripts.db.import_common import record_checksum              # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source")
    args = ap.parse_args(argv)

    src = read_json(args.source or os.path.join(config.DATA_DIR, "account.json"), {})
    history = src.get("balance_history") or []
    print(f"[account] config keys: {len(src)}, history points: {len(history)}")
    if args.dry_run:
        print("[account] DRY RUN -- nothing written")
        return 0

    repo = AccountRepository()
    repo.save(src)

    stored = repo.load()
    expected = {k: v for k, v in src.items() if k != "balance_history"}
    ok = record_checksum(stored) == record_checksum(expected)
    stored_history = repo.history()
    counts_ok = len(stored_history) == len(history)
    print(f"[account] config checksum: {'OK' if ok else 'MISMATCH'}")
    print(f"[account] history rows: {len(stored_history)} "
          f"(expected {len(history)}) {'OK' if counts_ok else 'MISMATCH'}")
    return 0 if (ok and counts_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Register `account` in `parity_report.py` with a `loader` that strips
`balance_history` and wraps the blob into a one-element list keyed by a constant.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/planning/test_sum_realized_pnl_db.py
python scripts/dev/testrun.py file tests/planning/test_account.py
python scripts/db/import_account.py --dry-run
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/planning/account.py scripts/db/import_account.py \
        scripts/db/parity_report.py tests/planning/test_sum_realized_pnl_db.py
git commit -m "feat(v67): sum realized P&L from rows, add the account importer"
```

---

### Task P2-16: Analytics parity over the migrated stores

Success criterion 3: analytics outputs are numerically identical before and
after. This is the task that produces that evidence for Part 2's stores, and it
is worth its own gate because the spec names it the primary evidence the
migration was faithful.

**Files:**
- Create: `tests/analytics/test_analytics_backend_parity.py`

**Interfaces:**
- Consumes: `TradeRepository` (P2-01), `TradeLog` (P2-04), the existing
  `build_snapshot` (`core/analytics/snapshots.py:25`).
- Produces: nothing consumed by later tasks. Pure verification.

- [ ] **Step 1: Write the test**

Create `tests/analytics/test_analytics_backend_parity.py`:

```python
"""Same trades, two backends, identical numbers.

Success criterion 3. It is a separate test rather than a line in another one
because it is the primary evidence the migration was faithful -- if this drifts,
every expectancy number this repo reports drifted with it.
"""
import os

import pytest

from swingbot import config
from swingbot.core.analytics.snapshots import build_snapshot
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.infra.jsonio import atomic_write_json
from swingbot.core.tracking.performance import TradeLog


def _closed(i, status, r):
    return dict(trade_id=f"T{i}", ticker=["AAPL", "MSFT", "NVDA"][i % 3],
                strategy=["RSI", "MACD"][i % 2], horizon="2w",
                direction="bullish" if i % 2 else "bearish", status=status,
                opened_at=f"2026-01-{(i % 27) + 1:02d}T15:00:00+00:00",
                closed_at=f"2026-02-{(i % 27) + 1:02d}T15:00:00+00:00",
                entry=100.0 + i, stop_loss=95.0 + i, take_profit=110.0 + i,
                confidence_level=(i % 5) + 1, r_multiple=r,
                realized_pnl_amount=r * 100.0, exit_price=100.0 + i + r)


@pytest.fixture
def population():
    rows = []
    for i in range(40):
        win = i % 3 != 0
        rows.append(_closed(i, "win" if win else "loss", 2.0 if win else -1.0))
    return rows


def _snapshot_from(trade_log):
    closed = [t for t in trade_log.get_trades(status=None, limit=None)
              if t.get("status") in ("win", "loss")]
    return build_snapshot(closed, starting_balance=10000.0, registry_entries=[])


def test_snapshots_are_identical_across_backends(population, tmp_path,
                                                 monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))

    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    from_file = _snapshot_from(TradeLog())

    for row in population:
        TradeRepository().upsert(row)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    from_db = _snapshot_from(TradeLog())

    assert from_db == from_file


def test_get_stats_is_identical_across_backends(population, tmp_path,
                                                monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    file_stats = TradeLog().get_extended_stats()

    for row in population:
        TradeRepository().upsert(row)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert TradeLog().get_extended_stats() == file_stats


def test_stats_by_confidence_is_identical(population, tmp_path, monkeypatch,
                                          db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    atomic_write_json(os.path.join(tmp_path, "trades.json"), population)
    file_stats = TradeLog().get_stats_by_confidence()

    for row in population:
        TradeRepository().upsert(row)
    monkeypatch.setattr(config, "DB_STORES", "trades:db")
    assert TradeLog().get_stats_by_confidence() == file_stats
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/analytics/test_analytics_backend_parity.py
```

Expected: `0 failed`.

**If any of the three fails, the failure is the deliverable, not the test.**
Read the diff before touching anything: the two most likely causes are a
`NUMERIC` column returning `Decimal` where the file returned `float` (fix by
casting in the repository, never by rounding the assertion) and an ordering
difference from `list_all()`'s `ORDER BY` versus file order (fix by matching the
file's order, since analytics that depend on order are analytics whose result
was always order-dependent).

- [ ] **Step 3: Commit**

```bash
git add tests/analytics/test_analytics_backend_parity.py
git commit -m "test(v67): pin analytics parity across storage backends"
```

---

### Task P2-17: The journal repository and importer

**Files:**
- Create: `swingbot/core/db/repositories/journal.py`
- Create: `scripts/db/import_journal.py`
- Modify: `scripts/db/parity_report.py`
- Test: `tests/db/test_journal_repository.py`

**Interfaces:**
- Consumes: `journal_entries` (P2-01), `run_import` (P2-02).
- Produces: `JournalRepository` with `entries(strategy=None, tag=None,
  outcome=None, since=None, has_note=None) -> list[dict]`; `journal_repo()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_journal_repository.py`:

```python
"""JournalRepository.entries mirrors JournalStore.entries exactly -- same
filters, same AND-combination, same newest-first ordering."""
import pytest

from swingbot.core.db.repositories.journal import JournalRepository


@pytest.fixture
def repo():
    return JournalRepository()


def _e(trade_id, **over):
    base = dict(trade_id=trade_id, strategy="RSI", outcome="win",
                closed_at="2026-01-09T15:00:00+00:00",
                created_at="2026-01-09T16:00:00+00:00",
                tags=["clean-entry"], note="", lesson="held to TP1")
    base.update(over)
    return base


def test_entries_are_newest_first_by_closed_at(repo, db_conn):
    repo.upsert(_e("OLD", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_e("NEW", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    assert [e["trade_id"] for e in repo.entries(conn=db_conn)] == ["NEW", "OLD"]


def test_filter_by_strategy(repo, db_conn):
    repo.upsert(_e("T1", strategy="RSI"), conn=db_conn)
    repo.upsert(_e("T2", strategy="MACD"), conn=db_conn)
    assert [e["trade_id"] for e in repo.entries(strategy="MACD", conn=db_conn)] == ["T2"]


def test_filter_by_outcome(repo, db_conn):
    repo.upsert(_e("T1", outcome="win"), conn=db_conn)
    repo.upsert(_e("T2", outcome="loss"), conn=db_conn)
    assert [e["trade_id"] for e in repo.entries(outcome="loss", conn=db_conn)] == ["T2"]


def test_filter_by_tag_uses_jsonb_containment(repo, db_conn):
    repo.upsert(_e("T1", tags=["clean-entry", "runner"]), conn=db_conn)
    repo.upsert(_e("T2", tags=["chased"]), conn=db_conn)
    assert [e["trade_id"] for e in repo.entries(tag="runner", conn=db_conn)] == ["T1"]


def test_filter_by_since_is_inclusive(repo, db_conn):
    repo.upsert(_e("T1", closed_at="2026-01-01T00:00:00+00:00"), conn=db_conn)
    repo.upsert(_e("T2", closed_at="2026-01-09T00:00:00+00:00"), conn=db_conn)
    out = repo.entries(since="2026-01-09T00:00:00+00:00", conn=db_conn)
    assert [e["trade_id"] for e in out] == ["T2"]


def test_filter_by_has_note(repo, db_conn):
    repo.upsert(_e("T1", note="  "), conn=db_conn)      # whitespace is no note
    repo.upsert(_e("T2", note="real note"), conn=db_conn)
    assert [e["trade_id"] for e in repo.entries(has_note=True, conn=db_conn)] == ["T2"]
    assert [e["trade_id"] for e in repo.entries(has_note=False, conn=db_conn)] == ["T1"]


def test_filters_are_and_combined(repo, db_conn):
    repo.upsert(_e("T1", strategy="RSI", outcome="win"), conn=db_conn)
    repo.upsert(_e("T2", strategy="RSI", outcome="loss"), conn=db_conn)
    out = repo.entries(strategy="RSI", outcome="loss", conn=db_conn)
    assert [e["trade_id"] for e in out] == ["T2"]


def test_re_adding_replaces_rather_than_duplicating(repo, db_conn):
    repo.upsert(_e("T1", lesson="first"), conn=db_conn)
    repo.upsert(_e("T1", lesson="second"), conn=db_conn)
    assert repo.count(conn=db_conn) == 1
    assert repo.get("T1", conn=db_conn)["lesson"] == "second"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_journal_repository.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/journal.py`:

```python
"""Per-trade lessons journal."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import journal_entries


class JournalRepository(Repository):
    def __init__(self):
        super().__init__(journal_entries, key="trade_id")

    def entries(self, *, strategy: str | None = None, tag: str | None = None,
                outcome: str | None = None, since: str | None = None,
                has_note: bool | None = None, conn=None) -> list[dict]:
        """Every matching entry, newest first. Filters are AND-combined and
        an omitted filter is not applied -- the same contract JournalStore
        .entries() has today, restated in SQL."""
        clauses = []
        if strategy is not None:
            clauses.append(journal_entries.c.strategy == strategy)
        if outcome is not None:
            clauses.append(journal_entries.c.outcome == outcome)
        if since is not None:
            clauses.append(journal_entries.c.closed_at >= since)
        if tag is not None:
            # jsonb containment: doc->'tags' @> '["runner"]'. This is what the
            # GIN index on doc answers, so a tag filter stays cheap as the
            # journal grows.
            clauses.append(journal_entries.c.doc["tags"].contains([tag]))
        if has_note is not None:
            note = sa.func.btrim(
                sa.func.coalesce(journal_entries.c.doc["note"].astext, ""))
            clauses.append(note != "" if has_note else note == "")
        return self.list_all(
            conn=conn,
            where=sa.and_(*clauses) if clauses else None,
            # closed_at NULLS LAST, then created_at -- JournalStore sorts on
            # `closed_at or created_at or ""`, which puts an entry with no
            # closed_at last. Matching that exactly is what keeps the
            # admin/Discord browsers rendering the same order.
            order_by=sa.desc(sa.func.coalesce(
                journal_entries.c.closed_at, journal_entries.c.created_at)),
        )


_repo: JournalRepository | None = None


def journal_repo() -> JournalRepository:
    global _repo
    if _repo is None:
        _repo = JournalRepository()
    return _repo
```

- [ ] **Step 4: Write the importer and register parity**

Create `scripts/db/import_journal.py` on `run_import`'s shape with
`key="trade_id"`, `name="journal"`, source `data/journal.json`. Register
`journal` in `parity_report.py`.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_journal_repository.py
python scripts/db/import_journal.py --dry-run
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/repositories/journal.py scripts/db/import_journal.py \
        scripts/db/parity_report.py tests/db/test_journal_repository.py
git commit -m "feat(v67): add the journal repository and importer"
```

---

### Task P2-18: JournalStore uses Postgres

**Files:**
- Modify: `swingbot/core/analytics/journal.py` (`JournalStore`, `:24-90`)
- Test: `tests/analytics/test_journal_db.py`

**Interfaces:**
- Consumes: `journal_repo` (P2-17), `stages`.
- Produces: no new public symbols. `add`, `get`, `entries` keep their
  signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_journal_db.py`:

```python
"""JournalStore at each stage."""
import os

import pytest

from swingbot import config
from swingbot.core.analytics.journal import JournalStore
from swingbot.core.db.repositories.journal import JournalRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _entry(trade_id="T1", **over):
    e = dict(trade_id=trade_id, strategy="RSI", outcome="win",
             closed_at="2026-01-09T15:00:00+00:00", tags=["runner"],
             note="", lesson="held to TP1")
    e.update(over)
    return e


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    JournalStore().add(_entry())
    assert os.path.exists(os.path.join(data_dir, "journal.json"))
    assert JournalRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "journal:dual")
    JournalStore().add(_entry())
    assert os.path.exists(os.path.join(data_dir, "journal.json"))
    assert JournalRepository().get("T1", conn=db_committed) is not None


def test_db_stage_reads_rows(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    store = JournalStore()
    store.add(_entry("T1"))
    store.add(_entry("T2", outcome="loss"))
    assert {e["trade_id"] for e in store.entries()} == {"T1", "T2"}
    assert [e["trade_id"] for e in store.entries(outcome="loss")] == ["T2"]
    assert not os.path.exists(os.path.join(data_dir, "journal.json"))


def test_add_stamps_created_at_every_time(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    store = JournalStore()
    first = store.add(_entry())
    second = store.add(_entry(lesson="revised"))
    assert second["created_at"] >= first["created_at"]
    assert store.get("T1")["lesson"] == "revised"


def test_add_returns_the_stamped_entry(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    out = JournalStore().add(_entry())
    assert "created_at" in out and out["trade_id"] == "T1"


def test_get_returns_none_for_a_missing_trade(data_dir, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DB_STORES", "journal:db")
    assert JournalStore().get("nope") is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/analytics/test_journal_db.py -q
```

Expected: `test_dual_stage_writes_both` fails.

- [ ] **Step 3: Branch the three methods**

In `JournalStore`:

```python
    def add(self, entry: dict) -> dict:
        from swingbot.core.db import stages
        stamped = dict(entry, created_at=datetime.now(timezone.utc).isoformat())
        if stages.writes_json("journal"):
            with _LOCK:
                entries = self._load()
                entries = [e for e in entries
                           if e.get("trade_id") != entry.get("trade_id")]
                entries.append(stamped)
                self._save(entries)
        if stages.writes_db("journal"):
            from swingbot.core.db.repositories.journal import journal_repo
            # upsert replaces on trade_id, which is exactly the
            # remove-then-append the file path does.
            journal_repo().upsert(stamped)
        return stamped
```

`get` and `entries` gain a `reads_db("journal")` branch delegating to
`journal_repo().get(trade_id)` and `journal_repo().entries(**filters)`. Keep the
existing file bodies below the branch untouched — they are the `json`-stage
behaviour and Part 6 deletes them.

Note `created_at` is stamped **once**, before either branch, so the two backends
cannot disagree about it at the dual stage. Stamping inside each branch is the
obvious-looking version and it is wrong.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/analytics/test_journal_db.py
python scripts/dev/testrun.py file tests/analytics/test_journal.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/journal.py tests/analytics/test_journal_db.py
git commit -m "feat(v67): migrate the journal to postgres"
```

---

