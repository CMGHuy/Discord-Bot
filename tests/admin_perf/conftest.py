"""Fixtures for the v205 admin read-performance tests (suite `admin-perf`).

The app, client, auth header and the admin suite's autouse pins are tests/admin's,
imported not copied (DATA_DIR isolation, module reloads, the seeded 10,000 account,
the refresher pinned off). The tests live here because the admin suite sits at its
max_tests cap (precedent: tests/live_api/conftest.py)."""
import pytest

from tests.admin.conftest import (  # noqa: F401
    _clear_login_limiter, _pin_admin_refresher_off, admin_app, auth, client)


@pytest.fixture
def sql_counted(db_engine):
    """The admin's statement counter on the test engine.

    In tests `engine.get_engine` is the autouse lazy lookup (tests/conftest.py
    `_store_database`), so the admin's engine hook never sees `db_engine`; attach
    the listener to it directly. Idempotent, and inert outside a request."""
    from swingbot.admin import request_timing
    request_timing._attach(db_engine)
    return db_engine
