# v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post

**Version:** ui 1.41.0 · bot 2.18.5
**Bump:** ui minor (an open admin tab gains spoken notifications and a new Settings section); bot patch (the simple-channel senders also record each accepted post, invisible in Discord)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer

## Why

The partner trades from the simple Discord channel (`DISCORD_CHANNEL_TRADES_SIMPLE_ID`):
new setups, fills, cancels, stop moves, results. When bomeo-capital.com is open
they want to *hear* each of those posts without watching Discord. Nothing about
which alerts are produced, their content or their timing changes; this adds a
second, spoken surface for the posts that already go out.

## Decisions (partner, 2026-11-12)

1. **What is spoken: a short headline** per post, e.g. "New long alert, AAPL,
   buy at 187.50" or "Order filled, MSFT". Never the full post text.
2. **Which posts: every simple-channel post**, filtered by **per-kind toggles
   on the Settings page** (order fill, order cancel, …), so the partner can
   silence any kind.
3. **Toggles are saved per browser/device** (localStorage), not on the server
   and not in `.env`.

Defaults chosen by the author (partner approved the design): everything on
except the Watch family (`NEAR_STOP`, `NEAR_TP`), which is the noisiest. A post
made while no tab was open is never spoken later (no backlog).

## Approaches considered

- **Chosen: the bot records each accepted simple-channel post** in a
  `feed_posts` table at send time; a NOTIFY raises a new `feed` SSE event; the
  SPA fetches the new rows and speaks them with the browser's Web Speech API
  (`speechSynthesis`, free, no external service). Matches the channel exactly.
- Rejected: deriving from the existing live events (`live_events.EVENT_KINDS`:
  alerted, paper filled, TP1, closed, killswitch). It misses cancels, stop
  moves, risk-cap cancels and near-stop/TP warnings and fires on events the
  channel never posts.
- Rejected: the admin reading the Discord channel through the Discord API.
  It would need the bot token inside the admin container, polling and rate-limit handling.

## Design

### 1. Recording a post (bot)

- **Table `feed_posts`** (Alembic revision `v227_001_feed_posts`):
  `id bigserial PK`, `posted_at timestamptz NOT NULL default now()`,
  `kind text NOT NULL` (a `presentation.kinds.Kind` member name),
  `ticker text NULL`, `headline text NOT NULL`. Index on `posted_at`. Its NOTIFY
  trigger comes from the shared `notify.trigger_ddl` (statement-level, on
  insert/update/delete), like `p3_007_notify_triggers.py`. **Three registries
  change together:** `swingbot/core/db/notify.CHANNELS` gains `feed`,
  `swingbot/core/db/events.TABLE_CHANNELS["feed_posts"] = "feed"`, and
  `schema.METADATA` gains the table (`tests/db/test_trigger_coverage.py`,
  `test_every_mapped_table_exists`).
- **Rollback:** the revision's downgrade drops the trigger and the table. It
  carries `ROLLBACK_SAFE = "..."` (v220 `scripts/ops/rollback_migrations.py`).
  This is honest because older code never reads `feed_posts`, and an older
  admin ignores the unknown `feed` channel (`admin/events/db_listener.py`). So
  `test_every_revision_newer_than_the_floor_is_rollback_safe` stays green, and
  a code-only rollback past v227 is not refused.
- **Kill switch:** `FEED_POSTS_ENABLED` in `swingbot/config.py`'s schema
  (bool, default on, hot-reloaded by SIGHUP). Off means the recorder returns
  at once, the site goes silent, and Discord is unaffected.
- **Recorder, split by package** (`docs/claude/architecture.md`):
  - SQL in a repository, `swingbot/core/db/repositories/feed_posts.py`:
    `insert(kind, ticker, headline)`, `after(id, limit)`, `latest_id()`, `prune(days)`.
  - Headline table and builder in `swingbot/core/presentation/feed_headline.py`.
  - The glue `record_feed_post(embed, ticker, kind=None)` in
    `swingbot/core/infra/feed_posts.py` imports both **lazily**, inside the
    function, so `core/infra` keeps no module-level import of the presentation
    registry (the cycle `posted_log.py` avoids).

  The recorder resolves the kind exactly as `log_posted` does and **never
  raises** (`swallowed(...)`). It also **never blocks the bot's loop for
  long**: the insert goes through the fail-fast `swingbot/core/db/side_engine.py`
  (autocommit, statement timeout, pool timeout equal to it, down-backoff),
  never the main pool. A slow database costs one bounded, dropped notification
  and nothing else.
