# Edge Engine pre-mortem (Task E95)

It is 12 months from now and the system failed. Not "underperformed" —
failed: the account is materially smaller, or the operator stopped
trusting it and turned it off. What killed it? This is written in advance,
honestly, so that when one of these actually starts happening it's
recognized instead of rationalized.

## Killer 1: Regime break — the edge was 2018–2023-shaped

Every strategy in `swingbot/core/registry.py`'s validation registry was
validated on 2020-2023 (TRAIN) and 2024-2025 (VALIDATION) data — six years
that included a specific character: a 2020 crash-and-V-recovery, a 2022
bear market, and a 2023-2025 bull run. If the market's future regime looks
nothing like that mixture (a decade-long grind, a structural volatility
regime shift, correlations across the whole watchlist going to 1), a
strategy that cleared every gate on 2018-2023 data can keep posting
alerts that no longer have real edge, and nothing in the live scan path
stops to ask "does this still work?" on its own.

**Tripwire:** the quarterly re-validation ritual
(`scripts/backtest/quarterly_revalidation.py`, Task E96) exists specifically to
catch this — it re-runs the fold sweep and permutation test every quarter
and prints a PASS/DEGRADED verdict against the previous quarter's numbers.
It is a human-run script, not a cron job, for exactly this reason: a
silently-logged DEGRADED verdict that nobody reads is the same as no
tripwire at all. If four quarters pass without anyone actually running it
and reading the output, this killer's tripwire has already failed before
the regime break does.

## Killer 2: Liquidity evaporation in a crash

A real crash doesn't just move prices down — it widens spreads and thins
order books on exactly the names this bot might be holding, meaning a
stop-loss that looks fine on a daily bar can fill materially worse than
the level the plan was sized against. This system models frictions
(`SLIPPAGE_BPS`, `edge/frictions.py`) as a fixed assumption calibrated
against normal conditions; it has no live mechanism that widens that
assumption when real liquidity is actually drying up.

**Tripwire:** `swingbot/core/universe.py`'s liquidity screen
(`liquidity_ok`/`liquidity_reason`) is re-checked every scan, not once at
onboarding — a ticker that was liquid last month and isn't anymore drops
out before a new entry is even considered. And the kill switch
(`edge/throttle.py`) engages hard on `abs(SPY daily move) > 5%`
(`KILL_SPY_MOVE_PCT`) — the exact kind of day liquidity evaporation
actually happens on. Neither of these re-prices an already-open stop
mid-crash; they only stop new entries from walking into one.

## Killer 3: Correlated overnight gap through every stop

The heat cap, sector cap, and correlation cap (`edge/heat.py`,
`edge/correlation.py`) all assume that "different" open positions are
actually somewhat independent. If they're all long the same overnight-gap
risk (same sector, same macro sensitivity, same crowded trade) a single
bad headline gaps every position through its stop simultaneously — the
caps bound how much capital *can* be exposed to that one morning, they
don't prevent the morning from happening.

**Tripwire:** this is precisely what the heat cap
(`PORTFOLIO_HEAT_CAP_PCT`, default 6%), the correlated-cluster cap
(`CORRELATED_HEAT_CAP_PCT`), and the sector cap (`SECTOR_HEAT_CAP_PCT`)
exist to bound — not to prevent the gap, but to guarantee that even the
worst correlated morning costs a bounded, pre-agreed percentage of
equity, not the account. If this killer still takes down the account, the
first thing to check is whether the caps were ever actually binding
(`open_heat`/`sector_heat`/`cluster_exposure`'s real numbers vs. their
caps) or just numbers nobody was watching.

## Killer 4: Data feed corruption

yfinance is free, third-party, and has silently returned corrupted,
stale, or partially-missing OHLCV data before. A backtest run against bad
data doesn't crash — it just quietly produces wrong numbers, and a live
scan fed bad data can build a plan against a price level that was never
real.

