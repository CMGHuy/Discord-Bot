# v153 Slash command parity. Part 3: `slash.py` chain I (`info`, `trades` ×2, `plans`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These four tasks are the first half of the **`slash.py` chain** (SP3 → SP4 → SP9 → SP10 → SP11 → SP12 → SP13 → … → SP16). They run **one at a time, in id order**: each one edits `swingbot/commands/slash.py`, deletes the blocks of the slash commands it now owns, and defines those commands again in its own module, in the same commit. They may run in parallel with Group 1 (SP5–SP8), whose files are disjoint.

**Shared conventions for this part** (they restate the index; the index wins on any conflict):

- `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity`. Never `cd`; use `git -C $WT` and absolute paths.
- Consumed from SP1 (`swingbot/commands/reply.py`): `CtxReply`, `InteractionReply`, `send_prefix_tip`. Consumed from SP1 (`tests/commands/reply_harness.py`): `ParityCase`. SP1's `tests/commands/test_reply_parity.py` parametrises over `all_cases()`, which imports every module in `tests/commands/parity_cases/`. Adding a module there is how a task adds its handlers to the harness.
- `ParityCase.expect`: `"send"` = both surfaces give the same `comparable(...)` events, at least one send, no edit, neither reply `failed`. `"multi_send"` = the same with at least two sends. `"error"` = the canned call ends in `send_error`, so `failed` is `True` on both. A `fail_stub` adds a second, failure-path run (`test_handler_error_parity`).
- **Embeds carry a timestamp.** `ui.apply_chrome` sets `embed.timestamp = discord.utils.utcnow()` (`swingbot/core/presentation/components.py:81`). The harness runs the handler twice, so any case whose handler builds a chromed embed must freeze that clock, or the two `embed.to_dict()` differ by microseconds. Every case module in this part has a `_freeze_clock(monkeypatch)` stub for that.
- A validation failure or a "not found" answer goes through `reply.send_error(...)`. On `CtxReply` that is the same channel message as today; it also sets `reply.failed`, so the prefix command sends no tip after it.
- A twin's decorators for the 19 existing slash commands are copied **verbatim** from `slash.py` (name, description, `describe`, `choices`, parameter names and defaults). Only the body changes.
- Narrow test runs only: `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.
- Before Step 1 of each task, confirm the previous chain link landed (each task's Step 0 names the grep).

# Phase 3: `slash.py` chain I

### Task SP9: `info`: strategies, confidence, ticker, strategycharts, regime, ping, help

**Model:** opus — seven handlers, the C15 `!ticker` split, the first atomic `slash.py` move, and the "Union, `!` body as base" output rule applied to four commands at once.

**Files:**
- Modify: `swingbot/commands/info.py` (whole file, 205 lines today)
- Modify: `swingbot/commands/slash.py` (delete the `/ping` `/help` `/confidence` `/strategies` `/regime` `/ticker` blocks; trim imports)
- Create: `tests/commands/parity_cases/info.py`
- Modify: `tests/commands/test_command_error_logging.py` (`_REPLIES` learns `send_error`)
- Modify: `tests/commands/test_stats_commands.py` (`test_six_bridge_commands_still_registered` imports `info`)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`; `ParityCase`. Consumes `slash.HORIZON_CHOICES` (stays in `slash.py`).
- Produces (ledger): `handle_strategies(reply)`, `handle_confidence(reply)`, `handle_ticker(reply, ticker: str)`, `handle_strategycharts(reply, ticker: str, horizon: str = "4w", direction: str = "bullish")`, `handle_regime(reply)`, `handle_ping(reply)`, `handle_help(reply)`; `info.HELP_DESCRIPTION` (SP17 consumes it when it rewrites `handle_help` onto `help_embeds()`). Slash twins `slash_ping`, `slash_help`, `slash_confidence`, `slash_strategies`, `slash_regime`, `slash_ticker` (moved, decorators verbatim) and `slash_strategycharts` (new).
- Output changes (index, Global Constraints "Every resulting `!` output change"): `!strategies` lists the 11 strategies (was 6) and keeps the `(needs N+ trading days of history)` note; `!help`/`!commands` header reads ``Prefix: `!`  •  Slash: `/` ``; `/strategies` gains the history note; tip line after every successful `!` answer. `!regime`'s "Could not fetch" answer, `!ticker`'s fetch failure and `!strategycharts`' validation answers now go through `send_error` (same text; no tip after them). `ephemeral=True` stays on `/ping` `/help` `/confidence` `/strategies` `/regime` and is a no-op on `!`.

- [ ] **Step 0: Confirm the chain so far landed**

```bash
git -C $WT grep -n "class CtxReply\|class InteractionReply\|def send_prefix_tip" -- swingbot/commands/reply.py
git -C $WT grep -n "def on_app_command_error" -- swingbot/commands/slash.py
git -C $WT grep -n 'name="ping"\|name="help"\|name="ticker"' -- swingbot/commands/slash.py
```

Expected: three hits, one hit, three hits. If the first two are empty, stop and report `BLOCKED: SP1/SP3 missing`. (SP4 changes nothing here unless v152 landed; it does not touch these blocks.)

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/info.py`:

```python
"""Reply-parity cases for swingbot/commands/info.py (v153 SP9).

Data seams are stubbed: the snapshot worker, the regime, the chart worker,
daily data and the currency lookup. `ui.apply_chrome` stamps
discord.utils.utcnow() on the /help embed, so that case freezes the clock.
"""
import datetime as dt
import os
import tempfile
import types

import discord
import pandas as pd

from swingbot.commands import info as info_mod
from swingbot.core.planning import plan_engine
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)
_REGIME = types.SimpleNamespace(
    label="Bullish (above 200EMA)", ticker="SPY", close=571.2, ema200=540.0,
    pct_above_ema=5.8, ema_slope_pct=0.42,
)
_PLAN = types.SimpleNamespace(
    strategy="MACD", horizon_key="4w", badge="VALIDATED", badge_stats={"win_rate": 61.2},
    trigger_price=159.5, stop_loss=150.0, tp1=170.0, tp2=181.25,
)


