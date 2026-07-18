"""Atomic JSON persistence: write to <path>.tmp then os.replace, so a crash
mid-write (power loss, OOM kill, docker restart) can never leave a torn
file behind for the next read to choke on.

Every store in this plan (JournalStore, snapshots.py, and the migrated
TradeLog/StateStore/account.py) goes through these two functions instead
of raw json.dump/json.load -- see Tasks A3/A4 for the migration of the
three pre-existing stores that used to write with plain json.dump.
"""
import json
import logging
import os

log = logging.getLogger("swing-bot.jsonio")


def atomic_write_json(path: str, obj) -> None:
    """Write `obj` as indented JSON to `path` without ever leaving a torn
    (partially-written) file behind, even if the process is killed
    mid-write.

    Mechanism: write to `<path>.tmp` first, fsync it to disk, then
    `os.replace(tmp, path)` -- os.replace is atomic on both POSIX and
    Windows (unlike os.rename on Windows, which fails if the destination
    exists; os.replace does not have that restriction on either OS), so
    any reader of `path` sees either the fully-old content or the fully-
    new content, never a half-written mix.

    `default=str` on json.dump means an unexpected non-JSON-native value
    (e.g. a stray datetime object a caller forgot to .isoformat()) is
    stringified instead of raising -- a persistence layer should degrade,
    not crash the trade it's trying to save.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str, default):
    """Read JSON from `path`, returning `default` (never raising) when the
    file is missing, empty, or corrupt. A corrupt file is logged as a
    warning rather than silently swallowed, so a real disk-corruption
    event is at least visible in the logs even though the bot keeps
    running on the fallback value."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("read_json(%s) failed (%s); returning default", path, exc)
        return default
