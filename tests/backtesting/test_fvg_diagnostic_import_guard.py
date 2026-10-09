"""v143: the diagnostic is research tooling. Nothing under swingbot/, and
neither entry point, may import it (no research code in the live path)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = "swingbot.core.backtesting.fvg_diagnostic"


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


def test_the_guard_sees_both_import_forms():
    assert MODULE in imported_names("from swingbot.core.backtesting import fvg_diagnostic")
    assert MODULE in imported_names("import swingbot.core.backtesting.fvg_diagnostic as fd")
    assert MODULE not in imported_names("from swingbot.core.market import fvg")


def test_no_live_path_imports_the_diagnostic():
    live = sorted((ROOT / "swingbot").rglob("*.py")) + [ROOT / "bot.py", ROOT / "admin_ui.py"]
    offenders = [path.relative_to(ROOT).as_posix() for path in live
                 if MODULE in imported_names(path.read_text(encoding="utf-8"))]
    assert offenders == []
