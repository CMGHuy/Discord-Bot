"""Read the Part 3 JSON stores into the record lists importer and parity compare.

One reader per store, shared by the importer and by `parity_report`: the row
list an importer writes and the row list parity compares against must come
from the same code, or a torn-line or default-filling difference between the
two shows up as a phantom mismatch (or, worse, hides a real one).

Every function takes what the store's file holds (parsed JSON, or a path for
the two JSONL / directory stores) and returns plain dicts. A missing or
malformed file is an empty list, never an exception.
"""
from __future__ import annotations

import datetime as dt
import json
import os

KILLSWITCH_KEY = "global"
PREFERENCES_OWNER = "admin"


def jobs_rows(raw: object) -> list[dict]:
    """`admin_jobs.json` is ``{job_id: record}``; a record's own `id` wins."""
    if not isinstance(raw, dict):
        return []
    return [{**record, "id": record.get("id", job_id)}
            for job_id, record in raw.items() if isinstance(record, dict)]


def scheduled_rows(raw: object) -> list[dict]:
    """`scheduled_jobs.json` is ``{job: 'YYYY-MM-DD'}``."""
    if not isinstance(raw, dict):
        return []
    return [{"job": job, "fired_on": fired_on} for job, fired_on in raw.items()]


def preferences_rows(raw: object) -> list[dict]:
    """The whole blob is one row owned by ``admin``; an empty blob is no row."""
    if not isinstance(raw, dict) or not raw:
        return []
    return [{"owner": PREFERENCES_OWNER, **raw}]


def killswitch_rows(raw: object) -> list[dict]:
    """The single-file state as one row, with the `state()` defaults filled in."""
    if not isinstance(raw, dict) or not raw:
        return []
    from swingbot import config
    return [{
        "key": KILLSWITCH_KEY,
        "on": bool(raw.get("on", config.KILLSWITCH_DEFAULT_ON)),
        "reason": raw.get("reason"),
        "at": raw.get("at"),
        "manual_release": bool(raw.get("manual_release", False)),
    }]


def ticker_rows(raw: object) -> list[dict]:
    """`ticker_directory.json` is ``{"fetched_at": ..., "rows": [...]}``."""
    rows = raw.get("rows") if isinstance(raw, dict) else None
    return [row for row in rows or [] if isinstance(row, dict) and row.get("symbol")]


def audit_rows(path: str) -> list[dict]:
    """`settings_audit.jsonl` entries in file order, each with a `seq`.

    The log has no natural key (two identical changes a minute apart are two
    entries), so an entry is identified by its position among the valid
    lines. That is sound because the file is append-only and the table is
    read back in insertion order. A line that does not parse, or lacks a
    `ts`, is skipped: a crash mid-append leaves exactly one such line at the
    end, and `read_settings_audit` skips it the same way.
    """
    if not os.path.isfile(path):
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("ts"):
                entries.append({"seq": len(entries), "ts": entry["ts"],
                                "changes": entry.get("changes") or []})
    return entries


def _json_files(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(name for name in os.listdir(directory) if name.endswith(".json"))


def _load_dict(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def file_mtime_iso(path: str) -> str:
    """When a file was last written, as a UTC ISO string."""
    return dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc).isoformat()


def tuning_result_rows(directory: str) -> list[dict]:
    """One row per `tuning_results/<job_id>.json`; the file holds the payload only."""
    rows = []
    for name in _json_files(directory):
        payload = _load_dict(os.path.join(directory, name))
        if payload is not None:
            rows.append({"job_id": name[:-len(".json")], **payload})
    return rows


def proposal_rows(directory: str) -> list[dict]:
    """One row per `tuning_proposals/<filename>`; `created_at` falls back to mtime."""
    rows = []
    for name in _json_files(directory):
        path = os.path.join(directory, name)
        data = _load_dict(path)
        if data is not None:
            rows.append({"filename": name,
                         **{"created_at": file_mtime_iso(path), **data}})
    return rows
