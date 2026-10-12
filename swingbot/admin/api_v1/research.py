"""GET /api/v1/research/ledger — the pre-registration ledger, read-only.

The ledger (`docs/superpowers/results/preregistration-ledger.jsonl`) is a
git-tracked record, not a runtime store: it ships inside the image, so what
this endpoint serves is **the ledger as of the deployed build**. A row
appended on `main` appears after the next deploy. Nothing here writes to it;
rows are appended only through `scripts/reports/preregistration_ledger.py`.

Each row gets three derived fields:

- `q` — its Benjamini-Hochberg q-value across every ledger row that has a
  p-value (`q_family_m` of them). Reported, never gating, and it mixes
  instruments by construction.
- `record_exists` / `record_kind` — whether the row's `record` path resolves
  in this deploy, and which docs folder it points into.

The whole ledger is returned (a few dozen rows); filtering, search and paging
are client-side. An invalid line makes `load_ledger` raise, and that surfaces
as a 500: a partial ledger would look complete.
"""
from __future__ import annotations

import os
from typing import Any

from flask import jsonify

from . import ApiError, api_v1
from .auth import require_auth

_RECORD_KINDS = ("results", "specs", "plans")


def _record_kind(record: str) -> str:
    parts = record.split("/")
    if len(parts) > 3 and parts[:2] == ["docs", "superpowers"] and parts[2] in _RECORD_KINDS:
        return parts[2]
    return "other"


def _record_exists(record: str, root: str) -> bool:
    parts = record.split("/")
    if os.path.isabs(record) or ".." in parts:
        return False
    return os.path.isfile(os.path.join(root, *parts))


def _enrich(row: dict, qvalues: dict, root: str) -> dict[str, Any]:
    return {
        **row,
        "q": qvalues.get(row["id"]),
        "record_exists": _record_exists(row["record"], root),
        "record_kind": _record_kind(row["record"]),
    }


@api_v1.route("/research/ledger", methods=["GET"])
@require_auth
def research_ledger():
    # Imported per request, like `analytics_registry` does with its reader.
    # `LEDGER_PATH` is read here, not bound as a default, so a test can point
    # the endpoint at a fixture ledger.
    from swingbot.core.backtesting.instrument import stats

    path = stats.LEDGER_PATH
    try:
        rows = stats.load_ledger(path)
    except ValueError as exc:
        raise ApiError("ledger_invalid", str(exc), 500) from exc

    # <root>/docs/superpowers/results/<ledger>: record paths are relative to
    # the tree the ledger itself lives in.
    root = str(path.parents[3])
    qvalues = stats.ledger_qvalues(rows)
    return jsonify({
        "rows": [_enrich(row, qvalues, root) for row in rows],
        "q_family_m": sum(1 for row in rows if row["p"] is not None),
        "verdicts": list(stats.VERDICTS),
        "instruments": list(stats.INSTRUMENTS),
    })
