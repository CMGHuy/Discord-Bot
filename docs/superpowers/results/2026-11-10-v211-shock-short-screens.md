# v211 shock-conditioned short screens — summary

**Spec:** `docs/superpowers/specs/2026-11-05-v209-market-shock-detector-design.md` § Track 2
**Plan:** `docs/superpowers/plans/2026-11-06-v211-shock-short-screens_0-index.md`
**Pass rule (frozen, unchanged):** ΔExpR ≥ +0.10R after costs, lower 95 % week-cluster bound > 0, ≥ 7 of 9 years (2011–2019) positive, N ≥ 300 (`docs/claude/backtest-methodology.md` § Stage −2). One shot each.
**Preflight (outcome-blind, committed before shot 1):** `results/2026-11-10-v211-shock-preflight.md`

| Idea | Verdict | N | ΔExpR | 95 % interval | Years positive | Shock weeks | Record |
|---|---|---|---|---|---|---|---|
| `shock_support_break_short` | SCREEN-FAIL | 6545 | -0.3131R | [-0.5259, -0.0732] | 1/9 | 70 | `results/2026-11-10-screen-shock_support_break_short.md` |
| `shock_failed_bounce_short` | SCREEN-FAIL | 8470 | -0.2000R | [-0.3843, -0.0014] | 1/9 | 70 | `results/2026-11-10-screen-shock_failed_bounce_short.md` |

**0 of 2 passed.**

## Printed beside each verdict (never gating)

| Idea | Event arm R | Unconditional control ΔExpR | Shock-day null ΔExpR | 3x slippage ΔExpR | `skipped_overlap` | Gap `>= +1%` ΔExpR (n) | `peak` vs `later` ΔExpR |
|---|---|---|---|---|---|---|---|
| `shock_support_break_short` | -0.1393R | -0.4242R | +0.0416R | -0.3122R | 911 | -0.1438R (1197) | -0.3328R / -0.2402R |
| `shock_failed_bounce_short` | -0.2070R | -0.2011R | -0.0314R | -0.1994R | 973 | -0.0359R (1234) | -0.2061R / -0.1563R |

**Short-family BH q** (every short idea screened so far, `screen_idea.SHORT_SCREEN_IDS`, as printed in shot 2's doc): `v104-b-short-mechanisms` = n/a (no p); `screen-range_breakdown_close` = 0.9996; `screen-shock_support_break_short` = 0.9996; `screen-shock_failed_bounce_short` = 0.9996.

## What the screens can and cannot say (spec § What the screens can and cannot say)

- They test the daily `SHOCK_D` proxy on the point-in-time S&P 500. **A pass does not license the Track 1 detector's labels** (no sector clause, no fast path, no VIX relief, no RECOVERY tier; index membership, not the watchlist).
- The year rule may sink a crash-only edge: the preflight found no year without a shock day and no year with zero events, so no year was empty and the fail does not rest on empty years. A `SCREEN-FAIL` or `SCREEN-UNDERPOWERED` is closed and never re-run with a looser definition.
- The shadow log (plans v209, v210) can motivate a new idea; it can never license one.

## What follows

**Neither passes:** Both definitions are closed: breadth-shock-conditioned breakdown shorts at daily resolution, this frozen `SHOCK_D` (enter 0.40, release 0.10 with `^VIX` down), these two triggers, the fixed 10-bar race, short only. That does not close shorting in a shock in general. Live shock behaviour now needs a new idea that passes its own screen, or the bot's-replay funnel on the live detector; `MARKET_SHOCK_MODE` stays `shadow` and the follow-on spec is not written. No re-run, no looser threshold, no other release rule under these names.

## Binding on any follow-on (partner, 2026-11-06; spec § Track 1, `MARKET_SHOCK_MODE` note)

The focus is SHORT performance, and **LONG issuing works as normal on a bullish day**. Any live behaviour may touch longs only while the label is SHOCK (or RECOVERY, if screened); under NORMAL the long lane stays **byte-identical to `MARKET_SHOCK_MODE=off`**, pinned by a regression test, and the follow-on's screen must show NORMAL-day longs unchanged. Nothing in this plan changed a live path: LONG issuing is byte-for-byte what it was.
