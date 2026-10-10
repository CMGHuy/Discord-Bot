# v153 Slash command parity. Part 4: `slash.py` chain II (`backtest`, `watchlist`, `stats`, `scanning/commands`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These tasks continue the `slash.py` chain after part 3 (SP9–SP12). This file holds SP13–SP14; SP15 lives in [`_4b-stats`](2026-10-10-v153-slash-command-parity_4b-stats.md) and SP16 in [`_4c-scanning`](2026-10-10-v153-slash-command-parity_4c-scanning.md) (split only for the 1500-line cap; both use the shared conventions below). They run **one at a time, in id order**: every one of them edits `swingbot/commands/slash.py`. Each task moves its slash commands out of `slash.py` and into its own module **in the same commit**. A name registered twice raises `CommandAlreadyRegistered` at import, and a name deleted first would be missing, so the move is atomic.

**Shared conventions for this part** (they restate the index and part 2's conventions block; the index wins on any conflict):

- `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity`. Never `cd`; use `git -C $WT` and absolute paths.
- Consumed from SP1 (`swingbot/commands/reply.py`): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `PREFIX_TIP_UNTIL`, `TOKEN_LIFETIME_S`, `_today`. Consumed from SP1 (`tests/commands/reply_harness.py`): `ParityCase`, `FakeContext`, `FakeInteraction`, `run_both`, `comparable`, `make_event`. SP1's `tests/commands/test_reply_parity.py` parametrises over `all_cases()`, which imports every module in `tests/commands/parity_cases/` and concatenates their `CASES`. Adding a module there is how a task adds its handlers to the harness.
- `ParityCase.expect` meanings (SP1's `_EXPECT` table). In every case both surfaces produce the same `comparable(...)` events.
  - `"send"`: at least one `"send"` and no `"edit"`; neither reply is `failed`.
  - `"edit"`: at least one `"send"` and at least one `"edit"`; neither reply is `failed`.
  - `"multi_send"`: at least two `"send"` events and no `"edit"`; neither reply is `failed`.
  - `"error"`: at least one `"send"`, and `failed` is `True` on both replies.
  - A case's `stub` is applied once, and the handler then runs twice (Context first) under it, so stubs must be idempotent. A `fail_stub` is applied on top of `stub` by `test_handler_error_parity`; that run must end with `failed` on both replies.
- A **validation failure** (a bad argument the user typed) answers through `reply.send_error(...)`. On `CtxReply` that is the same channel message as today. It also sets `reply.failed`, so the prefix command sends no tip after it. An **empty result** ("No closed trades yet") is a normal `reply.send`, not an error.
- Slow handlers call `await reply.defer()` **after** their validation and **before** the slow work. On `CtxReply` it is a no-op. On the slash surface it keeps Discord's 3-second acknowledgement, exactly as today's `interaction.response.defer()` did.
- **Moved slash commands keep their exact name, description, `describe` text, option names, option order and choices.** Copy the decorators verbatim from `slash.py`. Only the body changes. A `Choice` option is unwrapped (`opt.value if opt else <default>`) before the handler call.
- **Registration tests stay green until SP19 deletes them** (index, Global Constraints). When a task moves a name that `test_new_slash_commands_registered_on_tree`, `test_six_bridge_commands_still_registered` or `test_soak_slash_registered` asserts, it adds `import swingbot.commands.<module>  # noqa: F401` on the line directly after that test's `import swingbot.commands.slash` line. If part 3 already added a module import there, add yours on the next line.
- `test_command_error_logging.py`'s AST guard counts an `except Exception:` block as user-facing when it calls `send`, `send_message` or `edit`. Handlers now answer with `reply.send_error`, so SP13 Step 2 adds `send_error` to that set (if part 3's SP9 already did, leave it). Every `except Exception` that answers the user still logs with `exc_info=True` or `log.exception`.
- Each module task runs `python -m radon cc -s -n C` over every file it touched, `slash.py` included, and pastes the output into its report.
- Narrow test runs only: `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.

# Phase 4: `slash.py` chain II

### Task SP13: `backtest`: `!backtest`, `!backtestwatchlist` and their moved twins

**Model:** sonnet — two body moves onto handlers plus a verbatim decorator move out of `slash.py`; the one subtle point, translating the strategy choice, is spelled out below.

**Swallowed-error ratchet (audit 2026-10-10):** this task writes `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged): a handler moved from today's code keeps exactly the `swallowed(...)` call it carries in the current file (copy it from the file, not from this plan's pre-v148 text); a new handler that neither re-raises nor calls `swallowed()` follows the index Global Constraints bullet "Swallowed-error ratchet"; then run `python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/backtest.py` (imports at lines 12-22 today; `backtest_cmd` and `backtestwatchlist_cmd` at lines 221-298 today, to the end of the file)
- Modify: `swingbot/commands/slash.py` (delete the `/backtest` and `/backtestwatchlist` blocks; locate them with `git -C $WT grep -n 'name="backtest' -- swingbot/commands/slash.py`)
- Create: `tests/commands/parity_cases/backtest.py`
- Create: `tests/commands/test_backtest_twins.py` (task-private)
- Modify: `tests/commands/test_command_error_logging.py` (`_REPLIES` at line 8; append one test after line 78)
- Modify: `tests/commands/test_stats_commands.py` (`test_six_bridge_commands_still_registered`, one import line)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `PREFIX_TIP_UNTIL`, `reply._today`; `ParityCase`, `FakeContext`, `FakeInteraction`, `run_both`, `comparable`. Consumes `slash.HORIZON_CHOICES`, `slash.STRATEGY_CHOICES` (stay in `slash.py`).
- Produces (ledger): `handle_backtest(reply, ticker: str, horizon: str = "all", strategy: str = "all", date_from: str | None = None, date_to: str | None = None, list_setups: bool = False)` and `handle_backtestwatchlist(reply, horizon: str = "all", strategy: str = "all", date_from: str | None = None, date_to: str | None = None)`. `strategy` is a **canonical** strategy name (a `STRATEGY_MAP` value such as `"EMA Crossover"`) or `"all"`: exactly what `_parse_backtest_args` yields as `strategy_norm` today. Also `/backtest` (`slash_backtest`) and `/backtestwatchlist` (`slash_backtestwatchlist`), moved here with their decorators verbatim. New private helpers: `_range_str`, `_send_long`, `_ranked_combos`, `_format_leaderboard`, `_strategy_from_choice`.
- Output:
  - `!backtest` and `!backtestwatchlist` texts are unchanged; the tip follows a successful answer.
  - A data-fetch failure in `!backtest` answers the same `⚠️ Could not fetch data for …` text through `send_error`, so no tip follows it.
  - **Slash-only fix:** today's `/backtest` re-joins its options into prefix tokens, and `_parse_backtest_args` reads the default strategy token `"all"` as a horizon. So `/backtest horizon:4w` with no strategy runs **all** horizons, and `/backtestwatchlist` does the same. The twins now pass typed options straight to the handler, so the chosen horizon holds. `test_backtest_twins.py` pins it. No `!` output changes from this.

