# v210 — Market-shock notices and admin badge, part 1: notices and the tape API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (§ Units → *Discord notices*, *Admin*; § Track 1 tests → *Notice formatting*, *Frontend*)
**Index:** [`_0-index.md`](2026-11-06-v210-market-shock-notices-and-badge_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` §3.8 (queue), §3.9–3.10 (tape), §4 (test patterns), D1.

**Prerequisite: plan v209 merged.** Every `V209-*` id below names a task of
plan v209 (the detector, its tables, repository and `shock_scan.py` pass),
already merged on `main` before this plan's worktree is cut; this plan only
consumes their contracts.

Tasks: V210-1 (the pure `shock_notices` renderer), V210-1b (the
`market_shock` queue kind: validator and delivery dispatch), V210-2 (pure
payload helpers: open longs, rate limit, queue event), V210-2b (the
stepped-pass hook that enqueues the notice), V210-3 (the admin tape's `shock`
object). V210-1b, V210-2b and V210-3b are splits at the 20 KB task cap;
V210-3b (the SPA badge) sits in `_2-admin-badge.md` because this file would
otherwise pass 1500 lines. Order: V210-1 needs only v209's `shock` types;
V210-1b needs V210-1; V210-2 needs V210-1b; V210-2b needs V210-2 and v209's
V209-5b and V209-6a; V210-3 needs only v209 and may run beside V210-1..2b;
V210-3b needs V210-3.

**Decisions made here (inside the ledger's contracts):**

- **No new `Kind`.** `shock_notices.build_shock_embed` builds a
  `ui.PushEmbed` directly (title = the headline, `push_text` = the headline,
  stripe by label from the existing `kinds.HEALTH_RED` /
  `kinds.WATCH_STOP_ORANGE` / `kinds.HEALTH_GREEN` constants), so
  `presentation/kinds.py` and its table-driven tests are untouched and the
  notice can never carry the alert disclaimer.
- **The body ends with the footer copy.** On an entry into SHOCK (from
  NORMAL or a RECOVERY → SHOCK second leg) the description lists the open
  longs and its last line is `shock_notices.FOOTER`; the embed's own footer is
  `Event <event_id>`, as for the two lifecycle kinds.
- **Discord's 4096-character description cap:** open-long lines stop at a
  3,500-character budget and the rest collapse into `+<n> more open longs`.
- **Open longs unreadable:** when the trade log cannot be read, the payload
  carries `open_longs: []` plus `open_longs_unavailable: true` and the notice
  says so instead of the misleading `No open longs.`
- **A notice that cannot be built never costs the reading:** V210-2b swallows
  a notice-building failure (`scan.shock.notice`) and records the reading and
  state without a `notice_event`. A failing *enqueue* inside `record()` still
  rolls the whole pass back (v209 Review Focus 5, pinned in V209-5b, v209 (merged)).
- **Phone width:** the shell hides the whole tape strip below 640 px
  (`shell.css` `.tape-strip { display: none; }`), so the badge, which sits in
  the tape component, is not shown on phones; at 640–1023 px it wraps onto
  its own line under the tape, at ≥ 1024 px it sits to the tape's right
  (V210-3b). Flagged for the partner in the index's OPEN item, not decided here.

---

# Phase 1 — notices

### Task V210-1: `shock_notices.py` renderer — the `market_shock` status embed

**Model:** sonnet — pure formatting against fully pinned copy; no queue, database or Discord I/O in this half.

First half of the ledger's V210-1 (split at the 20 KB task cap). This task
builds the pure renderer; V210-1b registers the kind in the queue validator
and dispatches to this renderer from the delivery path.

**Files:**
- Create: `swingbot/core/scanning/shock_notices.py` (renderer half)
- Create: `tests/scanning/test_shock_notice_render.py` (suite `scanning`)

**Interfaces:**
- Consumes: `swingbot.core.market.shock.NORMAL`, `SHOCK`, `RECOVERY`, `ShockReading(...).as_row()` (V209-2, v209 (merged)); existing `ui.PushEmbed` (`swingbot/core/presentation/components.py`), `kinds.HEALTH_RED`, `kinds.WATCH_STOP_ORANGE`, `kinds.HEALTH_GREEN`, `tokens.DISCLAIMER`.
- Produces (V210-1b and V210-2 rely on these exactly):
  - `shock_notices.FOOTER: str` (exact copy in Global Constraints), `THROUGH_STOP = "THROUGH STOP"`, `NO_LONGS = "No open longs."`, `LONGS_UNAVAILABLE`.
  - `long_line(row: dict) -> str` for `row = {"ticker", "entry", "stop", "last" (float | None), "open_r" (float | None), "age_min" (int), "through_stop" (bool)}`.
  - `numbers_line(reading: dict) -> str`; `headline(payload: dict) -> str`.
  - `build_shock_embed(event: dict) -> discord.Embed` — a `ui.PushEmbed`; reads `event["event_id"]` and `event["payload"]` = `{"label", "prior_label", "occurred_at", "reading", "open_longs", "entry_into_shock", "open_longs_unavailable"?}` (the shape V210-1b validates).

The tests build event dicts by hand (`{"event_id": ..., "payload": ...}`), so
this task does not depend on V210-1b's validator.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_shock_notice_render.py`:

```python
"""v210: shock_notices renderer -- the market_shock embed and its copy."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.presentation import kinds, tokens
from swingbot.core.scanning import shock_notices

AT = "2026-11-05T14:45:00+00:00"
FOOTER = ("The bot moved no stop and closed nothing. "
          "Stop move-up and long block are pending screen (v209 Track 2).")


def reading_row(**over):
    fields = dict(as_of=datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc),
                  session_date=date(2026, 11, 5), minutes_since_open=75.0, breadth_frac=0.42,
                  sectors_down=5, sectors_total=8, breadth_speed=0.12, spy_atr_move=-1.8,
                  qqq_atr_move=-2.3, spy_last=671.2, spy_prev_close=683.0,
                  spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05, vix_level=21.13,
                  vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3, n_names=61,
                  insufficient=False) | over
    return shock.ShockReading(**fields).as_row()


def long_row(ticker="MU", **over):
    return dict(ticker=ticker, entry=100.0, stop=95.0, last=97.5, open_r=-0.5, age_min=125,
                through_stop=False) | over


def shock_event(label="SHOCK", prior="NORMAL", longs=(), **over):
    payload = dict(label=label, prior_label=prior, occurred_at=AT, reading=reading_row(),
                   open_longs=list(longs), entry_into_shock=label == "SHOCK") | over
    return {"event_id": "evt-1", "kind": "market_shock", "payload": payload}


def test_footer_is_the_exact_spec_copy():
    assert shock_notices.FOOTER == FOOTER


@pytest.mark.parametrize("over,line", [
    ({}, "MU · entry 100.00 · stop 95.00 · last 97.50 · -0.50R · 2h05m · "
         "stop at broker untouched: 95.00"),
    ({"last": 94.0, "open_r": -1.2, "age_min": 45, "through_stop": True},
     "MU · entry 100.00 · stop 95.00 · last 94.00 · -1.20R · 45m · THROUGH STOP"),
    ({"last": None, "open_r": None, "age_min": 0},
     "MU · entry 100.00 · stop 95.00 · last n/a · n/a R · 0m · stop status unknown: 95.00"),
    ({"last": 101.5, "open_r": 0.3, "age_min": 3005},
     "MU · entry 100.00 · stop 95.00 · last 101.50 · +0.30R · 50h05m · "
     "stop at broker untouched: 95.00"),
])
def test_long_line(over, line):
    assert shock_notices.long_line(long_row(**over)) == line


def test_headline_and_numbers_line():
    embed = shock_notices.build_shock_embed(shock_event())
    assert embed.title == "Market state: NORMAL → SHOCK" == embed.push_text
    assert embed.description.splitlines()[0] == (
        "breadth 42% · sectors 5/8 · speed +12pp · SPY -1.80 ATR · QQQ -2.30 ATR · "
        "VIX 21.13 (+27.2%)")


def test_missing_numbers_read_n_a():
    row = reading_row(breadth_frac=None, sectors_down=0, sectors_total=0, breadth_speed=None,
                      spy_atr_move=None, qqq_atr_move=None, vix_level=None, vix_chg_pct=None)
    assert shock_notices.numbers_line(row) == (
        "breadth n/a · sectors 0/0 · speed n/a · SPY n/a · QQQ n/a · VIX n/a")
    assert shock_notices.numbers_line(reading_row(vix_chg_pct=None)).endswith("VIX 21.13 (n/a)")


def test_entry_with_zero_open_longs_says_so_and_ends_with_the_footer():
    text = shock_notices.build_shock_embed(shock_event()).description
    assert "No open longs." in text and text.endswith(FOOTER)


def test_entry_lists_every_open_long_in_payload_order():
    longs = [long_row("MU"), long_row("STX", last=94.0, open_r=-1.2, through_stop=True)]
    lines = shock_notices.build_shock_embed(shock_event(longs=longs)).description.splitlines()
    assert "Open longs (2):" in lines
    assert lines.index(shock_notices.long_line(longs[0])) < lines.index(
        shock_notices.long_line(longs[1]))
    assert any(line.endswith("THROUGH STOP") for line in lines)
    assert "No open longs." not in lines and lines[-1] == FOOTER


def test_a_second_leg_lists_longs_and_the_footer_too():
    text = shock_notices.build_shock_embed(
        shock_event(prior="RECOVERY", longs=[long_row()])).description
    assert "Open longs (1):" in text and text.endswith(FOOTER)


def test_many_open_longs_stay_inside_discords_description_cap():
    longs = [long_row(f"T{i:03d}") for i in range(120)]
    text = shock_notices.build_shock_embed(shock_event(longs=longs)).description
    assert len(text) <= 4096 and "more open longs" in text and text.endswith(FOOTER)
    assert "Open longs (120):" in text


def test_unreadable_open_longs_are_named_not_hidden():
    text = shock_notices.build_shock_embed(
        shock_event(open_longs_unavailable=True)).description
    assert "Open longs unavailable: the trade log could not be read." in text
    assert "No open longs." not in text and text.endswith(FOOTER)


@pytest.mark.parametrize("label,prior", [("RECOVERY", "SHOCK"), ("NORMAL", "RECOVERY")])
def test_a_transition_out_of_shock_lists_no_longs_and_no_footer(label, prior):
    text = shock_notices.build_shock_embed(shock_event(label, prior)).description
    assert "open longs" not in text.lower() and FOOTER not in text


@pytest.mark.parametrize("label,prior,colour", [
    ("SHOCK", "NORMAL", kinds.HEALTH_RED), ("RECOVERY", "SHOCK", kinds.WATCH_STOP_ORANGE),
    ("NORMAL", "RECOVERY", kinds.HEALTH_GREEN)])
def test_status_chrome_never_an_alert(label, prior, colour):
    embed = shock_notices.build_shock_embed(shock_event(label, prior))
    assert embed.colour.value == colour
    assert embed.footer.text == "Event evt-1"
    assert tokens.DISCLAIMER not in embed.footer.text
    assert embed.timestamp == datetime.fromisoformat(AT)
    assert embed.kind is None


def test_the_payload_is_not_mutated():
    notice = shock_event(longs=[long_row()])
    before = repr(notice)
    shock_notices.build_shock_embed(notice)
    assert repr(notice) == before
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
Expected: FAIL — `ImportError: cannot import name 'shock_notices'`.

- [ ] **Step 3: Create `swingbot/core/scanning/shock_notices.py`**

```python
"""v210: market_shock notices for the v197 notify queue.

Renderer half (V210-1): the event's payload becomes one plain status embed --
headline, trigger numbers and, on an entry into SHOCK, one line per open long
for someone with resting orders at a broker. Never an alert embed: no Kind, no
disclaimer. Pure: no database, no network.
"""
from datetime import datetime

import discord

from swingbot.core import presentation as ui
from swingbot.core.market import shock
from swingbot.core.presentation import kinds

FOOTER = ("The bot moved no stop and closed nothing. "
          "Stop move-up and long block are pending screen (v209 Track 2).")
THROUGH_STOP = "THROUGH STOP"
NA = "n/a"
NO_LONGS = "No open longs."
LONGS_UNAVAILABLE = "Open longs unavailable: the trade log could not be read."
#: Discord caps a description at 4096 characters; the rest of the body fits in 596.
LONGS_BUDGET = 3500
COLOURS = {shock.SHOCK: kinds.HEALTH_RED, shock.RECOVERY: kinds.WATCH_STOP_ORANGE,
           shock.NORMAL: kinds.HEALTH_GREEN}


def _fmt(value, spec: str, suffix: str = "") -> str:
    return NA if value is None else f"{value:{spec}}{suffix}"


def _age(minutes: int) -> str:
    hours, mins = divmod(max(int(minutes), 0), 60)
    return f"{mins}m" if hours == 0 else f"{hours}h{mins:02d}m"


def _marker(row: dict) -> str:
    if row.get("last") is None:
        return f"stop status unknown: {row['stop']:.2f}"
    if row.get("through_stop"):
        return THROUGH_STOP
    return f"stop at broker untouched: {row['stop']:.2f}"


def long_line(row: dict) -> str:
    r = row.get("open_r")
    r_text = f"{NA} R" if r is None else f"{r:+.2f}R"
    return " · ".join((row["ticker"], f"entry {row['entry']:.2f}", f"stop {row['stop']:.2f}",
                       f"last {_fmt(row.get('last'), '.2f')}", r_text,
                       _age(row.get("age_min", 0)), _marker(row)))


def _vix(reading: dict) -> str:
    level, chg = reading.get("vix_level"), reading.get("vix_chg_pct")
    if level is None:
        return f"VIX {NA}"
    return f"VIX {level:.2f} ({_fmt(chg, '+.1f', '%')})"


def numbers_line(reading: dict) -> str:
    frac, speed = reading.get("breadth_frac"), reading.get("breadth_speed")
    return " · ".join((
        f"breadth {NA if frac is None else f'{frac * 100:.0f}%'}",
        f"sectors {reading.get('sectors_down', 0)}/{reading.get('sectors_total', 0)}",
        f"speed {NA if speed is None else f'{speed * 100:+.0f}pp'}",
        f"SPY {_fmt(reading.get('spy_atr_move'), '+.2f', ' ATR')}",
        f"QQQ {_fmt(reading.get('qqq_atr_move'), '+.2f', ' ATR')}",
        _vix(reading)))


def headline(payload: dict) -> str:
    return f"Market state: {payload['prior_label']} → {payload['label']}"


def _long_block(payload: dict) -> list[str]:
    if payload.get("open_longs_unavailable"):
        return [LONGS_UNAVAILABLE]
    rows = payload["open_longs"]
    if not rows:
        return [NO_LONGS]
    lines, used = [f"Open longs ({len(rows)}):"], 0
    for row in rows:
        line = long_line(row)
        if used + len(line) + 1 > LONGS_BUDGET:
            break
        lines.append(line)
        used += len(line) + 1
    shown = len(lines) - 1
    if shown < len(rows):
        lines.append(f"+{len(rows) - shown} more open longs")
    return lines


def _body(payload: dict) -> str:
    lines = [numbers_line(payload["reading"])]
    if payload["entry_into_shock"]:
        lines += ["", *_long_block(payload), "", FOOTER]
    return "\n".join(lines)


def build_shock_embed(event: dict) -> discord.Embed:
    """The status embed for one validated market_shock event."""
    payload = event["payload"]
    title = headline(payload)
    embed = ui.PushEmbed(title=title, description=_body(payload),
                         colour=discord.Color(COLOURS[payload["label"]]))
    embed.push_text = title
    embed.kind = None
    embed.set_footer(text=f"Event {event['event_id']}")
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed
```

`shock_notices` imports nothing from `lifecycle_notifications` or
`lifecycle_events` in this half (V210-2 adds `make_event`), so V210-1b's
import of it creates no cycle.

- [ ] **Step 4: Run it to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
Expected: PASS.

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`_long_block` about 6, every other function below 5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/shock_notices.py tests/scanning/test_shock_notice_render.py
git commit -m "feat(v210): shock_notices renderer -- market-state status embed, open-long lines"
```

### Task V210-1b: `market_shock` queue kind — validator and delivery dispatch

**Model:** sonnet — a third validator beside two that must stay byte-identical, plus one dispatch line; the copy and shapes are pinned by V210-1.

Second half of the ledger's V210-1 (split at the 20 KB task cap). Runs after
V210-1 on the same branch.

**Files:**
- Modify: `swingbot/core/infra/lifecycle_events.py` (`KINDS`, `_validate_shock_payload`, the kind check in `validate_event`, one dispatch in `_validate_payload`)
- Modify: `swingbot/core/scanning/lifecycle_notifications.py` (one dispatch branch in `build_lifecycle_notification`)
- Create: `tests/infra/test_lifecycle_events_market_shock.py` (suite `discord`)
- Modify: `tests/scanning/test_shock_notice_render.py` (append three delivery tests)

**Interfaces:**
- Consumes: `shock.LABELS`, `shock.SHOCK`, `ShockReading(...).as_row()` (V209-2, v209 (merged)); `shock_notices.build_shock_embed` (V210-1); existing `make_event`, `validate_event`, `_aware`, `_identity`, `BlockedDelivery`, `send_lifecycle_notification`.
- Produces (V210-2 relies on these exactly):
  - `lifecycle_events.KINDS = ("trade_closed", "plan_transition", "market_shock")`.
  - `lifecycle_events._validate_shock_payload(payload) -> None`: `label` and `prior_label` in `shock.LABELS` and different; aware ISO `occurred_at`; dict `reading`; list `open_longs`; optional bool `open_longs_unavailable`; bool `entry_into_shock` equal to `label == "SHOCK"` (the labels already differ, so that reads "into SHOCK"). Error codes: `invalid_shock_label`, `shock_notice_without_transition`, `invalid_transition_time`, `invalid_shock_reading`, `invalid_open_longs`, `invalid_entry_flag`.
  - `make_event(kind="market_shock", ...)` returns a validated event; `build_lifecycle_notification` / `send_lifecycle_notification` render and post it.

The two existing kinds keep their validators, renderers and tests
byte-for-byte: Step 4 runs their test files unchanged.

- [ ] **Step 1: Write the failing validator tests**

`tests/infra/test_lifecycle_events_market_shock.py`:

```python
"""v210: the market_shock kind of the v197 notify queue -- validation only."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import lifecycle_events
from swingbot.core.infra.lifecycle_events import make_event, validate_event
from swingbot.core.market import shock

AT = "2026-11-05T14:45:00+00:00"


def reading_row():
    return shock.ShockReading(
        as_of=datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc), session_date=date(2026, 11, 5),
        minutes_since_open=75.0, breadth_frac=0.42, sectors_down=5, sectors_total=8,
        breadth_speed=0.12, spy_atr_move=-1.8, qqq_atr_move=-2.3, spy_last=671.2,
        spy_prev_close=683.0, spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05,
        vix_level=21.13, vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3,
        n_names=61, insufficient=False).as_row()


def payload(**over):
    return dict(label="SHOCK", prior_label="NORMAL", occurred_at=AT, reading=reading_row(),
                open_longs=[], entry_into_shock=True) | over


def event(kind="market_shock", **over):
    return make_event(transition_id=f"market_shock:{AT}", kind=kind, target_channel_id="7",
                      occurred_at=AT, payload=payload(**over))


def test_kinds_gain_market_shock_last():
    assert lifecycle_events.KINDS == ("trade_closed", "plan_transition", "market_shock")


def test_a_valid_shock_event_is_deliverable_and_needs_no_ticker():
    built = event()
    validate_event(built)
    assert built["kind"] == "market_shock" and built["target_channel_id"] == "7"
    assert built["blocked"] is False and "ticker" not in built["payload"]


def test_a_second_leg_and_the_exits_are_valid():
    validate_event(event(label="SHOCK", prior_label="RECOVERY", entry_into_shock=True))
    validate_event(event(label="RECOVERY", prior_label="SHOCK", entry_into_shock=False))
    validate_event(event(label="NORMAL", prior_label="RECOVERY", entry_into_shock=False,
                         open_longs_unavailable=False))


def test_an_unrouted_shock_event_is_stored_blocked():
    built = make_event(transition_id="t", kind="market_shock", target_channel_id=None,
                       occurred_at=AT, payload=payload())
    assert built["blocked"] is True and built["last_error"] == "destination_unresolved"


def test_the_identity_is_kind_scoped():
    shock_id = event()["event_id"]
    assert shock_id == event()["event_id"]
    assert shock_id != lifecycle_events._identity(f"market_shock:{AT}", "plan_transition")


@pytest.mark.parametrize("over,code", [
    ({"label": "CALM"}, "invalid_shock_label"),
    ({"prior_label": None}, "invalid_shock_label"),
    ({"prior_label": "SHOCK"}, "shock_notice_without_transition"),
    ({"occurred_at": "2026-11-05T14:45:00"}, "invalid_transition_time"),
    ({"reading": None}, "invalid_shock_reading"),
    ({"open_longs": {}}, "invalid_open_longs"),
    ({"open_longs_unavailable": "no"}, "invalid_open_longs"),
    ({"entry_into_shock": "yes"}, "invalid_entry_flag"),
    ({"entry_into_shock": False}, "invalid_entry_flag"),
])
def test_a_malformed_shock_payload_is_refused(over, code):
    with pytest.raises(ValueError, match=code):
        event(**over)


def test_a_lifecycle_payload_under_the_shock_kind_is_refused():
    lifecycle = dict(ticker="AAPL", direction="bullish", plan_id="P-1", trade_id=None,
                     prior_status="PENDING", new_status="CANCELLED", reason="manual",
                     occurred_at=AT)
    with pytest.raises(ValueError, match="invalid_shock_label"):
        make_event(transition_id="t", kind="market_shock", target_channel_id="7",
                   occurred_at=AT, payload=lifecycle)


def test_a_shock_payload_under_a_lifecycle_kind_is_still_refused():
    with pytest.raises(ValueError, match="incomplete_payload"):
        event(kind="plan_transition")


def test_an_unknown_kind_is_still_refused():
    with pytest.raises(ValueError, match="invalid_event_kind_or_identity"):
        event(kind="market_note")
```

Append to `tests/scanning/test_shock_notice_render.py` (add `import asyncio`,
`from types import SimpleNamespace`, `from unittest.mock import AsyncMock, Mock`,
`from swingbot.core.infra.lifecycle_events import make_event` and
`lifecycle_notifications` to the existing `from swingbot.core.scanning import`
line):

```python
def queued(label="SHOCK", prior="NORMAL"):
    payload = shock_event(label, prior)["payload"]
    return make_event(transition_id=f"market_shock:{AT}", kind="market_shock",
                      target_channel_id="7", occurred_at=AT, payload=payload)


def test_lifecycle_renderer_dispatches_the_shock_kind():
    notice = queued()
    built = lifecycle_notifications.build_lifecycle_notification(notice)
    assert built.title == "Market state: NORMAL → SHOCK"
    assert built.footer.text == f"Event {notice['event_id']}"
    assert not any(field.name == "Recorded transition" for field in built.fields)


def test_a_malformed_shock_event_is_a_blocked_delivery():
    notice = queued()
    notice["payload"]["reading"] = None
    with pytest.raises(lifecycle_notifications.BlockedDelivery) as caught:
        lifecycle_notifications.build_lifecycle_notification(notice)
    assert caught.value.code == "malformed_payload"


def test_send_posts_the_shock_embed_with_its_push_line():
    channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=99)))
    bot = SimpleNamespace(get_channel=Mock(return_value=channel), fetch_channel=AsyncMock())
    assert asyncio.run(lifecycle_notifications.send_lifecycle_notification(
        bot, queued())) == "99"
    bot.get_channel.assert_called_once_with(7)
    kwargs = channel.send.await_args.kwargs
    assert kwargs["content"] == "Market state: NORMAL → SHOCK" == kwargs["embed"].title
```

- [ ] **Step 2: Run both to verify they fail**

Run: `python scripts/dev/testrun.py file tests/infra/test_lifecycle_events_market_shock.py`
Expected: FAIL — `AttributeError: ... has no attribute 'KINDS'`, and `ValueError: invalid_event_kind_or_identity` from every `make_event(kind="market_shock")`.

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
Expected: the three new tests FAIL with `ValueError: invalid_event_kind_or_identity`; V210-1's tests still pass.

- [ ] **Step 3: Implement**

3a. `swingbot/core/infra/lifecycle_events.py` — add
`from swingbot.core.market.shock import LABELS, SHOCK` (`shock.py` is pure, so
the infra module still does no I/O) and, above `_identity`:

```python
#: v210: the v197 queue's event kinds; market_shock is a status notice, not a lifecycle event.
KINDS = ("trade_closed", "plan_transition", "market_shock")
```

Append after `_validate_plan_transition`:

```python
def _validate_shock_payload(payload):
    """v210: a market-state transition notice (shock_notices.notice_payload)."""
    label, prior = payload.get("label"), payload.get("prior_label")
    if label not in LABELS or prior not in LABELS:
        raise ValueError("invalid_shock_label")
    if label == prior:
        raise ValueError("shock_notice_without_transition")
    _aware(payload.get("occurred_at"))
    if not isinstance(payload.get("reading"), dict):
        raise ValueError("invalid_shock_reading")
    unavailable = payload.get("open_longs_unavailable", False)
    if not isinstance(payload.get("open_longs"), list) or not isinstance(unavailable, bool):
        raise ValueError("invalid_open_longs")
    entry = payload.get("entry_into_shock")
    if not isinstance(entry, bool) or entry != (label == SHOCK):
        raise ValueError("invalid_entry_flag")
```

In `_validate_payload`, straight after the `isinstance(payload, dict)` check
and before `required = ...`:

```python
    if kind == "market_shock":
        _validate_shock_payload(payload)
        return
```

In `validate_event`, replace the literal tuple with `KINDS`
(`if kind not in KINDS or not event.get("transition_id"):`). Nothing else in
the file changes; `make_event` needs no edit (it already validates).

3b. `swingbot/core/scanning/lifecycle_notifications.py` — add
`from swingbot.core.scanning import shock_notices` and, inside the `try` of
`build_lifecycle_notification`, directly after `validate_event(event)`:

```python
        if event["kind"] == "market_shock":
            return shock_notices.build_shock_embed(event)
```

The existing `except` already turns a `KeyError`/`TypeError` from a broken
payload into `BlockedDelivery("malformed_payload")`; `_append_transition`
(which reads `ticker`/`direction`) never runs on a shock notice. The delivery
loop (`lifecycle_delivery.py`) and `notify_queue.py` are kind-agnostic and do
not change.

- [ ] **Step 4: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/infra/test_lifecycle_events_market_shock.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
`python scripts/dev/testrun.py file tests/infra/test_lifecycle_events.py`
`python scripts/dev/testrun.py file tests/scanning/test_lifecycle_notifications.py`
`python scripts/dev/testrun.py file tests/commands/test_lifecycle_delivery.py`
Expected: PASS; the last three are unchanged files (the two existing kinds are untouched).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`_validate_shock_payload` about 9; `_validate_payload` and `build_lifecycle_notification` +1 each, both well under 15).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/infra/lifecycle_events.py swingbot/core/scanning/lifecycle_notifications.py \
        tests/infra/test_lifecycle_events_market_shock.py tests/scanning/test_shock_notice_render.py
