# v116 — Part 1a: Phase 0, point-in-time rollback (V116-01 … V116-05)

Header, global constraints, revision ids and the full parallelisation map: `_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-09-30-v116-postgres-cutover-pitr-design.md` § Phase 0.

**This phase lands and is drilled before any store flips to `db`.**

**Parallelisation (Phase 0):**
- **Wave 1 (parallel):** V116-01, V116-07. Disjoint files: V116-01 owns `Dockerfile.db`, `deploy/db/pgbackrest.conf`, `docker-compose.yml`, `.gitignore`, `tests/db/test_compose.py`; V116-07 owns `swingbot/core/infra/pitr_watch.py`, `swingbot/commands/scanning/{loops,notices}.py`.
- **Wave 2 (parallel, after V116-01):** V116-02 (names the `Dockerfile.db` and `deploy/db/pgbackrest.conf` that V116-01 creates), V116-03 (edits `docker-compose.yml` after V116-01), V116-08 (runs the V116-01 image). Disjoint files among the three.
- **Wave 3 (parallel, after V116-03):** V116-04 (`deploy/deploy.sh`) and V116-05 (`scripts/ops/*` crons, `backup_db.sh`, `hetzner-setup.sh`). Both call `env_set.py` and `swingbot.core.infra.env_snapshot`, which V116-03 creates.
- **Sequential:** V116-06 after V116-05 (calls `restic_hourly.sh`). V116-09 after every other Phase 0 task (it ships them). V116-10 after V116-09 (runs on the deployed image and stanza).

Before the first task of this phase, if the worktree does not exist yet:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-09-30-v116-postgres-cutover-pitr -b 2026-09-30-v116-postgres-cutover-pitr origin/main
```

Every command below runs from the worktree root unless it says otherwise.

---

# Phase 0 — Point-in-time rollback

### Task V116-01: Postgres image with pgBackRest, wired into Compose

**Files:**
- Create: `Dockerfile.db`
- Create: `deploy/db/pgbackrest.conf`
- Modify: `docker-compose.yml` (the `db` service)
- Modify: `.gitignore` (add `/backups/`)
- Modify: `tests/db/test_compose.py` (the image assertion)
- Create: `tests/scripts/test_pitr_db_image.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Dockerfile.db` (build context `.`); `deploy/db/pgbackrest.conf` with stanza `swingbot`, repo path `/var/lib/pgbackrest`; Compose variables `SWING_BOT_DB_IMAGE` (default `swing-bot-db:local`) and `PG_ARCHIVE_MODE` (default `off`); host bind mount `./backups/pitr:/var/lib/pgbackrest`. V116-02 hashes the two build files into the tag; V116-08 and V116-09 run the image.

- [ ] **Step 1: Write the failing tests**

Replace `test_db_service_is_a_pinned_postgres_18_with_a_named_volume` in `tests/db/test_compose.py` with:

```python
def test_db_service_runs_the_pgbackrest_image_with_a_named_volume(compose):
    db = compose["services"]["db"]
    assert db["image"] == "${SWING_BOT_DB_IMAGE:-swing-bot-db:local}"
    assert db["build"] == {"context": ".", "dockerfile": "Dockerfile.db"}
    assert "pgdata" in compose["volumes"]
    assert any(volume.startswith("pgdata:") for volume in db["volumes"])
    assert "ports" not in db


def test_db_archives_wal_into_the_host_pitr_repo(compose):
    db = compose["services"]["db"]
    assert "./backups/pitr:/var/lib/pgbackrest" in db["volumes"]
    command = " ".join(db["command"])
    # Off unless production's .env says on: a dev box or CI with no stanza
    # would otherwise pile WAL up on its own disk.
    assert "archive_mode=${PG_ARCHIVE_MODE:-off}" in command
    assert "archive_command=pgbackrest --stanza=swingbot archive-push %p" in command
    assert "archive_timeout=300" in command


def test_the_test_database_stays_plain_postgres(compose):
    assert compose["services"]["db-test"]["image"] == "postgres:18-alpine"
```

Create `tests/scripts/test_pitr_db_image.py`:

```python
"""The PITR database image's build inputs (v116 Phase 0).

They cannot be built in the unit suite, so what is pinned is what a broken
edit would remove: the major version, pgBackRest itself, and the retention
that makes "any second in the last 30 days" true.
"""
import configparser
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "Dockerfile.db"
CONF = REPO / "deploy" / "db" / "pgbackrest.conf"


@pytest.fixture(scope="module")
def conf():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(CONF.read_text(encoding="utf-8"))
    return parser


def test_the_image_pins_postgres_18_and_adds_pgbackrest():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM postgres:18-alpine$", text, re.M)
    assert "apk add --no-cache pgbackrest" in text
    assert "COPY deploy/db/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf" in text


def test_retention_keeps_thirty_days_of_point_in_time_history(conf):
    assert conf["global"]["repo1-retention-full-type"] == "time"
    assert conf["global"]["repo1-retention-full"] == "30"


def test_compression_is_on(conf):
    # Every forced WAL switch archives a 16 MB segment; uncompressed, the
    # archive does not fit the disk (spec § Postgres).
    assert conf["global"]["compress-type"] in {"gz", "lz4", "zst", "bz2"}


def test_the_repo_is_the_bind_mounted_path_and_the_stanza_is_pg18(conf):
    assert conf["global"]["repo1-path"] == "/var/lib/pgbackrest"
    assert conf["swingbot"]["pg1-path"] == "/var/lib/postgresql/18/docker"
    assert conf["swingbot"]["pg1-user"] == "swingbot"


def test_the_backups_directory_is_never_committed():
    lines = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/backups/" in lines


