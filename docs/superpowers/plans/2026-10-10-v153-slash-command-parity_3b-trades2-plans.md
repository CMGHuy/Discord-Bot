# v153 Slash command parity. Part 3b: `slash.py` chain I, continued (`trades` II, `plans`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here.

Split out of part 3 (`..._3-info-trades-plans.md`) only for the 1500-line file cap. The "Shared conventions for this part" block at the top of part 3 applies here unchanged: `$WT`, the SP1 names, the `ParityCase.expect` meanings, the frozen embed clock, `send_error` for validation and "not found" answers, decorators of moved slash commands copied verbatim. SP11 and SP12 continue the `slash.py` chain, one at a time, after SP10.

# Phase 3: `slash.py` chain I (continued)

### Task SP11: `trades` II: performance, pnl, summary

**Model:** opus — the F52 `summary_cmd` must be split below 15 with byte-identical output (pinned by a before/after golden), plus the `/pnl` union and the `_send_chunks` removal.

**Complexity gate (audit 2026-10-10):** this task splits `summary_cmd` (52) below 15. If `scripts/dev/complexity_gate.py` exists (v149 merged), finish with `python $WT/scripts/dev/complexity_gate.py`, then `--update` and commit `scripts/dev/complexity_baseline.json` in this task's commit (verdicts `gone`/`improved` expected; `new`/`risen` never). Index Global Constraints, Complexity bullet.

