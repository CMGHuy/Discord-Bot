"""The DB fixtures stay isolated from each other and from earlier tests.

Both checks run pytest in a subprocess against a private database: the
failures they guard depend on fixture ORDER inside one process, which the
parent run's own ordering (and xdist's worker assignment) cannot pin down.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from tests.db import conftest as db_conftest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def private_database_url():
    """A throwaway database on the test server, dropped afterwards."""
    base = sa.engine.make_url(db_conftest.test_database_url())
    name = f"{base.database}_isolation_{uuid.uuid4().hex[:12]}"
    admin = sa.create_engine(base, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2})
    try:
        with admin.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # noqa: BLE001 - any connection failure shares one remedy
        admin.dispose()
        pytest.skip(f"test database unreachable: {exc}")
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            # The child also creates ``<name>_migrations`` for db_engine_empty.
            for doomed in (name, f"{name}_migrations"):
                connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{doomed}" WITH (FORCE)'))
        admin.dispose()


def _run_child(url: str, *targets: str) -> subprocess.CompletedProcess:
    # A child that inherited PYTEST_XDIST_* would think it is a worker and
    # move to a ``_gwN`` database instead of the private one.
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST_")}
    env["TEST_DATABASE_URL"] = url
    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-p", "no:cacheprovider", "-p", "no:randomly", "-q"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=300,
    )


def test_migration_tests_pass_when_run_after_each_other(private_database_url):
    """db_engine_empty used to share a database with db_engine, so a later
    upgrade-to-head hit tables that carried no alembic_version row."""
    result = _run_child(
        private_database_url, "tests/db/test_migrations.py", "tests/db/test_trigger_coverage.py",
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]


def test_a_committed_row_does_not_reach_the_next_test(private_database_url):
    """Tests that commit through the app engine used to leave their rows
    behind for whatever ran next on the same worker."""
    result = _run_child(private_database_url, "tests/db/isolation_cases/case_leak.py")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
