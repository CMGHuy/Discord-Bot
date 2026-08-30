# v67 — Part 9: Round trip and reversibility (tasks P9-05…P9-08)

> Continuation of `2026-08-29-v67-json-to-postgres_9a-round-trip.md`. Part of
> `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's Global
> Constraints and the `_9a` file before starting any task here** — the
> allowlist table, the Alembic revision-id table and the exit criteria live
> there and are not repeated.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

---

### Task P9-05: A field drop that can be undone

`edit_field.py drop` (P8-03) removes a doc key from every record with no
snapshot. That is fine for a field added an hour ago and wrong for one that has
been accumulating values for months — and the tool cannot tell the difference.

**Files:**
- Modify: `scripts/db/edit_field.py`
- Test: `tests/scripts/test_edit_field_reversible.py`

**Interfaces:**
- Consumes: the `data_migrations` ledger (P9-03), `rollback` (P9-04).
- Produces:
  - `drop_field(table, field, *, dry_run=False, snapshot=True) -> int` — records
    the prior values before removing them
  - `restore_field(table, field) -> int` — puts them back

**Why this reuses the data-migration ledger rather than inventing a second
one.** A drop *is* a value-level change with an undo; giving it its own storage
would mean two places to look when someone asks "what happened to this field",
and they would drift. The ledger entry is named `drop:<table>.<field>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_edit_field_reversible.py`:

```python
"""Dropping a doc field records what it removed."""
import pytest
import sqlalchemy as sa

from scripts.db.edit_field import drop_field, restore_field
from swingbot.core.db.data_migrations import runner
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import data_migrations, trades


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
        repo.insert(_t("D1", doomed="a", keep="yes"), conn=db_committed)
        repo.insert(_t("D2", doomed="b", keep="yes"), conn=db_committed)
        repo.insert(_t("D3", keep="yes"), conn=db_committed)
    yield repo
    with db_committed.begin():
        db_committed.execute(sa.delete(trades))
        db_committed.execute(sa.delete(data_migrations))


def test_drop_removes_the_field(seeded):
    assert drop_field("trades", "doomed") == 2
    assert "doomed" not in seeded.get("D1")


def test_drop_records_what_it_removed(seeded):
    drop_field("trades", "doomed")
    entry = runner.applied()["drop:trades.doomed"]
    assert len(entry["doc"]["before"]) == 2


def test_restore_puts_the_values_back(seeded):
    drop_field("trades", "doomed")
    assert restore_field("trades", "doomed") == 2
    assert seeded.get("D1")["doomed"] == "a"
    assert seeded.get("D2")["doomed"] == "b"


def test_restore_does_not_disturb_other_fields(seeded):
    drop_field("trades", "doomed")
    restore_field("trades", "doomed")
    assert seeded.get("D1")["keep"] == "yes"


def test_restore_does_not_invent_the_field_on_records_that_lacked_it(seeded):
    drop_field("trades", "doomed")
    restore_field("trades", "doomed")
    assert "doomed" not in seeded.get("D3")


def test_a_dry_run_records_nothing(seeded):
    drop_field("trades", "doomed", dry_run=True)
    assert "drop:trades.doomed" not in runner.applied()


def test_dropping_without_a_snapshot_is_possible_but_explicit(seeded):
    drop_field("trades", "doomed", snapshot=False)
    assert "drop:trades.doomed" not in runner.applied()
    with pytest.raises(KeyError):
        restore_field("trades", "doomed")


def test_restoring_something_never_dropped_raises(seeded):
    with pytest.raises(KeyError):
        restore_field("trades", "never_existed")


def test_dropping_twice_does_not_lose_the_first_snapshot(seeded):
    drop_field("trades", "doomed")
    drop_field("trades", "doomed")          # second is a no-op, 0 rows
    assert len(runner.applied()["drop:trades.doomed"]["doc"]["before"]) == 2
```

`test_dropping_twice_does_not_lose_the_first_snapshot` is the one that would
otherwise bite: a second drop matches nothing, and a naive implementation would
overwrite the ledger entry with an empty snapshot and quietly destroy the undo.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_edit_field_reversible.py -q
```

Expected: `ImportError: cannot import name 'restore_field'`.

- [ ] **Step 3: Snapshot before dropping**

In `scripts/db/edit_field.py`:

