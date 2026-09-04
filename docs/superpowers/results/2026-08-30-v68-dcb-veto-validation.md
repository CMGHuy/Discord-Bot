# v68 dead-cat-bounce veto — VALIDATION

Plan v68 Task D9. ONE pre-registered shot, spent once, result recorded as-is.
Raw output archived at
`docs/superpowers/results/2026-09-04-v68-d9-dcb-veto-validation.log`; the
collected population is `data/v68_validation_dcb.json` (gitignored,
`data/v68_*.json`).

## Setup

- **Window:** VALIDATION 2024-01-01..2025-12-31.
- **Cell:** `d15_gN_voff` = `{decline_pct: 15.0, gap_required: False,
  volume_ratio: None}` — the single cell TRAIN (Task D8,
  `2026-08-30-v68-dcb-veto-train.md`) selected as the greatest pooled ExpR
  improvement among qualifying cells (+0.0104R on TRAIN).
- **Tickers/horizons/gates:** identical to D8's TRAIN run — same 25-ticker
  alphabetical sample, same 5 horizons, same base confluence gates.
- **Wall-clock:** ~5.4 minutes.

## Result

```
Total VALIDATION accepted (unvetoed) trades: 1159

VALIDATION cell d15_gN_voff {'decline_pct': 15.0, 'gap_required': False, 'volume_ratio': None}: N=844 WR=34.5% [31.3,37.7] ExpR=-0.004 excl=21.4%
  FAIL: expectancy_r > 0
  FAIL: win_rate >= 50
  PASS: N >= 15
  PASS: scratches+timeouts <= 50% of closed
  -> AT LEAST ONE GATE FAILED
```

Baseline (veto off, VALIDATION window): N=859, WR=34.9%, ExpR=+0.0058. With
the veto on: N=844 (a 1.7% alert cut — far smaller than TRAIN's 5.3%), WR=34.5%
(-0.45pp), ExpR=-0.0039 (a **-0.0097R delta from baseline** — the opposite
sign from TRAIN's +0.0104R).

## Gates applied

Per `docs/claude/backtest-methodology.md`: `expectancy_r > 0`, `win_rate >=
50`, `N >= 15`, scratches+timeouts <= 50% of closed. **2 of 4 fail**
(`expectancy_r`, `win_rate`); `N` and the exclusion-rate gate pass.

## Decision

**FAIL — the default stays `false`.** `DEAD_CAT_BOUNCE_VETO`'s default is
NOT flipped; `swingbot/config.py` is unchanged; the code ships merged and
inert, matching the `--gap_required` arm's own TRAIN-row warning and D8's
observation that the selected cell's mechanism read as weak evidence for the
spec's textbook-pattern hypothesis. Both outcomes were legitimate going in
(`document-conventions.md`'s "both outcomes are legitimate" convention); this
one is a fail, and it is recorded as one.

## Observations

- **The sign flip is the headline finding, not the magnitude.** TRAIN showed
  a small positive delta (+0.0104R) built almost entirely on the "loosest
  cell wins" pattern flagged in the TRAIN doc — every axis improving toward
  *looser*, the gap-required arm net-negative at every decline threshold.
  VALIDATION shows a larger NEGATIVE delta (-0.0097R) on the identical cell.
  That is exactly the shape a TRAIN-only artifact produces: an effect that
  looked real on the tuning window evaporates (and here, reverses) on
  unseen data.
- **The alert cut is far smaller on VALIDATION** (1.7% vs TRAIN's 5.3%) even
  though the population sizes are comparable in proportion (1159 vs 2044
  baseline alerts, roughly half — expected for a 2-year window vs TRAIN's
  4-year window). Fewer dead-cat-bounce patterns fired on the newer data at
  the same threshold, which is at least consistent with the pattern being a
  low-incidence, noisy signal rather than a stable structural regularity —
  the TRAIN doc's suspicion, now with a second data point pointing the same
  way.
- **This closes the component as specified.** Re-running with a looser rule,
  a different cell, or an adjusted grid is a NEW pre-registration, not a
  re-read of this one — the one-shot VALIDATION budget for this exact
  hypothesis (decline_pct/gap_required/volume_ratio grid, this selection
  rule) is spent.
