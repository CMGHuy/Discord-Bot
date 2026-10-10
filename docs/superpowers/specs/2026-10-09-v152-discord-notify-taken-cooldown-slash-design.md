# v152 — Discord notify, Taken, cooldown

**Version:** ui 1.22.0 · bot 2.2.3 (at writing)
**Bump:** bot minor, ui patch — a Discord user meets a different bot: a new
channel that names them when a paper plan they follow moves, a persistent
`✅ Following` button on every alert, and fewer repeat posts for one symbol.
Someone who used the bot yesterday has to look at it anew, which is the
shape of a minor (`working-conventions.md` § The three levels). Slash parity,
the other user-visible change that argued for a minor, is now v153 and bumps
on its own; D1–D3 still carry the minor alone. The admin UI gains one
analytics breakdown option (`taken`) with its caption: a new control, a patch.
**Edge:** none (integrity) — nothing here changes which plans are built,
filled, stopped or closed. D3 suppresses only the Discord *post*: the plan is
still created, persisted and managed, and its trade still logged, so the
measured book is unchanged. D2 adds a dimension that splits the existing book;
it does not change it.
**Screen:** exempt (integrity)
**Panel:** veteran-trader, financial-advisor, staff-engineer
**Status:** spec written 2026-10-09; design approved section by section; panel review applied; D4 split to v153; plan written 2026-10-10 (`plans/2026-10-10-v152-discord-notify-taken-cooldown_0-index.md`).

## Why

Three frictions on the Discord surface, approved as one spec:

1. **Nobody is told when a plan they care about moves.** Lifecycle events
   already reach the execution feed (`notify_plan_events`,
   `swingbot/core/scanning/lifecycle_embeds.py:435`), but that is a channel
   for everyone; it never names a person.
2. **The bot cannot tell a followed plan from a purely paper one.** The live
   book is all paper; there is no record of which plans a human said they
   followed.
3. **One symbol can be re-alerted repeatedly.** The only existing cooldown is
   `REVERSAL_COOLDOWN_HOURS` (`swingbot/config.py:308`), which governs flips
   of an open trade, not posts.

## Facts the design rests on (verified 2026-10-09)

- **Plan buttons die after three minutes and never survive a restart.**
  `PlanActionView.__init__` defaults `timeout=180`
  (`swingbot/commands/views.py:56`), `on_timeout` disables every button
  (`views.py:68-75`), and nothing registers a persistent view
  (`git grep add_view\|add_dynamic_items` is empty). Its four buttons carry
  static ids `plan:chart`, `plan:breakdown`, `plan:watch`, `plan:dismiss`
  (`views.py:78`, `:110`, `:118`, `:127`) with no plan id in them. D2 makes
  the panel persistent; without it a Following button cannot work.
- **Watch is a global star, not a per-user record.** `watch_button`
  (`views.py:118-125`) toggles `starred_plans`, one row per `plan_id` with no
  user column (`swingbot/core/db/schema.py:111`,
  `swingbot/core/db/repositories/starred.py:13`). Any user's press unstars
  it for everyone. D1's mentions need per-user Watch, so D2 adds it.
- **A plan doc field written from a button would be lost.** `PlanStore.update`
  upserts the whole doc (`plan_store.py:52`, `repositories/base.py:73`), and
  `plan_from_dict` drops any key that is not a `TradePlanV2` field
  (`plan_types.py:182`). The manager rewrites open plans every 60 s tick
  (`plan_manager.py:447`). So followers live in their own table (D2), not on
  the plan doc — a departure from the brief's "on the plan doc", which allowed
  "or similar"; the trade still carries a copy.
- **The one-open-trade-per-ticker rule already blocks most repeats.** On the
  scheduled scan an existing open trade on the ticker skips the alert
  (`swingbot/core/scanning/scan_run.py:799`), and a PENDING plan has an open
  placeholder trade. D3's real population is a re-alert after a plan was
  cancelled, invalidated, expired, stopped or closed inside the window.
