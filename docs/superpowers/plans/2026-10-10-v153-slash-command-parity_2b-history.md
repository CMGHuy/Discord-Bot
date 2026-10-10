# v153 Slash command parity. Part 2b: Group 1 module `history` (`!plans`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here.

This is the fourth Group 1 task. It was split out of part 2 (`..._2-group1-modules.md`) only for the 1500-line file cap. The "Shared conventions for this part" block at the top of part 2 applies here unchanged: `$WT`, the SP1 names, the `ParityCase.expect` meanings, `send_error` for validation, and `defer()` after validation. SP8 runs in parallel with SP5–SP7 and with the `slash.py` chain.

# Phase 2: Group 1 modules (continued)

### Task SP8: `history`: `!plans` and `/plans`

**Model:** opus — `plans_cmd` is a legacy D24 body with a progress message edited across three branches; it must be split below 15 with every branch's text and order preserved.

**Files:**
- Modify: `swingbot/commands/history.py` (imports at lines 15-25; `_parse_plans_args` at lines 47-60; `plans_cmd` at lines 250-351, all today)
- Create: `tests/commands/parity_cases/history.py`

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`; `ParityCase`.
- Consumes (existing): `swingbot.commands.backtest.STRATEGY_MAP` (`backtest.py:26`) and `_parse_backtest_args` (`backtest.py:182`, already imported here); `swingbot.commands.slash.HORIZON_CHOICES`, `STRATEGY_CHOICES` (`slash.py:23-52`). `slash.py` never imports `history`, so there is no cycle (index, Circular imports).
- Produces (ledger): `handle_plans(reply, ticker: str | None, horizon: str = "all", strategy: str = "all", date_from: str | None = None, date_to: str | None = None)`. `strategy` is the **normalised** name (a `STRATEGY_MAP` value such as `"Break & Retest"`, or `"all"`), which is what `_parse_backtest_args` yields and what `_query_trade_log` / `_sync_generate_plans` compare against. Also `/plans`: `ticker` required, then optional `from_date`, `to_date`, `horizon` (`HORIZON_CHOICES`) and `strategy` (`STRATEGY_CHOICES`, whose `!`-style alias values go through `STRATEGY_MAP`). The 90-day default window moves into `handle_plans` (`_default_window`), so `/plans` with no dates gets the same window as `!plans`.
- Output:
  - `!plans` texts and their order are unchanged. The tip follows a successful answer.
  - A missing ticker (`USAGE`) and a `from:`/`to:` token in the ticker slot answer through `send_error`, with no tip.
  - The "Could not fetch data" branch still edits the status message. It also sets `reply.failed = True`, so no tip follows a failed answer.

- [ ] **Step 0: Confirm SP1 landed**

```bash
git -C $WT grep -n "class CtxReply\|class InteractionReply\|def send_prefix_tip" -- swingbot/commands/reply.py
git -C $WT grep -n "class ParityCase\|def all_cases" -- tests/commands/reply_harness.py
git -C $WT grep -n "^STRATEGY_MAP\|^def _parse_backtest_args" -- swingbot/commands/backtest.py
git -C $WT grep -n "^HORIZON_CHOICES\|^STRATEGY_CHOICES" -- swingbot/commands/slash.py
```

Expected: hits for every name. If SP13 (`backtest`) has already landed in the worktree, `STRATEGY_MAP` and `_parse_backtest_args` are still at module level there (SP13's ledger row keeps `_parse_backtest_args`). If the slash choices have moved, import them from wherever `slash.py` re-exports them (index, Global Constraints, `slash.HORIZON_CHOICES` stays importable).

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/history.py`:

