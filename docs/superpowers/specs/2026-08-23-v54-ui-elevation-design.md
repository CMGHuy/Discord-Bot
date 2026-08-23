# v54 — UI elevation: primitives, honest state, depth and register

**Bump:** `ui` minor — every workspace changes observably; no bot-side change.
**Edge:** `none (integrity)`
**Status:** design approved 2026-08-23; plan not yet written.
**Depends on:** v50, v51, v52, v53 all merged to `main` before Task 1 starts.

## Why this is `Edge: none (integrity)` and got picked anyway

This buys no expectancy. Under "Prioritise expectancy and win rate" that ranks
it below v51 (alert-density expectancy), and this document says so rather than
dressing it up.

It was chosen because the admin is the only surface through which a human
judges whether the bot is behaving, and three of its current defects are
*correctness* defects wearing a styling costume:

- A table that renders identically whether the fetch failed, the data has not
  arrived, or the measured answer is genuinely zero. `known-traps.md` already
  records that this repo has empty tables which are answers, not stubs — the
  UI cannot currently tell you which one it is showing.
- Data with no visible staleness marker, on a surface whose whole premise is
  live prices.
- `--pos` and `--neg` — the most carefully argued rule in `tokens.css` —
  locally redefined in three workspaces, so the valence law is already
  forking.

Those cost decisions, and bad decisions cost R. That is the argument; it is
not a claim that this plan raises `ExpR`, and no acceptance gate anywhere is
loosened by it.

## Where the UI actually stands (measured 2026-08-23, not assumed)

The token discipline is **already strong** and this plan does not "clean it
up": there are zero off-scale font sizes and zero off-scale spacing values
across 22k LOC — only 1px/2px borders sit off the scale, correctly.

The gaps are elsewhere, and each number below is the reason a decision exists:

| Measured | Value | Decision |
|---|---|---|
| Workspaces with an empty state | 1 of 7 (dashboard) | D3 |
| Workspaces with a loading skeleton | 1 of 7 (trades) | D3 |
| Files with `loading()` but nothing to show | 11 | D3 |
| `--surface-overlay` uses | 3 | D2 |
| `box-shadow` uses | 5 | D2 |
| `aria-live` / `aria-busy` files | 1 / 2 | D6 |
| Raw hexes in `ui/line-chart.ts:73` | 8 | D5 |
| Hand-written CSS rules across workspaces | ~296 | D7 |
| `.head` redefined in | 7 of 7 workspaces | D7 |
| `.pos` / `.neg` redefined in | 3 workspaces each | D7 |
| Raw controls outside `ui/` | 21 (12 button, 7 input, 2 select) | D7 |
| `sb-button` used vs raw `<button>` | 31 vs 12 of 43 | D7 |

The primitive layer is **not missing**. `ui/` already exports real components:
`button[sb-button]`, `sb-select`, `sb-text-input`, `sb-checkbox`, `sb-chip`,
`sb-quality-chip`, `sb-panel`, `sb-tab-bar`, `sb-control-row`, `sb-drawer`,
`sb-filter-bar`, `sb-empty-state`. Control adoption is 72% for buttons. The
leak is one level above the controls, in composites each workspace reinvents
locally.

## Non-goals

- **No new identity.** Dark-only stays; `#7b5cfa` stays; Inter and JetBrains
  Mono stay; 4px radii stay; the one-hue-one-valence law stays. No display
  face, no new logotype, no re-skin. v18/v20/v22 are extended, not superseded.
- **No light theme.** `tokens.css` argues this out already and nothing here
  reopens it.
- **No token churn.** Every existing token keeps its current value and
  meaning. This spec adds tokens; it changes none, so no component can break
  silently by being left alone.
- **No new data.** Nothing here asks the API for a field it does not serve.
- **No workspace rewrites.** `analytics.ts` (1582 lines) and `trade-detail.ts`
  (1083) are large, but splitting them is not this plan's job and would
  collide with v50's edits.

---

## D1 — Two registers, declared per panel

**Density is a property of the panel, not the app.**

- **Presentation register** — answers *"how am I doing?"* Hero metrics at
  `--text-metric`, `--space-20` gutters, charts lead, elevation used.
- **Instrument register** — answers *"what exactly happened to row 4,192?"*
  `--text-table` / `--text-micro`, `--space-8` gutters, tables lead, borders
  not shadows.

Both draw from the **same closed scales**. A register picks different rungs;
it never introduces a value that is not already on the scale. A register that
needed a new size would be a review defect, exactly as an off-scale literal is.

