# v153 Slash command parity. Part 2: Group 1 modules (`account`, `data`, `growth`, `history`)

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Index:** `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md`. Global Constraints, Parallelisation and the task ledger live there and are binding here. Read `## Global Constraints` before any task.

These four tasks are **Group 1**. SP5–SP7 are in this file. SP8 (`history`) is in `2026-10-10-v153-slash-command-parity_2b-history.md`, because the four tasks together exceed the 1500-line file cap. None of them owns an existing slash command, none touches `swingbot/commands/slash.py`, and their files are disjoint. They run in parallel with each other and with the `slash.py` chain (SP9 onwards), at most 2 implementers at once. SP7 waits for SP2 (it rewrites `growth.py` after SP2's move).

**Shared conventions for this part** (they restate the index; the index wins on any conflict):

- `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity`. Never `cd`; use `git -C $WT` and absolute paths.
- Consumed from SP1 (`swingbot/commands/reply.py`): `CtxReply`, `InteractionReply`, `send_prefix_tip`. Consumed from SP1 (`tests/commands/reply_harness.py`): `ParityCase`, `FakeContext`, `FakeInteraction`, `run_both`, `comparable`. SP1's `tests/commands/test_reply_parity.py` parametrises one test over `all_cases()`, which imports every module in `tests/commands/parity_cases/` and concatenates their `CASES`. Adding a module there is how a task adds its handlers to the harness. Before Step 1 of any task here, confirm these names exist: `git -C $WT grep -n "def run_both\|class ParityCase\|def all_cases\|class FakeInteraction" -- tests/commands/reply_harness.py` and `git -C $WT grep -n "class CtxReply\|class InteractionReply\|def send_prefix_tip" -- swingbot/commands/reply.py`. If either grep is empty, SP1 has not landed. Stop and report `BLOCKED: SP1 missing`.
- `ParityCase.expect` meanings, as SP1's `test_handler_parity` enforces them (the `_EXPECT` table in `tests/commands/test_reply_parity.py`). In every case both surfaces produce the same `comparable(...)` events.
  - `"send"`: at least one `"send"` and no `"edit"`; neither reply is `failed`.
  - `"edit"`: at least one `"send"` and at least one `"edit"`; neither reply is `failed`.
  - `"multi_send"`: at least two `"send"` events and no `"edit"`; neither reply is `failed`.
  - `"error"`: at least one `"send"`, and `failed` is `True` on both replies.
  - A case's `stub` is applied once, and the handler then runs twice (Context first) under it, so stubs must be idempotent.
- A validation failure answers through `reply.send_error(...)`. On `CtxReply` that is the same channel message as today. It also sets `reply.failed`, so the prefix command sends no tip after an error.
- Slow handlers call `await reply.defer()` **after** their validation and **before** the slow work. On `CtxReply` it is a no-op. On the slash surface it keeps Discord's 3-second acknowledgement.
- Every new slash command is new, so its name, description and options are free. Keep descriptions ≤ 100 characters and option names lower-case. SP18's parity test checks both.
- Narrow test runs only: `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.

# Phase 2: Group 1 modules

### Task SP5: `account`: handlers and the `/account` group

**Model:** sonnet — nine mechanical body moves plus one `app_commands.Group`; the contract is fixed by the ledger and no logic changes.

**Files:**
- Modify: `swingbot/commands/account.py` (whole file, 129 lines today)
- Create: `tests/commands/parity_cases/account.py`

**Interfaces:**
- Consumes (SP1): `swingbot.commands.reply.CtxReply`, `InteractionReply`, `send_prefix_tip`; `tests.commands.reply_harness.ParityCase`.
- Produces (ledger): `handle_account_show(reply)`, `handle_account_balance(reply, amount: float)`, `handle_account_risk(reply, pct: float)`, `handle_account_maxpositions(reply, n: int)`, `handle_account_sizing(reply, mode: str)`, `handle_account_positionpct(reply, pct: float)`, `handle_account_maxpositionpct(reply, pct: float)`, `handle_account_maxposition(reply, amount: float)`, `handle_account_maxrisk(reply, amount: float)`. Also `account_group = app_commands.Group(name="account", ...)`, with subcommands `show balance risk maxpositions sizing positionpct maxpositionpct maxposition maxrisk`, added to `bot.tree`. SP18 reads these as the `account <x>` slash paths of `SLASH_TWIN`.
- Output: no `!account` text changes. The only change is the tip line after each successful answer. `!account sizing bogus` sends the same `ValueError` text as today, now through `send_error`, so no tip follows it.

- [ ] **Step 0: Confirm SP1 landed**

```bash
git -C $WT grep -n "class CtxReply\|class InteractionReply\|def send_prefix_tip" -- swingbot/commands/reply.py
git -C $WT grep -n "class ParityCase\|def run_both\|def all_cases" -- tests/commands/reply_harness.py
```

Expected: three hits in each. Otherwise stop and report `BLOCKED: SP1 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/account.py`:

```python
"""Reply-parity cases for swingbot/commands/account.py (v153 SP5).

Every handler runs once through CtxReply and once through InteractionReply
with the account store stubbed; SP1's test_reply_parity compares the two
event streams. Stubs return a fixed config so no account file is touched.
"""
from swingbot.commands import account as account_mod
from tests.commands.reply_harness import ParityCase

_CFG = {
    "balance": 10_500.0,
    "base_balance": 10_000.0,
    "risk_pct": 1.0,
    "position_pct": 10.0,
    "max_position_pct": 10.0,
    "max_position_value_absolute": 1000,
    "max_risk_amount_absolute": 100,
    "max_open_positions": 5,
    "sizing_mode": "risk_pct",
}


def _stub(name: str, **overrides):
    """Patch account_mod.<name> to return the fixed config plus overrides."""
    cfg = {**_CFG, **overrides}

    def stub(monkeypatch):
        monkeypatch.setattr(account_mod, name, lambda *_a, **_k: dict(cfg))
    return stub


def _stub_bad_sizing(monkeypatch):
    def boom(mode):
        raise ValueError(f"Unknown sizing mode '{mode}'. Use risk or account.")
    monkeypatch.setattr(account_mod, "set_sizing_mode", boom)


CASES = [
    ParityCase("account_show_risk_pct", account_mod.handle_account_show,
               stub=_stub("load_account_config")),
    ParityCase("account_show_account_pct", account_mod.handle_account_show,
               stub=_stub("load_account_config", sizing_mode="account_pct")),
    ParityCase("account_show_kelly", account_mod.handle_account_show,
               stub=_stub("load_account_config", sizing_mode="kelly")),
    ParityCase("account_balance", account_mod.handle_account_balance,
               args=(10_000.0,), stub=_stub("set_balance")),
    ParityCase("account_risk", account_mod.handle_account_risk,
               args=(1.5,), stub=_stub("set_risk_pct", risk_pct=1.5)),
    ParityCase("account_maxpositions", account_mod.handle_account_maxpositions,
               args=(7,), stub=_stub("set_max_open_positions", max_open_positions=7)),
    ParityCase("account_sizing_account", account_mod.handle_account_sizing,
               args=("account",), stub=_stub("set_sizing_mode", sizing_mode="account_pct")),
    ParityCase("account_sizing_vol_target", account_mod.handle_account_sizing,
               args=("vol_target",), stub=_stub("set_sizing_mode", sizing_mode="vol_target")),
    ParityCase("account_sizing_risk", account_mod.handle_account_sizing,
               args=("risk",), stub=_stub("set_sizing_mode")),
    ParityCase("account_sizing_invalid", account_mod.handle_account_sizing,
               args=("bogus",), stub=_stub_bad_sizing, expect="error"),
    ParityCase("account_positionpct", account_mod.handle_account_positionpct,
               args=(12.5,), stub=_stub("set_position_pct", position_pct=12.5)),
    ParityCase("account_maxpositionpct", account_mod.handle_account_maxpositionpct,
               args=(20.0,), stub=_stub("set_max_position_pct", max_position_pct=20.0)),
    ParityCase("account_maxposition", account_mod.handle_account_maxposition,
               args=(2500.0,), stub=_stub("set_max_position_value_absolute",
                                          max_position_value_absolute=2500.0)),
    ParityCase("account_maxrisk", account_mod.handle_account_maxrisk,
               args=(150.0,), stub=_stub("set_max_risk_amount_absolute",
                                         max_risk_amount_absolute=150.0)),
]
```

- [ ] **Step 2: Run it to see it fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: a collection error, `AttributeError: module 'swingbot.commands.account' has no attribute 'handle_account_show'`.

- [ ] **Step 3: Rewrite `account.py` onto handlers**

Replace the whole of `$WT/swingbot/commands/account.py` with the code below. Every `ctx.send(...)` text is copied verbatim from today's file. The two `if/elif` text choices become the helpers `_sizing_line` and `_sizing_set_text`, so no function grows.

```python
"""!account and its subcommands, and their /account slash twins (v153).

Each body lives in one handle_account_<x>(reply, ...) handler. The prefix
command and the /account <x> subcommand both call it through a Reply
(swingbot/commands/reply.py), so the two surfaces cannot drift.
"""
import discord
from discord import app_commands

from swingbot.core.planning.account import (
    load_account_config, set_balance, set_max_open_positions, set_max_position_pct,
    set_max_position_value_absolute, set_max_risk_amount_absolute, set_position_pct,
    set_risk_pct, set_sizing_mode,
)
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip


_EDGE_SIZING_LABELS = {
    "kelly": "Quarter-Kelly", "vol_target": "Vol-target", "min_of_all": "Min-of-all",
}

# Values are what set_sizing_mode() accepts (core/planning/account.py).
SIZING_CHOICES = [
    app_commands.Choice(name="Risk % (size from stop distance)", value="risk"),
    app_commands.Choice(name="Account % (fixed allocation)", value="account"),
    app_commands.Choice(name="Quarter-Kelly", value="kelly"),
    app_commands.Choice(name="Vol-target", value="vol_target"),
    app_commands.Choice(name="Min-of-all", value="min_of_all"),
]


# ──────────────────────────────────────────────
# Text builders
# ──────────────────────────────────────────────

def _sizing_line(cfg: dict) -> str:
    mode = cfg.get("sizing_mode", "risk_pct")
    if mode == "account_pct":
        return f"Position sizing: **Account %** -- {cfg.get('position_pct', 0.1)}% of balance per trade"
    if mode in _EDGE_SIZING_LABELS:
        return (f"Position sizing: **{_EDGE_SIZING_LABELS[mode]}** -- effective risk computed "
                f"per-trade from strategy/volatility stats (config risk % {cfg['risk_pct']} is the ceiling)")
    return f"Position sizing: **Risk %** -- {cfg['risk_pct']}% of balance risked per trade"


def _sizing_set_text(cfg: dict) -> str:
    if cfg["sizing_mode"] == "account_pct":
        return (
            f"Position sizing set to **Account %** -- every trade now opens at "
            f"{cfg.get('position_pct', 0.1)}% of the account balance ({cfg['balance']}), "
            f"regardless of stop distance. Change the % with `!account positionpct <pct>`."
        )
    if cfg["sizing_mode"] in _EDGE_SIZING_LABELS:
        return (
            f"Position sizing set to **{_EDGE_SIZING_LABELS[cfg['sizing_mode']]}** -- effective risk is "
            f"computed per-trade from strategy/volatility stats, never above your risk % "
            f"({cfg['risk_pct']}%, the ceiling) or the frozen 2% hard cap."
        )
    return (
        f"Position sizing set to **Risk %** -- every trade is now sized so a full "
        f"stop-out costs {cfg['risk_pct']}% of the account balance."
    )


# ──────────────────────────────────────────────
# Handlers (one body per command, shared by ! and /)
# ──────────────────────────────────────────────

async def handle_account_show(reply) -> None:
    cfg = load_account_config()
    await reply.send(
        f"**Account settings:**\nBalance: {cfg['balance']} "
        f"(base {cfg.get('base_balance', cfg['balance'])} + all-time realized P&L)\n{_sizing_line(cfg)}\n"
        f"Max position size: {cfg.get('max_position_pct', 0.1)}% of balance, capped at "
        f"{cfg.get('max_position_value_absolute', 1000)} absolute\n"
        f"Max risk per trade: {cfg.get('max_risk_amount_absolute', 100)} absolute (hard cap, regardless of %)\n"
        f"Max concurrent open positions: {cfg.get('max_open_positions', 5)}\n\n"
        f"Change with `!account balance <amount>`, `!account sizing risk|account`, "
        f"`!account positionpct <pct>`, `!account risk <pct>`, `!account maxpositions <n>`, "
        f"`!account maxpositionpct <pct>`, `!account maxposition <amount>`, `!account maxrisk <amount>`"
    )


async def handle_account_balance(reply, amount: float) -> None:
    cfg = set_balance(amount)
    await reply.send(
        f"Base balance set to {amount} -- effective balance is now {cfg['balance']} "
        f"(base + all-time realized P&L). This will keep accounting for realized "
        f"gain/loss on top of this new base going forward."
    )


async def handle_account_risk(reply, pct: float) -> None:
    cfg = set_risk_pct(pct)
    await reply.send(f"Risk per trade set to {cfg['risk_pct']}%.")


async def handle_account_maxpositions(reply, n: int) -> None:
    cfg = set_max_open_positions(n)
    await reply.send(f"Max concurrent open positions set to {cfg['max_open_positions']}.")


async def handle_account_sizing(reply, mode: str) -> None:
    """`risk` (fixed-fractional, size varies with stop distance) or `account`
    (fixed allocation -- every trade opens at exactly `positionpct`% of the
    account, regardless of stop distance), or an edge sizing mode."""
    try:
        cfg = set_sizing_mode(mode)
    except ValueError as e:
        await reply.send_error(str(e))
        return
    await reply.send(_sizing_set_text(cfg))


async def handle_account_positionpct(reply, pct: float) -> None:
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    cfg = set_position_pct(pct)
    note = "" if cfg.get("sizing_mode") == "account_pct" else " (currently unused -- switch with `!account sizing account` to apply it)"
    await reply.send(f"Position size set to {cfg['position_pct']}% of account per trade{note}.")


async def handle_account_maxpositionpct(reply, pct: float) -> None:
    """Position-size cap as a % of balance -- see `!account maxposition` for the
    absolute currency cap that holds regardless of balance."""
    cfg = set_max_position_pct(pct)
    await reply.send(
        f"Max position size set to {cfg['max_position_pct']}% of balance "
        f"(still also capped at {cfg.get('max_position_value_absolute', 1000)} absolute)."
    )


async def handle_account_maxposition(reply, amount: float) -> None:
    """Hard currency cap on position value -- holds no matter what the account
    balance or % settings are. Set to 0 to disable and rely on maxpositionpct alone."""
    cfg = set_max_position_value_absolute(amount)
    await reply.send(
        f"Max position size set to {cfg['max_position_value_absolute']} absolute -- "
        f"no trade will ever open larger than this, regardless of balance or % settings."
    )


async def handle_account_maxrisk(reply, amount: float) -> None:
    """Hard currency cap on the REAL risk if a trade's stop-loss is hit -- holds no
    matter what the account balance, sizing mode, or risk % are. Set to 0 to disable."""
    cfg = set_max_risk_amount_absolute(amount)
    await reply.send(
        f"Max loss per trade set to {cfg['max_risk_amount_absolute']} absolute -- "
        f"no trade's real risk-if-stopped will ever exceed this, regardless of balance, "
        f"sizing mode, or risk %."
    )


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.group(name="account", invoke_without_command=True)
async def account_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_account_show(reply)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="balance")
async def account_balance(ctx, amount: float):
    reply = CtxReply(ctx)
    await handle_account_balance(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="risk")
