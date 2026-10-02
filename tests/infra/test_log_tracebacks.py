"""v111 §4: no warning or error about a caught exception is missing its
traceback, and log.exception() never repeats the exception text itself.

"Logs a caught exception" = a log.warning/log.error call inside an
`except ... as <name>:` block whose arguments mention <name>."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "swingbot"
_LOGGERS = {"log", "logger"}


def _is_log_call(node, methods):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in methods and isinstance(node.func.value, ast.Name)
            and node.func.value.id in _LOGGERS)


def _mentions(call, name):
    return any(isinstance(n, ast.Name) and n.id == name for arg in call.args for n in ast.walk(arg))


def _handler_calls(tree):
    for handler in ast.walk(tree):
        if isinstance(handler, ast.ExceptHandler) and handler.name:
            for stmt in handler.body:
                for node in ast.walk(stmt):
                    yield handler.name, node


def _findings(path):
    where = path.relative_to(ROOT.parent).as_posix()
    for name, node in _handler_calls(ast.parse(path.read_text(encoding="utf-8"))):
        if (_is_log_call(node, {"warning", "error"}) and _mentions(node, name)
                and not any(k.arg == "exc_info" for k in node.keywords)):
            yield f"{where}:{node.lineno} missing exc_info=True"
        if _is_log_call(node, {"exception"}) and _mentions(node, name):
            yield f"{where}:{node.lineno} log.exception repeats the exception argument"


def test_caught_exceptions_are_logged_with_their_traceback():
    offenders = [finding for path in sorted(ROOT.rglob("*.py")) for finding in _findings(path)]
    assert offenders == [], "\n".join(offenders)
