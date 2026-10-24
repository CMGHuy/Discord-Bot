"""V183-7: long sizing is byte-identical to pre-v183 main (golden values captured
at 7ac5e4ea), whatever a long is handed: no stamp, a gap stamp, a stop stamp."""
import pytest

from swingbot import config
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size
from swingbot.core.planning.gap_sizing import size_for, size_for_plan
from swingbot.core.tracking.performance import TradeLog
from tests.planning.test_plan_engine_model import _plan
from tests.store_seed import seed_store

BASE = {"balance": 10000.0, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 20.0,
        "max_position_value_absolute": 0.0, "max_risk_amount_absolute": 0.0}
RISK_ROWS = [((100.0, 95.0), 20.0, 100.0, 2000.0, False), ((50.0, 49.0), 40.0, 40.0, 2000.0, True),
             ((250.0, 240.0), 8.0, 80.0, 2000.0, True), ((10.0, 9.5), 200.0, 100.0, 2000.0, False),
             ((174.5, 170.96), 11.46, 40.57, 2000.0, True)]
ACCOUNT_ROWS = [((100.0, 95.0), 10.0, 50.0, 1000.0, False), ((50.0, 49.0), 20.0, 20.0, 1000.0, False),
                ((250.0, 240.0), 4.0, 40.0, 1000.0, False), ((10.0, 9.5), 100.0, 50.0, 1000.0, False),
                ((174.5, 170.96), 5.73, 20.29, 1000.0, False)]
GOLDEN = ([("risk_pct", *row, "risk_pct") for row in RISK_ROWS]
          + [("min_of_all", *row, "risk_pct") for row in RISK_ROWS]
          + [("account_pct", *row, "account_pct") for row in ACCOUNT_ROWS])
STAMPS = [None, {"rule": "gap_p99", "up_gap_p99_pct": 4.0, "n_up_gaps": 120},
          {"rule": "stop", "up_gap_p99_pct": 4.0, "n_up_gaps": 120}]


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


def _expected(shares, risk_amount, position_value, capped, mode):
    return dict(BASE, shares=shares, risk_amount=risk_amount, position_value=position_value,
                capped=capped, mode=mode)


@pytest.mark.parametrize("mode,levels,shares,risk,value,capped,out_mode", GOLDEN)
def test_long_sizing_matches_pre_v183_main(mode, levels, shares, risk, value, capped, out_mode):
    cfg = dict(BASE, sizing_mode=mode)
    entry, stop = levels
    expected = _expected(shares, risk, value, capped, out_mode)
    assert compute_position_size(entry, stop, cfg) == expected
    assert compute_position_size(entry, stop, cfg, gap_floor_pct=None) == expected
    for stamp in STAMPS:
        assert size_for(entry, stop, direction="bullish", gap_sizing=stamp, account_cfg=cfg) == expected
    plan = _plan(direction="bullish", trigger_price=entry, stop_loss=stop)
    assert size_for_plan(plan, account_cfg=cfg) == expected


def test_a_long_trade_record_is_unchanged_by_the_new_keyword(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", dict(BASE, sizing_mode="risk_pct", balance_history=[]))
    tlog = TradeLog()
    common = dict(ticker="AAPL", strategy="VWAP", horizon_key="4w", direction="bullish",
                  confidence_level=3, confidence_label="Medium", entry=100.0, stop_loss=95.0,
                  take_profit=110.0)
    tlog.log_trade(**common, plan_id="a")
    tlog.log_trade(**common, plan_id="b", gap_sizing=None)
    without, with_none = tlog.trade_for_plan("a"), tlog.trade_for_plan("b")
    volatile = {"id", "plan_id", "opened_at"}
    assert {k: v for k, v in without.items() if k not in volatile} == \
           {k: v for k, v in with_none.items() if k not in volatile}
    assert "gap_sizing" not in without and "risk_notice" not in without
    assert without["shares"] == 20.0
