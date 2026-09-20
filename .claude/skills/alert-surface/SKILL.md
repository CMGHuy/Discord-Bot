---
name: alert-surface
description: Use when editing the alert surface -- swingbot/core/scanning/engine.py, scan_embeds, embeds.py, or anything rendering a Discord alert or trade plan. This area has two OHLCV caches, legacy shims that silently no-op, and empty tables that are measured answers rather than stubs. Not for chart image generation and not for the admin UI.
---

# Alert surface

## Step 1 — Read the authority

`docs/claude/known-traps.md`, in full -- it is the shortest path to not
breaking this area. This skill does not restate any of it; nothing here
substitutes for reading it.

## Step 2 — An empty table is an answer

Before "fixing" a blank section in a rendered alert or trade plan, find out
whether it is measuring zero. Filling it with a placeholder destroys a real
result.

## Step 3 — Which cache?

There are two OHLCV caches with different freshness. Name which one your
change reads before you change it.

## Step 4 — Confirm the edit is live

Legacy shims here accept a call and do nothing. After the change, verify the
rendered output differs, not just that the function was called.

## The gate

A rendered before/after, not a passing unit test alone. Produce the actual
alert or trade-plan output on both sides of the change and diff it -- a green
suite that never renders the surface it claims to fix proves nothing here.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The table is empty, so it is a stub" | It may be the measured answer to a closed pre-registration -- check `docs/superpowers/results/` before filling it in. |
| "The function returned without error" | A silently no-op shim also returns without error. Absence of an exception is not evidence the call did anything. |
| "The cache looked stale, so I cleared both" | The two caches serve different consumers at different freshness by design; clearing the wrong one degrades a working path to fix a broken one. |
| "It's just a copy edit on the embed text" | Field order and grouping route through a shared accumulator, not raw field calls -- a hand-added field silently breaks that ordering. |

## Trigger table

Should fire: editing a field, section or copy in `embeds.py`.
Should fire: changing what `swingbot/core/scanning/engine.py`'s alert-building
loop passes into the embed.
Should fire: adding a new field to a Discord alert or trade-plan message.
Should not fire: editing a chart image renderer under `swingbot/core/charts/`.
Should not fire: changing an Angular component under `frontend/`.
Should not fire: changing a strategy's entry-signal logic under
`swingbot/core/edge/` (use `edge-module`).
