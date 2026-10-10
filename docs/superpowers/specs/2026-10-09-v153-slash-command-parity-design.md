# v153 — Slash command parity through shared handlers

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot minor — every Discord user meets a different command surface:
22 new top-level slash commands appear in the client's `/` picker, and every
`!` command now answers with a one-line nudge to its `/` twin. Someone who
used the bot yesterday sees new commands and a new habit being asked of them,
which is the shape of a minor (`working-conventions.md` § The three levels),
even though no command's result changes. No admin UI change. (Bot minor
confirmed by the staff-engineer panel.)
**Edge:** none (integrity) — no plan, fill, stop, close or alert changes;
the same handlers answer through a second surface.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer
**Status:** spec written 2026-10-09; split out of v152 (former D4) per partner so it deploys and rolls back alone; panel review applied 2026-10-09; plan `docs/superpowers/plans/2026-10-10-v153-slash-command-parity_0-index.md` written 2026-10-10 (22 tasks, 9 files).

Parent: v152 (`docs/superpowers/specs/2026-10-09-v152-discord-notify-taken-cooldown-slash-design.md`),
which keeps D1–D3 (notify, Following, cooldown) and links here from its
"What follows".

## Why

Two command surfaces disagree. `swingbot/commands/slash.py` registers 19
slash commands (`@bot.tree.command` at `slash.py:75`-`:465`); there are 39
top-level prefix commands plus 14 subcommands (table below). Of the 19, seven
carry their own copy of the prefix body (`/ping`, `/help`, `/confidence`,
`/strategies`, `/regime`, `/pnl` at `slash.py:75-162`; `/stop` at
`slash.py:248-256`), and **twelve** bridge into a prefix callback through
`commands.Context.from_interaction` — re-derived with
`git grep -n from_interaction swingbot/commands/slash.py`:

| Line | Slash command |
|---|---|
| `slash.py:184` | `/liveplans` |
| `slash.py:239` | `/check` |
| `slash.py:268` | `/ticker` |
| `slash.py:305` | `/backtest` |
| `slash.py:335` | `/backtestwatchlist` |
| `slash.py:356` | `/trades` |
| `slash.py:372` | `/performance` |
| `slash.py:406` | `/watchlist` |
| `slash.py:426` | `/top` |
| `slash.py:443` | `/stats` |
| `slash.py:456` | `/soak` |
| `slash.py:469` | `/lessons` |

(`slash.py:223` is a docstring mention, not a call.) 7 + 12 = 19. A fix to
one surface silently misses the other.

## Facts the design rests on (verified 2026-10-09)

- Slash commands are synced **globally** once per process start
  (`bot.tree.sync()` in `on_ready`, `swingbot/commands/scanning/loops.py:941`).
  `loops.py:935-937` sets `_ready_announcement_sent = True` **before** the
  sync, and a sync failure is only a WARNING (`loops.py:943-944`), so a
  failed sync is never retried in-process — only a restart (or the resync
  script below) re-syncs. Every restart re-syncs.
- `loops.py:941` is the only `tree.sync` call in the code base
  (`git grep -n "tree.sync" -- '*.py'`).
- The bot is one `commands.Bot` with prefix `!` (`swingbot/bot_core.py:35`);
  command modules register by import (`bot.py:45-56`).
- The admin process imports command modules too, for helpers:
  `swingbot/admin/api_v1/risk.py:280` imports `_collect_portfolio_state` from
  `swingbot.commands.growth` (defined `growth.py:102`), and
  `swingbot/admin/app.py:315` / `api_v1/system.py:419` import
  `swingbot.commands.scanning.runstate`, whose package `__init__`
  (`swingbot/commands/scanning/__init__.py:7`) imports `commands.py` and so
  registers its commands. Registering on `bot.tree` in the admin process is
  harmless — the admin never connects the bot and never syncs — but see
  task P below.
- `!help`/`/help` render `COMMANDS_BY_CATEGORY` (`swingbot/bot_core.py:79`).
- discord.py is pinned at 2.7.1 (`requirements.txt:22`).
- The only permission check on any command is `!killswitch`'s
  `@commands.has_permissions(administrator=True)` (`growth.py:90`;
  `git grep -n has_permissions swingbot/commands/`).
- Progress-message edits (`await msg.edit(...)` on a message the command
  sent) occur in `!scrapeall` (`data.py:156`, edits `:174`, `:212`, `:217`),
  `!plans` (`history.py:273`, edits `:279`-`:325`) and `!check`
  (`scanning/commands.py:153`-`:216`). `!backtest` (`backtest.py:229-255`)
  and `!download` (`data.py:48`) send several messages but never edit one.

