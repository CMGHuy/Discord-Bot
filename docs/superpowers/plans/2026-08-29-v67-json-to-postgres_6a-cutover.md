# v67 — Part 6: Cutover (tasks P6-01…P6-06)

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** Tasks P6-07…P6-12 are in
> `2026-08-29-v67-json-to-postgres_6b-cleanup.md`.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`
(sections 8 and 9).

Parts 2–5 built every store's Postgres path and left every store on `json`.
This part runs the migration for real: one revision graph, backups that have
actually been restored from, the production import on irreplaceable data, and
then the deletion of everything the `json` stage needed.

**Read this before touching production.** Local `data/` has no `trades.json` or
`plans.json`. The only real history lives on the Hetzner VM
(`167.233.26.185`, `docs/deploy/DEPLOY_HETZNER.md`), and there is no second
copy. Every task here that touches the VM says so in its title, takes a tarball
first, and runs a dry run before a real one.

## Alembic revision ids

Part 6 owns `p6_*` and is the only part that may create a **merge** revision.

| Revision | Content |
|---|---|
| `p6_000` | merge revision joining every part's head |
| `p6_001` | the complete NOTIFY trigger sweep, unconditional |
| `p6_002` | drop nothing — reserved; see P6-08's note on why tables are not dropped |

## Parallelisation

**Sequential throughout, and this is not a preference.** Part 6 is a cutover:
each task's precondition is the previous task's outcome. Backups before the
import, the import before the stage flip, the flip before the dead-path
deletion, the deletion before the final suite run.

**Part 6 begins only after Parts 2–5 are all merged to `main`.** Verify, do not
assume:

```bash
git fetch && git log --oneline origin/main | head -40
grep -rn "^### Task P[2-5]-" docs/superpowers/plans/ | wc -l   # expect 74
```

## Part 6 exit criteria

1. `alembic heads` returns exactly one head.
2. Every table that maps to an SSE concern has a NOTIFY trigger.
3. A `pg_dump` has been restored into an empty database and verified — once,
   for real, not described.
4. Production data is imported with equal row counts and equal per-record
   checksums.
5. Every store runs at `db` in production; no code path reads a migrated JSON
   file.
6. `python scripts/dev/testrun.py full` is green — `0 failed`, `0 xfailed`.
7. `VERSION.json` is bumped and `version_history.json` regenerated in the same
   commit.

---

# Phase 6 — Cutover

### Task P6-01: One revision graph

Parts 2–5 each hung off `p1_003`, so `alembic heads` now returns four. This is
the expected outcome of the parallel design, and a merge revision is the only
correct resolution — **never** edit a `down_revision` that has already run.

**Files:**
- Create: `swingbot/core/db/migrations/versions/p6_000_merge.py`
- Modify: `tests/db/test_migrations.py` (tighten the head assertion)

**Interfaces:**
- Consumes: every part's head revision.
- Produces: revision `p6_000`, the single head.

- [ ] **Step 1: Find the heads**

```bash
alembic heads
```

Expected: four ids — `p2_006`, `p3_007`, `p4_001`, `p5_004`. If any is missing,
that part is not merged; stop and check `git log origin/main` before going
further.

- [ ] **Step 2: Write the failing test**

`tests/db/test_migrations.py` already asserts one head (P1-05). It is currently
**failing** — which is correct and expected. Confirm:

```bash
python -m pytest tests/db/test_migrations.py::test_exactly_one_head -q
```

Expected: FAIL, naming the four heads. Add one more test beside it:

```python
def test_the_merge_revision_names_every_part(scripts):
    """A merge that forgot a part would silently drop that part's tables from
    a fresh `alembic upgrade head`."""
    merge = scripts.get_revision("p6_000")
    downs = set(merge.down_revision or ())
    assert downs == {"p2_006", "p3_007", "p4_001", "p5_004"}, downs
