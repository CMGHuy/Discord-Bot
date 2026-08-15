# Control alignment and settings grouping — Design (v22)

**Version:** ui 1.2.3 · bot 1.1.2
**Bump:** ui patch — every change here is visible, none of it makes the admin a
different product. A reader who used the Settings page yesterday finds the same
page, correctly aligned. (See `docs/claude/document-conventions.md`,
"The header block".)
**Date:** 2026-08-14
**Status:** implemented and merged 2026-08-15 as ui 1.2.4, via plan
`docs/superpowers/plans/implemented/2026-08-14-v24-control-alignment.md`. Its
Tasks 1–13 shipped; Task 14's manual responsive pass was never run, so nothing
in this design has been verified at a real viewport. Read that plan's Status
block before trusting any layout claim here.

---

## Why this exists

The complaint was concrete: *"Some buttons are not aligned with its components.
Some fields are in random position. Each settings page section should group
checkboxes to a group, input field to another one."*

Reading the code found three mechanical causes, none of them a styling
oversight:

1. **The three form controls disagree about where the label goes.** `sb-select`
   and `sb-text-input` stack the label above the control (`.field { flex-direction:
   column }`, `form-controls.ts:46,100`); `sb-checkbox` puts it beside the box
   with no top label at all (`form-controls.ts:165`). Put them in one row and
   they cannot align — there is no shared reference edge.

2. **No shared control height.** `button[sb-button]` is `padding: 6px 14px`
   (`button.ts:34`), inputs are `4px 8px` (`form-controls.ts:54,108`). With
   borders that is 29px against 25px: a button beside a field is 4px taller
   before labels enter into it.

3. **The settings form is one undifferentiated grid.** `.fields` flows every
   field of a section — checkbox, select, number, text — into
   `repeat(auto-fill, minmax(260px, 1fr))` in raw `config.py` declaration order.
   A one-line checkbox lands in a cell sized for a labelled text input, so rows
   go ragged. That is the "random position".

Across the six workspaces the same absence shows up as 47 hand-rolled flex rows
using `center`, `baseline`, `flex-start` and `stretch` more or less at random.
`sb-filter-bar` already gets it right (`align-items: flex-end`,
`filter-bar.ts:43`) — it is the only row in the app that reasoned about it.

**The problem is not the design system; it is the absence of a rule about what a
control row is.** `tokens.css` is coherent and every token carries its
rationale. This spec adds the missing contract and applies it.

---

## Decisions

### Decision 1 — one control height, `--control-h: 28px`

A new token in `tokens.css`. Every interactive control's box resolves to exactly
that height:

| Control | Now | After |
|---|---|---|
| `sb-text-input`, `sb-select` | `padding: 4px 8px` → 25px | `padding: 6px 8px` → 28px |
| `button[sb-button]` | `padding: 6px 14px` → 29px | unchanged padding, 28px enforced |

Inputs gain 3px, buttons lose 1px. Nothing in the app visibly moves, and a
button beside a field is flush.

**28, not 26 or 30.** 26 is the input's current height and is below a
comfortable click target; 30 is the button's and costs a row of visible data in
every table toolbar on a dashboard built for density (11px table type). 28 sits
on the 4px grid the spacing scale already implies and moves both sides by less
than the eye resolves.

`.icon` buttons keep `padding: var(--space-4)` and are exempt: they are square
by construction and sized by their glyph.

### Decision 2 — `sb-checkbox` gains an optional top label

A new `topLabel` input rendering the same `.label` span the other two controls
use. When set, the checkbox's control box starts at the same y-offset as a
labelled input beside it.

The inline caption stays and remains required — it is the checkbox's own
accessible name, and the `<label>` wrapping the input is what makes clicking the
text toggle it. The top label is **additive**, for the one case where a checkbox
shares a row with labelled controls. The Settings `.find` row is the live
example.

### Decision 3 — `sb-control-row` is the only sanctioned control row

One layout primitive in `ui/layout.ts`, owning the rule:

```css
.row {
  display: flex;
  align-items: flex-end;
  align-content: flex-start;
  flex-wrap: wrap;
  gap: var(--space-10);
}
```

