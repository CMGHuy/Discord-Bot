"""v147 V147-9: the fail-open live gate-rejection recorder."""
import datetime as dt
import logging
from types import SimpleNamespace

import pytest

from swingbot.core.edge import rs_gate
from swingbot.core.market.levels import Scenario
from swingbot.core.planning.builders import primary_strategy_for
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.scanning import qualify
from swingbot.core.scanning import rejection_recorder as rr
from tests.helpers import make_ohlcv

UTC = dt.timezone.utc
AFTER_CLOSE = dt.datetime(2024, 2, 26, 22, 0, tzinfo=UTC)   # 17:00 ET: the 2024-02-26 bar is complete
INTRADAY = dt.datetime(2024, 2, 26, 15, 0, tzinfo=UTC)      # 10:00 ET: the 2024-02-26 bar is forming


class FakeRepo:
    def __init__(self, fail=False):
        self.records, self.fail = [], fail

    def insert_ignore(self, record):
        if self.fail:
            raise RuntimeError("database down")
        self.records.append(record)
        return True


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(rr, "_repo", lambda: fake)
    monkeypatch.setattr(rr, "_utc_now", lambda: AFTER_CLOSE)
    return fake


def _frame():
    frame = make_ohlcv([100.0 + 0.1 * i for i in range(40)], start="2024-01-02")
    assert frame.index[-1].date().isoformat() == "2024-02-26"      # close 103.9; 2024-02-23 close 103.8
    return frame


def _scenario():
    return Scenario(direction="bearish", entry=103.9, market_price=103.9, stop_loss=106.0,
                    stop_sources=["Rolling resistance"], stop_distance_pct=2.02, tight_stop=False,
                    atr_floor_pct=1.5, take_profit=98.0, target_distance_pct=5.7,
                    target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
                    target2_sources=None)


def _plan():
    return TradePlanV2(plan_id="p1", ticker="AAPL", created_at="2024-02-26", source="confluence",
                       strategy="Fibonacci", horizon_key="4w", direction="bearish",
                       entry_type="stop_entry", trigger_price=103.9, entry_price=None, expiry_bars=5,
                       stop_loss=106.5, tp1=98.0, tp1_fraction=0.5, tp2=95.0,
                       breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                       quality_breakdown=[], badge="WEAK", badge_stats={},
                       status=PlanStatus.PENDING, status_history=[])


def _item(**over):
    base = dict(result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="bearish"),
                plan=_scenario(), rs_combined=40.0, plan_v2_rejected_plan=None,
                plan_v2_rejected_margin=None)
    base.update(over)
    return SimpleNamespace(**base)


def _kwargs(**over):
    base = dict(ticker="AAPL", gate="rs", reason="rs_blocked", source="confluence",
                strategy="Fibonacci", horizon="4w", direction="bearish", signal_date="2024-02-26",
                frame=_frame(), margin=15.0, scenario=_scenario())
    base.update(over)
    return base


@pytest.mark.parametrize("value", [5.0, 24.9, 25.0, 25.1, 40.0, 90.0])
def test_rs_margin_is_positive_exactly_where_the_bearish_gate_blocks(value):
    blocked = rs_gate.rs_verdict("AAPL", "bearish", value, rs_available=True)["status"] == "block"
    assert (rs_gate.rs_margin(value) > 0) == blocked
    assert rs_gate.rs_margin(value + 1.0) - rs_gate.rs_margin(value) == pytest.approx(1.0)


def test_a_completed_signal_bar_is_stored_as_the_price_basis(repo):
    assert rr.record_rejection(**_kwargs()) is True
    (row,) = repo.records
    assert row["signal_date"] == "2024-02-26" and row["signal_close"] == pytest.approx(103.9)
    assert "basis_date" not in row
    assert row["cf_status"] == "pending" and row["resolved_at"] is None
    assert row["created_at"] == AFTER_CLOSE
    assert "heat_before" in row and row["heat_before"] is None
    assert "heat_cap" in row and row["heat_cap"] is None
    assert row["scenario"]["entry"] == 103.9 and row["plan"] is None
    assert row["margin"] == 15.0 and row["source"] == "confluence"


def test_a_forming_signal_bar_stores_the_last_completed_bar_as_the_basis(repo, monkeypatch):
    monkeypatch.setattr(rr, "_utc_now", lambda: INTRADAY)
    rr.record_rejection(**_kwargs())
    (row,) = repo.records
    assert row["signal_date"] == "2024-02-26"            # the live constructor's created_at
    assert row["signal_close"] is None
    assert row["basis_date"] == "2024-02-23" and row["basis_close"] == pytest.approx(103.8)


def test_no_qualifying_target_is_inserted_already_no_plan(repo):
    rr.record_rejection(**_kwargs(gate="plan_rejected", reason="no_qualifying_target", margin=None))
    (row,) = repo.records
    assert row["cf_status"] == "no-plan" and row["resolved_at"] == row["created_at"] == AFTER_CLOSE


