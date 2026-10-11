# v152 M0 — notify volume and cooldown estimate (production, read-only)

**Run:** 2026-10-11, `PlanStore().all()` on the Hetzner bot container, window 2026-09-13T00:22:12Z .. 2026-10-11T00:22:12Z (4 weeks).
**Plan:** [v152 index](../plans/2026-10-10-v152-discord-notify-taken-cooldown_0-index.md), task V152-1.

## D1 — notify channel, messages/week per event

| Event | Messages/week | n (4 weeks) | Note |
|---|---|---|---|
| near_stop | ≤ 27.5 | | upper bound: plans filled; fires only in the regular session, once per plan |
| tp1 | 7.2 | 29 | PARTIAL, or CLOSED `win` (no-TP2 plan) |
| tp2 | 3.0 | 12 | CLOSED `tp1_runner_tp2` |
| stopped | 19.8 | 79 | CLOSED in `_STOPPED_REASONS` |
| expired | 0.2 | 1 | CANCELLED other than invalidated / risk_cap |
| closed_other | 16.2 | 65 | measured unconditionally; live posts only with a Following follower |
| **all** | ≤ 74.0 | | structural bound: ≤ 3 per filled plan + 1 per expired plan |

## D3 — scheduled alert posts/week, 24 h `(ticker, direction, horizon_key)` cooldown

| | Posts/week | n (4 weeks) |
|---|---|---|
| before (regular-lane plans) | 39.5 | 158 |
| after the cooldown | 38.2 | 153 |
| held | | 5 |

Most-held keys: `(EBAY, bullish, 3m)`, `(MSTR, bullish, 7m)`, `(GLW, bullish, 2m)`, `(SNPS, bullish, 4w)`, `(ASTS, bullish, 4w)` (1 each).

## Caveats

- Plans pruned before the window start are not counted (oldest `created_at` in store: 2026-07-24 00:00:00+00:00; 564 plans in store).
- `origin is None` is the regular lane; it includes plans created by the admin-UI-triggered scan and `!check` if those persist plans, which the live rule never suppresses — the "after" figure is a lower bound on posts.
- `created_at` date-only rows: 0 in the window, so the 24 h window is not coarse here.
- After launch `alert_posts` measures D3 directly (`outcome = 'suppressed'`).
