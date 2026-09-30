"""v104 §2.4: an in-scope plan without risk-based sizing is neither stored nor posted."""
from types import SimpleNamespace

import pytest

from swingbot.core.scanning import strategy_pass as sp


class _Store:
    def __init__(self):
        self.plans = []

    def all(self):
        return list(self.plans)

    def add(self, plan):
        self.plans.append(plan)


class _Log:
    def __init__(self):
        self.logged = []

    def open_trade_for_ticker(self, ticker):
        return None

    def log_trade(self, **kwargs):
        self.logged.append(kwargs)


def _plan():
    return SimpleNamespace(plan_id="p1", source="strategy", strategy="Fibonacci", direction="bullish",
                           horizon_key="4w", trigger_price=100.0, stop_loss=94.0, tp1=110.0, tp2=None,
                           badge="WEAK", quality_score=0, cohort_label="COHORT_UNKNOWN", cohort_stats={},
                           risk_features={}, ledger="weak", entry_context={}, ticker="AAPL")


@pytest.fixture
def deps():
    return sp._PassDeps(plan_store=_Store(), trade_log=_Log(), mode="live", live_allow=set(),
                        rs_combined_of=lambda ticker: None, asof_of=None)


def _emit(deps, monkeypatch, sizing_ok):
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda *args, **kwargs: _plan())
    monkeypatch.setattr(sp, "risk_sizing_ok", lambda plan: sizing_ok)
    monkeypatch.setattr(sp, "build_strategy_alert_embed", lambda plan: "embed")
    result = sp.PassResult()
    sp._emit_signal(result, None, ticker="AAPL", strategy="Fibonacci", direction="bullish",
                    horizon="4w", bar_date="2026-09-25", regime=None, deps=deps)
    return result


def test_sizing_failure_blocks_store_trade_and_alert(deps, monkeypatch):
    result = _emit(deps, monkeypatch, sizing_ok=False)
    assert result.sizing_blocked == 1
    assert deps.plan_store.plans == [] and deps.trade_log.logged == [] and result.alerts == []


def test_sizing_ok_opens_the_trade_and_alerts(deps, monkeypatch):
    result = _emit(deps, monkeypatch, sizing_ok=True)
    assert result.opened == 1 and len(result.alerts) == 1 and len(deps.plan_store.plans) == 1


def test_the_simple_mirror_is_an_embed_never_a_str(deps, monkeypatch):
    """v110 §6.1 regression: the 4th tuple element was simple_line(plan), a
    str that _send_alerts sent as embed= -- it failed on every strategy alert,
    logged a warning, and the full alert pinged instead of the mirror."""
    import discord

    result = _emit(deps, monkeypatch, sizing_ok=True)
    simple = result.alerts[0][3]
    assert isinstance(simple, discord.Embed)
    assert simple.push_text.startswith("🆕 NEW SETUP · ▲ LONG AAPL · STRATEGY")


def test_simple_line_is_gone():
    assert not hasattr(sp, "simple_line")
