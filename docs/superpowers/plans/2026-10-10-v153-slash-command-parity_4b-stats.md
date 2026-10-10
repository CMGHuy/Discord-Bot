# v153 Slash command parity. Part 4b: `slash.py` chain II (continued: `stats`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here.

This task continues the `slash.py` chain. It was split out of part 4 (`..._4-backtest-watchlist-stats-scanning.md`) only for the 1500-line file cap (audit 2026-10-10). The "Shared conventions for this part" block at the top of part 4 applies here unchanged: `$WT`, the SP1 names, the `ParityCase.expect` meanings, `send_error` for validation, `defer()` after validation, verbatim decorators for moved twins, and radon over every touched file. SP15 runs after SP14; part 4c's SP16 runs after it.

# Phase 4: `slash.py` chain II (continued)

### Task SP15: `stats`: soak, top, stats, lessons, calibration, journal

**Model:** sonnet — six body moves onto handlers in one module, two new twins and four verbatim twin moves; `stats_cmd` and `lessons_cmd` split along their existing branches with no logic change.

**Cross-plan (audit 2026-10-10):** if `git -C $WT grep -n PLAN_TEMPLATE_RE -- swingbot/commands/views.py` prints a line (v152 merged), v152's persistent panel only accepts a 36-char dashed UUID plan id and a 17–20-digit author id in its `custom_id`: the `!top` fixtures (`_plan(...)` ids used by `stats_top_panels` and `test_top_panel_is_locked_to_the_invoking_user_on_both_surfaces`) use UUID plan ids, the `FakeContext`/`FakeInteraction` user id is an 18-digit snowflake (the `views == [1, 1]` assertion uses that id), and the panel test also asserts `view.children` is non-empty. Otherwise write the fixtures as planned.

**Files:**
- Modify: `swingbot/commands/stats.py` (imports at lines 5-18 today; `soak_cmd` 41-51, `top_cmd` 110-124, `stats_cmd` 206-260, `lessons_cmd` 284-314, `calibration_cmd` 330-368, `journal_cmd` 378-395)
- Modify: `swingbot/commands/slash.py` (delete `/top`, `/stats`, `/soak`, `/lessons`; locate with `git -C $WT grep -n 'name="top"\|name="stats"\|name="soak"\|name="lessons"' -- swingbot/commands/slash.py`)
- Create: `tests/commands/parity_cases/stats.py`
- Modify: `tests/commands/test_stats_commands.py` (one import line in `test_new_slash_commands_registered_on_tree`; a v153 block appended at the end of the file)
- Modify: `tests/commands/test_slash_commands.py` (one import line in `test_soak_slash_registered`)

`tests/admin/test_v144_pooled_readers.py:57` and `tests/commands/test_stats_commands.py:228-244` drive `soak_cmd.callback` with a `MagicMock` ctx. Its `ctx.command.qualified_name` is not a `str`, so `send_prefix_tip` sends nothing and both stay green **unchanged** (index, Global Constraints). Step 6 runs them to prove it.

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `PREFIX_TIP_UNTIL`, `reply._today`; `ParityCase`, `FakeContext`, `run_both`, `comparable`. Consumes `slash.PERIOD_CHOICES` (stays in `slash.py`).
- Produces (ledger): `handle_soak(reply, strategy: str)`, `handle_top(reply, n: int | None = None)`, `handle_stats(reply, period: str = "all")`, `handle_lessons(reply, arg: str = "5")`, `handle_calibration(reply)`, `handle_journal(reply, target: str, note: str | None = None)`. Private helpers `_stats_all`, `_stats_period`, `_lessons_week`, `_lessons_recent`. Twins: `/top` (`slash_top`), `/stats` (`slash_stats`), `/soak` (`slash_soak`) and `/lessons` (`slash_lessons`) moved with their decorators verbatim; `/calibration` (`slash_calibration`) and `/journal` (`slash_journal`) new.
- Unchanged names other code reads: `soak_lines`, `top_plans`, `_fake_item_from_plan`, `_mini_table`, `stats_embed`, `_since`, `lessons_lines`, `_tag_cloud`, `calibration_lines`, `_journal_note_result`, `LIVE_STATUSES`, `_plan_store` (the daily digest and `test_send_alerts_v110.py` / `test_posted_log.py` patch `stats._fake_item_from_plan`).
- Output:
  - Every `!` text is unchanged; the tip follows a successful answer.
  - `!stats <bad period>` and `!lessons <not a number>` answer the same text through `send_error`, with no tip.
  - `!top` attaches `PlanActionView(plan.plan_id, author_id=reply.author.id)`, the same id as `ctx.author.id`.
  - Every parity stub freezes `discord.utils.utcnow` (`_freeze_clock`, the part 3 pattern): `ui.apply_chrome` stamps it on the `!stats <period>` and `!calibration` embeds, and the harness runs each handler twice.
  - Every chart render stays inside its `lambda target: render_…(…)` line, passed to `asyncio.to_thread(cached_chart, …)`. `test_no_direct_chart_render_calls_outside_to_thread` scans this module line by line, so keep those lines intact.

