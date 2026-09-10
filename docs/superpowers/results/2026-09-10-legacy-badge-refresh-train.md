# Legacy strategy badge refresh — TRAIN check (2026-09-10)

**Edge: none (integrity).** Fibonacci, RSI, and Support/Resistance carried a
`VALIDATED` registry badge (`run_date: 2026-07-18`) computed under the fixed
per-strategy reward:risk table that plan v31 deleted on 2026-08-17
(`docs/superpowers/results/2026-08-17-structural-target-train.md`,
`docs/superpowers/results/2026-08-17-structural-target-validation.md`). v31's
own TRAIN grid already covered these three and found no qualifying cell, but
their VALIDATED badges were left in place, flagged as describing "deleted
arithmetic" rather than corrected. This measurement resolves that flag.

## What ran

Free, repeatable Stage 0/1 TRAIN check only — no VALIDATION budget spent, per
`docs/claude/backtest-methodology.md`'s funnel ("a config that fails train
never gets a validation shot"). Full cached universe (77 tickers, 2 excluded
illiquid per Task E12), TRAIN window 2020-01-01..2023-12-31, current live
defaults (`--exit-model v2 --scale-out`), badge threshold explicit
(`--pass-wr 50`, since the script's own default is the stale pre-v31 80
floor):

```
python scripts/backtest/run_backtest_range.py --train --strategy "<name>" \
  --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10
```

## Result

| Strategy | N | Win rate | ExpR | Excl% | PASS? |
|---|---|---|---|---|---|
| Fibonacci | 246 | 35.4% | +0.232 | 30% | FAIL (win rate) |
| RSI | 38 | 23.7% | −0.120 | 52% | FAIL (win rate, ExpR, excl%) |
| Support/Resistance | 247 | 45.7% | +0.316 | 29% | FAIL (win rate) |

All three fail the `win_rate >= 50` badge clause by a wide margin under
today's dynamic reward:risk band (`MIN/MAX_RISK_REWARD_RATIO` = 1.5/2.5).
None qualify for a VALIDATION look. **These numbers corroborate v31's own
TRAIN grid to within rounding** (Fibonacci 36.1%, Support/Resistance 45.6%,
RSI 23.7% — an exact match) — this is confirmation, not new noise.

## What changed

`swingbot/core/backtesting/validation_registry.json` rows for Fibonacci, RSI,
and Support/Resistance were re-emitted honestly as `WEAK`, `window:
2020-01-01..2023-12-31`, `run_date: 2026-09-10` (registry schema supports a
TRAIN-window badge; `N>=30` train / `N>=15` validation is exactly why). This
is a same-key merge (`source`, `strategy`, `horizon`) — the stale
pre-v31 VALIDATED rows are replaced, not appended alongside.

**Registry now stands at 2 VALIDATED (MACD, Volume Profile), 9 WEAK**
(Break & Retest, EMA Crossover, Elliott Wave, Fibonacci, MA Ribbon, RSI,
RSI Divergence, Support/Resistance, VWAP).

## Not touched

- No production code or config changed — this is a data-only registry
  correction.
- The four strategies already closed as "permanently WEAK" from the
  2026-07-18 rescue phase (EMA Crossover, Elliott Wave, MA Ribbon, RSI
  Divergence) and the two closed under v31 (Break & Retest, VWAP) are
  untouched — reopening any of those still needs a genuinely new mechanism,
  not this refresh.
- Whether any of Fibonacci/RSI/Support-Resistance deserves a *new*
  pre-registered rescue hypothesis (the way RSI's range-regime gate was
  rescued in round 2) is a separate, unstarted question.