def _freeze_clock(monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _df(rows: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "Close": [100.0 + i for i in range(rows)],
        "Volume": [1_000_000 + i for i in range(rows)],
    })


def _result(strategy: str, horizon: str, trend: str, triggered: bool):
    return types.SimpleNamespace(strategy=strategy, horizon_key=horizon, trend=trend, triggered=triggered)


def _png(name: str) -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-info-"), name)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    return path


def _stub_ping(monkeypatch):
    # bot.latency is NaN while the bot is not connected; round(NaN) raises.
    monkeypatch.setattr(info_mod, "bot", types.SimpleNamespace(latency=0.042))


def _stub_regime(regime):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod.scan_engine, "get_regime", lambda: regime)
    return stub


def _stub_ticker(results, plan=None):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod, "_sync_ticker_snapshot", lambda ticker: (_df(), results, _REGIME))
        monkeypatch.setattr(plan_engine, "build_strategy_plan", lambda *a, **k: plan)
    return stub


def _ticker_down(monkeypatch):
    def boom(ticker):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(info_mod, "_sync_ticker_snapshot", boom)


def _stub_charts(rows: int = 400, paths=lambda: {
        "EMA": _png("AAPL_strategy_EMA.png"), "VWAP": _png("AAPL_strategy_VWAP.png")}):
    def stub(monkeypatch):
        monkeypatch.setattr(info_mod, "get_daily_data", lambda ticker, period: _df(rows))
        monkeypatch.setattr(info_mod, "get_currency_symbol", lambda ticker, default: "$")
        monkeypatch.setattr(info_mod, "_sync_strategy_charts", lambda *a: paths())
    return stub


def _charts_down(monkeypatch):
    def boom(ticker, period):
        raise RuntimeError("no data")
    monkeypatch.setattr(info_mod, "get_daily_data", boom)


_TRIGGERED = [_result("MACD", "4w", "bullish", True), _result("RSI", "2w", "bearish", False)]
_MANY = [_result(f"Strategy{i:02d}", "4w", "bullish", False) for i in range(80)]

CASES = [
    ParityCase("info_strategies", info_mod.handle_strategies),
    ParityCase("info_confidence", info_mod.handle_confidence),
    ParityCase("info_ping", info_mod.handle_ping, stub=_stub_ping),
    ParityCase("info_help", info_mod.handle_help, stub=_freeze_clock),
    ParityCase("info_regime", info_mod.handle_regime, stub=_stub_regime(_REGIME)),
    ParityCase("info_regime_unavailable", info_mod.handle_regime,
               stub=_stub_regime(None), expect="error"),
    ParityCase("info_ticker_no_setup", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_TRIGGERED), fail_stub=_ticker_down, expect="multi_send"),
    ParityCase("info_ticker_with_plan", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_TRIGGERED, _PLAN), expect="multi_send"),
    ParityCase("info_ticker_long_message", info_mod.handle_ticker, args=("aapl",),
               stub=_stub_ticker(_MANY), expect="multi_send"),
    ParityCase("info_strategycharts", info_mod.handle_strategycharts, args=("aapl", "4w", "bullish"),
               stub=_stub_charts(), fail_stub=_charts_down, expect="multi_send"),
    ParityCase("info_strategycharts_no_paths", info_mod.handle_strategycharts, args=("aapl",),
               stub=_stub_charts(paths=dict), expect="multi_send"),
    ParityCase("info_strategycharts_short_history", info_mod.handle_strategycharts, args=("aapl",),
               stub=_stub_charts(rows=5), expect="error"),
    ParityCase("info_strategycharts_bad_horizon", info_mod.handle_strategycharts,
               args=("aapl", "zz"), expect="error"),
    ParityCase("info_strategycharts_bad_direction", info_mod.handle_strategycharts,
               args=("aapl", "4w", "sideways"), expect="error"),
]
```

- [ ] **Step 2: Run it to see it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.info' has no attribute 'handle_strategies'`.

- [ ] **Step 3: Rewrite `info.py` onto handlers, with the twins**

Replace the whole of `$WT/swingbot/commands/info.py` with the code below. Every text is today's `!` text, except the four "Union" changes listed under Interfaces. `ticker_cmd` (C15) is split into `_ticker_table_lines`, `_signal_plan`, `_ticker_plan_lines` and `_message_parts`; the split keeps every line, the plan-engine import at call time (so tests can patch it) and the 1990-char newline split.

