# v67 — Part 9: Round trip and reversibility (tasks P9-01…P9-04)

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** Part 7 must be merged
> (profiles, the snapshot pull, the read-only role) and Part 8's codec tooling
> must exist. Tasks P9-05…P9-08 are in
> `2026-08-29-v67-json-to-postgres_9b-data-migrations.md`.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

## Why this part exists

Part 7 made production data reachable from a dev machine. Part 8 made a record's
*shape* cheap to change. Three things they left undone, each of which is a
question someone will ask within a month of the cutover:

1. **"I trained locally — now get the result into production."** Part 7 is
   one-directional. There is no path back, and the obvious improvisations
   (`psql` from a tunnel, restoring a local dump over production) are exactly
   the ones that lose trade history.
2. **"Roll it back."** Every part runs `alembic downgrade` once, by hand, for
   the revision it just wrote. Nothing checks that the *whole graph* still goes
   down and back up, so "rollback is easy" is an untested claim about
   thirty-odd revisions.
3. **"The field's values are wrong now, not its name."** Rename, drop and
   promote change what a field is *called* and where it is *stored*. Changing
   what it *contains* — units, a split, a reshaped nested structure — has no
   tool, no dry run and no undo.

`_9a` covers the push and the downgrade guarantee; `_9b` covers value-level
data migrations and their rollback.

## What may move from local to production, and what may not

The push is **allowlisted by table**, and the list is short on purpose:

| Table | Push? | Why |
|---|---|---|
| `tuning_results` | **yes** | a grid run takes hours; running it locally is the point |
| `tuning_proposals` | **yes** | derived from a tuning run, reviewed by a human |
| `fold_trades` | **yes** | E39's fold outcomes, computed offline by design |
| `rs_cache`, `ticker_meta_cache`, `ticker_directory` | no | regenerate in production in seconds, and are date-sensitive |
| `settings` | **no** | that is the admin UI's job. Pushing config from a dev checkout is how production ends up running someone's experiment |
| every trading-state table | **never** | trades, plans, account, journal, state, watchlist. Production is the source of truth for these and a push would overwrite real history with a stale copy |
| `validation_registry.json` | n/a | still a file in git — its value *is* its auditable provenance, and it deploys with the image |

**The allowlist is the mechanism, not a guideline.** The tool takes table names
and refuses anything not on the list, with the reason from this table attached
to the refusal.

## Alembic revision ids

Part 9 owns `p9_*`.

| Revision | Content |
|---|---|
| `p9_001` | `data_migrations` — the applied-migrations ledger and its snapshots |

## Parallelisation

- **Group 9a (parallel):** P9-01 (push) and P9-02 (downgrade coverage) —
  different files, no shared symbol.
- **Sequential: P9-03 before P9-04** — the runner before its rollback.
- Part 9 runs after Part 7 and lands before P6-12, which is still the plan's
  single full-suite gate.

## Part 9 exit criteria

1. A locally-computed artifact reaches production with one command, against an
   allowlist that makes pushing trading state impossible rather than
   discouraged.
2. Every Alembic revision goes up, down and up again on a real database, proven
   by a test rather than by having been done once by hand.
3. A value-level data migration is a named, versioned, idempotent, dry-runnable
   script — and it records enough to be undone.
4. `scripts/db/edit_field.py drop` cannot lose data irrecoverably.
5. The pull → train → push round trip has been walked end-to-end.
6. `python scripts/dev/testrun.py fast` is green.

---

# Phase 9 — Round trip and reversibility

### Task P9-01: Push a locally-computed artifact to production

**Files:**
- Create: `scripts/ops/push_prod_artifacts.py`
- Modify: `Makefile`
- Test: `tests/scripts/test_push_prod_artifacts.py`

**Interfaces:**
- Consumes: `profiles.engine_for` (P7-04), `record_checksum` (P2-02),
  `backup_db.sh` (P6-03).
- Produces:
  - `PUSHABLE: dict[str, str]` — table → the reason it is pushable
  - `REFUSED: dict[str, str]` — table → the reason it is not
  - `push(tables, *, dry_run=True, source="snapshot") -> dict[str, int]`
  - CLI: `python scripts/ops/push_prod_artifacts.py tuning_results --dry-run`

**Four properties, and a test for each.** This is the only tool in the plan
that writes to production from a dev machine, so its guarantees are the
deliverable rather than its convenience:

1. **Allowlisted.** A table not in `PUSHABLE` is refused with the reason.
2. **Dry run by default.** `--dry-run` is the default and `--apply` is the
   opt-in, which is the opposite of the rest of this repo's scripts and is
   deliberate for the one that writes to production.
3. **Backs up production first.** Every real run triggers `backup_db.sh` before
   the first write.
4. **Upsert, never delete.** A push adds and updates rows; it never removes one.
   A local database missing a row production has is the normal case (you pulled
   a week ago), not an instruction to delete it.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_push_prod_artifacts.py`:

```python
"""The only tool here that writes to production. Its guarantees ARE the
deliverable."""
import pytest

