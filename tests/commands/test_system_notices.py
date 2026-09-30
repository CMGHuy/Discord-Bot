"""v110 §5: SYSTEM notices -- registry embeds, the healthcheck line,
retrospective chunking, and the guarded send."""
import asyncio
import logging
import types

import pytest

from swingbot.commands.scanning import notices
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

FUNNEL = {"tickers": 50, "checked": 400, "scenarios_found": 6, "fully_qualifying": 3,
          "deduped": 2, "skipped_already_open": 1, "awaiting_confirmation": 1,
          "failed_min_confluence": 2, "failed_min_confidence": 0, "rs_blocked": 1}


def _online():
    return notices.bot_online_embed(now_text="2026-09-28 09:00 CEST", session_start=9,
                                    session_end=22, interval=5, watchlist_size=77,
                                    open_count=2, min_level=3)


@pytest.mark.parametrize("build,kind,colour", [
    (lambda: notices.health_alert_embed(3, "never", RuntimeError("boom")),
     Kind.HEALTH_ALERT, kinds.HEALTH_RED),
    (notices.health_recovered_embed, Kind.HEALTH_RECOVERED, kinds.HEALTH_GREEN),
    (_online, Kind.BOT_ONLINE, kinds.SYSTEM_SLATE),
    (lambda: notices.config_notice_embed("Scan interval every 5 min → every 10 min"),
     Kind.CONFIG_CHANGE, kinds.SYSTEM_SLATE),
    (lambda: notices.scan_summary_embed("10:05", FUNNEL, 2), Kind.SCAN_SUMMARY, kinds.SYSTEM_SLATE),
    (lambda: notices.deep_scan_embed("Watchlist candidates for Monday", 4),
     Kind.DEEP_SCAN, kinds.SYSTEM_SLATE),
])
def test_every_system_notice_is_a_system_push(build, kind, colour):
    embed = build()
    assert embed.push_text.startswith(f"{kinds.badge(kind)} SYSTEM · {kind.label}")
    assert embed.title.startswith(f"{kinds.badge(kind)} {kind.label}")
    assert embed.color.value == colour
    assert embed.footer.text == "SYSTEM"
    assert embed.timestamp is not None


def test_health_alert_names_the_streak_and_the_error():
    embed = notices.health_alert_embed(3, "never", RuntimeError("tick exploded"))
    assert embed.title == "🚨 HEALTH ALERT · 3 failed tick(s) in a row"
    assert "RuntimeError: tick exploded" in embed.description
    assert "Last successful tick: never" in embed.description


def test_bot_online_carries_the_session_facts():
    embed = _online()
    assert embed.title == "🤖 ONLINE · 2026-09-28 09:00 CEST"
    assert "09:00–22:00 Berlin" in embed.description
    assert "Watchlist: 77 ticker(s)" in embed.description and "Lv3" in embed.description


def test_config_notice_keeps_its_note():
    embed = notices.config_notice_embed("Min confidence level Lv3 → Lv4", "Lv4+ from now on.")
    assert embed.title == "⚙️ CONFIG · Min confidence level Lv3 → Lv4"
    assert embed.description == "Lv4+ from now on."
    assert notices.config_notice_embed("x").description is None


def test_scan_summary_marks_priority_and_explains_the_gap():
    embed = notices.scan_summary_embed("10:05", FUNNEL, 2, notices.scan_gap_note(FUNNEL),
                                       priority=True)
    assert embed.title == "🩺 SCAN · 10:05 · 2 new alert(s) ✨"
    assert "(1 merged as duplicate setup(s), 1 already open)" in embed.description
    assert "✅" not in embed.description
    assert "🟢" not in embed.title and "🟡" not in embed.title


def test_scan_gap_note_is_empty_when_nothing_was_dropped():
    assert notices.scan_gap_note({"fully_qualifying": 2, "deduped": 2}) == ""


def test_has_priority_reads_the_star_in_alert_titles():
    star = (types.SimpleNamespace(title="🆕 ▲ LONG A · ALERT · Lv5 ⭐"),)
    plain = (types.SimpleNamespace(title="🆕 ▲ LONG B · ALERT · Lv3"),)
    assert notices.has_priority([plain, star])
    assert not notices.has_priority([plain])
    assert not notices.has_priority([(types.SimpleNamespace(title=None),)])


def test_healthcheck_is_a_stethoscope_text_line_with_plain_marks():
    text = notices.healthcheck_text("10:05", FUNNEL, 2, 2)
    assert text.startswith("🩺 **Healthcheck** (10:05) — nothing new this tick")
    assert ("✔ 3 fully qualifying (⏳ 1 still awaiting confirmation (needs to reappear "
            "2 scan(s) in a row before it posts))") in text
    assert "✖ failed a requirement: 2 below min strategies, 1 blocked by RS gate" in text
    assert "📂 2 open trade(s)" in text
    for glyph in ("✅", "❌", "💓"):
        assert glyph not in text


def test_healthcheck_without_a_funnel_is_the_short_form():
    assert notices.healthcheck_text("10:05", None, 0, 2) == (
        "🩺 **Healthcheck** (10:05) — scan complete, nothing new\n• 📂 0 open trade(s)")


def test_chunk_text_splits_at_the_last_newline_under_the_limit():
    text = "a" * 1500 + "\n" + "b" * 1000
    chunks = notices.chunk_text(text)
    assert chunks == ["a" * 1500, "\n" + "b" * 1000]
    assert "".join(chunks) == text


def test_chunk_text_hard_splits_a_line_longer_than_the_limit():
    assert [len(c) for c in notices.chunk_text("x" * 4000)] == [1990, 1990, 20]


def test_chunk_text_drops_blank_chunks():
    assert notices.chunk_text("   ") == []


def test_retrospective_embeds_number_their_parts_and_fit_discord():
    embeds = notices.retrospective_embeds(["x" * 2500, "   ", "short"])
    assert [e.title for e in embeds] == [
        "📜 RETROSPECTIVE · 1/3", "📜 RETROSPECTIVE · 2/3", "📜 RETROSPECTIVE · 3/3"]
    assert all(len(e.description) <= 4096 for e in embeds)
    assert embeds[2].description == "short"


def test_a_single_chunk_retrospective_has_no_part_number():
    assert notices.retrospective_embeds(["short"])[0].title == "📜 RETROSPECTIVE"


class _Chan:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return "msg"


def test_send_guarded_passes_the_content_line():
    chan, embed = _Chan(), notices.health_recovered_embed()
    assert asyncio.run(notices.send_guarded(chan, embed, what="x")) == "msg"
    assert chan.sent == [{"embed": embed, "content": embed.push_text}]


def test_send_guarded_logs_the_traceback_and_returns_none(caplog):
    with caplog.at_level(logging.WARNING, logger="swing-bot"):
        result = asyncio.run(notices.send_guarded(
            _Chan(fail=True), notices.health_recovered_embed(), what="recovery notice"))
    assert result is None
    record = next(r for r in caplog.records if "recovery notice" in r.getMessage())
    assert record.exc_info is not None