Declared as a class on the panel root: `.register-presentation` /
`.register-instrument`. A workspace sets a default on its root; an individual
panel may opt out.

**Why per panel and not per workspace:** analytics is genuinely both — its top
summary strip presents, its tables instrument. A workspace-level rule would
force analytics to misdeclare itself, and the first exception would license
the rest.

Default assignment:

| Register | Surfaces |
|---|---|
| presentation | dashboard, calendar (v53), analytics summary strip |
| instrument | trades, risk, system, watchlist, versions, analytics tables |

## D2 — The elevation ladder, and the one-shadow law

Four levels, using the four existing surface tokens, whose values already form
a clean four-step lightness ramp (`#0a0b10` → `#10121a` → `#171a25` →
`#1e2230`):

| Level | Token | Border | Shadow | Meaning |
|---|---|---|---|---|
| L0 | `--bg` | none | none | the page |
| L1 | `--surface` | `--border` | none | a panel resting on the page |
| L2 | `--surface-raised` | `--border` | none | a thing on a panel: sticky header, selected row, inline card |
| L3 | `--surface-overlay` | `--border-strong` | yes | a thing floating free of layout: dropdown, popover, tooltip, toast, drawer, dialog |

**Shadow appears at L3 and nowhere else.**

In a dark UI a shadow under a panel is mud rather than depth — near-black on
near-black reads as smudge. Depth here is carried by surface *lightness*, and
shadow is reserved to carry one specific meaning: *this element is not part of
the page flow*. That makes elevation readable instead of decorative, and it is
mechanically checkable (see G3).

New tokens, the only two this decision adds:

- `--shadow-overlay: 0 8px 24px rgba(0, 0, 0, .55), 0 2px 6px rgba(0, 0, 0, .4)`
- `--scrim: var(--overlay-dim)` — alias, so modal scrims stop hand-rolling
  their own rgba.

L3 elements that are modal (dialog, mobile drawer) take the scrim; L3 elements
that are transient (tooltip, dropdown, toast) do not.

## D3 — `sb-async`: honest state, four branches

One wrapper owns every fetch-backed region. Defined in `_1`, applied in `_2`.

| Branch | Renders |
|---|---|
| `loading` | a **shaped** skeleton — correct column count, correct row height |
| `error` | message + retry action |
| `stale` | values dimmed to `--text-secondary` + an `as of HH:MM` chip in `--warn` |
| `empty` | `sb-empty-state`, **with a required reason** |

**The skeleton is shaped, not a spinner.** It must occupy the same geometry
the loaded content will, so nothing reflows on arrival. A spinner replaced by
a table moves every element on the page at the moment the reader started
reading it.

**The empty branch requires the caller to name which empty it is:**

- `no-data-yet` — nothing has been fetched, or the set is genuinely
  unpopulated.
- `measured-zero` — the computation ran and the answer is zero.

`known-traps.md` warns that this repo contains empty tables which are measured
answers rather than stubs. Rendering both identically is a correctness bug: it
tells the reader "something is broken" when the truthful message is "the scan
found nothing, and that is the finding." Making the reason a **required**
input means it cannot be skipped by omission — a call site that has not
thought about it will not compile.

This decision absorbs the locally-redefined `.stale` (5 workspaces) and
`.error` (5 workspaces).

## D4 — Numeric law

Every numeric cell in the app obeys all of:

1. **Right-aligned**, `.num` (mono, `tabular-nums`).
2. **Decimals fixed per unit**, never per value: R → 2dp, % → 1dp, price →
   2dp, count → integer.
3. **Unit named once**, in the column header. Cells do not repeat it.
4. **Sign encoded twice** — glyph *and* colour. Never colour alone: it fails
   for colour-blind readers, and it fails in a screenshot pasted into Discord.
5. **Zero and absent render differently**: `0.00` is a measurement, `—` is the
   absence of one. This is D3's distinction at cell scale.
6. **Magnitude gets one shared inline bar component**, so "how big" is
   scannable without reading digits.

Absorbs the locally-redefined `.pos` / `.neg` / `.muted` (3 workspaces each)
by promoting them to global utilities.

## D5 — One chart system, and a series-colour namespace

`ui/line-chart.ts:73` hardcodes eight raw hexes outside the token system. They
are replaced by `--chart-1` … `--chart-8`, governed by one rule:

**A categorical series colour may never be `--pos` or `--neg`.**

