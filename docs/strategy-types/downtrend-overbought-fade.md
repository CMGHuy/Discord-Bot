# Downtrend Overbought Fade (v113 Part A, short-only, masked)

`ENTRY_FUNCS["Downtrend Overbought Fade"]` = short-only wrapper over
`fade_frame` (`swingbot/core/market/short_entries.py`) · sizing `_fade_plan`
in `swingbot/core/planning/short_builders.py` · plan shape
`PLAN_SHAPES["Downtrend Overbought Fade"]` in `swingbot/core/planning/params.py`
· gate **bearish only, ships masked** (`STRATEGY_GATES["Downtrend Overbought
Fade"] = {"directions": ()}`) and lives on the masked `1w` horizon only.
**It is never live: it never alerts and no scan selects it.** It closed
NO-LIFT at Stage 1 on TRAIN, so its holdout shot was never spent. Shared
rules: [shared-mechanics.md](shared-mechanics.md), in particular §8 (the `1w`
horizon, `cells`, the reward floor and the `limit` entry type).

## Idea

A stock in a confirmed downtrend that bounces hard for a day or two gets
overbought on a very short RSI. The premise was that such a bounce is a
counter-trend rally that fades back toward the downtrend within a week, so
selling the spike with a tight stop and a small fixed target should pay. It
was the only mechanism v113 built for short-horizon bearish days.

## Entry rule

All constants are fixed by the v113 spec and its pre-registration; only `m`
(below) was gridded.

- **Downtrend:** `close < SMA200` and `SMA200 < SMA200[t-20]` (a falling
  200-day average over 20 bars).
- **Spike:** `RSI(2) >= 90`.
- **Earnings clear:** no earnings reaction in the next 7 bars
  (`evt_bars_to_next` outside `[0, 7]`). This reads the scheduled next report
  date, the one sanctioned forward-looking exception (v104 §3.4). Without
  `evt_bars_to_next` in the frame the strategy returns no signal (silent, as
  Earnings Gap Drift does).
- **Horizon-independent:** the signal ignores `horizon_key`; the mask keeps it
  on `1w`.

## Plan and exits

- **Entry:** a sell **limit** at the signal bar's close, good for one bar
  (`expiry_bars` 1, so bar t+1 only). It fills when that bar's high reaches
  it, at `max(open, limit)` (a gap up through it fills at the open). No fill,
  no trade. Fill-bar rule: shared-mechanics §8.
- **Stop:** `entry x 1.02` (2%), the `1w` ceiling. A stop beyond the horizon's
  ceiling drops the plan, never capped.
- **Target:** `TP1 = entry - m x (stop - entry)`, one target for the whole
  position (`tp1_fraction` 1.0). **Grid `m` in {1.0, 1.25, 1.5}, loosest 1.0.**
  `1w` carries a 2.0% reward floor, which no plan hit (floor-drop rate 0.000 at
  every `m`).
- **No break-even move** (`breakeven_trigger_fraction` 1.0) and no runner: the
  single-leg exit walk applies; a plan still open after the horizon's 7
  holding days times out.

## Measured

Part A, bearish, `1w`, TRAIN 2010-01-01..2025-12-31, universe 74. Source:
`docs/superpowers/results/2026-09-30-v113-partA.json` / `-partA.md`.

| `m` | N | WR | ExpR | Bootstrap lower bound | Tier |
|---|---|---|---|---|---|
| 1.0 | 1045 | 35.50% | −0.128 | −0.196 | none |
| 1.25 | 1027 | 32.62% | −0.090 | −0.167 | none |
| 1.5 | 1004 | 29.78% | −0.056 | −0.141 | none |

**NO-LIFT at Stage 1.** Tier 1 failed on WR and ExpR at every `m`; Tier 2
failed on ExpR and the lower bound at every `m`. There is no plateau and no
winner. ExpR is negative at every `m`; the best WR is 35.50% at N=1045
(`m` 1.0). Stage 2's 13 walk-forward folds (test years 2013-2025, all at
`m` 1.5) reported clears=False, with 13 qualifying and 4 positive; 2016 (N=76,
WR 17.11%, ExpR −0.446) and 2023 (N=107, WR 22.43%, ExpR −0.264) are the
worst. The cap-bind rate is 0.993 at every `m`, context only, not a verdict.

**Holdout: none spent.** `proceed_to_holdout` was False, so the one-shot
2026 window is untouched (`results/2026-09-30-v113-holdout.md`). The live-parity
tasks (earnings context at alert time, limit entry, whole-position target,
time stop, resting-order alert line, unmask) were skipped. Reopening needs a
new mechanism, not another `m` and not a second look at this population
(`docs/claude/backtest-methodology.md`'s v113 rows).

## Pseudocode

```python
if "evt_bars_to_next" not in df: return no_signal

downtrend = Close < SMA(Close, 200) and SMA200 < SMA200.shift(20)
spike     = RSI(Close, 2) >= 90
clear     = not (0 <= evt_bars_to_next <= 7)
fire if downtrend and spike and clear

entry  = Close[t]                     # sell limit, live for bar t+1 only
stop   = entry * 1.02
target = entry - m * (stop - entry)   # m in {1.0, 1.25, 1.5}; whole position
```
