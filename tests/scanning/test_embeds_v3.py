"""
Task B2: tier/badge theming applied to build_embed. Covers the real
two-attribute shape (item.plan = legacy scenario, item.plan_v2 = optional
TradePlanV2 -- see embeds.py's _v2_plan helper) rather than the plan
document's stale "item.plan.badge" assumption.
"""
import datetime as dt
import types

import discord
import pandas as pd
import pytest

from swingbot import config
from swingbot.commands.scanning import _ordered_alerts
from swingbot.core.market.explain import build_explanation
from swingbot.core.planning.plan_engine import TradePlanV2
from swingbot.core.scanning import embed_theme as theme
from swingbot.core.scanning.embeds import (
    RequirementCheck, build_closed_trade_embed, build_embed, build_near_close_embed, confidence_color,
    regenerate_chart_for_trade,
)
from swingbot.core.scanning import embeds as embeds_mod, plan_table, snapshots
from swingbot.core.presentation import ansi
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


def make_plan_v2(badge="VALIDATED", confidence_level=3, quality_breakdown=None,
                  entry_type="market", trigger_price=100.0, direction="bullish",
                  quality_score=72, badge_stats=None, plan_id="plan-1"):
    return TradePlanV2(
        plan_id=plan_id, ticker="NVDA", created_at="2026-07-19", source="strategy",
        strategy="RSI Pullback", horizon_key="2w", direction=direction,
        entry_type=entry_type, trigger_price=trigger_price, entry_price=100.0, expiry_bars=5,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=120.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=quality_score, quality_breakdown=quality_breakdown or [("regime", 15), ("htf", 8)],
        confidence_level=confidence_level, badge=badge,
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
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / "scan_snapshots.json"))


def _build(item, perf_stats=None, layout="detailed"):
    return build_embed(
        item, explanation="Test explanation.", perf_stats=perf_stats or PERF_STATS_EMPTY,
        open_positions_warning=None, chart_filename=None, htf_info=None, layout=layout,
    )


def test_alert_description_leads_with_the_ansi_plan_headline():
    assert _build(make_item()).description.startswith("```ansi\n")


def test_alert_headline_carries_entry_target_stop_in_the_spa_form():
    plain = ansi._ESCAPE_RE.sub("", _build(make_item()).description)
    assert "→" in plain and "/" in plain


def test_the_explanation_survives_below_the_headline():
    assert "Test explanation." in _build(make_item()).description


def test_the_wide_plan_table_is_gone():
    fields = [field.name for field in _build(make_item()).fields]
    assert not any(name.startswith("🎯 Trade plan") for name in fields)


def test_no_description_line_scrolls_on_a_phone():
    inside_block = False
    for line in _build(make_item()).description.splitlines():
        if line.startswith("```"):
            inside_block = not inside_block
            continue
        if inside_block:
            assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH, line


def test_an_unmet_requirement_gets_its_own_field():
    field = next(f for f in _build(make_item(all_ok=False)).fields if f.name == "⚠ Blocked by")
    assert "needs" in field.value


def test_a_blocked_alert_takes_the_inert_accent_not_red():
    from swingbot.core.presentation import tokens
    assert _build(make_item(all_ok=False)).color.value == tokens.ACCENT_BLOCKED


def test_a_clean_alert_has_no_blocked_field():
    assert all(f.name != "⚠ Blocked by" for f in _build(make_item()).fields)


def test_blocked_by_sits_above_the_quality_fields():
    names = [f.name for f in _build(make_item(all_ok=False)).fields]
    assert names.index("⚠ Blocked by") < names.index("Confidence")


def test_weak_plan_v2_uses_its_confidence_level_colour(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="WEAK", confidence_level=1))
    embed = _build(item)
    assert embed.color.value == 0x9ACD32
    assert "WEAK" not in embed.title
    assert "NVDA" in embed.title


