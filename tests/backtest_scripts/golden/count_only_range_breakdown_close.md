[range_breakdown_close] 2/2 tickers (100%)
# v182 count: `range_breakdown_close` (outcome-blind: no race, no R)

**Window:** 2010-01-01..2019-12-31 (events from 2011-01-01). **Universe:** 2 PIT S&P 500 members, 2 counted, 0 missing from the cache, 0 empty frames.
**Idea:** short, entry next_open, fixed race, cap 20 bars.
**Command:** `python scripts/backtest/screen_idea.py --idea range_breakdown_close --count-only`

| step | events |
|---|---:|
| raw events | 5 |
| dropped_nonmember | 0 |
| dropped_warmup | 0 |
| dropped_window | 0 |
| skipped_overlap (full-cap bound) | 2 |
| dropped_no_match | 1 |
| **count N** | **2** |

Non-overlap here assumes every trade lasts the full 20-bar cap, so the real run books at least as many events before the null match.

**Gate:** N = 2 < 300: no run, no ledger row; report to the partner.

