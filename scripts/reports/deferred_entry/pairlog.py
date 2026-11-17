"""v229 pair log: one JSON line per eligible plan, appended once, never rewritten.

``data/v229/pairs.jsonl`` is the long run's checkpoint (spec section 2): each
finished trade is one line, flushed and fsynced, so a verdict never
re-derives twelve weeks and a restart skips trade ids already present. A
killed run leaves at most one line without its newline; that torn tail is
dropped and the trade redone. A malformed line inside the file is refused:
something other than ``append_pair`` wrote it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_LOG = "data/v229/pairs.jsonl"


class PairLogError(ValueError):
    """A log line that is not a pair, or a duplicate trade id."""


def _parse(line: str, lineno: int) -> dict:
    try:
        row = json.loads(line)
    except ValueError as exc:
        raise PairLogError(f"pair log line {lineno} is not JSON: {exc}") from exc
    if not isinstance(row, dict) or not row.get("trade_id"):
        raise PairLogError(f"pair log line {lineno} is not a pair (no trade_id)")
    return row


def _drop_torn_tail(path: Path, data: bytes) -> bytes:
    """Truncate a last line that never got its newline; return the kept bytes."""
    if not data or data.endswith(b"\n"):
        return data
    keep = data.rfind(b"\n") + 1
    with path.open("r+b") as handle:
        handle.truncate(keep)
        handle.flush()
        os.fsync(handle.fileno())
    return data[:keep]


def read_pairs(path) -> dict[str, dict]:
    """``trade_id -> pair`` in file order; a missing file is an empty log."""
    path = Path(path)
    if not path.exists():
        return {}
    data = _drop_torn_tail(path, path.read_bytes())
    out: dict[str, dict] = {}
    for lineno, line in enumerate(data.decode("utf-8").split("\n"), start=1):
        if not line.strip():
            continue
        row = _parse(line, lineno)
        if row["trade_id"] in out:
            raise PairLogError(f"pair log line {lineno}: duplicate trade_id {row['trade_id']!r}")
        out[row["trade_id"]] = row
    return out


def _line(pair: dict) -> str:
    try:
        return json.dumps(pair, sort_keys=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise PairLogError(f"pair {pair.get('trade_id')!r} is not JSON-serialisable: {exc}") from exc


def append_pair(path, pair: dict, *, known: set[str] | None = None) -> None:
    """Append one pair; refuse a missing or duplicate ``trade_id``.

    ``known`` is the caller's set of ids already logged (from ``read_pairs``);
    it is updated in place. Without it the log is re-read."""
    trade_id = pair.get("trade_id") if isinstance(pair, dict) else None
    if not trade_id:
        raise PairLogError("a pair needs a non-empty trade_id")
    path = Path(path)
    ids = known if known is not None else set(read_pairs(path))
    if trade_id in ids:
        raise PairLogError(f"trade_id {trade_id!r} is already in the pair log")
    line = _line(pair)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    ids.add(trade_id)
