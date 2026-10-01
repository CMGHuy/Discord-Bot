"""Versioned .env copies for point-in-time rollback (v116 Phase 0)."""
import ast
import datetime as dt
import os
import pathlib
import sys

import pytest

from swingbot.core.infra import env_snapshot as es

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)


def _env(tmp_path, text="A=1\n"):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_first_snapshot_copies_the_file_under_backups_env(tmp_path):
    out = es.take_snapshot(str(_env(tmp_path)), now=T0)
    assert out == str(tmp_path / "backups" / "env" / "2026-10-01T10-00-00-000000Z.env")
    assert pathlib.Path(out).read_text(encoding="utf-8") == "A=1\n"


def test_unchanged_content_takes_no_second_snapshot(tmp_path):
    env = _env(tmp_path)
    es.take_snapshot(str(env), now=T0)
    assert es.take_snapshot(str(env), now=T0 + dt.timedelta(hours=1)) is None
    assert len(es.snapshot_names(es.snapshot_dir(str(env)))) == 1


def test_changed_content_takes_a_new_snapshot_that_sorts_last(tmp_path):
    env = _env(tmp_path)
    es.take_snapshot(str(env), now=T0)
    env.write_text("A=2\n", encoding="utf-8")
    es.take_snapshot(str(env), now=T0 + dt.timedelta(microseconds=5))
    names = es.snapshot_names(es.snapshot_dir(str(env)))
    assert len(names) == 2
    newest = pathlib.Path(es.snapshot_dir(str(env))) / names[-1]
    assert newest.read_text(encoding="utf-8") == "A=2\n"


def test_a_missing_env_is_not_an_error(tmp_path):
    assert es.take_snapshot(str(tmp_path / ".env")) is None


def test_stamp_of_round_trips_the_file_name():
    assert es.stamp_of("2026-10-01T10-00-00-000123Z.env") == T0.replace(microsecond=123)
    assert es.stamp_of("notes.txt") is None


def test_prune_keeps_the_newest_snapshot_older_than_the_window(tmp_path):
    directory = tmp_path / "backups" / "env"
    directory.mkdir(parents=True)
    names = ["2026-08-01T00-00-00-000000Z.env", "2026-08-15T00-00-00-000000Z.env",
             "2026-09-20T00-00-00-000000Z.env"]
    for name in names:
        (directory / name).write_text(name, encoding="utf-8")
    removed = es.prune(str(directory), keep_days=30, now=dt.datetime(2026, 10, 1, tzinfo=UTC))
    # 08-15 is the version that was live when the 30-day window opened.
    assert removed == [str(directory / names[0])]
    assert es.snapshot_names(str(directory)) == names[1:]


def test_cli_snapshot_then_prune(tmp_path, capsys):
    env = _env(tmp_path)
    assert es.main(["snapshot", str(env)]) == 0
    assert es.main(["prune", es.snapshot_dir(str(env)), "30"]) == 0
    assert len(es.snapshot_names(es.snapshot_dir(str(env)))) == 1


def test_the_module_is_stdlib_only():
    """It runs as `python3 -m` on the VM host, where no requirement is installed."""
    tree = ast.parse(pathlib.Path(es.__file__).read_text(encoding="utf-8"))
    roots = {alias.name.split(".")[0] for node in ast.walk(tree)
             if isinstance(node, ast.Import) for alias in node.names}
    roots |= {node.module.split(".")[0] for node in ast.walk(tree)
              if isinstance(node, ast.ImportFrom) and node.module}
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}, roots


def test_prune_keeps_a_snapshot_exactly_at_the_cutoff(tmp_path):
    directory = tmp_path / "backups" / "env"
    directory.mkdir(parents=True)
    names = ["2026-08-01T00-00-00-000000Z.env", "2026-09-01T00-00-00-000000Z.env"]
    for name in names:
        (directory / name).write_text(name, encoding="utf-8")
    now = dt.datetime(2026, 10, 1, tzinfo=UTC)
    assert es.prune(str(directory), keep_days=30, now=now) == []
    assert es.snapshot_names(str(directory)) == names


def test_prune_of_a_missing_or_empty_directory_removes_nothing(tmp_path):
    assert es.prune(str(tmp_path / "nope"), 30, T0) == []
    (tmp_path / "empty").mkdir()
    assert es.prune(str(tmp_path / "empty"), 30, T0) == []


def test_prune_keeps_a_single_old_snapshot(tmp_path):
    directory = tmp_path / "backups" / "env"
    directory.mkdir(parents=True)
    (directory / "2026-01-01T00-00-00-000000Z.env").write_text("x", encoding="utf-8")
    assert es.prune(str(directory), 30, T0) == []
    assert len(es.snapshot_names(str(directory))) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_snapshot_file_is_0600_and_directory_0700_even_if_precreated(tmp_path):
    directory = tmp_path / "backups" / "env"
    directory.mkdir(parents=True, mode=0o755)
    os.chmod(directory, 0o755)
    out = es.take_snapshot(str(_env(tmp_path)), now=T0)
    assert os.stat(out).st_mode & 0o777 == 0o600
    assert os.stat(directory).st_mode & 0o777 == 0o700


def test_snapshot_quietly_reports_failure(tmp_path, monkeypatch):
    env = _env(tmp_path)

    def boom(*_a, **_k):
        raise OSError("denied")

    monkeypatch.setattr(es, "take_snapshot", boom)
    assert es.snapshot_quietly(str(env)) is False
    monkeypatch.undo()
    assert es.snapshot_quietly(str(env)) is True
