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


def test_no_stray_temp_files_left_behind(tmp_path):
    """The temp name is unique now, so 'no <path>.tmp' is too weak a check --
    assert the directory holds exactly the target file."""
    p = str(tmp_path / "x.json")
    atomic_write_json(p, {"a": 1})
    assert os.listdir(tmp_path) == ["x.json"]


def test_concurrent_writers_do_not_clobber_each_others_temp(tmp_path):
    """Regression: a fixed `<path>.tmp` meant two processes writing the same
    file shared one temp -- the second os.replace died with FileNotFoundError.
    Hit in production 2026-08-04 by the bot and admin UI sharing data/."""
    import threading

    p = str(tmp_path / "shared.json")
    errors = []
    barrier = threading.Barrier(8)

    def writer(n):
        try:
            barrier.wait()
            for _ in range(25):
                atomic_write_json(p, {"writer": n, "payload": list(range(200))})
        except BaseException as exc:  # noqa: BLE001 - the assertion is "none"
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent writes raised: {errors[:3]}"
    # Whoever won, the file must be complete and parseable -- never torn.
    assert read_json(p, None) is not None
    assert os.listdir(tmp_path) == ["shared.json"]


def test_write_preserves_existing_file_mode(tmp_path):
    """mkstemp creates 0600; a rewrite must not silently narrow permissions
    on a file the other container reads."""
    p = str(tmp_path / "perm.json")
    atomic_write_json(p, {"a": 1})
    os.chmod(p, 0o644)
    atomic_write_json(p, {"a": 2})
    assert oct(os.stat(p).st_mode & 0o777) == "0o644"
