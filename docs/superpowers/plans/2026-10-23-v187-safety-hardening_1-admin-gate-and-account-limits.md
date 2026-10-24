# v187 — Safety hardening, part 1: admin gate and account limits (V187-1..V187-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read this part whole**: `grep -n "^### Task V187-6:" -A 320 docs/superpowers/plans/2026-10-23-v187-safety-hardening_1-admin-gate-and-account-limits.md`.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [2026-10-23-v187-safety-hardening-design.md](../specs/2026-10-23-v187-safety-hardening-design.md) — § Why 1–2, § D1, § D2, § Testing (D1, D2, Numerics, D2 additions)
**Index:** [2026-10-23-v187-safety-hardening_0-index.md](2026-10-23-v187-safety-hardening_0-index.md) — Goal, Global Constraints, Spec clarifications 1–7, Contracts and the task ledger live there. Every task below implicitly includes the Global Constraints; the ledger's names, signatures and paths are final.

**Part 1 is two files.** V187-1..V187-5 are here; V187-6 and V187-7 (the sizing backstop) are in [2026-10-23-v187-safety-hardening_1b-sizing-backstop.md](2026-10-23-v187-safety-hardening_1b-sizing-backstop.md), because the seven tasks with full code do not fit one file under the 1500-line cap. Same part, same ledger rows.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-23-v187-safety-hardening` (branch `2026-10-23-v187-safety-hardening`, created in V187-1). Every task edits files **inside `$WT`**; `Create:`/`Modify:` paths are relative to the worktree root. Use `git -C "$WT"` for git, and run tests in a subshell: `(cd "$WT" && python scripts/dev/testrun.py file <test>)`.

**Database.** The account setters and `load_account_config` hit Postgres through `account_repo()`. The new tests below stub `load_account_config` / `save_account_config` / `account_repo` so they never touch the store, but the existing files re-run here (`tests/planning/test_account_db.py`, the sizing callers' tests) do: run `/replicate-prod-db` once before the first test run of this part (CLAUDE.md). If the local `db-test` is down, those tests skip with the start command; start it and re-run, never accept a skip as green.

## Parallelisation

See the index's `## Parallelisation`. Inside this part: V187-1 runs first (worktree). V187-2 and V187-3 may then run together (disjoint files). V187-4 follows V187-3 (same file `planning/account.py`, consumes `_validated`). V187-5 follows V187-1 and V187-3 (same file `commands/account.py`; consumes the `ValueError` contract). V187-6 follows V187-4 and V187-7 follows V187-6 (same function `compute_position_size`). Any part-2 task except V187-13 may run beside any task here, at most two implementers at once.

### Task V187-1: Worktree; administrator gate on the account setters

**Model:** sonnet — sixteen decorator lines over two command surfaces plus a parametrised permission test; mechanical but multi-surface, with the discord.py check APIs to get right.

**Files:**
- Modify: `swingbot/commands/account.py` (imports l.7-8; prefix subcommands l.165-225; slash subcommands l.242-288)
- Create: `tests/commands/test_account_admin_gate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the worktree `$WT` and branch `2026-10-23-v187-safety-hardening` every later task uses; `from discord.ext import commands` in `swingbot/commands/account.py`; `@commands.has_permissions(administrator=True)` on `account_balance`, `account_risk`, `account_maxpositions`, `account_sizing`, `account_positionpct`, `account_maxpositionpct`, `account_maxposition`, `account_maxrisk`; `@app_commands.checks.has_permissions(administrator=True)` on `slash_account_balance`, `slash_account_risk`, `slash_account_maxpositions`, `slash_account_sizing`, `slash_account_positionpct`, `slash_account_maxpositionpct`, `slash_account_maxposition`, `slash_account_maxrisk`. V187-2's coverage test reads these checks. `account_cmd` (the `!account` group callback) and `slash_account_show` stay ungated.

**Why (spec Why 1, D1).** The only permission decorators in the repo are on the kill switch (`swingbot/commands/growth.py:120,230`). Any guild member can run `!account risk 10` or `/account balance 1` today. The gate is the decorator `growth.py` already uses; refusals already flow through `bot_core.on_command_error` (`commands.CheckFailure` → `🚫 You don't have permission to run that command.`) and `slash.py` `APP_CHECK_REPLIES[app_commands.MissingPermissions]` (same text, ephemeral). The `/account` group gets **no** `default_permissions`: discord.py allows it only on top-level commands and the group also holds the read-only `show` (spec D1). Bodies stay byte-identical (`tests/commands/test_slash_parity.py` checks one `handle_*` call per body); only decorators are added, under the `@...command(...)` line and under any `@app_commands.describe`/`choices` lines, so the check wraps the callback before the command object is built.

**How the tests prove refusal leaves state unchanged.** A prefix `Command.invoke(ctx)` runs `prepare` → `can_run` before the callback, so `invoke` with a non-admin `ctx` raises `commands.MissingPermissions` and the patched setter is never reached (probed on discord.py 2.7.1 with `killswitch_command`). The bot registers no global checks, so `ctx.bot.can_run` is stubbed to `True`. Slash checks are plain predicates on `interaction.permissions` (the pattern `tests/commands/test_slash_parity.py:263-270` uses); discord.py only runs the callback after every check returns `True`.

- [ ] **Step 1: Create the worktree**

```bash
R="E:/Documents/Private/Projects/Discord-Bot"
WT="$R/.claude/worktrees/2026-10-23-v187-safety-hardening"
git -C "$R" status --short --branch | head -3          # on main, plan files committed
git -C "$R" worktree add "$WT" -b 2026-10-23-v187-safety-hardening main
git -C "$WT" log --oneline -1
```

Expected: the worktree exists on the new branch at `main`'s HEAD.

- [ ] **Step 2: Write the failing test**

Create `$WT/tests/commands/test_account_admin_gate.py`:

