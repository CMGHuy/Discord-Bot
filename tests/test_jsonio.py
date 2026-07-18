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


def test_overwrite_existing_file(tmp_path):
    p = str(tmp_path / "overwrite.json")
    # Write initial content
    atomic_write_json(p, {"version": 1, "data": "first"})
    assert read_json(p, None) == {"version": 1, "data": "first"}
    # Overwrite with different content
    atomic_write_json(p, {"version": 2, "data": "second"})
    assert read_json(p, None) == {"version": 2, "data": "second"}
    # No .tmp file left behind
    assert not os.path.exists(p + ".tmp")


def test_read_invalid_utf8_returns_default(tmp_path):
    p = str(tmp_path / "invalid_utf8.json")
    # Write invalid UTF-8 bytes directly (0xFF is not valid UTF-8)
    with open(p, "wb") as f:
        f.write(b'{"key": "\xff"}')
    # Should return default instead of raising UnicodeDecodeError
    assert read_json(p, {"fallback": True}) == {"fallback": True}


def test_statestore_atomic(tmp_path):
    from swingbot.core.state import StateStore

    path = str(tmp_path / "state.json")
    store = StateStore(path=path)
    store.set_last_trend("AAPL|Fibonacci|4w", "bullish")
    assert not os.path.exists(path + ".tmp")

    reloaded = StateStore(path=path)
    assert reloaded.get_last_trend("AAPL|Fibonacci|4w") == "bullish"


def test_account_config_atomic(tmp_path):
    from swingbot.core import account as account_module

    path = str(tmp_path / "account.json")
    cfg = account_module.load_account_config(path)  # seeds a fresh file
    assert not os.path.exists(path + ".tmp")
    account_module.set_balance(50_000.0, path)
    assert not os.path.exists(path + ".tmp")

    reloaded = account_module.load_account_config(path)
    assert reloaded["base_balance"] == 50_000.0
