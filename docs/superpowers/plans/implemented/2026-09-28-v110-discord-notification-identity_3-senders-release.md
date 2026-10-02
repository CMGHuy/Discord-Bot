# v110 — Part 3: senders, system notices, verification and release

Header, goal, global constraints, resolved spec gaps, parallelisation and conventions live in [`_0-index`](2026-09-28-v110-discord-notification-identity_0-index.md). Every task below implicitly includes its Global Constraints. Phase A is in [`_1-registry`](2026-09-28-v110-discord-notification-identity_1-registry.md) and Phase B in [`_2-builders`](2026-09-28-v110-discord-notification-identity_2-builders.md).

# Phase C — Senders and system notices

### Task V110-8: Strategy-alert mirror is a real embed (spec §6.1)

**Files:**
- Modify: `swingbot/core/scanning/strategy_pass.py` (the import line, `simple_line` (deleted) and the `result.alerts.append(...)` line in `_emit_signal`)
- Test: `tests/scanning/test_strategy_pass_emit.py`

**Interfaces:**
- Consumes: V110-4's `alert_embeds.build_strategy_simple_embed(plan)`.
- Produces: strategy alert tuples are `(PushEmbed, None, plan, PushEmbed)`. The 4th element is never a `str` again.

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_strategy_pass_emit.py`:

```python
def test_the_simple_mirror_is_an_embed_never_a_str(deps, monkeypatch):
    """v110 §6.1 regression: the 4th tuple element was simple_line(plan), a
    str that _send_alerts sent as embed= -- it failed on every strategy alert,
    logged a warning, and the full alert pinged instead of the mirror."""
    import discord

    result = _emit(deps, monkeypatch, sizing_ok=True)
    simple = result.alerts[0][3]
    assert isinstance(simple, discord.Embed)
    assert simple.push_text.startswith("🆕 NEW SETUP · ▲ LONG AAPL · STRATEGY")


def test_simple_line_is_gone():
    assert not hasattr(sp, "simple_line")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_emit.py`
Expected: FAIL. `result.alerts[0][3]` is a `str`, and `sp.simple_line` exists.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/scanning/strategy_pass.py`, change:

```python
from swingbot.core.scanning.alert_embeds import build_strategy_alert_embed
```

to:

```python
from swingbot.core.scanning.alert_embeds import (build_strategy_alert_embed,
                                                 build_strategy_simple_embed)
```

Delete the whole `simple_line` function. In `_emit_signal`, change:

```python
    result.alerts.append((build_strategy_alert_embed(plan), None, plan, simple_line(plan)))
```

to:

```python
    # v110 §6.1: the simple-channel mirror is an embed like every other alert's.
    result.alerts.append((build_strategy_alert_embed(plan), None, plan,
                          build_strategy_simple_embed(plan)))
```

Confirm that nothing else used it: `git grep -n "simple_line" -- swingbot tests` prints only the new `test_simple_line_is_gone`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_emit.py tests/scanning/test_strategy_pass_signals.py tests/scanning/test_strategy_pass_frame.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/scanning/strategy_pass.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/strategy_pass.py tests/scanning/test_strategy_pass_emit.py
git commit -m "fix(v110): strategy-alert simple mirror is a registry embed, not a str

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/scanning/strategy_pass.py tests/scanning/test_strategy_pass_emit.py
```

---

### Task V110-9: `_send_alerts` — content lines and per-message isolation; digest and deep-scan text

Load the `alert-surface` skill first. `_send_alerts` still only posts already-built tuples. The routing, the mirror-first ordering and the silent policy are unchanged.

**Files:**
- Modify: `swingbot/commands/scanning/alerts.py`:
  - `_post_daily_digest`, `deep_scan_report` and `_send_alerts`
  - new helpers `_append_overflow_digest`, `_destination`, `_mirror` and `_post_alert`
- Test: `tests/commands/test_send_alerts_v110.py` (new). `tests/scanning/test_simple_alerts.py`, `tests/infra/test_silent_alerts_channel.py` and `tests/marketdata/test_universe.py::test_deep_scan_report_renders` must stay green **unchanged**.

**Interfaces:**
- Consumes: V110-1's `Kind.DIGEST` and `kinds.content_line`, and V110-3's `ui.push_kwargs`.
- Produces:
  - `deep_scan_report(items) -> str` has no 🔭 header line; the header moves to V110-12's embed title. Each candidate line leads with its ▲/▼.
  - `DEEP_SCAN_NOTE` is a module constant.

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_send_alerts_v110.py`:

