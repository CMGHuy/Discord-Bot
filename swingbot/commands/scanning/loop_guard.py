"""Restart-on-error for the bot's background ``tasks.loop`` jobs.

When a loop body raises, discord.ext.tasks awaits the loop's error handler and
then re-raises, which ends the task for good. The handler runs *inside* that
still-running task, so ``loop.is_running()`` is True there and the old
``if not loop.is_running(): loop.restart()`` handlers never restarted anything.

``restart_on_error`` installs a handler that logs the traceback and, once the
failed task has actually finished, starts the loop again after a delay (the
loop's own interval, clamped), so a body that fails every time retries on its
schedule instead of spinning. A cancelled loop (``loop.cancel()``/``stop()``)
never reaches the error handler and is left alone.
"""
from __future__ import annotations

import asyncio
import logging

from discord.ext import tasks

from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)

MIN_RESTART_DELAY_S = 5.0
MAX_RESTART_DELAY_S = 300.0


def restart_delay(loop: tasks.Loop) -> float:
    """The loop's interval in seconds, clamped to [MIN, MAX]."""
    interval = (loop.hours or 0) * 3600 + (loop.minutes or 0) * 60 + (loop.seconds or 0)
    return min(MAX_RESTART_DELAY_S, max(MIN_RESTART_DELAY_S, float(interval)))


def _start_if_idle(loop: tasks.Loop, name: str) -> None:
    if loop.is_running():
        return
    try:
        loop.start()
        log.warning("%s loop restarted after a failure", name)
    except Exception as exc:
        swallowed(log, "scan.loop_guard.restart", exc, "%s loop could not be restarted", name,
                  level=logging.ERROR, exc_info=True)


def _schedule_restart(loop: tasks.Loop, name: str, delay: float) -> None:
    event_loop = asyncio.get_running_loop()

    def _when_done(_task) -> None:
        event_loop.call_later(delay, _start_if_idle, loop, name)

    task = loop.get_task()
    if task is None or task.done():
        _when_done(task)
    else:
        task.add_done_callback(_when_done)


def restart_on_error(loop: tasks.Loop, name: str, *, delay: float | None = None) -> tasks.Loop:
    """Install the log-and-restart error handler on ``loop``; returns ``loop``."""
    wait = restart_delay(loop) if delay is None else delay

    async def _on_error(*args) -> None:
        exc = args[-1]
        log.error("%s loop raised past its own handling -- restarting in %.0fs: %s",
                  name, wait, exc, exc_info=exc)
        _schedule_restart(loop, name, wait)

    _on_error.__loop_guard__ = True
    loop.error(_on_error)
    return loop
