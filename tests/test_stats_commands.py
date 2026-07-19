import datetime as dt
import types

import discord
import pytest

from swingbot.commands.stats import _fake_item_from_plan, stats_embed, top_plans
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
    embed = stats_embed(_fixture_snapshot())
    joined = "\n".join(f.value for f in embed.fields) + embed.description
    assert "Win rate" in joined
    assert "70.0%" in joined
    assert "Expectancy" in joined
    assert "0.35" in joined


def test_stats_embed_none_heavy_snapshot_shows_dashes_not_none():
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


import datetime as dt

from swingbot.commands.stats import _since

TODAY = dt.date(2026, 7, 11)


def test_since_7d_30d_90d():
    assert _since("7d", TODAY) == TODAY - dt.timedelta(days=7)
    assert _since("30d", TODAY) == TODAY - dt.timedelta(days=30)
    assert _since("90d", TODAY) == TODAY - dt.timedelta(days=90)


def test_since_ytd_is_jan_1():
    assert _since("ytd", TODAY) == dt.date(2026, 1, 1)


def test_since_all_is_none():
    assert _since("all", TODAY) is None


def test_since_unknown_period_defaults_to_none():
    assert _since("bogus", TODAY) is None


from swingbot.commands.stats import lessons_lines


def _entry(ticker, outcome, r, lesson, tags=None):
    return {"ticker": ticker, "outcome": outcome, "r_realized": r, "auto_lesson": lesson, "tags": tags or []}


def test_lessons_lines_renders_each_entry():
    entries = [
        _entry("AAA", "win", 1.5, "Clean capture: banked 90% of the available move."),
        _entry("BBB", "loss", -1.0, "Entry was wrong from the first bar — review the trigger, not the exit."),
        _entry("CCC", "scratch", 0.0, "No follow-through within the horizon — count it as rent, not error."),
    ]
    lines = lessons_lines(entries)
    assert len(lines) == 3
    assert "AAA" in lines[0] and "+1.50R" in lines[0] and "Clean capture" in lines[0]
    assert "✅" in lines[0]
    assert "❌" in lines[1]
    assert "⬜" in lines[2] or "➖" in lines[2]


from swingbot.commands.stats import calibration_lines


def test_calibration_lines_marks_failing_tier_and_drift_alert():
    tiers = [
        {"tier": "A", "n": 40, "win_rate": 60.0, "expectancy_r": 0.1, "expected_band": ">=80", "ok": False},
        {"tier": "B", "n": 5, "win_rate": None, "expectancy_r": None, "expected_band": "70-80", "ok": None},
    ]
    decay_lines = ["📉 Fibonacci: OOS WR 81.6% -> live WR 64.0% (N=25) — drift alert"]
    lines = calibration_lines(tiers, decay_lines)
    assert any("❌" in l and "A" in l for l in lines)
    assert any("—" in l and "B" in l for l in lines)
    assert any("Fibonacci" in l for l in lines)


from swingbot.commands.stats import _journal_note_result


def test_journal_note_result_success(tmp_path, monkeypatch):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore(path=str(tmp_path / "journal.json"))
    store.add({"trade_id": "T1", "ticker": "NVDA", "outcome": "win", "r_realized": 1.0,
              "auto_lesson": "lesson", "tags": []})
    msg = _journal_note_result(store, "T1", "watch the gap next time")
    assert "saved" in msg.lower() or "note" in msg.lower()
    assert store.get("T1")["note"] == "watch the gap next time"


def test_journal_note_result_missing_id(tmp_path):
    from swingbot.core.analytics.journal import JournalStore
    store = JournalStore(path=str(tmp_path / "journal.json"))
    msg = _journal_note_result(store, "missing", "x")
    assert "no journal entry" in msg.lower()


def test_help_catalog_covers_analytics_and_plans():
    from swingbot.bot_core import COMMANDS_BY_CATEGORY, COMMAND_USAGE

    all_listed = {cmd.split()[0].lstrip("!") for cmds in COMMANDS_BY_CATEGORY.values() for cmd, _ in cmds}
    for name in ("top", "stats", "lessons", "calibration", "journal", "plans", "liveplans"):
        assert name in all_listed, f"{name} missing from COMMANDS_BY_CATEGORY"
        assert name in COMMAND_USAGE, f"{name} missing from COMMAND_USAGE"
