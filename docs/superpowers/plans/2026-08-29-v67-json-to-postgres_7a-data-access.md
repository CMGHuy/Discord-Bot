# v67 — Part 7: Dev/prod data access (tasks P7-01…P7-06)

> Part of `2026-08-29-v67-json-to-postgres_0-index.md`. **Read the index's
> Global Constraints before starting any task here.** P6-01…P6-11 must be
> merged and production must already be running on Postgres (P6-07) before this
> part begins — until then production data is still JSON files and you get it
> the old way. **P6-12 lands after this part**, so that the plan's single
> full-suite gate covers Part 7's code too. Tasks P7-07…P7-12 are in
> `2026-08-29-v67-json-to-postgres_7b-datasets.md`.

**Spec:** `docs/superpowers/specs/2026-08-29-v67-json-to-postgres-design.md`

## Why this part exists

Parts 1–6 replace the persistence layer and leave one workflow broken that
nobody wrote down: **`scp`-ing `data/*.json` off the VM to look at real trades
locally.** The `db` service publishes no ports (P1-03, deliberately — a
Postgres on a public VM with a published port ends up in someone else's
botnet), so after the cutover there is no path from a dev machine to production
data at all.

That is a regression this plan would otherwise ship. This part closes it, and
takes the opportunity to make the local analysis path better than the one it
replaces rather than merely equivalent.

## Three access modes, named

The modes differ in their **safety properties**, so they get names rather than
being three ways of setting one variable:

| Profile | What it is | Writes? | Use for |
|---|---|---|---|
| `local` | this machine's `db` container | yes | development, tests |
| `snapshot` | a local database restored from a production dump | yes — it is a copy | backtests, training, analysis, "why did that trade close there" |
| `prod-ro` | production, over an SSH tunnel, as a SELECT-only role | **no** | "what is it doing right now" |

**`snapshot` is the one to reach for by default.** It is full speed, needs no
network, and nothing you do to it can reach production. `prod-ro` exists for
the questions a snapshot cannot answer — the ones about *now*.

**Write protection is a Postgres role, not a Python check.** A `if
readonly: raise` is one refactor away from being wrong, and the thing it
guards is production trade history. P7-01 makes the server refuse.

## Alembic revision ids

Part 7 owns `p7_*`, hanging off `p6_001` — Part 6 is merged by the time this
part starts, so there is one head to hang from.

| Revision | Content |
|---|---|
| `p7_001` | the `swingbot_ro` read-only role and its default privileges |

## Parallelisation

- **Sequential: P7-01 before P7-03 and P7-05** — both consume the read-only
  role.
- **Group 7a (parallel):** P7-02 (`pull_prod_db.sh`) and P7-06
  (`scripts/db/query.py`) — different files, no shared symbol.
- **Sequential: P7-04 before P7-05, P7-06 and everything in `_7b`** — the
  profile resolver is what they all select a database with.

## Part 7 exit criteria

1. A production snapshot can be pulled to a local database with one command,
   and it never touches the local development database.
2. A local session can read production live, through an SSH tunnel, as a role
   that Postgres itself refuses writes from.
3. No committed file points `DATABASE_URL` at production.
4. Closed trades, plans and telemetry are available as pandas DataFrames from
   any profile, in one import.
5. `python scripts/dev/testrun.py fast` is green.

---

# Phase 7 — Dev/prod data access

### Task P7-01: A read-only role

Postgres refuses the write. Nothing in Python is trusted to.

**Files:**
- Create: `swingbot/core/db/migrations/versions/p7_001_readonly_role.py`
- Modify: `swingbot/config.py` (one field: `POSTGRES_RO_PASSWORD`)
- Modify: `.env.example`
- Test: `tests/db/test_readonly_role.py`

**Interfaces:**
- Consumes: `p6_001` (P6-02).
- Produces: the Postgres role `swingbot_ro`, with `SELECT` on every table in
  `public` **and** default privileges so a table created later is covered
  without anyone remembering to re-grant.

**The default-privileges half is the part that matters.** A one-time
`GRANT SELECT ON ALL TABLES` covers the tables that exist when it runs and
silently misses every table added afterwards — which, in a repo whose data
model changes about once per plan, means the grant is stale within a month.
`ALTER DEFAULT PRIVILEGES` covers the future ones.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_readonly_role.py`:

```python
"""The read-only role, enforced by Postgres rather than by a Python guard."""
import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.slow          # needs its own connection, so it commits

RO_URL_TEMPLATE = "postgresql+psycopg://swingbot_ro:{pw}@{host}:{port}/{db}"


@pytest.fixture
def ro_engine(db_engine):
    """An engine connected as swingbot_ro against the test database."""
    url = db_engine.url
    ro = RO_URL_TEMPLATE.format(pw="swingbot_ro", host=url.host,
                                port=url.port, db=url.database)
    engine = sa.create_engine(ro, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("select 1"))
    except Exception as exc:                       # noqa: BLE001
        engine.dispose()
        pytest.skip(f"swingbot_ro not provisioned on the test database: {exc}")
    yield engine
    engine.dispose()


def test_the_role_can_read(ro_engine):
    from swingbot.core.db.schema import trades
    with ro_engine.connect() as conn:
        conn.execute(sa.select(sa.func.count()).select_from(trades)).scalar_one()


def test_the_role_cannot_insert(ro_engine):
    from swingbot.core.db.schema import trades
    with ro_engine.connect() as conn:
        with pytest.raises(sa.exc.ProgrammingError, match="permission denied"):
            conn.execute(sa.insert(trades).values(
                trade_id="RO-1", ticker="AAPL", strategy="RSI", horizon="2w",
                direction="bullish", status="open",
                opened_at="2026-01-02T15:00:00+00:00"))


def test_the_role_cannot_update(ro_engine):
    from swingbot.core.db.schema import trades
    with ro_engine.connect() as conn:
        with pytest.raises(sa.exc.ProgrammingError, match="permission denied"):
            conn.execute(sa.update(trades).values(status="win"))


