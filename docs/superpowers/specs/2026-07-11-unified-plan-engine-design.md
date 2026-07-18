# Unified Trade-Plan Engine v2 — Design Spec

Date: 2026-07-11
Status: **Shipped** (code complete through Task 100 on 2026-07-18 — engine,
registry, quality score, plan manager, Discord UX, shadow tooling, cutover
funnel, rescue round for RSI [VALIDATED] and RSI Divergence
[rejected-on-train]; operational rollout gates — shadow sessions, cutover,
legacy removal — and remaining rescues per
`docs/superpowers/plans/2026-07-11-unified-plan-engine-v2.md` Progress block)
Previous status: Approved (design dialogue 2026-07-11)
Predecessor: `docs/superpowers/specs/2026-07-10-strategy-winrate-redesign-design.md`
(implemented and validated; see `docs/superpowers/results/2026-07-validation.md`)

## 1. Goal

Every trade plan the bot emits carries a proven, out-of-sample win-rate
pedigree, and live behavior matches backtested behavior because both run the
same code.

Success criteria:

1. Every emitted plan is stamped either ✅ **VALIDATED** (its source setup —
   the (source, strategy, horizon) combination that produced it — showed
   ≥80% win rate AND positive expectancy on the held-out validation window)
   or ⚠️ **WEAK** (still emitted, clearly warned, showing its real numbers).
2. Pooled win rate across VALIDATED plans is ≥80% out-of-sample under the
   v2 exit model.
3. One code path produces entries, stops, targets, and exits for scan
   alerts, strategy signals, backtests, and paper-trade management. No
   live/backtest drift by construction.
4. Weak/failing strategies keep computing and emitting plans (user
   requirement) — never silently hidden — with explicit caution labeling.

Non-goals (out of scope): real-money execution, streaming/websocket data,
options, new paid data providers, ML models in the live path.

## 2. Current state (facts this design builds on)

Two disjoint pipelines exist today:

- **Pipeline A — live confluence scan** (`scanning/engine.py` + `levels.py`):
  produces all Discord alerts and paper trades. Entry = current price at scan
  time; SL/TP from nearest clustered S&R levels (`levels.build_scenarios`,
  `levels.py:464-561`). Confidence model in `scanning/confidence.py`.
  **Never validated** against the 80% bar. No unit tests.
- **Pipeline B — strategy signals** (`signals.py` + `entry_filters.py` +
  `backtest.py`): validated out-of-sample 2026-07-10. 6/11 strategies PASS
  (VWAP, Fibonacci, S&R, MACD, Volume Profile, Break & Retest); 5 FAIL
  (RSI 68.4%, RSI Divergence 75.8%, MA Ribbon 78.1%, EMA Crossover 76.9%,
  Elliott Wave 74.8%). Only surfaces to users as a bias table (`!ticker`).
- `trade_plan.compute_trade_plan` (`trade_plan.py:75`) is dead in production;
  its sizing logic is duplicated in `backtest._trade_plan_at`
  (`backtest.py:118-215`).
- Exit model (validated): single entry at close, ATR/structural stop,
  TP at `STRATEGY_RR_OVERRIDE` (0.35–0.40, hard floor 0.30), stop→BE once
  favorable excursion ≥ `BREAKEVEN_TRIGGER_FRACTION=0.5` × target distance.
  Outcomes: win / loss / scratch / timeout. No partial exits anywhere.
- `backtest_confluence.py` is a third, separate definition of edge
  (agreement≥2, RR=0.25, no BE logic) — to be retired.
- Live monitoring exists: `trade_monitor` loop @60s
  (`commands/scanning.py:755-825`) drives SL/TP fills and near-TP timeout
  exits on paper trades (`performance.py`).
- `ScenarioSignal.strategy` is hardcoded `"S/R Confluence"`
  (`levels.py:577`), so per-strategy attribution of live trades is
  reconstructed heuristically.
- Data: yfinance daily bars (`data.get_daily_data`), 1-minute live quotes
  with 15s TTL (`data.get_current_price`). `data_store.py` caches intraday
  CSV but is unused by the scan.
- State: JSON files under `data/` (trades.json, account.json, state.json).
- Validation discipline established by round 1: tune on 2020–2023 (TRAIN),
  validate once on 2024–2025 (VALIDATION), pre-registered gates, no
  retuning after seeing validation numbers.

## 3. Architecture overview