- [ ] **Step 0: Confirm the chain position**

```bash
git -C $WT grep -n 'name="watchlist"' -- swingbot/commands/slash.py
git -C $WT grep -n "PlanActionView(" -- swingbot/commands/stats.py
git -C $WT log --oneline -5 -- swingbot/commands/stats.py
```

Expected: the first is **empty** (SP14 landed; otherwise stop and report `BLOCKED: SP14 missing`). The second shows exactly `view = PlanActionView(plan.plan_id, author_id=ctx.author.id)` inside `top_cmd`.

(No v152 dependency: v152 does not edit `stats.py` — its `PlanActionView` keeps its constructor signature — so this task never waits for v152. If the `PlanActionView(` line differs from the one above, keep the current line inside `handle_top` and change only `ctx` to `reply`.)

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/stats.py`:

```python
"""Reply-parity cases for swingbot/commands/stats.py (v153 SP15)."""
import datetime as dt
import os
import tempfile
from types import SimpleNamespace

import discord

from swingbot.commands import stats as stats_mod
from swingbot.core.scanning import engine as scan_engine
from tests.commands.reply_harness import ParityCase

_VERDICT = {"n_closed": 31, "exp_r": 0.25, "badge_exp_r": 0.21, "median_entry_dev": 0.04,
            "clauses": {"n": True, "non_inferior": True, "entry_parity": True}, "pass": True}
_ENTRIES = [
    {"trade_id": "T1", "ticker": "AAA", "outcome": "win", "r_realized": 1.5,
     "auto_lesson": "Clean capture.", "tags": ["trend"]},
    {"trade_id": "T2", "ticker": "BBB", "outcome": "loss", "r_realized": -1.0,
     "auto_lesson": "Entry was wrong.", "tags": ["trend", "gap"]},
]


_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)


def _freeze_clock(monkeypatch):
    """ui.apply_chrome stamps discord.utils.utcnow() on every chromed embed
    (presentation/components.py); the handler runs twice, so freeze it."""
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _chart_path() -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-stats-"), "chart.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG")
    return path


def _plan(plan_id: str):
    return SimpleNamespace(plan_id=plan_id, ticker=plan_id.upper(), source="strategy", strategy="MACD",
                           status="PENDING")


def _stub_plans(plans):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        monkeypatch.setattr(stats_mod.PlanStore, "all", lambda self: list(plans))
        monkeypatch.setattr(stats_mod, "is_regular", lambda plan: True)
        monkeypatch.setattr(stats_mod, "market_today", lambda: dt.date(2026, 10, 9))
        monkeypatch.setattr(stats_mod, "top_plans", lambda plans, n, today=None: list(plans)[:n])
        monkeypatch.setattr(stats_mod, "_fake_item_from_plan", lambda plan: plan)
        monkeypatch.setattr(stats_mod, "build_embed",
                            lambda item, *a, **k: discord.Embed(title=item.plan_id))
        monkeypatch.setattr("swingbot.core.backtesting.registry.get_badge",
                            lambda *a, **k: SimpleNamespace(status="VALIDATED"))
        monkeypatch.setattr("swingbot.core.edge.strategy_soak.soak_verdict", lambda plans, badge: dict(_VERDICT))
    return stub


