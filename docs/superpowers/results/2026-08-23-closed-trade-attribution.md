# v50 — Closed-trade attribution: measurement result

**Plan:** `docs/superpowers/plans/2026-08-22-v50-closed-trade-attribution.md`
**Measured:** 2026-08-23, commit `ac80ae7`
**Instrument:** `metrics.exit_reason_split`, `metrics.hold_by_outcome`
**Outcome: the instrument is built, tested and wired into the weekly digest.
Neither statistic could be measured — this checkout has no closed-trade
record. See "What the record actually is".**

The plan called the measurement the deliverable and the code the instrument.
The instrument works; there is nothing here to point it at. That is the
result, and it is written down rather than substituted for.

## What the record actually is

`PerformanceTracker` reads `data/trades.json` (`tracking/performance.py:218`).
**That file does not exist** — not in `data/`, not in any worktree, not in
`data/backups/`. `find . -name trades.json` returns nothing. Whatever live
paper-trade history exists lives on the deployed container, not in this
checkout.

The only trade-shaped file present is `data/journal.json`, 89 entries spanning
2026-08-06 → 2026-08-23. It is a different schema and it cannot stand in:

| Field the statistics need | Entries carrying it |
|---|---|
| `close_reason` (or a `legs[-1].reason`) | **0 of 89** |
| `entry` + `stop_loss` + `exit_price` (for `r_multiple`) | **0 of 89** |
| `status` | 0 of 89 — the journal's field is `outcome` |
| non-zero `holding_days` | **1 of 89** |

## What the two statistics say over it anyway

Run unmapped, as the digest would run them:

    exit_reason_split -> other: n=89 (100%), total_r 0.0, avg_r None
                         every other reason n=0
    hold_by_outcome   -> all None, n_winners 0, n_losers 0

Run with `outcome` force-mapped onto `status` (not something the code does —
done only to see whether anything is recoverable):

    exit_reason_split -> other: n=89 (100%), win_rate 18.9%
    hold_by_outcome   -> winners 3.78d (n=14), losers 0.0d (n=60), ratio 0.00x

Both are artefacts of the record, not findings about the bot:

- **100% "other"** is exactly the signal that bucket was designed to give — no
  entry here carries an exit reason at all.
- **losers 0.0d** is 88 of 89 entries having `opened_at == closed_at` to the
  millisecond. A single winner carries the only real hold (52.94d), which is
  the whole of the 3.78d winner average. A ratio of 0.00x labelled `low` is
  arithmetically correct over that input and means nothing about exit design.

**Neither number should be quoted.** The disposition ratio for this bot is
unmeasured.

## One finding that does not need the record

Rendering the digest against a mixed fixture surfaced a real vocabulary gap:
`plan_engine.py:1266` emits `close_reason = "breakeven_stop"`, and
`EXIT_REASONS` — frozen by this plan's Task 1 — does not contain it, so those
closes land in `other`. `plan_engine.py:1338` likewise emits
`"runner_timeout"`, which reaches the `timeout` bucket via `resolve_outcome`
rather than by name.

Left as-is deliberately. The list was pre-registered, a non-empty `other` is
the designed signal rather than a bug, and widening the vocabulary mid-plan
would have destroyed the evidence that it needed widening.

## What would make this measurable

A `data/trades.json` with real closes — either pulled off the deployed
container or accumulated by running the bot. A backtest-derived population
would answer a **different** question (the plan engine's exit distribution over
historical replay, not the live paper record) and was deliberately not
substituted for it.
