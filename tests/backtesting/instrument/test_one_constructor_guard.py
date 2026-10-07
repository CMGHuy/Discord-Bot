"""v136 rule 3: one plan constructor.

`_trade_plan_at` is gone from production code. The frozen v1 instrument keeps
its arithmetic as `_v1_plan_levels`, reachable only from run_backtest's v1 loop
and the two v1 parity reports. Inside backtest.py, plans are constructed in
exactly two places: `_bt_plan` (v1) and `_live_plan_at` (v2, via
build_strategy_plan).
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKTEST = ROOT / "swingbot" / "core" / "backtesting" / "backtest.py"
RETIRED = re.compile(r"(?<![A-Za-z0-9_])_trade_plan_at(?![A-Za-z0-9_])")
V1_ONLY = "_v1_plan_levels"
V1_CALLERS = {
    "swingbot/core/backtesting/backtest.py",
    "scripts/reports/parity_exits.py",
    "scripts/reports/parity_sizing.py",
}


def _sources():
    for top in ("swingbot", "scripts"):
        for path in sorted((ROOT / top).rglob("*.py")):
            yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8", errors="replace")


def _references(text, name):
    """True when code (not a comment or string) names `name`: a bare name, an
    attribute, or an import alias. Prose in comments may mention the v1 path."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.alias) and node.name == name:
            return True
    return False


def _callers_by_name(path):
    """{called bare name: {enclosing top-level function names}} for one module."""
    found = {}
    for fn in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                found.setdefault(node.func.id, set()).add(fn.name)
    return found


def test_the_retired_constructor_name_is_gone_from_production_code():
    assert [rel for rel, text in _sources() if RETIRED.search(text)] == []


def test_only_frozen_v1_code_reaches_the_v1_plan_path():
    assert [rel for rel, text in _sources()
            if rel not in V1_CALLERS and _references(text, V1_ONLY)] == []


def test_backtest_constructs_plans_in_exactly_two_places():
    calls = _callers_by_name(BACKTEST)
    assert calls.get("TradePlanV2") == {"_bt_plan"}
    assert calls.get("build_strategy_plan") == {"_live_plan_at"}
    assert calls.get("_bt_plan") == {"run_backtest"}
    assert calls.get("_v1_plan_levels") == {"run_backtest"}
    assert calls.get("_live_plan_at") == {"_replay_live_constructor"}