- **Lifecycle events already exist** as `PlanEvent`s from `PlanManager.poll`
  (`plan_manager.py:53-58`, `:447`), posted by `_post_plan_events`
  (`swingbot/commands/scanning/loops.py:488`) inside `trade_monitor`
  (`loops.py:542`, `:620`), a 60-second loop separate from the scan. Gated on
  `INTRADAY_MANAGER_V2` (default true, `config.py:627`). Stopped closes are
  `_STOPPED_REASONS` (`plan_manager.py:87`). `_post_plan_events` returns early
  when the feed post raises or delivers nothing (`loops.py:494-498`), and only
  un-acked feed notices are re-sent (`resend_notices`, `plan_manager.py:347`).
- **A near-stop warning already exists, and is different.**
  `_check_near_close` (`swingbot/core/scanning/analyze.py:431`) warns at a
  percentage distance, on legacy trades, at scan time, to the history
  channel. D1's near-stop is R-based, per plan, once. Both coexist.
- **Admin links come from v151.** v151's contract: `apply_chrome`
  (`swingbot/core/presentation/components.py:64`) gains a `link_base`
  keyword, `plan_link(plan_id, base)` is pure, and every plan-carrying caller
  passes `link_base=config.ADMIN_PUBLIC_URL` (a Discord Alerts field). D1's
  notifier is such a caller and adds **no second URL key**.

## D1 — Trade-event notifications in a dedicated channel

**Config.** `DISCORD_CHANNEL_NOTIFY_ID` — a new `Field` in `swingbot/config.py`,
section "Discord Connection", beside the other `DISCORD_CHANNEL_*_ID` keys
(`config.py:106-125`), default empty (empty = D1 off), hot-reloadable.

**Events.** Posted to the channel, never as DMs:

| Notify event | Source `PlanEvent` | Kind (`presentation/kinds.py`) | Posted when |
|---|---|---|---|
| `near_stop` | **new** `near_stop` (below) | `NEAR_STOP` (`:124`) | always |
| `tp1` | `tp1_partial`; also `closed` reason `win` (no-TP2 plan closed whole at TP1, `plan_manager.py:621-625`) | `TP1_HIT` (`:118`) | always |
| `tp2` | `closed`, reason `tp1_runner_tp2` (`plan_manager.py:970`) | `WIN` (`:129`) | always |
| `stopped` | `closed`, reason in `_STOPPED_REASONS` | `STOPPED` (`:128`) | always |
| `expired` | `cancelled_expired` (`plan_manager.py:708`, `:724`) | `EXPIRED` (`:133`) | always |
| `closed_other` | any other `closed` reason (time exit, `stall_exit` `:837`, structure exit `tp1_runner_progress_stall` `:877`); `cancelled_invalidated` (`:757`); `cancelled_risk_cap` (`:740`) | `EXITED` (`:131`), `INVALIDATED` (`:134`), `RISK_CAP` (`:121`) | **only** when the plan has ≥ 1 Following follower; mentions only them |

`closed_other` is the partner's addition: a follower who placed the plan must
hear that the bot's paper copy is gone, whatever the reason; a Watch-only
follower need not. The mapping is two dicts — `(transition, reason)` first,
then `transition` with `closed → closed_other` as the fallback — no `if/elif`
chain. Standalone `be_moved`/`stop_moved` (`plan_manager.py:66`) are **not**
separate notify events; the move is carried by the next message (below).

**Copy rule (every message).** Factual paper-plan event wording, no
imperatives. Templates, one per event, in `follow_notify.py` as a table:

- `near_stop`: "Paper plan update: AAPL long is 0.21R from its stop. Stop
  182.40, last 183.10."
- `tp1`: "Paper plan update: AAPL long reached TP1 at 190.00. Stop now at
  185.00 (breakeven), remaining target 196.00." For the no-TP2 `win` close:
  "Paper plan closed at TP1 190.00: +1.0R."
