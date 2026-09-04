# v68 dead-cat-bounce veto — TRAIN grid

Plan v68 Task D8. One replay pass over TRAIN with the veto held off
(`dcb_params=None`), twelve parameter cells scored against that single pass
(`scripts/backtest/measure_dcb_veto.py`). Raw output archived at
`docs/superpowers/results/2026-09-04-measure-dcb-veto-train.log`; the
collected population is `data/v68_train_dcb.json` (gitignored, `data/v3*_*.json`
precedent).

## Setup

- **Window:** TRAIN 2020-01-01..2023-12-31.
- **Tickers:** 25 of 77 watchlist symbols, deterministic alphabetical stride
  (every 3rd, `SAMPLE_EVERY = 3`, same convention as
  `tune_confluence_gates.py`): `AAPL, AMAT, ARM, AVGO, BKNG, CRWD, DDOG, EBAY,
  GD, GM, HD, HPQ, INTC, ISRG, META, MSFT, NBIS, NOW, PANW, PLTR, QCOM, SHOP,
  SNOW, UBER, WDC`.
- **Horizons:** `4w, 2m, 3m, 4m, 6m`.
- **Gates:** `min_reward_pct=3.0, min_stop_distance_pct=2.0,
  max_stop_distance_pct=7.0, cooldown_bars=5, min_confluence=1,
  min_risk_reward=0.0` — the raw confluence-scenario population (loosest
  confluence floor), not a production-tuned gate set; the veto's effect is
  measured as a delta over this same population in every cell, so the
  absolute win rate here is not compared against the engine's live
  acceptance gates.
- **Wall-clock:** ~6 minutes (process-pool replay, one pass).

NBIS produced 0 accepted trades in this sample and ARM produced only 2 —
both are named here, not silently absorbed into the 25-ticker total; every
other ticker contributed. No fetch failures, no crashes (exit code 0).

## Baseline (veto off)

```
BASELINE (veto off): N=1516 WR=35.0% [32.6,37.4] ExpR=-0.002 alerts=2044 excl=21.7%
```

2044 accepted (unvetoed) confluence scenarios; 1516 evaluated (win+loss)
trades after excluding not-triggered/scratch/timeout; 530 wins.

## The pre-registered rule

> select the cell with the greatest pooled ExpR improvement over the
> veto-off baseline, among cells with N>=30 surviving trades AND an
> alert-volume cut <=30%. If no cell satisfies both, no cell is selected and
> VALIDATION is NOT spent.

## The twelve-cell table

| cell | N | WR% | ExpR | dExpR | cut% | excl% | qualifies |
|---|---:|---:|---:|---:|---:|---:|---|
| d15_gN_voff | 1431 | 35.6 | +0.008 | **+0.0104** | 5.3 | 21.7 | PASS |
| d15_gN_v08  | 1498 | 35.4 | +0.007 | +0.0094 | 0.9 | 21.8 | PASS |
| d15_gY_voff | 1464 | 35.0 | -0.006 | -0.0035 | 3.3 | 21.6 | PASS |
| d15_gY_v08  | 1509 | 35.1 | +0.001 | +0.0036 | 0.4 | 21.7 | PASS |
| d20_gN_voff | 1449 | 35.3 | +0.002 | +0.0045 | 4.4 | 21.5 | PASS |
| d20_gN_v08  | 1504 | 35.2 | +0.004 | +0.0062 | 0.6 | 21.7 | PASS |
| d20_gY_voff | 1464 | 35.0 | -0.006 | -0.0035 | 3.3 | 21.6 | PASS |
| d20_gY_v08  | 1509 | 35.1 | +0.001 | +0.0036 | 0.4 | 21.7 | PASS |
| d25_gN_voff | 1465 | 34.9 | -0.007 | -0.0040 | 3.2 | 21.7 | PASS |
| d25_gN_v08  | 1509 | 35.1 | +0.001 | +0.0036 | 0.4 | 21.7 | PASS |
| d25_gY_voff | 1472 | 34.8 | -0.010 | -0.0077 | 2.8 | 21.6 | PASS |
| d25_gY_v08  | 1509 | 35.1 | +0.001 | +0.0036 | 0.4 | 21.7 | PASS |

