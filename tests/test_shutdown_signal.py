"""SIGTERM must close the bot, not be ignored.

The bot is PID 1 in its container, and the kernel does not apply default
signal dispositions to PID 1 -- a process with no explicit SIGTERM handler
simply ignores it. So every `docker stop` / `docker compose restart` / deploy
sent SIGTERM, got nothing back, waited out the 10s grace period and then
SIGKILLed the bot (exit 137).

These pin the handler itself. What it buys is a clean gateway close and an
exit inside a second; it does NOT let an in-flight scan finish (asyncio.run's
shutdown cancels the @tasks.loop coroutines once bot.run returns) -- see the
docstring on _handle_shutdown_signal.
"""
import asyncio
import signal
import types

import pytest

import swingbot.bot_core as bc


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Module-level install/in-progress flags are process-global; restore
    them so test order can't matter."""
    monkeypatch.setattr(bc, "_shutdown_handler_installed", False)
    monkeypatch.setattr(bc, "_shutdown_in_progress", False)
    monkeypatch.setattr(bc, "_shutdown_task", None)


def _fake_loop():
    loop = types.SimpleNamespace(added=[])
    loop.add_signal_handler = lambda *a: loop.added.append(a)
    return loop


# -- installation ----------------------------------------------------------

def test_registers_sigterm_on_the_running_loop(monkeypatch):
    loop = _fake_loop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    bc.install_shutdown_signal_handler()

    assert [a[0] for a in loop.added] == [signal.SIGTERM]
    assert bc._shutdown_handler_installed is True


def test_installation_is_idempotent(monkeypatch):
    """on_ready can fire more than once (a gateway RESUME re-runs it), and a
    second registration would stack a second close()."""
    loop = _fake_loop()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    bc.install_shutdown_signal_handler()
    bc.install_shutdown_signal_handler()

    assert len(loop.added) == 1


def test_platform_without_add_signal_handler_is_not_fatal(monkeypatch):
    """Windows has no add_signal_handler for SIGTERM. The bot must still
    start -- graceful shutdown is a nice-to-have, not a requirement."""
    loop = types.SimpleNamespace()

    def boom(*a):
        raise NotImplementedError

    loop.add_signal_handler = boom
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    bc.install_shutdown_signal_handler()          # must not raise

    assert bc._shutdown_handler_installed is False


# -- the handler itself ----------------------------------------------------

def _run_handler(times=1):
    closed = []

    async def fake_close():
        closed.append(1)

    async def go():
        for _ in range(times):
            bc._handle_shutdown_signal("SIGTERM")
        # let the task created by the handler actually run
        for _ in range(3):
            await asyncio.sleep(0)
        return bc._shutdown_task

    task = asyncio.run(_with_close(go, fake_close))
    return closed, task


async def _with_close(go, fake_close):
    original = bc.bot.close
    bc.bot.close = fake_close
    try:
        return await go()
    finally:
        bc.bot.close = original


def test_sigterm_closes_the_gateway():
    closed, _ = _run_handler()
    assert closed == [1]


def test_a_second_sigterm_does_not_stack_a_second_close():
    """An impatient second `docker stop` must not start closing twice."""
    closed, _ = _run_handler(times=3)
    assert closed == [1]


def test_the_close_task_is_referenced():
    """asyncio holds only a weak reference to a running task, so a bare
    create_task() whose result nobody keeps can be garbage-collected
    mid-await -- which would silently skip the close it was created for."""
    _, task = _run_handler()
    assert task is not None


def test_a_failing_close_still_lets_the_process_exit():
    """Nothing is salvageable at this point; hanging until Docker's SIGKILL
    is strictly worse than logging and exiting."""
    async def boom():
        raise RuntimeError("gateway already gone")

    async def go():
        bc._handle_shutdown_signal("SIGTERM")
        for _ in range(3):
            await asyncio.sleep(0)
        return bc._shutdown_task

    task = asyncio.run(_with_close(go, boom))
    assert task.done() and task.exception() is None