def test_the_role_cannot_delete(ro_engine):
    from swingbot.core.db.schema import trades
    with ro_engine.connect() as conn:
        with pytest.raises(sa.exc.ProgrammingError, match="permission denied"):
            conn.execute(sa.delete(trades))


def test_the_role_cannot_create_a_table(ro_engine):
    with ro_engine.connect() as conn:
        with pytest.raises(sa.exc.ProgrammingError, match="permission denied"):
            conn.execute(sa.text("CREATE TABLE ro_should_not_exist (i int)"))


def test_a_table_created_after_the_grant_is_still_readable(ro_engine, db_engine):
    """ALTER DEFAULT PRIVILEGES, not a one-time GRANT. A repo whose data model
    changes once per plan outgrows a one-time grant within a month."""
    with db_engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE IF NOT EXISTS later_table (i int)"))
    try:
        with ro_engine.connect() as conn:
            conn.execute(sa.text("select count(*) from later_table")).scalar_one()
    finally:
        with db_engine.begin() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS later_table"))


def test_the_role_cannot_read_the_settings_table(ro_engine):
    """Non-sensitive by policy, but it is still configuration and a read-only
    analysis role has no business in it. Revoked explicitly."""
    with ro_engine.connect() as conn:
        with pytest.raises(sa.exc.ProgrammingError, match="permission denied"):
            conn.execute(sa.text("select * from settings")).all()
```

The last test states a policy decision worth being explicit about: the
read-only role is for **trading data**, not configuration. `settings` holds
nothing secret (P4-01 keeps secrets in `.env`) but it is the one table where a
casual local query is answering a question the operator should be asking the
admin UI.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_readonly_role.py -q
```

Expected: every test skips — the role does not exist yet. **A skip is not a
pass here**; the fixture's skip message is what tells you the migration has not
run.

- [ ] **Step 3: Add the password field**

Append to `FIELDS` in `swingbot/config.py`, in the Database section:

```python
    Field("POSTGRES_RO_PASSWORD", "POSTGRES_RO_PASSWORD", "Database",
          "Read-only role password",
          type="password", sensitive=True, hot_reloadable=False,
          default="swingbot_ro",
          help="Password for the swingbot_ro SELECT-only role, used by local "
               "analysis over an SSH tunnel (scripts/ops/tunnel_prod_db.sh). "
               "This role can read trading data and nothing else -- Postgres "
               "refuses its writes, so a mistake at a psql prompt cannot "
               "reach production."),
```

- [ ] **Step 4: Write the migration**

Create `swingbot/core/db/migrations/versions/p7_001_readonly_role.py`:

```python
"""create the swingbot_ro SELECT-only role

Revision ID: p7_001
Revises: p6_001

The role exists so a developer can read production live without being able to
change it, and so that guarantee is enforced by Postgres rather than by an
`if readonly:` in application code -- which is one refactor away from being
wrong, guarding production trade history.
"""
import os

from alembic import op

revision = "p7_001"
down_revision = "p6_001"
branch_labels = None
depends_on = None

# Tables the read-only role may NOT read. It is an analysis role for trading
# data; configuration is the admin UI's job to show.
DENIED = ("settings",)


def upgrade() -> None:
    password = os.getenv("POSTGRES_RO_PASSWORD", "swingbot_ro")
    # Quoted with a dollar-quoted literal so a password containing a quote is
    # not a SQL injection into our own migration.
    op.execute(f"""
        DO $do$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'swingbot_ro') THEN
            CREATE ROLE swingbot_ro LOGIN PASSWORD $pw${password}$pw$;
          ELSE
            ALTER ROLE swingbot_ro LOGIN PASSWORD $pw${password}$pw$;
          END IF;
        END
        $do$;
    """)
    op.execute("GRANT CONNECT ON DATABASE swingbot TO swingbot_ro")
    op.execute("GRANT USAGE ON SCHEMA public TO swingbot_ro")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO swingbot_ro")
    # The half that keeps this correct as the schema grows: a table created
    # next month is covered without anyone remembering to re-grant.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "GRANT SELECT ON TABLES TO swingbot_ro")
    for table in DENIED:
        op.execute(f"REVOKE ALL ON TABLE {table} FROM swingbot_ro")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               "REVOKE SELECT ON TABLES FROM swingbot_ro")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM swingbot_ro")
    op.execute("REVOKE ALL ON SCHEMA public FROM swingbot_ro")
    op.execute("REVOKE ALL ON DATABASE swingbot FROM swingbot_ro")
    op.execute("DROP ROLE IF EXISTS swingbot_ro")
```

`GRANT CONNECT ON DATABASE swingbot` names the database literally, which is
correct for production and wrong for the test database. Provision the role on
the test database from the harness instead — add to `tests/db/conftest.py`'s
`db_engine` fixture, after `METADATA.create_all`:

```python
    # The read-only role, so tests/db/test_readonly_role.py has something to
    # test. Mirrors p7_001 rather than running it: the migration names the
    # production database in its GRANT CONNECT.
    with engine.begin() as conn:
        conn.execute(sa.text("""
            DO $do$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='swingbot_ro')
              THEN CREATE ROLE swingbot_ro LOGIN PASSWORD 'swingbot_ro'; END IF;
            END $do$;"""))
        conn.execute(sa.text(
            f"GRANT CONNECT ON DATABASE {engine.url.database} TO swingbot_ro"))
        conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO swingbot_ro"))
        conn.execute(sa.text(
            "GRANT SELECT ON ALL TABLES IN SCHEMA public TO swingbot_ro"))
        conn.execute(sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                             "GRANT SELECT ON TABLES TO swingbot_ro"))
        conn.execute(sa.text("REVOKE ALL ON TABLE settings FROM swingbot_ro"))
```

Two definitions of the same grants is a duplication worth naming: the
alternative is a migration that reads the database name from the connection,
which would make the production grant depend on what someone typed in
`DATABASE_URL`. A test asserting the two lists match is P7-12's job.

