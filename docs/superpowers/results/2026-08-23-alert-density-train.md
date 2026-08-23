# Alert-density expectancy — TRAIN measurement

**Plan:** `docs/superpowers/plans/2026-08-22-v51-alert-density-expectancy.md`
**Window:** TRAIN, 2020-01-01 … 2023-12-31 (entry dates). VALIDATION was not read.
**Run date:** 2026-08-23
**Payload:** `docs/superpowers/results/2026-08-23-alert-density-train.json`
**Verdict:** the pre-registered hypothesis is **not supported**, and the measure
as pre-registered turns out not to test the mechanism the plan named. The idea is
closed in this form. See "What would actually test the hypothesis" for the one
thing a successor could pre-register.

---

## What was measured, stated before the numbers

**Density definition** (fixed in code before any data contact, and not
revisited): a trade's density is the number of trades **opened on the same
calendar date** across the whole universe, counted in the same backtest run,
**including itself**. Entry date comes from `opened_at`.

This is a **proxy for alert count — not every alert becomes a trade.** In both
populations `opened_at` is the **signal bar's** date: that is what
`BacktestTrade.entry_date` already is (`backtest.py` stamps `df.index[i].date()`
for signal index `i`), and it is what `run_scenario_backtest` windows confluence
trades by ("start/end restrict SIGNAL dates"). It is the day the setup fired, not
necessarily the day a stop-entry order filled.

**Buckets**, frozen before any number was read:

| bucket | trades opened that day |
|---|---|
| `quiet` | 1 |
| `normal` | 2–3 |
| `busy` | 4–7 |
| `flood` | 8 or more |

**Configuration.** 68 tickers × 10 horizons. Exits v2 + scale-out, frictions on
— the deployed configuration. The confluence population comes from the scenario
replay (`replay_scenarios` + `simulate_exit`, the same primitives
`backtest_scenarios._replay_ticker` uses); the named-strategy population comes
from `run_backtest` across all 11 strategies. Plans that never triggered are
excluded: a plan that never opened cannot contribute to a day's density.

**Universe.** 78 watchlist tickers, of which 68 were usable: 3 uncached, 2
excluded illiquid, 5 excluded bad data (same exclusion sequence as
`run_backtest_range.run_scenario_mode`).

`N` below counts **closed** trades (the expectancy denominator, including
scratches and timeouts, as `pool()` does). `Win%` is over win/loss only, so its
denominator is smaller — both are given per bucket in the JSON payload.

---

## The tables

Every bucket is reported, including empty ones. None were empty here.

### Confluence scan only — the population the hypothesis is about

Pooled: 4644 closed / 3873 evaluated, 36.7% WR, **+0.027R**, +126.23R total.

| bucket | range | N | share | n_eval | Win% | ExpR | total R |
|---|---|---|---|---|---|---|---|
| `quiet` | 1 | 141 | 3.0% | 117 | 38.5 | −0.001 | −0.10 |
| `normal` | 2–3 | 385 | 8.3% | 313 | 35.5 | −0.007 | −2.86 |
| `busy` | 4–7 | 1077 | 23.2% | 915 | 30.6 | **−0.110** | −118.61 |
| `flood` | 8+ | 3041 | 65.5% | 2528 | 39.0 | **+0.081** | +247.79 |

### Named strategies only

Pooled: 4163 closed / 3012 evaluated, 45.7% WR, +0.226R, +939.31R total.

| bucket | range | N | share | n_eval | Win% | ExpR | total R |
|---|---|---|---|---|---|---|---|
| `quiet` | 1 | 164 | 3.9% | — | 39.3 | +0.119 | +19.46 |
| `normal` | 2–3 | 519 | 12.5% | — | 40.2 | +0.159 | +82.75 |
| `busy` | 4–7 | 709 | 17.0% | — | 44.1 | +0.190 | +134.46 |
| `flood` | 8+ | 2771 | 66.6% | — | 47.5 | +0.254 | +702.64 |

### All trades pooled

Pooled: 8807 closed / 6885 evaluated, 40.6% WR, +0.121R, +1065.54R total.

| bucket | range | N | share | Win% | ExpR | total R |
|---|---|---|---|---|---|---|
| `quiet` | 1 | 72 | 0.8% | 39.0 | +0.062 | +4.45 |
| `normal` | 2–3 | 451 | 5.1% | 40.9 | +0.113 | +50.95 |
| `busy` | 4–7 | 1321 | 15.0% | 35.3 | +0.006 | +7.82 |
| `flood` | 8+ | 6963 | 79.1% | 41.7 | +0.144 | +1002.31 |

### How dense the days actually are

| population | days | trades/day min / median / mean / max | days per bucket |
|---|---|---|---|
| confluence | 719 | 1 / 5 / 6.5 / 39 | quiet 141, normal 156, busy 201, flood 221 |
| strategies | 713 | 1 / 3 / 5.8 / 75 | quiet 164, normal 217, busy 142, flood 190 |
| all | 941 | 1 / 7 / 9.4 / 84 | quiet 72, normal 179, busy 247, flood 443 |

The day counts are well spread across buckets, so the bucket edges are not
degenerate at the *day* level. Trades nevertheless concentrate in `flood`
(65–79%), because flood days carry many trades each — that is arithmetic, not a
finding.

---

## Observations

**1. There is no monotone decline. The hypothesis is not supported.** On the
confluence population expectancy falls from `quiet` (−0.001) through `normal`
(−0.007) to `busy` (−0.110) and then **reverses hard** at `flood` (+0.081), which
is also the largest bucket at 65.5% of trades. "More alerts on a day → worse
expectancy" is false as stated: the densest bucket is the second-best one. A
single negative cell in the middle of a non-monotone series, with the extreme
bucket positive, is not a gradient to build on.

