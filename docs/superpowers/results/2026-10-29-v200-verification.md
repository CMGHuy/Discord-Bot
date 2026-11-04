# v200 verification

Spec: [Scout tooling integrity](../specs/2026-10-29-v200-scout-tooling-integrity.md) · Plan: [index](../plans/2026-10-29-v200-scout-tooling-integrity_0-index.md).
Counts only. No pooled ExpR or win rate is quoted here (`pooled-numbers`), and no v200 q or Δ is set beside a 10-29 one.

## Item 1 — fresh autopsy

Read-only export from production at 2026-11-04T10:53Z (`export_book_rows.sh` rows and rejections), autopsy run into the scratchpad.

- CSV: 1031 data rows; the header ends `plan_issued_at,plan_issued_at_source`.
- Alert-hour coverage, by source:
  - trades: live 289, discord 0, unknown 560
  - plans: live 361, discord 0, unknown 398
- Hours read from `plan_issued_at`: 361 rows. 434 rows carry a first-status stamp but no issue time, and their hour stays unknown. No hour came from a date-only or fill stamp, checked row by row against `plan_issued_at`.
- Stall line, verbatim: `- stall exclusion stall_2026_08: N 37, gross ExpR -0.645, worst R -6.033`
- N after the stall exclusion: 849. `autopsy_schema` 2. 357 cells, every one tagged `defined_at` and carrying eras.
- Era boundary: 2026-09-15T08:54:50Z (VM git reflog, `8c0aeec965ff` reset).
- `discord` stays 0 until `v200_001` ships through the partner's deploy.

## Item 2 — 10-29 rows re-merged

The 8 raw 10-29 rows, each given a `direction`. Rule: a row citing a cell whose Δ interval is negative is `avoid`; a positive interval or a playbook row is `exploit`.

| Idea | direction |
|---|---|
| pre-close-exit-on-gap-risk | avoid |
| stop-fill-overshoot-audit | avoid |
| bank-partial-on-favourable-open-gap | avoid |
| no-chase-favourable-gap-limit | avoid |
| atr-reentry-after-stop | exploit |
| tight-base-breakout | exploit |
| after-close-alerts-resting-order-only | exploit |
| weekend-hold-survivor-screen | exploit |

- **Legacy run** (the committed 10-29 autopsy, schema 1): the legacy banner is present, the four 10-29 drop reasons reproduce exactly, 4 ranked and 4 dropped.
- **Schema-2 view** (same figures, `defined_at` from the v200 cut tags): 3 ranked, 5 dropped.
  - Ranked: after-close-alerts-resting-order-only, atr-reentry-after-stop, tight-base-breakout.
  - Dropped as not known at entry:
    - bank-partial-on-favourable-open-gap: `cell open_gap_bucket=favourable is fill-defined (not known at entry)`
    - no-chase-favourable-gap-limit: `cell open_gap_bucket=favourable is fill-defined (not known at entry)`
    - pre-close-exit-on-gap-risk: `cell gap_through_stop=through_stop is outcome-defined (not known at entry)`
    - stop-fill-overshoot-audit: `cell exit_reason=stop is outcome-defined (not known at entry)`
    - weekend-hold-survivor-screen: `cell weekend_hold=yes is outcome-defined (not known at entry)`
- The fifth drop, `weekend-hold-survivor-screen`, follows from spec Part 5.2, which tags `weekend_hold` as `outcome` (it reads `exit_date`), although the spec's Verification list names only four rows.
- The 10-29 figures are the pre-v200 artefact figures, so this re-merge tests the rule, not the book. No v200 q or Δ is compared with them.

## Item 3 — backfill match rate

See [the dry-run record](2026-10-29-v200-backfill-dry-run.md) (V200-6): the partner saw the match rate on 2026-11-04 and approved pinning it in `v200_001`.

## Item 4 — full suite

pending V200-18