```python
"""Reply-parity cases for swingbot/commands/history.py (v153 SP8).

The trade-log query and the backtest generator are stubbed; every case
passes explicit dates so the header text never depends on today's date.
"""
from types import SimpleNamespace

from swingbot.commands import history as history_mod
from tests.commands.reply_harness import ParityCase

_WINDOW = {"date_from": "2026-07-01", "date_to": "2026-09-30"}


def _logged(i: int, status: str) -> dict:
    return {
        "id": f"T{i:04d}", "ticker": "TSLA", "direction": "bullish" if i % 2 else "bearish",
        "status": status, "entry_price": 250.0 + i, "stop_loss": 240.0, "take_profit": 280.0,
        "confidence_level": 3, "strategy": "Break & Retest", "horizon_key": "4w",
        "opened_at": f"2026-08-{10 + i:02d}T14:30:00",
    }


def _setup(i: int, outcome: str):
    trade = SimpleNamespace(
        direction="bullish", outcome=outcome, r_multiple=1.8 if outcome == "win" else -1.0,
        entry_date=f"2026-07-{1 + i:02d}", exit_date=None if outcome == "timeout" else f"2026-07-{2 + i:02d}",
        holding_days=3, entry=100.0 + i, stop_loss=95.0, take_profit=110.0,
    )
    return ("Break & Retest", "4w", trade, "$")


def _stub_recorded(monkeypatch):
    rows = [_logged(1, "win"), _logged(2, "loss"), _logged(3, "open")]
    monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: list(rows))


def _stub_generated(n: int):
    setups = [_setup(i, ("win", "loss", "timeout")[i % 3]) for i in range(n)]

    def stub(monkeypatch):
        monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: [])
        monkeypatch.setattr(history_mod, "_sync_generate_plans", lambda *a, **k: (list(setups), 500))
    return stub


def _stub_generate_fails(monkeypatch):
    monkeypatch.setattr(history_mod, "_query_trade_log", lambda *a, **k: [])

    def boom(*_a, **_k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(history_mod, "_sync_generate_plans", boom)


CASES = [
    ParityCase("plans_recorded", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_recorded, expect="edit"),
    ParityCase("plans_generated_batched", history_mod.handle_plans, args=("tsla", "4w", "Break & Retest"),
               kwargs=dict(_WINDOW), stub=_stub_generated(16), expect="edit"),
    ParityCase("plans_generated_none", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_generated(0), expect="edit"),
    ParityCase("plans_generate_fails", history_mod.handle_plans, args=("tsla",), kwargs=dict(_WINDOW),
               stub=_stub_generate_fails, expect="error"),
    ParityCase("plans_no_ticker", history_mod.handle_plans, args=(None,), expect="error"),
    ParityCase("plans_date_in_ticker_slot", history_mod.handle_plans, args=("from:2026-01-01",),
               expect="error"),
]
```

`plans_generated_batched` uses 16 setups, so the joined lines pass the 1800-char batch limit and the batch loop sends more than one message. `plans_generate_fails` edits the status message and then sets `reply.failed`, so the `"error"` expectation (same events, `failed` on both) holds.

- [ ] **Step 2: Run it to see it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.history' has no attribute 'handle_plans'`.

- [ ] **Step 3: Rewrite the `!plans` code in `history.py`**

3a. Replace the import block (lines 15-25 today) with:

```python
import asyncio
import datetime as dt
import logging
from collections import defaultdict

import discord
from discord import app_commands

from swingbot.bot_core import bot
from swingbot.core import presentation as ui
from swingbot.core.scanning import engine as scan_engine
from swingbot.core.marketdata.data import get_daily_data, get_currency_symbol
from swingbot import config
from swingbot.core.market.strategy import live_horizons
from swingbot.commands.backtest import STRATEGY_MAP, _parse_backtest_args
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES, STRATEGY_CHOICES
```

3b. Replace `_parse_plans_args` (lines 47-60 today) with the two functions below. `_parse_plans_args` keeps its name and return shape.

```python
def _default_window(date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    """Default to the last 90 days when neither bound is given."""
    if not date_from and not date_to:
        date_from = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    return date_from, date_to


def _parse_plans_args(args: tuple):
    """
    Same flexible parser as backtest — horizon, strategy, from:, to:.
    Returns (horizon, strategy_norm, date_from, date_to).
    Defaults to last 90 days if no dates given.
    """
    horizon, strategy_norm, date_from, date_to, _list_setups = _parse_backtest_args(args)
    date_from, date_to = _default_window(date_from, date_to)
    return horizon, strategy_norm, date_from, date_to
```

3c. Replace `plans_cmd` (from `@bot.command(name="plans")` to the end of the file) with the code below. Every string is copied verbatim from today's body. The D24 body becomes `handle_plans` plus `_plans_ticker_error`, `_plans_header`, `_post_logged_plans`, `_generated_headline`, `_send_setup_batches` and `_post_generated_plans`.

