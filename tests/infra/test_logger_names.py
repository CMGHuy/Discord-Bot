"""v111 §3: every module under swingbot/ names its logger with __name__.

Hard-coded names went stale (e.g. "swing-bot.scan_engine" in six modules,
a shim removed in v27) and made a bot.log line untraceable to its module."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "swingbot"


def _python_files():
    return sorted(ROOT.rglob("*.py"))


def _literal_logger_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger" and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            yield node.lineno, first.value


def test_no_module_names_its_logger_with_a_swing_bot_literal():
    offenders = [f"{path.relative_to(ROOT.parent).as_posix()}:{line} {name!r}"
                 for path in _python_files()
                 for line, name in _literal_logger_names(path)
                 if name.startswith(("swing-bot", "swingbot"))]
    assert offenders == [], "use logging.getLogger(__name__):\n" + "\n".join(offenders)


def _borrows_bot_core_log(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "swingbot.bot_core"
            and any(alias.name == "log" for alias in node.names)]


def test_no_module_borrows_the_bot_core_logger():
    offenders = [f"{path.relative_to(ROOT.parent).as_posix()}:{line}"
                 for path in _python_files() for line in _borrows_bot_core_log(path)]
    assert offenders == [], "give the module its own logging.getLogger(__name__):\n" + "\n".join(offenders)