```python
def _ledger_name(table: str, field: str) -> str:
    return f"drop:{table}.{field}"


def drop_field(table: str, field: str, *, dry_run: bool = False,
               snapshot: bool = True) -> int:
    """Remove a doc field from every record carrying it.

    Records the prior values into the data_migrations ledger first, so
    restore_field() can put them back. That reuses the ledger rather than
    inventing a second store: a drop IS a value-level change with an undo, and
    two places to look for "what happened to this field" would drift.
    """
    _check(table, field)
    engine = _engine()
    with engine.begin() as conn:
        rows = conn.execute(sa.text(
            f"SELECT id, doc -> :f AS value FROM {table} WHERE doc ? :f"),
            {"f": field}).all()
        affected = len(rows)
        if dry_run or not affected:
            return affected

        if snapshot:
            # on_conflict_do_nothing, NOT do_update: a second drop matches
            # nothing, and overwriting the entry with an empty snapshot would
            # quietly destroy the undo the first drop recorded.
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            from swingbot.core.db.schema import data_migrations
            conn.execute(pg_insert(data_migrations).values(
                name=_ledger_name(table, field),
                applied_at=sa.func.now(),
                rows_changed=affected,
                doc={"table": table, "field": field,
                     "before": [{"id": r.id, "value": r.value} for r in rows]},
            ).on_conflict_do_nothing(index_elements=[data_migrations.c.name]))

        conn.execute(sa.text(
            f"UPDATE {table} SET doc = doc - :f WHERE doc ? :f"), {"f": field})
    return affected


def restore_field(table: str, field: str) -> int:
    """Put back what drop_field removed."""
    from swingbot.core.db.data_migrations import runner

    entry = runner.applied()[_ledger_name(table, field)]     # KeyError if none
    before = entry["doc"]["before"]
    engine = _engine()
    with engine.begin() as conn:
        for snap in before:
            conn.execute(sa.text(f"""
                UPDATE {table}
                   SET doc = doc || jsonb_build_object(:f, CAST(:v AS jsonb)),
                       updated_at = now()
                 WHERE id = :id
            """), {"f": field, "v": json.dumps(snap["value"]), "id": snap["id"]})
        conn.execute(sa.text(
            "DELETE FROM data_migrations WHERE name = :n"),
            {"n": _ledger_name(table, field)})
    return len(before)
```

Add `restore <table> <field>` to the CLI, and `import json` at the top.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_edit_field_reversible.py
python scripts/dev/testrun.py file tests/scripts/test_edit_field.py
```

Expected: `0 failed` for both. P8-03's tests must still pass unchanged — the
snapshot is additive.

- [ ] **Step 5: Update the recipe**

In `docs/claude/schema-evolution.md`'s **drop** section: the drop is recorded
and `restore` puts it back, `--no-snapshot` opts out for a field you are certain
about, and a drop older than the ledger entry's lifetime is a `pg_dump` restore
rather than a `restore_field`.

- [ ] **Step 6: Commit**

```bash
git add scripts/db/edit_field.py docs/claude/schema-evolution.md \
        tests/scripts/test_edit_field_reversible.py
git commit -m "feat(v67): make a doc-field drop reversible"
```

---

### Task P9-06: Walk the round trip end to end

Every piece exists; nothing has run them in sequence against real data. This is
the task that finds the step somebody forgot.

**Files:**
- Create: `docs/deploy/DB_ROUND_TRIP.md`
- Test: `tests/scripts/test_round_trip_smoke.py`

**Interfaces:**
- Consumes: everything in Parts 7 and 9.
- Produces: the walk's record, with real numbers.

**The automated half is a smoke test against two local databases.** It cannot
reach production, so it proves the *mechanics* — pull-shaped restore, compute,
push-shaped upsert, verify — while Step 3 proves the real thing by hand.

- [ ] **Step 1: Write the smoke test**

Create `tests/scripts/test_round_trip_smoke.py`:

```python
"""The round trip's mechanics, between two local databases.

It cannot reach production, so what it proves is that pull-shaped restore,
local compute and push-shaped upsert compose. The real walk is by hand, in
Step 3, and its record is docs/deploy/DB_ROUND_TRIP.md.
"""
import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db import profiles
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.db.schema import fold_trades, trades


