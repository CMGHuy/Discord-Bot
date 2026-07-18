# Pooled out-of-sample win rate across validated sources (Task 93)

All numbers are from single pre-registered VALIDATION runs on
2024-01-01..2025-12-31 (v2 exits + scale-out), pooled from the committed
JSONs — no window re-exposure:

- `exit_v2_validation.json` (Task 32 — all 11 strategies)
- `docs/superpowers/results/rescue_elliott_validation.json` (Task 106 —
  Elliott under its adopted gate; supersedes Task 32's ungated Elliott row)
- `docs/superpowers/results/confluence_validation.json` (Task 41)

Pooling math: wins and evaluated trades summed per group
(`WR = Σwins/Σn_eval`); expectancy weighted by closed trades
(`ExpR = Σ(ExpR_i × closed_i)/Σclosed_i`) — identical definitions to the
harness's own `pool()`.

## The headline number (spec success criterion 2)

| Pool | Sources | N (win+loss) | Win rate | ExpR | Criterion |
|---|---|---|---|---|---|
| **VALIDATED** | VWAP, Fibonacci, Support/Resistance, RSI, MACD, Break & Retest, Volume Profile | **814** | **84.2%** | **+0.259** | **≥80% — MET** |

Every plan stamped ✅ VALIDATED comes from this pool: pooled out-of-sample
win rate **84.2%** over 814 evaluated trades, expectancy **+0.259R** per
closed trade. The spec's "pooled WR ≥ 80" success criterion is met.

Per-source rows (all PASS individually):

| Source | N | WR% | ExpR |
|---|---|---|---|
| Support/Resistance | 186 | 87.1 | +0.326 |
| Break & Retest | 148 | 84.5 | +0.210 |
| Volume Profile | 47 | 83.0 | +0.479 |
| Fibonacci | 203 | 82.3 | +0.268 |
| MACD | 123 | 81.3 | +0.120 |
| VWAP | 77 | 80.5 | +0.250 |
| RSI (rescued, Tasks 95–97) | 30 | 100.0 | +0.304 |

(RSI's N=30 is 3 unique setups replicated across 10 horizons — the
harness's standard pooling; recorded honestly in
`2026-07-rescue-rsi-train.md`.)

## The WEAK pool, honestly

| Pool | Sources | N | Win rate | ExpR |
|---|---|---|---|---|
| WEAK (strategy) | EMA Crossover, Elliott Wave (gated, Task 106), MA Ribbon, RSI Divergence | 1389 | 76.2% | +0.191 |
| WEAK (confluence scan) | confluence/ALL, pooled over 10 horizons | 4641 | 53.5% | -0.171 |

- The four WEAK strategies are not losers — pooled expectancy is positive
  (+0.191R) — they are simply under the 80% WR bar their badge claims
  require. They keep emitting plans with the ⚠️ caution block quoting these
  real numbers.
- The confluence-scan source is materially worse than the strategy sources
  (53.5% WR, negative expectancy) and is WEAK at every horizon; its plans
  always carry the caution block.

## Caveats

- The validation window (2024–2025) has now been read once per component
  as budgeted, plus the spec §13 reuse notes; treat any future look at
  this window as tainted for selection purposes.
- Pooled WR weights each evaluated trade equally, so high-N sources
  dominate; the per-source table above is the honest per-edge view.