**Why `send_error` joins `_REPLIES`:** `test_every_user_facing_exception_is_logged_with_its_traceback` finds `except Exception:` blocks that answer the user by the method they call. After this part, handlers answer through `reply.send_error`. Without the new name, an unlogged `except Exception: await reply.send_error(...)` would slip past the guard.

- [ ] **Step 0: Confirm the chain position**

```bash
git -C $WT grep -n "class CtxReply\|def send_prefix_tip" -- swingbot/commands/reply.py
git -C $WT grep -n 'name="liveplans"\|name="trades"\|name="ticker"' -- swingbot/commands/slash.py
git -C $WT grep -n 'name="backtest"\|name="backtestwatchlist"' -- swingbot/commands/slash.py
```

Expected: two hits in `reply.py`. The second grep must be **empty**, because SP9–SP12 moved those commands out. The third shows both blocks still in `slash.py`. If the second grep is not empty, part 3 has not landed: stop and report `BLOCKED: SP12 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/backtest.py`:

```python
"""Reply-parity cases for swingbot/commands/backtest.py (v153 SP13)."""
from types import SimpleNamespace

from swingbot.commands import backtest as backtest_mod
from tests.commands.reply_harness import ParityCase

_TRADE = SimpleNamespace(outcome="win", r_multiple=1.2, exit_date="2024-02-01", direction="bullish",
                         entry=100.0, stop_loss=95.0, take_profit=110.0, entry_date="2024-01-15")


def _summary(ticker="AAA", strategy=None, evaluated=6, trades=()):
    return SimpleNamespace(
        ticker=ticker, strategy=strategy or backtest_mod.ALL_STRATEGIES[0], horizon_key="4w",
        total_signals=8, evaluated=evaluated, scratches=1, timeouts=1, wins=evaluated - 1, losses=1,
        win_rate=66.7, expectancy_r=0.35, max_drawdown_pct=9.5, avg_holding_days=6.0,
        trades=list(trades),
    )


def _stub_one(summaries):
    def stub(monkeypatch):
        monkeypatch.setattr(backtest_mod, "_sync_backtest_one", lambda *a: (250, list(summaries)))
    return stub


def _fetch_fails(monkeypatch):
    def boom(*a):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(backtest_mod, "_sync_backtest_one", boom)


def _stub_watchlist(summaries, errors=()):
    def stub(monkeypatch):
        monkeypatch.setattr(backtest_mod, "load_watchlist", lambda: ["AAA", "BBB", "CCC"])
        monkeypatch.setattr(backtest_mod, "_sync_backtest_watchlist",
                            lambda *a: (list(summaries), list(errors)))
    return stub


_ONE = [_summary()]
_WITH_TRADES = [_summary(trades=[_TRADE, _TRADE])]
# 40 strategy rows push the table past the 1950-char single-message limit.
_MANY = [_summary(strategy=backtest_mod.ALL_STRATEGIES[i % len(backtest_mod.ALL_STRATEGIES)])
         for i in range(40)]
_BOARD = [_summary("AAA"), _summary("BBB", evaluated=9), _summary("CCC", evaluated=2)]
_THIN = [_summary("AAA", evaluated=2), _summary("BBB", evaluated=3)]

CASES = [
    ParityCase("backtest_table", backtest_mod.handle_backtest, args=("aapl",),
               stub=_stub_one(_ONE), fail_stub=_fetch_fails, expect="multi_send"),
    ParityCase("backtest_setups_in_range", backtest_mod.handle_backtest, args=("aapl", "4w", "MACD"),
               kwargs={"date_from": "2024-01-01", "date_to": "2024-06-30", "list_setups": True},
               stub=_stub_one(_WITH_TRADES), expect="multi_send"),
    ParityCase("backtest_long_table_chunks", backtest_mod.handle_backtest, args=("aapl",),
               stub=_stub_one(_MANY), expect="multi_send"),
    ParityCase("backtest_fetch_fails", backtest_mod.handle_backtest, args=("aapl",),
               stub=_fetch_fails, expect="error"),
    ParityCase("backtestwatchlist_leaderboard", backtest_mod.handle_backtestwatchlist,
               stub=_stub_watchlist(_BOARD), expect="multi_send"),
    ParityCase("backtestwatchlist_skips_and_no_combo", backtest_mod.handle_backtestwatchlist,
               kwargs={"date_from": "2024-01-01"},
               stub=_stub_watchlist(_THIN, errors=[("DDD", "no data")]), expect="multi_send"),
]
```

