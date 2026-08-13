# Admin UI design system

**Date:** 2026-08-08
**Version:** ui 1.0.9 · bot 1.1.2
**Status:** design agreed, not implemented
**Scope:** design only — no Angular code, no backend work

## Why this exists

The admin UI is being rebuilt as an Angular SPA. That migration is too large for
one spec, so it is split into six sub-projects:

| # | Sub-project | Status |
|---|---|---|
| 1 | REST API for the whole admin surface | not started |
| 2 | Real-time event push (bot → admin) | not started |
| 3 | **Design system** | **this document** |
| 4 | Angular shell + build/deploy/auth | not started |
| 5 | The workspace implementations | not started |
| 6 | Cutover, delete Jinja | not started |

This document covers **only** sub-project 3. It defines what the new UI looks
like and how it is organised. It specifies no components in Angular terms, no
API shapes, and no build tooling.

Delivery remains a big-bang cutover: everything is built behind the existing
Jinja UI and switched once. Decomposition here is a planning device, not a
change to that decision.

## The problem being solved

Three faults were identified in the current UI, all confirmed as real rather
than cosmetic:

1. **Too dense to scan.** Fourteen stat cards of equal weight in one row, and a
   nineteen-column table. No hierarchy tells you what matters.
2. **Structure.** Eleven flat sidebar entries with no grouping. One trade's data
   is spread across Dashboard (live P&L), Performance (its strategy's record),
   Journal (notes) and its own detail page — four places for one thing.
3. **Inconsistency.** Styling drifted as pages accumulated: inline styles,
   one-off colours, components that nearly match.

A recurring root cause runs through 1 and 3: **the design deferred decisions to
the user instead of making them.** The compact/full density toggle and the
drag-to-reorder columns both exist because nobody decided what earns space.

## Decision 1 — Information architecture

Eleven flat pages become **six workspaces**:

| Workspace | Absorbs | Purpose |
|---|---|---|
| **Cockpit** | Dashboard | What is true right now |
| **Trades** | Plans, Journal, trade detail | Every trade as an entity |
| **Analytics** | Performance, Strategies, Calibration, Tuning | Historical analysis |
| **Universe** | Watchlist | Tickers, with per-ticker detail |
| **Risk** | Risk | Exposure and the killswitch |
| **System** | Settings, Logs | Administration |

### The entity model inside Trades

Trades is the one workspace that is entity-first rather than page-first, because
it is where the four-way split hurt:

- **List** — every trade regardless of state. Status (`PENDING` / `ACTIVE` /
  `PARTIAL` / `CLOSED` / `CANCELLED`) is a *filter*, not a separate page. This
  absorbs both the Plans board and the Dashboard's two tables.
- **Detail** — one trade, with tabs: **Plan** (entry, stop, TP1/TP2, R:R,
  sizing) · **Live** (price, unrealised P&L, SL→TP progress) · **Chart** ·
  **Notes** (was Journal) · **Strategy** (how this setup has performed).

Universe follows the same shape at lower priority: a ticker list plus a per-ticker
view showing its open trades, past trades and chart.

Tuning sits under Analytics rather than System: it proposes strategy parameters
from backtests, which is analysis rather than administration.

Risk keeps its own destination rather than folding into Cockpit, because it owns
the killswitch — an operational control, not a readout.

## Decision 2 — Density and hierarchy

> **Superseded in part by v18 (2026-08-13).** The compact/full toggle, the
> drag-to-reorder columns and the seven-column default all come back — the
> committed default turned out to be seven columns nobody could extend into the
> view they actually wanted. Row expansion survives with a narrower job. The
> Cockpit header's two tiers below are untouched. See spec v18 Decision 4.

**The compact/full toggle is removed. The drag-to-reorder columns are removed.**
Both are replaced by a committed default plus targeted escape hatches.

### Cockpit header — two tiers

Nine metrics are daily. Nine equal cards reproduces the original fault, so
hierarchy comes from **size**, not from culling:

- **Primary (3 large cards):** Account balance · Open P&L · Risk used
- **Secondary (6 compact chips):** Open trades · Avg confidence · Win rate ·
  Expectancy · Equity 30d (sparkline) · Position premium

**Moved to Analytics:** Wins, Losses, Avg realized P&L, Best trade, Worst trade,
Avg holding period.

Arithmetic: fourteen cards today, minus those six, plus one new (Risk used) —
nine. "Risk used" is open portfolio heat as a percentage of
`PORTFOLIO_HEAT_CAP_PCT`; it is promoted from the Risk page because current
exposure belongs beside current P&L.

### Trades table — seven columns plus expansion

Always visible: `#` · Status · Ticker · Now · P&L% · Held · actions.

Row expansion reveals what the other eleven columns carried: plan levels
(entry/target/stop, R:R), setup (strategy, horizon, confidence level and score),
sizing (shares, deployed, unrealised amount), and opened timestamp.

The test applied: **a column earns its place if you scan it down the rows.** If
you inspect it for one trade at a time, it belongs in the expansion.

### Column picker

Users may add any of the eleven expansion fields back as columns.

Three constraints keep this from becoming the old toggle:

1. The seven-column default is the **designed** state, not one preset among
   equals. "Reset to default" is always available.
2. **Visibility only — order is fixed by design.** This is what allows the
   drag-to-reorder machinery to retire.
3. The choice persists per user.

## Decision 3 — Visual language

> **Superseded in part by v18 (2026-08-13).** The three-rule colour system
> (`green/red = money only · amber = caution · blue = interactive only ·
> everything else greyscale`) becomes *one colour, one **valence***, and the
> palette moves off near-black onto an indigo-charcoal ramp. The motion rule
> ("120ms on state change, nothing on entrance") becomes a three-step scale;
> the specific thing it ruled out — a card flash on every push event — stays
> ruled out. The type scale, the density and the monospace numerics below are
> untouched. See spec v18 Decisions 2 and 3.

**Terminal:** near-black, monospace numerics, minimal chrome, colour reserved for
signal. Chosen over evolving the current palette (too little change for a stated
"dated" problem) and over a light modern look (whitespace fights the density this
tool needs, and it is harsher on a screen watched for hours).

**Dark only.** No light theme. A terminal aesthetic does not have a light
counterpart worth maintaining, and this is a single-user private tool.

### Colour tokens

```
--bg              #000000    page
--surface         #0a0a0a    cards, panels
--surface-raised  #121212    expanded rows, menus, modals
--border          #1c1c1c    default rules
--border-strong   #2a2a2a    emphasised separation

--text            #f0f0f0    primary values
--text-secondary  #888888    labels
--text-muted      #666666    supporting detail
--text-faint      #444444    row numbers, disabled

--pos             #00d26a    profit
--neg             #ff4d4d    loss
--warn            #ffb020    caution (risk near cap, paused, stale)
--accent          #4d9fff    interactive only
```

**Colour rules, enforced by review:**

- Green and red mean **P&L direction**. Never decoration, never status-that-isn't-money.
- Amber means **caution** — risk approaching cap, scanning paused, data stale.
- Blue means **interactive** — links, focus rings, selection. Never applied to data.
- Anything else is greyscale.

This is the single biggest fix for "inconsistent": the current UI uses blue for
both values and links, and green for both profit and generic success.

**Consequence for quality indicators.** Confidence level, confidence score and
tier chips are currently coloured green/amber/red by value, which the rule above
forbids — they are quality, not money. They move to a greyscale ramp with amber
reserved for the weakest band: `Lv5/A` at `--text`, `Lv3/B` at `--text-secondary`,
`Lv1/C` at `--warn`. Applying the rule and leaving these unchanged would be
worse than not applying it, because green would then mean two different things
in adjacent columns of the same row.

### Typography

Two vendored families:

- **JetBrains Mono** — every numeric and tabular value. Not a stylistic choice:
  digits align down a column, which is what makes a dense price table scannable.
  Must be vendored alongside Inter, as `static/vendor/inter/` already is.
- **Inter** — labels, prose, navigation. Already vendored.

Scale (px): `9` micro-label · `10` chip · `11` table body · `12` body ·
`14` subheading · `18` section title · `23` primary metric.

### Spacing, radii, motion

- Spacing scale: `4 · 6 · 8 · 10 · 14 · 20 · 28`. No arbitrary values.
- Radii: `4px` panels and controls, `3px` chips. Tight — terminal, not consumer app.
- Motion: 120ms ease-out on state change. No entrance animations. The current
  blinking status dot survives; the card-flash on refresh does not (real-time
  push makes "something changed" continuous rather than a 5s event).

## Component inventory

What the six workspaces need. This is the build list for sub-project 5, not an
Angular API.

**Shell:** sidebar nav · workspace header · bot/connection status · toast host

**Data display:** metric card (large) · metric chip (compact) · sparkline ·
data table (sticky header, sortable, column picker, expandable rows, pagination) ·
status indicator (dot + SL→TP progress bar) · chip/tag (tier, horizon,
confidence) · chart container · empty state

**Input:** button (primary/secondary/danger/ghost/icon) · select · text input ·
checkbox · filter bar · confirm dialog

**Layout:** panel · tab bar · split view · drawer

The data table is the load-bearing component — it appears in Trades, Analytics,
Universe and Risk, and carries the column picker and row expansion. It should be
specified and built first, and the other workspaces should not begin until it is
settled.

## Explicitly out of scope

- Angular implementation of any component
- API shapes and endpoints (sub-project 1)
- Real-time transport (sub-project 2)
- Build tooling, routing, auth (sub-project 4)
- Chart rendering internals — lightweight-charts stays; only its container and
  theme are in scope here
- Mobile and responsive layouts. This is a desktop monitoring tool on a private
  network. Below ~1100px is not designed for.

## Risks

**The metrics moved to Analytics may be missed.** Six figures currently
glanceable become one click away. This is the accepted cost of committing to a
hierarchy, and it is reversible — the chip strip has room.

**Terminal is a polarising look.** It fits what this app is, but it is the
option most likely to feel tiring after months. Mitigation: the tokens are
centralised, so a palette change later is a token edit rather than a rewrite.

**Monospace costs horizontal space.** Mono digits are wider than Inter's. The
seven-column table has room; the expansion content needs checking at 1280px
before the design is called done.

**The column picker can regress into the old toggle** if the default is treated
as merely one option among many. The three constraints above exist to prevent
that and should be enforced in review.

## Open questions

None blocking. Two to settle during sub-project 5:

1. Whether Analytics needs its own sub-navigation, or whether four sections
   (Performance, Strategies, Calibration, Tuning) fit as tabs.
2. Whether the Trades list needs saved filters, or whether status filter plus
   the existing six dropdowns suffice.
