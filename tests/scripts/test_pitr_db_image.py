"""The PITR database image's build inputs (v116 Phase 0).

They cannot be built in the unit suite, so what is pinned is what a broken
edit would remove: the major version, pgBackRest itself, and the retention
that makes "any second in the last 30 days" true.
"""
import configparser
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO / "Dockerfile.db"
CONF = REPO / "deploy" / "db" / "pgbackrest.conf"


@pytest.fixture(scope="module")
def conf():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(CONF.read_text(encoding="utf-8"))
    return parser


def test_the_image_pins_postgres_18_and_adds_pgbackrest():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^FROM postgres:18-alpine$", text, re.M)
    assert "apk add --no-cache pgbackrest" in text
    assert "COPY deploy/db/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf" in text


def test_retention_keeps_thirty_days_of_point_in_time_history(conf):
    assert conf["global"]["repo1-retention-full-type"] == "time"
    assert conf["global"]["repo1-retention-full"] == "30"


def test_compression_is_on(conf):
    # Every forced WAL switch archives a 16 MB segment; uncompressed, the
    # archive does not fit the disk (spec § Postgres).
    assert conf["global"]["compress-type"] in {"gz", "lz4", "zst", "bz2"}


def test_the_repo_is_the_bind_mounted_path_and_the_stanza_is_pg18(conf):
    assert conf["global"]["repo1-path"] == "/var/lib/pgbackrest"
    assert conf["swingbot"]["pg1-path"] == "/var/lib/postgresql/18/docker"
    assert conf["swingbot"]["pg1-user"] == "swingbot"


def test_the_backups_directory_is_never_committed():
    lines = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/backups/" in lines


@pytest.mark.parametrize("path", [DOCKERFILE, CONF])
def test_lf_line_endings(path):
    assert b"\r" not in path.read_bytes()
