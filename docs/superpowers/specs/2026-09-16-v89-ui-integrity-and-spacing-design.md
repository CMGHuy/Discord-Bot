# v89 — Admin UI audit, part 1: numbers that lie, and one spacing rule

**Version:** ui 1.18.2 · bot 1.9.0
**Bump:** ui patch — every change is a bug fix or a visual adjustment to an
existing screen; nobody has to relearn a page. The bot line is untouched
(see §3.3 for the one place that was deliberately left alone).
**Edge:** none (integrity) — no setup, exit or sizing changes. It is still
urgent: the partner places real broker orders from these screens, and a
flattering expectancy or a chart drawn with the wrong sign is a decision made
on a false number.
**Date:** 2026-09-16

## 1. Why this exists

On 2026-09-16 the partner asked for an audit of the whole admin UI — how data
is visualised on phone and desktop, overall UX, and **one consistent spacing
between tables and panels**. The audit was run against production
(`bomeo-capital.com`, ui 1.18.2) with Playwright at 390 / 1024 / 1440 px, with
a measuring script for gaps between sibling panels.

It found ~30 issues, which the partner agreed to split into four specs, run in
this order:

1. **This spec** — numbers that are wrong or contradict each other, and the
   spacing rule every later layout builds on.
2. Phone layouts — position cards, a filter sheet, destructive actions out of
   thumb reach, the ticker tape at 390 px, the 1024 px dashboard collapse.
3. Visualisation upgrades — trade-detail price ladder, strategy dot plot with
   N, confidence contribution bars, consolidating Analytics' five overlapping
   stat panels.
4. Watchlist load time (~20 s behind a full-screen spinner).

Specs 2–4 take their own numbers when written. Nothing here pre-empts them:
this spec fixes what a chart *says*, not how the page is arranged, except for
spacing.

## 2. Scope

**In:** every finding in §3 and the rule in §4, on the Dashboard, Risk,
Trades, Trade detail, Calendar, Analytics, Watchlist, System and Versions
workspaces.

**Out:** anything that changes how plans are produced or scored; new
workspaces (Research, Reports stay stubs); phone-specific layouts (spec 2);
new chart types beyond the one bar component §3.1 needs (spec 3).

## 3. Part A — integrity findings

Each item: what production showed, the traced cause, and the decided fix.

### 3.1 Bar charts reuse a count histogram for signed values and rates

**Observed.** Analytics › *By month* draws −82.47 and −72.86 as full-width
green bars. *By holding period*, *By planned R:R*, *By direction* and *By day
of week* print raw floats (`64.705882`, `52.272727`) that overflow the panel,
colour every bar green including rates below 50%, show no visible reference
line, and wrap labels like `Saturday (n=3 — below 20, rate withheld)` over six
lines.