**Be precise about what this fixes**, because it changes how much work Phase 3
is: flexbox already aligns items per-line when wrapping — `align-items` applies
within each flex line, not across the container. So the orphaned-button look is
not a wrapping bug; it is items of mismatched height inside a line, and
Decisions 1 and 2 are what fix it. The primitive's real jobs are to stop the next
component picking `center` at random, and to give the guard test (Decision 9)
something to assert against.

`sb-filter-bar` becomes a consumer rather than a second implementation of the
same rule.

**A `stacked` input** collapses the row to a full-width vertical stack below a
breakpoint. `scan-tab`'s `.kill` row already hand-rolls exactly this
(`flex-direction: column; align-items: stretch`); that behaviour moves into the
primitive instead of remaining a local exception.

### Decision 4 — settings fields group by control type, derived in the frontend

`settings-tab` partitions each section's fields using the control type it already
derives in `controlOf(field)`, into three blocks in this order:

1. checkboxes
2. selects
3. text and number inputs

**The partition is stable**, so `config.py`'s declaration order survives inside
each group and related settings stay adjacent.

**No `config.py` change, and the schema-driven property is preserved.** The
grouping keys off the control type the schema already implies, never off a field
name, so *a new setting in `config.py` still appears here with zero frontend
change* — the property spec v14 Decision 8 forbids losing. An `if (key === …)`
here would end it just as surely as one in the renderer.

Checkboxes lead because they are the shortest cells and the fastest to scan; the
tallest and most variable cells sink to the bottom of the panel.

### Decision 5 — groups are signposted by spacing alone

`--space-20` between groups against `--space-14` between fields. No
sub-headings, no separator rules.

Sub-headings here would be widget-shape names — "Toggles", "Choices", "Values" —
under a panel that already has a real, meaningful heading. A reader learns
nothing from "Values" that a column of input boxes has not already said, and
every section in the page would carry three of them.

### Decision 6 — cells align via subgrid

This is the mechanism that makes "keep the responsive grid" and "keep all the
chrome visible" compatible. Each `.field` declares four bands and spans four
parent rows:

```css
.fields {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-14);
}
.field {
  grid-row: span 4;              /* label · control · help · meta */
  display: grid;
  grid-template-rows: subgrid;
}
```

The parent sizes each band to the tallest cell **across the row**, so every
control in a row starts at the same y, every help block starts at the same y,
and every meta line bottoms out together — with variable-length help text and no
truncation.

Without subgrid the two requirements fight: fixed per-cell row heights need the
help text clamped, and unclamped help text makes each cell's control sit at its
own offset. Subgrid is the only mechanism that satisfies both, and it is
available in every browser this app targets.

The checkbox group gets a narrower track — `minmax(200px, 1fr)` — since a
checkbox has no 260px-wide control to hold.

### Decision 7 — all field chrome stays visible

Help text, the `config.py` key, the default badge, "reset to default",
"restart required" and "stored value hidden" all remain on screen at rest.

This is a configuration page whose readers are looking for exactly those facts;
hiding the key and the default behind hover would make "which fields differ from
default" unanswerable at a glance, unreachable on touch, and would undo what
SR56 and SR63 were for. Decision 6 is what makes keeping them affordable.

### Decision 8 — the changed-field marker gets a constant gutter

`.changed` currently adds `border-left: 2px solid var(--accent)` **and**
`padding-left: var(--space-8)` to edited fields only, so editing a field shifts
its contents 10px right of its unedited neighbours. The marker is itself an
alignment offender.

Every cell gets the same 10px gutter with a transparent border; `.changed` only
recolours it. Nothing moves when you type.

### Decision 9 — verification is a source guard plus unit tests

Following `ui/tokens.spec.ts`, which already asserts the design system by
reading `tokens.css` as text — an established pattern here, not new
infrastructure.

- **Guard test:** `--control-h` exists in `tokens.css`; all four control
  components consume it; no file under `workspaces/` declares `align-items` on a
  row that also renders `sb-button` / `sb-select` / `sb-text-input` /
  `sb-checkbox`. The last assertion is what catches the 48th row.
- **Unit tests:** `sb-control-row` (including `stacked`), and the checkbox's
  top-label mode.
- **Grouping test:** a section with mixed control types comes out partitioned in
  the Decision 4 order, with schema order preserved inside each group.

No visual-regression screenshots. Baselines rot, and font rendering differs
between a dev machine and the Docker build — the failure mode is a suite that
cries wolf until someone stops reading it.

