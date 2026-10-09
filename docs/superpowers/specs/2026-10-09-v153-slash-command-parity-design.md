# v153 — Slash command parity through shared handlers

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot minor — every Discord user meets a different command surface:
22 new top-level slash commands appear in the client's `/` picker, and every
`!` command now answers with a one-line nudge to its `/` twin. Someone who
used the bot yesterday sees new commands and a new habit being asked of them,
which is the shape of a minor (`working-conventions.md` § The three levels),
even though no command's result changes. No admin UI change.
**Edge:** none (integrity) — no plan, fill, stop, close or alert changes;
the same handlers answer through a second surface.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer
**Status:** spec written 2026-10-09; split out of v152 (former D4) per partner so it deploys and rolls back alone; no plan yet.

Parent: v152 (`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`),
which keeps D1–D3 (notify, Following, cooldown) and links here from its
"What follows".

## Why

Two command surfaces disagree. `swingbot/commands/slash.py` registers 19
slash commands (`@bot.tree.command` at `slash.py:75`-`:465`); there are 39
top-level prefix commands plus 14 subcommands (table below). Three slash
commands re-implement their prefix twin's body (`/strategies`, `/regime`,
`/pnl`, `slash.py:112-166`), and seven bridge into a prefix callback through
`commands.Context.from_interaction` (`slash.py:184`, `:239`, `:268`, `:305`,
`:335`, `:356`, `:406`). A fix to one surface silently misses the other.

## Facts the design rests on (verified 2026-10-09)

- Slash commands are synced **globally** once per process start
  (`bot.tree.sync()` in `on_ready`, `swingbot/commands/scanning/loops.py:941`),
  guarded so a reconnect does not re-sync.
- The bot is one `commands.Bot` with prefix `!` (`swingbot/bot_core.py:35`);
  command modules register by import (`bot.py:42`).
- `!help`/`/help` render `COMMANDS_BY_CATEGORY` (`swingbot/bot_core.py:79`).
- discord.py is pinned at 2.7.1 (`requirements.txt:22`).

## Shape

A `Reply` protocol in new `swingbot/commands/reply.py` — `defer()`,
`send(content=, embed=, file=, view=, ephemeral=)` returning an editable
message, `send_chunks(text)` — with `CtxReply` and `InteractionReply`. Every
command body moves into `async def handle_<name>(reply, <typed args>)`, next
to its prefix command in the same module. The prefix command parses its
arguments, calls the handler, then sends one line: **`Tip: this is now
/<twin>`**. The slash twin, **defined in the same module**, calls the same
handler. `slash.py` keeps only shared choices and helpers (`slash.py:23-74`);
its 19 commands move to their modules and onto handlers, ending the
duplicated bodies and every `Context.from_interaction` bridge.

*Hybrid commands considered, rejected:* `!check`, `!backtest`, `!plans`,
`!liveplans` take free-form `*args` that a hybrid command cannot expose as
typed slash options, and the existing twins already chose typed options.

**Grouping.** Discord forbids a command that is also a group, so a prefix
group that runs on its own maps to a `show` subcommand. Admin-only
`!killswitch` (`growth.py:89`) gets
`app_commands.default_permissions(administrator=True)`; every other twin keeps
the prefix command's (absent) permission check — parity, not a new policy.

| Prefix | Defined | Slash twin | Status |
|---|---|---|---|
| `!account` | `account.py:15` | `/account show` | new |
| `!account balance\|risk\|maxpositions\|sizing\|positionpct\|maxpositionpct\|maxposition\|maxrisk` | `account.py:39-120` | `/account <same>` | new (8) |
| `!backtest` | `backtest.py:221` | `/backtest` | exists |
| `!backtestwatchlist` | `backtest.py:256` | `/backtestwatchlist` | exists |
| `!charts` | `data.py:19` | `/charts` | new |
| `!download` | `data.py:48` | `/download` | new |
| `!cached` | `data.py:90` | `/cached` | new |
| `!scrapeall` | `data.py:129` | `/scrapeall` | new |
| `!growth` | `growth.py:66` | `/growth` | new |
| `!killswitch` | `growth.py:89` | `/killswitch` (admin) | new |
| `!portfolio` | `growth.py:216` | `/portfolio` | new |
| `!plans` | `history.py:250` | `/plans` | new |
| `!strategies` | `info.py:40` | `/strategies` | exists |
| `!confidence` | `info.py:53` | `/confidence` | exists |
| `!ticker` | `info.py:58` | `/ticker` | exists |
| `!strategycharts` | `info.py:128` | `/strategycharts` | new |
| `!regime` | `info.py:176` | `/regime` | exists |
| `!ping` | `info.py:190` | `/ping` | exists |
| `!commands` (alias `!help`) | `info.py:195` | `/help` | exists |
| `!liveplans` | `plans.py:164` | `/liveplans` | exists |
| `!recap` | `scanning/commands.py:22` | `/recap` | new |
| `!check` | `scanning/commands.py:48` | `/check` | exists |
| `!session` | `scanning/commands.py:297` | `/session` | new |
| `!status` | `scanning/commands.py:312` | `/status` | new |
| `!pause` | `scanning/commands.py:334` | `/pause` | new |
| `!resume` | `scanning/commands.py:349` | `/resume` | new |
| `!stop` | `scanning/commands.py:361` | `/stop` | exists |
| `!soak` | `stats.py:40` | `/soak` | exists |
| `!top` | `stats.py:108` | `/top` | exists |
| `!stats` | `stats.py:204` | `/stats` | exists |
| `!lessons` | `stats.py:282` | `/lessons` | exists |
| `!calibration` | `stats.py:328` | `/calibration` | new |
| `!journal` | `stats.py:376` | `/journal` | new |
| `!trades` | `trades.py:167` | `/trades` | exists |
| `!trades clear` | `trades.py:188` | `/trades-clear` | new |
| `!trades clear history` | `trades.py:196` | `/trades-clear-history` | new |
| `!trade` | `trades.py:311` | `/trade show` | new |
| `!trade delete` | `trades.py:329` | `/trade delete` | new |
| `!tradecharts` | `trades.py:338` | `/tradecharts` | new |
| `!performance` | `trades.py:385` | `/performance` | exists |
| `!pnl` | `trades.py:423` | `/pnl` | exists |
| `!summary` | `trades.py:469` | `/summary` | new |
| `!watchlist` | `watchlist.py:13` | `/watchlist` (action `show`) | exists |
| `!watchlist add\|remove\|clear` | `watchlist.py:19-47` | `/watchlist` action `add\|remove\|clear` | exists (3) |