```

- [ ] **Step 3: Create the merge revision**

```bash
alembic merge -m "merge parts 2-5" --rev-id p6_000 p2_006 p3_007 p4_001 p5_004
```

Open the generated file and confirm it has an empty `upgrade()`/`downgrade()`
and a tuple `down_revision`. Replace its docstring with:

```python
"""merge parts 2-5 into one head

Revision ID: p6_000
Revises: p2_006, p3_007, p4_001, p5_004

Parts 2-5 ran concurrently, each hanging its chain off p1_003, so four heads
is the designed outcome rather than an accident. This joins them. It applies
no DDL: every table already exists by the time this runs.

Never resolve a branch by editing a down_revision that has already run
somewhere -- a database that applied the old value has no way back.
"""
```

- [ ] **Step 4: Verify on a virgin database**

The point of a merge revision is that a fresh database builds the whole schema
in one pass. Test that, not just the current one:

```bash
docker compose --profile test up -d db-test
TEST_DATABASE_URL=postgresql+psycopg://swingbot:swingbot@localhost:55432/swingbot_test \
  docker compose exec db-test psql -U swingbot -d swingbot_test \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
DATABASE_URL=postgresql+psycopg://swingbot:swingbot@localhost:55432/swingbot_test \
  alembic upgrade head
DATABASE_URL=postgresql+psycopg://swingbot:swingbot@localhost:55432/swingbot_test \
  alembic heads
```

Expected: `p6_000 (head)`, and every table present.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_migrations.py
```

Expected: `0 failed`, including `test_exactly_one_head`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/migrations/versions/p6_000_merge.py \
        tests/db/test_migrations.py
git commit -m "feat(v67): merge the four migration heads"
```

---

### Task P6-02: The complete trigger sweep

Parts 3 and 5 installed triggers **conditionally**, skipping tables another part
had not created yet. Now every table exists, so the sweep runs unconditionally
and the coverage test becomes a real gate rather than a check against a partial
map.

**Files:**
- Create: `swingbot/core/db/migrations/versions/p6_001_trigger_sweep.py`
- Modify: `tests/db/test_trigger_coverage.py`

**Interfaces:**
- Consumes: `TABLE_CHANNELS` (P3-18), `trigger_ddl` (P1-12), `p6_000` (P6-01).
- Produces: revision `p6_001`.

- [ ] **Step 1: Tighten the coverage test**

In `tests/db/test_trigger_coverage.py`, replace the conditional table check with
an unconditional one and add:

```python
def test_the_sweep_is_no_longer_conditional(db_conn):
    """P3-007 and P5-004 skipped tables another part had not created. After
    p6_001 there is no such thing as a table this map names but the database
    lacks."""
    import sqlalchemy as sa
    from swingbot.core.db import events, notify

    installed = {row[0] for row in db_conn.execute(sa.text(
        "select tgname from pg_trigger where not tgisinternal"))}
    missing = {t for t in events.TABLE_CHANNELS
               if notify.trigger_name(t) not in installed}
    assert not missing, (
        f"tables with no NOTIFY trigger after the sweep: {sorted(missing)}")


def test_no_table_has_two_notify_triggers(db_conn):
    """The sweep drops before it creates. A duplicate would double every
    event, which the debounce hides until it does not."""
    import sqlalchemy as sa
    rows = db_conn.execute(sa.text(
        "select tgrelid::regclass::text, count(*) from pg_trigger "
        "where not tgisinternal and tgname like '%_notify_trg' "
        "group by 1 having count(*) > 1")).all()
    assert rows == [], f"duplicate notify triggers: {rows}"
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_trigger_coverage.py -q
```

Expected: `test_the_sweep_is_no_longer_conditional` fails if any part's
conditional sweep skipped a table.

- [ ] **Step 3: Write the revision**

Create `swingbot/core/db/migrations/versions/p6_001_trigger_sweep.py`:

```python
"""install every NOTIFY trigger, unconditionally

Revision ID: p6_001
Revises: p6_000

p3_007 and p5_004 skipped tables another part had not created yet, because
Parts 2-5 could land in any order. Every table exists now, so this sweep is
unconditional -- and DROP-then-CREATE per table, so re-running it is safe and
a table can never end up with two triggers doubling its events.
"""
from alembic import op

from swingbot.core.db.events import TABLE_CHANNELS
from swingbot.core.db.notify import (NOTIFY_FUNCTION_SQL, trigger_ddl,
                                     trigger_name)

