# Downside coverage: inverse-instrument alerts for falling tape

**Bump:** none (spec; the implementing plan declares its own release level)
**Edge:** volume
**Status:** Spec. No gate changed, no pre-registration spent, no production change performed.
**Basis:** Session diagnosis 2026-09-21 against the live book, the cached universe and the
shipped gate tables. An earlier revision of this spec deferred to a stocks-only/no-ETF
boundary inherited from the v97 roadmap; that plan has since been withdrawn and the boundary
with it, so the inverse-instrument route is now the primary proposal.

## Goal

**Alert something usable when the market is falling.** The operator places resting broker
orders from these alerts, so a book that can only ever go long is a real-money exposure gap
during a decline, not a statistics problem. The bar is coverage, not beating the long book's
expectancy.

## Problem

The production book is not 90% long. It is **100% long**.

Re-derived from `data/journal.json` this session: 173 closed trades, **173 bullish, 0 bearish**.
Of those, 158 are decided (non-null `r_realized`): win rate 62.0%, mean R +1.537, median R
+1.000, range -1.00 to +5.50. The book spans **2026-08-06 .. 2026-09-21 — roughly six weeks.**

That window is recorded so no later reader over-reads the headline. Six weeks of rising tape
would produce few shorts under any honest gate, so part of the zero is sample, not defect. What
survives the caveat is structural: a majority of the engine cannot emit a short **in any
regime**, so the gap would persist through a decline.

## Why it happens: four layers

Measured this session by calling `ENTRY_FUNCS` directly (pre-gate) over the 75 cached tickers
across horizons `{4w, 2m, 3m, 6m}`:

**The detectors find shorts.** 9,133 bullish entries vs **2,433 bearish — 21.0% of raw signal
is short.** Short setups are not absent. They are discarded, in four places:

| # | Layer | Site | Effect |
|---|---|---|---|
| 1 | Direction masks | `market/strategy_types.py:214` `STRATEGY_GATES` | 7 of 10 strategies carry `directions: ("bullish",)`. Discards **1,948 of 2,433 bearish entries (80.1%)** before any other gate runs. Only Break & Retest, EMA Crossover, RSI Divergence and Elliott Wave can fire short at all. |
| 2 | Shared regime gate | `market/entry_filters.py:49-51` | `bull_regime` = close > MA200 **rising over 20 bars**; `bear_regime` = MA200 **falling over 120 bars** AND close < MA200. A 6x lookback asymmetry. Over 106,716 bars / 74 tickers: bull passes **59.0%**, bear **18.4%** (3.2x). Recomputing bear with the bull's 20-bar slope gives 24.5%, so this layer is real but secondary to layer 1. |
| 3 | RS gate | `edge/rs_gate.py` | Its own docstring: `RS_LEADER_PERCENTILE=0` structurally disables the bullish arm, so "in production this gate only ever blocks bearish setups." In v93 it removed 38-67% of every bearish sample. |
| 4 | Universe | `data/watchlist.json` | 76 symbols: US large-cap tech/growth plus `GC=F` and `SI=F`. No instrument that rises when the market falls. |

## What is already closed

`docs/claude/backtest-methodology.md:150` — **v93 re-derived the bearish arms for all seven
bullish-only masks on TRAIN plus folds. All seven failed the fixed rule.** No VALIDATION was
spent. That row is closed and **must not be re-run**. This spec does not reopen it, does not
re-read its table for a different verdict, and does not propose looser thresholds.

Its per-strategy evidence is recorded here so no future session mistakes this spec for a rescue
attempt: Fibonacci 21.3% WR, VWAP 12.5%, Volume Profile 25.0%, Support/Resistance 36.2%,
MA Ribbon 42.6%, MACD 52.6%, RSI 0.0% (N=10).

**This spec routes around that closure rather than through it.** It proposes no change to any
direction mask, regime gate or RS threshold.

## Proposal: trade the decline with the arms that already work

Add four unleveraged inverse ETFs to the watchlist as ordinary symbols. The **already-shipped
bullish arms** trade them. No gate, mask, threshold or shared table is modified — which is
precisely why the long book is provably untouched (see Isolation).

**Instruments: PSQ, SH, RWM, DOG.** Selected on measured hedge quality against this specific
watchlist and on liquidity, not on judgment:

| Symbol | Tracks | Corr vs book | Downside beta | Median daily $vol |
|---|---|---:|---:|---:|
| PSQ | -1x Nasdaq-100 | **-0.936** | **-0.92** | $136M |
| SH | -1x S&P 500 | -0.910 | -0.79 | $225M |
| RWM | -1x Russell 2000 | -0.848 | -0.88 | $45M |
| DOG | -1x Dow 30 | -0.811 | -0.71 | $30M |

Correlation and downside beta are against an equal-weight daily-return series of the 73 cached
watchlist names; liquidity is median daily dollar volume 2018-06..2025-12.

**Leveraged inverses are excluded.** -2x/-3x products (SQQQ, SDS, SPXU) carry severe
path-dependent daily-rebalance decay that breaks multi-month horizons structurally.

