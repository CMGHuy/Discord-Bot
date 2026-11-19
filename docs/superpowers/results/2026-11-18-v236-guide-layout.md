# v236 guide layout check -- 2026-11-19

Base `http://localhost:1234`; widths 390, 820, 1440; pages `/insights/guide/`, `/insights/guide/what-it-is`, `/insights/guide/glossary`, `/insights/guide/pipeline`; deep links `what-it-is#the-notice`, `glossary#r-multiple`. Script: `scripts/dev/guide_layout_check.py`.

| Width | Contents | Problems |
|---|---|---|
| 390 | picker | 0 |
| 820 | drawer | 0 |
| 1440 | rail | 0 |

## Verdict

PASS: no problems.

## Layout audit (`node frontend/scripts/layout-audit.mjs --widths 390,768,1440`)

Guide routes after the fixes below: `/insights/guide` and `/insights/guide/pipeline` are clean at 390 and 1440 and at 768 except one finding.

Fixed in this task: links inside a chapter's prose were 53x15px tap targets at 390 and 768 (they now carry the shared 44px `--hit-min` box through `.md a::after`); a cold load of `/insights/guide/<slug>#<anchor>` lost its `#anchor` at sign-in (`SessionStore.boot` kept only path and query), so deep links landed at the top of the chapter (now kept whole via `arrivalUrl()`).

Open on the guide: `/insights/guide/pipeline @768 clipped sb-breadcrumb > span.crumb "The scan pipeline, end to end"` (needs 166px, has 97px). This is the shell breadcrumb's detail crumb at tablet width, the same finding the main app already shows for `/trades/calendar/:date @768` ("Thursday, November 19, 2026", needs 170px, has 97px); it is not a guide-page defect and is left to the shell.

## Other pages

Present on the same run and unrelated to the guide: `/trades/calendar/:date @390,768` leg-name tap (58x17 and 86x17px), `/insights/analytics @390` document overflow by 123px, `/system?tab=logs @768` toolbar buttons clipped, `/trades @1440` data-table vcenter.
