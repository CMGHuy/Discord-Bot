"""v110 §4: closed-trade and near-close posts carry the registry push line."""
import asyncio
from types import SimpleNamespace

from swingbot import config
from swingbot.core.scanning import lifecycle_embeds


class _Chan:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs)


def _bot(chan):
    return SimpleNamespace(get_channel=lambda _id: chan)


def _trade():
    return {"id": "trade-42", "ticker": "NVDA", "status": "win", "entry": 100.0,
            "exit_price": 110.0, "stop_loss": 95.0, "take_profit": 110.0,
            "direction": "bullish", "strategy": "RSI Pullback", "horizon_key": "2w",
            "confidence_label": "High", "confidence_level": 4}


def test_closed_trade_is_sent_with_its_registry_push_line(monkeypatch):
    chan = _Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    asyncio.run(lifecycle_embeds.notify_closed_trades(_bot(chan), [_trade()]))
    sent = chan.sent[0]
    assert sent["content"] == sent["embed"].push_text
    assert sent["content"].startswith("🏁 RESULT · ▲ LONG NVDA · CLOSED · ✅ WIN")
    assert "**NVDA**" not in sent["content"]          # the old ✅ WIN — **TICK** header is gone


def test_near_close_is_sent_with_its_registry_push_line(monkeypatch):
    chan = _Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    trade = {**_trade(), "status": "open"}
    warning = {"trade": trade, "near_which": "take-profit", "sl_dist_pct": 4.0,
               "tp_dist_pct": 0.8, "current_price": 109.0}
    asyncio.run(lifecycle_embeds.notify_near_close(_bot(chan), [warning]))
    assert chan.sent[0]["content"] == "👀 WATCH · ▲ LONG NVDA · NEARING TP · 0.8% away"