New module `swingbot/core/plan_engine.py` becomes the single authority for
trade-plan construction and exit policy. Everything that today invents its
own entry/SL/TP — `levels.build_scenarios` sizing, `backtest._trade_plan_at`,
`trade_plan.py` — either delegates to it or is replaced by it.

```
 sources                    engine                        consumers
 ─────────                  ──────                        ─────────
 strategy signals ──┐
 (signals.py,       ├──►  plan_engine.build_plan() ──►  TradePlanV2
 entry_filters.py)  │       • entry trigger                 │
                    │       • SL / TP1 / runner rule        ├─► scan embeds + charts
 confluence setups ─┘       • quality score                 ├─► paper trades (performance.py)
 (levels.py)                • validation badge              ├─► backtest simulator
                            • lifecycle status              └─► intraday plan manager
```

The exit policy lives in one place (`plan_engine.simulate_exit` /
`plan_engine.step_exit`) consumed in vectorized/loop form by the backtest and
in incremental form by the live manager, sharing the same constants and
transition rules.

## 4. TradePlanV2 (dataclass, `plan_engine.py`)

Fields (exact names final at implementation, semantics fixed here):

- Identity: `plan_id` (uuid), `ticker`, `created_at`, `source`
  (`"strategy" | "confluence"`), `strategy` (real generating strategy —
  fixes the `"S/R Confluence"` hardcoding), `horizon_key`, `direction`
  (`"bullish" | "bearish"`).
- Entry: `entry_type` (`"stop_entry" | "market"`), `trigger_price`
  (stop-entry level: for breakout-class setups the setup level being broken;
  for others the scan-time price), `entry_price` (fill, set on trigger),
  `expiry_bars` (cancel if not triggered within N daily bars; default 5,
  train-tunable).
- Risk: `stop_loss`, `tp1` (at validated `STRATEGY_RR_OVERRIDE` R:R),
  `tp1_fraction` (default 0.50), `tp2` (next structural level beyond TP1 or
  None), `breakeven_trigger_fraction` (0.5, unchanged), `runner_trail`
  (chandelier: highest close since TP1 − `trail_atr_mult` × ATR(14);
  `trail_atr_mult` default 2.5, train-tunable only).
- Quality: `quality_score` (0–100 int), `quality_breakdown`
  (list of (component, points)), `tier` (`"A" | "B" | "C"`).
- Pedigree: `badge` (`"VALIDATED" | "WEAK"`), `badge_stats`
  (OOS N/WR/ExpR from the registry, shown verbatim in embeds).
- Lifecycle: `status`
  (`PENDING → ACTIVE → PARTIAL → CLOSED(reason)` | `CANCELLED(reason)`),
  `status_history` (timestamped transitions).

## 5. Exit model v2 — hybrid scale-out

Designed so the validated round-1 numbers carry over unchanged:

- **TP1 is exactly the validated target** (`STRATEGY_RR_OVERRIDE` R:R, floor
  0.30) and the BE trigger stays at 0.5 × TP1 distance. Therefore the win
  definition — *TP1 touched* — is identical to round 1's "TP touched", and
  per-strategy WR is unchanged by construction.
- New behavior at TP1: close `tp1_fraction` (50%) of the position, move the
  stop on the remainder to break-even (entry). The runner rides toward `tp2`
  with the chandelier trail; whichever of {tp2, trail, BE stop} is hit first
  closes it.
- Outcomes: `win` (TP1 hit; runner sub-outcome recorded as
  `runner_tp2 | runner_trail | runner_be | runner_timeout`), `loss` (stop
  before BE trigger), `scratch` (BE stop after trigger, before TP1),
  `timeout` (unchanged; marked to market). `win_rate` over win+loss only;
  `expectancy_r` over all closed trades — same definitions as round 1.
- The runner cannot turn a win into a loss (its stop is at BE), so ExpR for
  winners is bounded below by `tp1_fraction × tp1_r` minus slippage; the
  runner is pure expectancy upside.
- Conservative same-bar ordering (stop before target) is preserved in the
  backtest simulator; the live manager uses actual tick sequence from
  polled prices with today's gap-aware fill rules (`performance.py`).

## 6. Quality score and validation badges

**Quality score** (transparent, points-based, no ML in live path). Components
and default points (weights tunable on TRAIN only; total clamped 0–100):