```python
"""!strategies, !confidence, !regime, !ticker, !strategycharts, !commands/!help,
!ping, and their slash twins (v153).

Each body lives in one handle_<name>(reply, ...) handler. The prefix command
and the slash twin both call it through a Reply (swingbot/commands/reply.py),
so the two surfaces cannot drift.
"""
import asyncio
import logging
import os

import discord
from discord import app_commands

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.scanning import engine as scan_engine
from swingbot.bot_core import bot, CONFIDENCE_EXPLAINER, COMMANDS_BY_CATEGORY
from swingbot.core.marketdata.data import get_currency_symbol, get_daily_data
from swingbot.core.market.strategy import HORIZONS, MIN_BARS, evaluate_all, live_horizons
from swingbot.core.charts.trade_chart import generate_all_strategy_charts
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import HORIZON_CHOICES

log = logging.getLogger(__name__)

#: The help embed's description; SP17's help_embeds() reuses it.
HELP_DESCRIPTION = "Alerts only, never places trades. Prefix: `!`  •  Slash: `/`"

STRATEGY_NAMES = (
    "EMA Crossover, VWAP, Fibonacci retracement, Support/Resistance breakout, "
    "RSI mean-reversion, MACD, Elliott Wave, MA Ribbon, Break & Retest, RSI Divergence, Volume Profile"
)

#: !ticker splits its snapshot on a newline at or before this many chars.
TICKER_MESSAGE_LIMIT = 1990

# /strategycharts draws one horizon; "all" is a scan choice, not a chart horizon.
CHART_HORIZON_CHOICES = [choice for choice in HORIZON_CHOICES if choice.value != "all"]
DIRECTION_CHOICES = [
    app_commands.Choice(name="bullish", value="bullish"),
    app_commands.Choice(name="bearish", value="bearish"),
]


def format_signal_plan_line(plan) -> str:
    """Compact !ticker plan line: 'MACD 4w ✅ 81.3% | entry 101.20 stop
    99.10 tp1 101.94 tp2 104.00' (tp2 clause omitted when there's no TP2)."""
    badge_mark = "✅" if plan.badge == "VALIDATED" else "⚠️"
    wr = (plan.badge_stats or {}).get("win_rate", 0.0)
    line = (f"{plan.strategy} {plan.horizon_key} {badge_mark} {wr:.1f}% | "
           f"entry {plan.trigger_price:.2f} stop {plan.stop_loss:.2f} "
           f"tp1 {plan.tp1:.2f}")
    if plan.tp2 is not None:
        line += f" tp2 {plan.tp2:.2f}"
    return line


def _sync_ticker_snapshot(ticker: str):
    """All the blocking work for !ticker (network fetch, indicator computation) in one place, run via to_thread."""
    df = get_daily_data(ticker, period=config.DEFAULT_HISTORY_PERIOD)
    results = evaluate_all(ticker, df)
    regime = scan_engine.get_regime()
    return df, results, regime


def _ticker_table_lines(ticker: str, df, results, regime) -> list[str]:
    last_close = float(df["Close"].iloc[-1])
    last_vol = int(df["Volume"].iloc[-1])

    lines = [f"**{ticker}** snapshot — close {last_close:.2f}, volume {last_vol:,}"]
    if regime:
        lines.append(f"Market regime: {regime.label}")
    lines.append("```")
    lines.append(f"{'Strategy':18s} {'Horiz':5s} {'Bias':8s} {'Fresh today':>11s}")
    for r in results:
        fresh = "YES" if r.triggered else ""
        lines.append(f"{r.strategy:18s} {r.horizon_key:5s} {r.trend:8s} {fresh:>11s}")
    lines.append("```")
    lines.append(
        "'Fresh today' = the signal crossed on today's candle. Only Level "
        f"{config.MIN_ALERT_CONFIDENCE_LEVEL}+ confidence signals become alerts via `!check`; "
        "everything is shown here regardless of confidence."
    )
    return lines


def _signal_plan(df, ticker: str, r):
    from swingbot.core.planning.plan_engine import build_strategy_plan
    try:
        return build_strategy_plan(df, len(df) - 1, ticker=ticker,
                                   strategy=r.strategy, horizon_key=r.horizon_key,
                                   direction=r.trend)
    except Exception:
        return None


def _ticker_plan_lines(ticker: str, df, results) -> list[str]:
    plan_lines = []
    for r in results:
        if not r.triggered:
            continue
        plan = _signal_plan(df, ticker, r)
        if plan is not None:
            plan_lines.append(format_signal_plan_line(plan))
    if plan_lines:
        return ["**Trade plans (v2)**", *plan_lines]
    if any(r.triggered for r in results):
        return [
            f"**Trade plans (v2)** — no qualifying setup: no level beyond entry "
            f"pays {config.MIN_RISK_REWARD_RATIO:.1f}:1 against its own stop."]
    return []


def _message_parts(msg: str, limit: int = TICKER_MESSAGE_LIMIT) -> list[str]:
    """Split on the last newline at or before `limit`; a whitespace-only tail is dropped."""
    parts = []
    while len(msg) > limit:
        split_at = msg.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        parts.append(msg[:split_at])
        msg = msg[split_at:]
    if msg.strip():
        parts.append(msg)
    return parts


def _sync_strategy_charts(ticker: str, df, direction: str, h: dict, currency_symbol: str):
    """All the blocking work for !strategycharts (chart rendering for every strategy) in one place, run via to_thread."""
    return generate_all_strategy_charts(
        ticker, df, direction, h["label"], config.TRADE_CHART_DIR, h,
        currency_symbol=currency_symbol, filename_prefix=f"{ticker}_strategy",
    )


def _strategycharts_problem(horizon: str, direction: str) -> str | None:
    if horizon not in live_horizons():
        return f"Unknown horizon '{horizon}'. Use one of: {', '.join(live_horizons())}"
    if direction not in ("bullish", "bearish"):
        return "Direction must be 'bullish' or 'bearish'."
    return None


def _help_embed() -> discord.Embed:
    embed = discord.Embed(title="📖 Swing Trade Bot — Commands", description=HELP_DESCRIPTION)
    for category, cmds in COMMANDS_BY_CATEGORY.items():
        value = "\n".join(f"`{cmd}` — {desc}" for cmd, desc in cmds)
        embed.add_field(name=category, value=value, inline=False)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome("scratch"))
    return embed


# ──────────────────────────────────────────────
# Handlers (one body per command, shared by ! and /)
# ──────────────────────────────────────────────

async def handle_strategies(reply) -> None:
    lines = [f"**Strategies:** {STRATEGY_NAMES}", "", "**Swing horizons:**"]
    for key in live_horizons():
        h = HORIZONS[key]
        lines.append(f"`{key}` — {h['label']} (needs {MIN_BARS[key]}+ trading days of history)")
    await reply.send("\n".join(lines), ephemeral=True)


async def handle_confidence(reply) -> None:
    await reply.send(CONFIDENCE_EXPLAINER, ephemeral=True)