- **Call sites: only the simple-channel sends, after Discord accepted them**:
  `commands/scanning/alerts.py:_mirror` (new setups, tickets, strategy mirrors)
  and the feed branch of `core/scanning/lifecycle_embeds._send_instruction`
  (fills, cancels, stop moves, TP1, results, near-stop/TP). In both, the call
  sits **inside the `try`, right after `log_posted`**, so a failed send records
  nothing. The history-channel fallback copy is **not** recorded: that isn't a
  simple-channel post. `git grep TRADES_SIMPLE_ID` finds only these two senders.
- **Ordering invariant:** the bot process is the only writer of `feed_posts`,
  and it writes synchronously. Id order is therefore commit order, which is
  what makes `after=<id>` paging gap-free. A future second writer (refresher,
  worker) must break this assumption explicitly, with a `posted_at` cursor,
  not silently.
- **Headline builder** `feed_headline(kind, embed, ticker) -> str`: a table
  from `Kind` to a spoken phrase ("New alert", "Order filled", "Order
  cancelled", "Move stop loss", "Take profit one", "Stopped out", …), plus
  ticker, side and the entry price when the embed or plan carries them. Missing
  pieces are dropped, never spoken as "None". A kind with no table entry falls
  back to its `Kind.label`, lower-cased. Kept table-driven (complexity < 15).
- **Retention, owned by the bot process:** at most once per hour per process,
  the recorder first runs `SELECT 1 ... WHERE posted_at < now() - interval
  '7 days' LIMIT 1`, and deletes only if a row is found. The statement trigger
  fires even on a zero-row `DELETE`, so the check keeps the prune from raising
  an empty `feed` event to every open tab each hour. The hourly gate is an
  in-process timestamp, not a scheduled job.

### 2. Serving it (admin)

- `feed` joins the SSE taxonomy: `EVENT_NAMES` in `frontend/src/app/api/event-stream.ts`
  and the server-side registries above. `tests/admin/test_sse_contract.py` keeps
  both sides in step. A `resync` bumps every event, `feed` included. The
  notifier's fetch-after-last-id makes that harmless: it returns nothing new.
- `GET /api/v1/feed-posts?after=<id>&limit=<n>` (auth required) returns
  `{"items": [{id, posted_at, kind, family, ticker, headline}], "latest_id"}`
  oldest first, `limit` default 20, max 50. `after` omitted returns no items
  and just `latest_id`, which is how a fresh page starts without a backlog.
- `GET /api/v1/feed-posts/kinds` returns the toggleable kinds grouped by
  family with their labels, so the Settings section never hard-codes the
  registry.

### 3. Speaking it (SPA)

- **`VoiceNotifier`** (root service, started by the shell): on start it
  reads `latest_id`; on every `feed` event it fetches `after=<last id>`,
  drops kinds the toggles silence, and queues the headlines on
  `speechSynthesis` one at a time (never overlapping). After an SSE
  `resync`/reconnect it fetches from its last id, so nothing is spoken twice.
  **After a reconnect it speaks at most the 5 newest posts**, followed by "and
  N more" when it skipped any. A long disconnect never turns into a minute of
  speech.
- **Voice chip, one control in the top bar at every width** (phone, tablet and
  desktop alike, never inside a menu, 44 px target, text label beside the icon,
  `aria-label` naming its action). Its states:
  - *Locked* ("Enable voice"): voice is on in Settings but the page hasn't had
    the user gesture browsers require. This happens on **every page load and
    reload**. The chip stays visible until tapped. A tap speaks "Voice
    notifications on" and moves the chip to *Live*.
  - *Live* (speaker icon, "Voice on"): a headline is being spoken or queued, so
    the icon animates. A tap **stops the current headline, clears the queue and
    mutes for this session** (*Muted*, "Voice muted", one tap re-arms).
  - *Blocked*: the browser refused speech even after the tap (`speechSynthesis`
    error, or `speaking` never starting within 2 s). The chip reads "Voice
    blocked" and its tooltip/hint explains how to allow sound for the site.
  - *Unavailable*: the browser has no `speechSynthesis`. The chip reads "No
    voice on this browser" once per session, then hides. Settings says the same.
  - Voice switched off in Settings: no chip.

### 4. Settings → Voice notifications (SPA)

A new section in the System → Settings tab (`workspaces/system/settings-tab.ts`):

A new collapsible block, "Voice notifications", matching the tab's existing
collapsible blocks:

- Master switch "Speak simple-channel posts" (default on). Off greys out and
  disables every switch below it, with the reason shown inline ("Turn on voice
  to choose kinds").
- One group per family (New setup, Entry, Manage, Watch, Result). Each group
  has a family switch and one switch per kind. Every control is a labelled
  `role="switch"` reachable by keyboard. A family switch over a mixed set shows
  an indeterminate state, and toggling it sets every kind in the family to the
  new value. Each kind row shows the Discord label ("FILLED") and, under it in
  plain words, the phrase that will be spoken ("Order filled, <ticker>"), plus a
  small ▶ preview that speaks a sample headline for that kind. Watch is off by
  default. Everything else is on.
- Voice picker: it fills on `voiceschanged` and shows "Loading voices…" until
  then. A stored voice this device doesn't have falls back to the system
  default, with a one-line note. Rate slider 0.8 to 1.4 (default 1.0) with its
  value printed beside it and a 44 px thumb on phone. "Test voice" speaks a
  sample new-alert headline.
- Stored in localStorage under `swingbot.voice.v1` as
  `{enabled, kinds: {<KIND>: bool}, voice, rate}`. Reads are wrapped in
  try/catch, and a missing or garbled value falls back to the defaults. A kind
  added later that isn't in the stored map takes its family default.
- **Three widths:** phone stacks groups in one column with 44 px switch rows;
  tablet two columns; desktop two columns. Labels wrap, never truncate. The
  block and the top-bar chip pass `node frontend/scripts/layout-audit.mjs` at
  phone, tablet and desktop widths (Playwright).

## Testing

- Backend: the recorder writes one row per accepted simple-channel send and
  none when the send raised. It never raises on a database failure, writes
  nothing with `FEED_POSTS_ENABLED` off, and uses the side engine. The prune
  issues no `DELETE` when nothing is old. The migration is rollback-safe
  (`test_rollback_migrations.py`). The history
  fallback isn't recorded. The headline builder covers every `Kind` in the table,
  the label fallback and missing ticker/side/price. The endpoint covers `after`
  paging, the empty case, the `limit` cap, auth and the kinds listing. The prune
  removes only rows older than 7 days. The migration has an upgrade/downgrade
  test. The SSE contract test passes with `feed`.
- Frontend: the notifier skips the backlog at start, speaks in order without
  overlap, honours the master switch and per-kind toggles, resumes from its
  last id after a resync, and stays idle without `speechSynthesis`. The settings
  section covers defaults, persistence, a garbled store, the family switch and
  the "Test voice" button. Layout is checked at phone, tablet and desktop widths.

## Out of scope

- Speaking posts from other channels (history, notify, system).
- Browser push notifications while no tab is open.
- Server-side text-to-speech or any paid voice service.

## Panel review

Run 2026-11-12 on e4846c25. Both seats returned ADVISORY findings only, no BLOCKING.

- ux-designer 1: chip behaviour on every reload and when speech is blocked after the tap -- applied (§3 chip states Locked/Blocked).
- ux-designer 2: undefined "overflow row" on phone, 44 px, aria-label -- applied (chip in the top bar at every width).
- ux-designer 3: switch semantics, indeterminate family switch, master greys children -- applied (§4).
- ux-designer 4: show the spoken phrase per kind, per-kind preview -- applied (§4).
- ux-designer 5: voice picker loading/fallback, rate value and 44 px thumb -- applied (§4).
- ux-designer 6: unavailable state visible outside Settings -- applied (chip state Unavailable).
- ux-designer 7: collapsible block, name the layout audit -- applied (§4).
- ux-designer 8: stop/mute control, cap reconnect speech -- applied (chip Live/Muted; 5-newest cap).
- staff-engineer 1: rollback story, ROLLBACK_SAFE, downgrade -- applied (§1 Rollback).
- staff-engineer 2: the insert must not block the bot loop -- applied (side_engine).
- staff-engineer 3: statement trigger fires on an empty prune DELETE -- applied (check before delete).
- staff-engineer 4: name all three server registries, resync bumps feed -- applied (§1, §2).
- staff-engineer 5: import seams, repository pattern -- applied (repository + presentation + lazy glue).
- staff-engineer 6: kill switch, prune owner -- applied (FEED_POSTS_ENABLED; prune owned by the bot process).
- staff-engineer 7: record inside the try after log_posted, single-writer ordering invariant -- applied (§1).
- staff-engineer 8: UI belongs to ux-designer -- applied (no change; covered above).