| Component | Points |
|---|---|
| Market regime aligned (SPY vs 200-EMA vs plan direction) | 0–15 |
| HTF bias aligned (ticker 50/200-EMA) | 0–15 |
| Confluence count at target/stop levels (existing `count_confirming_strategies`) | 0–20 |
| Volume confirmation (volume ratio vs 20-day avg) | 0–10 |
| ATR-percentile sanity (not in top volatility decile) | 0–10 |
| Entry-to-level distance (trigger near setup level, not chasing) | 0–10 |
| Source validation status (VALIDATED source) | 0–20 |

Tiers: A ≥ 75, B ≥ 50, C < 50. Tier affects presentation (ordering,
color, warning text), never suppression — WEAK sources still emit.

**Validation registry**: a committed JSON file
(`swingbot/core/validation_registry.json`) generated by the acceptance
harness, mapping `(source, strategy, horizon_key)` → `{status, n, win_rate,
expectancy_r, window, run_date}`. `plan_engine` loads it to stamp badges;
embeds print the stats verbatim. WEAK plans render a fixed caution block:
"⚠️ WEAK: this setup did not reach 80% win rate out-of-sample (WR X%,
N=Y). Treat with extra care."

**Offline ML audit** (`scripts/audit_quality_score.py`): logistic regression
of realized backtest outcomes on score components; asserts realized WR is
monotone non-decreasing across score deciles. Run manually after tuning;
never imported by the bot.

## 7. Confluence pipeline under validation

New scenario backtest (`swingbot/core/backtest_scenarios.py` or a mode of
the existing harness): replays `build_level_map → build_scenarios`
bar-by-bar over history, feeds resulting plans through the shared exit
simulator, and reports with the same acceptance gates
(WR ≥ 80, ExpR > 0, N floors: 30 train / 15 validation, exclusions ≤ 50%).

- Confidence-level and requirement gates for the confluence source are tuned
  on TRAIN only (grid over `MIN_ALERT_CONFIDENCE_LEVEL`, requirement
  subsets, horizon subsets), pre-registered, then validated once.
- The confluence source gets its own registry entries (per horizon), so scan
  alerts earn VALIDATED/WEAK badges exactly like strategies.
- `backtest_confluence.py` is retired once the scenario backtest supersedes
  it (its agreement-count idea survives as the confluence-count score
  component).
- Fix `ScenarioSignal.strategy` to carry real attribution (primary source
  from level clustering) end-to-end into trades.json.

**Validation-window hygiene**: the 2024–2025 window was consumed once by
round 1 for Pipeline B's gates. It is reused here only for components never
tuned against it (scale-out runner params, confluence gates, rescue
hypotheses), each with a single pre-registered validation run per component.
No component gets a second look; results are reported as-is.

## 8. Intraday plan manager

Evolves the existing 60s `trade_monitor` into a plan-lifecycle manager
(`swingbot/core/plan_manager.py`), still on polled yfinance quotes (no new
data provider), session-aware, keeping today's gap-aware fill rules.

States and transitions:

- `PENDING`: plan created from a scan/signal; waiting for stop-entry
  trigger. Cancel on: expiry (`expiry_bars`), setup invalidation (price
  closes beyond stop side of setup level before trigger), or manual admin
  close. Breakout-class setups (Break & Retest, S&R breaks, confluence
  breakout scenarios) use stop-entry at the level; mean-reversion setups may
  use market entry at scan (per-strategy mapping fixed at implementation,
  tuned on TRAIN).
- `ACTIVE`: filled. Manager enforces BE move at 0.5 × TP1 distance, SL/TP1
  detection.
- `PARTIAL`: TP1 banked (50% closed at TP1, realized), stop at BE, runner
  managed (tp2 / chandelier trail / BE stop).
- `CLOSED(reason)`: `loss | scratch | tp1_runner_tp2 | tp1_runner_trail |
  tp1_runner_be | timeout | manual | invalidated`.

Every transition posts a Discord alert to the existing channels
(`DISCORD_CHANNEL_TRADES_ID` for entries, `..._TRADES_HISTORY_ID` for
closes/partials) and is persisted in trades.json (schema extended for
two-leg exits: per-leg exit price/time/realized R and P&L; account balance
math in `account.py` updated accordingly). Retrospective and `!pnl`/
`!trades` outputs updated for partial fills.

## 9. Discord UX