revision = "p6_001"
down_revision = "p6_000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(NOTIFY_FUNCTION_SQL)
    for table, channel in sorted(TABLE_CHANNELS.items()):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {table}")
        op.execute(trigger_ddl(table, channel))


def downgrade() -> None:
    for table in sorted(TABLE_CHANNELS):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name(table)} ON {table}")
```

This revision imports `TABLE_CHANNELS` from application code, which every other
migration in this plan deliberately avoids. The reason it is acceptable here and
nowhere else: this revision's *job* is "make the database match the current map",
so it is correct for it to drift with the map. A `create_table` revision must
never do that, because its job is "make the database match what the map said
**then**".

- [ ] **Step 4: Migrate and verify**

```bash
alembic upgrade head
docker compose exec db psql -U swingbot -d swingbot -c \
  "select tgrelid::regclass, tgname from pg_trigger where not tgisinternal order by 1"
python scripts/dev/testrun.py file tests/db/test_trigger_coverage.py
```

Expected: one `*_notify_trg` per mapped table, and `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/db/migrations/versions/p6_001_trigger_sweep.py \
        tests/db/test_trigger_coverage.py
git commit -m "feat(v67): sweep every NOTIFY trigger into place"
```

---

### Task P6-03: Nightly backups

A `pg_dump` into `./data/backups/db/`, beside the existing `data/backups/env/`,
keeping **14 days** — enough for a bad change to survive a week unnoticed
without unbounded disk growth.

**Files:**
- Create: `scripts/ops/backup_db.sh`
- Modify: `docker-compose.yml` (mount `./data/backups` into the db service)
- Modify: `Makefile` (a `backup-db` target)
- Modify: `docs/deploy/DEPLOY_HETZNER.md`
- Test: `tests/scripts/test_backup_db.py`

**Interfaces:**
- Consumes: the `db` service (P1-03).
- Produces:
  - `scripts/ops/backup_db.sh` — one timestamped dump plus retention pruning
  - `make backup-db`

**Why a shell script and not Python.** `pg_dump` lives inside the db container
and the natural invocation is `docker compose exec`. A Python wrapper would add
a layer whose only job is to build that command string, and the thing that has
to work at 3am is the command, not the wrapper.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_backup_db.py`:

```python
"""The backup script's shape. It cannot be executed in CI, so what is
asserted is the properties a broken edit would remove."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backup_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/backup_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    """A dump script that continues after a failed pg_dump writes a truncated
    file over a good one and reports success."""
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_it_dumps_with_a_timestamped_name(source):
    assert "pg_dump" in source
    assert "%Y" in source or "date " in source


def test_it_writes_into_the_backups_directory(source):
    assert "data/backups/db" in source


def test_it_prunes_by_age_not_by_count(source):
    """14 DAYS, not 14 files: a day with three manual dumps must not evict
    two weeks of nightly ones."""
    assert "-mtime" in source or "--older-than" in source
    assert "14" in source


def test_it_verifies_the_dump_is_non_empty_before_pruning(source):
    """Prune-then-dump, or prune without checking, is how a bad night deletes
    the last good backup."""
    dump_at = source.index("pg_dump")
    prune_at = source.rindex("-mtime") if "-mtime" in source else len(source)
    assert dump_at < prune_at, "pruning must come after a verified dump"
    assert "-s " in source or "wc -c" in source or "test -s" in source


def test_the_makefile_exposes_it():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "backup-db:" in makefile


def test_the_compose_file_mounts_the_backup_directory():
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load(
        (REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    mounts = compose["services"]["db"].get("volumes") or []
    assert any("backups" in str(m) for m in mounts)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_backup_db.py -q
```

Expected: every test fails on the missing script.

- [ ] **Step 3: Write the script**

Create `scripts/ops/backup_db.sh`:

```bash
#!/usr/bin/env bash
# Nightly Postgres backup: one timestamped dump into data/backups/db/,
# pruning anything older than 14 days.
#
# 14 days, by age and not by count: it covers a bad change surviving a week
# unnoticed, and a day with three manual dumps must not evict two weeks of
# nightly ones. Disk cost is bounded by the database's own size, which for
# this repo's write volume is measured in megabytes.
#
# Restore is documented in docs/deploy/DEPLOY_HETZNER.md and has been
# exercised once, on a throwaway database -- an unexercised restore is a hope,
# not a backup.
set -euo pipefail

cd "$(dirname "$0")/../.."

BACKUP_DIR="data/backups/db"
STAMP="$(date -u +%Y-%m-%d_%H-%M-%S)"
OUT="${BACKUP_DIR}/swingbot_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

# --clean --if-exists so the dump can be replayed into a database that still
# has objects; -Fp (plain) so it is greppable and restorable with psql alone,
# with no dependency on a matching pg_restore version.
docker compose exec -T db \
  pg_dump -U swingbot -d swingbot --clean --if-exists -Fp \
  | gzip -9 > "$OUT"

# A failed dump under `set -o pipefail` already aborted above, but an empty
# file is the failure mode that would otherwise pass silently -- and pruning
# after an empty dump is how the last good backup gets deleted.
if [ ! -s "$OUT" ]; then
  echo "backup_db: dump is empty, refusing to prune: $OUT" >&2
  exit 1
fi

echo "backup_db: wrote $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_DIR" -name 'swingbot_*.sql.gz' -type f -mtime +14 -print -delete
```

```bash
chmod +x scripts/ops/backup_db.sh
```

- [ ] **Step 4: Wire it up**

In `docker-compose.yml`, add to the `db` service:

```yaml
      # The dump lands here, on the host, beside data/backups/env/. A backup
      # that lives only inside the container's volume is not a backup.
      - ./data/backups:/backups
```

In the `Makefile`:

```make
backup-db:
	./scripts/ops/backup_db.sh
```

and add `backup-db` to the `.PHONY` line.

In `docs/deploy/DEPLOY_HETZNER.md`, document the cron entry:

```
0 3 * * *  cd /srv/swing-bot && ./scripts/ops/backup_db.sh >> logs/backup.log 2>&1
```

- [ ] **Step 5: Run it for real, locally**

```bash
./scripts/ops/backup_db.sh
ls -la data/backups/db/
gunzip -c data/backups/db/*.sql.gz | head -20
```

Expected: a non-empty `.sql.gz`, whose first lines are Postgres dump headers.

- [ ] **Step 6: Run the tests and commit**

```bash
python scripts/dev/testrun.py file tests/scripts/test_backup_db.py
git add scripts/ops/backup_db.sh docker-compose.yml Makefile \
        docs/deploy/DEPLOY_HETZNER.md tests/scripts/test_backup_db.py
git commit -m "feat(v67): add nightly postgres backups with 14-day retention"
```

---

### Task P6-04: Restore the backup, once, for real

Success criterion 6. **An unexercised restore is a hope, not a backup** — so
this task is performed, not described, and its evidence is committed.