```python
"""v187 D1: the eight account setters answer only to server administrators.

Prefix: `Command.invoke` runs `can_run` (and so the has_permissions check)
before the callback, so a refused invoke never reaches the setter. Slash:
the checks are predicates on `interaction.permissions`, run by discord.py
before the callback. `!account` / `/account show` stay open.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from swingbot import bot_core
from swingbot.commands import account as account_mod
from swingbot.commands.slash import APP_CHECK_REPLIES

DENIED = "🚫 You don't have permission to run that command."

# (prefix command, its slash twin, the setter name it calls)
GATED = [
    (account_mod.account_balance, account_mod.slash_account_balance, "set_balance"),
    (account_mod.account_risk, account_mod.slash_account_risk, "set_risk_pct"),
    (account_mod.account_maxpositions, account_mod.slash_account_maxpositions, "set_max_open_positions"),
    (account_mod.account_sizing, account_mod.slash_account_sizing, "set_sizing_mode"),
    (account_mod.account_positionpct, account_mod.slash_account_positionpct, "set_position_pct"),
    (account_mod.account_maxpositionpct, account_mod.slash_account_maxpositionpct, "set_max_position_pct"),
    (account_mod.account_maxposition, account_mod.slash_account_maxposition,
     "set_max_position_value_absolute"),
    (account_mod.account_maxrisk, account_mod.slash_account_maxrisk, "set_max_risk_amount_absolute"),
]
_IDS = [prefix.qualified_name for prefix, _slash, _setter in GATED]


def _ctx(permissions: discord.Permissions) -> MagicMock:
    ctx = MagicMock()
    ctx.permissions = permissions
    ctx.bot.can_run = AsyncMock(return_value=True)   # the bot registers no global checks
    return ctx


def _interaction(permissions: discord.Permissions) -> MagicMock:
    interaction = MagicMock()
    interaction.permissions = permissions
    return interaction


def _spy_setters(monkeypatch) -> list:
    calls = []
    for _prefix, _slash, setter in GATED:
        monkeypatch.setattr(account_mod, setter,
                            lambda *a, _name=setter, **k: calls.append(_name) or {})
    return calls


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_prefix_setter_refuses_a_non_admin_and_saves_nothing(prefix, slash, setter, monkeypatch):
    calls = _spy_setters(monkeypatch)
    with pytest.raises(commands.MissingPermissions):
        asyncio.run(prefix.invoke(_ctx(discord.Permissions.none())))
    assert calls == []


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_prefix_setter_admits_an_administrator(prefix, slash, setter):
    assert asyncio.run(prefix.can_run(_ctx(discord.Permissions(administrator=True)))) is True


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_slash_setter_refuses_a_non_admin(prefix, slash, setter):
    assert slash.checks, f"/{slash.qualified_name} has no checks"
    with pytest.raises(app_commands.MissingPermissions):
        for check in slash.checks:
            check(_interaction(discord.Permissions.none()))


@pytest.mark.parametrize("prefix,slash,setter", GATED, ids=_IDS)
def test_slash_setter_admits_an_administrator(prefix, slash, setter):
    admin = _interaction(discord.Permissions(administrator=True))
    assert all(check(admin) for check in slash.checks)


def test_account_group_carries_no_default_permissions():
    # discord.py allows default_permissions only on top-level commands, and the
    # group holds the read-only `show` -- the subcommand checks are the gate.
    assert account_mod.account_group.default_permissions is None


def test_read_only_account_views_stay_open_to_a_non_admin():
    member = discord.Permissions.none()
    assert asyncio.run(account_mod.account_cmd.can_run(_ctx(member))) is True
    assert account_mod.slash_account_show.checks == []


def test_prefix_refusal_uses_the_existing_permission_reply():
    sent = []

    class _Ctx:
        command = None

        async def send(self, content=None, **kw):
            sent.append(content)

    asyncio.run(bot_core.on_command_error(_Ctx(), commands.MissingPermissions(["administrator"])))
    assert sent == [DENIED]


def test_slash_refusal_uses_the_existing_ephemeral_reply():
    assert APP_CHECK_REPLIES[app_commands.MissingPermissions] == DENIED
```

- [ ] **Step 3: Run it to verify it fails**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_account_admin_gate.py)`
Expected: FAIL — the prefix `refuses_a_non_admin` cases fail (no `MissingPermissions`: the invoke either reaches the spy or trips over the `MagicMock` ctx), the slash refusal cases fail on `has no checks`; the read-only, group and reply tests already pass.

- [ ] **Step 4: Add the gates**

In `$WT/swingbot/commands/account.py`, change the imports (l.7-8):

```python
import discord
from discord import app_commands
from discord.ext import commands
```

Add `@commands.has_permissions(administrator=True)` under each of the eight prefix setter decorators. The result for each (bodies and docstrings unchanged):

```python
@account_cmd.command(name="balance")
@commands.has_permissions(administrator=True)
async def account_balance(ctx, amount: float):
    reply = CtxReply(ctx)
    await handle_account_balance(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="risk")
@commands.has_permissions(administrator=True)
async def account_risk(ctx, pct: float):
    reply = CtxReply(ctx)
    await handle_account_risk(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositions")
@commands.has_permissions(administrator=True)
async def account_maxpositions(ctx, n: int):
    reply = CtxReply(ctx)
    await handle_account_maxpositions(reply, n)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="sizing")
@commands.has_permissions(administrator=True)
async def account_sizing(ctx, mode: str):
    """`!account sizing risk` (fixed-fractional, size varies with stop distance) or
    `!account sizing account` (fixed allocation -- every trade opens at exactly
    `positionpct`% of the account, regardless of stop distance)."""
    reply = CtxReply(ctx)
    await handle_account_sizing(reply, mode)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="positionpct")
@commands.has_permissions(administrator=True)
async def account_positionpct(ctx, pct: float):
    """Only used in 'account' sizing mode -- see `!account sizing`."""
    reply = CtxReply(ctx)
    await handle_account_positionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxpositionpct")
@commands.has_permissions(administrator=True)
async def account_maxpositionpct(ctx, pct: float):
    """Position-size cap as a % of balance."""
    reply = CtxReply(ctx)
    await handle_account_maxpositionpct(reply, pct)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxposition")
@commands.has_permissions(administrator=True)
async def account_maxposition(ctx, amount: float):
    """Hard currency cap on position value."""
    reply = CtxReply(ctx)
    await handle_account_maxposition(reply, amount)
    await send_prefix_tip(ctx, reply)


@account_cmd.command(name="maxrisk")
@commands.has_permissions(administrator=True)
async def account_maxrisk(ctx, amount: float):
    """Hard currency cap on the real risk if a trade's stop-loss is hit."""
    reply = CtxReply(ctx)
    await handle_account_maxrisk(reply, amount)
    await send_prefix_tip(ctx, reply)
```

Add `@app_commands.checks.has_permissions(administrator=True)` as the last decorator above each of the eight slash setters (`slash_account_show` untouched):

```python
@account_group.command(name="balance", description="Set the base balance (realized P&L keeps adding on top)")
@app_commands.describe(amount="New base balance")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_balance(interaction: discord.Interaction, amount: float):
    await handle_account_balance(InteractionReply(interaction), amount)


@account_group.command(name="risk", description="Set the % of balance risked per trade")
@app_commands.describe(pct="Risk per trade, in percent")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_risk(interaction: discord.Interaction, pct: float):
    await handle_account_risk(InteractionReply(interaction), pct)


@account_group.command(name="maxpositions", description="Set the max number of concurrent open positions")
@app_commands.describe(n="Max concurrent open positions")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_maxpositions(interaction: discord.Interaction, n: int):
    await handle_account_maxpositions(InteractionReply(interaction), n)


