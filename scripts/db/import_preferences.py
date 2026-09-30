#!/usr/bin/env python3
"""Import data/ui_preferences.json into the ui_preferences table (one row)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.preferences import PreferencesRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db import part3_sources  # noqa: E402
from scripts.db.import_common import run_import  # noqa: E402


def load_source(path: str | None) -> list[dict]:
    """The whole blob is one row owned by admin; no file, or an empty one, is no row."""
    raw = read_json(path or os.path.join(config.DATA_DIR, "ui_preferences.json"), {})
    return part3_sources.preferences_rows(raw)


def write_one(repo, record: dict) -> None:
    prefs = {key: value for key, value in record.items() if key != "owner"}
    repo.save(prefs, record["owner"])


def main(argv=None) -> int:
    return run_import(sys.argv[1:] if argv is None else argv, load_source=load_source,
                      write_one=write_one, repo=PreferencesRepository(), key="owner",
                      name="preferences")


if __name__ == "__main__":
    raise SystemExit(main())
