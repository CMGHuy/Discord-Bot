"""GET/POST /api/v1/jobs and /api/v1/analytics/tuning/proposals.

Jobs sit at the TOP level rather than under analytics/ (spec v11 Decision
4): a job is infrastructure for async work. Tuning happens to be the only
kind today, but the resource is about background execution, not analysis.

Proposals sit under analytics/ because a tuning proposal is an analytical
artefact -- spec 3 put Tuning in the Analytics workspace for the same
reason.

**The path-traversal guards are carried over verbatim, not re-derived.**
`job_id` and a proposal `filename` both flow from client input into a
filesystem path. Flask's URL converter rejects a literal '/' but NOT a
backslash -- and on Windows os.path.join treats '\' as a separator and a
drive-letter prefix as an absolute-path override that discards the
directory entirely. Without the allow-list regexes below, the delete route
is an arbitrary-file-delete primitive on a Windows host. The guards came
from the since-deleted pages.py, which documented them at length; the
reasoning applies here unchanged.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from flask import jsonify, request

from swingbot import config
from swingbot.admin.jobs import build_tune_args
from swingbot.admin.jobs import manager as job_manager

from . import api_v1, error
from .auth import require_auth


def _proposals_dir() -> str:
    from swingbot.admin.queries import TUNING_PROPOSALS_DIR_NAME
    return os.path.join(config.DATA_DIR, TUNING_PROPOSALS_DIR_NAME)


# --- jobs ----------------------------------------------------------------

@api_v1.route("/jobs", methods=["GET"])
@require_auth
def list_jobs():
    return jsonify({"jobs": job_manager.all()[:20]})


@api_v1.route("/jobs/<job_id>", methods=["GET"])
@require_auth
def get_job(job_id: str):
    """Status plus a log tail, so the SPA can show progress without a
    second round trip. Refetched on the `jobs` event (sub-project 2),
    replacing the Tuning page's polling."""
    from swingbot.admin.queries import _JOB_ID_RE

    if not _JOB_ID_RE.match(job_id):
        return error("invalid", "Invalid job id.", 400)
    status = job_manager.status(job_id)
    if not status:
        return error("not_found", f"No job with id {job_id!r}", 404)
    return jsonify({**status, "log_tail": job_manager.tail(job_id, n=50)})


@api_v1.route("/jobs/<job_id>/result", methods=["GET"])
@require_auth
def get_job_result(job_id: str):
    """A finished tuning job's grid, one row per parameter combination.

    SR51. The job has always written this file and `_load_result` has always
    read it, but only the Jinja page ever rendered it -- so the SPA could
    launch a grid and never see what it found, which also made the Propose
    action below unreachable by any route.

    `passes` is computed here rather than left to the client. The acceptance
    bar is four conditions (`_grid_row_passes`), it is the same bar
    `scripts/backtest/tune_strategy.py` prints, and a second copy of it in TypeScript
    is how the two would come to disagree about which rows are worth taking.
    """
    from swingbot.admin.queries import _JOB_ID_RE, _grid_row_passes, _load_result

    if not _JOB_ID_RE.match(job_id):
        return error("invalid", "Invalid job id.", 400)

    result = _load_result(job_id)
    if result is None:
        # Not an error: a job that is still running has no result yet, and a
        # 404 here would have the UI report a failure for the ordinary case of
        # "it has not finished". The caller distinguishes the two by the job's
        # own state, which it already has.
        return jsonify({"job_id": job_id, "strategy": None, "grid": []})

    grid = [
        {**row, "row_index": index, "passes": _grid_row_passes(row)}
        for index, row in enumerate(result.get("grid", []))
    ]
    return jsonify({
        "job_id": job_id,
        "strategy": result.get("strategy"),
        # The index is carried on the row because it is what POST /proposals
        # identifies a row by. Leaving the client to infer it from array
        # position would break the moment anything sorted or filtered the grid.
        "grid": grid,
    })


@api_v1.route("/jobs/tune", methods=["POST"])
@require_auth
def start_tune_job():
    payload = request.get_json(silent=True) or {}
    strategy = payload.get("strategy", "")
    params = payload.get("params")
    try:
        args = build_tune_args(strategy, params)
    except ValueError as exc:
        # build_tune_args also enforces TRAIN-only windows. A ValueError here
        # can mean "you asked to tune against the validation window", which
        # is a spent resource -- surface its message rather than a generic one.
        return error("invalid", str(exc), 400)
    try:
        job_id = job_manager.start("tune", args)
    except RuntimeError:
        return error("conflict", "Another job is already running.", 409)
    return jsonify({"job_id": job_id})


# --- tuning proposals ----------------------------------------------------

@api_v1.route("/analytics/tuning/proposals", methods=["GET"])
@require_auth
def list_proposals():
    from swingbot.admin.queries import _list_proposals

    return jsonify({"proposals": _list_proposals()})


@api_v1.route("/analytics/tuning/proposals", methods=["POST"])
@require_auth
def create_proposal():
    """Freeze one grid row from a finished tuning job into a proposal file.

    Deliberately NOT an "apply": the note written into the file says so.
    Applying means editing entry_filters.DEFAULT_PARAMS by hand, running the
    suite, and only then spending a validation shot -- this endpoint records
    a candidate, it does not change how the bot trades.
    """
    from swingbot.core import entry_filters
    from swingbot.admin.queries import _load_result

    payload = request.get_json(silent=True) or {}
    job_id = payload.get("job_id", "")
    try:
        row_index = int(payload.get("row_index", -1))
    except (TypeError, ValueError):
        return error("invalid", "row_index must be an integer.", 400)

    result = _load_result(job_id)
    if not result or row_index < 0 or row_index >= len(result.get("grid", [])):
        return error("not_found", "Could not find that job/row.", 404)

    row = result["grid"][row_index]
    strategy = result["strategy"]
    proposal = {
        "strategy": strategy,
        "proposed_params": row["params"],
        "train_stats": {k: v for k, v in row.items() if k != "params"},
        "current_params": dict(entry_filters.DEFAULT_PARAMS.get(strategy, {})),
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Apply by editing entry_filters.DEFAULT_PARAMS, run the suite, and only then "
            "consider a validation shot — remembering the window is spent."
        ),
    }

    directory = _proposals_dir()
    os.makedirs(directory, exist_ok=True)
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    strat_slug = strategy.lower().replace(" ", "-").replace("/", "-").replace("&", "and")
    filename = f"{ts_slug}-{strat_slug}.json"
    with open(os.path.join(directory, filename), "w", encoding="utf-8") as f:
        json.dump(proposal, f, indent=2)
    return jsonify({"filename": filename, "proposal": proposal})


@api_v1.route("/analytics/tuning/proposals/<filename>", methods=["DELETE"])
@require_auth
def delete_proposal(filename: str):
    from swingbot.admin.queries import _PROPOSAL_FILENAME_RE

    if not _PROPOSAL_FILENAME_RE.match(filename):
        # See this module's docstring: without this, a backslash or a
        # drive-letter prefix makes the line below delete an arbitrary file.
        return error("invalid", "Invalid proposal filename.", 400)
    path = os.path.join(_proposals_dir(), filename)
    if not os.path.exists(path):
        return error("not_found", f"No proposal named {filename!r}", 404)
    os.remove(path)
    return jsonify({"deleted": filename})
