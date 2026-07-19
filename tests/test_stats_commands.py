import datetime as dt
import types

import discord
import pytest

from swingbot.commands.stats import _fake_item_from_plan, top_plans
from swingbot.core.plan_engine import TradePlanV2
from swingbot.core.scanning import embeds as embeds_mod
from swingbot.core.scanning.embeds import build_embed

TODAY = dt.date(2026, 7, 11)


@pytest.fixture(autouse=True)
def _isolated_scan_snapshots(tmp_path, monkeypatch):
    """build_embed calls _snapshot_and_diff, which reads/writes a shared
    on-disk snapshot cache (data/scan_snapshots.json) -- redirect it to a
    per-test tmp file so this test never pollutes the real data dir (see
    tests/test_embeds_v3.py's identical fixture)."""
    monkeypatch.setattr(embeds_mod, "_SNAPSHOT_PATH", str(tmp_path / "scan_snapshots.json"))


def _plan(ticker, status="PENDING", badge="VALIDATED", quality_score=50):
    return types.SimpleNamespace(
        plan_id=f"id-{ticker}", ticker=ticker, status=status, badge=badge, tier="A",
        quality_score=quality_score, direction="bullish", entry_type="market",
        trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        regime_aligned=True, created_at="2026-07-11",
    )


def test_top_plans_returns_n_ranked_excludes_closed():
    plans = [
        _plan("AAA", quality_score=10),
        _plan("BBB", quality_score=90),
        _plan("CCC", status="CLOSED", quality_score=100),
        _plan("DDD", status="CANCELLED", quality_score=100),
        _plan("EEE", status="ACTIVE", quality_score=60),
    ]
    top = top_plans(plans, n=2, today=TODAY)
    assert [p.ticker for p in top] == ["BBB", "EEE"]


def test_top_plans_n_larger_than_available_returns_all_eligible():
    plans = [_plan("AAA"), _plan("BBB", status="CLOSED")]
    top = top_plans(plans, n=5, today=TODAY)
    assert [p.ticker for p in top] == ["AAA"]


def make_plan_v2(badge="VALIDATED", tier="A", quality_score=72, plan_id="plan-1"):
    return TradePlanV2(
        plan_id=plan_id, ticker="NVDA", created_at="2026-07-19", source="strategy",
        strategy="RSI Pullback", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=120.0,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=quality_score, quality_breakdown=[("regime", 15), ("htf", 8)],
        tier=tier, badge=badge,
        badge_stats={"n": 40, "win_rate": 82.5, "expectancy_r": 0.9, "window": "2020-2023"},
        status="PENDING",
    )


def test_fake_item_from_plan_builds_embed_without_crashing_and_engages_theming():
    plan = make_plan_v2(badge="VALIDATED", tier="A")
    item = _fake_item_from_plan(plan)

    # item.plan is a legacy-shaped stand-in with all the fields
    # _build_trade_plan_table reads -- not the raw TradePlanV2.
    assert item.plan.entry == plan.entry_price
    assert item.plan.stop_loss == plan.stop_loss
    assert item.plan.take_profit == plan.tp1
    assert item.plan.target2_price == plan.tp2
    assert item.plan_v2 is plan

    embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")

    assert isinstance(embed, discord.Embed)
    # Tier/badge chip prefix proves plan_v2 theming actually engaged, not
    # just that build_embed returned without raising.
    assert embed.title.startswith("🅰")
    assert "VALIDATED" in embed.title
    assert "NVDA" in embed.title


def _fixture_snapshot():
    return {
        "built_at": "2026-07-11T20:00:00+00:00",
        "overall": {
            "n": 40, "wins": 28, "losses": 12, "win_rate": 70.0, "expectancy_r": 0.35,
            "profit_factor": 1.8, "sharpe": 0.6, "sortino": 0.9, "max_drawdown_pct": 12.5,
            "total_pnl": 3210.5, "streaks": {"current": 3, "current_kind": "win", "best_win_streak": 5, "worst_loss_streak": 3},
        },
        "by": {
            "tier": [
                {"key": "A", "n": 20, "wins": 16, "losses": 4, "win_rate": 80.0, "expectancy_r": 0.5, "avg_r": 0.5, "profit_factor": 2.2, "total_pnl": 2000.0},
                {"key": "B", "n": 20, "wins": 12, "losses": 8, "win_rate": 60.0, "expectancy_r": 0.2, "avg_r": 0.2, "profit_factor": 1.3, "total_pnl": 1210.5},
            ],
            "strategy": [
                {"key": "EMA Crossover", "n": 15, "wins": 11, "losses": 4, "win_rate": 73.3, "expectancy_r": 0.4, "avg_r": 0.4, "profit_factor": 2.0, "total_pnl": 1500.0},
            ],
        },
    }


def test_stats_embed_has_key_numbers():
    from swingbot.commands.stats import stats_embed
    embed = stats_embed(_fixture_snapshot())
    joined = "\n".join(f.value for f in embed.fields) + embed.description
    assert "Win rate" in joined
    assert "70.0%" in joined
    assert "Expectancy" in joined
    assert "0.35" in joined


def test_stats_embed_none_heavy_snapshot_shows_dashes_not_none():
    from swingbot.commands.stats import stats_embed
    empty = {
        "built_at": "2026-07-11T20:00:00+00:00",
        "overall": {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "expectancy_r": None,
                    "profit_factor": None, "sharpe": None, "sortino": None, "max_drawdown_pct": None,
                    "total_pnl": 0.0, "streaks": {"current": 0, "current_kind": None, "best_win_streak": 0, "worst_loss_streak": 0}},
        "by": {"tier": [], "strategy": []},
    }
    embed = stats_embed(empty)
    joined = "\n".join(f.value for f in embed.fields) + embed.description
    assert "None" not in joined
    assert "—" in joined
