# v153 Slash command parity. Part 4b: `slash.py` chain II, last link (`scanning/commands`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here.

This is the last task of the `slash.py` chain. It was split out of part 4 (`..._4-backtest-watchlist-stats-scanning.md`) only for the 1500-line file cap. The "Shared conventions for this part" block at the top of part 4 applies here unchanged: `$WT`, the SP1 names, the `ParityCase.expect` meanings, `send_error` for validation, `defer()` after validation, verbatim decorators for moved twins, and radon over every touched file. SP16 runs after SP15.

# Phase 4: `slash.py` chain II (continued)

### Task SP16: `scanning/commands`: recap, check, session, status, pause, resume, stop

**Model:** opus — `check_cmd` (D23) and `_check_historical` (C17) are legacy bodies with a background progress poller and edit-based delivery; they must be split below 15, gain the stale-token path, and keep every text and the alert routing exactly.

**Files:**
- Modify: `swingbot/commands/scanning/commands.py` (whole command section, 379 lines today)
- Modify: `swingbot/commands/slash.py` (delete `/check` and `/stop`; then trim the module docstring and dead imports)
- Create: `tests/commands/parity_cases/scanning.py`
- Modify: `tests/commands/test_commands_check.py` (update the one existing test; append a v153 block)
- Modify: `tests/scanning/test_short_lane_scan.py` (line 288: the source check moves from `check_cmd.callback` to `_finish_check`)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `TOKEN_LIFETIME_S`, `PREFIX_TIP_UNTIL`, `reply._today`; `ParityCase`, `FakeContext`, `FakeInteraction`, `run_both`, `comparable`. Consumes `slash.HORIZON_CHOICES`. Consumes `scanning/alerts.py`'s `_send_alerts`, `post_short_universe` and `send_then_short`, which take `reply` as their `destination` (index, Global Constraints: they call `destination.send(content=?, embed=, file=?, view=?, silent=)`).
- Produces (ledger): `handle_recap(reply, date_arg: str = "")`, `handle_check(reply, horizon: str = "all", min_confluence: int | None = None, date_from: str | None = None, date_to: str | None = None)`, `_check_historical(reply, horizon, date_from, date_to)` (same name, first parameter now a `Reply`), `handle_session(reply)`, `handle_status(reply)`, `handle_pause(reply)`, `handle_resume(reply)`, `handle_stop(reply)`. Prefix name `check_cmd` is kept (re-exported by `scanning/__init__.py:10`). Private helpers: `_parse_check_args`, `_check_intro`, `_elapsed_str`, `_crawl_label`, `_analyze_label`, `_progress_label`, `_poll_check_progress`, `_check_live`, `_show_result`, `_min_strats_bit`, `_no_alerts_text`, `_check_summary`, `_finish_check`, `_historical_line`, `_pack_messages`, `_session_now`, `_min_from_option`. Twins: `/check` (`slash_check`) and `/stop` (`slash_stop`) moved with their decorators verbatim; `/recap`, `/session`, `/status`, `/pause`, `/resume` new. Afterwards `slash.py` contains no `@bot.tree.command` and `swingbot/commands/` contains no `from_interaction`.
- Output:
  - Every `!` text is unchanged; the tip follows a successful answer.
  - `!recap <bad date>` and a failed retrospective answer the same texts through `send_error` (no tip).
  - `!stop` with no scan running answers the same text; it carries `ephemeral=True`, a no-op on `CtxReply` (union rule). `/stop` now logs `Stop requested via !stop (by %s).` with the invoking user, as `!stop` did.
  - `!pause` / `!resume` / `!stop` log `reply.author`, which is `ctx.author` on the prefix surface.
  - `!check` still edits its progress message into the summary: `CtxReply.stale` is always `False`. On `/check`, once the 15-minute token is stale (`InteractionReply.stale`), the poller stops editing and the summary goes out as a fresh `send`, which a stale reply posts with `interaction.channel.send`. The alerts follow through `reply.send` too. This is the spec's "loses its later progress edits, never its result".
  - **Slash-only fix:** today's `/check` re-joins its options into tokens. The typed path passes them straight through. `_min_from_option` keeps today's token rule (`str(n).isdigit()`), so a negative `min_strategies` is still ignored.

- [ ] **Step 0: Confirm the chain position**

```bash
git -C $WT grep -n 'name="top"\|name="soak"' -- swingbot/commands/slash.py
git -C $WT grep -n "@bot.tree.command" -- swingbot/commands/slash.py
```

Expected: the first is **empty** (SP15 landed; otherwise stop and report `BLOCKED: SP15 missing`). The second shows exactly two hits, `name="check"` and `name="stop"`. If `/notify` is still listed, SP4 did not run: stop and report `BLOCKED: SP4 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/scanning.py`:

```python
"""Reply-parity cases for swingbot/commands/scanning/commands.py (v153 SP16)."""
import datetime as dt

from swingbot.bot_core import bot
from swingbot.commands.scanning import commands as commands_mod
from tests.commands.reply_harness import ParityCase

_FUNNEL = {"scenarios_found": 7, "failed_min_confluence": 3, "failed_min_confidence": 2,
           "conf_level_counts": {4: 1, 5: 1}}


def _trade(number: int, horizon: str = "4w") -> dict:
    return {"id": f"trade-{number}", "ticker": f"T{number:03d}", "opened_at": "2026-08-01T09:30:00+00:00",
            "horizon_key": horizon, "direction": "bullish" if number % 2 else "bearish", "status": "open",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence_level": 3,
            "strategy": "MACD"}


def stub_scan(alerts=(), *, funnel=None, stopped=False, on_scan=lambda: None):
    """run_scan returns `alerts`; every alert sender posts one line per alert
    to its destination, so the destination (the reply) is observable."""
    def stub(monkeypatch):
        async def run_scan(*, horizon_filter, require_confirmation, bot, progress, min_confluence):
            on_scan()
            progress.funnel = funnel
            progress.stopped = stopped
            return list(alerts)

        async def send_each(destination, alerts, **_kw):
            for alert in alerts:
                await destination.send(content=f"alert {alert}")

        async def no_short(destination, **_kw):
            return []
        monkeypatch.setattr(commands_mod.scan_engine, "run_scan", run_scan)
        monkeypatch.setattr(commands_mod, "_send_alerts", send_each)
        monkeypatch.setattr(commands_mod, "send_then_short", send_each)
        monkeypatch.setattr(commands_mod, "post_short_universe", no_short)
    return stub


def _stub_history(trades):
    def stub(monkeypatch):
        monkeypatch.setattr(commands_mod.trade_log, "get_trades", lambda **_kw: list(trades))
    return stub


def _stub_recap(monkeypatch):
    async def post(channel_id_override=None, today=None):
        return None
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)


def _recap_fails(monkeypatch):
    async def post(channel_id_override=None, today=None):
        raise RuntimeError("no trades table")
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)


def _stub_state(*, paused=False, running=False, active=True):
    def stub(monkeypatch):
        monkeypatch.setattr(commands_mod.runstate, "is_scan_paused", lambda: paused)
        monkeypatch.setattr(commands_mod.runstate, "set_scan_paused", lambda value: None)

        async def refresh():
            return None
        monkeypatch.setattr(commands_mod.presence, "_refresh_presence", refresh)
        monkeypatch.setattr(commands_mod.scan_engine, "is_scan_running", lambda: running)
        monkeypatch.setattr(commands_mod.scan_engine, "request_stop", lambda: None)
        monkeypatch.setattr(commands_mod, "in_session", lambda: active)
        monkeypatch.setattr("swingbot.bot_core.in_session", lambda: active)
        monkeypatch.setattr(commands_mod, "_session_now",
                            lambda: dt.datetime(2026, 10, 9, 15, 30, tzinfo=commands_mod.SESSION_TZ))
        monkeypatch.setattr(commands_mod, "load_watchlist", lambda: ["AAPL", "MSFT"])
        monkeypatch.setattr(commands_mod.trade_log, "get_stats", lambda: {"open": 2, "win": 5, "loss": 3})
        # bot.latency is NaN while the bot is not connected; round(NaN) raises.
        monkeypatch.setattr(type(bot), "latency", property(lambda self: 0.042))
    return stub


CASES = [
    ParityCase("scanning_recap_today", commands_mod.handle_recap, stub=_stub_recap, fail_stub=_recap_fails),
    ParityCase("scanning_recap_bad_date", commands_mod.handle_recap, args=("09/10/2026",), expect="error"),
    ParityCase("scanning_check_alerts", commands_mod.handle_check, args=("4w", 2),
               stub=stub_scan(["A", "B"], funnel=_FUNNEL), expect="edit"),
    ParityCase("scanning_check_no_alerts_funnel", commands_mod.handle_check,
               stub=stub_scan([], funnel=_FUNNEL), expect="edit"),
    ParityCase("scanning_check_no_alerts_plain", commands_mod.handle_check, stub=stub_scan([]), expect="edit"),
    ParityCase("scanning_check_stopped", commands_mod.handle_check,
               stub=stub_scan(["A"], stopped=True), expect="edit"),
    ParityCase("scanning_check_historical", commands_mod.handle_check, args=("4w",),
               kwargs={"date_from": "2026-08-01", "date_to": "2026-08-31"},
               stub=_stub_history([_trade(i) for i in range(30)] + [_trade(99, "2w")]), expect="multi_send"),
    ParityCase("scanning_check_historical_empty", commands_mod.handle_check,
               kwargs={"date_from": "2027-01-01"}, stub=_stub_history([_trade(1)])),
    ParityCase("scanning_session", commands_mod.handle_session, stub=_stub_state(paused=True)),
    ParityCase("scanning_status", commands_mod.handle_status, stub=_stub_state(active=False)),
    ParityCase("scanning_pause", commands_mod.handle_pause, stub=_stub_state(paused=False)),
    ParityCase("scanning_pause_already", commands_mod.handle_pause, stub=_stub_state(paused=True)),
    ParityCase("scanning_resume", commands_mod.handle_resume, stub=_stub_state(paused=True)),
    ParityCase("scanning_resume_already", commands_mod.handle_resume, stub=_stub_state(paused=False)),
    ParityCase("scanning_stop", commands_mod.handle_stop, stub=_stub_state(running=True)),
    ParityCase("scanning_stop_nothing_running", commands_mod.handle_stop, stub=_stub_state(running=False)),
]
```