- `tp2`: "Paper plan closed at TP2 196.00: +2.4R."
- `stopped`: "Paper plan closed at its stop 182.40: −1.0R" (scratch: "at
  breakeven 185.00: 0.0R"; trail: "at its trailing stop …").
- `expired`: "Paper plan expired unfilled."
- `closed_other`: "Paper plan closed by time exit / stall exit / structure
  exit at 187.30: +0.4R" or "Paper plan cancelled: invalidated before entry /
  risk cap reached."

Every message on an ACTIVE or PARTIAL plan states the **current resting stop**
(`resting_stop`, `plan_manager.py:133`) and the remaining target as facts, so
a breakeven or trail move since the last message is never silent. The embed
footer ends with **"Paper plan update, not advice."** A forbidden-phrase list
(`exit now`, `move stop`, `move your stop`, `take profit`, `sell now`,
`buy now`, `close your`, `you should`) is a module constant; a test renders
every event × direction and asserts none appears in content, title,
description, fields or footer. The `MOVE_STOP` and `CANCEL` kinds
(`kinds.py:119`, `:120`) are imperative labels and are never used here.

**Near-stop detection.** A pure helper `PlanManager._near_stop_event(plan,
price, now)` returns `PlanEvent(plan_id, "near_stop", {stop, price, r_dist})`
when the plan is ACTIVE or PARTIAL, `is_regular_session(now)`
(`swingbot/core/market/session.py:48`) is true, price is not beyond the stop,
and `abs(price - resting_stop(plan)) <= 0.25 * abs(entry_price - stop_loss)`
(initial R). `r_dist` is that distance in initial R. Called from `poll` after
`_step` as one `events.extend(...)` statement: `poll` (complexity 20) **gains
no branch** and no write; it uses the price `poll` already fetched.
*Limits, stated:* near-stop arms in the regular session only — pre- and
after-hours prints never fire it. The manager polls every 60 s; a gap or fast
move that is already beyond the stop at the next poll fires only `stopped`,
never `near_stop`. Once per plan: the dedupe is the `plan_notifications`
claim (below), so the helper emits on every in-band tick and the notifier
drops repeats from an in-process cache of sent claims, loaded once.
`notify_plan_events` must skip `near_stop` (it would otherwise post every
unknown transition to history, `lifecycle_embeds.py:457-460`): one
`FOLLOW_ONLY_EVENTS` membership test, complexity 12 → 13.

**Delivery.** New `swingbot/commands/scanning/follow_notify.py`,
`async def notify_followers(bot, events)`. `_post_plan_events` is split so
the feed and the notifier are **independent**: `_post_feed(events)` (today's
body up to the ack), then `notify_followers` in its own `try` regardless of the
feed's result — it is no longer behind the early returns at `loops.py:494-498`
— then the ack when there were deliveries. Per event: map to a notify event,
resolve followers, claim, send. Every DB call (followers, prefs, claims) runs
through `asyncio.to_thread`.

**Idempotent, with its own retry.** Table `plan_notifications` (Schema). The
notifier inserts `(plan_id, event)` with `state=pending` and the event detail
in `doc`, `ON CONFLICT DO NOTHING`; zero rows inserted = already claimed,
skip. After Discord accepts the send it sets `state=sent` — that write is the
near-stop "stamp", so nothing is marked done before a successful send. A
failed send leaves the row `pending`, `attempts += 1`. **Retry source:**
`retry_pending_notifications()` runs once per `trade_monitor` tick
(`loops.py:542`), re-sending `pending` rows older than 60 s from their stored
detail and the plan's current state; after 5 attempts the row becomes
`failed` and is logged at WARNING. Retries for every event therefore depend
on this table alone, never on `resend_notices`. Guarantee: one message per
`(plan, event)`, with at most one duplicate when the `sent` write fails after
a successful send.

**Message.** Built as a `PushEmbed` through the kinds registry and sent with
`ui.push_kwargs` (`components.py:106`; `known-traps.md`: a bare
`send(embed=)` drops the push line), via
`apply_chrome(embed, kind=..., plan_id=plan.plan_id,
link_base=config.ADMIN_PUBLIC_URL)` — v151's caller-side contract; the
notifier resolves nothing itself. Content = the copy-rule line + mentions of
each eligible follower, `allowed_mentions=AllowedMentions(users=[...],
roles=False, everyone=False)`. No eligible follower → the message still posts,
`silent=True`, no mention (except `closed_other`, which does not post at all
without a Following follower). It carries a persistent Chart button (D2).

**`/notify` and per-user defaults.** A slash command defined in
`swingbot/commands/slash.py` beside today's 19 (`slash.py:75`-`:465`), in
their `@bot.tree.command` style; v153 later moves it with the rest. No
arguments → an ephemeral list of **which events this channel announces**
(the six above, with the `closed_other` Following-only rule) and the caller's
setting for each. `event:<near_stop|tp1|tp2|stopped|expired|closed_other|all>
enabled:<bool>` sets one; `watch_mode:<mention|silent>` sets how Watch-only
plans treat the caller. Stored in `notify_prefs`. Defaults: a **Following**
follower is mentioned for all six; a **Watch-only** follower is mentioned for
`tp1`, `tp2`, `stopped`, and *not* for `near_stop` or `expired` (defaults
OFF); `watch_mode=silent` drops every Watch-only mention while the message
still posts. An explicit toggle overrides the default. A preference decides
only whether *that user* is mentioned, never whether the message posts.
Quiet hours are **not** added: messages are channel posts the user can mute,
and near-stop already arms only in the regular session.

**Channel topic.** Set by hand as a production step (the bot is not given
Manage Channels): "Paper plan updates for plans you follow: near stop, TP1,
TP2, stopped, expired; closed/cancelled for Following only. Not advice.
/notify to choose."

**Volume.** Structural bound: at most one message per `(plan, event)`, and a
plan reaches at most three (near_stop, tp1, one terminal), so weekly volume
≤ 3 × plans filled per week + plans expired per week, with `closed_other`
added only for followed plans. The plan's first task measures the real
figure read-only on production (`prod-inspector`) from the last four weeks of
`plans` transitions — messages/week per event — and the same query's D3
estimate (below); both land in the plan's results note before D1 ships.

## D2 — Following button, per-user Watch, `taken` dimension

**Persistent panel.** `PlanActionView` becomes `timeout=None` and its buttons
become `discord.ui.DynamicItem` subclasses with template
`plan:<action>:(?P<plan_id>[0-9a-f-]{36})(?::(?P<author>\d{17,20}))?` (plan
ids are `uuid4` strings, `swingbot/core/planning/builders.py:461`; longest id
72 chars, under Discord's 100). **Author lock — choice: the author id rides
in the `custom_id`.** The `!top` panel (`swingbot/commands/stats.py:121`)
encodes `ctx.author.id`; scan and digest alerts (`alerts.py:284`, `:80`, author `None`) omit the
segment. The lock is checked from the parsed id, so `!top` panels also
survive a restart, through one view class. Registered once with
`bot.add_dynamic_items(...)` in a new `setup_hook` (`bot_core.py`, the bot at
`:35`), before the gateway connects. discord.py is pinned at 2.7.1
(`requirements.txt:22`); dynamic items exist from 2.4. Chart, Breakdown,
Watch and Dismiss keep their behaviour; their plan reads, which run on the
event loop today (`views.py:81`, `:112`), move to `asyncio.to_thread`.

**Legacy ids — choice: fallback.** A persistent `LegacyPlanPanel`
(`timeout=None`) registered with `bot.add_view` claims the four static ids.
Chart, Breakdown and Watch reply ephemerally "This alert predates v152 — use
the plan page or `!plans`."; Dismiss still removes the panel (it needs no
plan id). Old alerts never show "This interaction failed" after the deploy.

**Followers table.** `plan_followers` holds one row per
`(plan_id, user_id, kind)`, `kind ∈ {watch, taken}`, doc
`{at, status_at_press}`. Repository `followers_repo()` with `add`, `remove`,
`has`, `user_ids(plan_id, kinds)`; every call from a button via
`asyncio.to_thread`.

- **Watch** toggles the presser's `watch` row. The first watcher stars the
  plan (`star_plan`), removing the last watcher unstars it — `!plans` sorting
  keeps working. Legacy stars with no watcher rows stay starred.
- **✅ Following** (kind `taken`) records intent to follow the plan, not a
  fill: the wording is "followed", never "executed". Toggles the presser's
  `taken` row, accepted only while the plan is PENDING, ACTIVE or PARTIAL. On
  CLOSED or CANCELLED it refuses ephemerally: a press after the outcome is
  known would let hindsight pick the winners. `status_at_press` is kept.
- **The ephemeral reply informs, never blocks.** It states the plan's status
  and entry validity: for PENDING, sessions left of `expiry_bars`
  (`plan_types.py:33`) and "plan stale" when one or none is left; for ACTIVE
  or PARTIAL, the latest cached price against `entry_price` and "price already
  beyond entry by xR" when it is; plus "Recorded as followed — paper plan, not
  your fill." The price comes from `get_daily_data` in `asyncio.to_thread`, as
  the Chart button does (`views.py:86`); a fetch failure drops that line only.
- Following implies being mentioned (D1).

**On the trade.** The followers table is the truth; the trade carries a
denormalised `taken_by: [user_id, ...]` (an *add*, lands in the trade `doc`).
Written twice, both idempotent: at press, by a new `TradeLog.mark_taken`
under the module `_LOCK` using `Repository.patch` (JSONB `||`, no
read-modify-write, `base.py:85`); and re-stamped from the table in
`close_plan_trade` (`swingbot/core/tracking/performance.py:736`) just before
its upsert, complexity 7 → 8. Trades survive plan pruning, so the dimension
does too.

**Analytics.** `"taken"` joins `DIMENSIONS`
(`swingbot/core/analytics/aggregate.py:107`) with extractor
`"followed" if t.get("taken_by") else "paper"`.
`GET /analytics/by-dimension` (`swingbot/admin/api_v1/analytics.py:364`)
validates against `DIMENSIONS` already (`:411`). The SPA adds
`{ value: 'taken', label: 'Followed vs paper' }` to `BREAKDOWN_DIMENSIONS`
(`frontend/src/app/stores/analytics.store.ts:275`). When that breakdown is
selected, the attribution tab (`workspaces/analytics/tabs/attribution.ts:131`)
shows the caption **"Paper results, R units, pre-tax. Followed records the
plan as followed, not your fill."** and `dimensionVisible` (`:238-244`)
orders `exp_r` before `win_rate` — expectancy leads, win rate is secondary,
`n` stays shown per cell. The `followed` cell will sit under `MIN_CELL_N = 20`
(`aggregate.py:22`) for a long time; the existing small-N treatment applies.

## D3 — Per-symbol alert cooldown

**Config.** `ALERT_SYMBOL_COOLDOWN_HOURS`, `type="float"`, default `24`,
`min=0`, section "Discord Alerts"; `0` = off; hot-reloadable.

**Rule.** On the scheduled path only, an alert for `(ticker, direction,
horizon_key)` is not posted when an alert with the same key was **posted**
within the window. A flipped direction or a different horizon posts normally.
`!check` and the admin-UI trigger are on-demand snapshots and are never
suppressed. **A held alert is a different plan**, with its own `plan_id` and
lifecycle; it does not supersede or update the plan posted earlier, and that
plan's followers are not moved to it. **Stated consequence:** a re-entry
setup after a stop-out inside the window is hidden from the channel (still
built, managed and in the book).

**Where.** Owner module: new `swingbot/commands/scanning/cooldown.py`
(`suppressed(plan, now)`, `record(plan, outcome)`, `held_note()`, `prune()`).
At post time `_send_alerts` (`swingbot/commands/scanning/alerts.py:220`)
takes a new keyword `apply_cooldown: bool = False`, passed `True` only by the
scheduled session scan (`loops.py:198`, through `send_then_short` and
`post_short_universe`, `alerts.py:291`, `:308`). The **store-write-halt
re-post** (`loops.py:109-114`) does **not** pass it: those trades are already
in the book and would otherwise vanish from Discord, and `StoreWriteHalt`
must still propagate untouched. `_send_alerts` (complexity 9) gains one
branch. A suppressed alert sends neither the full alert nor its simple
mirror. Capped overflow (`alerts.py:262-264`) ranks only what survives.

**Fails open.** Any error reading the window (`suppressed`) or writing
`alert_posts` (`record`) → the alert **posts** and a WARNING is logged; a
cooldown fault can never cost an alert or raise into the scan. Both calls run
via `asyncio.to_thread`.

**Record.** Table `alert_posts`, append-only: `ticker`, `at`, `outcome ∈
{posted, suppressed}`, doc `{direction, horizon_key, plan_id}`. A row is
written after Discord accepts a post, or when a post is suppressed. Tens of
rows a day. `cooldown.prune()` deletes rows older than
`max(ALERT_SYMBOL_COOLDOWN_HOURS, 7 days)` once a day from `daily_recap`
(`loops.py:653-654`), in `to_thread`, failure logged.

**Unchanged book.** The plan was persisted and its placeholder trade logged
by `scan_run` (`scan_run.py:322`, `:1101`) before `_send_alerts` runs;
suppression touches neither. The plan stays visible in `!plans`, the admin UI
and the digest ranking.

**Visible held count — two surfaces.** (1) **Choice: a one-line ops note per
scan.** After `send_then_short` in `session_scan` (`loops.py:198`), when the
scan held ≥ 1 alert, one silent line goes to `_ops_channel()`
(`loops.py:50`, ops channel else the alerts channel), guarded like
`notices.send_guarded` (`notices.py:35`): "Cooldown held 2 alert(s) this
scan: AAPL long 4w, MSFT short 2w (posted within 24h)." This is the cheapest
surface that is visible with the digest off — no new channel, no new key.
(2) `_post_daily_digest` (`alerts.py:53`) appends
`· N alert(s) held by the symbol cooldown today` to its content line when
`N > 0` (Berlin session date); `digest_payload` (`alerts.py:40`) unchanged;
the digest stays behind `DAILY_DIGEST_ENABLED` (default false, `config.py:746`).

**Expected volume.** No alert-post record exists before v152, so the plan's
first task estimates it from production `plans` (scheduled source): posts/week
today = plans/week; after = the same set minus those with an identical
`(ticker, direction, horizon_key)` posted in the previous 24 h. Both figures
go into the results note; after launch `alert_posts` measures it directly.

## Schema

One DDL revision `v152_001`, `down_revision` = the head at implementation
(`v116_002` at writing — recompute with `python -m alembic heads`); its
`downgrade()` drops the four tables and is exercised by
`tests/db/test_migrations.py`. Each table is hybrid (`doc`, `updated_at`),
registered in `schema.py` with a `PROMOTION_REASONS` line per promoted column
(`schema-evolution.md`):

| Table | Promoted | Reason |
|---|---|---|
| `plan_followers` | `plan_id` (FK `plans`, cascade), `user_id` BIGINT, `kind`; unique on the three | natural key; lookup by plan |
| `plan_notifications` | `plan_id` (FK `plans`, cascade), `event`, `state`; unique on `(plan_id, event)` | the idempotency claim; the retry sweep's `state='pending'` filter |
| `notify_prefs` | `user_id` unique | natural key |
| `alert_posts` | `ticker`, `at`, `outcome`; index `(ticker, at)` | the cooldown window query |

**Index choice for `alert_posts`:** only `(ticker, at)`, which serves the
per-ticker window lookup. The digest count, the ops note and the prune scan
`at` over at most ~7 days of tens of rows — a sequential scan of a few
hundred rows, cheaper than maintaining a second index.

Field adds, no revision: trade `taken_by`. No rename, drop or read-time
upcast. (The earlier draft's `TradePlanV2.near_stop_notified_at` is gone: the
`plan_notifications` row is the stamp.)

## Complexity

Every new or changed function ends below 15 (`radon cc -s -n C`). The legacy
functions touched gain nothing: `PlanManager.poll` (20) gets one statement
and no branch; `_step_active` (21) is not edited. Event mapping, copy
templates and `/notify` choices are tables, not `if/elif` chains. Measured
today: `notify_plan_events` 12, `_send_alerts` 9, `close_plan_trade` 7.

## Testing

- D1: near-stop fires at ≤ 0.25 R, not beyond the stop, regular session only
  (not pre/after-hours), for ACTIVE and PARTIAL, and posts once; a gap beyond
  the stop yields `stopped` only; `notify_plan_events` ignores `near_stop`;
  each mapped transition picks its notify event and Kind; `closed_other` posts
  only with a Following follower and mentions only them; the copy-rule test
  (forbidden phrases, footer, resting stop and remaining target on tp1 and
  every ACTIVE/PARTIAL message, near-stop stop price and R distance); a
  second identical event posts nothing; a failed send stays `pending` and the
  sweep retries it, `failed` after 5; the feed raising or delivering nothing
  still runs the notifier; mentions honour defaults (Watch-only: near_stop and
  expired off), toggles and `watch_mode=silent`; `allowed_mentions`; no
  follower → silent, no mention; empty `DISCORD_CHANNEL_NOTIFY_ID` → no send;
  `apply_chrome` receives `link_base=config.ADMIN_PUBLIC_URL`. v151's AST
  guard (task V151-6) scans a fixed `MODULES` list of `apply_chrome`
  callers with per-module call counts; v152 adds `follow_notify.py` to that
  list with its call count, or the new caller goes unguarded.
- D2: a dynamic item rebuilds from its `custom_id` alone (restart), with and
  without the author segment, and the `!top` lock holds after rebuild; the
  legacy static ids reply with the predates-v152 line and Dismiss still works;
  Watch per user and star bookkeeping; Following refused on CLOSED and
  CANCELLED; the reply's stale / beyond-entry lines; `taken_by` on the trade
  after press and after close; `stats_by(..., "taken")` splits
  `followed`/`paper`; the SPA store spec gains the option, the caption and
  the `exp_r`-first order.
- D3: same key inside the window suppressed; flipped direction or other
  horizon posted; `0` = off; `!check`/UI trigger and the store-write-halt
  re-post never suppressed (halt still raises); a raising read or write posts
  anyway; suppressed alert still has its plan and trade; ops note line once
  per scan with ≥ 1 held; digest line counts today; prune keeps the window.
- `tests/db/test_schema_contract.py` and the unknown-field round trip cover
  the four tables; `tests/db/test_migrations.py` the revision and downgrade.
- One full suite, as the plan's final task.

## Production and rollback

- **Forward.** Deploy the image; run `docker compose exec bot alembic upgrade
  head` (`docs/deploy/DEPLOY_HETZNER.md:281`) before restarting the bot. Set
  `DISCORD_CHANNEL_NOTIFY_ID` on the VM with
  `python3 scripts/ops/env_set.py` (`mirror-prod`; `.env.example` gains the
  key in the same commit), then set the channel topic by hand.
  `ALERT_SYMBOL_COOLDOWN_HOURS` goes live at its default 24 on deploy.
- **Image-only rollback.** The four tables stay and are ignored by the old
  image. Buttons on alerts posted under v152 then fail with Discord's "This
  interaction failed" — the old image registers no dynamic items and no
  legacy reply; the plan page and `!plans` still work. Notifications and the
  cooldown stop. `alembic downgrade v116_002` is optional and drops the
  followers record.
- **PITR rollback.** `scripts/ops/rollback_to.sh` restores Postgres to one
  second (`rollback_to.sh:6`) with the matching image, so `plan_followers`,
  `plan_notifications` and trade `taken_by` rewind together with the book;
  a target before `v152_001` removes the tables along with the revision.
  Discord messages already posted are not rolled back (`rollback_to.sh:8-9`).

## What this does not do

DMs; separate stop-move notifications; quiet hours; removing the legacy
near-close warning or the execution feed; changing which plans are built or
how they are managed; recording real fills.

## What follows

D4 slash parity moved to v153 (docs/superpowers/specs/2026-10-09-v153-slash-command-parity-design.md) so it deploys and rolls back alone.

## Parallelisation

- **Sequential first — M0:** the read-only production measurement (D1
  messages/week per event, D3 posts/week before and after), recorded in the
  plan's results note.
- **Sequential — F (foundation):** the four tables, revision `v152_001` and
  its downgrade, their repositories, and both config keys. Every later group
  consumes a repository or a key, and `schema.py`/`config.py` are shared.
- **Group 1 (parallel, after F):** D2 panel + legacy fallback + followers +
  trade copy (`views.py`, `bot_core.py`, `stats.py`, `performance.py`); D3
  cooldown module + `alerts.py` + digest; D1 manager half (`plan_manager.py`,
  `lifecycle_embeds.py`); `aggregate.py` + the SPA option, caption and order.
  Disjoint files; each consumes only F.
- **Sequential edges:** D1 notifier (`follow_notify.py`) after D2 (consumes
  the `ChartButton` dynamic item and follower rows) **and after v151 has
  merged** (it passes `link_base`, which v151 adds to `apply_chrome`).
  `/notify` (`slash.py`) after the notifier (it reads the event table). The
  `loops.py` edits in order — D1's `_post_plan_events` split and retry sweep,
  then D3's `apply_cooldown` argument, ops note and prune — one file.
- **Independent of v153:** v153 may land before or after; whichever lands
  second moves or keeps `/notify` per v153's table.
- The full suite last.

## Panel review

- veteran-trader: [BLOCKING] tp1 and stop-move messages carry the new resting stop and remaining target, phrased as fact -- applied
- veteran-trader: notify closes by time/stall/structure exit and cancels (invalidated, risk cap) -- applied (`closed_other`, Following-only, partner decision)
- veteran-trader: state near_stop gap/poll limits and pre/after-hours behaviour -- applied (regular session only; beyond-stop at poll fires `stopped` only)
- veteran-trader: Following reply shows status and entry validity, informs never blocks -- applied
- veteran-trader: cooldown hold is a different plan, re-entry after stop-out is hidden, held count visible without the digest -- applied (ops note per scan + digest line)
- veteran-trader: weekly notify volume estimate; `silent` option for Watch-only followers -- applied (structural bound + M0 measurement; `watch_mode=silent`)
- veteran-trader: near_stop content includes stop price and distance in R -- applied
- financial-advisor: [BLOCKING] copy rule, no imperatives, "Paper plan update, not advice." footer, forbidden-phrase test -- applied
- financial-advisor: [BLOCKING] `taken` dimension labelled paper results, R units, pre-tax, followed not filled; expectancy leads, N shown -- applied
- financial-advisor: label Taken as "Following" intent, "followed" not "executed", keep status_at_press -- applied
- financial-advisor: `/notify` output and channel topic state which events are announced -- applied
- financial-advisor: state expected alerts/week before vs after cooldown -- applied (M0 measurement from production plans; `alert_posts` after launch)
- financial-advisor: near_stop and expired default OFF for Watch-only; quiet hours stated -- applied (quiet hours not added, reason given)
- financial-advisor: Taken cell shows N; expectancy leads, win rate secondary -- applied
- staff-engineer: [BLOCKING] cooldown fails open; store-write-halt re-post skips the cooldown so StoreWriteHalt propagates -- applied
- staff-engineer: [BLOCKING] notifier independent of the feed result; near-stop stamped only after a successful send; retries independent of resend_notices -- applied (`plan_notifications` state + per-tick retry sweep)
- staff-engineer: resolve the admin base URL at the caller per v151, no second URL key -- applied (`apply_chrome(..., plan_id=..., link_base=config.ADMIN_PUBLIC_URL)`)
- staff-engineer: author id in the DynamicItem custom_id or non-persistent `!top` -- applied (author id in custom_id)
- staff-engineer: pre-v152 static-id buttons get a legacy fallback or a cutoff -- applied (fallback reply; Dismiss still works)
- staff-engineer: slash payload offline build and Discord limits in the parity test -- applied (moved to v153)
- staff-engineer: Production/Rollback section (alembic upgrade, downgrade, VM key, image-only and PITR rollback) -- applied
- staff-engineer: all notifier/button DB calls via asyncio.to_thread -- applied
- staff-engineer: alert_posts owner, nightly prune, index choice -- applied (`cooldown.py`; prune in `daily_recap`; `(ticker, at)` only)
- staff-engineer: split D4 out of v152 -- applied: D4 split to v153 per partner
