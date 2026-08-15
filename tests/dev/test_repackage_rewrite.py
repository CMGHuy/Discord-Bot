"""Unit tests for the one-shot v27 re-package tool. Deleted with it in Task 15."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "_repackage", Path(__file__).resolve().parents[2] / "scripts" / "dev" / "_repackage.py")
_repackage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repackage)
rewrite = _repackage.rewrite


def test_absolute_module_import():
    assert rewrite("from swingbot.core.infra.jsonio import atomic_write_json") == \
        "from swingbot.core.infra.jsonio import atomic_write_json"


def test_string_literal_patch_target():
    assert rewrite('mock.patch("swingbot.core.marketdata.data.fetch_ohlc")') == \
        'mock.patch("swingbot.core.marketdata.data.fetch_ohlc")'


def test_package_attribute_import_with_alias():
    assert rewrite("from swingbot.core import data as data_module") == \
        "from swingbot.core.marketdata import data as data_module"


def test_package_attribute_split_across_packages():
    out = rewrite("from swingbot.core import levels, jsonio")
    assert "from swingbot.core.market import levels" in out
    assert "from swingbot.core.infra import jsonio" in out


def test_sibling_relative_becomes_absolute():
    assert rewrite("from .indicators import atr") == \
        "from swingbot.core.market.indicators import atr"


def test_parent_relative_becomes_absolute():
    assert rewrite("from ..volatility import bollinger_bands") == \
        "from swingbot.core.market.volatility import bollinger_bands"


def test_parent_relative_package_attribute():
    assert rewrite("from .. import levels") == \
        "from swingbot.core.market import levels"


def test_indented_relative_import_keeps_indent():
    assert rewrite("        from ..indicators import atr as a") == \
        "        from swingbot.core.market.indicators import atr as a"


def test_non_moving_packages_untouched():
    for line in ("from swingbot.core.charts.trade_chart import render",
                 "from swingbot.core.edge.sizing import size_position",
                 "from swingbot.core.scanning.engine import run_scan"):
        assert rewrite(line) == line


def test_multiline_import_prefix_only():
    src = "from .plan_engine import (\n    build_strategy_plan,\n)"
    assert rewrite(src) == \
        "from swingbot.core.planning.plan_engine import (\n    build_strategy_plan,\n)"


def test_idempotent():
    once = rewrite("from swingbot.core.infra.jsonio import atomic_write_json")
    assert rewrite(once) == once


def test_parenthesised_package_import_fails_loudly():
    """The one form the rewriter cannot see must abort, not pass through."""
    import pytest
    with pytest.raises(SystemExit, match="parenthesised"):
        rewrite("from swingbot.core import (\n    levels,\n    jsonio,\n)")