- [ ] **Step 2: Update the existing test and write the v153 tests (failing)**

In `$WT/tests/commands/test_commands_check.py`, add `from swingbot.commands.reply import CtxReply` below the `commands_mod` import, and change line 32 to:

```python
    asyncio.run(commands_mod._check_historical(CtxReply(ctx), "all", "2026-08-01", "2026-08-31"))
```

`CtxReply.send` passes `content` positionally, so the test's `call.args[0]` reads still hold. Then append:

```python


# --- v153 SP16: handlers, edit semantics, the stale token, tips and twins -------

import datetime as dt
import inspect

from swingbot.bot_core import bot
from swingbot.commands import reply as reply_mod
from swingbot.commands.reply import TOKEN_LIFETIME_S, InteractionReply
from tests.commands.parity_cases.scanning import _FUNNEL, stub_scan
from tests.commands.reply_harness import FakeContext, FakeInteraction, run_both


def _tip_window_open(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def _edits(events):
    return [event[1] for event in events if event[0] == "edit"]


def test_check_edits_the_progress_handle_identically_on_both_surfaces(monkeypatch):
    stub_scan(["A", "B"], funnel=_FUNNEL)(monkeypatch)

    run = run_both(lambda reply: commands_mod.handle_check(reply, "4w", 2), monkeypatch)

    assert _edits(run.ctx_events) == _edits(run.inter_events) == [
        "🔬 Scan complete — building results…",
        "✅ **2 qualifying trade(s)** (min Lv{lv}, min strategies: 2)  •  confidence breakdown: Lv4:1  Lv5:1".format(
            lv=commands_mod.config.MIN_ALERT_CONFIDENCE_LEVEL),
    ]
    sends = [event[1] for event in run.ctx_events if event[0] == "send"]
    assert sends[0].startswith("🔬 Scanning `4w` · min confidence Lv")
    assert sends[1:] == ["alert A", "alert B"]


def test_stale_check_posts_its_summary_and_alerts_as_fresh_channel_messages(monkeypatch):
    now = [0.0]

    def outlive_the_token():
        now[0] = TOKEN_LIFETIME_S + 1.0

    stub_scan(["A"], funnel=_FUNNEL, on_scan=outlive_the_token)(monkeypatch)
    events: list = []
    interaction = FakeInteraction(events)
    reply = InteractionReply(interaction, clock=lambda: now[0])

    asyncio.run(commands_mod.handle_check(reply))

    summary = [event for event in events if (event[1] or "").startswith("✅")]
    assert [event[0] for event in summary] == ["send"]
    assert not any(event[0] == "edit" for event in events)
    assert interaction.calls[-2:] == ["channel.send", "channel.send"]
    assert events[-1][1] == "alert A"


def test_prefix_check_parses_tokens_into_the_handler(monkeypatch):
    seen = {}

    async def fake(reply, *args):
        seen["args"] = args
    monkeypatch.setattr(commands_mod, "handle_check", fake)

    asyncio.run(commands_mod.check_cmd.callback(FakeContext([]), "4W", "3", "from:2026-08-01", "junk"))

    assert seen["args"] == ("4w", 3, "2026-08-01", None)


def test_check_prefix_answer_ends_with_the_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    stub_scan([])(monkeypatch)
    events: list = []

    asyncio.run(commands_mod.check_cmd.callback(FakeContext(events, qualified_name="check")))

    assert events[-1][1] == "Tip: this is now /check"


def test_recap_posts_to_the_invoking_channel_on_both_surfaces(monkeypatch):
    channels = []

    async def post(channel_id_override=None, today=None):
        channels.append(channel_id_override)
    monkeypatch.setattr(commands_mod.recap, "_post_retrospective", post)

    run_both(lambda reply: commands_mod.handle_recap(reply, "2026-10-09"), monkeypatch)

    assert channels == [10, 10]  # FakeContext / FakeInteraction default channel_id


def test_bad_recap_date_answers_once_without_a_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    events: list = []

    asyncio.run(commands_mod.recap_cmd.callback(FakeContext(events, qualified_name="recap"), "tomorrow"))

    assert [event[1] for event in events] == ["⚠️ Unrecognised date `tomorrow`. Use YYYY-MM-DD."]


def test_stop_logs_the_invoking_user_on_both_surfaces(monkeypatch, caplog):
    import logging
    monkeypatch.setattr(commands_mod.scan_engine, "is_scan_running", lambda: True)
    monkeypatch.setattr(commands_mod.scan_engine, "request_stop", lambda: None)

    with caplog.at_level(logging.INFO, logger=commands_mod.log.name):
        run_both(commands_mod.handle_stop, monkeypatch)

    assert [r.getMessage() for r in caplog.records if "Stop requested" in r.getMessage()] == [
        "Stop requested via !stop (by user1).", "Stop requested via !stop (by user1)."]


def test_scanning_twins_live_in_commands_py_and_slash_py_holds_none():
    from swingbot.commands import slash
    from swingbot.commands.scanning import commands as module

    assert "@bot.tree.command" not in inspect.getsource(slash)
    for name in ("check", "stop", "recap", "session", "status", "pause", "resume"):
        assert bot.tree.get_command(name) is getattr(module, f"slash_{name}")
    assert slash.HORIZON_CHOICES  # tests/market/test_v113_horizon_vocab.py reads it


def test_no_context_bridge_is_left_in_the_commands_package():
    import pathlib
    root = pathlib.Path(commands_mod.__file__).resolve().parents[1]
    offenders = [str(p) for p in root.rglob("*.py") if "from_interaction" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_moved_check_and_stop_keep_their_payload():
    check = commands_mod.slash_check
    assert check.description == "Live scan or historical review of recorded trade plans"
    assert [p.name for p in check.parameters] == ["horizon", "min_strategies", "from_date", "to_date"]
    assert commands_mod.slash_stop.description == "Stop whatever scan is currently running"
    assert commands_mod.slash_stop.parameters == []


def test_slash_check_passes_typed_options_and_drops_a_negative_minimum(monkeypatch):
    from discord import app_commands
    seen = {}

    async def fake(reply, *args):
        seen["args"] = args
    monkeypatch.setattr(commands_mod, "handle_check", fake)

    asyncio.run(commands_mod.slash_check.callback(
        FakeInteraction([]), horizon=app_commands.Choice(name="4w", value="4w"),
        min_strategies=-1, from_date=None, to_date="2026-08-31"))

    assert seen["args"] == ("4w", None, None, "2026-08-31")
```

