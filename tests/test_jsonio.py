import json
import os

from swingbot.core.jsonio import atomic_write_json, read_json


def test_roundtrip(tmp_path):
    p = str(tmp_path / "x.json")
    atomic_write_json(p, {"a": 1})
    assert read_json(p, None) == {"a": 1}
    assert not os.path.exists(p + ".tmp")


def test_read_missing_returns_default(tmp_path):
    assert read_json(str(tmp_path / "nope.json"), []) == []


def test_read_corrupt_returns_default(tmp_path):
    p = str(tmp_path / "bad.json")
    with open(p, "w") as f:
        f.write("{truncated")
    assert read_json(p, {"d": True}) == {"d": True}


def test_write_creates_missing_parent_dir(tmp_path):
    # journal.json / analytics_snapshot.json / plans.json etc. are all
    # first-write-ever files the first time a fresh checkout runs -- the
    # parent (data/) normally already exists, but a nested tmp_path
    # subdirectory in a test, or a brand-new deploy target, might not.
    p = str(tmp_path / "nested" / "sub" / "y.json")
    atomic_write_json(p, [1, 2, 3])
    assert read_json(p, None) == [1, 2, 3]


def test_roundtrip_list_and_unicode(tmp_path):
    p = str(tmp_path / "list.json")
    obj = [{"ticker": "AAPL", "note": "target hit — clean 2R capture €"}]
    atomic_write_json(p, obj)
    assert read_json(p, None) == obj