git commit -m "feat(v210): market_shock queue kind -- validator and delivery dispatch"
```

### Task V210-2: Notice payload helpers — open longs, rate limit, queue event

**Model:** sonnet — pure helpers with pinned shapes; the kind, copy and transaction are already fixed by V210-1, V210-1b and V209-5b (v209 (merged)).

First half of the ledger's V210-2 (split at the 20 KB task cap): the pure
payload half of `shock_notices.py`. V210-2b hooks it into the stepped pass.

**Files:**
- Modify: `swingbot/core/scanning/shock_notices.py` (append the payload half)
- Create: `tests/scanning/test_shock_notice_payload.py` (suite `scanning`)

**Interfaces:**
- Consumes: `make_event` and the `market_shock` kind with its validator (V210-1b); `ShockState`, `ShockReading`, `shock.SHOCK` (V209-2..4, v209 (merged)); `config.DISCORD_CHANNEL_OPS_ID`, `config.DISCORD_CHANNEL_TRADES_ID`.
- Produces (V210-2b calls these exactly):
  - `shock_notices.open_long_rows(trades: list[dict], last_prices: Mapping[str, float], now: datetime) -> list[dict]` — trades with `direction == "bullish"`, a ticker and a positive `entry` and `stop_loss`, sorted by ticker; each row `{"ticker", "entry", "stop", "last", "open_r", "age_min", "through_stop"}` with `open_r = (last − entry) / (entry − stop)` (`None` without a last price or when `entry ≤ stop`) and `through_stop = last <= stop`.
  - `shock_notices.should_notify(prior_label: str, new_label: str, last_notice_at: datetime | None, now: datetime, min_dwell_min: int) -> bool`.
  - `shock_notices.notice_payload(prior: ShockState, new: ShockState, reading: ShockReading, open_longs: list[dict], now: datetime) -> dict`.
  - `shock_notices.notice_event(payload: dict, *, as_of: datetime) -> dict` — `make_event(transition_id=f"market_shock:{as_of.isoformat()}", kind="market_shock", target_channel_id=config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None, occurred_at=payload["occurred_at"], payload=payload)`.

**Rules (spec § Discord notices, Global Constraints):** a notice only on a
label change; any transition **into** SHOCK (from NORMAL, or the RECOVERY →
SHOCK second leg) is always sent and lists the open longs; any other
transition is sent only when no notice went out in the last
`SHOCK_MIN_DWELL_MIN` minutes (`last_notice_at`), and lists none. A dropped
notice is not deferred. Open longs are read only on an entry into SHOCK. The
last price is the pass's fresh quote set (`quotes` in `_stepped_pass`, already
filtered by `SHOCK_QUOTE_MAX_AGE_S`), so an unquoted long shows `last n/a`.
The channel id is computed in the worker thread from config, never through
`bot.get_channel`.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_shock_notice_payload.py`:

```python
"""v210: market_shock notice payload, open longs, rate limit, and the stepped-pass hook."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.scanning import shock_notices

UTC = timezone.utc
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)            # 10:00 ET, a regular session
READING = shock.ShockReading(
    as_of=NOW, session_date=date(2026, 11, 5), minutes_since_open=30.0, breadth_frac=0.45,
    sectors_down=6, sectors_total=9, breadth_speed=0.15, spy_atr_move=-1.6, qqq_atr_move=-2.1,
    spy_last=490.0, spy_prev_close=500.0, spy_session_low=489.0, spy_new_low=True,
    spy_retrace=0.0, vix_level=21.1, vix_chg_pct=27.0, vix_session_high=21.1,
    vix_off_high_pct=0.0, n_names=60, insufficient=False)
QUOTES = {"SPY": 490.0, "STX": 94.0}


def trade(ticker, *, direction="bullish", entry=100.0, stop=95.0,
          opened="2026-11-05T12:55:00+00:00"):
    return {"ticker": ticker, "direction": direction, "entry": entry, "stop_loss": stop,
            "opened_at": opened, "status": "open"}


TRADES = [trade("STX"), trade("MU", entry=50.0, stop=48.0), trade("NVDA", direction="bearish")]


def test_open_long_rows_keep_open_longs_sorted_with_r_age_and_marker():
    rows = shock_notices.open_long_rows(TRADES, {"STX": 94.0, "MU": 51.0}, NOW)
    assert [r["ticker"] for r in rows] == ["MU", "STX"]
    mu, stx = rows
    assert mu == {"ticker": "MU", "entry": 50.0, "stop": 48.0, "last": 51.0,
                  "open_r": pytest.approx(0.5), "age_min": 125, "through_stop": False}
    assert stx["open_r"] == pytest.approx(-1.2) and stx["through_stop"] is True


def test_an_unquoted_long_has_no_last_no_r_and_is_not_through():
    (row,) = shock_notices.open_long_rows([trade("MU")], {}, NOW)
    assert (row["last"], row["open_r"], row["through_stop"]) == (None, None, False)


def test_last_exactly_at_the_stop_is_through_it():
    (row,) = shock_notices.open_long_rows([trade("MU")], {"MU": 95.0}, NOW)
    assert row["through_stop"] is True and row["open_r"] == pytest.approx(-1.0)


def test_a_stop_at_or_above_entry_has_no_r():
    (row,) = shock_notices.open_long_rows([trade("MU", stop=100.0)], {"MU": 101.0}, NOW)
    assert row["open_r"] is None and row["through_stop"] is False


@pytest.mark.parametrize("bad", [{"entry": None}, {"stop_loss": 0}, {"ticker": ""}])
def test_a_trade_without_entry_stop_or_ticker_is_skipped(bad):
    assert shock_notices.open_long_rows([trade("MU") | bad], {"MU": 99.0}, NOW) == []


@pytest.mark.parametrize("opened,age", [("2026-11-05T12:55:00", 125), ("garbage", 0), (None, 0)])
def test_age_treats_naive_as_utc_and_unreadable_as_zero(opened, age):
    (row,) = shock_notices.open_long_rows([trade("MU", opened=opened)], {}, NOW)
    assert row["age_min"] == age


def test_no_open_trades_gives_no_rows():
    assert shock_notices.open_long_rows([], QUOTES, NOW) == []


@pytest.mark.parametrize("prior,new,minutes_ago,sent", [
    ("SHOCK", "SHOCK", None, False),
    ("NORMAL", "SHOCK", 5, True),            # entry: always sent
    ("RECOVERY", "SHOCK", 5, True),          # second leg inside the window: still sent
    ("SHOCK", "RECOVERY", 44, False),
    ("SHOCK", "RECOVERY", 45, True),
    ("RECOVERY", "NORMAL", None, True),
])
def test_should_notify(prior, new, minutes_ago, sent):
    last = None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago)
    assert shock_notices.should_notify(prior, new, last, NOW, 45) is sent


def test_notice_payload_and_event(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "111")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "222")
    longs = shock_notices.open_long_rows(TRADES, QUOTES, NOW)
    payload = shock_notices.notice_payload(shock.ShockState(label="RECOVERY"),
                                           shock.ShockState(label="SHOCK", since=NOW),
                                           READING, longs, NOW)
    assert payload == {"label": "SHOCK", "prior_label": "RECOVERY",
                       "occurred_at": "2026-11-05T15:00:00+00:00", "reading": READING.as_row(),
                       "open_longs": longs, "entry_into_shock": True}
    event = shock_notices.notice_event(payload, as_of=NOW)
    assert event["kind"] == "market_shock" and event["target_channel_id"] == "111"
    assert event["transition_id"] == "market_shock:2026-11-05T15:00:00+00:00"
    assert event["queued_at"] == payload["occurred_at"] and event["blocked"] is False


@pytest.mark.parametrize("ops,trades_id,target", [("", "222", "222"), ("", "", None)])
def test_notice_routes_to_trades_then_blocks(monkeypatch, ops, trades_id, target):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", ops)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", trades_id)
    payload = shock_notices.notice_payload(shock.ShockState(), shock.ShockState(label="SHOCK"),
                                           READING, [], NOW)
    event = shock_notices.notice_event(payload, as_of=NOW)
    assert event["target_channel_id"] == target and event["blocked"] is (target is None)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_notice_payload.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.shock_notices' has no attribute 'open_long_rows'`.