In `$WT/tests/scanning/test_short_lane_scan.py`, change line 288 to:

```python
    assert "send_then_short(reply, alerts" in inspect.getsource(commands._finish_check)
```

- [ ] **Step 3: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_commands_check.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
```

Expected: the first two fail at collection (`AttributeError: ... has no attribute 'handle_recap'` / `stub_scan` import); the third fails on `commands._finish_check`.

- [ ] **Step 4: Rewrite `scanning/commands.py`**

4a. Replace the import block (lines 1-14 today) with:

```python
import asyncio
import datetime as dt
import logging
import time

import discord
from discord import app_commands

from swingbot import config
from swingbot.bot_core import SESSION_TZ, bot, in_session
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.market.strategy import LEGACY_HORIZONS
from swingbot.core.marketdata.watchlist import load_watchlist
from . import presence, recap, runstate
from .alerts import _send_alerts, post_short_universe, send_then_short
```

`slash.py` imports no command module, so this is not circular. `bot.py` imports `scanning` first; that now imports `slash.py` early, which only registers the tree error handler.

4b. Replace `recap_cmd` (lines 22-45 today) with:

```python
async def handle_recap(reply, date_arg: str = "") -> None:
    import datetime as _dt
    today = None
    if date_arg:
        try:
            today = _dt.date.fromisoformat(date_arg)
        except ValueError:
            await reply.send_error(f"⚠️ Unrecognised date `{date_arg}`. Use YYYY-MM-DD.")
            return

    await reply.send("⏳ Building retrospective…")
    try:
        await recap._post_retrospective(channel_id_override=reply.channel.id, today=today)
    except Exception as exc:
        log.exception("!recap failed")
        await reply.send_error(f"❌ Failed to build retrospective: {exc}")


@bot.command(name="recap")
async def recap_cmd(ctx, date_arg: str = ""):
    """
    Post today's (or a specific day's) retrospective on demand.

    Usage:
      !recap              → today in Berlin time
      !recap 2026-07-04   → specific date (YYYY-MM-DD)
    """
    reply = CtxReply(ctx)
    await handle_recap(reply, date_arg)
    await send_prefix_tip(ctx, reply)
```

4c. Replace `check_cmd` and `_check_historical` (lines 48-294 today) with the code below. Every user-facing string is today's; the label chain, the funnel text and the per-plan line are split out verbatim.

```python
def _parse_check_args(args) -> tuple[str, int | None, str | None, str | None]:
    """!check's free-form tokens -> (horizon, min_confluence, date_from, date_to)."""
    horizon = "all"
    min_confluence = None
    date_from = date_to = None
    for token in args:
        tl = token.lower()
        if tl in ("all", *LEGACY_HORIZONS):
            horizon = tl
        elif tl.startswith("from:"):
            date_from = token[5:]
        elif tl.startswith("to:"):
            date_to = token[3:]
        elif tl.isdigit():
            min_confluence = int(tl)
    return horizon, min_confluence, date_from, date_to


@bot.command(name="check")
async def check_cmd(ctx, *args: str):
    """
    Live scan with optional date filtering.

    Usage:
      !check [horizon] [min_strategies] [from:YYYY-MM-DD] [to:YYYY-MM-DD]

    When from:/to: are given, queries the trade log for plans recorded in
    that window instead of running a live scan.
    Examples:
      !check
      !check 4w
      !check 4w 2
      !check from:2024-01-01 to:2024-12-31
      !check 4w from:2024-06-01
    """
    reply = CtxReply(ctx)
    await handle_check(reply, *_parse_check_args(args))
    await send_prefix_tip(ctx, reply)


