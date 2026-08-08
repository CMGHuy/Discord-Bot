# Market context, context gates, and level lifecycle (v11)

Design doc. Origin: a review of **dsgex.ai** — a real-time options
dealer-positioning platform — to find features worth replicating in swingbot to
improve win rate and trade-plan quality.

## 1. What DSGEX is, and what actually transfers

DSGEX is an *options microstructure* product: dealer gamma exposure (GEX) by
strike, call/put walls, gamma flip, and options tape reading. Swingbot is a
stock/ETF OHLCV swing bot with **no options data anywhere**
(`git grep option_chain|gamma|open_interest` returns nothing).

Features therefore split on **whether they can be backtested**, which is
decisive here because every component in this repo is gated on TRAIN/VALIDATION
evidence (`docs/claude/backtest-methodology.md`).

| DSGEX feature | Needs | Verdict |
|---|---|---|
| **Sigils & Spectrum** — King/Floor/Ceiling/Gatekeeper tags, Fresh→Tested→Delivered→Decaying lifecycle | level classification + state machine | **Replicable on pure OHLCV.** The concept transfers; the options plumbing does not. → **P1** |
| **Positioning** (asset managers / leveraged funds / dealers) | CFTC Traders in Financial Futures | **Free, weekly, history to 2006.** Backtestable. → **P2b** |
| **IV vs RV / vol risk premium** | IV history | RV half is free and backtestable; IV half is snapshot-only. RV portion → **P0** (`ctx_rv_pct`) |
| **Session Replay** | historical bars | Already exists (`replay_scenarios`, `portfolio_replay`). No work. |
| **Dealer Net GEX by strike**, **Key Levels** (call/put wall, gamma flip) | option chain OI + gamma | yfinance gives a **current snapshot only, no history** → cannot be backtested today. → **P3** starts the archive. |
| **Notable Flow Scanner** (aggressor-signed prints, sweeps) | tick/tape data | Not feasible. Dropped. |

DSGEX's "asset managers / leveraged funds / dealers" breakdown is precisely the
CFTC **Traders in Financial Futures** taxonomy — that report is what the panel
is showing, and it is free.

## 2. The blocking finding

Swingbot already has a market-context gate. It is **triple-inert**:

1. `strategy_types.py:311` — `REGIME_ALLOW: dict[str, tuple] = {}` (empty)
2. `config.REGIME_GATES_ENABLED` — defaults `False`
3. **`entries_for()` is never passed a `regimes` series at all.**
   `run_backtest → _vectorized_entries → entries_for` has no market dataframe
   anywhere in its call chain; live `evaluate_all(ticker, df)` likewise.

Item 3 is the real blocker, and edge-engine-v4 explicitly deferred it as "a
separate, much larger architectural task". **No market-context feature — regime,
COT, GEX, IV/RV — can gate anything until that channel exists.**

Asymmetry worth noting: live, `scanning/engine.py:1215` already passes
`regime=regime` into *plan building*. So context reaches the trade plan but not
the entry signal. The backtest has neither.

## 3. Components

```
P0 (market context layer) ──> P2a (regime gate) ──> P2b (COT positioning)
P1 (level lifecycle)          independent
P3 (options snapshot archive) independent
```

Each component gets its own implementation plan and its own **pre-registered
validation shot**. Every flag ships default-off. One component is registered at
a time — a bundled validation run cannot attribute its own result.

---

## 4. P0 — market context layer

### 4.1 Channel shape

Context travels as **namespaced columns on the ticker dataframe**, not as a
threaded parameter.

Rejected alternatives, recorded so they are not re-litigated:

- **Explicit parameter threading** through `evaluate_all` → 11 `STRATEGY_FUNCS`
  → `entries_for`, plus `run_backtest` → `_vectorized_entries` and every script
  that calls them (~15 signatures). More explicit, but it carries a second
  series alongside `df` that must be reindexed at every use — which is exactly
  where alignment bugs hide.
- **Ambient module-level state** (`set_current()` once per run). Zero plumbing,
  but hidden global state that breaks under `pytest -n 4` (the standard runner)
  and any concurrent scan. **Rejected.**

Columns win on a specific technical ground, not on diff size: context becomes
**index-aligned to `df` by construction**, so the existing NO-LOOKAHEAD
discipline (`shift(+n)`, trailing `rolling`, `.fillna(False)`) covers it for
free and is auditable the same way. A regime gate is precisely the feature where
an off-by-one silently leaks tomorrow's regime into today's entry, the backtest
looks excellent, and live underperforms. Columns make that class of bug
inexpressible; parameters make it easy to write and hard to spot.