- [ ] **Step 3: Append the payload half to `swingbot/core/scanning/shock_notices.py`**

Add to the imports `import math`, `from collections.abc import Mapping`,
`from datetime import datetime, timedelta, timezone` (replacing the bare
`datetime` import), `from swingbot import config` and
`from swingbot.core.infra.lifecycle_events import make_event`; extend the
module docstring with "Payload half (V210-2): open-long rows, the rate limit
and the queue event; config is read only for the target channel." Append:

```python
KIND = "market_shock"


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _age_min(opened_at, now: datetime) -> int:
    try:
        opened = datetime.fromisoformat(str(opened_at))
    except ValueError:
        return 0
    opened = opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc)
    return max(int((now - opened).total_seconds() // 60), 0)


def _long_row(trade: dict, last_prices: Mapping[str, float], now: datetime) -> dict | None:
    entry, stop = _positive(trade.get("entry")), _positive(trade.get("stop_loss"))
    if entry is None or stop is None:
        return None
    last = _positive(last_prices.get(trade["ticker"]))
    risk = entry - stop
    open_r = None if last is None or risk <= 0 else (last - entry) / risk
    return {"ticker": str(trade["ticker"]), "entry": entry, "stop": stop, "last": last,
            "open_r": open_r, "age_min": _age_min(trade.get("opened_at"), now),
            "through_stop": last is not None and last <= stop}


def open_long_rows(trades: list[dict], last_prices: Mapping[str, float],
                   now: datetime) -> list[dict]:
    """One row per open long, by ticker; shorts and rows without entry/stop are skipped."""
    rows = (_long_row(t, last_prices, now) for t in trades
            if t.get("direction") == "bullish" and t.get("ticker"))
    return sorted((row for row in rows if row is not None), key=lambda row: row["ticker"])


def should_notify(prior_label: str, new_label: str, last_notice_at: datetime | None,
                  now: datetime, min_dwell_min: int) -> bool:
    """One notice per SHOCK_MIN_DWELL_MIN, except a transition into SHOCK."""
    if prior_label == new_label:
        return False
    if new_label == shock.SHOCK or last_notice_at is None:
        return True
    return now - last_notice_at >= timedelta(minutes=min_dwell_min)


def notice_payload(prior: shock.ShockState, new: shock.ShockState,
                   reading: shock.ShockReading, open_longs: list[dict], now: datetime) -> dict:
    return {"label": new.label, "prior_label": prior.label, "occurred_at": now.isoformat(),
            "reading": reading.as_row(), "open_longs": list(open_longs),
            "entry_into_shock": new.label == shock.SHOCK and prior.label != shock.SHOCK}


def notice_event(payload: dict, *, as_of: datetime) -> dict:
    """The queue event; the channel id is computed here, never via bot.get_channel."""
    channel = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None
    return make_event(transition_id=f"{KIND}:{as_of.isoformat()}", kind=KIND,
                      target_channel_id=channel, occurred_at=payload["occurred_at"],
                      payload=payload)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_notice_payload.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_notice_render.py`