async def handle_check(reply, horizon: str = "all", min_confluence: int | None = None,
                       date_from: str | None = None, date_to: str | None = None) -> None:
    """Live scan, or (with a date bound) the recorded plans in that window."""
    await reply.defer()
    if date_from or date_to:
        await _check_historical(reply, horizon, date_from, date_to)
        return
    await _check_live(reply, horizon, min_confluence)


def _min_strats_bit(min_confluence: int | None) -> str:
    return f", min strategies: {min_confluence}" if min_confluence else ""


def _check_intro(horizon: str, min_lv: int, min_confluence: int | None) -> str:
    return (
        f"🔬 Scanning `{horizon}` · min confidence Lv{min_lv}"
        + (f" · min strategies {min_confluence}" if min_confluence else "")
        + " · starting…"
    )


def _elapsed_str(scan_started: float) -> str:
    secs = round(time.monotonic() - scan_started)
    return f"{secs}s" if secs < 60 else f"{secs // 60}m{secs % 60:02d}s"


def _crawl_label(progress, elapsed: str) -> str:
    ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
    pct = round(progress.done / progress.total * 100) if progress.total else 0
    return (
        f"📡 **Crawling** — {progress.done}/{progress.total} ticker(s) fetched "
        f"({pct}%){ticker_bit} · ⏱️ {elapsed}"
    )


def _analyze_label(progress, horizon: str, elapsed: str) -> str:
    ticker_bit = f" `{progress.current_ticker}`" if progress.current_ticker else ""
    found_bit = f" · **{progress.qualifying_found} qualifying** so far" if progress.qualifying_found else ""
    return (
        f"🔬 **Analyzing** ({horizon}) — {progress.done}/{progress.total} ticker·horizon combo(s) "
        f"({progress.pct}%){ticker_bit}{found_bit} · ⏱️ {elapsed}"
    )


def _progress_label(progress, horizon: str, elapsed: str) -> str:
    if progress.stage == "starting":
        # ScanProgress's own default stage, before _sync_run_scan's
        # background thread has done anything -- most commonly because
        # another scan (the automatic session scan, or a concurrent !check)
        # is still holding _scan_lock. Without this branch the generic
        # "Analyzing" label fires instead, showing a literal "0/0 (0%)"
        # that reads identically to a genuinely stuck scan (v56).
        return f"⏳ **Waiting to start** (queued behind another scan) · ⏱️ {elapsed}"
    if progress.stage == "crawling data":
        return _crawl_label(progress, elapsed)
    if progress.stage == "building alerts":
        if progress.alerts_total:
            return (
                f"📊 **Building alerts** — {progress.alerts_done}/{progress.alerts_total} done "
                f"(generating charts…) · ⏱️ {elapsed}"
            )
        return (
            f"📊 **Deduplicating** — {progress.qualifying_found} qualifying "
            f"scenario(s) found, merging similar setups… · ⏱️ {elapsed}"
        )
    if progress.stage == "analyzing" and progress.done == 0 and progress.current_ticker is None:
        # Market regime (SPY vs its 200-day EMA) is fetched once, right
        # before the per-ticker loop starts -- without this branch the
        # message would sit on "0/N tickers (0%)", which reads as "stuck".
        return f"🌐 **Checking market regime** (SPY vs 200-day EMA)… · ⏱️ {elapsed}"
    return _analyze_label(progress, horizon, elapsed)


async def _poll_check_progress(reply, progress_msg, progress, horizon: str, scan_started: float) -> None:
    """Edit the progress message as scan stages advance, until cancelled.
    Stops once the interaction token is stale: its webhook message can no
    longer be edited (a prefix reply is never stale)."""
    last_shown = None
    while not reply.stale:
        # Progress labels change only as scan stages advance; a two-second
        # cadence remains responsive without needlessly consuming Discord
        # edit rate-limit capacity during a long scan.
        await asyncio.sleep(2.0)
        label = _progress_label(progress, horizon, _elapsed_str(scan_started))
        if label == last_shown or reply.stale:
            continue
        try:
            await progress_msg.edit(content=label)
        except discord.NotFound:
            return
        last_shown = label


async def _check_live(reply, horizon: str, min_confluence: int | None) -> None:
    min_lv = config.MIN_ALERT_CONFIDENCE_LEVEL
    progress = scan_engine.ScanProgress()
    scan_started = time.monotonic()
    progress_msg = await reply.send(_check_intro(horizon, min_lv, min_confluence))

    poller = asyncio.create_task(_poll_check_progress(reply, progress_msg, progress, horizon, scan_started))
    try:
        alerts = await scan_engine.run_scan(
            horizon_filter=horizon, require_confirmation=False, bot=bot, progress=progress,
            min_confluence=min_confluence,
        )
    finally:
        poller.cancel()
    await _finish_check(reply, progress_msg, progress, alerts, min_lv, min_confluence)


async def _show_result(reply, progress_msg, content: str) -> None:
    """Turn the progress message into a result line. A stale interaction
    token cannot edit, so the result goes out as a fresh send instead."""
    if reply.stale:
        await reply.send(content)
    else:
        await progress_msg.edit(content=content)


