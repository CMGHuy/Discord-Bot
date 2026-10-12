# v160 eToro demo mirror, part 1: foundations, sizing and order checks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task EM3" -A 400 <this file>`; never read the plan whole.

**Spec:** `docs/superpowers/specs/etoro-migration/2026-10-11-v160-etoro-demo-mirror-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)

**Index:** `docs/superpowers/plans/etoro-migration/2026-10-11-v160-etoro-demo-mirror_0-index.md` carries the Global Constraints, the `## Parallelisation` table and the task ledger. Every task below implicitly includes those constraints. This part holds **EM1–EM3**: Phase 1 (v159 gate, worktree, `requests` pin, the two settings, the `broker_orders` table and repository) and the start of Phase 2 (`sizing.py`). **EM4–EM5 (`checks.py`) are in the sibling file `2026-10-11-v160-etoro-demo-mirror_1b-checks.md`**: the index assigns them to part 1, but with full code part 1 would pass the 1500-line cap, and a task is never split or compressed.

**Shell variables used in every task** (Git Bash; never `cd`):

```bash
REPO="E:/Documents/Private/Projects/Discord-Bot"
WT="$REPO/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror"
```

## Parallelisation (this part)

EM1 first, alone. Then EM2 ∥ EM3 (disjoint files, no shared contract). EM4 and EM5 (in `_1b`): EM4 after EM1 (may run beside EM7 from part 2); EM5 after EM4 (same file, `checks.py`, appends to `_OPEN_CHECKS`). See the index for the cross-part edges.

# Phase 1: gate, settings and storage

### Task EM1: Preflight: v159 gate, worktree, `requests` pin, the two settings, broker-package allow-list

**Model:** haiku — mechanical: two declarative settings, one pin, one `.env.example` block and one test swap, every line given below.

Spec § Config, § Components (`requests` pinned at the installed version), Depends on. Index § Depends on v159 (hard gate), § Global Constraints (settings, demo only).

**Files:**
- Modify: `requirements.txt` (after `yfinance==0.2.66`, ~l.23)
- Modify: `swingbot/config.py` (section "eToro Paper Trading", ~l.127-150 once v159 ER7 has landed)
- Modify: `.env.example` (eToro block, ~l.421-430 once v159 ER7 has landed)
- Modify: `tests/infra/test_config_etoro.py`
- Modify (v159 ER7): `tests/broker/test_guard.py` (replace `test_the_broker_package_holds_only_the_guard`)

**Interfaces:**
- Consumes (v159 ER7/ER8, must be on `main`): `swingbot/core/broker/guard.py` (`assert_demo`, `RealAccountBlocked`, `UNLOCK_KEYS`), `tests/broker/test_guard.py` (`guard` imported at module top; `unguarded_etoro_modules`), the `ETORO_ALLOW_REAL`/`ETORO_REAL_SIGNOFF` fields; `swingbot.config.Field`, `config.reload()`, `config.ENV_PATH`, `config._ENV_MTIME`, `config._DOTENV_LOADED`, `config._DOTENV_FROM_CANONICAL_PATH` (all exist: `swingbot/config.py:54`, `:1404`, `:1414`, `:1417`).
- Produces:
  - `requests==<the version pip show reports>` in `requirements.txt` (2.34.2 on 2026-10-11).
  - `config.ETORO_MIRROR_ENABLED: bool`: `Field(type="checkbox", default="false")`, section `"eToro Paper Trading"`, hot-reloadable, not sensitive.
  - `config.ETORO_MAX_TRADE_USD: float`: `Field(type="float", default="100", min=0, step=10)`, same section, hot-reloadable, not sensitive.
  - `tests/broker/test_guard.py::ALLOWED_BROKER_MODULES = {"__init__.py", "guard.py", "etoro_client.py", "mirror.py", "sizing.py", "checks.py", "executor.py"}` and `test_the_broker_package_holds_only_known_modules` (replaces `test_the_broker_package_holds_only_the_guard`).

- [ ] **Step 0: Prove the v159 gate, then create or reuse the worktree**

```bash
REPO="E:/Documents/Private/Projects/Discord-Bot"
WT="$REPO/.claude/worktrees/2026-10-11-v160-etoro-demo-mirror"
git -C "$REPO" fetch --quiet origin 2>/dev/null || true
git -C "$REPO" log --oneline -1 main
git -C "$REPO" grep -n "def assert_demo" main -- swingbot/core/broker/guard.py
git -C "$REPO" grep -n "def unguarded_etoro_modules" main -- tests/broker/test_guard.py
git -C "$REPO" grep -n "def test_the_broker_package_holds_only_the_guard" main -- tests/broker/test_guard.py
```

Expected: each `git grep` prints exactly one line. **If the first or second prints nothing, stop and return `BLOCKED: v159 ER7/ER8 not on main`.** Do not create the worktree and do not stub the guard. If only the third prints nothing, v159 renamed its file-list test: read `tests/broker/test_guard.py` on `main` and apply Step 3 to whichever test pins the package's file list.

Then (use the `worktree-lifecycle` skill):

```bash
git -C "$REPO" worktree list | grep -F "2026-10-11-v160-etoro-demo-mirror" \
  || git -C "$REPO" worktree add "$WT" -b 2026-10-11-v160-etoro-demo-mirror main
git -C "$WT" status --short --branch
```

Expected: `## 2026-10-11-v160-etoro-demo-mirror`, clean. If the worktree already exists, reuse it and resume at its first uncommitted task.

- [ ] **Step 1: Write the failing tests**

