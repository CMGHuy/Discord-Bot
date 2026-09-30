"""v111 §3: an exception a command shows the user is also logged with its traceback."""
import ast
import asyncio
import logging
import pathlib

COMMANDS = pathlib.Path(__file__).resolve().parents[2] / "swingbot" / "commands"
_REPLIES = {"send", "send_message", "edit"}


def _calls(handler):
    return [node for stmt in handler.body for node in ast.walk(stmt)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]


def _logs_traceback(handler):
    for call in _calls(handler):
        if call.func.attr == "exception":
            return True
        if call.func.attr in {"warning", "error"} and any(k.arg == "exc_info" for k in call.keywords):
            return True
    return False


def _silent_user_facing_handlers(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        catches_exception = isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
        replies = any(call.func.attr in _REPLIES for call in _calls(handler))
        if catches_exception and replies and not _logs_traceback(handler):
            yield handler.lineno


def test_every_user_facing_exception_is_logged_with_its_traceback():
    offenders = [f"{path.relative_to(COMMANDS.parent.parent).as_posix()}:{line}"
                 for path in sorted(COMMANDS.rglob("*.py"))
                 for line in _silent_user_facing_handlers(path)]
    assert offenders == [], "add log.warning(..., exc_info=True) beside the reply:\n" + "\n".join(offenders)


class _Ctx:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(args[0] if args else kwargs)


def test_ticker_command_failure_is_logged_and_still_shown(monkeypatch, caplog):
    from swingbot.commands import info

    def boom(ticker):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(info, "_sync_ticker_snapshot", boom)
    ctx = _Ctx()
    with caplog.at_level(logging.WARNING, logger=info.log.name):
        asyncio.run(info.ticker_cmd.callback(ctx, "aapl"))

    [record] = [r for r in caplog.records if r.name == info.log.name]
    assert record.levelno == logging.WARNING and record.exc_info is not None
    assert "AAPL" in record.getMessage()
    assert ctx.sent[-1] == "⚠️ Could not fetch data for AAPL: yahoo down"


def test_backtest_watchlist_worker_failure_is_logged_and_still_reported(monkeypatch, caplog):
    from swingbot.commands import backtest

    def boom(ticker, period="max"):
        raise RuntimeError("no data")

    monkeypatch.setattr(backtest, "get_daily_data", boom)
    with caplog.at_level(logging.WARNING, logger=backtest.log.name):
        summaries, errors = backtest._sync_backtest_watchlist(["AAPL"], "swing", None, None, None)

    [record] = [r for r in caplog.records if r.name == backtest.log.name]
    assert record.exc_info is not None and "AAPL" in record.getMessage()
    assert summaries == [] and errors == [("AAPL", "no data")]
