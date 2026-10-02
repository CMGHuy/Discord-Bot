"""Real-PostgreSQL fixtures with fast transaction-rollback isolation."""
import hashlib
import os
import pathlib

import pytest
import sqlalchemy as sa
from sqlalchemy import exc as sa_exc

from swingbot.core.db.events import TABLE_CHANNELS
from swingbot.core.db.schema import METADATA

MAX_IDENTIFIER_BYTES = 63
DEFAULT_TEST_URL = "postgresql+psycopg://swingbot:swingbot@127.0.0.1:55432/swingbot_test"


def test_database_url() -> str:
    """URL for the disposable Compose test database."""
    return os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_URL)


def _checkout_token(root: pathlib.Path | None = None) -> str:
    """Short stable token for this checkout, from its resolved absolute path.

    The test container is shared by every checkout and concurrent session on the
    machine; without a per-checkout token two suite runs use the same database
    names and wipe each other.  Derived from ``__file__``, never the cwd."""
    root = root if root is not None else pathlib.Path(__file__).resolve().parents[2]
    return hashlib.sha1(root.resolve().as_posix().encode()).hexdigest()[:8]


def _database_name(base: str, token: str, worker: str | None, suffix: str = "") -> str:
    """``<base>_<token>[_<worker>][<suffix>]`` within Postgres' 63-byte limit.

    Only the BASE is truncated when too long: the token carries uniqueness and
    the worker/suffix carry purpose, so none of them may be cut."""
    tail = f"_{token}" + (f"_{worker}" if worker else "") + suffix
    return base[: max(1, MAX_IDENTIFIER_BYTES - len(tail.encode()))] + tail


def _create_database(base_url: sa.engine.URL, name: str) -> None:
    """Create ``name`` if absent; tolerate a concurrent process creating it first."""
    admin = sa.create_engine(base_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 2})
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                sa.text("select 1 from pg_database where datname = :name"), {"name": name},
            ).scalar()
            if not exists:
                try:
                    connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
                except sa_exc.ProgrammingError as exc:
                    if "already exists" not in str(exc):
                        raise
    finally:
        admin.dispose()


def _worker_database(url: str, suffix: str = "") -> str:
    """This checkout's database for this xdist worker (plus a purpose suffix).

    Every session drops and recreates ``public``; workers sharing a database
    race on the catalog (``pg_type_typname_nsp_index`` unique violations), and so
    do checkouts sharing one.  Names are ``<db>_<token>[_gw<N>][suffix]``, always
    created on first use; the admin connection stays on the BASE database."""
    base = sa.engine.make_url(url)
    name = _database_name(base.database, _checkout_token(), os.getenv("PYTEST_XDIST_WORKER"), suffix)
    _create_database(base, name)
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
def db_engine_empty():
    """A schema-free engine for migration tests that create the schema themselves.

    It gets its OWN database (``..._empty``): dropping ``public`` in the database the
    store tests share would delete the tables the session-scoped ``db_engine`` created
    once, and every later store test on that worker would fail on a missing relation."""
    engine = _connect_or_skip(test_database_url(), "_empty")
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    yield engine
    engine.dispose()


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
    yield engine
    engine.dispose()


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