- [ ] **Step 2: Write the twin, tip and error-logging tests (failing)**

Create `$WT/tests/commands/test_backtest_twins.py`:

```python
"""v153 SP13: /backtest and /backtestwatchlist live in backtest.py, keep their
sync payload, and hand typed options straight to the shared handlers."""
import asyncio
import datetime as dt
import inspect

from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands import backtest as backtest_mod
from swingbot.commands import reply as reply_mod
from swingbot.commands.reply import CtxReply, InteractionReply
from tests.commands.reply_harness import FakeContext, FakeInteraction, comparable, run_both


def _capture(monkeypatch, name):
    seen = {}

    async def fake(reply, *args, **kwargs):
        seen.update(reply=reply, args=args, kwargs=kwargs)
    monkeypatch.setattr(backtest_mod, name, fake)
    return seen


def test_twins_live_in_backtest_py_and_slash_py_no_longer_defines_them():
    from swingbot.commands import slash
    source = inspect.getsource(slash)
    assert 'name="backtest"' not in source and 'name="backtestwatchlist"' not in source
    assert bot.tree.get_command("backtest") is backtest_mod.slash_backtest
    assert bot.tree.get_command("backtestwatchlist") is backtest_mod.slash_backtestwatchlist


def test_moved_twins_keep_their_description_and_options():
    assert backtest_mod.slash_backtest.description == "Backtest a ticker against historical data"
    assert [p.name for p in backtest_mod.slash_backtest.parameters] == [
        "ticker", "horizon", "strategy", "from_date", "to_date", "setups"]
    assert backtest_mod.slash_backtestwatchlist.description == (
        "Backtest every watchlist ticker, ranked by expectancy")
    assert [p.name for p in backtest_mod.slash_backtestwatchlist.parameters] == [
        "horizon", "strategy", "from_date", "to_date"]


def test_slash_backtest_keeps_the_chosen_horizon_when_strategy_is_omitted(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtest")
    asyncio.run(backtest_mod.slash_backtest.callback(
        FakeInteraction([]), ticker="aapl", horizon=app_commands.Choice(name="4w", value="4w"),
        strategy=None, from_date="2024-01-01", to_date=None, setups=True))

    assert isinstance(seen["reply"], InteractionReply)
    assert seen["args"] == ("aapl", "4w", "all", "2024-01-01", None, True)


def test_slash_strategy_choice_becomes_the_canonical_name(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtestwatchlist")
    asyncio.run(backtest_mod.slash_backtestwatchlist.callback(
        FakeInteraction([]), horizon=None,
        strategy=app_commands.Choice(name="EMA Crossover", value="ema"), from_date=None, to_date=None))

    assert seen["args"] == ("all", "EMA Crossover", None, None)


def test_every_strategy_choice_maps_to_a_canonical_name():
    from swingbot.commands.slash import STRATEGY_CHOICES
    for choice in STRATEGY_CHOICES:
        expected = "all" if choice.value == "all" else backtest_mod.STRATEGY_MAP[choice.value]
        assert backtest_mod._strategy_from_choice(choice) == expected
    assert backtest_mod._strategy_from_choice(None) == "all"


def test_backtest_multi_send_order_is_identical_on_both_surfaces(monkeypatch):
    from tests.commands.parity_cases.backtest import _ONE, _stub_one
    _stub_one(_ONE)(monkeypatch)

    run = run_both(lambda reply: backtest_mod.handle_backtest(reply, "aapl"), monkeypatch)

    contents = [event[1] for event in comparable(run.ctx_events)]
    assert contents == [event[1] for event in comparable(run.inter_events)]
    assert len(contents) == 3
    assert contents[0] == "Backtesting **AAPL**… this can take a few seconds."
    assert contents[1].startswith("Backtest — **AAPL** (250 bars of history):")
    assert contents[2].startswith("**Win rate by strategy**")


def test_backtestwatchlist_prefix_answer_ends_with_the_tip(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))
    monkeypatch.setattr(backtest_mod, "load_watchlist", lambda: [])
    monkeypatch.setattr(backtest_mod, "_sync_backtest_watchlist", lambda *a: ([], []))
    events: list = []

    asyncio.run(backtest_mod.backtestwatchlist_cmd.callback(FakeContext(events, qualified_name="backtestwatchlist")))

    assert events[-1][1] == "Tip: this is now /backtestwatchlist"


def test_prefix_backtest_passes_parsed_tokens_to_the_handler(monkeypatch):
    seen = _capture(monkeypatch, "handle_backtest")
    asyncio.run(backtest_mod.backtest_cmd.callback(
        FakeContext([]), "tsla", "4w", "bnr", "from:2024-01-01", "setups"))

    assert isinstance(seen["reply"], CtxReply)
    assert seen["args"] == ("tsla", "4w", "Break & Retest", "2024-01-01", None, True)
```

