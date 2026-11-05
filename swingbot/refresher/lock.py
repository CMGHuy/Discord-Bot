"""v201: one refresher at a time. A session-level advisory lock held on one
dedicated connection for as long as the block runs; a second container during a
compose recreate gets False and fetches nothing."""
from contextlib import contextmanager
from typing import Iterator

import sqlalchemy as sa

from swingbot.core.db import engine

ADVISORY_LOCK_KEY = 201001


@contextmanager
def single_instance() -> Iterator[bool]:
    conn = engine.get_engine().connect()
    held = False
    try:
        held = bool(conn.execute(sa.text("SELECT pg_try_advisory_lock(:k)"),
                                 {"k": ADVISORY_LOCK_KEY}).scalar())
        conn.commit()
        yield held
    finally:
        if held:
            conn.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
            conn.commit()
        conn.close()