## Shape

### The `Reply` contract (new `swingbot/commands/reply.py`)

A `Reply` protocol with two implementations, `CtxReply(ctx)` and
`InteractionReply(interaction)`. Pinned semantics:

| Member | `CtxReply` | `InteractionReply` |
|---|---|---|
| `await defer(ephemeral=False)` | no-op | `interaction.response.defer(thinking=True, ephemeral=...)` if the response is not done; no-op otherwise |
| `await send(content=None, embed=None, file=None, files=None, view=None, ephemeral=False)` → handle | `ctx.send(...)`; returns the `discord.Message`; `ephemeral` **ignored** (documented: a prefix reply is always a channel message, as today) | first call with no defer: `response.send_message(...)` then returns `await interaction.original_response()`; otherwise `followup.send(..., wait=True)` and returns the `WebhookMessage` |
| `await send_chunks(text, ephemeral=False)` | splits at 1900 chars (as `slash.py:63-68` does today), each chunk through `send` | same |
| handle `.edit(content=, embed=, view=, attachments=)` | `Message.edit` | `InteractionMessage.edit` / `WebhookMessage.edit` — same keyword set |
| `await send_error(text)` | `send(text)` and sets `reply.failed = True` | `send(text, ephemeral=True)` and sets `reply.failed = True` |