**Cause.** `ui/histogram.ts` is a *count* histogram: width is
`count / tallest`, `tallest` is floored at 1, the count prints unformatted, and
"negative" means *the label starts with `-`*. `analytics.store.ts`
`monthHistogram` feeds it `return_pct` under labels like `2026-07` (never
negative by that test; its comment claims the predicate "already colours a
signed value correctly" — it does not). The win-rate splits feed it rates.

**Fix.** Keep `sb-histogram` for counts only (return and R-multiple
distributions, where it is correct). Add one component, `sb-bar-list`, for a
labelled value per row:

- `mode: 'signed' | 'rate'`. Signed draws a diverging bar from a centre zero
  axis, coloured by sign. Rate draws against a fixed 0–100 scale with a
  visible reference line (the population's win rate) and colours by
  *above/below the reference*, not by a hard-coded green.
- A `format` input; values are never printed raw.
- `n` is its own right-aligned column, not part of the label. A withheld rate
  shows a muted `n<20` and no bar.

Move *By month* (signed %), *By horizon* (§3.2), and the four win-rate splits
onto it. Fix `monthHistogram`'s false comment.

### 3.2 By horizon bars anchor at the wrong edge

**Observed.** Negative horizons grow leftward from the right edge; the one
positive value (9m, +0.002) is a dot on the far left. There is no zero line.

**Cause.** `ui/magnitude.ts` is one-sided: a negative bar is
`margin-left: auto` in the same track as a positive one.

**Fix.** *By horizon* moves to `sb-bar-list` in signed mode (§3.1). Other
`sb-magnitude` call sites whose values are always non-negative stay.

### 3.3 Three expectancies and four win rates on one page

**Observed.** Dashboard *Expectancy* and Analytics *Overall* read **−0.030R**;
Analytics *Derived* reads **−0.142R**, which is also Total R ÷ N
(−112.8 / 793). Win rate reads 50.1% (N=854), 52.9% (Derived, 798 trades) and
50.0% (donut, n=786).

**Cause.** Two expectancy definitions coexist:

- `tracking/performance.py` (the `stats` dict, read by
  `admin/api_v1/dashboard.py:222` and `analytics.py:135`) **expands scale-out
  legs into separate outcomes and drops every trade whose status is not
  `win`/`loss`** — scratches included.
- `analytics/metrics.expectancy_r` (read by `Derived`) averages
  `r_multiple()` per trade, legs blended, scratches included.

The all-time R-multiple histogram has **271 trades in the 0.0R bin**. Leaving
them out is what lifts −0.142R to −0.030R. The admin figure the partner sees
first is the flattering one.

**Decision.** Every admin surface reads expectancy from
`metrics.expectancy_r` and win rate from `metrics.win_rate`, over the
population the panel names, and shows that population's `N` beside the
figure. A trade is the unit an order is placed on, and a scratch really is a
0R outcome that uses up a shot. Two figures with the same label and the same
population must be equal; a test pins it (§5).

**Deliberately not changed:** `performance.py`'s `stats` also feeds
`scanning/plan_table.py` and the confidence breakdown's *Track record* line.
Changing it changes plan confidence, which is bot behaviour and a
pre-registration question, not a UI fix. It is recorded as a follow-on (§7).

### 3.4 "Total return −94.72%" on an account that lost 0.26%

**Observed.** Analytics › *Derived* shows Total return −94.72% and Annualised
−100.00%, beside Total P&L −2,639.93 € on a ~1,000,000 € account.

**Cause.** `metrics.total_return_pct` compounds **per-trade price returns** as
if each trade used 100% of the account in sequence. 798 trades averaging
−0.33% compound to −93%. `annualised_return_pct` and `calmar` derive from it.

**Fix.** *Total return*, *Annualised* and *Calmar* are computed from the same
account equity series the Equity chart draws: realised P&L over the starting
balance. The per-trade compounding functions stay for the backtest code that
uses them, renamed at their admin call site so they cannot be mistaken for
account figures. If a per-trade figure is kept on screen, its label says
"per trade, 100% sizing".

### 3.5 Exit reason mix is 91.4% "other"

**Observed.** The *Exit reason mix* donut is a grey ring: `other` n=729 of 798.

**Cause.** `metrics._exit_reason_bucket` maps only exact `EXIT_REASONS`
strings and `resolve_outcome` results. Its own docstring says a large `other`
bucket is "a finding about the data": production close-reason strings exist
that the list does not know.

**Fix.** A read-only production query lists the distinct close-reason texts in
`other` with counts. Each maps to an existing bucket where the meaning is
unambiguous, extending the exact-match table and never adding a fuzzy
fallback. Anything ambiguous stays `other`. Tests use the real strings. While
`other` exceeds 20%, the panel shows that share as a warning line above the
donut rather than letting a grey ring pass as data.

### 3.6 Calendar shows the future as flat days

**Observed.** 17–30 September (future) render `0` P&L and `0` trades,
identical to a real flat day. Today is not marked. The *By weekday* table's
header cells do not line up with its value columns.

**Fix.** Days after today render date-only (no value, no count); today gets an
outline. The weekday table's row-header `th` gets the same alignment and width
rules as its body cells.

### 3.7 Raw markdown on screen

**Observed.** `**AXON**`, `**462.52**` in Trade detail › *Why this trade*;
`**Worst:**`, `**Top tags:**` in Analytics › *Journal*.

**Fix.** One shared inline formatter that escapes HTML and then renders
`**bold**` only. Both call sites use it. No `innerHTML` of an unescaped
server string.

### 3.8 Risk page

- **Every position shows `0.00%` risk.** These positions carry ~0.003% each,
  below two decimals. Show risk to adaptive precision, and show the € amount
  at risk beside it.
- **"No sector exposure" with four open positions.** `growth.py` writes
  `sector_heat = {}` when no sector map resolves. Distinguish *no positions*
  from *sectors unknown for N positions*.
- **Scan health reads `—s LAST SCAN`.** An absent value renders as "No scan
  recorded", not a unit glued to a dash.
- **The same heat drawn three ways:** 0.01% figure, a bar, and a gauge reading
  0.2%. The gauge measures utilisation *of the cap*, the figure measures share
  *of the account*, and nothing says which is which. Keep the figure and bar,
  drop the gauge, and add one line: `0.2% of the 6.0% cap used`.
- `ui/gauge.ts` writes `height="auto"` on an `<svg>`, which is the console
  error on every page load. Fix the attribute; the component stays for other
  callers.

### 3.9 Dashboard

- **Win rate 100.0% and Expectancy 0.00R with no N.** Every rate and
  expectancy tile shows its N, per §3.3.
- **Recent Activity shows a green ▲ next to "Closed at −1.00R".** The arrow is
  trade direction; the text is outcome. The outcome (R) is coloured by sign,
  and the direction glyph is muted so it does not read as a result.

### 3.10 Smaller correctness items

- Donut centre totals (`786`, `708`, `731`) render near-invisible, dark on
  dark. They use the secondary text token.
- The "age unknown" / "as of … stale" labels float mid-toolbar or at the far
  edge, away from the data they qualify. They move into the owning panel's
  header, beside its title. Why Dashboard and Risk read "age unknown" at all is
  traced in the plan: a freshness stamp the endpoint does not send is a bug,
  not a label.
- Analytics › *By ticker* replaces the win rate with `n=17` when N<20, mixing
  two units in one column. It shows `—` and leaves N to the Trades column.
- Row counts repeat: Trades prints "1–25 of 948" three times and the rows
  selector twice, and Dashboard and Risk print "4 rows" twice. Each table
  prints its count and selector once, at the top.

## 4. Part B — one spacing rule

### 4.1 What production measures today

| Workspace | Vertical gaps between sibling panels (px) |
|---|---|
| Dashboard | 40, 60 (horizontal 20) |
| Risk | 20, 10, **0** |
| Trade detail | 14, **0** |
| Watchlist | 10, 68 |
| Analytics | 14, 38, 54, 75, 104 |
| Calendar | 20 |
| System | 32, 40, 20 |

**Causes.**

- Workspaces add their own `margin-top` on top of the host grid's gap
  (`dashboard.ts`: `.positions-panel` and `.bottom-row` each add `--space-20`
  to a `--register-pad` gap, hence 40).
- Some workspaces stack panels with no gap at all.
- `--register-pad` is 20 in the presentation register and 10 in the instrument
  register, so two pages with the same structure space differently.
- Two tokens are referenced but never defined: `--space-16`
  (`analytics/sections/exit-quality.ts`, so the Exit quality grid has **no
  gap**) and `--space-2` (`versions.ts`, twice). CSS drops an undefined
  `var()` silently.

### 4.2 The rule

1. **One token, `--section-gap`,** defined in `tokens.css`: `--space-20`, and
   `--space-14` below the `sm` breakpoint (640). It is the gap between any two
   sibling panels on every workspace, vertical and horizontal alike, in both
   registers.
2. **Panels never own outer margins.** A workspace host is a single-column
   grid with `gap: var(--section-gap)`. A row of side-by-side panels is a
   nested grid with the same gap. No `margin-top` or `margin-bottom` on a
   panel, a panel row, or a section heading.
3. **A section heading between groups** (Analytics' "By segment",
   "Breakdowns") sits inside the stack like any other child and takes the same
   gap. It is not a floating label hugging the panel below.
4. **Inside a panel,** nothing changes: header `--space-10`/`--space-14`,
   body `--space-14`, tables edge to edge (`sb-panel`'s existing rules).
5. **Tile groups** (metric cards, stat tiles) use `--space-10` between tiles.
6. **Off-scale values** (`2px` gaps, `1px`/`2px` paddings) move to
   `--space-4`, except hairline borders.
7. **Side-by-side panels of unequal height** align to the top and leave the
   shorter one short. Nothing stretches a panel to fill the hole, and nothing
   pads beneath it.

`--register-pad` stays for what it already does inside panels. It stops
governing the gap between them.

### 4.3 Guards

- A unit test reads every `var(--space-N)`, and every other `var(--…)` token
  referenced in `frontend/src`, and fails on any not defined in `tokens.css`
  or `styles.css`. That would have caught `--space-16` and `--space-2`.
- A unit test scans workspace component styles for `margin-top`/
  `margin-bottom`/`margin-block` declarations on panel-level selectors and
  fails on any not in an explicit, commented allowlist.
- The Playwright gap-measuring snippet used for this audit is committed as
  `scripts/dev/ui_spacing_audit.js`: paste-into-devtools, no credentials. The
  verification task records its output per workspace at 390 and 1440 px.
  Every sibling-panel gap must read 14 or 20.

## 5. Testing

- **Unit (Vitest):** `sb-bar-list` signed mode (negative bar left of zero,
  coloured `--neg`), rate mode (reference line position, colour by reference),
  formatting, withheld rows; the inline formatter (escapes `<script>`, renders
  bold, leaves single `*` alone); Calendar future-day rendering; the token and
  margin guards.
- **Backend (pytest):**
  - `analytics` and `dashboard` endpoints return the same `expectancy_r` and
    `win_rate` for the same population, including a fixture with scale-out
    legs and a scratch, where the two old definitions differ.
  - Total return equals realised P&L ÷ starting balance.
  - Exit-reason bucketing maps each real production string.
- **Live check** after deploy: re-run the audit script on the eight workspaces,
  confirm *By month* signs, and confirm the Dashboard and Analytics expectancy
  match the Derived figure.
- One full suite run, as the plan's last task.

## 6. Parallelisation

- **Sequential first:** B1 (`--section-gap` token, the two guard tests,
  `sb-bar-list`, the inline formatter, the `gauge.ts` attribute). Every
  workspace task consumes one or more of these.
- **Group 1 (parallel, after B1):** one task per workspace file, each applying
  §4.2 *and* that workspace's §3 items, because both edit the same component
  file: Dashboard, Risk, Trades + Trade detail, Calendar, Watchlist, System +
  Versions.
- **Analytics is its own sequential task** after B1 (`analytics.ts`,
  `analytics.store.ts`, `sections/exit-quality.ts`). It consumes the backend
  payload from Group 2, so it runs after that group.
- **Group 2 (parallel with Group 1):** backend — expectancy/win-rate
  unification in `admin/api_v1/analytics.py` + `dashboard.py`; account-equity
  total return in `metrics.py`'s admin path; exit-reason mapping (after its
  read-only production query).
- **Last:** live audit re-run, then the full suite.

## 7. Follow-ons recorded, not built

- **The bot's `stats` expectancy excludes scratches and splits legs**
  (`performance.py`), and feeds plan confidence's *Track record* line and
  `plan_table.py`. Whether that population is the right one for a confidence
  input is a bot spec with its own pre-registration question. This spec only
  stops the admin UI from displaying it as *the* expectancy.
- The 271 trades in the 0.0R bin are the same population as the
  near-TP-timeout lead the book-autopsy work starts from (recorded in v82's
  Follow-on).
- Specs 2–4 from §1.
