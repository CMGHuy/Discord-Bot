# v152 — Discord: trade-event notifications, Taken button, symbol cooldown, slash parity

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot minor, ui patch — a Discord user meets a different bot: a new
channel that pings them by name about their plans, a persistent `✅ Taken`
button on every alert, fewer repeat posts for one symbol, and every `!`
command now answering with a nudge to its `/` twin. Someone who used the bot
yesterday has to look at it anew, which is the shape of a minor
(`working-conventions.md` § The three levels). The admin UI gains one
analytics breakdown option (`taken`): a new control, a patch.
**Edge:** none (integrity) — nothing here changes which plans are built,
filled, stopped or closed. D3 suppresses only the Discord *post*: the plan is
still created, persisted and managed, and its trade still logged, so the
measured book is unchanged. D2 adds a dimension that splits the existing book;
it does not change it.
**Screen:** exempt (integrity)
**Panel:** veteran-trader, financial-advisor, staff-engineer
**Status:** spec written 2026-10-09; design approved section by section; no plan yet.

## Why

Four separate frictions on the Discord surface, approved as one spec:

1. **Nobody is told when a plan they care about moves.** Lifecycle events
   already reach the execution feed (`notify_plan_events`,
   `swingbot/core/scanning/lifecycle_embeds.py:435`), but that is a channel
   for everyone; it never names a person.
2. **The bot cannot tell an acted-on trade from a paper one.** The live book
   is all paper; there is no record of which plans a human actually placed.
3. **One symbol can be re-alerted repeatedly.** The only existing cooldown is
   `REVERSAL_COOLDOWN_HOURS` (`swingbot/config.py:308`), which governs flips
   of an open trade, not posts.
4. **Two command surfaces disagree.** `swingbot/commands/slash.py` registers
   19 slash commands; there are 39 top-level prefix commands plus 14
   subcommands (table in D4).

## Facts the design rests on (verified 2026-10-09)

- **Plan buttons die after three minutes and never survive a restart.**
  `PlanActionView.__init__` defaults `timeout=180`
  (`swingbot/commands/views.py:57`), `on_timeout` disables every button
  (`views.py:69-76`), and nothing registers a persistent view
  (`git grep add_view\|add_dynamic_items` is empty). A Taken button on that
  view would be unusable on any alert older than three minutes. D2 therefore
  makes the panel persistent; without it D2 cannot work.
- **Watch is a global star, not a per-user record.** `watch_button`
  (`views.py:118-125`) toggles `starred_plans`, one row per `plan_id` with no
  user column (`swingbot/core/db/schema.py:111-115`,
  `swingbot/core/db/repositories/starred.py:13-17`). Any user's press unstars
  it for everyone. D1's mentions need per-user Watch, so D2 adds it.
- **A plan doc field written from a button would be lost.** `PlanStore.update`
  upserts the whole doc from `plan_to_dict` (`plan_store.py:52-56`,
  `repositories/base.py:73-83`), and `plan_from_dict` drops any key that is not
  a `TradePlanV2` field (`plan_types.py:182-187`). The manager re-reads and
  rewrites open plans every 60 s tick (`plan_manager.py:447-543`). A
  `taken_by` list on the plan doc, written by the button, races that rewrite
  — the lost-update shape v67 was built to end. So followers live in their own
  table (D2), not on the plan doc. **This departs from the brief's "on the
  plan doc"**, which allowed "or similar"; the trade still carries the copy.
- **The one-open-trade-per-ticker rule already blocks most repeats.** On the
  scheduled scan an existing open trade on the ticker skips the alert
  (`swingbot/core/scanning/scan_run.py:799-849`), and a PENDING plan has an
  open placeholder trade. D3's real population is a re-alert after a plan
  was cancelled, invalidated, expired or closed inside the window.
- **Lifecycle events already exist** as `PlanEvent`s from `PlanManager.poll`
  (`plan_manager.py:53-58`, `:447`), posted by `_post_plan_events`
  (`swingbot/commands/scanning/loops.py:488`) inside `trade_monitor`
  (`loops.py:542`, `:620`), a 60-second loop separate from the scan. Gated
  on `INTRADAY_MANAGER_V2` (default true, `config.py:627`). Stopped closes
  are `_STOPPED_REASONS` (`plan_manager.py:87`).