def _no_alerts_text(f: dict | None, min_lv: int, min_confluence: int | None) -> str:
    base = f"📭 **No qualifying trades** right now (min confidence: Lv{min_lv}" + _min_strats_bit(min_confluence)
    if not (f and f.get("scenarios_found", 0) > 0):
        return base + ")."
    not_ready_parts = []
    if f.get("failed_min_confluence", 0):
        not_ready_parts.append(f"{f['failed_min_confluence']} below min strategies")
    if f.get("failed_min_confidence", 0):
        not_ready_parts.append(f"{f['failed_min_confidence']} below min confidence (Lv{min_lv}+)")
    not_ready_str = (", ".join(not_ready_parts) + " — ") if not_ready_parts else ""
    return base + f").\n{not_ready_str}{f['scenarios_found']} scenario(s) analyzed."


def _check_summary(alerts: list, f: dict | None, min_lv: int, min_confluence: int | None) -> str:
    lv_counts = f.get("conf_level_counts", {}) if f else {}
    lv_breakdown = (
        "  ".join(f"Lv{lv}:{cnt}" for lv, cnt in sorted(lv_counts.items()))
        if lv_counts else "none"
    )
    return (
        f"✅ **{len(alerts)} qualifying trade(s)** (min Lv{min_lv}"
        + _min_strats_bit(min_confluence)
        + f")  •  confidence breakdown: {lv_breakdown}"
    )


async def _finish_check(reply, progress_msg, progress, alerts: list, min_lv: int,
                        min_confluence: int | None) -> None:
    """Result line on the progress message, then the alerts to the caller (`reply`)."""
    if progress.stopped:
        await _show_result(
            reply, progress_msg,
            f"🛑 **Scan stopped early** (use `!stop` to cancel a scan in progress) — "
            f"{len(alerts)} alert(s) built from what completed before the stop.",
        )
        if alerts:
            await _send_alerts(reply, alerts)
        return

    if not reply.stale:
        await progress_msg.edit(content="🔬 Scan complete — building results…")

    if not alerts:
        await _show_result(reply, progress_msg, _no_alerts_text(progress.funnel, min_lv, min_confluence))
        await post_short_universe(reply, bot=bot, require_confirmation=False)
        return

    await _show_result(reply, progress_msg, _check_summary(alerts, progress.funnel, min_lv, min_confluence))
    await send_then_short(reply, alerts, bot=bot, require_confirmation=False)


def _historical_line(t: dict) -> str:
    direction_emoji = "📈" if t.get("direction") == "bullish" else "📉"
    status_emoji = {"open": "🟡", "win": "✅", "loss": "❌", "closed": "⬜"}.get(t.get("status", ""), "⬜")
    entry   = t.get("entry_price", t.get("entry", "?"))
    stop    = t.get("stop_loss", "?")
    target  = t.get("take_profit", "?")
    lv      = t.get("confidence_level", "?")
    strats  = t.get("strategy", "?")
    horizon_k = t.get("horizon_key", "?")
    opened  = t.get("opened_at", "?")[:10]
    ticker  = t.get("ticker", "?")
    tid     = t.get("id", "?")
    return (
        f"{direction_emoji} {status_emoji} **{ticker}** `{horizon_k}` — "
        f"Lv{lv} · {strats}\n"
        f"Entry **{entry}** · Stop {stop} · Target {target}\n"
        f"Opened: {opened}  `ID: {tid}`  — use `!trade {tid}` for full details & chart"
    )


def _pack_messages(lines: list[str]) -> list[str]:
    """Pack lines into Discord-safe messages instead of one request per plan."""
    messages, chunk, chunk_len = [], [], 0
    for line in lines:
        line_len = len(line) + (2 if chunk else 0)
        if chunk and chunk_len + line_len > _DISCORD_MESSAGE_LIMIT:
            messages.append("\n\n".join(chunk))
            chunk, chunk_len = [], 0
            line_len = len(line)
        chunk.append(line)
        chunk_len += line_len
    if chunk:
        messages.append("\n\n".join(chunk))
    return messages


async def _check_historical(reply, horizon: str, date_from: str | None, date_to: str | None):
    """Show trade plans recorded in the trade log within a date window."""
    from_dt = date_from or "0000-01-01"
    to_dt   = date_to   or "9999-12-31"

    all_trades = trade_log.get_trades(status=None, limit=None)

    # Filter by opened_at date and optional horizon
    def _in_range(t):
        opened = t.get("opened_at", "")[:10]  # YYYY-MM-DD
        if opened < from_dt or opened > to_dt:
            return False
        if horizon != "all" and t.get("horizon_key") != horizon:
            return False
        return True

    trades = [t for t in all_trades if _in_range(t)]

    range_str = f"{date_from or '…'} → {date_to or 'now'}"
    horiz_str = f" · horizon `{horizon}`" if horizon != "all" else ""

    if not trades:
        await reply.send(
            f"📭 No recorded trade plans found for **{range_str}**{horiz_str}.\n"
            "Trade plans are only recorded when the bot posts an alert (or you run `!check`)."
        )
        return

    total = len(trades)
    displayed = trades[:_HISTORICAL_CHECK_MAX_RESULTS]
    truncation = (
        f" Showing the first {_HISTORICAL_CHECK_MAX_RESULTS}; narrow the date range or horizon for the rest."
        if total > len(displayed) else ""
    )
    header = (
        f"📋 **{total} recorded trade plan(s)** — {range_str}{horiz_str}.{truncation}\n"
        "*(from the trade log — these are plans the bot actually posted)*\n"
    )
    await reply.send(header)

    # The display cap above bounds request pressure for broad ranges.
    for message in _pack_messages([_historical_line(t) for t in displayed]):
        await reply.send(message)
