# v133 — role coverage vs level-vote count: TRAIN measurement

**Spec:** `docs/superpowers/specs/no-lift/2026-10-06-v133-liquidity-role-coverage-design.md`
**Plan:** `docs/superpowers/plans/no-lift/2026-10-06-v133-liquidity-role-coverage_0-index.md`
**Run:** 2026-10-12, branch `2026-10-06-v133-liquidity-role-coverage` at `157b61bf`, `--workers 4`
**Window:** TRAIN 2020-01-01..2023-12-31, full cached universe (72 tickers), all ten horizons, 12207 closed trades
**Raw output:** `2026-10-06-v133-role-coverage.txt`, `2026-10-06-v133-role-coverage.json`

## Verdict

```
== VERDICT (confluence-sourced, pre-registered in the v133 spec) ==
bullish  spread_roles -0.0597  spread_votes +0.0659  clause1=False clause2=False clause3=True thin=False
bearish  spread_roles +0.4913  spread_votes +0.3207  clause1=False clause2=True clause3=True thin=False
clause4 (bearish agrees in sign, or is thin) = False
VERDICT: not more informative
```

| | spread_roles | spread_votes | clause 1 | clause 2 | clause 3 | thin |
|---|---|---|---|---|---|---|
| bullish | -0.0597 | +0.0659 | False | False | True | False |
| bearish | +0.4913 | +0.3207 | False | True | True | False |

Clause 4 (bearish agrees in sign, or is thin): False

The verdict decides only whether a follow-on expectancy spec is written. It picks none of that spec's thresholds.

## Tables 1 and 2 (the two that enter the verdict)

```
== 1. role_coverage ==
confluence bearish  0-1      N= 2051  WR  31.94%  ExpR -0.0305
confluence bearish  2        N= 1608  WR  34.88%  ExpR -0.0627
confluence bearish  3-4      N=  184  WR  44.85%  ExpR +0.4608
confluence bearish  None     N=    5  thin
confluence bullish  0-1      N= 2229  WR  38.72%  ExpR +0.1955
confluence bullish  2        N= 1652  WR  35.35%  ExpR +0.0785
confluence bullish  3-4      N=  233  WR  32.55%  ExpR +0.1358
confluence bullish  None     N=    5  thin
strategy   bearish  0-1      N=  185  WR  24.68%  ExpR -0.0515
strategy   bearish  2        N=  318  WR  38.40%  ExpR +0.1331
strategy   bearish  3-4      N=  142  WR  39.86%  ExpR +1.1422
strategy   bullish  0-1      N= 1362  WR  45.28%  ExpR +0.4075
strategy   bullish  2        N= 1372  WR  41.44%  ExpR +0.3662
strategy   bullish  3-4      N=  861  WR  35.49%  ExpR +0.1651

== 2. control: target confluence count (confluence-sourced only) ==
confluence bearish  2        N=  523  WR  24.58%  ExpR -0.2897
confluence bearish  3        N=  631  WR  32.86%  ExpR -0.0201
confluence bearish  4+       N= 2694  WR  36.01%  ExpR +0.0310
confluence bullish  2        N=  561  WR  31.56%  ExpR +0.0861
confluence bullish  3        N=  669  WR  37.67%  ExpR +0.1615
confluence bullish  4+       N= 2889  WR  37.93%  ExpR +0.1521
```

## Tables 3 to 6 (descriptive, no verdict)

