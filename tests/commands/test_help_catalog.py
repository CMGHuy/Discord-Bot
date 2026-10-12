"""v153 SP17: the help catalog shows each row's slash twin and fits
Discord's embed limits (field value <= 1024, <= 25 fields, <= 6000 chars)."""
import datetime as dt

import discord
import pytest

from swingbot.bot_core import COMMANDS_BY_CATEGORY
from swingbot.commands import info
from tests.commands.reply_harness import comparable, run_both

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)
ROWS = [(usage, desc) for rows in COMMANDS_BY_CATEGORY.values() for usage, desc in rows]


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    # ui.apply_chrome stamps utcnow(); two builds must compare equal.
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


@pytest.mark.parametrize("usage, desc, expected", [
    ("!ping", "Check bot latency", "`!ping` · `/ping` — Check bot latency"),
    ("!commands", "Show this list", "`!commands` · `/help` — Show this list"),
    ("!trades clear", "Delete ALL trade records",
     "`!trades clear` · `/trades-clear` — Delete ALL trade records"),
    ("!trades [open|win|loss|all] [per_page]", "x",
     "`!trades [open|win|loss|all] [per_page]` · `/trades` — x"),
    ("!trade delete ID", "x", "`!trade delete ID` · `/trade delete` — x"),
    ("!trade ID", "x", "`!trade ID` · `/trade show` — x"),
    ("!account", "x", "`!account` · `/account show` — x"),
    ("!account sizing risk|account", "x", "`!account sizing risk|account` · `/account sizing` — x"),
    ("!watchlist add TICKER", "x", "`!watchlist add TICKER` · `/watchlist add` — x"),
    ("!nosuchcommand ARG", "x", "`!nosuchcommand ARG` — x"),
])
def test_help_line(usage, desc, expected):
    assert info.help_line(usage, desc) == expected


def test_every_row_keeps_the_bang_form_first_and_has_a_slash_twin():
    for usage, desc in ROWS:
        assert usage.startswith("!"), usage
        assert info.help_line(usage, desc).startswith(f"`{usage}` · `/"), f"no slash twin for {usage!r}"


def test_every_embed_and_field_fits_discord_limits():
    for embed in info.help_embeds():
        assert len(embed.fields) <= info.EMBED_FIELD_LIMIT == 25
        assert len(embed) <= info.EMBED_TOTAL_LIMIT == 6000
        for field in embed.fields:
            assert 0 < len(field.value) <= info.FIELD_VALUE_LIMIT == 1024, field.name
            assert len(field.name) <= 256


def test_every_row_appears_once_and_in_order():
    rendered = "\n".join(field.value for embed in info.help_embeds() for field in embed.fields)
    assert rendered.split("\n") == [info.help_line(usage, desc) for usage, desc in ROWS]


def test_an_oversized_category_continues_in_a_cont_field():
    names = [field.name for embed in info.help_embeds() for field in embed.fields]
    # 1262 chars with slash forms (1116 before v153, already over 1024).
    assert "📊 Trades & performance (cont.)" in names
    for category in COMMANDS_BY_CATEGORY:
        assert names.count(category) == 1
    assert names[0] == next(iter(COMMANDS_BY_CATEGORY))


def test_first_embed_carries_the_title_and_both_prefixes():
    first = info.help_embeds()[0]
    assert first.title == info.HELP_TITLE == "📖 Swing Trade Bot — Commands"
    assert first.description == info.HELP_DESCRIPTION
    assert "Prefix: `!`" in first.description and "Slash: `/`" in first.description
    assert first.footer.text  # apply_chrome ran


def test_field_chunks_break_between_lines_only():
    assert info._field_chunks(["a" * 600, "b" * 400, "c" * 30], 1024) == [
        "a" * 600 + "\n" + "b" * 400, "c" * 30]
    assert info._field_chunks(["a" * 600, "b" * 600], 1024) == ["a" * 600, "b" * 600]
    assert info._field_chunks(["x" * 2000], 1024) == ["x" * 1023 + "…"]
    assert info._field_chunks([], 1024) == []


def test_help_spills_into_further_embeds_within_limits(monkeypatch):
    big = {f"Category {i:02d}": [("!ping", "d" * 900)] for i in range(30)}
    monkeypatch.setattr(info, "COMMANDS_BY_CATEGORY", big)
    embeds = info.help_embeds()
    assert len(embeds) >= 2
    assert all(embed.title == info.HELP_TITLE + " (cont.)" for embed in embeds[1:])
    assert all(embed.description is None for embed in embeds[1:])
    for embed in embeds:
        assert len(embed) <= 6000 and len(embed.fields) <= 25
    assert [field.name for embed in embeds for field in embed.fields] == list(big)


def test_handle_help_sends_every_embed_on_both_surfaces(monkeypatch):
    run = run_both(info.handle_help, monkeypatch)
    count = len(info.help_embeds())
    assert comparable(run.ctx_events) == comparable(run.inter_events)
    assert [event[0] for event in run.ctx_events] == ["send"] * count
    assert all(event[5] for event in run.inter_events)  # ephemeral on /help
    assert not run.ctx_reply.failed and not run.inter_reply.failed