```python
"""v110: _send_alerts pushes content lines and isolates every send; the
digest carries one registry content line; deep-scan candidates show ▲/▼."""
import asyncio
import logging
import types

import discord
import pytest

from swingbot import config
from swingbot.commands.scanning import alerts
from swingbot.commands.scanning.alerts import _send_alerts, deep_scan_report
from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind


class Chan:
    def __init__(self, fail_on=()):
        self.sent, self.calls, self.fail_on = [], 0, set(fail_on)

    async def send(self, *args, **kwargs):
        self.calls += 1
        if self.calls in self.fail_on:
            raise RuntimeError("discord is having a day")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=self.calls)


@pytest.fixture
def simple(monkeypatch):
    chan = Chan()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    monkeypatch.setattr(config, "MAX_ALERTS_PER_SCAN", 10, raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", "999", raising=False)
    monkeypatch.setattr(alerts, "bot", types.SimpleNamespace(get_channel=lambda _id: chan),
                        raising=False)
    return chan


def test_one_failing_send_does_not_abort_the_batch(simple, caplog):
    """v110 §6.2 regression: the main send was unguarded, so one failure lost
    every alert after it."""
    main = Chan(fail_on={1})
    batch = [("E1", None, None, "S1"), ("E2", None, None, "S2"), ("E3", None, None, "S3")]
    with caplog.at_level(logging.WARNING, logger="swing-bot"):
        asyncio.run(_send_alerts(main, batch))
    assert [s["embed"] for s in main.sent] == ["E2", "E3"]
    assert [s["embed"] for s in simple.sent] == ["S1", "S2", "S3"]
    failures = [r for r in caplog.records if "rest of the batch" in r.getMessage()]
    assert len(failures) == 1 and failures[0].exc_info is not None


def test_pushed_embeds_carry_their_content_line_on_both_channels(simple):
    main = Chan()
    full = ui.push_embed(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐")
    mirror = ui.push_embed(Kind.SETUP_SIMPLE, "AAPL", "bullish", "Lv4")
    asyncio.run(_send_alerts(main, [(full, None, None, mirror)]))
    assert main.sent[0]["content"] == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert main.sent[0]["silent"] is True
    assert simple.sent[0] == {"embed": mirror,
                              "content": "🆕 NEW SETUP · ▲ LONG AAPL · SIMPLE · Lv4"}


@pytest.fixture
def digest_env(monkeypatch):
    from swingbot.commands import stats, views
    from swingbot.core.planning import plan_store
    from swingbot.core.scanning import embeds

    class View:
        def __init__(self, plan_id, author_id=None):
            self.message = None

    monkeypatch.setattr(plan_store, "PlanStore", lambda: types.SimpleNamespace(all=lambda: []))
    monkeypatch.setattr(stats, "_fake_item_from_plan", lambda plan: plan)
    monkeypatch.setattr(embeds, "build_embed",
                        lambda item, *a, **k: discord.Embed(title=item.plan_id))
    monkeypatch.setattr(views, "PlanActionView", View)


def test_digest_sends_one_content_line_for_the_batch(digest_env, monkeypatch):
    plans = [types.SimpleNamespace(plan_id="p1"), types.SimpleNamespace(plan_id="p2")]
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: plans)
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert len(chan.sent) == 2                     # no separate 📌 header message
    assert chan.sent[0]["content"] == kinds.content_line(
        Kind.DIGEST, "", detail="2 VALIDATED plan(s), ranked by follow score")
    assert chan.sent[0]["content"].startswith("🆕 NEW SETUP · TOP PLANS")
    assert "content" not in chan.sent[1]
    assert [s["embed"].title for s in chan.sent] == ["p1", "p2"]


def test_an_empty_digest_still_says_so_through_the_registry(digest_env, monkeypatch):
    monkeypatch.setattr(alerts, "digest_payload", lambda all_plans, today, max_n: [])
    chan = Chan()
    asyncio.run(alerts._post_daily_digest(chan))
    assert chan.sent == [
        {"content": "🆕 NEW SETUP · TOP PLANS · no VALIDATED plans qualified today"}]


def test_deep_scan_report_marks_each_candidates_direction():
    def item(ticker, direction, score):
        plan = types.SimpleNamespace(strategy="MACD", direction=direction)
        return types.SimpleNamespace(ticker=ticker, quality_score=score,
                                     trigger_distance_pct=1.2, plan=plan)

    lines = deep_scan_report([item("AAA", "bullish", 80), item("BBB", "bearish", 60)]).splitlines()
    assert lines[0].lower().startswith("watchlist candidates for monday")
    assert lines[1].startswith("▲ AAA") and lines[2].startswith("▼ BBB")
    assert all("🔭" not in line for line in lines)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py`
Expected: FAIL. The first send's `RuntimeError` escapes `_send_alerts`, no `content` is sent, the digest posts a separate header, and the deep-scan lines have no glyph.

- [ ] **Step 3: Write the implementation**

In `swingbot/commands/scanning/alerts.py`, add below `from swingbot.core import presentation as ui`:

```python
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
```

In `_post_daily_digest`, replace everything from `    if not top:` to the end of the function with:

```python
    if not top:
        await channel.send(content=kinds.content_line(
            Kind.DIGEST, "", detail="no VALIDATED plans qualified today"))
        return

    # v110 §4: one registry content line for the whole batch, on its first
    # embed -- it replaces the separate "📌 Top plans today" header message.
    header = kinds.content_line(
        Kind.DIGEST, "", detail=f"{len(top)} VALIDATED plan(s), ranked by follow score")
    for index, plan in enumerate(top):
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=None)
        kwargs = {"embed": embed, "view": view}
        if index == 0:
            kwargs["content"] = header
        view.message = await channel.send(**kwargs)
```

Replace the whole `deep_scan_report` function with:

```python
DEEP_SCAN_NOTE = ("Watchlist candidates for Monday -- forming setups at relaxed "
                  "thresholds (NOT alerts, NOT validated signals)")


def deep_scan_report(items: list) -> str:
    """Task E87: renders the Saturday weekend-deep-scan candidate list --
    NOT alerts, just a curated heads-up for Monday. Pure formatting; see
    weekend_deep_scan() for how `items` gets built from a relaxed-threshold
    scan pass. v110: the 🔭 header is the SYSTEM embed's title (recap.py),
    and each candidate leads with its ▲/▼."""
    lines = [DEEP_SCAN_NOTE]
    for it in sorted(items, key=lambda i: -(i.quality_score or 0))[:15]:
        glyph = ui.direction_glyph(getattr(it.plan, "direction", ""))
        lines.append(f"{glyph} {it.ticker:<6} {it.plan.strategy:<18} "
                     f"q{it.quality_score} — {ui.fmt_pct(it.trigger_distance_pct)} from trigger")
    return "\n".join(lines)
```

Replace the body of `_send_alerts` below its docstring, from `    from swingbot.commands.views import PlanActionView` to the end of the function, with:

```python
    from swingbot.commands.views import PlanActionView
    from swingbot.core.analytics.rank import follow_score

    # Alert-flood control (Task E77): _ordered_alerts already ranks by
    # follow_score (rank_plans, THE shared ordering), so the cap is applied
    # directly to that ranked list.
    ordered = _ordered_alerts(alerts)
    cap = getattr(config, "MAX_ALERTS_PER_SCAN", 10)
    to_send, overflow = ordered[:cap], ordered[cap:]
    if overflow:
        _append_overflow_digest(to_send, overflow, follow_score)

    firehose_id = getattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "") or ""
    firehose_channel = bot.get_channel(int(firehose_id)) if route_by_confidence and firehose_id else None
    simple_channel = _simple_alert_channel()

    for alert in to_send:
        # Tolerant unpack: engine.py emits 4-tuples (…, simple_embed), but the
        # legacy 3-tuple shape is still built by hand in tests. A missing 4th
        # element just means "no simple mirror for this one".
        embed, chart_path, plan = alert[0], alert[1], alert[2]
        simple_embed = alert[3] if len(alert) > 3 else None
        send_to = _destination(destination, firehose_channel, firehose_id, plan,
                               route_by_confidence)
        # ONE ping per signal, from the simple channel: the mirror goes FIRST
        # and its success decides whether the full alert is silenced.
        mirrored = await _mirror(simple_channel, simple_embed, plan)
        # v110 §6.2: each send is isolated -- one failure is logged with its
        # traceback and the rest of the batch still posts.
        try:
            await _post_alert(send_to, embed, chart_path, plan, mirrored, PlanActionView)
        except Exception:
            log.warning("Could not post alert for %s -- the rest of the batch still posts.",
                        getattr(plan, "ticker", None) or getattr(embed, "title", "?"),
                        exc_info=True)
```

