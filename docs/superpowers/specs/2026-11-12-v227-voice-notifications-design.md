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
  `ticker text NULL`, `headline text NOT NULL`. Index on `posted_at`. A NOTIFY
  trigger on insert raises the new `feed` concern, following
  `p3_007_notify_triggers.py`.
- **Recorder** `record_feed_post(embed, ticker, kind=None)` in a new
  `swingbot/core/infra/feed_posts.py`, beside `posted_log.py`. It resolves the
  kind exactly as `log_posted` does, builds the headline, inserts one row and
  **never raises**: a failure goes to `swallowed(...)` so a database hiccup
  cannot abort a Discord send.
- **Call sites: only the simple-channel sends, after Discord accepted them**:
  `commands/scanning/alerts.py:_mirror` (new setups, tickets, strategy mirrors)
  and the feed branch of `core/scanning/lifecycle_embeds._send_instruction`
  (fills, cancels, stop moves, TP1, results, near-stop/TP). The history-channel
  fallback copy is **not** recorded: that isn't a simple-channel post.
- **Headline builder** `feed_headline(kind, embed, ticker) -> str`: a table
  from `Kind` to a spoken phrase ("New alert", "Order filled", "Order
  cancelled", "Move stop loss", "Take profit one", "Stopped out", …), plus
  ticker, side and the entry price when the embed or plan carries them. Missing
  pieces are dropped, never spoken as "None". A kind with no table entry falls
  back to its `Kind.label`, lower-cased. Kept table-driven (complexity < 15).
- **Retention:** rows older than 7 days are pruned by the recorder at most
  once per hour (cheap `DELETE ... WHERE posted_at < now() - interval '7 days'`).

### 2. Serving it (admin)

- `feed` joins the SSE taxonomy: `EVENT_NAMES` in `frontend/src/app/api/event-stream.ts`
  and the server-side concern list. `tests/admin/test_sse_contract.py` keeps
  both sides in step.
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
  `resync`/reconnect it fetches from its last id, so nothing is spoken twice
  and a long disconnect speaks at most `limit` posts.
- **Unlock:** browsers refuse speech until the page gets a user gesture. When voice is
  enabled and not yet unlocked this session, the shell shows a small
  "Enable voice" chip (speaker icon). One tap speaks a short "Voice
  notifications on" and hides the chip. On phone it sits in the top bar's
  overflow row. On tablet/desktop it sits in the top bar.
- **Browser without `speechSynthesis`:** the Settings section says voice is
  unavailable on this browser, and the notifier stays idle.

### 4. Settings → Voice notifications (SPA)

A new section in the System → Settings tab (`workspaces/system/settings-tab.ts`):

- Master switch "Speak simple-channel posts" (default on).
- One group per family (New setup, Entry, Manage, Watch, Result), each with a
  family switch and one switch per kind, labelled with the Discord label
  (e.g. "FILLED", "CANCEL ORDER"). Watch is off by default; everything else is on.
- Voice picker (the browser's voices, default the system voice), rate slider
  (0.8 to 1.4, default 1.0), and a "Test voice" button.
- Stored in localStorage under `swingbot.voice.v1` as
  `{enabled, kinds: {<KIND>: bool}, voice, rate}`. Reads are wrapped in
  try/catch, and a missing or garbled value falls back to the defaults. A kind
  added later that isn't in the stored map takes its family default.
- **Three widths:** phone stacks groups in one column with 44 px switch rows;
  tablet two columns; desktop two columns beside the existing settings layout.
  Labels wrap, never truncate.

## Testing

- Backend: the recorder writes one row per accepted simple-channel send and
  none when the send raised. It never raises on a database failure. The history
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
