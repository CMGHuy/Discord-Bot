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


def test_admin_writes_env_versions_into_the_host_backups(compose):
    assert "./backups/env:/app/backups/env" in compose["services"]["admin"]["volumes"]
