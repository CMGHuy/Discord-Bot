"""Guards the v61 split: facades stay complete and dependencies one-way."""
import ast
import pathlib

from swingbot.core.scanning import engine


PKG = pathlib.Path(engine.__file__).parent


def test_every_exported_name_resolves():
    for name in engine.__all__:
        assert getattr(engine, name, None) is not None, f"{name} in __all__ but not importable"


def test_no_submodule_imports_the_facade():
    """Named singleton imports are allowed; importing the module is not."""
    offenders = []
    for path in PKG.glob("*.py"):
        if path.name == "engine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in (None, "."):
                if any(alias.name == "engine" for alias in node.names):
                    offenders.append(path.name)
    assert offenders == [], f"import cycle risk -- these import the facade: {offenders}"


def test_fetch_does_not_import_analyze():
    """CRAWL must not depend on ANALYZE."""
    tree = ast.parse((PKG / "fetch.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "analyze" not in imported


def test_trade_log_is_one_object():
    from swingbot.core.scanning import scan_run

    assert scan_run.trade_log is engine.trade_log
