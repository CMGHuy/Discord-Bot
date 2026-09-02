"""
commands/scanning's config_watcher background task (30s interval).

Production incident (2026-09-02): same root cause and same commit as the
_send_alerts NameError (see tests/infra/test_silent_alerts_channel.py's
test_the_scan_tick_actually_delivers_a_built_alert) -- the v61 refactor that
moved config_watcher's body into loops.py referenced _MANUAL_CLOSE_QUEUE and
_TRIGGER_FILE (both defined in runstate.py) by their bare names instead of
runstate._MANUAL_CLOSE_QUEUE / runstate._TRIGGER_FILE. Neither name is
imported into loops.py's own namespace, so every tick raised NameError as
soon as it reached the manual-close-notification-queue check, was caught by
@config_watcher.error, and the loop restarted itself forever -- silently
losing config hot-reload and the admin UI's "Run !check now" trigger.

No pytest-asyncio in this repo -- coroutines are driven with asyncio.run().
"""
import asyncio

from swingbot.commands.scanning import loops


def _run(coro):
    return asyncio.run(coro)


def test_config_watcher_tick_completes_without_a_nameerror(monkeypatch, tmp_path):
    monkeypatch.setattr(loops, "auto_reload_if_changed", lambda: {}, raising=False)
    # Point both queue/trigger files at a directory guaranteed not to contain
    # them, so the tick takes the "nothing queued" path either way -- the bug
    # is a NameError on the bare name, which fires regardless of file state.
    monkeypatch.setattr(loops.runstate, "_MANUAL_CLOSE_QUEUE", str(tmp_path / "manual_close_notify.json"))
    monkeypatch.setattr(loops.runstate, "_TRIGGER_FILE", str(tmp_path / "trigger_check.flag"))

    _run(loops.config_watcher.coro())