- **A near-stop warning already exists, and is different.**
  `_check_near_close` (`swingbot/core/scanning/analyze.py:431`) warns at a
  percentage distance (`NEAR_CLOSE_THRESHOLD_PCT`), on legacy trades, at scan
  time, to the history channel. D1's near-stop is R-based, per plan, once.
  Both coexist; D1 removes nothing.
- **Admin links come from v151.** No admin base URL exists today. v151
  introduces `ADMIN_PUBLIC_URL` (empty = no link) and `plan_link(plan_id)`,
  used by `apply_chrome(..., plan_id=...)`
  (`swingbot/core/presentation/components.py:64`) to set `embed.url`. D1 uses
  that and adds **no second URL key**.

## D1 — Trade-event notifications in a dedicated channel

**Config.** `DISCORD_CHANNEL_NOTIFY_ID` — a new `Field` in `swingbot/config.py`,
section "Discord Connection", beside the other `DISCORD_CHANNEL_*_ID` keys
(`config.py:107-125`), default empty (empty = D1 off), hot-reloadable (the
default).

**Events.** Posted to the channel, never as DMs:

| Notify event | Source `PlanEvent` | Kind (existing, `presentation/kinds.py`) |
|---|---|---|
| `near_stop` | **new** `near_stop` (below) | `NEAR_STOP` (`kinds.py:124`) |
| `tp1` | `tp1_partial`; also `closed` with reason `win` (no-TP2 plan closed whole at TP1, `plan_manager.py:621-623`) | `TP1_HIT` (`kinds.py:118`) |
| `tp2` | `closed`, reason `tp1_runner_tp2` (`plan_manager.py:970`) | `WIN` (`kinds.py:129`) |
| `stopped` | `closed`, reason in `_STOPPED_REASONS` | `STOPPED` (`kinds.py:128`) |
| `expired` | `cancelled_expired` (`plan_manager.py:708`, `:724`) | `EXPIRED` (`kinds.py:133`) |

Other closes (time exit, stall exit, structure exits) and other cancels
(invalidated, risk cap) are **not** notified — outside the approved list. A
new event type is one row in this table later.

**Near-stop detection.** A helper `PlanManager._near_stop_event(plan, price)`
returns a `PlanEvent(plan_id, "near_stop", {...})` when the plan is ACTIVE or
PARTIAL, `near_stop_notified_at` is None, price is not beyond the stop, and
`abs(price - resting_stop(plan)) <= 0.25 * abs(entry_price - stop_loss)`
(initial R; `resting_stop` at `plan_manager.py:133` is the stop the exit
check uses). It stamps `near_stop_notified_at` (new `TradePlanV2` field,
`str | None = None` — an *add*: lands in `doc`, no revision) and the manager
persists it in the same `store.update` it already performs — the manager owns
plan writes, so no race. Called from `poll` after `_step` as one
`events.extend(...)` statement: `poll` is complexity 20 today and **gains no
branch**. It uses the price `poll` already fetched; zero extra requests.
`notify_plan_events` must skip `near_stop` (it would otherwise post every
unknown transition to history, `lifecycle_embeds.py:454-459`): one
`FOLLOW_ONLY_EVENTS` membership test, complexity 12 → 13.

**Delivery.** New `swingbot/commands/scanning/follow_notify.py`,
`async def notify_followers(bot, events)`, awaited in `_post_plan_events`
after the feed post (`loops.py:488`) — so it runs in `trade_monitor`, never in
the scan. Per event: map to a notify event (table above, a dict lookup — no
`if/elif` chain), resolve followers, claim, send.

**Idempotent.** Table `plan_notifications` (D-schema). Before sending, the
notifier inserts `(plan_id, event)` with `ON CONFLICT DO NOTHING`; zero rows
inserted = already sent, skip. A failed send deletes its claim so the next
re-emission retries. Re-emissions are real: `resend_notices` re-sends feed
notices until the feed acknowledges them (`plan_manager.py:347`), and a
restart replays nothing that was claimed. Delivery is therefore at most once
per `(plan, event)`, and exactly once whenever Discord accepts the send.

