"""Guards the v61 split of plan_engine.py."""
import ast
import pathlib

from swingbot.core.planning import plan_engine

PKG = pathlib.Path(plan_engine.__file__).parent


def test_every_exported_name_resolves():
    for name in plan_engine.__all__:
        assert getattr(plan_engine, name, None) is not None, f"{name} exported but missing"


def test_scanning_still_gets_what_it_imports():
    assert plan_engine.build_confluence_plan is not None
    assert plan_engine.primary_strategy_for is not None


def test_backtest_and_live_share_one_simulator():
    from swingbot.core.backtesting import backtest
    from swingbot.core.planning import exit_sim
    assert backtest.simulate_exit is exit_sim.simulate_exit


def test_no_submodule_imports_the_facade():
    offenders = []
    for path in PKG.glob("*.py"):
        if path.name == "plan_engine.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(a.name == "plan_engine" for a in node.names):
                offenders.append(path.name)
    assert offenders == [], f"import cycle risk: {offenders}"