```python
SETUP_BATCH_CHARS = 1800
GENERATED_FOOTER = (
    "⚠️ *Generated setups are backtest simulations — no fees/slippage. "
    "Overlapping signals within the same strategy/horizon are skipped. "
    "Recorded alerts (`!check`) apply stricter confluence and confidence filters.*"
)


def _plans_ticker_error(ticker: str | None) -> str | None:
    """The answer for an unusable ticker argument, or None when it is usable."""
    if ticker is None:
        return USAGE
    if ticker.upper().startswith(("FROM:", "TO:")):
        return f"⚠️ Please provide a ticker first.\n{USAGE}"
    return None


def _plans_header(ticker: str, horizon: str, strategy_norm: str,
                  date_from: str | None, date_to: str | None) -> str:
    range_str = f"{date_from or '…'} → {date_to or 'now'}"
    horiz_str = f" · horizon `{horizon}`" if horizon != "all" else ""
    strat_str = f" · strategy `{strategy_norm}`" if strategy_norm != "all" else ""
    return f"**{ticker}** · {range_str}{horiz_str}{strat_str}"


async def _post_logged_plans(reply, status_msg, ticker: str, header_ctx: str, logged: list) -> None:
    await status_msg.edit(
        content=f"📋 Found **{len(logged)} recorded** trade plan(s) for {header_ctx}:"
    )
    await reply.send("**Win rate by strategy** (recorded alerts):")
    await reply.send(_build_summary_stats_from_logged(logged))
    for t in logged:
        await reply.send(_format_logged_plan(t))
    await reply.send(
        f"*These are plans the bot actually posted. "
        f"Use `!plans {ticker} ... generate` to also see backtest-generated setups.*"
    )


def _generated_headline(setups: list, header_ctx: str, bar_count: int) -> str:
    ev_count = sum(1 for _, _, t, _ in setups if t.outcome in ("win", "loss"))
    win_count = sum(1 for _, _, t, _ in setups if t.outcome == "win")
    win_pct = f"{win_count/ev_count*100:.0f}%" if ev_count else "n/a"
    total_r = sum(t.r_multiple or 0 for _, _, t, _ in setups if t.outcome in ("win", "loss"))
    total_r_str = f"{total_r:+.1f}R" if ev_count else "n/a"
    return (
        f"⚙️ **{len(setups)} setup(s)** for {header_ctx} ({bar_count} bars)\n"
        f"📊 Closed trades: **{ev_count}** evaluated · **{win_pct}** win rate · **{total_r_str}** total R\n"
        f"*(one trade at a time per strategy/horizon — overlapping signals skipped)*"
    )


async def _send_setup_batches(reply, setups: list) -> None:
    """Individual setups, joined into messages of at most ~SETUP_BATCH_CHARS."""
    batch = []
    for strat, horiz, trade, cur in setups:
        line = _format_generated_plan(strat, horiz, trade, cur)
        batch.append(line)
        if len("\n\n".join(batch)) > SETUP_BATCH_CHARS:
            await reply.send("\n\n".join(batch[:-1]))
            batch = [line]
    if batch:
        await reply.send("\n\n".join(batch))


async def _post_generated_plans(reply, status_msg, ticker: str, header_ctx: str, window: tuple) -> None:
    """Nothing recorded: generate setups from the backtest engine.
    `window` is (horizon, strategy_norm, date_from, date_to)."""
    await status_msg.edit(
        content=(
            f"📭 No recorded plans found for {header_ctx}.\n"
            f"🔄 Generating historical setups via backtest engine…"
        )
    )
    try:
        setups, bar_count = await asyncio.to_thread(_sync_generate_plans, ticker, *window)
    except Exception as e:
        log.warning("!plans %s: could not generate plans", ticker, exc_info=True)
        await status_msg.edit(content=f"⚠️ Could not fetch data for **{ticker}**: {e}")
        reply.failed = True   # an error answer is not followed by the prefix tip
        return

    if not setups:
        await status_msg.edit(
            content=(
                f"📭 No trade setups found for {header_ctx} "
                f"({bar_count} bars of history checked).\n"
                "Try a wider date range, different horizon, or different strategy."
            )
        )
        return

    await status_msg.edit(content=_generated_headline(setups, header_ctx, bar_count))
    await reply.send(_build_summary_stats(setups))
    await _send_setup_batches(reply, setups)
    await reply.send(GENERATED_FOOTER)


async def handle_plans(reply, ticker: str | None, horizon: str = "all", strategy: str = "all",
                       date_from: str | None = None, date_to: str | None = None) -> None:
    """
    Show or generate trade plans for a ticker over a date range.
    `strategy` is a normalised name (a STRATEGY_MAP value) or "all".
    """
    error = _plans_ticker_error(ticker)
    if error:
        await reply.send_error(error)
        return

    ticker = ticker.upper()
    date_from, date_to = _default_window(date_from, date_to)
    header_ctx = _plans_header(ticker, horizon, strategy, date_from, date_to)

    await reply.defer()
    status_msg = await reply.send(f"🔍 Looking up trade plans for {header_ctx}…")

    # --- Step 1: check trade log ---
    logged = _query_trade_log(ticker, horizon, strategy, date_from, date_to)
    if logged:
        await _post_logged_plans(reply, status_msg, ticker, header_ctx, logged)
        return

    # --- Step 2: nothing recorded — generate from backtest ---
    await _post_generated_plans(reply, status_msg, ticker, header_ctx,
                                (horizon, strategy, date_from, date_to))


@bot.command(name="plans")
async def plans_cmd(ctx, ticker: str = None, *args):
    """
    Show or generate trade plans for a ticker over a date range.

    !plans TICKER [from:DATE] [to:DATE] [horizon] [strategy]
    """
    reply = CtxReply(ctx)
    horizon, strategy_norm, date_from, date_to = _parse_plans_args(args)
    await handle_plans(reply, ticker, horizon, strategy_norm, date_from, date_to)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /plans (new in v153)
# ──────────────────────────────────────────────

def _strategy_from_choice(choice) -> str:
    """STRATEGY_CHOICES values are !-style aliases ("bnr"); handle_plans takes
    the normalised name, so they go through the same STRATEGY_MAP as !plans."""
    if choice is None:
        return "all"
    return STRATEGY_MAP.get(choice.value, "all")


@bot.tree.command(name="plans", description="Recorded trade plans for a ticker, or backtest-generated setups if none")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. TSLA",
    from_date="Start date YYYY-MM-DD (default: 90 days ago)",
    to_date="End date YYYY-MM-DD (optional)",
    horizon="Swing horizon (default: all)",
    strategy="Strategy (default: all)",
)
@app_commands.choices(horizon=HORIZON_CHOICES, strategy=STRATEGY_CHOICES)
async def slash_plans(
    interaction: discord.Interaction,
    ticker: str,
    from_date: str = None,
    to_date: str = None,
    horizon: app_commands.Choice[str] = None,
    strategy: app_commands.Choice[str] = None,
):
    await handle_plans(
        InteractionReply(interaction), ticker,
        horizon=horizon.value if horizon else "all",
        strategy=_strategy_from_choice(strategy),
        date_from=from_date, date_to=to_date,
    )
```