@pytest.fixture
def two_databases(monkeypatch, db_engine, db_committed):
    """`local` and `snapshot` both pointing at the test database is enough:
    what is being tested is that the tools read one profile and write the
    other, not that they are physically separate."""
    url = db_engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(config, "DATABASE_URL", url)
    monkeypatch.setattr(config, "DATABASE_URL_SNAPSHOT", url)
    profiles.reset_engines()
    with db_committed.begin():
        repo = TradeRepository()
        for i in range(8):
            win = i % 3 != 0
            repo.insert(dict(
                trade_id=f"RT{i}", ticker="AAPL", strategy="RSI",
                horizon="2w", direction="bullish",
                status="win" if win else "loss",
                opened_at=f"2026-01-{i + 1:02d}T15:00:00+00:00",
                closed_at=f"2026-02-{i + 1:02d}T15:00:00+00:00",
                r_multiple=2.0 if win else -1.0), conn=db_committed)
    yield
    with db_committed.begin():
        db_committed.execute(sa.delete(trades))
        db_committed.execute(sa.delete(fold_trades))
    profiles.reset_engines()


def test_step_1_the_snapshot_is_readable_as_a_frame(two_databases):
    from swingbot.core.db import datasets
    df = datasets.closed_trades_frame(profile="snapshot")
    assert len(df) == 8
    assert "r_multiple" in df.columns


def test_step_2_a_local_computation_produces_an_artifact(two_databases):
    """The 'training' step, standing in for a grid run."""
    from swingbot.core.db import datasets
    df = datasets.closed_trades_frame(profile="snapshot")
    by_strategy = df.groupby("strategy")["r_multiple"].mean().to_dict()
    assert by_strategy["RSI"] == pytest.approx((2.0 * 5 + -1.0 * 3) / 8)


def test_step_3_the_artifact_is_pushable(two_databases, db_committed):
    from swingbot.core.db.repositories.fold_trades import FoldTradesRepository
    with db_committed.begin():
        FoldTradesRepository().put(
            "RSI", {"outcomes": [{"r": 2.0}, {"r": -1.0}]}, conn=db_committed)
    from scripts.ops.push_prod_artifacts import push
    assert push(["fold_trades"], dry_run=True, source="snapshot") == {
        "fold_trades": 1}


def test_step_4_trading_state_is_refused_at_every_step(two_databases):
    from scripts.ops.push_prod_artifacts import RefusedPush, push
    for table in ("trades", "plans", "account"):
        with pytest.raises(RefusedPush):
            push([table], dry_run=True, source="snapshot")


def test_the_round_trip_is_documented():
    import pathlib
    doc = (pathlib.Path(__file__).resolve().parents[2]
           / "docs" / "deploy" / "DB_ROUND_TRIP.md")
    assert doc.exists()
    text = doc.read_text(encoding="utf-8")
    for needle in ("db-pull", "db-push", "--apply", "rollback"):
        assert needle in text, needle
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/scripts/test_round_trip_smoke.py
```

Expected: all pass except `test_the_round_trip_is_documented`, which fails until
Step 4.

- [ ] **Step 3: Walk it for real — TOUCHES PRODUCTION**

```bash
# 1. pull
make db-pull

# 2. look at what came back
python scripts/db/query.py --profile snapshot \
  "select status, count(*) from trades group by status"

# 3. compute something locally
python -c "
from swingbot.core.db import datasets
df = datasets.closed_trades_frame(profile='snapshot')
print(df.groupby('strategy')['r_multiple'].agg(['count','mean']))
"

# 4. dry-run the push, read it, then apply
python scripts/ops/push_prod_artifacts.py fold_trades --source snapshot
python scripts/ops/push_prod_artifacts.py fold_trades --source snapshot --apply

# 5. confirm production actually has it
make db-tunnel        # in another terminal
python scripts/db/query.py --profile prod-ro "select strategy from fold_trades"
```

**Compare step 3's per-strategy table against `!performance` on the live bot.**
If they disagree, stop — the accessors and the application's own aggregation
disagree about the same data, and that is worth more attention than finishing
this task.

- [ ] **Step 4: Record it**

Create `docs/deploy/DB_ROUND_TRIP.md`: the five commands above with their real
output, the timing of each (a pull of production's history is the slow step and
people should know roughly how slow), anything that did not work first time, and
the rollback path — `restore_db.sh` for the whole database,
`migrate_data.py rollback` for a transform, `edit_field.py restore` for a drop.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy/DB_ROUND_TRIP.md tests/scripts/test_round_trip_smoke.py
git commit -m "docs(v67): walk and record the pull -> train -> push round trip"
```