from scripts.ops.push_prod_artifacts import (PUSHABLE, REFUSED, RefusedPush,
                                             push)


def test_the_allowlist_is_the_three_derived_artifacts():
    assert set(PUSHABLE) == {"tuning_results", "tuning_proposals", "fold_trades"}


def test_every_trading_state_table_is_explicitly_refused():
    for table in ("trades", "plans", "starred_plans", "account", "journal",
                  "signal_state", "watchlist"):
        assert table in REFUSED, f"{table} is not explicitly refused"
        assert REFUSED[table].strip(), f"{table}'s refusal has no reason"


def test_settings_is_refused_with_its_reason():
    assert "settings" in REFUSED
    assert "admin" in REFUSED["settings"].lower()


def test_pushing_a_refused_table_names_the_reason(monkeypatch):
    with pytest.raises(RefusedPush) as exc:
        push(["trades"], dry_run=True)
    assert "trades" in str(exc.value)
    assert REFUSED["trades"][:20] in str(exc.value)


def test_pushing_an_unknown_table_is_refused():
    with pytest.raises(RefusedPush, match="not on the allowlist"):
        push(["no_such_table"], dry_run=True)


def test_dry_run_is_the_default():
    import inspect
    assert inspect.signature(push).parameters["dry_run"].default is True


def test_the_cli_requires_apply_to_write():
    """--dry-run is the default and --apply is the opt-in. That is the
    opposite of every other script here, on purpose."""
    import scripts.ops.push_prod_artifacts as mod
    source = open(mod.__file__, encoding="utf-8").read()
    assert "--apply" in source
    assert "dry_run=not args.apply" in source or "not args.apply" in source


def test_a_real_run_backs_up_production_first(monkeypatch, db_committed):
    calls = []
    import scripts.ops.push_prod_artifacts as mod
    monkeypatch.setattr(mod, "_backup_production", lambda: calls.append("backup"))
    monkeypatch.setattr(mod, "_rows_to_push", lambda t, s: [])
    monkeypatch.setattr(mod, "_upsert_into_production", lambda t, rows: 0)
    push(["fold_trades"], dry_run=False)
    assert calls == ["backup"], "production was written without a backup"


def test_a_dry_run_does_not_back_up(monkeypatch):
    calls = []
    import scripts.ops.push_prod_artifacts as mod
    monkeypatch.setattr(mod, "_backup_production", lambda: calls.append("backup"))
    monkeypatch.setattr(mod, "_rows_to_push", lambda t, s: [{"strategy": "RSI"}])
    push(["fold_trades"], dry_run=True)
    assert calls == []


def test_a_dry_run_reports_what_it_would_write(monkeypatch):
    import scripts.ops.push_prod_artifacts as mod
    monkeypatch.setattr(mod, "_rows_to_push",
                        lambda t, s: [{"strategy": "RSI"}, {"strategy": "MACD"}])
    assert push(["fold_trades"], dry_run=True) == {"fold_trades": 2}


def test_a_push_never_deletes(monkeypatch):
    """A local database missing a row production has is the normal case -- you
    pulled a week ago -- not an instruction to delete it."""
    import scripts.ops.push_prod_artifacts as mod
    source = open(mod.__file__, encoding="utf-8").read()
    assert "delete" not in source.lower().replace("never delete", "").replace(
        "does not delete", "")


def test_the_source_profile_may_not_be_production(monkeypatch):
    with pytest.raises(RefusedPush, match="source"):
        push(["fold_trades"], dry_run=True, source="prod-ro")