**Unleveraged sector inverses are excluded** on evidence, not preference: they hedge this
watchlist *worse* and are effectively untradeable — MYY $0.2M, REK $0.2M, SEF $0.3M, EFZ $0.4M
median daily dollar volume, with REK correlating only -0.615. No unleveraged tech inverse
exists (ProShares' REW is -2x), so PSQ is the tech proxy — and with the watchlist being heavily
Nasdaq-100 constituents, PSQ is also the best hedge measured.

### Why it self-gates

On a synthetic -1x SPY series built from the cached SPY history, `bull_regime` passed:

```
2018 0.0%   2019 0.0%   2020  4.3%   2021 0.0%
2022 50.6%  2023 1.2%   2024  0.0%   2025 0.0%
```

The same gate that makes shorts rare is the gate that switches this on **only** in a real
decline and off the rest of the time. Coverage appears when needed and vanishes otherwise, with
no new regime flag, no new state, and nothing to tune. 23 bullish entries fired across six
strategies on that single instrument, essentially all in 2022.

### Why this is executable

Long PSQ is a plain buy order. A genuine short needs margin and a locate. For an operator
placing resting orders, this route is **more** actionable, not less.

**Correction (2026-09-21, found while planning):** an earlier revision claimed these
instruments skip earnings blackout via `market/events.py:49`, removing a class of gap risk.
That gate keys off `is_etf()`, which reads `data/universe/etfs.json` — and PSQ, SH, RWM and DOG
are **not in that file** (17 entries, not even SPY or QQQ). The property only holds once the
implementing plan registers them. It is a task, not a freebie.

## What is genuinely new and must be measured

The synthetic series above models **no** expense ratio and **no** daily-rebalance drag. Real
SH/PSQ carry both, and drag compounds with holding period — which is exactly what decides the
horizon restriction. Applying arms validated on a liquidity-filtered *equity* population to
inverse ETFs is an **out-of-population extrapolation**.

This is a new question nobody has asked, not a re-run of anything closed, so it takes its own
pre-registered shot:

**Q-INV — On real inverse-ETF data, which horizons clear the gate under current arithmetic?**

## Scope

**In scope:** fetching real data for the four instruments; the Q-INV TRAIN measurement; the
horizon restriction it selects; the four isolation requirements below; the differential
verification.

**Non-goals**, each with its reason:

- **Reopening v93.** Closed. No direction mask is touched.
- **Changing `bear_regime`, the RS gate, or any `STRATEGY_GATES` entry.** Not needed for this
  route; see Follow-on work.
- **Leveraged or sector inverse instruments.** Excluded on measured evidence above.
- **Genuine stock shorts (borrowing shares).** A different mechanism with a different risk
  profile; see Follow-on work.
- **Exit-model changes.** Out of scope.

## Evaluation contract

Pre-registered before any run, quoted verbatim into the results document, per
`docs/claude/backtest-methodology.md`:

- Window: TRAIN only. VALIDATION is not spent by this spec under any outcome.
- Arithmetic: v2 exits, scale-out, TP2 levels, frictions on. Frozen for the duration.
- Frictions must reflect **ETF** spreads and expense ratio, not equity assumptions.
- A horizon subset clears only with WR >= 50%, ExpR > 0, decided N >= 30, scratch+timeout share
  <= 50%, and at least two anchored fold years with N >= 15 and positive ExpR.
- The measurement runs **per instrument and pooled**; an instrument that fails alone does not
  ride in on the basket's pooled number.
- If nothing clears, the component closes and **no instrument ships**. No threshold is
  loosened and no second grid is run on the same question.
- If it clears, the instruments ship behind a config flag **default on** (decided 2026-09-21).

**The default-on decision moves the safety checkpoint earlier, and the plan must honour that.**
The repo's usual posture is default-off with a separate enabling decision. Here there is no
post-merge checkpoint: the operator places resting broker orders from alerts, so these become
real-money-actionable the moment the change merges. All three of the following must therefore
hold **before merge**, not after:

1. Q-INV clears the pre-registered rule above, per instrument and pooled.
2. The differential test passes (Isolation, below) — long alerts byte-identical.
3. All four isolation requirements have landed, including the cohort-key change; the registry
   is not regenerated before it does.

If any one fails, nothing ships and the flag does not exist. The flag remains in place after
merge as a **kill switch** — the operator can turn the basket off without a revert.

## Isolation: the long book must not move

A hard requirement. This route changes **symbols, not logic**, so no long entry should change.
That must be **proved, not asserted**. Four coupling points found this session, each with a
requirement:

1. **Cohort registry dilution.** `backtesting/cohort_registry.py` keys cells on
   `direction|regime2_state`, and `band()` classifies each cell against a pooled `pool_mean_r`.
   An inverse-ETF trade is `direction="bullish"` — it lands in the **same cell** as long-AAPL,
   and adding population shifts `pool_mean_r`, re-banding existing bullish cells whose own
   performance never changed. **Requirement:** extend the key to
   `direction|regime2_state|population`, leaving existing bullish cell keys byte-identical. Do
   not regenerate the registry until this lands.
2. **Badge drift false alarms.** `analytics/calibration.py:83 badge_drift()` compares live
   closed trades per strategy against the registry. Inverse trades logged under a shared
   strategy name move that strategy's live WR and raise spurious decay alerts.
   **Requirement:** badge and drift populations filter to the equity population.
3. **Open-slot accounting.** **Correction (2026-09-21, found while planning):** an earlier
   revision of this spec claimed "slots are the only binding limiter." That is **false**.
   `max_open_positions` is **advisory only** — `scanning/scan_run.py:824` compares `open_count`
   against it purely to compose a warning string ("consider skipping new size here"); nothing
   anywhere blocks on it. The heat caps are separately non-binding:
   `max_position_value_absolute = 1000` / `max_risk_amount_absolute = 100` against a $1M balance
   puts per-trade heat near 0.01%, far under the 6% `PORTFOLIO_HEAT_CAP_PCT`.

   The real defect is therefore narrower but still real: inverse positions would inflate the
   shared `open_count` and raise **spurious warnings on long alerts** — a live path where an
   inverse position visibly degrades a long trade plan. **Requirement:** the warning's
   `open_count` becomes equity-only, and a genuine concurrent cap of **4** inverse positions is
   introduced (it does not exist today), held **outside** the 30 and
   never drawing from it. Four is the full basket, chosen deliberately so no instrument is
   arbitrarily locked out of a decline. The cap's purpose here is isolation, not diversification
   — the four are ~0.95 correlated with each other and should be understood as roughly one trade
   at 4x size, which is why they must never compete for a long slot.
4. **Shared-table mutation.** **Requirement:** the horizon restriction is a per-symbol overlay
   resolved at call time. Never mutate `STRATEGY_GATES` or `HORIZONS`, and never use
   `entry_filters.gate_override()` outside tests — it mutates a global dict in place and can
   leak into a concurrent live scan.

**One favorable property to preserve:** `edge/correlation.py` clusters on `corr > threshold` —
one-sided. An inverse ETF at corr ~ -0.9 never joins an equity cluster, so it cannot inflate
correlated heat and block a long. The four instruments *do* cluster with each other (mutual
corr ~ +0.95), which self-limits the basket. The existing model does the right thing here by
construction; do not "fix" it into two-sided clustering.

**Verification — the deliverable that discharges this section:**

- A differential test: run the scan pipeline over the current watchlist with the inverse
  symbols present and absent, and assert the emitted **long** alerts are identical — tickers,
  strategies, horizons, entries, stops, targets, sizes.
- A closed-book invariance check. **Correction (2026-09-21):** an earlier revision asserted the
  fixed figures N=158 / WR 62.0% / ExpR +1.537. That is the wrong shape of assertion — the bot
  is live and the book grows every session (it read 158 decided when this spec was drafted, 161
  while the plan was being written, and 162 hours later). A frozen N would fail for reasons
  having nothing to do with this change. **Requirement:** snapshot per-`trade_id` outcomes
  before the change and assert every pre-existing trade's outcome is byte-identical after,
  rather than asserting an aggregate.
- `python scripts/dev/testrun.py full` as the implementing plan's single final verification
  task.

## Follow-on work (separate specs, not this one)

Recorded so the diagnosis above is not lost, and deliberately **not** folded in — each is a
different mechanism with its own risk profile and would need its own decomposition:

- **Q1 — Does the RS laggard arm improve bearish expectancy, or harm it?** `rs_gate.py` records
  that the *bullish* arm was disabled for measuring negative at every TRAIN threshold. The
  bearish arm was retained but no record shows it was ever measured as *improving* bearish
  outcomes. v93 applied it as a fixed filter and never tested it. Testing a filter that has only
  ever been assumed is a new question, not a re-run.
- **Q2 — Is `bear_regime`'s 120-bar lookback derived, or inherited?** No result document derives
  the 120 against `bull_regime`'s 20. It gates every bearish arm, including the four strategies
  v93 never masked.
- **Shadow-first bearish book.** Lift the seven direction masks into the **shadow path only**
  (`backtesting/shadow_log.py`, `scripts/reports/shadow_parity_report.py`,
  `edge/strategy_soak.py` already exist), never alerted and never paper-traded, to accumulate
  live forward sample. Forward data is not the reserved window, so this is the one route that
  could legitimately reopen v93 later at zero budget cost.

## Decisions taken

All resolved 2026-09-21. No open questions block the implementing plan.

1. **Inverse sub-cap: 4**, the full basket, held outside the 30-slot long cap. See Isolation
   requirement 3.
2. **Ship default-on** once Q-INV clears, with the three pre-merge preconditions above and the
   flag retained as a kill switch. See Evaluation contract.
3. **The withdrawn v97 plan was restored and moved** to
   `docs/superpowers/plans/no-lift/2026-09-20-v97-directional-precision-improvement.md` per
   `docs/claude/document-lifecycle.md:90`, with a closing note recording the two decisions of
   its that were load-bearing elsewhere.
