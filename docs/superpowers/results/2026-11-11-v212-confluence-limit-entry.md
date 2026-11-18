# v212 — Confluence limit entry partway to the support: results

**Spec (the pre-registration):** `docs/superpowers/specs/2026-11-06-v212-confluence-limit-entry.md`.
**Pre-registration record:** `docs/superpowers/results/2026-11-11-v212-preregistration.md` (committed `3aedb886`; `observed_n` appended in `0b0915e2`, before Stage 0).
**Plan:** `docs/superpowers/plans/2026-11-06-v212-confluence-limit-entry_0-index.md`.
**Driver:** `scripts/backtest/measure_confluence_limit.py` at `main` `4497ddd8`; stage files under `docs/superpowers/results/v212/`.
**Verdict:** NO-LIFT (UNDERPOWERED at Stage 0); selected cell `none`. `CONFLUENCE_LIMIT_ENTRY_F` stays `0`.

## Frozen before any run

Everything frozen is in the pre-registration record above: the rule, the grid `f ∈ {⅓, ½, ⅔}` (3 looks, pooled directions), the three clauses, the harvest gate family, the plateau and thin rules, TRAIN 2020-01-01..2023-12-31, folds 2021 / 2022 / 2023, VALIDATION 2024-01-01..2025-12-31, the universe and the data source.

## Stage −1 (census, no outcome read)

**Stage -1: REACHABLE**

| key | value |
|---|---|
| stage | -1 |
| verdict | REACHABLE |
| alerts | 38630 |

**cells**

| cell | in_scope | kept | observed_n |
|---|---|---|---|
| f0.333 | 38630 | 22519 | 15180 |
| f0.5 | 38630 | 32447 | 20162 |
| f0.667 | 38630 | 36957 | 20939 |


## Stage 0 (paired MDE)

**Stage 0: UNDERPOWERED**

| key | value |
|---|---|
| stage | 0 |
| verdict | UNDERPOWERED |
| mde_ceiling_r | 0.1000 |
| power | 0.8000 |

**cells**

| cell | mde_r | observed_n | powered | target_n |
|---|---|---|---|---|
| f0.333 | 0.0778 | 12101 | True | 6050 |
| f0.5 | 0.0979 | 15356 | True | 7678 |
| f0.667 | 0.1391 | 15276 | False | 7638 |


**Paired N versus registered `observed_n` (disclosure).** Stage 0's paired N is lower than the `observed_n` registered in the pre-registration in every cell. The registered figure counts keys where the arm's limit filled. Stage 0 counts only keys that also have a closed reference (market-entry) trade, and on some keys the reference was `not_triggered` while the deeper limit filled. Removing those keys reproduces Stage 0 exactly:

| cell | registered observed_n | reference `not_triggered` | Stage 0 paired N |
|---|---|---|---|
| f0.333 | 15180 | 3079 | 12101 |
| f0.5 | 20162 | 4806 | 15356 |
| f0.667 | 20939 | 5663 | 15276 |

This is a wording looseness in the registration ("filled keys" versus the paired definition the driver uses), not a wiring fault. The pre-registration is left unedited and the verdict follows the driver's frozen mechanics: one underpowered cell (f0.667, MDE 0.1391R against the 0.10R ceiling) ends the chain.

## Stage 1 (clauses and plateau, TRAIN)

Did not run: the chain ended at Stage 0 (UNDERPOWERED).

## Stage 2 (folds)

Did not run: the chain ended at Stage 0 (UNDERPOWERED).

## Stage 3 (VALIDATION, one shot)

Did not run: the chain ended at Stage 0 (UNDERPOWERED). The VALIDATION budget is intact.

## Disclosures (printed, never gating)

Not computed: the chain ended at Stage 0.

## Prediction

The `Edge:` line predicted ExpR up, fewer trades and fewer noise stop-outs on filled trades. Not measured: no stage that scores ExpR ran, so the prediction is neither hit nor missed.

## Multiple testing (reported, never gating)

All three looks are `NO-LIFT` with no p-value (the chain ended before any ExpR was scored): BH q = n/a for `v212-f0.333`, `v212-f0.5` and `v212-f0.667`, across 16 ledger p-values.

The ledger rows carry instrument `v2`, the driver's stamp; the plan's scratch check expected `v1`. The pre-registration does not name an instrument.

## Evidence files

- `v212-census-train-rows.json` (15073278 bytes)
- `v212-rows-train-rows.json` (109181841 bytes)
- `v212-rows-train-touch-rows.json` (107950704 bytes)
- `v212-stage0.json` (504 bytes)
- `v212-stageM1.json` (1440 bytes)

The two TRAIN row dumps are 109 MB and 108 MB, over GitHub's push limit, so they are git-ignored and stay local. SHA-256: `v212-rows-train-rows.json` `fbbbec0fef504c27976a849062136bfbf8340fc2dfdab2c11a9e7056305c14bb`; `v212-rows-train-touch-rows.json` `1a229b127c7f8abcfb605c0fe34529f5872f2e88c3a5c6676e29e7ff8ef7d0c4`.

## What follows

Closed: a row in `backtest-methodology.md` § Closed pre-registrations (V212-17). Another f, buffer, expiry or a limit at the support is not a new mechanism.