**Message.** Built as a `PushEmbed` through the kinds registry and sent with
`ui.push_kwargs` (`known-traps.md`: a bare `send(embed=)` drops the push
line); `apply_chrome(..., plan_id=plan.plan_id)` gives the v151 plan link.
Content = the registry content line + mentions of each follower (Watch or
Taken, D2) whose `/notify` preferences allow this event, with
`allowed_mentions=AllowedMentions(users=[...], roles=False, everyone=False)`.
No eligible follower → the message still posts, `silent=True`, no mention.
It carries a persistent Chart button (D2's `ChartButton` dynamic item).

**`/notify`.** Slash command (owned by D4's structure): no arguments shows the
caller's five toggles (ephemeral); `event:<near_stop|tp1|tp2|stopped|expired|all>
enabled:<bool>` sets them. Stored in `notify_prefs`, default all on. A
preference only decides whether *that user* is mentioned, never whether the
message posts.

## D2 — Taken button, per-user Watch, `taken` dimension

**Persistent panel.** `PlanActionView` becomes `timeout=None` and its buttons
become `discord.ui.DynamicItem` subclasses with templates
`plan:<action>:(?P<plan_id>[0-9a-f-]{36})` (plan ids are `uuid4` strings,
`swingbot/core/planning/builders.py:461`; 49 chars, under Discord's 100).
Registered once with `bot.add_dynamic_items(...)` before the gateway connects,
so a click on any alert ever posted — before or after a restart — reaches its
handler. discord.py is pinned at 2.7.1 (`requirements.txt:22`); dynamic items
exist from 2.4. The author-locked `!top` panel (`swingbot/commands/stats.py:121`)
keeps its lock through the same view. Chart, Breakdown, Watch and Dismiss
keep their behaviour; Dismiss still removes the panel for everyone.

**Followers table.** `plan_followers` holds one row per
`(plan_id, user_id, kind)`, `kind ∈ {watch, taken}`, doc
`{at, status_at_press}`. Repository `followers_repo()` with `add`, `remove`,
`has`, `user_ids(plan_id, kinds)`.

- **Watch** toggles the presser's `watch` row. The first watcher stars the
  plan (`star_plan`), removing the last watcher unstars it — `!plans` sorting
  keeps working. Legacy stars with no watcher rows stay starred.
- **✅ Taken** toggles the presser's `taken` row, accepted only while the plan
  is PENDING, ACTIVE or PARTIAL. On CLOSED or CANCELLED it refuses
  ephemerally: a press after the outcome is known would let hindsight pick
  the "taken" winners and poison the comparison. `status_at_press` is kept so
  analytics can later split "placed before fill" from "after".
- Taken implies being mentioned (D1 mentions Watch ∪ Taken).

**On the trade.** The followers table is the truth; the trade carries a
denormalised `taken_by: [user_id, ...]` (an *add*, lands in the trade `doc`).
Written twice, both idempotent: at press, by a new `TradeLog.mark_taken`
under the module `_LOCK` using `Repository.patch` (JSONB `||`, no
read-modify-write, `base.py:85-99`); and re-stamped from the table in
`close_plan_trade` (`swingbot/core/tracking/performance.py:736`) just before
its upsert, complexity 7 → 8. Trades survive plan pruning, so the
dimension does too.

**Analytics.** `"taken"` joins `DIMENSIONS`
(`swingbot/core/analytics/aggregate.py:107`) with extractor
`"taken" if t.get("taken_by") else "paper"`. `GET /analytics/by-dimension` (`swingbot/admin/api_v1/analytics.py:364`)
validates against `DIMENSIONS` already (`:411`).
The SPA adds `{ value: 'taken', label: 'Taken vs paper' }` to
`BREAKDOWN_DIMENSIONS` (`frontend/src/app/stores/analytics.store.ts:275`).
The `taken` cell will sit under `MIN_CELL_N = 20` (`aggregate.py:22`) for a
long time; the existing small-N treatment applies, nothing new.

## D3 — Per-symbol alert cooldown

**Config.** `ALERT_SYMBOL_COOLDOWN_HOURS`, `type="float"`, default `24`,
`min=0`, section "Discord Alerts"; `0` = off; hot-reloadable.

**Rule.** On the scheduled path only, an alert for `(ticker, direction,
horizon_key)` is not posted when an alert with the same ticker, direction
and horizon was **posted** within the window. A flipped direction or a
different horizon posts normally. `!check` and the admin-UI trigger are
on-demand snapshots and are never suppressed.

**Where.** At post time, in `_send_alerts`
(`swingbot/commands/scanning/alerts.py:220`), behind a new keyword
`apply_cooldown: bool = False`, passed `True` only by the scheduled session
scan (`loops.py:198`, through `send_then_short` and `post_short_universe`)
and its store-write-halt re-post (`loops.py:113`). The decision is a helper
`_cooldown_suppressed(plan, now)` (a `to_thread` read) so `_send_alerts`
(complexity 9) gains one branch. A suppressed alert sends neither the full
alert nor its simple mirror. Capped overflow (`alerts.py:262-264`) is
unaffected: the cap ranks only what survives the cooldown.

**Record.** Table `alert_posts`, append-only: `ticker`, `at`, `outcome ∈
{posted, suppressed}`, doc `{direction, horizon_key, plan_id}`. A row is
written after Discord accepts a post, or when a post is suppressed. Tens of
rows a day; no pruning.

**Unchanged book.** The plan was persisted and its placeholder trade logged
by `scan_run` (`scan_run.py:322-341`, `:1101`) before `_send_alerts` runs;
suppression touches neither. The plan stays visible in `!plans`, the admin UI
and the digest ranking.

**Digest.** `_post_daily_digest` (`alerts.py:53`) appends
`· N alert(s) held by the symbol cooldown today` to the content line of both
branches (plans / no VALIDATED plans) when `N > 0`, counting today's
`suppressed` rows (Berlin session date). `digest_payload` (`alerts.py:40`) is
unchanged. The digest itself stays behind `DAILY_DIGEST_ENABLED`
(default false, `config.py:746`).

## D4 — Slash parity through shared handlers

**Shape.** A `Reply` protocol in new `swingbot/commands/reply.py` —
`defer()`, `send(content=, embed=, file=, view=, ephemeral=)` returning an
editable message, `send_chunks(text)` — with `CtxReply` and
`InteractionReply`. Every command body moves into
`async def handle_<name>(reply, <typed args>)`, next to its prefix command in
the same module. The prefix command parses its arguments, calls the handler,
then sends one line: `Tip: this is now /<twin>`. The slash twin, **defined in
the same module**, calls the same handler. `slash.py` keeps only shared
choices and helpers; its 19 commands move to their modules and onto
handlers, ending today's duplicated bodies (`/strategies`, `/regime`, `/pnl`
re-implement their prefix twins, `slash.py:112-166`) and the
`Context.from_interaction` bridge (`slash.py:407-417`).

*Hybrid commands considered, rejected:* `!check`, `!backtest`, `!plans`,
`!liveplans` take free-form `*args` that a hybrid command cannot expose as
typed slash options, and the existing twins already chose typed options.

**Grouping.** Discord forbids a command that is also a group, so a prefix
group that runs on its own maps to a `show` subcommand. Admin-only
`!killswitch` (`growth.py:90`) gets
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

`/trades` stays a plain command because it already exists with options, so
its clear subcommands become hyphenated top-level names. `/notify` (D1) is
slash-only. Top-level slash commands after D4: 42 including `/notify`, under
Discord's 100.
`COMMANDS_BY_CATEGORY` (`swingbot/bot_core.py:79`, rendered by `!help` and
`/help`) lists the slash form first.

**Parity test.** `tests/commands/test_slash_parity.py` walks
`bot.walk_commands()` and asserts every qualified prefix name maps — through
one explicit `SLASH_TWIN` override dict, identity otherwise — to a command
path in `bot.tree`, including group subcommands and `choice`-dispatched
actions (`watchlist`). A second assertion: every handler is called by
exactly one prefix and one slash command (no duplicated bodies).

## Schema

One DDL revision `v152_001`, `down_revision` = the head at implementation
(`v116_002` at writing — recompute with `python -m alembic heads`). Each table
is hybrid (`doc`, `updated_at`), registered in `schema.py` with a
`PROMOTION_REASONS` line per promoted column (`schema-evolution.md`):

| Table | Promoted | Reason |
|---|---|---|
| `plan_followers` | `plan_id` (FK `plans`, cascade), `user_id` BIGINT, `kind`; unique on the three | natural key; lookup by plan |
| `plan_notifications` | `plan_id` (FK `plans`, cascade), `event`; unique on the pair | the idempotency claim |
| `notify_prefs` | `user_id` unique | natural key |
| `alert_posts` | `ticker`, `at`, `outcome`; index `(ticker, at)` | the cooldown window query, the digest count |

Field adds, no revision: `TradePlanV2.near_stop_notified_at`, trade
`taken_by`. No rename, drop or read-time upcast.

## Complexity

Every new or changed function ends below 15 (`radon cc -s -n C`). The two
legacy functions touched gain nothing: `PlanManager.poll` (20) gets one
statement and no branch, `_step_active` (21) is not edited. Event mapping and
`/notify` choices are tables, not `if/elif` chains. Measured today:
`notify_plan_events` 12, `_send_alerts` 9, `close_plan_trade` 7.

## Testing

- D1: near-stop fires once at ≤ 0.25 R and not beyond the stop, for ACTIVE
  and PARTIAL; the stamp persists; `notify_plan_events` ignores `near_stop`;
  each mapped transition picks its notify event and Kind; an unmapped close
  posts nothing; a second identical event (re-sent notice, restart) posts
  nothing; a failed send releases its claim; mentions honour `/notify` and
  `allowed_mentions`; no follower → silent, no mention; empty
  `DISCORD_CHANNEL_NOTIFY_ID` → no send; content line present (`push_kwargs`).
- D2: a dynamic item rebuilds from its `custom_id` alone (restart); Watch per
  user and star bookkeeping; Taken refused on CLOSED and CANCELLED; `taken_by`
  on the trade after press and after close; `stats_by(..., "taken")` splits
  `taken`/`paper`; the SPA store spec gains the option.
- D3: same direction+horizon inside the window suppressed; flipped direction
  or other horizon posted; `0` = off; `!check`/UI trigger never suppressed;
  suppressed alert still has its plan and trade; digest line counts today.
- D4: the parity test; one test per moved handler through both `Reply`
  implementations; the prefix hint line; `/killswitch` default permissions.
- `tests/db/test_schema_contract.py` and the unknown-field round trip cover
  the four tables; `tests/db/test_migrations.py` the revision id.
- One full suite, as the plan's final task.

## What this does not do

DMs; notifying invalidated, risk-cap, time-exit or stall closes; removing the
legacy near-close warning or the execution feed; changing which plans are
built or how they are managed; permission policy on destructive commands
beyond parity; retiring prefix commands.

## Parallelisation

- **Sequential first — F (foundation):** the four tables, revision
  `v152_001`, their repositories, and both config keys. Every later group
  consumes a repository or a key, and `schema.py`/`config.py` are shared files.
- **Group 1 (parallel, after F):** D2 panel + followers + trade copy
  (`views.py`, `performance.py`); D3 cooldown + digest (`alerts.py`); D1
  manager half (`plan_types.py`, `plan_manager.py`, `lifecycle_embeds.py`);
  `aggregate.py` + the SPA option. Disjoint files; each consumes only F.
- **D4 per-module tasks (parallel among themselves, after F):** one task per
  command module (`account`, `backtest`, `data`, `growth`, `history`, `info`,
  `plans`, `stats`, `trades`, `watchlist`, `scanning/commands`), after one
  task that adds `reply.py` and slims `slash.py`, which every module task
  consumes. `stats.py` waits for D2 (both touch the `!top` panel).
- **Sequential edges:** D1 notifier (`follow_notify.py`) after D2 (consumes
  the `ChartButton` dynamic item and Watch/Taken rows). The `loops.py` edits
  in order — D1's `_post_plan_events` hook, then D3's `apply_cooldown`
  arguments — one file. `/notify` after the D4 `reply.py` task. The parity
  test after every D4 module task. D1's plan link needs v151 merged; until
  then `apply_chrome` sets no URL and nothing else changes.
- The full suite last.