In `$WT/tests/commands/test_command_error_logging.py`, change line 8 to:

```python
_REPLIES = {"send", "send_message", "edit", "send_error"}
```

(If part 3's SP9 already added `"send_error"`, leave the line as it is.) Then append:

```python


def test_backtest_command_failure_is_logged_shown_and_not_followed_by_a_tip(monkeypatch, caplog):
    import datetime as dt

    from swingbot.commands import backtest
    from swingbot.commands import reply as reply_mod
    from tests.commands.reply_harness import FakeContext

    def boom(*args):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(backtest, "_sync_backtest_one", boom)
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))
    events: list = []
    with caplog.at_level(logging.WARNING, logger=backtest.log.name):
        asyncio.run(backtest.backtest_cmd.callback(FakeContext(events, qualified_name="backtest"), "aapl"))

    [record] = [r for r in caplog.records if r.name == backtest.log.name]
    assert record.exc_info is not None and "AAPL" in record.getMessage()
    assert events[-1][1] == "⚠️ Could not fetch data for AAPL: yahoo down"
    assert not any((event[1] or "").startswith("Tip:") for event in events)
```

In `$WT/tests/commands/test_stats_commands.py`, inside `test_six_bridge_commands_still_registered`, add on the line after `import swingbot.commands.slash  # noqa: F401  -- registers on import`:

```python
    import swingbot.commands.backtest  # noqa: F401  -- v153: /backtest moved here
```

- [ ] **Step 3: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_backtest_twins.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
```

Expected: the first fails at collection (`AttributeError: module 'swingbot.commands.backtest' has no attribute 'handle_backtest'`). The second fails at collection too (`ImportError` from `tests.commands.parity_cases.backtest`, or `AttributeError: ... 'slash_backtest'`). In the third, the new test **already passes**: today's `backtest_cmd` sends the error text and never a tip. It is a guard that the error path still sends no tip once Step 4 adds `send_prefix_tip`. The older tests pass.

- [ ] **Step 4: Rewrite the command section of `backtest.py`**

4a. Replace the import block (lines 12-22 today) with:

```python
import asyncio
import logging

import discord
from discord import app_commands

from swingbot.core.backtesting.backtest import (
    ALL_STRATEGIES, run_backtest, run_backtest_daterange, run_full_backtest,
)
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES, STRATEGY_CHOICES
from swingbot.core import presentation as ui
from swingbot.core.marketdata.data import get_daily_data
from swingbot.core.market.strategy import live_horizons
from swingbot.core.marketdata.watchlist import load_watchlist
```

`slash.py` imports no command module, so importing its choice lists here is not circular (index, Global Constraints).

4b. Replace everything from `@bot.command(name="backtest")` to the end of the file with:

```python
def _range_str(date_from: str | None, date_to: str | None) -> str:
    return f" [{date_from or '…'} → {date_to or 'now'}]" if (date_from or date_to) else ""


async def _send_long(reply, msg: str) -> None:
    """One message up to 1950 chars, else 1900-char chunks (today's split)."""
    if len(msg) <= 1950:
        await reply.send(msg)
        return
    for chunk in [msg[i:i+1900] for i in range(0, len(msg), 1900)]:
        await reply.send(chunk)


async def handle_backtest(reply, ticker: str, horizon: str = "all", strategy: str = "all",
                          date_from: str | None = None, date_to: str | None = None,
                          list_setups: bool = False) -> None:
    """Backtest one ticker. `strategy` is a canonical name (a STRATEGY_MAP value) or "all"."""
    ticker = ticker.upper()
    range_str = _range_str(date_from, date_to)
    await reply.defer()
    await reply.send(f"Backtesting **{ticker}**{range_str}… this can take a few seconds.")
    try:
        bar_count, summaries = await asyncio.to_thread(
            _sync_backtest_one, ticker, horizon, strategy, date_from, date_to
        )
    except Exception as e:
        log.warning("!backtest %s: could not fetch data", ticker, exc_info=True)
        await reply.send_error(f"⚠️ Could not fetch data for {ticker}: {e}")
        return

    header = f"Backtest — **{ticker}**{range_str} ({bar_count} bars of history):"
    if list_setups:
        msg = _format_setup_list(header, summaries)
    else:
        msg = _format_backtest_table(header, summaries)
    await _send_long(reply, msg)

    # Per-strategy win rate, combined across every horizon shown above.
    await reply.send(_format_per_strategy_winrate(summaries))


def _ranked_combos(all_summaries: list) -> list:
    """Combos with 5+ closed trades, best expectancy first."""
    evaluated = [s for s in all_summaries if s.evaluated >= 5]
    evaluated.sort(key=lambda s: (s.expectancy_r if s.expectancy_r is not None else -999), reverse=True)
    return evaluated


def _format_leaderboard(evaluated: list, range_str: str) -> str:
    lines = [
        f"**Watchlist backtest leaderboard**{range_str} (combos with 5+ closed trades, ranked by ExpR):",
        "```",
        f"{'Ticker':7s} {'Strategy':18s} {'Horiz':5s} {'Eval':>4s} {'Win%':>6s} {'ExpR':>6s} {'MaxDD%':>7s}",
    ]
    for s in evaluated[:20]:
        wr = ui.fmt_pct(s.win_rate) if s.win_rate is not None else "n/a"
        er = ui.fmt_r(s.expectancy_r) if s.expectancy_r is not None else "n/a"
        dd = ui.fmt_pct(-abs(s.max_drawdown_pct)) if s.max_drawdown_pct is not None else "n/a"
        lines.append(f"{s.ticker:7s} {s.strategy:18s} {s.horizon_key:5s} {s.evaluated:4d} {wr:>6s} {er:>6s} {dd:>7s}")
    lines.append("```")
    lines.append("⚠️ Overlapping trades counted independently, no fees/slippage, survivorship bias.")
    return "\n".join(lines)


async def handle_backtestwatchlist(reply, horizon: str = "all", strategy: str = "all",
                                   date_from: str | None = None, date_to: str | None = None) -> None:
    """Backtest every watchlist ticker; `strategy` as in handle_backtest."""
    await reply.defer()
    tickers = load_watchlist()
    range_str = _range_str(date_from, date_to)
    await reply.send(f"Backtesting **{len(tickers)}** watchlist ticker(s){range_str}… this can take a while.")

    all_summaries, errors = await asyncio.to_thread(
        _sync_backtest_watchlist, tickers, horizon, strategy, date_from, date_to
    )
    for t, err in errors:
        await reply.send(f"⚠️ Skipping {t}: {err}")

    evaluated = _ranked_combos(all_summaries)

    # Per-strategy win rate across the WHOLE watchlist (every ticker, every
    # horizon tested, combined) -- answers "is every strategy hitting 80%?"
    # directly, regardless of whether any single ticker/horizon combo had
    # enough trades on its own to make the leaderboard below.
    await reply.send(_format_per_strategy_winrate(all_summaries))

    if not evaluated:
        await reply.send(
            "No combo had ≥5 closed backtest trades across the watchlist — "
            "try `!backtest TICKER` on individual names instead."
        )
        return
    await reply.send(_format_leaderboard(evaluated, range_str))


@bot.command(name="backtest")
async def backtest_cmd(ctx, ticker: str, *args):
    horizon, strategy_norm, date_from, date_to, list_setups = _parse_backtest_args(args)
    reply = CtxReply(ctx)
    await handle_backtest(reply, ticker, horizon, strategy_norm, date_from, date_to, list_setups)
    await send_prefix_tip(ctx, reply)


@bot.command(name="backtestwatchlist")
async def backtestwatchlist_cmd(ctx, *args):
    horizon, strategy_norm, date_from, date_to, _ = _parse_backtest_args(args)
    reply = CtxReply(ctx)
    await handle_backtestwatchlist(reply, horizon, strategy_norm, date_from, date_to)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (moved from slash.py in v153; payload unchanged)
# ──────────────────────────────────────────────

def _strategy_from_choice(choice) -> str:
    """A STRATEGY_CHOICES value ("ema", …, "all") -> the canonical name the handlers take."""
    if choice is None:
        return "all"
    return STRATEGY_MAP.get(choice.value, "all")


@bot.tree.command(name="backtest", description="Backtest a ticker against historical data")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. AAPL",
    horizon="Swing horizon (default: all)",
    strategy="Strategy to test (default: all)",
    from_date="Start date YYYY-MM-DD (optional)",
    to_date="End date YYYY-MM-DD (optional)",
    setups="List every individual trade setup instead of the summary table",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtest(
    interaction: discord.Interaction,
    ticker: str,
    horizon: app_commands.Choice[str] = None,
    strategy: app_commands.Choice[str] = None,
    from_date: str = None,
    to_date: str = None,
    setups: bool = False,
):
    await handle_backtest(
        InteractionReply(interaction), ticker, horizon.value if horizon else "all",
        _strategy_from_choice(strategy), from_date, to_date, setups,
    )


@bot.tree.command(name="backtestwatchlist", description="Backtest every watchlist ticker, ranked by expectancy")
@app_commands.describe(
    horizon="Swing horizon (default: all)",
    strategy="Strategy to test (default: all)",
    from_date="Start date YYYY-MM-DD (optional)",
    to_date="End date YYYY-MM-DD (optional)",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_backtestwatchlist(
    interaction: discord.Interaction,
    horizon: app_commands.Choice[str] = None,
    strategy: app_commands.Choice[str] = None,
    from_date: str = None,
    to_date: str = None,
):
    await handle_backtestwatchlist(
        InteractionReply(interaction), horizon.value if horizon else "all",
        _strategy_from_choice(strategy), from_date, to_date,
    )
```

- [ ] **Step 5: Delete the two blocks from `slash.py`**

In `$WT/swingbot/commands/slash.py`, delete the `/backtest` banner comment (the three `# ─…`/`# /backtest` lines), the whole `slash_backtest` command, the `/backtestwatchlist` banner and the whole `slash_backtestwatchlist` command. Leave every choice list in place: `HORIZON_CHOICES` and `STRATEGY_CHOICES` are now imported by `backtest.py`.

```bash
git -C $WT grep -n 'name="backtest\|from_interaction' -- swingbot/commands/slash.py
```

Expected: no `name="backtest…"` hit. The remaining `from_interaction` hits belong to commands SP14–SP16 still move.

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_backtest_twins.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
python $WT/scripts/dev/testrun.py file tests/commands/test_backtest_format.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
```

Expected: `0 failed`, `0 xfailed` on all six. The parity file gains 6 `backtest_*` cases and one `test_handler_error_parity[backtest_table]`.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/backtest.py $WT/swingbot/commands/slash.py
```

Expected: `_run_backtest_combo` C(15) (legacy, unchanged, not touched) and `_format_per_strategy_winrate` C(11). `backtestwatchlist_cmd` C(14) is gone: its body is now `handle_backtestwatchlist` (below C) plus `_ranked_combos` and `_format_leaderboard`. Nothing new is listed. Paste the output into the task report.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/backtest.py swingbot/commands/slash.py tests/commands/parity_cases/backtest.py tests/commands/test_backtest_twins.py tests/commands/test_command_error_logging.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP13 backtest handlers; /backtest and /backtestwatchlist move out of slash.py"
```

### Task SP14: `watchlist`: one handler, an action table, and the moved `/watchlist`

**Model:** sonnet — a 50-line module rewritten onto one dispatch table; the guard and its text are fixed by the spec and the ledger.

**Swallowed-error ratchet (audit 2026-10-10):** this task writes `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged): a handler moved from today's code keeps exactly the `swallowed(...)` call it carries in the current file (copy it from the file, not from this plan's pre-v148 text); a new handler that neither re-raises nor calls `swallowed()` follows the index Global Constraints bullet "Swallowed-error ratchet"; then run `python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`. Otherwise write them as planned.