---

### Task P9-07: One page for the whole workflow

Six documents now describe pieces of this. Someone with a question has to know
which one to open, and they will not.

**Files:**
- Modify: `docs/deploy/DB_LOCAL_DEV.md` (becomes the entry point)
- Modify: `docs/claude/schema-evolution.md`
- Modify: `README.md`, `CLAUDE.md`
- Test: extend `tests/test_docs_consistency.py`

**Interfaces:**
- Consumes: everything in Parts 7, 8 and 9.
- Produces: nothing in code.

**Structure it by the question, not by the tool.** A reader arrives with "how do
I train on real data", not with "tell me about profiles".

- [ ] **Step 1: Extend the consistency test**

Add to `tests/test_docs_consistency.py`:

```python
ROUND_TRIP_QUESTIONS = [
    "train on real data",
    "publish",
    "change a field",
    "roll",
]


def test_the_local_dev_guide_answers_each_question():
    text = (REPO / "docs/deploy/DB_LOCAL_DEV.md").read_text(encoding="utf-8").lower()
    for question in ROUND_TRIP_QUESTIONS:
        assert question in text, f"no section answering {question!r}"


def test_every_reversal_path_is_named_somewhere():
    text = "\n".join(
        (REPO / d).read_text(encoding="utf-8")
        for d in ("docs/deploy/DB_LOCAL_DEV.md",
                  "docs/deploy/DB_ROUND_TRIP.md",
                  "docs/claude/schema-evolution.md"))
    for tool in ("restore_db.sh", "migrate_data.py rollback",
                 "edit_field.py restore", "alembic downgrade"):
        assert tool in text, f"{tool} is not documented as a reversal path"


def test_claude_md_is_still_within_budget():
    lines = (REPO / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200, f"CLAUDE.md is {len(lines)} lines"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_docs_consistency.py -q
```

Expected: the two new tests fail.

- [ ] **Step 3: Restructure the guide**

Rewrite `docs/deploy/DB_LOCAL_DEV.md` around four questions:

```markdown
# Working with real data

## "I want to train on real data"

    make db-pull
    python -c "
    from swingbot.core.db import datasets
    df = datasets.closed_trades_frame(profile='snapshot')
    "

## "I computed something locally and production needs it"

    python scripts/ops/push_prod_artifacts.py tuning_results --source snapshot
    python scripts/ops/push_prod_artifacts.py tuning_results --source snapshot --apply

Only `tuning_results`, `tuning_proposals` and `fold_trades` can be pushed.
Everything else is refused with the reason -- trading state belongs to
production and a push would overwrite real history with a stale copy.

## "I need to change a field"

See `docs/claude/schema-evolution.md`. Add costs nothing; rename and drop are
one command; promote is a generated migration and no call-site change.

## "I need to roll something back"

| What went wrong | Undo |
|---|---|
| a schema revision | `alembic downgrade <rev>` — proven by `make db-check-downgrade` |
| a data transform | `python scripts/db/migrate_data.py rollback <name> --apply` |
| a dropped field | `python scripts/db/edit_field.py restore <table> <field>` |
| a promotion | remove the name from `PROMOTED`; the doc copy was never stripped |
| anything else | `scripts/ops/restore_db.sh <dump> <target>` |
```

Then keep the reference sections — the three profiles, the `.env` variables,
troubleshooting — below the questions rather than above them.

`CLAUDE.md` gets **one** line, and it displaces something into
`docs/claude/architecture.md`:

```bash
make db-pull                  # prod -> local snapshot; then --profile snapshot
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/test_docs_consistency.py
wc -l CLAUDE.md
```

Expected: `0 failed`, `CLAUDE.md` at 200 or fewer.

- [ ] **Step 5: Commit**

```bash
git add docs/deploy/DB_LOCAL_DEV.md docs/claude/schema-evolution.md \
        docs/claude/architecture.md README.md CLAUDE.md \
        tests/test_docs_consistency.py
git commit -m "docs(v67): one page for train, publish, change and roll back"
```

---

### Task P9-08: Part 9 verification

**Files:**
- Create: `tests/db/test_part9_exit.py`

**Interfaces:**
- Consumes: everything in Part 9.
- Produces: nothing.

- [ ] **Step 1: Write the exit test**

Create `tests/db/test_part9_exit.py`:

```python
"""Checks that only make sense once every Part 9 task has landed."""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_no_trading_state_table_is_pushable():
    """The single most important property in this part."""
    from scripts.ops.push_prod_artifacts import PUSHABLE, REFUSED
    trading_state = {"trades", "plans", "starred_plans", "account",
                     "account_balance_history", "journal_entries",
                     "signal_state", "watchlist"}
    assert not (trading_state & set(PUSHABLE))
    # And every one of them is refused BY NAME, so a new table is a visible gap
    # rather than a silent fall-through.
    for table in ("trades", "plans", "account", "watchlist"):
        assert table in REFUSED


def test_every_schema_table_is_either_pushable_or_refused():
    from scripts.ops.push_prod_artifacts import PUSHABLE, REFUSED
    from swingbot.core.db.schema import METADATA
    known = set(PUSHABLE) | set(REFUSED)
    # data_migrations is the ledger; it is neither pushed nor pulled.
    unclassified = set(METADATA.tables) - known - {"data_migrations"}
    assert not unclassified, (
        f"tables the push tool has no opinion about: {sorted(unclassified)}. "
        f"Add each to PUSHABLE or REFUSED with its reason.")


def test_every_reversal_has_a_tool():
    assert (REPO / "scripts/ops/restore_db.sh").exists()
    assert (REPO / "scripts/db/migrate_data.py").exists()
    from scripts.db.edit_field import restore_field
    from swingbot.core.db.data_migrations.runner import rollback
    assert callable(restore_field) and callable(rollback)


def test_the_downgrade_check_is_a_named_command():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "db-check-downgrade:" in makefile


@pytest.mark.parametrize("target", ["db-pull:", "db-push:", "db-tunnel:",
                                    "db-query:", "db-export:",
                                    "db-check-downgrade:"])
def test_the_makefile_exposes_the_whole_workflow(target):
    assert target in (REPO / "Makefile").read_text(encoding="utf-8")


def test_the_push_tool_is_the_only_writer_to_production():
    """Nothing else may resolve a production write URL."""
    hits = []
    for path in (REPO / "swingbot").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "prod-write" in text or "DATABASE_URL_PROD_WRITE" in text:
            hits.append(path.relative_to(REPO).as_posix())
    assert hits == ["swingbot/core/db/profiles.py"], hits


def test_prod_write_is_not_a_selectable_profile():
    """No --profile flag may select a write connection to production."""
    from swingbot.core.db import profiles
    assert "prod-write" not in profiles.PROFILES
```

`test_every_schema_table_is_either_pushable_or_refused` is the maintenance
guard: the next table someone adds fails this until they decide, in writing,
whether it may travel.

- [ ] **Step 2: Run everything Part 9 touched**

```bash
python scripts/dev/testrun.py file tests/db/test_part9_exit.py
python scripts/dev/testrun.py fast
python -m pytest tests/db/ tests/scripts/ -q
make db-check-downgrade
```

Expected: `0 failed`, `0 xfailed` on all four. The third covers the `slow`
reversibility walk the fast tier skips.

- [ ] **Step 3: Commit**

```bash
git add tests/db/test_part9_exit.py
git commit -m "test(v67): pin Part 9 exit criteria"
```

---

## Part 9 exit criteria

Repeated from `_9a` so this file closes on its own terms:

1. A locally-computed artifact reaches production with one command, against an
   allowlist that makes pushing trading state impossible rather than
   discouraged.
2. Every Alembic revision goes up, down and up again on a real database.
3. A value-level data migration is named, versioned, idempotent, dry-runnable
   and undoable.
4. `edit_field.py drop` cannot lose data irrecoverably.
5. The pull → train → push round trip has been walked end-to-end and recorded
   with real numbers.
6. `python scripts/dev/testrun.py fast` is green.

## What Part 9 does not do

1. **No bidirectional sync.** The push is one-way and allowlisted; there is no
   merge, no conflict resolution and no "make these two databases the same".
   Production is the source of truth for trading state and local is the source
   of truth for nothing — a sync would need an answer to "which side wins" that
   this domain does not have.
2. **No scheduled push.** Publishing a tuning result is a decision someone
   makes after reading it, which is why `--apply` is opt-in and there is no
   cron entry.
3. **No cross-version data migration.** `migrate_data.py` transforms values
   under the current schema. A change needing both a structural migration and a
   value transform is two steps, in that order, and the recipe says so.
