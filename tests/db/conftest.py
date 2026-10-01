"""Real-PostgreSQL fixtures with fast transaction-rollback isolation."""
import os

import pytest
import sqlalchemy as sa

from swingbot.core.db.events import TABLE_CHANNELS
from swingbot.core.db.schema import METADATA

DEFAULT_TEST_URL = "postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/swingbot_test"


def test_database_url() -> str:
    """URL for the disposable Compose test database."""
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_URL)


def _worker_database(url: str, suffix: str = "") -> str:
    """One database per xdist worker, optionally one more per purpose.

    Every session drops and recreates ``public``; workers sharing a database
    race on the catalog (``pg_type_typname_nsp_index`` unique violations), so
    under ``-n 4`` each gets ``<db>_gw<N>``, created on first use.  ``suffix``
    carves a further private database (``<db>[_gw<N>]_<suffix>``) for a fixture
    whose schema must not be disturbed by -- or disturb -- ``db_engine``'s.
    """
    base = sa.engine.make_url(url)
    worker = os.getenv("PYTEST_XDIST_WORKER")
    name = "_".join(part for part in (base.database, worker, suffix) if part)
    if name == base.database:
        return url
    admin = sa.create_engine(base, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2})
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                sa.text("select 1 from pg_database where datname = :name"), {"name": name},
            ).scalar()
            if not exists:
                connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    return base.set(database=name).render_as_string(hide_password=False)


def _connect_or_skip(url: str, suffix: str = "") -> sa.Engine:
    # A developer who has not started the optional service must not pay the
    # driver default TCP timeout for every database test.  The runner already
    # gives the exact start command; this is only its fast safety net.
    engine = None
    try:
        engine = sa.create_engine(
            _worker_database(url, suffix),
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
        )
        with engine.connect() as connection:
            connection.execute(sa.text("select 1"))
    except Exception as exc:  # noqa: BLE001 - connection failures all share one remedy
        if engine is not None:
            engine.dispose()
        pytest.skip(
            f"test database unreachable at {url}: {exc}\n"
            "Start it with: docker compose --profile test up -d db-test"
        )
    return engine


@pytest.fixture(scope="session")
def _migrations_engine():
    """One engine for the migrations database, kept for the whole session.

    That database is separate from ``db_engine``'s: ``db_engine`` builds its
    schema with ``create_all`` (no ``alembic_version`` row), so sharing one
    database made a later ``upgrade head`` collide with those tables.
    """
    engine = _connect_or_skip(test_database_url(), "migrations")
    yield engine
    engine.dispose()


@pytest.fixture
def db_engine_empty(_migrations_engine):
    """A schema-free engine for migration tests that create the schema themselves.

    The schema is reset before every test, so each one starts from nothing and
    must run ``upgrade head`` itself.
    """
    with _migrations_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    return _migrations_engine


# Engines handed out by ``db_engine``, so the autouse cleanup below can reach
# them without instantiating the fixture (a test skipped because the database
# is unreachable must not error in teardown).
_BUILT_ENGINES: dict[str, sa.Engine] = {}


@pytest.fixture(scope="session")
def db_engine():
    """An engine with the declared schema created once per test session."""
    engine = _connect_or_skip(test_database_url())
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    METADATA.create_all(engine)
    from swingbot.core.db.notify import NOTIFY_FUNCTION_SQL, trigger_ddl
    with engine.begin() as connection:
        connection.execute(sa.text(NOTIFY_FUNCTION_SQL))
        for table, channel in TABLE_CHANNELS.items():
            connection.execute(sa.text(trigger_ddl(table, channel)))
    _BUILT_ENGINES["db_engine"] = engine
    yield engine
    _BUILT_ENGINES.pop("db_engine", None)
    engine.dispose()


@pytest.fixture(autouse=True)
def _empty_tables_after_db_tests(request):
    """Truncate every declared table after any test that used ``db_engine``.

    Rows committed through the app engine (outside ``db_conn``'s rollback)
    otherwise reach whatever test runs next on the same worker.  Tests that
    never touch the database pay one list lookup.
    """
    yield
    if "db_engine" not in request.fixturenames:
        return
    engine = _BUILT_ENGINES.get("db_engine")
    names = ", ".join(table.name for table in METADATA.sorted_tables)
    if engine is not None and names:
        with engine.begin() as connection:
            connection.execute(sa.text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_conn(db_engine):
    """A transaction that is rolled back after every test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()


@pytest.fixture
def db_committed(db_engine):
    """A committing connection for notification tests, cleaned by truncation."""
    connection = db_engine.connect()
    try:
        yield connection
    finally:
        connection.rollback()
        names = ", ".join(table.name for table in METADATA.sorted_tables)
        if names:
            with connection.begin():
                connection.execute(sa.text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        connection.close()


@pytest.fixture
def store_db(db_committed, db_engine, monkeypatch):
    """Stage-aware code under test reaches the test database through the
    app's own engine (config.DATABASE_URL); every table is truncated after
    the test by db_committed. Yields the committing connection for asserts."""
    from swingbot import config
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield db_committed
    reset_engine()
