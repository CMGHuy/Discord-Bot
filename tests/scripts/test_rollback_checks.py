"""v220 V220-4: config-key, compose db block and market-data writer checks."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_checks as rc  # noqa: E402

has_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _config(*keys: str) -> str:
    rows = "\n".join(f'    Field("{k}", "{k.lower()}", "S", "label", default=""),' for k in keys)
    return f"from dataclasses import dataclass\n\nFIELDS = [\n{rows}\n]\n"


ALL = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")


def test_declared_config_keys_reads_the_first_positional_string():
    src = _config("B_KEY", "A_KEY", "B_KEY") + 'X = Field(name="NOT_POSITIONAL")\nY = Other("NOPE")\n'
    assert rc.declared_config_keys(src) == ["A_KEY", "B_KEY"]


@pytest.mark.parametrize("src,match", [("FIELDS = [\n", "unparsable"), ("X = 1\n", "no Field")])
def test_declared_config_keys_refuses_what_it_cannot_read(src, match):
    with pytest.raises(ValueError, match=match):
        rc.declared_config_keys(src)


def test_env_key_names_returns_names_only():
    env = ("# comment\n\nDISCORD_TOKEN=abc=def\nexport POSTGRES_PASSWORD = s3cret\n"
           "  DATABASE_URL=postgresql://u:p@db/x\nnot a key line\n1BAD=x\nlower_ok=1\n")
    names = rc.env_key_names(env)
    assert names == {"DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL", "lower_ok"}
    assert not any(secret in repr(names) for secret in ("abc", "s3cret", "postgresql"))


def test_check_config_passes_when_everything_is_present():
    target = head = _config(*ALL, "OLD_OK")
    assert rc.check_config(target, head, {*ALL, "OLD_OK"}) == ([], [])


def test_a_missing_critical_key_refuses():
    refusals, warnings = rc.check_config(_config(*ALL), _config(*ALL), {"DISCORD_TOKEN", "DATABASE_URL"})
    assert refusals == ["critical key POSTGRES_PASSWORD is missing from .env"] and warnings == []


def test_a_key_removed_since_the_target_warns():
    refusals, warnings = rc.check_config(_config(*ALL, "GONE_KEY", "STILL_HERE"),
                                         _config(*ALL, "STILL_HERE"), set(ALL))
    assert refusals == []
    assert len(warnings) == 1 and warnings[0].startswith("GONE_KEY: ")


def test_an_extra_env_key_is_neither_refused_nor_warned():
    assert rc.check_config(_config(*ALL), _config(*ALL, "NEW_KEY"), {*ALL, "NEW_KEY", "STRAY"}) == ([], [])


@pytest.mark.parametrize("target,head,who", [
    ("FIELDS = [\n", _config(*ALL), "target"),
    (None, _config(*ALL), "target"),
    ("", _config(*ALL), "target"),
    (_config(*ALL), "X = 1\n", "HEAD"),
])
def test_an_unreadable_config_refuses(target, head, who):
    refusals, warnings = rc.check_config(target, head, set(ALL))
    assert len(refusals) == 1 and refusals[0].startswith(f"{who} swingbot/config.py") and warnings == []


COMPOSE = """\
# header comment
name: x
services:
  db:
    # pinned major
    image: ${SWING_BOT_DB_IMAGE:-swing-bot-db:local}
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}

    volumes:
      - pgdata:/var/lib/postgresql

  db-test:
    image: postgres:18
  bot:
    image: ${SWING_BOT_IMAGE:-swing-bot:latest}
volumes:
  pgdata:
"""


def test_compose_db_block_stops_at_the_next_sibling_and_drops_comments():
    block = rc.compose_db_block(COMPOSE)
    assert block.splitlines() == [
        "  db:", "    image: ${SWING_BOT_DB_IMAGE:-swing-bot-db:local}", "    environment:",
        "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}", "    volumes:", "      - pgdata:/var/lib/postgresql"]


def test_compose_db_block_without_a_db_service_raises():
    with pytest.raises(ValueError, match="no db service"):
        rc.compose_db_block("services:\n  bot:\n    image: x\n  db-test:\n    image: y\n")


def test_check_compose_ignores_comments_and_other_services():
    other = COMPOSE.replace("# pinned major", "# reworded").replace("postgres:18", "postgres:17") \
                   .replace("swing-bot:latest", "swing-bot:old")
    assert rc.check_compose(other, COMPOSE) == []


def test_check_compose_refuses_a_changed_db_block():
    old = COMPOSE.replace("pgdata:/var/lib/postgresql", "pgdata:/var/lib/postgresql/data")
    refusals = rc.check_compose(old, COMPOSE)
    assert len(refusals) == 1 and "db service differs" in refusals[0]
    assert "/var/lib/postgresql/data" in refusals[0]


@pytest.mark.parametrize("target,head,who", [(None, COMPOSE, "target"), ("services:\n", COMPOSE, "target"),
                                             (COMPOSE, "services:\n", "HEAD")])
def test_check_compose_refuses_an_unreadable_file(target, head, who):
    refusals = rc.check_compose(target, head)
    assert len(refusals) == 1 and refusals[0].startswith(f"{who} docker-compose.yml")


def _git_repo(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@e"}

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                              env=env, check=True).stdout.strip()

    def commit(files):
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(text.encode("utf-8"))
        git("add", "-A")
        git("commit", "-q", "-m", "c")
        return git("rev-parse", "HEAD")

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    return repo, commit


@has_git
def test_changed_writer_paths_and_show(tmp_path):
    repo, commit = _git_repo(tmp_path)
    a = commit({"swingbot/refresher/loop.py": "x = 1\n", "swingbot/core/marketdata/data_store.py": "s\n",
                "swingbot/other.py": "o\n"})
    b = commit({"swingbot/other.py": "changed\n"})
    c = commit({"swingbot/refresher/loop.py": "x = 2\n", "swingbot/refresher/new.py": "n\n"})
    assert rc.changed_writer_paths(repo, a, b) == []
    assert rc.changed_writer_paths(repo, a, c) == ["swingbot/refresher/loop.py", "swingbot/refresher/new.py"]
    assert rc.changed_writer_paths(repo, a, c, paths=("swingbot/core/marketdata/data_store.py",)) == []
    assert rc.show(repo, a, "swingbot/refresher/loop.py") == "x = 1\n"
    assert rc.show(repo, a, "swingbot/refresher/new.py") is None
    with pytest.raises(subprocess.CalledProcessError):
        rc.changed_writer_paths(repo, "0" * 40, c)


def test_the_real_config_declares_every_critical_key():
    keys = rc.declared_config_keys((REPO / rc.CONFIG_PATH).read_text(encoding="utf-8"))
    assert set(rc.CRITICAL_KEYS) <= set(keys) and len(keys) >= 200


def test_the_real_compose_db_block():
    block = rc.compose_db_block((REPO / rc.COMPOSE_PATH).read_text(encoding="utf-8"))
    assert block.startswith("  db:\n") and "${SWING_BOT_DB_IMAGE" in block
    assert "db-test" not in block and "swing-bot:latest" not in block


def test_every_writer_path_exists():
    assert all((REPO / p).exists() for p in rc.MARKET_DATA_WRITER_PATHS)


@has_git
def test_the_cache_writers_are_defined_only_inside_the_writer_paths():
    out = subprocess.run(["git", "-C", str(REPO), "grep", "-l", "-e", "def save_to_disk(",
                          "-e", "def refresh_symbol(", "--", "swingbot"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out and all(any(f.startswith(p) for p in rc.MARKET_DATA_WRITER_PATHS) for f in out), out
