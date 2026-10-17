"""v148 OH10: analyze/fetch handlers count their swallowed errors per tag."""
import types

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import analyze, fetch


@pytest.fixture(autouse=True)
def _clean():
    sw.reset()
    yield
    sw.reset()


def test_decision_context_blocks_count_under_their_own_tags(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("probe")

    monkeypatch.setattr(analyze, "load_account_config", boom, raising=False)
    item = types.SimpleNamespace(plan_v2=None, plan=None,
                                 result=types.SimpleNamespace(ticker="AAPL"))
    ctx = analyze.build_decision_context(item, {}, None)
    assert "weekly" not in ctx and "quality" not in ctx
    snap = sw.snapshot()
    for tag in ("weekly", "rs", "outcomes", "sizing", "quality"):
        assert snap[f"scan.decision_context.{tag}"]["count"] == 1, snap


def test_map_tickers_failures_are_counted_and_still_none():
    assert fetch.map_tickers(lambda t: 1 / 0, ["A", "B"], workers=1) == [None, None]
    entry = sw.snapshot()["scan.map_tickers"]
    assert entry["count"] == 2
    assert entry["last_error"] == "ZeroDivisionError: division by zero"