Green means gain and red means loss on every other surface in this app. A
series that happened to be green would be lying to a reader whom every other
screen has trained. Series colours are therefore a **separate namespace**,
declared as such — which is also the honest resolution of the tension with the
"a sixth hue is a review defect" rule in `tokens.css`. That rule governs
*semantic* hues. Categorical series are not semantic; they are identifiers,
and the two namespaces must not overlap.

The ramp is derived from the existing `--accent` / `--info` / `--warn` family
by controlled lightness and chroma steps, and must satisfy: adjacent pairs
distinguishable at 1px stroke width; no member within ΔE 10 of `--pos` or
`--neg`.

One shared axis / grid / tooltip treatment then applies across `line-chart`,
`sparkline`, `histogram` and `trade-chart`, which currently each style their
own.

## D6 — Information architecture, accessibility, motion

**Nav grouping.** Eight workspaces is past what a flat list communicates:

| Group | Entries |
|---|---|
| MONITOR | dashboard · watchlist · risk |
| REVIEW | trades · calendar · analytics |
| SYSTEM | system · versions |

Group labels are `--text-micro`, `--text-muted`, and hidden on the collapsed
rail, where the existing `.label` clip rule already handles them.

**Accessibility.**

- One `aria-live="polite"` region **per workspace**, not per cell. Per-cell
  live regions on a push-driven UI produce continuous announcement, which is
  worse than silence.
- `aria-busy` on the `sb-async` host while loading.
- Focus moves to the workspace `<h1>` on route change; drawer and dialog trap
  focus and restore it to the invoking element on close.
- Contrast audit of every text-token / surface-token pair against WCAG AA
  (4.5:1). One rule falls out of it and is binding: **`--text-faint`
  (`#464d63`) is never used for text that must be read** — it is a rule and
  divider colour only.

**Motion.** A single `[sbFlash]` directive: fires at `--dur-base` with
`--pos-soft` / `--neg-soft`, **only when the bound value actually changed**,
and only on the cell. Never on the card — `tokens.css` already rules that out,
and this implements the rule rather than restating it.

## D7 — The primitive layer

Ordered first in the plan, because every later decision installs parts this
one builds.

**9a. Close the control gaps — by fixing the primitives, not the call sites.**

21 raw controls remain outside `ui/`. The instinct is to migrate them. That
instinct is wrong here, and the census shows why — each cluster was diagnosed
individually rather than counted:

| Raw control | Where | Diagnosis |
|---|---|---|
| `class="chip"`, `class="chip moved"` | versions | `sb-button` has no `chip` variant |
| `class="segment"` | versions | no `segment` variant |
| `class="link"` | versions | no `link` variant |
| `<input type="date">` ×2 | analytics | `sb-text-input` has no `date` type |
| `<input>` ×2 with `ngModel` | login | primitives use `model()`, not `ControlValueAccessor` |
| `<button class="toast">` | toast-host | the whole toast is the button; structural |
| `<input type="file">` | settings-tab | file inputs cannot be wrapped without losing the picker |
| 8 buttons, 1 checkbox, 1 text input, 2 selects | shell, profile-menu, login, settings-tab, watchlist, logs-tab | primitive already fits — plain migration |

Only the first five rows are real gaps. Note what the census also
disproves: `sb-button` **does** already have an `icon` variant, so the shell's
icon buttons are migrations, not gaps — a plan written from the raw count
alone would have added a variant that exists.

`form-controls.ts:5` records why login is raw: *"Nothing in this application
uses Angular forms."* Login is the exception to that, and it predates the
primitives. Either the primitives gain `ControlValueAccessor` or login drops
`ngModel` for `model()`; the plan picks the second, because adding CVA to
three components to serve two fields in one template is the larger change.

So 9a inverts the usual order. First extend the primitives to cover the real
gaps — `sb-button` gains `chip`, `segment` and `link`; `sb-text-input` gains
`date` — then migrate. Migrating first would either force call sites onto
controls that do not fit, or produce a fistful of allowlist exceptions, and
**a gate that starts life with a fistful of exceptions teaches everyone that
exceptions are normal.**

Two entries stay raw and land on the allowlist with reasons: the file input
and the toast. That is the whole permanent exception list, and 9d requires
each entry to justify itself in a comment.

**9b. Extract the reinvented composites.** New components, each replacing a
pattern measurably duplicated across workspaces:

