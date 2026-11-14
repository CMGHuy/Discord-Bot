---
name: alert-surface
description: "Use when editing the alert surface -- swingbot/core/scanning/scan_run.py's alert-building loop, alert_embeds.py, lifecycle_embeds.py, plan_table.py, the embeds.py/engine.py facades, or anything rendering or sending a Discord alert or trade plan. This area has two OHLCV caches, wiring points that silently no-op, and empty tables that are measured answers rather than stubs. Not for chart image generation and not for the admin UI."
---
<!-- GENERATED from .claude/skills/alert-surface/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Alert surface

## Step 1 — Read the authority

```bash
python scripts/dev/doc_section.py docs/claude/known-traps.md "Two OHLCV caches" "Full-history cache" "Legacy shims" "Measured-empty tables" "Scan parameter and replay gate parity" "The market_data cache never self-heals"
```

Those sections of `docs/claude/known-traps.md` are the shortest path to not
breaking this area.
**Whole file instead when:** changing where sizing or embed-building is wired,
or how a message is sent.
Exit code 2 from `doc_section.py` means read the whole file. This skill does
not restate any of it; nothing here substitutes for reading it.

**Where the code actually is.** `embeds.py` and `engine.py` are re-export
facades -- edit the module behind them: `alert_embeds.py` (`build_embed`,
`build_simple_alert`), `lifecycle_embeds.py` (closed / near-close / plan-event
embeds), `plan_table.py` (plan rows, sizing snapshot), and `scan_run.py`
(`_sync_run_scan`'s alert-building loop). The old `core/scan_embeds.py` /
`core/scan_engine.py` shims are deleted; do not look for them.

## Step 2 — An empty table is an answer

Before "fixing" a blank section in a rendered alert or trade plan, find out
whether it is measuring zero. Filling it with a placeholder destroys a real
result.

## Step 3 — Which cache?

There are two OHLCV caches with different freshness. Name which one your
change reads before you change it.

## Step 4 — Confirm the edit is live

Some wiring points here accept a change and do nothing: sizing added in
`commands/scanning/alerts.py::_send_alerts` (it only posts already-built
tuples), a raw `embed.add_field()` instead of the `sections[...]` accumulator,
or a bare `send(embed=...)` that drops the push-preview line. After the change,
verify the rendered output differs, not just that the function was called.

## The gate

A rendered before/after, not a passing unit test alone. Produce the actual
alert or trade-plan output on both sides of the change and diff it -- a green
suite that never renders the surface it claims to fix proves nothing here.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The table is empty, so it is a stub" | It may be the measured answer to a closed pre-registration -- check `docs/superpowers/results/` before filling it in. |
| "The function returned without error" | A change wired into the wrong layer also returns without error. Absence of an exception is not evidence the call did anything. |
| "I'll edit `embeds.py`" | It is a 23-line re-export facade; the builder lives in `alert_embeds.py` / `lifecycle_embeds.py` / `plan_table.py`. |
| "The cache looked stale, so I cleared both" | The two caches serve different consumers at different freshness by design; clearing the wrong one degrades a working path to fix a broken one. |
| "It's just a copy edit on the embed text" | Field order and grouping route through a shared accumulator, not raw field calls -- a hand-added field silently breaks that ordering. |
| "I'll post to the simple channel from a new sender" | Only `commands/scanning/alerts.py::_mirror` and the feed branch of `lifecycle_embeds._send_instruction` post there, and each calls `record_feed_post` right after `log_posted`, inside the `try` (v227). A new simple-channel sender without it never reaches bomeo-capital.com's voice notifications; a call outside the `try` speaks posts Discord refused. `FEED_POSTS_ENABLED=false` silences the site without touching Discord. |

## Trigger table

Should fire: editing a field, section or copy in `embeds.py` or `alert_embeds.py`.
Should fire: changing what `swingbot/core/scanning/scan_run.py`'s alert-building
loop passes into the embed.
Should fire: adding a new field to a Discord alert or trade-plan message.
Should not fire: editing a chart image renderer under `swingbot/core/charts/`.
Should not fire: changing an Angular component under `frontend/`.
Should not fire: changing a strategy's entry-signal logic under
`swingbot/core/edge/` (use `edge-module`).