```

4d. Replace `session_cmd`, `status_cmd`, `pause_cmd`, `resume_cmd` and `stop_cmd` (line 297 today to the end of the file) with:

```python
def _session_now() -> dt.datetime:
    """Seam for tests (monkeypatched)."""
    return dt.datetime.now(SESSION_TZ)


async def handle_session(reply) -> None:
    from swingbot.bot_core import in_session
    now = _session_now()
    active = in_session()
    start = config.SESSION_START_HOUR
    end = config.SESSION_END_HOUR
    status = "🟢 **Active**" if active else "🔴 **Inactive**"
    paused_bit = "\n⏸️ **Scanning is paused** — use `!resume` or the admin UI to resume." if runstate.is_scan_paused() else ""
    await reply.send(
        f"{status} — session window: {start:02d}:00–{end:02d}:00 Europe/Berlin (Mon-Fri)\n"
        f"Current time: {now.strftime('%Y-%m-%d %H:%M %Z')}{paused_bit}"
    )


async def handle_status(reply) -> None:
    wl = load_watchlist()
    stats = trade_log.get_stats()
    active = in_session()
    session_status = "🟢 active" if active else "🔴 inactive"
    latency_ms = round(bot.latency * 1000) if bot.latency else None
    paused = runstate.is_scan_paused()
    scan_line = "⏸️ **paused** (manual !check still works)" if paused else "▶️ running"
    await reply.send(
        f"**Bot status**\n"
        f"Automatic scanning: {scan_line}\n"
        f"Session: {session_status} ({config.SESSION_START_HOUR:02d}:00–{config.SESSION_END_HOUR:02d}:00 Berlin)\n"
        f"Watchlist: {len(wl)} ticker(s)\n"
        f"Open positions: {stats['open']} / {config.MAX_OPEN_POSITIONS} max\n"
        f"Closed trades: {stats.get('win', 0)} wins · {stats.get('loss', 0)} losses\n"
        f"Min confidence: Lv{config.MIN_ALERT_CONFIDENCE_LEVEL} · "
        f"Min strategies: {config.MIN_TARGET_CONFLUENCE_COUNT}\n"
        f"Gateway latency: {latency_ms}ms" + (" ⚠️ high" if latency_ms and latency_ms > 300 else "")
    )


async def handle_pause(reply) -> None:
    """Pause the automatic background scan loop. Manual !check still works."""
    if runstate.is_scan_paused():
        await reply.send("⏸️ Scanning is already paused.")
        return
    runstate.set_scan_paused(True)
    log.info("Automatic scanning paused via !pause (by %s).", reply.author)
    await presence._refresh_presence()
    await reply.send(
        "⏸️ **Automatic scanning paused.** The bot will stop posting scheduled alerts. "
        "`!check` still works on demand. Use `!resume` or the admin UI to turn it back on."
    )


async def handle_resume(reply) -> None:
    """Resume the automatic background scan loop after a !pause."""
    if not runstate.is_scan_paused():
        await reply.send("▶️ Scanning is already running.")
        return
    runstate.set_scan_paused(False)
    log.info("Automatic scanning resumed via !resume (by %s).", reply.author)
    await presence._refresh_presence()
    await reply.send("▶️ **Automatic scanning resumed.**")


async def handle_stop(reply) -> None:
    """
    Stop whatever scan is currently in progress (!check, /check, the
    admin UI's "Run !check now" trigger, or the automatic session scan).

    Different from !pause: !pause only stops FUTURE automatic scans from
    starting -- a scan already running keeps going. !stop cuts short a
    scan that's already running, right now. It's cooperative (checked
    once per ticker inside scan_engine's crawl/analyze/alert-building
    loops), so it takes effect at the next checkpoint, not instantly --
    there's no way to forcibly kill a scan mid-fetch.
    """
    if not scan_engine.is_scan_running():
        await reply.send("ℹ️ No scan is currently running.", ephemeral=True)
        return
    scan_engine.request_stop()
    log.info("Stop requested via !stop (by %s).", reply.author)
    await reply.send("🛑 **Stop requested** — the running scan will end after finishing its current ticker.")


# Each prefix command calls its handler itself (the index's prefix pattern),
# so SP18's one-body check sees the call inside the command.

@bot.command(name="session")
async def session_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_session(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="status")
async def status_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_status(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="pause")
async def pause_cmd(ctx):
    """Pause the automatic background scan loop. Manual !check still works."""
    reply = CtxReply(ctx)
    await handle_pause(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="resume")
async def resume_cmd(ctx):
    """Resume the automatic background scan loop after a !pause."""
    reply = CtxReply(ctx)
    await handle_resume(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="stop")
