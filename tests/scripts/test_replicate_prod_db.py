"""replicate_prod_db.sh: production is only read, and the live local database
is never the default target."""
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "replicate_prod_db.sh"


@pytest.fixture(scope="module")
def source():
    assert SCRIPT.exists(), "scripts/ops/replicate_prod_db.sh is missing"
    return SCRIPT.read_text(encoding="utf-8")


def _run(*args):
    # Arguments, not env vars: on Windows `bash` from Python can be WSL's, which
    # does not forward the environment.
    return subprocess.run(["bash", SCRIPT.relative_to(REPO).as_posix(), *args],
                          cwd=REPO, capture_output=True, text=True, timeout=60)


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail", source, re.M)


def test_it_uses_lf_line_endings():
    assert b"\r" not in SCRIPT.read_bytes()


def test_it_reaches_production_only_through_the_ssh_wrapper(source):
    assert "ssh-hetzner.sh" in source
    assert not re.search(r"^\s*(ssh|scp)\s", source, re.M), "raw ssh/scp"


def test_production_is_only_read(source):
    """No write verb may be sent to the VM: every remote command is a dump or a
    SELECT."""
    remote = [ln for ln in source.splitlines() if "SSH_HETZNER\" \"" in ln]
    assert remote, "no remote command found"
    for ln in remote:
        assert not re.search(r"\b(alembic|DROP|DELETE|INSERT|UPDATE|restart|rm )\b", ln), ln


def test_default_target_is_a_replica_not_the_live_database():
    r = _run("--dry-run")
    assert r.returncode == 0
    assert "swingbot_prod_replica" in r.stdout
    assert "swingbot_prod_replica" in r.stdout.split("target :")[1]


def test_the_live_local_database_needs_an_explicit_flag():
    r = _run("swingbot")
    assert r.returncode == 2
    assert "--i-mean-it" in r.stderr


def test_a_target_name_cannot_carry_sql():
    r = _run("a;drop database swingbot")
    assert r.returncode == 2
