"""v110: the retrospective posts one guarded SYSTEM embed per chunk; the
weekend deep scan posts one 🔭 SYSTEM embed."""
import asyncio
import types

from swingbot import config
from swingbot.commands.scanning import recap


class _Chan:
    def __init__(self, fail_on=()):
        self.sent, self.calls, self.fail_on = [], 0, set(fail_on)

    async def send(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)


def _channel(monkeypatch, chan):
    async def resolve(*args, **kwargs):
        return chan
    monkeypatch.setattr(recap, "_resolve_retrospective_channel", resolve)


def test_one_failed_chunk_never_drops_the_rest_of_the_recap(monkeypatch):
    """v110 §6.3 regression: the chunk sends were unguarded."""
    from swingbot.core.tracking import retrospective

    monkeypatch.setattr(retrospective, "build_daily_retrospective",
                        lambda trades, today=None: ["x" * 2500, "   ", "short"])
    monkeypatch.setattr(recap, "trade_log", types.SimpleNamespace(get_trades=lambda **kw: []))
    chan = _Chan(fail_on={1})
    _channel(monkeypatch, chan)
    asyncio.run(recap._post_retrospective())
    assert chan.calls == 3
    assert [s["embed"].title for s in chan.sent] == [
        "📜 RETROSPECTIVE · 2/3", "📜 RETROSPECTIVE · 3/3"]
    assert all(s["content"].startswith("📜 SYSTEM · RETROSPECTIVE") for s in chan.sent)


def test_weekend_deep_scan_posts_one_system_embed(monkeypatch):
    from swingbot.core.marketdata import data

    plan = types.SimpleNamespace(ticker="AAA", trigger_price=10.0, quality_score=70,
                                 strategy="MACD", direction="bullish")

    async def run_scan(**kwargs):
        return [(None, None, plan)]

    monkeypatch.setattr(config, "SIGNAL_CONFIRMATION_SCANS", 2)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 3)
    monkeypatch.setattr(recap.scan_engine, "run_scan", run_scan)
    monkeypatch.setattr(data, "get_current_price", lambda ticker: 10.5)
    chan = _Chan()
    _channel(monkeypatch, chan)
    report = asyncio.run(recap.weekend_deep_scan())
    sent = chan.sent[0]
    assert sent["embed"].title == "🔭 WEEKEND DEEP SCAN · 1 candidate(s)"
    assert sent["content"].startswith("🔭 SYSTEM · WEEKEND DEEP SCAN")
    assert sent["embed"].description == report and "▲ AAA" in report


def test_deep_scan_report_fits_one_embed_at_the_15_candidate_cap():
    from swingbot.commands.scanning.alerts import deep_scan_report

    plan = types.SimpleNamespace(strategy="Break & Retest Long", direction="bearish")
    items = [types.SimpleNamespace(ticker="ABCDEFGHIJ", quality_score=100, plan=plan,
                                   trigger_distance_pct=12.34) for _ in range(40)]
    assert len(deep_scan_report(items)) <= 4096
