"""A settings save leaves a .env version behind (v116 Phase 0)."""
from swingbot.admin import helpers
from swingbot.core.infra import env_snapshot


def test_writing_env_text_snapshots_before_and_after(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))
    helpers._write_env_text("A=2\n")
    directory = tmp_path / "backups" / "env"
    contents = [(directory / name).read_text(encoding="utf-8")
                for name in env_snapshot.snapshot_names(str(directory))]
    assert contents == ["A=1\n", "A=2\n"]


def test_a_snapshot_failure_never_fails_the_save(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(helpers, "ENV_PATH", str(env))

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(env_snapshot, "take_snapshot", boom)
    helpers._write_env_text("A=2\n")
    assert env.read_text(encoding="utf-8") == "A=2\n"
