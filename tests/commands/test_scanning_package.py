"""Registration guards for the scanning command package."""
import importlib


EXPECTED_COMMANDS = {"recap", "check", "session", "status", "pause", "resume", "stop"}
EXPECTED_LOOPS = {
    "session_scan", "heartbeat", "config_watcher", "trade_monitor",
    "daily_recap", "weekend_deep_scan_task", "market_data_refresh",
}


def test_every_command_is_registered():
    from swingbot.bot_core import bot
    importlib.import_module("swingbot.commands.scanning")
    registered = {command.name for command in bot.commands}
    assert EXPECTED_COMMANDS <= registered, f"missing: {EXPECTED_COMMANDS - registered}"


def test_every_task_loop_is_reachable_on_the_facade():
    scanning = importlib.import_module("swingbot.commands.scanning")
    for name in EXPECTED_LOOPS:
        loop = getattr(scanning, name, None)
        assert loop is not None, f"{name} not exposed on the scanning facade"
        assert hasattr(loop, "start"), f"{name} is not a discord.py task loop"


def test_error_and_before_loop_handlers_are_attached():
    scanning = importlib.import_module("swingbot.commands.scanning")
    assert scanning.session_scan._error is not None
    assert scanning.market_data_refresh._before_loop is not None
