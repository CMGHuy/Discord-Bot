"""v140: the screen is research tooling. Nothing under swingbot/ outside
swingbot/core/backtesting/ may import it (no research code in the live path)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCREEN = "swingbot.core.backtesting.screen"
BACKTESTING = ROOT / "swingbot" / "core" / "backtesting"


def imported_names(text: str) -> set:
    """Every dotted module name an import statement can bind, including
    ``from pkg import mod`` as ``pkg.mod``."""
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _reaches_screen(names) -> bool:
    return any(n == SCREEN or n.startswith(SCREEN + ".") for n in names)


def test_the_guard_sees_both_import_forms():
    assert _reaches_screen(imported_names("from swingbot.core.backtesting import screen"))
    assert _reaches_screen(imported_names("import swingbot.core.backtesting.screen.race"))
    assert not _reaches_screen(imported_names("from swingbot.core.backtesting import acceptance"))


def test_nothing_outside_backtesting_imports_the_screen():
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "swingbot").rglob("*.py"))
        if BACKTESTING not in path.parents
        and _reaches_screen(imported_names(path.read_text(encoding="utf-8")))
    ]
    assert offenders == []
