"""Pins the database service's security and startup dependencies."""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")
COMPOSE = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_db_service_is_a_pinned_postgres_18_with_a_named_volume(compose):
    db = compose["services"]["db"]
    assert db["image"] == "postgres:18-alpine"
    assert "pgdata" in compose["volumes"]
    assert any(volume.startswith("pgdata:") for volume in db["volumes"])
    assert "ports" not in db


def test_db_healthcheck_uses_pg_isready(compose):
    assert any("pg_isready" in str(part) for part in compose["services"]["db"]["healthcheck"]["test"])


@pytest.mark.parametrize("service", ["bot", "admin"])
def test_application_services_wait_for_a_healthy_database(compose, service):
    assert compose["services"][service]["depends_on"]["db"] == {
        "condition": "service_healthy"
    }
