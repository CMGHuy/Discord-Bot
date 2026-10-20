"""plans.status_history: re-tag the 2026-09-30 bulk clear as manual_bulk

v173 §2. On 2026-09-30 20:54-20:55 UTC one bulk "close open" ran through the
same `_close_plan` as a single close and recorded reason "manual" on 15
plans. A bulk clear is not a decision, and the override-fidelity report must
not count it as one. This revision sets the terminal status_history entry's
reason to "manual_bulk" on exactly the 15 plan ids pinned below (from a
read-only production SELECT, recorded in the v173 plan index) and on
nothing else.

Refusals raise RuntimeError before anything is written:
- some, but not all, of the pinned plans exist;
- a pinned plan's last status_history entry is not
  {"status": "CLOSED", "reason": <from>}.
A database holding none of the pinned plans (a fresh install, the test
database, a dev fixture book) is not the production book: one log line,
nothing written, so `alembic upgrade head` still works there. Downgrade is
the exact reverse over the same 15 entries.

Revision ID: v173_001
Revises: v171_001
"""
from __future__ import annotations

import copy
import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "v173_001"
down_revision = "v171_001"   # = python -m alembic heads on main at release (V173-17); v173_002 chains on v173_001
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Copied verbatim from the v173 plan index, § Pinned bulk-clear ids (V173-4).
PINNED_PLAN_IDS: tuple[str, ...] = (
    "fc6f5a54-9911-4e6f-87e8-64fb157e7fe8",  # ABNB 2026-09-30T20:54:08.198635+00:00
    "9e60f623-8f4c-4d21-851a-20bd81e18911",  # ADBE 2026-09-30T20:54:09.605131+00:00
    "42d752e2-413b-44ea-a432-814e0258aa5c",  # GLW 2026-09-30T20:54:11.460717+00:00
    "e60436d2-12e8-4163-a825-c530e4873ac7",  # AMD 2026-09-30T20:54:12.748735+00:00
    "6369c662-6ca7-4b28-be13-cb79bc401474",  # XAUUSD 2026-09-30T20:54:14.990983+00:00
    "4fae973d-52a0-4959-b6f8-6cd40276255f",  # STX 2026-09-30T20:54:16.410449+00:00
    "fb6d5ff9-cf3d-48e4-bc8b-1fe1166af091",  # GM 2026-09-30T20:54:17.899056+00:00
    "02df69da-86ce-4e4c-a721-a5f86a83580e",  # GEV 2026-09-30T20:54:21.301654+00:00
    "b48202d7-7d3a-4f81-8f80-fa7d6e66b6cf",  # CEG 2026-09-30T20:54:29.245966+00:00
    "fe08cb81-dcf7-444f-9d27-94374e1aa5b1",  # SNOW 2026-09-30T20:54:33.740533+00:00
    "839a8283-f232-4c58-8586-1108b95c17ad",  # BA 2026-09-30T20:54:40.702872+00:00
    "220afd69-841f-42bc-9d55-1c1a8448fb55",  # PEP 2026-09-30T20:54:50.206798+00:00
    "d4578fd4-2ecf-4ad2-a93e-cf0417d78511",  # ASTS 2026-09-30T20:54:55.833270+00:00
    "0cbf5e60-165a-4e96-aaaa-e8948c6d9416",  # RKLB 2026-09-30T20:55:08.008858+00:00
    "f6431f11-7298-44a2-8dfc-aed1a8a87614",  # MSTR 2026-09-30T20:55:15.216261+00:00
)

# FOR UPDATE: the 15 rows stay locked from the check to the write (one transaction).
_SELECT = sa.text(
    "SELECT plan_id, doc->'status_history' AS hist FROM plans WHERE plan_id = ANY(:ids) FOR UPDATE")
_UPDATE = sa.text(
    "UPDATE plans SET doc = jsonb_set(doc, '{status_history}', CAST(:hist AS jsonb)) "
    "WHERE plan_id = :plan_id")


def _terminal_is(history, reason: str) -> bool:
    """True when `history`'s last entry is a CLOSED transition with `reason`."""
    if not isinstance(history, list) or not history:
        return False
    last = history[-1]
    return (isinstance(last, dict) and last.get("status") == "CLOSED"
            and last.get("reason") == reason)


def retag(histories: dict[str, list], *, frm: str, to: str) -> dict[str, list]:
    """New status_history lists for every pinned plan, terminal reason `frm`
    -> `to`. Raises RuntimeError, naming the ids, when a pinned id is missing
    from `histories` or its terminal entry is not CLOSED/`frm`. Never mutates
    `histories`."""
    missing = [pid for pid in PINNED_PLAN_IDS if pid not in histories]
    if missing:
        raise RuntimeError(f"v173_001: pinned plans missing: {missing}")
    wrong = [pid for pid in PINNED_PLAN_IDS if not _terminal_is(histories[pid], frm)]
    if wrong:
        raise RuntimeError(
            f"v173_001: last status_history entry is not CLOSED/{frm!r} for {wrong}")
    out: dict[str, list] = {}
    for pid in PINNED_PLAN_IDS:
        history = copy.deepcopy(list(histories[pid]))
        history[-1]["reason"] = to
        out[pid] = history
    return out


def _as_list(value):
    """A jsonb value as Python: psycopg decodes it already; text is parsed."""
    return json.loads(value) if isinstance(value, str) else value


def apply(conn, *, frm: str, to: str) -> int:
    """Re-tag the pinned plans on `conn`; returns the rows written. Every
    check runs before the first write."""
    rows = conn.execute(_SELECT, {"ids": list(PINNED_PLAN_IDS)}).fetchall()
    histories = {row[0]: _as_list(row[1]) for row in rows}
    if not histories:
        log.info("v173_001: none of the %d pinned plans exist here (not the production "
                 "book); nothing to re-tag", len(PINNED_PLAN_IDS))
        return 0
    changed = retag(histories, frm=frm, to=to)
    for pid, history in changed.items():
        conn.execute(_UPDATE, {"hist": json.dumps(history), "plan_id": pid})
    log.info("v173_001: re-tagged %d plans %s -> %s", len(changed), frm, to)
    return len(changed)


def upgrade() -> None:
    apply(op.get_bind(), frm="manual", to="manual_bulk")


def downgrade() -> None:
    apply(op.get_bind(), frm="manual_bulk", to="manual")
