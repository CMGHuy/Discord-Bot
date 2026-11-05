"""Pins the database service's security and startup dependencies."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
COMPOSE = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


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


def test_db_healthcheck_uses_pg_isready(compose):
    assert any("pg_isready" in str(part) for part in compose["services"]["db"]["healthcheck"]["test"])


@pytest.mark.parametrize("service", ["bot", "admin"])
def test_application_services_wait_for_a_healthy_database(compose, service):
    assert compose["services"][service]["depends_on"]["db"] == {
        "condition": "service_healthy"
    }


def test_every_published_port_binds_to_loopback(compose):
    # Docker-published ports bypass UFW: anything not on 127.0.0.1 is public.
    published = [
        (name, port)
        for name, service in compose["services"].items()
        for port in service.get("ports", [])
    ]
    assert ("admin", "127.0.0.1:${ADMIN_PORT:-1234}:${ADMIN_PORT:-1234}") in published
    assert all(str(port).startswith("127.0.0.1:") for _, port in published), published


def test_admin_writes_env_versions_into_the_host_backups(compose):
    assert "./backups/env:/app/backups/env" in compose["services"]["admin"]["volumes"]


DEPLOY = COMPOSE.parent / "deploy" / "deploy.sh"


def test_refresher_runs_its_own_entry_point_off_the_bot_image(compose):
    bot, refresher = compose["services"]["bot"], compose["services"]["refresher"]
    assert refresher["image"] == bot["image"]
    assert refresher["command"] == ["python", "-m", "swingbot.refresher"]
    assert refresher["container_name"] == "swing-refresher"
    assert refresher["restart"] == "unless-stopped"
    assert refresher["env_file"] == bot["env_file"]
    assert refresher["healthcheck"]["test"] == bot["healthcheck"]["test"]


def test_refresher_mounts_exactly_the_bot_state(compose):
    # Same daily-cache volume as bot and admin (spec Operations): the FX pair
    # files it refreshes, and the bars v204's snapshot job will read.
    assert compose["services"]["refresher"]["volumes"] == compose["services"]["bot"]["volumes"]


def test_refresher_is_capped_and_never_built_or_published(compose):
    refresher = compose["services"]["refresher"]
    assert refresher["cpus"] == "0.5" and refresher["mem_limit"] == "1g"
    assert "build" not in refresher and "ports" not in refresher


def test_deploy_verifies_the_refresher_runs_the_pulled_image():
    src = DEPLOY.read_text(encoding="utf-8")
    # v201: the list is probed (refresher only when the image has the module)
    assert 'SERVICES="bot admin refresher"' in src
    assert "for svc in $SERVICES; do" in src
    assert "for svc in bot admin; do" not in src
