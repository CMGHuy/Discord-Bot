# v203 UI shell cockpit — results: layout audit

**Spec:** [2026-10-29-v202-ui-shell-cockpit-design.md](../specs/2026-10-29-v202-ui-shell-cockpit-design.md) §8 "Layout"
**Plan:** [2026-10-29-v203-ui-shell-cockpit-dock_0-index.md](../plans/2026-10-29-v203-ui-shell-cockpit-dock_0-index.md) — V203-10, V203-10b

**Verdict: NOT exit 0.** 135 unallowed findings, none of them in a v203-owned element once the blank-page flakes are set aside. The plan's "exit 0, every count 0" gate is not met; the partner decides how to close it (see Notes).

## Run

- Branch and commit: `2026-10-29-v203-ui-shell-cockpit-dock` @ `b5bd4f15`; base `http://localhost:1234` on the replica synced 2026-11-05 (`swingbot_prod_replica`, alembic `v200_001`, MATCH, 37 tables).
- Command: `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`; 135 unallowed, 0 allowed.
- Routes: 29 (the v202 paths), at 390, 768 and 1440.
- The local bot was not running, so the alarm chip showed "Bot down" on every page (a useful check: the alarm, killswitch chip, search icon and avatar fit the bar at 768).

## Findings per check

| Check | 390 | 768 | 1440 |
|---|---|---|---|
| overflow | 0 | 0 | 0 |
| offscreen | 0 | 0 | 0 |
| clipped | 0 | 35 | 60 |
| tap | 0 | 5 | 0 |
| text | 0 | 0 | 0 |
| baseline | 3 | 15 | 6 |
| vcenter | 0 | 3 | 1 |
| hint | 2 | 0 | 0 |
| rail-label | 0 | 1 | 0 |
| dock | 3 | 1 | 0 |

Allowed: none. Stale allow-list entries: none.

## Where the findings are

**Not v203's elements (components v203 does not touch; untested against a pre-v203 baseline, which was not run):**

- `sb-tape` (`clipped` 95 across the tiles, `tap` 5 at 768: tiles are 19 px tall). The tape is a scrolling lane clipped by its viewport by design.
- `sb-page > header.bar` baseline (17: the 20 px title against the 12–14 px actions beside it), `sb-stat-strip` and `sb-market-value` baseline (7), two `vcenter` groups (`sb-panel` table on trade detail, `sb-data-table` date column on the watchlist), and two `sb-hint` popovers that open zero-size (`About R`, `About Win rate`).

**Flakes of the local server, not defects:** the dock (4) and rail-label (1) findings are all on `/insights/analytics?tab=edge|pipeline|tuning`, where the screenshot is a blank page (the SPA had not rendered; the local admin was busy with yfinance downloads). Re-shot with `--settle 4000`, `/insights/analytics?tab=edge` at 768 renders the full shell: labelled rail, wordmark · breadcrumb · alarm · killswitch · search · avatar, live strip. The set of failing routes changed between runs (tuning@390, pipeline@768, then edge/pipeline/tuning), which a real defect would not do.

## Fixed during the run (commit `bd9550aa`)

- At 768 the wordmark squeezed the breadcrumb and the search trigger into ellipses (23 `clipped` findings). Below 1024 px the trigger is now its magnifier (words stay in the accessible name) and the breadcrumb shows only the current crumb.
- The `baseline` check read the docked column's "Live" heading against the page title as one text line (3 findings). It now skips landmark columns (`main`, `aside`, `nav`).
- The dock probe waited a fixed 400 ms; it now waits for the strip and the sheet.

## Read off the screenshots

- 768 (`/insights/analytics?tab=edge`): the 80 px rail with labelled entries and System at the foot; the bar reads wordmark · breadcrumb · "Bot down" alarm · Armed · search icon · avatar; the live strip sits under the tape.
- 1440 and 390 were checked through the audit's own measurements (no overflow, no off-screen element at either width, rail-label 0, dock 0 at 1440); screenshots were not individually read.

## Notes

- Closing this at exit 0 needs the tape, page-header, stat-strip, vcenter and hint findings fixed in their own components (outside the v203 ledger), or allow-listed against the plan's rule that nothing is. The partner's call.
- A re-run with the local bot started and the admin given time to warm would remove the blank-page flakes.