Append to `$WT/tests/infra/test_config_etoro.py` (keep the existing tests, including v159's two):

```python
def test_mirror_switch_and_trade_cap_are_declared():
    keys = {f.key: f for f in config.FIELDS}
    switch, cap = keys["ETORO_MIRROR_ENABLED"], keys["ETORO_MAX_TRADE_USD"]
    assert switch.section == cap.section == "eToro Paper Trading"
    assert switch.type == "checkbox" and switch.default == "false"
    assert cap.type == "float" and cap.default == "100"
    assert cap.min == 0 and cap.step == 10
    assert switch.hot_reloadable and cap.hot_reloadable
    assert not switch.sensitive and not cap.sensitive
    assert "DEMO" in switch.help
    assert "no_trade_cap" in cap.help and "never up" in cap.help


def test_mirror_settings_have_their_cast_types():
    assert isinstance(config.ETORO_MIRROR_ENABLED, bool)
    assert isinstance(config.ETORO_MAX_TRADE_USD, float)


def test_a_reload_picks_up_both_mirror_settings(monkeypatch, tmp_path):
    """Hot reload (SIGHUP -> config.reload()) reaches both settings with no
    restart. Every global the reload reassigns is pinned so it is restored."""
    for key in ("ETORO_MIRROR_ENABLED", "ETORO_MAX_TRADE_USD"):
        monkeypatch.setenv(key, "")                             # restores os.environ
        monkeypatch.setattr(config, key, getattr(config, key))  # restores the global
    for attr in ("_ENV_MTIME", "_DOTENV_LOADED", "_DOTENV_FROM_CANONICAL_PATH"):
        monkeypatch.setattr(config, attr, getattr(config, attr))
    env = tmp_path / ".env"
    env.write_text("ETORO_MIRROR_ENABLED=true\nETORO_MAX_TRADE_USD=250\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_PATH", str(env))
    config.reload()
    assert config.ETORO_MIRROR_ENABLED is True
    assert config.ETORO_MAX_TRADE_USD == 250.0


def test_requests_is_pinned_exactly():
    """The mirror's client imports requests first-party (v160); Docker installs
    from requirements.txt, so a transitive-only install is not enough."""
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^requests==\d+\.\d+\.\d+$", text, re.MULTILINE)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_config_etoro.py`
Expected: FAIL: `KeyError: 'ETORO_MIRROR_ENABLED'` (declaration test), `AttributeError: module 'swingbot.config' has no attribute 'ETORO_MIRROR_ENABLED'` (cast-type and reload tests), and the `requests` pin assertion.

- [ ] **Step 3: Swap the guard test's file-list pin for an allow-list**

v159's `test_the_broker_package_holds_only_the_guard` asserts the package holds exactly `__init__.py` and `guard.py`; EM3 adds `sizing.py`, so it must become a subset check before any broker module lands. In `$WT/tests/broker/test_guard.py`, delete that whole test function (its comment line included) and put this in its place:

```python
#: Every module v160 may add beside v159's guard. A file outside this set is a
#: stray or a new module whose plan forgot to register it here. A subset, not
#: an equality: v160's tasks add these one at a time.
ALLOWED_BROKER_MODULES = {"__init__.py", "guard.py", "etoro_client.py", "mirror.py",
                          "sizing.py", "checks.py", "executor.py"}


def test_the_broker_package_holds_only_known_modules():
    from pathlib import Path
    pkg = Path(guard.__file__).parent
    present = {p.name for p in pkg.glob("*.py")}
    assert {"__init__.py", "guard.py"} <= present
    unknown = sorted(present - ALLOWED_BROKER_MODULES)
    assert not unknown, f"unregistered broker modules: {unknown}"
```

Leave every other test in the file (the guard cases and v159 ER8's AST scan) untouched.

- [ ] **Step 4: Pin `requests`**

Read the installed version and pin exactly that:

```bash
python -m pip show requests | head -2
```

Expected: `Version: 2.34.2` (if it differs, pin what it prints). In `$WT/requirements.txt`, directly after the `yfinance==0.2.66` line, insert:

```
# v160: the eToro demo mirror's REST client (swingbot/core/broker/etoro_client.py)
# imports requests first-party. Already installed transitively by yfinance and
# alpaca-py; pinned at that same version so the Docker image cannot drift.
requests==2.34.2
```

- [ ] **Step 5: Declare the two settings**

In `$WT/swingbot/config.py`, the section comment line that starts `    # --- eToro paper trading` (v159 ER7 rewrote it) becomes:

```python
    # --- eToro paper trading (credentials, the stage-3 lock broker/guard.py reads, the v160 demo mirror) ---
```

In the `ETORO_USER_KEY` field's `help`, replace the words `no code reads it yet.` with `read by the v160 demo mirror (swingbot/core/broker/etoro_client.py), demo routes only.` (re-wrap the string pieces as needed). In the `ETORO_API_KEY` field's `help`, replace the sentence `Leave blank until the eToro paper integration is built.` (split over two string pieces) with `Blank leaves the demo mirror's requests unauthenticated, and eToro answers 401.` Change nothing else in those two fields.

Directly after the `ETORO_REAL_SIGNOFF` field (v159 ER7's last eToro field), add:

```python
    Field("ETORO_MIRROR_ENABLED", "ETORO_MIRROR_ENABLED", "eToro Paper Trading",
          "Mirror plans to the eToro demo account", type="checkbox", default="false",
          help="When on, every main-ledger plan the bot fills on paper is also opened, "
               "stop-moved and closed on the eToro DEMO account (v160). Demo only: the code "
               "holds no real-account route. Off makes the mirror a no-op; open demo "
               "positions keep their eToro-side stop and target but stop following the bot."),
    Field("ETORO_MAX_TRADE_USD", "ETORO_MAX_TRADE_USD", "eToro Paper Trading",
          "Max USD per demo position", type="float", default="100", min=0, step=10,
          help="The most money put into one eToro demo position, in USD (eToro's order "
               "currency). The plan's own 2%-risk size is scaled down to fit, never up; "
               "entry, stop and target are unchanged, so R stays comparable to paper. "
               "0 or less skips every open (skip reason no_trade_cap)."),
```

- [ ] **Step 6: Add both settings to `.env.example`**

In `$WT/.env.example`, the comment line that starts `# --- eToro paper trading` becomes:

```
# --- eToro paper trading (credentials, the stage-3 lock, the v160 demo mirror) ---
```

Directly after the `ETORO_REAL_SIGNOFF=` line (v159 ER7), add:

```
# Demo mirror (v160): every main-ledger plan the bot fills on paper is also
# traded on the eToro DEMO account. Leave off until scripts/ops/etoro_demo_smoke.py
# has passed on the VM.
ETORO_MIRROR_ENABLED=false
# Most USD put into one demo position. The plan's own size is scaled down to
# it, never up. 0 or less skips every open (no_trade_cap).
ETORO_MAX_TRADE_USD=100
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_config_etoro.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/infra/test_env_example_sync.py`
Expected: PASS (both new keys present in `.env.example`).

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS, including `test_the_broker_package_holds_only_known_modules` and v159's `test_no_module_in_the_repo_touches_etoro_without_the_guard` (`swingbot/config.py` is exempt from the AST scan).

- [ ] **Step 8: Commit**

```bash
git -C "$WT" add requirements.txt swingbot/config.py .env.example \
  tests/infra/test_config_etoro.py tests/broker/test_guard.py
git -C "$WT" commit -m "feat(v160): EM1 -- requests pin, ETORO_MIRROR_ENABLED and ETORO_MAX_TRADE_USD

Two hot-reloaded settings in the eToro Paper Trading section: the demo
mirror switch (off) and the per-position USD cap (100; 0 or less skips
every open). requests pinned at the version already installed
transitively, because the mirror's client imports it first-party. v159's
exact file-list pin on swingbot/core/broker/ becomes an allow-list so
v160's modules can land one task at a time.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task EM2: `broker_orders` table, Alembic `v160_001`, repository

**Model:** opus — a schema change with a matching Alembic revision, a savepoint-scoped `IntegrityError` dedupe and the queue semantics every later task relies on.

Spec § Table `broker_orders`, § Executor rules (no row, no send; per-plan ordering), § Event mapping (deduplication). Index § Global Constraints (Alembic, `TABLE_CHANNELS`, never `StoreWriteHalt`). Read `docs/claude/schema-evolution.md` § Revision ids before writing the revision (`python scripts/dev/doc_section.py docs/claude/schema-evolution.md`).

**Files:**
- Modify: `swingbot/core/db/schema.py` (new table after `dropped_doc_fields`, ~l.205; new `PROMOTION_REASONS` entry before the closing `}`, ~l.291)
- Create: `swingbot/core/db/migrations/versions/v160_001_broker_orders.py`
- Create: `swingbot/core/db/repositories/broker_orders.py`
- Create: `tests/db/test_broker_orders_repository.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (import + one `CASES` row)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `schema.METADATA`, `schema.PROMOTION_REASONS` (`swingbot/core/db/schema.py:28`, `:19`, `:11`, `:217`); `Repository` (`swingbot/core/db/repositories/base.py:15`: `_tx`, `_record`, `_values`, `patch`, `count`); db fixtures `db_conn` (`tests/db/conftest.py:127`).
- Produces (EM8, EM9, EM11, EM12, EM13 rely on these exact names):
  - Table `broker_orders`: `id` BigInteger PK; NOT NULL `plan_id` Text, `action` Text, `event_key` Text, `seq` Integer, `request_id` Text (unique), `status` Text, `created_at` TIMESTAMPTZ (`server_default now()`); nullable `position_id` BigInteger; `doc`, `updated_at` from `standard_columns()`; `UniqueConstraint("plan_id", "action", "event_key", name="broker_orders_plan_action_key_uq")`; `Index("broker_orders_plan_seq_idx", "plan_id", "seq")`; `Index("broker_orders_status_idx", "status")`. Promoted: `("plan_id", "action", "event_key", "seq", "request_id", "status", "position_id", "created_at")`. Every other record field lives in `doc`.
  - `swingbot/core/db/repositories/broker_orders.py`:
    - `STATUSES = ("queued", "sending", "in_flight", "filled", "rejected", "skipped", "closed_by_broker")`
    - `FINAL_STATUSES = frozenset({"filled", "rejected", "skipped", "closed_by_broker"})`
    - `class BrokerOrderRepository(Repository)`, key `request_id`:
      - `insert_new(record: dict, *, conn=None) -> dict | None`: assigns `seq` = next free per `plan_id` (any caller `seq` is ignored), sets `status` to `"queued"` when absent, refuses an unknown status with `ValueError`; returns `None` when `(plan_id, action, event_key)` or `request_id` already exists (unique violation, SQLSTATE 23505, caught inside a savepoint so the caller's transaction stays usable); any other `IntegrityError` propagates.
      - `for_plan(plan_id: str, *, conn=None) -> list[dict]`: `seq` ascending.
      - `with_status(statuses: Iterable[str], *, conn=None) -> list[dict]`: ordered `plan_id, seq`.
      - `set_status(request_id: str, status: str, changes: dict | None = None, *, conn=None) -> None`: patches `changes` plus `status`; `ValueError` on an unknown status, `LookupError` when no row has that `request_id`.
      - `all_rows(*, conn=None) -> list[dict]`: ordered `plan_id, seq`; **each row also carries `updated_at` as an ISO-8601 string** (read-only, for the parity report's snapshot header; never pass it back into a write, `updated_at` is a reserved key).
      - `open_positions(*, conn=None) -> list[dict]`: the `open` rows with status `filled` whose plan has no `close_all` row with status `filled` or `closed_by_broker` and no row with status `closed_by_broker`; ordered `plan_id, seq`.
    - `broker_orders_repo() -> BrokerOrderRepository` (process singleton).
  - Records returned by every method are flat dicts (`merge_doc`): promoted columns plus `doc` keys; `created_at` comes back as a `datetime`; `position_id` is absent while NULL.

- [ ] **Step 1: Confirm the Alembic head**

```bash
python - "$WT" <<'HEADS_EOF'
import sys
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config()
cfg.set_main_option("script_location", sys.argv[1] + "/swingbot/core/db/migrations")
print(ScriptDirectory.from_config(cfg).get_heads())
HEADS_EOF
```

Expected: `['v144_001']`. If it prints a different single id (v159 or another plan added a revision), use that id wherever `v144_001` appears in Step 4 (`down_revision` and the `Revises:` docstring line). If it prints two ids, stop: `BLOCKED: two Alembic heads on main`.

- [ ] **Step 2: Write the failing tests**

Create `$WT/tests/db/test_broker_orders_repository.py`:

```python
"""broker_orders (v160): the eToro demo mirror's order ledger. One row per
broker action, written before the request is sent ("no row, no send");
(plan_id, action, event_key) is unique, so a resent plan notice can never
place a second order. DB tests skip when the db-test Postgres is down: start
it and rerun, a skipped run does not count."""
from pathlib import Path

import pytest
import sqlalchemy as sa

from swingbot.core.db import events, schema
from swingbot.core.db.repositories.broker_orders import (
    FINAL_STATUSES, STATUSES, BrokerOrderRepository, broker_orders_repo)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMOTED = ("plan_id", "action", "event_key", "seq", "request_id", "status",
            "position_id", "created_at")


def _row(plan_id="P1", action="open", event_key="filled", **extra):
    return {"plan_id": plan_id, "action": action, "event_key": event_key,
            "request_id": f"{plan_id}:{action}:{event_key}", "ticker": "AAPL", **extra}


@pytest.fixture
def repo():
    return BrokerOrderRepository()


# --- schema contract (no database) -----------------------------------------

def test_the_table_promotes_exactly_the_queried_columns():
    assert schema.promoted_for("broker_orders") == PROMOTED
    assert set(schema.PROMOTION_REASONS["broker_orders"]) == set(PROMOTED)


def test_identity_and_nullability():
    table = schema.METADATA.tables["broker_orders"]
    assert table.c.request_id.unique is True
    for name in ("plan_id", "action", "event_key", "seq", "request_id", "status", "created_at"):
        assert table.c[name].nullable is False, name
    assert table.c.position_id.nullable is True
    assert table.c.created_at.server_default is not None


def test_the_dedupe_constraint_and_both_indexes_exist():
    table = schema.METADATA.tables["broker_orders"]
    uniques = {c.name: tuple(col.name for col in c.columns)
               for c in table.constraints if isinstance(c, sa.UniqueConstraint)}
    assert uniques["broker_orders_plan_action_key_uq"] == ("plan_id", "action", "event_key")
    indexes = {i.name: tuple(col.name for col in i.columns) for i in table.indexes}
    assert indexes["broker_orders_plan_seq_idx"] == ("plan_id", "seq")
    assert indexes["broker_orders_status_idx"] == ("status",)


def test_the_status_vocabulary():
    assert STATUSES == ("queued", "sending", "in_flight", "filled", "rejected",
                        "skipped", "closed_by_broker")
    assert FINAL_STATUSES == frozenset({"filled", "rejected", "skipped", "closed_by_broker"})
    assert FINAL_STATUSES < set(STATUSES)


def test_no_admin_page_listens_to_it():
    assert "broker_orders" not in events.TABLE_CHANNELS


def test_the_revision_v160_001_sits_on_the_chain():
    # Not "is the head": a later plan's revision must not break this test.
    # tests/db/test_migrations.py::test_exactly_one_head guards the graph.
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "swingbot/core/db/migrations"))
    scripts = ScriptDirectory.from_config(cfg)
    revision = scripts.get_revision("v160_001")
    assert revision is not None and revision.down_revision is not None
    assert scripts.get_revision(revision.down_revision) is not None


def test_the_repository_is_a_process_singleton():
    assert broker_orders_repo() is broker_orders_repo()
    assert broker_orders_repo().key == "request_id"


# --- insert_new ---------------------------------------------------------------

def test_insert_new_assigns_seq_per_plan_and_defaults_to_queued(repo, db_conn):
    first = repo.insert_new(_row(), conn=db_conn)
    second = repo.insert_new(_row(action="move_stop", event_key="101.5000"), conn=db_conn)
    other = repo.insert_new(_row(plan_id="P2"), conn=db_conn)
    assert (first["seq"], second["seq"], other["seq"]) == (1, 2, 1)
    assert first["status"] == "queued"
    assert first["ticker"] == "AAPL"            # a doc field round-trips
    assert first["created_at"] is not None      # server default


def test_insert_new_keeps_an_explicit_status(repo, db_conn):
    row = repo.insert_new(_row(status="skipped", skip_reason="ineligible"), conn=db_conn)
    assert row["status"] == "skipped" and row["skip_reason"] == "ineligible"


def test_a_caller_supplied_seq_is_ignored(repo, db_conn):
    assert repo.insert_new(_row(seq=99), conn=db_conn)["seq"] == 1


def test_a_duplicate_key_returns_none_and_burns_no_seq(repo, db_conn):
    assert repo.insert_new(_row(), conn=db_conn) is not None
    assert repo.insert_new(_row(), conn=db_conn) is None
    nxt = repo.insert_new(_row(action="close_all", event_key="closed"), conn=db_conn)
    assert nxt["seq"] == 2
    assert repo.count(conn=db_conn) == 2


def test_a_duplicate_request_id_alone_is_also_a_duplicate(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    clash = dict(_row(event_key="other"), request_id="P1:open:filled")
    assert repo.insert_new(clash, conn=db_conn) is None


def test_a_duplicate_leaves_the_callers_transaction_usable(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    repo.insert_new(_row(), conn=db_conn)
    # Without the savepoint this read fails with InFailedSqlTransaction.
    assert [r["seq"] for r in repo.for_plan("P1", conn=db_conn)] == [1]


def test_a_not_null_violation_is_not_swallowed(repo, db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        repo.insert_new(_row(event_key=None), conn=db_conn)
    assert repo.count(conn=db_conn) == 0        # still usable after the savepoint


def test_an_unknown_status_is_refused(repo, db_conn):
    with pytest.raises(ValueError, match="unknown status"):
        repo.insert_new(_row(status="done"), conn=db_conn)


# --- reads and status changes ----------------------------------------------------

def test_for_plan_is_in_seq_order(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    repo.insert_new(_row(action="close_units", event_key="tp1_partial"), conn=db_conn)
    repo.insert_new(_row(plan_id="P2"), conn=db_conn)
    assert [r["action"] for r in repo.for_plan("P1", conn=db_conn)] == ["open", "close_units"]


def test_with_status_filters_and_orders_by_plan_then_seq(repo, db_conn):
    repo.insert_new(_row(plan_id="P2"), conn=db_conn)
    repo.insert_new(_row(plan_id="P1"), conn=db_conn)
    repo.insert_new(_row(plan_id="P1", action="close_all", event_key="closed",
                         status="skipped"), conn=db_conn)
    rows = repo.with_status(["queued", "sending"], conn=db_conn)
    assert [(r["plan_id"], r["seq"]) for r in rows] == [("P1", 1), ("P2", 1)]
    with pytest.raises(ValueError):
        repo.with_status(["done"], conn=db_conn)


def test_set_status_patches_promoted_and_doc_fields(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    repo.set_status("P1:open:filled", "filled",
                    {"position_id": 2_150_000_123, "avg_price": 100.25, "units_filled": 1.5},
                    conn=db_conn)
    row = repo.for_plan("P1", conn=db_conn)[0]
    assert row["status"] == "filled" and row["position_id"] == 2_150_000_123
    assert row["avg_price"] == 100.25 and row["units_filled"] == 1.5
    assert row["ticker"] == "AAPL"              # untouched doc fields survive


def test_set_status_without_changes(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    repo.set_status("P1:open:filled", "sending", conn=db_conn)
    assert repo.for_plan("P1", conn=db_conn)[0]["status"] == "sending"


def test_set_status_refuses_an_unknown_status_and_a_missing_row(repo, db_conn):
    repo.insert_new(_row(), conn=db_conn)
    with pytest.raises(ValueError):
        repo.set_status("P1:open:filled", "done", conn=db_conn)
    with pytest.raises(LookupError):
        repo.set_status("no-such-request", "filled", conn=db_conn)


def test_all_rows_carry_updated_at_for_the_snapshot_header(repo, db_conn):
    repo.insert_new(_row(plan_id="P2"), conn=db_conn)
    repo.insert_new(_row(plan_id="P1"), conn=db_conn)
    rows = repo.all_rows(conn=db_conn)
    assert [r["plan_id"] for r in rows] == ["P1", "P2"]
    assert all(isinstance(r["updated_at"], str) and "T" in r["updated_at"] for r in rows)


def test_open_positions_are_filled_opens_of_plans_not_yet_closed(repo, db_conn):
    def add(plan_id, action, event_key, status):
        repo.insert_new(_row(plan_id=plan_id, action=action, event_key=event_key,
                             status=status), conn=db_conn)
    add("P1", "open", "filled", "filled")                     # open, nothing after
    add("P2", "open", "filled", "filled")
    add("P2", "close_all", "closed", "filled")                # closed by the bot
    add("P3", "open", "filled", "filled")
    add("P3", "move_stop", "99.0000", "closed_by_broker")     # eToro closed it
    add("P4", "open", "filled", "rejected")                   # never opened
    add("P5", "open", "filled", "filled")
    add("P5", "close_units", "tp1_partial", "filled")         # partial: still open
    add("P6", "open", "filled", "filled")
    add("P6", "close_all", "closed", "queued")                # close not done yet
    add("P7", "open", "filled", "filled")
    add("P7", "close_all", "closed", "closed_by_broker")
    rows = repo.open_positions(conn=db_conn)
    assert [(r["plan_id"], r["action"]) for r in rows] == [
        ("P1", "open"), ("P5", "open"), ("P6", "open")]
```

Add the round-trip case in `$WT/tests/db/test_unknown_field_round_trip.py`. Add the import in alphabetical position, between the `account` and `flags` imports (directly before `from swingbot.core.db.repositories.flags import FlagRepository`):

```python
from swingbot.core.db.repositories.broker_orders import BrokerOrderRepository
```

and add this row at the end of `CASES` (after `"market_data_state"`):

```python
    "broker_orders": (BrokerOrderRepository, {"plan_id": "P-probe", "action": "open",
                                              "event_key": "filled", "seq": 1,
                                              "request_id": "R-probe", "status": "queued"}),
```

- [ ] **Step 3: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/db/test_broker_orders_repository.py`
Expected: FAIL: `ModuleNotFoundError: No module named 'swingbot.core.db.repositories.broker_orders'`.

- [ ] **Step 4: Add the table, its promotion reasons and the revision**

In `$WT/swingbot/core/db/schema.py`, directly after the `dropped_doc_fields = register(...)` block and before the `#: Why each promoted column is a column...` comment, add:

```python
# v160: the eToro demo mirror's order ledger. One row per broker action,
# written before the request is sent. No NOTIFY trigger: no admin page reads it.
broker_orders = register(sa.Table("broker_orders", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("plan_id", sa.Text, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("event_key", sa.Text, nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("request_id", sa.Text, nullable=False, unique=True),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("position_id", sa.BigInteger),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
              server_default=sa.func.now()),
    *standard_columns(),
    sa.UniqueConstraint("plan_id", "action", "event_key", name="broker_orders_plan_action_key_uq"),
    sa.Index("broker_orders_plan_seq_idx", "plan_id", "seq"),
    sa.Index("broker_orders_status_idx", "status")),
    ("plan_id", "action", "event_key", "seq", "request_id", "status", "position_id", "created_at"))
```

In the same file, add this entry as the last item of `PROMOTION_REASONS` (after `"dropped_doc_fields": {...},`):

```python
    "broker_orders": {
        "plan_id": "the paper plan a broker action mirrors; dedupe key and plan_seq index",
        "action": "part of the (plan_id, action, event_key) dedupe unique constraint",
        "event_key": "dedupe key part; a resent plan notice maps to the same key",
        "seq": "broker_orders_plan_seq_idx; per-plan send order",
        "request_id": "natural key; the x-request-id eToro deduplicates a resend on",
        "status": "broker_orders_status_idx; the executor's work queue",
        "position_id": "eToro position the close and stop routes address; reconciliation join",
        "created_at": "NOT NULL time the mirror decided to act",
    },
```

Create `$WT/swingbot/core/db/migrations/versions/v160_001_broker_orders.py`:

```python
"""broker_orders: the eToro demo mirror's order ledger (v160)

Additive. No NOTIFY trigger: no admin page reads this table, so it is not in
events.TABLE_CHANNELS. Older code ignores the table, so a routine rollback
needs no downgrade; downgrade() drops it and runs only by a deliberate
decision after scripts/ops/etoro_mirror_drain.py has closed every position.

Revision ID: v160_001
Revises: v144_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v160_001"
down_revision = "v144_001"
branch_labels = None
depends_on = None


def _std():
    return [
        sa.Column("doc", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("plan_id", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("event_key", sa.Text, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("request_id", sa.Text, nullable=False, unique=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("position_id", sa.BigInteger),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        *_std(),
        sa.UniqueConstraint("plan_id", "action", "event_key",
                            name="broker_orders_plan_action_key_uq"),
    )
    op.create_index("broker_orders_plan_seq_idx", "broker_orders", ["plan_id", "seq"])
    op.create_index("broker_orders_status_idx", "broker_orders", ["status"])


def downgrade() -> None:
    op.drop_index("broker_orders_status_idx", table_name="broker_orders")
    op.drop_index("broker_orders_plan_seq_idx", table_name="broker_orders")
    op.drop_table("broker_orders")
```

- [ ] **Step 5: Write the repository**

Create `$WT/swingbot/core/db/repositories/broker_orders.py`:

```python
"""broker_orders (v160): the eToro demo mirror's order ledger.

One row per broker action. The executor writes the row *before* it sends the
request ("no row, no send"), so the row is also the idempotency record:
`(plan_id, action, event_key)` is unique, and an action whose key is already
present is dropped here, before any request exists. `seq` orders a plan's
actions and is assigned only to an action that survived deduplication, so a
dropped duplicate never leaves a gap in the per-plan send order.

`Repository.upsert` conflicts on one column only, so the composite dedupe is a
plain INSERT whose unique violation is caught inside a savepoint: the caller's
transaction stays usable after a duplicate.
"""
from __future__ import annotations

from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import broker_orders

STATUSES = ("queued", "sending", "in_flight", "filled", "rejected", "skipped",
            "closed_by_broker")
FINAL_STATUSES = frozenset({"filled", "rejected", "skipped", "closed_by_broker"})

_UNIQUE_VIOLATION = "23505"        # PostgreSQL SQLSTATE unique_violation
_CLOSING = frozenset({"filled", "closed_by_broker"})


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"broker_orders: unknown status {status!r}; expected one of {STATUSES}")


def _is_duplicate(exc: IntegrityError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION


def _is_filled_open(row: dict) -> bool:
    return row["action"] == "open" and row["status"] == "filled"


def _plan_still_open(rows: list[dict]) -> bool:
    """False once eToro closed the position or the bot's close_all completed."""
    if any(row["status"] == "closed_by_broker" for row in rows):
        return False
    return not any(row["action"] == "close_all" and row["status"] in _CLOSING for row in rows)


class BrokerOrderRepository(Repository):
    def __init__(self):
        super().__init__(broker_orders, key="request_id")

    def _ordered(self, connection: sa.Connection, where=None) -> list:
        table = self.table
        statement = sa.select(table).order_by(table.c.plan_id, table.c.seq, table.c.id)
        if where is not None:
            statement = statement.where(where)
        return connection.execute(statement).all()

    def _next_seq(self, connection: sa.Connection, plan_id) -> int:
        statement = (sa.select(sa.func.coalesce(sa.func.max(self.table.c.seq), 0))
                     .where(self.table.c.plan_id == plan_id))
        return int(connection.execute(statement).scalar_one()) + 1

    def insert_new(self, record: dict, *, conn: sa.Connection | None = None) -> dict | None:
        """Insert one action; None when its key (or request id) already exists."""
        status = record.get("status", "queued")
        _check_status(status)
        with self._tx(conn) as connection:
            seq = self._next_seq(connection, record.get("plan_id"))
            values = self._values({**record, "status": status, "seq": seq})
            statement = sa.insert(self.table).values(**values).returning(self.table)
            try:
                with connection.begin_nested():
                    row = connection.execute(statement).one()
            except IntegrityError as exc:
                if _is_duplicate(exc):
                    return None
                raise
        return self._record(row)

    def for_plan(self, plan_id: str, *, conn: sa.Connection | None = None) -> list[dict]:
        with self._tx(conn) as connection:
            rows = self._ordered(connection, self.table.c.plan_id == plan_id)
        return [self._record(row) for row in rows]

    def with_status(self, statuses: Iterable[str], *,
                    conn: sa.Connection | None = None) -> list[dict]:
        wanted = list(statuses)
        for status in wanted:
            _check_status(status)
        with self._tx(conn) as connection:
            rows = self._ordered(connection, self.table.c.status.in_(wanted))
        return [self._record(row) for row in rows]

    def set_status(self, request_id: str, status: str, changes: dict | None = None, *,
                   conn: sa.Connection | None = None) -> None:
        _check_status(status)
        if self.patch(request_id, {**(changes or {}), "status": status}, conn=conn) is None:
            raise LookupError(f"broker_orders: no row with request_id {request_id!r}")

    def all_rows(self, *, conn: sa.Connection | None = None) -> list[dict]:
        """Every row, plus its `updated_at` as ISO text (read-only, for reports)."""
        with self._tx(conn) as connection:
            rows = self._ordered(connection)
        return [{**self._record(row), "updated_at": row.updated_at.isoformat()} for row in rows]

    def open_positions(self, *, conn: sa.Connection | None = None) -> list[dict]:
        """The filled `open` row of every plan whose demo position is still open."""
        table = self.table
        opened = sa.select(table.c.plan_id).where(table.c.action == "open",
                                                   table.c.status == "filled")
        with self._tx(conn) as connection:
            rows = [self._record(row) for row in self._ordered(connection, table.c.plan_id.in_(opened))]
        by_plan: dict[str, list[dict]] = {}
        for row in rows:
            by_plan.setdefault(row["plan_id"], []).append(row)
        return [row for plan_rows in by_plan.values() if _plan_still_open(plan_rows)
                for row in plan_rows if _is_filled_open(row)]


_repo: BrokerOrderRepository | None = None


def broker_orders_repo() -> BrokerOrderRepository:
    global _repo
    if _repo is None:
        _repo = BrokerOrderRepository()
    return _repo
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/db/test_broker_orders_repository.py`
Expected: PASS, `0 failed`, `0 xfailed`, **and no skips**. If the DB tests skip, the db-test Postgres is down: start it with the command the skip message prints and rerun; a skipped run does not finish this task.

Run each of these and expect PASS with no skips:

```bash
python "$WT/scripts/dev/testrun.py" file tests/db/test_migrations.py
python "$WT/scripts/dev/testrun.py" file tests/db/test_schema.py
python "$WT/scripts/dev/testrun.py" file tests/db/test_schema_contract.py
python "$WT/scripts/dev/testrun.py" file tests/db/test_unknown_field_round_trip.py
python "$WT/scripts/dev/testrun.py" file tests/db/test_trigger_coverage.py
```

`test_migrations_produce_exactly_the_declared_schema` is the one that proves `schema.py` and `v160_001` agree on columns, the unique constraint and both indexes; if it reports a diff, fix whichever side disagrees with the Produces block above.

- [ ] **Step 7: Complexity**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/db/repositories/broker_orders.py"`
Expected: no output (every function below C).

- [ ] **Step 8: Commit**

```bash
git -C "$WT" add swingbot/core/db/schema.py \
  swingbot/core/db/migrations/versions/v160_001_broker_orders.py \
  swingbot/core/db/repositories/broker_orders.py \
  tests/db/test_broker_orders_repository.py tests/db/test_unknown_field_round_trip.py
git -C "$WT" commit -m "feat(v160): EM2 -- broker_orders table, Alembic v160_001, repository

The demo mirror's order ledger: one row per broker action, written before
the request goes out. (plan_id, action, event_key) is unique, so a resent
plan notice is dropped at insert (savepoint-scoped unique violation) and
never reaches eToro; seq is assigned only to a surviving action. No NOTIFY
trigger: no admin page reads the table.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2: sizing and order checks

### Task EM3: `sizing.py`: the plan's size scaled to the cap

**Model:** sonnet — a small pure module, but rounding direction and float edge cases decide whether a size can ever exceed the plan's.

Spec § Sizing and order checks ("Sizing", steps 1–3), § Components (`sizing.py`). Index § Global Constraints (Sizing, Units precision).

**Files:**
- Create: `swingbot/core/broker/sizing.py`
- Create: `tests/broker/test_sizing.py`

**Interfaces:**
- Consumes: nothing beyond the standard library. `tests/broker/__init__.py` exists (v159 ER7). `ALLOWED_BROKER_MODULES` already lists `sizing.py` (EM1).
- Produces (EM4, EM6, EM8 rely on these):
  - `WHOLE_UNIT_DECIMALS = 0`, `FRACTIONAL_UNIT_DECIMALS = 4`
  - `round_down(value: float, decimals: int) -> float`: truncates toward zero at `decimals` places through `Decimal(str(value))`; `0.0` for anything not finite and positive (including `None`); a negative `decimals` is treated as 0.
  - `@dataclass(frozen=True) class SizeResult: units: float; plan_units: float; plan_notional: float; capped_notional: float; scale_factor: float`
  - `mirror_units(plan_units: float, entry: float, max_trade_usd: float, precision: int) -> SizeResult`: `units = round_down(min(plan_units, max_trade_usd / entry), precision)`, never above `plan_units`; `plan_notional = plan_units * entry`, `capped_notional = units * entry`, `scale_factor = units / plan_units`. Any of `plan_units`, `entry`, `max_trade_usd` not finite and positive gives `units = capped_notional = scale_factor = 0.0` (with `plan_units`/`plan_notional` kept when they are themselves valid, else `0.0`). Every field is always a finite float.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/broker/test_sizing.py`:

```python
"""broker.sizing (v160): the paper plan's own size, scaled DOWN to
ETORO_MAX_TRADE_USD and rounded down to the instrument's unit precision.
Entry, stop and target are not inputs, so they cannot change."""
import ast
import inspect
import math

import pytest

from swingbot.core.broker import sizing
from swingbot.core.broker.sizing import (
    FRACTIONAL_UNIT_DECIMALS, WHOLE_UNIT_DECIMALS, SizeResult, mirror_units, round_down)

NAN, INF = float("nan"), float("inf")


def test_the_precision_constants():
    assert (WHOLE_UNIT_DECIMALS, FRACTIONAL_UNIT_DECIMALS) == (0, 4)


def test_the_plan_size_is_scaled_down_to_the_cap():
    # The paper plan: 40 units at 50.00 = 2,000 notional. Cap 100 -> 2 units.
    result = mirror_units(40, 50.0, 100.0, WHOLE_UNIT_DECIMALS)
    assert result == SizeResult(units=2.0, plan_units=40.0, plan_notional=2000.0,
                                capped_notional=100.0, scale_factor=0.05)


def test_a_cap_above_the_plan_notional_never_raises_the_units():
    result = mirror_units(1.5, 50.0, 10_000.0, FRACTIONAL_UNIT_DECIMALS)
    assert result.units == 1.5
    assert result.scale_factor == 1.0
    assert result.capped_notional == result.plan_notional == 75.0


def test_a_different_cap_changes_only_the_units():
    small = mirror_units(40, 50.0, 100.0, FRACTIONAL_UNIT_DECIMALS)
    large = mirror_units(40, 50.0, 250.0, FRACTIONAL_UNIT_DECIMALS)
    assert (small.units, large.units) == (2.0, 5.0)
    assert small.plan_units == large.plan_units == 40.0
    assert small.plan_notional == large.plan_notional == 2000.0


def test_whole_units_round_down_never_up():
    result = mirror_units(10, 37.0, 100.0, WHOLE_UNIT_DECIMALS)      # 100 / 37 = 2.70
    assert result.units == 2.0
    assert result.capped_notional == 74.0


def test_fractional_units_round_down_to_four_places():
    result = mirror_units(10, 37.0, 100.0, FRACTIONAL_UNIT_DECIMALS)
    assert result.units == 2.7027
    assert result.capped_notional == pytest.approx(99.9999)
    assert result.capped_notional <= 100.0


def test_a_share_dearer_than_the_cap_sizes_to_zero_whole_units():
    result = mirror_units(5, 450.0, 100.0, WHOLE_UNIT_DECIMALS)
    assert result.units == 0.0 and result.scale_factor == 0.0
    assert result.plan_notional == 2250.0


@pytest.mark.parametrize("plan_units, entry, cap", [
    (0, 50.0, 100.0), (-1, 50.0, 100.0), (NAN, 50.0, 100.0), (INF, 50.0, 100.0),
    (None, 50.0, 100.0), (10, 0.0, 100.0), (10, NAN, 100.0), (10, -5.0, 100.0),
    (10, 50.0, 0.0), (10, 50.0, -5.0), (10, 50.0, NAN),
])
def test_invalid_inputs_size_to_zero_with_finite_fields(plan_units, entry, cap):
    result = mirror_units(plan_units, entry, cap, FRACTIONAL_UNIT_DECIMALS)
    assert result.units == result.capped_notional == result.scale_factor == 0.0
    assert all(math.isfinite(v) for v in (result.plan_units, result.plan_notional))


def test_a_zero_cap_keeps_the_plan_fields_for_the_record():
    result = mirror_units(40, 50.0, 0.0, WHOLE_UNIT_DECIMALS)
    assert (result.plan_units, result.plan_notional) == (40.0, 2000.0)


def test_units_never_exceed_the_plan_or_the_cap_across_a_grid():
    for plan_units in (0.5, 1, 3.3333, 17, 250):
        for entry in (0.37, 9.99, 101.5, 999.0):
            for cap in (1.0, 100.0, 1e6):
                for precision in (WHOLE_UNIT_DECIMALS, FRACTIONAL_UNIT_DECIMALS):
                    result = mirror_units(plan_units, entry, cap, precision)
                    assert 0.0 <= result.units <= plan_units
                    assert result.units * entry <= cap + 1e-9


@pytest.mark.parametrize("value, decimals, expected", [
    (2.70279, 4, 2.7027), (0.29, 2, 0.29), (2.9999, 0, 2.0), (5.0, 0, 5.0),
    (1.23456789, 4, 1.2345), (7.5, -1, 7.0), (0.0, 4, 0.0), (-1.5, 0, 0.0),
    (NAN, 4, 0.0), (INF, 4, 0.0), (None, 4, 0.0),
])
def test_round_down(value, decimals, expected):
    assert round_down(value, decimals) == expected


def test_sizing_is_pure():
    tree = ast.parse(inspect.getsource(sizing))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {(node.module or "").split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}
    assert imported <= {"__future__", "dataclasses", "decimal", "math"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_sizing.py`
Expected: FAIL: `ModuleNotFoundError: No module named 'swingbot.core.broker.sizing'`.

- [ ] **Step 3: Write the module**

Create `$WT/swingbot/core/broker/sizing.py`:

```python
"""Mirror sizing (v160): the paper plan's own size, scaled down to the eToro cap.

Pure. `plan_units` is what planning.account.compute_position_size gave the
paper plan (the 2%-risk size the alert shows). The mirror never raises it: it
only scales it down so units x entry stays within ETORO_MAX_TRADE_USD, then
rounds DOWN to the instrument's unit precision (whole, or 4 decimals when
eToro's eligibility reports fractional units). Entry, stop and target are not
inputs and are never changed, so R per trade stays comparable to paper.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

WHOLE_UNIT_DECIMALS = 0
FRACTIONAL_UNIT_DECIMALS = 4


def _positive(value) -> bool:
    """True for a finite number above zero; False for None, NaN, inf, <= 0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def round_down(value: float, decimals: int) -> float:
    """Truncate toward zero at `decimals` places; 0.0 unless finite and positive.

    Goes through Decimal(str(value)) because binary floats round the wrong way
    at the boundary: 0.29 * 100 is 28.999999999999996, which a floor would cut
    to 0.28."""
    if not _positive(value):
        return 0.0
    quantum = Decimal(1).scaleb(-max(0, int(decimals)))
    return float(Decimal(str(float(value))).quantize(quantum, rounding=ROUND_DOWN))


@dataclass(frozen=True)
class SizeResult:
    units: float            # what the mirror sends
    plan_units: float       # the paper plan's size
    plan_notional: float    # plan_units x entry
    capped_notional: float  # units x entry
    scale_factor: float     # units / plan_units


def _zero(plan_units, entry) -> SizeResult:
    """No order. Keeps the plan's own figures when they are valid, for the row."""
    units = float(plan_units) if _positive(plan_units) else 0.0
    notional = units * float(entry) if units and _positive(entry) else 0.0
    return SizeResult(units=0.0, plan_units=units, plan_notional=notional,
                      capped_notional=0.0, scale_factor=0.0)


def mirror_units(plan_units: float, entry: float, max_trade_usd: float,
                 precision: int) -> SizeResult:
    """The plan's units scaled down so units x entry <= max_trade_usd."""
    if not (_positive(plan_units) and _positive(entry) and _positive(max_trade_usd)):
        return _zero(plan_units, entry)
    plan_units, entry = float(plan_units), float(entry)
    target = min(plan_units, float(max_trade_usd) / entry)
    units = min(round_down(target, precision), plan_units)
    return SizeResult(units=units, plan_units=plan_units, plan_notional=plan_units * entry,
                      capped_notional=units * entry, scale_factor=units / plan_units)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_sizing.py`
Expected: PASS, `0 failed`, `0 xfailed`.

Run: `python "$WT/scripts/dev/testrun.py" file tests/broker/test_guard.py`
Expected: PASS (`sizing.py` is in `ALLOWED_BROKER_MODULES`; the AST scan ignores it, it touches no eToro name).

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C "$WT/swingbot/core/broker/sizing.py"`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/core/broker/sizing.py tests/broker/test_sizing.py
git -C "$WT" commit -m "feat(v160): EM3 -- broker sizing: the plan's size scaled down to the cap

mirror_units scales the paper plan's own units down so units x entry stays
within ETORO_MAX_TRADE_USD, rounds down to whole or 4-decimal units, and
records plan notional, capped notional and scale factor. It never raises a
size; invalid inputs size to zero. Pure.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

