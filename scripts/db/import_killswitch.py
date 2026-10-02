#!/usr/bin/env python3
"""Import data/killswitch.json into the killswitch table (one row)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.killswitch import KillswitchRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    raw = read_json(path or os.path.join(config.DATA_DIR, "killswitch.json"), {})
    return part3_sources.killswitch_rows(raw)


def write_one(repo, record: dict) -> None:
    """Map the file's on/at onto the table's engaged/engaged_at."""
    repo.upsert({"key": record["key"], "engaged": record["on"],
                 "engaged_at": record["at"], "reason": record["reason"],
                 "manual_release": record["manual_release"]})


def main(argv=None) -> int:
    return run_import(sys.argv[1:] if argv is None else argv, load_source=load_source,
                      write_one=write_one, repo=KillswitchRepository(), key="key",
                      name="killswitch")


if __name__ == "__main__":
    raise SystemExit(main())