@pytest.mark.parametrize("path", [DOCKERFILE, CONF])
def test_lf_line_endings(path):
    assert b"\r" not in path.read_bytes()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/db/test_compose.py tests/scripts/test_pitr_db_image.py`
Expected: FAIL — `KeyError: 'build'` / `FileNotFoundError: Dockerfile.db`.

- [ ] **Step 3: Create `Dockerfile.db`**

```dockerfile
# Postgres with pgBackRest for point-in-time recovery (v116 Phase 0).
#
# The major version is pinned: a major upgrade is a pg_upgrade, not a tag
# bump. CI tags this image by the content hash of this file and
# deploy/db/pgbackrest.conf and never re-pushes an existing tag, so a tag in
# backups/deploys.jsonl always names the same bytes. To pick up a new
# postgres:18 patch release, change REBUILD.
FROM postgres:18-alpine
ARG REBUILD=2026-09-30
RUN apk add --no-cache pgbackrest \
 && mkdir -p /var/lib/pgbackrest /var/log/pgbackrest /var/spool/pgbackrest \
 && chown -R postgres:postgres /var/lib/pgbackrest /var/log/pgbackrest /var/spool/pgbackrest
COPY deploy/db/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
```

- [ ] **Step 4: Create `deploy/db/pgbackrest.conf`**

```ini
# pgBackRest for the swingbot database (v116 Phase 0).
# repo1 is the host bind mount /opt/swing-bot/backups/pitr, OUTSIDE pgdata:
# losing the database volume must not lose its history.
[global]
repo1-path=/var/lib/pgbackrest
# Time-based: keep as many full backups as it takes for 30 days of PITR.
repo1-retention-full-type=time
repo1-retention-full=30
compress-type=gz
start-fast=y
log-level-console=info
log-level-file=off

[swingbot]
# postgres:18 images keep PGDATA one level down from the volume root.
pg1-path=/var/lib/postgresql/18/docker
pg1-user=swingbot
pg1-database=swingbot
```

- [ ] **Step 5: Rewire the `db` service in `docker-compose.yml`**

Replace the line `    image: postgres:18-alpine` under `db:` (the `db-test` service keeps its own) with the block below, and add the second volume line under the existing `- pgdata:/var/lib/postgresql`:

```yaml
    # v116: postgres:18-alpine + pgBackRest (Dockerfile.db). Production pins
    # the GHCR tag in .env (deploy.sh writes it); locally `make up` builds it.
    image: ${SWING_BOT_DB_IMAGE:-swing-bot-db:local}
    build:
      context: .
      dockerfile: Dockerfile.db
    # WAL archiving for point-in-time recovery. PG_ARCHIVE_MODE is `on` only
    # in production's .env; anywhere without a pgBackRest stanza, archiving
    # would fail and WAL would pile up on the local disk.
    command:
      - postgres
      - -c
      - archive_mode=${PG_ARCHIVE_MODE:-off}
      - -c
      - archive_command=pgbackrest --stanza=swingbot archive-push %p
      - -c
      - archive_timeout=300
```

```yaml
      - ./backups/pitr:/var/lib/pgbackrest   # pgBackRest repo, outside pgdata (v116)
```

- [ ] **Step 6: Ignore the host backups directory**

Append to the "Data directories" block of `.gitignore`:

```
# v116 point-in-time recovery: pgBackRest repo, .env versions, restic repo,
# deploys.jsonl. VM-only; never committed.
/backups/
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/db/test_compose.py tests/scripts/test_pitr_db_image.py`
Expected: PASS.

- [ ] **Step 8: Confirm the two facts the config relies on, against the real images**

Run: `docker run --rm postgres:18-alpine sh -c 'echo $PGDATA; id postgres'`
Expected: `/var/lib/postgresql/18/docker` and `uid=70(postgres) gid=70(postgres)`. If PGDATA differs, fix `pg1-path` (and the drill in V116-08) before continuing.

Run: `docker build -f Dockerfile.db -t swing-bot-db:local . && docker run --rm swing-bot-db:local pgbackrest version`
Expected: `pgBackRest 2.` followed by a version. Then `docker compose config --quiet` exits 0.

- [ ] **Step 9: Commit**

```bash
git add Dockerfile.db deploy/db/pgbackrest.conf docker-compose.yml .gitignore tests/db/test_compose.py tests/scripts/test_pitr_db_image.py
git commit -m "feat(v116): postgres image with pgBackRest and WAL archiving behind PG_ARCHIVE_MODE

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-02: CI publishes the db image; GHCR keeps tags 45 days

**Files:**
- Modify: `.github/workflows/deploy.yml` (new `db-image` job; `deploy` job `needs`/`envs`/`env`)
- Modify: `.github/workflows/registry-retention.yml` (`cut-off`, `image-names`)
- Create: `tests/dev/test_ci_db_image.py`

**Interfaces:**
- Consumes: `Dockerfile.db`, `deploy/db/pgbackrest.conf` (V116-01).
- Produces: GHCR package `ghcr.io/<owner>/<repo>-db`, tag `pgcfg-<first 12 hex of sha256(Dockerfile.db ‖ deploy/db/pgbackrest.conf)>`; job output `needs.db-image.outputs.image`; the deploy SSH step exports `SWING_BOT_DB_IMAGE` to `deploy.sh` (V116-04 reads it).

- [ ] **Step 1: Record the GHCR retention as found**

Run: `grep -n "cut-off\|keep-n-most-recent\|image-names" .github/workflows/registry-retention.yml`
Expected (found while planning, 2026-09-30): `cut-off: 14d`, `keep-n-most-recent: 10`, `image-names: ${{ github.event.repository.name }}`. Also run `gh api "/users/$(gh repo view --json owner -q .owner.login)/packages/container/$(gh repo view --json name -q .name | tr '[:upper:]' '[:lower:]')/versions" --paginate --jq '.[-1].created_at'` to see the oldest retained version (if the token lacks `read:packages`, note that and rely on the workflow value). Write both values into this task's commit message body. 14 days is short of the 30-day window; this task raises it.

- [ ] **Step 2: Write the failing test**

