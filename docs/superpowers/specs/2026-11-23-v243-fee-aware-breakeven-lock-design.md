# v243 — Fee-aware break-even lock

**Version:** ui 1.45.0 · bot 2.19.5
**Bump:** bot minor, ui patch
**Edge:** harvest
**Screen:** harvest-headroom docs/superpowers/results/2026-11-23-be-lock-headroom.md
**Panel:** risk-manager, veteran-trader, quant-researcher

## Why

A break-even stop sits exactly on the entry today (`plan_manager.py` sets
`working_stop = entry` once price reaches `breakeven_trigger()`). On a real
broker that is not break-even: Trade Republic charges €1 to open and €1 to
close, so a break-even stop-out loses €2 net. The partner wants the stop to lock
a small real gain instead: after both fees the trade still clears at least 0.1%
of the position's value, and never less than €1. In the partner's words: no
pain, no gain.

## The rule

One pure helper sits next to `breakeven_trigger()` in
`swingbot/core/planning/plan_types.py`. It is the only place the formula lives,
and the live plan manager, the replay exit sim and the order ticket all call it:

```
lock_eur      = 2 × BROKER_FEE_PER_ORDER + max(BE_LOCK_PCT/100 × shares × entry_eur, BE_LOCK_MIN_EUR)
offset_px     = (lock_eur / fx_eur_per_quote) / shares        # per share, quote currency
be_lock_price = entry + sign × offset_px
be_arm_price  = entry + sign × max(breakeven_trigger_fraction × |tp1 − entry|, 2 × offset_px)
```

Worked example (the partner's): 5 shares × €200 gives lock = 2 + max(1, 1) =
€3, so the offset is €0.60 a share and the stop goes to €200.60. A stop-out
there clears €1 net after both fees.

- **Arming.** The stop moves only once price reaches `be_arm_price`: the normal
  trigger, or twice the lock offset, whichever is further from entry. The lock
  then always sits at most halfway between entry and the price that armed it,
  so it is never placed at or through the market. Until then the original stop
  stays.
- **Shares.** These are the alert's sized shares, the size snapshotted onto
  the plan or trade.
- **FX.** Taken at issue time.
- **Stored, not recomputed.** Both prices are computed when the plan is issued
  and stored as optional plan fields `be_lock_price` and `be_arm_price`, added
  to `_OMIT_WHEN_NONE` so existing plan documents stay byte-identical. Arming
  reads the stored fields, so the 60 s loop does no FX lookup.
- **Fallback.** A plan without the fields keeps today's rule (`working_stop =
  entry`, armed at `breakeven_trigger()`) and logs one line naming the reason.
  That covers plans issued before this change, plans with no sized shares, and
  plans whose FX was missing at issue.
- **Settings** (in `.env`, hot-reloaded, section Plan Engine v2):
  `BE_LOCK_ENABLED=true`, a kill switch back to `entry`;
  `BROKER_FEE_PER_ORDER=1.0` (€); `BE_LOCK_PCT=0.1`; `BE_LOCK_MIN_EUR=1.0`.
- **Replay** has no shares or euros. It derives a nominal share count as
  `COMMISSION_RISK_BASIS / |entry − stop|` (the convention `commission_r()`
  already uses), sets FX to 1, and calls the same helper. `exit_sim.py:176`
  (`cur_stop = entry_price if stop_moved`) and its arm test read the helper's
  output, so live and backtest share one formula.
- **Unchanged.** The v39 runner floor at TP1 is untouched. It already sits far
  above the lock, and once TP1 banks, the higher of the two stops wins.

## Outcome and statistics

- A stop-out at `be_lock_price` is booked with its real R and € P&L, outcome
  **`win`**, exit reason **`breakeven_lock`**. The partner wants it counted as
  a win and kept visible as break-even in the statistics.
- Win-rate statistics read the reason and show a split. For example: "Win rate
  54% (of which 6% break-even)" plus a "win rate excl. break-even" figure. The
  journal and the trade tables show a small "BE" badge on those wins.
- Historic `scratch` rows are left as they are. The spec's ship date is the
  comparability break: win rates before and after it are not like for like,
  and the analytics caption names the date.

## Surfaces

- **Alert and trade plan:** a new line, "Break-even → $200.60 (locks +€1 net
  after fees) once price reaches $X". It is omitted on fallback plans.
- **Execution feed:** the MOVE STOP ping carries the lock price. The v81 order
  ticket reads the stored fields.
- **Admin trade detail:** shows the BE lock and arm prices.

Every UI change is checked at phone, tablet and desktop widths (`ui-design.md`).

## Evidence

Live book 2026-07-06..2026-11-23, 1,360 closed trades (`docs/superpowers/results/2026-11-23-be-lock-headroom.md`):
281 armed break-even, 116 stopped there at ~0R. The lock sits a median 0.17R above entry
(fees dominate at the book's sizes), and the 2x-offset arm rule would have delayed 0 of 281 arms.
Net effect: **+18.09R** (strict bound) to **+5.91R** (pessimistic, close day counted as a lock touch),
positive under both. LONG is near flat on the pessimistic bound (+0.55R) -- it rests on the strict bound
being closer to the truth, so the first month live compares lock stop-outs against item-4 style give-ups.

## Tests

- **Helper:** the partner's example (€200.60), the €1 minimum binding, the 0.1%
  binding, a short mirrored, FX conversion, arm = 2 × offset on a small
  position, and zero or missing shares returning "no lock".
- **Plan manager:** arms at `be_arm_price` and not before. A stop-out at the
  lock gives `win` with reason `breakeven_lock`. The kill switch and legacy
  plans fall back to `entry`. The TP1 runner floor still wins after a partial.
- **Replay:** `exit_sim` produces the same lock as the live helper for
  identical inputs.
- **Stats:** the break-even split counts correctly, including the empty case
  and the all-break-even case.
- **Regression:** existing long and short plans (no stored fields) produce
  byte-identical events and documents.
- **Embeds and feed:** the alert line and the MOVE STOP price are covered, and
  a fallback plan shows no line.

## Out of scope

- Per-trade manual share entry (the partner chose the alert's sized shares).
- Recomputing FX live at arm time.
- Changing the break-even trigger fraction. That was closed by evidence on
  2026-11-12.
