"""journal_entries.doc.excursion_source: label every measured entry "daily"

v228 V228-7. Before v228 every journal MFE/MAE/exit-efficiency figure was
measured on daily bars; from v228 each entry records which bars measured it
in the doc field `excursion_source` ("5min", "15min", "hourly" or "daily").
This revision stamps "daily" on every existing entry that has an `mfe_r` and
no source, so no reader ever has to treat a missing source as anything
(docs/claude/schema-evolution.md: no read-time upcasting).

Rows left unlabelled on purpose:
- `mfe_r` is an explicit JSON null (no bars covered the trade at close):
  there is no daily figure to label, and the v228 upgrade pass may still
  measure it on intraday bars later.
- the entry already names a source (written by v228 code before this ran).

The downgrade is a no-op: stripping the field would also strip the intraday
sources the upgrade pass writes after this revision, and a re-upgrade would
then label those intraday numbers "daily". Older code keeps unknown doc
fields, so leaving the field in place is safe (ROLLBACK_SAFE below).

Revision ID: v228_001
Revises: v208_001
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "v228_001"
down_revision = "v208_001"
branch_labels = None
depends_on = None

ROLLBACK_SAFE = (
    "older code never reads the journal doc field excursion_source and keeps "
    "unknown doc fields on read and patch (v116 unknown-field round-trip); the "
    "one loss is that older code re-journaling a trade upserts the entry "
    "without excursion_source, which the v228 upgrade pass re-derives"
)

log = logging.getLogger("alembic.runtime.migration")

_STAMP = sa.text(
    "UPDATE journal_entries "
    "SET doc = doc || jsonb_build_object('excursion_source', 'daily') "
    "WHERE doc->>'mfe_r' IS NOT NULL AND doc->'excursion_source' IS NULL")


def stamp(conn) -> int:
    """Label every measured, unlabelled journal entry "daily"; rows stamped."""
    return conn.execute(_STAMP).rowcount


def upgrade() -> None:
    stamped = stamp(op.get_bind())
    log.info("v228_001: stamped %d journal entry row(s) excursion_source=daily", stamped)


def downgrade() -> None:
    """No-op by design: see the module docstring and ROLLBACK_SAFE."""
