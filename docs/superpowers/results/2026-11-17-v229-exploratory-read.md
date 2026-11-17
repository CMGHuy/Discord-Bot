# v229 exploratory read — deferred entry on the live LONG book

**Spec:** `docs/superpowers/specs/2026-11-14-v229-deferred-entry-counterfactual-design.md`.
**Plan:** `docs/superpowers/plans/2026-11-15-v229-deferred-entry-counterfactual_0-index.md`, Task V229-13.
**Pre-registration:** `docs/superpowers/results/2026-11-17-v229-preregistration.md`; T0 `2026-11-17T18:43:37+00:00`; rule hash `8bbaaa9781535813`.
**Host checkout:** `5dd375ca454250f6aab5c1f86616dec43e0b40b8` (script SHA in the report body: `5dd375ca454250f6aab5c1f86616dec43e0b40b8`); archive last bar `2026-11-17T18:05:00+00:00`.
**Run:** `export_book_rows.sh rows` on the VM host, then the CLI in `append` and `exploratory` mode in the bot container (commands in plan V229-13).
**Exploratory: no verdict, not evidence.** Its window overlaps the data that motivated the idea; it only checks calibration. Nothing in the forward rule changes after it.
**Calibration:** agreement 0.88 on 300 plans, 92 excluded; CALIBRATED: the forward read starts (V229-14).

---
# v229 deferred-entry counterfactual: exploratory read

**EXPLORATORY (no verdict)**

- T0: 2026-11-17T18:43:37+00:00
- Archive last bar: 2026-11-17T18:05:00+00:00
- Script git SHA: 5dd375ca454250f6aab5c1f86616dec43e0b40b8
- Frozen rule hash: 8bbaaa9781535813

Disclosures:

- Single leg to TP1: no runner, no TP2; the live scale-out is not reproduced.
- The control starts at the first bar at or after opened_at, so a stop-out inside the entry bar is missed: this flatters the control and biases d_A downward on exactly the noise stops tested.
- The live path class comes from the export's last leg only: a TP1 partial whose runner leg is labelled scratch classes as scratch.
- Trades still open at the read date are not in the export and are absent from the population.
- All R is net of frictions; arms A and B pay twice the entry slippage (a market order in the last half hour). Gross R is printed beside and gates nothing.
- Arm B's skip is a mechanical wick touch, not a trader's judgement that the level held.

## Population funnel

| reason | count |
|---|---|
| entry_type_unknown | 124 |
| eligible | 392 |
| not_market | 52 |
| close_bucket | 24 |
| outside_session | 129 |
| no_coverage | 10 |
| pending | 43 |
| not_trade | 112 |
| bucket midday | 224 |
| bucket open | 168 |

## Arms

| arm | N | taken | wins | win rate | ExpR net | total R | ExpR gross |
|---|---|---|---|---|---|---|---|
| C | 392 | 392 | 142 | 0.362 | -0.115 | -45.001 | -0.043 |
| A | 392 | 392 | 128 | 0.327 | -0.279 | -109.297 | -0.181 |
| B | 392 | 275 | 94 | 0.342 | -0.178 | -69.796 | -0.110 |

## Deltas

| delta | N | weeks | mean | 97.5% lower | one-sided p |
|---|---|---|---|---|---|
| d_A | 392 | 16 | -0.164 | -0.400 | 0.905 |
| d_B | 392 | 16 | -0.063 | -0.297 | 0.698 |

d_B over the plans B took (disclosure): n=275, mean -0.496

## Calibration

| sim \ live | loss | scratch | win |
|---|---|---|---|
| loss | 145 | 3 | 2 |
| scratch | 11 | 45 | 10 |
| win | 5 | 5 | 74 |

- Agreement: 0.880 over n=300 (threshold 0.80); excluded 92
- Mean R_C -0.115, mean live R +0.010, Spearman 0.753 (information only)

## Per week

| week | N | d_A | d_B |
|---|---|---|---|
| 2026-W31 | 52 | -0.643 | -0.541 |
| 2026-W32 | 38 | -0.093 | -0.057 |
| 2026-W33 | 17 | -0.166 | -0.196 |
| 2026-W34 | 10 | -0.072 | +0.155 |
| 2026-W35 | 5 | -0.463 | -0.800 |
| 2026-W36 | 11 | -0.277 | -0.277 |
| 2026-W37 | 4 | -0.022 | +0.251 |
| 2026-W38 | 14 | +0.486 | +0.218 |
| 2026-W39 | 7 | -0.045 | -0.045 |
| 2026-W40 | 28 | +0.371 | -0.032 |
| 2026-W41 | 21 | +0.356 | +0.347 |
| 2026-W42 | 50 | -0.657 | -0.448 |
| 2026-W43 | 25 | -0.058 | +0.470 |
| 2026-W44 | 45 | -0.163 | +0.216 |
| 2026-W45 | 58 | +0.210 | +0.317 |
| 2026-W46 | 7 | -1.892 | -1.892 |

## Splits

| cell | N | d_A | d_B |
|---|---|---|---|
| fill_above | 211 | -0.655 | -0.641 |
| fill_below | 181 | +0.408 | +0.611 |
| with_events | 47 | -0.214 | -0.319 |
| without_events | 345 | -0.157 | -0.028 |

## Arm B skips

- Skipped: 117; control R of the skipped plans -0.955

## Tradeability

- mean_fill_vs_entry_r: +0.153
- mean_day_low_vs_stop_r: -0.677
- mean_price_1530_vs_entry_r: +0.154
- count_shifted_stop_above_day_low: 240
- count_plan_expired: 0
- count_entry_bar_stopout: 1
- count_earnings_after_close: 5
- count_monthly_opex: 15
- count_fomc: 27
- count_event_day: 47
- first_gap_r: C -0.074, A +0.052, B +0.029
- gap_through_stop: C 35, A 83, B 55
- bar_1530_median: volume +131882.500, range_r +0.236, open_vs_last_close_r +0.064

## Context

- Live LONG trades opened at or after 15:30 ET: n=24, ExpR -0.139

## Bearish disclosure

Never enters the verdict. n=106, d_A -0.156, d_B -0.037

| arm | N | taken | ExpR net |
|---|---|---|---|
| C | 106 | 106 | -0.104 |
| A | 106 | 106 | -0.260 |
| B | 106 | 72 | -0.142 |