```python
"""CI builds the PITR db image, the deploy receives it, and GHCR keeps
every tag long enough for a 30-day rollback (v116 Phase 0)."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_a_job_builds_the_db_image_from_its_own_inputs():
    job = _load("deploy.yml")["jobs"]["db-image"]
    text = yaml.safe_dump(job)
    assert "Dockerfile.db" in text
    assert "deploy/db/pgbackrest.conf" in text
    assert "pgcfg-" in text
    # Immutable once pushed: an existing tag is never rebuilt over.
    assert "docker manifest inspect" in text


def test_the_deploy_waits_for_and_passes_the_db_image():
    deploy = _load("deploy.yml")["jobs"]["deploy"]
    assert "db-image" in deploy["needs"]
    step = deploy["steps"][0]
    assert "SWING_BOT_DB_IMAGE" in step["with"]["envs"]
    assert step["env"]["SWING_BOT_DB_IMAGE"] == "${{ needs.db-image.outputs.image }}"


def test_ghcr_retention_covers_the_rollback_window_for_both_images():
    step = _load("registry-retention.yml")["jobs"]["prune"]["steps"][0]
    cut = step["with"]["cut-off"]
    assert cut.endswith("d") and int(cut[:-1]) >= 30
    assert "-db" in step["with"]["image-names"]
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/dev/test_ci_db_image.py`
Expected: FAIL — `KeyError: 'db-image'`.

- [ ] **Step 4: Add the `db-image` job to `.github/workflows/deploy.yml`**

Insert after the `docker-build` job (before `# ── 3b. Container health`):

```yaml
  # ── 3a'. Postgres image (v116 PITR) ─────────────────────────────────────────
  # postgres:18-alpine + pgBackRest. Tagged by the content hash of its two
  # build inputs, NOT by commit: a per-commit tag would recreate the database
  # container on every push to main. A tag that already exists is never
  # rebuilt or re-pushed, so a tag recorded in backups/deploys.jsonl always
  # names the same bytes (to take a new postgres:18 patch, bump REBUILD in
  # Dockerfile.db).
  db-image:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image: ${{ steps.dbtag.outputs.image }}
    steps:
      - uses: actions/checkout@v7

      - name: Resolve the db image tag from its build inputs
        id: dbtag
        run: |
          IMAGE="ghcr.io/$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')-db"
          TAG="pgcfg-$(cat Dockerfile.db deploy/db/pgbackrest.conf | sha256sum | cut -c1-12)"
          echo "image=$IMAGE:$TAG" >> "$GITHUB_OUTPUT"
          echo "Resolved $IMAGE:$TAG"

      - name: Log in to GHCR
        if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build, and push unless the tag already exists
        run: |
          REF="${{ steps.dbtag.outputs.image }}"
          if docker manifest inspect "$REF" >/dev/null 2>&1; then
            echo "Already published: $REF -- not rebuilt"
            exit 0
          fi
          docker build -f Dockerfile.db -t "$REF" .
          if [ "${{ github.ref }}" = "refs/heads/main" ] && [ "${{ github.event_name }}" != "pull_request" ]; then
            docker push "$REF"
            echo "Pushed $REF"
          fi
```

In the `deploy` job: change `needs: [docker-build, container-healthcheck, cleanup, compose-lint]` to `needs: [docker-build, db-image, container-healthcheck, cleanup, compose-lint]`; change `envs: SWING_BOT_IMAGE,APP_DIR` to `envs: SWING_BOT_IMAGE,SWING_BOT_DB_IMAGE,APP_DIR`; and add under its `env:` (next to `SWING_BOT_IMAGE`):

```yaml
          # v116: the PITR db image this run resolved. deploy.sh pins it in
          # .env and records it in backups/deploys.jsonl.
          SWING_BOT_DB_IMAGE: ${{ needs.db-image.outputs.image }}
```

- [ ] **Step 5: Raise GHCR retention and cover the db package**

In `.github/workflows/registry-retention.yml`, rename the step to `Delete image versions older than 45 days` and set:

```yaml
          # v116: rollback_to.sh pulls the tag that was live at the target
          # second, up to 30 days back, and that image may itself be older than
          # the target. 45 days covers the window plus that age; rollback_to.sh
          # still refuses a tag GHCR no longer has.
          image-names: "${{ github.event.repository.name }}, ${{ github.event.repository.name }}-db"
          cut-off: 45d
```

Check `image-names` syntax against the `snok/container-retention-policy@v3.1.0` README (it documents a comma-separated list with wildcard support). If the README says otherwise, split into two steps, one per package, and adjust the test's third assertion to read both steps.

- [ ] **Step 6: Run the test, and the existing CI-invocation test**

Run: `python scripts/dev/testrun.py file tests/dev/test_ci_db_image.py tests/dev/test_testrun_ci_invocations.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/deploy.yml .github/workflows/registry-retention.yml tests/dev/test_ci_db_image.py
git commit -m "ci(v116): publish the pgBackRest db image; keep GHCR tags 45 days

GHCR retention found 2026-09-30: cut-off 14d, keep-n-most-recent 10
(<oldest retained version from Step 1>).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-03: `.env` versions — snapshot helper, admin save hook, in-place `env_set.py`

**Files:**
- Create: `swingbot/core/infra/env_snapshot.py`
- Modify: `swingbot/admin/helpers.py:99` (`_write_env_text`)
- Modify: `docker-compose.yml` (`admin` volumes)
- Create: `scripts/ops/env_set.py`
- Modify: `.env.example` (commented placeholders in `# --- Database ---`)
- Create: `tests/infra/test_env_snapshot.py`, `tests/admin/test_settings_env_snapshot.py`, `tests/scripts/test_env_set.py`
- Modify: `tests/db/test_compose.py` (admin mount)

