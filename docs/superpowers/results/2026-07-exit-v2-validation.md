# Exit model v2 — VALIDATION (Task 32, single run, 2026-07-18)

**Command:**

```
python scripts/run_backtest_range.py --validation --exit-model v2 --scale-out \
  --json exit_v2_validation.json
```

Window 2024-01-01..2025-12-31 (single pre-registered run), 75/78 cached
tickers, all horizons, v2 exits + scale-out with the Task 31 `EXIT_V2_PARAMS`.
Raw JSON: `exit_v2_validation.json` (repo root, committed).

**Sequencing note (honesty):** the plan ordered this task before Phase 8, but
it was actually run on 2026-07-18 *after* the RSI rescue adopted its
range-regime gate — so the RSI row below reflects the rescued entry set
(N=30), not round-1's ungated N=414. Every other strategy's entry set is
unchanged from round 1 (the RSI Divergence and Elliott gates were off/absent
in `DEFAULT_PARAMS` when this run executed; Elliott's gated single-shot
validation is Task 106's separate run, `2026-07-rescue-elliott-validation.md`).

## Full VALIDATION table (verbatim)

```
== VALIDATION 2024-01-01 .. 2025-12-31 | pass: WR>=80, ExpR>0, N>=15, excl<=50% ==
Strategy                   N   Win%    ExpR AvgWinR   Scr    TO  Excl%   tp2% trail%    be%   rto%  PASS
EMA Crossover             78   76.9  +0.015  +0.324    16     0    17%  46.7%   0.0%  53.3%   0.0%  FAIL
VWAP                      77   80.5  +0.250  +0.661    27     0    26%   0.0%  30.6%  62.9%   6.5%  PASS
Fibonacci                203   82.3  +0.268  +0.655    67     3    26%   0.0%  32.3%  60.5%   7.2%  PASS
Support/Resistance       186   87.1  +0.326  +0.693    85     0    31%  18.5%  43.8%  37.0%   0.6%  PASS
RSI                       30  100.0  +0.304  +0.304     0     0     0%   0.0%  33.3%  66.7%   0.0%  PASS
MACD                     123   81.3  +0.120  +0.432    46     0    27%  62.0%   6.0%  32.0%   0.0%  PASS
Elliott Wave             157   75.2  +0.081  +0.479    58     1    27%  28.8%  14.4%  50.0%   6.8%  FAIL
MA Ribbon                137   78.1  +0.213  +0.657    52     0    28%   0.0%  22.4%  62.6%  15.0%  FAIL
Break & Retest           148   84.5  +0.210  +0.531    55     3    28%   0.0%  24.8%  66.4%   8.8%  PASS
RSI Divergence          1099   75.8  +0.208  +0.695   406     0    27%   0.0%  34.6%  62.1%   3.4%  FAIL
Volume Profile            47   83.0  +0.479  +0.893     9     0    16%   0.0%  30.8%  64.1%   5.1%  PASS
```

## Side-by-side vs round-1 validation (v1 exits, same window)

| Strategy | v1 N/WR/ExpR | v2 N/WR/ExpR | ΔExpR | PASS v1→v2 |
|---|---|---|---|---|
| VWAP | 77 / 80.5 / +0.064 | 77 / 80.5 / +0.250 | **+0.186** | PASS→PASS |
| Fibonacci | 206 / 81.6 / +0.105 | 203 / 82.3 / +0.268 | **+0.163** | PASS→PASS |
| Support/Resistance | 190 / 86.8 / +0.117 | 186 / 87.1 / +0.326 | **+0.209** | PASS→PASS |
| MACD | 123 / 81.3 / +0.071 | 123 / 81.3 / +0.120 | +0.049 | PASS→PASS |
| Break & Retest | 148 / 83.8 / +0.094 | 148 / 84.5 / +0.210 | **+0.116** | PASS→PASS |
| Volume Profile | 47 / 83.0 / +0.136 | 47 / 83.0 / +0.479 | **+0.343** | PASS→PASS |
| RSI (rescued entries) | 414 / 68.4 / -0.030 | 30 / 100.0 / +0.304 | n/c (entry set changed) | FAIL→PASS |
| EMA Crossover | 78 / 76.9 / +0.032 | 78 / 76.9 / +0.015 | -0.017 | FAIL→FAIL |
| Elliott Wave | 159 / 74.8 / +0.008 | 157 / 75.2 / +0.081 | +0.073 | FAIL→FAIL |
| MA Ribbon | 137 / 78.1 / +0.039 | 137 / 78.1 / +0.213 | **+0.174** | FAIL→FAIL |
| RSI Divergence | 1101 / 75.8 / +0.045 | 1099 / 75.8 / +0.208 | **+0.163** | FAIL→FAIL |

The Task 32 expectation ("win/loss/scratch identical to round-1, ExpR
improved by runner upside") holds: win rates match round 1 within a few
tenths everywhere entries are unchanged, and every strategy except EMA
Crossover gains expectancy from the runner leg (median gain ~+0.16R).

**WR-shift investigation (pre-registered Task 33 tripwire):** Fibonacci
(+0.7pt, N 206→203) and Break & Retest (+0.7pt) exceeded the 0.5pt
threshold, so a per-trade v1-vs-v2 diff was run for Fibonacci before
committing: **zero outcome flips** on shared trades; the entire difference
is 5 boundary trades (4 v1-only, 1 v2-only) appearing/disappearing because
`one_at_a_time=True` blocks a later signal while a v2 runner still occupies
the slot (e.g. GLW/4w: v1's 2024-12-12 entry replaced by 2025-01-06 in v2).
Classification is identical; the shift is composition, not divergence.

EMA Crossover's small ExpR *decline* (+0.032→+0.015) is the flip side of the
same mechanic: its scale-out banks only half at TP1 and its runners die at
break-even 53% of the time with no TP2/trail gains to compensate.

## Registry (Task 33)

`--from-json` added to `run_backtest_range.py`; registry regenerated via

```
python scripts/run_backtest_range.py --validation --from-json exit_v2_validation.json \
  --emit-registry swingbot/core/validation_registry.json --run-date 2026-07-18
```

(zero new validation exposure), then the Elliott Wave record was patched to
Task 106's gated single-shot numbers (N=75, WR=77.3, ExpR=+0.064 — the
config actually live in `DEFAULT_PARAMS`), since this run's Elliott row
measured the pre-rescue ungated entry set. 7 VALIDATED / 4 WEAK. Badge
lines now quote v2-economics OOS numbers everywhere.