async def stop_cmd(ctx):
    """Stop whatever scan is currently in progress (see handle_stop)."""
    reply = CtxReply(ctx)
    await handle_stop(reply)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (/check and /stop moved from slash.py in v153, payload
# unchanged; /recap /session /status /pause /resume new)
# ──────────────────────────────────────────────

def _min_from_option(n: int | None) -> int | None:
    """Today's token rule: `str(n).isdigit()` -- a negative minimum is ignored."""
    return n if n is not None and n >= 0 else None


@bot.tree.command(name="check", description="Live scan or historical review of recorded trade plans")
@app_commands.describe(
    horizon="Swing horizon (default: all)",
    min_strategies="Override min confirmed strategies for this run (live mode only)",
    from_date="Start date YYYY-MM-DD — enables historical mode, shows recorded plans",
    to_date="End date YYYY-MM-DD — use with from_date for a specific window",
)
@app_commands.choices(horizon=HORIZON_CHOICES)
async def slash_check(
    interaction: discord.Interaction,
    horizon: app_commands.Choice[str] = None,
    min_strategies: int = None,
    from_date: str = None,
    to_date: str = None,
):
    await handle_check(
        InteractionReply(interaction), horizon.value if horizon else "all",
        _min_from_option(min_strategies), from_date or None, to_date or None,
    )


@bot.tree.command(name="stop", description="Stop whatever scan is currently running")
async def slash_stop(interaction: discord.Interaction):
    await handle_stop(InteractionReply(interaction))


@bot.tree.command(name="recap", description="Post today's (or a given day's) retrospective in this channel")
@app_commands.describe(date="Day to recap, YYYY-MM-DD (default: today, Berlin time)")
async def slash_recap(interaction: discord.Interaction, date: str = None):
    await handle_recap(InteractionReply(interaction), date or "")


@bot.tree.command(name="session", description="Show the scan session window and whether it is active now")
async def slash_session(interaction: discord.Interaction):
    await handle_session(InteractionReply(interaction))


@bot.tree.command(name="status", description="Bot status: scanning, session, watchlist, open positions, latency")
async def slash_status(interaction: discord.Interaction):
    await handle_status(InteractionReply(interaction))


@bot.tree.command(name="pause", description="Pause the automatic background scan loop (manual /check still works)")
async def slash_pause(interaction: discord.Interaction):
    await handle_pause(InteractionReply(interaction))


@bot.tree.command(name="resume", description="Resume the automatic background scan loop")
async def slash_resume(interaction: discord.Interaction):
    await handle_resume(InteractionReply(interaction))
```

`trade_log`, `_HISTORICAL_CHECK_MAX_RESULTS` and `_DISCORD_MESSAGE_LIMIT` stay where they are (module top, lines 18-20 today).

- [ ] **Step 5: Empty `slash.py` of commands and trim it**

5a. In `$WT/swingbot/commands/slash.py`, delete the `/check` banner and the whole `slash_check` command (its long docstring included), and the `/stop` banner and the whole `slash_stop` command.

5b. Replace the module docstring with:

```python
"""
Shared slash-command (/command) building blocks.

Since v153 every slash command lives next to its prefix (!) twin, in the
same module, and both call one shared handle_<name>(reply, ...) handler
(swingbot/commands/reply.py). This module keeps only what several of them
share: the choice lists, and the bot.tree error handler for app-command
check failures. It must never import a command module (they import it).

The tree is synced to Discord once per process start, in on_ready
(swingbot/commands/scanning/loops.py).
"""
```

5c. Remove every import that is now unused. List them with:

```bash
python - <<'PY'
import ast, pathlib
path = pathlib.Path("/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity/swingbot/commands/slash.py")
tree = ast.parse(path.read_text(encoding="utf-8"))
imported = {}
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
print(sorted((line, name) for name, line in imported.items() if name not in used))
PY
```

Expected candidates: `asyncio`, `commands`, `COMMANDS_BY_CATEGORY`, `CONFIDENCE_EXPLAINER`, `ui`, `HORIZONS`, `scan_engine`. Delete each one the script lists, then re-run it until it prints `[]`. Keep `bot` (the error handler's `@bot.tree.error`), `discord`, `app_commands`, `logging` and `live_horizons`.

```bash
git -C $WT grep -n "@bot.tree.command\|from_interaction" -- swingbot/commands/
```

Expected: no hit.

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_commands_check.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_error_handler.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
python $WT/scripts/dev/testrun.py file tests/market/test_v113_horizon_vocab.py
```

Expected: `0 failed`, `0 xfailed` on all eight. The parity file gains 16 `scanning_*` cases and `test_handler_error_parity[scanning_recap_today]`.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/scanning/commands.py $WT/swingbot/commands/slash.py
```

Expected: no output. `check_cmd` D(23) and `_check_historical` C(17) are gone: their bodies are now `handle_check`, `_check_live`, `_progress_label` (about B8), `_finish_check`, `_no_alerts_text`, `_pack_messages` and `_historical_line`, each below C. Paste the output into the task report. If `_progress_label` or `_finish_check` lands at C, split the next branch into a named helper; do not change a string.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/scanning/commands.py swingbot/commands/slash.py tests/commands/parity_cases/scanning.py tests/commands/test_commands_check.py tests/scanning/test_short_lane_scan.py
git -C $WT commit -m "feat(v153): SP16 scanning handlers; /check and /stop leave slash.py, /recap /session /status /pause /resume new"
```

