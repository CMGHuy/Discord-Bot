# v153 Slash command parity. Part 4: `slash.py` chain II (`backtest`, `watchlist`, `stats`, `scanning/commands`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These tasks continue the `slash.py` chain after part 3 (SP9–SP12). They run **one at a time, in id order**: every one of them edits `swingbot/commands/slash.py`. Each task moves its slash commands out of `slash.py` and into its own module **in the same commit**. A name registered twice raises `CommandAlreadyRegistered` at import, and a name deleted first would be missing, so the move is atomic.

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


async def _prefix_watchlist(ctx, action: str, ticker: str | None = None) -> None:
    reply = CtxReply(ctx)
    await handle_watchlist(reply, action, ticker)
    await send_prefix_tip(ctx, reply)


@bot.group(name="watchlist", invoke_without_command=True)
async def watchlist_cmd(ctx):
    await _prefix_watchlist(ctx, "show")


@watchlist_cmd.command(name="add")
async def watchlist_add(ctx, ticker: str = None):
    await _prefix_watchlist(ctx, "add", ticker)


@watchlist_cmd.command(name="remove")
async def watchlist_remove(ctx, ticker: str = None):
    await _prefix_watchlist(ctx, "remove", ticker)


@watchlist_cmd.command(name="clear")
async def watchlist_clear(ctx):
    await _prefix_watchlist(ctx, "clear")


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

### Task SP15: `stats`: soak, top, stats, lessons, calibration, journal

**Model:** sonnet — six body moves onto handlers in one module, two new twins and four verbatim twin moves; `stats_cmd` and `lessons_cmd` split along their existing branches with no logic change.

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
  - Every chart render stays inside its `lambda target: render_…(…)` line, passed to `asyncio.to_thread(cached_chart, …)`. `test_no_direct_chart_render_calls_outside_to_thread` scans this module line by line, so keep those lines intact.

- [ ] **Step 0: Confirm the chain position, and check v152 D2**

```bash
git -C $WT grep -n 'name="watchlist"' -- swingbot/commands/slash.py
git -C $WT grep -n "PlanActionView(" -- swingbot/commands/stats.py
git -C $WT log --oneline -5 -- swingbot/commands/stats.py
```

Expected: the first is **empty** (SP14 landed; otherwise stop and report `BLOCKED: SP14 missing`). The second shows exactly `view = PlanActionView(plan.plan_id, author_id=ctx.author.id)` inside `top_cmd`.

**If v152 is in flight or landed** (brief §0.1(b)): v152's D2 task edits the same `!top` panel lines (`stats.py:121-124`: `embed = build_embed(...)` and the `PlanActionView` line). If the log shows a v152 commit touching `stats.py`, or the `PlanActionView(` line differs from the one above, keep v152's version of those lines inside `handle_top` and change only `ctx` to `reply` in them. If v152 is in flight but its D2 has not landed, stop and report `BLOCKED: wait for v152 D2 (stats.py !top panel)`.

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
        path = _chart_path()
        monkeypatch.setattr("swingbot.core.analytics.snapshots.load_snapshot", lambda: snap)
        monkeypatch.setattr("swingbot.core.analytics.snapshots.refresh_snapshot", lambda: None)
        monkeypatch.setattr(stats_mod, "stats_embed", lambda s: discord.Embed(title="📐 Analytics"))
        monkeypatch.setattr("swingbot.core.charts.cache.cached_chart", lambda key, render: path)
    return stub


def _stub_trades(trades):
    def stub(monkeypatch):
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
    ParityCase("stats_period_unknown", stats_mod.handle_stats, args=("fortnight",), expect="error"),
    ParityCase("stats_lessons_recent", stats_mod.handle_lessons, stub=_stub_journal),
    ParityCase("stats_lessons_week", stats_mod.handle_lessons, args=("week",), stub=_stub_journal,
               expect="multi_send"),
    ParityCase("stats_lessons_not_a_number", stats_mod.handle_lessons, args=("lots",), expect="error"),
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

(If Step 0 found v152's D2 version of the `embed = …` / `view = …` lines, use those lines here with `ctx` replaced by `reply`.)

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

