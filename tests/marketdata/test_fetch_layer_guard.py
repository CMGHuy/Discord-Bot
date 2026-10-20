"""v171 D1/D8: every Alpaca and yfinance request in swingbot/ goes through the
shared layer. A provider call lives in a provider function the layer calls;
this guard fails any direct import or download anywhere else."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALLOWED = frozenset({
    "swingbot/core/marketdata/shared/",            # the layer itself (the tape feed's Yahoo download)
    "swingbot/core/marketdata/providers/",         # alpaca-py is imported only here
    "swingbot/core/marketdata/yf_safe.py",         # the serialised, budgeted yfinance wrapper
    "swingbot/core/marketdata/data.py",            # quote, daily-batch and metadata provider functions
    "swingbot/core/marketdata/data_store.py",      # yfinance-basis daily and intraday writers (leased)
    "swingbot/core/marketdata/data_refresh.py",    # batched yfinance-basis bar refresh writer (leased)
    "swingbot/core/marketdata/daily_delta.py",     # D4 window and full fetch on the yfinance basis
    "swingbot/core/market/events.py",              # earnings provider functions behind layer.get
    "swingbot/core/marketdata/backtest_cache.py",  # research cache: backtests are out of scope (spec D3)
    "swingbot/core/marketdata/export_data.py",     # research export: out of scope (spec D3)
})


def _provider_module(name: str) -> bool:
    return name.split(".")[0] in {"yfinance", "alpaca"}


def _import_hit(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [f"import {a.name}" for a in node.names if _provider_module(a.name)]
    if not (isinstance(node, ast.ImportFrom) and node.module):
        return []
    if _provider_module(node.module):
        return [f"from {node.module}"]
    if node.module.endswith("yf_safe") and any(a.name == "download" for a in node.names):
        return ["from yf_safe import download"]
    return []


def _download_hit(node: ast.AST) -> list[str]:
    if (isinstance(node, ast.Attribute) and node.attr == "download"
            and isinstance(node.value, ast.Name) and node.value.id == "yf_safe"):
        return [f"yf_safe.download at line {node.lineno}"]
    return []


def _violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        found += _import_hit(node) + _download_hit(node)
    return found


def _allowed(rel: str) -> bool:
    return any(rel == a or (a.endswith("/") and rel.startswith(a)) for a in ALLOWED)


def test_no_provider_call_outside_the_layer():
    offenders = {}
    for path in sorted((ROOT / "swingbot").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if not _allowed(rel) and (hits := _violations(path)):
            offenders[rel] = hits
    assert offenders == {}, (
        "Direct Alpaca/yfinance use outside the shared layer (spec v171 D1). Route it "
        f"through swingbot/core/marketdata/shared (layer.get or layer.lease): {offenders}")


def test_every_allowlisted_file_still_needs_its_entry():
    for entry in ALLOWED:
        path = ROOT / entry
        assert path.exists(), f"stale allowlist entry {entry}"
        if path.is_file():
            assert _violations(path), f"{entry} no longer calls a provider: drop it from ALLOWED"


def test_the_guard_sees_every_form(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import yfinance as yf\n"
        "from alpaca.data.historical import StockHistoricalDataClient\n"
        "from swingbot.core.marketdata.yf_safe import download\n"
        "from swingbot.core.marketdata import yf_safe\n"
        "yf_safe.download('AAPL')\n", encoding="utf-8")
    assert len(_violations(sample)) == 4