def _stub_snapshot(snap):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        path = _chart_path()
        monkeypatch.setattr("swingbot.core.analytics.snapshots.load_snapshot", lambda: snap)
        monkeypatch.setattr("swingbot.core.analytics.snapshots.refresh_snapshot", lambda: None)
        monkeypatch.setattr(stats_mod, "stats_embed", lambda s: discord.Embed(title="📐 Analytics"))
        monkeypatch.setattr("swingbot.core.charts.cache.cached_chart", lambda key, render: path)
    return stub


def _stub_trades(trades):
    def stub(monkeypatch):
        _freeze_clock(monkeypatch)
        path = _chart_path()
        monkeypatch.setattr(scan_engine.trade_log, "get_trades", lambda **kw: list(trades))
        monkeypatch.setattr("swingbot.core.analytics.metrics.win_rate", lambda t: 50.0)
        monkeypatch.setattr("swingbot.core.analytics.metrics.expectancy_r", lambda t: 0.2)
        monkeypatch.setattr("swingbot.core.analytics.metrics.profit_factor", lambda t: 1.4)
        monkeypatch.setattr("swingbot.core.analytics.calibration.level_calibration",
                            lambda t: [{"level": 5, "n": len(t), "win_rate": 50.0}])
        monkeypatch.setattr("swingbot.core.analytics.calibration.score_deciles",
                            lambda t: [{"decile": 9, "win_rate": 70.0}])
        monkeypatch.setattr("swingbot.core.analytics.insights.edge_decay_report", lambda t: [])
        monkeypatch.setattr("swingbot.core.analytics.insights.weekly_digest",
                            lambda entries, closed, today: ["**Week** part 1", "part 2"])
        monkeypatch.setattr("swingbot.core.charts.cache.cached_chart", lambda key, render: path)
    return stub


class _Journal:
    def entries(self, **kw):
        return [dict(e) for e in _ENTRIES]

    def set_note(self, trade_id, note):
        return trade_id == "T1"


def _stub_journal(monkeypatch):
    monkeypatch.setattr("swingbot.core.analytics.journal.JournalStore", _Journal)
    _stub_trades(_CLOSED)(monkeypatch)


_TODAY = dt.date.today().isoformat()
_CLOSED = [{"status": "win", "closed_at": f"{_TODAY}T15:00:00"},
           {"status": "loss", "closed_at": f"{_TODAY}T16:00:00"}]

CASES = [
    ParityCase("stats_soak_verdict", stats_mod.handle_soak, args=("MACD",), stub=_stub_plans([_plan("p1")])),
    ParityCase("stats_soak_no_plans", stats_mod.handle_soak, args=("MACD",), stub=_stub_plans([])),
    ParityCase("stats_top_panels", stats_mod.handle_top, args=(2,),
               stub=_stub_plans([_plan("p1"), _plan("p2"), _plan("p3")]), expect="multi_send"),
    ParityCase("stats_top_empty", stats_mod.handle_top, stub=_stub_plans([])),
    ParityCase("stats_all_with_chart", stats_mod.handle_stats,
               stub=_stub_snapshot({"built_at": "2026-10-09T08:00:00", "equity_curve": []})),
    ParityCase("stats_all_no_snapshot", stats_mod.handle_stats, stub=_stub_snapshot(None)),
    ParityCase("stats_period_30d", stats_mod.handle_stats, args=("30D",), stub=_stub_trades(_CLOSED)),
    ParityCase("stats_period_empty", stats_mod.handle_stats, args=("7d",), stub=_stub_trades([])),
    ParityCase("stats_period_unknown", stats_mod.handle_stats, args=("fortnight",), stub=_freeze_clock,
               expect="error"),
    ParityCase("stats_lessons_recent", stats_mod.handle_lessons, stub=_stub_journal),
    ParityCase("stats_lessons_week", stats_mod.handle_lessons, args=("week",), stub=_stub_journal,
               expect="multi_send"),
    ParityCase("stats_lessons_not_a_number", stats_mod.handle_lessons, args=("lots",), stub=_freeze_clock,
               expect="error"),
    ParityCase("stats_calibration", stats_mod.handle_calibration, stub=_stub_trades(_CLOSED)),
    ParityCase("stats_calibration_no_trades", stats_mod.handle_calibration, stub=_stub_trades([])),
    ParityCase("stats_journal_note_saved", stats_mod.handle_journal, args=("T1", "watch the gap"),
               stub=_stub_journal),
    ParityCase("stats_journal_ticker_list", stats_mod.handle_journal, args=("aaa",), stub=_stub_journal),
    ParityCase("stats_journal_ticker_unknown", stats_mod.handle_journal, args=("zzz",), stub=_stub_journal),
]
```

- [ ] **Step 2: Write the registration, tip and twin tests (failing)**

In `$WT/tests/commands/test_stats_commands.py`, inside `test_new_slash_commands_registered_on_tree`, add after the `import swingbot.commands.slash` line (and after any module import part 3 added there):

```python
    import swingbot.commands.stats  # noqa: F401  -- v153: /top /stats /lessons moved here