Add these helpers directly above `async def _send_alerts`:

```python
def _append_overflow_digest(to_send: list, overflow: list, follow_score) -> None:
    """Name every capped-out plan in the last posted alert's footer.

    Index rather than unpack: engine.py emits 4-tuples, and a fixed 3-name
    unpack once raised before any send, losing every alert."""
    overflow_plans = [a[2] for a in overflow if len(a) > 2 and a[2] is not None]
    digest_items = [(p.ticker, round(follow_score(p))) for p in overflow_plans]
    if not digest_items:
        return
    digest = "+%d more: %s" % (len(digest_items),
                               ", ".join(f"{t} ({s})" for t, s in digest_items))
    last_embed = to_send[-1][0]
    existing_footer = last_embed.footer.text if last_embed.footer else None
    last_embed.set_footer(text=f"{existing_footer} | {digest}" if existing_footer else digest)


def _destination(destination, firehose_channel, firehose_id: str, plan, route_by_confidence: bool):
    """The channel one alert posts to: the caller's, or the firehose (Task E86)."""
    if not (route_by_confidence and firehose_channel is not None and plan is not None):
        return destination
    target_id = route_channel_id(type("I", (), {"plan": plan})())
    return firehose_channel if target_id == firehose_id else destination


async def _mirror(simple_channel, simple_embed, plan) -> bool:
    """Post the simple-channel mirror with its content line; True once it
    landed. A failure never costs the real alert -- it keeps its ping."""
    if simple_channel is None or not simple_embed:
        return False
    try:
        await simple_channel.send(**ui.push_kwargs(simple_embed))
    except Exception as exc:
        log.warning("Could not post simple alert for %s to channel %s: %s "
                    "-- full alert will notify instead.",
                    getattr(plan, "ticker", "?"),
                    getattr(config, "DISCORD_CHANNEL_TRADES_SIMPLE_ID", ""), exc)
        return False
    return True


async def _post_alert(send_to, embed, chart_path, plan, mirrored: bool, view_cls) -> None:
    """Send one full alert: content line, chart, plan buttons. silent=True
    only once the mirror landed (the alerts channel forces it regardless)."""
    view = view_cls(plan.plan_id, author_id=None) if plan is not None else None
    kwargs = {**ui.push_kwargs(embed), "silent": mirrored}
    if chart_path:
        kwargs["file"] = discord.File(chart_path, filename=os.path.basename(chart_path))
    if view is not None:
        kwargs["view"] = view
    msg = await send_to.send(**kwargs)
    if view is not None:
        view.message = msg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py tests/scanning/test_simple_alerts.py tests/infra/test_silent_alerts_channel.py tests/marketdata/test_universe.py`
Expected: PASS, 0 failed, with the existing three files unedited.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/alerts.py`
Expected: no output. `_send_alerts` drops from 26 to under 11.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/alerts.py tests/commands/test_send_alerts_v110.py
git commit -m "fix(v110): isolate each alert send; push content lines; digest and deep-scan text through the registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/alerts.py tests/commands/test_send_alerts_v110.py
```

---

### Task V110-10: `commands/scanning/notices.py` — SYSTEM embeds, healthcheck line, chunking, guarded send

**Files:**
- Create: `swingbot/commands/scanning/notices.py`
- Test: `tests/commands/test_system_notices.py` (new)

**Interfaces:**
- Consumes: V110-1 (`Kind`, `kinds.badge`) and V110-3 (`ui.push_embed`, `ui.apply_chrome(kind=…)`, `ui.push_kwargs`).
- Produces (consumed by V110-11 and V110-12):
  - Constants: `HEALTHCHECK_BADGE` and `RETRO_CHUNK = 1990`.
  - Embed builders:
    - `system_embed(kind, detail="", description=None)`
    - `health_alert_embed(failures, last_success, exc)`
    - `health_recovered_embed()`
    - `bot_online_embed(*, now_text, session_start, session_end, interval, watchlist_size, open_count, min_level)`
    - `config_notice_embed(detail, note="")`
    - `scan_summary_embed(now_str, funnel, alert_count, gap_note="", priority=False)`
    - `deep_scan_embed(report, count)`
    - `retrospective_embeds(messages) -> list`
  - Text helpers:
    - `scan_gap_note(funnel) -> str`
    - `has_priority(alerts) -> bool`
    - `healthcheck_text(now_str, funnel, open_count, confirmation_scans) -> str`
    - `chunk_text(text, limit=RETRO_CHUNK) -> list[str]`
  - `async send_guarded(channel, embed, *, what) -> message | None`

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_system_notices.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/commands/test_system_notices.py`
Expected: FAIL — `ImportError: cannot import name 'notices'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/commands/scanning/notices.py`:

```python
"""v110 §5-§6: SYSTEM notices as registry-styled embeds, and the guarded send.

The builders are pure (no bot import), so they are testable alone; loops.py and
recap.py only resolve channels and send. send_guarded is the one place an
unprompted push swallows its own failure: it is logged with its traceback,
never raised, so one bad send cannot abort a batch or a startup.
"""
import logging

from swingbot.core import presentation as ui
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

log = logging.getLogger("swing-bot")

#: The old 2000-char message chunk size. Each chunk is now an embed
#: description (4096 limit), so the same split still fits.
RETRO_CHUNK = 1990
HEALTHCHECK_BADGE = kinds.badge(Kind.HEALTHCHECK)

_FAIL_LABELS = (
    ("failed_min_confluence", "below min strategies"),
    ("failed_min_confidence", "below min confidence"),
    ("rs_blocked", "blocked by RS gate"),
)


def system_embed(kind: Kind, detail: str = "", description: str | None = None):
    """A SYSTEM PushEmbed: registry title, push line, stripe and footer."""
    embed = ui.push_embed(kind, "", None, detail, description=description)
    ui.apply_chrome(embed, kind=kind)
    return embed


async def send_guarded(channel, embed, *, what: str):
    """Send one pushed embed; a failure is logged with exc_info and swallowed."""
    try:
        return await channel.send(**ui.push_kwargs(embed))
    except Exception:
        log.warning("Could not post %s -- continuing", what, exc_info=True)
        return None


def health_alert_embed(failures: int, last_success: str, exc: Exception):
    return system_embed(Kind.HEALTH_ALERT, f"{failures} failed tick(s) in a row", (
        f"• Last successful tick: {last_success}\n"
        f"• Latest error: `{type(exc).__name__}: {str(exc)[:400]}`\n"
        "No alerts are being produced until this clears."))