Every cell cleared N>=30 by a wide margin (smallest surviving N is 1431)
and every cell cleared the <=30% alert-cut budget by a wide margin (largest
cut is 5.3%) — the veto is a low-incidence pattern check, not a broad
filter, at every parameter setting tried.

## Selection

```
Selection: d15_gN_voff (selected)
```

`d15_gN_voff` = `{decline_pct: 15.0, gap_required: False, volume_ratio:
None}` — the loosest cell in the grid (shallowest decline threshold, no gap
requirement, no volume-conviction test) — cleared both budget gates and had
the largest pooled ExpR improvement (+0.0104R) of the twelve.

## Observations

- **The effect is real but small, and it is a "loosest cell wins" result.**
  Every axis in the grid moves toward looser as `dExpR` improves: decline_pct
  15 beats 20 beats 25 within each gap/volume combination; `gap_required=False`
  beats `True` in every matched pair; `volume_ratio=None` (off) beats `0.8`
  in the `gN`/`voff` vs `v08` comparison at `decline_pct=15`. That is not
  what a real "textbook dead-cat-bounce is worse than average" mechanism
  would look like — a genuine pattern-quality signal should reward the
  *stricter* cells (a confirmed gap, confirmed volume divergence) with a
  bigger edge, not a smaller one. The pattern here reads more like "block a
  few more low-quality bullish entries, mostly at random with respect to the
  detector's own selectivity," which is a weaker, noisier claim than the
  spec's textbook-pattern hypothesis.
- **The `gap_required=True` arm is net negative in every decline_pct row**
  (`d15_gY_voff` -0.0035, `d20_gY_voff` -0.0035, `d25_gY_voff` -0.0077) —
  requiring a gap-down during the decline is actively worse than not
  requiring one, at every decline threshold. If a VALIDATION shot were spent
  on a gapped cell it would almost certainly fail; none is selected here.
  `d15_gY_voff` and `d20_gY_voff` are byte-identical in this table
  (1464/35.0/-0.006/-0.0035/3.3%/21.6%) — the same population qualifies at
  both decline thresholds once a gap is required, i.e. the gap requirement
  is the binding constraint in that pair, not decline_pct.
- **`volume_ratio=0.8` collapses four of six decline/gap combinations to the
  identical row** (1509/35.1/+0.001/+0.0036/0.4%/21.7% for `d15_gY_v08`,
  `d20_gY_v08`, `d20_gN_v08` differs slightly at 1504, `d25_gN_v08`,
  `d25_gY_v08`) — the volume-conviction filter is so restrictive relative to
  the decline/gap axes that it dominates which trades survive regardless of
  the other two settings, and the survivors it leaves are a near-null arm
  (+0.0036R delta) rather than a stronger one. A stricter conviction test
  does not buy a bigger edge here either.
- **Exclusion rate (scratch+timeout share) is flat at ~21.6-21.8% across
  every cell**, including the unvetoed baseline — the veto changes which
  bullish trades enter, not how the ones that do enter resolve once
  triggered. Consistent with it being an entry-side filter only.
- **The selected cell's improvement is small in absolute terms**
  (+0.0104R pooled, against a -0.002R unvetoed baseline) and the cell that
  won is also the cell that filtered the fewest trades (a 15% decline
  threshold with no other requirement is the easiest bar to clear, so
  `gN_voff` at `decline_pct=15` fires on the *most* frames of any cell,
  meaning it also blocks the most bullish entries — 5.3% is the largest cut
  in the table, not the smallest). A bigger cut and a bigger (if still
  modest) ExpR gain moving together is at least directionally consistent
  with "blocking more of these entries helps a little," rather than the
  cut and the gain being unrelated by chance.

## Verdict

`d15_gN_voff` clears both TRAIN acceptance clauses (N>=30, alert-cut<=30%)
and has the greatest pooled ExpR improvement among qualifying cells. Per the
pre-registered rule, this earns ONE VALIDATION shot (Task D9) — but the
mechanism read above (looser wins on every axis, gapped arm net-negative,
volume-conviction arm near-null) is weak evidence for the spec's original
"textbook dead-cat-bounce" hypothesis specifically, and should be weighed
against that when interpreting whatever VALIDATION returns.