```

In `$WT/tests/commands/test_slash_commands.py`, inside `test_soak_slash_registered`, add after its `import swingbot.commands.slash  # noqa: F401` line:

```python
    import swingbot.commands.stats  # noqa: F401  -- v153: /soak moved here
```

Append to `$WT/tests/commands/test_stats_commands.py`:

```python


# --- v153 SP15: stats handlers, the tip line and the twins ----------------------

def _tip_window_open(monkeypatch):
    from swingbot.commands import reply as reply_mod
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def test_stats_twins_live_in_stats_py():
    import inspect as _inspect

    from swingbot.bot_core import bot
    from swingbot.commands import slash
    from swingbot.commands import stats as stats_mod

    source = _inspect.getsource(slash)
    for name in ("top", "stats", "soak", "lessons"):
        assert f'name="{name}"' not in source, f"/{name} still defined in slash.py"
    for name in ("top", "stats", "soak", "lessons", "calibration", "journal"):
        assert bot.tree.get_command(name) is getattr(stats_mod, f"slash_{name}")


def test_moved_stats_twins_keep_their_payload():
    from swingbot.commands import stats as stats_mod

    assert stats_mod.slash_top.description == "Highest follow-score PENDING/ACTIVE plans"
    assert [p.name for p in stats_mod.slash_top.parameters] == ["n"]
    assert stats_mod.slash_stats.description == "Win rate, expectancy, and risk-adjusted stats"
    assert [c.value for c in stats_mod.slash_stats.parameters[0].choices] == ["7d", "30d", "90d", "ytd", "all"]
    assert stats_mod.slash_soak.description == "v93 trust-rule readout for a strategy's shadow plans"
    assert [(p.name, p.required) for p in stats_mod.slash_soak.parameters] == [("strategy", True)]
    assert stats_mod.slash_lessons.description == "Recent journal entries and their auto-generated lessons"
    assert [p.name for p in stats_mod.slash_lessons.parameters] == ["arg"]


def test_new_journal_twin_takes_target_then_optional_note():
    from swingbot.commands import stats as stats_mod

    assert [(p.name, p.required) for p in stats_mod.slash_journal.parameters] == [
        ("target", True), ("note", False)]
    assert stats_mod.slash_calibration.parameters == []


def test_soak_prefix_answer_ends_with_the_tip(monkeypatch):
    import asyncio

    from swingbot.commands.stats import soak_cmd
    from swingbot.core.planning.plan_store import PlanStore
    from tests.commands.reply_harness import FakeContext

    _tip_window_open(monkeypatch)
    monkeypatch.setattr(PlanStore, "all", lambda self: [])
    events: list = []

    asyncio.run(soak_cmd.callback(FakeContext(events, qualified_name="soak"), strategy="MACD"))

    assert [event[1] for event in events] == [
        "No strategy-sourced plans for `MACD` yet (is STRATEGY_ALERTS_MODE off?).",
        "Tip: this is now /soak",
    ]


def test_bad_stats_period_answers_once_without_a_tip(monkeypatch):
    import asyncio

    from swingbot.commands.stats import stats_cmd
    from tests.commands.reply_harness import FakeContext

    _tip_window_open(monkeypatch)
    events: list = []

    asyncio.run(stats_cmd.callback(FakeContext(events, qualified_name="stats"), "fortnight"))

    assert [event[1] for event in events] == [
        "Unrecognized period `fortnight`. Use one of: 7d, 30d, 90d, ytd, all."]


def test_top_panel_is_locked_to_the_invoking_user_on_both_surfaces(monkeypatch):
    from swingbot.commands import stats as stats_mod
    from tests.commands.parity_cases.stats import _plan, _stub_plans
    from tests.commands.reply_harness import run_both

    _stub_plans([_plan("p1")])(monkeypatch)
    views = []
    real = stats_mod.PlanActionView

    def spy(plan_id, author_id):
        views.append(author_id)
        return real(plan_id, author_id=author_id)
    monkeypatch.setattr(stats_mod, "PlanActionView", spy)

    run_both(lambda reply: stats_mod.handle_top(reply, 1), monkeypatch)

    assert views == [1, 1]  # FakeContext.author.id and FakeInteraction.user.id
```

