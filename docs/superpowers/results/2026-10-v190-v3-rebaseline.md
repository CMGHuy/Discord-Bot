# v190 re-baseline: instrument v3 (PIT S&P 500 on the Alpaca store)

*describes an instrument change; never a lift; selects nothing*

**Spec:** `docs/superpowers/specs/2026-10-24-v190-pit-alpaca-universe-design.md`
**Plan:** `docs/superpowers/plans/2026-10-24-v190-pit-alpaca-universe_0-index.md`
**Code:** `f76e608433630881bd9265a72db4891da6a5cf11`
**Integrity:** frozen `_integrity.json` sha256 `15fc954888263f3a8041a8387416cdf12ec10cd605cbeb9c7eff0c83c725f99b`; see `2026-10-v190-pit-integrity.md`.

## Inputs

Legs, run 2026-10-31 (20:00-22:05 UTC), one strategy per chunk, all 11 strategies, both directions:

- Leg A: `run_backtest_range.py --instrument v3 --tp2 none --train --exit-model v2 --scale-out --strategy "<name>" --json ... --trades-jsonl ...`
- Leg B: `run_backtest_range.py --instrument v1 --data-source alpaca --tickers-file watchlist.txt --train --exit-model v2 --scale-out --strategy "<name>" --json ... --trades-jsonl ...`

Both ran through a wrapper (`data/backtest_results/v190/run_smoke_local.py`) that only stubs the database-backed watchlist read in the run-end report line; it changes no trade. Leg A carries the AABA, INFO, LB, SE, STI and WYND removal recorded in the integrity results doc (they place no trades).

| Leg | Strategy | Rows | sha256 |
| --- | --- | --- | --- |
| A | break-retest | 3666 | `0209e484b9f4fb9aa9f9339b0ff01c20283334e9aee6f4da9dbe40b42a9a77b7` |
| A | elliott-wave | 1650 | `014acaa253ef9e43aeddf009879b6cc64a15d4fa31088647fda7e32980c6158b` |
| A | ema-crossover | 1109 | `7ae9284c89cb919e5288a0ab4292ef0f98011aa6fe86a551e0c080c840bfe689` |
| A | fibonacci | 6492 | `b80f09fea75659f619df86c4e026e33135dbced8297e9b73df190a00fecb77e0` |
| A | ma-ribbon | 6551 | `40bbae250c2b7150f84fc8a2a0b27f557d294582e9d64f302c4b0ce5a907ac85` |
| A | macd | 4805 | `46dbf63c22ee6775c06f6513bbee843ff80f014797a3de89b91a1e43bde146cc` |
| A | rsi-divergence | 38068 | `c4c0d39e79a80e821850687b4e7850f3020236c126693f93251967658d496cbe` |
| A | rsi | 577 | `08ff6e66f1bf756138dc9a45f0d2c9b2450dc62b83028f6e4b60c8f2a05db9ba` |
| A | support-resistance | 5318 | `92c68398bbc15b27647e4d6a760b7833290ab9e89c9e2aa675d432301693705c` |
| A | volume-profile | 2477 | `007a960183b1996a010398fb6b48d83e2d56a721e4f0acb09f97ae0450e1e985` |
| A | vwap | 2504 | `1143d710ad4c7818d84329949b1aeffd3594155da69b8f935e33a1af9898fbf4` |
| B | break-retest | 120 | `10f781fac63db6407fad4ba52d5624a4fe527a55fcc7b9efd096e9141592356c` |
| B | elliott-wave | 148 | `3ac95f4d1233260f9a6e98c649b020d9f913e343edde4852a6a05c87639176a5` |
| B | ema-crossover | 65 | `ce181529ac15d19fbc583310528435b26a9ff91a760d47571679ca928ce83273` |
| B | fibonacci | 353 | `8bd9be48b0c2dfc590d8f123eb0b5fd71154356ad390c03a6b6a9dfa32cc8a9f` |
| B | ma-ribbon | 282 | `5bee51a38ff4bec3eefdcde34cdc513bca78692d47cd90b6645162b7a4635bfc` |
| B | macd | 179 | `5cb6125a31c4a5d6388a8c0b9c3b78e7e0ebdee82d9e8a102c6bff475647ef44` |
| B | rsi-divergence | 1936 | `8cff0a53f44008c0fbe97bbbe26130dcd22906d8d76ff143a93e74bbdb37ff96` |
| B | rsi | 60 | `55ed915b9016916d54c60daffaac394f5e34e0ffc4ab4a8e94692d91b86c3efa` |
| B | support-resistance | 342 | `2da181fefeac6266403f0a4834ea083ecc76fcb9e69258b05a38e4f7fb627d07` |
| B | volume-profile | 82 | `fe53b4ed1a59922b21cf8ea1f2af1512f5df79d0828c28346c72c1a01a784339` |
| B | vwap | 78 | `2036278e27bb6a1c036f7a27faadebe49dea7d5dcface98ce45e08a98025634d` |

