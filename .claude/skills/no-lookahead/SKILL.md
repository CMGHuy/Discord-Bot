---
name: no-lookahead
description: Use when editing or reviewing entry-signal, feature or indicator computation under swingbot/core/market/, swingbot/core/edge/, swingbot/core/scanning/ or swingbot/core/planning/ -- anything that decides what a bar knew at the time. Catches lookahead bias, which inflates every downstream backtest silently. Not for chart rendering, embeds, admin UI or persistence code.
---

# No-lookahead

## Step 1 — Read the authority

`docs/claude/architecture.md` for the NO-LOOKAHEAD rule itself and the
entry-signal single source both the live scanner and the backtest read from.
Then `docs/claude/known-traps.md` for the two OHLCV caches, which is where a
lookahead bug usually enters — a feature computed against the wrong one sees
a bar it should not yet know about. This skill does not restate either.

## Step 2 — Name the bar

For the value you are computing, state which bar index it is allowed to see
and which it is not, in one sentence. If you cannot say it in one sentence,
the function is doing two things — split it before touching the lookahead
question at all.

## Step 3 — Trace the shifts

Every rolling window, `shift`, `resample` and merge on a datetime index is a
place a future value can leak backwards. Walk each one in the diff against
Step 2's sentence: does this operation's output at bar *k* depend on any
input dated after bar *k*? A centred or two-sided operation almost always
answers yes.

## Step 4 — Prove it with a truncation test

Compute the feature over the full series, then again over the same series
truncated at bar *k*. The value at bar *k* must be identical between the two
runs. A feature whose value at *k* changes once the future is removed was
reading it — that is the whole test, and it needs no market opinion to run.

## The gate

Pass means the truncation test exists, is committed alongside the feature it
covers, and passes. Reasoning through the shifts by eye in Step 3 is how you
find the bug; the truncation test is what proves you found all of it.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "It only reads the close of the same bar" | The scanner runs intrabar — that close is not settled yet when the signal fires live. |
| "The backtest agrees with live" | Agreement is not proof; both paths can read the identical leak and confirm each other. |
| "It's a centred window, but a small one" | Centred is lookahead by construction, regardless of width — smallness only shrinks the leak, not its existence. |
| "It's just a rolling mean, those are safe" | Only if the window is trailing-only; check which side `.rolling()`/`.resample()` was called with, don't assume from the function name. |

## Trigger table

Should fire: adding a new indicator or feature column to `market/signals.py`
or `edge/factors.py`.
Should fire: changing a `resample` rule or bar-aggregation step anywhere
under `core/market/` or `core/scanning/`.
Should fire: reviewing a pull request that touches `entry_filters.py` or a
strategy's entry gate.
Should not fire: editing `scanning/embeds.py` or another presentation-layer
file with no feature math.
Should not fire: changing Discord message copy or an embed field label.
Should not fire: renaming a config field in `.env`/`config.py` with no change
to what data a computation reads.
