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


def test_it_pins_env_only_after_compose_up_succeeds_and_before_the_record(src):
    """.env must always equal the running images: a failed pull/up under
    set -e must leave the old pin in place."""
    up = src.index("docker compose up -d --no-build --wait")
    pin_bot = src.index('env_set.py SWING_BOT_IMAGE "$IMAGE"')
    pin_db = src.index('env_set.py SWING_BOT_DB_IMAGE "$DB_IMAGE"')
    record = src.index(">> backups/deploys.jsonl")
    assert up < pin_bot < pin_db < record
    assert "sed -i" not in src


def test_it_records_the_deploy_right_after_the_containers_switch(src):
    up = src.index("docker compose up -d --no-build --wait")
    record = src.index(">> backups/deploys.jsonl")
    smoke = src.index("smoke_spa.py --from-config")
    assert up < record < smoke
    assert "git rev-parse HEAD" in src


def test_the_record_is_one_json_line_and_an_append_failure_only_warns(src):
    fmt = ('printf ' + chr(39) + '{"ts":"%s","git_sha":"%s","bot_image":"%s","db_image":"%s"}'
           + chr(92) + 'n' + chr(39) + ' ' + chr(92))
    assert fmt in src
    tail = src[src.index(">> backups/deploys.jsonl"):].split(chr(10))[0]
    assert '|| echo "WARNING: could not append deploys.jsonl" >&2' in tail


def _chown_block(src):
    start = src.index("mkdir -p backups/env backups/pitr")
    return src[start:src.index("python3 scripts/ops/env_set.py", start)]


def test_it_prepares_backup_dirs_before_any_snapshot_or_compose_up(src):
    """Docker creates a missing bind-mount source root-owned, which would make
    env snapshots (deploy user) and pgbackrest archive-push (uid 70) fail."""
    mk = src.index("mkdir -p backups/env backups/pitr")
    up = src.index("docker compose up -d --no-build --wait")
    first_pin = src.index("env_set.py SWING_BOT_IMAGE")
    assert mk < up < first_pin
    block = _chown_block(src)
    assert "chmod 700 backups/env" in block
    assert "chown 70:70 backups/pitr" in block
    assert "sudo -n chown 70:70 backups/pitr" in block


def test_chown_failure_is_fatal_when_archiving_is_on_else_a_loud_warning(src):
    block = _chown_block(src)
    assert "2>/dev/null" not in block          # the reason must reach stderr
    assert 'PG_ARCHIVE_MODE' in block
    fatal = block.index("exit 1")
    warn = block.index("WARNING")
    on_check = block.index('= "on"')
    assert on_check < fatal and "exit 1" not in block[warn:]


def test_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()
