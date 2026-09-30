"""v110: loops.py pushes SYSTEM embeds -- config notices and a guarded bot-online post."""
import asyncio
import logging
import types

from swingbot import config
from swingbot.commands.scanning import loops


class _Chan:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)


def _wire(monkeypatch, chan):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "123", raising=False)
    monkeypatch.setattr(loops, "bot", types.SimpleNamespace(get_channel=lambda _id: chan),
                        raising=False)
    monkeypatch.setattr(loops, "trade_log", types.SimpleNamespace(get_stats=lambda: {"open": 2}))


def test_config_change_posts_a_silent_config_embed(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, chan)
    asyncio.run(loops._post_config_notices({"MIN_ALERT_CONFIDENCE_LEVEL": (3, 4),
                                            "LOG_LEVEL": ("INFO", "DEBUG")}))
    assert len(chan.sent) == 1                     # LOG_LEVEL is not a notified key
    assert chan.sent[0]["content"] == "⚙️ SYSTEM · CONFIG · Min confidence level Lv3 → Lv4"
    assert "Lv4+" in chan.sent[0]["embed"].description
    assert chan.sent[0]["silent"] is True


def test_a_failing_config_notice_never_raises(monkeypatch):
    _wire(monkeypatch, _Chan(fail=True))
    asyncio.run(loops._post_config_notices({"SCAN_INTERVAL_MINUTES": (5, 10)}))


def test_bot_online_is_a_system_embed(monkeypatch):
    chan = _Chan()
    _wire(monkeypatch, chan)
    asyncio.run(loops._post_bot_online(77))
    assert chan.sent[0]["content"].startswith("🤖 SYSTEM · ONLINE · ")
    assert "Watchlist: 77 ticker(s) · open trades: 2" in chan.sent[0]["embed"].description


def test_bot_online_send_failure_is_logged_not_raised(monkeypatch, caplog):
    """v110 §6.3 regression: the startup post was unguarded."""
    _wire(monkeypatch, _Chan(fail=True))
    with caplog.at_level(logging.WARNING, logger="swing-bot"):
        asyncio.run(loops._post_bot_online(77))
    assert any("bot-online" in r.getMessage() and r.exc_info for r in caplog.records)


def test_no_trades_channel_means_no_bot_online_post(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "", raising=False)
    asyncio.run(loops._post_bot_online(77))
