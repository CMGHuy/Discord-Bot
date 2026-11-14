# v226 Stop-width attribution: result

**Run:** 2026-11-14, TRAIN confluence replay 2020-01-06..2023-12-29 (signal date) under the live stop settings, with the live book (closed production trades, read from the local replica) printed beside it and never gating. Read-only; VALIDATION never read.
**Spec:** `docs/superpowers/specs/2026-11-12-v226-stop-width-attribution-design.md`
**Plan:** `docs/superpowers/plans/2026-11-12-v226-stop-width-attribution_0-index.md`

**Verdict: NO CANDIDATE.** Closes "tight stops in ATR terms" as measured; recorded in `docs/claude/backtest-methodology.md` § Closed pre-registrations.

Rule, quoted from the spec (pre-registered; computed once, in this run; later runs are descriptive and never revise it):

> Each bucket (at most 4 looks; `unknown` is disclosed, never a look) is compared
> with **every other TRAIN row with a known `stop_atr`**, using the existing
> week-clustered bootstrap (`expectancy_attribution._look`, 10,000 resamples,
> seed 42). Δ = bucket ExpR − rest ExpR, in net R.
>
> A bucket is a **veto candidate** when all six hold:
>
> 1. Δ ≤ −0.10R (exactly −0.10 passes);
> 2. the upper 95% bound of Δ is < 0 (exactly 0 fails);
> 3. bucket ExpR < 0 (removing a positive-ExpR bucket lowers Total R);
> 4. Δ < 0 in at least 3 of the 4 TRAIN calendar years 2020–2023 (a year with
>    no bucket rows counts against);
> 5. bucket N ≥ 300;
> 6. Benjamini–Hochberg at q < 0.10 over **this study's own family** of bucket
>    looks (at most 4), never pooled with v146's family or with live looks.
>
> Study verdict:
>
> - **`VETO-CANDIDATE`** naming every passing bucket;
> - **`UNDERPOWERED`** when fewer than two buckets reach N ≥ 300. This does
>   **not** close the question;
> - **`NO CANDIDATE`** otherwise. This closes "tight stops in ATR terms" as
>   measured, recorded in `backtest-methodology.md` § Closed pre-registrations.

All figures are as stored in `data/reports/stop-width-attribution.json`: R net of frictions, `ExpR gross` beside it, seed 42, 10000 week-clustered bootstrap resamples.

## Verdict

**Verdict: NO CANDIDATE** -- closes "tight stops in ATR terms" as measured (backtest-methodology.md § Closed pre-registrations).

