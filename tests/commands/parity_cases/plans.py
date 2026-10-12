"""Reply-parity cases for swingbot/commands/plans.py (v153 SP12).

PlanStore is replaced by an in-memory store of v2-shaped stand-ins (the
same shape tests/commands/test_plans_board.py uses); starred ids are empty;
the embed clock is frozen because render_board applies chrome.
"""
import datetime as dt
import types

import discord

from swingbot.commands import plans as plans_mod
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)


def _plan(ticker, status, badge="VALIDATED", confidence_level=5, quality_score=80):
    return types.SimpleNamespace(
        plan_id=f"{ticker}-{status}", ticker=ticker, status=status, badge=badge,
        confidence_level=confidence_level, quality_score=quality_score, direction="bullish",
        entry_type="market", trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        entry_price=None, legs_realized=[], working_stop=None, regime_aligned=True,
        created_at="2026-10-09",
    )


_PLANS = [
    _plan("NVDA", "ACTIVE", confidence_level=5),
    _plan("AAPL", "ACTIVE", badge="WEAK", confidence_level=3, quality_score=60),
    _plan("MSFT", "PENDING", confidence_level=4, quality_score=70),
]


class _FakeStore:
    def __init__(self, plans):
        self._plans = list(plans)

    def open_plans(self):
        return list(self._plans)


def _stub(plans=_PLANS):
    def stub(monkeypatch):
        monkeypatch.setattr(plans_mod, "PlanStore", lambda: _FakeStore(plans))
        monkeypatch.setattr(plans_mod, "starred_ids", set)
        monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)
    return stub


CASES = [
    ParityCase("liveplans_all", plans_mod.handle_liveplans, stub=_stub()),
    ParityCase("liveplans_active_level3", plans_mod.handle_liveplans, args=("ACTIVE", "3"), stub=_stub()),
    ParityCase("liveplans_weak_badge", plans_mod.handle_liveplans, kwargs={"badge": "WEAK"}, stub=_stub()),
    ParityCase("liveplans_ticker", plans_mod.handle_liveplans, kwargs={"ticker": "NVDA"}, stub=_stub()),
    ParityCase("liveplans_empty_store", plans_mod.handle_liveplans, stub=_stub([])),
]