```

`test_a_real_run_backs_up_production_first` is the one worth the most: it fails
if anyone reorders the backup below the first write.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_push_prod_artifacts.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write it**

Create `scripts/ops/push_prod_artifacts.py`:

```python
#!/usr/bin/env python3
"""Publish a locally-computed artifact to production.

    python scripts/ops/push_prod_artifacts.py tuning_results            # dry run
    python scripts/ops/push_prod_artifacts.py tuning_results --apply

The other direction from `make db-pull`: you run a grid locally because it
takes hours, and production needs the result.

This is the ONLY tool in this repo that writes to production from a dev
machine, so it is built around four guarantees rather than around convenience:

  1. allowlisted by table -- see PUSHABLE/REFUSED below;
  2. dry run by DEFAULT, --apply is the opt-in;
  3. every real run backs production up before its first write;
  4. upsert only. A push never deletes a row.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import sqlalchemy as sa                                       # noqa: E402

from swingbot.core.db import profiles                        # noqa: E402
from swingbot.core.db.codec import merge_doc, split_doc      # noqa: E402
from swingbot.core.db.schema import METADATA, promoted_for   # noqa: E402


class RefusedPush(ValueError):
    """The push is not allowed, and the reason says why."""


#: table -> why it is safe to compute locally and publish.
PUSHABLE = {
    "tuning_results": "a grid run takes hours; running it locally is the point",
    "tuning_proposals": "derived from a tuning run and reviewed by a human",
    "fold_trades": "E39's fold outcomes, computed offline by design",
}

#: table -> why it is NOT. Every refusal carries its reason so the error is an
#: explanation rather than a wall.
REFUSED = {
    "trades": "production is the source of truth for trade history; a push "
              "would overwrite real records with a stale local copy",
    "plans": "same as trades -- live lifecycle state, owned by production",
    "starred_plans": "owned by whoever is using the admin UI, not by a checkout",
    "account": "balance and risk settings are live trading state",
    "journal": "written from closed trades in production",
    "signal_state": "per-scan debounce state; meaningless outside its own process",
    "watchlist": "edit it in the admin UI, where the change is audited",
    "settings": "that is the admin UI's job. Pushing config from a dev checkout "
                "is how production ends up running someone's experiment",
    "rs_cache": "regenerates in production in seconds and is date-sensitive",
    "ticker_meta_cache": "regenerates from the network on demand",
    "ticker_directory": "regenerates from the exchange listing weekly",
    "scan_telemetry": "an append-only record of production's own scans",
    "shadow_plans": "an append-only record of production's own scans",
    "retrospective_history": "written by production's own retrospective",
    "analytics_snapshot": "rebuilt from closed trades; pushing one would show "
                          "numbers derived from a stale local copy",
    "scan_snapshots": "rewritten by production's next scan",
}


def _check(tables: list[str], source: str) -> None:
    if profiles.is_readonly(source):
        raise RefusedPush(
            f"source profile {source!r} is read-only -- there is nothing to "
            f"push FROM production TO production. Use 'local' or 'snapshot'.")
    for table in tables:
        if table in PUSHABLE:
            continue
        if table in REFUSED:
            raise RefusedPush(f"{table!r} is not pushable: {REFUSED[table]}")
        raise RefusedPush(
            f"{table!r} is not on the allowlist. Pushable tables: "
            f"{', '.join(sorted(PUSHABLE))}. If this one should be, add it to "
            f"PUSHABLE with the reason -- do not bypass this check.")


def _backup_production() -> None:
    """Run backup_db.sh against production before the first write."""
    ssh = os.getenv("SWINGBOT_SSH", "scripts/ops/ssh-hetzner.sh")
    print("push: backing production up first...", flush=True)
    subprocess.run([ssh, "cd /srv/swing-bot && ./scripts/ops/backup_db.sh"],
                   check=True)


def _rows_to_push(table: str, source: str) -> list[dict]:
    t = METADATA.tables[table]
    engine = profiles.engine_for(source)
    with engine.connect() as conn:
        rows = conn.execute(sa.select(t)).all()
    promoted = promoted_for(table)
    return [merge_doc(row._mapping, promoted) for row in rows]


def _upsert_into_production(table: str, rows: list[dict]) -> int:
    """Upsert every row. Never deletes: a local database missing a row
    production has is the normal case (you pulled a week ago), not an
    instruction to remove it."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    t = METADATA.tables[table]
    promoted = promoted_for(table)
    key = promoted[0]
    engine = profiles.engine_for("prod-write")
    written = 0
    with engine.begin() as conn:
        for i, record in enumerate(rows, 1):
            columns, doc = split_doc(record, promoted)
            values = {**columns, "doc": doc}
            stmt = pg_insert(t).values(**values).on_conflict_do_update(
                index_elements=[t.c[key]],
                set_={**{k: v for k, v in values.items() if k != key},
                      "updated_at": sa.func.now()})
            conn.execute(stmt)
            written += 1
            if i % 50 == 0 or i == len(rows):
                print(f"push: {table}: {i}/{len(rows)}", flush=True)
    return written