def test_a_plan_object_is_stored_as_its_dict(repo):
    plan = _plan()
    rr.record_rejection(**_kwargs(gate="plan_rejected", reason="risk_cap", plan=plan))
    assert repo.records[0]["plan"] == plan_to_dict(plan)


def test_spot_metals_are_never_stored(repo):
    assert rr.record_rejection(**_kwargs(ticker="XAUUSD")) is False
    assert repo.records == []


def test_a_failing_write_returns_false_and_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(rr, "_repo", lambda: FakeRepo(fail=True))
    monkeypatch.setattr(rr, "_last_warning", None)
    with caplog.at_level(logging.DEBUG, logger=rr.__name__):
        assert rr.record_rejection(**_kwargs()) is False
        assert rr.record_rejection(**_kwargs()) is False
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "scan unaffected" in warnings[0].getMessage()


def test_a_snapshot_that_cannot_be_built_never_raises(repo):
    assert rr.record_rejection(**_kwargs(frame=None)) is False
    assert rr.record_item_block(_item(), {}, "rs", "rs_blocked", source="confluence") is False
    assert repo.records == []


def test_strategy_rs_block_carries_the_margin_and_the_pins(repo):
    deps = SimpleNamespace(rs_combined_of=lambda ticker: 40.0)
    assert rr.record_strategy_block(deps, _frame(), ticker="AAPL", strategy="RSI", horizon="2w",
                                    direction="bearish", gate="rs", reason="rs_blocked") is True
    (row,) = repo.records
    assert row["source"] == "strategy" and row["strategy"] == "RSI" and row["horizon"] == "2w"
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(40.0))
    assert row["plan"] is None and row["scenario"] is None
    assert {"stop_mult", "tp2_r", "time_stop_days", "params"} <= set(row["scan_params"])
    assert row["scan_params"]["params"]                        # ScanParams pinned at block time


def test_strategy_compression_block_keeps_its_stamp_and_has_no_margin(repo):
    deps = SimpleNamespace(rs_combined_of=lambda ticker: None)
    rr.record_strategy_block(deps, _frame(), ticker="AAPL", strategy="Compression Short",
                             horizon="2w", direction="bearish", gate="compression",
                             reason="earnings_blackout", entry_context={"compression_mode": "broad"})
    (row,) = repo.records
    assert row["gate"] == "compression" and row["reason"] == "earnings_blackout"
    assert row["margin"] is None and row["entry_context"] == {"compression_mode": "broad"}


def test_confluence_rs_block_is_labelled_with_the_primary_strategy(repo):
    item = _item()
    assert rr.record_item_block(item, {"AAPL": _frame()}, "rs", "rs_blocked", source="confluence")
    (row,) = repo.records
    assert row["strategy"] == primary_strategy_for(item.plan)
    assert row["margin"] == pytest.approx(rs_gate.rs_margin(40.0))
    assert row["scenario"]["stop_loss"] == 106.0 and row["direction"] == "bearish"


def test_risk_cap_block_uses_the_stamped_plan_and_margin(repo):
    plan = plan_to_dict(_plan())
    item = _item(plan_v2_rejected_plan=plan, plan_v2_rejected_margin=0.5)
    rr.record_item_block(item, {"AAPL": _frame()}, "plan_rejected", "risk_cap", source="confluence")
    (row,) = repo.records
    assert row["plan"] == plan and row["margin"] == 0.5 and row["cf_status"] == "pending"


def test_an_rs_row_never_carries_a_rejected_plan(repo):
    item = _item(plan_v2_rejected_plan=plan_to_dict(_plan()), plan_v2_rejected_margin=0.5)
    rr.record_item_block(item, {"AAPL": _frame()}, "rs", "rs_blocked", source="confluence")
    assert repo.records[0]["plan"] is None


def test_short_verdicts_map_rs_and_plan_stages_only(repo):
    frames = {"AAPL": _frame()}
    assert rr.record_short_verdict(qualify.Rejected(_item(), "rs", "rs_blocked"), frames)
    assert rr.record_short_verdict(qualify.Rejected(_item(), "plan", "no_qualifying_target"), frames)
    assert not rr.record_short_verdict(qualify.Rejected(_item(), "confirmation", "unmet"), frames)
    assert not rr.record_short_verdict(qualify.Rejected(_item(), "trade_decision", "existing_trade"),
                                       frames)
    assert not rr.record_short_verdict(qualify.Accepted(_item()), frames)
    assert [(r["gate"], r["source"], r["cf_status"]) for r in repo.records] == [
        ("rs", "short_lane", "pending"), ("plan_rejected", "short_lane", "no-plan")]


def test_the_default_repo_is_the_lazy_singleton():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    assert rr._repo() is gate_rejections_repo()
