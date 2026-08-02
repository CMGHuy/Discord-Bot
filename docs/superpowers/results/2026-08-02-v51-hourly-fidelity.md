# V51 Step 4 — daily-vs-hourly exit fidelity, and the error bar V52 must carry

**Measured 2026-08-02** with `scripts/hourly_fidelity_replay.py` (the harness
V23 Step 1 will reuse).

## The question

Every backtest here walks **daily** bars. A daily bar cannot say which of the
stop and the target was touched first when it spans both, so the exit walk
always checks the stop first — a *convention*, not a measurement. This replays
the same trades on hourly bars, where the sequence is mostly observable.

- Window **2023-08-25 .. 2023-12-31** — the entire overlap between
  `market_data/hourly/` (starts 2023-08-25) and TRAIN (ends 2023-12-31).
  ~612 hourly bars/ticker, ~87 trading days, 7 bars/day.
- 77 tickers with both feeds; horizons **2w, 4w, 2m** only — 3m+ cannot resolve
  inside 87 days and would score as timeouts by construction.
- Entries held **identical** across both runs (entry, stop, TP1 copied from the
  daily trade). This compares exits only.
- **145 replayed trades.**

## Result

| | |
|---|---|
| Outcome agreement | **101 / 145 = 69.7%** |
| **Disagreement rate** | **30.3%** |
| Mean R, daily | **+0.631** |
| Mean R, hourly | **+0.313** |
| **Daily overstatement** | **+0.318R per trade** |

Flips (daily → hourly): `scratch→win` 14, `loss→scratch` 9, `loss→win` 8,
`win→scratch` 8, `scratch→loss` 4, `win→loss` 1.

## The trail confound, found and removed

A first pass reported −0.391R. That number was **partly an artifact**: the walk
trails by `trail_atr_mult × ATR(14)` computed on whatever bars it is handed, and
ATR(14) on hourly bars is a fraction of ATR(14) on daily. A raw hourly replay
therefore trails several times tighter and stops the runner out sooner — a
**different exit policy**, not a finer view of the same one.

Rescaling the multiple by (daily ATR / hourly ATR) at entry holds the policy
fixed and moves the gap to **−0.318R**, so about 19% of the original gap was the
artifact and the rest is real. `--raw-trail` reproduces the unscaled run.

Diagnostic worth keeping: rescaling changed **no outcome at all** (101/145 both
ways). Under scale-out the outcome class is decided in phase 1 — which barrier
is reached first — which the trail cannot touch. **So the 30.3% is a clean
phase-1 fidelity result, and only the R gap was ever confounded.**

## What actually drives the disagreement

Not the textbook same-bar case. Daily bars spanning **both** barriers occur in
only 7 of 145 trades (4.8%), and hourly disagreed on 1 of those.

The flip pattern points at the **breakeven trigger** instead: `scratch↔win` and
`loss↔scratch` are 35 of the 44 flips. On hourly bars a trade can reach the BE
trigger and retrace to entry *inside a single daily bar* — a sequence the daily
walk structurally cannot see, so it reports a clean win or loss where the real
path was a scratch (and vice versa).

**So the resolution problem is broader than stop-vs-target ordering.** It is
intra-bar *sequencing* of trigger-then-retrace, and it moves ~30% of outcomes.

> **Known undercount.** The 4.8% figure checks each trade's segment against its
> ORIGINAL stop only. It does not test the moved breakeven stop, which the flip
> pattern says is the dominant mechanism — so the true ambiguity rate is higher
> than 4.8% and that row should not be quoted as "the" ambiguity rate. Fixing it
> means tracking the BE move per bar inside the replay; deferred to V23, which
> owns the wider run.

## What V52 must carry

1. **A 30.3% outcome-disagreement error bar on every win-rate number.** A cohort
   measured at 70% on daily bars is not distinguishable from one in the low 60s
   or high 70s on this evidence alone. Against an 80% bar with rungs 10 points
   apart, **that error bar is wider than the gaps the ladder is trying to
   resolve.**
2. **Daily expectancy is optimistic by ~0.318R.** V51 Step 2 established that
   break-even swings between 41.2% and 58.3% depending entirely on runner
   performance; this says the daily replay flatters exactly that quantity. A
   daily-measured +0.35R cohort could be near zero in reality.
3. Adopt nothing on daily evidence alone where the margin is under ~0.3R.

## Caveats, stated rather than buried

- **N=145 is small** and comes from one 4-month window in a single regime
  (late 2023). This bounds the error, it does not characterise it.
- Only 2w/4w/2m. Longer horizons are the ones V17 grids hardest, and they are
  **untested** here because the hourly window cannot hold them.
- 7 hourly bars/day assumed for the holding-period conversion.
- `STRATEGY_GATES` makes most strategies bullish-only, so shorts are barely
  represented.
- Yahoo's ~730-day intraday depth is a hard ceiling (V23 Step 3). The window
  cannot be widened backwards, ever — this is the most fidelity evidence that
  will ever exist for a TRAIN-window claim.

## Reproduce

```
python scripts/hourly_fidelity_replay.py --horizons 2w,4w,2m --json out.json
python scripts/hourly_fidelity_replay.py --horizons 2w,4w,2m --raw-trail   # confounded
```