async def handle_ticker(reply, ticker: str) -> None:
    """Full current-state snapshot for one ticker, independent of alert confirmation or confidence filter."""
    ticker = ticker.upper()
    await reply.send(f"Pulling a full snapshot for {ticker}…")
    try:
        df, results, regime = await asyncio.to_thread(_sync_ticker_snapshot, ticker)
    except Exception as e:
        log.warning("!ticker %s: could not fetch data", ticker, exc_info=True)
        await reply.send_error(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
    lines = _ticker_table_lines(ticker, df, results, regime) + _ticker_plan_lines(ticker, df, results)
    for part in _message_parts("\n".join(lines)):
        await reply.send(part)


async def handle_strategycharts(reply, ticker: str, horizon: str = "4w", direction: str = "bullish") -> None:
    """
    Generates one standalone chart per supported strategy (EMA, VWAP,
    Fibonacci, FVG, Bollinger, Donchian, Rolling S/R, Floor Pivot,
    Zigzag Pivot, Trendline) for one ticker -- what EACH strategy says
    on its OWN, not the merged multi-strategy consensus level !check
    alerts show. A diagnostic/exploration tool: it does NOT apply the
    usual reward/stop/risk-reward/confidence/confluence filters, so a
    chart showing up here doesn't mean it would ever qualify as a real
    alert.
    """
    ticker, horizon, direction = ticker.upper(), horizon.lower(), direction.lower()
    problem = _strategycharts_problem(horizon, direction)
    if problem:
        await reply.send_error(problem)
        return

    h = HORIZONS[horizon]
    await reply.send(f"Simulating every supported strategy for {ticker} ({h['label']}, {direction})…")
    try:
        df = await asyncio.to_thread(get_daily_data, ticker, config.DEFAULT_HISTORY_PERIOD)
    except Exception as e:
        log.warning("!strategycharts %s: could not fetch data", ticker, exc_info=True)
        await reply.send_error(f"⚠️ Could not fetch data for {ticker}: {e}")
        return
    if len(df) < MIN_BARS.get(horizon, 0):
        await reply.send_error(
            f"Not enough history for {ticker} at this horizon ({len(df)} bars, needs {MIN_BARS[horizon]}+).")
        return

    currency_symbol = get_currency_symbol(ticker, config.CURRENCY_SYMBOL)
    paths = await asyncio.to_thread(_sync_strategy_charts, ticker, df, direction, h, currency_symbol)
    if not paths:
        await reply.send(f"No strategy currently has a usable {direction} level for {ticker} at this horizon.")
        return

    await reply.send(
        f"**{len(paths)} strategy chart(s) for {ticker}** ({h['label']}, {direction}) -- each shows what THAT ONE "
        "strategy alone thinks the next level is; none of `!check`'s usual filters are applied here."
    )
    for family, path in paths.items():
        await reply.send(f"**{family}**", file=discord.File(path, filename=os.path.basename(path)))


async def handle_regime(reply) -> None:
    await reply.defer(ephemeral=True)
    regime = await asyncio.to_thread(scan_engine.get_regime)
    if regime is None:
        await reply.send_error("Could not fetch market regime right now.")
        return
    await reply.send(
        f"**Market regime:** {regime.label}\n"
        f"{regime.ticker} close: {regime.close} | 200EMA: {regime.ema200} "
        f"({regime.pct_above_ema:+.1f}%) | 200EMA slope (20d): {regime.ema_slope_pct:+.2f}%\n\n"
        f"This feeds into confidence scoring (+10 pts when a signal agrees with the regime).",
        ephemeral=True,
    )


async def handle_ping(reply) -> None:
    await reply.send(f"🏓 Pong! {round(bot.latency * 1000)}ms", ephemeral=True)


async def handle_help(reply) -> None:
    await reply.send(embed=_help_embed(), ephemeral=True)


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.command(name="strategies")
async def strategies_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_strategies(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="confidence")
async def confidence_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_confidence(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="ticker")
async def ticker_cmd(ctx, ticker: str):
    """Full current-state snapshot for one ticker, independent of alert confirmation or confidence filter."""
    reply = CtxReply(ctx)
    await handle_ticker(reply, ticker)
    await send_prefix_tip(ctx, reply)


@bot.command(name="strategycharts")
async def strategycharts_cmd(ctx, ticker: str, horizon: str = "4w", direction: str = "bullish"):
    """One standalone chart per strategy for one ticker (diagnostic; no alert filters)."""
    reply = CtxReply(ctx)
    await handle_strategycharts(reply, ticker, horizon, direction)
    await send_prefix_tip(ctx, reply)


@bot.command(name="regime")
async def regime_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_regime(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="ping")
async def ping_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_ping(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="commands", aliases=["help"])
async def commands_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_help(reply)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (moved from slash.py in v153, decorators verbatim;
# /strategycharts is new)
# ──────────────────────────────────────────────

@bot.tree.command(name="ping", description="Check bot latency")
async def slash_ping(interaction: discord.Interaction):
    await handle_ping(InteractionReply(interaction))


@bot.tree.command(name="help", description="Show all available commands")
async def slash_help(interaction: discord.Interaction):
    await handle_help(InteractionReply(interaction))


@bot.tree.command(name="confidence", description="Explain the 5 confidence levels")
async def slash_confidence(interaction: discord.Interaction):
    await handle_confidence(InteractionReply(interaction))


@bot.tree.command(name="strategies", description="List available strategies and swing horizons")
async def slash_strategies(interaction: discord.Interaction):
    await handle_strategies(InteractionReply(interaction))


@bot.tree.command(name="regime", description="Show current broad market regime (SPY trend)")
async def slash_regime(interaction: discord.Interaction):
    await handle_regime(InteractionReply(interaction))


@bot.tree.command(name="ticker", description="Full bias snapshot for a single stock across all strategies")
@app_commands.describe(ticker="Stock ticker symbol, e.g. AAPL")
async def slash_ticker(interaction: discord.Interaction, ticker: str):
    await handle_ticker(InteractionReply(interaction), ticker)


@bot.tree.command(name="strategycharts",
                  description="One chart per strategy for a ticker (diagnostic, no alert filters)")
@app_commands.describe(
    ticker="Stock ticker symbol, e.g. AAPL",
    horizon="Swing horizon (default: 4w)",
    direction="Trade direction (default: bullish)",
)
@app_commands.choices(horizon=CHART_HORIZON_CHOICES, direction=DIRECTION_CHOICES)
async def slash_strategycharts(
    interaction: discord.Interaction,
    ticker: str,
    horizon: app_commands.Choice[str] = None,
    direction: app_commands.Choice[str] = None,
):
    await handle_strategycharts(
        InteractionReply(interaction), ticker,
        horizon.value if horizon else "4w",
        direction.value if direction else "bullish",
    )
```

- [ ] **Step 4: Delete the six moved blocks from `slash.py` (same commit)**

In `$WT/swingbot/commands/slash.py`, delete each of these blocks whole, including its `# ────` banner comment pair and the blank lines after it:

| Banner | Function |
|---|---|
| `# /ping` | `slash_ping` |
| `# /help` | `slash_help` |
| `# /confidence` | `slash_confidence` |
| `# /strategies` | `slash_strategies` |
| `# /regime` | `slash_regime` |
| `# /ticker` | `slash_ticker` |

Then trim the imports those blocks alone used. Replace

```python
from swingbot.bot_core import bot, COMMANDS_BY_CATEGORY, CONFIDENCE_EXPLAINER
from swingbot.core import presentation as ui
from swingbot.core.market.strategy import HORIZONS, live_horizons
```

with

```python
from swingbot.bot_core import bot
from swingbot.core.market.strategy import live_horizons
```

`import asyncio` stays (`/pnl` still uses it until SP11), as do `commands` (bridges) and `scan_engine` (`/stop` until SP16). Check nothing dangling is left:

```bash
grep -n "ui\.\|HORIZONS\[\|COMMANDS_BY_CATEGORY\|CONFIDENCE_EXPLAINER\|def slash_ping\|def slash_help\|def slash_confidence\|def slash_strategies\|def slash_regime\|def slash_ticker" $WT/swingbot/commands/slash.py
python -m py_compile $WT/swingbot/commands/slash.py $WT/swingbot/commands/info.py
```

Expected: grep prints nothing; py_compile is silent.

- [ ] **Step 5: Keep the registration and error-logging tests honest**

In `$WT/tests/commands/test_stats_commands.py`, inside `test_six_bridge_commands_still_registered`, directly under `import swingbot.commands.slash  # noqa: F401  -- registers on import`, add:

```python
    import swingbot.commands.info  # noqa: F401  -- v153 SP9: /ticker moved here
```

In `$WT/tests/commands/test_command_error_logging.py`, replace line 8

```python
_REPLIES = {"send", "send_message", "edit"}
```

with

```python
# v153: handlers answer through a Reply; send_error is a reply too.
_REPLIES = {"send", "send_message", "edit", "send_error"}
```

`test_ticker_command_failure_is_logged_and_still_shown` stays as written: its `_Ctx` has no `command`, so `send_prefix_tip` sends nothing and `ctx.sent[-1]` is still the error text, which `CtxReply.send_error` passes positionally.

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_views.py
python $WT/scripts/dev/testrun.py file tests/market/test_v113_horizon_vocab.py
```

Expected: every run `0 failed`, `0 xfailed`; the 14 `info_*` cases and `test_handler_error_parity[info_ticker_no_setup]`, `[info_strategycharts]` pass. If `test_command_error_logging` now flags a handler in another module, that handler answers an `except Exception` without logging: report it, do not edit another task's module.

- [ ] **Step 7: Check the tree**

```bash
PYTHONPATH=$WT python -c "import swingbot.commands.info, swingbot.commands.slash; from swingbot.bot_core import bot; names = sorted(c.name for c in bot.tree.get_commands()); print(len(names), names)"
```

Expected: the names include `confidence help ping regime strategies strategycharts ticker`, each once (a duplicate would have raised `CommandAlreadyRegistered` on import), plus the 13 commands still in `slash.py`.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/info.py $WT/swingbot/commands/slash.py
```

Expected: nothing printed (`ticker_cmd` was C15; every new function is below C). Paste the output, or `(none)`, into the task report.

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/commands/info.py swingbot/commands/slash.py tests/commands/parity_cases/info.py tests/commands/test_command_error_logging.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP9 info handlers; /ping /help /confidence /strategies /regime /ticker move to info.py, /strategycharts new"
```

### Task SP10: `trades` I: trades, trades clear, clear history, trade, trade delete, tradecharts

**Model:** sonnet — six mechanical body moves, one moved slash command and one `app_commands.Group`; no body is at or over complexity 15.

**Files:**
- Modify: `swingbot/commands/trades.py` (lines 1-18 imports, 167-200 and 311-356 commands; a twins section appended at the end)
- Modify: `swingbot/commands/slash.py` (delete the `/trades` block)
- Create: `tests/commands/parity_cases/trades.py` (SP11 extends it)
- Modify: `tests/commands/test_stats_commands.py` (`test_six_bridge_commands_still_registered` imports `trades`)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`; `ParityCase`. Consumes `slash.TRADE_FILTER_CHOICES` (stays in `slash.py`).
- Produces (ledger): `handle_trades(reply, status: str = "all", per_page: int = DEFAULT_PER_PAGE)`, `handle_trades_clear(reply)`, `handle_trades_clear_history(reply)`, `handle_trade_show(reply, trade_id: str)`, `handle_trade_delete(reply, trade_id: str)`, `handle_tradecharts(reply, status: str = "open", limit: int = 5)`. Slash: `/trades` (moved, decorators verbatim), `/trades-clear`, `/trades-clear-history`, `trade_group` = `/trade` with `show` and `delete`, `/tradecharts`. SP18 reads `trades-clear`, `trades-clear-history`, `trade show`, `trade delete` as `SLASH_TWIN` values.
- Also produces, for SP11 to reuse: the `# / slash twins (v153)` section at the end of `trades.py`, and in `tests/commands/parity_cases/trades.py` the `_FakeLog`, `_stub`, `_freeze_clock` and `_png` helpers.
- Output: `!trades`, `!trade`, `!tradecharts` text unchanged. Their "Status must be one of…" and "No trade found…" answers now go through `send_error` (same text; no tip after them). `TradesPaginator` keys on `reply.author.id` (was `ctx.author.id`; same user on `!`).

- [ ] **Step 0: Confirm SP9 landed**

```bash
git -C $WT grep -n "def handle_ticker" -- swingbot/commands/info.py
git -C $WT grep -n 'name="trades"' -- swingbot/commands/slash.py
```

Expected: one hit each. Otherwise stop and report `BLOCKED: SP9 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/trades.py`:

```python
"""Reply-parity cases for swingbot/commands/trades.py (v153 SP10, SP11).

`trade_log` is replaced by an in-memory _FakeLog; chart rendering returns a
tiny PNG on disk (discord.File opens it); the currency lookup is fixed; the
embed clock is frozen because apply_chrome stamps utcnow().
"""
import datetime as dt
import os
import tempfile

import discord

from swingbot.commands import trades as trades_mod
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)

OPEN_TRADE = {
    "id": "T0001", "ticker": "AAPL", "strategy": "S/R Confluence",
    "target_sources": ["Fibonacci 61.8%"], "stop_sources": [], "horizon_key": "4w",
    "direction": "bullish", "confidence_level": 4, "entry": 180.0, "stop_loss": 172.0,
    "take_profit": 196.0, "target2": 204.0, "risk_reward_ratio": 2.0, "status": "open",
    "opened_at": "2026-10-09T08:45:00+00:00", "shares": 5, "plan_id": "p-aapl-0001",
}
WIN_TRADE = {
    "id": "T0002", "ticker": "MSFT", "strategy": "S/R Confluence",
    "target_sources": [], "stop_sources": [], "horizon_key": "2w",
    "direction": "bearish", "confidence_level": 3, "entry": 430.0, "stop_loss": 440.0,
    "take_profit": 410.0, "status": "win", "opened_at": "2026-10-06T09:00:00+00:00",
    "closed_at": "2026-10-09T13:10:00+00:00", "exit_price": 412.0,
    "realized_pnl_amount": 90.0, "shares": 5, "close_reason": "TP1 hit",
}
LOSS_TRADE = {
    **WIN_TRADE, "id": "T0003", "ticker": "NVDA", "status": "loss", "direction": "bullish",
    "entry": 120.0, "stop_loss": 114.0, "take_profit": 132.0, "exit_price": 114.0,
    "realized_pnl_amount": -30.0, "close_reason": "stop hit",
}
ALL_TRADES = [OPEN_TRADE, WIN_TRADE, LOSS_TRADE]


class _FakeLog:
    """The slice of TradeLog that trades.py calls."""

    def __init__(self, trades):
        self.trades = list(trades)

    def get_trades(self, status="all", limit=None, sort_by=None, ledger=None):
        rows = [t for t in self.trades if status == "all" or t["status"] == status]
        return rows[:limit] if limit else rows

    def clear_open(self):
        return sum(1 for t in self.trades if t["status"] == "open")

    def clear_history(self):
        return sum(1 for t in self.trades if t["status"] != "open")

    def get_trade_by_id(self, trade_id):
        return next((t for t in self.trades if t["id"] == trade_id), None)

    def delete_trade(self, trade_id):
        return self.get_trade_by_id(trade_id) is not None

    def get_stats(self, level=None, ledger=None):
        rows = [t for t in self.trades if level is None or t["confidence_level"] == level]
        wins = sum(1 for t in rows if t["status"] == "win")
        losses = sum(1 for t in rows if t["status"] == "loss")
        closed = wins + losses
        return {"total": len(rows), "open": sum(1 for t in rows if t["status"] == "open"),
                "closed": closed, "wins": wins, "losses": losses,
                "win_rate": wins / closed * 100 if closed else None}

    def get_stats_by_confidence(self):
        return {lvl: self.get_stats(lvl) for lvl in range(1, 6)}

    def weak_summary(self):
        return {"wins": 1, "losses": 2, "n": 3, "total_pnl": -12.5}


def _freeze_clock(monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)


def _png(name: str) -> str:
    path = os.path.join(tempfile.mkdtemp(prefix="v153-trades-"), name)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    return path


def _chart_for_open(trade):
    return _png(f"{trade['id']}_chart.png") if trade["status"] == "open" else None


def _stub(trades=ALL_TRADES, chart=_chart_for_open):
    def stub(monkeypatch):
        monkeypatch.setattr(trades_mod, "trade_log", _FakeLog(trades))
        monkeypatch.setattr(trades_mod.scan_engine, "regenerate_chart_for_trade", chart)
        monkeypatch.setattr(trades_mod, "get_currency_symbol", lambda ticker, default: "$")
        _freeze_clock(monkeypatch)
    return stub


CASES = [
    ParityCase("trades_all", trades_mod.handle_trades, stub=_stub()),
    ParityCase("trades_open_two_per_page", trades_mod.handle_trades, args=("open", 2), stub=_stub()),
    ParityCase("trades_empty", trades_mod.handle_trades, args=("win",), stub=_stub([OPEN_TRADE])),
    ParityCase("trades_bad_status", trades_mod.handle_trades, args=("pending",),
               stub=_stub(), expect="error"),
    ParityCase("trades_clear", trades_mod.handle_trades_clear, stub=_stub()),
    ParityCase("trades_clear_history", trades_mod.handle_trades_clear_history, stub=_stub()),
    ParityCase("trade_show_with_chart", trades_mod.handle_trade_show, args=("T0001",), stub=_stub()),
    ParityCase("trade_show_closed_no_chart", trades_mod.handle_trade_show, args=("T0002",), stub=_stub()),
    ParityCase("trade_show_missing", trades_mod.handle_trade_show, args=("NOPE",),
               stub=_stub(), expect="error"),
    ParityCase("trade_delete", trades_mod.handle_trade_delete, args=("T0003",), stub=_stub()),
    ParityCase("trade_delete_missing", trades_mod.handle_trade_delete, args=("NOPE",),
               stub=_stub(), expect="error"),
    ParityCase("tradecharts_all", trades_mod.handle_tradecharts, args=("all", 3),
               stub=_stub(), expect="multi_send"),
    ParityCase("tradecharts_empty", trades_mod.handle_tradecharts, args=("loss",),
               stub=_stub([OPEN_TRADE])),
    ParityCase("tradecharts_bad_status", trades_mod.handle_tradecharts, args=("pending",),
               stub=_stub(), expect="error"),
]
```

- [ ] **Step 2: Run it to see it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.trades' has no attribute 'handle_trades'`.

- [ ] **Step 3: Imports**

In `$WT/swingbot/commands/trades.py`, change the module docstring (line 1) to

```python
"""!trades, !trade, !tradecharts, !performance, !pnl, !summary, and their slash twins (v153)."""
```

and below `import discord` add `from discord import app_commands`; below `from swingbot.bot_core import bot` add:

```python
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import TRADE_FILTER_CHOICES
```

Below `DEFAULT_PER_PAGE = 10` add:

```python
TRADE_STATUSES = ("open", "win", "loss", "all")
STATUS_ERROR = "Status must be one of: open, win, loss, all"
```

- [ ] **Step 4: `!trades`, `!trades clear`, `!trades clear history` onto handlers**

Replace today's lines 167-200 (from `@bot.group(name="trades", invoke_without_command=True)` through the end of `trades_clear_history`) with:

```python
async def handle_trades(reply, status: str = "all", per_page: int = DEFAULT_PER_PAGE) -> None:
    """
    Shows every logged trade -- any confidence level, any status by
    default -- sorted highest confidence first, paginated with Prev/Next
    buttons. `per_page` sets how many rows show per page (1-25).
    """
    if status not in TRADE_STATUSES:
        await reply.send_error(STATUS_ERROR)
        return
    per_page = max(MIN_PER_PAGE, min(per_page, MAX_PER_PAGE))
    await reply.defer()

    trades = trade_log.get_trades(status=status, limit=None, sort_by="confidence")
    if not trades:
        await reply.send(f"No trades found for status='{status}'.")
        return

    view = TradesPaginator(trades, f"**Trades ({status}, sorted by confidence high→low)**", per_page,
                           reply.author.id)
    view.message = await reply.send(view.render(), view=view)


async def handle_trades_clear(reply) -> None:
    """Clear all currently OPEN/active trades. Closed trade history is kept."""
    count = trade_log.clear_open()
    await reply.send(f"Cleared {count} open trade(s). Closed win/loss history was not touched.")


async def handle_trades_clear_history(reply) -> None:
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    count = trade_log.clear_history()
    await reply.send(f"Cleared {count} closed trade record(s). Open trades were not touched.")


@bot.group(name="trades", invoke_without_command=True)
async def trades_cmd(ctx, status: str = "all", per_page: int = DEFAULT_PER_PAGE):
    """
    Shows every logged trade -- any confidence level, any status by
    default -- sorted highest confidence first, paginated with Prev/Next
    buttons. `per_page` sets how many rows show per page (1-25).
    """
    reply = CtxReply(ctx)
    await handle_trades(reply, status, per_page)
    await send_prefix_tip(ctx, reply)


@trades_cmd.group(name="clear", invoke_without_command=True)
async def trades_clear(ctx):
    """Clear all currently OPEN/active trades. Closed trade history is kept.
    Use `!trades clear history` to remove closed trade records instead."""
    reply = CtxReply(ctx)
    await handle_trades_clear(reply)
    await send_prefix_tip(ctx, reply)


@trades_clear.command(name="history")
async def trades_clear_history(ctx):
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    reply = CtxReply(ctx)
    await handle_trades_clear_history(reply)
    await send_prefix_tip(ctx, reply)
```

- [ ] **Step 5: `!trade`, `!trade delete`, `!tradecharts` onto handlers**

Replace today's lines 311-356 (from `@bot.group(name="trade", invoke_without_command=True)` through the end of `tradecharts_cmd`) with:

```python
async def handle_trade_show(reply, trade_id: str) -> None:
    match = trade_log.get_trade_by_id(trade_id)
    if not match:
        await reply.send_error(f"No trade found with id `{trade_id}`. Use `!trades` to list recent ones.")
        return
    await reply.defer()

    embed = _build_trade_detail_embed(match)
    chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, match)
    if chart_path:
        filename = os.path.basename(chart_path)
        embed.set_image(url=f"attachment://{filename}")
        await reply.send(embed=embed, file=discord.File(chart_path, filename=filename))
    else:
        embed.add_field(name="⚠️ Chart", value="Could not generate a chart for this trade right now.", inline=False)
        await reply.send(embed=embed)


async def handle_trade_delete(reply, trade_id: str) -> None:
    deleted = trade_log.delete_trade(trade_id)
    if not deleted:
        await reply.send_error(f"No trade found with id `{trade_id}`.")
        return
    await reply.send(f"Deleted trade `{trade_id}`.")


async def handle_tradecharts(reply, status: str = "open", limit: int = 5) -> None:
    if status not in TRADE_STATUSES:
        await reply.send_error(STATUS_ERROR)
        return
    limit = min(limit, 10)
    trades = trade_log.get_trades(status=status, limit=limit)
    if not trades:
        await reply.send(f"No trades found for status='{status}'.")
        return

    await reply.send(f"Generating charts for {len(trades)} trade(s)…")
    for t in trades:
        chart_path = await asyncio.to_thread(scan_engine.regenerate_chart_for_trade, t)
        caption = f"**{t['id']}** {t['ticker']} — {t['strategy']} ({t['horizon_key']}), {t['direction']}, status: {t['status']}"
        if chart_path:
            await reply.send(caption, file=discord.File(chart_path, filename=os.path.basename(chart_path)))
        else:
            await reply.send(caption + " (chart unavailable)")


@bot.group(name="trade", invoke_without_command=True)
async def trade_cmd(ctx, trade_id: str):
    reply = CtxReply(ctx)
    await handle_trade_show(reply, trade_id)
    await send_prefix_tip(ctx, reply)


@trade_cmd.command(name="delete")
async def trade_delete(ctx, trade_id: str):
    reply = CtxReply(ctx)
    await handle_trade_delete(reply, trade_id)
    await send_prefix_tip(ctx, reply)


@bot.command(name="tradecharts")
async def tradecharts_cmd(ctx, status: str = "open", limit: int = 5):
    reply = CtxReply(ctx)
    await handle_tradecharts(reply, status, limit)
    await send_prefix_tip(ctx, reply)
```

- [ ] **Step 6: The twins section (end of `trades.py`)**

Append to the end of `$WT/swingbot/commands/trades.py`, after `summary_cmd`. The `/trades` decorators are copied verbatim from `slash.py`. SP11 appends its own twins to this section.

```python


# ──────────────────────────────────────────────
# / slash twins (v153). /trades moved from slash.py with its decorators
# verbatim. A command cannot also be a group, so `!trades clear` and
# `!trades clear history` become the top-level /trades-clear and
# /trades-clear-history; `!trade` alone maps to /trade show.
# ──────────────────────────────────────────────

@bot.tree.command(name="trades", description="List logged trades with pagination")
@app_commands.describe(
    filter="Filter by trade status (default: all)",
    per_page="Trades per page (default: 10)",
)
@app_commands.choices(filter=TRADE_FILTER_CHOICES)
async def slash_trades(
    interaction: discord.Interaction,
    filter: app_commands.Choice[str] = None,
    per_page: int = 10,
):
    await handle_trades(InteractionReply(interaction), filter.value if filter else "all", per_page)


@bot.tree.command(name="trades-clear", description="Clear all open trades (closed trade history is kept)")
async def slash_trades_clear(interaction: discord.Interaction):
    await handle_trades_clear(InteractionReply(interaction))


@bot.tree.command(name="trades-clear-history", description="Clear all closed trade records (open trades are kept)")
async def slash_trades_clear_history(interaction: discord.Interaction):
    await handle_trades_clear_history(InteractionReply(interaction))


trade_group = app_commands.Group(name="trade", description="Show or delete one logged trade")


@trade_group.command(name="show", description="Full detail and chart for one trade")
@app_commands.describe(trade_id="Trade ID, as listed by /trades")
async def slash_trade_show(interaction: discord.Interaction, trade_id: str):
    await handle_trade_show(InteractionReply(interaction), trade_id)


@trade_group.command(name="delete", description="Delete one logged trade")
@app_commands.describe(trade_id="Trade ID, as listed by /trades")
async def slash_trade_delete(interaction: discord.Interaction, trade_id: str):
    await handle_trade_delete(InteractionReply(interaction), trade_id)


bot.tree.add_command(trade_group)


@bot.tree.command(name="tradecharts", description="Chart the most recent trades of one status")
@app_commands.describe(
    status="Trade status (default: open)",
    limit="How many trades to chart (max 10, default 5)",
)
@app_commands.choices(status=TRADE_FILTER_CHOICES)
async def slash_tradecharts(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] = None,
    limit: int = 5,
):
    await handle_tradecharts(InteractionReply(interaction), status.value if status else "open", limit)
```

- [ ] **Step 7: Delete `/trades` from `slash.py` (same commit)**

In `$WT/swingbot/commands/slash.py`, delete the `# /trades` banner pair and the whole `slash_trades` function with its decorators. `TRADE_FILTER_CHOICES` stays (`trades.py` imports it). Then:

```bash
grep -n "def slash_trades\|name=\"trades\"" $WT/swingbot/commands/slash.py
python -m py_compile $WT/swingbot/commands/slash.py $WT/swingbot/commands/trades.py
```

Expected: grep prints nothing; py_compile is silent.

- [ ] **Step 8: Keep the registration test honest**

In `$WT/tests/commands/test_stats_commands.py`, inside `test_six_bridge_commands_still_registered`, under the `import swingbot.commands.info` line SP9 added, add:

```python
    import swingbot.commands.trades  # noqa: F401  -- v153 SP10: /trades moved here
```

- [ ] **Step 9: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
```

Expected: every run `0 failed`, `0 xfailed`; the 14 `trades_*`/`trade_*`/`tradecharts_*` cases pass.

- [ ] **Step 10: Check the tree**

```bash
PYTHONPATH=$WT python -c "import swingbot.commands.trades as t, swingbot.commands.slash; from swingbot.bot_core import bot; print(sorted(c.name for c in bot.tree.get_commands() if c.name.startswith('trade'))); print(sorted(c.name for c in t.trade_group.commands)); print(sorted(c.qualified_name for c in bot.walk_commands() if c.qualified_name.startswith('trade')))"
```

Expected:
`['trade', 'tradecharts', 'trades', 'trades-clear', 'trades-clear-history']`, `['delete', 'show']`, and `['trade', 'trade delete', 'tradecharts', 'trades', 'trades clear', 'trades clear history']`.

- [ ] **Step 11: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/trades.py $WT/swingbot/commands/slash.py
```

Expected: only the legacy lines, unchanged: `summary_cmd` F (52), `format_trade_row` C (16), `_build_trade_detail_embed` C (14), `performance_cmd` C (12). Nothing new. (SP11 splits `summary_cmd`.) Paste the output into the task report.

- [ ] **Step 12: Commit**

```bash
git -C $WT add swingbot/commands/trades.py swingbot/commands/slash.py tests/commands/parity_cases/trades.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP10 trades/trade/tradecharts handlers; /trades moves to trades.py, /trades-clear, /trades-clear-history, /trade, /tradecharts new"
```