**Interfaces:**
- Consumes: nothing.
- Produces: `env_snapshot.STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S-%fZ"`, `env_snapshot.SUFFIX = ".env"`, `snapshot_dir(env_path) -> str` (`<dir of env_path>/backups/env`), `snapshot_names(directory) -> list[str]` (sorted), `stamp_of(name) -> datetime | None`, `take_snapshot(env_path, *, now=None) -> str | None`, `snapshot_quietly(env_path) -> None`, `prune(directory, keep_days=30, now=None) -> list[str]`, CLI `python3 -m swingbot.core.infra.env_snapshot {snapshot <env>|prune <dir> <days>}`. `scripts/ops/env_set.py`: `set_value(text, key, value) -> str`, `get_value(text, key) -> str | None`, `write_in_place(path, text) -> None`, CLI `python3 scripts/ops/env_set.py [--env PATH] KEY VALUE` and `--get KEY`. Used by V116-04/05/06/08/09 and every Phase 3 flip.

- [ ] **Step 1: Write the failing tests**

`tests/infra/test_env_snapshot.py`:

```python
"""Versioned .env copies for point-in-time rollback (v116 Phase 0)."""
import ast
import datetime as dt
import os
import pathlib
import sys

from swingbot.core.infra import env_snapshot as es

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)


def _env(tmp_path, text="A=1\n"):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_first_snapshot_copies_the_file_under_backups_env(tmp_path):
    out = es.take_snapshot(str(_env(tmp_path)), now=T0)
    assert out == str(tmp_path / "backups" / "env" / "2026-10-01T10-00-00-000000Z.env")
    assert pathlib.Path(out).read_text(encoding="utf-8") == "A=1\n"


def test_unchanged_content_takes_no_second_snapshot(tmp_path):
    env = _env(tmp_path)
    es.take_snapshot(str(env), now=T0)
    assert es.take_snapshot(str(env), now=T0 + dt.timedelta(hours=1)) is None
    assert len(es.snapshot_names(es.snapshot_dir(str(env)))) == 1


def test_changed_content_takes_a_new_snapshot_that_sorts_last(tmp_path):
    env = _env(tmp_path)
    es.take_snapshot(str(env), now=T0)
    env.write_text("A=2\n", encoding="utf-8")
    es.take_snapshot(str(env), now=T0 + dt.timedelta(microseconds=5))
    names = es.snapshot_names(es.snapshot_dir(str(env)))
    assert len(names) == 2
    newest = pathlib.Path(es.snapshot_dir(str(env))) / names[-1]
    assert newest.read_text(encoding="utf-8") == "A=2\n"


def test_a_missing_env_is_not_an_error(tmp_path):
    assert es.take_snapshot(str(tmp_path / ".env")) is None


def test_stamp_of_round_trips_the_file_name():
    assert es.stamp_of("2026-10-01T10-00-00-000123Z.env") == T0.replace(microsecond=123)
    assert es.stamp_of("notes.txt") is None


def test_prune_keeps_the_newest_snapshot_older_than_the_window(tmp_path):
    directory = tmp_path / "backups" / "env"
    directory.mkdir(parents=True)
    names = ["2026-08-01T00-00-00-000000Z.env", "2026-08-15T00-00-00-000000Z.env",
             "2026-09-20T00-00-00-000000Z.env"]
    for name in names:
        (directory / name).write_text(name, encoding="utf-8")
    removed = es.prune(str(directory), keep_days=30, now=dt.datetime(2026, 10, 1, tzinfo=UTC))
    # 08-15 is the version that was live when the 30-day window opened.
    assert removed == [str(directory / names[0])]
    assert es.snapshot_names(str(directory)) == names[1:]


def test_cli_snapshot_then_prune(tmp_path, capsys):
    env = _env(tmp_path)
    assert es.main(["snapshot", str(env)]) == 0
    assert es.main(["prune", es.snapshot_dir(str(env)), "30"]) == 0
    assert len(es.snapshot_names(es.snapshot_dir(str(env)))) == 1


def test_the_module_is_stdlib_only():
    """It runs as `python3 -m` on the VM host, where no requirement is installed."""
    tree = ast.parse(pathlib.Path(es.__file__).read_text(encoding="utf-8"))
    roots = {alias.name.split(".")[0] for node in ast.walk(tree)
             if isinstance(node, ast.Import) for alias in node.names}
    roots |= {node.module.split(".")[0] for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module}
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}, roots
```

`tests/admin/test_settings_env_snapshot.py`:

```python
"""A settings save leaves a .env version behind (v116 Phase 0)."""
from swingbot.admin import helpers
from swingbot.core.infra import env_snapshot


def test_writing_env_text_snapshots_before_and_after(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    helpers._write_env_text("A=2\n")
    directory = tmp_path / "backups" / "env"
    contents = [(directory / name).read_text(encoding="utf-8")
                for name in env_snapshot.snapshot_names(str(directory))]
    assert contents == ["A=1\n", "A=2\n"]


def test_a_snapshot_failure_never_fails_the_save(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(env_snapshot, "take_snapshot", boom)
    helpers._write_env_text("A=2\n")
    assert env.read_text(encoding="utf-8") == "A=2\n"
```

`tests/scripts/test_env_set.py`:

```python
"""scripts/ops/env_set.py: one KEY=value, in place, then a snapshot (v116)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import env_set  # noqa: E402


def test_replaces_an_existing_key():
    assert env_set.set_value("A=1\nB=2\n", "B", "3") == "A=1\nB=3\n"


def test_appends_a_missing_key_with_a_newline():
    assert env_set.set_value("A=1\n", "C", "x") == "A=1\nC=x\n"
    assert env_set.set_value("A=1", "C", "x") == "A=1\nC=x\n"


def test_replaces_every_duplicate_so_last_wins_still_holds():
    assert env_set.set_value("B=1\nB=2\n", "B", "9") == "B=9\nB=9\n"


def test_a_value_is_literal_not_a_regex_template():
    assert env_set.set_value("A=1\n", "A", r"x\1y") == "A=x\\1y\n"


def test_get_reads_the_last_value_without_quotes():
    assert env_set.get_value('B=1\nB="two"\n', "B") == "two"
    assert env_set.get_value("A=1\n", "Z") is None


def test_main_writes_in_place_and_snapshots(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    inode = os.stat(env).st_ino
    assert env_set.main(["--env", str(env), "A", "2"]) == 0
    assert env.read_text(encoding="utf-8") == "A=2\n"
    assert os.stat(env).st_ino == inode, "a rename breaks the single-file bind mount"
    assert len(list((tmp_path / "backups" / "env").iterdir())) == 2


def test_main_get_prints_the_value(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("RESTIC_PASSWORD=s3cret\n", encoding="utf-8")
    assert env_set.main(["--env", str(env), "--get", "RESTIC_PASSWORD"]) == 0
    assert capsys.readouterr().out == "s3cret\n"
```