```
== 3. role_trigger ==
confluence bearish  False    N= 3748  WR  34.04%  ExpR -0.0192
confluence bearish  None     N=    5  thin
confluence bearish  True     N=   95  WR  25.93%  ExpR -0.0699
confluence bullish  False    N= 4029  WR  37.43%  ExpR +0.1536
confluence bullish  None     N=    5  thin
confluence bullish  True     N=   85  WR  18.29%  ExpR -0.2557
strategy   bearish  False    N=  556  WR  33.70%  ExpR +0.0591
strategy   bearish  True     N=   89  WR  40.91%  ExpR +1.8219
strategy   bullish  False    N= 2977  WR  42.42%  ExpR +0.3526
strategy   bullish  True     N=  618  WR  36.94%  ExpR +0.2426

== 4. liq_stop_side_atr  TRAIN quintile edges=[3.04744, 5.043724, 7.699573, 11.444441] ==
confluence bearish  None     N= 1517  WR  33.93%  ExpR -0.0244
confluence bearish  Q1       N=  401  WR  31.70%  ExpR -0.0218
confluence bearish  Q2       N=  458  WR  36.27%  ExpR +0.0287
confluence bearish  Q3       N=  433  WR  36.13%  ExpR -0.0029
confluence bearish  Q4       N=  394  WR  29.92%  ExpR -0.1104
confluence bearish  Q5       N=  645  WR  34.16%  ExpR -0.0050
confluence bullish  None     N=  993  WR  31.68%  ExpR +0.0101
confluence bullish  Q1       N=  756  WR  35.43%  ExpR +0.1141
confluence bullish  Q2       N=  743  WR  34.55%  ExpR +0.0792
confluence bullish  Q3       N=  676  WR  38.26%  ExpR +0.1624
confluence bullish  Q4       N=  594  WR  48.57%  ExpR +0.4826
confluence bullish  Q5       N=  357  WR  40.38%  ExpR +0.1233
strategy   bearish  None     N=   89  WR  31.34%  ExpR -0.1193
strategy   bearish  Q1       N=   74  WR  60.00%  ExpR +0.9549
strategy   bearish  Q2       N=   66  WR  44.26%  ExpR +0.9005
strategy   bearish  Q3       N=   91  WR  22.73%  ExpR +0.8456
strategy   bearish  Q4       N=  133  WR  39.17%  ExpR +0.1866
strategy   bearish  Q5       N=  192  WR  26.03%  ExpR -0.1368
strategy   bullish  None     N=  373  WR  49.65%  ExpR +0.5366
strategy   bullish  Q1       N=  616  WR  51.19%  ExpR +0.6728
strategy   bullish  Q2       N=  579  WR  45.68%  ExpR +0.5436
strategy   bullish  Q3       N=  648  WR  35.83%  ExpR +0.1583
strategy   bullish  Q4       N=  723  WR  36.66%  ExpR +0.1678
strategy   bullish  Q5       N=  656  WR  34.80%  ExpR +0.0705

== 5. sweep stop-outs: losing trades whose stop bar or the next 3 bars closed back beyond the stop ==
confluence bearish  losses= 2197  swept  72.83%
confluence bullish  losses= 2318  swept  67.26%
strategy   bearish  losses=  353  swept  79.60%
strategy   bullish  losses= 1650  swept  74.79%

== 6. census per horizon: share of entry bars (percent) ==
2m       N= 1316  live stop-side pool  77.9  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
2w       N=  920  live stop-side pool  76.7  role_context=None   0.9  role_location=None   0.9  role_path=None   0.9  role_trigger=None   0.9
3m       N= 1380  live stop-side pool  78.1  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
4m       N= 1250  live stop-side pool  75.4  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
4w       N= 1411  live stop-side pool  79.3  role_context=None   0.1  role_location=None   0.1  role_path=None   0.1  role_trigger=None   0.1
5m       N= 1158  live stop-side pool  72.8  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
6m       N= 1155  live stop-side pool  72.0  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
7m       N= 1307  live stop-side pool  74.3  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
8m       N= 1166  live stop-side pool  73.6  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
9m       N= 1144  live stop-side pool  75.2  role_context=None   0.0  role_location=None   0.0  role_path=None   0.0  role_trigger=None   0.0
```

## What this does and does not show

Bullish confluence trades did not separate better by role coverage than by target vote count: the role spread is -0.0597R against +0.0659R for votes, so clauses 1 and 2 fail. Bearish confluence shows a role spread (+0.4913R) larger than the vote spread (+0.3207R), but its 3-4 role bucket has N=184 against N=2,051 in the 0-1 bucket, and clause 4 requires the two sides to agree in sign. The bullish 3-4 bucket (N=233, ExpR +0.1358) sits below the 0-1 bucket (N=2,229, ExpR +0.1955), the opposite direction to bearish. The `None` buckets (N=5 per side) and the strategy-sourced rows do not enter the verdict. Table 6 shows a live stop-side pool on 72.0 to 79.3 percent of entry bars across horizons, and Table 5 shows 67.26 to 79.60 percent of losing trades closing back beyond the stop within three bars; both are descriptive only.
