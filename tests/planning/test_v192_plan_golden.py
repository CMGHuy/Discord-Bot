"""v192 flag-off parity for the builders: with MARKET_ENTRY_NEXT_OPEN off and
GAP_RECLAIM_ATR at 0, market plans are built ACTIVE with entry_price = the
entry, a market_entry transition, and no reclaim_atr / reclaim_level / waits_next_open /
reclaim_session key. Captured at V192-1 on unmodified code; never regenerate."""
import json
import os
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from swingbot.core.planning.plan_types import plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v192" / "plan_golden.json"
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")
RECLAIM_KEYS = ("reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open")
#: name -> (direction, entry, level stop, own target)
CONFLUENCE = {
    "conf_bull": ("bullish", 100.0, 98.4, 104.0),
    "conf_bear": ("bearish", 100.0, 101.6, 96.0),
    "conf_penny_bull": ("bullish", 0.85, 0.838, 0.88),
}
STRATEGY_PLANS = 8


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    for f in config.FIELDS:
        if f.search_class == "searchable":
            monkeypatch.setattr(config, f.attr, config._cast(f, f.default), raising=False)


def _snap(plan):
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _confluence(direction, entry, stop, target):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([entry] * 60, spread=0.05), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")
    return None if plan is None else _snap(plan)


def _strategy_sweep():
    df = load_v74_fixture()["AAPL"]
    found = []
    for index in range(120, len(df), 7):
        for strategy in ALL_STRATEGIES:
            for direction in ("bullish", "bearish"):
                plan = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                           horizon_key="4w", direction=direction)
                if plan is not None and plan.entry_type == "market":
                    found.append({"index": index, **_snap(plan)})
                if len(found) == STRATEGY_PLANS:
                    return found
    return found


def _capture():
    return {"confluence": {name: _confluence(*args) for name, args in CONFLUENCE.items()},
            "strategy": _strategy_sweep()}


def _golden(captured):
    if os.environ.get("V192_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_market_plans_match_the_pre_v192_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    built = [s for s in golden["confluence"].values() if s is not None] + golden["strategy"]
    assert len(golden["strategy"]) == STRATEGY_PLANS, "the sweep must find real strategy plans"
    assert len(built) >= STRATEGY_PLANS + 2
    for snap in built:
        _assert_market_plan(snap)
    assert captured == golden


def _assert_market_plan(snap):
    assert snap["plan"]["entry_type"] == "market"
    assert snap["plan"]["status"] == "ACTIVE"
    assert snap["plan"]["entry_price"] == snap["plan"]["trigger_price"]
    assert not set(RECLAIM_KEYS) & set(snap["keys"])