@account_group.command(name="sizing", description="Choose the position-sizing mode")
@app_commands.describe(mode="Sizing mode")
@app_commands.choices(mode=SIZING_CHOICES)
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_sizing(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    await handle_account_sizing(InteractionReply(interaction), mode.value)


@account_group.command(name="positionpct", description="Set the position size as a % of account (account sizing mode)")
@app_commands.describe(pct="Position size, in percent of the account")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_positionpct(interaction: discord.Interaction, pct: float):
    await handle_account_positionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxpositionpct", description="Cap a position's size as a % of balance")
@app_commands.describe(pct="Position-size cap, in percent of balance")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_maxpositionpct(interaction: discord.Interaction, pct: float):
    await handle_account_maxpositionpct(InteractionReply(interaction), pct)


@account_group.command(name="maxposition", description="Cap a position's value in currency (0 disables)")
@app_commands.describe(amount="Max position value, absolute")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_maxposition(interaction: discord.Interaction, amount: float):
    await handle_account_maxposition(InteractionReply(interaction), amount)


@account_group.command(name="maxrisk", description="Cap the real loss per trade in currency (0 disables)")
@app_commands.describe(amount="Max loss per trade, absolute")
@app_commands.checks.has_permissions(administrator=True)
async def slash_account_maxrisk(interaction: discord.Interaction, amount: float):
    await handle_account_maxrisk(InteractionReply(interaction), amount)
```

Add one line to the module docstring, after l.5: `The eight setters are administrator-only (v187 D1); !account and /account show stay open.`

- [ ] **Step 5: Run the new test and the parity guards**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_account_admin_gate.py)`
Expected: PASS (all cases).

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_slash_parity.py)`
Expected: PASS — bodies are unchanged and the `/account` group carries no `default_member_permissions`, so `test_killswitch_is_the_only_admin_gated_command_and_is_guild_only` still holds (V187-2 changes it for the two top-level trades commands).

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_reply_parity.py)`
Expected: PASS — handlers untouched.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/commands/account.py tests/commands/test_account_admin_gate.py
git -C "$WT" commit -m "fix(account): account setters answer only to server administrators (v187 D1)"
```

### Task V187-2: Administrator gate on the trade-wiping commands; allowlist coverage test

**Model:** sonnet — six decorators, one existing parity assertion to widen and a command-enumerating coverage test; judgement only in reading the registered names.

**Files:**
- Modify: `swingbot/commands/trades.py` (imports l.6-7; `trades_clear` l.218, `trades_clear_history` l.227, `trade_delete` l.397, `slash_trades_clear` l.708, `slash_trades_clear_history` l.713, `slash_trade_delete` l.727)
- Modify: `tests/commands/test_slash_parity.py` (module docstring item 5, l.11; `test_killswitch_is_the_only_admin_gated_command_and_is_guild_only` l.252-260)
- Create: `tests/commands/test_state_command_gates.py`

**Interfaces:**
- Consumes: V187-1's gated account setters (the coverage test enumerates `swingbot.commands.account` too, so it is red until V187-1 has landed in `$WT`).
- Produces: `GATED_MODULES`, `READ_ONLY_COMMANDS`, `_is_admin_gated(cmd) -> bool` in `tests/commands/test_state_command_gates.py`; administrator gates on `!trades clear`, `!trades clear history`, `!trade delete`, `/trades-clear`, `/trades-clear-history`, `/trade delete`; `default_permissions(administrator=True)` on `/trades-clear` and `/trades-clear-history` only.

**Why (spec Why 1, D1).** `!trades clear`, `!trades clear history` and `!trade delete` wipe or delete trade records with no check, and so do their slash twins. `/trades-clear` and `/trades-clear-history` are top-level, so they also get `@app_commands.default_permissions(administrator=True)`, which hides them from non-admins in the client; `/trade delete` sits in `trade_group` with the read-only `show`, so it relies on the check alone. `!trades clear` is a group (`invoke_without_command=True`); discord.py does run a parent group's checks before a subcommand, but the spec lists both, so `history` is gated explicitly too and the coverage test sees it on its own.

**The allowlist (verified 2026-10-23 against `bot.walk_commands()` / `bot.tree.walk_commands()` on `main`).** Registered from the two modules: prefix `account`, `account balance|risk|maxpositions|sizing|positionpct|maxpositionpct|maxposition|maxrisk`, `trades`, `trades clear`, `trades clear history`, `trade`, `trade delete`, `tradecharts`, `performance`, `pnl`, `summary`; slash `account show`, the eight `account <setter>`, `trades`, `trades-clear`, `trades-clear-history`, `trade show`, `trade delete`, `tradecharts`, `performance`, `pnl`, `summary`. The read-only set is exactly the index contract's literal and matches spec D1's list (`!check` lives in another module). If the implementer finds a registered name in either module that is neither gated here nor in the literal below, stop and ask; never extend the allowlist on your own.

**`test_slash_parity.py` trap.** `test_killswitch_is_the_only_admin_gated_command_and_is_guild_only` asserts the only payload with `default_member_permissions` is `killswitch`. Adding `default_permissions` to the two trades commands breaks it by design; it is widened to the exact three-name set, and the guild-only assertions on `/killswitch` stay.

- [ ] **Step 1: Write the failing coverage test**

Create `$WT/tests/commands/test_state_command_gates.py`:

```python
"""v187 D1: every command in the account and trades modules is either
read-only (allowlisted here) or answers only to server administrators.

Driven by the READ-ONLY allowlist, not by a list of state-changing commands:
a command added to either module is gated by default -- forget the gate and
this test fails until the command is gated or deliberately allowlisted.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ext import commands

from swingbot.bot_core import bot
from swingbot.commands import modules

modules.import_bot_command_modules()

GATED_MODULES = ("swingbot.commands.account", "swingbot.commands.trades")
READ_ONLY_COMMANDS = frozenset({
    # prefix (qualified_name): the group callbacks `account`, `trades`, `trade` are the read-only views
    "account", "trades", "trade", "tradecharts", "performance", "pnl", "summary",
    # slash (qualified_name)
    "account show", "trade show",
})   # "trades", "tradecharts", "performance", "pnl", "summary" are shared prefix/slash names

# Every permission except administrator: a has_permissions(administrator=True)
# check refuses it, a check on any lesser permission would let it through.
ALL_BUT_ADMIN = discord.Permissions.all()
ALL_BUT_ADMIN.administrator = False


def _is_admin_gated(cmd) -> bool:
    return any("has_permissions" in getattr(check, "__qualname__", "") for check in cmd.checks)


def _prefix_commands() -> list:
    return [c for c in bot.walk_commands() if c.callback.__module__ in GATED_MODULES]


def _slash_commands() -> list:
    return [c for c in bot.tree.walk_commands()
            if isinstance(c, app_commands.Command) and c.callback.__module__ in GATED_MODULES]


def _violations(cmds) -> list[str]:
    return sorted(c.qualified_name for c in cmds
                  if c.qualified_name not in READ_ONLY_COMMANDS and not _is_admin_gated(c))


def _gated(cmds) -> list:
    return [c for c in cmds if c.qualified_name not in READ_ONLY_COMMANDS]


def _ctx(permissions: discord.Permissions) -> MagicMock:
    ctx = MagicMock()
    ctx.permissions = permissions
    ctx.bot.can_run = AsyncMock(return_value=True)   # the bot registers no global checks
    return ctx


def _interaction(permissions: discord.Permissions) -> MagicMock:
    interaction = MagicMock()
    interaction.permissions = permissions
    return interaction


def test_every_prefix_command_is_read_only_or_admin_gated():
    assert _violations(_prefix_commands()) == []


def test_every_slash_command_is_read_only_or_admin_gated():
    assert _violations(_slash_commands()) == []


def test_the_checker_catches_an_ungated_command():
    fake = SimpleNamespace(qualified_name="trades nuke", checks=[])
    assert _violations([fake]) == ["trades nuke"]


def test_every_allowlisted_name_is_registered_and_open():
    cmds = _prefix_commands() + _slash_commands()
    names = {c.qualified_name for c in cmds}
    assert READ_ONLY_COMMANDS <= names, sorted(READ_ONLY_COMMANDS - names)
    assert [c.qualified_name for c in cmds
            if c.qualified_name in READ_ONLY_COMMANDS and _is_admin_gated(c)] == []


def test_the_expected_commands_are_gated():
    gated = {c.qualified_name for c in _gated(_prefix_commands())}
    assert {"trades clear", "trades clear history", "trade delete", "account risk"} <= gated
    gated = {c.qualified_name for c in _gated(_slash_commands())}
    assert {"trades-clear", "trades-clear-history", "trade delete", "account balance"} <= gated


@pytest.mark.parametrize("cmd", _gated(_prefix_commands()), ids=lambda c: c.qualified_name)
def test_gated_prefix_command_needs_administrator_itself(cmd):
    with pytest.raises(commands.MissingPermissions):
        asyncio.run(cmd.can_run(_ctx(ALL_BUT_ADMIN)))
    assert asyncio.run(cmd.can_run(_ctx(discord.Permissions(administrator=True)))) is True


@pytest.mark.parametrize("cmd", _gated(_slash_commands()), ids=lambda c: c.qualified_name)
def test_gated_slash_command_needs_administrator_itself(cmd):
    with pytest.raises(app_commands.MissingPermissions):
        for check in cmd.checks:
            check(_interaction(ALL_BUT_ADMIN))
    admin = _interaction(discord.Permissions(administrator=True))
    assert all(check(admin) for check in cmd.checks)


def test_only_the_two_top_level_wipes_are_hidden_from_non_admins():
    from swingbot.commands import trades as trades_mod

    admin = discord.Permissions(administrator=True)
    assert trades_mod.slash_trades_clear.default_permissions == admin
    assert trades_mod.slash_trades_clear_history.default_permissions == admin
    assert trades_mod.trade_group.default_permissions is None   # holds the read-only `show`
```

- [ ] **Step 2: Run it to verify it fails**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_state_command_gates.py)`
Expected: FAIL — the prefix violations list is `['trade delete', 'trades clear', 'trades clear history']`, the slash list is `['trade delete', 'trades-clear', 'trades-clear-history']`; the trades cases of the two parametrised tests fail; `default_permissions` is `None` for both top-level wipes. The `account ...` cases pass (V187-1).

- [ ] **Step 3: Add the gates**

In `$WT/swingbot/commands/trades.py`, change the imports (l.6-7):

```python
import discord
from discord import app_commands
from discord.ext import commands
```

Prefix commands (bodies and docstrings unchanged):

```python
@trades_cmd.group(name="clear", invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def trades_clear(ctx):
    """Clear all currently OPEN/active trades. Closed trade history is kept.
    Use `!trades clear history` to remove closed trade records instead."""
    reply = CtxReply(ctx)
    await handle_trades_clear(reply)
    await send_prefix_tip(ctx, reply)


@trades_clear.command(name="history")
@commands.has_permissions(administrator=True)
async def trades_clear_history(ctx):
    """Clear all CLOSED trade records (win/loss/manually-closed). Open trades are kept."""
    reply = CtxReply(ctx)
    await handle_trades_clear_history(reply)
    await send_prefix_tip(ctx, reply)
```

```python
@trade_cmd.command(name="delete")
@commands.has_permissions(administrator=True)
async def trade_delete(ctx, trade_id: str):
    reply = CtxReply(ctx)
    await handle_trade_delete(reply, trade_id)
    await send_prefix_tip(ctx, reply)
```

Slash commands (the decorator order matches `growth.py:225-232`):

```python
@bot.tree.command(name="trades-clear", description="Clear all open trades (closed trade history is kept)")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def slash_trades_clear(interaction: discord.Interaction):
    await handle_trades_clear(InteractionReply(interaction))


@bot.tree.command(name="trades-clear-history", description="Clear all closed trade records (open trades are kept)")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.has_permissions(administrator=True)
async def slash_trades_clear_history(interaction: discord.Interaction):
    await handle_trades_clear_history(InteractionReply(interaction))
```

```python
@trade_group.command(name="delete", description="Delete one logged trade")
@app_commands.describe(trade_id="Trade ID, as listed by /trades")
@app_commands.checks.has_permissions(administrator=True)
async def slash_trade_delete(interaction: discord.Interaction, trade_id: str):
    await handle_trade_delete(InteractionReply(interaction), trade_id)
```

- [ ] **Step 4: Widen the slash-parity admin assertion**

In `$WT/tests/commands/test_slash_parity.py`, docstring item 5 (l.11) becomes:

```
5. Admin-gated payloads are exactly /killswitch, /trades-clear and
   /trades-clear-history (v187); /killswitch is guild-only with a runtime check.
```

and the test (l.252-260) becomes:

```python
def test_admin_default_permissions_are_exactly_killswitch_and_the_trade_wipes():
    from swingbot.commands.growth import slash_killswitch

    admin = discord.Permissions(administrator=True).value
    gated = {p["name"]: p["default_member_permissions"] for p in _payloads()
             if p.get("default_member_permissions") is not None}
    # v187 D1: the two top-level trade wipes are hidden from non-admins too;
    # /account and /trade are groups holding a read-only `show`, so they
    # rely on their subcommands' runtime checks instead.
    assert gated == {"killswitch": admin, "trades-clear": admin, "trades-clear-history": admin}
    payload = slash_killswitch.to_dict(bot.tree)
    assert payload["dm_permission"] is False
    assert slash_killswitch.guild_only is True
```

`to_dict` emits `default_member_permissions` as the int `8` (`Permissions(administrator=True).value`), checked on discord.py 2.7.1.

- [ ] **Step 5: Run the tests**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_state_command_gates.py)`
Expected: PASS.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_slash_parity.py)`
Expected: PASS (one-body AST check and `SLASH_TWIN` map untouched; widened admin set holds).

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_account_admin_gate.py)`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C "$WT" add swingbot/commands/trades.py tests/commands/test_slash_parity.py tests/commands/test_state_command_gates.py
git -C "$WT" commit -m "fix(trades): trade-wiping commands answer only to administrators; allowlist coverage test (v187 D1)"
```

### Task V187-3: One validator for every account setter

**Model:** sonnet — one table-driven validator and seven one-line setter calls, with a wide boundary table to test; contained to one module.

**Files:**
- Modify: `swingbot/core/planning/account.py` (imports l.57-62; new block after `_append_balance_history` ~l.166; setters `set_balance` l.169, `set_risk_pct` l.199, `set_max_open_positions` l.206, `set_max_position_pct` l.213, `set_max_position_value_absolute` l.220, `set_max_risk_amount_absolute` l.229, `set_position_pct` l.259)
- Create: `tests/planning/test_account_validator.py`

**Interfaces:**
- Consumes: `RISK_CEILING_PCT` (exists, `swingbot/core/edge/sizing.py:19`, value `2.0`).
- Produces: `_validated(key: str, value) -> float | int` in `swingbot/core/planning/account.py` (V187-4 calls it for the seed, V187-5's handlers rely on its `ValueError`); module imports `import math`, `import numbers`, `from swingbot.core.edge.sizing import RISK_CEILING_PCT` (V187-6/7 use `math` and the constant). Every `set_*` except `set_sizing_mode` validates **before** `load_account_config()`, so an invalid value raises `ValueError` and nothing is loaded or saved.

**Why (spec Why 2, D2).** `set_risk_pct` stores any float, and `!account risk 10` or `-1` then sizes every alert. The table and messages are fixed in the index § Contracts → Validator. `bool` is refused for every key (`True` is an `int`); non-numbers (a `str`) are refused with the same message; an unknown key raises `KeyError` (a programming error, not user input). `max_open_positions` accepts an `int` or an integral finite float and returns `int` (never truncates `2.5`). A huge Python int that overflows `float()` is refused, not crashed on. `swingbot/core/edge/sizing.py` imports only `math`, so the module-level import adds no cycle.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/planning/test_account_validator.py`:

```python
"""v187 D2: one validator for every account setter (index § Contracts)."""
import re

import pytest

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning import account as acct

NAN, INF = float("nan"), float("inf")
BAD_FLOATS = [NAN, INF, -INF, -1.0]

# key: (accepted values, refused values)
TABLE = {
    "risk_pct": ([0.01, 1.0, RISK_CEILING_PCT], BAD_FLOATS + [0, 0.0, RISK_CEILING_PCT + 0.01, 100]),
    "position_pct": ([0.001, 100, 100.0], BAD_FLOATS + [0, 100.01]),
    "max_position_pct": ([0.1, 100.0], BAD_FLOATS + [0, 100.01]),
    "max_position_value_absolute": ([0, 0.0, 1000.0, 1e9], BAD_FLOATS),
    "max_risk_amount_absolute": ([0, 100.0], BAD_FLOATS),
    "base_balance": ([0.01, 10_000, 1e8], BAD_FLOATS + [0]),
    "max_open_positions": ([1, 30, 3.0], BAD_FLOATS + [0, 2.5]),
}
CASES_OK = [(k, v) for k, (ok, _bad) in TABLE.items() for v in ok]
CASES_BAD = [(k, v) for k, (_ok, bad) in TABLE.items() for v in bad]
MESSAGES = {
    "risk_pct": "Risk per trade must be above 0% and at most 2.0% (got {v}).",
    "position_pct": "Position size must be above 0% and at most 100% of the account (got {v}).",
    "max_position_pct": "Max position size must be above 0% and at most 100% of the account (got {v}).",
    "max_position_value_absolute": "Max position value must be 0 (off) or more (got {v}).",
    "max_risk_amount_absolute": "Max risk per trade must be 0 (off) or more (got {v}).",
    "base_balance": "Balance must be above 0 (got {v}).",
    "max_open_positions": "Max open positions must be a whole number of 1 or more (got {v}).",
}


@pytest.mark.parametrize("key,value", CASES_OK, ids=[f"{k}={v}" for k, v in CASES_OK])
def test_accepts(key, value):
    got = acct._validated(key, value)
    assert got == value
    assert type(got) is (int if key == "max_open_positions" else float)


@pytest.mark.parametrize("key,value", CASES_BAD, ids=[f"{k}={v}" for k, v in CASES_BAD])
def test_refuses_with_the_setting_and_its_range(key, value):
    with pytest.raises(ValueError) as err:
        acct._validated(key, value)
    assert str(err.value) == MESSAGES[key].format(v=value)


def test_risk_message_is_rendered_from_the_ceiling_constant(monkeypatch):
    monkeypatch.setattr(acct, "RISK_CEILING_PCT", 1.5)
    with pytest.raises(ValueError, match=r"at most 1\.5% \(got 1\.6\)"):
        acct._validated("risk_pct", 1.6)
    assert acct._validated("risk_pct", 1.5) == 1.5


@pytest.mark.parametrize("key", sorted(TABLE))
def test_bool_and_text_are_refused_for_every_key(key):
    for value in (True, False, "1", None):
        with pytest.raises(ValueError):
            acct._validated(key, value)


def test_max_open_positions_stores_an_integral_float_as_int():
    assert acct._validated("max_open_positions", 3.0) == 3
    assert isinstance(acct._validated("max_open_positions", 3.0), int)


def test_an_int_too_large_for_a_float_is_refused():
    with pytest.raises(ValueError):
        acct._validated("max_open_positions", 10 ** 400)


def test_unknown_key_is_a_programming_error():
    with pytest.raises(KeyError):
        acct._validated("sizing_mode", "risk")


# ── setters: validate first, save nothing on refusal ────────────────────

SETTERS = [
    (acct.set_balance, "base_balance", 5000.0, -1.0),
    (acct.set_risk_pct, "risk_pct", 1.5, 10.0),
    (acct.set_max_open_positions, "max_open_positions", 7, 2.5),
    (acct.set_max_position_pct, "max_position_pct", 20.0, 0.0),
    (acct.set_max_position_value_absolute, "max_position_value_absolute", 0.0, NAN),
    (acct.set_max_risk_amount_absolute, "max_risk_amount_absolute", 150.0, -5.0),
    (acct.set_position_pct, "position_pct", 12.5, 100.5),
]


@pytest.fixture
def store(monkeypatch):
    saved = []
    monkeypatch.setattr(acct, "load_account_config",
                        lambda: {"base_balance": 10_000.0, "balance": 10_000.0, "balance_history": []})
    monkeypatch.setattr(acct, "save_account_config", lambda cfg: saved.append(dict(cfg)))
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return saved


@pytest.mark.parametrize("setter,key,good,bad", SETTERS, ids=[s[1] for s in SETTERS])
def test_setter_refuses_an_invalid_value_and_saves_nothing(store, setter, key, good, bad):
    with pytest.raises(ValueError, match=re.escape(MESSAGES[key].split(" (got")[0])):
        setter(bad)
    assert store == []


@pytest.mark.parametrize("setter,key,good,bad", SETTERS, ids=[s[1] for s in SETTERS])
def test_setter_stores_the_validated_value(store, setter, key, good, bad):
    cfg = setter(good)
    assert cfg[key] == good and store[-1][key] == good


def test_max_open_positions_setter_stores_an_int(store):
    assert acct.set_max_open_positions(3.0)["max_open_positions"] == 3
    assert type(store[-1]["max_open_positions"]) is int
```

- [ ] **Step 2: Run it to verify it fails**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_validator.py)`
Expected: FAIL — `AttributeError: module 'swingbot.core.planning.account' has no attribute '_validated'` (and `RISK_CEILING_PCT` for the monkeypatch test); the setter refusal cases fail with `DID NOT RAISE`.

- [ ] **Step 3: Implement the validator**

In `$WT/swingbot/core/planning/account.py`, the imports (l.57-62) become:

```python
import math
import numbers
from dataclasses import dataclass
from datetime import datetime, timezone

from swingbot import config as app_config
from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.market import opex
from swingbot.core.market.session import BERLIN_TZ as _BERLIN_TZ
```

Add after `_append_balance_history` (before `set_balance`):

```python
# v187 D2: every account setter (and the .env seed, see _validated_seed)
# goes through _validated. key: (lower bound, lower bound inclusive,
# upper bound or None, message). "{ceiling}" renders RISK_CEILING_PCT, so
# the 2% never appears as a second literal here.
_SETTING_RULES: dict[str, tuple[float, bool, float | None, str]] = {
    "risk_pct": (0.0, False, None,
                 "Risk per trade must be above 0% and at most {ceiling}% (got {value})."),
    "position_pct": (0.0, False, 100.0,
                     "Position size must be above 0% and at most 100% of the account (got {value})."),
    "max_position_pct": (0.0, False, 100.0,
                         "Max position size must be above 0% and at most 100% of the account (got {value})."),
    "max_position_value_absolute": (0.0, True, None, "Max position value must be 0 (off) or more (got {value})."),
    "max_risk_amount_absolute": (0.0, True, None, "Max risk per trade must be 0 (off) or more (got {value})."),
    "base_balance": (0.0, False, None, "Balance must be above 0 (got {value})."),
    "max_open_positions": (1.0, True, None,
                           "Max open positions must be a whole number of 1 or more (got {value})."),
}
_INTEGER_SETTINGS = frozenset({"max_open_positions"})


def _upper_bound(key: str, high: float | None) -> float | None:
    # risk_pct's ceiling is read at call time so it always tracks the constant.
    return RISK_CEILING_PCT if key == "risk_pct" else high


def _as_finite_number(value) -> float | None:
    """`value` as a finite float, or None for a bool, a non-number, NaN, +-inf
    or an int too large for a float."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _in_range(number: float, low: float, low_inclusive: bool, high: float | None) -> bool:
    above = number >= low if low_inclusive else number > low
    return above and (high is None or number <= high)


