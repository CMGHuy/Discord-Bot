"""Reply-parity cases for swingbot/commands/stats.py (v153 SP15)."""
import datetime as dt
import os
import tempfile
from types import SimpleNamespace

import discord

from swingbot.commands import stats as stats_mod
from swingbot.core.scanning import engine as scan_engine
from tests.commands.reply_harness import ParityCase

_VERDICT = {"n_closed": 31, "exp_r": 0.25, "badge_exp_r": 0.21, "median_entry_dev": 0.04,
            "clauses": {"n": True, "non_inferior": True, "entry_parity": True}, "pass": True}
_ENTRIES = [
    {"trade_id": "T1", "ticker": "AAA", "outcome": "win", "r_realized": 1.5,
     "auto_lesson": "Clean capture.", "tags": ["trend"]},
    {"trade_id": "T2", "ticker": "BBB", "outcome": "loss", "r_realized": -1.0,
     "auto_lesson": "Entry was wrong.", "tags": ["trend", "gap"]},
]


_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)


def _freeze_clock(monkeypatch):
    """ui.apply_chrome stamps discord.utils.utcnow() on every chromed embed
    (presentation/components.py); the handler runs twice, so freeze it."""
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _chart_path() -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-stats-"), "chart.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG")
    return path


def _plan(plan_id: str):
    return SimpleNamespace(plan_id=plan_id, ticker=plan_id.upper(), source="strategy", strategy="MACD",
                           status="PENDING")


def _stub_plans(plans):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        monkeypatch.setattr(stats_mod.PlanStore, "all", lambda self: list(plans))
        monkeypatch.setattr(stats_mod, "is_regular", lambda plan: True)
        monkeypatch.setattr(stats_mod, "market_today", lambda: dt.date(2026, 10, 9))
        monkeypatch.setattr(stats_mod, "top_plans", lambda plans, n, today=None: list(plans)[:n])
        monkeypatch.setattr(stats_mod, "_fake_item_from_plan", lambda plan: plan)
        monkeypatch.setattr(stats_mod, "build_embed",
                            lambda item, *a, **k: discord.Embed(title=item.plan_id))
        monkeypatch.setattr("swingbot.core.backtesting.registry.get_badge",
                            lambda *a, **k: SimpleNamespace(status="VALIDATED"))
        monkeypatch.setattr("swingbot.core.edge.strategy_soak.soak_verdict", lambda plans, badge: dict(_VERDICT))
    return stub


def _stub_snapshot(snap):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        path = _chart_path()
        monkeypatch.setattr("swingbot.core.analytics.snapshots.load_snapshot", lambda: snap)
        monkeypatch.setattr("swingbot.core.analytics.snapshots.refresh_snapshot", lambda: None)
        monkeypatch.setattr(stats_mod, "stats_embed", lambda s: discord.Embed(title="📐 Analytics"))
        monkeypatch.setattr("swingbot.core.charts.cache.cached_chart", lambda key, render: path)
    return stub


def _stub_trades(trades):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        path = _chart_path()
        monkeypatch.setattr(scan_engine.trade_log, "get_trades", lambda **kw: list(trades))
        monkeypatch.setattr("swingbot.core.analytics.metrics.win_rate", lambda t: 50.0)
        monkeypatch.setattr("swingbot.core.analytics.metrics.expectancy_r", lambda t: 0.2)
        monkeypatch.setattr("swingbot.core.analytics.metrics.profit_factor", lambda t: 1.4)
        monkeypatch.setattr("swingbot.core.analytics.calibration.level_calibration",
                            lambda t: [{"level": 5, "n": len(t), "win_rate": 50.0}])
        monkeypatch.setattr("swingbot.core.analytics.calibration.score_deciles",
                            lambda t: [{"decile": 9, "win_rate": 70.0}])
        monkeypatch.setattr("swingbot.core.analytics.insights.edge_decay_report", lambda t: [])
        monkeypatch.setattr("swingbot.core.analytics.insights.weekly_digest",
                            lambda entries, closed, today: ["**Week** part 1", "part 2"])
        monkeypatch.setattr("swingbot.core.charts.cache.cached_chart", lambda key, render: path)
    return stub


class _Journal:
    def entries(self, **kw):
        return [dict(e) for e in _ENTRIES]

    def set_note(self, trade_id, note):
        return trade_id == "T1"


def _stub_journal(monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.JournalStore", _Journal)
    _stub_trades(_CLOSED)(monkeypatch)


_TODAY = dt.date.today().isoformat()
_CLOSED = [{"status": "win", "closed_at": f"{_TODAY}T15:00:00"},
           {"status": "loss", "closed_at": f"{_TODAY}T16:00:00"}]

CASES = [
    ParityCase("stats_soak_verdict", stats_mod.handle_soak, args=("MACD",), stub=_stub_plans([_plan("p1")])),
    ParityCase("stats_soak_no_plans", stats_mod.handle_soak, args=("MACD",), stub=_stub_plans([])),
    ParityCase("stats_top_panels", stats_mod.handle_top, args=(2,),
               stub=_stub_plans([_plan("p1"), _plan("p2"), _plan("p3")]), expect="multi_send"),
    ParityCase("stats_top_empty", stats_mod.handle_top, stub=_stub_plans([])),
    ParityCase("stats_all_with_chart", stats_mod.handle_stats,
               stub=_stub_snapshot({"built_at": "2026-10-09T08:00:00", "equity_curve": []})),
    ParityCase("stats_all_no_snapshot", stats_mod.handle_stats, stub=_stub_snapshot(None)),
    ParityCase("stats_period_30d", stats_mod.handle_stats, args=("30D",), stub=_stub_trades(_CLOSED)),
    ParityCase("stats_period_empty", stats_mod.handle_stats, args=("7d",), stub=_stub_trades([])),
    ParityCase("stats_period_unknown", stats_mod.handle_stats, args=("fortnight",), stub=_freeze_clock,
               expect="error"),
    ParityCase("stats_lessons_recent", stats_mod.handle_lessons, stub=_stub_journal),
    ParityCase("stats_lessons_week", stats_mod.handle_lessons, args=("week",), stub=_stub_journal,
               expect="multi_send"),
    ParityCase("stats_lessons_not_a_number", stats_mod.handle_lessons, args=("lots",), stub=_freeze_clock,
               expect="error"),
    ParityCase("stats_calibration", stats_mod.handle_calibration, stub=_stub_trades(_CLOSED)),
    ParityCase("stats_calibration_no_trades", stats_mod.handle_calibration, stub=_stub_trades([])),
    ParityCase("stats_journal_note_saved", stats_mod.handle_journal, args=("T1", "watch the gap"),
               stub=_stub_journal),
    ParityCase("stats_journal_ticker_list", stats_mod.handle_journal, args=("aaa",), stub=_stub_journal),
    ParityCase("stats_journal_ticker_unknown", stats_mod.handle_journal, args=("zzz",), stub=_stub_journal),
]
