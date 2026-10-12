"""v153 SP6: a /scrapeall that outlives its interaction token still delivers
its result as a fresh message, never as an edit of the dead webhook message."""
import asyncio

from swingbot.commands import data as data_mod
from swingbot.commands.reply import CtxReply, InteractionReply, TOKEN_LIFETIME_S
from tests.commands.reply_harness import FakeContext, FakeInteraction

ROWS = [{"ticker": "AAA", "bars": 10, "start": "2020-01-02", "end": "2020-02-03", "from_cache": False}]


def _stub(monkeypatch, tmp_path, on_scrape=lambda: None):
    monkeypatch.setattr(data_mod, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(data_mod.config, "EXPORT_DIR", str(tmp_path))

    def scrape(tickers, out_dir, force=False, on_ticker_done=None, **_kw):
        on_scrape()
        return list(ROWS)
    monkeypatch.setattr(data_mod.export_data, "scrape_watchlist_history", scrape)


def _summary_events(events):
    return [e for e in events if (e[1] or "").startswith("**Scrape complete**")]


def test_stale_interaction_posts_the_summary_as_a_fresh_channel_message(monkeypatch, tmp_path):
    now = [0.0]

    def outlive_the_token():
        now[0] = TOKEN_LIFETIME_S + 1.0

    _stub(monkeypatch, tmp_path, on_scrape=outlive_the_token)
    events: list = []
    interaction = FakeInteraction(events)
    reply = InteractionReply(interaction, clock=lambda: now[0])

    asyncio.run(data_mod.handle_scrapeall(reply))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] != "edit"
    assert "channel.send" in interaction.calls
    assert not reply.failed


def test_fresh_interaction_edits_the_progress_message_into_the_summary(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    events: list = []
    reply = InteractionReply(FakeInteraction(events), clock=lambda: 0.0)

    asyncio.run(data_mod.handle_scrapeall(reply))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] == "edit"


def test_prefix_scrapeall_still_edits_its_progress_message(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    events: list = []

    asyncio.run(data_mod.handle_scrapeall(CtxReply(FakeContext(events))))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] == "edit"
