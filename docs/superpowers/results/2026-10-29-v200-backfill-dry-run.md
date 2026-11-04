# v200 Discord issue-time backfill: dry run, 2026-11-04

Read-only. Script `scripts/ops/backfill_issued_at_discord.py` (this commit), run in the bot container
over REST against DISCORD_CHANNEL_TRADES_ID (never the simple mirror), messages 2026-07-01..2026-09-16 ET.

## Result
- Plans without issued_at, created 2026-07-01..09-16: 417 (of 436 plans created in the window)
- Matched: 370 of 417 (88.7%) -- exact 370, key 0
- Ambiguous (left unknown): 27; no candidate: 20
- Messages read 4728, parsed as alerts 1933
- Lag hours (00:00 ET on the bar date to the post): min 9.63, p25 10.85, median 13.07, p75 16.15, max 109.09
- One-to-one check: no message matched twice

## Embed layouts seen
- July 2026: title `<chips> 🟢 LONG (buy) — TICKER` / `🔴 SHORT (sell) — TICKER`, fields `Setup` and
  `Swing type`. The first draft parser missed the `(buy)`/`(sell)` order word; fixed test-first
  (`test_alert_key_reads_the_july_layout_with_the_order_word`).
- From 2026-07-19: the footer carries `plan <8 chars>`, so almost every plan resolves by exact id; no
  match needed the ticker/direction/strategy/horizon key.
- Every sampled `Swing type` label (1-2 week, 4-week, 2-month, 3-month, 6-month) mapped through
  `HORIZON_LABEL_TO_KEY`; no historical labels were needed.
- Sampled unparsed messages are non-alert posts (no embed title).
- Plan fields live in table columns (`ticker`, `strategy`, `horizon_key`, `created_at`), only
  `direction` in the doc; the first draft query read them from the doc and found 0 plans, fixed.

## Outliers
No negative lag. 15 matched plans lag above 72 h (plan prefixes): 06ab29ba 76.8, 10bcc3e5 84.1,
15d9da26 76.2, 457467f3 76.2, 54892ada 103.4, 76cd6319 109.1, 93428e99 79.3, 9e3e7573 105.2,
a60b02b6 78.9, b8b914cc 107.4, c5d811f5 100.5, d556ae41 79.5, d87990e7 78.8, eccb6940 76.7,
f24910ba 79.3. All are exact plan-id matches; the long lags are a plan whose bar date precedes a
weekend or holiday gap before its post.

## Decision needed
The partner decides whether V200-7 pins these 370 matches in revision v200_001.
The raw CSV stays in the scratchpad (`v200_backfill.csv`) and is never committed.