def push(tables: list[str], *, dry_run: bool = True,
         source: str = "snapshot") -> dict[str, int]:
    _check(tables, source)
    plan = {table: _rows_to_push(table, source) for table in tables}

    if dry_run:
        for table, rows in plan.items():
            print(f"push: DRY RUN -- would upsert {len(rows)} row(s) into "
                  f"production.{table}")
        return {table: len(rows) for table, rows in plan.items()}

    _backup_production()
    return {table: _upsert_into_production(table, rows)
            for table, rows in plan.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tables", nargs="+", choices=sorted(PUSHABLE) + sorted(REFUSED))
    ap.add_argument("--source", choices=profiles.PROFILES, default="snapshot")
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without it this is a dry run.")
    args = ap.parse_args(argv)
    try:
        result = push(args.tables, dry_run=not args.apply, source=args.source)
    except RefusedPush as exc:
        print(f"push: {exc}", file=sys.stderr)
        return 2
    for table, n in result.items():
        print(f"push: {table}: {n} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`profiles.engine_for("prod-write")` names a **fourth** profile that Part 7 does
not define, and that is deliberate: a write connection to production must not be
reachable from any of the three profiles an analysis tool selects. Add it to
`profiles.py` as a profile that resolves `DATABASE_URL_PROD_WRITE`, is **not**
in `PROFILES` (so no `--profile` flag can select it), and is refused by
`assert_application_database`. Update `tests/db/test_profiles.py` accordingly.

- [ ] **Step 4: Add the Makefile target**

```make
# make db-push TABLES="tuning_results fold_trades"   (dry run)
# make db-push TABLES="tuning_results" APPLY=--apply
db-push:
	python scripts/ops/push_prod_artifacts.py $(TABLES) $(APPLY)
```

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_push_prod_artifacts.py
python scripts/dev/testrun.py file tests/db/test_profiles.py
python scripts/ops/push_prod_artifacts.py trades          # expect a refusal, exit 2
python scripts/ops/push_prod_artifacts.py fold_trades     # expect a dry run
```

Expected: `0 failed`, then a refusal naming the reason, then a dry run.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/push_prod_artifacts.py swingbot/core/db/profiles.py \
        Makefile tests/scripts/test_push_prod_artifacts.py tests/db/test_profiles.py
git commit -m "feat(v67): publish locally-computed artifacts to production"
```

---

### Task P9-02: Every revision goes down and back up

"Rollback is easy" is currently an untested claim about thirty-odd revisions,
each of which had its `downgrade()` run once by hand at the moment it was
written and never again.

**Files:**
- Test: `tests/db/test_migration_reversibility.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: the full revision graph, `db_engine_empty` (P1-07).
- Produces: `make db-check-downgrade`.

**Why this matters more than it looks.** A `downgrade()` is written in the same
minute as its `upgrade()`, against an empty local database, and then never
exercised again — so by the time anyone needs one, it has had months to rot
against a revision that landed after it. The test walks the whole graph, which
is the only way to catch a downgrade that works alone and fails in sequence.

- [ ] **Step 1: Write the test**

Create `tests/db/test_migration_reversibility.py`:

```python
"""The whole revision graph, down and back up.

Each downgrade() was run once by hand when its revision was written, against an
empty database, and never again. This is what catches one that works alone and
fails in sequence.
"""
import pathlib

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

pytestmark = pytest.mark.slow          # it walks every revision twice

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def cfg(db_engine_empty):
    config = Config(str(REPO / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        db_engine_empty.url.render_as_string(hide_password=False))
    return config


def _tables(engine) -> set[str]:
    with engine.connect() as conn:
        return set(sa.inspect(conn).get_table_names())


def test_the_graph_upgrades_from_empty(cfg, db_engine_empty):
    command.upgrade(cfg, "head")
    tables = _tables(db_engine_empty)
    from swingbot.core.db.schema import METADATA
    missing = set(METADATA.tables) - tables
    assert not missing, f"upgrade left tables uncreated: {sorted(missing)}"


def test_the_graph_downgrades_to_base(cfg, db_engine_empty):
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    left = _tables(db_engine_empty) - {"alembic_version"}
    assert not left, f"downgrade left tables behind: {sorted(left)}"


def test_the_graph_upgrades_again_after_a_full_downgrade(cfg, db_engine_empty):
    """The one that catches a downgrade which drops something the next upgrade
    assumes is already gone -- or leaves something it assumes is absent."""
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from swingbot.core.db.schema import METADATA
    assert set(METADATA.tables) <= _tables(db_engine_empty)


def test_every_revision_steps_down_one_at_a_time(cfg, db_engine_empty):
    """Walking down one revision at a time, rather than straight to base,
    exercises each downgrade() against the state its own upgrade() produced."""
    scripts = ScriptDirectory.from_config(cfg)
    command.upgrade(cfg, "head")
    revisions = [r.revision for r in scripts.walk_revisions()]   # head -> base
    for revision in revisions:
        down = scripts.get_revision(revision).down_revision
        target = "base" if down is None else (
            down[0] if isinstance(down, tuple) else down)
        try:
            command.downgrade(cfg, target)
        except Exception as exc:                                 # noqa: BLE001
            pytest.fail(f"downgrade of {revision} -> {target} failed: {exc}")


def test_no_revision_has_an_empty_downgrade_without_saying_why(cfg):
    """A `pass` downgrade is legitimate -- a merge revision, or one that only
    creates a trigger it also drops. An UNEXPLAINED one is a revision nobody
    can roll back, discovered at the worst moment."""
    versions = REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
    offenders = []
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        body = text.split("def downgrade")[-1]
        stripped = [l.strip() for l in body.splitlines()[1:] if l.strip()]
        meaningful = [l for l in stripped if not l.startswith("#")
                      and not l.startswith('"""')]
        if meaningful == ["pass"]:
            # Legitimate only if the docstring or a comment explains it.
            if "deliberately empty" not in text and "no DDL" not in text:
                offenders.append(path.name)
    assert not offenders, (
        f"revisions with an unexplained empty downgrade(): {offenders}. "
        f"Either write the downgrade or say in the docstring why there is "
        f"nothing to undo.")
```

- [ ] **Step 2: Run it**

```bash
python -m pytest tests/db/test_migration_reversibility.py -q
```

Expected: `0 failed`. **A failure here is a real finding**, and the right fix is
the broken `downgrade()`, never the test. If a revision genuinely cannot be
reversed — a destructive data migration, say — its docstring says so and the
test's allowlist grows one entry with that reason.

- [ ] **Step 3: Expose it as a command**

```make
db-check-downgrade:
	python -m pytest tests/db/test_migration_reversibility.py -q
```

Document it in `docs/claude/schema-evolution.md`'s promote section: **run this
before shipping a revision**, because the moment you need a downgrade is never
the moment to discover it does not work.

- [ ] **Step 4: Commit**

```bash
git add tests/db/test_migration_reversibility.py Makefile \
        docs/claude/schema-evolution.md
git commit -m "test(v67): prove every revision downgrades and re-upgrades"
```

---

### Task P9-03: The data-migration runner

Rename, drop and promote change what a field is *called* and where it is
*stored*. This is for changing what it *contains* — units, a split, a reshaped
nested structure — which is the case the other three do not cover and the one
that actually recurs.

**Files:**
- Create: `swingbot/core/db/data_migrations/__init__.py`
- Create: `swingbot/core/db/data_migrations/runner.py`
- Create: `swingbot/core/db/migrations/versions/p9_001_data_migrations.py`
- Modify: `swingbot/core/db/schema.py`
- Create: `scripts/db/migrate_data.py`
- Test: `tests/db/test_data_migration_runner.py`

**Interfaces:**
- Consumes: `Repository` (P1-09), `profiles` (P7-04).
- Produces:
  - table `data_migrations` — `name` UNIQUE, `applied_at`, `rows_changed`, `doc`
  - `@data_migration(name)` — a decorator registering a transform
  - `DataMigration` protocol: `select(table) -> where clause`,
    `transform(record) -> dict | None`
  - `run(name, *, profile=None, dry_run=True, batch=500) -> Result`
  - CLI: `python scripts/db/migrate_data.py list | run <name> [--apply]`

**Four properties the runner enforces, so each migration does not have to:**

- **Idempotent.** A migration records itself in `data_migrations`; re-running is
  a no-op unless `--force`.
- **Dry run by default**, like the push tool, and for the same reason.
- **Batched with flushed progress.** A transform over every trade is exactly the
  kind of run `docs/claude/working-conventions.md` requires per-unit output from.
- **`transform` returning `None` means skip.** A migration should not have to
  express "leave this record alone" as "return it unchanged", because those two
  are different and only one of them writes a row.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_data_migration_runner.py`:

```python
"""Value-level data migrations: named, idempotent, dry-runnable, batched."""
import pytest

from swingbot.core.db.data_migrations import runner
from swingbot.core.db.repositories.trades import TradeRepository


def _t(trade_id, **over):
    base = dict(trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="open",
                opened_at="2026-01-02T15:00:00+00:00")
    base.update(over)
    return base


@pytest.fixture
def seeded(db_committed):
    repo = TradeRepository()
    with db_committed.begin():
        for i in range(5):
            repo.insert(_t(f"M{i}", stop_pct=1.5 + i), conn=db_committed)
        repo.insert(_t("NOFIELD"), conn=db_committed)
    yield repo
    import sqlalchemy as sa
    from swingbot.core.db.schema import data_migrations, trades
    with db_committed.begin():
        db_committed.execute(sa.delete(trades))
        db_committed.execute(sa.delete(data_migrations))


@pytest.fixture
def pct_to_fraction():
    @runner.data_migration("stop_pct_to_fraction")
    class _M:
        table = "trades"

        def select(self, t):
            return t.c.doc.has_key("stop_pct")          # noqa: W601

        def transform(self, record):
            value = record.get("stop_pct")
            if value is None:
                return None
            return {"stop_fraction": value / 100.0}
    yield "stop_pct_to_fraction"
    runner.REGISTRY.pop("stop_pct_to_fraction", None)


def test_a_dry_run_reports_without_writing(seeded, pct_to_fraction):
    result = runner.run(pct_to_fraction, dry_run=True)
    assert result.rows_matched == 5
    assert result.rows_changed == 0
    assert "stop_fraction" not in seeded.get("M0")


def test_applying_transforms_the_records(seeded, pct_to_fraction):
    result = runner.run(pct_to_fraction, dry_run=False)
    assert result.rows_changed == 5
    assert seeded.get("M0")["stop_fraction"] == pytest.approx(0.015)


def test_a_record_without_the_field_is_untouched(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=False)
    assert "stop_fraction" not in seeded.get("NOFIELD")


def test_the_transform_is_a_patch_not_a_replace(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=False)
    got = seeded.get("M0")
    assert got["ticker"] == "AAPL"
    assert got["stop_pct"] == 1.5        # the old field is not removed for us


def test_it_is_idempotent(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=False)
    second = runner.run(pct_to_fraction, dry_run=False)
    assert second.skipped is True
    assert second.rows_changed == 0


def test_force_reruns_it(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=False)
    again = runner.run(pct_to_fraction, dry_run=False, force=True)
    assert again.skipped is False


def test_it_is_recorded_in_the_ledger(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=False)
    applied = runner.applied()
    assert pct_to_fraction in applied
    assert applied[pct_to_fraction]["rows_changed"] == 5


def test_a_dry_run_is_not_recorded(seeded, pct_to_fraction):
    runner.run(pct_to_fraction, dry_run=True)
    assert pct_to_fraction not in runner.applied()


def test_returning_none_skips_the_record(seeded):
    @runner.data_migration("skip_everything")
    class _M:
        table = "trades"

        def select(self, t):
            return None

        def transform(self, record):
            return None
    try:
        result = runner.run("skip_everything", dry_run=False)
        assert result.rows_changed == 0
        assert result.rows_matched == 6
    finally:
        runner.REGISTRY.pop("skip_everything", None)


def test_an_unknown_migration_raises():
    with pytest.raises(KeyError):
        runner.run("no_such_migration", dry_run=True)


def test_a_transform_that_raises_aborts_without_partial_writes(seeded):
    @runner.data_migration("explodes")
    class _M:
        table = "trades"

        def select(self, t):
            return None

        def transform(self, record):
            if record["trade_id"] == "M3":
                raise RuntimeError("boom")
            return {"touched": True}
    try:
        with pytest.raises(RuntimeError):
            runner.run("explodes", dry_run=False, batch=1000)
        # One transaction for the batch, so nothing landed.
        assert "touched" not in seeded.get("M0")
    finally:
        runner.REGISTRY.pop("explodes", None)
```

`test_a_transform_that_raises_aborts_without_partial_writes` pins the property
that makes a failed migration recoverable: a half-applied transform over trade
history is far worse than one that did not start.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_data_migration_runner.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Add the ledger table**

Append to `swingbot/core/db/schema.py`:

```python
# Which data migrations have run. Separate from alembic_version because these
# transform VALUES rather than structure -- they are not part of the schema
# graph, they are not ordered relative to it, and a schema downgrade must not
# silently un-record one.
data_migrations = register(
    sa.Table(
        "data_migrations", METADATA,
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("applied_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("rows_changed", sa.BigInteger, nullable=False),
        *standard_columns(),
    ),
    ("name", "applied_at", "rows_changed"),
)
```

Create `swingbot/core/db/migrations/versions/p9_001_data_migrations.py` on the
usual shape, hanging off Part 8's head.

- [ ] **Step 4: Write the runner**

Create `swingbot/core/db/data_migrations/runner.py`:

```python
"""Value-level data migrations.

Rename, drop and promote (Part 8) change what a field is CALLED and where it is
STORED. This is for changing what it CONTAINS -- units, a split, a reshaped
nested structure -- which is the case those three do not cover and the one that
actually recurs.

A migration is a class with `table`, `select(t)` and `transform(record)`:

    @data_migration("stop_pct_to_fraction")
    class StopPctToFraction:
        table = "trades"

        def select(self, t):
            return t.c.doc.has_key("stop_pct")

        def transform(self, record):
            value = record.get("stop_pct")
            return None if value is None else {"stop_fraction": value / 100.0}

`transform` returns the fields to PATCH, or None to skip. Returning a patch
rather than a whole record is what keeps a migration from having to know about
every other field -- and `None` means skip, which is different from "return it
unchanged" because only one of those writes a row.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Callable

import sqlalchemy as sa

from swingbot.core.db.codec import merge_doc, split_doc
from swingbot.core.db.schema import METADATA, data_migrations, promoted_for

log = logging.getLogger("swing-bot.data-migrations")

REGISTRY: dict[str, Any] = {}


def data_migration(name: str) -> Callable:
    def register(cls):
        if name in REGISTRY:
            raise ValueError(f"a data migration named {name!r} already exists")
        REGISTRY[name] = cls()
        return cls
    return register


@dataclass
class Result:
    name: str
    rows_matched: int = 0
    rows_changed: int = 0
    skipped: bool = False


def _engine(profile: str | None):
    from swingbot.core.db import profiles
    return profiles.engine_for(profile)


def applied(*, profile: str | None = None) -> dict[str, dict]:
    with _engine(profile).connect() as conn:
        rows = conn.execute(sa.select(data_migrations)).all()
    return {r._mapping["name"]: dict(r._mapping) for r in rows}


def run(name: str, *, profile: str | None = None, dry_run: bool = True,
        batch: int = 500, force: bool = False) -> Result:
    migration = REGISTRY[name]                 # KeyError on a typo, deliberately
    table = METADATA.tables[migration.table]
    promoted = promoted_for(migration.table)
    result = Result(name=name)

    engine = _engine(profile)

    if not dry_run and not force and name in applied(profile=profile):
        log.info("data migration %r already applied; skipping", name)
        result.skipped = True
        return result

    where = migration.select(table)
    stmt = sa.select(table)
    if where is not None:
        stmt = stmt.where(where)

    with engine.connect() as conn:
        rows = conn.execute(stmt).all()
    result.rows_matched = len(rows)
    log.info("data migration %r: %d row(s) matched", name, result.rows_matched)

    patches: list[tuple[Any, dict]] = []
    for row in rows:
        record = merge_doc(row._mapping, promoted)
        patch = migration.transform(record)
        if patch:
            patches.append((row._mapping["id"], patch))

    if dry_run:
        print(f"[{name}] DRY RUN -- would change {len(patches)} of "
              f"{result.rows_matched} row(s)")
        return result

    # One transaction for the whole run. A half-applied transform over trade
    # history is far worse than one that did not start.
    with engine.begin() as conn:
        for i, (row_id, patch) in enumerate(patches, 1):
            columns, doc_patch = split_doc(patch, promoted)
            values: dict[str, Any] = {**columns, "updated_at": sa.func.now()}
            if doc_patch:
                values["doc"] = table.c.doc.op("||")(
                    sa.cast(sa.literal(doc_patch, sa.JSON),
                            sa.dialects.postgresql.JSONB))
            conn.execute(sa.update(table)
                         .where(table.c.id == row_id).values(**values))
            result.rows_changed += 1
            if i % batch == 0 or i == len(patches):
                print(f"[{name}] {i}/{len(patches)} written", flush=True)

        conn.execute(sa.insert(data_migrations).values(
            name=name,
            applied_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            rows_changed=result.rows_changed,
            doc={"table": migration.table, "matched": result.rows_matched},
        ).on_conflict_do_update(
            index_elements=[data_migrations.c.name],
            set_={"applied_at": sa.func.now(),
                  "rows_changed": result.rows_changed})
            if force else
            sa.insert(data_migrations).values(
                name=name,
                applied_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                rows_changed=result.rows_changed,
                doc={"table": migration.table, "matched": result.rows_matched}))
    return result
```

The conditional `on_conflict_do_update` above is awkward to read — replace it
with a plain `pg_insert(...).on_conflict_do_update(...)` in both cases while
implementing; the ledger row should be upserted either way, and `force` only
governs whether the migration *runs*, not how it is recorded.

Create `scripts/db/migrate_data.py` with `list` and `run <name> [--apply]
[--db-profile]` subcommands, importing every module under
`swingbot/core/db/data_migrations/` so decorators register.

- [ ] **Step 5: Run the tests**

```bash
alembic upgrade head
python scripts/dev/testrun.py file tests/db/test_data_migration_runner.py
python scripts/db/migrate_data.py list
```

Expected: `0 failed`, and an empty migration list (none written yet — that is
the correct state, not a stub).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/data_migrations swingbot/core/db/schema.py \
        swingbot/core/db/migrations/versions/p9_001_data_migrations.py \
        scripts/db/migrate_data.py tests/db/test_data_migration_runner.py
git commit -m "feat(v67): add the value-level data migration runner"
```

---

### Task P9-04: Data migrations are reversible

A transform that cannot be undone is a transform nobody will run on production
data — which makes the runner from P9-03 an ornament.

**Files:**
- Modify: `swingbot/core/db/data_migrations/runner.py`
- Modify: `scripts/db/migrate_data.py`
- Test: `tests/db/test_data_migration_rollback.py`

**Interfaces:**
- Consumes: `run` (P9-03), the `data_migrations` table.
- Produces:
  - `run(..., snapshot: bool = True)` — records each changed row's **prior doc**
    into the ledger row's `doc.before`
  - `rollback(name, *, profile=None, dry_run=True) -> Result`

**The snapshot is the whole doc, not a diff.** A diff would be smaller and would
also require the rollback to reason about how patches compose. Storing the prior
`doc` verbatim makes the undo a straight write, which is the property worth
paying bytes for on an operation that runs once.

**And it has a bound.** Above `SNAPSHOT_MAX_ROWS` the runner refuses unless
`--no-snapshot` is passed explicitly, because silently skipping the snapshot on
a large table is exactly how someone discovers there is no undo.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_data_migration_rollback.py`:

```python
"""A transform that cannot be undone is one nobody will run on real data."""
import pytest

from swingbot.core.db.data_migrations import runner
from swingbot.core.db.repositories.trades import TradeRepository


def _t(trade_id, **over):
    base = dict(trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="open",
                opened_at="2026-01-02T15:00:00+00:00")
    base.update(over)
    return base


@pytest.fixture
def seeded(db_committed):
    repo = TradeRepository()
    with db_committed.begin():
        for i in range(3):
            repo.insert(_t(f"R{i}", stop_pct=1.5 + i, keep="yes"),
                        conn=db_committed)
    yield repo
    import sqlalchemy as sa
    from swingbot.core.db.schema import data_migrations, trades
    with db_committed.begin():
        db_committed.execute(sa.delete(trades))
        db_committed.execute(sa.delete(data_migrations))


@pytest.fixture
def migration():
    @runner.data_migration("to_fraction")
    class _M:
        table = "trades"

        def select(self, t):
            return t.c.doc.has_key("stop_pct")          # noqa: W601

        def transform(self, record):
            return {"stop_fraction": record["stop_pct"] / 100.0,
                    "stop_pct": None}
    yield "to_fraction"
    runner.REGISTRY.pop("to_fraction", None)


def test_the_prior_doc_is_recorded(seeded, migration):
    runner.run(migration, dry_run=False)
    entry = runner.applied()[migration]
    assert "before" in entry["doc"]
    assert len(entry["doc"]["before"]) == 3


def test_rollback_restores_every_changed_record(seeded, migration):
    runner.run(migration, dry_run=False)
    assert seeded.get("R0")["stop_fraction"] == pytest.approx(0.015)
    runner.rollback(migration, dry_run=False)
    got = seeded.get("R0")
    assert got["stop_pct"] == 1.5
    assert "stop_fraction" not in got


def test_rollback_restores_fields_the_transform_nulled(seeded, migration):
    runner.run(migration, dry_run=False)
    runner.rollback(migration, dry_run=False)
    assert seeded.get("R0")["keep"] == "yes"


def test_a_rollback_dry_run_changes_nothing(seeded, migration):
    runner.run(migration, dry_run=False)
    runner.rollback(migration, dry_run=True)
    assert "stop_fraction" in seeded.get("R0")


def test_rollback_clears_the_ledger_entry(seeded, migration):
    runner.run(migration, dry_run=False)
    runner.rollback(migration, dry_run=False)
    assert migration not in runner.applied()


def test_it_can_be_re_run_after_a_rollback(seeded, migration):
    runner.run(migration, dry_run=False)
    runner.rollback(migration, dry_run=False)
    result = runner.run(migration, dry_run=False)
    assert result.skipped is False
    assert result.rows_changed == 3


def test_rolling_back_something_never_applied_raises(migration):
    with pytest.raises(KeyError):
        runner.rollback(migration, dry_run=False)


def test_a_run_without_a_snapshot_refuses_to_roll_back(seeded, migration):
    runner.run(migration, dry_run=False, snapshot=False)
    with pytest.raises(ValueError, match="no snapshot"):
        runner.rollback(migration, dry_run=False)


def test_a_large_table_refuses_to_run_without_an_explicit_choice(
        seeded, migration, monkeypatch):
    """Silently skipping the snapshot on a large table is how someone finds
    out there is no undo."""
    monkeypatch.setattr(runner, "SNAPSHOT_MAX_ROWS", 2)
    with pytest.raises(ValueError, match="snapshot"):
        runner.run(migration, dry_run=False)
    # Explicit is fine.
    assert runner.run(migration, dry_run=False, snapshot=False).rows_changed == 3
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_data_migration_rollback.py -q
```

Expected: `AttributeError: module ... has no attribute 'rollback'`.

- [ ] **Step 3: Add the snapshot and the rollback**

In `runner.py`:

```python
#: Above this, run() refuses unless snapshot=False is passed explicitly. The
#: snapshot is the whole prior doc per changed row, so it is bounded by rows
#: times record size -- fine for a few thousand trades, not for a telemetry
#: table. Refusing beats silently leaving someone with no undo.
SNAPSHOT_MAX_ROWS = 20_000
```

`run()` gains `snapshot: bool = True`, collects `{"id": row_id, "doc": prior}`
for every row it patches, and writes that list into the ledger row's
`doc["before"]`. It raises when `len(patches) > SNAPSHOT_MAX_ROWS and snapshot`.

```python
def rollback(name: str, *, profile: str | None = None,
             dry_run: bool = True) -> Result:
    """Restore every record this migration changed, from its recorded prior doc.

    The snapshot is the whole prior doc rather than a diff. A diff would be
    smaller and would also make the undo reason about how patches compose;
    a straight write is the property worth paying bytes for on an operation
    that runs once.
    """
    entry = applied(profile=profile)[name]        # KeyError if never applied
    before = (entry.get("doc") or {}).get("before")
    if before is None:
        raise ValueError(
            f"data migration {name!r} was run with no snapshot, so there is "
            f"nothing to restore from. Restore from a pg_dump instead "
            f"(scripts/ops/restore_db.sh).")

    table = METADATA.tables[entry["doc"]["table"]]
    result = Result(name=name, rows_matched=len(before))
    if dry_run:
        print(f"[{name}] DRY RUN -- would restore {len(before)} row(s)")
        return result

    with _engine(profile).begin() as conn:
        for i, snap in enumerate(before, 1):
            conn.execute(sa.update(table)
                         .where(table.c.id == snap["id"])
                         .values(doc=snap["doc"], updated_at=sa.func.now()))
            result.rows_changed += 1
            if i % 500 == 0 or i == len(before):
                print(f"[{name}] restored {i}/{len(before)}", flush=True)
        conn.execute(sa.delete(data_migrations)
                     .where(data_migrations.c.name == name))
    return result
```

Note the rollback restores `doc` **wholesale**, which also undoes promoted-column
changes only if the transform touched doc alone. A transform that writes a
promoted column must record those too — add that to the snapshot as
`{"id", "doc", "columns"}` and restore both. Write the test for it before the
code.

Add `rollback <name> [--apply]` to `scripts/db/migrate_data.py`.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_data_migration_rollback.py
python scripts/dev/testrun.py file tests/db/test_data_migration_runner.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/data_migrations/runner.py scripts/db/migrate_data.py \
        tests/db/test_data_migration_rollback.py
git commit -m "feat(v67): make data migrations reversible"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_9b-data-migrations.md`**
(P9-05…P9-08): a reversible field drop, the end-to-end round-trip walk, the
workflow documentation, and Part 9's verification.