Watchlist file: 77 lines, sha256 `c4ad25acea2c59d6d86e2fac16e19847c4028b90b26f6055b6c7e230b36e4862`.
Seeds: ticker 190, week 42 (`stats.WEEK_BOOTSTRAP_SEED`); 10000 resamples.

## How this may be cited

A later spec may cite only the power columns (N, the A/B and C/B ratios, coverage, first counted dates, MDE). WR and ExpR below are description only. Any v3 badge or default-instrument rule is frozen before this table is read, or is scored on the 2026 holdout alone.

# v190 re-baseline: instrument v3

*describes an instrument change; never a lift; selects nothing*

Every v3 fold is in-sample or tainted for today's strategies: test years 2021-2023 lie inside v1 TRAIN, which tuned every live setting, and 2024-2025 is v1 VALIDATION. No out-of-fold figure below is out-of-sample, and the 2021 fold has a little under four effective training years (the regime gate's ~320-bar warm-up eats into 2017).

Confluence is not measured on legs A and C: run_backtest_range --scenarios is refused under every non-v1 instrument (scan replay is unwired there). No v1 figure stands in for it.

Leg B uses the v1 cost model (zero commission and financing); legs A and C use v2/v3 fills and costs. WR and ExpR across legs are not like for like.

| Leg | Instrument / universe |
| --- | --- |
| A | v3, PIT S&P 500 |
| C | v3, watchlist PIT members |
| B | v1, watchlist |

## Power (citable)

Bootstrap resamples: 10000.

| Leg | Population | N | Tickers | Weeks | mde_r_formula | mde_r_ticker | mde_r_week |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | fold-train 2017-01-01..2024-12-31 (purged) | 65619 | 586 | 413 | +0.076 | +0.080 (seed 190) | +0.110 (seed 42) |
| C | fold-train 2017-01-01..2024-12-31 (purged) | 6455 | 52 | 401 | +0.238 | +0.236 (seed 190) | +0.264 (seed 42) |
| B | TRAIN 2020-01-01..2023-12-31 | 3645 | 61 | 200 | +0.285 | +0.295 (seed 190) | +0.309 (seed 42) |

Population N ratios: A/B = 18.002; C/B = 1.771.

cells: 11 strategies × 2 directions × 10 horizons × 3 legs = 660 (249 non-empty)

### Coverage

Integrity SHA-256: `15fc954888263f3a8041a8387416cdf12ec10cd605cbeb9c7eff0c83c725f99b`.

Tickers: 821; admitted: 754; no bars: 44; trimmed: 30; with signal cuts: 58.

| Exclusion reason | N |
| --- | --- |
| identity re-derived: flagged: price-mismatch | 55 |
| identity re-derived: flagged: short-overlap | 5 |
| in-span break 2020-04-01 (price): resolve by hand | 1 |
| in-span break 2021-10-04 (volume): resolve by hand | 1 |
| in-span break 2023-03-13 (volume): resolve by hand | 1 |
| in-span break 2023-06-07 (price+volume): resolve by hand | 1 |
| no daily bars in the store window | 2 |
| unresolved break 2023-03-09 (edge) | 1 |

### First counted entry

| Leg | Strategy | First entry |
| --- | --- | --- |
| A | Break & Retest | 2017-01-04 |
| A | EMA Crossover | 2017-01-05 |
| A | Elliott Wave | 2017-01-09 |
| A | Fibonacci | 2017-01-04 |
| A | MA Ribbon | 2017-01-04 |
| A | MACD | 2017-01-06 |
| A | RSI | 2017-05-09 |
| A | RSI Divergence | 2017-01-04 |
| A | Support/Resistance | 2017-01-04 |
| A | VWAP | 2017-01-04 |
| A | Volume Profile | 2017-03-20 |
| C | Break & Retest | 2017-01-06 |
| C | EMA Crossover | 2017-02-21 |
| C | Elliott Wave | 2017-01-09 |
| C | Fibonacci | 2017-01-04 |
| C | MA Ribbon | 2017-01-05 |
| C | MACD | 2017-01-27 |
| C | RSI | 2020-02-04 |
| C | RSI Divergence | 2017-01-05 |
| C | Support/Resistance | 2017-01-19 |
| C | VWAP | 2017-01-05 |
| C | Volume Profile | 2017-04-18 |
| B | Break & Retest | 2020-01-02 |
| B | EMA Crossover | 2020-05-05 |
| B | Elliott Wave | 2020-01-02 |
| B | Fibonacci | 2020-01-06 |
| B | MA Ribbon | 2020-01-08 |
| B | MACD | 2020-04-09 |
| B | RSI | 2020-02-03 |
| B | RSI Divergence | 2020-01-07 |
| B | Support/Resistance | 2020-01-02 |
| B | VWAP | 2020-01-06 |
| B | Volume Profile | 2020-01-06 |