async def account_risk(ctx, pct: float):
    reply = CtxReply(ctx)
    await handle_account_risk(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositions")
async def account_maxpositions(ctx, n: int):
    reply = CtxReply(ctx)
    await handle_account_maxpositions(reply, n)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="sizing")
async def account_sizing(ctx, mode: str):
    """`!account sizing risk` (fixed-fractional, size varies with stop distance) or
    `!account sizing account` (fixed allocation -- every trade opens at exactly
    `positionpct`% of the account, regardless of stop distance)."""
    reply = CtxReply(ctx)
    await handle_account_sizing(reply, mode)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="positionpct")
async def account_positionpct(ctx, pct: float):
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    reply = CtxReply(ctx)
    await handle_account_positionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositionpct")
async def account_maxpositionpct(ctx, pct: float):
    """Position-size cap as a % of balance."""
    reply = CtxReply(ctx)
    await handle_account_maxpositionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxposition")
async def account_maxposition(ctx, amount: float):
    """Hard currency cap on position value."""
    reply = CtxReply(ctx)
    await handle_account_maxposition(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxrisk")
async def account_maxrisk(ctx, amount: float):
    """Hard currency cap on the real risk if a trade's stop-loss is hit."""
    reply = CtxReply(ctx)
    await handle_account_maxrisk(reply, amount)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# /account slash group (new in v153; `!account` alone maps to /account show)
# ──────────────────────────────────────────────

account_group = app_commands.Group(
    name="account", description="Show or change the account balance, risk and position sizing",
)


@account_group.command(name="show", description="Show the account settings")
async def slash_account_show(interaction: discord.Interaction):
    await handle_account_show(InteractionReply(interaction))


@account_group.command(name="balance", description="Set the base balance (realized P&L keeps adding on top)")
@app_commands.describe(amount="New base balance")
async def slash_account_balance(interaction: discord.Interaction, amount: float):
    await handle_account_balance(InteractionReply(interaction), amount)


@account_group.command(name="risk", description="Set the % of balance risked per trade")
@app_commands.describe(pct="Risk per trade, in percent")
async def slash_account_risk(interaction: discord.Interaction, pct: float):
    await handle_account_risk(InteractionReply(interaction), pct)


@account_group.command(name="maxpositions", description="Set the max number of concurrent open positions")
@app_commands.describe(n="Max concurrent open positions")
async def slash_account_maxpositions(interaction: discord.Interaction, n: int):
    await handle_account_maxpositions(InteractionReply(interaction), n)


@account_group.command(name="sizing", description="Choose the position-sizing mode")
@app_commands.describe(mode="Sizing mode")
@app_commands.choices(mode=SIZING_CHOICES)
async def slash_account_sizing(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    await handle_account_sizing(InteractionReply(interaction), mode.value)


@account_group.command(name="positionpct", description="Set the position size as a % of account (account sizing mode)")
@app_commands.describe(pct="Position size, in percent of the account")
async def slash_account_positionpct(interaction: discord.Interaction, pct: float):
    await handle_account_positionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxpositionpct", description="Cap a position's size as a % of balance")
@app_commands.describe(pct="Position-size cap, in percent of balance")
async def slash_account_maxpositionpct(interaction: discord.Interaction, pct: float):
    await handle_account_maxpositionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxposition", description="Cap a position's value in currency (0 disables)")
@app_commands.describe(amount="Max position value, absolute")
async def slash_account_maxposition(interaction: discord.Interaction, amount: float):
    await handle_account_maxposition(InteractionReply(interaction), amount)


@account_group.command(name="maxrisk", description="Cap the real loss per trade in currency (0 disables)")
@app_commands.describe(amount="Max loss per trade, absolute")
async def slash_account_maxrisk(interaction: discord.Interaction, amount: float):
    await handle_account_maxrisk(InteractionReply(interaction), amount)


bot.tree.add_command(account_group)
```

- [ ] **Step 4: Run the harness**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
```

Expected: `0 failed`, `0 xfailed`. The 14 `account_*` cases pass.

- [ ] **Step 5: Check the group's shape**

```bash
PYTHONPATH=$WT python -c "import swingbot.commands.account as a; print(a.account_group.name, sorted(c.name for c in a.account_group.commands)); from swingbot.bot_core import bot; print([c.name for c in bot.tree.get_commands() if c.name == 'account'])"
```

Expected:
`account ['balance', 'maxposition', 'maxpositionpct', 'maxpositions', 'maxrisk', 'positionpct', 'risk', 'show', 'sizing']` and `['account']`.

- [ ] **Step 6: Neighbouring tests and complexity**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python -m radon cc -s -n C $WT/swingbot/commands/account.py
```

Expected: the first is green (`/account` is new and does not collide with the 19). radon prints nothing (every function is below C). Paste the radon output, or `(none)`, into the task report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/commands/account.py tests/commands/parity_cases/account.py
git -C $WT commit -m "feat(v153): SP5 account handlers and /account slash group"
```

### Task SP6: `data`: charts, download, cached, scrapeall

**Model:** opus — `!scrapeall` is a legacy C18 body with a background progress poller and edit-based delivery; it must be split below 15 and gain a stale-token path without changing what `!scrapeall` delivers.

**Swallowed-error ratchet (audit 2026-10-10):** this task writes `except Exception` handlers. If `tests/infra/test_swallowed_ratchet.py` exists (v148 merged): a handler moved from today's code keeps exactly the `swallowed(...)` call it carries in the current file (copy it from the file, not from this plan's pre-v148 text); a new handler that neither re-raises nor calls `swallowed()` follows the index Global Constraints bullet "Swallowed-error ratchet"; then run `python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py`. Otherwise write them as planned.

**Complexity gate (audit 2026-10-10):** this task splits `scrapeall_cmd` (18) below 15. If `scripts/dev/complexity_gate.py` exists (v149 merged), finish with `python $WT/scripts/dev/complexity_gate.py`, then `--update` and commit `scripts/dev/complexity_baseline.json` in this task's commit (verdicts `gone`/`improved` expected; `new`/`risen` never). Index Global Constraints, Complexity bullet.

**Files:**
- Modify: `swingbot/commands/data.py` (whole file, 223 lines today)
- Create: `tests/commands/parity_cases/data.py`
- Create: `tests/commands/test_scrapeall_stale.py` (task-private; no other task touches it)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply` (with `clock=`), `TOKEN_LIFETIME_S`, `send_prefix_tip`; `ParityCase`, `FakeInteraction`.
- Consumes (existing): `swingbot.core.marketdata.data_store.TIMEFRAMES` (`data_store.py:50`, 10 timeframes, each with an `"interval"` code that is an `INTERVAL_CONFIG` key); `export_data.scrape_watchlist_history(tickers, out_dir, ..., force=, on_ticker_done=)` (`export_data.py:186`); `export_ticker(ticker, out_dir) -> dict` (`export_data.py:129`); `download_and_cache(ticker, interval) -> dict` (`data_store.py:346`).
- Produces (ledger): `handle_charts(reply)`, `handle_download(reply, interval: str, ticker: str | None = None)`, `handle_cached(reply)`, `handle_scrapeall(reply, mode: str = "cached")`, and the new slash commands `/charts`, `/download`, `/cached`, `/scrapeall`.
- Output: the `!` texts are unchanged; only the tip line is added after a successful answer. The usage reply for a bad `!scrapeall` mode, the empty-watchlist reply and `!download`'s unknown-interval reply now go through `send_error`. Their text is unchanged and no tip follows them. With `CtxReply`, `reply.stale` is always `False`, so `!scrapeall` still edits its progress message into the summary exactly as today.

**Why the stale path.** A `/scrapeall` interaction token lives 15 minutes. `InteractionReply.stale` turns `True` at `TOKEN_LIFETIME_S` (14 min). Once it is stale, the progress poller stops editing, and the final summary is posted with `reply.send(...)`, which a stale `InteractionReply` routes to `interaction.channel.send`. It is never an edit of a dead webhook message. This is the spec's "loses its later progress edits, never its result".

- [ ] **Step 0: Confirm SP1 landed**

```bash
git -C $WT grep -n "class CtxReply\|class InteractionReply\|TOKEN_LIFETIME_S =\|def send_prefix_tip" -- swingbot/commands/reply.py
git -C $WT grep -n "class ParityCase\|class FakeInteraction\|calls" -- tests/commands/reply_harness.py
```

Expected: hits for all four names in `reply.py` and both classes in the harness. `FakeInteraction` records `"channel.send"` in `.calls` when a stale reply posts to the channel; Step 2's test relies on it.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/data.py`:

```python
"""Reply-parity cases for swingbot/commands/data.py (v153 SP6).

Network and disk seams are stubbed: the watchlist, export_ticker,
download_and_cache, scrape_watchlist_history, config.EXPORT_DIR and the
market-data cache directory. Each stub builds its own temp directory so the
real exports/ and market_data/ trees are never touched (handle_charts
rmtree()s config.EXPORT_DIR).
"""
import os
import tempfile

from swingbot.commands import data as data_mod
from tests.commands.reply_harness import ParityCase


def _tmp() -> str:
    return tempfile.mkdtemp(prefix="v153-data-")


def _watchlist(monkeypatch, tickers=("AAA", "BBB")):
    monkeypatch.setattr(data_mod, "load_watchlist", lambda: list(tickers))
    monkeypatch.setattr(data_mod.config, "EXPORT_DIR", _tmp())


def _stub_charts(monkeypatch):
    _watchlist(monkeypatch)
    src = _tmp()   # outside EXPORT_DIR, which handle_charts wipes
    paths = {}
    for key, name in (("csv", "x.csv"), ("recent_chart", "recent.png"), ("full_chart", "full.png")):
        paths[key] = os.path.join(src, name)
        with open(paths[key], "w") as f:
            f.write("x")
    monkeypatch.setattr(data_mod, "export_ticker",
                        lambda ticker, out_dir: {"bars": 250, **paths})


def _stub_charts_one_fails(monkeypatch):
    _stub_charts(monkeypatch)
    ok = data_mod.export_ticker

    def export(ticker, out_dir):
        if ticker == "BBB":
            raise RuntimeError("yahoo down")
        return ok(ticker, out_dir)
    monkeypatch.setattr(data_mod, "export_ticker", export)


def _stub_download(monkeypatch):
    _watchlist(monkeypatch)
    monkeypatch.setattr(data_mod, "download_and_cache", lambda t, interval: {
        "ticker": t, "rows": 1234, "start": "2020-01-02 00:00:00", "end": "2026-10-09 00:00:00"})


def _stub_download_fails(monkeypatch):
    _watchlist(monkeypatch)

    def boom(t, interval):
        raise RuntimeError("no data")
    monkeypatch.setattr(data_mod, "download_and_cache", boom)


def _stub_cache(monkeypatch):
    base = _tmp()
    os.makedirs(os.path.join(base, "daily"))
    with open(os.path.join(base, "daily", "AAA.csv"), "w") as f:
        f.write("Date,Close\n2026-01-02,1\n2026-01-03,2\n")
    monkeypatch.setattr(data_mod, "CACHE_DIR", base)


def _stub_cache_missing(monkeypatch):
    monkeypatch.setattr(data_mod, "CACHE_DIR", os.path.join(_tmp(), "absent"))


def _scrape_rows(n_ok: int):
    rows = [{"ticker": f"T{i:03d}", "bars": 5000 + i, "start": "2000-01-03",
             "end": "2026-10-09", "from_cache": i % 2 == 0} for i in range(n_ok)]
    return rows + [{"ticker": "BAD", "error": "boom"}]


def _stub_scrape(n_ok: int):
    def stub(monkeypatch):
        _watchlist(monkeypatch, tickers=[f"T{i:03d}" for i in range(n_ok)] + ["BAD"])

        def scrape(tickers, out_dir, force=False, on_ticker_done=None, **_kw):
            os.makedirs(out_dir, exist_ok=True)
            return _scrape_rows(n_ok)
        monkeypatch.setattr(data_mod.export_data, "scrape_watchlist_history", scrape)
    return stub


def _stub_empty_watchlist(monkeypatch):
    _watchlist(monkeypatch, tickers=())


CASES = [
    ParityCase("charts", data_mod.handle_charts, stub=_stub_charts, expect="multi_send"),
    ParityCase("charts_one_export_fails", data_mod.handle_charts,
               stub=_stub_charts_one_fails, expect="multi_send"),
    ParityCase("download_one_ticker", data_mod.handle_download, args=("1d", "aapl"),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_1m_watchlist", data_mod.handle_download, args=("1m",),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_hourly_window", data_mod.handle_download, args=("1h",),
               stub=_stub_download, expect="multi_send"),
    ParityCase("download_all_fail", data_mod.handle_download, args=("daily",),
               stub=_stub_download_fails, expect="multi_send"),
    ParityCase("download_unknown_interval", data_mod.handle_download, args=("7y",),
               stub=_stub_download, expect="error"),
    ParityCase("cached", data_mod.handle_cached, stub=_stub_cache),
    ParityCase("cached_nothing", data_mod.handle_cached, stub=_stub_cache_missing),
    ParityCase("scrapeall_short_summary", data_mod.handle_scrapeall,
               stub=_stub_scrape(2), expect="edit"),
    ParityCase("scrapeall_long_summary_attaches_file", data_mod.handle_scrapeall,
               args=("force",), stub=_stub_scrape(60), expect="edit"),
    ParityCase("scrapeall_bad_mode", data_mod.handle_scrapeall, args=("sometimes",),
               stub=_stub_scrape(2), expect="error"),
    ParityCase("scrapeall_empty_watchlist", data_mod.handle_scrapeall,
               stub=_stub_empty_watchlist, expect="error"),
]
```

- [ ] **Step 2: Write the stale-token test (failing)**

Create `$WT/tests/commands/test_scrapeall_stale.py`:

```python
"""v153 SP6: a /scrapeall that outlives its interaction token still delivers
its result as a fresh message, never as an edit of the dead webhook message."""
import asyncio

from swingbot.commands import data as data_mod
from swingbot.commands.reply import CtxReply, InteractionReply, TOKEN_LIFETIME_S
from tests.commands.reply_harness import FakeContext, FakeInteraction

ROWS = [{"ticker": "AAA", "bars": 10, "start": "2020-01-02", "end": "2020-02-03", "from_cache": False}]


def _stub(monkeypatch, tmp_path, on_scrape=lambda: None):
    monkeypatch.setattr(data_mod, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(data_mod.config, "EXPORT_DIR", str(tmp_path))

    def scrape(tickers, out_dir, force=False, on_ticker_done=None, **_kw):
        on_scrape()
        return list(ROWS)
    monkeypatch.setattr(data_mod.export_data, "scrape_watchlist_history", scrape)


def _summary_events(events):
    return [e for e in events if (e[1] or "").startswith("**Scrape complete**")]


def test_stale_interaction_posts_the_summary_as_a_fresh_channel_message(monkeypatch, tmp_path):
    now = [0.0]

    def outlive_the_token():
        now[0] = TOKEN_LIFETIME_S + 1.0

    _stub(monkeypatch, tmp_path, on_scrape=outlive_the_token)
    events: list = []
    interaction = FakeInteraction(events)
    reply = InteractionReply(interaction, clock=lambda: now[0])

    asyncio.run(data_mod.handle_scrapeall(reply))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] != "edit"
    assert "channel.send" in interaction.calls
    assert not reply.failed


def test_fresh_interaction_edits_the_progress_message_into_the_summary(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    events: list = []
    reply = InteractionReply(FakeInteraction(events), clock=lambda: 0.0)

    asyncio.run(data_mod.handle_scrapeall(reply))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] == "edit"


def test_prefix_scrapeall_still_edits_its_progress_message(monkeypatch, tmp_path):
    _stub(monkeypatch, tmp_path)
    events: list = []

    asyncio.run(data_mod.handle_scrapeall(CtxReply(FakeContext(events))))

    summary = _summary_events(events)
    assert len(summary) == 1
    assert summary[0][0] == "edit"
```

- [ ] **Step 3: Run both to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_scrapeall_stale.py
```

Expected: collection errors, `AttributeError: module 'swingbot.commands.data' has no attribute 'handle_charts'` (and `handle_scrapeall`).

- [ ] **Step 4: Rewrite `data.py` onto handlers**

Replace the whole of `$WT/swingbot/commands/data.py` with the code below. Every user-facing string is copied verbatim from today's file. `scrapeall_cmd` (C18) becomes `handle_scrapeall` plus four named helpers: `_scrape_intro`, `_scrape_with_progress`/`_poll_scrape_progress`, `_scrape_summary` and `_deliver_scrape_summary`.

```python
"""!charts, !download, !cached, !scrapeall and their slash twins (v153).

Each body lives in one handle_<name>(reply, ...) handler; the prefix command
and the /<name> slash command both call it through a Reply
(swingbot/commands/reply.py).
"""
import asyncio
import logging
import os
import shutil

import discord
from discord import app_commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core.marketdata import export_data
from swingbot.core.marketdata.data_store import (
    DATA_DIR as CACHE_DIR, INTERVAL_CONFIG, TIMEFRAMES, download_and_cache,
)
from swingbot.core.marketdata.export_data import export_ticker
from swingbot.core.marketdata.watchlist import load_watchlist

log = logging.getLogger(__name__)

MESSAGE_LIMIT = 1900
SCRAPE_POLL_S = 1.5
SCRAPE_USAGE = ("Usage: `!scrapeall` (skip tickers already scraped in the last ~20h) "
                "or `!scrapeall force` (re-download everything).")
SCRAPE_EMPTY = "Watchlist is empty -- add tickers with `!watchlist add TICKER` first."
SCRAPE_LONG_NOTE = "\n(Full per-ticker table attached below -- too long for one message.)"

# One choice per canonical timeframe; the value is its yfinance code, which is
# an INTERVAL_CONFIG key, so `1m` keeps !download's 1-minute warning.
INTERVAL_CHOICES = [
    app_commands.Choice(name=f"{name} ({cfg['interval']})", value=cfg["interval"])
    for name, cfg in TIMEFRAMES.items()
]
SCRAPE_MODE_CHOICES = [
    app_commands.Choice(name="cached (skip tickers scraped in the last ~20h)", value="cached"),
    app_commands.Choice(name="force (re-download everything)", value="force"),
]


# ──────────────────────────────────────────────
# charts
# ──────────────────────────────────────────────

async def _post_chart_export(reply, ticker: str) -> None:
    try:
        result = await asyncio.to_thread(export_ticker, ticker, config.EXPORT_DIR)
    except Exception as e:
        log.warning("!charts: could not export %s", ticker, exc_info=True)
        await reply.send(f"⚠️ Could not export {ticker}: {e}")
        return
    await reply.send(
        content=f"**{ticker}** — {result['bars']} trading days of history",
        files=[
            discord.File(result["csv"]),
            discord.File(result["recent_chart"]),
            discord.File(result["full_chart"]),
        ],
    )


async def handle_charts(reply) -> None:
    tickers = load_watchlist()
    await reply.defer()
    await reply.send(f"Downloading full historical daily data for {len(tickers)} ticker(s)… this can take a bit.")

    if os.path.exists(config.EXPORT_DIR):
        shutil.rmtree(config.EXPORT_DIR)
    os.makedirs(config.EXPORT_DIR, exist_ok=True)

    for ticker in tickers:
        await _post_chart_export(reply, ticker)

    await reply.send("Done — all watchlist history exported above.")


# ──────────────────────────────────────────────
# download
# ──────────────────────────────────────────────

def _download_intro(interval: str, cfg: dict, n_tickers: int) -> str:
    if interval == "1m":
        return (
            f"⚠️ Heads up: Yahoo Finance only provides **1-minute** candles for the trailing **~30 days** — "
            f"there's no source for years of 1-minute history for free. Pulling the maximum available "
            f"(~30 days) for {n_tickers} ticker(s) now and caching it to disk…"
        )
    if cfg["max_days"] is not None:
        return f"Downloading {interval} data (max ~{cfg['max_days']} days available from Yahoo) for {n_tickers} ticker(s)…"
    return f"Downloading full {interval} history for {n_tickers} ticker(s)…"


async def _download_all(reply, tickers: list, interval: str) -> list:
    results = []
    for t in tickers:
        try:
            results.append(await asyncio.to_thread(download_and_cache, t, interval))
        except Exception as e:
            log.warning("!download: %s failed", t, exc_info=True)
            await reply.send(f"⚠️ {t}: {e}")
    return results


def _download_table(results: list) -> str:
    lines = ["**Cached to disk:**", "```"]
    lines.append(f"{'Ticker':8s} {'Rows':>7s} {'From':19s} {'To':19s}")
    for r in results:
        lines.append(f"{r['ticker']:8s} {r['rows']:7d} {r['start'][:19]:19s} {r['end'][:19]:19s}")
    lines.append("```")
    return "\n".join(lines)


async def handle_download(reply, interval: str, ticker: str | None = None) -> None:
    interval = interval.lower()
    if interval not in INTERVAL_CONFIG:
        await reply.send_error(f"Unknown interval '{interval}'. Use one of: {', '.join(INTERVAL_CONFIG)}")
        return

    tickers = [ticker.upper()] if ticker else load_watchlist()
    await reply.defer()
    await reply.send(_download_intro(interval, INTERVAL_CONFIG[interval], len(tickers)))

    results = await _download_all(reply, tickers, interval)
    if not results:
        await reply.send("Nothing downloaded.")
        return
    await reply.send(_download_table(results))


# ──────────────────────────────────────────────
# cached
# ──────────────────────────────────────────────

def _cached_row(tf: str, full_dir: str) -> str | None:
    """One summary row for a timeframe folder, or None if it holds no CSV."""
    symbols = rows = size_kb = 0
    for fname in sorted(os.listdir(full_dir)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(full_dir, fname)
        symbols += 1
        size_kb += os.path.getsize(path) / 1024
        try:
            with open(path) as f:
                rows += sum(1 for _ in f) - 1
        except OSError:
            continue
    if not symbols:
        return None
    return f"{tf:10s} {symbols:8d} {rows:10d} {size_kb:7.0f}K"


async def handle_cached(reply) -> None:
    base_dir = CACHE_DIR
    if not os.path.exists(base_dir):
        await reply.send("Nothing cached yet. Use `!download INTERVAL [TICKER]` first.")
        return

    # Layout is market_data/{timeframe}/{TICKER}.csv -- summarise per
    # timeframe folder rather than listing every symbol, since a populated
    # cache is 500+ files per timeframe and would blow the 2000-char limit.
    rows = []
    for tf in sorted(os.listdir(base_dir)):
        full_dir = os.path.join(base_dir, tf)
        if os.path.isdir(full_dir) and (row := _cached_row(tf, full_dir)):
            rows.append(row)
    if not rows:
        await reply.send("Nothing cached yet. Use `!download TIMEFRAME [TICKER]` first.")
        return
    header = f"{'Timeframe':10s} {'Symbols':>8s} {'Rows':>10s} {'Size':>8s}"
    await reply.send("\n".join(["**Locally cached data:**", "```", header, *rows, "```"]))


# ──────────────────────────────────────────────
# scrapeall
# ──────────────────────────────────────────────

def _scrape_intro(n_tickers: int, force: bool) -> str:
    return (
        f"Scraping full (all-time) history for {n_tickers} ticker(s), "
        f"{'forcing a fresh download for all of them' if force else 'skipping any already scraped in the last ~20h'}… "
        f"0/{n_tickers}"
    )


async def _poll_scrape_progress(reply, progress_msg, done_counter: dict, total: int) -> None:
    """Edit the progress message every SCRAPE_POLL_S until cancelled. Stops
    once the interaction token is stale: its webhook message can no longer
    be edited (a prefix reply is never stale)."""
    last_shown = None
    while not reply.stale:
        await asyncio.sleep(SCRAPE_POLL_S)
        label = f"Scraping full history… {done_counter['n']}/{total}"
        if label == last_shown or reply.stale:
            continue
        try:
            await progress_msg.edit(content=label)
        except discord.NotFound:
            return
        last_shown = label


async def _scrape_with_progress(reply, progress_msg, tickers: list, out_dir: str, force: bool) -> list:
    done_counter = {"n": 0}

    def _on_done(ticker, ok):
        done_counter["n"] += 1

    poller = asyncio.create_task(_poll_scrape_progress(reply, progress_msg, done_counter, len(tickers)))
    try:
        return await asyncio.to_thread(
            export_data.scrape_watchlist_history, tickers, out_dir, force=force, on_ticker_done=_on_done,
        )
    finally:
        poller.cancel()


def _scrape_summary(results: list, n_tickers: int, out_dir: str) -> tuple[str, str]:
    """(summary header, fenced per-ticker table) for a finished scrape."""
    ok_results = [r for r in results if r and not r.get("error")]
    failed = [r for r in results if r and r.get("error")]
    cached_count = sum(1 for r in ok_results if r.get("from_cache"))
    fresh_count = len(ok_results) - cached_count

    header = (
        f"**Scrape complete** — {len(ok_results)}/{n_tickers} succeeded "
        f"({fresh_count} freshly downloaded, {cached_count} already cached, {len(failed)} failed).\n"
        f"Saved to `{out_dir}` on disk."
    )
    table_lines = ["```", f"{'Ticker':8s} {'Bars':>7s} {'From':12s} {'To':12s} {'Source':6s}"]
    for r in ok_results:
        table_lines.append(f"{r['ticker']:8s} {r['bars']:7d} {str(r['start']):12s} {str(r['end']):12s} {'cache' if r['from_cache'] else 'fresh':6s}")
    if failed:
        table_lines += ["", "Failed:"] + [f"{r['ticker']:8s} {r['error']}" for r in failed]
    table_lines.append("```")
    return header, "\n".join(table_lines)


def _summary_file(out_dir: str, table_text: str) -> discord.File:
    summary_path = os.path.join(out_dir, "_scrape_summary.txt")
    with open(summary_path, "w") as f:
        f.write(table_text.strip("`"))
    return discord.File(summary_path, filename="scrape_summary.txt")


async def _deliver_scrape_summary(reply, progress_msg, header: str, table_text: str, out_dir: str) -> None:
    """Turn the progress message into the summary. A stale interaction token
    cannot edit, so its summary goes out as a fresh send instead -- the result
    is never lost. A too-long table goes out as an attached text file."""
    full_message = header + "\n" + table_text
    fits = len(full_message) <= MESSAGE_LIMIT
    text = full_message if fits else header + SCRAPE_LONG_NOTE
    try:
        if reply.stale:
            await reply.send(text)
        else:
            await progress_msg.edit(content=text)
        if not fits:
            await reply.send(file=_summary_file(out_dir, table_text))
    except discord.NotFound:
        await reply.send(full_message[:MESSAGE_LIMIT])


async def handle_scrapeall(reply, mode: str = "cached") -> None:
    """
    Downloads FULL ("all time", period="max") daily history for EVERY
    ticker in the watchlist at once, concurrently -- see
    export_data.py's module docstring for the stock-market-scraper
    ideas this borrows. Skips a ticker entirely if it was already
    scraped within the last ~20h, unless `!scrapeall force` is used.

    Unlike !charts, this does NOT post every CSV/chart to the channel
    (dozens of file uploads for a full watchlist isn't practical) --
    it saves everything to exports/full_history/ on disk (persisted via
    the Docker volume) and posts a summary table, or a CSV attachment
    if the watchlist is too big for one Discord message.
    """
    mode = mode.lower()
    if mode not in ("cached", "force"):
        await reply.send_error(SCRAPE_USAGE)
        return
    tickers = load_watchlist()
    if not tickers:
        await reply.send_error(SCRAPE_EMPTY)
        return

    force = mode == "force"
    out_dir = os.path.join(config.EXPORT_DIR, "full_history")
    await reply.defer()
    progress_msg = await reply.send(_scrape_intro(len(tickers), force))
    results = await _scrape_with_progress(reply, progress_msg, tickers, out_dir, force)
    header, table_text = _scrape_summary(results, len(tickers), out_dir)
    await _deliver_scrape_summary(reply, progress_msg, header, table_text, out_dir)


# ──────────────────────────────────────────────
# ! prefix commands
# ──────────────────────────────────────────────

@bot.command(name="charts")
async def charts_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_charts(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="download")
async def download_cmd(ctx, interval: str, ticker: str = None):
    reply = CtxReply(ctx)
    await handle_download(reply, interval, ticker)
    await send_prefix_tip(ctx, reply)


@bot.command(name="cached")
async def cached_cmd(ctx):
    reply = CtxReply(ctx)
    await handle_cached(reply)
    await send_prefix_tip(ctx, reply)


@bot.command(name="scrapeall")
async def scrapeall_cmd(ctx, mode: str = "cached"):
    """!scrapeall [force] -- full all-time daily history for the whole watchlist."""
    reply = CtxReply(ctx)
    await handle_scrapeall(reply, mode)
    await send_prefix_tip(ctx, reply)


# ──────────────────────────────────────────────
# / slash twins (new in v153)
# ──────────────────────────────────────────────

@bot.tree.command(name="charts", description="Export full daily history (CSV and charts) for every watchlist ticker")
async def slash_charts(interaction: discord.Interaction):
    await handle_charts(InteractionReply(interaction))


@bot.tree.command(name="download", description="Download and cache price history for one ticker or the watchlist")
@app_commands.describe(interval="Timeframe to download", ticker="One ticker (default: the whole watchlist)")
@app_commands.choices(interval=INTERVAL_CHOICES)
async def slash_download(interaction: discord.Interaction, interval: app_commands.Choice[str],
                         ticker: str = None):
    await handle_download(InteractionReply(interaction), interval.value, ticker)


@bot.tree.command(name="cached", description="Summarise the locally cached market data per timeframe")
async def slash_cached(interaction: discord.Interaction):
    await handle_cached(InteractionReply(interaction))


@bot.tree.command(name="scrapeall", description="Scrape full all-time daily history for the whole watchlist")
@app_commands.describe(mode="cached skips tickers scraped in the last ~20h; force re-downloads all")
@app_commands.choices(mode=SCRAPE_MODE_CHOICES)
async def slash_scrapeall(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
    await handle_scrapeall(InteractionReply(interaction), mode.value if mode else "cached")
```

Two equivalences to check while reviewing the diff:
- `!scrapeall` long-table path. Today it edits the progress message to `header + note` and then sends the file. `_deliver_scrape_summary` does the same through `fits=False`. The `discord.NotFound` fallback still sends `full_message[:1900]`.
- `!cached`. Today it appends rows into one `lines` list, and an empty result answers the `TIMEFRAME` variant of the hint. The new code builds the same lines in the same order.

- [ ] **Step 5: Run both tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_scrapeall_stale.py
```

Expected: `0 failed`, `0 xfailed` on both. The 13 `data` cases and the 3 stale tests pass. If `scrapeall_long_summary_attaches_file` fails only on the file event, check that the stub created `out_dir`.

- [ ] **Step 6: Neighbouring tests and complexity**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_slash_commands.py
python -m radon cc -s -n C $WT/swingbot/commands/data.py
```

Expected: the first is green. radon prints nothing: `scrapeall_cmd` C18 is gone, and every new function is below C. Paste the radon output, or `(none)`, into the task report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/commands/data.py tests/commands/parity_cases/data.py tests/commands/test_scrapeall_stale.py
git -C $WT commit -m "feat(v153): SP6 data handlers, /charts /download /cached /scrapeall, stale-token summary"
```

### Task SP7: `growth`: growth, killswitch, portfolio

**Model:** sonnet — three short body moves; the one subtle part, `/killswitch`'s permission decorators, is fully specified here and in the spec.

**Files:**
- Modify: `swingbot/commands/growth.py` (imports at the top; `growth_command` and `killswitch_command` at lines 66-99 today; `portfolio_command` at lines 216-220 today, before SP2. Re-locate them with `git -C $WT grep -n "async def \|^def \|^@bot" -- swingbot/commands/growth.py`)
- Create: `tests/commands/parity_cases/growth.py`
- Modify: `tests/commands/test_growth_command.py` (append a v153 block after the last test, line 219 today)

**Interfaces:**
- Consumes (SP1): `CtxReply`, `InteractionReply`, `send_prefix_tip`, `PREFIX_TIP_UNTIL`, `reply._today`; `ParityCase`.
- Consumes (SP2): `growth.py`'s line `from swingbot.core.edge.portfolio_state import collect_portfolio_state as _collect_portfolio_state` (SP2 Step 3). `handle_portfolio` and the parity stub use the local name `_collect_portfolio_state`. Step 0 confirms it.
- Produces (ledger): `handle_growth(reply, target: float = 10.0)`, `handle_killswitch(reply, action: str = "status")`, `handle_portfolio(reply)`. Also `/growth`, `/portfolio`, and `/killswitch`, whose function is named `slash_killswitch` (SP18 reads it). `/killswitch` has action choices `status`/`on`/`off`, `@app_commands.default_permissions(administrator=True)`, `@app_commands.checks.has_permissions(administrator=True)` and `@app_commands.guild_only()`. SP3's `bot.tree.error` handler answers its `MissingPermissions` and `NoPrivateMessage`.
- Output:
  - `!growth`, `!killswitch` and `!portfolio` texts are unchanged. Only the tip follows a successful answer.
  - `!growth 1` answers the same text through `send_error`, with no tip.
  - `!killswitch` keeps `@commands.has_permissions(administrator=True)`, and any action other than `status`/`on` still releases. That is today's behaviour, and parity keeps it. The slash surface can only send `status`/`on`/`off`.
- Existing tests: `test_growth_command.py` drives `.callback(ctx)` with a `MagicMock` ctx. Its `ctx.command.qualified_name` is not a `str`, so `send_prefix_tip` sends nothing and every `assert_awaited_once` stays true (index, Global Constraints). Those tests are left unchanged. The new block pins the tip and `/killswitch`.

- [ ] **Step 0: Confirm SP1 and SP2 landed**

```bash
git -C $WT grep -n "class CtxReply\|def send_prefix_tip\|^PREFIX_TIP_UNTIL\|def _today" -- swingbot/commands/reply.py
git -C $WT grep -n "portfolio_state" -- swingbot/commands/growth.py
git -C $WT grep -n "def _collect_portfolio_state" -- swingbot/commands/growth.py
```

Expected: four hits in `reply.py`, and one import line in `growth.py` ending `as _collect_portfolio_state`. The third grep must be **empty**. If it is not, SP2 has not landed: stop and report `BLOCKED: SP2 missing`.

- [ ] **Step 1: Write the parity cases (failing)**

Create `$WT/tests/commands/parity_cases/growth.py`:

```python
"""Reply-parity cases for swingbot/commands/growth.py (v153 SP7)."""
import os
import tempfile

from swingbot.commands import growth as growth_mod
from tests.commands.reply_harness import ParityCase

_BASE_STATS = {"expectancy_r": None, "n_closed": 0, "risk_pct": 1.0}


def _stub_stats(**extra):
    def stub(monkeypatch):
        monkeypatch.setattr(growth_mod, "_collect_stats", lambda target=10.0: {**_BASE_STATS, **extra})
    return stub


def _stub_stats_with_chart(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(prefix="v153-growth-"), "mc_fan.png")
    with open(path, "wb") as f:
        f.write(b"\x89PNG")
    _stub_stats(mc_chart_path=path)(monkeypatch)


def _stub_kill(on: bool):
    state = {"on": on, "reason": "manual" if on else None}

    def stub(monkeypatch):
        monkeypatch.setattr("swingbot.core.edge.throttle.kill_state", lambda: dict(state))
        monkeypatch.setattr("swingbot.core.edge.throttle.set_kill",
                            lambda on, reason=None: {"on": on, "reason": reason})
    return stub


def _stub_portfolio(monkeypatch):
    state = {
        "open_heat": 4.5, "heat_cap": 6.0, "sector_heat": {"Technology": 2.5, "Energy": 1.0},
        "clusters": [["AAA", "BBB"]], "throttle_mult": 0.5, "paused": False,
        "kill": {"on": False, "reason": None},
        "growth": {"current_multiple": 1.32, "pct_to_target": 12.1},
    }
    # SP2 binds collect_portfolio_state under this local name in growth.py.
    monkeypatch.setattr(growth_mod, "_collect_portfolio_state", lambda: dict(state))


_GROWTH_PATH = {"realized_daily_growth": 0.001, "on_track_vs": {8: True},
                "current_multiple": 1.2, "pct_to_target": 8.0}

CASES = [
    ParityCase("growth_report", growth_mod.handle_growth, args=(5.0,), stub=_stub_stats()),
    ParityCase("growth_report_with_path_line", growth_mod.handle_growth,
               stub=_stub_stats(growth_path=_GROWTH_PATH)),
    ParityCase("growth_report_with_mc_chart", growth_mod.handle_growth,
               stub=_stub_stats_with_chart),
    ParityCase("growth_target_not_above_1x", growth_mod.handle_growth, args=(1.0,),
               stub=_stub_stats(), expect="error"),
    ParityCase("killswitch_status_off", growth_mod.handle_killswitch, stub=_stub_kill(False)),
    ParityCase("killswitch_status_on", growth_mod.handle_killswitch, args=("status",),
               stub=_stub_kill(True)),
    ParityCase("killswitch_on", growth_mod.handle_killswitch, args=("on",), stub=_stub_kill(False)),
    ParityCase("killswitch_off", growth_mod.handle_killswitch, args=("off",), stub=_stub_kill(True)),
    ParityCase("portfolio", growth_mod.handle_portfolio, stub=_stub_portfolio),
]
```

- [ ] **Step 2: Append the tip and `/killswitch` tests (failing)**

Append to `$WT/tests/commands/test_growth_command.py`:

```python


# --- v153 SP7: the prefix tip line and the /killswitch twin -------------------

def _named_ctx(qualified_name: str) -> MagicMock:
    """A MagicMock ctx whose command has a real qualified name, so
    send_prefix_tip resolves it in SLASH_TWIN (a bare MagicMock does not)."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.command.qualified_name = qualified_name
    return ctx


def _tip_window_open(monkeypatch):
    import datetime as dt
    from swingbot.commands import reply as reply_mod
    monkeypatch.setattr(reply_mod, "_today", lambda: reply_mod.PREFIX_TIP_UNTIL - dt.timedelta(days=1))


def test_growth_prefix_answer_is_followed_by_the_slash_tip(monkeypatch):
    from swingbot.core.planning import account as account_module
    _tip_window_open(monkeypatch)
    monkeypatch.setattr(account_module, "load_account_config",
                        lambda: {"risk_pct": 1.0, "base_balance": None, "balance": None})
    monkeypatch.setattr(account_module, "get_balance_history_points", lambda: [])
    ctx = _named_ctx("growth")

    asyncio.run(growth_command.callback(ctx, target=5.0))

    assert ctx.send.await_count == 2
    assert "GROWTH REALITY CHECK" in ctx.send.call_args_list[0].args[0]
    assert ctx.send.call_args_list[-1].args[0] == "Tip: this is now /growth"


def test_growth_prefix_error_is_not_followed_by_a_tip(monkeypatch):
    _tip_window_open(monkeypatch)
    ctx = _named_ctx("growth")

    asyncio.run(growth_command.callback(ctx, target=1.0))

    ctx.send.assert_awaited_once()
    assert "1x" in ctx.send.call_args.args[0]


def test_killswitch_prefix_tip_names_the_slash_twin(monkeypatch):
    _tip_window_open(monkeypatch)
    ctx = _named_ctx("killswitch")

    asyncio.run(killswitch_command.callback(ctx, action="status"))

    assert ctx.send.call_args_list[-1].args[0] == "Tip: this is now /killswitch"


def test_slash_killswitch_is_hidden_from_non_admins_and_guild_only():
    from swingbot.commands.growth import slash_killswitch
    assert slash_killswitch.default_permissions is not None
    assert slash_killswitch.default_permissions.administrator is True
    assert slash_killswitch.guild_only is True


def test_slash_killswitch_check_rejects_a_non_administrator():
    from discord import app_commands
    from swingbot.commands.growth import slash_killswitch
    interaction = MagicMock()
    interaction.permissions = discord.Permissions.none()

    assert slash_killswitch.checks, "/killswitch must carry the has_permissions check"
    with pytest.raises(app_commands.MissingPermissions):
        slash_killswitch.checks[0](interaction)


def test_slash_killswitch_check_allows_an_administrator():
    from swingbot.commands.growth import slash_killswitch
    interaction = MagicMock()
    interaction.permissions = discord.Permissions.all()

    assert slash_killswitch.checks[0](interaction) is True


def test_slash_killswitch_offers_exactly_status_on_off():
    from swingbot.commands.growth import slash_killswitch
    (action,) = slash_killswitch.parameters
    assert [c.value for c in action.choices] == ["status", "on", "off"]
    assert action.required is False
```

- [ ] **Step 3: Run both to see them fail**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_growth_command.py
```

Expected: the first fails at collection (`AttributeError: ... 'handle_growth'`). In the second, the eight older tests pass. The new tests fail with `ImportError: cannot import name 'slash_killswitch'`, and the tip tests fail on `await_count == 2` / the last call.

- [ ] **Step 4: Rewrite the command section of `growth.py`**

4a. Replace the import block at the top (lines 1-14 today, plus SP2's `portfolio_state` import, which stays exactly as SP2 wrote it) so it reads:

```python
"""!growth, !killswitch, !portfolio and their slash twins (Edge plan E2; v153).

Each command body lives in one handle_<name>(reply, ...) handler shared by
the prefix command and its /<name> slash twin (swingbot/commands/reply.py).
"""
import asyncio
import os
from datetime import date

import discord
from discord import app_commands
from discord.ext import commands

from swingbot import config
from swingbot.bot_core import bot
from swingbot.commands.reply import CtxReply, InteractionReply, send_prefix_tip
from swingbot.core import presentation as ui
from swingbot.core.planning import account as account_module
from swingbot.core.edge.growth import AVG_DAYS_PER_MONTH, growth_report, growth_path
from swingbot.core.tracking.performance import TradeLog
```

Keep SP2's `from swingbot.core.edge.portfolio_state import ...` line directly below these imports.

4b. Replace `growth_command` and `killswitch_command` (the `@bot.command(name="growth")` block through the end of `killswitch_command`) with:

```python
def _growth_path_line(gp: dict, target: float) -> str:
    on_track = gp["on_track_vs"].get(8, False)
    on_track_str = "yes" if on_track else "no"
    return (f"\nat {gp['current_multiple']:.2f}x — {ui.fmt_pct(gp['pct_to_target'])} of the way "
            f"(log scale) toward {target:g}x; on track for {target:g}x-in-8y: {on_track_str}")


async def handle_growth(reply, target: float = 10.0) -> None:
    """Show the honest math to <target>x at current expectancy/frequency."""
    if target <= 1:
        await reply.send_error(
            f"Target must be greater than 1x (got {target:g}x) -- a target of 1x or "
            "less means \"no growth needed\" or \"shrink\", which this dashboard doesn't model. "
            "Try e.g. `!growth 10`."
        )
        return
    await reply.defer()
    stats = await asyncio.to_thread(_collect_stats, target)
    report = growth_report(stats, target=target)
    gp = stats.get("growth_path")
    if gp and gp.get("realized_daily_growth") is not None:
        report += _growth_path_line(gp, target)
    chart_path = stats.get("mc_chart_path")
    file = discord.File(chart_path, filename=os.path.basename(chart_path)) if chart_path else None
    await reply.send(f"```\n{report}\n```", file=file)


async def handle_killswitch(reply, action: str = "status") -> None:
    """on|off|status — hard pause for all new entries."""
    from swingbot.core.edge import throttle
    if action == "status":
        st = throttle.kill_state()
        await reply.send(f"kill switch: {'🔴 ON — ' + str(st['reason']) if st['on'] else '🟢 off'}")
        return
    st = throttle.set_kill(action == "on", reason="manual")
    await reply.send(f"kill switch {'engaged 🔴 — no new entries' if st['on'] else 'released 🟢'}")


@bot.command(name="growth")
async def growth_command(ctx, target: float = 10.0):
    """Show the honest math to <target>x at current expectancy/frequency."""
    reply = CtxReply(ctx)
    await handle_growth(reply, target)
    await send_prefix_tip(ctx, reply)


@bot.command(name="killswitch")
@commands.has_permissions(administrator=True)
async def killswitch_command(ctx, action: str = "status"):
    """!killswitch on|off|status — hard pause for all new entries."""
    reply = CtxReply(ctx)
    await handle_killswitch(reply, action)
    await send_prefix_tip(ctx, reply)
```

4c. Replace `portfolio_command` (the `@bot.command(name="portfolio")` block) with:

```python
async def handle_portfolio(reply) -> None:
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    await reply.defer()
    state = await asyncio.to_thread(_collect_portfolio_state)
    await reply.send(f"```\n{portfolio_report(state)}\n```")


@bot.command(name="portfolio")
async def portfolio_command(ctx):
    """Open heat vs cap, sector bars, clusters, throttle + kill state."""
    reply = CtxReply(ctx)
    await handle_portfolio(reply)
    await send_prefix_tip(ctx, reply)
```

4d. Append the slash twins at the end of the file, after `rs_rotation_report`:

```python


# ──────────────────────────────────────────────
# / slash twins (new in v153)
# ──────────────────────────────────────────────

KILLSWITCH_CHOICES = [
    app_commands.Choice(name="status", value="status"),
    app_commands.Choice(name="on — block all new entries", value="on"),
    app_commands.Choice(name="off — release the kill switch", value="off"),
]


@bot.tree.command(name="growth", description="The honest math to a target multiple at current expectancy and frequency")
@app_commands.describe(target="Target account multiple, above 1 (default 10)")
async def slash_growth(interaction: discord.Interaction, target: float = 10.0):
    await handle_growth(InteractionReply(interaction), target)


# Mirrors !killswitch's runtime check, not just its visibility (spec,
# "Grouping and permissions"): hidden from non-admins in the picker,
# enforced at invocation, and unavailable in DMs where no administrator
# permission exists. SP3's bot.tree.error handler answers the check failures.
@bot.tree.command(name="killswitch", description="Hard pause for all new entries (administrators only)")
@app_commands.describe(action="status (default), on or off")
@app_commands.choices(action=KILLSWITCH_CHOICES)
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def slash_killswitch(interaction: discord.Interaction, action: app_commands.Choice[str] = None):
    await handle_killswitch(InteractionReply(interaction), action.value if action else "status")


@bot.tree.command(name="portfolio", description="Open heat vs cap, sector heat, correlated clusters, throttle and kill state")
async def slash_portfolio(interaction: discord.Interaction):
    await handle_portfolio(InteractionReply(interaction))
```

- [ ] **Step 5: Run the tests**

```bash
python $WT/scripts/dev/testrun.py file tests/commands/test_reply_parity.py
python $WT/scripts/dev/testrun.py file tests/commands/test_growth_command.py
python $WT/scripts/dev/testrun.py file tests/edge/test_edge_heat.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
```

Expected: `0 failed`, `0 xfailed` on all four. The last two guard SP2's move, which this task must not disturb.

- [ ] **Step 6: Complexity**

```bash
python -m radon cc -s -n C $WT/swingbot/commands/growth.py
```

Expected: `_collect_stats` is still C(12) (unchanged), and nothing else is listed. `_collect_portfolio_state` D(22) moved out in SP2. Paste the output into the task report.

- [ ] **Step 7: Commit**

```bash
git -C $WT add swingbot/commands/growth.py tests/commands/parity_cases/growth.py tests/commands/test_growth_command.py
git -C $WT commit -m "feat(v153): SP7 growth handlers, /growth /portfolio and admin-only /killswitch"
```