def _validated(key: str, value) -> float | int:
    """Normalised value for an account setting, or ValueError naming the setting and its range."""
    low, low_inclusive, high, message = _SETTING_RULES[key]
    error = ValueError(message.format(value=value, ceiling=RISK_CEILING_PCT))
    number = _as_finite_number(value)
    if number is None or not _in_range(number, low, low_inclusive, _upper_bound(key, high)):
        raise error
    if key in _INTEGER_SETTINGS:
        if not number.is_integer():
            raise error
        return int(number)
    return number
```

Each setter validates on its first line and stores the validated value (docstrings unchanged):

```python
def set_balance(balance: float) -> dict:
    """...docstring unchanged..."""
    balance = _validated("base_balance", balance)
    config = load_account_config()
    # ...rest of the body unchanged (it already uses `balance`)...


def set_risk_pct(risk_pct: float) -> dict:
    value = _validated("risk_pct", risk_pct)
    config = load_account_config()
    config["risk_pct"] = value
    save_account_config(config)
    return config


def set_max_open_positions(max_open: int) -> dict:
    value = _validated("max_open_positions", max_open)
    config = load_account_config()
    config["max_open_positions"] = value
    save_account_config(config)
    return config


def set_max_position_pct(max_pct: float) -> dict:
    value = _validated("max_position_pct", max_pct)
    config = load_account_config()
    config["max_position_pct"] = value
    save_account_config(config)
    return config