- [ ] **Step 3: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
```

Expected: the first fails at collection (`AttributeError: module 'swingbot.commands.stats' has no attribute 'handle_soak'`). In the second, the older tests pass and the six new ones fail (`slash_top` missing, no tip, `handle_top` missing).

- [ ] **Step 4: Rewrite the command bodies of `stats.py`**

4a. In the import block, below `import discord`, add:

```python
from discord import app_commands
```

and below `from swingbot.core.analytics.rank import rank_plans`, add:

```python
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import PERIOD_CHOICES
```

Extend the module docstring's first line to read `"""!soak, !top, !stats, !lessons, !calibration, !journal and their slash twins -- the analytics-facing`, keeping the rest of the docstring.

4b. Replace `soak_cmd` (the `@bot.command(name="soak")` block) with:

```python
async def handle_soak(reply, strategy: str) -> None:
    from swingbot.core.backtesting.registry import get_badge
    from swingbot.core.edge.strategy_soak import soak_verdict
    await reply.defer()
    plans = [plan for plan in PlanStore().all()
             if plan.source == "strategy" and plan.strategy == strategy and is_regular(plan)]
    if not plans:
        await reply.send(f"No strategy-sourced plans for `{strategy}` yet (is STRATEGY_ALERTS_MODE off?).")
        return
    badge = get_badge("strategy", strategy)
    await reply.send("\n".join(soak_lines(strategy, soak_verdict(plans, badge), badge)))


@bot.command(name="soak")
async def soak_cmd(ctx, *, strategy: str):
    reply = CtxReply(ctx)
    await handle_soak(reply, strategy)
    await send_prefix_tip(ctx, reply)
```

4c. Replace `top_cmd` with:

```python
async def handle_top(reply, n: int | None = None) -> None:
    n = n or config.DIGEST_MAX_PLANS
    await reply.defer()
    plans = PlanStore().all()
    top = top_plans(plans, n, today=market_today())
    if not top:
        await reply.send("No PENDING/ACTIVE plans right now.")
        return

    await reply.send(f"📌 **Top {len(top)} plan(s) by follow score:**")
    for plan in top:
        item = _fake_item_from_plan(plan)
        embed = build_embed(item, "", {"closed": 0}, None, None, layout="compact")
        view = PlanActionView(plan.plan_id, author_id=reply.author.id)
        view.message = await reply.send(embed=embed, view=view)


@bot.command(name="top")
async def top_cmd(ctx, n: int = None):
    reply = CtxReply(ctx)
    await handle_top(reply, n)
    await send_prefix_tip(ctx, reply)
```

(If Step 0 found a different current `embed = …` / `view = …` line, use the current line here with `ctx` replaced by `reply`.)

4d. Replace `stats_cmd` with the handler and its two branch helpers. The bodies are today's, with `ctx` replaced by `reply`; the chart `lambda` line is unchanged:

```python
async def _stats_all(reply) -> None:
    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot
    import asyncio

    snap = load_snapshot()
    if snap is None:
        await asyncio.to_thread(refresh_snapshot)
        snap = load_snapshot()
    if snap is None:
        await reply.send("No analytics snapshot available yet — not enough closed trades, or the snapshot build failed. Check logs.")
        return

    embed = stats_embed(snap)

    import os

    from swingbot.core.charts.analytics_charts import render_equity_curve
    from swingbot.core.charts.cache import cached_chart

    chart_path = await asyncio.to_thread(
        cached_chart,
        {"kind": "equity_curve", "snapshot_built_at": snap["built_at"]},
        lambda target: render_equity_curve(snap["equity_curve"], os.path.dirname(target), filename=os.path.basename(target)),
    )
    await reply.send(embed=embed, file=discord.File(chart_path, filename=os.path.basename(chart_path)))


async def _stats_period(reply, period: str, since: dt.date) -> None:
    from swingbot.core.scanning import engine as scan_engine
    from swingbot.core.analytics import metrics as m

    all_trades = scan_engine.trade_log.get_trades(status="all", limit=None, ledger="main")
    closed = [t for t in all_trades if t.get("status") in ("win", "loss")
              and t.get("closed_at", "")[:10] >= since.isoformat()]
    if not closed:
        await reply.send(f"No closed trades in the last `{period}` window.")
        return

    embed = discord.Embed(
        title=f"📐 Analytics — last {period}",
        description=(
            f"**N** {len(closed)}  ·  **Win rate** {ui.fmt_pct(m.win_rate(closed))}  ·  "
            f"**Expectancy** {ui.fmt_r(m.expectancy_r(closed))}  ·  "
            f"**Profit factor** {_dash(m.profit_factor(closed), '{:.2f}')}"
        ),
    )
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"))
    await reply.send(embed=embed)


async def handle_stats(reply, period: str = "all") -> None:
    period = period.lower()
    if period == "all":
        await reply.defer()
        await _stats_all(reply)
        return
    since = _since(period, dt.date.today())
    if since is None:
        await reply.send_error(f"Unrecognized period `{period}`. Use one of: 7d, 30d, 90d, ytd, all.")
        return
    await reply.defer()
    await _stats_period(reply, period, since)


@bot.command(name="stats")
async def stats_cmd(ctx, period: str = "all"):
    reply = CtxReply(ctx)
    await handle_stats(reply, period)
    await send_prefix_tip(ctx, reply)
```

4e. Replace `lessons_cmd` with:

```python
async def _lessons_week(reply, store) -> None:
    from swingbot.core.scanning import engine as scan_engine
    from swingbot.core.analytics.insights import weekly_digest
    import datetime as _dt

    all_trades = scan_engine.trade_log.get_trades(status="all", limit=None, ledger="main")
    closed = [t for t in all_trades if t.get("status") in ("win", "loss", "closed")]
    messages = weekly_digest(store.entries(), closed, today=_dt.date.today())
    for msg in messages:
        await reply.send(msg)


async def _lessons_recent(reply, store, n: int) -> None:
    entries = store.entries()[:n]
    if not entries:
        await reply.send("No journal entries yet.")
        return

    lines = lessons_lines(entries)
    text = "\n".join(lines) + f"\n\n**Tags:** {_tag_cloud(entries)}"
    await reply.send(f"📖 **Last {len(entries)} journal entr{'y' if len(entries)==1 else 'ies'}:**\n{text[:1900]}")


async def handle_lessons(reply, arg: str = "5") -> None:
    from swingbot.core.analytics.journal import JournalStore

    if arg.lower() == "week":
        await reply.defer()
        await _lessons_week(reply, JournalStore())
        return
    try:
        n = max(1, min(25, int(arg)))
    except ValueError:
        await reply.send_error(f"`{arg}` isn't a number or `week`. Usage: `!lessons [n|week]`.")
        return
    await reply.defer()
    await _lessons_recent(reply, JournalStore(), n)


@bot.command(name="lessons")
async def lessons_cmd(ctx, arg: str = "5"):
    reply = CtxReply(ctx)
    await handle_lessons(reply, arg)
    await send_prefix_tip(ctx, reply)
```

4f. Replace `calibration_cmd`: rename it `async def handle_calibration(reply) -> None:` (drop its `@bot.command(name="calibration")` decorator), insert `await reply.defer()` as its first statement, and change its two `await ctx.send(` calls to `await reply.send(`. Every other line stays as it is, the `lambda target: render_calibration(…)` line included. Below it add:

```python
@bot.command(name="calibration")
async def calibration_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_calibration(reply)
    await send_prefix_tip(ctx, reply)
```

4g. Replace `journal_cmd` with:

```python
async def handle_journal(reply, target: str, note: str | None = None) -> None:
    from swingbot.core.analytics.journal import JournalStore
    await reply.defer()
    store = JournalStore()

    if note:
        # target is a trade_id in this form.
        await reply.send(_journal_note_result(store, target, note))
        return

    # No note text -> target is a ticker to list, reusing lessons_lines.
    entries = store.entries()
    matching = [e for e in entries if e.get("ticker", "").upper() == target.upper()]
    if not matching:
        await reply.send(f"No journal entries for `{target.upper()}`.")
        return
    lines = lessons_lines(matching)
    await reply.send(f"📖 **{len(matching)} journal entr{'y' if len(matching)==1 else 'ies'} for {target.upper()}:**\n" + "\n".join(lines)[:1900])


@bot.command(name="journal")
async def journal_cmd(ctx, target: str, *, note: str = None):
    reply = CtxReply(ctx)
    await handle_journal(reply, target, note)
    await send_prefix_tip(ctx, reply)
```

4h. Append the twins at the end of the file. The four moved ones are copied verbatim from `slash.py`:

```python


# ──────────────────────────────────────────────
# / slash twins (/top /stats /soak /lessons moved from slash.py in v153,
# payload unchanged; /calibration and /journal new)
# ──────────────────────────────────────────────

@bot.tree.command(name="top", description="Highest follow-score PENDING/ACTIVE plans")
@app_commands.describe(n="How many plans to show (default: config.DIGEST_MAX_PLANS)")
async def slash_top(interaction: discord.Interaction, n: int = None):
    await handle_top(InteractionReply(interaction), n)


@bot.tree.command(name="stats", description="Win rate, expectancy, and risk-adjusted stats")
@app_commands.describe(period="Time window")
@app_commands.choices(period=PERIOD_CHOICES)
async def slash_stats(interaction: discord.Interaction, period: app_commands.Choice[str] = None):
    await handle_stats(InteractionReply(interaction), period.value if period else "all")


@bot.tree.command(name="soak", description="v93 trust-rule readout for a strategy's shadow plans")
@app_commands.describe(strategy="Exact strategy name, e.g. MACD")
async def slash_soak(interaction: discord.Interaction, strategy: str):
    await handle_soak(InteractionReply(interaction), strategy)


@bot.tree.command(name="lessons", description="Recent journal entries and their auto-generated lessons")
@app_commands.describe(arg="A number of entries, or 'week' for the weekly digest")
async def slash_lessons(interaction: discord.Interaction, arg: str = "5"):
    await handle_lessons(InteractionReply(interaction), arg)


@bot.tree.command(name="calibration", description="Win rate per confidence level, edge decay and score deciles")
async def slash_calibration(interaction: discord.Interaction):
    await handle_calibration(InteractionReply(interaction))


@bot.tree.command(name="journal", description="Save a note on a trade, or list a ticker's journal entries")
@app_commands.describe(
    target="A trade id (to save a note) or a ticker (to list its entries)",
    note="Note text to save on that trade id; leave blank to list a ticker",
)
async def slash_journal(interaction: discord.Interaction, target: str, note: str = None):
    await handle_journal(InteractionReply(interaction), target, note)
```

- [ ] **Step 5: Delete the four blocks from `slash.py`**

In `$WT/swingbot/commands/slash.py`, delete the banner comments and the whole `slash_top`, `slash_stats`, `slash_soak` and `slash_lessons` commands. Keep `PERIOD_CHOICES`.

```bash
git -C $WT grep -n 'name="top"\|name="stats"\|name="soak"\|name="lessons"\|commands.stats' -- swingbot/commands/slash.py
```

Expected: no hit.

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/admin/test_v144_pooled_readers.py
python $WT/scripts/dev/testrun.py file tests/commands/test_send_alerts_v110.py
python $WT/scripts/dev/testrun.py file tests/infra/test_posted_log.py
```

Expected: `0 failed`, `0 xfailed` on all six. The parity file gains 17 `stats_*` cases. `test_soak_cmd_empty_state_guard_short_circuits_before_badge_lookup` and `test_soak_cmd_reads_regular_plans_only` pass unchanged.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/stats.py $WT/swingbot/commands/slash.py
```

Expected: no output; every handler, helper and twin is below C. Paste it into the task report.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/stats.py swingbot/commands/slash.py tests/commands/parity_cases/stats.py tests/commands/test_stats_commands.py tests/commands/test_slash_commands.py
git -C $WT commit -m "feat(v153): SP15 stats handlers; /top /stats /soak /lessons move out of slash.py, /calibration /journal new"
```