**Files:**
- Modify: `swingbot/commands/trades.py` (today's lines 385-421 `performance_cmd`, 423-450 `pnl_cmd`, 469-557 `summary_cmd`; the SP10 twins section)
- Modify: `swingbot/commands/slash.py` (delete `_send_chunks`, `/pnl`, `/performance`; drop `import asyncio`)
- Modify: `tests/commands/parity_cases/trades.py` (created by SP10)

**Interfaces:**
- Consumes (SP10): the `# / slash twins (v153)` section of `trades.py`; `_FakeLog`, `_stub`, `_freeze_clock`, `OPEN_TRADE`, `WIN_TRADE`, `LOSS_TRADE`, `ALL_TRADES` in `tests/commands/parity_cases/trades.py`. Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `Reply.send_chunks`; `ParityCase`.
- Produces (ledger): `handle_performance(reply, level: int | None = None)`, `handle_pnl(reply)` (the `!pnl` table through `send_chunks`), `handle_summary(reply)`. Slash: `/performance` and `/pnl` moved (decorators verbatim), `/summary` new. `slash._send_chunks` deleted.
- Output: `!performance`, `!pnl`, `!summary` text unchanged (a `!pnl` table over 1900 chars is now split into several messages instead of failing Discord's 2000-char cap). `/pnl` now answers with the `!pnl` table and its "Fetching current prices…" line (Controller decision 1; the old slash body appended raw row dicts). `Level must be 1-5.` goes through `send_error`.

- [ ] **Step 0: Confirm SP10 landed**

```bash
git -C $WT grep -n "def handle_tradecharts\|^trade_group = " -- swingbot/commands/trades.py
git -C $WT grep -n "class _FakeLog" -- tests/commands/parity_cases/trades.py
git -C $WT grep -n "def slash_pnl\|def slash_performance\|def _send_chunks" -- swingbot/commands/slash.py
```

Expected: two hits, one hit, three hits. Otherwise stop and report `BLOCKED: SP10 missing`.

- [ ] **Step 1: Capture the `!summary` golden before touching it**

`summary_cmd` (F52) is rewritten into helpers; its embed must not change. Write this throwaway script (not committed) to `/tmp/v153_sp11_summary_golden.py`:

```python
"""Dump !summary's embed for two canned days; run before and after SP11."""
import asyncio
import datetime as dt
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from swingbot.commands import trades as trades_mod
from tests.commands.parity_cases.trades import ALL_TRADES, WIN_TRADE, _FakeLog

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)
MANUAL = {**WIN_TRADE, "id": "T0004", "ticker": "AMD", "status": "closed",
          "exit_price": None, "realized_pnl_amount": None, "close_reason": "manual"}


class _FixedDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 10, 9, 18, 0, tzinfo=dt.timezone.utc).astimezone(tz)


def dump(trades, acct):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(trades_mod, "trade_log", _FakeLog(trades))
        mp.setattr(trades_mod, "datetime", _FixedDatetime)
        mp.setattr(trades_mod.account_module, "get_daily_summary", lambda: acct)
        mp.setattr(discord.utils, "utcnow", lambda: _NOW)
        ctx = MagicMock()
        ctx.send = AsyncMock()
        asyncio.run(trades_mod.summary_cmd.callback(ctx))
        return ctx.send.call_args.kwargs["embed"].to_dict()


out = {
    "busy": dump([*ALL_TRADES, MANUAL], {"balance": 10_120.0, "pct_change_today": 0.6}),
    "quiet": dump([], {"balance": None, "pct_change_today": None}),
}
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), sort_keys=True, ensure_ascii=False, indent=1)
```

Run it on the unchanged code:

```bash
PYTHONPATH=$WT python /tmp/v153_sp11_summary_golden.py /tmp/v153_sp11_before.json && wc -c /tmp/v153_sp11_before.json
```

Expected: a non-empty JSON file. (A MagicMock ctx gets no tip, before or after.)

- [ ] **Step 2: Extend the parity cases (failing)**

Append to `$WT/tests/commands/parity_cases/trades.py`:

```python
# ── SP11: performance, pnl, summary ─────────────────────────────────────

import types  # noqa: E402

MANUAL_TRADE = {**WIN_TRADE, "id": "T0004", "ticker": "AMD", "status": "closed",
                "exit_price": None, "realized_pnl_amount": None, "close_reason": "manual"}
_METRICS = {
    "n_trades": 12, "sharpe": 0.41, "sortino": 0.66, "max_drawdown_pct": 6.2, "calmar": 1.1,
    "profit_factor": 1.35, "avg_win_pct": 3.1, "avg_loss_pct": -2.2,
    "best_trade_pct": 8.4, "worst_trade_pct": -4.0,
}


class _FixedDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return dt.datetime(2026, 10, 9, 18, 0, tzinfo=dt.timezone.utc).astimezone(tz)


def _with_metrics(monkeypatch):
    monkeypatch.setattr(trades_mod, "compute_risk_metrics", lambda closed: dict(_METRICS))


def _pnl_row(trade, price=None):
    if price is None:
        return {"trade": trade, "pnl": None}
    pct = (price - trade["entry"]) / trade["entry"] * 100
    return {"trade": trade, "pnl": types.SimpleNamespace(
        current_price=price, pct_change=pct, distance_to_sl_pct=4.4, distance_to_tp_pct=6.1)}


def _stub_pnl(rows):
    def stub(monkeypatch):
        monkeypatch.setattr(trades_mod.scan_engine, "get_all_unrealized_pnl", lambda: list(rows))
    return stub


def _stub_summary(trades, acct):
    def stub(monkeypatch):
        _stub(trades)(monkeypatch)
        monkeypatch.setattr(trades_mod, "datetime", _FixedDatetime)
        monkeypatch.setattr(trades_mod.account_module, "get_daily_summary", lambda: dict(acct))
    return stub


_PNL_ROWS = [_pnl_row(OPEN_TRADE, 184.5), _pnl_row({**OPEN_TRADE, "id": "T0009", "ticker": "AMD"})]
_MANY_PNL_ROWS = [_pnl_row({**OPEN_TRADE, "id": f"T{i:04d}"}, 181.0 + i / 10) for i in range(60)]

CASES += [
    ParityCase("performance_overall", trades_mod.handle_performance, stub=_stub()),
    ParityCase("performance_level", trades_mod.handle_performance, args=(3,), stub=_stub()),
    ParityCase("performance_with_risk_metrics", trades_mod.handle_performance,
               stub=lambda mp: (_stub()(mp), _with_metrics(mp))),
    ParityCase("performance_bad_level", trades_mod.handle_performance, args=(9,),
               stub=_stub(), expect="error"),
    ParityCase("pnl", trades_mod.handle_pnl, stub=_stub_pnl(_PNL_ROWS), expect="multi_send"),
    ParityCase("pnl_none_open", trades_mod.handle_pnl, stub=_stub_pnl([]), expect="multi_send"),
    ParityCase("pnl_chunked", trades_mod.handle_pnl, stub=_stub_pnl(_MANY_PNL_ROWS), expect="multi_send"),
    ParityCase("summary_busy_day", trades_mod.handle_summary,
               stub=_stub_summary([*ALL_TRADES, MANUAL_TRADE], {"balance": 10_120.0, "pct_change_today": 0.6})),
    ParityCase("summary_quiet_day", trades_mod.handle_summary,
               stub=_stub_summary([], {"balance": None, "pct_change_today": None})),
]
```

Then:

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.trades' has no attribute 'handle_performance'`.

- [ ] **Step 3: `!performance` onto a handler**

In `$WT/swingbot/commands/trades.py`, replace `performance_cmd` (from `@bot.command(name="performance")` through its final `await ctx.send("\n".join(lines))`) with the code below. The level check moves ahead of the trade fetch; it reads no data, so every answer is unchanged.

```python
def _level_performance_lines(level: int, all_trades: list) -> list[str]:
    stats = trade_log.get_stats(level)
    wr = f"{stats['win_rate']:.0f}%" if stats["win_rate"] is not None else "n/a"
    lines = [
        f"**Confidence Level {level}** — {stats['total']} trades logged "
        f"({stats['open']} open, {stats['closed']} closed)",
        f"Win rate: {wr} ({stats['wins']}W / {stats['losses']}L)",
    ]
    closed_at_level = [t for t in all_trades if t["confidence_level"] == level and t["status"] in ("win", "loss")]
    _append_risk_metrics_lines(lines, closed_at_level)
    return lines


def _overall_performance_lines(all_trades: list) -> list[str]:
    lines = ["**Performance by confidence level:**"]
    by_level = trade_log.get_stats_by_confidence()
    for lvl in range(1, 6):
        s = by_level[lvl]
        wr = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "n/a"
        lines.append(f"Lv{lvl}: {wr} win rate — {s['wins']}W/{s['losses']}L closed, {s['open']} open ({s['total']} total)")
    overall = trade_log.get_stats(ledger="main")
    wr_overall = f"{overall['win_rate']:.0f}%" if overall["win_rate"] is not None else "n/a"
    lines.append(f"\n**Overall:** {wr_overall} win rate — {overall['wins']}W/{overall['losses']}L closed, {overall['open']} open")

    closed_overall = [t for t in all_trades if t["status"] in ("win", "loss")]
    _append_risk_metrics_lines(lines, closed_overall)
    weak = trade_log.weak_summary()
    lines.append(f"\n**WEAK ledger (separate):** {weak['wins']}W/{weak['losses']}L, "
                 f"N {weak['n']}, P&L {weak['total_pnl']:+.2f}")
    return lines


async def handle_performance(reply, level: int | None = None) -> None:
    if level is not None and level not in range(1, 6):
        await reply.send_error("Level must be 1-5.")
        return
    await reply.defer()
    all_trades = trade_log.get_trades(status="all", limit=None, ledger="main")
    if level is None:
        lines = _overall_performance_lines(all_trades)
    else:
        lines = _level_performance_lines(level, all_trades)
    await reply.send("\n".join(lines))


@bot.command(name="performance")
async def performance_cmd(ctx, level: int = None):
    reply = CtxReply(ctx)
    await handle_performance(reply, level)
    await send_prefix_tip(ctx, reply)
```

- [ ] **Step 4: `!pnl` onto a handler**

Replace `pnl_cmd` (from `@bot.command(name="pnl")` through its final `await ctx.send("\n".join(lines))`) with:

```python
def _pnl_lines(rows: list) -> list[str]:
    lines = [f"**Unrealized P/L — {len(rows)} open trade(s):**", "```"]
    lines.append(f"{'ID':8s} {'Ticker':6s} {'Dir':7s} {'Entry':>9s} {'Now':>9s} {'P/L%':>7s} {'ToSL%':>6s} {'ToTP%':>6s}")
    total_pct = 0.0
    counted = 0
    for row in rows:
        t, pnl = row["trade"], row["pnl"]
        if pnl is None:
            lines.append(f"{t['id']:8s} {t['ticker']:6s} {t['direction']:7s} {'price unavailable':>40s}")
            continue
        lines.append(
            f"{t['id']:8s} {t['ticker']:6s} {t['direction']:7s} {t['entry']:>9.2f} {pnl.current_price:>9.2f} "
            f"{pnl.pct_change:>+6.2f}% {pnl.distance_to_sl_pct:>5.1f}% {pnl.distance_to_tp_pct:>5.1f}%"
        )
        total_pct += pnl.pct_change
        counted += 1
    lines.append("```")
    if counted:
        lines.append(f"Average unrealized P/L across {counted} priced trade(s): {total_pct/counted:+.2f}%")
    lines.append("ToSL%/ToTP% = how far the current price is from the stop-loss / recommended TP.")
    return lines


async def handle_pnl(reply) -> None:
    await reply.send("Fetching current prices for all open trades…")
    rows = await asyncio.to_thread(scan_engine.get_all_unrealized_pnl)
    if not rows:
        await reply.send("No open trades right now.")
        return
    await reply.send_chunks("\n".join(_pnl_lines(rows)))


@bot.command(name="pnl")
async def pnl_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_pnl(reply)
    await send_prefix_tip(ctx, reply)
```

- [ ] **Step 5: `!summary` onto a handler, split below 15**

Replace `summary_cmd` (from `@bot.command(name="summary")` through its final `await ctx.send(embed=embed)`) with the code below. Every field name, value, order and inline flag is today's; the three-way emoji choices become `_sign_mark`, and the two 1000-char clips become `_clip_field`.

```python
_SPACER = "​"


def _sign_mark(value, positive: str, negative: str, zero: str) -> str:
    """`positive` above 0, `negative` below, `zero` at 0 or None."""
    v = value or 0
    if v > 0:
        return positive
    if v < 0:
        return negative
    return zero


def _clip_field(text: str) -> str:
    return text[:997] + "…" if len(text) > 1000 else text


def _add_spacer(embed: discord.Embed) -> None:
    embed.add_field(name=_SPACER, value=_SPACER, inline=True)   # keeps the 3-column grid even


def _summary_day(all_trades: list, today) -> dict:
    opened = [t for t in all_trades if _berlin_date(t.get("opened_at")) == today]
    closed = [
        t for t in all_trades
        if t["status"] in ("win", "loss", "closed") and _berlin_date(t.get("closed_at")) == today
    ]
    return {
        "opened": opened,
        "closed": closed,
        "wins": [t for t in closed if t["status"] == "win"],
        "losses": [t for t in closed if t["status"] == "loss"],
        "manual": [t for t in closed if t["status"] == "closed"],
    }


def _summary_money(closed: list) -> tuple:
    """(net realized amount, average realized P&L %), each None when nothing counts."""
    amounts = [t["realized_pnl_amount"] for t in closed if t.get("realized_pnl_amount") is not None]
    net_amount = sum(amounts) if amounts else None
    pnl_pcts = [p for t in closed if (p := closed_pnl_pct(t)) is not None]
    avg_pnl_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else None
    return net_amount, avg_pnl_pct


def _add_count_fields(embed: discord.Embed, day: dict, open_count: int) -> None:
    embed.add_field(name="🆕 Opened today", value=str(len(day["opened"])), inline=True)
    embed.add_field(name="🏁 Closed today", value=str(len(day["closed"])), inline=True)
    embed.add_field(name="📂 Still open", value=str(open_count), inline=True)

    embed.add_field(name="Wins", value=f"✅ {len(day['wins'])}", inline=True)
    embed.add_field(name="Losses", value=f"❌ {len(day['losses'])}", inline=True)
    if day["manual"]:
        embed.add_field(name="Manually closed", value=f"🔒 {len(day['manual'])}", inline=True)
    else:
        _add_spacer(embed)


def _add_money_fields(embed: discord.Embed, avg_pnl_pct, net_amount) -> None:
    pnl_emoji = _sign_mark(avg_pnl_pct, "🟢", "🔴", "⚪")
    net_emoji = _sign_mark(net_amount, "🟢", "🔴", "⚪")
    embed.add_field(name="📊 Avg realized P&L", value=f"{pnl_emoji} {ui.fmt_pct(avg_pnl_pct)}" if avg_pnl_pct is not None else "n/a", inline=True)
    embed.add_field(name="💰 Net gain/loss", value=f"{net_emoji} {net_amount:+.2f}" if net_amount is not None else "n/a", inline=True)
    _add_spacer(embed)


def _add_balance_fields(embed: discord.Embed, acct: dict) -> None:
    embed.add_field(name="🏦 Account balance", value=ui.fmt_price(acct["balance"]) if acct["balance"] is not None else "n/a", inline=True)
    bal_change = acct.get("pct_change_today")
    bal_emoji = _sign_mark(bal_change, "📈", "📉", "➖")
    embed.add_field(
        name="Balance change today",
        value=f"{bal_emoji} {ui.fmt_pct(bal_change)}" if bal_change is not None else "no change yet today",
        inline=True,
    )
    _add_spacer(embed)


def _closed_trade_line(t: dict) -> str:
    icon = kinds.outcome_mark(_STATUS_OUTCOME.get(t["status"], "manual"))
    pct = closed_pnl_pct(t)
    amt = t.get("realized_pnl_amount")
    pct_str = ui.fmt_pct(pct) if pct is not None else "n/a"
    amt_str = f"{amt:+.2f}" if amt is not None else "n/a"
    return f"{icon} `{t['id']}` {t['ticker']:6s} {pct_str:>8s}  ({amt_str})"


def _opened_trade_line(t: dict) -> str:
    return (
        f"{'🟩' if t['direction'] == 'bullish' else '🟥'} `{t['id']}` {t['ticker']:6s} "
        f"{ui.direction_glyph(t['direction'])} {'LONG' if t['direction'] == 'bullish' else 'SHORT'} "
        f"{ui.confidence_label(t.get('confidence_level'), None)}"
    )


def _add_trade_lists(embed: discord.Embed, day: dict) -> None:
    if day["closed"]:
        ordered = sorted(day["closed"], key=lambda t: t.get("closed_at") or "")
        text = _clip_field("\n".join(_closed_trade_line(t) for t in ordered))
        embed.add_field(name="Closed trades today", value=f"```{text}```", inline=False)
    if day["opened"]:
        text = _clip_field("\n".join(_opened_trade_line(t) for t in day["opened"]))
        embed.add_field(name="Opened trades today", value=f"```{text}```", inline=False)
    if not day["opened"] and not day["closed"]:
        embed.add_field(name=_SPACER, value="No trades opened or closed yet today.", inline=False)


def _summary_embed(today, all_trades: list, open_count: int, acct: dict) -> discord.Embed:
    day = _summary_day(all_trades, today)
    net_amount, avg_pnl_pct = _summary_money(day["closed"])
    embed = discord.Embed(title=f"📋 Today's Summary — {today.isoformat()} (Berlin)")
    _add_count_fields(embed, day, open_count)
    _add_money_fields(embed, avg_pnl_pct, net_amount)
    _add_balance_fields(embed, acct)
    _add_trade_lists(embed, day)
    ui.apply_chrome(embed, accent=ui.accent_for_outcome(_sign_mark(net_amount, "win", "loss", "scratch")))
    return embed


async def handle_summary(reply) -> None:
    """
    Everything that happened TODAY (Europe/Berlin calendar day) in one
    place: trades opened, trades closed (win/loss, %, and $/€), and the
    account balance's own movement today -- a quick end-of-day (or
    check-in-anytime) status read without digging through !trades or the
    admin Performance page.
    """
    today = datetime.now(_BERLIN_TZ).date()
    all_trades = trade_log.get_trades(status="all", limit=None, ledger="main")
    acct = account_module.get_daily_summary()
    open_count = trade_log.get_stats()["open"]
    await reply.send(embed=_summary_embed(today, all_trades, open_count, acct))


@bot.command(name="summary")
async def summary_cmd(ctx):
    """Everything that happened today (Europe/Berlin calendar day) in one place."""
    reply = CtxReply(ctx)
    await handle_summary(reply)
    await send_prefix_tip(ctx, reply)
```

- [ ] **Step 6: Compare the `!summary` golden**

```bash
PYTHONPATH=$WT python /tmp/v153_sp11_summary_golden.py /tmp/v153_sp11_after.json && diff /tmp/v153_sp11_before.json /tmp/v153_sp11_after.json && echo IDENTICAL
```

Expected: `IDENTICAL`. Any diff means the split changed output: fix the helper, never the golden. Paste the line into the task report, then delete both JSON files and the script.

- [ ] **Step 7: The twins**

Append to the end of the `# / slash twins (v153)` section of `$WT/swingbot/commands/trades.py` (after `slash_tradecharts`). `/performance` and `/pnl` decorators are copied verbatim from `slash.py`:

```python


@bot.tree.command(name="performance", description="Win rate + risk-adjusted stats for closed trades")
@app_commands.describe(level="Filter to a specific confidence level (1-5), or omit for overall")
async def slash_performance(
    interaction: discord.Interaction,
    level: int = None,
):
    await handle_performance(InteractionReply(interaction), level)


@bot.tree.command(name="pnl", description="Current unrealized P&L for every open trade")
async def slash_pnl(interaction: discord.Interaction):
    await handle_pnl(InteractionReply(interaction))


@bot.tree.command(name="summary", description="Today's trades opened and closed, P&L and balance change (Berlin day)")
async def slash_summary(interaction: discord.Interaction):
    await handle_summary(InteractionReply(interaction))
```

- [ ] **Step 8: Delete `_send_chunks`, `/pnl` and `/performance` from `slash.py` (same commit)**

In `$WT/swingbot/commands/slash.py`, delete whole, with their `# ────` banner pairs:

| Banner | Code |
|---|---|
| `# Helper — send long text in chunks` | `_send_chunks` (dead once `/pnl` moves; `Reply.send_chunks` replaces it) |
| `# /pnl` | `slash_pnl` |
| `# /performance` | `slash_performance` |

`import asyncio` now has no user left in `slash.py`; delete it. Then:

```bash
grep -n "asyncio\|_send_chunks\|def slash_pnl\|def slash_performance" $WT/swingbot/commands/slash.py
git -C $WT grep -n "_send_chunks" -- swingbot tests scripts
python -m py_compile $WT/swingbot/commands/slash.py $WT/swingbot/commands/trades.py
```

Expected: both greps print nothing; py_compile is silent.

- [ ] **Step 9: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_command_error_logging.py
```

Expected: every run `0 failed`, `0 xfailed`; the nine new cases (`performance_*`, `pnl*`, `summary_*`) pass, and `pnl_chunked` shows at least three sends on both surfaces. `test_six_bridge_commands_still_registered` still finds `/performance` (SP10 made it import `trades`).

- [ ] **Step 10: Check the tree**

```bash
PYTHONPATH=$WT python -c "import swingbot.commands.trades, swingbot.commands.slash; from swingbot.bot_core import bot; names = [c.name for c in bot.tree.get_commands()]; print([n for n in ('performance', 'pnl', 'summary') if names.count(n) != 1])"
```

Expected: `[]`.

- [ ] **Step 11: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/trades.py $WT/swingbot/commands/slash.py
```

Expected: only `format_trade_row` C (16) and `_build_trade_detail_embed` C (14), both legacy and untouched. `summary_cmd` F (52) and `performance_cmd` C (12) are gone; no new function reaches C. Paste the output into the task report.

- [ ] **Step 12: Commit**

```bash
git -C $WT add swingbot/commands/trades.py swingbot/commands/slash.py tests/commands/parity_cases/trades.py
git -C $WT commit -m "feat(v153): SP11 performance/pnl/summary handlers; /performance /pnl move to trades.py, /summary new, summary split below 15"
```

### Task SP12: `plans`: `!liveplans`

**Model:** sonnet — one body move and one moved slash command; the only subtlety is that the slash options map onto the parser's output, which the steps spell out.

**Files:**
- Modify: `swingbot/commands/plans.py` (imports; `liveplans_cmd`, today's lines 163-184; a twin appended)
- Modify: `swingbot/commands/slash.py` (delete the `/liveplans` block)
- Create: `tests/commands/parity_cases/plans.py`
- Modify: `tests/commands/test_plans_board.py` (`:177-179`, content is now positional)
- Modify: `tests/commands/test_stats_commands.py` (`test_new_slash_commands_registered_on_tree` imports `plans`)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`; `ParityCase`. Consumes `slash.STATUS_CHOICES`, `slash.LEVEL_CHOICES` (stay in `slash.py`).
- Produces (ledger): `handle_liveplans(reply, status: str = "All", level: str = "All", badge: str = "All", ticker: str | None = None)`; `/liveplans` moved with its decorators verbatim (options `status`, `level` only, as today).
- The slash options map exactly as the old bridge did. The old twin passed `status.value.lower()` and `level:<value>` through `_parse_board_args`, which upper-cases a status (`"pending"` → `"PENDING"`) and keeps a level digit (`"level:3"` → `"3"`), and skipped `"All"`. The `Choice` values are already `"PENDING"`/`"ACTIVE"`/`"PARTIAL"`/`"All"` and `"1"`…`"5"`/`"All"`, so the twin passes `status.value` and `level.value` unchanged.
- Output: `!liveplans` unchanged apart from the tip line. `PlanBoardView` keys on `reply.author.id` (was `ctx.author.id`). `CtxReply` passes the board text positionally (`ctx.send(content, embed=…, view=…)`; was `content=` keyword), which is why `test_plans_board.py:178-179` changes.

- [ ] **Step 0: Confirm SP11 landed**

```bash
git -C $WT grep -n "def handle_summary" -- swingbot/commands/trades.py
git -C $WT grep -n "def slash_liveplans" -- swingbot/commands/slash.py
```

Expected: one hit each. Otherwise stop and report `BLOCKED: SP11 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/plans.py`:

```python
"""Reply-parity cases for swingbot/commands/plans.py (v153 SP12).

PlanStore is replaced by an in-memory store of v2-shaped stand-ins (the
same shape tests/commands/test_plans_board.py uses); starred ids are empty;
the embed clock is frozen because render_board applies chrome.
"""
import datetime as dt
import types

import discord

from swingbot.commands import plans as plans_mod
from tests.commands.reply_harness import ParityCase

_NOW = dt.datetime(2026, 10, 9, 14, 30, tzinfo=dt.timezone.utc)


def _plan(ticker, status, badge="VALIDATED", confidence_level=5, quality_score=80):
    return types.SimpleNamespace(
        plan_id=f"{ticker}-{status}", ticker=ticker, status=status, badge=badge,
        confidence_level=confidence_level, quality_score=quality_score, direction="bullish",
        entry_type="market", trigger_price=100.0, stop_loss=95.0, tp1=110.0, tp2=None,
        entry_price=None, legs_realized=[], working_stop=None, regime_aligned=True,
        created_at="2026-10-09",
    )


_PLANS = [
    _plan("NVDA", "ACTIVE", confidence_level=5),
    _plan("AAPL", "ACTIVE", badge="WEAK", confidence_level=3, quality_score=60),
    _plan("MSFT", "PENDING", confidence_level=4, quality_score=70),
]


class _FakeStore:
    def __init__(self, plans):
        self._plans = list(plans)

    def open_plans(self):
        return list(self._plans)


def _stub(plans=_PLANS):
    def stub(monkeypatch):
        monkeypatch.setattr(plans_mod, "PlanStore", lambda: _FakeStore(plans))
        monkeypatch.setattr(plans_mod, "starred_ids", set)
        monkeypatch.setattr(discord.utils, "utcnow", lambda: _NOW)
    return stub


CASES = [
    ParityCase("liveplans_all", plans_mod.handle_liveplans, stub=_stub()),
    ParityCase("liveplans_active_level3", plans_mod.handle_liveplans, args=("ACTIVE", "3"), stub=_stub()),
    ParityCase("liveplans_weak_badge", plans_mod.handle_liveplans, kwargs={"badge": "WEAK"}, stub=_stub()),
    ParityCase("liveplans_ticker", plans_mod.handle_liveplans, kwargs={"ticker": "NVDA"}, stub=_stub()),
    ParityCase("liveplans_empty_store", plans_mod.handle_liveplans, stub=_stub([])),
]
```

- [ ] **Step 2: Run it to see it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.plans' has no attribute 'handle_liveplans'`.

- [ ] **Step 3: `!liveplans` onto a handler, with the twin**

In `$WT/swingbot/commands/plans.py`, below `import discord` add `from discord import app_commands`, and below `from swingbot.bot_core import bot` add:

```python
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.commands.slash import LEVEL_CHOICES, STATUS_CHOICES
```

Then replace `liveplans_cmd` (from `@bot.command(name="liveplans")` to the end of the file) with:

```python
async def handle_liveplans(reply, status: str = "All", level: str = "All", badge: str = "All",
                           ticker: str | None = None) -> None:
    """The live PENDING/ACTIVE/PARTIAL board. The ticker filter is fixed at
    invocation: the view's render_fn closes over `ticker`, so changing the
    status/level/badge dropdowns never drops it (Task B16)."""
    await reply.defer()
    store = PlanStore()
    plans = store.open_plans()
    content, embed = render_board(
        plans, status=status, level=level, badge=badge, ticker=ticker, page=0,
    )
    view = PlanBoardView(
        render_fn=lambda status, level, badge: render_board(
            plans, status=status, level=level, badge=badge, ticker=ticker, page=0,
        ),
        author_id=reply.author.id,
        items=plans,
    )
    view.message = await reply.send(content, embed=embed, view=view)


@bot.command(name="liveplans")
async def liveplans_cmd(ctx, *args: str):
    parsed = _parse_board_args(args)
    reply = CtxReply(ctx)
    await handle_liveplans(
        reply,
        status=parsed.get("status", "All"),
        level=parsed.get("level", "All"),
        badge=parsed.get("badge", "All"),
        ticker=parsed.get("ticker"),
    )
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /liveplans (moved from slash.py in v153, decorators verbatim). The
# Choice values are what _parse_board_args produced from the old bridge's
# args, so they go to the handler unchanged.
# ──────────────────────────────────────────────

@bot.tree.command(name="liveplans", description="Live v2 plan lifecycle board (PENDING/ACTIVE/PARTIAL)")
@app_commands.describe(status="Filter by lifecycle status", level="Filter by confidence level")
@app_commands.choices(status=STATUS_CHOICES, level=LEVEL_CHOICES)
async def slash_liveplans(
    interaction: discord.Interaction,
    status: app_commands.Choice[str] = None,
    level: app_commands.Choice[str] = None,
):
    await handle_liveplans(
        InteractionReply(interaction),
        status=status.value if status else "All",
        level=level.value if level else "All",
    )
```

- [ ] **Step 4: Delete `/liveplans` from `slash.py` (same commit)**

In `$WT/swingbot/commands/slash.py`, delete the `# /liveplans` banner pair and the whole `slash_liveplans` function with its decorators. `STATUS_CHOICES` and `LEVEL_CHOICES` stay. Then:

```bash
grep -n "def slash_liveplans\|liveplans_cmd" $WT/swingbot/commands/slash.py
python -m py_compile $WT/swingbot/commands/slash.py $WT/swingbot/commands/plans.py
```

Expected: grep prints nothing; py_compile is silent.

- [ ] **Step 5: Update the two existing tests**

In `$WT/tests/commands/test_plans_board.py`, inside `test_liveplans_cmd_ticker_filter_survives_view_filter_change`, replace

```python
    ctx.send.assert_awaited_once()
    _, kwargs = ctx.send.call_args
    assert "NVDA" in kwargs["content"] and "AAPL" not in kwargs["content"]
```

with

```python
    # v153: CtxReply passes the board text positionally; a MagicMock ctx has
    # no str qualified_name, so no tip follows and this is still the only send.
    ctx.send.assert_awaited_once()
    args, kwargs = ctx.send.call_args
    assert "NVDA" in args[0] and "AAPL" not in args[0]
```

The rest of the test (`view = kwargs["view"]`, the `render_fn` re-render) stays: it now proves the closure over `ticker` inside `handle_liveplans`.

In `$WT/tests/commands/test_stats_commands.py`, inside `test_new_slash_commands_registered_on_tree`, under `import swingbot.commands.slash  # noqa: F401 -- import side effect registers the commands`, add:

```python
    import swingbot.commands.plans  # noqa: F401  -- v153 SP12: /liveplans moved here
```

- [ ] **Step 6: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_plans_board.py
python $WT/scripts/dev/testrun.py file tests/commands/test_stats_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python $WT/scripts/dev/testrun.py file tests/commands/test_views.py
```

Expected: every run `0 failed`, `0 xfailed`; the five `liveplans_*` cases pass; `test_no_direct_chart_render_calls_outside_to_thread` still passes over `plans.py`.

- [ ] **Step 7: Check the tree and the option payload**

```bash
PYTHONPATH=$WT python -c "import swingbot.commands.plans, swingbot.commands.slash; from swingbot.bot_core import bot; [cmd] = [c for c in bot.tree.get_commands() if c.name == 'liveplans']; print(cmd.description); print([(o['name'], [c['value'] for c in o['choices']]) for o in cmd.to_dict(bot.tree)['options']])"
```

Expected:
`Live v2 plan lifecycle board (PENDING/ACTIVE/PARTIAL)` and
`[('status', ['All', 'PENDING', 'ACTIVE', 'PARTIAL']), ('level', ['All', '1', '2', '3', '4', '5'])]` — the same sync payload as before the move.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/plans.py $WT/swingbot/commands/slash.py
```

Expected: only `render_board` D (22), legacy and untouched. Paste the output into the task report.

- [ ] **Step 9: Commit**

```bash
git -C $WT add swingbot/commands/plans.py swingbot/commands/slash.py tests/commands/parity_cases/plans.py tests/commands/test_plans_board.py tests/commands/test_stats_commands.py
git -C $WT commit -m "feat(v153): SP12 liveplans handler; /liveplans moves to plans.py"
```