def set_max_position_value_absolute(amount: float) -> dict:
    """...docstring unchanged..."""
    value = _validated("max_position_value_absolute", amount)
    config = load_account_config()
    config["max_position_value_absolute"] = value
    save_account_config(config)
    return config


def set_max_risk_amount_absolute(amount: float) -> dict:
    """...docstring unchanged..."""
    value = _validated("max_risk_amount_absolute", amount)
    config = load_account_config()
    config["max_risk_amount_absolute"] = value
    save_account_config(config)
    return config


def set_position_pct(pct: float) -> dict:
    value = _validated("position_pct", pct)
    config = load_account_config()
    config["position_pct"] = value
    save_account_config(config)
    return config
```

(`...docstring unchanged...` means leave the existing docstring text in place, not a literal.) `set_sizing_mode` is untouched.

- [ ] **Step 4: Run the tests**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_validator.py)`
Expected: PASS.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_db.py)` (after `/replicate-prod-db`)
Expected: PASS — `set_balance(5000.0)` / `set_balance(1000.0)` are valid.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/edge/test_edge_sizing.py)`
Expected: PASS (`set_sizing_mode` untouched; the module-level `RISK_CEILING_PCT` import adds no cycle).

Run: `(cd "$WT" && python scripts/dev/complexity_gate.py)`
Expected: no new offender (`_validated` B-grade, helpers A).

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add swingbot/core/planning/account.py tests/planning/test_account_validator.py
git -C "$WT" commit -m "fix(account): every account setter refuses NaN, inf, negative and out-of-range values (v187 D2)"
```

### Task V187-4: Validated `.env` seed and an honest RISK_PER_TRADE_PCT field

**Model:** sonnet — a seed-path wrapper over V187-3's validator plus a config default/help fix and one sync-test tolerance removed; small but crosses three files.

**Files:**
- Modify: `swingbot/core/planning/account.py` (`load_account_config` seed branch ~l.140-152; new helpers above it; module logger)
- Modify: `swingbot/config.py` (`RISK_PER_TRADE_PCT` l.521-527, `MAX_OPEN_POSITIONS` help l.528-531)
- Modify: `tests/infra/test_env_example_sync.py` (docstring l.16-22; one new test)
- Create: `tests/planning/test_account_seed_validation.py`

**Interfaces:**
- Consumes: `_validated(key, value)` (V187-3).
- Produces: `_SEED_ENV_KEYS: dict[str, str]`, `_field_default(env_key: str) -> str`, `_validated_seed(defaults: dict) -> dict`; module logger `log = logging.getLogger(__name__)` in `swingbot/core/planning/account.py` (V187-6 logs its `sizing:` warnings through it); `RISK_PER_TRADE_PCT` `Field` with `default="1.0"`, `max=2`.

**Why (spec D2 "The .env seed path", "Copy"; index clarification 5).** `load_account_config` seeds a brand-new account row straight from `app_config` with no setter, so `RISK_PER_TRADE_PCT=10` in `.env` would seed 10%. Each seeded value now goes through `_validated`; a failure falls back to the schema `Field` default (read from `swingbot.config.FIELDS` by env key) with a warning. That default is `"0.01"` today (0.01% risk), so it is corrected to `"1.0"`, matching `.env.example:326`, and the docstring tolerance in `test_env_example_sync.py` for that mismatch goes; a new test pins the two equal. Stored rows are not re-validated here (the sizing backstop, V187-6, covers them). `sizing_mode` and `balance_history` are not in `_SEED_ENV_KEYS` (the mode is normalised elsewhere). `MAX_OPEN_POSITIONS`'s help says "Informational only, same as the two fields above", which stops being true once `RISK_PER_TRADE_PCT` sizes alerts; its own behaviour (a warning line in the alert, `scan_run.py:1116-1119`) is described instead. `MAX_POSITION_SIZE_PCT`, `MAX_POSITION_VALUE_ABSOLUTE`, `MAX_RISK_AMOUNT_ABSOLUTE` help is accurate and stays. All seven `Field` defaults pass `_validated` (`1000000`, `1.0`, `30`, `0.1`, `0.1`, `1000`, `100`), so the fallback itself can never raise.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/planning/test_account_seed_validation.py`:

```python
"""v187 D2: a brand-new account row seeded from .env is validated."""
import logging

import pytest

from swingbot import config as app_config
from swingbot.core.planning import account as acct


class _Repo:
    def __init__(self):
        self.saved = []

    def load(self):
        return None            # no stored row: the seed branch runs

    def save(self, cfg):
        self.saved.append(dict(cfg))


@pytest.fixture
def repo(monkeypatch):
    from swingbot.core.db.repositories import account as repo_mod
    fake = _Repo()
    monkeypatch.setattr(repo_mod, "account_repo", lambda: fake)
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return fake


def test_every_seed_key_falls_back_to_a_valid_field_default():
    for key, env_key in acct._SEED_ENV_KEYS.items():
        acct._validated(key, float(acct._field_default(env_key)))


def test_risk_field_default_is_one_percent_and_capped_at_two():
    field = next(f for f in app_config.FIELDS if f.key == "RISK_PER_TRADE_PCT")
    assert (field.default, field.max) == ("1.0", 2)
    assert "informational only" not in field.help.lower()


def test_a_ten_percent_env_risk_seeds_the_default_and_warns(repo, monkeypatch, caplog):
    monkeypatch.setattr(app_config, "RISK_PER_TRADE_PCT", 10.0)
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        cfg = acct.load_account_config()
    assert cfg["risk_pct"] == 1.0 and repo.saved[-1]["risk_pct"] == 1.0
    [record] = [r for r in caplog.records if "RISK_PER_TRADE_PCT" in r.getMessage()]
    assert "10.0" in record.getMessage() and "1.0" in record.getMessage()


@pytest.mark.parametrize("attr,key,bad", [
    ("ACCOUNT_BALANCE", "base_balance", -5.0),
    ("MAX_OPEN_POSITIONS", "max_open_positions", 0),
    ("MAX_POSITION_SIZE_PCT", "max_position_pct", float("nan")),
    ("POSITION_SIZE_PCT_OF_ACCOUNT", "position_pct", 150.0),
    ("MAX_POSITION_VALUE_ABSOLUTE", "max_position_value_absolute", -1.0),
    ("MAX_RISK_AMOUNT_ABSOLUTE", "max_risk_amount_absolute", float("inf")),
])
def test_each_invalid_seed_value_falls_back(repo, monkeypatch, attr, key, bad):
    monkeypatch.setattr(app_config, attr, bad)
    cfg = acct.load_account_config()
    assert cfg[key] == acct._validated(key, float(acct._field_default(attr)))


def test_a_valid_seed_is_kept_and_does_not_warn(repo, monkeypatch, caplog):
    monkeypatch.setattr(app_config, "RISK_PER_TRADE_PCT", 1.5)
    with caplog.at_level(logging.WARNING, logger=acct.log.name):
        cfg = acct.load_account_config()
    assert cfg["risk_pct"] == 1.5
    assert not [r for r in caplog.records if "RISK_PER_TRADE_PCT" in r.getMessage()]


def test_a_stored_row_is_not_rewritten_by_the_seed_check(monkeypatch):
    from swingbot.core.db.repositories import account as repo_mod
    stored = {"base_balance": 10_000.0, "risk_pct": 10.0, "balance_history": []}
    fake = _Repo()
    fake.load = lambda: dict(stored)
    monkeypatch.setattr(repo_mod, "account_repo", lambda: fake)
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    assert acct.load_account_config()["risk_pct"] == 10.0   # the sizing backstop covers it
```

Append to `$WT/tests/infra/test_env_example_sync.py`:

```python
def test_risk_per_trade_default_matches_env_example():
    # v187 D2: the schema default is the seed fallback for an invalid .env
    # value, so it must be the sane 1% .env.example ships, not 0.01%.
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    m = re.search(r"^RISK_PER_TRADE_PCT=(.*)$", text, re.MULTILINE)
    schema = {f.key: f.default for f in config.FIELDS}
    assert m and m.group(1).strip() == schema["RISK_PER_TRADE_PCT"] == "1.0"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_seed_validation.py)`
