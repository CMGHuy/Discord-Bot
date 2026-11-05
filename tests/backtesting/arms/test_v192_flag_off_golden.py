"""v192 flag-off parity (spec § Testing, first bullet): with
MARKET_ENTRY_NEXT_OPEN off and GAP_RECLAIM_ATR at 0 the replay fills and exits
market, stop-entry, limit and v180 Turtle Soup plans exactly as it did before
v192 touched exit_sim.py, builders.py or knobs.py, and run_arm returns the same
ArmTrade rows for both engines. Captured at V192-1, before any v192 code change
-- never regenerate it to make this pass."""
import dataclasses
import json
import math
import os
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting.arms.engine import run_arm
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "v192" / "replay_golden.json"
WINDOW = ("1900-01-01", "2100-12-31")
SIGNALS = range(20, 141, 15)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    """Every searchable knob at its shipped default (the v192 knobs included once they exist)."""
    for f in config.FIELDS:
        if f.search_class == "searchable":
            monkeypatch.setattr(config, f.attr, config._cast(f, f.default), raising=False)


def _wave(n=170):
    rows, prev = [], 100.0
    for i in range(n):
        close = 100.0 + 6.0 * math.sin(i / 5.0) + 0.03 * i
        open_ = prev + 0.4 * math.sin(i * 1.7)
        rows.append((round(open_, 4), round(max(open_, close) + 0.8, 4),
                     round(min(open_, close) - 0.8, 4), round(close, 4)))
        prev = close
    return make_ohlcv(rows, start="2024-01-02")


def _market(c, direction, **kw):
    sign = 1 if direction == "bullish" else -1
    base = dict(direction=direction, entry_type="market", trigger_price=c, entry_price=c,
                status=PlanStatus.ACTIVE, stop_loss=c * (1 - sign * 0.03),
                tp1=c * (1 + sign * 0.04), tp2=c * (1 + sign * 0.08), tp1_fraction=0.5)
    base.update(kw)
    return _plan(**base)


def _turtle(c):
    shape = PLAN_SHAPES[TURTLE_SOUP]
    return _plan(strategy=TURTLE_SOUP, horizon_key="2w", direction="bullish",
                 entry_type=shape["entry_type"], expiry_bars=shape["expiry_bars"],
                 tp1_fraction=shape["tp1_fraction"],
                 breakeven_trigger_fraction=shape["breakeven_trigger_fraction"],
                 hold_cap_bars=shape["hold_cap_bars"], trigger_price=c,
                 stop_loss=c * 0.98, tp1=c * 1.04, tp2=None)


def _plans(c):
    """name -> (plan, scale_out) for one signal close c."""
    return {
        "mkt_strategy_bull_so": (_market(c, "bullish"), True),
        "mkt_strategy_bull_single": (_market(c, "bullish"), False),
        "mkt_strategy_bear_so": (_market(c, "bearish"), True),
        "mkt_confluence_bull_so": (_market(c, "bullish", source="confluence",
                                           strategy="S/R Confluence"), True),
        "mkt_confluence_bear_so": (_market(c, "bearish", source="confluence",
                                           strategy="S/R Confluence"), True),
        "mkt_hold_cap_bull": (_market(c, "bullish", hold_cap_bars=5), True),
        "stop_entry_bull": (_plan(entry_type="stop_entry", trigger_price=c * 1.01,
                                  stop_loss=c * 0.97, tp1=c * 1.05, tp2=c * 1.09,
                                  expiry_bars=3), True),
        "limit_bull": (_plan(entry_type="limit", trigger_price=c * 0.99, stop_loss=c * 0.96,
                             tp1=c * 1.03, tp2=None, tp1_fraction=1.0, expiry_bars=1), True),
        "turtle_soup": (_turtle(c), True),
    }


def _exits():
    df = _wave()
    out = []
    for i in SIGNALS:
        for name, (plan, scale_out) in _plans(float(df["Close"].values[i])).items():
            res = simulate_exit(df, i, plan, scale_out=scale_out)
            out.append({"name": name, "signal": i, "result": dataclasses.asdict(res)})
    return out


def _arms():
    frame = load_v74_fixture()["AAPL"]
    trades = run_arm("AAPL", frame, ("confluence", "strategy"), ("4w",), WINDOW, {})
    return [dataclasses.asdict(t) for t in trades]


def _golden(captured):
    if os.environ.get("V192_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_replay_matches_the_pre_v192_golden():
    captured = json.loads(json.dumps({"exits": _exits(), "arms": _arms()}))
    golden = _golden(captured)
    names = {row["name"] for row in golden["exits"]}
    assert names == set(_plans(100.0)), "every entry family is pinned"
    outcomes = {row["result"]["outcome"] for row in golden["exits"]}
    assert {"win", "loss"} <= outcomes, "the wave must exercise wins and losses"
    assert len(golden["arms"]) >= 5, "the arm capture must hold real trades"
    assert captured == golden
