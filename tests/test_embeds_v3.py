"""
Task B2: tier/badge theming applied to build_embed. Covers the real
two-attribute shape (item.plan = legacy scenario, item.plan_v2 = optional
TradePlanV2 -- see embeds.py's _v2_plan helper) rather than the plan
document's stale "item.plan.badge" assumption.
"""
import datetime as dt
import types

import discord
import pytest

from swingbot import config
from swingbot.commands.scanning import _ordered_alerts
from swingbot.core.explain import build_explanation
from swingbot.core.plan_engine import TradePlanV2
from swingbot.core.scanning import embed_theme as theme
from swingbot.core.scanning.embeds import (
    RequirementCheck, build_closed_trade_embed, build_embed, build_near_close_embed, confidence_color,
)
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


def make_plan_v2(badge="VALIDATED", tier="B", quality_breakdown=None,
                  entry_type="market", trigger_price=100.0, direction="bullish",
                  quality_score=72, badge_stats=None, plan_id="plan-1"):
    return TradePlanV2(
        plan_id=plan_id, ticker="NVDA", created_at="2026-07-19", source="strategy",
        strategy="RSI Pullback", horizon_key="2w", direction=direction,
        entry_type=entry_type, trigger_price=trigger_price, entry_price=100.0, expiry_bars=5,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=120.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=quality_score, quality_breakdown=quality_breakdown or [("regime", 15), ("htf", 8)],
        tier=tier, badge=badge,
        badge_stats=badge_stats or {"n": 40, "win_rate": 82.5, "expectancy_r": 0.9, "window": "2020-2023"},
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


def _build(item, perf_stats=None, layout="detailed"):
    return build_embed(
        item, explanation="Test explanation.", perf_stats=perf_stats or PERF_STATS_EMPTY,
        open_positions_warning=None, chart_filename=None, htf_info=None, layout=layout,
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


# ── Task B3: compact/detailed layouts ────────────────────────────────────

def test_detailed_layout_still_has_confirmed_by_and_if_it_gets_there(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    embed = _build(item, layout="detailed")
    field_names = [f.name for f in embed.fields]
    assert "Confirmed by" in field_names
    assert "🔀 If it gets there" in field_names


def test_compact_layout_has_at_most_six_fields(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    embed = _build(item, layout="compact")
    # Was <=5 pre-Task-B6; the always-on "🧭 Follow score" field added by
    # this task raises the compact-mode ceiling by exactly one field.
    assert len(embed.fields) <= 6


def test_compact_layout_drops_confirmed_by_and_what_changed_and_branches(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    # First build (any layout) seeds the on-disk snapshot so the second
    # build has something to diff against -- otherwise "what changed" is
    # always None on a first sighting regardless of layout, and the "it
    # got dropped for compact" assertion would be vacuously true.
    seed_item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    _build(seed_item, layout="detailed")

    changed_plan = make_legacy_plan(entry=101.0)
    item = ScanItem(
        result=make_result(), plan=changed_plan, conf=make_conf(),
        requirements=[RequirementCheck(key="min_reward", label="Min reward %", passed=True, detail="10.0% (needs 3.0%+)")],
        combined_from=[{"strategy": "RSI Pullback", "horizon_key": "2w"}],
        plan_v2=make_plan_v2(badge="VALIDATED", tier="B"),
    )
    embed = _build(item, layout="compact")
    field_names = [f.name for f in embed.fields]
    assert "Confirmed by" not in field_names
    assert "🔄 What changed since last scan" not in field_names
    assert "🔀 If it gets there" not in field_names
    assert "⚠️ Position limit" not in field_names


def test_compact_layout_includes_one_line_quality_summary(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    embed = _build(item, layout="compact")
    quality_fields = [f for f in embed.fields if f.name == "📐 Quality"]
    assert len(quality_fields) == 1
    assert quality_fields[0].value.startswith("Tier B · 72/100 · ✅ VALIDATED")
    assert "OOS N=40 WR 82.5%" in quality_fields[0].value
    # B2's two separate pedigree fields are replaced, not duplicated, in compact mode.
    field_names = [f.name for f in embed.fields]
    assert "✅ VALIDATED" not in field_names
    assert not any(name.startswith("Quality: 72/100") for name in field_names)


# --- Task B4: trigger-aware explanation wording ---------------------------

def _fake_scenario_result(direction="bullish", ticker="NVDA", horizon_label="2 Weeks", strategy="RSI Pullback"):
    scenario = types.SimpleNamespace(
        direction=direction, target_sources=["EMA", "Fibonacci"], stop_sources=["Structure"],
        take_profit=110.0, target_distance_pct=10.0,
        stop_loss=95.0, stop_distance_pct=5.0,
        target2_price=115.0, target2_distance_pct=15.0,
    )
    return types.SimpleNamespace(
        scenario=scenario, ticker=ticker, horizon_label=horizon_label, strategy=strategy,
    )


def test_build_explanation_stop_entry_bullish_shows_buy_stop_wording():
    result = _fake_scenario_result(direction="bullish")
    plan = make_plan_v2(entry_type="stop_entry", trigger_price=112.5, direction="bullish")
    text = build_explanation(result, plan=plan)
    assert "BUY STOP above" in text
    assert "112.5" in text or "112.50" in text


def test_build_explanation_stop_entry_bearish_shows_sell_stop_wording():
    result = _fake_scenario_result(direction="bearish")
    plan = make_plan_v2(entry_type="stop_entry", trigger_price=87.5, direction="bearish")
    text = build_explanation(result, plan=plan)
    assert "SELL STOP below" in text


def test_build_explanation_market_entry_shows_enters_at_market():
    result = _fake_scenario_result(direction="bullish")
    plan = make_plan_v2(entry_type="market", direction="bullish")
    text = build_explanation(result, plan=plan)
    assert "Enters at market" in text


def test_build_explanation_no_plan_omits_trigger_wording():
    result = _fake_scenario_result(direction="bullish")
    text = build_explanation(result, plan=None)
    assert "BUY STOP" not in text
    assert "Enters at market" not in text


# --- Task B5: alerts ordered by follow_score -------------------------------

_TODAY = dt.date(2026, 7, 19)  # matches make_plan_v2's default created_at, i.e. "fresh"


def _alert(embed_title, plan_v2):
    return (discord.Embed(title=embed_title), None, plan_v2)


def test_ordered_alerts_ranks_plan_carrying_alerts_by_follow_score():
    # low: WEAK badge (0) + quality 50 (20) + no regime (0) + fresh (10) = 30
    low = make_plan_v2(badge="WEAK", tier="C")
    low.quality_score = 50
    low.regime_aligned = False

    # mid: VALIDATED (40) + quality 50 (20) + no regime (0) + fresh (10) = 60
    mid = make_plan_v2(badge="VALIDATED", tier="B")
    mid.quality_score = 50
    mid.regime_aligned = False

    # high: VALIDATED (40) + quality 75 (30) + regime aligned (10) + fresh (10) = 90
    high = make_plan_v2(badge="VALIDATED", tier="A")
    high.quality_score = 75
    high.regime_aligned = True

    alerts = [_alert("low", low), _alert("high", high), _alert("mid", mid)]
    ordered = _ordered_alerts(alerts, today=_TODAY)

    assert [a[2] for a in ordered] == [high, mid, low]
    assert [a[0].title for a in ordered] == ["high", "mid", "low"]


# --- Task B7: WEAK block goes compact --------------------------------------

def test_weak_plan_gets_single_line_caution_as_first_field(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="WEAK", tier="C",
                            badge_stats={"n": 42, "win_rate": 63.4, "expectancy_r": 0.1, "window": "2020-2023"})
    item = make_item(plan_v2=plan_v2)
    embed = _build(item, layout="detailed")
    first_field = embed.fields[0]
    assert first_field.name.startswith("⚠️ WEAK")
    assert "N=42" in first_field.value
    assert "63.4%" in first_field.value
    assert first_field.value.strip() == first_field.value
    assert "\n" not in first_field.value


def test_validated_plan_has_no_weak_field_anywhere(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", tier="B"))
    embed = _build(item, layout="detailed")
    assert not any(f.name.startswith("⚠️ WEAK") for f in embed.fields)


def test_weak_plan_detailed_mode_has_exactly_one_weak_field(monkeypatch):
    # Guards against the duplicate-field bug: naively adding the new headline
    # caution on top of the existing badge_field_for(plan_v2) append would
    # leave two separately-named/valued "⚠️ WEAK"-ish fields in detailed mode.
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="WEAK", tier="C"))
    embed = _build(item, layout="detailed")
    weak_fields = [f for f in embed.fields if f.name.startswith("⚠️ WEAK")]
    assert len(weak_fields) == 1
    # And quality_lines(plan_v2) must still fire for WEAK plans -- it's
    # independent of badge, only gated on quality_breakdown.
    field_names = [f.name for f in embed.fields]
    assert any(name.startswith("Quality: 72/100") for name in field_names)


def test_ordered_alerts_keeps_legacy_alerts_after_plan_alerts_in_original_order():
    high = make_plan_v2(badge="VALIDATED", tier="A")
    high.quality_score = 75
    high.regime_aligned = True

    low = make_plan_v2(badge="WEAK", tier="C")
    low.quality_score = 50
    low.regime_aligned = False

    legacy_first = _alert("legacy-first", None)
    legacy_second = _alert("legacy-second", None)

    # Legacy alerts interleaved with plan alerts in the input -- they must
    # all land after every plan-carrying alert, preserving their own
    # original relative order (legacy-first before legacy-second).
    alerts = [legacy_first, _alert("low", low), legacy_second, _alert("high", high)]
    ordered = _ordered_alerts(alerts, today=_TODAY)

    assert [a[0].title for a in ordered] == ["high", "low", "legacy-first", "legacy-second"]


# --- Task B6: "why follow this" follow-score breakdown field ---------------

def test_follow_score_field_present_with_chip_and_components(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", tier="A", quality_score=82)
    plan_v2.regime_aligned = True
    plan_v2.created_at = dt.date.today().isoformat()  # fresh as of "today"
    item = make_item(plan_v2=plan_v2)
    embed = _build(item)
    follow_fields = [f for f in embed.fields if f.name == "🧭 Follow score"]
    assert len(follow_fields) == 1
    value = follow_fields[0].value
    assert "▰" in value
    assert "validated" in value.lower()
    assert "quality" in value.lower()


def test_follow_score_field_present_in_compact_layout_too(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", tier="A", quality_score=82)
    plan_v2.regime_aligned = True
    plan_v2.created_at = dt.date.today().isoformat()
    item = make_item(plan_v2=plan_v2)
    embed = _build(item, layout="compact")
    follow_fields = [f for f in embed.fields if f.name == "🧭 Follow score"]
    assert len(follow_fields) == 1
    assert "▰" in follow_fields[0].value


def test_follow_score_field_absent_without_plan_v2(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=None)
    embed = _build(item)
    assert not any(f.name == "🧭 Follow score" for f in embed.fields)


# --- Task B8: unified footer/timestamp across the three embed builders -----

def _make_closed_trade(**overrides):
    trade = {
        "id": "trade-42", "ticker": "NVDA", "status": "win",
        "entry": 100.0, "exit_price": 110.0, "stop_loss": 95.0, "take_profit": 110.0,
        "direction": "bullish", "strategy": "RSI Pullback", "horizon_key": "2w",
        "confidence_label": "High", "confidence_level": 4,
    }
    trade.update(overrides)
    return trade


def _make_near_close_warning(**trade_overrides):
    trade = {
        "id": "trade-99", "ticker": "NVDA", "strategy": "RSI Pullback", "horizon_key": "2w",
        "direction": "bullish", "confidence_label": "High", "confidence_level": 4,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
    }
    trade.update(trade_overrides)
    return {
        "trade": trade, "current_price": 96.0, "near_which": "stop-loss",
        "sl_dist_pct": 1.0, "tp_dist_pct": 14.6,
    }


def test_all_three_embeds_share_timestamp_and_disclaimer_and_preserve_ids(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")

    scan_item = make_item(plan_v2=make_plan_v2(plan_id="12345678-abcd-efgh"))
    scan_embed = _build(scan_item)

    closed_trade = _make_closed_trade()  # no plan_id key -- legacy trade
    closed_embed = build_closed_trade_embed(closed_trade)

    warning = _make_near_close_warning()
    near_close_embed = build_near_close_embed(warning)

    # All three get a non-None timestamp stamped by apply_footer.
    assert scan_embed.timestamp is not None
    assert closed_embed.timestamp is not None
    assert near_close_embed.timestamp is not None

    # All three share the identical disclaimer prefix once the plan-id
    # suffix is stripped off.
    prefixes = {
        scan_embed.footer.text.split(" · plan ")[0],
        closed_embed.footer.text.split(" · plan ")[0],
        near_close_embed.footer.text.split(" · plan ")[0],
    }
    assert len(prefixes) == 1

    # Scan embed's footer carries the 8-char-truncated plan id.
    assert "plan 12345678" in scan_embed.footer.text

    # Closed-trade embed has no plan_id -- no " · plan " suffix at all.
    assert " · plan " not in closed_embed.footer.text

    # Trade ID information (previously footer-only) is preserved as a field
    # on the closed-trade embed, since it appears nowhere else in the body.
    trade_id_fields = [f for f in closed_embed.fields if f.name == "Trade ID"]
    assert len(trade_id_fields) == 1
    assert "trade-42" in trade_id_fields[0].value
    assert "Plan Engine v2" not in trade_id_fields[0].value  # no plan_id/legs on this trade

    # Near-close embed keeps its usage-hint Trade ID field too.
    near_id_fields = [f for f in near_close_embed.fields if f.name == "Trade ID"]
    assert len(near_id_fields) == 1
    assert "trade-99" in near_id_fields[0].value
    assert "!trade trade-99" in near_id_fields[0].value


def test_closed_trade_embed_trade_id_field_shows_plan_engine_v2_suffix_when_v2():
    trade = _make_closed_trade(plan_id="plan-abc")
    embed = build_closed_trade_embed(trade)
    trade_id_field = next(f for f in embed.fields if f.name == "Trade ID")
    assert "trade-42" in trade_id_field.value
    assert "Plan Engine v2" in trade_id_field.value
    assert "plan plan-abc" in embed.footer.text


def test_heat_blocked_item_renders_headline_field_with_size_zero():
    # Edge plan E7: portfolio heat cap is flagged on the embed, never
    # hidden -- engine.py sets item.heat_blocked right before build_embed.
    item = make_item()
    item.heat_blocked = {"allowed": False, "open_heat": 6.4, "remaining": 0.0, "cap": 6.0}
    embed = _build(item)
    heat_fields = [f for f in embed.fields if "heat cap" in f.name.lower()]
    assert len(heat_fields) == 1
    assert "6.4%" in heat_fields[0].value and "6.0%" in heat_fields[0].value
    assert "0 shares" in heat_fields[0].value


def test_no_heat_blocked_attr_adds_no_field():
    item = make_item()
    embed = _build(item)
    assert not [f for f in embed.fields if "heat cap" in f.name.lower()]