Expected: FAIL — `AttributeError: ... has no attribute '_SEED_ENV_KEYS'` / `'log'`; the field test sees `('0.01', None)`.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py)`
Expected: FAIL — `'1.0' == '0.01'`.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/planning/account.py`, add `import logging` to the import block (alphabetical, before `import math`) and, after the imports, `log = logging.getLogger(__name__)`. Add above `load_account_config`:

```python
# v187 D2: account key -> the .env key that seeds it on a brand-new row.
_SEED_ENV_KEYS: dict[str, str] = {
    "base_balance": "ACCOUNT_BALANCE",
    "risk_pct": "RISK_PER_TRADE_PCT",
    "max_open_positions": "MAX_OPEN_POSITIONS",
    "max_position_pct": "MAX_POSITION_SIZE_PCT",
    "position_pct": "POSITION_SIZE_PCT_OF_ACCOUNT",
    "max_position_value_absolute": "MAX_POSITION_VALUE_ABSOLUTE",
    "max_risk_amount_absolute": "MAX_RISK_AMOUNT_ABSOLUTE",
}


def _field_default(env_key: str) -> str:
    """The schema default for an .env key (swingbot.config.FIELDS)."""
    return next(f.default for f in app_config.FIELDS if f.key == env_key)


def _validated_seed(defaults: dict) -> dict:
    """`defaults` with every seeded setting validated; an invalid .env value
    falls back to its schema default, with a warning."""
    seeded = dict(defaults)
    for key, env_key in _SEED_ENV_KEYS.items():
        try:
            seeded[key] = _validated(key, defaults[key])
        except ValueError as exc:
            seeded[key] = _validated(key, float(_field_default(env_key)))
            log.warning("account seed: %s=%r is invalid (%s); seeding the default %r instead",
                        env_key, defaults[key], exc, seeded[key])
    return seeded
```

In `load_account_config`, the seed branch (after the `if stored:` block) starts with the validation:

```python
    # Brand-new account -- seed balance_history with a starting point so the
    # "balance over time" chart has something to plot from before the first
    # trade ever closes, instead of an empty series until then.
    defaults = _validated_seed(defaults)   # v187 D2: .env values never bypass the setters' rules
    defaults["balance"] = round(defaults["base_balance"] + _sum_realized_pnl(), 2)
    # ...rest unchanged...
```

In `$WT/swingbot/config.py`, the two fields become:

```python
    Field("RISK_PER_TRADE_PCT", "RISK_PER_TRADE_PCT", "Account Defaults", "Risk per trade %",
          type="float", default="1.0", min=0, max=2, step=0.01,
          help="The % of account balance a single trade loses if its stop-loss is hit (1% means a full "
               "stop-out costs 1% of the account). Seeds the account's risk-per-trade the first time the "
               "account is created; that setting sizes the suggested position on every alert, capped at "
               "2%. Edit anytime with !account risk PCT (administrators only)."),
    Field("MAX_OPEN_POSITIONS", "MAX_OPEN_POSITIONS", "Account Defaults", "Max open positions",
          type="number", default="30", min=1, step=1,
          help="Seeds the account's open-position limit. It never blocks an alert: once this many paper "
               "trades are open, new alerts still post but the Discord embed shows a position-limit "
               "warning. Edit anytime with !account maxpositions N (administrators only)."),
```

In `$WT/tests/infra/test_env_example_sync.py`, the third docstring bullet (l.16-22) becomes:

```
* **Schema defaults that are themselves wrong.** `MAX_POSITION_SIZE_PCT` is
  documented as a percentage (capped at `max=100`) but defaults to `0.1`,
  i.e. 0.1%. A test that forced the example to match the schema would push
  that onto every fresh install. (`RISK_PER_TRADE_PCT` was the second case
  until v187 set its default to `1.0`; it is now pinned equal below, because
  the default is the seed fallback for an invalid `.env` value.)
```

- [ ] **Step 4: Run the tests**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_seed_validation.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/infra/test_env_example_sync.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_validator.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_account_db.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/planning/test_stop_scope.py)` → PASS (reads `config.RISK_PER_TRADE_PCT`; any value ≤ 2 keeps its budget arithmetic).
Run: `(cd "$WT" && git grep -ln "RISK_PER_TRADE_PCT" tests/admin)`; for each file listed run `python scripts/dev/testrun.py file <it>` → PASS (the admin form now enforces `max=2`).

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add swingbot/core/planning/account.py swingbot/config.py tests/infra/test_env_example_sync.py tests/planning/test_account_seed_validation.py
git -C "$WT" commit -m "fix(account): validate the .env account seed; RISK_PER_TRADE_PCT defaults to 1%, max 2% (v187 D2)"
```

### Task V187-5: Discord handlers refuse invalid settings; true cap copy; stored → used line

**Model:** sonnet — seven handlers routed through one refusal helper, three copy lines and a display helper, with parity cases; one module plus its tests.

**Files:**
- Modify: `swingbot/commands/account.py` (imports l.7-16; `_sizing_line` l.37-44; `_sizing_set_text` l.47-63; handlers l.85-151)
- Modify: `tests/commands/parity_cases/account.py` (one stub, two `ParityCase`s)
- Create: `tests/commands/test_account_handlers_validation.py`

**Interfaces:**
- Consumes: V187-1's gated commands (same file; bodies untouched here); V187-3's `ValueError` from every `set_*` (message names the setting and its range); `RISK_CEILING_PCT` from `swingbot.core.edge.sizing`.
- Produces: `_risk_used_text(cfg: dict) -> str` and `_apply_setting(reply, setter, value) -> dict | None` in `swingbot/commands/account.py`.

**Why (spec D2 bullets 1, 2 and "Copy").** A refused value must reach the user as the validator's message, identically on `!` and `/` (`reply.send_error`, the path `handle_account_sizing` already uses), and nothing is saved (the setter raised before loading). `_sizing_set_text`'s "the frozen 2% hard cap" (l.58) becomes true with V187-6 and is rendered from `RISK_CEILING_PCT`. A legacy stored `risk_pct` above the cap is shown as `10% stored → 2% used (hard cap)` so the clamp is never silent; every in-range value renders exactly as today (`f"{cfg['risk_pct']}%"`), so the existing parity cases see no change. `_apply_setting` looks the setter up through the module global at call time, so the parity stubs that patch `account_mod.set_*` keep working.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/commands/test_account_handlers_validation.py`:

```python
"""v187 D2: invalid account settings are refused with the validator's message
and nothing is saved; the legacy clamp is visible in !account."""
import asyncio

import pytest

from swingbot.commands import account as account_mod
from swingbot.core.planning import account as acct


class _Reply:
    def __init__(self):
        self.sent, self.errors = [], []

    async def send(self, content=None, **kw):
        self.sent.append(content)

    async def send_error(self, text, **kw):
        self.errors.append(text)


@pytest.fixture
def saved(monkeypatch):
    out = []
    monkeypatch.setattr(acct, "load_account_config",
                        lambda: {"base_balance": 10_000.0, "balance": 10_000.0, "risk_pct": 1.0,
                                 "sizing_mode": "risk_pct", "balance_history": []})
    monkeypatch.setattr(acct, "save_account_config", lambda cfg: out.append(dict(cfg)))
    monkeypatch.setattr(acct, "_sum_realized_pnl", lambda: 0.0)
    return out