Cost accepted: `df` is copied and sliced in several places, and any path that
rebuilds a frame without going through `attach` loses the columns. The
fail-closed accessor is what makes that survivable rather than silent.

### 4.2 Module surface

New `swingbot/core/market_context.py`:

```python
CTX_COLUMNS: tuple[str, ...]
attach(df, *, spy_df, cot_df=None) -> pd.DataFrame   # copy + ctx_* columns
get(df, name) -> pd.Series | None                     # strict, fail-closed
has_context(df) -> bool
class MissingContextError(RuntimeError): ...
```

`get()` returns `None` when the gate flag is off — which is exactly what
`apply_regime_gate` already treats as "leave entries untouched"
(`regimes is None` short-circuit). When the flag is **on** and the column is
missing it raises `MissingContextError`; it never degrades to `None`, because
that would silently open the gate.

| Column | Source | Notes |
|---|---|---|
| `ctx_regime` | `regime2.regime_series(spy_df)` | existing 4 states: `bull_quiet`, `bull_volatile`, `bear_quiet`, `bear_volatile` |
| `ctx_rv_pct` | SPY 20d realized vol, percentile within trailing 252d | continuous form of regime2's binary 0.60 split; lets P2 test finer cuts with no new data source |
| `ctx_cot_z` | reserved for P2b | declared now, populated later, so the block's shape never changes |

### 4.3 Alignment rule

SPY is the calendar; a ticker's index has holes (halts, late listings).

    spy_series.reindex(df.index, method="ffill")

**ffill only — never bfill, never interpolate.** A ticker bar predating SPY
history yields NaN, and NaN blocks, matching the existing `.fillna(False)`
convention in `entry_filters`.

### 4.4 Data flow

- **Backtest**: load SPY once per run in the frame loader; `attach` to each
  ticker frame before `run_backtest`.
- **Live**: the crawl already fetches SPY for `get_market_regime`
  (`scanning/regime.py:89`) — reuse that frame, `attach` during the crawl before
  `evaluate_all`.

Neither path adds a network call.

### 4.5 Failure behaviour

`get()` **fails closed**: with `REGIME_GATES_ENABLED` on and the column absent
or NaN, entries are blocked. With the flag off, `get()` is a no-op returning an
all-permissive series.

Consequence, accepted deliberately: if the SPY fetch fails during a live scan
and the gate is on, **every alert is suppressed for that scan**. A context gate
that silently opens when its data is missing is strictly worse than no gate,
because it invites trust in alerts that were never filtered. This requires a
loud log line and an admin-UI indicator, never a silent skip.

### 4.6 Tests

- `attach`: index alignment, ffill-only, NaN before SPY history begins.
- `get`: raises `MissingContextError` when flag on + column missing; no-op when
  flag off.
- **Lookahead**: shift `spy_df` forward one bar and assert the gated entry set
  *changes* — proves the gate reads the aligned bar rather than a leaked one.
