# SPA refresh — QA walk

Plan `2026-08-13-v21-spa-refresh.md`. One section per phase, walked against a
running SPA on the built bundle, not against `ng serve` — the bundle is what
deploys, and NG54 already cost a release to that distinction.

Fixtures come from `scripts/seed_parity_fixtures.py`, in the worktree's own
`data/`.

---

## Phase 1 — Tables (SR7–SR18)

Walked 2026-08-13. Server on the real bundle, Chromium at 1440×900.

### Both tables, both modes

| Line | Result |
|---|---|
| Trades renders the compact set, in order | **PASS** — `# status ticker confidence direction now plan pnl r opened closed` |
| Trades renders the full set | **PASS** — adds `R:R strategy horizon held realised` |
| Density toggle switches between them | **PASS**, and back again |
| Dashboard renders the same definitions | **PASS** — same headers, its own table id |
| Dashboard has no per-page control | **PASS** — deliberate; the panel is capped and its filter is fixed |

### The cells

| Line | Result |
|---|---|
| Plan cell on a long | **PASS** — `101.00 → 110.00 / 95.00`, target green, stop red |
| Plan cell on a short | **PASS** — same order, target is the lower number, colours carry the roles |
| Direction arrow | **PASS** — ▲/▼ with `aria-label` "Long (bullish)" / "Short (bearish)" |
| Confidence | **PASS** — `Lv4 · 81`; separator absent when the score is |
| Status bar near TP | **PASS** — 85%, band `toward_target`, "Near target" |
| Status bar near SL | **PASS** — 15%, band `toward_stop`, "Near stop-loss" |
| Status bar at entry | **PASS** — 50%, band `neutral`, "Near entry" |
| Status bar with no price | **PASS** — chip plus "no price" |
| PENDING | **PASS** — chip alone, no bar |
| CLOSED | **PASS** — chip alone |

**The spectrum needed new fixtures.** The original set prices plans at ~101
against real quotes near 493, so every live bar clamped to 100% and the walk
showed four identical full bars. `_spectrum_plans()` now derives stop and
target *from the live price* so a position lands at a chosen point on its own
span. First attempt placed them symmetrically and moved the entry instead,
which varied only the band and left three identical half-bars — the levels have
to be asymmetric for the bar length itself to differ.

### Interaction

| Line | Result |
|---|---|
| Picker independence across modes | **PASS** — arranging Full left Compact untouched |
| Drag-reorder by mouse | **PASS** |
| Reorder by keyboard | **PASS** — Left/Right on a focused header |
| Pinned column immovable | **PASS** — actions neither drags nor accepts a drop |
| Per-page 10 / 25 / 50 / All | **PASS** — 10 → 10 rows, All → all 40 |
| Selector survives choosing All | **PASS** — it is outside the pager, so it does not delete itself |
| Preferences survive a reload | **PASS**, after two defects below |
| Console clean | **PASS** — no errors, no 4xx |

### Defects found and fixed

**1. Per-page changed nothing.** The selector wrote the preference and the
query kept sending `DEFAULT_PER_PAGE` — a constant, so the effect had nothing
to re-run on. Choosing "All" saved "All" and returned 25 rows forever. Fixed by
reading the signal in the query.

**2. Saved preferences were written and then ignored.** Every workspace seeded
its density, columns and page size synchronously in a field initialiser, but
`PreferencesStore.load()` is async — so on a cold load those reads got `{}` and
everyone saw the defaults. The write path worked perfectly, which is what makes
this hard to notice: the server had the right values the whole time. Fixed with
an effect that applies stored preferences once `isLoaded()` flips.

**3. The per-page control disagreed with the table.** `[value]` on a `<select>`
is applied before `@for` has created any options, so it matched nothing and the
control fell back to its first entry — it read "10" while the table was paging
by 50. Moved to `[selected]` on the option.

All three are pinned by tests. Each is the same shape: a control that looked
right and did nothing, or did something and looked wrong.

### Not walked

- **A second browser.** Preferences are server-side, so a reload in one browser
  exercises the same path a second browser would; a genuinely concurrent check
  belongs with the multi-session work, not here.

---

## Phase 2 — Shell and responsive (SR20–SR31)

Walked 2026-08-13, same server and bundle.

### Every workspace at four widths

`document.documentElement.scrollWidth` vs `window.innerWidth`, measured rather
than eyeballed. Twenty combinations, every one equal:

| | 390 | 768 | 1280 | 1920 |
|---|---|---|---|---|
| Dashboard | 390 | 768 | 1280 | 1920 |
| Trades | 390 | 768 | 1280 | 1920 |
| Analytics | 390 | 768 | 1280 | 1920 |
| Watchlist | 390 | 768 | 1280 | 1920 |
| System | 390 | 768 | 1280 | 1920 |

**PASS** — no horizontal document scroll anywhere. Cards render only at 390
(Trades 25, Watchlist 7, Analytics 5); the tables return above it.

### The sidebar

| Line | Result |
|---|---|
| Expanded is 200px, rail is 52px | **PASS** — measured |
| Toggle flips it | **PASS**, after the defect below |
| Toggle persists through a reload | **PASS** |
| Labels survive the collapse | **PASS** — clipped to 1px, text still in the DOM, `aria-label` intact |
| 1024 forces the rail, descending | **PASS** — 1024 expanded, 1023 railed |
| 1024 restores it, ascending | **PASS** — with no stored preference |
| 640 switches to overlay | **PASS** — 640 no overlay, 639 overlay |
| A navigation closes the overlay | **PASS** |
| Scrim dismisses it | **PASS** |

### The profile menu

| Line | Result |
|---|---|
| Opens on the avatar | **PASS** |
| Opens by keyboard | **PASS** — focus the trigger, Enter |
| Escape closes | **PASS** |
| Outside click closes | **PASS** |
| A click inside does not close it | **PASS** |
| Focus returns to the trigger | **PASS** |
| The sidebar's own Sign out is gone | **PASS** |

### The avatar

Sidebar mark, profile trigger (with a 2× `srcset`), and the favicon set —
**PASS**. Not on the login card: that card is Jinja and NG57 deletes it, so an
avatar there would be added only to be removed.

### Defect found and fixed

**The sidebar toggle did nothing.** The handler computed the new state and
then wrote its own inverse, so the two cancelled and the class never changed.
The composition rule the unit tests check was correct the whole time — the
handler feeding it was not, which is exactly the gap a walk exists to cover.

### An ambiguity, resolved and recorded

SR21's prose says crossing a breakpoint "re-applies the automatic state",
which read strictly would discard a user's explicit collapse the moment they
resized. Its own step 1 test list says only that crossing below 1024 "forces
the rail regardless of the stored value" — and says nothing about ascending.
The implementation follows the test list: below `md` the rail is forced; above
it the stored preference applies if there is one, and the automatic state if
there is not. Both readings agree on everything the checklist actually names;
they differ only for a user who collapsed deliberately and then resized, and
silently discarding that choice is the worse of the two.