Add to `tests/db/test_compose.py`:

```python
def test_admin_writes_env_versions_into_the_host_backups(compose):
    assert "./backups/env:/app/backups/env" in compose["services"]["admin"]["volumes"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_env_snapshot.py tests/admin/test_settings_env_snapshot.py tests/scripts/test_env_set.py tests/db/test_compose.py`
Expected: FAIL — `ImportError: cannot import name 'env_snapshot'`, `ModuleNotFoundError: env_set`.

- [ ] **Step 3: Create `swingbot/core/infra/env_snapshot.py`**

```python
"""Versioned copies of .env for point-in-time rollback (v116 Phase 0).

Every path that changes .env -- the admin settings save, deploy/deploy.sh and
scripts/ops/env_set.py -- leaves a copy at ``backups/env/<UTC ts>.env`` beside
the .env when its content changed, so scripts/ops/rollback_to.sh can put back
the .env that was live at any second of the last 30 days.

Stdlib only: the VM host runs it as ``python3 -m swingbot.core.infra.env_snapshot``
with no requirements installed. Copied, never rewritten: .env is a single-file
bind mount (known-traps.md, "Editing production .env with sed -i").
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import os
import shutil
import sys

log = logging.getLogger(__name__)

#: Fixed width with microseconds, so lexical order is time order and two
#: saves in one second never overwrite each other.
STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S-%fZ"
SUFFIX = ".env"


def snapshot_dir(env_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(env_path)), "backups", "env")


def stamp_of(name: str) -> dt.datetime | None:
    if not name.endswith(SUFFIX):
        return None
    try:
        parsed = dt.datetime.strptime(name[:-len(SUFFIX)], STAMP_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc)


def snapshot_names(directory: str) -> list[str]:
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    return sorted(name for name in names if stamp_of(name) is not None)


def _digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def take_snapshot(env_path: str, *, now: dt.datetime | None = None) -> str | None:
    """Copy ``env_path`` if it differs from the newest copy; return the new path."""
    if not os.path.isfile(env_path):
        return None
    directory = snapshot_dir(env_path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    names = snapshot_names(directory)
    if names and _digest(os.path.join(directory, names[-1])) == _digest(env_path):
        return None
    stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime(STAMP_FORMAT)
    target = os.path.join(directory, stamp + SUFFIX)
    shutil.copyfile(env_path, target)
    os.chmod(target, 0o600)
    return target


def snapshot_quietly(env_path: str) -> None:
    """take_snapshot for callers that must not fail: a save beats its history."""
    try:
        path = take_snapshot(env_path)
    except OSError:
        log.warning("could not snapshot %s", env_path, exc_info=True)
        return
    if path:
        log.info("snapshotted .env to %s", path)


def prune(directory: str, keep_days: int = 30, now: dt.datetime | None = None) -> list[str]:
    """Delete versions older than the window, except the newest of them:
    that one was live when the window opened, and a rollback to the window's
    first second needs it."""
    cutoff = (now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=keep_days)
    old = [name for name in snapshot_names(directory) if stamp_of(name) < cutoff]
    doomed = [os.path.join(directory, name) for name in old[:-1]]
    for path in doomed:
        os.remove(path)
    return doomed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="env_snapshot")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("env_path")
    pruner = sub.add_parser("prune")
    pruner.add_argument("directory")
    pruner.add_argument("days", type=int)
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        print(take_snapshot(args.env_path) or "unchanged")
        return 0
    for path in prune(args.directory, args.days):
        print(f"pruned {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Hook the admin save**

In `swingbot/admin/helpers.py`, add `from swingbot.core.infra import env_snapshot` to the imports, and make `_write_env_text` snapshot on both sides of the write (the "before" copy captures a hand edit made since the last snapshot):

```python
def _write_env_text(text: str) -> None:
    # (existing utf-8 comment block unchanged)
    env_snapshot.snapshot_quietly(ENV_PATH)
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            backup = f.read()
        with open(ENV_PATH + ".bak", "w", encoding="utf-8") as f:
            f.write(backup)
    parent = os.path.dirname(ENV_PATH) or "."
    fd, tmp = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=parent, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ENV_PATH)
    # v116: a version per save, so rollback_to.sh can restore the .env that
    # was live at any second. Never fails the save.
    env_snapshot.snapshot_quietly(ENV_PATH)
```

The test's `take_snapshot` monkeypatch raises `OSError`, which `snapshot_quietly` catches, so the save proceeds.

- [ ] **Step 5: Mount the snapshot directory into the admin container**

In `docker-compose.yml`, under `admin:` → `volumes:`, after `- ./.env.bak:/app/.env.bak`, add:

```yaml
      - ./backups/env:/app/backups/env   # v116: .env versions written on every settings save
