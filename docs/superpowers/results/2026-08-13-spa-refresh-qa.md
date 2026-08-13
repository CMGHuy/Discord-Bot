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