- Parity: `regime_series` vs per-bar `classify` must agree (already required by
  regime2's docstring); extend the assertion through `attach`.

---

## 5. P2a — the regime gate

### 5.1 Shape

`REGIME_ALLOW` stays `dict[str, tuple]` — per *strategy*, not per
(strategy, horizon). That is 11 strategies × 4 regimes = **44 binary
decisions**. Extending to per-horizon would be 11 × 10 × 4 = **440 cells**
fitted on one TRAIN window; that is not a gate, it is a lookup table of noise.
The existing structure is already the right shape.

P2a changes **no gate code**. `apply_regime_gate` already masks correctly. P2a
flips the flag, fills the table, and relies on P0 to finally deliver a real
`regimes` series.

### 5.2 Pre-registered selection rule

Fixed before any fold runs:

> Deny `(strategy, regime)` only if **all three** hold on TRAIN:
> `N_cell >= 30`, `expectancy_r < 0`, and the negative sign holds in **≥3 of 4**
> sub-folds. Otherwise the cell stays **allowed**.

Sub-folds are the four calendar years of TRAIN — 2020, 2021, 2022, 2023 — each
evaluated independently. A cell whose `N` falls below 30 *within* a sub-fold
counts as "sign does not hold" for that fold rather than being dropped from the
denominator; otherwise a single-fold cell could clear "3 of 4" on one year's
evidence.

Default-allow is deliberate. Every denial removes trades; a gate pays only if
the effect is real, and if it is noise the sample has been cut for nothing.

### 5.3 Selection metric — expectancy, not win rate

The originating request was to improve *win rate*. Win rate is trivially gameable
by gating: deny enough cells and it rises while total expectancy falls, because
winners are cut alongside losers.

**The rule selects on `expectancy_r` and reports `win_rate`.** A config that
raises win rate while lowering expectancy is a **fail**. This is written down
so a later session cannot quietly re-read it the other way.

Acceptance remains the standing gate: `win_rate >= 80`, `expectancy_r > 0`,
`N >= 30` train / `N >= 15` validation, scratches+timeouts ≤ 50%.

### 5.4 Expected-failure note

TRAIN (2020-01-01..2023-12-31) contains one large bull run and two sharp
drawdowns, so `bear_volatile` may simply lack `N >= 30` cells. "No gate
justified" is a legitimate, recordable outcome — **not** a prompt to loosen
thresholds and retry. That is the failure mode the one-shot validation budget
exists to prevent.

### 5.5 Outcome (2026-08-08) — NO GATE JUSTIFIED. P2a is closed.

The pre-registered shot ran: 78 tickers × 11 strategies × 10 horizons over
TRAIN. **Zero of the 44 cells cleared the rule**, so `REGIME_ALLOW` stays `{}`
and `REGIME_GATES_ENABLED` stays default-off. Evidence:
`docs/superpowers/results/2026-08-08-regime-allow-train.{md,json}`,
reproducible via `scripts/fill_regime_allow.py`.

The rule needed `N>=30` **and** `expectancy_r<0` **and** a negative sign in
≥3 of 4 sub-folds. The binding constraint was the third: the worst cells by
expectancy (RSI Divergence `bear_quiet`, −0.267 on N=242; `bear_volatile`,
−0.122 on N=383) reached only **2 of 4** and **1 of 4** negative folds — not
because the sign flipped, but because 2020–2021 hold almost no bear-regime
bars, so those folds have N<30 and score as "sign does not hold" by §5.2.
TRAIN's regime coverage, not the strategies, is what failed to support a gate.

This is the recorded result, not a threshold to retune. **Do not re-run this
with relaxed bounds** — the shot is spent, and a rule fitted after seeing this
table is no longer pre-registered. A future gate needs *more bear data*
(a longer TRAIN window, which changes the frozen backtest windows and is its
own decision), not a looser rule.

**P2b (COT) is therefore not built** — §6 conditions it on P2a clearing
validation, and P2a did not clear. The design in §6 stands as-is for whenever
the data situation changes; the lookahead trap recorded there is the part
worth keeping.

The P0 channel it was built on is **not** wasted: `market_context.attach`/`get`
is what finally makes `entries_for` regime-aware at all, and it is the
prerequisite for any future context gate (COT, IV/RV, GEX).

---

## 6. P2b — COT positioning (deferred, designed)

Cut from v1 on validation-budget grounds: each added context dimension
multiplies the selection surface that a single pre-registered shot must justify.
`ctx_regime` costs no new data and no new failure modes; COT costs a fetch
script, a cache, a release-date calendar, and its own pre-registration. Built
only if P2a clears validation.

**Source.** CFTC Traders in Financial Futures, E-mini S&P 500. Weekly, free,
history to 2006 — covers both windows.

**The lookahead trap, recorded now so it is not rediscovered later.** Positions
are reported *as of Tuesday* but released *Friday 15:30 ET*. Keying on the
as-of date leaks three days. The value must become usable only on the first bar
**after release**, then forward-filled.

**Feature.** `ctx_cot_z` — leveraged-funds net position as a z-score over a
trailing 3-year window (positioning extreme read contrarian).

---

## 7. P1 — level lifecycle ("Sigils")

### 7.1 The landmine that decides the architecture

Two parallel plan paths exist:

- `backtest.py:122` — `_trade_plan_at(df, i, direction, strategy, horizon_key,
  atr_series, ..., entry_levels=None)` ← what the **backtest** sizes through
- `plan_engine.py:379` — `build_strategy_plan(df, index, *, ticker, strategy,
  horizon_key, ..., level_map=None)` ← what **live** builds through

edge-engine-v4 records `DATA_DRIVEN_STOPS_ENABLED` scoring exactly 0.0000 and
burning its pre-registered shot **because it reached only `build_strategy_plan`
while the backtest sized through `_trade_plan_at`**. A one-path implementation
is unmeasurable by construction.

Both hooks already exist (`entry_levels`, `level_map`, both defaulting to
`None`), and `plan_engine.py:154` notes the sizing builders were "extracted
verbatim from `backtest._trade_plan_at`". P1 uses that seam: **one
implementation, both callers.**

### 7.2 Module surface

New `swingbot/core/levels_lifecycle.py`:

```python
@dataclass(frozen=True)
class Level:
    price: float
    role: str            # "floor" (below px) | "ceiling" (above px)
    state: str           # "fresh" | "tested" | "delivered" | "decaying"
    touches: int
    bars_since_touch: int
    strength: float
    is_king: bool        # highest-strength level in the horizon's range

classify_levels(df, i, raw_levels, *, horizon_key) -> list[Level]
```

### 7.3 State machine

All computed from bars ≤ `i`:

| State | Rule |
|---|---|
| `fresh` | formed, no touch since formation — untested, therefore unproven |
| `tested` | ≥1 touch within `0.25×ATR14` that did **not** close beyond → it held |
| `delivered` | a close beyond by `> k×ATR` → level consumed; a stop is no longer valid there |
| `decaying` | `bars_since_touch >` horizon-scaled threshold → conviction fading |

Tolerance is **ATR-relative, not a fixed percentage**, so it scales across a $9
ETF and a $900 stock — consistent with `entry_filters` (`ATR_FLOOR_PCT`,
`atr_calm`).

### 7.4 Consumers

Three, in increasing risk order, **each behind its own flag** so each is
measurable alone:

1. **Stop anchoring** *(plan quality)* — prefer a `tested` floor over a `fresh`
   one; **never** anchor to a `delivered` level.
2. **Target realism** *(plan quality)* — count non-delivered ceilings between
   entry and TP1. This is DSGEX's **Gatekeeper** concept, the most direct
   translation in the whole design: the level that must break for the plan to
   work.
3. **Entry filter** *(win rate)* — skip the setup when a `king` ceiling sits
   inside the early part of the path to TP1.

### 7.5 Tests

Golden OHLCV fixtures where each transition is unambiguous, plus one structural
assertion that is cheap and proves a great deal:

    classify_levels(df, i) == classify_levels(df.iloc[:i+1], i)

If truncating the future changes the answer, there is lookahead. This makes the
NO-LOOKAHEAD rule mechanically checkable rather than a review convention.

**Measurement.** A/B over TRAIN through `portfolio_replay`, exactly as the
reversal work in `7d5164b` did.

---

## 8. P3 — options snapshot archive

Deliberately dumb; its only job is to not lose data.

`scripts/record_option_snapshots.py`, run daily near the close. For a **capped**
symbol set (SPY, QQQ, IWM + selected watchlist names) it pulls `Ticker.options`
then `Ticker.option_chain(expiry)` for expiries ≤ 90 days, writing
`market_data/options/YYYY/MM/DD/SYMBOL.parquet`. `market_data/` is already
gitignored (`.gitignore:17`) and search-ignored (`.ignore`).

Idempotent — re-running a date overwrites. A failed symbol logs and is skipped;
a missing day is a hole in the archive, never a crash. Nothing under `swingbot/`
imports it, so it cannot affect the live path.

**Record raw, derive nothing.** Store strike, expiry, OI, volume, IV, bid/ask as
fetched, plus the **snapshot timestamp**. Not computed GEX. The dealer sign
convention, gamma model, and spot multiplier are all currently guesses; storing
only today's guess makes the archive worth exactly that guess. Raw chains can be
recomputed forever. The timestamp matters because a 15:55 ET snapshot and a
09:35 one are different animals.

**Honest caveats.** yfinance option data is mediocre: OI updates once daily,
greeks are absent (gamma would be computed via Black-Scholes later), and IV is
yfinance's own calculation. At ~100–300 KB per symbol-day, ~10 symbols is
~0.5 GB/year — hence the cap rather than the full watchlist.

P3 gates nothing and improves nothing today. It is pure option value on a 6–12
month horizon: every day not recording is a day of history that cannot be
recovered.

---

## 9. Out of scope

- Notable Flow Scanner / tape reading — requires tick data.
- Live GEX walls or gamma flip as *gating* inputs — no historical data to
  validate them; P3 exists to remove that objection later.
- Per-horizon regime gates (440 cells) — see §5.1.
- Any ML in the live path — standing repo rule.