**Files:**
- Modify: `swingbot/commands/watchlist.py` (whole file, 50 lines today)
- Modify: `swingbot/commands/slash.py` (delete the `/watchlist` block; locate it with `git -C $WT grep -n 'name="watchlist"' -- swingbot/commands/slash.py`)
- Create: `tests/commands/parity_cases/watchlist.py`
- Create: `tests/commands/test_watchlist_twin.py` (task-private)
- Modify: `tests/commands/test_stats_commands.py` (`test_six_bridge_commands_still_registered`, one import line)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `PREFIX_TIP_UNTIL`, `reply._today`; `ParityCase`, `FakeContext`, `FakeInteraction`, `run_both`, `comparable`.
- Produces (ledger): `handle_watchlist(reply, action: str = "show", ticker: str | None = None)`; `WATCHLIST_ACTIONS: dict[str, Callable]` with keys `show add remove clear` (in that order) and private values `_watchlist_show`, `_watchlist_add`, `_watchlist_remove`, `_watchlist_clear`, each `async (reply, ticker: str | None) -> None`; `MISSING_TICKER = "Please provide a ticker for add/remove actions."`. The prefix subcommands `watchlist_add` and `watchlist_remove` take `ticker: str = None`. `/watchlist` (`slash_watchlist`) moves here with its decorators verbatim: one command, an `action` choice (`show add remove clear`) and a `ticker` option. SP18 resolves `SLASH_TWIN`'s `watchlist <x>` against that choice list, so the choice values must stay exactly `show`, `add`, `remove`, `clear`.
- Output (index, Global Constraints, items 4 and 5):
  - A bare `!watchlist add` or `!watchlist remove` now answers `Please provide a ticker for add/remove actions.` through `send_error` (no tip). Before, discord.py raised `MissingRequiredArgument` and `on_command_error` showed the `COMMAND_USAGE["watchlist add"]` hint. That `COMMAND_USAGE` entry stays; it is simply no longer reached for these two.
  - `!watchlist add aapl` stores `AAPL`. `add_ticker`, `remove_ticker`, `ensure_cached_background` and `get_daily_data` now receive the upper-cased ticker, as `/watchlist` already did. Every message text is unchanged (they already printed `ticker.upper()`).
  - An action outside the table answers `send_error` naming the valid actions. The slash choice list cannot produce one; the handler guards it for direct callers.
  - The tip names the slash path from `SLASH_TWIN`: `Tip: this is now /watchlist add` (the `add` choice of `/watchlist`).