## Folds (legs A and C)

| Leg | Test year | Effective fold-train N | Fold-test N |
| --- | --- | --- | --- |
| A | 2021 | 31288 | 11125 |
| A | 2022 | 42275 | 5860 |
| A | 2023 | 48273 | 6816 |
| A | 2024 | 55090 | 10535 |
| A | 2025 | 65619 | 7491 |
| C | 2021 | 2991 | 1115 |
| C | 2022 | 4096 | 484 |
| C | 2023 | 4581 | 681 |
| C | 2024 | 5261 | 1193 |
| C | 2025 | 6455 | 880 |

## WR and ExpR (description only)

| Leg | Population | N | N evaluated | WR (%) | ExpR |
| --- | --- | --- | --- | --- | --- |
| A | fold-train 2017-01-01..2024-12-31 (purged) | 65619 | 52724 | 36.9 | +0.019 |
| A | all trades | 73217 | 58750 | 36.9 | +0.011 |
| C | fold-train 2017-01-01..2024-12-31 (purged) | 6455 | 5210 | 42.8 | +0.207 |
| C | all trades | 7349 | 5950 | 42.4 | +0.222 |
| B | TRAIN 2020-01-01..2023-12-31 | 3645 | 2926 | 41.5 | +0.372 |
| B | all trades | 3645 | 2926 | 41.5 | +0.372 |

### Entry year (all trades)

| Leg | Population | N | N evaluated | WR (%) | ExpR |
| --- | --- | --- | --- | --- | --- |
| A | 2017 | 9242 | 7287 | 44.8 | +0.232 |
| A | 2018 | 7477 | 5996 | 32.4 | -0.057 |
| A | 2019 | 8084 | 6203 | 37.1 | -0.019 |
| A | 2020 | 6587 | 5480 | 37.8 | -0.015 |
| A | 2021 | 11125 | 8861 | 35.2 | -0.102 |
| A | 2022 | 5860 | 4919 | 26.3 | -0.222 |
| A | 2023 | 6816 | 5649 | 35.5 | +0.032 |
| A | 2024 | 10535 | 8393 | 41.5 | +0.203 |
| A | 2025 | 7491 | 5962 | 36.5 | -0.079 |
| C | 2017 | 854 | 666 | 56.6 | +0.582 |
| C | 2018 | 617 | 515 | 44.1 | +0.239 |
| C | 2019 | 826 | 613 | 43.7 | +0.194 |
| C | 2020 | 699 | 558 | 41.0 | +0.028 |
| C | 2021 | 1115 | 887 | 36.0 | -0.047 |
| C | 2022 | 484 | 391 | 34.3 | +0.022 |
| C | 2023 | 681 | 565 | 46.4 | +0.279 |
| C | 2024 | 1193 | 1029 | 41.4 | +0.359 |
| C | 2025 | 880 | 726 | 38.8 | +0.260 |
| B | 2020 | 798 | 639 | 46.2 | +0.420 |
| B | 2021 | 1264 | 993 | 38.0 | +0.282 |
| B | 2022 | 690 | 524 | 35.1 | +0.243 |
| B | 2023 | 893 | 770 | 46.5 | +0.556 |

### Fold test side

| Leg | Population | N | N evaluated | WR (%) | ExpR |
| --- | --- | --- | --- | --- | --- |
| A | 2021 test | 11125 | 8861 | 35.2 | -0.102 |
| A | 2022 test | 5860 | 4919 | 26.3 | -0.222 |
| A | 2023 test | 6816 | 5649 | 35.5 | +0.032 |
| A | 2024 test | 10535 | 8393 | 41.5 | +0.203 |
| A | 2025 test | 7491 | 5962 | 36.5 | -0.079 |
| C | 2021 test | 1115 | 887 | 36.0 | -0.047 |
| C | 2022 test | 484 | 391 | 34.3 | +0.022 |
| C | 2023 test | 681 | 565 | 46.4 | +0.279 |
| C | 2024 test | 1193 | 1029 | 41.4 | +0.359 |
| C | 2025 test | 880 | 726 | 38.8 | +0.260 |

### Top two horizons

| Leg | Population | Horizons | N share | R share |
| --- | --- | --- | --- | --- |
| A | fold-train 2017-01-01..2024-12-31 (purged) | 4w, 3m | 0.310 | +0.402 |
| C | fold-train 2017-01-01..2024-12-31 (purged) | 4w, 3m | 0.317 | +0.361 |
| B | TRAIN 2020-01-01..2023-12-31 | 4w, 2m | 0.317 | +0.305 |

