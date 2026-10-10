# v153 Slash command parity through shared handlers. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief SP7` or `grep -n "^### Task SP7:" -A 260 docs/superpowers/plans/2026-10-10-v153-slash-command-parity_*.md`.

**Spec:** `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md`
**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Brief:** `.superpowers/briefs/2026-10-10-v153-slash-command-parity.md` (its "Controller decisions" section is binding and is restated under Global Constraints)

**Goal:** every `!` command body moves into one `async def handle_<name>(reply, <typed args>)` next to its prefix command. The prefix command and a slash twin defined in the same module both call that handler through a `Reply` (`CtxReply` / `InteractionReply`). `slash.py` keeps only the shared choice lists, plus a new `bot.tree.error` handler. That ends the seven duplicated bodies and all twelve `Context.from_interaction` bridges. 22 new top-level slash commands appear, for 41 in total (42 if v152's `/notify` has landed). Each `!` command answers with a one-line `Tip: this is now /<twin>` until `PREFIX_TIP_UNTIL`. A parity test pins the prefix-to-slash mapping, the one-body rule and Discord's sync-payload limits. A resync script is the rollback remedy.

**Architecture:**
- **New `swingbot/commands/reply.py`.** It holds the `Reply` protocol with its two implementations, the complete `SLASH_TWIN` table, `prefix_tip` / `send_prefix_tip` and `PREFIX_TIP_UNTIL`. Handlers touch only `Reply`, never `ctx` or `interaction`.
- **Module tasks.** Each module task moves its bodies into handlers, adds its twins, and adds its cases to the parametrised reply-parity harness. In the same task it deletes from `slash.py` the blocks of any slash command it now owns, so no name is ever registered twice or missing.
- **New `swingbot/core/edge/portfolio_state.py`.** It takes `_collect_portfolio_state` out of a command module, so the admin process no longer imports `swingbot.commands.growth`.
- **New `swingbot/commands/modules.py`.** It parses `bot.py`'s command-module imports and is shared by the parity test and `scripts/ops/resync_slash_commands.py`.

**Tech Stack:** Python 3.11, discord.py 2.7.1 (`app_commands`), pytest via `scripts/dev/testrun.py` (tests are `asyncio.run(...)`-driven, no pytest-asyncio), radon, `ast`.

## Progress

Not started. Update this block when a phase closes.

## Where to work

- **Branch and worktree:** `2026-10-10-v153-slash-command-parity`, at `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v153-slash-command-parity` (written `$WT` below). The main tree is `$R` = `/home/user/Discord-Bot`. SP1 Step 0 creates the worktree with the `worktree-lifecycle` skill. Name it in every subagent dispatch.
- **Never `cd`.** Use absolute paths and `git -C $WT`. Run `python $WT/scripts/dev/testrun.py file tests/...` against `$WT`.
- **discord.py must be installed** where tests run. The cloud sandbox lacks it (brief, Controller decision 8). The plan does not change for that; implementers run on a machine that has it.
- **This plan is committed on `main`.** Only the implementation is branched. Each task commits on the branch.
- **The bump (`bot` minor) is applied at close-out (`/close-out`)**, after SP22 is green. No task edits `VERSION.json`.
- **v152 is NOT merged on this branch** (brief §0.1). Its edges are written as "if v152 landed" checks: SP4 (`/notify` move), SP15 (`stats.py` `!top` panel overlap) and SP18 (count 41 vs 42).

## Global Constraints

- **The `Reply` contract (binding on every task; created by SP1).**
  - `Reply` is a `typing.Protocol` with these members:
    - `failed: bool`
    - read-only properties `author`, `channel` and `stale: bool`
    - `async defer(ephemeral: bool = False) -> None`
    - `async send(content: str | None = None, *, embed=None, file=None, files=None, view=None, ephemeral: bool = False, silent: bool = False)`, returning a handle
    - `async send_chunks(text: str, *, ephemeral: bool = False) -> None`, which splits at `CHUNK = 1900` chars and sends each chunk through `send`
    - `async send_error(text: str, *, ephemeral: bool = True)`, which sends and then sets `failed = True`
  - **Kwargs.** Both implementations pass **only non-`None` kwargs** on to discord.py. Passing `view=None` or `file=None` to `Webhook.send` raises in discord.py.
  - **`CtxReply(ctx)`:**
    - `defer` is a no-op and `ephemeral` is ignored.
    - `send` calls `ctx.send(content, **kw)` with `content` **positional** when it is not `None`, otherwise `ctx.send(**kw)`. It returns the `discord.Message`.
    - `author` is `ctx.author`, `channel` is `ctx.channel`, and `stale` is always `False`.
  - **`InteractionReply(interaction, *, clock=time.monotonic)`:**
    - `defer` calls `interaction.response.defer(thinking=True, ephemeral=...)` when `not interaction.response.is_done()`, otherwise it does nothing.
    - On a first `send` while the response is not done, `send` calls `response.send_message(...)` and then returns `await interaction.original_response()`.
    - Otherwise `send` calls `followup.send(..., wait=True)` and returns the `WebhookMessage`.
    - `author` is `interaction.user` and `channel` is `interaction.channel`.
    - `stale` is `clock() - started >= TOKEN_LIFETIME_S` (`= 14 * 60`). Once stale, `send` posts with `interaction.channel.send(...)` instead, with `ephemeral` dropped. This is what makes the spec's line "a longer `/scrapeall` loses its later progress edits, never its result" true: follow-ups use the same 15-minute token.
- **The prefix pattern** (every prefix command):
  ```python
  @bot.command(name="ping")
  async def ping_cmd(ctx):
      reply = CtxReply(ctx)
      await handle_ping(reply)
      await send_prefix_tip(ctx, reply)
  ```
  The prefix command parses its free-form `*args`, using the module's existing parser, into the handler's typed args.
- **The slash twin pattern:** `await handle_<name>(InteractionReply(interaction), <args from options>)`. A `Choice` option is unwrapped (`opt.value if opt else <default>`) before the call.
- **`send_prefix_tip(ctx, reply)`:**
  - It reads `qualified_name` via `getattr(getattr(ctx, "command", None), "qualified_name", None)`.
  - It sends nothing when that is not a `str` key of `SLASH_TWIN`, when `reply.failed` is set, or when `prefix_tip(...)` returns `None`.
  - Existing tests drive `.callback(ctx)` with a `MagicMock` ctx or a plain recorder. Those therefore get **no** tip, and only tests that build a real `commands.Context` see it.
  - `prefix_tip(qualified_name, today)` returns `f"Tip: this is now /{SLASH_TWIN[name]}"` while `today < PREFIX_TIP_UNTIL`.
- **Output rule: "Union, `!` body as base"** (Controller decision 1). Each handler starts from the `!` body and takes in the slash side's fixes:
  - `/strategies` lists the 11 strategies **and** keeps the `(needs N+ trading days of history)` note.
  - `/pnl` uses the `!pnl` table.
  - The help header reads ``Prefix: `!`  •  Slash: `/` ``.
  - `/stop` logs `(by %s)` with `reply.author`.
  - `/ticker`, `/backtest` and `/watchlist` upper-case the ticker.
  - `/watchlist` add/remove guard against a missing ticker.
  - `ephemeral=True` stays wherever the slash body had it; it is a no-op on `CtxReply`.
- **Every resulting `!` output change** (the spec's "no command's result changes" is amended by SP21):
  1. The `Tip: this is now /<twin>` line, sent after every successful `!` answer until `PREFIX_TIP_UNTIL`.
  2. `!strategies` lists 11 strategies instead of 6.
  3. `!help` / `!commands`: the header names both prefixes, and each row shows its slash form. Fields and embeds are split to stay within Discord's limits; the current "📊 Trades & performance" field is already 1116 chars, over the 1024 cap.
  4. A bare `!watchlist add|remove` answers `Please provide a ticker for add/remove actions.` instead of the `COMMAND_USAGE` hint.
  5. `!watchlist add aapl` stores `AAPL`. `add_ticker` used to receive the raw text.

  `!scrapeall` and `!check` deliver unchanged, because `CtxReply.stale` is always `False`.
- **Author and channel** (Controller decision 2). Handlers use `reply.author.id`, `reply.author` and `reply.channel.id`. Today's `ctx.author.id` uses are at `plans.py:181`, `stats.py:123` and `trades.py:184`; `ctx.author` at `scanning/commands.py:341,356,378`; `ctx.channel.id` at `scanning/commands.py:42`.
- **Alerts destination.** `_send_alerts`, `post_short_universe` and `send_then_short` (`scanning/alerts.py:220,291,308`) take `reply` as `destination`. They call `destination.send(content=?, embed=, file=?, view=?, silent=)`, which is why `Reply.send` takes `silent`.
- **Tests that assert the only or last `ctx.send`** (Controller decision 3) are updated in the same task as their module:
  - `test_growth_command.py` (SP7)
  - `test_command_error_logging.py` (SP9 `ticker`, SP13 `backtestwatchlist`)
  - `test_plans_board.py:175-179`: `kwargs["content"]` becomes positional `args[0]` (SP12)
  - `test_stats_commands.py:228-244` and `tests/admin/test_v144_pooled_readers.py:57` (SP15)
  - `test_commands_check.py` (SP16: `_check_historical(CtxReply(ctx), ...)`)
- **Registration tests stay green until SP19 deletes them.** These are `test_new_slash_commands_registered_on_tree`, `test_six_bridge_commands_still_registered` and `test_soak_slash_registered`. Each sequential module task that moves one of their names out of `slash.py` adds `import swingbot.commands.<module>  # noqa: F401` next to their `import swingbot.commands.slash`. That applies to SP9 `info`, SP10 `trades`, SP12 `plans`, SP13 `backtest`, SP14 `watchlist` and SP15 `stats`.
- **The 19 existing slash commands keep their exact name, description and options.** Copy the decorators verbatim from `slash.py` when moving them.
- **Circular imports.** Twins import choice lists from `swingbot.commands.slash`. `slash.py` must never import a command module at top level. `slash.HORIZON_CHOICES` stays importable (`tests/market/test_v113_horizon_vocab.py:28-29`).
- **Complexity.** Every handler, prefix command and twin must be < 15. Legacy bodies at ≥ 15 are split into named helpers as they become handlers: `scrapeall_cmd` 18, `plans_cmd` 24, `ticker_cmd` 15, `summary_cmd` 52, `check_cmd` 23 and `_check_historical` 17. `_collect_portfolio_state` (22) moves unchanged. Each module task runs `python -m radon cc -s -n C <touched files>` and pastes the output into its report.
- **Line numbers:** use the brief's verified numbers, not the spec's. The sync is at `loops.py:1047`, the warning at `:1048-1049` and the guard at `:1041-1043`; `stats.py:41/110/123`.
- **Green means `0 failed` and `0 xfailed`.** Per task, run the narrow `python $WT/scripts/dev/testrun.py file <test>`. The full suite runs once, in SP22.

## Production and rollback (for the controller, after merge)

- **Deploy is the image alone.** There is no schema change and no config key. `on_ready` bulk-overwrites the global command set on every process start (`loops.py:1047`).
- **After deploy:**
  ```bash
  bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 10m bot | grep -E 'Synced [0-9]+ slash|Failed to sync slash'"
  ```
  Expect `Synced 41` (`42` if v152 landed). `Failed to sync` means the sync was rejected and is not retried in-process. Run the resync script.
- **Rollback** is image-only. After a rollback, run the same log check. If it shows the WARNING, run:
  ```bash
  bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/ops/resync_slash_commands.py"
  ```
  `docker compose restart bot` is the fallback. During propagation (up to an hour), clients may still list the 22 new commands. Every `!` command works throughout.
- **`PREFIX_TIP_UNTIL`** is pinned by SP21 to the planned deploy day + 90 days. If the deploy slips by more than a week, re-pin it in a one-line commit before deploying.

## Parallelisation

| Task | Files | Depends on | Why sequential / parallel |
|---|---|---|---|
| SP1 reply contract + harness | `reply.py`, `tests/commands/reply_harness.py`, `tests/commands/parity_cases/__init__.py`, `tests/commands/parity_cases/reply_selftest.py`, `tests/commands/test_reply_parity.py` | — | Every module task consumes `Reply`, `CtxReply`, `InteractionReply`, `send_prefix_tip` and the harness |
| SP2 `collect_portfolio_state` move (spec task P) | `core/edge/portfolio_state.py`, `growth.py`, `admin/api_v1/risk.py`, 2 tests, 4 comment mentions | — | Can run **in parallel with SP1 and SP3**. It must land before SP7, which rewrites `growth.py` |
| SP3 `bot.tree.error` handler | `slash.py`, `tests/commands/test_slash_error_handler.py` | — | Can run in parallel with SP1/SP2. It is the first link of the `slash.py` chain (SP3 → SP4 → SP9 → … → SP16) |
| SP4 `/notify` move (if v152 landed) | `slash.py`, `notify.py`, `bot.py` (only if landed) | SP1, SP3 | Edits `slash.py`. It needs `InteractionReply` |
| SP5 `account` | `account.py`, `parity_cases/account.py` | SP1 | **Group 1:** parallel with SP6/SP7/SP8 and with the `slash.py` chain (disjoint files) |
| SP6 `data` | `data.py`, `parity_cases/data.py`, `tests/commands/test_scrapeall_stale.py` | SP1 | Group 1 |
| SP7 `growth` | `growth.py`, `parity_cases/growth.py`, `tests/commands/test_growth_command.py` | SP1, SP2 | Group 1. It runs after SP2, which edits `growth.py` |
| SP8 `history` | `history.py`, `parity_cases/history.py` | SP1 | Group 1 |
| SP9 `info` | `info.py`, `slash.py`, `parity_cases/info.py`, `test_command_error_logging.py`, `test_stats_commands.py` | SP1, SP4 | `slash.py` chain. It moves `/ping` `/help` `/confidence` `/strategies` `/regime` `/ticker` |
| SP10 `trades` I: list, clear, trade, tradecharts | `trades.py`, `slash.py`, `parity_cases/trades.py`, `test_stats_commands.py` | SP9 | `slash.py` chain. It moves `/trades` |
| SP11 `trades` II: performance, pnl, summary | `trades.py`, `slash.py`, `parity_cases/trades.py` | SP10 | Same files as SP10. It moves `/performance` and `/pnl` |
| SP12 `plans` | `plans.py`, `slash.py`, `parity_cases/plans.py`, `test_plans_board.py`, `test_stats_commands.py` | SP11 | `slash.py` chain. It moves `/liveplans` |
| SP13 `backtest` | `backtest.py`, `slash.py`, `parity_cases/backtest.py`, `test_command_error_logging.py`, `test_stats_commands.py` | SP12 | `slash.py` chain. It moves `/backtest` and `/backtestwatchlist` |
| SP14 `watchlist` | `watchlist.py`, `slash.py`, `parity_cases/watchlist.py`, `test_stats_commands.py` | SP13 | `slash.py` chain. It moves `/watchlist` |
| SP15 `stats` | `stats.py`, `slash.py`, `parity_cases/stats.py`, `test_stats_commands.py`, `test_slash_commands.py`, `tests/admin/test_v144_pooled_readers.py` | SP14 (and v152 D2 if in flight) | `slash.py` chain. It moves `/top` `/stats` `/soak` `/lessons`. It waits for v152's D2 (same `!top` panel, `stats.py:121-123`) only if v152 is in flight |
| SP16 `scanning/commands` | `scanning/commands.py`, `slash.py`, `parity_cases/scanning.py`, `test_commands_check.py` | SP15 | `slash.py` chain. It moves `/check` and `/stop`. It is the last `slash.py` command move and leaves `slash.py` with choices plus the error handler |
| SP17 help catalog | `bot_core.py`, `info.py`, `tests/commands/test_help_catalog.py`, `test_stats_commands.py` | SP5–SP16 | Spec: the `COMMANDS_BY_CATEGORY` edit comes after every module task. It renders slash forms from `SLASH_TWIN` |
| SP18 parity test | `swingbot/commands/modules.py`, `tests/commands/test_slash_parity.py` | SP5–SP17 | Asserts the end state of every module |
| SP19 superseded tests | `test_slash_commands.py`, `test_stats_commands.py` | SP18 | Deletes what SP18 now covers |
| SP20 resync script | `scripts/ops/resync_slash_commands.py`, `tests/scripts/test_resync_slash_commands.py` | SP18 | Imports `swingbot.commands.modules` (SP18). It can run **in parallel with SP19** (disjoint files) |
| SP21 pin `PREFIX_TIP_UNTIL`, amend the spec | `reply.py`, spec file | SP20 | Deploy-day pin. It runs last before the suite |
| SP22 full suite | — | all | Final gate |

Recommended order: {SP1, SP2, SP3} (2 implementers at once), then SP4. After that come Group 1 {SP5, SP6, SP7, SP8} and the chain SP9 → SP16, with at most 2 implementers at once. Then SP17, SP18, {SP19, SP20}, SP21 and SP22.

## Task ledger

| Task | Title | Part | Model | Files (C = create, M = modify, D = delete lines) | Creates, consumed later |
|---|---|---|---|---|---|
| SP1 | `Reply` contract, `SLASH_TWIN`, tip helpers, reply-parity harness | 1 | sonnet | C `swingbot/commands/reply.py`, C `tests/commands/reply_harness.py`, C `tests/commands/parity_cases/__init__.py`, C `tests/commands/parity_cases/reply_selftest.py`, C `tests/commands/test_reply_parity.py` | `reply.py`: `CHUNK = 1900`, `TOKEN_LIFETIME_S = 14 * 60`, `PREFIX_TIP_UNTIL: datetime.date` (provisional `date(2027, 1, 8)`, re-pinned in SP21), `Reply` (Protocol), `CtxReply(ctx)`, `InteractionReply(interaction, *, clock=time.monotonic)`, `SLASH_TWIN: dict[str, str]` (all 53 qualified prefix names; see the table at the end of this index), `prefix_tip(qualified_name: str, today: datetime.date) -> str \| None`, `send_prefix_tip(ctx, reply) -> None` (today from `reply._today()`, a module function `_today() -> date` that tests monkeypatch). `reply_harness.py`: `Event = tuple[str, str \| None, dict \| None, tuple[str, ...], str \| None, bool]` (kind, content, embed dict, file names, view type name, ephemeral); `FakeMessage(events)` (`.edit(**kw)` records `("edit", …)`); `FakeContext(events, *, author_id=1, channel_id=10, qualified_name=None)`; `FakeInteraction(events, *, user_id=1, channel_id=10)` (`response.is_done()`, `response.send_message`, `response.defer`, `followup.send(wait=True)`, `original_response()`, `channel.send`, and `.calls: list[str]` of the raw method names); `ParityCase(id: str, handler: Callable, args: tuple = (), kwargs: dict = {}, stub: Callable[[pytest.MonkeyPatch], None] \| None = None, fail_stub: Callable[[pytest.MonkeyPatch], None] \| None = None, expect: str = "send")`, where `expect` is one of `"send"`, `"edit"`, `"multi_send"`, `"error"`; `run_both(case_or_call, monkeypatch) -> BothRun(ctx_events, inter_events, ctx_reply, inter_reply)`; `comparable(events) -> list` (drops `defer` events and the ephemeral field); `all_cases() -> list[ParityCase]` (imports every module in `tests.commands.parity_cases` and concatenates their `CASES`) |
| SP2 | Move `_collect_portfolio_state` to `core/edge/portfolio_state.py` (spec task P) | 1 | sonnet | C `swingbot/core/edge/portfolio_state.py`, M `swingbot/commands/growth.py`, M `swingbot/admin/api_v1/risk.py`, M `swingbot/admin/api_v1/dashboard.py` (comment), M `swingbot/core/tracking/retrospective.py` (comment), M `tests/edge/test_edge_heat.py`, M `tests/admin/test_api_v1_dashboard.py` | `swingbot.core.edge.portfolio_state.collect_portfolio_state() -> dict` (body unchanged). `growth.py` imports it under the same local name for `portfolio_command` |
| SP3 | `bot.tree.error` handler for app-command check failures | 1 | sonnet | M `swingbot/commands/slash.py`, C `tests/commands/test_slash_error_handler.py` | `slash.on_app_command_error(interaction, error)`, registered with `@bot.tree.error`. It answers `app_commands.MissingPermissions` with `"🚫 You don't have permission to run that command."` and `app_commands.NoPrivateMessage` with `"This command only works in a server."`, both ephemeral (`send_message` if not done, else `followup.send`). Everything else is logged with `log.exception` and re-raised |
| SP4 | `/notify` out of `slash.py` (only if v152 landed) | 1 | sonnet | M `swingbot/commands/slash.py`, C `swingbot/commands/notify.py`, M `bot.py`: **only if** `git grep -n 'name="notify"' -- swingbot/commands/slash.py` is non-empty; otherwise no file changes and a no-op note in `.superpowers/sdd/progress.md` | If landed: `notify.handle_notify(reply, ...)` (slash-only, `SLASH_ONLY = {"notify"}` consumed by SP18) |
| SP5 | `account`: handlers and the `/account` group | 2 | sonnet | M `swingbot/commands/account.py`, C `tests/commands/parity_cases/account.py` | `handle_account_show(reply)`, `handle_account_balance(reply, amount: float)`, `handle_account_risk(reply, pct: float)`, `handle_account_maxpositions(reply, n: int)`, `handle_account_sizing(reply, mode: str)`, `handle_account_positionpct(reply, pct: float)`, `handle_account_maxpositionpct(reply, pct: float)`, `handle_account_maxposition(reply, amount: float)`, `handle_account_maxrisk(reply, amount: float)`; `account_group = app_commands.Group(name="account", ...)` with subcommands `show balance risk maxpositions sizing positionpct maxpositionpct maxposition maxrisk` |
| SP6 | `data`: charts, download, cached, scrapeall | 2 | opus | M `swingbot/commands/data.py`, C `tests/commands/parity_cases/data.py`, C `tests/commands/test_scrapeall_stale.py` | `handle_charts(reply)`, `handle_download(reply, interval: str, ticker: str \| None = None)`, `handle_cached(reply)`, `handle_scrapeall(reply, mode: str = "cached")` (C18 is split below 15; the final summary is a fresh `send` when `reply.stale`); `/charts`, `/download`, `/cached`, `/scrapeall` |
| SP7 | `growth`: growth, killswitch, portfolio | 2 | sonnet | M `swingbot/commands/growth.py`, C `tests/commands/parity_cases/growth.py`, M `tests/commands/test_growth_command.py` | `handle_growth(reply, target: float = 10.0)`, `handle_killswitch(reply, action: str = "status")`, `handle_portfolio(reply)`; `/growth`, `/portfolio`, and `/killswitch` (action choices `status`/`on`/`off`, `@app_commands.default_permissions(administrator=True)`, `@app_commands.checks.has_permissions(administrator=True)`, `@app_commands.guild_only()`), function name `slash_killswitch` (read by SP18) |
| SP8 | `history`: `!plans` | 2 | opus | M `swingbot/commands/history.py`, C `tests/commands/parity_cases/history.py` | `handle_plans(reply, ticker: str \| None, horizon: str = "all", strategy: str = "all", date_from: str \| None = None, date_to: str \| None = None)` (D24 is split below 15; the progress handle is edited); `/plans` (ticker required; `from_date`, `to_date`, `horizon` = `HORIZON_CHOICES`, `strategy` = `STRATEGY_CHOICES`) |
| SP9 | `info`: strategies, confidence, ticker, strategycharts, regime, ping, help | 3 | opus | M `swingbot/commands/info.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/info.py`, M `tests/commands/test_command_error_logging.py`, M `tests/commands/test_stats_commands.py` | `handle_strategies(reply)`, `handle_confidence(reply)`, `handle_ticker(reply, ticker: str)` (C15 split), `handle_strategycharts(reply, ticker: str, horizon: str = "4w", direction: str = "bullish")`, `handle_regime(reply)`, `handle_ping(reply)`, `handle_help(reply)`; `info.HELP_DESCRIPTION = "Alerts only, never places trades. Prefix: \`!\`  •  Slash: \`/\`"` (SP17 consumes). `/strategycharts` is new; `/ping` `/help` `/confidence` `/strategies` `/regime` `/ticker` are moved |
| SP10 | `trades` I: trades, trades clear, clear history, trade, trade delete, tradecharts | 3 | sonnet | M `swingbot/commands/trades.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/trades.py`, M `tests/commands/test_stats_commands.py` | `handle_trades(reply, status: str = "all", per_page: int = DEFAULT_PER_PAGE)`, `handle_trades_clear(reply)`, `handle_trades_clear_history(reply)`, `handle_trade_show(reply, trade_id: str)`, `handle_trade_delete(reply, trade_id: str)`, `handle_tradecharts(reply, status: str = "open", limit: int = 5)`; `/trades` (moved), `/trades-clear`, `/trades-clear-history`, the `/trade` group (`show`, `delete`), `/tradecharts` |
| SP11 | `trades` II: performance, pnl, summary | 3 | opus | M `swingbot/commands/trades.py`, M `swingbot/commands/slash.py`, M `tests/commands/parity_cases/trades.py` | `handle_performance(reply, level: int \| None = None)`, `handle_pnl(reply)` (the `!pnl` table, through `send_chunks`), `handle_summary(reply)` (F52 split below 15); `/performance` and `/pnl` moved, `/summary` new; `slash._send_chunks` deleted (dead) |
| SP12 | `plans`: `!liveplans` | 3 | sonnet | M `swingbot/commands/plans.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/plans.py`, M `tests/commands/test_plans_board.py`, M `tests/commands/test_stats_commands.py` | `handle_liveplans(reply, status: str = "All", level: str = "All", badge: str = "All", ticker: str \| None = None)`; `/liveplans` moved |
| SP13 | `backtest`: backtest, backtestwatchlist | 4 | sonnet | M `swingbot/commands/backtest.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/backtest.py`, M `tests/commands/test_command_error_logging.py`, M `tests/commands/test_stats_commands.py` | `handle_backtest(reply, ticker: str, horizon: str = "all", strategy: str = "all", date_from: str \| None = None, date_to: str \| None = None, list_setups: bool = False)`, `handle_backtestwatchlist(reply, horizon: str = "all", strategy: str = "all", date_from: str \| None = None, date_to: str \| None = None)` (exact optional parameters = what `_parse_backtest_args` and today's prefix parsing yield; the part may add parameters but not rename these); `/backtest` and `/backtestwatchlist` moved |
| SP14 | `watchlist` | 4 | sonnet | M `swingbot/commands/watchlist.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/watchlist.py`, M `tests/commands/test_stats_commands.py` | `handle_watchlist(reply, action: str = "show", ticker: str \| None = None)`; `WATCHLIST_ACTIONS: dict[str, Callable]` (keys `show add remove clear`, private `_watchlist_<action>` values); `MISSING_TICKER = "Please provide a ticker for add/remove actions."`; prefix subcommands take `ticker: str = None`; `/watchlist` moved |
| SP15 | `stats`: soak, top, stats, lessons, calibration, journal | 4 | sonnet | M `swingbot/commands/stats.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/stats.py`, M `tests/commands/test_stats_commands.py`, M `tests/commands/test_slash_commands.py`, M `tests/admin/test_v144_pooled_readers.py` | `handle_soak(reply, strategy: str)`, `handle_top(reply, n: int \| None = None)`, `handle_stats(reply, period: str = "all")`, `handle_lessons(reply, arg: str = "5")`, `handle_calibration(reply)`, `handle_journal(reply, target: str, note: str \| None = None)`; `/soak` `/top` `/stats` `/lessons` moved, `/calibration` `/journal` new |
| SP16 | `scanning/commands`: recap, check, session, status, pause, resume, stop | 4 | opus | M `swingbot/commands/scanning/commands.py`, M `swingbot/commands/slash.py`, C `tests/commands/parity_cases/scanning.py`, M `tests/commands/test_commands_check.py` | `handle_recap(reply, date_arg: str = "")`, `handle_check(reply, horizon: str = "all", min_confluence: int \| None = None, date_from: str \| None = None, date_to: str \| None = None)` (D23 split), `_check_historical(reply, horizon, date_from, date_to)` (C17 split; same name), `handle_session(reply)`, `handle_status(reply)`, `handle_pause(reply)`, `handle_resume(reply)`, `handle_stop(reply)`; prefix name `check_cmd` kept (re-exported by `scanning/__init__.py`); `/check` and `/stop` moved, `/recap` `/session` `/status` `/pause` `/resume` new. Afterwards `slash.py` contains no `@bot.tree.command` |
| SP17 | Help catalog lists slash forms within Discord embed limits | 5 | sonnet | M `swingbot/bot_core.py`, M `swingbot/commands/info.py`, C `tests/commands/test_help_catalog.py`, M `tests/commands/test_stats_commands.py` | `info.help_line(usage: str, desc: str) -> str` (longest `SLASH_TWIN` key matching the usage's leading words → `` `!usage` · `/twin` — desc``) and `info.help_embeds() -> list[discord.Embed]` (fields ≤ 1024 chars split as `"<category> (cont.)"`, ≤ 25 fields and ≤ 6000 chars per embed). `COMMANDS_BY_CATEGORY` keeps `(usage, desc)` tuples, `!` form first |
| SP18 | Slash parity test and shared module list | 5 | sonnet | C `swingbot/commands/modules.py`, C `tests/commands/test_slash_parity.py` | `modules.BOT_PY: Path`, `modules.bot_command_modules(bot_py: Path = BOT_PY) -> list[str]` (dotted names parsed from `^from swingbot\.commands import (\w+)` lines), `modules.import_bot_command_modules(bot_py: Path = BOT_PY) -> list[ModuleType]` |
| SP19 | Delete superseded registration tests | 5 | haiku | M `tests/commands/test_slash_commands.py`, M `tests/commands/test_stats_commands.py` | — |
| SP20 | `scripts/ops/resync_slash_commands.py` rollback remedy | 5 | sonnet | C `scripts/ops/resync_slash_commands.py`, C `tests/scripts/test_resync_slash_commands.py` | `resync(bot, token: str) -> int`, `main() -> int` |
| SP21 | Pin `PREFIX_TIP_UNTIL` to deploy day + 90; amend the spec's output line | 5 | haiku | M `swingbot/commands/reply.py`, M `docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md` | — |
| SP22 | Full suite | 5 | haiku | — | — |

### `SLASH_TWIN` (SP1 writes it exactly; SP18 asserts it against `bot.walk_commands()` and `bot.tree`)

| Qualified prefix name | Slash path |
|---|---|
| `account` | `account show` |
| `account balance` / `risk` / `maxpositions` / `sizing` / `positionpct` / `maxpositionpct` / `maxposition` / `maxrisk` | `account <same>` (8 rows) |
| `backtest`, `backtestwatchlist`, `charts`, `download`, `cached`, `scrapeall`, `growth`, `killswitch`, `portfolio`, `plans`, `strategies`, `confidence`, `ticker`, `strategycharts`, `regime`, `ping`, `liveplans`, `recap`, `check`, `session`, `status`, `pause`, `resume`, `stop`, `soak`, `top`, `stats`, `lessons`, `calibration`, `journal`, `trades`, `tradecharts`, `performance`, `pnl`, `summary` | same name (35 rows) |
| `commands` | `help` |
| `trades clear` | `trades-clear` |
| `trades clear history` | `trades-clear-history` |
| `trade` | `trade show` |
| `trade delete` | `trade delete` |
| `watchlist` | `watchlist show` |
| `watchlist add` / `remove` / `clear` | `watchlist add` / `watchlist remove` / `watchlist clear` |

53 rows: 39 top-level and 14 subcommands. Slash paths with a space are either a group subcommand (`account`, `trade`) or a `/watchlist` `action` choice value. SP18 resolves `watchlist <x>` against the `action` option's choice values.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-10-v153-slash-command-parity_1-foundation.md` | SP1–SP4 | `Reply` contract and harness, task P, tree error handler, `/notify` check |
| 2 | `2026-10-10-v153-slash-command-parity_2-group1-modules.md` | SP5–SP7 | Group 1 (parallel): `account`, `data`, `growth` |
| 2b | `2026-10-10-v153-slash-command-parity_2b-history.md` | SP8 | Group 1 (parallel): `history` (split from part 2 for the 1500-line cap) |
| 3 | `2026-10-10-v153-slash-command-parity_3-info-trades-plans.md` | SP9–SP10 | `slash.py` chain I: `info`, `trades` I |
| 3b | `2026-10-10-v153-slash-command-parity_3b-trades2-plans.md` | SP11–SP12 | `slash.py` chain I (continued): `trades` II, `plans` (split from part 3 for the 1500-line cap) |
| 4 | `2026-10-10-v153-slash-command-parity_4-backtest-watchlist-stats-scanning.md` | SP13–SP16 | `slash.py` chain II: `backtest`, `watchlist`, `stats`, `scanning/commands` |
| 5 | `2026-10-10-v153-slash-command-parity_5-catalog-parity-resync-suite.md` | SP17–SP22 | Help catalog, parity test, superseded tests, resync script, tip date, full suite |