- [ ] **Step 0: Confirm the chain position**

```bash
git -C $WT grep -n 'name="backtest"' -- swingbot/commands/slash.py
git -C $WT grep -n 'name="watchlist"' -- swingbot/commands/slash.py swingbot/commands/watchlist.py
```

Expected: the first is **empty** (SP13 landed); the second shows the `/watchlist` block in `slash.py` and the `@bot.group(name="watchlist"…)` in `watchlist.py`. If the first is not empty, stop and report `BLOCKED: SP13 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/watchlist.py`:

```python
"""Reply-parity cases for swingbot/commands/watchlist.py (v153 SP14).

The spec's /watchlist edge cases are here as `expect="error"` cases: a
missing ticker for add and for remove, and an unknown action, must give the
same send_error text on both surfaces."""
from swingbot.commands import watchlist as watchlist_mod
from tests.commands.reply_harness import ParityCase


def _stub(tickers=("AAPL", "MSFT"), fetch_fails=False):
    def stub(monkeypatch):
        monkeypatch.setattr(watchlist_mod, "load_watchlist", lambda: list(tickers))
        monkeypatch.setattr(watchlist_mod, "add_ticker", lambda t: [*tickers, t])
        monkeypatch.setattr(watchlist_mod, "remove_ticker", lambda t: [x for x in tickers if x != t])
        monkeypatch.setattr(watchlist_mod, "clear_watchlist", lambda: None)
        monkeypatch.setattr(watchlist_mod, "ensure_cached_background", lambda t: None)

        def fetch(ticker, period):
            if fetch_fails:
                raise RuntimeError("no such symbol")
            return None
        monkeypatch.setattr(watchlist_mod, "get_daily_data", fetch)
    return stub


CASES = [
    ParityCase("watchlist_show", watchlist_mod.handle_watchlist, stub=_stub()),
    ParityCase("watchlist_show_empty", watchlist_mod.handle_watchlist, args=("show",), stub=_stub(())),
    ParityCase("watchlist_add_lowercase", watchlist_mod.handle_watchlist, args=("add", "nvda"), stub=_stub()),
    ParityCase("watchlist_add_fetch_fails", watchlist_mod.handle_watchlist, args=("add", "gold"),
               stub=_stub(fetch_fails=True), expect="multi_send"),
    ParityCase("watchlist_remove", watchlist_mod.handle_watchlist, args=("remove", "msft"), stub=_stub()),
    ParityCase("watchlist_clear", watchlist_mod.handle_watchlist, args=("clear",), stub=_stub()),
    ParityCase("watchlist_add_missing_ticker", watchlist_mod.handle_watchlist, args=("add",),
               stub=_stub(), expect="error"),
    ParityCase("watchlist_remove_missing_ticker", watchlist_mod.handle_watchlist, args=("remove", ""),
               stub=_stub(), expect="error"),
    ParityCase("watchlist_unknown_action", watchlist_mod.handle_watchlist, args=("rename", "AAPL"),
               stub=_stub(), expect="error"),
]
```

