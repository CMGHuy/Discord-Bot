"""scripts/ops/env_set.py: one KEY=value, in place, then a snapshot (v116)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import env_set  # noqa: E402


def test_replaces_an_existing_key():
    assert env_set.set_value("A=1\nB=2\n", "B", "3") == "A=1\nB=3\n"


def test_appends_a_missing_key_with_a_newline():
    assert env_set.set_value("A=1\n", "C", "x") == "A=1\nC=x\n"
    assert env_set.set_value("A=1", "C", "x") == "A=1\nC=x\n"


def test_replaces_every_duplicate_so_last_wins_still_holds():
    assert env_set.set_value("B=1\nB=2\n", "B", "9") == "B=9\nB=9\n"


def test_a_value_is_literal_not_a_regex_template():
    assert env_set.set_value("A=1\n", "A", r"x\1y") == "A=x\\1y\n"


def test_get_reads_the_last_value_without_quotes():
    assert env_set.get_value('B=1\nB="two"\n', "B") == "two"
    assert env_set.get_value("A=1\n", "Z") is None


def test_main_writes_in_place_and_snapshots(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    inode = os.stat(env).st_ino
    assert env_set.main(["--env", str(env), "A", "2"]) == 0
    assert env.read_text(encoding="utf-8") == "A=2\n"
    assert os.stat(env).st_ino == inode, "a rename breaks the single-file bind mount"
    assert len(list((tmp_path / "backups" / "env").iterdir())) == 2


def test_main_get_prints_the_value(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("RESTIC_PASSWORD=s3cret\n", encoding="utf-8")
    assert env_set.main(["--env", str(env), "--get", "RESTIC_PASSWORD"]) == 0
    assert capsys.readouterr().out == "s3cret\n"


def test_main_warns_on_stderr_when_the_snapshot_fails(tmp_path, monkeypatch, capsys):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")

    def boom(*_a, **_k):
        raise PermissionError("backups/env is root-owned")

    monkeypatch.setattr(env_set.env_snapshot, "take_snapshot", boom)
    assert env_set.main(["--env", str(env), "A", "2"]) == 0
    assert env.read_text(encoding="utf-8") == "A=2\n"
    assert "snapshot FAILED" in capsys.readouterr().err


def test_main_preserves_crlf_bytes(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"A=1\r\nB=2\r\n")
    assert env_set.main(["--env", str(env), "B", "3"]) == 0
    assert env.read_bytes() == b"A=1\r\nB=3\r\n"
