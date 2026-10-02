#!/usr/bin/env python3
"""Import data/settings_audit.jsonl into the settings_audit table."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlalchemy as sa  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.db.engine import get_engine  # noqa: E402
from swingbot.core.db.repositories.settings_audit import SettingsAuditRepository  # noqa: E402
from swingbot.core.db.schema import settings_audit  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    """Entries in file order; a torn trailing line is skipped, not fatal."""
    return part3_sources.audit_rows(path or os.path.join(config.DATA_DIR, "settings_audit.jsonl"))


def prepare(repo) -> None:
    """The log has no natural key, so a rerun replaces the table rather than appending."""
    with get_engine().begin() as connection:
        connection.execute(sa.delete(settings_audit))


def write_one(repo, record: dict) -> None:
    repo.append(record["changes"], ts=record["ts"])


def main(argv=None) -> int:
    return run_import(sys.argv[1:] if argv is None else argv, load_source=load_source,
                      write_one=write_one, repo=SettingsAuditRepository(), key="seq",
                      name="settings_audit", prepare=prepare)


if __name__ == "__main__":
    raise SystemExit(main())