Candidates: none.
Powered buckets (N ≥ 300): 4 of 4; BH family size 4 (this study's bucket looks only). Computed once on TRAIN; VALIDATION never read.

Edges (TRAIN quartiles of stop_atr, frozen, outcome-blind): 0.23, 0.35, 0.49.

## TRAIN: the six pre-registered clauses

| Bucket | N | ExpR | Δ | 95% CI | p | q | years Δ<0 | 1 Δ≤−0.10 | 2 CI<0 | 3 ExpR<0 | 4 ≥3/4 yrs | 5 N≥300 | 6 q<0.10 | candidate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Q1 (<0.23) | 1767 | -0.1112 | -0.1337 | [-0.3417, 0.0812] | 0.2146 | 0.7015 | 2/4 | yes | no | yes | no | yes | no | no |
| Q2 (0.23–0.35) | 1767 | 0.0451 | 0.0748 | [-0.0841, 0.2374] | 0.3508 | 0.7015 | 1/4 | no | no | no | no | yes | no | no |
| Q3 (0.35–0.49) | 1765 | 0.0091 | 0.0267 | [-0.1397, 0.1926] | 0.7661 | 0.7661 | 2/4 | no | no | no | no | yes | no | no |
| Q4 (≥0.49) | 1770 | 0.0131 | 0.0322 | [-0.1325, 0.1994] | 0.7041 | 0.7661 | 2/4 | no | no | no | no | yes | no | no |

Δ per TRAIN year (bucket ExpR − rest ExpR; n/a = no rows that year, which counts against clause 4):

| Bucket | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|
| Q1 (<0.23) | 0.2215 | 0.2831 | -0.4337 | -0.1875 |
| Q2 (0.23–0.35) | 0.1020 | 0.1416 | 0.1589 | -0.0754 |
| Q3 (0.35–0.49) | -0.4081 | -0.1267 | 0.3396 | 0.0366 |
| Q4 (≥0.49) | 0.1086 | -0.2364 | -0.1785 | 0.1688 |

## TRAIN buckets

Unknown stop_atr rows (outside the edges and the bootstrap base): 0. The clamped share is a lower-bound provenance flag (identity-based, read at run time); None rows leave its denominator.

| Bucket | N | Win% | ExpR | ExpR gross | median RR | clamped share | clamped None | Δ long | Δ short |
|---|---|---|---|---|---|---|---|---|---|
| Q1 (<0.23) | 1767 | 26.4 | -0.1112 | -0.0368 | 2.50 | 1.000 | 0 | 0.0135 | -0.3241 |
| Q2 (0.23–0.35) | 1767 | 30.5 | 0.0451 | 0.1253 | 2.50 | 1.000 | 0 | -0.0397 | 0.2062 |
| Q3 (0.35–0.49) | 1765 | 28.6 | 0.0091 | 0.0852 | 2.50 | 1.000 | 0 | 0.0124 | 0.0486 |
| Q4 (≥0.49) | 1770 | 28.4 | 0.0131 | 0.0883 | 2.50 | 1.000 | 0 | 0.0154 | 0.0545 |

Removal arithmetic (descriptive; ignores replacement trades):

| Bucket | pooled ExpR | ExpR without | ΔTotal R | N removed |
|---|---|---|---|---|
| Q1 (<0.23) | -0.0110 | 0.0224 | 196.5448 | 1767 |
| Q2 (0.23–0.35) | -0.0110 | -0.0297 | -79.6613 | 1767 |
| Q3 (0.35–0.49) | -0.0110 | -0.0177 | -16.0102 | 1765 |
| Q4 (≥0.49) | -0.0110 | -0.0190 | -23.2175 | 1770 |

Mix:

- Q1 (<0.23): direction bearish 0.44, bullish 0.56; horizon 2m 0.09, 2w 0.07, 3m 0.10, 4m 0.10, 4w 0.08, 5m 0.11, 6m 0.11, 7m 0.11, 8m 0.11, 9m 0.10
- Q2 (0.23–0.35): direction bearish 0.45, bullish 0.55; horizon 2m 0.08, 2w 0.04, 3m 0.09, 4m 0.11, 4w 0.05, 5m 0.11, 6m 0.12, 7m 0.13, 8m 0.12, 9m 0.13
- Q3 (0.35–0.49): direction bearish 0.51, bullish 0.49; horizon 2m 0.07, 2w 0.05, 3m 0.08, 4m 0.10, 4w 0.05, 5m 0.11, 6m 0.12, 7m 0.13, 8m 0.14, 9m 0.15
- Q4 (≥0.49): direction bearish 0.50, bullish 0.50; horizon 2m 0.06, 2w 0.05, 3m 0.08, 4m 0.08, 4w 0.05, 5m 0.11, 6m 0.12, 7m 0.15, 8m 0.15, 9m 0.15

## Live buckets (TRAIN edges; printed beside TRAIN, never gates)

Unknown stop_atr rows (outside the edges and the bootstrap base): 808. The clamped share is a lower-bound provenance flag (identity-based, read at run time); None rows leave its denominator.

| Bucket | N | Win% | ExpR | ExpR gross | median RR | clamped share | clamped None | Δ long | Δ short | same-day loss share |
|---|---|---|---|---|---|---|---|---|---|---|
| Q1 (<0.23) | 162 | 25.9 | 0.0009 | 0.0780 | 2.50 | 0.649 | 14 | 0.0339 | n/a | 0.658 |
| Q2 (0.23–0.35) | 106 | 31.1 | -0.1165 | -0.0407 | 2.14 | 0.375 | 18 | n/a | n/a | 0.658 |
| Q3 (0.35–0.49) | 57 | 22.8 | -0.0919 | -0.0165 | 2.06 | 0.400 | 12 | n/a | n/a | 0.591 |
| Q4 (≥0.49) | 154 | 27.3 | 0.0600 | 0.1367 | 2.06 | 0.426 | 25 | 0.1224 | n/a | 0.607 |

Removal arithmetic (descriptive; ignores replacement trades):

| Bucket | pooled ExpR | ExpR without | ΔTotal R | N removed |
|---|---|---|---|---|
| Q1 (<0.23) | -0.0171 | -0.0263 | -0.1499 | 162 |
| Q2 (0.23–0.35) | -0.0171 | 0.0111 | 12.3462 | 106 |
| Q3 (0.35–0.49) | -0.0171 | -0.0070 | 5.2410 | 57 |
| Q4 (≥0.49) | -0.0171 | -0.0537 | -9.2357 | 154 |

Mix:

- Q1 (<0.23): direction bearish 0.26, bullish 0.74; horizon 2m 0.08, 2w 0.27, 3m 0.10, 4m 0.06, 4w 0.24, 5m 0.06, 6m 0.06, 7m 0.04, 8m 0.04, 9m 0.06; family Bollinger lower 0.09, Donchian low 0.06, EMA14 0.01, EMA150 0.01, EMA20 0.02, EMA30 0.01, EMA50 0.01, EMA8 0.01, EMA80 0.01, EMA9 0.01, FVG (bearish) 0.09, FVG (bullish) 0.02, Fib 23.6% 0.01, Fib 38.2% 0.03, Fib 50.0% 0.04, Fib 61.8% 0.09, Fib 78.6% 0.14, Floor Pivot 0.02, Floor R1 0.05, Floor R2 0.04, Floor S1 0.01, Floor S2 0.03, Pivot low 0.01, Rolling support 0.01, Trendline (2x touch) 0.03, Trendline (3x touch) 0.02, Trendline (4x touch) 0.02, Trendline (5x touch) 0.04, Trendline (6x touch) 0.02, Trendline (8x touch) 0.01, Volume Profile HVN 0.04
- Q2 (0.23–0.35): direction bearish 0.15, bullish 0.85; horizon 2m 0.23, 2w 0.18, 3m 0.10, 4m 0.13, 4w 0.17, 5m 0.05, 6m 0.03, 7m 0.06, 8m 0.02, 9m 0.04; family Bollinger lower 0.08, Bollinger upper 0.01, Donchian low 0.03, EMA14 0.01, EMA8 0.01, FVG (bearish) 0.17, FVG (bullish) 0.04, Fib 23.6% 0.07, Fib 38.2% 0.01, Fib 50.0% 0.06, Fib 61.8% 0.08, Fib 78.6% 0.10, Floor Pivot 0.02, Floor R1 0.05, Floor R2 0.01, Floor S1 0.02, Pivot high 0.02, Pivot low 0.01, Trendline (2x touch) 0.03, Trendline (5x touch) 0.05, Trendline (6x touch) 0.02, Trendline (7x touch) 0.02, Trendline (9x touch) 0.01, VWAP 0.02, Volume Profile HVN 0.08
- Q3 (0.35–0.49): direction bearish 0.19, bullish 0.81; horizon 2m 0.18, 2w 0.12, 3m 0.12, 4m 0.05, 4w 0.25, 5m 0.07, 6m 0.04, 7m 0.05, 8m 0.09, 9m 0.04; family Bollinger lower 0.04, Bollinger upper 0.04, Donchian high 0.02, EMA20 0.02, EMA9 0.04, FVG (bearish) 0.21, FVG (bullish) 0.05, Fib 23.6% 0.04, Fib 38.2% 0.04, Fib 50.0% 0.04, Fib 61.8% 0.12, Fib 78.6% 0.12, Rolling resistance 0.02, Trendline (3x touch) 0.02, Trendline (4x touch) 0.04, Trendline (9x touch) 0.02, VWAP 0.04, Volume Profile HVN 0.12
- Q4 (≥0.49): direction bearish 0.07, bullish 0.93; horizon 2m 0.16, 2w 0.11, 3m 0.18, 4m 0.07, 4w 0.12, 5m 0.08, 6m 0.06, 7m 0.09, 8m 0.08, 9m 0.06; family Bollinger lower 0.04, Bollinger upper 0.03, Donchian high 0.01, Donchian low 0.01, EMA13 0.01, EMA14 0.01, EMA20 0.01, EMA250 0.01, EMA30 0.01, EMA300 0.01, EMA350 0.01, EMA40 0.01, EMA60 0.01, FVG (bearish) 0.17, FVG (bullish) 0.06, Fib 23.6% 0.05, Fib 38.2% 0.03, Fib 50.0% 0.02, Fib 61.8% 0.05, Fib 78.6% 0.11, Floor Pivot 0.01, Floor R1 0.01, Floor S1 0.01, Floor S2 0.03, Pivot high 0.01, Rolling resistance 0.02, Rolling support 0.01, Swing high 0.01, Swing low 0.01, Trendline (2x touch) 0.01, Trendline (3x touch) 0.01, Trendline (4x touch) 0.03, Trendline (5x touch) 0.04, Trendline (6x touch) 0.03, Trendline (7x touch) 0.01, Trendline (8x touch) 0.02, Trendline (9x touch) 0.01, VWAP 0.01, Volume Profile HVN 0.06

## stop_atr against atr_pct (disclosed, never a look)

- TRAIN: Spearman rho -1.0000, mirrored-bucket overlap 0.998
- Live: Spearman rho -0.5962, mirrored-bucket overlap 0.526

|rho| between stop_atr and atr_pct is 1.0000 on TRAIN (>= 0.8): this verdict is about ticker volatility, not stop placement.

## What this is

Descriptive, not a veto. Each bucket's filled TRAIN rows are compared with the rest; this does not estimate what a veto would do to pooled ExpR, because a vetoed plan frees a slot that a different plan would take. A VETO-CANDIDATE only licenses the Stage -2 screen and the paired replay that would measure that.

## What each verdict buys

- **VETO-CANDIDATE** licenses a veto idea, not a veto: it must earn a SCREEN-AVOID-PASS from a Stage -2 avoid idea before its spec, and that spec measures the veto on the bot's own replay with replacement trades included (paired).
- **NO CANDIDATE** closes "tight stops in ATR terms" as measured (backtest-methodology.md § Closed pre-registrations).
- **UNDERPOWERED** leaves the question open and names the N that would power it.

## Provenance

- Code: branch `2026-11-12-v226-stop-width-attribution` at `7bf014ddec152c2fd836c63e50691ac111cf0e04`.
- TRAIN rows: `data/reports/v226-train-scenarios.jsonl`, 7069 rows, sha256 `7be02217fef6e8d1e5afa48de4a39a9e7151e64f47f55330ca2adb50cc988b2d`.
- Tickers: `logs/v226/tickers.txt`, from the main checkout's watchlist (watchlist.json sha256 f545ec0c691cb6fabb180778743369db10a18b513afbd7f070d0f74bd15da586 tickers 77).
- Live: live rows 1287 | unknown stop_atr 808 | last closed 2026-11-13T21:06:10.475035+00:00.
- Preflight: stop settings MATCH against production `.env` (compared as hashes; values never printed); store `source alpaca | store watchlist | store_dir E:\Documents\Private\Projects\Discord-Bot\data\market_data | manifest 9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60`, `check_history_store.py --verify-hashes` exit 1: 399 unexplained gap(s), 0 hash problem(s), all in the intraday series (15min 258, hourly 141): mostly 2019-08-12 and 2019-12-24 calendar bar-count artefacts on every ticker, plus ASTS (69) and HIMS (63) pre-listing days in each intraday interval; the daily series has 0 unexplained gaps and the scenario replay reads no intraday series. The partner approved proceeding (2026-11-14). Full log: `logs/v226/store-check.log`.
- Frictions `{"commission_r": 0.02, "slippage_bps": 5.0}`; live fills include frictions: False.

Run sidecar (`data/reports/v226-train-scenarios.jsonl.run.json`):

```json
{
 "command": [
  "--scenarios",
  "--train",
  "--exit-model",
  "v2",
  "--scale-out",
  "--tickers-file",
  "logs/v226/tickers.txt",
  "--trades-jsonl",
  "data/reports/v226-train-scenarios.jsonl"
 ],
 "git_head": "7bf014ddec152c2fd836c63e50691ac111cf0e04",
 "membership_asof": "2026-11-14",
 "stop_settings": {
  "sha256": "6436cc4bd30b88e80a6fbbd2ea358698fd96540e5e8820e816408bd3389c9416"
 },
 "watchlist": {
  "tickers": [
   "AAPL",
   "ABNB",
   "ADBE",
   "AMAT",
   "AMD",
   "AMZN",
   "ARM",
   "ASTS",
   "AVGO",
   "AXON",
   "BA",
   "BKNG",
   "CEG",
   "CRM",
   "CRWD",
   "DDOG",
   "DELL",
   "DOCU",
   "EBAY",
   "FTNT",
   "GD",
   "GEV",
   "GLW",
   "GM",
   "GOOGL",
   "GS",
   "HIMS",
   "HOOD",
   "ILMN",
   "INTC",
   "INTU",
   "IREN",
   "ISRG",
   "JNJ",
   "JPM",
   "META",
   "MRNA",
   "MRVL",
   "MSFT",
   "MSTR",
   "MU",
   "NBIS",
   "NFLX",
   "NKE",
   "NOW",
   "NVDA",
   "ORCL",
   "PANW",
   "PEP",
   "PFE",
   "PLTR",
   "PYPL",
   "QBTS",
   "RKLB",
   "SBUX",
   "SHOP",
   "SNDK",
   "SNOW",
   "SNPS",
   "SOFI",
   "STX",
   "TSLA",
   "UBER",
   "V",
   "WMT"
  ],
  "universe": "watchlist"
 },
 "window": {
  "from": "2020-01-01",
  "to": "2023-12-31"
 }
}
```

Store provenance (`data/reports/v226-train-scenarios.jsonl.provenance.json`):

```json
{
 "adjustment": "all",
 "data_source": "alpaca",
 "excluded": {
  "ASML": "flagged: price-mismatch",
  "CVX": "flagged: price-mismatch",
  "GC=F": "not in store",
  "HD": "flagged: price-mismatch",
  "HPQ": "flagged: price-mismatch",
  "IBM": "flagged: price-mismatch",
  "QCOM": "flagged: price-mismatch",
  "SI=F": "not in store",
  "SPCX": "flagged: short-overlap",
  "UNH": "flagged: price-mismatch",
  "WDC": "flagged: price-mismatch",
  "XAGUSD": "skipped: spot metal (built from futures)",
  "XAUUSD": "skipped: spot metal (built from futures)"
 },
 "feed": "sip",
 "manifest_hash": "9e0a4e0ddd62886d5077f5d27aa86a6f1447b9285ad6af7d6b4af0c292a49b60",
 "store": "watchlist",
 "store_dir": "E:\\Documents\\Private\\Projects\\Discord-Bot\\data\\market_data"
}
```

Hashes (`logs/v226/sha256.txt`; copies sit in the main checkout's `data/reports/` and `logs/v226/`):

```
7be02217fef6e8d1e5afa48de4a39a9e7151e64f47f55330ca2adb50cc988b2d *data/reports/v226-train-scenarios.jsonl
43060c66810dc02bc66f54c70f0c28fcb0e54c97579e106889be6edff95aa7c2 *data/reports/v226-train-scenarios.jsonl.run.json
fe88cb60b9bfe356cdca71d9cc90233764bb06c91ded04b3466ef868eadd6319 *data/reports/v226-train-scenarios.jsonl.provenance.json
54392c7c5b56e478c891e06eab97963aa62e47517d590feb9704add3378735cb *data/reports/v226-train-scenarios.jsonl.done.jsonl
52541185b0c94070147524e4d36249270cbfc577e219bdfcc2786bbfc36e9ba1 *data/reports/stop-width-attribution.json
123dede765a6e2fcd0c9e809fa218e1b75e9d70f41f14af19184200bc2e552a0 *logs/v226/stop-width.md
```

## Observations

Every figure below is read from the tables above; nothing new is computed and no threshold is chosen from them.

- **Unknown `stop_atr`.** TRAIN: 0 unknown of 7069 rows (0%), so all 7069 TRAIN rows sit in the four buckets. Live: 808 unknown of 1287 rows (about 63%); the four live buckets hold the other 479 (162 + 106 + 57 + 154).
- **Δ sign, TRAIN against live (descriptive; live never gates).** The live tables print no per-bucket Δ; its sign is read from bucket ExpR against the live pooled ExpR (−0.0171), equivalently from `ExpR without` against pooled. TRAIN Δ is negative for Q1 and positive for Q2, Q3 and Q4. Live, Q1 (+0.0009) and Q4 (+0.0600) sit above pooled and Q2 (−0.1165) and Q3 (−0.0919) below. The sign differs between TRAIN and live for Q1, Q2 and Q3, and agrees for Q4.
- **Volatility, not placement.** TRAIN Spearman rho between `stop_atr` and `atr_pct` is −1.0000 with mirrored-bucket overlap 0.998 (live: −0.5962, overlap 0.526), and `volatility_note` is true. **This verdict is about ticker volatility, not stop placement.**
- **Clamped share (saturated in TRAIN; see Caveats).** `stop_clamped` is 1.000 in every TRAIN bucket (Q1, Q2, Q3, Q4), with 0 `None` rows: every TRAIN row is flagged, so the flag has saturated and carries no information in TRAIN. Live buckets print 0.649, 0.375, 0.400 and 0.426 (with 14, 18, 12 and 25 `None` rows).
- **Mix.** No TRAIN bucket is above 70% one way on direction (bearish 0.44–0.51) or on any horizon (largest single horizon share 0.15). Every live bucket is above 70% bullish (Q1 0.74, Q2 0.85, Q3 0.81, Q4 0.93); no live horizon share is above 70%. Δ by direction differs in sign from the bucket's Δ in two TRAIN buckets: Q1 (Δ −0.1337; Δ long +0.0135, Δ short −0.3241) and Q2 (Δ +0.0748; Δ long −0.0397, Δ short +0.2062). In Q3 and Q4 both directions share the bucket's positive sign.
- **Removal arithmetic of the decisive bucket** (Q1 (<0.23), the most negative Δ, −0.1337; no bucket is a candidate): pooled TRAIN ExpR −0.0110, ExpR without Q1 +0.0224, ΔTotal R +196.5448, N removed 1767. This ignores replacement trades: a vetoed plan frees a slot that another plan would take.
- **Live same-day losses.** The share of live losses closed on their entry day is 0.658 (Q1), 0.658 (Q2), 0.591 (Q3) and 0.607 (Q4). The spec's 2026-11-12 observation was that about 47% of trades (N = 223, closed 2026-10-29..2026-11-12) stopped out the day they opened. The bases differ (the bucket share is over losses only; the spec's figure is over all trades in a shorter window), so the two sit side by side and are not compared.

## Caveats

- **Descriptive, not a veto.** Each bucket's filled TRAIN rows are compared with the rest. The study does not estimate what a veto would do to pooled ExpR, because a vetoed plan frees a slot that a different plan would take.
- **`stop_atr` is measured from the signal close,** not from the planned entry or trigger (`swingbot/core/edge/context.py`); a truncation test pins it as point-in-time.
- **`stop_clamped` is a lower-bound provenance flag:** identity-based (a natural stop that lands on the clamp is flagged too) and read from `CLAMP_STOP_TO_HARD_CAP` at run time; `None` rows leave its denominator.
- **The live book never gates.** Live N is small and correlated, and the live trades fall inside the v2 instrument's sealed holdout (2026-01-01 onward): any follow-on screened from these tables has seen them and must say so.
- **Fill models differ.** The replay and the live tracker do not model gap fills identically, so live and TRAIN R compare in sign and order, not to the last decimal.
- **The store check exited 1, not 0.** `check_history_store.py --verify-hashes` reported 399 unexplained gaps and 0 hash problems, all in the intraday series (15min 258, hourly 141): mostly 2019-08-12 and 2019-12-24 calendar bar-count artefacts on every ticker, plus ASTS (69) and HIMS (63) pre-listing days in each intraday interval. The daily series has 0 unexplained gaps and the scenario replay reads no intraday series; the partner approved proceeding (2026-11-14). Full log: `logs/v226/store-check.log`.
- **The TRAIN replay was interrupted once.** It stopped at 39/65 tickers (part-1 log `logs/v226/replay-part1.log`) and was resumed with the identical command from its done-list (`resuming data/reports/v226-train-scenarios.jsonl: 39 ticker(s) already done`); the finished run logged `loaded 65/77` and `Wrote 7069 trade rows` (`logs/v226/replay.log`).
- **The study's Markdown was rendered from the saved report.** The study script exited 1 while printing its Markdown to a Windows cp1252 console (`UnicodeEncodeError` on U+2265), after `data/reports/stop-width-attribution.json` had been written. `logs/v226/stop-width.md` was rendered from that saved report with `stop_width_markdown`, with no recomputation; the script now prints UTF-8 (commit `dfb1d99e`). The verdict was computed once.
- **Live `stop_atr` is mostly unknown.** 808 of 1287 live rows have no `stop_atr` (`logs/v226/live-rows.txt`: `live rows 1287 | unknown stop_atr 808`; the report's live unknown count is 808), so the live buckets describe 479 rows only.

- **TRAIN stop placement did not vary (panel finding, quant-engineer 1).** Every TRAIN row is `stop_clamped` (share 1.000, 0 `None`), and Spearman rho between `stop_atr` and `atr_pct` is -1.0000 with mirrored-bucket overlap 0.998. That pattern is what a near-constant `stop_pct` produces (`stop_atr` = `stop_pct` / `atr_pct`): in the replay every stop sat at the clamp, so the four buckets are ticker-volatility (ATR%) bins and the study did not measure stop placement. Live shows 0.375-0.649 clamped. The gap has no verified mechanism. Unverified candidates read from code: (a) the live book mixes strategy-path plans, the replay is confluence-only; (b) later live stop changes (v139 arm S, the v191 ATR band, a v212 limit stop); (c) the identity test uses a 1e-6 percentage-point tolerance, so tick-rounded live stops can read as not clamped; (d) only three stop settings (`CLAMP_STOP_TO_HARD_CAP`, `MIN_STOP_DISTANCE_PCT`, `MAX_STOP_LOSS_PCT`) were compared with production, while `ScanParams.from_config()` reads other stop- and entry-shaping settings from the local `.env`. `stop_clamped` is also measured from the trigger and `stop_atr` from the signal close, so for stop-entry plans `stop_atr` is not exactly 1.75% / ATR%; and ATR is on each horizon's own bar frame.
- **Power (panel finding, quant-researcher 2).** Q1's 95% interval is [-0.3417, +0.0812], half-width about 0.21R, so clause 2 could not fire for a delta much smaller in size than about -0.21R, and the observed Q1 delta of -0.1337 lies inside that blind zone. NO CANDIDATE reads "no effect of about 0.2R or more at these N", not "no effect".
- **Direction (panel finding, quant-researcher 3).** Q1's negative delta comes from shorts: delta by direction short -0.3241, long +0.0135. Any short-only, low-`stop_atr` follow-on is a post-hoc subgroup of this table and must say so.
- **Universe (panel finding, quant-researcher 4).** The universe is today's watchlist (membership as of 2026-11-14) and 65 of 77 tickers loaded; the exclusions (price-mismatch flags such as ASML, CVX, HD, QCOM, UNH, WDC, plus spot metals and tickers absent from the store) are in `logs/v226/replay-part1.log`. Because the buckets are in effect ticker-volatility bins, the ticker set decides the edges and who fills them. The 7069 rows (the spec expected about 5,558) are not explained here.
- **Run head.** The replay's sidecar `git_head` is `7bf014dd` (the commit the replay started at); later branch commits changed documentation, tests and the study script's print path only.

## What follows

Closed as measured: a TRAIN quartile cut of `stop_atr` (stop distance in ATR14 units) under the replay's stops, which were all clamped, so this tested ATR% bins and not stop placement. Natural (unclamped) stop placement relative to ATR was never measured and stays open. Recorded in `docs/claude/backtest-methodology.md` § Closed pre-registrations. Reopening needs a mechanism other than "a TRAIN quartile of stop distance in ATR14 units".

## Panel review

Close-out panel on the merged diff (`42f16c50..3432cbd5`) and this document, 2026-11-14: `quant-researcher` (6 findings, all ADVISORY) and `quant-engineer` (1 BLOCKING, 7 ADVISORY). The verdict was not re-run and no number above changed; every applied item is a disclosure or wording change.

- quant-engineer 1 (BLOCKING): saturated clamp flag, rho -1.0000, and the unexplained live 0.375-0.649 -- applied (Caveats "TRAIN stop placement did not vary", Observations bullet, What follows, the closed row).
- quant-researcher 1: "closes tight stops in ATR terms" over-claims; same evidence as engineer 1 -- applied (What follows and the closed row now say natural-stop placement was never measured and stays open).
- quant-researcher 2: the test could not detect about -0.2R or smaller -- applied (Caveats "Power").
- quant-researcher 3: Q1's negative delta is carried by shorts -- applied (Caveats "Direction"; the closed row names a short-only cut as a post-hoc subgroup).
- quant-researcher 4: universe is today's watchlist, 65 of 77 loaded, 7069 rows unexplained -- applied as disclosure (Caveats "Universe"); the 7069 versus 5,558 difference stays unexplained.
- quant-researcher 5: the ledger p 0.2146 is the minimum of 4 looks and enters the ledger-wide family as a single p; the study's own q is 0.7015 -- rejected as a ledger edit (rows are written only by `scripts/reports/preregistration_ledger.py`, ledger q-values never gate); recorded here instead.
- quant-researcher 6 (parity, out of seat) -- covered by engineer 1.
- quant-engineer 2: only 3 stop settings compared with production -- applied (in the Caveats item, candidate (d)); widening the preflight is a follow-on for any re-measurement, not for this closed verdict.
- quant-engineer 3: `stop_clamped` from the trigger and `stop_atr` from the close; ATR on the horizon frame -- applied (same Caveats item).
- quant-engineer 4: resume does not check each done entry's `rows` against surviving rows -- not applied: the code is merged and green; recorded as a hardening idea (assert `entry["rows"]` on resume), no behaviour change made in a close-out.
- quant-engineer 5: run head -- applied (Caveats "Run head": sidecar `git_head` `7bf014dd`).
- quant-engineer 6: identical resample draws across buckets make the 4 looks correlated -- noted, no change (a plumbing observation; the pre-registered rule fixes one seed).
- quant-engineer 7: quartile freezing is TRAIN-only with no outcome leakage; 808 of 1287 live rows unknown is disclosed -- no defect.
- quant-engineer 8: store and cache use -- the doc asserts the replay reads only the daily series; the panel did not verify it. Recorded as unverified by the panel.