def test_validated_plan_uses_the_confidence_level_colour_without_badge(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
    embed = _build(item)
    assert embed.color.value == 0x9ACD32
    assert "VALIDATED" not in embed.title
    assert "NVDA" in embed.title


def test_no_v2_plan_falls_back_to_confidence_color_and_plain_title(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=None, all_ok=True)
    embed = _build(item)
    assert embed.color.value == confidence_color(item.conf.level).value
    assert not embed.title.startswith(("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"))
    assert "NVDA" in embed.title


def test_confidence_and_follow_fields_render_when_plan_v2_has_quality_breakdown(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", confidence_level=5, quality_breakdown=[("regime", 15), ("htf", 8)])
    item = make_item(plan_v2=plan_v2)
    embed = _build(item)
    field_names = [f.name for f in embed.fields]
    assert "Confidence" in field_names
    assert "Follow" in field_names
    # The plan now leads the description, rather than consuming a wide field.
    assert embed.description.startswith("```ansi\n")


# ── Task B3: compact/detailed layouts ────────────────────────────────────

def test_detailed_layout_still_has_confirmed_by_and_if_it_gets_there(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
    embed = _build(item, layout="detailed")
    field_names = [f.name for f in embed.fields]
    assert "Confirmed by" in field_names
    assert "🔀 If it gets there" in field_names


def test_compact_layout_has_at_most_six_fields(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
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
    seed_item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
    _build(seed_item, layout="detailed")

    changed_plan = make_legacy_plan(entry=101.0)
    item = ScanItem(
        result=make_result(), plan=changed_plan, conf=make_conf(),
        requirements=[RequirementCheck(key="min_reward", label="Min reward %", passed=True, detail="10.0% (needs 3.0%+)")],
        combined_from=[{"strategy": "RSI Pullback", "horizon_key": "2w"}],
        plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3),
    )
    embed = _build(item, layout="compact")
    field_names = [f.name for f in embed.fields]
    assert "Confirmed by" not in field_names
    assert "🔄 What changed since last scan" not in field_names
    assert "🔀 If it gets there" not in field_names
    assert "⚠️ Position limit" not in field_names


def test_compact_layout_includes_confidence_and_follow_fields(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
    embed = _build(item, layout="compact")
    field_names = [f.name for f in embed.fields]
    assert "Confidence" in field_names and "Follow" in field_names


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
    low = make_plan_v2(badge="WEAK", confidence_level=1)
    low.quality_score = 50
    low.regime_aligned = False

    # mid: VALIDATED (40) + quality 50 (20) + no regime (0) + fresh (10) = 60
    mid = make_plan_v2(badge="VALIDATED", confidence_level=3)
    mid.quality_score = 50
    mid.regime_aligned = False

    # high: VALIDATED (40) + quality 75 (30) + regime aligned (10) + fresh (10) = 90
    high = make_plan_v2(badge="VALIDATED", confidence_level=5)
    high.quality_score = 75
    high.regime_aligned = True

    alerts = [_alert("low", low), _alert("high", high), _alert("mid", mid)]
    ordered = _ordered_alerts(alerts, today=_TODAY)

    assert [a[2] for a in ordered] == [high, mid, low]
    assert [a[0].title for a in ordered] == ["high", "mid", "low"]


# --- Task B7: WEAK block goes compact --------------------------------------

def test_weak_plan_badge_is_not_rendered(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="WEAK", confidence_level=1,
                            badge_stats={"n": 42, "win_rate": 63.4, "expectancy_r": 0.1, "window": "2020-2023"})
    item = make_item(plan_v2=plan_v2)
    embed = _build(item, layout="detailed")
    blob = embed.title + embed.description + "".join(f.name + f.value for f in embed.fields)
    assert "WEAK" not in blob


def test_validated_plan_has_no_badge_field_anywhere(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="VALIDATED", confidence_level=3))
    embed = _build(item, layout="detailed")
    blob = embed.title + embed.description + "".join(f.name + f.value for f in embed.fields)
    assert "VALIDATED" not in blob and "WEAK" not in blob


def test_weak_plan_keeps_confidence_and_follow_without_a_badge(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    item = make_item(plan_v2=make_plan_v2(badge="WEAK", confidence_level=1))
    embed = _build(item, layout="detailed")
    field_names = [f.name for f in embed.fields]
    assert "Confidence" in field_names and "Follow" in field_names


def test_ordered_alerts_keeps_legacy_alerts_after_plan_alerts_in_original_order():
    high = make_plan_v2(badge="VALIDATED", confidence_level=5)
    high.quality_score = 75
    high.regime_aligned = True

    low = make_plan_v2(badge="WEAK", confidence_level=1)
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

def test_follow_score_field_is_the_kit_meter_with_components(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", confidence_level=5, quality_score=82)
    plan_v2.regime_aligned = True
    plan_v2.created_at = dt.date.today().isoformat()  # fresh as of "today"
    item = make_item(plan_v2=plan_v2)
    embed = _build(item)
    follow_fields = [f for f in embed.fields if f.name == "Follow"]
    assert len(follow_fields) == 1
    value = follow_fields[0].value
    assert "▰" in value
    assert "validated" in value.lower()
    assert "quality" in value.lower()


def test_follow_score_field_is_present_in_compact_layout_too(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    plan_v2 = make_plan_v2(badge="VALIDATED", confidence_level=5, quality_score=82)
    plan_v2.regime_aligned = True
    plan_v2.created_at = dt.date.today().isoformat()
    item = make_item(plan_v2=plan_v2)
    embed = _build(item, layout="compact")
    follow_fields = [f for f in embed.fields if f.name == "Follow"]
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


def test_monthly_opex_renders_a_headline_field(monkeypatch):
    # v44: flagged on every alert that day, exactly like heat_blocked above.
    # The tightened gates already decided what posts; this tells the reader
    # what kind of day the survivors were found on.
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)
    embed = _build(make_item())
    opex_fields = [f for f in embed.fields if "OPEX" in f.name]
    assert len(opex_fields) == 1
    assert "expiration" in opex_fields[0].value.lower()


def test_weekly_opex_renders_a_distinct_headline_field(monkeypatch):
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.WEEKLY)
    embed = _build(make_item())
    assert [f for f in embed.fields if "eekly opex" in f.name]


def test_no_opex_field_off_an_expiration_day(monkeypatch):
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: None)
    embed = _build(make_item())
    assert not [f for f in embed.fields if "opex" in f.name.lower()]


def test_no_opex_field_when_the_flag_is_off(monkeypatch):
    # The whole feature is inert by default: even on a real third Friday the
    # embed must be byte-identical to today's.
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    embed = _build(make_item())
    assert not [f for f in embed.fields if "opex" in f.name.lower()]


def test_cluster_blocked_item_renders_headline_field_with_size_zero():
    # Edge plan E8: correlated-cluster cap is flagged on the embed, never
    # hidden -- engine.py sets item.cluster_blocked right before build_embed.
    item = make_item()
    item.cluster_blocked = {"allowed": False, "cluster": ["AAPL", "MSFT"],
                            "correlated_heat": 4.0, "max_corr": 0.91, "remaining": 0.0, "cap": 3.0}
    embed = _build(item)
    cluster_fields = [f for f in embed.fields if "correlated cluster" in f.name.lower()]
    assert len(cluster_fields) == 1
    assert "AAPL, MSFT" in cluster_fields[0].value
    assert "4.0%" in cluster_fields[0].value and "3.0%" in cluster_fields[0].value
    assert "0 shares" in cluster_fields[0].value


def test_no_cluster_blocked_attr_adds_no_field():
    item = make_item()
    embed = _build(item)
    assert not [f for f in embed.fields if "correlated cluster" in f.name.lower()]


def test_kill_switch_blocked_item_stays_visible_with_zero_suggested_size():
    item = make_item()
    item.kill_switch_blocked = {"on": True, "reason": "drawdown >20%", "at": "2026-07-26T00:00:00+00:00"}
    embed = _build(item)
    headline_fields = [f for f in embed.fields if "ENTRIES PAUSED" in f.name]
    assert len(headline_fields) == 1
    assert "drawdown >20%" in headline_fields[0].name
    assert "0 shares" in headline_fields[0].value


def _intraday_field(embed):
    fields = [f for f in embed.fields if "intraday" in f.name.lower()]
    assert len(fields) <= 1
    return fields[0] if fields else None


def test_intraday_annotation_renders_confirm_and_against():
    # Edge plan E29: a live-only annotation -- it never blocks or resizes
    # anything, it just tells the operator whether the 1h tape agrees.
    item = make_item()
    item.intraday = True
    assert "confirms" in _intraday_field(_build(item)).value

    item = make_item()
    item.intraday = False
    assert "against" in _intraday_field(_build(item)).value


def test_no_intraday_reading_adds_no_field():
    # None = no data = neutral: nothing to say, so say nothing.
    item = make_item()
    item.intraday = None
    assert _intraday_field(_build(item)) is None
    assert _intraday_field(_build(make_item())) is None


# =====================================================================
# Final-review Finding 1 -- regenerate_chart_for_trade() must hand its
# trade's stored trendline fit to generate_trade_chart(), the same way
# scanning/engine.py does on the alert path (see
# tests/test_trade_chart_stored_fit.py::test_the_scan_hands_its_stored_fit_to_the_png).
# Without this, re-viewing an older trade in Discord refits a fresh line
# against today's data while the SPA (market.py) keeps drawing the one
# stored fit -- the two disagree about the same trade's line.
# =====================================================================

def _regen_frame(n=30):
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0,
                         "Close": 100.0, "Volume": 1_000.0}, index=idx)


def _make_trade(**overrides):
    trade = {
        "id": "t1", "ticker": "AAPL", "horizon_key": "4w",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "direction": "bullish", "strategy": "RSI", "status": "open",
        "opened_at": "2026-01-01T00:00:00+00:00",
    }
    trade.update(overrides)
    return trade


def _stub_regenerate_deps(monkeypatch, df):
    """get_daily_data and currency lookup, stubbed so the test never touches
    the network -- captures generate_trade_chart's kwargs instead of
    actually rendering a PNG."""
    from swingbot.core.scanning import lifecycle_embeds as embeds_mod

    monkeypatch.setattr(embeds_mod, "get_daily_data", lambda ticker: df)
    monkeypatch.setattr(embeds_mod, "get_currency_symbol", lambda ticker, default: default)
    captured = {}

    def _fake_generate(*args, **kwargs):
        captured.update(kwargs)
        return "/tmp/fake_view.png"

    monkeypatch.setattr(embeds_mod, "generate_trade_chart", _fake_generate)
    return captured


def test_regenerate_chart_passes_the_stored_trendline_fit(monkeypatch):
    stored_fit = {
        "slope": 0.1, "intercept": 99.0, "side": "support", "strength": 3,
        "points": [{"t": 1704067200, "price": 99.0}, {"t": 1705276800, "price": 100.0}],
    }
    captured = _stub_regenerate_deps(monkeypatch, _regen_frame())
    trade = _make_trade(trendline_fit=stored_fit)

    path = regenerate_chart_for_trade(trade)

    assert path == "/tmp/fake_view.png"
    assert captured.get("trendline_fit") is stored_fit


def test_regenerate_chart_passes_none_without_a_stored_fit(monkeypatch):
    # A trade logged before this feature (or never trendline-confirmed) has
    # no trendline_fit key at all -- the kwarg must still be PASSED as None,
    # not omitted, so generate_trade_chart falls back to its own live fit
    # exactly as it always has (see trade_chart.py's need_target_trendline /
    # need_stop_trendline fallback).
    captured = _stub_regenerate_deps(monkeypatch, _regen_frame())
    trade = _make_trade()

    regenerate_chart_for_trade(trade)

    assert "trendline_fit" in captured
    assert captured["trendline_fit"] is None