Every handler uses only this surface; a handler never touches `ctx` or
`interaction` directly. The returned handle is what progress-message
handlers (`!scrapeall`, `!plans`, `!check`) edit. A webhook handle stays
editable for 15 minutes (Discord's interaction-token lifetime); that limit
exists today for the bridged `/check` and is unchanged — a longer
`/scrapeall` loses its later progress edits, never its result, because the
handler's final summary goes through `send`, which the plan's task must
keep as a fresh `send` (not an edit) whenever the token may be stale.

### Handlers, twins and the tip line

Every command body moves into `async def handle_<name>(reply, <typed args>)`,
next to its prefix command in the same module. The prefix command parses
its arguments, calls the handler, then calls `send_prefix_tip(ctx, reply)`.
The slash twin, **defined in the same module**, calls the same handler.
`slash.py` keeps only shared choices and helpers (`slash.py:23-68`); its 19
commands move to their modules and onto handlers, ending the duplicated
bodies and every `Context.from_interaction` bridge.

**Tip line.** One tested helper in `reply.py`:
`prefix_tip(qualified_name, today) -> str | None` returns
`"Tip: this is now /<twin>"`, where `<twin>` comes **only** from the
`SLASH_TWIN` table (below) — no string is built anywhere else.
`send_prefix_tip(ctx, reply)` sends it, and skips it when the handler raised
or set `reply.failed` (an error answer is not followed by a nudge).

**Long-run cost (decided).** The prefix surface stays **by decision, with no
removal date** — v153 adds a surface, it retires nothing. The tip line
retires itself: `reply.py` holds `PREFIX_TIP_UNTIL`, a `date` constant set
by the plan's deploy task to deploy day + 90 days; after it `prefix_tip`
returns `None`. A date check, not a config key, so v153 stays "no schema, no
config key". Owner: the partner. Deleting the dead constant and helper is
folded into the next plan that touches `swingbot/commands/reply.py`.

*Hybrid commands considered, rejected:* `!check`, `!backtest`, `!plans`,
`!liveplans` take free-form `*args` that a hybrid command cannot expose as
typed slash options, and the existing twins already chose typed options.

### `SLASH_TWIN`

A complete dict in `reply.py`: every qualified prefix name (as
`bot.walk_commands()` yields it, e.g. `"trades clear history"`) → its slash
path (e.g. `"trades-clear-history"`, `"account balance"`,
`"watchlist add"` for a choice-dispatched action). The parity test and the
tip line both read it; nothing else maps names.

### Grouping and permissions

Discord forbids a command that is also a group, so a prefix group that runs
on its own maps to a `show` subcommand.

`/killswitch` mirrors `!killswitch`'s runtime check, not just its visibility:
`@app_commands.default_permissions(administrator=True)` (hides it from
non-admins in the picker), **plus**
`@app_commands.checks.has_permissions(administrator=True)` (enforced at
invocation, as `growth.py:90` enforces for the prefix) **plus**
`@app_commands.guild_only()` (no DMs, where no administrator permission
exists). `!killswitch` is the only command with a permission check
(Facts), so it is the only admin-only twin; every other twin keeps the
prefix command's (absent) check — parity, not a new policy.

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
| `!killswitch` | `growth.py:89` | `/killswitch` (admin, guild-only) | new |
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

**The 19 existing slash commands keep their exact name, description and
options.** Moving them changes no sync payload, so a rollback re-syncs an
identical definition for them and users see no flip on those 19.

**`/trades-clear` naming.** `/trades` already exists as a plain command with
options (`slash.py:344`) and a command cannot also be a group, so the clear
subcommands become hyphenated top-level names, `/trades-clear` and
`/trades-clear-history`, rather than turning `/trades` into a group (which
would change an existing command's invocation). Both keep the prefix
command's behaviour and (absent) permission check.

**`/watchlist`** keeps its choice-dispatched shape (one command, an `action`
choice, `slash.py:384-415`). Its guard — `add`/`remove` need a ticker
(`slash.py:401-403`) — moves into the shared `handle_watchlist(reply,
action, ticker)`, so both surfaces answer a missing ticker with the same
`send_error` text; the prefix `add`/`remove` subcommands take
`ticker: str = None` so the handler, not discord.py's
`MissingRequiredArgument`, answers. The `if/elif` dispatch
(`slash.py:408-415`) becomes a dict of action → handler; an action outside
the dict answers `send_error` naming the valid actions.

**New top-level names:** 22 (`/account`, `/trade` count once each as
groups). After v153: 41, plus v152's `/notify` = 42, under Discord's 100
global commands. `/notify` is slash-only; if v152 has landed, it moves out of
`slash.py` into `swingbot/commands/notify.py` with its handler, unchanged.

**Help.** `COMMANDS_BY_CATEGORY` (`bot_core.py:79`) lists the slash form
first, the prefix form after it.

## Tests

### Reply-parity harness (one, parametrised)

New `tests/commands/test_reply_parity.py`, offline (no gateway, no HTTP).
Fakes: `FakeContext` (`send` records the call and returns a `FakeMessage`
that records `edit` calls) and `FakeInteraction` (`response.send_message`,
`response.defer`, `response.is_done()`, `followup.send(wait=True)` returning
a `FakeWebhookMessage`, `original_response()`), both recording into one
normalised event list: `(kind, content, embed.to_dict(), file names, view
type, ephemeral)`.

Parametrisation: **every `handle_*` × {`CtxReply`, `InteractionReply`}**,
each handler with one canned argument set and its data seams stubbed.
Assertions per handler:

- the same sequence of content / embed / file / view on both surfaces
  (ephemeral excluded from the comparison — it is a no-op on Context);
- the same error path: a forced failure produces the same `send_error` text
  and `reply.failed` on both.

Edge cases, each its own test:

- `defer()` then `send()` → the interaction goes through `followup.send`
  (`wait=True`), the context through `ctx.send`; both return an editable
  handle;
- a second `send()` after an initial `send_message` → `followup.send`;
- `ephemeral=True` on `CtxReply` → a plain channel message (documented
  no-op), and `defer()` on `CtxReply` sends nothing;
- `send_chunks` with a 4500-char text → three messages, each ≤ 1900 chars,
  on both surfaces;
- edit semantics, one test each for `!scrapeall`, `!plans` and `!check`:
  the handle returned by `send` receives the same ordered `edit` calls on
  both surfaces;
- multi-send, one test each for `!backtest` and `!download` (they send
  several messages and never edit — Facts);
- `/watchlist`: missing ticker for `add` and for `remove`, and an unknown
  action, give the same `send_error` text on both surfaces.

### Parity test

`tests/commands/test_slash_parity.py`, offline. It imports every module
`bot.py` imports (parsed from its `from swingbot.commands import` lines,
`bot.py:45-56`), so it walks exactly what the live bot registers.

1. **Mapping.** Every qualified name from `bot.walk_commands()` is a
   `SLASH_TWIN` key, and every `SLASH_TWIN` value is a command path in
   `bot.tree`, including group subcommands and `choice`-dispatched actions
   (`watchlist`).
2. **One body.** Every `handle_*` is called by exactly one prefix and one
   slash command (no duplicated bodies; no `Context.from_interaction` left
   in `swingbot/commands/`).
3. **Sync payload.** Build each top-level command's sync payload with
   `cmd.to_dict(bot.tree)` for `bot.tree.get_commands()` — the same JSON
   `tree.sync()` sends — and assert Discord's limits: name matches
   `^[-_a-z0-9]{1,32}$` (lowercase), description present and 1–100 chars on
   every command, subcommand and option, ≤ 25 options per command, ≤ 25
   choices per option, ≤ 25 subcommands per group, ≤ 100 top-level global
   commands, and required options before optional ones. A payload Discord
   would reject fails here instead of in `on_ready` at deploy, where
   `tree.sync()` failure is only a WARNING (`loops.py:943-944`), is not
   retried, and would leave the old set live.
4. **Tip helper.** `prefix_tip` returns the `SLASH_TWIN` text before
   `PREFIX_TIP_UNTIL` and `None` on and after it; `send_prefix_tip` sends
   nothing after a handler error.
5. **`/killswitch`.** `default_permissions.administrator` is set, the
   `has_permissions` check rejects a non-admin interaction, and the command
   is guild-only.

### Existing tests this supersedes

- `tests/commands/test_slash_commands.py` (21 lines, two tests):
  `test_slash_has_no_direct_colour` **stays** (`slash.py` still exists and
  must stay colour-free); `test_soak_slash_registered` is **deleted** —
  parity test 1 covers `/soak` and every other command.
- `tests/commands/test_stats_commands.py:348-389`: `BRIDGE_COMMANDS` and
  `test_six_bridge_commands_still_registered` are **deleted** (the bridges
  are gone; parity test 1 covers registration);
  `test_bot_entrypoint_still_imports_the_slash_module` is **deleted** —
  `slash.py` no longer registers commands, and parity test 1's import list
  is read from `bot.py` itself, which is the entry-point guard it stood for.

## Complexity

Every handler and command ends below 15. Each per-module task runs
`python -m radon cc -s -n C` over every module it touched (including
`reply.py` and `slash.py` where touched) and records the output in its
report. Moving a body never changes its behaviour.

## Production and rollback

- **No schema, no config key.** Deploy is the image alone; `on_ready`
  bulk-overwrites the global command set (`loops.py:941`) on every process
  start.
- **Global-sync propagation.** Global commands can take up to an hour to
  appear on every client; the prefix commands keep working throughout, and
  the tip line is harmless before the slash twin shows up. No guild-scoped
  sync is added.
- **Daily create limit — unverified, from memory, not a plan input.** A
  Discord cap of about 200 application-command creates per day is
  remembered, not checked against current Discord documentation. No plan
  step rests on it: the deploy step does not count syncs, and the signal of
  any rejected sync, whatever the cause, is the WARNING at `loops.py:944`,
  checked after every deploy and rollback. Restarts also re-sync
  (`loops.py:941`), so a restart loop multiplies syncs.
- **Rollback.** Image-only: the previous image syncs its own set on start,
  removing the 22. Nothing persisted changes, so `rollback_to.sh` is never
  needed for v153 alone. Independent of v152: either may roll back without
  the other.
- **Rollback remedy — resync script.** Because a failed sync is not retried
  in-process (Facts), a rollback whose sync logs the WARNING leaves the 22
  v153 commands registered against an image that no longer handles them.
  New `scripts/ops/resync_slash_commands.py` (committed in this repo, so it
  ships in the image via `COPY . .`) imports the command modules `bot.py`
  imports, logs in with the bot token without opening the gateway, and calls
  `bot.tree.sync()` — bulk-overwriting the global set with **the running
  image's** commands — printing the synced count. Run on production:
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/resync_slash_commands.py"`.
  It is idempotent; a restart (`docker compose restart bot`) is the
  fallback. The plan's task confirms against discord.py 2.7.1's source that
  `login()` sets the application id `tree.sync()` needs.
- **What users see after a rollback, during propagation (up to an hour).**
  Clients may still list the 22 v153 commands; invoking one gets Discord's
  "outdated command" notice or "The application did not respond", and the
  previous image logs an unknown-command error — no state changes. The 19
  existing commands behave as before (identical definitions). Every `!`
  command works throughout, without the tip line.

## What this does not do

Retire prefix commands (kept by decision, no removal date); add permission
policy beyond parity (only `/killswitch` maps its existing admin check);
change any command's output beyond the tip line and the `/watchlist`
missing-ticker text on the prefix surface; guild-scoped sync.

## Parallelisation

- **Sequential first — R:** add `swingbot/commands/reply.py` only
  (`Reply`, `CtxReply`, `InteractionReply`, `SLASH_TWIN`, `prefix_tip`,
  `send_prefix_tip`, `PREFIX_TIP_UNTIL`) with its harness edge-case tests.
  `slash.py` is **not** touched in R. Every module task consumes `Reply`.
- **Sequential — P (before the `growth` task):** move
  `_collect_portfolio_state` (`growth.py:102`) out of the command module to
  `swingbot/core/edge/portfolio_state.py` as `collect_portfolio_state`,
  unchanged in behaviour; update its callers — `growth.py:219`,
  `swingbot/admin/api_v1/risk.py:280`, `tests/edge/test_edge_heat.py:96`
  and the monkeypatch target at `tests/admin/test_api_v1_dashboard.py:241-247`.
  The admin process then no longer imports `swingbot.commands.growth`. (Its
  `swingbot.commands.scanning.runstate` import still registers the scanning
  commands on an unsynced tree — harmless, Facts.)
- **Module tasks — one per command module**, each moving its bodies into
  handlers, adding its slash twins, adding its rows to the reply-parity
  harness, and, **in the same commit**, deleting from `slash.py` the blocks
  of any slash command it now owns — registering a name twice raises
  `CommandAlreadyRegistered` at import, and deleting first would unregister
  it, so the move is atomic and no command is ever missing.
  - **Group 1 (parallel, after R):** `account`, `data`, `growth` (after P),
    `history` — they own no existing slash command and never touch
    `slash.py`. Disjoint files.
  - **Sequential (after R, one at a time — all edit `slash.py`):** `info`,
    `trades`, `plans`, `backtest`, `watchlist`, `stats`,
    `scanning/commands`. `stats.py` waits for v152's D2 task if v152 is in
    flight (both touch the `!top` panel, `stats.py:121`).
- **Sequential edges:** `/notify` move (if v152 landed) after R; the
  `COMMANDS_BY_CATEGORY` edit (`bot_core.py`) after every module task; the
  parity test, the superseded-test deletions and the resync script after
  every module task.
- The full suite last.

## Panel review

2026-10-09, `staff-engineer` and `senior-engineer`; every finding accepted.

- staff-engineer: [BLOCKING] rollback remedy — `scripts/ops/resync_slash_commands.py` bulk-overwrites the global set to the running image's commands, run via `ssh-hetzner.sh` + `docker compose exec -T bot`; `loops.py:935-937` sets `_ready_announcement_sent` before the sync so a failed sync is never retried in-process; what users see during post-rollback propagation stated -- applied
- staff-engineer: 200/day create cap marked unverified, from memory, not a plan input; deploy step no longer rests on it; restarts also re-sync (`loops.py:941`) -- applied
- staff-engineer: `/killswitch` gets runtime `app_commands.checks.has_permissions(administrator=True)` and `guild_only()` on top of `default_permissions`, matching `growth.py:90`; verified it is the only admin-only command -- applied
- staff-engineer: admin imports `swingbot.commands.growth` (`risk.py:280`) — chose the move: task P relocates `_collect_portfolio_state` to `swingbot/core/edge/portfolio_state.py`; noted the remaining `scanning.runstate` import registers harmlessly (admin never syncs) -- applied
- staff-engineer: bot minor bump confirmed (note in header) -- applied
- staff-engineer: long-run cost — prefix surface stays by decision, no removal date; tip retires after 90 days via a `PREFIX_TIP_UNTIL` date check (no config key), owner the partner -- applied
- staff-engineer: hand-off to senior-engineer -- applied
- senior-engineer: [BLOCKING] one parametrised harness `tests/commands/test_reply_parity.py`: every handler × {`CtxReply`, `InteractionReply`} with fake Context/Interaction, same content/embed/file and error path, edge cases defer-then-send, followup after send, ephemeral/defer no-op on Context, `send_chunks` over 2000 chars -- applied
- senior-engineer: [BLOCKING] `Reply` contract pinned (handle types, `original_response`/`followup.send(wait=True)`, Context no-ops, identical `edit`); edit tests target the handlers that actually edit — `!scrapeall`, `!plans`, `!check` — since `!backtest`/`!download` never edit (verified), which get multi-send tests instead -- applied
- senior-engineer: [BLOCKING] bridge inventory re-derived with `git grep`: **12** `from_interaction` call sites (was 7), plus 7 self-bodied commands = 19 -- applied
- senior-engineer: `tests/commands/test_slash_commands.py` checked: colour test stays, `/soak` registration test deleted; `test_stats_commands.py:348-389` bridge/entry-point tests deleted as superseded -- applied
- senior-engineer: radon over touched modules per task; `/watchlist` guard (`slash.py:401-403`) moves into the shared handler; tests for unknown action and missing ticker -- applied
- senior-engineer: tip text from the complete `SLASH_TWIN` table only, skipped on handler error, one tested helper -- applied
- senior-engineer: ordering — R adds `reply.py` only; each module task removes its own `slash.py` blocks in the same commit so no command is ever unregistered (or double-registered); `/watchlist` keeps its choice-dispatched shape -- applied