- [ ] **Step 2: Write the twin and prefix tests (failing)**

Create `$WT/tests/commands/test_watchlist_twin.py`:

```python
"""v153 SP14: /watchlist and !watchlist share handle_watchlist."""
import asyncio
import datetime as dt
import inspect

from swingbot.bot_core import bot
from swingbot.commands import reply as reply_mod
from swingbot.commands import watchlist as watchlist_mod
from tests.commands.parity_cases.watchlist import _stub
from tests.commands.reply_harness import FakeContext, comparable, run_both


def _tip_window_open(monkeypatch):
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def test_action_table_is_the_slash_choice_list():
    choices = [c.value for c in watchlist_mod.slash_watchlist.parameters[0].choices]
    assert list(watchlist_mod.WATCHLIST_ACTIONS) == ["show", "add", "remove", "clear"] == choices


def test_watchlist_twin_lives_in_watchlist_py_with_its_payload_unchanged():
    from swingbot.commands import slash
    assert 'name="watchlist"' not in inspect.getsource(slash)
    assert bot.tree.get_command("watchlist") is watchlist_mod.slash_watchlist
    assert watchlist_mod.slash_watchlist.description == "Show, add, or remove tickers from the watchlist"
    assert [p.name for p in watchlist_mod.slash_watchlist.parameters] == ["action", "ticker"]
    assert [c.name for c in watchlist_mod.slash_watchlist.parameters[0].choices] == [
        "Show", "Add", "Remove", "Clear"]


def test_missing_ticker_is_the_same_text_on_both_surfaces_and_ephemeral_only_on_slash(monkeypatch):
    run = run_both(lambda reply: watchlist_mod.handle_watchlist(reply, "add"), monkeypatch)

    assert run.ctx_events == [("send", watchlist_mod.MISSING_TICKER, None, (), None, False)]
    assert run.inter_events == [("send", watchlist_mod.MISSING_TICKER, None, (), None, True)]
    assert run.ctx_reply.failed and run.inter_reply.failed


def test_unknown_action_names_the_valid_actions(monkeypatch):
    run = run_both(lambda reply: watchlist_mod.handle_watchlist(reply, "rename", "AAPL"), monkeypatch)

    assert comparable(run.ctx_events) == comparable(run.inter_events)
    text = run.ctx_events[0][1]
    assert "rename" in text and "show, add, remove, clear" in text


def test_prefix_add_stores_the_upper_cased_ticker_and_ends_with_the_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    _stub()(monkeypatch)
    stored, cached = [], []
    monkeypatch.setattr(watchlist_mod, "add_ticker", lambda t: stored.append(t) or ["AAPL", t])
    monkeypatch.setattr(watchlist_mod, "ensure_cached_background", cached.append)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_add.callback(FakeContext(events, qualified_name="watchlist add"), "nvda"))

    assert stored == ["NVDA"] and cached == ["NVDA"]
    assert events[0][1] == "Added **NVDA**. Watchlist: AAPL, NVDA"
    assert events[-1][1] == "Tip: this is now /watchlist add"


def test_bare_prefix_add_answers_the_guard_without_a_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_add.callback(FakeContext(events, qualified_name="watchlist add")))

    assert [event[1] for event in events] == [watchlist_mod.MISSING_TICKER]


def test_prefix_group_shows_the_list_and_tips_the_show_choice(monkeypatch):
    _tip_window_open(monkeypatch)
    _stub()(monkeypatch)
    events: list = []

    asyncio.run(watchlist_mod.watchlist_cmd.callback(FakeContext(events, qualified_name="watchlist")))

    assert [event[1] for event in events] == [
        "Current watchlist: AAPL, MSFT", "Tip: this is now /watchlist show"]
```