### Decision 10 — responsive is checked, not redesigned

Every converted row is checked at the four breakpoints in `ui/breakpoints.ts`
(`xs`/`sm`/`md`/`lg`/`xl`, floors 640/1024/1440/1920), with attention at `sm` and
`md` where the sidebar collapses to its rail and the workspace gains width
mid-transition. The Settings grid is checked at `xs`, where the tracks yield one
column on a 360px phone and the subgrid bands still have to hold.

---

## Scope

**In:** `tokens.css`, `ui/form-controls.ts`, `ui/button.ts`, `ui/layout.ts`,
`ui/filter-bar.ts`, `ui/confirm-dialog.ts`, `workspaces/system/settings-tab.ts`,
and the control rows in the nine workspace files below.

**Out:** palette, type scale, panel treatment. The token system is deliberate and
this spec does not touch it. Charts are `v23`.

### The conversion targets

Classify-then-convert, not find-replace. Most of the 47 flex rows in these files
are **text** rows — `.head` on `baseline`, `.cell`, `.meta`, `.count` — which
must not become control rows; converting them would be the same mistake in the
other direction. `baseline` on a text row is correct and stays.

| File | Controls | Note |
|---|---|---|
| `trades/trades.ts` | 16 | densest — filter bar, chips, pagination |
| `system/settings-tab.ts` | 11 | Phase 2 |
| `analytics/analytics.ts` | 6 | 1523 lines, four tabs |
| `system/scan-tab.ts` | 5 | owns the `.kill` stacking row |
| `system/logs-tab.ts` | 3 | level filter, follow toggle |
| `watchlist/watchlist.ts` | 2 | add-ticker row |
| `risk/risk.ts` | 2 | |
| `dashboard/dashboard.ts` | 1 | |
| `trades/trade-detail.ts` | 1 | |

Plus `ui/confirm-dialog.ts` and `ui/filter-bar.ts` as the primitive's first two
in-repo consumers.

---

## Phases

**Phase 1 — the contract.** `--control-h`; the four controls consume it;
`sb-checkbox` top label; `sb-control-row`; `sb-filter-bar` and
`sb-confirm-dialog` converted; guard test.

**Phase 2 — Settings.** Type grouping; subgrid cell skeleton; constant
`.changed` gutter; the `.find` row and the save bar converted; grouping test.

**Phase 3 — the workspaces.** The nine files above, classified and converted;
responsive check at four breakpoints.

Phase 3 can be cut without invalidating 1 and 2.

---

## Parallelisation

- **Sequential:** Phase 1 before Phases 2 and 3 in their entirety. Every task in
  both consumes `--control-h`, `sb-control-row` or the checkbox's top label.
- **Within Phase 1 — sequential.** The token, the controls that read it, the row
  primitive and the guard test form a chain: each consumes the previous one's
  symbol, and three of the four edit `ui/` files that the others also touch.
- **Phases 2 and 3 — parallel with each other.** Phase 2 is confined to
  `settings-tab.ts`; Phase 3 touches the other eight workspace files. Disjoint
  files, no shared contract beyond Phase 1's.
- **Within Phase 3 — parallel, one task per file.** The nine conversions share
  no file and introduce nothing the others consume. This is the widest group in
  the spec and the reason the phase is worth doing as a phase.
- **Sequential:** the responsive check last, after every row it inspects exists
  in converted form.

The disjoint-files test is what governs here, not "unrelated features":
concurrent sessions share this working tree, so two agents on one file do not
merge — the second silently overwrites the first.

---

## Risks

- **Subgrid on the settings grid is the one novel mechanism.** If a band
  collapses unexpectedly the failure is visible immediately and confined to one
  page; the fallback is per-cell `grid-template-rows` with clamped help text,
  which is Decision 6's rejected alternative and can be adopted without touching
  any other decision.
- **The guard test's `align-items` assertion will fire on legitimate one-off
  layouts.** It is scoped to rows that render controls specifically, which is
  narrow enough to be a signal rather than noise; if it proves otherwise, narrow
  it further rather than deleting it.
- **`--control-h` changes every control in the app at once.** That is the point,
  and it is also why Phase 1 lands and is reviewed on its own before anything
  builds on it.
