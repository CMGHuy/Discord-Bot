"""v187 D2: invalid account settings are refused with the validator's message
and nothing is saved; the legacy clamp is visible in !account."""
import asyncio

import pytest

from swingbot.commands import account as account_mod
from swingbot.core.planning import account as acct


class _Reply:
    def __init__(self):
        self.sent, self.errors = [], []

    async def send(self, content=None, **kw):
        self.sent.append(content)

    async def send_error(self, text, **kw):
        self.errors.append(text)


@pytest.fixture
def saved(monkeypatch):
    out = []
    monkeypatch.setattr(acct, "load_account_config",
                        lambda: {"base_balance": 10_000.0, "balance": 10_000.0, "risk_pct": 1.0,
                                 "sizing_mode": "risk_pct", "balance_history": []})
    monkeypatch.setattr(acct, "save_account_config", lambda cfg: out.append(dict(cfg)))
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return out


CASES = [
    (account_mod.handle_account_balance, -100.0, "Balance must be above 0 (got -100.0)."),
    (account_mod.handle_account_risk, 10.0, "Risk per trade must be above 0% and at most 2.0% (got 10.0)."),
    (account_mod.handle_account_risk, float("nan"), "Risk per trade must be above 0% and at most 2.0% (got nan)."),
    (account_mod.handle_account_maxpositions, 0,
     "Max open positions must be a whole number of 1 or more (got 0)."),
    (account_mod.handle_account_positionpct, 150.0,
     "Position size must be above 0% and at most 100% of the account (got 150.0)."),
    (account_mod.handle_account_maxpositionpct, -1.0,
     "Max position size must be above 0% and at most 100% of the account (got -1.0)."),
    (account_mod.handle_account_maxposition, -1.0, "Max position value must be 0 (off) or more (got -1.0)."),
    (account_mod.handle_account_maxrisk, float("inf"), "Max risk per trade must be 0 (off) or more (got inf)."),
]


@pytest.mark.parametrize("handler,value,message", CASES, ids=[f"{c[0].__name__}={c[1]}" for c in CASES])
def test_invalid_value_replies_with_the_message_and_saves_nothing(saved, handler, value, message):
    reply = _Reply()
    asyncio.run(handler(reply, value))
    assert reply.errors == [message] and reply.sent == [] and saved == []


def test_valid_value_still_saves_and_confirms(saved):
    reply = _Reply()
    asyncio.run(account_mod.handle_account_risk(reply, 1.5))
    assert reply.sent == ["Risk per trade set to 1.5%."] and saved[-1]["risk_pct"] == 1.5


@pytest.mark.parametrize("stored,text", [
    (1.0, "1.0%"),
    (2.0, "2.0%"),
    (10.0, "10% stored → 2% used (hard cap)"),
    (2.5, "2.5% stored → 2% used (hard cap)"),
])
def test_risk_used_text(stored, text):
    assert account_mod._risk_used_text({"risk_pct": stored}) == text


def test_account_show_makes_the_legacy_clamp_visible(monkeypatch):
    cfg = {"balance": 10_000.0, "base_balance": 10_000.0, "risk_pct": 10.0, "sizing_mode": "risk_pct"}
    monkeypatch.setattr(account_mod, "load_account_config", lambda: dict(cfg))
    reply = _Reply()
    asyncio.run(account_mod.handle_account_show(reply))
    assert "Risk %** -- 10% stored → 2% used (hard cap) of balance risked per trade" in reply.sent[0]


def test_edge_mode_copy_names_the_real_hard_cap():
    text = account_mod._sizing_set_text({"sizing_mode": "kelly", "risk_pct": 1.0, "balance": 1.0})
    assert text.endswith("(1.0%, the ceiling) or the frozen 2% hard cap.")
