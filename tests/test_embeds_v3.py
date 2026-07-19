"""
Task B2: tier/badge theming applied to build_embed. Covers the real
two-attribute shape (item.plan = legacy scenario, item.plan_v2 = optional
TradePlanV2 -- see embeds.py's _v2_plan helper) rather than the plan
document's stale "item.plan.badge" assumption.
"""
import types

import discord
import pytest

from swingbot import config
from swingbot.core.plan_engine import TradePlanV2
from swingbot.core.scanning import embed_theme as theme
from swingbot.core.scanning.embeds import RequirementCheck, build_embed, confidence_color
from swingbot.core.scanning import embeds as embeds_mod
from swingbot.core.scanning.engine import ScanItem


def make_result(ticker="NVDA", trend="bullish", strategy="RSI Pullback", horizon_label="2 Weeks", horizon_key="2w"):
    return types.SimpleNamespace(
        ticker=ticker, trend=trend, strategy=strategy, horizon_label=horizon_label, horizon_key=horizon_key,
    )


def make_legacy_plan(entry=100.0, stop_loss=95.0, take_profit=110.0, target2_price=115.0):
    return types.SimpleNamespace(
        entry=entry, stop_loss=stop_loss, take_profit=take_profit, target2_price=target2_price,
        target_sources=["EMA", "Fibonacci"], stop_sources=["Structure"],
        risk_reward_ratio=2.0, stop_distance_pct=5.0, target_distance_pct=10.0, target2_distance_pct=15.0,
    )


def make_conf(level=4, label="High", score=80):
    return types.SimpleNamespace(level=level, label=label, score=score)


def make_plan_v2(badge="VALIDATED", tier="B", quality_breakdown=None):
    return TradePlanV2(
        plan_id="plan-1", ticker="NVDA", created_at="2026-07-19", source="strategy",
        strategy="RSI Pullback", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=120.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=72, quality_breakdown=quality_breakdown or [("regime", 15), ("htf", 8)],
        tier=tier, badge=badge,
        badge_stats={"n": 40, "win_rate": 82.5, "expectancy_r": 0.9, "window": "2020-2023"},
        status="PENDING",
    )


def make_item(plan_v2=None, all_ok=True):
    requirements = [
        RequirementCheck(key="min_reward", label="Min reward %", passed=all_ok, detail="10.0% (needs 3.0%+)"),
    ]
    return ScanItem(
        result=make_result(), plan=make_legacy_plan(), conf=make_conf(),
        requirements=requirements,
        combined_from=[{"strategy": "RSI Pullback", "horizon_key": "2w"}],
        plan_v2=plan_v2,
    )


PERF_STATS_EMPTY = {"closed": 0, "wins": 0, "losses": 0, "win_rate": 0.0}


@pytest.fixture(autouse=True)
def _isolated_scan_snapshots(tmp_path, monkeypatch):
    """build_embed calls _snapshot_and_diff, which reads/writes a shared
    on-disk snapshot cache (data/scan_snapshots.json) -- redirect it to a
    per-test tmp file so these tests never read stale state left behind by
    a previous run or another test, and never pollute the real data dir."""
    monkeypatch.setattr(embeds_mod, "_SNAPSHOT_PATH", str(tmp_path / "scan_snapshots.json"))


def _build(item, perf_stats=None):
    return build_embed(
        item, explanation="Test explanation.", perf_stats=perf_stats or PERF_STATS_EMPTY,
        open_positions_warning=None, chart_filename=None, htf_info=None,
    )


def test_weak_plan_v2_gets_amber_color_and_weak_title_chip(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="WEAK", tier="C"))
    embed = _build(item)
    assert embed.color.value == 0xE67E22
    assert embed.title.startswith(f"{theme.tier_chip('C')} ⚠️ WEAK · ")
    assert "NVDA" in embed.title


def test_validated_tier_b_plan_gets_tier_color_and_validated_title_chip(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    embed = _build(item)
    assert embed.color.value == 0xF1C40F
    assert embed.title.startswith(f"{theme.tier_chip('B')} ✅ VALIDATED · ")
    assert "NVDA" in embed.title


def test_no_v2_plan_falls_back_to_confidence_color_and_plain_title(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=None, all_ok=True)
    embed = _build(item)
    assert embed.color.value == confidence_color(item.conf.level).value
    assert not embed.title.startswith(("🅰", "🅱", "🅲"))
    assert "NVDA" in embed.title


def test_quality_and_badge_fields_render_when_plan_v2_has_quality_breakdown(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", tier="A", quality_breakdown=[("regime", 15), ("htf", 8)])
    item = make_item(plan_v2=plan_v2)
    embed = _build(item)
    field_names = [f.name for f in embed.fields]
    assert "✅ VALIDATED" in field_names
    assert any(name.startswith("Quality: 72/100") for name in field_names)
    # Trade plan field still present too -- nothing got dropped in the reorder.
    assert "🎯 Trade plan (v2)" in field_names