- Scan alert embeds: badge line (✅ VALIDATED w/ OOS stats, or ⚠️ WEAK block),
  quality tier + score with per-component breakdown, entry trigger semantics
  ("BUY STOP above X" vs "at market"), TP1/TP2/trail description, both-leg
  sizing from `account.compute_position_size`.
- `!ticker` gains a per-signal mini trade plan (from the same engine) with
  badges — the strategy pipeline finally surfaces actionable plans.
- New `!plans` command: lifecycle board of PENDING/ACTIVE/PARTIAL plans.
- Charts: entry-trigger line + TP1/TP2/trail zones on the existing
  mplfinance charts.

## 10. Migration safety (feature flags + shadow mode)

- Config flags (via existing `config.FIELDS`/admin UI): `PLAN_ENGINE_V2`,
  `SCALE_OUT_ENABLED`, `INTRADAY_MANAGER_V2` — all default off in prod
  until cutover.
- **Shadow mode**: with `PLAN_ENGINE_V2=shadow`, the v2 engine runs inside
  the scan loop, logging the plans it *would* emit
  (`data/shadow_plans.jsonl`) without posting. A parity report script
  compares shadow vs legacy output over ≥5 sessions (same tickers, entry
  deltas, SL/TP deltas, would-be badges) before cutover.
- Legacy paths (`levels.build_scenarios` sizing, `backtest_confluence.py`,
  dead `trade_plan.compute_trade_plan`) are deleted only after cutover +
  one clean week.
- Each phase of the implementation plan ships something independently
  verifiable (tests + backtest gates), so work can pause between phases.

## 11. Rescue phase — the 5 failing strategies

Throughout all phases they keep emitting ⚠️ WEAK plans. Then, one rescue
attempt each, in this order, with hypotheses **pre-registered here** (before
any new data contact). Method per strategy: implement hypothesis → grid on
TRAIN only → if train gates pass (WR ≥ 80, ExpR > 0, N ≥ 30, excl ≤ 50%),
run the single validation shot → accept (badge flips VALIDATED) or reject
(stays WEAK forever, attempt documented in results doc).

| Strategy | Pre-registered hypothesis |
|---|---|
| RSI (68.4% OOS) | Mean-reversion edge exists only in range regimes: gate on ADX(14) < threshold (grid 20/25/30) + price within Bollinger(20,2) bands; drop trend-day entries. |
| RSI Divergence (75.8%) | Require confirmation quality: volume ratio ≥ threshold on reclaim bar + reclaim strength (close > prior swing midpoint); grid both. |
| MA Ribbon (78.1%) | Require ribbon expansion (ribbon width percentile rising) at entry — filter chop entries that mean-revert through the ribbon. |
| Elliott Wave (74.8%) | Stricter wave-2 validation: retrace bounded 38–79% of wave-1 and wave-2 duration ≤ wave-1 duration; reject overlapping structures. |
| EMA Crossover (76.9%) | Documented likely-unrescuable (round 1 found no gate). Last attempt: replace cross-day entry with first pullback-to-fast-EMA entry after cross. If it fails, permanent WEAK. |

## 12. Testing & verification

- Unit tests for: plan_engine construction + exit simulator (golden-trade
  fixtures covering every outcome incl. runner sub-outcomes and same-bar
  conservative ordering), quality score components, registry loading/badge
  stamping, levels/scenario generation (first-ever tests for the live
  pipeline), plan_manager lifecycle via a fake price-feed harness (trigger,
  BE move, partial fill, trail, invalidation, expiry, gap fills), trades.json
  two-leg schema + account math, embed rendering (badges, WEAK block).
- Acceptance gates per phase: the established train/validation harness
  (`scripts/run_backtest_range.py`) extended for v2 exits and scenarios;
  every gate pre-registered; VALIDATION run once per component.
- Shadow-mode parity report is a hard gate before cutover.
- `make check` (py_compile) + pytest green at every phase boundary.

## 13. Risks

- **Validation-window erosion**: 2024–2025 gets one look per new component;
  accepted residual risk, documented per run.
- **yfinance polling granularity**: 60s polls can miss intrabar trigger+TP
  sequences; mitigated by existing gap-aware conservative fills; accepted.
- **Scenario backtest fidelity**: historical replay of level maps is
  compute-heavy; mitigated by the existing CSV OHLCV cache and per-day
  memoization of level maps.
- **Two-leg accounting bugs**: mitigated by golden-number unit tests on
  account math before enabling `SCALE_OUT_ENABLED`.
