"""A background tasks.loop that raises is logged with its traceback and restarted.

discord.py calls a loop's error handler from inside the still-running task, so
`loop.is_running()` is True there: the old `if not loop.is_running(): restart()`
handlers never restarted anything, and the loop stayed dead until the next
container restart.
"""
import asyncio
import logging

from discord.ext import tasks

from swingbot.commands.scanning import loop_guard, loops, ops_watch


def _flaky_loop(fail_times: int, ran: list):
    @tasks.loop(seconds=0.01)
    async def flaky():
        ran.append(len(ran))
        if len(ran) <= fail_times:
            raise RuntimeError(f"boom {len(ran)}")
        flaky.stop()
    return flaky


def test_a_raising_loop_is_restarted_after_the_delay(monkeypatch, caplog):
    ran: list = []
    flaky = _flaky_loop(1, ran)
    loop_guard.restart_on_error(flaky, "flaky", delay=0.01)

    async def run():
        flaky.start()
        for _ in range(200):
            await asyncio.sleep(0.01)
            if len(ran) >= 2 and not flaky.is_running():
                break

    with caplog.at_level(logging.ERROR, logger=loop_guard.log.name):
        asyncio.run(run())
    assert len(ran) >= 2, "loop never ran again after raising"
    record = next(r for r in caplog.records if "flaky" in r.getMessage())
    assert record.exc_info and isinstance(record.exc_info[1], RuntimeError)


def test_restart_survives_repeated_failures(monkeypatch):
    ran: list = []
    flaky = _flaky_loop(3, ran)
    loop_guard.restart_on_error(flaky, "flaky", delay=0.01)

    async def run():
        flaky.start()
        for _ in range(300):
            await asyncio.sleep(0.01)
            if len(ran) >= 4 and not flaky.is_running():
                break

    asyncio.run(run())
    assert len(ran) >= 4


def test_a_cancelled_loop_is_not_restarted():
    ran: list = []

    @tasks.loop(seconds=0.01)
    async def steady():
        ran.append(1)

    loop_guard.restart_on_error(steady, "steady", delay=0.01)

    async def run():
        steady.start()
        await asyncio.sleep(0.05)
        steady.cancel()
        await asyncio.sleep(0.05)
        return steady.is_running()

    assert asyncio.run(run()) is False


def test_restart_delay_defaults_to_the_loop_interval_within_bounds():
    @tasks.loop(seconds=30)
    async def every_30s():
        pass

    @tasks.loop(minutes=15)
    async def every_15m():
        pass

    @tasks.loop(seconds=1)
    async def every_1s():
        pass

    assert loop_guard.restart_delay(every_30s) == 30
    assert loop_guard.restart_delay(every_15m) == loop_guard.MAX_RESTART_DELAY_S
    assert loop_guard.restart_delay(every_1s) == loop_guard.MIN_RESTART_DELAY_S


def test_every_background_loop_has_the_guard():
    found = {name: obj for mod in (loops, ops_watch) for name, obj in vars(mod).items()
             if isinstance(obj, tasks.Loop)}
    assert len(found) >= 17
    unguarded = sorted(name for name, obj in found.items()
                       if getattr(obj._error, "__loop_guard__", False) is not True)
    assert unguarded == []