CASES = [
    (account_mod.handle_account_balance, -100.0, "Balance must be above 0 (got -100.0)."),
    (account_mod.handle_account_risk, 10.0, "Risk per trade must be above 0% and at most 2.0% (got 10.0)."),
    (account_mod.handle_account_risk, float("nan"), "Risk per trade must be above 0% and at most 2.0% (got nan)."),
    (account_mod.handle_account_maxpositions, 0,
     "Max open positions must be a whole number of 1 or more (got 0)."),
    (account_mod.handle_account_positionpct, 150.0,
     "Position size must be above 0% and at most 100% of the account (got 150.0)."),
    (account_mod.handle_account_maxpositionpct, -1.0,
     "Max position size must be above 0% and at most 100% of the account (got -1.0)."),
    (account_mod.handle_account_maxposition, -1.0, "Max position value must be 0 (off) or more (got -1.0)."),
    (account_mod.handle_account_maxrisk, float("inf"), "Max risk per trade must be 0 (off) or more (got inf)."),
]


@pytest.mark.parametrize("handler,value,message", CASES, ids=[f"{c[0].__name__}={c[1]}" for c in CASES])
def test_invalid_value_replies_with_the_message_and_saves_nothing(saved, handler, value, message):
    reply = _Reply()
    asyncio.run(handler(reply, value))
    assert reply.errors == [message] and reply.sent == [] and saved == []


def test_valid_value_still_saves_and_confirms(saved):
    reply = _Reply()
    asyncio.run(account_mod.handle_account_risk(reply, 1.5))
    assert reply.sent == ["Risk per trade set to 1.5%."] and saved[-1]["risk_pct"] == 1.5


@pytest.mark.parametrize("stored,text", [
    (1.0, "1.0%"),
    (2.0, "2.0%"),
    (10.0, "10% stored → 2% used (hard cap)"),
    (2.5, "2.5% stored → 2% used (hard cap)"),
])
def test_risk_used_text(stored, text):
    assert account_mod._risk_used_text({"risk_pct": stored}) == text


def test_account_show_makes_the_legacy_clamp_visible(monkeypatch):
    cfg = {"balance": 10_000.0, "base_balance": 10_000.0, "risk_pct": 10.0, "sizing_mode": "risk_pct"}
    monkeypatch.setattr(account_mod, "load_account_config", lambda: dict(cfg))
    reply = _Reply()
    asyncio.run(account_mod.handle_account_show(reply))
    assert "Risk %** -- 10% stored → 2% used (hard cap) of balance risked per trade" in reply.sent[0]


def test_edge_mode_copy_names_the_real_hard_cap():
    text = account_mod._sizing_set_text({"sizing_mode": "kelly", "risk_pct": 1.0, "balance": 1.0})
    assert text.endswith("(1.0%, the ceiling) or the frozen 2% hard cap.")
```

In `$WT/tests/commands/parity_cases/account.py`, add after `_stub_bad_sizing`:

```python
def _stub_bad_risk(monkeypatch):
    def boom(pct):
        raise ValueError(f"Risk per trade must be above 0% and at most 2.0% (got {pct}).")
    monkeypatch.setattr(account_mod, "set_risk_pct", boom)
```

and append to `CASES`:

```python
    ParityCase("account_risk_invalid", account_mod.handle_account_risk,
               args=(10.0,), stub=_stub_bad_risk, expect="error"),
    ParityCase("account_show_legacy_risk_above_cap", account_mod.handle_account_show,
               stub=_stub("load_account_config", risk_pct=10.0)),
```

- [ ] **Step 2: Run them to verify they fail**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_account_handlers_validation.py)`
Expected: FAIL — the invalid cases raise `ValueError` out of the handler; `_risk_used_text` is missing.

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_reply_parity.py)`
Expected: FAIL on `account_risk_invalid` (unhandled `ValueError`).

- [ ] **Step 3: Implement**

In `$WT/swingbot/commands/account.py`, imports:

```python
import math

import discord
from discord import app_commands
from discord.ext import commands

from swingbot.core.edge.sizing import RISK_CEILING_PCT
from swingbot.core.planning.account import (
```

(the rest of the import block unchanged). Text builders:

```python
def _risk_used_text(cfg: dict) -> str:
    """The stored risk %, or `10% stored → 2% used (hard cap)` when a legacy
    row sits above the cap compute_position_size clamps it to (v187 D2)."""
    stored = cfg.get("risk_pct")
    if isinstance(stored, (int, float)) and math.isfinite(stored) and stored > RISK_CEILING_PCT:
        return f"{stored:g}% stored → {RISK_CEILING_PCT:g}% used (hard cap)"
    return f"{stored}%"


def _sizing_line(cfg: dict) -> str:
    mode = cfg.get("sizing_mode", "risk_pct")
    if mode == "account_pct":
        return f"Position sizing: **Account %** -- {cfg.get('position_pct', 0.1)}% of balance per trade"
    if mode in _EDGE_SIZING_LABELS:
        return (f"Position sizing: **{_EDGE_SIZING_LABELS[mode]}** -- effective risk computed "
                f"per-trade from strategy/volatility stats (config risk {_risk_used_text(cfg)} is the ceiling)")
    return f"Position sizing: **Risk %** -- {_risk_used_text(cfg)} of balance risked per trade"
```

In `_sizing_set_text`, the edge-mode sentence's last line and the risk-mode sentence become:

```python
            f"({cfg['risk_pct']}%, the ceiling) or the frozen {RISK_CEILING_PCT:g}% hard cap."
        )
    return (
        f"Position sizing set to **Risk %** -- every trade is now sized so a full "
        f"stop-out costs {_risk_used_text(cfg)} of the account balance."
    )
```

Handlers — add the helper above `handle_account_show`, then route the seven setters through it:

```python
async def _apply_setting(reply, setter, value) -> dict | None:
    """setter(value), or None after replying with the validator's message
    (v187 D2: nothing was saved, the setter raised before loading)."""
    try:
        return setter(value)
    except ValueError as exc:
        await reply.send_error(str(exc))
        return None


async def handle_account_balance(reply, amount: float) -> None:
    cfg = await _apply_setting(reply, set_balance, amount)
    if cfg is None:
        return
    await reply.send(
        f"Base balance set to {amount} -- effective balance is now {cfg['balance']} "
        f"(base + all-time realized P&L). This will keep accounting for realized "
        f"gain/loss on top of this new base going forward."
    )


async def handle_account_risk(reply, pct: float) -> None:
    cfg = await _apply_setting(reply, set_risk_pct, pct)
    if cfg is None:
        return
    await reply.send(f"Risk per trade set to {cfg['risk_pct']}%.")


async def handle_account_maxpositions(reply, n: int) -> None:
    cfg = await _apply_setting(reply, set_max_open_positions, n)
    if cfg is None:
        return
    await reply.send(f"Max concurrent open positions set to {cfg['max_open_positions']}.")
```

`handle_account_positionpct`, `handle_account_maxpositionpct`, `handle_account_maxposition` and `handle_account_maxrisk` change the same way: their first line `cfg = set_x(value)` becomes `cfg = await _apply_setting(reply, set_x, value)` followed by `if cfg is None:` / `return`; docstrings and `reply.send(...)` bodies unchanged. `handle_account_sizing` and `handle_account_show` are unchanged.

- [ ] **Step 4: Run the tests**

Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_account_handlers_validation.py)` → PASS.
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_reply_parity.py)` → PASS (both new cases: identical events on both surfaces).
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_slash_parity.py)` → PASS (command bodies untouched).
Run: `(cd "$WT" && python scripts/dev/testrun.py file tests/commands/test_command_error_logging.py)` → PASS (`except ValueError`, not `except Exception`, so the traceback rule does not apply).

- [ ] **Step 5: Commit**

```bash
git -C "$WT" add swingbot/commands/account.py tests/commands/parity_cases/account.py tests/commands/test_account_handlers_validation.py
git -C "$WT" commit -m "fix(account): handlers reply with the validator's refusal; show stored -> used risk (v187 D2)"
```

