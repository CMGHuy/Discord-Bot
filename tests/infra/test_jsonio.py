import json
import os

import pytest

from swingbot.core.infra import jsonio

from swingbot.core.infra.jsonio import atomic_write_json, read_json


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
    from swingbot.core.infra.state import StateStore

    path = str(tmp_path / "state.json")
    store = StateStore(path=path)
    assert store.confirm_or_update("AAPL|Fibonacci|4w", "bullish", required_confirmations=1) is True
    assert not os.path.exists(path + ".tmp")

    reloaded = StateStore(path=path)
    # Matches the already-confirmed value -> no pending flip -> False.
    # If persistence were broken, `confirmed` would reload as None, the
    # first-confirmation branch would fire again, and this would wrongly
    # return True -- so this assertion still proves the reload worked.
    assert reloaded.confirm_or_update("AAPL|Fibonacci|4w", "bullish", required_confirmations=1) is False


def test_account_config_atomic(tmp_path):
    from swingbot.core.planning import account as account_module

    path = str(tmp_path / "account.json")
    cfg = account_module.load_account_config(path)  # seeds a fresh file
    assert not os.path.exists(path + ".tmp")
    account_module.set_balance(50_000.0, path)
    assert not os.path.exists(path + ".tmp")

    reloaded = account_module.load_account_config(path)
    assert reloaded["base_balance"] == 50_000.0


# --- Windows transient lock on os.replace ---------------------------------
# `os.replace` is atomic, but on Windows it fails transiently with
# PermissionError when something else briefly holds a handle on either file --
# Defender scanning the freshly-written .tmp is the usual cause. Seen three
# times in one afternoon, each in a DIFFERENT test, which is what identified
# the write helper rather than any single caller as the culprit. The same
# failure in the bot loses a trade or plan write silently.

def test_a_transient_permission_error_is_retried(tmp_path, monkeypatch):
    from unittest import mock

    target = str(tmp_path / "plans.json")
    real = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)

    with mock.patch.object(jsonio.os, "replace", flaky):
        jsonio.atomic_write_json(target, [{"plan_id": "p1"}])

    assert calls["n"] == 3, "should have retried past the two failures"
    assert jsonio.read_json(target, None) == [{"plan_id": "p1"}]


def test_a_permanent_permission_error_still_raises(tmp_path, monkeypatch):
    """Bounded retry, not infinite patience. A write that never landed must
    not be reported as one that did — the caller has to be able to tell."""
    from unittest import mock

    target = str(tmp_path / "plans.json")
    jsonio.atomic_write_json(target, [{"plan_id": "original"}])

    def always(src, dst):
        raise PermissionError(5, "Access is denied")

    with mock.patch.object(jsonio.os, "replace", always):
        with pytest.raises(PermissionError):
            jsonio.atomic_write_json(target, [{"plan_id": "never-lands"}])

    # The previous content survives: a failed replace leaves the target alone.
    assert jsonio.read_json(target, None) == [{"plan_id": "original"}]
