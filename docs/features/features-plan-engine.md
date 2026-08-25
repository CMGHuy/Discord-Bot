# Features — bot runtime and Plan Engine v2

Event-loop responsiveness, and how a validated trade plan is built with badges and scale-out.

Part of the features documentation — index at [features.md](features.md).

## Event loop responsiveness

All the heavy work — Yahoo Finance fetches, pandas/indicator computation,
matplotlib chart rendering, backtesting — runs in a background thread via
`asyncio.to_thread()`, never directly on Discord's event loop. Without
this, a scan or backtest that takes more than ~10 seconds blocks the
gateway heartbeat and Discord can flag the bot as unresponsive
(`discord.gateway Shard ID None heartbeat blocked`). A scan lock
(`asyncio.Lock`) also ensures the automatic session scan and a manual
`!check` can't run their file-writing work at the same time. This applies
to every command that fetches data or renders a chart: `!check`,
`!ticker`, `!backtest`, `!backtestwatchlist`, `!charts`, `!scrapeall`,
`!download`, `!pnl`, `!trade`, `!tradecharts`, `!watchlist add`.

## Plan Engine v2: validated trade plans with badges and scale-out

Every trade plan the bot emits can be produced by one shared engine
(`swingbot/core/planning/plan_engine.py`) whose exit behavior was backtested under a
train/validation split — so live behavior equals backtested behavior by
construction. Rollout is gated by three flags (all in `.env` / the admin
UI's "Plan Engine v2" section, hot-reloadable):

| Flag | Values | Meaning |
|---|---|---|
| `PLAN_ENGINE_V2` | `off` / `shadow` / `on` | `off` = legacy behavior. `shadow` = v2 plans are computed and logged to `data/shadow_plans.jsonl` during scans but not posted (parity evidence for the cutover — compare with `python scripts/reports/shadow_parity_report.py`). `on` = alerts price and emit v2 plans. |
| `SCALE_OUT_ENABLED` | `true`/`false` | At TP1, close 50% and move the stop to the **runner floor** — entry plus 2/3 of the entry→TP1 move (v39; it was plain break-even before) — while the runner rides toward TP2 with a chandelier ATR trail that only ratchets that floor further into profit. Enable only after `PLAN_ENGINE_V2=on` has run cleanly. |
| `INTRADAY_MANAGER_V2` | `true`/`false` | The 60s monitor manages the full plan lifecycle (PENDING → ACTIVE → PARTIAL → CLOSED): entry triggers, break-even moves, TP1 partials, runner trail, invalidation — with a Discord alert per transition. `!plans` shows the live board. |

**Defaults ship fully live** (`PLAN_ENGINE_V2=on`, `SCALE_OUT_ENABLED=true`,
`INTRADAY_MANAGER_V2=true`) so a fresh deployment runs the validated engine
immediately with no staged rollout required. If you'd rather stage it
yourself: `shadow` for ≥5 scan sessions (compare against legacy numbers via
`python scripts/reports/shadow_parity_report.py`) → `on` for ≥5 clean sessions →
enable scale-out + manager.

**The validated numbers below predate v39's runner floor.** Every win-rate
and expectancy figure quoted for the scale-out exit model was measured with
the runner's stop starting at plain break-even. v39 starts it at
`entry + 2/3 × (tp1 − entry)` instead (`plan_engine.runner_floor`), which is
strictly more protective of realized gains and never less — so it shipped
default-on without a pre-registered re-validation, unlike every entry in
`docs/claude/backtest-methodology.md`'s closed-pre-registrations table.
Treat the cited numbers as a floor on the new model's performance, not a
measurement of it, until a fresh TRAIN/VALIDATION run against the new floor
is done.

**Target selection (v31): structural, banded, honest about "no setup."**
Every plan's target is a real price level, not a fixed fraction of its own
risk. `plan_engine.select_structural_target` picks the nearest candidate
level beyond entry that pays at least `MIN_RISK_REWARD_RATIO` (1.5) against
the plan's own risk, capped at `MAX_RISK_REWARD_RATIO` (2.5) — a level
farther out than the cap doesn't disqualify the setup, it becomes TP2
instead. Each strategy supplies its own candidate list: the unified level
map for confluence-source plans, the fib swing/retracements/extensions for
Fibonacci, the classic wave-3 projections for Elliott Wave, rolling
structural highs/lows plus a volume-strength band for Support/Resistance,
and an ATR ladder for the eight strategies with no native price structure
(volatility itself is the structure). **When nothing on that list clears
the floor, the plan is `None` — a real "no trade here" answer, not a
fallback to a smaller, arithmetic-derived target.** A scan that filters a
ticker out this way counts it under `filtered_by_rr` in the scan-summary
log rather than silently dropping it; `!ticker` says "no qualifying setup:
no level beyond entry pays X:1 against its own stop" instead of just
omitting the trade-plans section.

**Badges: what they legally claim.** Every v2 plan is stamped from
`swingbot/core/validation_registry.json`:

- ✅ **VALIDATED** — this plan's signal source cleared `win_rate ≥ 80%,
  expectancy > 0, N ≥ 15, scratches+timeouts ≤ 50%` on the **held-out
  2024–2025 window it was never tuned on** (tuning used 2020–2023 only,
  and each source got exactly one validation shot). The badge line shows
  the actual N / win-rate / expectancy behind the claim.
- ⚠️ **WEAK** — the source did not clear that bar out-of-sample. Weak
  plans are **never suppressed**; they carry a caution block with the real
  numbers instead. A win rate printed on a badge is always an
  out-of-sample number, never a train number.

The registry regenerates only from validation runs
(`python scripts/backtest/run_backtest_range.py --validation --exit-model v2
--scale-out --emit-registry swingbot/core/validation_registry.json
--run-date <date>`), never by hand.

**Rescue outcomes.** Round 1 validated 6 of 11 strategies out-of-sample;
each of the other 5 got one pre-registered rescue attempt (a new opt-in
gate, TRAIN-only tuning, then a single validation-window look, no
retuning after). Only **RSI** cleared the bar (range-regime gate,
100% WR / N=30), bringing the total to **7 of 11 VALIDATED**. RSI
Divergence and MA Ribbon's gates never qualified on TRAIN; Elliott Wave
and EMA Crossover both passed TRAIN comfortably but missed the 80%
out-of-sample floor by a few points and stay WEAK. Full scoreboard and
pooled numbers: `docs/superpowers/results/2026-07-v2-final-report.md`.
