"""v218 V218-7: the build a response came from, the first ETag input (P3-c)."""
import hashlib

import pytest

from swingbot.admin import build_identity


@pytest.fixture
def version_file(tmp_path, monkeypatch):
    path = tmp_path / "VERSION.json"
    path.write_text('{"ui": "1.40.3", "bot": "2.17.3"}', encoding="utf-8")
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(path))
    monkeypatch.delenv("SWING_BOT_IMAGE", raising=False)
    build_identity.reset_cache()
    yield path
    build_identity.reset_cache()


def test_the_value_is_the_version_file_hash_and_the_image_tag(version_file, monkeypatch):
    monkeypatch.setenv("SWING_BOT_IMAGE", "ghcr.io/cmghuy/discord-bot:sha-abc")
    digest = hashlib.sha256(version_file.read_bytes()).hexdigest()[:16]
    assert build_identity.build_version() == f"{digest}|ghcr.io/cmghuy/discord-bot:sha-abc"


def test_without_the_image_tag_the_version_file_alone_names_the_build(version_file):
    digest, _, image = build_identity.build_version().partition("|")
    assert len(digest) == 16 and image == ""


def test_a_version_file_change_changes_the_value_after_a_cache_reset(version_file):
    before = build_identity.build_version()
    version_file.write_text('{"ui": "1.40.4", "bot": "2.17.4"}', encoding="utf-8")
    assert build_identity.build_version() == before          # cached per process
    build_identity.reset_cache()
    assert build_identity.build_version() != before


def test_the_image_tag_present_or_absent_gives_different_values(version_file, monkeypatch):
    absent = build_identity.build_version()
    monkeypatch.setenv("SWING_BOT_IMAGE", "ghcr.io/cmghuy/discord-bot:sha-def")
    build_identity.reset_cache()
    assert build_identity.build_version() != absent


def test_a_missing_version_file_raises_and_caches_nothing(version_file, monkeypatch):
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(version_file.with_name("absent.json")))
    with pytest.raises(OSError):
        build_identity.build_version()
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(version_file))
    assert build_identity.build_version().count("|") == 1    # recovers once the file is back


def test_the_default_path_is_the_repo_version_file():
    build_identity.reset_cache()
    assert build_identity.VERSION_PATH.replace("\\", "/").endswith("/VERSION.json")
    assert len(build_identity.build_version().partition("|")[0]) == 16
    build_identity.reset_cache()
