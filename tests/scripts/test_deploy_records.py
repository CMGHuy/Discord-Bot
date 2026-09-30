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


def test_it_prepares_backup_dirs_before_any_snapshot_or_compose_up(src):
    """Docker creates a missing bind-mount source root-owned, which would make
    env snapshots (deploy user) and pgbackrest archive-push (uid 70) fail."""
    mk = src.index("mkdir -p backups/env backups/pitr")
    first_pin = src.index("env_set.py SWING_BOT_IMAGE")
    up = src.index("docker compose up -d --no-build --wait")
    assert mk < first_pin < up
    assert "chmod 700 backups/env" in src
    assert "70:70" in src and "backups/pitr" in src.split("70:70")[1].split("\n\n")[0]


def test_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()