In `$WT/tests/commands/test_stats_commands.py`, inside `test_six_bridge_commands_still_registered`, add after the `import swingbot.commands.slash` line (and after SP13's `backtest` line):

```python
    import swingbot.commands.watchlist  # noqa: F401  -- v153: /watchlist moved here
```

- [ ] **Step 3: Run them to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_watchlist_twin.py
```

Expected: both fail at collection (`AttributeError: module 'swingbot.commands.watchlist' has no attribute 'handle_watchlist'`).

- [ ] **Step 4: Rewrite `watchlist.py`**

Replace the whole of `$WT/swingbot/commands/watchlist.py` with:

```python
"""!watchlist and its subcommands, and the /watchlist twin (v153).

One handler, handle_watchlist(reply, action, ticker), answers both surfaces.
Its actions are the WATCHLIST_ACTIONS table, whose keys are also the
/watchlist `action` choice values.
"""
import asyncio
import logging
from typing import Awaitable, Callable

import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core.marketdata.backtest_cache import ensure_cached_background
from swingbot.core.marketdata.data import get_daily_data
from swingbot.core.marketdata.watchlist import add_ticker, clear_watchlist, load_watchlist, remove_ticker

log = logging.getLogger(__name__)

MISSING_TICKER = "Please provide a ticker for add/remove actions."
_NEEDS_TICKER = ("add", "remove")


async def _watchlist_show(reply, ticker: str | None = None) -> None:
    tickers = load_watchlist()
    await reply.send(f"Current watchlist: {', '.join(tickers) if tickers else '(empty)'}")


async def _watchlist_add(reply, ticker: str | None) -> None:
    tickers = add_ticker(ticker)
    # Kick off the full-history backtest-cache download in the background
    # (non-blocking; logs when done). Skips instantly if already cached.
    ensure_cached_background(ticker)
    await reply.send(f"Added **{ticker}**. Watchlist: {', '.join(tickers)}")

    try:
        await asyncio.to_thread(get_daily_data, ticker, "5d")
    except Exception as e:
        log.warning("!watchlist add %s: could not fetch data", ticker, exc_info=True)
        await reply.send(
            f"⚠️ Heads up: couldn't fetch data for **{ticker}** ({e}). "
            f"It's still in your watchlist, but scans will skip it until this resolves. "
            f"Common fixes: indices use Yahoo's `^` format (S&P 500 = `^GSPC`), spot metals are "
            f"gold = `XAUUSD`, silver = `XAGUSD` (futures `GC=F` / `SI=F` still work and stay "
            f"futures-priced), forex needs a `=X` suffix "
            f"(e.g. `EURUSD=X`). Use `!watchlist remove {ticker}` if you want to try a different symbol."
        )


async def _watchlist_remove(reply, ticker: str | None) -> None:
    tickers = remove_ticker(ticker)
    await reply.send(f"Removed **{ticker}**. Watchlist: {', '.join(tickers)}")


async def _watchlist_clear(reply, ticker: str | None = None) -> None:
    clear_watchlist()
    await reply.send("Watchlist cleared.")


WATCHLIST_ACTIONS: dict[str, Callable[..., Awaitable[None]]] = {
    "show": _watchlist_show,
    "add": _watchlist_add,
    "remove": _watchlist_remove,
    "clear": _watchlist_clear,
}


async def handle_watchlist(reply, action: str = "show", ticker: str | None = None) -> None:
    """Show, add, remove or clear. add/remove need a ticker; it is upper-cased."""
    run = WATCHLIST_ACTIONS.get(action)
    if run is None:
        await reply.send_error(
            f"Unknown watchlist action `{action}`. Use one of: {', '.join(WATCHLIST_ACTIONS)}."
        )
        return
    if action in _NEEDS_TICKER and not ticker:
        await reply.send_error(MISSING_TICKER)
        return
    await reply.defer()
    await run(reply, ticker.upper() if ticker else None)


# Each prefix command calls the handler itself (the index's prefix pattern),
# so SP18's one-body check sees the call inside the command.

@bot.group(name="watchlist", invoke_without_command=True)
async def watchlist_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "show")
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="add")
async def watchlist_add(ctx, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "add", ticker)
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="remove")
async def watchlist_remove(ctx, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "remove", ticker)
    await send_prefix_tip(ctx, reply)


@watchlist_cmd.command(name="clear")
async def watchlist_clear(ctx):
    reply = CtxReply(ctx)
    await handle_watchlist(reply, "clear")
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /watchlist (moved from slash.py in v153; payload unchanged)
# ──────────────────────────────────────────────

@bot.tree.command(name="watchlist", description="Show, add, or remove tickers from the watchlist")
@app_commands.describe(
    action="Action to perform (leave blank to just show the list)",
    ticker="Ticker to add or remove",
)
@app_commands.choices(action=[
    app_commands.Choice(name="Show",   value="show"),
    app_commands.Choice(name="Add",    value="add"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Clear",  value="clear"),
])
async def slash_watchlist(
    interaction: discord.Interaction,
    action: app_commands.Choice[str] = None,
    ticker: str = None,
):
    await handle_watchlist(InteractionReply(interaction), action.value if action else "show", ticker)
```

The heads-up text is today's, with `ticker.upper()` replaced by `ticker` (already upper-cased by `handle_watchlist`), so it reads the same.

- [ ] **Step 5: Delete the `/watchlist` block from `slash.py`**

In `$WT/swingbot/commands/slash.py`, delete the `/watchlist` banner comment and the whole `slash_watchlist` command (the decorators with their inline `Choice` list, and the body through the `watchlist_clear.callback(ctx)` line).

```bash
git -C $WT grep -n 'name="watchlist"\|commands.watchlist' -- swingbot/commands/slash.py
```

Expected: no hit.

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_watchlist_twin.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
```

Expected: `0 failed`, `0 xfailed` on all four. The parity file gains 9 `watchlist_*` cases.

- [ ] **Step 7: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/watchlist.py $WT/swingbot/commands/slash.py
```

Expected: no output (every function below C). Paste it into the task report.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/commands/watchlist.py swingbot/commands/slash.py tests/commands/parity_cases/watchlist.py tests/commands/test_watchlist_twin.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP14 watchlist handler and action table; /watchlist moves out of slash.py"
```