def health_recovered_embed():
    return system_embed(Kind.HEALTH_RECOVERED, "scan tick healthy again",
                        "The scan tick completed successfully again.")


def bot_online_embed(*, now_text: str, session_start: int, session_end: int, interval: int,
                     watchlist_size: int, open_count: int, min_level: int):
    return system_embed(Kind.BOT_ONLINE, now_text, (
        f"Session: {session_start:02d}:00–{session_end:02d}:00 Berlin · "
        f"scan every {interval} min\n"
        f"Watchlist: {watchlist_size} ticker(s) · open trades: {open_count} · "
        f"min confidence: Lv{min_level}"))


def config_notice_embed(detail: str, note: str = ""):
    return system_embed(Kind.CONFIG_CHANGE, detail, note or None)


def scan_gap_note(funnel: dict) -> str:
    """Why "qualifying" and "alerts posted" can differ: merged duplicates and
    tickers that already have an open trade."""
    parts = []
    qualifying = funnel.get("fully_qualifying", 0)
    merged = max(0, qualifying - funnel.get("deduped", qualifying))
    if merged:
        parts.append(f"{merged} merged as duplicate setup(s)")
    if funnel.get("skipped_already_open", 0):
        parts.append(f"{funnel['skipped_already_open']} already open")
    return f" ({', '.join(parts)})" if parts else ""


def has_priority(alerts: list) -> bool:
    """True when any posted alert's title carries the ⭐ priority mark."""
    return any("⭐" in (getattr(alert[0], "title", None) or "") for alert in alerts)


def scan_summary_embed(now_str: str, funnel: dict, alert_count: int,
                       gap_note: str = "", priority: bool = False):
    detail = f"{now_str} · {alert_count} new alert(s)" + (" ✨" if priority else "")
    return system_embed(Kind.SCAN_SUMMARY, detail, (
        f"📡 {funnel['tickers']} tickers, {funnel['checked']} combos checked\n"
        f"🧮 {funnel['scenarios_found']} scenario(s) found "
        f"(✔ {funnel['fully_qualifying']} qualifying)\n"
        f"**{alert_count} new alert(s) posted above**{gap_note}"))


def _fail_bits(funnel: dict) -> list[str]:
    return [f"{funnel[key]} {label}" for key, label in _FAIL_LABELS if funnel.get(key, 0)]


def healthcheck_text(now_str: str, funnel: dict | None, open_count: int,
                     confirmation_scans: int) -> str:
    """The per-tick healthcheck: a plain, silent text line (v110 §5), 🩺-prefixed.

    "qualifying" = passed every hard requirement; "awaiting confirmation" is
    a SUBSET of it (passed, but not yet seen SIGNAL_CONFIRMATION_SCANS scans in
    a row). The failure tallies are not a partition -- one scenario can fail
    more than one requirement, so they can sum past the scenario count."""
    if not funnel:
        return (f"{HEALTHCHECK_BADGE} **Healthcheck** ({now_str}) — scan complete, nothing new\n"
                f"• 📂 {open_count} open trade(s)")
    awaiting = funnel.get("awaiting_confirmation", 0)
    confirm_note = (f" (needs to reappear {confirmation_scans} scan(s) in a row before it posts)"
                    if awaiting else "")
    bullets = [
        f"📡 {funnel['tickers']} tickers scanned",
        f"🧮 {funnel['scenarios_found']} scenario(s) found",
        (f"✔ {funnel['fully_qualifying']} fully qualifying "
         f"(⏳ {awaiting} still awaiting confirmation{confirm_note})"),
    ]
    fail_bits = _fail_bits(funnel)
    if fail_bits:
        bullets.append(f"✖ failed a requirement: {', '.join(fail_bits)}")
    bullets.append(f"📂 {open_count} open trade(s)")
    return (f"{HEALTHCHECK_BADGE} **Healthcheck** ({now_str}) — nothing new this tick\n"
            + "\n".join(f"• {bullet}" for bullet in bullets))


def deep_scan_embed(report: str, count: int):
    return system_embed(Kind.DEEP_SCAN, f"{count} candidate(s)", report)


def chunk_text(text: str, limit: int = RETRO_CHUNK) -> list[str]:
    """Split at the last newline before ``limit`` (hard at ``limit`` when a
    line is longer), exactly as the pre-v110 retrospective loop did; blank
    chunks are dropped."""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    return [chunk for chunk in chunks if chunk.strip()]