**Tripwire:** `universe.py`'s `data_quality_issues` gate runs per ticker,
per scan, and a ticker that fails it is excluded from that pass entirely
(logged, not silently used). If the *fraction* of the whole universe
failing quality checks in one scan exceeds 20%
(`KILL_DATA_FAIL_FRAC`) — a mass feed outage, not one bad ticker — the
kill switch engages system-wide. The quarterly re-validation script
(E96) also sweeps the entire cached universe for data quality issues as
its own explicit step, independent of live scanning.

## Killer 5: Overfit residue that survived the harness

Every gate in this plan (train/validation split, permutation testing,
plateau checks, ablation) is a real defense against overfitting, but none
of them are proof against it — a component or parameter that happened to
survive every check by chance is still possible, especially with as many
strategies and horizons as this system evaluates. As of this pre-mortem,
that specific risk is smaller than it could be: Task E33's component-
adoption grid found **zero** components that cleared the pre-registered
fold gate, and adopted zero — there is currently no adopted component
whose survival is in question, only the baseline strategies in the
validation registry.

**Tripwire:** any future component adoption is required to clear
`run_folds`'s pre-registered gate (`GATE_MIN_IMPROVING_FOLDS=2`,
`GATE_MAX_DEGRADATION_R=0.05`, `GATE_MIN_N_PER_FOLD=30`) AND a permutation
test (`scripts/backtest/permutation_test.py`) before being adopted, and the
quarterly re-validation ritual re-runs the permutation test on whatever
*is* adopted every quarter, not just once at adoption time. Ablation
(`scripts/backtest/ablation.py`) exists to find and drop the weakest-contributing
adopted component the moment one starts dragging on the pooled numbers.

## Killer 6: Operator overriding throttles in a drawdown

This is the most human killer on this list, not a technical one. A
drawdown is exactly the psychological moment every bias pushes toward "one
more trade to get it back" or "just this once, size up to recover faster"
— and if the operator can quietly turn off the throttle in that moment,
every other defense on this list is decoration.

**Tripwire:** the drawdown throttle (`DD_LADDER`: >8% dd → 0.75x size,
>12% → 0.50x, >16% → 0.25x, >20% → fully paused, resuming only below 15%
dd) is code, not a setting toggled per-trade — changing its behavior
means editing frozen constants in `edge/throttle.py`, a reviewed code
change, not a live override. And the weekly risk report
(`weekly_risk_report`, posted automatically every Sunday) explicitly
surfaces `throttle_activations` — an operator who's been quietly
overriding the throttle has to see that number every single week, not
just once.

## Killer 7: Position sizing creep

The slow version of Killer 6: not one dramatic override, but a gradual
drift toward larger positions as confidence builds during a winning
streak — no single decision looks reckless, but the cumulative sizing
ends up materially more aggressive than what was actually validated.

**Tripwire:** frozen sizing constants bound this structurally, not by
policy: quarter-Kelly (`KELLY_FRACTION_CAP=0.25`) caps how aggressively
even a genuinely strong track record can size up, `RISK_CEILING_PCT=2.0`
is a hard per-trade ceiling regardless of Kelly's own suggestion, and the
same `DD_LADDER` from Killer 6 cuts size automatically the moment a
winning streak turns — there's no size that survives a drawdown at full
exposure long enough to compound risk further. `KELLY_MIN_SAMPLE=30`
also means a short hot streak can't yet justify sizing up at all; the
Kelly estimate falls back to `RISK_FLOOR_PCT` until there's enough real
sample to trust.

## Honest bottom line

Every tripwire above already exists in the code today — this document
doesn't propose new defenses, it inventories the ones already built and
says plainly what they do and don't cover. The gap in every single one of
them is the same: **a tripwire that requires a human to read its output is
only as reliable as that habit.** The quarterly ritual, the weekly risk
report, the kill-switch log line — none of them stop anything by
themselves if the operator stops looking. That's not a flaw unique to
this system; it's the actual, permanent cost of choosing bounded-and-
readable over automated-and-opaque.
