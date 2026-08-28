"""Regression for a cross-test config leak found via a full-suite -n4 flake:
tests/scanning/test_engine_v2_plans.py::test_sync_run_scan_gates_attach_plan_v2_on_all_ok
failed once with its monkeypatched MIN_REWARD_PCT/MIN_RISK_REWARD_RATIO/etc.
silently replaced by the REAL project .env's values, logged as
".env modified on disk (mtime changed) -- auto-reloading config".

Root cause: admin/app.py's before_request hook calls
config.auto_reload_if_changed() on every request. That function compares
the current .env's (mtime, size) against the module global
config._ENV_MTIME and, on a mismatch, calls config.reload(), which
reassigns _ENV_MTIME via a plain `global` statement -- not through
monkeypatch, so monkeypatch's teardown has no way to know about or undo it.

admin_app (conftest.py) points config.ENV_PATH at a tmp_path .env for the
life of one test. Any request through the Flask test client during that
test makes auto_reload_if_changed() see a mismatch (a different file) and
permanently caches THAT tmp file's signature into _ENV_MTIME. Once the test
ends, monkeypatch restores ENV_PATH to the real path but leaves the stale
tmp signature in _ENV_MTIME -- so the NEXT test in the same xdist worker
that reads the real .env sees a spurious "changed" verdict and gets its own
monkeypatched config silently overwritten by whatever the real .env holds.

Reproduced without timing luck or a real Flask request: the exact
mechanism (patch ENV_PATH, call auto_reload_if_changed, let the patch
unwind) is replicated directly against the config module."""
import pytest

import swingbot.config as config


def test_env_mtime_does_not_leak_past_an_isolated_reload(tmp_path):
    real_env_path = config.ENV_PATH
    real_mtime_before = config._ENV_MTIME

    # -- shape of one admin_app-isolated test that happens to trigger a
    # request through app.py's before_request hook --
    with pytest.MonkeyPatch.context() as mp:
        tmp_env = tmp_path / ".env"
        tmp_env.write_text("DISCORD_TOKEN=test-token\n", encoding="utf-8")
        mp.setattr(config, "ENV_PATH", str(tmp_env))
        # The fix under test: conftest.py's admin_app fixture pins
        # _ENV_MTIME the same way it pins ENV_PATH, so monkeypatch's
        # teardown restores it regardless of what reload() does meanwhile.
        mp.setattr(config, "_ENV_MTIME", config._ENV_MTIME)

        config.auto_reload_if_changed()   # what the before_request hook does
        assert config._ENV_MTIME == config._env_signature(), (
            "sanity check: the tmp .env's differing signature should have "
            "triggered a real reload inside this isolated block"
        )

    # -- back in the "real world": the next test in this worker starts here --
    assert config.ENV_PATH == real_env_path
    assert config._ENV_MTIME == real_mtime_before, (
        "the tmp .env's signature leaked past monkeypatch teardown -- a "
        "later test in the same xdist worker would see a phantom .env "
        "change and have its own config silently reloaded from disk"
    )
    assert config.auto_reload_if_changed() == {}, (
        "a leaked _ENV_MTIME caused a spurious auto-reload against the "
        "real .env outside any test's own isolation"
    )