Expected: PASS (pure: no database, no network).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`_long_row` about 6, every other new function below 5).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/shock_notices.py tests/scanning/test_shock_notice_payload.py
git commit -m "feat(v210): market_shock notice payload -- open longs, rate limit, queue event"
```

### Task V210-2b: Enqueue the notice from the stepped pass

**Model:** sonnet — one guarded hook in `_stepped_pass` plus a trade-log reader; every helper it calls is pinned by V210-2.

Second half of the ledger's V210-2 (split at the 20 KB task cap). Runs after
V210-2 on the same branch.

**Files:**
- Modify (created by V209-6, v209 (merged)): `swingbot/core/scanning/shock_scan.py` (`_stepped_pass` passes `notice_event`; new `_open_trades`, `_open_longs`, `_notice_for`, `_safe_notice`)
- Modify (created by V209-6a, v209 (merged)): `tests/scanning/test_shock_pass.py` (one stub line in the autouse `_env` fixture, Step 3c)
- Create: `tests/scanning/test_shock_pass_notice.py` (suite `scanning`)

**Interfaces:**
- Consumes: V210-2's `open_long_rows`, `should_notify`, `notice_payload`, `notice_event`; `shock_scan._stepped_pass(frames, live_prices, sector_of, quotes_at, spy_df, now, repo)` and its local `quotes`, `build_snapshot`, `read_vix` (V209-6/6a, v209 (merged)); `repo.current_state()["last_notice_at"]`, `repo.record(..., notice_event=)` (V209-5b, v209 (merged)); existing `swingbot.core.scanning.singletons.trade_log.get_trades(status="open", limit=None)`.
- Produces: `shock_scan._open_trades() -> list[dict] | None` (`None` when the trade log cannot be read). A stepped pass that changes the label hands `record()` the notice the V210-2 rules allow, in the reading's transaction.

- [ ] **Step 1: Write the failing tests**

`tests/scanning/test_shock_pass_notice.py`:

```python
"""v210: the stepped pass enqueues a market_shock notice with its reading."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot import config
from swingbot.core.market import shock
from swingbot.core.scanning import shock_scan, singletons

UTC = timezone.utc
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)            # 10:00 ET, a regular session
READING = shock.ShockReading(
    as_of=NOW, session_date=date(2026, 11, 5), minutes_since_open=30.0, breadth_frac=0.45,
    sectors_down=6, sectors_total=9, breadth_speed=0.15, spy_atr_move=-1.6, qqq_atr_move=-2.1,
    spy_last=490.0, spy_prev_close=500.0, spy_session_low=489.0, spy_new_low=True,
    spy_retrace=0.0, vix_level=21.1, vix_chg_pct=27.0, vix_session_high=21.1,
    vix_off_high_pct=0.0, n_names=60, insufficient=False)
QUOTES = {"SPY": 490.0, "STX": 94.0}


def trade(ticker, *, direction="bullish", entry=100.0, stop=95.0):
    return {"ticker": ticker, "direction": direction, "entry": entry, "stop_loss": stop,
            "opened_at": "2026-11-05T12:55:00+00:00", "status": "open"}


TRADES = [trade("STX"), trade("MU", entry=50.0, stop=48.0), trade("NVDA", direction="bearish")]


class _Repo:
    def __init__(self, label, last_notice_at=None):
        self.state = {"label": label, "last_notice_at": last_notice_at,
                      "doc": {"state": shock.ShockState(label=label).as_row()}}
        self.records = []

    def current_state(self, *, conn=None):
        return self.state

    def latest_reading(self, *, conn=None):
        return None

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.records.append({"after": state_after, "event": notice_event})
        return len(self.records)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "DISCORD_CHANNEL_OPS_ID", "111")
    monkeypatch.setattr(shock_scan, "build_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(shock_scan, "read_vix", lambda *a, **k: None)
    monkeypatch.setattr(shock_scan.shock, "measure", lambda snapshot, prev, th: READING)
    monkeypatch.setattr(shock_scan.fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("unexpected quote fetch"))
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: TRADES)


def _step(monkeypatch, prior, new, *, minutes_ago=None):
    monkeypatch.setattr(shock_scan.shock, "step",
                        lambda state, reading, th: shock.ShockState(label=new, since=NOW))
    last = None if minutes_ago is None else NOW - timedelta(minutes=minutes_ago)
    repo = _Repo(prior, last)
    label = shock_scan.run_shock_pass(step_shock=True, frames={}, live_prices=QUOTES,
                                      sector_of={}, quotes_at=NOW, now=NOW, repo=repo)
    (record,) = repo.records
    assert label == new == record["after"]
    return record["event"]


def test_entry_into_shock_enqueues_with_the_open_longs(monkeypatch):
    event = _step(monkeypatch, "NORMAL", "SHOCK")
    payload = event["payload"]
    assert (payload["prior_label"], payload["label"], payload["entry_into_shock"]) == (
        "NORMAL", "SHOCK", True)
    assert [r["ticker"] for r in payload["open_longs"]] == ["MU", "STX"]
    assert payload["open_longs"][0]["last"] is None                  # MU unquoted this pass
    assert event["target_channel_id"] == "111"


def test_a_second_leg_inside_the_rate_limit_still_enqueues(monkeypatch):
    event = _step(monkeypatch, "RECOVERY", "SHOCK", minutes_ago=5)
    assert event is not None and event["payload"]["entry_into_shock"] is True


def test_a_rate_limited_exit_records_the_reading_without_a_notice(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: pytest.fail("longs read"))
    assert _step(monkeypatch, "SHOCK", "RECOVERY", minutes_ago=10) is None


def test_an_exit_after_the_dwell_is_announced_without_longs(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: pytest.fail("longs read"))
    payload = _step(monkeypatch, "SHOCK", "RECOVERY", minutes_ago=45)["payload"]
    assert payload["open_longs"] == [] and payload["entry_into_shock"] is False


def test_no_transition_no_notice(monkeypatch):
    assert _step(monkeypatch, "SHOCK", "SHOCK", minutes_ago=500) is None


def test_an_unreadable_trade_log_is_flagged_not_hidden(monkeypatch):
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: None)
    payload = _step(monkeypatch, "NORMAL", "SHOCK")["payload"]
    assert payload["open_longs"] == [] and payload["open_longs_unavailable"] is True


def test_a_notice_that_cannot_be_built_still_records_the_reading(monkeypatch, caplog):
    def boom(payload, *, as_of):
        raise ValueError("invalid_shock_reading")
    monkeypatch.setattr(shock_scan.shock_notices, "notice_event", boom)
    assert _step(monkeypatch, "NORMAL", "SHOCK") is None
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.notice" for r in caplog.records)


def test_open_trades_reads_the_trade_log_and_swallows_a_failure(monkeypatch):
    monkeypatch.undo()                                   # the real _open_trades
    calls = []

    def get_trades(status=None, limit=20, **kwargs):
        calls.append((status, limit))
        return TRADES
    monkeypatch.setattr(singletons.trade_log, "get_trades", get_trades)
    assert shock_scan._open_trades() == TRADES and calls == [("open", None)]

    def boom(**kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(singletons.trade_log, "get_trades", boom)
    assert shock_scan._open_trades() is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_shock_pass_notice.py`
Expected: FAIL — `AttributeError: <module 'swingbot.core.scanning.shock_scan'> has no attribute '_open_trades'` from the fixture's `monkeypatch.setattr`.

- [ ] **Step 3: Hook the notice into `swingbot/core/scanning/shock_scan.py`**

3a. Extend the package import to `from swingbot.core.scanning import fetch, shock_notices`.

3b. In `_stepped_pass`, replace the `repo.record(...)` line with:

```python
    event = _safe_notice(state, new_state, reading, quotes, now, repo, th)
    repo.record(reading.as_row(), new_state.as_row(), state_after=new_state.label,
                notice_event=event)
```

and append above `_stepped_pass`:

```python
def _open_trades() -> list[dict] | None:
    """Open trades for a SHOCK notice; None when the trade log cannot be read."""
    try:
        from swingbot.core.scanning.singletons import trade_log
        return list(trade_log.get_trades(status="open", limit=None) or [])
    except Exception as exc:
        swallowed(log, "scan.shock.open_trades", exc, "shock: open trades unreadable: %s", exc)
        return None


def _open_longs(quotes, now) -> tuple[list[dict], bool]:
    trades = _open_trades()
    if trades is None:
        return [], True
    return shock_notices.open_long_rows(trades, quotes, now), False


def _notice_for(prior, new, reading, quotes, now, repo, th) -> dict | None:
    if prior.label == new.label:
        return None
    last_notice_at = (repo.current_state() or {}).get("last_notice_at")
    if not shock_notices.should_notify(prior.label, new.label, last_notice_at, now,
                                       th.min_dwell_min):
        return None
    longs, unavailable = (_open_longs(quotes, now) if new.label == shock.SHOCK
                          else ([], False))
    payload = shock_notices.notice_payload(prior, new, reading, longs, now)
    if unavailable:
        payload["open_longs_unavailable"] = True
    return shock_notices.notice_event(payload, as_of=reading.as_of)


def _safe_notice(prior, new, reading, quotes, now, repo, th) -> dict | None:
    """A notice that cannot be built never costs the reading or the state step."""
    try:
        return _notice_for(prior, new, reading, quotes, now, repo, th)
    except Exception as exc:
        swallowed(log, "scan.shock.notice", exc,
                  "shock: notice not built; the reading is still recorded: %s", exc,
                  exc_info=True)
        return None
```

`current_state()` is re-read only on a label change. `singletons` is imported
inside `_open_trades`, so importing `shock_scan` never builds the trade log.

3c. `tests/scanning/test_shock_pass.py` (V209-6a, v209 (merged)): its
`test_two_stepped_crash_readings_enter_shock_and_record_each` now reaches
`_open_trades`; keep that file hermetic by adding one line to its autouse
`_env` fixture:

```python
    monkeypatch.setattr(shock_scan, "_open_trades", lambda: [])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run each:
`python scripts/dev/testrun.py file tests/scanning/test_shock_pass_notice.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_pass.py`
`python scripts/dev/testrun.py file tests/scanning/test_shock_notice_payload.py`
Expected: PASS (no database, no network: fake repository, stubbed trade log and quote fetch).

Run: `python scripts/dev/complexity_gate.py`
Expected: no violation (`_notice_for` about 6, every other new function below 5; `_stepped_pass` gains no branch).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/shock_scan.py tests/scanning/test_shock_pass_notice.py \
        tests/scanning/test_shock_pass.py
git commit -m "feat(v210): stepped pass enqueues the market_shock notice with its reading"
```

# Phase 2 — admin badge

### Task V210-3: Admin tape `shock` object (API)

**Model:** sonnet — one read-only field on an existing endpoint, its shape pinned by the ledger; the SPA half is V210-3b.

First half of the ledger's V210-3 (split at the 20 KB task cap): the API
field. V210-3b (part 2, `_2-admin-badge.md`) renders it as the SPA badge.

**Files:**
- Modify: `swingbot/admin/api_v1/market.py` (`_iso()`, `_shock_fields()`, `_shock_block()`, `"shock"` in both returns of `tape()`)
- Create: `tests/admin/test_api_v1_tape_shock.py` (suite `admin`)

**Interfaces:**
- Consumes: `market_shock.market_shock_repo().current_state()` / `.latest_reading()` (V209-5b, v209 (merged)); `shock_scan.shock_mode()` (V209-6, v209 (merged)); `ShockReading.as_row()` keys (V209-2, v209 (merged)).
- Produces (V210-3b reads it): `GET /api/v1/market/tape` → `"shock": null` under `off` (or an unknown mode), before the first state row, or when the store cannot be read; else `{"label", "since", "as_of", "breadth_pct", "sectors_down", "sectors_total", "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_missing": bool}` (`breadth_pct = round(breadth_frac * 100, 1)`; `as_of` is the last reading's; `vix_missing = vix_level is None`). Both returns of `tape()` carry the key; the admin never steps the detector.

- [ ] **Step 1: Write the failing API tests**

`tests/admin/test_api_v1_tape_shock.py`:

```python
"""v210: GET /api/v1/market/tape carries the market-shock state for the SPA badge."""
from datetime import date, datetime, timezone

import pytest

from swingbot import config
from swingbot.core.db.repositories import market_shock
from swingbot.core.market import shock

_LOGIN = {"username": "admin", "password": "admin"}
SINCE = datetime(2026, 11, 5, 14, 45, tzinfo=timezone.utc)
STATE = {"label": "SHOCK", "since": SINCE, "session_date": date(2026, 11, 5),
         "vix_session_high": 21.4, "last_reading_id": 7, "last_notice_at": None,
         "updated_at": SINCE, "doc": {}}


def reading(**over):
    fields = dict(as_of=datetime(2026, 11, 5, 15, 0, tzinfo=timezone.utc),
                  session_date=date(2026, 11, 5), minutes_since_open=90.0, breadth_frac=0.4237,
                  sectors_down=5, sectors_total=8, breadth_speed=0.12, spy_atr_move=-1.8,
                  qqq_atr_move=-2.3, spy_last=671.2, spy_prev_close=683.0,
                  spy_session_low=670.9, spy_new_low=True, spy_retrace=0.05, vix_level=21.13,
                  vix_chg_pct=27.2, vix_session_high=21.4, vix_off_high_pct=1.3, n_names=61,
                  insufficient=False) | over
    return shock.ShockReading(**fields).as_row() | {"id": 7, "state_after": "SHOCK"}


class _Repo:
    def __init__(self, state=None, latest=None, fail=False):
        self.state, self.latest, self.fail = state, latest, fail

    def current_state(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.state

    def latest_reading(self, *, conn=None):
        return self.latest


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_daily_batch_network(monkeypatch):
    from swingbot.admin import tape_cache
    tape_cache.reset()
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch", lambda syms: {})
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")


def _shock(client, monkeypatch, repo, symbols="^GSPC"):
    monkeypatch.setattr(market_shock, "market_shock_repo", lambda: repo)
    resp = client.get(f"/api/v1/market/tape?symbols={symbols}")
    assert resp.status_code == 200
    return resp.get_json()["shock"]


def test_the_state_and_its_last_reading_reach_the_badge(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(STATE, reading())) == {
        "label": "SHOCK", "since": "2026-11-05T14:45:00+00:00",
        "as_of": "2026-11-05T15:00:00+00:00", "breadth_pct": 42.4, "sectors_down": 5,
        "sectors_total": 8, "spy_atr_move": -1.8, "qqq_atr_move": -2.3, "vix_level": 21.13,
        "vix_chg_pct": 27.2, "vix_missing": False}


def test_a_reading_without_vix_says_vix_missing(logged_in, monkeypatch):
    got = _shock(logged_in, monkeypatch, _Repo(STATE, reading(vix_level=None, vix_chg_pct=None)))
    assert got["vix_missing"] is True and got["vix_level"] is None


def test_a_state_row_without_a_reading_has_empty_numbers(logged_in, monkeypatch):
    got = _shock(logged_in, monkeypatch, _Repo(STATE, None))
    assert got["label"] == "SHOCK" and got["as_of"] is None and got["breadth_pct"] is None
    assert got["vix_missing"] is True


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_or_an_unknown_mode_sends_null_and_reads_nothing(logged_in, monkeypatch, mode):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
    assert _shock(logged_in, monkeypatch, _Repo(fail=True)) is None


def test_no_state_row_yet_sends_null(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(None, None)) is None


def test_a_dead_store_never_fails_the_tape(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(fail=True)) is None


def test_the_empty_symbols_reply_carries_the_key_too(logged_in, monkeypatch):
    assert _shock(logged_in, monkeypatch, _Repo(STATE, reading()), symbols="")["label"] == "SHOCK"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_tape_shock.py`
Expected: FAIL — `KeyError: 'shock'`.

- [ ] **Step 3: Implement the API field in `swingbot/admin/api_v1/market.py`**

Insert above the `@api_v1.route("/market/tape", ...)` decorator:

```python
def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _shock_fields(state: dict, reading: dict) -> dict:
    frac = reading.get("breadth_frac")
    return {"label": state["label"], "since": _iso(state.get("since")),
            "as_of": reading.get("as_of"),
            "breadth_pct": None if frac is None else round(frac * 100, 1),
            **{key: reading.get(key) for key in ("sectors_down", "sectors_total",
                                                 "spy_atr_move", "qqq_atr_move",
                                                 "vix_level", "vix_chg_pct")},
            "vix_missing": reading.get("vix_level") is None}


def _shock_block() -> dict | None:
    """v210: the tape badge's market-shock state. None under `off`, before the
    first stepped pass, or when the store cannot be read -- the tape never fails
    on it. Read-only: the admin never steps the detector."""
    from swingbot.core.db.repositories import market_shock
    from swingbot.core.scanning.shock_scan import shock_mode

    if shock_mode() == "off":
        return None
    try:
        repo = market_shock.market_shock_repo()
        state = repo.current_state()
        reading = (repo.latest_reading() or {}) if state else {}
    except Exception as exc:
        swallowed(logging.getLogger(__name__), "ops.market.tape_shock", exc,
                  "tape: market-shock state unreadable: %s", exc)
        return None
    return _shock_fields(state, reading) if state else None
```

In `tape()`, the early return becomes
`return jsonify({"as_of": as_of, "rows": [], "shock": _shock_block()})` and the
final one `return jsonify({"as_of": as_of, "rows": rows, "shock": _shock_block()})`
(no new branch in `tape()`, CC stays 9).

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_tape_shock.py` and `python scripts/dev/testrun.py file tests/admin/test_api_v1_tape.py`
Expected: PASS (the existing tape tests are unchanged).

- [ ] **Step 4: Commit**

```bash
git add swingbot/admin/api_v1/market.py tests/admin/test_api_v1_tape_shock.py
git commit -m "feat(v210): admin tape carries the market-shock state"
```