| New | Replaces | Duplicated in |
|---|---|---|
| `sb-section-head` | `.head` | 7 workspaces |
| `sb-row-link` | `.row-link` | 4 |
| `sb-note` | `.note` | 3 |
| `sb-chip-row` | `.chips` | 3 |
| `sb-async` | `.stale`, `.error` | 5, 5 |
| global valence utilities | `.pos`, `.neg`, `.muted` | 3, 3, 3 |

**9c. The gallery route.** `/ui` renders every primitive, in every variant, in
every state — including the four `sb-async` branches and both registers.

This is the keystone of the plan, for a reason that is not cosmetic. It is the
only surface on which D2's ladder, D4's numeric law and D5's chart ramp can be
seen *together* and judged as one system; reviewing them one workspace at a
time is how inconsistency survives review. It is also what makes reuse the
path of least resistance — a developer who cannot find a primitive writes a
`<div>`.

The route sits behind the same auth guard as the rest of the SPA. It ships in
the production bundle deliberately: a gallery that exists only in dev rots,
because nothing fails when it does.

**9d. The regression gate.** `ui/primitives.spec.ts`, following the existing
`ui/tokens.spec.ts` precedent, fails on:

- a raw `<button>`, `<input>` or `<select>` in a template outside `ui/`;
- `.pos`, `.neg`, `.muted`, `.stale`, `.error` or `.head` defined in a
  component outside `ui/` or global CSS;
- a hex literal outside `tokens.css`.

An allowlist file accompanies it, and **every entry carries a comment
justifying itself** — the convention the rest of this repo already uses for
documented exceptions. Without this gate, 9a and 9b decay to today's state
within a handful of features, which is exactly how it got here.

---

## Acceptance gates

Each is mechanically checkable; none is a judgement call.

| # | Gate |
|---|---|
| G1 | `sb-async` wraps every fetch-backed region: count equals the number of fetching surfaces, enumerated in the plan. |
| G2 | Every `sb-async` empty branch passes an explicit reason. No default. |
| G3 | `box-shadow` appears in exactly one rule in the codebase (the L3 rule). |
| G4 | Zero hex literals outside `tokens.css`. |
| G5 | Every text-token / surface-token pair ≥ 4.5:1, or documented as non-text. |
| G6 | No layout shift on data arrival: skeleton geometry matches loaded geometry for each surface. |
| G7 | `ui/primitives.spec.ts` passes, with an allowlist whose every entry is justified in a comment. |
| G8 | `/ui` renders every exported primitive; a primitive absent from the gallery fails the spec. |
| G9 | No `--chart-*` member within ΔE 10 of `--pos` or `--neg`. |
| G10 | Python suite unchanged at `1686 passed, 66 skipped, 0 failed, 0 xfailed`; frontend vitest green. |

G10 matters more than it looks: this plan touches no Python, so a moved Python
count means something unintended happened.

## Parallelisation

```
_1-primitives (D7)                  solo wave
       |
       +-- _2-states    (D3)        parallel with _3
       +-- _3-craft     (D2, D4)    parallel with _2
                |
                +-- _4-register (D1, D5)   parallel with _5
                +-- _5-ia-a11y  (D6)       parallel with _4
```

- **`_1` runs alone.** It edits `ui/` and touches every workspace file. Nothing
  may run beside it — this working tree is shared, and two agents in one file
  overwrite rather than merge.
- **`_2` ∥ `_3`** — disjoint files. `_2` installs `sb-async` at call sites;
  `_3` edits `tokens.css` and the numeric primitives. Neither reads the
  other's output.
- **`_4` ∥ `_5`** — `_4` needs `_3`'s elevation and chart tokens to exist;
  `_5` needs `_2`'s wrapper for `aria-busy` and focus handling. Between
  themselves they are disjoint: `_4` is panels and charts, `_5` is shell nav,
  live regions and the flash directive.
- **The sequencing is load-bearing, not tidiness.** Styling D2's elevation
  before D7 extracts `sb-section-head` would mean styling seven copies of one
  header and then deleting six.

## Risks

| Risk | Mitigation |
|---|---|
| v50–v53 slip; this plan is blocked | Accepted deliberately. Restyling v53's calendar twice costs more than waiting. |
| `_1` is a wide diff across every workspace | It is mechanical and gate-checked. `_1` merges to `main` before any of `_2`–`_5` starts. |
| Nav grouping (D6) is the change most likely to be disliked | It is the most severable item in the plan: cutting it unravels nothing else. |
| The gallery route rots | G8 fails the build when a primitive is missing from it. |
| The `--chart-*` ramp is hard to satisfy under G9 | The ΔE constraint is checked in a unit test at token-definition time, before any chart is restyled. |
