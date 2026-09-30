"""v111 §3: per-symbol, per-scan DEBUG lines for dedup merges and gate rejects."""
import logging
from types import SimpleNamespace

from swingbot import config
from swingbot.core.scanning import analyze, dedup, engine
from swingbot.core.scanning.analyze import ScanItem, paper_trade_decision
from swingbot.core.scanning.embeds import RequirementCheck
from tests.helpers import make_ohlcv
from tests.scanning.test_engine_v2_plans import _item, _scenario


def _messages(caplog, logger):
    return [r.getMessage() for r in caplog.records if r.name == logger.name]


def _dedup_item(strategy, score):
    return SimpleNamespace(
        result=SimpleNamespace(ticker="AAPL", trend="bullish", strategy=strategy, horizon_key="4w"),
        plan=SimpleNamespace(entry=100.0, take_profit=110.0, stop_loss=95.0),
        conf=SimpleNamespace(score=score, level=3))


def test_dedup_merge_is_logged_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        out = dedup.dedup_scan_items([_dedup_item("EMA", 60), _dedup_item("Fibonacci", 70)])
    assert len(out) == 1
    assert _messages(caplog, dedup.log) == [
        "dedup: AAPL bullish merged 2 scenario(s) into Fibonacci/4w"]
    assert all(r.levelno == logging.DEBUG for r in caplog.records if r.name == dedup.log.name)


def test_a_lone_scenario_logs_nothing(caplog):
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        dedup.dedup_scan_items([_dedup_item("EMA", 60)])
    assert _messages(caplog, dedup.log) == []


def test_sector_collapse_is_logged_at_debug(caplog):
    items = [SimpleNamespace(sector="XLK", follow_score=80, ticker="AAPL"),
             SimpleNamespace(sector="XLK", follow_score=60, ticker="MSFT")]
    with caplog.at_level(logging.DEBUG, logger=dedup.log.name):
        dedup.dedup_sector_items(items)
    assert _messages(caplog, dedup.log) == ["dedup: sector XLK kept AAPL over MSFT"]


def test_an_unmet_gate_is_logged_with_its_reason(caplog):
    item = ScanItem(result=SimpleNamespace(ticker="AAPL", horizon_key="4w"), plan=None, conf=None,
                    requirements=[RequirementCheck(key="k0", label="Gate 0", passed=False, detail="too far")])
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        assert paper_trade_decision(item, False) == (False, "unmet: Gate 0: too far")
    assert "gate: AAPL (4w) not logged -- unmet: Gate 0: too far" in _messages(caplog, analyze.log)


def test_an_allowed_item_logs_nothing(caplog):
    item = ScanItem(result=None, plan=None, conf=None, requirements=[])
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        assert paper_trade_decision(item, False) == (True, None)
    assert not any(m.startswith("gate:") for m in _messages(caplog, analyze.log))


def test_a_plan_rejection_is_logged_with_its_reason(monkeypatch, caplog):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *a, **k: None)
    item = _item()
    with caplog.at_level(logging.DEBUG, logger=analyze.log.name):
        engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60), "AAPL", "4w", level_map=None)
    assert item.plan_v2_rejected == "no_qualifying_target"
    assert "gate: AAPL (4w) plan rejected -- no_qualifying_target" in _messages(caplog, analyze.log)
