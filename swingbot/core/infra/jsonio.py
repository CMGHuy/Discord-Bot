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
import time

log = logging.getLogger("swing-bot.jsonio")

#: `os.replace` is atomic, but on Windows it can still fail transiently with
#: PermissionError (WinError 5 / 32) when something else holds a handle on
#: either file for a few milliseconds -- Defender scanning the freshly-written
#: .tmp is the usual culprit, and an indexer or a backup agent will do it too.
#: Nothing is wrong with the data; the call simply has to be made again.
#:
#: Observed three times in one afternoon on this machine, each time in a
#: different test, which is what identified it as the write helper rather than
#: any one caller. The same failure in the bot would surface as a lost trade
#: or plan write, silently, so this is a production fix that happens to have
#: been found by the suite.
_REPLACE_ATTEMPTS = 6
_REPLACE_BACKOFF_S = 0.02


def _replace_with_retry(tmp: str, path: str) -> None:
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(tmp, path)
            if attempt > 1:
                log.info("os.replace(%s) succeeded on attempt %d", path, attempt)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                # Out of retries: raise rather than swallow. A write that
                # never lands must not look like one that did.
                log.warning("os.replace(%s) still blocked after %d attempts",
                            path, attempt)
                raise
            # Linear, not exponential: the window is milliseconds, and a
            # long backoff would stall a scan loop for a transient lock.
            time.sleep(_REPLACE_BACKOFF_S * attempt)


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
    _replace_with_retry(tmp, path)


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
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("read_json(%s) failed (%s); returning default", path, exc)
        return default
