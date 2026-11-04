"""v200 Part 2: exclude the trades that were open during the August 2026 stop-monitor stall.

The rule (frozen by spec v200 Part 2):

* A trade is excluded when ``opened < window.end and closed >= window.start`` for any
  window: open at any moment in it, whatever its close reason or close time. Both bounds
  compare tz-aware UTC instants to the second.
* A missing ``opened`` or ``closed`` gives False (never matched).
* Only ``row_kind == "trade"`` rows with a ``trade_id`` are candidates.

The report applies the committed ``trade_ids`` of ``exclusions.json`` by id (V200-10); the
rule itself is only re-run by the rebuild test and by this CLI:

    python scripts/reports/autopsy/exclusions.py <rows.csv>

which prints the rebuilt ids as a JSON list on stdout. This module has no relative import
at module level, so it runs both as ``autopsy.exclusions`` and as a script.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUSIONS_PATH = Path(__file__).with_name("exclusions.json")
_REQUIRED = ("reason", "rule", "windows", "trade_ids")


@dataclass(frozen=True)
class Window:
    start: dt.datetime
    end: dt.datetime


@dataclass(frozen=True)
class Exclusion:
    key: str
    reason: str
    rule: str
    windows: tuple[Window, ...]
    trade_ids: frozenset[str]


def _instant(key: str, text: str) -> dt.datetime:
    stamp = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError(f"exclusion {key!r}: timestamp {text!r} has no offset")
    return stamp.astimezone(dt.timezone.utc)


def _window(key: str, raw: dict) -> Window:
    window = Window(_instant(key, raw["start"]), _instant(key, raw["end"]))
    if window.start >= window.end:
        raise ValueError(f"exclusion {key!r}: window start {raw['start']} is not before end {raw['end']}")
    return window


def _entry(key: str, raw: dict) -> Exclusion:
    missing = [name for name in _REQUIRED if name not in raw]
    if missing:
        raise ValueError(f"exclusion {key!r}: missing {', '.join(missing)}")
    return Exclusion(key=key, reason=raw["reason"], rule=raw["rule"],
                     windows=tuple(_window(key, w) for w in raw["windows"]),
                     trade_ids=frozenset(raw["trade_ids"]))


def load_exclusions(path: Path = EXCLUSIONS_PATH, *,
                    input_fingerprints: dict | None = None) -> list[Exclusion]:
    """The committed exclusions sorted by key; the file's hash goes into the fingerprints."""
    path = Path(path)
    data = path.read_bytes()
    if input_fingerprints is not None:
        input_fingerprints[str(path.resolve())] = hashlib.sha256(data).hexdigest()
    payload = json.loads(data.decode("utf-8"))
    return [_entry(key, payload[key]) for key in sorted(payload)]


def open_in_window(opened: dt.datetime | None, closed: dt.datetime | None, window: Window) -> bool:
    """True when the trade was open at any moment in the window; untimed trades never match."""
    if opened is None or closed is None:
        return False
    return opened < window.end and closed >= window.start


def rebuild_trade_ids(rows, windows) -> list[str]:
    """Sorted unique ids of the trade rows the rule excludes."""
    return sorted({r.trade_id for r in rows
                   if r.row_kind == "trade" and r.trade_id
                   and any(open_in_window(r.opened_at_utc, r.closed_at_utc, w) for w in windows)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v200: rebuild the stall trade ids from a rows export")
    parser.add_argument("rows", type=Path)
    parser.add_argument("--exclusions", type=Path, default=EXCLUSIONS_PATH)
    parser.add_argument("--key", default="stall_2026_08")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(root), str(root / "scripts" / "reports")]
    from autopsy.rows import load_rows
    loaded = load_rows(args.rows)
    [entry] = [e for e in load_exclusions(args.exclusions) if e.key == args.key]
    untimed = sum(1 for r in loaded if r.row_kind == "trade"
                  and (r.opened_at_utc is None or r.closed_at_utc is None))
    print(f"{untimed} trade rows lack opened_at or closed_at and are never matched", file=sys.stderr)
    print(json.dumps(rebuild_trade_ids(loaded, entry.windows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