**2. The measure is dominated by horizon depth, not ticker breadth — so it does
not test the mechanism the plan named.** This is the most important observation
in this document. The plan's hypothesis is that "many simultaneous alerts are one
market-wide condition **wearing many tickers**." The per-day provenance says that
is not what a dense day is:

| confluence bucket | trades/day | distinct tickers/day | distinct horizons/day | trades per ticker |
|---|---|---|---|---|
| `quiet` | 1.0 | 1.0 | 1.0 | 1.00 |
| `normal` | 2.5 | 1.6 | 2.4 | 1.57 |
| `busy` | 5.4 | 2.0 | 4.9 | 2.63 |
| `flood` | 13.8 | 3.5 | 8.5 | **3.94** |

A confluence `flood` day is 13.8 trades spread over only **3.5 tickers** and 8.5
horizons — roughly **four trades per ticker**. Density here is mostly *one setup
counted once per timeframe*, which is spec v49's pathology one level down, not
market-wide breadth. Whatever the `busy` cell's −0.110R is, it cannot be
attributed to "one condition wearing many tickers", because on these days there
are only two or three tickers involved.

**3. Density is partly a volatility proxy.** Mean absolute SPY daily move by
confluence bucket: `quiet` 0.867%, `normal` 0.886%, `busy` 0.870%, `flood`
**1.429%**. Flood days move the benchmark ~64% more than every other bucket.
More volatility crosses more levels and triggers more scenarios across more
horizons, which is a mechanical reason for density rather than an edge.

**4. The named-strategy population rises monotonically with density, which is
the regime reading Task 4 was told to check for.** Strategies go +0.119 → +0.159
→ +0.190 → +0.254, with win rate climbing 39.3% → 47.5%, and their `busy`/`flood`
days carry a positive mean SPY return (+0.317% / +0.251%). Busy days are simply
good days for these strategies. This is the "busy days are trending days where
every setup works" artefact the plan predicted, and it appears plainly in the
population that is *not* the hypothesis target. It means density is entangled
with regime, and any future density work has to control for regime rather than
assume density is independent of it.

**5. The premise the plan rests on does not reproduce on TRAIN in this
configuration, and that is worth recording separately.** The plan's `Edge:` line
starts from the book's confluence figure of 53.5% WR / **−0.171R** over 4641
trades. That figure is **VALIDATION (2024–25)**. Measured on TRAIN with v2 exits
and scale-out, this run's confluence population is 36.7% WR / **+0.027R** over
4644 closed trades — near break-even and *not* negative, with a much lower win
rate and a positive expectancy (bigger winners, fewer of them). Same scanner,
different window, qualitatively different picture. This run was not designed to
explain that gap and does not: it is one window, one exit configuration, and the
win-rate conventions differ (this document's `N` includes scratches and
timeouts). Recording it because CLAUDE.md's instruction is to re-derive the
pooled numbers rather than quote them, and re-deriving on a second window did not
agree. **Anyone about to build on "confluence is a negative-expectancy
population" should re-derive it first, on the window they actually intend to
act on.**

---

## What would actually test the hypothesis

Not drafted here as a gate, and not run: the plan has no shot to spend, and
redefining density after seeing this result is exactly the failure the one-shot
discipline exists to prevent. Recording the requirement only, for whoever
pre-registers a successor:

The stated mechanism is **breadth** — many *tickers* alerting at once. This
measurement counted *trades*, which turned out to be ~4× depth-dominated at the
dense end. A successor spec would need density defined as **distinct tickers
alerting on a day** (or alerts per ticker-day collapsed to one), pre-registered
before contact, and it would need to control for the benchmark's move that day,
because observation 3 shows the two are entangled. Whether that is worth a shot
is a separate judgement — note that the depth dimension it would isolate is
v49's territory, and v49 closed as no-lift.

---

## Live cross-check — anecdote only

`data/scan_telemetry.jsonl` covers **11 days** (2026-08-07 … 2026-08-23), 1412
scan records, 600 alerts: **median 28 alerts/day, mean 54.6, min 8, max 260 — all
11 days land in `flood`.**

At n=11 days this cannot confirm or refute anything, and it counts a different
quantity (alerts *posted*, where this measurement counts trades *opened*). It is
here to catch a gross definitional error, and it catches one worth stating: live
alert volume runs an order of magnitude above the `flood` floor of 8. The bucket
edges were chosen for a trade-count proxy on a 75-ticker universe and they do
discriminate at the day level in the backtest, but they are **not** calibrated to
live alert counts, and nobody should read `flood` here as "a normal live day".

---

## Reproduction

```bash
python scripts/data/fetch_backtest_data.py        # once, network
python scripts/backtest/measure_alert_density.py --train \
    --json docs/superpowers/results/2026-08-23-alert-density-train.json
```

~33 minutes on 12 cores (11 workers), 68 tickers × 10 horizons × 2 populations =
1360 units, one flushed progress line per unit. `--dump-trades <path>` writes all
8807 raw trade records for audit; they are deliberately not committed, since a
multi-MB JSON in this repo is a context landmine.

**Do not read the committed JSON whole** — it is 608 KB, mostly the ~2400
per-day rows across the three populations. Query it (`python -c "import json;
d=json.load(open(...)); ..."`) the way the tables above were produced. This
document is the readable summary; the JSON is the payload behind it.