- [ ] **Step 5: Migrate and run**

```bash
alembic upgrade head
docker compose exec db psql -U swingbot -d swingbot -c "\du swingbot_ro"
docker compose --profile test up -d db-test
python -m pytest tests/db/test_readonly_role.py -q
```

Expected: the role listed with no attributes, and `0 failed` with nothing
skipped.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/migrations/versions/p7_001_readonly_role.py \
        swingbot/config.py .env.example tests/db/conftest.py \
        tests/db/test_readonly_role.py
git commit -m "feat(v67): add a SELECT-only postgres role for local analysis"
```

---

### Task P7-02: Pull a production snapshot — TOUCHES PRODUCTION (read-only)

One command, from a dev machine, that leaves a local database holding a copy of
production. This is the replacement for `scp data/*.json`.

**Files:**
- Create: `scripts/ops/pull_prod_db.sh`
- Modify: `Makefile`
- Test: `tests/scripts/test_pull_prod_db.py`

**Interfaces:**
- Consumes: `restore_db.sh` (P6-04), `scripts/ops/ssh-hetzner.sh` (uncommitted).
- Produces: `make db-pull` → a local database named `swingbot_snapshot`.

**Two safety properties this script must have, and the tests exist for both:**

1. **It never writes to the local `swingbot` database.** The target is
   `swingbot_snapshot`, hardcoded. A developer who has been working locally
   must not lose that work to a pull.
2. **It only ever reads production.** `pg_dump` and nothing else. No `psql -c`,
   no `docker compose restart`, no write of any kind over the SSH connection.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_pull_prod_db.py`:

```python
"""The pull script's safety properties. It cannot be run in CI, so what is
asserted is what a careless edit would remove."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "pull_prod_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/pull_prod_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_the_local_target_is_the_snapshot_database(source):
    assert "swingbot_snapshot" in source


def test_it_never_targets_the_local_development_database(source):
    """A pull must not be able to destroy local work in progress."""
    for line in source.splitlines():
        if line.strip().startswith("#"):
            continue
        assert not re.search(r"\bswingbot\b(?!_snapshot|_ro)", line), (
            f"line targets the live database name: {line.strip()}")


def test_it_only_reads_production(source):
    """pg_dump and nothing else over the SSH connection."""
    remote = [l for l in source.splitlines() if "$SSH" in l or "ssh " in l]
    assert remote, "no remote invocation found"
    joined = " ".join(remote)
    assert "pg_dump" in joined
    for forbidden in ("psql -c", "restart", "rm ", "DROP", "INSERT", "UPDATE"):
        assert forbidden not in joined, f"pull script does more than read: {forbidden}"


def test_it_names_the_ssh_helper_and_degrades_with_a_message(source):
    """ssh-hetzner.sh is gitignored (it shells through WSL to a key in WSL's
    own home), so this must say what to do rather than failing obscurely."""
    assert "ssh-hetzner.sh" in source
    assert "SWINGBOT_SSH" in source


def test_it_keeps_the_dump_on_disk(source):
    """The dump is worth keeping: it is also a backup, and re-restoring it is
    faster than pulling again."""
    assert "data/backups/db" in source or "data/snapshots" in source


def test_the_makefile_exposes_it():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "db-pull:" in makefile
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_pull_prod_db.py -q
```

Expected: every test fails on the missing script.

- [ ] **Step 3: Write it**

Create `scripts/ops/pull_prod_db.sh`:

```bash
#!/usr/bin/env bash
# Pull a production snapshot into a LOCAL database named swingbot_snapshot.
#
# This replaces `scp data/*.json` -- the workflow v67 would otherwise take
# away. It is read-only against production: one pg_dump over SSH, nothing else.
#
#   make db-pull
#   ./scripts/ops/pull_prod_db.sh
#
# The local target is swingbot_snapshot, hardcoded and never swingbot: a pull
# must not be able to destroy whatever you were working on locally.
set -euo pipefail

cd "$(dirname "$0")/../.."

# ssh-hetzner.sh is gitignored -- it shells through WSL to a key in WSL's own
# home, so its contents are machine-specific. Override with SWINGBOT_SSH if
# your path in is different.
SSH="${SWINGBOT_SSH:-scripts/ops/ssh-hetzner.sh}"
if [ ! -x "$SSH" ]; then
  echo "pull_prod_db: no SSH helper at $SSH" >&2
  echo "  It is gitignored (machine-specific). Create it, or set" >&2
  echo "  SWINGBOT_SSH=/path/to/your/ssh-wrapper -- see docs/deploy/DEPLOY_HETZNER.md" >&2
  exit 1
fi

TARGET="swingbot_snapshot"
SNAP_DIR="data/backups/db"
STAMP="$(date -u +%Y-%m-%d_%H-%M-%S)"
DUMP="${SNAP_DIR}/prod_${STAMP}.sql.gz"

mkdir -p "$SNAP_DIR"

echo "pull_prod_db: dumping production (read-only)..."
# The ONLY remote command. --no-owner --no-acl so the restore does not try to
# recreate production's roles locally, which would fail and is not wanted.
"$SSH" "cd /srv/swing-bot && docker compose exec -T db \
  pg_dump -U swingbot -d swingbot --no-owner --no-acl --clean --if-exists -Fp" \
  | gzip -9 > "$DUMP"

if [ ! -s "$DUMP" ]; then
  echo "pull_prod_db: dump is empty; production may not be up. Nothing changed." >&2
  rm -f "$DUMP"
  exit 1
fi

echo "pull_prod_db: got $DUMP ($(du -h "$DUMP" | cut -f1))"
echo "pull_prod_db: restoring into local '$TARGET' (NOT 'swingbot')"
./scripts/ops/restore_db.sh "$DUMP" "$TARGET"

cat <<EOF

pull_prod_db: done. To use it:

  export DATABASE_URL_SNAPSHOT=postgresql+psycopg://swingbot:\${POSTGRES_PASSWORD}@localhost:5432/$TARGET
  python scripts/db/query.py --profile snapshot "select count(*) from trades"

Your local development database ('swingbot') was not touched.
EOF
```

```bash
chmod +x scripts/ops/pull_prod_db.sh
```

`restore_db.sh` (P6-04) refuses the `swingbot` target without `--i-mean-it`, so
even a typo in `TARGET` here is caught one layer down. Two independent guards
for the same mistake is proportionate when the mistake destroys local work.

The local `db` service must publish a port for `restore_db.sh` to reach it from
the host — it already does not (P1-03). `restore_db.sh` goes through
`docker compose exec`, so no port is needed; **do not add one.**

- [ ] **Step 4: Add the Makefile target**

```make
db-pull:
	./scripts/ops/pull_prod_db.sh
```

and add `db-pull` to `.PHONY`.

- [ ] **Step 5: Run it for real**

```bash
make db-pull
docker compose exec db psql -U swingbot -d swingbot_snapshot -c "
  SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"
docker compose exec db psql -U swingbot -d swingbot -c "SELECT count(*) FROM trades;"
```

Expected: the snapshot holding real production row counts, and the local
`swingbot` database unchanged.

- [ ] **Step 6: Run the tests and commit**

```bash
python scripts/dev/testrun.py file tests/scripts/test_pull_prod_db.py
git add scripts/ops/pull_prod_db.sh Makefile tests/scripts/test_pull_prod_db.py
git commit -m "feat(v67): pull a production snapshot into a local database"
```

---

### Task P7-03: An SSH tunnel to production, read-only

For the questions a snapshot cannot answer — the ones about right now.

**Files:**
- Create: `scripts/ops/tunnel_prod_db.sh`
- Modify: `Makefile`
- Test: `tests/scripts/test_tunnel_prod_db.py`

**Interfaces:**
- Consumes: the `swingbot_ro` role (P7-01).
- Produces: `make db-tunnel` → a local port forwarding to production Postgres,
  and the `DATABASE_URL_PROD_RO` to use with it.

**Why a tunnel and not a published port.** Publishing 5432 on the VM would make
this a one-liner and would also put a Postgres on the public internet. The
tunnel is authenticated by the SSH key that already exists, exposes nothing
new, and closes when the terminal does.

**Port 55434**, not 5432 and not 55432: it must not collide with the local `db`
container or the `db-test` one. Getting those confused means running a query
against the wrong database and believing the answer.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_tunnel_prod_db.py`:

```python
"""The tunnel script's safety properties."""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "tunnel_prod_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/tunnel_prod_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_it_forwards_rather_than_publishing(source):
    """A published port on the VM would put Postgres on the public internet."""
    assert "-L" in source
    assert "ports:" not in source


def test_it_uses_a_port_that_collides_with_neither_local_database(source):
    assert "55434" in source
    assert "55432" not in source, "55432 is the test database"


def test_the_printed_url_uses_the_read_only_role(source):
    """The whole point. A tunnel handing out the swingbot superuser URL would
    be a tunnel that can drop production tables."""
    urls = [l for l in source.splitlines() if "postgresql" in l]
    assert urls, "no DATABASE_URL printed"
    for line in urls:
        assert "swingbot_ro" in line, f"non-read-only URL printed: {line.strip()}"
        assert not re.search(r"://swingbot:", line), line.strip()


def test_it_names_the_ssh_helper_and_the_override(source):
    assert "ssh-hetzner.sh" in source
    assert "SWINGBOT_SSH" in source


def test_the_makefile_exposes_it():
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "db-tunnel:" in makefile
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_tunnel_prod_db.py -q
```

Expected: all fail on the missing script.

- [ ] **Step 3: Write it**

Create `scripts/ops/tunnel_prod_db.sh`:

```bash
#!/usr/bin/env bash
# Forward production Postgres to localhost:55434, as the SELECT-only role.
#
# Blocks until interrupted. Run it in one terminal, query from another:
#
#   make db-tunnel                      # terminal 1
#   python scripts/db/query.py --profile prod-ro "select count(*) from trades"
#
# A TUNNEL, not a published port: the VM exposes nothing new, the SSH key that
# already exists is the authentication, and it closes when this terminal does.
#
# The URL printed uses swingbot_ro, which Postgres refuses writes from. That is
# the guarantee -- not this script's good intentions.
set -euo pipefail

cd "$(dirname "$0")/../.."

SSH="${SWINGBOT_SSH:-scripts/ops/ssh-hetzner.sh}"
if [ ! -x "$SSH" ]; then
  echo "tunnel_prod_db: no SSH helper at $SSH" >&2
  echo "  It is gitignored (machine-specific). Create it, or set" >&2
  echo "  SWINGBOT_SSH=/path/to/your/ssh-wrapper." >&2
  exit 1
fi

# 55434: not 5432 (the local db container) and not 55432 (db-test). Confusing
# those means querying the wrong database and believing the answer.
LOCAL_PORT=55434

cat <<EOF
tunnel_prod_db: forwarding production Postgres to localhost:${LOCAL_PORT}

  export DATABASE_URL_PROD_RO="postgresql+psycopg://swingbot_ro:\${POSTGRES_RO_PASSWORD}@localhost:${LOCAL_PORT}/swingbot"

This connection is READ-ONLY -- Postgres refuses writes from swingbot_ro.
Ctrl-C to close.

EOF

# The container publishes no port, so forward to the container's address on the
# compose network as seen from the VM. `docker compose port` would be cleaner
# but the db service deliberately has no published port to report.
exec "$SSH" -N -L "${LOCAL_PORT}:$(printf '%s' 'localhost'):5432" \
  "docker compose -f /srv/swing-bot/docker-compose.yml exec -T db true"
```

**That last line will not work as written, and finding out how is part of this
task.** `ssh -L` forwards to a host reachable *from the VM*, and the db
container has no port on the VM's own network. Two workable shapes, and the
executor picks one after testing:

- **`socat` on the VM** — forward `localhost:5432` on the VM to the container,
  then `-L 55434:localhost:5432`. Needs `socat` installed there.
- **Publish the port on the VM's loopback only** — add
  `ports: ["127.0.0.1:5432:5432"]` to the `db` service. Not public (loopback
  binding), reachable by `ssh -L`. This is the simpler option and the one to
  try first; if you take it, **update `tests/db/test_compose.py`**, whose
  P1-03 assertion that `db` publishes nothing must become "publishes only on
  loopback", with the reasoning written into the test.

Do not leave the placeholder in. A script that looks right and does not work is
worse than no script.

- [ ] **Step 4: Add the Makefile target and test it live**

```make
db-tunnel:
	./scripts/ops/tunnel_prod_db.sh
```

In one terminal `make db-tunnel`; in another:

```bash
psql "postgresql://swingbot_ro:${POSTGRES_RO_PASSWORD}@localhost:55434/swingbot" \
  -c "select count(*) from trades;"
psql "postgresql://swingbot_ro:${POSTGRES_RO_PASSWORD}@localhost:55434/swingbot" \
  -c "delete from trades;"
```

Expected: a real count, then `ERROR: permission denied for table trades`. **Run
the second command.** The guarantee is worth confirming once by hand.

- [ ] **Step 5: Run the tests and commit**

```bash
python scripts/dev/testrun.py file tests/scripts/test_tunnel_prod_db.py
python scripts/dev/testrun.py file tests/db/test_compose.py
git add scripts/ops/tunnel_prod_db.sh Makefile docker-compose.yml \
        tests/scripts/test_tunnel_prod_db.py tests/db/test_compose.py
git commit -m "feat(v67): add a read-only ssh tunnel to production postgres"
```

---

### Task P7-04: Profile resolution

One place decides which database a command talks to, so no script builds a URL
by hand and no developer has to remember which port was which.

**Files:**
- Create: `swingbot/core/db/profiles.py`
- Modify: `swingbot/config.py` (two fields)
- Modify: `.env.example`
- Test: `tests/db/test_profiles.py`

**Interfaces:**
- Consumes: `config.DATABASE_URL` (P1-02), `DatabaseUnavailable` (P1-02).
- Produces:
  - `PROFILES = ("local", "snapshot", "prod-ro")`
  - `resolve_url(profile: str | None = None) -> str`
  - `is_readonly(profile) -> bool`
  - `engine_for(profile) -> sqlalchemy.Engine` — a **separate** engine from
    `get_engine()`, cached per profile
  - `config.DATABASE_URL_SNAPSHOT`, `config.DATABASE_URL_PROD_RO`

**`engine_for` is deliberately not `get_engine`.** `get_engine()` is the
application's single pool against its own database, and every store goes
through it. An analysis tool pointing that singleton at a snapshot would make
the running bot read the snapshot too. They are separate objects because they
are separate things.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_profiles.py`:

```python
"""Which database a command talks to, decided in one place."""
import pytest

from swingbot import config
from swingbot.core.db import profiles


@pytest.fixture(autouse=True)
def _reset():
    profiles.reset_engines()
    yield
    profiles.reset_engines()


def test_the_three_profiles():
    assert profiles.PROFILES == ("local", "snapshot", "prod-ro")


def test_local_is_the_default(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@localhost:5432/swingbot")
    assert profiles.resolve_url() == config.DATABASE_URL
    assert profiles.resolve_url("local") == config.DATABASE_URL


def test_snapshot_resolves_its_own_url(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL_SNAPSHOT",
                        "postgresql+psycopg://u:p@localhost:5432/swingbot_snapshot")
    assert "swingbot_snapshot" in profiles.resolve_url("snapshot")


def test_prod_ro_resolves_its_own_url(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL_PROD_RO",
                        "postgresql+psycopg://swingbot_ro:p@localhost:55434/swingbot")
    assert "swingbot_ro" in profiles.resolve_url("prod-ro")


def test_an_unset_profile_names_what_to_do(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL_SNAPSHOT", "")
    from swingbot.core.db.engine import DatabaseUnavailable
    with pytest.raises(DatabaseUnavailable) as exc:
        profiles.resolve_url("snapshot")
    assert "DATABASE_URL_SNAPSHOT" in str(exc.value)
    assert "db-pull" in str(exc.value), "the error should say how to create one"


def test_an_unknown_profile_raises(monkeypatch):
    with pytest.raises(ValueError, match="not a known profile"):
        profiles.resolve_url("production")


def test_prod_ro_is_the_only_readonly_profile():
    assert profiles.is_readonly("prod-ro") is True
    assert profiles.is_readonly("local") is False
    assert profiles.is_readonly("snapshot") is False


def test_prod_ro_refuses_a_superuser_url(monkeypatch):
    """A URL naming swingbot rather than swingbot_ro under this profile is a
    misconfiguration that would silently give a write connection to production."""
    monkeypatch.setattr(config, "DATABASE_URL_PROD_RO",
                        "postgresql+psycopg://swingbot:p@localhost:55434/swingbot")
    from swingbot.core.db.engine import DatabaseUnavailable
    with pytest.raises(DatabaseUnavailable, match="swingbot_ro"):
        profiles.resolve_url("prod-ro")


def test_engine_for_is_cached_per_profile(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@localhost:5432/swingbot")
    monkeypatch.setattr(config, "DATABASE_URL_SNAPSHOT",
                        "postgresql+psycopg://u:p@localhost:5432/swingbot_snapshot")
    assert profiles.engine_for("local") is profiles.engine_for("local")
    assert profiles.engine_for("local") is not profiles.engine_for("snapshot")


def test_engine_for_is_not_the_application_engine(monkeypatch):
    """get_engine() is the running bot's pool. An analysis tool repointing it
    would make the bot read the snapshot too."""
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://u:p@localhost:5432/swingbot")
    from swingbot.core.db import engine as app_engine
    app_engine.reset_engine()
    assert profiles.engine_for("local") is not app_engine.get_engine()
    app_engine.reset_engine()
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_profiles.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.db.profiles'`.

- [ ] **Step 3: Add the two fields**

Append to `FIELDS` in the Database section:

```python
    Field("DATABASE_URL_SNAPSHOT", "DATABASE_URL_SNAPSHOT", "Database",
          "Snapshot database URL",
          type="password", sensitive=True, hot_reloadable=False,
          help="A LOCAL database holding a production snapshot, created by "
               "`make db-pull`. Full speed, no network, and nothing you do to "
               "it can reach production -- this is the one to use for "
               "backtests, training and analysis. Empty until you pull one."),
    Field("DATABASE_URL_PROD_RO", "DATABASE_URL_PROD_RO", "Database",
          "Production read-only URL",
          type="password", sensitive=True, hot_reloadable=False,
          help="Production Postgres through the SSH tunnel "
               "(`make db-tunnel`), as the swingbot_ro role. Must name "
               "swingbot_ro -- a URL naming swingbot here would be a write "
               "connection to production and is refused."),
```

- [ ] **Step 4: Write the resolver**

Create `swingbot/core/db/profiles.py`:

```python
"""Which database a command talks to.

Three profiles, differing in their safety properties rather than merely in
their URLs -- see the table at the top of the Part 7 plan file:

    local     this machine's db container. Read/write. The default.
    snapshot  a LOCAL copy of production (`make db-pull`). Read/write; it is a
              copy, so nothing you do to it can reach production. Use this for
              backtests, training and analysis.
    prod-ro   production over an SSH tunnel, as a SELECT-only role. For the
              questions a snapshot cannot answer -- the ones about now.
"""
from __future__ import annotations

from sqlalchemy import Engine, create_engine

from swingbot import config
from swingbot.core.db.engine import DatabaseUnavailable

PROFILES = ("local", "snapshot", "prod-ro")
DEFAULT_PROFILE = "local"

_READONLY = frozenset({"prod-ro"})

_ATTR = {
    "local": "DATABASE_URL",
    "snapshot": "DATABASE_URL_SNAPSHOT",
    "prod-ro": "DATABASE_URL_PROD_RO",
}

_HOWTO = {
    "snapshot": "Create one with `make db-pull`, then export "
                "DATABASE_URL_SNAPSHOT as that command prints.",
    "prod-ro": "Open the tunnel with `make db-tunnel`, then export "
               "DATABASE_URL_PROD_RO as that command prints.",
    "local": "Set DATABASE_URL in .env (see .env.example).",
}

_engines: dict[str, Engine] = {}


def is_readonly(profile: str | None = None) -> bool:
    return (profile or DEFAULT_PROFILE) in _READONLY


def resolve_url(profile: str | None = None) -> str:
    profile = profile or DEFAULT_PROFILE
    if profile not in PROFILES:
        raise ValueError(
            f"{profile!r} is not a known profile; expected one of "
            f"{', '.join(PROFILES)}")

    attr = _ATTR[profile]
    url = (getattr(config, attr, "") or "").strip()
    if not url:
        raise DatabaseUnavailable(f"{attr} is not set. {_HOWTO[profile]}")

    if not url.startswith("postgresql+psycopg://"):
        raise DatabaseUnavailable(
            f"{attr} must start with postgresql+psycopg:// -- got "
            f"{url.split('://', 1)[0]}://")

    # A prod-ro URL naming the owning role is a write connection to production
    # wearing a read-only label. Refuse it here rather than trusting whoever
    # exported it.
    if profile == "prod-ro" and "://swingbot_ro:" not in url:
        raise DatabaseUnavailable(
            "DATABASE_URL_PROD_RO must connect as swingbot_ro. The URL given "
            "names a different role, which would be a WRITE connection to "
            "production. Re-read what `make db-tunnel` printed.")
    return url


def engine_for(profile: str | None = None) -> Engine:
    """An engine for `profile`, cached.

    Deliberately NOT engine.get_engine(): that is the running application's
    single pool against its own database, and every store goes through it. An
    analysis tool repointing that singleton would make the bot read the
    snapshot too.
    """
    profile = profile or DEFAULT_PROFILE
    if profile in _engines:
        return _engines[profile]
    engine = create_engine(resolve_url(profile), pool_pre_ping=True,
                           pool_size=2, max_overflow=2, future=True)
    _engines[profile] = engine
    return engine


def reset_engines() -> None:
    """Dispose every profile engine. For tests, and for a changed URL."""
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
```

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_profiles.py
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/profiles.py swingbot/config.py .env.example \
        tests/db/test_profiles.py
git commit -m "feat(v67): add local/snapshot/prod-ro database profiles"
```

---

### Task P7-05: The bot never runs against a non-local profile

Profiles exist for analysis. The running bot and admin must use `local` and
nothing else — a bot writing into a snapshot would produce alerts against data
that is not its own, and a bot pointed at `prod-ro` would fail every write in a
way that takes a while to diagnose.

**Files:**
- Modify: `swingbot/core/db/engine.py`
- Modify: `bot.py`, `admin_ui.py` (one startup assertion each)
- Test: `tests/db/test_profile_isolation.py`

**Interfaces:**
- Consumes: `profiles` (P7-04).
- Produces: `engine.assert_application_database() -> None`, called at startup.

**Belt and braces on top of the role.** P7-01 makes Postgres refuse a
`prod-ro` write. This makes the bot refuse to *start* against it, so the
failure is one clear line at boot instead of a permission error at the first
trade — which would happen hours later, during a session, on a write that
mattered.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_profile_isolation.py`:

```python
"""The application uses `local` and nothing else."""
import pytest

from swingbot import config
from swingbot.core.db import engine as dbengine


@pytest.fixture(autouse=True)
def _clean():
    dbengine.reset_engine()
    yield
    dbengine.reset_engine()


def test_a_local_url_is_accepted(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot:p@db:5432/swingbot")
    dbengine.assert_application_database()


def test_a_readonly_role_is_refused(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot_ro:p@localhost:55434/swingbot")
    with pytest.raises(dbengine.DatabaseUnavailable, match="read-only"):
        dbengine.assert_application_database()


def test_the_snapshot_database_is_refused(monkeypatch):
    """A bot writing into a snapshot posts alerts against data that is not
    its own, and nothing about that is visible from the outside."""
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot:p@localhost:5432/swingbot_snapshot")
    with pytest.raises(dbengine.DatabaseUnavailable, match="snapshot"):
        dbengine.assert_application_database()


def test_the_tunnel_port_is_refused(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot:p@localhost:55434/swingbot")
    with pytest.raises(dbengine.DatabaseUnavailable, match="tunnel"):
        dbengine.assert_application_database()


def test_the_test_database_is_refused(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot:p@localhost:55432/swingbot_test")
    with pytest.raises(dbengine.DatabaseUnavailable, match="test"):
        dbengine.assert_application_database()


def test_the_error_says_what_to_do(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL",
                        "postgresql+psycopg://swingbot_ro:p@localhost:55434/swingbot")
    with pytest.raises(dbengine.DatabaseUnavailable) as exc:
        dbengine.assert_application_database()
    assert "DATABASE_URL" in str(exc.value)


@pytest.mark.parametrize("entry", ["bot.py", "admin_ui.py"])
def test_the_entry_point_calls_it(entry):
    import pathlib
    repo = pathlib.Path(__file__).resolve().parents[2]
    text = (repo / entry).read_text(encoding="utf-8")
    assert "assert_application_database" in text, (
        f"{entry} does not assert its database at startup")
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/db/test_profile_isolation.py -q
```

Expected: `AttributeError: module ... has no attribute 'assert_application_database'`.

- [ ] **Step 3: Write the assertion**

Append to `swingbot/core/db/engine.py`:

```python
#: Markers that mean "this URL is not the application's own database".
#: Belt and braces on top of the swingbot_ro role: Postgres already refuses a
#: read-only write, but that surfaces as a permission error hours later on a
#: write that mattered. This makes it one line at boot instead.
_NOT_APPLICATION = (
    ("://swingbot_ro:", "a read-only analysis role"),
    ("_snapshot", "the snapshot database (a copy of production)"),
    (":55434/", "the production read-only tunnel"),
    (":55432/", "the test database"),
    ("_test", "the test database"),
)


def assert_application_database() -> None:
    """Refuse to start against anything but the application's own database.

    Called from bot.py and admin_ui.py at startup. A bot writing into a
    snapshot posts alerts against data that is not its own, and nothing about
    that is visible from the outside until someone compares two databases.
    """
    url = (config.DATABASE_URL or "").strip()
    for marker, description in _NOT_APPLICATION:
        if marker in url:
            raise DatabaseUnavailable(
                f"DATABASE_URL points at {description}, which the bot and "
                f"admin must never run against. Analysis tools select a "
                f"database with --profile (see swingbot/core/db/profiles.py); "
                f"DATABASE_URL is the application's own database only."
            )
```

- [ ] **Step 4: Call it at startup**

In `bot.py` and `admin_ui.py`, immediately after config loads and before
anything opens a connection:

```python
from swingbot.core.db.engine import assert_application_database

assert_application_database()
```

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/db/test_profile_isolation.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/db/engine.py bot.py admin_ui.py \
        tests/db/test_profile_isolation.py
git commit -m "feat(v67): refuse to start the bot against a non-local database"
```

---

### Task P7-06: A read-only query tool

`cat data/trades.json | jq '.[] | select(.ticker=="AAPL")'` was how a question
got answered. This is the replacement, and it works against any profile.

**Files:**
- Create: `scripts/db/query.py`
- Modify: `Makefile`
- Test: `tests/scripts/test_query_tool.py`

**Interfaces:**
- Consumes: `profiles.engine_for` (P7-04).
- Produces: `run_query(sql, profile=None, fmt="table") -> str` and a CLI:

```bash
python scripts/db/query.py "select ticker, status from trades limit 5"
python scripts/db/query.py --profile snapshot --format csv "select * from trades"
python scripts/db/query.py --profile prod-ro "select count(*) from trades"
```

**It refuses anything but a single SELECT.** Not because a developer cannot be
trusted with SQL, but because this tool is the one that will be pointed at
`prod-ro` and at a snapshot people care about, and "I meant to run that against
local" is a real sentence. `psql` remains available for anyone who wants the
sharp version.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_query_tool.py`:

```python
"""The read-only query tool."""
import pytest

from swingbot import config
from scripts.db.query import UnsafeQuery, run_query


@pytest.fixture
def seeded(monkeypatch, db_engine, db_committed):
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db import profiles
    profiles.reset_engines()
    from swingbot.core.db.repositories.trades import TradeRepository
    with db_committed.begin():
        TradeRepository().insert(dict(
            trade_id="Q1", ticker="AAPL", strategy="RSI", horizon="2w",
            direction="bullish", status="open",
            opened_at="2026-01-02T15:00:00+00:00"), conn=db_committed)
    yield
    profiles.reset_engines()


def test_a_select_returns_rows(seeded):
    out = run_query("select trade_id, ticker from trades")
    assert "Q1" in out and "AAPL" in out


def test_csv_output(seeded):
    out = run_query("select trade_id from trades", fmt="csv")
    assert out.splitlines()[0].strip() == "trade_id"
    assert "Q1" in out


def test_json_output(seeded):
    import json
    rows = json.loads(run_query("select trade_id from trades", fmt="json"))
    assert rows == [{"trade_id": "Q1"}]


def test_an_empty_result_is_not_an_error(seeded):
    out = run_query("select trade_id from trades where trade_id = 'nope'")
    assert "0 row" in out or out.strip() != ""


@pytest.mark.parametrize("sql", [
    "delete from trades",
    "update trades set status = 'win'",
    "insert into trades (trade_id) values ('x')",
    "drop table trades",
    "truncate trades",
    "create table x (i int)",
    "alter table trades add column x int",
    "grant select on trades to public",
])
def test_a_write_is_refused(seeded, sql):
    with pytest.raises(UnsafeQuery):
        run_query(sql)


def test_a_second_statement_is_refused(seeded):
    """`select 1; delete from trades` must not reach the server."""
    with pytest.raises(UnsafeQuery, match="one statement"):
        run_query("select 1; delete from trades")


def test_a_trailing_semicolon_is_fine(seeded):
    run_query("select trade_id from trades;")


def test_a_cte_select_is_allowed(seeded):
    out = run_query("with x as (select trade_id from trades) select * from x")
    assert "Q1" in out


def test_a_writing_cte_is_refused(seeded):
    with pytest.raises(UnsafeQuery):
        run_query("with x as (delete from trades returning 1) select * from x")


def test_an_unknown_profile_raises(seeded):
    with pytest.raises(ValueError, match="not a known profile"):
        run_query("select 1", profile="production")
```

`test_a_writing_cte_is_refused` is the one a naive "does it start with SELECT"
check gets wrong, which is why it is here.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scripts/test_query_tool.py -q
```

Expected: `ModuleNotFoundError: No module named 'scripts.db.query'`.

- [ ] **Step 3: Write it**

Create `scripts/db/query.py`:

```python
#!/usr/bin/env python3
"""Run a read-only SQL query against any database profile.

The replacement for `cat data/trades.json | jq`.

    python scripts/db/query.py "select ticker, status from trades limit 5"
    python scripts/db/query.py --profile snapshot --format csv "select * from trades"
    python scripts/db/query.py --profile prod-ro "select count(*) from trades"

Refuses anything but a single SELECT. Not because SQL needs supervision, but
because this is the tool that gets pointed at prod-ro and at a snapshot someone
cares about, and "I meant to run that against local" is a real sentence. Use
psql when you want the sharp version.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import sqlalchemy as sa                                     # noqa: E402

from swingbot.core.db import profiles                       # noqa: E402


class UnsafeQuery(ValueError):
    """The query is not a single read-only statement."""


# Word-boundary matched so a column named `update_reason` or a string literal
# containing "insert" does not trip it -- and applied to the whole statement,
# not just its first word, because a writing CTE starts with SELECT... or
# rather with WITH, and ends in a DELETE.
_WRITE = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|"
    r"comment|copy|vacuum|reindex|call|do)\b", re.I)


def check_readonly(sql: str) -> str:
    """Return the statement, or raise UnsafeQuery."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise UnsafeQuery("empty query")
    if ";" in stripped:
        raise UnsafeQuery(
            "pass one statement at a time -- `select 1; delete from trades` "
            "is two, and the second is why this check exists")
    if not re.match(r"^\s*(select|with|table|explain|show)\b", stripped, re.I):
        raise UnsafeQuery(f"only SELECT is allowed here; got: {stripped[:40]!r}")
    match = _WRITE.search(stripped)
    if match:
        raise UnsafeQuery(
            f"{match.group(0).upper()} found in a query this tool will not "
            f"run. Use psql if you mean it.")
    return stripped


def _format(rows: list[dict], columns: list[str], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(rows, indent=2, default=str)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in columns})
        return buf.getvalue()
    if not rows:
        return "(0 rows)\n"
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows))
              for c in columns}
    line = "  ".join(c.ljust(widths[c]) for c in columns)
    out = [line, "  ".join("-" * widths[c] for c in columns)]
    for row in rows:
        out.append("  ".join(str(row.get(c, "")).ljust(widths[c])
                             for c in columns))
    out.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return "\n".join(out) + "\n"


def run_query(sql: str, profile: str | None = None, fmt: str = "table",
              limit: int | None = None) -> str:
    statement = check_readonly(sql)
    engine = profiles.engine_for(profile)
    with engine.connect() as conn:
        # A read-only transaction, so even a server-side function that tried
        # to write is refused. Cheap, and it makes the guarantee not depend on
        # the regex above being exhaustive.
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        result = conn.execute(sa.text(statement))
        columns = list(result.keys())
        rows = [dict(zip(columns, r)) for r in
                (result.fetchmany(limit) if limit else result.fetchall())]
    return _format(rows, columns, fmt)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sql")
    ap.add_argument("--profile", choices=profiles.PROFILES,
                    default=profiles.DEFAULT_PROFILE)
    ap.add_argument("--format", dest="fmt", choices=("table", "csv", "json"),
                    default="table")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)
    try:
        sys.stdout.write(run_query(args.sql, args.profile, args.fmt, args.limit))
    except UnsafeQuery as exc:
        print(f"query: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`SET TRANSACTION READ ONLY` is the belt to the regex's braces: it makes the
guarantee hold even where the pattern does not, which matters because a regex
over SQL is never exhaustive.

- [ ] **Step 4: Add a Makefile shortcut**

```make
# make db-query Q="select count(*) from trades"
db-query:
	python scripts/db/query.py "$(Q)"
```

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scripts/test_query_tool.py
python scripts/db/query.py "select count(*) from trades"
python scripts/db/query.py "delete from trades"     # expect a refusal, exit 2
```

Expected: `0 failed`, a count, then `query: DELETE found in a query this tool
will not run.`

- [ ] **Step 6: Commit**

```bash
git add scripts/db/query.py Makefile tests/scripts/test_query_tool.py
git commit -m "feat(v67): add a read-only cross-profile query tool"
```

---

**Continue with `2026-08-29-v67-json-to-postgres_7b-datasets.md`**
(P7-07…P7-12): DataFrame accessors for analysis and training, dataset export,
the backtest bridge, the local-dev quickstart, and Part 7's verification.