**Files:**
- Create: `scripts/ops/restore_db.sh`
- Create: `docs/deploy/DB_RESTORE.md` (the drill's record)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (point at it)
- Test: `tests/scripts/test_restore_db.py`

**Interfaces:**
- Consumes: `backup_db.sh` (P6-03).
- Produces: `scripts/ops/restore_db.sh <dump.sql.gz> <target-db>`.

**The target-database argument has no default, on purpose.** A restore script
whose default target is production is a script that eventually restores over
production. Making the target explicit costs one word and removes that.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_restore_db.py`:

```python
"""The restore script's safety properties."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "restore_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/restore_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_the_target_database_has_no_default(source):
    """A restore whose default target is production eventually restores over
    production."""
    assert "usage" in source.lower()
    assert re.search(r'\$\{?2', source), "no second positional argument"
    assert "swingbot}" not in source, "the target must not default to swingbot"


def test_it_refuses_the_production_database_without_an_explicit_flag(source):
    assert "--i-mean-it" in source or "FORCE" in source


def test_it_verifies_the_dump_exists_before_touching_anything(source):
    dump_check = source.index("-f ") if "-f " in source else source.index("-s ")
    psql_at = source.index("psql")
    assert dump_check < psql_at


def test_the_drill_is_recorded():
    doc = REPO / "docs" / "deploy" / "DB_RESTORE.md"
    assert doc.exists(), "the restore drill has no record"
    text = doc.read_text(encoding="utf-8")
    assert re.search(r"20\d\d-\d\d-\d\d", text), "no date on the drill record"
    assert "row count" in text.lower() or "rows" in text.lower()
```

`test_the_drill_is_recorded` is the one that matters: it fails until the drill
has actually been run and written down.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_restore_db.py -q
```

Expected: all fail on the missing script.

- [ ] **Step 3: Write the restore script**

Create `scripts/ops/restore_db.sh`:

```bash
#!/usr/bin/env bash
# Restore a pg_dump into a named database.
#
#   ./scripts/ops/restore_db.sh data/backups/db/swingbot_2026-08-30_03-00-00.sql.gz swingbot_restore_test
#
# The target database is a REQUIRED argument with no default. A restore script
# whose default target is production is a script that eventually restores over
# production; one word removes that.
set -euo pipefail

cd "$(dirname "$0")/../.."

DUMP="${1:-}"
TARGET="${2:-}"
FORCE="${3:-}"

if [ -z "$DUMP" ] || [ -z "$TARGET" ]; then
  echo "usage: $0 <dump.sql.gz> <target-database> [--i-mean-it]" >&2
  echo "  the target database is required and has no default" >&2
  exit 2
fi

if [ ! -s "$DUMP" ]; then
  echo "restore_db: no such dump, or it is empty: $DUMP" >&2
  exit 1
fi

if [ "$TARGET" = "swingbot" ] && [ "$FORCE" != "--i-mean-it" ]; then
  echo "restore_db: '$TARGET' is the live database." >&2
  echo "  Restore into a throwaway database first and compare row counts." >&2
  echo "  If you really mean it, pass --i-mean-it as the third argument." >&2
  exit 1
fi

echo "restore_db: creating $TARGET"
docker compose exec -T db psql -U swingbot -d postgres \
  -c "DROP DATABASE IF EXISTS \"$TARGET\";" \
  -c "CREATE DATABASE \"$TARGET\";"

echo "restore_db: replaying $DUMP into $TARGET"
gunzip -c "$DUMP" | docker compose exec -T db psql -U swingbot -d "$TARGET" -v ON_ERROR_STOP=1

echo "restore_db: row counts in $TARGET"
docker compose exec -T db psql -U swingbot -d "$TARGET" -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"
```

```bash
chmod +x scripts/ops/restore_db.sh
```

- [ ] **Step 4: Run the drill**

This is the task. Do it, do not describe it:

```bash
./scripts/ops/backup_db.sh
DUMP=$(ls -t data/backups/db/*.sql.gz | head -1)
docker compose exec db psql -U swingbot -d swingbot -c \
  "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"
./scripts/ops/restore_db.sh "$DUMP" swingbot_restore_drill
```

Compare the two row-count tables line by line. They must match exactly.

Then confirm the restored database is not merely populated but *usable*:

```bash
DATABASE_URL=postgresql+psycopg://swingbot:swingbot@localhost:5432/swingbot_restore_drill \
  alembic current
```

Expected: `p6_001 (head)` — the dump carried `alembic_version`, so the restored
database knows where it is in the migration graph. A restore that lands at a
different revision is a restore you cannot migrate forward from.

Clean up:

```bash
docker compose exec db psql -U swingbot -d postgres \
  -c "DROP DATABASE swingbot_restore_drill;"
```

- [ ] **Step 5: Record it**

Create `docs/deploy/DB_RESTORE.md` with: the date, the exact commands run, the
row-count table from both databases side by side, the `alembic current` output,
and one paragraph on what would have been done differently if they had not
matched. Write the real numbers from the run — not placeholders.

Add a pointer from `docs/deploy/DEPLOY_HETZNER.md`.

- [ ] **Step 6: Run the tests and commit**

```bash
python scripts/dev/testrun.py file tests/scripts/test_restore_db.py
git add scripts/ops/restore_db.sh docs/deploy/DB_RESTORE.md \
        docs/deploy/DEPLOY_HETZNER.md tests/scripts/test_restore_db.py
git commit -m "feat(v67): add and exercise the database restore drill"
```

---

### Task P6-05: Per-record JSON export

`cat data/trades.json` was how a single trade got inspected. Postgres takes that
away, and the spec says to give it back — a per-record JSON export in the admin
UI, so inspecting one trade does not need `psql`.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (or wherever the trade detail
  endpoint lives — `grep -rn "trades/<" swingbot/admin/api_v1/`)
- Modify: `swingbot/admin/api_v1/plans.py` similarly
- Test: `tests/admin/test_record_export.py`

**Interfaces:**
- Consumes: `trades_repo` (P2-01), `plans_repo` (P2-07).
- Produces:
  - `GET /api/v1/trades/<trade_id>/export` → the raw record as JSON
  - `GET /api/v1/plans/<plan_id>/export` → the same for a plan

**Raw means raw.** The point of `cat data/trades.json` was seeing exactly what
is stored, including fields no UI renders. These endpoints return the merged
flat dict with no filtering, no formatting and no derived fields — anything else
makes them a different tool that answers a different question.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_record_export.py`:

```python
"""Per-record export: what `cat data/trades.json` used to give."""
import json

import pytest

from swingbot import config
from swingbot.core.db.repositories.trades import TradeRepository


@pytest.fixture
def client(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "trades:db,plans:db")
    from tests.admin.conftest import authed_client       # existing helper
    return authed_client()


def _seed(**over):
    rec = dict(trade_id="T1", ticker="AAPL", strategy="RSI", horizon="2w",
               direction="bullish", status="open",
               opened_at="2026-01-02T15:00:00+00:00", entry=100.0,
               stop_loss=95.0, confidence_level=4,
               an_undocumented_field={"nested": [1, 2, 3]})
    rec.update(over)
    TradeRepository().upsert(rec)
    return rec


def test_export_returns_the_record(client):
    _seed()
    body = client.get("/api/v1/trades/T1/export").get_json()
    assert body["trade_id"] == "T1"
    assert body["ticker"] == "AAPL"


def test_export_includes_fields_no_ui_renders(client):
    """The whole point: seeing exactly what is stored, not what is displayed."""
    _seed()
    body = client.get("/api/v1/trades/T1/export").get_json()
    assert body["an_undocumented_field"] == {"nested": [1, 2, 3]}


def test_export_omits_infrastructure_columns(client):
    _seed()
    body = client.get("/api/v1/trades/T1/export").get_json()
    for key in ("id", "doc", "updated_at"):
        assert key not in body


def test_a_missing_record_is_a_404(client):
    assert client.get("/api/v1/trades/nope/export").status_code == 404


def test_export_requires_auth(client):
    from tests.admin.conftest import anon_client         # existing helper
    assert anon_client().get("/api/v1/trades/T1/export").status_code in (401, 302)


def test_the_response_is_valid_json_a_human_can_read(client):
    _seed()
    text = client.get("/api/v1/trades/T1/export").get_data(as_text=True)
    assert json.loads(text)
    assert "\n" in text, "expected indented JSON, not a single line"


def test_plans_export_works_the_same_way(client):
    from swingbot.core.db.repositories.plans import PlanRepository
    PlanRepository().upsert(dict(
        plan_id="P1", ticker="AAPL", strategy="RSI", horizon_key="2w",
        status="pending", created_at="2026-01-02T15:00:00+00:00"))
    assert client.get("/api/v1/plans/P1/export").get_json()["plan_id"] == "P1"
```

The helper names `authed_client` / `anon_client` are the plausible ones — read
`tests/admin/conftest.py` and use the real ones.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/admin/test_record_export.py -q
```

Expected: 404s from Flask on the unregistered routes.

- [ ] **Step 3: Add the endpoints**

In `swingbot/admin/api_v1/trades.py`:

```python
@api_v1.route("/trades/<trade_id>/export", methods=["GET"])
@require_auth
def export_trade(trade_id: str):
    """The raw stored record, as JSON.

    This replaces `cat data/trades.json` -- which is why it returns the record
    unfiltered and unformatted, including fields no screen renders. Anything
    else would be a different tool answering a different question, and the
    question this one answers is "what is actually stored".
    """
    from swingbot.core.tracking.performance import TradeLog
    record = TradeLog().get_trade_by_id(trade_id)
    if record is None:
        return error("not_found", f"no trade {trade_id!r}", 404)
    return current_app.response_class(
        json.dumps(record, indent=2, sort_keys=True, default=str) + "\n",
        mimetype="application/json")
```

Going through `TradeLog` rather than the repository directly keeps the endpoint
correct at every stage — at `json` it exports the file's record, at `db` the
row's, and the export is always what the application itself would read.

Mirror it in `plans.py` against `PlanStore.get()`, serialising through
`plan_to_dict`.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/admin/test_record_export.py
python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py swingbot/admin/api_v1/plans.py \
        tests/admin/test_record_export.py
git commit -m "feat(v67): add per-record JSON export for trades and plans"
```

---

### Task P6-06: The production import runbook — TOUCHES PRODUCTION

The one-shot operation on irreplaceable data. A tarball first, then a dry run,
then the real run with checksums.

**Files:**
- Create: `docs/deploy/DB_CUTOVER.md`
- Create: `scripts/db/import_all.py`
- Test: `tests/scripts/test_import_all.py`

**Interfaces:**
- Consumes: every importer from Parts 2, 3 and 5, plus P4-04's.
- Produces: `import_all(dry_run=False, only=None) -> dict[str, int]` — exit code
  per importer, and a CLI that stops on the first failure.

**Ordering is a correctness requirement, not a convenience.** `starred_plans`
has a foreign key into `plans` (P2-12), so plans import first. The runbook and
`import_all.py` share one ordered list so they cannot disagree.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_import_all.py`:

```python
"""The ordered importer list, and the guards around a one-shot operation."""
import pytest

from scripts.db.import_all import ORDER, import_all


def test_plans_import_before_starred_plans():
    """starred_plans.plan_id is a foreign key into plans.plan_id (p2_006).
    Importing stars first fails every row."""
    assert ORDER.index("plans") < ORDER.index("starred")


def test_trades_import_before_account():
    """_sum_realized_pnl reads trades to derive the account balance."""
    assert ORDER.index("trades") < ORDER.index("account")


def test_every_importer_in_the_order_exists():
    import importlib
    for name in ORDER:
        importlib.import_module(f"scripts.db.import_{name}")


def test_the_order_covers_every_registered_parity_store():
    from scripts.db.parity_report import STORES
    # Not every importer has a parity store (settings, shadow) and not every
    # parity store has an importer -- but a store with neither is a store
    # nobody checked, so assert the union covers what is registered.
    named = set(ORDER) | {"settings", "shadow"}
    unchecked = {s for s in STORES if s.replace("_plans", "") not in named}
    assert not unchecked, f"stores with no importer: {sorted(unchecked)}"


def test_dry_run_writes_nothing(tmp_path, monkeypatch, db_committed):
    from swingbot import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    results = import_all(dry_run=True)
    assert all(code == 0 for code in results.values()), results


def test_import_all_stops_on_the_first_failure(monkeypatch, tmp_path):
    from swingbot import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    import scripts.db.import_all as mod
    calls = []

    def fake_run(name, dry_run):
        calls.append(name)
        return 0 if len(calls) < 2 else 1

    monkeypatch.setattr(mod, "_run_one", fake_run)
    results = mod.import_all()
    assert len(calls) == 2, "it kept going after a failure"
    assert results[calls[-1]] == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_import_all.py -q
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write the orchestrator**

Create `scripts/db/import_all.py`:

```python
#!/usr/bin/env python3
"""Run every importer, in an order the foreign keys require.

    python scripts/db/import_all.py --dry-run
    python scripts/db/import_all.py

Stops at the first failure. This runs once, against data that has no second
copy, so "carry on and see what else breaks" is the wrong behaviour -- the
first failure is the one to look at.
"""
import argparse
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

#: Order matters, twice over:
#:   plans before starred  -- starred_plans.plan_id is a FK into plans (p2_006)
#:   trades before account -- _sum_realized_pnl derives the balance from trades
#: Everything else is independent; the order below is just the spec's inventory
#: order, so a reader can check it against the spec without re-deriving it.
ORDER = [
    "trades", "plans", "starred", "account", "journal", "state", "watchlist",
    "jobs", "scheduled", "preferences", "settings_audit", "killswitch",
    "ticker_directory", "tuning",
    "settings",
    "telemetry", "shadow", "retrospective",
]


def _run_one(name: str, dry_run: bool) -> int:
    mod = importlib.import_module(f"scripts.db.import_{name}")
    argv = ["--dry-run"] if dry_run else []
    if hasattr(mod, "main"):
        return mod.main(argv)
    # run_import-based scripts expose their CLI through __main__ only; call the
    # same entry point directly rather than shelling out.
    from scripts.db.import_common import run_import
    return run_import(argv, load_source=mod.load_source,
                      write_one=mod.write_one, repo=mod.REPO_FACTORY(),
                      key=mod.KEY, name=name)


def import_all(dry_run: bool = False, only: list[str] | None = None) -> dict:
    results: dict[str, int] = {}
    for name in (only or ORDER):
        print(f"\n=== {name} ===", flush=True)
        code = _run_one(name, dry_run)
        results[name] = code
        if code != 0:
            print(f"\nimport_all: {name} FAILED (exit {code}); stopping.",
                  file=sys.stderr)
            break
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="+", choices=ORDER)
    args = ap.parse_args(argv)
    results = import_all(dry_run=args.dry_run, only=args.only)
    print("\n=== summary ===")
    for name in results:
        print(f"  {name}: {'OK' if results[name] == 0 else 'FAILED'}")
    return 0 if all(c == 0 for c in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`_run_one`'s `run_import` branch needs `REPO_FACTORY` and `KEY` module
constants on each `run_import`-based importer. Add them — it is two lines per
script and it removes a subprocess from the path.

- [ ] **Step 4: Write the runbook**

Create `docs/deploy/DB_CUTOVER.md`. It is an operator document, so it is a
numbered list of commands with the reason for each, not prose:

1. **Take a tarball first.** `tar czf ~/data-preflight-$(date -u +%F).tgz data/`
   on the VM. The spec names this: the underlying data is irreplaceable and the
   dry run reduces the risk rather than removing it.
2. **Bring up the database.** `docker compose up -d db` and confirm
   `pg_isready`.
3. **Migrate.** `docker compose exec bot alembic upgrade head`, then
   `alembic current` — expect `p6_001 (head)`.
4. **Dry run.** `docker compose exec bot python scripts/db/import_all.py --dry-run`.
   Read every count against `wc -l` / `jq length` on the corresponding file.
   A count that disagrees is a stop, not a note.
5. **Stop the bot.** `docker compose stop bot admin`. The import must not race
   a live writer.
6. **Real run.** `docker compose exec db ...` is not enough — run
   `docker compose run --rm bot python scripts/db/import_all.py`, and keep the
   output.
7. **Verify.** `python scripts/db/parity_report.py --all`. Every store `OK`.
8. **Back up immediately.** `./scripts/ops/backup_db.sh` — the first dump that
   contains real history.
9. **Then, and only then, flip stages** — P6-07.

Each step gets one sentence saying what a failure there means and what to do
about it. Step 5 in particular: if the bot was running, discard the import
(`DROP DATABASE`, recreate, migrate) and start again rather than reconciling.

- [ ] **Step 5: Rehearse locally**

```bash
python scripts/dev/testrun.py file tests/scripts/test_import_all.py
python scripts/db/import_all.py --dry-run
```

Expected: `0 failed`, and a dry run that walks every importer. Local `data/` is
mostly empty, so most counts are 0 — that is the documented local state, and it
still exercises the ordering and the CLI.

- [ ] **Step 6: Commit**

```bash
git add scripts/db/import_all.py scripts/db/import_*.py \
        docs/deploy/DB_CUTOVER.md tests/scripts/test_import_all.py
git commit -m "feat(v67): add the production import orchestrator and runbook"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_6b-cleanup.md`**
(P6-07…P6-12): the production stage flip, the dead-path deletion, the docs
sweep, and the full-suite gate.
