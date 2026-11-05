"""Where the project's ONE local database container is, and who may log in.

There is exactly one local Postgres, the `swing-db` container, published on
127.0.0.1:SWING_DB_PORT (default 56789) by the git-ignored
docker-compose.override.yml. Its credentials are the ones in `.env`'s
`DATABASE_URL`; this module reuses them and never prints or returns them
anywhere but inside a connection URL handed to a driver.

`.env` is read from the MAIN checkout, because a worktree has none of its own
(it is git-ignored). Any worktree or agent may read it this way; the values
must never be printed, logged, quoted or written to a doc.

stdlib only: `testrun.py` and `tests/db/conftest.py` both load this file by
path, before (or without) the swingbot package being importable.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import urllib.parse

HOST = "127.0.0.1"  # not "localhost": docker publishes IPv4 only; IPv6-first stalls ~5s on Windows
DEFAULT_PORT = 56789
TEST_DATABASE = "swingbot_test"
# Only when no .env is readable (CI sets TEST_DATABASE_URL explicitly).
FALLBACK_URL = "postgresql+psycopg://swingbot:swingbot@127.0.0.1:56789/swingbot_test"


def main_checkout() -> pathlib.Path:
    """The repo's main working tree, even when called from a worktree."""
    here = pathlib.Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return here
    common = pathlib.Path(out)
    return (common if common.is_absolute() else here / common).resolve().parent


def _env_database_url(env_file: pathlib.Path) -> str | None:
    """`DATABASE_URL` from an env file, or None; never raises on a missing file."""
    try:
        lines = env_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == "DATABASE_URL":
            return value.strip().strip("'\"") or None
    return None


def local_url(database: str = TEST_DATABASE, *, env_file: pathlib.Path | None = None) -> str:
    """URL of `database` inside swing-db, logging in with `.env`'s credentials.

    `TEST_DATABASE_URL` wins when set and `database` is the test database (CI
    and explicit overrides); otherwise the credentials come from `.env`, with
    host and port swapped for the published ones. Never print the result."""
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit and database == TEST_DATABASE:
        return explicit
    raw = _env_database_url(env_file or main_checkout() / ".env")
    if not raw:
        return FALLBACK_URL.rsplit("/", 1)[0] + f"/{database}"
    parsed = urllib.parse.urlparse(raw)
    userinfo = parsed.netloc.rpartition("@")[0]
    port = os.getenv("SWING_DB_PORT", str(DEFAULT_PORT))
    netloc = f"{userinfo}@{HOST}:{port}" if userinfo else f"{HOST}:{port}"
    scheme = "postgresql+psycopg"
    return urllib.parse.urlunparse((scheme, netloc, f"/{database}", "", "", ""))
