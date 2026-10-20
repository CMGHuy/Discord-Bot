"""v171 D9: once-a-minute tape sampler for the blank-tape success check (V171-34).

Appends one JSON line per minute to --out while it runs:
``{"at", "in_session", "blank": [symbols] | null, "error": str | null}``.
Run on the VM through scripts/ops/v171_tape_sampler_cron.sh, piped over stdin
into the bot container. Imports of swingbot sit inside functions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone


def blank_symbols(entries: dict, symbols) -> list[str]:
    """Symbols (in order) whose entry is missing or has neither price nor change %."""
    blank = []
    for symbol in symbols:
        entry = entries.get(symbol)
        if entry is None or (entry.price is None and entry.change_pct is None):
            blank.append(symbol)
    return blank


def sample(now: datetime) -> dict:
    from swingbot.core.market.session import is_regular_session, is_tape_open
    in_session = bool(is_regular_session(now) and is_tape_open(now))
    out = {"at": now.isoformat(), "in_session": in_session, "blank": [], "error": None}
    if not in_session:
        return out
    try:
        from swingbot.core.marketdata.shared import tape
        out["blank"] = blank_symbols(tape.read_tape(list(tape.TAPE_FIXED)), tape.TAPE_FIXED)
    except Exception as exc:  # noqa: BLE001 - the sampler must keep running
        out["blank"], out["error"] = None, f"{type(exc).__name__}: {exc}"
    return out


def _past(now: datetime, until_utc: str) -> bool:
    hour, minute = (int(part) for part in until_utc.split(":"))
    return (now.hour, now.minute) > (hour, minute)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--until-utc", default="21:15")
    args = ap.parse_args(argv)
    while True:
        now = datetime.now(timezone.utc)
        if _past(now, args.until_utc):
            return 0
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(sample(now)) + "\n")
        time.sleep(60 - time.time() % 60)


if __name__ == "__main__":
    sys.exit(main())