```

- [ ] **Step 6: Create `scripts/ops/env_set.py`**

```python
#!/usr/bin/env python3
"""Set one KEY=value in the VM's .env IN PLACE, then snapshot it (v116).

In place means the same inode. .env is a single-file bind mount; a rename
(sed -i, most editors) leaves the running containers reading the old file
(docs/claude/known-traps.md). Stdlib only: it runs on the VM host.

    python3 scripts/ops/env_set.py DB_STORES 'flags:dual,heartbeat:dual'
    python3 scripts/ops/env_set.py --get DB_STORES

Then restart and verify inside the containers -- this script only edits.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from swingbot.core.infra import env_snapshot  # noqa: E402  (stdlib-only)


def _pattern(key: str) -> re.Pattern:
    return re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=.*$", re.M)


def set_value(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = _pattern(key)
    if pattern.search(text):
        return pattern.sub(lambda _match: line, text)
    separator = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{separator}{line}\n"


def get_value(text: str, key: str) -> str | None:
    matches = _pattern(key).findall(text)
    if not matches:
        return None
    value = matches[-1].split("=", 1)[1].strip()
    return value.strip("'\"")


def write_in_place(path: str, text: str) -> None:
    with open(path, "r+", encoding="utf-8") as handle:
        handle.seek(0)
        handle.write(text)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", default=os.path.join(ROOT, ".env"))
    parser.add_argument("--get", metavar="KEY")
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args(argv)
    with open(args.env, encoding="utf-8") as handle:
        text = handle.read()
    if args.get:
        print(get_value(text, args.get) or "")
        return 0
    if args.key is None or args.value is None:
        parser.error("pass KEY VALUE, or --get KEY")
    env_snapshot.snapshot_quietly(args.env)
    inode = os.stat(args.env).st_ino
    write_in_place(args.env, set_value(text, args.key, args.value))
    if os.stat(args.env).st_ino != inode:
        print("env_set: .env changed inode; restart the containers", file=sys.stderr)
        return 1
    env_snapshot.snapshot_quietly(args.env)
    print(f"env_set: {args.key} updated in place in {args.env}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Document the three VM-only keys in `.env.example`**

Directly after the `DB_STORES=` line in `# --- Database ---`, add (comments only: `tests/test_env_example_sync.py` rejects an assignment the schema does not define, the same reason `SWING_BOT_IMAGE` is a comment):

```
# Point-in-time recovery (v116). Read by docker-compose.yml and the VM's
# scripts/ops/ crons, not by swingbot/config.py -- so commented here, like
# SWING_BOT_IMAGE. Production sets all three (docs/deploy/DB_RESTORE.md);
# deploy.sh writes SWING_BOT_DB_IMAGE itself.
# PG_ARCHIVE_MODE=on
# SWING_BOT_DB_IMAGE=ghcr.io/<owner>/<repo>-db:pgcfg-<12 hex>
# RESTIC_PASSWORD=change-me
```

- [ ] **Step 8: Run the tests, plus the admin tests that exercise the save path**

Run: `python scripts/dev/testrun.py file tests/infra/test_env_snapshot.py tests/admin/test_settings_env_snapshot.py tests/scripts/test_env_set.py tests/db/test_compose.py tests/test_env_example_sync.py tests/test_helpers.py`
Expected: PASS.

- [ ] **Step 9: Complexity and commit**

Run: `python -m radon cc -s -n C swingbot/core/infra/env_snapshot.py swingbot/admin/helpers.py scripts/ops/env_set.py` — expect no output.

```bash
git add swingbot/core/infra/env_snapshot.py swingbot/admin/helpers.py docker-compose.yml .env.example tests/infra/test_env_snapshot.py tests/admin/test_settings_env_snapshot.py tests/scripts/test_env_set.py tests/db/test_compose.py
git add --chmod=+x scripts/ops/env_set.py
git commit -m "feat(v116): versioned .env snapshots on every change path; in-place env_set.py

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-04: `deploy.sh` pins both images in `.env` and records every deploy

**Files:**
- Modify: `deploy/deploy.sh` (after `export SWING_BOT_IMAGE="$IMAGE"`, the pull block, and after `docker compose up -d --no-build --wait`)
- Create: `tests/scripts/test_deploy_records.py`

**Interfaces:**
- Consumes: `scripts/ops/env_set.py` (V116-03), `SWING_BOT_DB_IMAGE` from CI (V116-02).
- Produces: `/opt/swing-bot/backups/deploys.jsonl`, one line per deploy: `{"ts": "<UTC Z>", "git_sha": "<40 hex>", "bot_image": "<ref>", "db_image": "<ref>"}`, appended right after the containers switch. `.env` keys `SWING_BOT_IMAGE`/`SWING_BOT_DB_IMAGE` always equal the running images. V116-06 reads both.

- [ ] **Step 1: Write the failing test**

```python
"""deploy.sh records what it deployed, for rollback_to.sh (v116 Phase 0).
It cannot run in the suite; the asserted properties are what an edit
would silently remove."""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "deploy.sh"


@pytest.fixture(scope="module")
def src():
    return SCRIPT.read_text(encoding="utf-8")


def test_it_resolves_exports_and_pulls_the_db_image(src):
    assert 'DB_IMAGE="${SWING_BOT_DB_IMAGE:-$(env_value SWING_BOT_DB_IMAGE)}"' in src
    assert 'export SWING_BOT_DB_IMAGE="$DB_IMAGE"' in src
    assert 'docker pull "$DB_IMAGE"' in src


def test_it_pins_both_images_in_env_in_place_before_starting(src):
    pin_bot = src.index('env_set.py SWING_BOT_IMAGE "$IMAGE"')
    pin_db = src.index('env_set.py SWING_BOT_DB_IMAGE "$DB_IMAGE"')
    up = src.index("docker compose up -d --no-build --wait")
    assert pin_bot < up and pin_db < up
    assert "sed -i" not in src


def test_it_records_the_deploy_right_after_the_containers_switch(src):
    up = src.index("docker compose up -d --no-build --wait")
    record = src.index(">> backups/deploys.jsonl")
    smoke = src.index("smoke_spa.py --from-config")
    assert up < record < smoke
    for key in ('"ts"', '"git_sha"', '"bot_image"', '"db_image"'):
        assert key in src
    assert "git rev-parse HEAD" in src


def test_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deploy_records.py`
Expected: FAIL — `ValueError: substring not found`.

- [ ] **Step 3: Resolve the db image** — insert directly after `export SWING_BOT_IMAGE="$IMAGE"`:

```bash
# v116: the PITR Postgres image (Dockerfile.db). CI passes it; a manual deploy
# falls back to the pin deploy.sh last wrote into .env.
DB_IMAGE="${SWING_BOT_DB_IMAGE:-$(env_value SWING_BOT_DB_IMAGE)}"
if [ -z "$DB_IMAGE" ]; then
  echo "No db image to deploy. CI passes SWING_BOT_DB_IMAGE; for a manual" >&2
  echo "deploy, take the last one recorded in backups/deploys.jsonl." >&2
  exit 1
fi
export SWING_BOT_DB_IMAGE="$DB_IMAGE"

# v116: .env is the record of what runs. Pinned in place (env_set.py never
# renames the bind-mounted file) and snapshotted, so rollback_to.sh and any
# later manual `docker compose up` see these exact tags -- never a stale pin
# left behind by an earlier rollback.
echo "==> Pinning the deployed images in .env"
python3 scripts/ops/env_set.py SWING_BOT_IMAGE "$IMAGE"
python3 scripts/ops/env_set.py SWING_BOT_DB_IMAGE "$DB_IMAGE"
```

- [ ] **Step 4: Pull it** — after `docker pull "$IMAGE"`:

```bash
echo "==> Pulling $DB_IMAGE"
docker pull "$DB_IMAGE"
```

- [ ] **Step 5: Record the deploy** — directly after the line `docker compose up -d --no-build --wait`:

```bash

# v116: the rollback index. Written the moment the containers switched --
# before verification, because a deploy that fails verification is still the
# one running, and rollback_to.sh resolves "what ran at second T" from here.
echo "==> Recording this deploy in backups/deploys.jsonl"
mkdir -p backups
printf '{"ts":"%s","git_sha":"%s","bot_image":"%s","db_image":"%s"}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(git rev-parse HEAD)" "$IMAGE" "$DB_IMAGE" \
  >> backups/deploys.jsonl
```

- [ ] **Step 6: Run the test and bash's syntax check**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deploy_records.py` — expected PASS.
Run: `bash -n deploy/deploy.sh` — expected no output.

- [ ] **Step 7: Commit**

```bash
git add deploy/deploy.sh tests/scripts/test_deploy_records.py
git commit -m "feat(v116): deploy.sh pins both images in .env and appends backups/deploys.jsonl

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task V116-05: Backup schedule — pgBackRest nightly, restic hourly, monthly verify, pg_dump 90 days

**Files:**
- Create: `scripts/ops/pitr_backup.sh`, `scripts/ops/restic_hourly.sh`, `scripts/ops/pitr_verify.sh`, `scripts/ops/install_pitr_crons.sh`
- Modify: `scripts/ops/backup_db.sh` (14 → 90 days)
- Modify: `deploy/hetzner-setup.sh:40` (install `restic python3`)
- Modify: `tests/scripts/test_backup_db.py` (the `"14"` assertion)
- Create: `tests/scripts/test_pitr_crons.py`

**Interfaces:**
- Consumes: `env_set.py --get` and `python3 -m swingbot.core.infra.env_snapshot prune` (V116-03).
- Produces: cron scripts; logs `logs/pitr_backup.log`, `logs/restic.log`, `logs/pitr_verify.log` (the last ends each run with `VERDICT <date> PASS|FAIL`); restic repo `backups/restic`, host `swing-bot`, tag `market_data`. V116-06 calls `scripts/ops/restic_hourly.sh` for its checkpoint.

- [ ] **Step 1: Write the failing tests**

In `tests/scripts/test_backup_db.py`, replace `test_it_prunes_by_age_not_by_count` with:

```python
def test_it_prunes_by_age_not_by_count(source):
    """90 DAYS (v116: day-level restores beyond the 30-day PITR window), not
    90 files: a day with three manual dumps must not evict older nightly ones."""
    assert "-mtime +90" in source
```

Create `tests/scripts/test_pitr_crons.py`:

```python
"""The v116 PITR cron scripts' shape. They run only on the VM; what is
pinned is what an edit would silently break."""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
NAMES = ["pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh", "install_pitr_crons.sh"]


def _text(name):
    return (OPS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_strict_mode_and_lf(name):
    assert "set -" in _text(name)
    assert b"\r" not in (OPS / name).read_bytes()
    assert "sed -i" not in _text(name)


def test_backup_is_full_on_sunday_and_differential_otherwise():
    text = _text("pitr_backup.sh")
    assert "TYPE=diff" in text and "TYPE=full" in text and "%u" in text
    assert 'pgbackrest --stanza=swingbot --type="$TYPE" backup' in text


def test_env_versions_are_pruned_after_the_backup():
    text = _text("pitr_backup.sh")
    assert text.index("backup </dev/null") < text.index("env_snapshot prune backups/env 30")


def test_restic_snapshots_market_data_and_keeps_thirty_days():
    text = _text("restic_hourly.sh")
    assert "restic backup" in text and "market_data" in text
    assert "--keep-within 30d --prune" in text
    assert "env_set.py --get RESTIC_PASSWORD" in text


def test_verify_checks_both_repos_and_prints_a_verdict():
    text = _text("pitr_verify.sh")
    assert "pgbackrest --stanza=swingbot verify" in text
    assert "restic check" in text
    assert "VERDICT" in text


def test_installer_is_idempotent_and_schedules_all_three():
    text = _text("install_pitr_crons.sh")
    assert "grep -vF" in text
    for name in ("pitr_backup.sh", "restic_hourly.sh", "pitr_verify.sh"):
        assert name in text


def test_the_vm_setup_installs_restic_and_python3():
    text = (REPO / "deploy" / "hetzner-setup.sh").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("apt-get install -y ca-certificates"))
    assert "restic" in line and "python3" in line
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_crons.py tests/scripts/test_backup_db.py`
Expected: FAIL — `FileNotFoundError` for the four scripts; `-mtime +90` absent.

- [ ] **Step 3: Create `scripts/ops/pitr_backup.sh`**

```bash
#!/usr/bin/env bash
# Nightly pgBackRest backup (v116 Phase 0): full on Sundays, differential on
# other days. pgBackRest applies repo1-retention-full=30 (time-based) itself,
# keeping 30 days of point-in-time history. Then .env versions older than 30
# days are pruned (the newest of them is kept: it was live when the window
# opened). Installed by install_pitr_crons.sh; logs to logs/pitr_backup.log.
set -euo pipefail
cd "$(dirname "$0")/../.."

TYPE=diff
if [ "$(date -u +%u)" = "7" ]; then
  TYPE=full
fi
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pgbackrest ${TYPE} ==="
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot --type="$TYPE" backup </dev/null
python3 -m swingbot.core.infra.env_snapshot prune backups/env 30
echo "=== done ==="
```

- [ ] **Step 4: Create `scripts/ops/restic_hourly.sh`**

```bash
#!/usr/bin/env bash
# Hourly restic snapshot of market_data/ (v116 Phase 0), then forget
# snapshots older than 30 days. The repo is local (backups/restic): this
# protects against a bad refresh or a bad rollback, not against losing the VM
# (spec § Honest limits). Installed by install_pitr_crons.sh.
set -euo pipefail
cd "$(dirname "$0")/../.."

RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
if [ -z "$RESTIC_PASSWORD" ]; then
  echo "restic_hourly: RESTIC_PASSWORD is not set in .env" >&2
  exit 1
fi
export RESTIC_PASSWORD
export RESTIC_REPOSITORY="$PWD/backups/restic"

echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) restic backup market_data ==="
restic backup --host swing-bot --tag market_data "$PWD/market_data"
restic forget --host swing-bot --tag market_data --keep-within 30d --prune
```

- [ ] **Step 5: Create `scripts/ops/pitr_verify.sh`**

```bash
#!/usr/bin/env bash
# Monthly proof that both PITR repos are readable (v116 Phase 0):
# `pgbackrest verify` and `restic check`. Ends with one VERDICT line.
# Installed by install_pitr_crons.sh; logs to logs/pitr_verify.log.
set -uo pipefail
cd "$(dirname "$0")/../.."

rc=0
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) pitr verify ==="
docker compose exec -T -u postgres db pgbackrest --stanza=swingbot verify </dev/null || rc=1
RESTIC_PASSWORD="$(python3 scripts/ops/env_set.py --get RESTIC_PASSWORD)"
export RESTIC_PASSWORD
export RESTIC_REPOSITORY="$PWD/backups/restic"
restic check || rc=1
if [ "$rc" = 0 ]; then
  echo "VERDICT $(date -u +%F) PASS"
else
  echo "VERDICT $(date -u +%F) FAIL"
fi
exit "$rc"
```

- [ ] **Step 6: Create `scripts/ops/install_pitr_crons.sh`**

```bash
#!/usr/bin/env bash
# Installs (idempotently) the v116 PITR crons on the Hetzner VM. Run ON the
# VM as root, from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_pitr_crons.sh
# backup_db.sh's own 03:00 line (installed 2026-09-30) is left alone.
set -euo pipefail

MARKER='# v116 PITR (installed by install_pitr_crons.sh)'
BASE=/opt/swing-bot
chmod +x "$BASE/scripts/ops/pitr_backup.sh" "$BASE/scripts/ops/restic_hourly.sh" \
         "$BASE/scripts/ops/pitr_verify.sh"
{
  crontab -l 2>/dev/null | grep -vF "$MARKER" \
    | grep -vE 'pitr_backup\.sh|restic_hourly\.sh|pitr_verify\.sh' || true
  echo "$MARKER"
  echo "30 2 * * * $BASE/scripts/ops/pitr_backup.sh >> $BASE/logs/pitr_backup.log 2>&1"
  echo "7 * * * * $BASE/scripts/ops/restic_hourly.sh >> $BASE/logs/restic.log 2>&1"
  echo "0 4 1 * * $BASE/scripts/ops/pitr_verify.sh >> $BASE/logs/pitr_verify.log 2>&1"
} | crontab -

echo "Installed crontab:"
crontab -l
```

- [ ] **Step 7: `backup_db.sh` to 90 days, restic on the VM**

In `scripts/ops/backup_db.sh`: header comment `pruning anything older than 14 days.` → `pruning anything older than 90 days.`; the next paragraph's `14 days, by age and not by count: it covers a bad change surviving a week unnoticed, and a day with three manual dumps must not evict two weeks of nightly ones.` → `90 days, by age and not by count (v116): day-level restores beyond the 30-day point-in-time window, and a day with three manual dumps must not evict older nightly ones.`; last line `-mtime +14` → `-mtime +90`.

In `deploy/hetzner-setup.sh:40`: `apt-get install -y ca-certificates curl gnupg git ufw` → `apt-get install -y ca-certificates curl gnupg git ufw restic python3`.

- [ ] **Step 8: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_pitr_crons.py tests/scripts/test_backup_db.py`
Expected: PASS. Also `for f in scripts/ops/pitr_backup.sh scripts/ops/restic_hourly.sh scripts/ops/pitr_verify.sh scripts/ops/install_pitr_crons.sh scripts/ops/backup_db.sh; do bash -n "$f"; done` — no output.

- [ ] **Step 9: Commit**

```bash
git add --chmod=+x scripts/ops/pitr_backup.sh scripts/ops/restic_hourly.sh scripts/ops/pitr_verify.sh scripts/ops/install_pitr_crons.sh
git add scripts/ops/backup_db.sh deploy/hetzner-setup.sh tests/scripts/test_backup_db.py tests/scripts/test_pitr_crons.py
git commit -m "feat(v116): PITR backup schedule -- pgBackRest nightly, restic hourly, monthly verify; pg_dump 90 days

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

