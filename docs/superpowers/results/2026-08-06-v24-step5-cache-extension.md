# V24 Step 5 — extending `data/backtest_cache/` to the window end

**Date:** 2026-08-06 · **Task:** plan v8 V24 Step 5 · **Harness:**
`scripts/extend_backtest_cache.py` (new), `tests/test_extend_backtest_cache.py`

V24's window is `1999-01-01 .. 2026-08-03`. The cache did not reach the end of
it, so Step 5 exists to close that gap **without** touching history. This file
records what was written and, more importantly, what was refused.

## Result

All **95** cached tickers now end **2026-08-03**, the window's last bar.

| | files | bars | history |
|---|---|---|---|
| appended | 91 | +3,314 | byte-identical |
| rebased | 4 | +180 net | uniformly rescaled |
| skipped / errored | 0 | — | — |

The cache started in two cohorts, not one: **77 files ended 2026-07-17** (the
V1 bridge from `market_data/daily`) and **18 ended 2025-12-30** (the original
fetch). Both are now level.

## Why a new script instead of `fetch_backtest_data.py --force`

The existing refresh path is all-or-nothing across every ticker and writes with
a bare `df.to_csv(path)`, bypassing `backtest_cache.save_to_disk` — so V43's
`CacheShrinkError` guard never fires on it. At its default `--start 2018-06-01`
it would have silently truncated ~20 years off the deep-history files. The new
script only ever appends, writes atomically (temp file + `os.replace`), re-reads
at full length before the swap, and refuses to shrink.

History is left untouched **by construction, not by inspection**: the append path
copies the original bytes and concatenates only new rows, because a CSV round-trip
through pandas is not byte-stable (`108.07000000000001` → `108.07`). Re-serializing
would have put 27 years through a formatter for no reason and turned a 3.5k-row
extension into a 191k-line diff on a git-tracked cache.

## The two hazards it was built to refuse

**1. Adjustment-basis seams.** `auto_adjust=True` back-adjusts the whole series
relative to *today*, so refetching an already-cached bar can return a different
price than when it was written. Appending today's-basis bars onto an older basis
splices in a gap that never happened. Every ticker's overlap is therefore
re-measured before anything is written, on **both shape and level** — a uniform
offset has spread ≈0 but is still a different basis — and a ticker that does not
reproduce within 0.02pp is skipped.

**2. Mixed conventions in one cache.** This cache is not uniform: 94 of 95 files
are dividend-adjusted, **SPY is raw**. Fetching everything adjusted would rewrite
SPY's entire history onto a different basis — a methodology change wearing a
cache-refresh costume. Each file's convention is detected from its own overlap
and preserved.

## The four rebases, and why they are exact

Four tickers went ex-dividend since they were cached, so their files are a
*uniform* multiple of today's series. Appending would have spliced in a gap-down
that never happened; rebasing rewrites the file onto today's basis, which is
exact — **a uniform rescale leaves every percentage return, and therefore every
R-multiple, unchanged.**

Measured against `HEAD` after the fact, over the full overlap:

| ticker | overlap bars | offset | residual spread | start date | last |
|---|---|---|---|---|---|
| ASML | 6,674 | −0.1292% | 0.00015pp | 2000-01-03 *(unmoved)* | 2026-07-17 → 2026-08-03 |
| PFE | 6,674 | −1.7193% | 0.00025pp | 2000-01-03 *(unmoved)* | 2026-07-17 → 2026-08-03 |
| DELL | 2,492 | −0.1650% | 0.00009pp | 2016-08-17 *(unmoved)* | 2026-07-17 → 2026-08-03 |
| TLT | 1,906 | −0.4012% | 0.00021pp | 2018-06-01 *(unmoved)* | 2025-12-30 → 2026-08-03 |

Residual spread ≤0.00025pp across every one — the rescale is uniform to float
noise, which is what makes returns invariant. **Start dates did not move.** A
`period="max"` refetch reaches back further than this cache deliberately does
(PFE's live history starts in the 1970s against a cache starting 2000-01-03), and
prepending decades would have quietly enlarged the TRAIN window for a handful of
tickers. Rebase clamps to the file's existing first bar.

`--rebase` is opt-in. Without it those four are **skipped**, not merged.

## Integrity sweep after the write

All 95 files re-read and checked for monotonicity, duplicate dates, NaNs,
non-positive prices, and `High < Low`:

- **94 clean.**
- **GC_F** has one `High < Low` row at **2009-11-23**. This is **pre-existing
  upstream data**, present identically in `HEAD` and not introduced here —
  verified by re-running the same check against the committed file.

## What this does not claim

- The extension is a **data** change, not a methodology one, and adopts nothing.
  No gate, parameter, or config moved.
- It does **not** fire V24 Steps 2-4. Step 5 was the prerequisite; the shot itself
  is still gated on an explicit human decision, because V17, V51, V52, V21, V53
  and V54 all terminated with an **empty adopted set** — there is no adopted
  config for the one permitted window reuse to validate.
- Run while no grid was in flight, per Step 5's own constraint (a mid-sweep cache
  change is the confound that invalidated three V17 chunks, `7398e67`).