Equivalence notes for the reviewer:
- In `!plans` with no ticker, `_parse_plans_args(())` now runs before the usage answer. It is pure and cheap, and the answer is the same `USAGE` text.
- `_query_trade_log` still runs synchronously on the event loop, as it does today. Moving it to a thread is not in scope.
- Every `discord.Color`-free rule still holds (`test_plans_board.py::test_no_direct_colour_remains_in_either_module` scans this file).

- [ ] **Step 4: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_history_format.py
python $WT/scripts/dev/testrun.py file tests/commands/test_plans_board.py
```

Expected: `0 failed`, `0 xfailed` on all three. The six `plans_*` cases pass.

- [ ] **Step 5: Check the slash option order and the strategy mapping**

```bash
PYTHONPATH=$WT python -c "from swingbot.commands import history as h; print([(p.name, p.required) for p in h.slash_plans.parameters]); from discord import app_commands as a; print(h._strategy_from_choice(a.Choice(name='x', value='bnr')), h._strategy_from_choice(None))"
```

Expected: `[('ticker', True), ('from_date', False), ('to_date', False), ('horizon', False), ('strategy', False)]`, then `Break & Retest all`.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/history.py
```

Expected: only `_build_summary_stats` C(11) (unchanged, legacy); `plans_cmd` D24 is gone and every new function is below C. Paste the output into the task report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/commands/history.py tests/commands/parity_cases/history.py
git -C $WT commit -m "feat(v153): SP8 history handle_plans split below 15, new /plans"
```

