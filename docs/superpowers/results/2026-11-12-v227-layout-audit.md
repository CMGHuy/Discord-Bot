# v227 layout audit — voice chip and Settings → Voice notifications

**Plan:** [v227 part 3](../plans/2026-11-12-v227-voice-notifications_3-settings-release.md) (V227-14)
**Date:** 2026-11-13 · **Branch head:** 57414cda (audit ran against the working tree on top of it)
**Command:** `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,768,1440`

| Width | First run exit | Findings on this page | Final run exit |
|---|---|---|---|
| 390 | 1 | 0 | 1 (only off-page findings, below) |
| 768 | 1 | 0 | 1 (only off-page findings, below) |
| 1440 | 1 | 2 baseline (`li.kind` x25, `div.voice-controls`) | 1 (only off-page findings, below) |

Final run: no finding names `sb-voice-chip`, `.status-cluster`, `sb-voice-settings`, `sb-switch`, `.preview`, `.rate` or `summary`. Exit stays 1 because of the off-page findings listed below, which this task leaves alone.

## Fixes
- `voice-settings.ts`: `.voice-controls` Voice vs Rate label baselines 4px apart (1440) -> `align-items: flex-start`, `.voice-controls > button { align-self: flex-end; }` (pinned by "aligns the kind rows and the voice controls on one baseline (v227 audit)")
- `voice-settings.ts`: `li.kind` label vs ▶ preview baseline 3.5px apart -> `.kind { align-items: center; }` (same spec test). `align-items: baseline` was tried first and made it worse (4.5px).

## Chip labels (clipped shots)
- 390: the audit's full-page shot shows "Enable voice" fitting beside the killswitch chip in the top bar, nothing clipped. The clicked state ("Voice on" / "Voice blocked") was NOT checked: `browse.mjs shots` never rendered the chip in its session (`--click`/`--clip` on `sb-voice-chip` matched nothing), so Step 5's clipped shots could not be taken. Needs a manual look at the longest label before release.
- 768: not checked, same reason.

## Findings left alone
- /trades @390 overflow document, 1px wider than the viewport — not this page
- /trades @768 tap `sb-leg-name > span.name` 86x17px (x28) — not this page
- /ui @768 and @1440 baseline `sb-control-row > div.row` 3.0px (x6) — not this page
- Not compared against `main`; assumed pre-existing since none touch v227 components.
- Replica: incremental top-up reported MISMATCH (`alert_posts`, `market_fetch_counts`, `market_refresh_queue` hold extra stale rows); `--full` was blocked by 15 other sessions on the replica. Irrelevant to layout.
- Build warning: `shell.css` exceeds its 5.00 kB budget by 515 bytes (warning only).