**`/trades-clear` naming.** `/trades` already exists as a plain command with
options (`slash.py:344`) and a command cannot also be a group, so the clear
subcommands become hyphenated top-level names, `/trades-clear` and
`/trades-clear-history`, rather than turning `/trades` into a group (which
would change an existing command's invocation). Both keep the prefix
command's behaviour and (absent) permission check.

**New top-level names:** 22 (`/account`, `/trade` count once each as
groups). After v153: 41, plus v152's `/notify` = 42, under Discord's 100
global commands. `/notify` is slash-only; if v152 has landed, it moves out of
`slash.py` into `swingbot/commands/notify.py` with its handler, unchanged.

**Help.** `COMMANDS_BY_CATEGORY` (`bot_core.py:79`) lists the slash form
first, the prefix form after it.

## Parity test

`tests/commands/test_slash_parity.py`, offline (no gateway, no HTTP):

1. **Mapping.** Walk `bot.walk_commands()` and assert every qualified prefix
   name maps — through one explicit `SLASH_TWIN` override dict, identity
   otherwise — to a command path in `bot.tree`, including group subcommands
   and `choice`-dispatched actions (`watchlist`).
2. **One body.** Every `handle_*` is called by exactly one prefix and one
   slash command (no duplicated bodies; no `Context.from_interaction` left in
   `swingbot/commands/`).
3. **Sync payload (staff-engineer #6).** Build each top-level command's sync
   payload with `cmd.to_dict(bot.tree)` for `bot.tree.get_commands()` — the
   same JSON `tree.sync()` sends — and assert Discord's limits: name matches
   `^[-_a-z0-9]{1,32}$` (lowercase), description present and 1–100 chars on
   every command, subcommand and option, ≤ 25 options per command, ≤ 25
   choices per option, ≤ 25 subcommands per group, ≤ 100 top-level global
   commands, and required options before optional ones. A payload Discord
   would reject fails here instead of in `on_ready` at deploy, where
   `tree.sync()` failure is only a WARNING (`loops.py:943-944`) and would
   leave the old set live.

Plus one test per moved handler through both `Reply` implementations, the
prefix hint line, and `/killswitch` default permissions.

## Complexity

Every handler and command ends below 15 (`radon cc -s -n C`). The
`/watchlist` action dispatch (`slash.py:408-415`, an `if/elif` chain today)
becomes a dict of action → handler. Moving a body never changes its
behaviour.

## Production and rollback

- **No schema, no config key.** Deploy is the image alone; `on_ready`
  bulk-overwrites the global command set (`loops.py:941`).
- **Global-sync propagation.** Global commands can take up to an hour to
  appear on every client; the prefix commands keep working throughout, and
  the hint line is harmless before the slash twin shows up. No guild-scoped
  sync is added.
- **Daily create limit.** Discord caps application-command *creates* at 200
  per day. A forward deploy creates 22 new top-level commands; a rollback
  deletes them (deletes are not capped) and a re-deploy creates the same 22
  again — ~44 creates for one forward/rollback/forward cycle, so at most four
  such cycles fit in a day. A fifth sync that day is rejected; the plan's
  deploy step notes this and the sync WARNING (`loops.py:944`) is the signal.
- **Rollback.** Image-only: the previous image syncs its own set on start,
  removing the 22. Nothing persisted changes, so `rollback_to.sh` is never
  needed for v153 alone. Independent of v152: either may roll back without
  the other.

## What this does not do

Retire prefix commands; add permission policy beyond parity (only
`/killswitch` maps its existing admin check); change any command's output;
guild-scoped sync.

## Parallelisation

- **Sequential first — R:** add `reply.py` (`Reply`, `CtxReply`,
  `InteractionReply`) and slim `slash.py` to shared choices and helpers.
  Every module task consumes `Reply`.
- **Group 1 (parallel, after R):** one task per command module — `account`,
  `backtest`, `data`, `growth`, `history`, `info`, `plans`, `stats`, `trades`,
  `watchlist`, `scanning/commands` — each moving its bodies into handlers and
  adding its slash twins. Disjoint files. `stats.py` waits for v152's D2 task
  if v152 is in flight (both touch the `!top` panel, `stats.py:121`).
- **Sequential edges:** `/notify` move (if v152 landed) after R; the
  `COMMANDS_BY_CATEGORY` edit (`bot_core.py`) after every module task; the
  parity test after every module task.
- The full suite last.