def retrospective_embeds(messages: list[str]) -> list:
    """One RETROSPECTIVE embed per chunk, numbered ``i/n`` when there is more than one."""
    chunks = [chunk for message in messages for chunk in chunk_text(message)]
    total = len(chunks)
    return [system_embed(Kind.RETROSPECTIVE, f"{index}/{total}" if total > 1 else "", chunk)
            for index, chunk in enumerate(chunks, 1)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/commands/test_system_notices.py tests/presentation/test_no_adhoc_color.py tests/commands/test_scanning_package.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/notices.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/notices.py tests/commands/test_system_notices.py
git commit -m "feat(v110): SYSTEM notice builders, healthcheck line, retrospective chunking and guarded send

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/notices.py tests/commands/test_system_notices.py
```

---

### Task V110-11: `loops.py` — health, scan summary, healthcheck, config notices, bot online

**Files:**
- Modify: `swingbot/commands/scanning/loops.py`:
  - imports
  - `_maybe_escalate_health` and `_post_health_recovered`
  - `_session_scan_tick` (summary block, healthcheck block)
  - `config_watcher` (the notice block)
  - `on_ready` (the startup notice)
  - new `_CONFIG_NOTICES`, `_post_config_notices` and `_post_bot_online`
- Test: `tests/scanning/test_heartbeat_outcome.py`, `tests/commands/test_loops_notices.py` (new)

**Interfaces:**
- Consumes: V110-10's `notices.*` and V110-3's `ui.push_kwargs`.
- Produces:
  - `loops._post_config_notices(changed: dict) -> None` (async)
  - `loops._post_bot_online(wl_size: int) -> None` (async, guarded)

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_loops_notices.py`:

```python
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
```

In `tests/scanning/test_heartbeat_outcome.py`, change `_FakeChannel.send` to:

```python
    async def send(self, content=None, **kw):
        self.sent.append({"content": content, **kw})
```

In `test_escalates_once_at_the_threshold_then_stays_quiet`, replace the two assertions `assert "3" in channel.sent[0]` and `assert "RuntimeError" in channel.sent[0]` with:

```python
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "3" in channel.sent[0]["embed"].title
    assert "RuntimeError" in channel.sent[0]["embed"].description
```

In `test_recovery_posts_exactly_one_notice`, replace `assert "recover" in channel.sent[1].lower()` with:

```python
    assert channel.sent[1]["content"].startswith("✅ SYSTEM · RECOVERED")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_notices.py tests/scanning/test_heartbeat_outcome.py`
Expected: FAIL. `_post_config_notices` / `_post_bot_online` do not exist, and the health posts are plain text, so `channel.sent[0]["embed"]` raises `KeyError`.

- [ ] **Step 3: Write the implementation**

In `swingbot/commands/scanning/loops.py`, change `from . import presence, recap, runstate` to `from . import notices, presence, recap, runstate`, and add `from swingbot.core import presentation as ui` below `from swingbot.core.infra.jsonio import atomic_write_json, read_json`.

**Health.** In `_maybe_escalate_health`, replace the `await channel.send(...)` call (the multi-line f-string beginning `f"🚨 **Bot health alert**`) with:

```python
    # Unguarded on purpose: a failed send must leave the alert inactive so the
    # next failing tick retries it (session_scan logs the exception).
    await channel.send(**ui.push_kwargs(notices.health_alert_embed(failures, last, exc)))
```

In `_post_health_recovered`, replace `await channel.send("✅ **Bot health recovered** — the scan tick completed successfully again.")` with:

```python
    await channel.send(**ui.push_kwargs(notices.health_recovered_embed()))
```

**Scan summary.** In `_session_scan_tick`, inside `if alerts:` → `if f:`, replace everything from the comment line `# "qualifying" and "alerts posted" can legitimately differ:` through `await channel.send(summary)` with:

```python
            # v110 §5: a SYSTEM embed. "qualifying" and "alerts posted" can
            # legitimately differ (merged duplicates, already-open tickers);
            # scan_gap_note spells that out. ✨ = a ⭐ priority setup posted.
            summary = notices.scan_summary_embed(
                now_str, f, len(alerts), notices.scan_gap_note(f), notices.has_priority(alerts))
            await channel.send(**ui.push_kwargs(summary))
```

**Healthcheck.** In the `else:` branch, keep the `# Healthcheck post -- one short message every scan tick …` comment block. Replace everything from the `open_count = trade_log.get_stats()["open"]` line directly below that comment through `await presence._post_healthcheck(channel, healthcheck)` with:

```python
        open_count = trade_log.get_stats()["open"]
        healthcheck = notices.healthcheck_text(now_str, f, open_count,
                                               config.SIGNAL_CONFIRMATION_SCANS)
        await presence._post_healthcheck(channel, healthcheck)
```

**Config notices.** Directly above `@tasks.loop(seconds=30)` / `async def config_watcher`, add:

```python
#: Settings whose hot-reload is announced in Discord -> (detail, note) for the
#: CONFIG embed (v110 §5).
_CONFIG_NOTICES = {
    "MIN_ALERT_CONFIDENCE_LEVEL": lambda old, new: (
        f"Min confidence level Lv{old} → Lv{new}",
        f"Next `!check` and scheduled scans will use Lv{new}+."),
    "MIN_TARGET_CONFLUENCE_COUNT": lambda old, new: (
        f"Min strategies confirmed {old} → {new}", ""),
    "SCAN_INTERVAL_MINUTES": lambda old, new: (
        f"Scan interval every {old} min → every {new} min", ""),
    "MIN_RISK_REWARD_RATIO": lambda old, new: (f"Min R:R ratio {old} → {new}", ""),
}


async def _post_config_notices(changed: dict) -> None:
    """One CONFIG embed per announced key that changed; each send guarded."""
    if not config.DISCORD_CHANNEL_TRADES_ID:
        return
    channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
    if not channel:
        return
    for key, describe in _CONFIG_NOTICES.items():
        if key in changed:
            detail, note = describe(*changed[key])
            await notices.send_guarded(channel, notices.config_notice_embed(detail, note),
                                       what=f"config-change notice for {key}")
```

In `config_watcher`, replace everything from the comment `# Notify Discord channel about key setting changes so the user can` through the line `log.warning("Could not post config-change notice to Discord: %s", _e)` (the whole `_notify_keys` dict and its send loop) with:

```python
        # Notify Discord about key setting changes (v110: CONFIG embeds).
        await _post_config_notices(changed)
```

**Bot online.** Directly above `@bot.event` / `async def on_ready`, add:

```python
async def _post_bot_online(wl_size: int) -> None:
    """Startup notice (v110 §5): a SYSTEM embed, send guarded (§6.3)."""
    if not config.DISCORD_CHANNEL_TRADES_ID:
        return
    channel = silence(bot.get_channel(int(config.DISCORD_CHANNEL_TRADES_ID)))
    if not channel:
        return
    embed = notices.bot_online_embed(
        now_text=dt.datetime.now(SESSION_TZ).strftime("%Y-%m-%d %H:%M %Z"),
        session_start=config.SESSION_START_HOUR, session_end=config.SESSION_END_HOUR,
        interval=config.SCAN_INTERVAL_MINUTES, watchlist_size=wl_size,
        open_count=trade_log.get_stats()["open"],
        min_level=config.MIN_ALERT_CONFIDENCE_LEVEL)
    await notices.send_guarded(channel, embed, what="bot-online notice")
```

At the end of `on_ready`, replace everything from the comment `# Post a startup notice to the alerts channel so there's a visible` to the end of the function (the `if config.DISCORD_CHANNEL_TRADES_ID:` block and its `await channel.send(...)`) with:

```python
    # A visible timestamp in Discord for when the bot came (back) online.
    await _post_bot_online(wl_size)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_loops_notices.py tests/scanning/test_heartbeat_outcome.py tests/infra/test_silent_alerts_channel.py tests/commands/test_config_watcher_task.py tests/commands/test_scanning_package.py tests/test_config_reload.py tests/test_scheduled_jobs.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/loops.py`
Expected:
- `_session_scan_tick` below 30.
- `config_watcher` below 27.
- `on_ready` below 17.
- `trade_monitor` (16) and `market_data_refresh` (14) unchanged.
- `_post_config_notices` and `_post_bot_online` absent.

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/loops.py tests/commands/test_loops_notices.py tests/scanning/test_heartbeat_outcome.py
git commit -m "feat(v110): health, scan summary, config and bot-online notices as SYSTEM embeds; 🩺 healthcheck line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/loops.py tests/commands/test_loops_notices.py tests/scanning/test_heartbeat_outcome.py
```

---

### Task V110-12: `recap.py` — retrospective embeds (guarded) and the deep-scan SYSTEM embed

**Files:**
- Modify: `swingbot/commands/scanning/recap.py` (imports, the tail of `_post_retrospective`, the tail of `weekend_deep_scan`)
- Test: `tests/commands/test_recap_notices.py` (new)

**Interfaces:**
- Consumes:
  - V110-10: `notices.retrospective_embeds`, `notices.send_guarded` and `notices.deep_scan_embed`.
  - V110-9: `deep_scan_report`, now without its header.
  - V110-3: `ui.push_kwargs`.
- Produces: no new names. `weekend_deep_scan()` still returns the report string.

- [ ] **Step 1: Write the failing test**

Create `tests/commands/test_recap_notices.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/commands/test_recap_notices.py`
Expected: FAIL. The first chunk's `RuntimeError` escapes `_post_retrospective`, and the deep scan posts a plain string, so `sent["embed"]` raises `KeyError`.

- [ ] **Step 3: Write the implementation**

In `swingbot/commands/scanning/recap.py`, add these imports below `from swingbot.core.scanning import engine as scan_engine`:

```python
from swingbot.core import presentation as ui
from . import notices
```

In `_post_retrospective`, replace everything from `    for msg in messages:` to the end of the function with:

```python
    # v110 §5/§6.3: one SYSTEM embed per chunk (chunks still sized for the
    # old 2000-char limit, well inside an embed's 4096), each send guarded
    # so one failed chunk never drops the rest of the recap.
    for embed in notices.retrospective_embeds(messages):
        await notices.send_guarded(channel, embed, what="retrospective chunk")
```

In `weekend_deep_scan`, replace:

```python
    if channel is not None:
        await channel.send(report)
    return report
```

with:

```python
    if channel is not None:
        # v110 §5: the 🔭 header is the SYSTEM embed's title; the body is the report.
        await channel.send(**ui.push_kwargs(notices.deep_scan_embed(report, len(items))))
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/commands/test_recap_notices.py tests/test_config_reload.py tests/test_scheduled_jobs.py tests/commands/test_scanning_package.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/commands/scanning/recap.py`
Expected: no output (`_post_retrospective` drops from 7).

- [ ] **Step 6: Commit**

```bash
git add swingbot/commands/scanning/recap.py tests/commands/test_recap_notices.py
git commit -m "fix(v110): guarded retrospective embeds per chunk; weekend deep scan as a SYSTEM embed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/commands/scanning/recap.py tests/commands/test_recap_notices.py
```

---

# Phase D — Docs, verification, release

### Task V110-13: Refresh the stale embed notes (spec §6.4)

**Files:**
- Modify: `docs/claude/known-traps.md` (the "Sizing and embed-building" and "Add embed fields" bullets, and the `scan_snapshots.json` location)
- Modify: `docs/claude/architecture.md` (the `presentation/` sentence)

**Interfaces:**
- Consumes: the names from V110-3 (`PushEmbed`, `push_kwargs`) and the module locations verified in Step 1.
- Produces: docs only.

- [ ] **Step 1: Verify every location before writing it**

Run:

```bash
git grep -n "def _sync_run_scan\|build_simple_alert(item)" -- swingbot/core/scanning/scan_run.py
git grep -n "^SECTION_ORDER" -- swingbot/core/presentation/tokens.py
git grep -n "def build_embed" -- swingbot/core/scanning/alert_embeds.py
git grep -n 'open(_SNAPSHOT_PATH, "w")' -- swingbot/core/scanning/snapshots.py
git grep -n "def _sizing_snapshot" -- swingbot/core/scanning/plan_table.py
```

Expected: all five match. Use the `snapshots.py` line number printed here in Step 2, rather than the `22` measured on 2026-09-28, if the two differ.

- [ ] **Step 2: Edit `docs/claude/known-traps.md`**

Replace:

```
- **Sizing and embed-building happen in `core/scanning/engine.py`'s
  alert-building loop**, right before `build_embed()` — *not* in
  `commands/scanning.py::_send_alerts`, which only posts already-built
  tuples. Wiring sizing there is a silent no-op.
- **Add embed fields through the `sections["headline"]` accumulator** in
  `embeds.py`, never a raw `embed.add_field()` — the latter breaks
  `embed_theme.SECTION_ORDER`.
```

with:

```
- **Sizing and embed-building happen in `core/scanning/scan_run.py`'s
  alert-building loop** (inside `_sync_run_scan`: the heat / cluster /
  kill-switch stamps, then `build_embed()` and `build_simple_alert()`) —
  *not* in `commands/scanning/alerts.py::_send_alerts`, which only posts
  already-built tuples. Wiring sizing there is a silent no-op. The v2
  ticket's share count comes from `plan_table._sizing_snapshot`, called by
  `execution_embeds.build_ticket_embed`.
- **Add embed fields through the `sections[...]` accumulator** in
  `core/scanning/alert_embeds.py::build_embed`, never a raw
  `embed.add_field()` — the latter breaks `presentation.SECTION_ORDER`
  (`core/presentation/tokens.py`).
- **Every pushed message is styled by `core/presentation/kinds.py` (v110)
  and built as a `PushEmbed`.** Send it with
  `channel.send(**ui.push_kwargs(embed))`. A bare `send(embed=embed)` still
  posts, but silently drops the push-preview `content` line, which is the only
  text a phone notification shows. Command replies call
  `apply_chrome(accent=…)` and are deliberately not registry-styled.
```

In the plain-`open(path, "w")` list, change `` `scan_snapshots.json` (`core/scanning/embeds.py:58`) `` to `` `scan_snapshots.json` (`core/scanning/snapshots.py:22`) ``, using the line number from Step 1.

- [ ] **Step 3: Edit `docs/claude/architecture.md`**

Replace:

```
Discord colour, glyph, number format and embed part: pure `tokens.py`,
  phone-safe `ansi.py`, then whole embed parts in `components.py`. Nothing
```

with:

```
Discord colour, glyph, number format and embed part: pure `tokens.py`,
  the v110 notification registry `kinds.py` (six families, one `Kind` per
  pushed event, the stripe ramps — the only styling path for pushed
  messages), phone-safe `ansi.py`, then whole embed parts in `components.py`
  (including `PushEmbed`, whose push line every sender passes as `content`). Nothing
```

- [ ] **Step 4: Verify the Codex mirror**

`AGENTS.md` only condenses these docs ("known-traps.md before changing … embeds"), and that line is still true, so it needs no edit.

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: PASS. If it fails, run `python scripts/dev/sync_codex.py`, fix `AGENTS.md` as it says, and include `AGENTS.md` in the commit below.

- [ ] **Step 5: Commit**

```bash
git add docs/claude/known-traps.md docs/claude/architecture.md
git commit -m "docs(v110): refresh stale embed notes -- scan_run alert loop, alert_embeds accumulator, snapshots.py, PushEmbed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/claude/known-traps.md docs/claude/architecture.md
```

---

### Task V110-14: Full-suite verification, complexity sweep and the rendered before/after

**Files:** none, apart from a fix-forward that touches whatever the failures name. Scratch files go to the session scratchpad.

**Interfaces:**
- Consumes: V110-1..V110-13 committed on the worktree branch.
- Produces: a green branch, the complexity table, and the `alert-surface` rendered-diff evidence.

- [ ] **Step 1: The one full-suite run**

Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full` in the worktree. Require `0 failed` and `0 xfailed`. A changed pass count is not a failure. A red result is this plan's regressions, so fix forward from the failures it names. If a failure passes in isolation and sits in code this plan never touched, report it with both outputs and do not call the suite green.

- [ ] **Step 2: Complexity sweep over everything the plan touched**

Run:

```bash
python -m radon cc -s -n C swingbot/core/presentation/kinds.py swingbot/core/presentation/ansi.py swingbot/core/presentation/components.py swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/execution_embeds.py swingbot/core/scanning/lifecycle_embeds.py swingbot/core/scanning/strategy_pass.py swingbot/commands/scanning/alerts.py swingbot/commands/scanning/notices.py swingbot/commands/scanning/loops.py swingbot/commands/scanning/recap.py swingbot/commands/trades.py
```

Expected:
- Only the legacy functions appear, each strictly below its baseline:
  - `build_embed` < 41, `build_closed_trade_embed` < 20
  - `_session_scan_tick` < 30, `config_watcher` < 27, `on_ready` < 17
  - `summary_cmd` < 54, `_build_trade_detail_embed` < 17
- These appear unchanged: `trade_monitor` 16, `format_trade_row` 16, `market_data_refresh` 14, `regenerate_chart_for_trade` 12, `notify_plan_events` 12, `performance_cmd` 12.
- `_send_alerts` no longer appears.

Any other function at 15 or more is a regression to split before V110-15.

- [ ] **Step 3: Syntax pass**

Run: `python -m py_compile bot.py admin_ui.py swingbot/core/presentation/kinds.py swingbot/commands/scanning/notices.py swingbot/commands/scanning/loops.py swingbot/commands/scanning/recap.py swingbot/commands/scanning/alerts.py`
Expected: no output.

- [ ] **Step 4: The alert-surface gate — rendered before/after**

Write this script to `<scratchpad>/render_pushed.py`:

```python
"""v110 alert-surface gate: dump every pushed builder's rendered output."""
import json
import sys
import tempfile
from types import SimpleNamespace

root, out_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)

from swingbot import config  # noqa: E402
from swingbot.core.planning.plan_manager import PlanEvent  # noqa: E402
from swingbot.core.scanning import (alert_embeds, execution_embeds,  # noqa: E402
                                    lifecycle_embeds, snapshots)
from tests.planning.test_plan_engine_model import _plan  # noqa: E402
from tests.scanning.test_embeds_v3 import make_item, make_plan_v2  # noqa: E402

snapshots._SNAPSHOT_PATH = tempfile.mktemp(suffix=".json")   # never touch data/
execution_embeds._sizing_snapshot = lambda entry, plan: None
config.PLAN_ENGINE_V2 = "on"

TRADE = {"id": "t-1", "ticker": "NVDA", "status": "win", "entry": 100.0, "exit_price": 110.0,
         "stop_loss": 95.0, "take_profit": 110.0, "direction": "bullish",
         "strategy": "RSI Pullback", "horizon_key": "2w", "confidence_label": "High",
         "confidence_level": 4}
WARNING = {"trade": {**TRADE, "status": "open"}, "near_which": "stop-loss",
           "sl_dist_pct": 1.0, "tp_dist_pct": 9.0, "current_price": 96.0}
STRATEGY = SimpleNamespace(plan_id="0123456789ab", ticker="AAPL", strategy="Fibonacci",
                           direction="bearish", horizon_key="4w", trigger_price=100.0,
                           stop_loss=106.0, tp1=90.0, tp2=None, badge="VALIDATED",
                           ledger="main", confidence_level=5)
V2 = make_plan_v2()


def ticket():
    item = make_item(plan_v2=make_plan_v2())
    item.paper_logged = True
    return alert_embeds.build_simple_alert(item)


def legacy_simple():
    config.PLAN_ENGINE_V2 = "off"
    try:
        return alert_embeds.build_simple_alert(make_item())
    finally:
        config.PLAN_ENGINE_V2 = "on"


BUILDERS = {
    "full_alert": lambda: alert_embeds.build_embed(
        make_item(plan_v2=make_plan_v2()), "Explanation.", {"closed": 0}, None, None),
    "full_alert_blocked": lambda: alert_embeds.build_embed(
        make_item(all_ok=False), "Explanation.", {"closed": 0}, None, None),
    "legacy_simple": legacy_simple,
    "ticket": ticket,
    "strategy_signal": lambda: alert_embeds.build_strategy_alert_embed(STRATEGY),
    "feed_filled": lambda: execution_embeds.build_instruction_embed(
        V2, PlanEvent(V2.plan_id, "filled", {"entry_price": 100.0})),
    "feed_be": lambda: execution_embeds.build_instruction_embed(
        V2, PlanEvent(V2.plan_id, "be_moved", {"working_stop": 100.0})),
    "feed_exit": lambda: execution_embeds.build_instruction_embed(V2, PlanEvent(
        V2.plan_id, "closed", {"reason": "loss", "exit_price": 94.0, "session": "regular"})),
    "closed_trade": lambda: lifecycle_embeds.build_closed_trade_embed(TRADE),
    "near_close": lambda: lifecycle_embeds.build_near_close_embed(WARNING),
    "plan_event_win": lambda: lifecycle_embeds.build_plan_event_embed(
        _plan(entry_price=100.0), PlanEvent("p1", "closed", {"reason": "win", "exit_price": 111.0})),
}


def dump(embed):
    data = embed.to_dict()
    data.pop("timestamp", None)
    return {"content": getattr(embed, "push_text", None), **data}


out = {name: dump(build()) for name, build in BUILDERS.items()}
try:
    from swingbot.commands.scanning import notices
    out["system"] = {
        "health_alert": dump(notices.health_alert_embed(3, "never", RuntimeError("boom"))),
        "recovered": dump(notices.health_recovered_embed()),
        "scan_summary": dump(notices.scan_summary_embed(
            "10:05", {"tickers": 5, "checked": 40, "scenarios_found": 2,
                      "fully_qualifying": 1}, 1, "", True)),
        "healthcheck": notices.healthcheck_text("10:05", None, 2, 2),
    }
except ImportError:
    out["system"] = "absent before v110"
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
```

Run it once against `main` (the repository root, which is untouched by this branch) and once against the worktree:

```bash
python <scratchpad>/render_pushed.py E:/Documents/Private/Projects/Discord-Bot <scratchpad>/before.json
python <scratchpad>/render_pushed.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-09-28-v110-discord-notification-identity <scratchpad>/after.json
git diff --no-index --word-diff=plain <scratchpad>/before.json <scratchpad>/after.json > <scratchpad>/render.diff
```

Check `after.json` and report the result table (builder → title → content → footer → colour) to the controller:
- Every builder has a non-null `content` that starts with its title's badge.
- No `title` or `content` contains 🟢 or 🔴.
- Only the NEW SETUP builders (`full_alert*`, `legacy_simple`, `ticket`, `strategy_signal`) have the disclaimer footer.
- `closed_trade`, `feed_exit` and `plan_event_win` show the realised R in the ANSI block.

`render.diff` must show a change on every builder. A builder whose rendered output is identical before and after means a shim ate the change (`alert-surface`), so stop and investigate.

---

### Task V110-15: Merge and release `bot minor`

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`

**Interfaces:**
- Consumes: V110-14's green branch.
- Produces: the branch merged on `main`, the release commit and the regenerated history, pushed to `origin/main` (which triggers the image build and deploy).

- [ ] **Step 1: Merge**

Follow the `worktree-lifecycle` skill. Run `git fetch` and compare with `origin/main`, because another session may have committed. Then merge branch `2026-09-28-v110-discord-notification-identity` into `main`. If the merge resolved conflicts, run `python scripts/dev/testrun.py full` once on the result (the one exception in `document-conventions.md`). Otherwise do not re-run anything.

- [ ] **Step 2: Bump — read `VERSION.json` from disk**

Read `VERSION.json` now: never this plan, the spec's `Version:` line, or memory. Increment `bot` at the **minor** level (reset its patch to 0), leave `ui` and `ui_updated` untouched, and set `bot_updated` to the current UTC time in `YYYY-MM-DD HH-MM-SS` format.

```bash
git add VERSION.json
git commit -m "release(bot): <new bot version> -- distinct, colourful Discord notifications (one registry of kinds)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- VERSION.json
```

- [ ] **Step 3: Regenerate the version history (after the bump commit)**

Run: `python scripts/dev/build_version_matrix.py`
Check: `git diff swingbot/admin/version_history.json` shows the new bot pair as `current`, with a real commit (not `"uncommitted"`).
Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS.

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): <new bot version> -- distinct, colourful Discord notifications (one registry of kinds)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/admin/version_history.json
```

- [ ] **Step 4: Push**

Run `git fetch` and confirm that `main` is ahead of `origin/main` only by this plan's commits. Then run `git push origin main`. The GitHub Actions deploy runs on the push.

---

### Task V110-16: Production verification and close-out

This is an operator task, run by the controller. Production reads go through the `prod-inspector` agent, which is read-only. Nothing on the VM is edited. If anything there has to change, the `mirror-prod` rule applies.

**Files:**
- Move: `docs/superpowers/specs/2026-09-28-v110-discord-notification-identity-design.md` → `docs/superpowers/specs/implemented/`
- Move: the four plan parts `…_0-index.md`, `…_1-registry.md`, `…_2-builders.md` and `…_3-senders-release.md` → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: V110-15's deployed image.
- Produces: the acceptance criteria checked on production, and the documents closed.

- [ ] **Step 1: Confirm the deploy (prod-inspector, read-only)**

Confirm that:
- the bot container runs the image built from V110-15's push;
- the bot logs the new version at start;
- `/opt/swing-bot/logs/bot.log` has no `Could not post bot-online notice` line after that start.

- [ ] **Step 2: The acceptance checks**

1. **Strategy mirror (spec acceptance 3).** After the first strategy alert since the deploy, `bot.log` has **no** `Could not post simple alert` warning for it. Grep `bot.log*` from the deploy time and report the count (expected 0).
2. **Batch isolation.** Report any `Could not post alert for` line with its traceback. It shows the guard working, and the traceback says why the send failed.
3. **Push previews and channel look (spec acceptance 1 and 2).** Ask the partner for one phone push screenshot and one channel screenshot, covering at least one NEW SETUP, one RESULT and one SYSTEM message. Each kind should be identifiable from the preview alone, and again from stripe plus badge. Record the answer. A kind that is not identifiable is a follow-up spec, not a hotfix.

- [ ] **Step 3: Close out the documents**

```bash
git mv docs/superpowers/specs/2026-09-28-v110-discord-notification-identity-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_0-index.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_1-registry.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_2-builders.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_3-senders-release.md docs/superpowers/plans/implemented/
```

Fix the `**Spec:**` link in the moved `_0-index` to `../../specs/implemented/2026-09-28-v110-discord-notification-identity-design.md`. Check it with `ls docs/superpowers/specs/implemented/2026-09-28-v110-discord-notification-identity-design.md`. If the shipped impact differed from `Bump: bot minor` / `Edge: none (integrity)`, amend the spec's line with one clause saying why.

```bash
git add docs/superpowers/specs/implemented/2026-09-28-v110-discord-notification-identity-design.md docs/superpowers/plans/implemented/2026-09-28-v110-discord-notification-identity_*.md
git commit -m "docs(v110): close out -- notification kinds live on production

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/specs/2026-09-28-v110-discord-notification-identity-design.md docs/superpowers/specs/implemented/2026-09-28-v110-discord-notification-identity-design.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_0-index.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_1-registry.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_2-builders.md docs/superpowers/plans/2026-09-28-v110-discord-notification-identity_3-senders-release.md docs/superpowers/plans/implemented/2026-09-28-v110-discord-notification-identity_0-index.md docs/superpowers/plans/implemented/2026-09-28-v110-discord-notification-identity_1-registry.md docs/superpowers/plans/implemented/2026-09-28-v110-discord-notification-identity_2-builders.md docs/superpowers/plans/implemented/2026-09-28-v110-discord-notification-identity_3-senders-release.md
git push origin main
```

- [ ] **Step 4: Remove the worktree**

Remove `.claude/worktrees/2026-09-28-v110-discord-notification-identity` per `worktree-lifecycle`. Before deleting the branch, run `git rev-list --count main..2026-09-28-v110-discord-notification-identity`: it must print `0`. Otherwise **stop** and ask. Never touch a branch with `backup` in its name or any `stable-*` branch (`docs/claude/git-safety.md`).
